# routes/main.py
from flask import Blueprint, render_template, redirect, url_for, session, flash, current_app, request
from flask_login import login_required, current_user
from models import db, TestDefinition, Attempt # Import necessary models
from api_handler import ChatGPTHandler, APIError, AuthenticationError # Import API Handler

bp = Blueprint('main', __name__)

@bp.route('/')
@login_required # Require login for the main page now
def index():
    # Fetch test definitions created by the current user
    user_tests = TestDefinition.query.filter_by(user_id=current_user.id).order_by(TestDefinition.timestamp.desc()).all()

    display_tests = []
    for test_def in user_tests:
        best_score = None
        max_score = float(test_def.question_count) if test_def.question_count > 0 else 0.0
        completed_attempts = Attempt.query.filter_by(test_definition_id=test_def.id, is_complete=True).all()
        if completed_attempts:
            # Ensure scores are not None before finding max
            valid_scores = [a.total_score for a in completed_attempts if a.total_score is not None]
            if valid_scores:
                best_score = max(valid_scores)

        display_tests.append({
            'id': test_def.id,
            'title': test_def.title or "Untitled Test",
            'timestamp': test_def.timestamp,
            'question_count': test_def.question_count,
            'best_score': best_score,
            'max_possible_score': max_score,
            'attempt_count': len(test_def.attempts) # Access attempts relationship
        })

    return render_template('index.html', tests=display_tests)

# --- Theme Routes (moved from app.py, require login) ---
@bp.route('/generate_theme', methods=['POST'])
@login_required
def generate_theme():
    # Check if user has API key set
    if not current_user.api_key_set or not current_user.get_api_key():
        flash("Please set your OpenAI API key in settings first.", "warning")
        return redirect(url_for('settings.account_settings')) # Redirect to settings

    theme_description = request.form.get('theme_description')
    if not theme_description:
        flash("Please enter a theme description.", "warning")
        return redirect(url_for('settings.account_settings')) # Redirect to settings

    try:
        # Get API key for the current user
        api_key = current_user.get_api_key()
        if not api_key: # Double check after decryption
            flash("Could not retrieve your API key.", "danger")
            return redirect(url_for('settings.account_settings'))

        handler = ChatGPTHandler(api_key=api_key)
        css_code = handler.generate_css_theme(theme_description)
        session['custom_css'] = css_code # Store theme in session
        flash("CSS theme generated and applied for this session!", "success")
    except AuthenticationError:
        flash("API Authentication failed. Please check your API key in settings.", "danger")
        # Optionally clear the invalid key flag for the user in DB?
        # current_user.api_key_set = False
        # db.session.commit()
    except (APIError, ValueError, Exception) as e:
        flash(f"Error generating theme: {e}", "danger")
        current_app.logger.error(f"Theme generation error for user {current_user.id}: {e}")

    return redirect(url_for('settings.account_settings')) # Redirect back to settings page

@bp.route('/clear_theme')
@login_required
def clear_theme():
    session.pop('custom_css', None)
    flash("Custom theme cleared for this session.", "info")
    return redirect(url_for('settings.account_settings')) # Redirect back to settings page
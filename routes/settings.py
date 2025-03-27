# routes/settings.py
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from models import db, User
from forms import SettingsForm, ThemeForm # Define these forms
from encryption import encrypt_data, decrypt_data

bp = Blueprint('settings', __name__)

@bp.route('/account', methods=['GET', 'POST'])
@login_required
def account_settings():
    settings_form = SettingsForm()
    theme_form = ThemeForm() # Add theme form here

    if settings_form.validate_on_submit() and 'submit_api_key' in request.form:
        api_key = settings_form.api_key.data
        try:
            # Attempt to validate key roughly before saving (optional)
            # handler = ChatGPTHandler(api_key=api_key) # This makes an API call! Careful.
            # Maybe just check format? if not api_key.startswith("sk-"): raise ValueError("Invalid format")

            current_user.set_api_key(api_key) # Encrypts and sets flag
            db.session.commit()
            flash('OpenAI API Key updated successfully!', 'success')
        except ValueError as e:
            flash(f'Invalid API Key: {e}', 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating API Key: {e}', 'danger')
        return redirect(url_for('settings.account_settings')) # Redirect to refresh

    # Pre-populate API key field carefully (e.g., show '********key' or just 'Set')
    # DO NOT pre-populate the actual key in the form value attribute!
    api_key_status = "Set" if current_user.api_key_set else "Not Set"

    # Theme form is handled by main.generate_theme via POST action

    return render_template('settings/account.html',
                           title='Settings',
                           settings_form=settings_form,
                           theme_form=theme_form,
                           api_key_status=api_key_status)
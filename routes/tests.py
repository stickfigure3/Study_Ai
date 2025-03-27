# routes/tests.py
import json
import string
from datetime import datetime, timezone
from flask import Blueprint, render_template, redirect, url_for, flash, request, session, jsonify, current_app
from flask_login import login_required, current_user
from models import db, User, TestDefinition, Question, Attempt, Answer
from models import create_question_from_dict
from forms import GenerateTestForm # Define this form
from api_handler import ChatGPTHandler, APIError, AuthenticationError
from utils import extract_text_from_pdf
bp = Blueprint('tests', __name__)

# --- Helper: Get API Handler for Current User ---
def get_user_api_handler():
    if not current_user.is_authenticated or not current_user.api_key_set:
        flash("Please log in and set your API key in settings.", "warning")
        return None
    api_key = current_user.get_api_key()
    if not api_key:
        flash("Could not retrieve your API key. Please set it in settings.", "danger")
        # Maybe mark api_key_set as False?
        # current_user.api_key_set = False
        # db.session.commit()
        return None
    try:
        handler = ChatGPTHandler(api_key=api_key)
        return handler
    except ValueError as e: # Handles invalid key format during init
        flash(f"API Key Error: {e}. Please update in settings.", "danger")
        # current_user.api_key_set = False # Mark as not set if init fails
        # db.session.commit()
        return None
    except AuthenticationError:
        flash("API Authentication Failed. Please check your API key in settings.", "danger")
        # current_user.api_key_set = False
        # db.session.commit()
        return None
    except Exception as e:
        flash(f"Error initializing API Handler: {e}", "danger")
        current_app.logger.error(f"API Handler init error for user {current_user.id}: {e}")
        return None

# --- Helper: Check Answer Logic (same as before) ---
def check_answer_logic(question_model, user_input):
    is_correct = None; score = None
    q_type = question_model.question_type
    correct_info = question_model.correct_answer_info # Use property

    if q_type == 'multiple_choice':
        try:
            user_choice_index = int(user_input)
            # Need correct index from stored info
            opts = question_model.options
            correct_index = -1
            if isinstance(correct_info, int) and 0 <= correct_info < len(opts):
                correct_index = correct_info
            elif isinstance(correct_info, str):
                try: correct_index = opts.index(correct_info)
                except ValueError: pass # Try case insensitive below
                if correct_index == -1:
                    try: correct_index = [o.lower() for o in opts].index(correct_info.lower())
                    except ValueError: pass

            is_correct = (user_choice_index == correct_index) if correct_index != -1 else False
            score = 1.0 if is_correct else 0.0
        except (ValueError, TypeError, IndexError): is_correct = False; score = 0.0
    elif q_type == 'fill_in_the_blank':
        correct_answer_str = str(correct_info) if correct_info is not None else ""
        translator = str.maketrans('', '', string.punctuation)
        processed_user = str(user_input).lower().translate(translator).strip()
        processed_correct = correct_answer_str.lower().translate(translator).strip()
        is_correct = (processed_user == processed_correct)
        score = 1.0 if is_correct else 0.0
    elif q_type == 'free_response': is_correct = None; score = None # Graded by API later
    return is_correct, score


# --- Route to Generate New Test Definition ---
@bp.route('/generate', methods=['GET', 'POST'])
@login_required
def generate_test():
    form = GenerateTestForm()
    if form.validate_on_submit():
        # --- 1. Get Handler (Checks API Key) ---
        handler = get_user_api_handler()
        if not handler:
            # Handler function already flashes a message
            return redirect(url_for('settings.account_settings'))

        # --- 2. Initialize Variables ---
        source_text = None
        extracted_from_pdf = False # Flag to know the source

        # --- 3. Get Data from Form ---
        text_input_data = form.text_input.data.strip()
        pdf_file_data = form.pdf_file.data # This is a FileStorage object
        num_questions = form.num_questions.data
        title = form.title.data.strip() or "Untitled Test" # Use strip() and default

        # --- 4. Determine Source Text (Text Area or PDF) ---
        if text_input_data:
            source_text = text_input_data
            current_app.logger.info(f"Using text input for test generation (length: {len(source_text)}).")
        elif pdf_file_data:
            current_app.logger.info(f"Processing uploaded PDF: {pdf_file_data.filename}")
            try:
                # Check filename extension again just in case
                if not pdf_file_data.filename or not pdf_file_data.filename.lower().endswith('.pdf'):
                    flash("Invalid file type uploaded. Please upload a PDF.", "warning")
                    return render_template('tests/generate.html', form=form)

                # Attempt PDF extraction
                extracted_text = extract_text_from_pdf(pdf_file_data.stream)

                if not extracted_text or not extracted_text.strip():
                    flash("Could not extract any readable text from the PDF. It might be empty, image-based, or corrupted.", "danger")
                    return render_template('tests/generate.html', form=form)

                source_text = extracted_text.strip()
                extracted_from_pdf = True
                current_app.logger.info(f"Extracted {len(source_text)} characters from PDF.")

            except Exception as e:
                current_app.logger.error(f"Error processing PDF file '{pdf_file_data.filename}': {e}", exc_info=True) # Log full traceback
                flash(f"An unexpected error occurred while processing the PDF file.", "danger")
                return render_template('tests/generate.html', form=form)
        else:
            # This case should theoretically be caught by form.validate_on_submit()
            # but we add it as a safeguard.
            flash("No source material provided. Please paste text or upload a PDF.", "warning")
            return render_template('tests/generate.html', form=form)

        # --- 5. Check if source_text is valid after processing ---
        if not source_text:
            # This might happen if PDF extraction yielded only whitespace
            flash("Source material appears to be empty after processing.", "danger")
            return render_template('tests/generate.html', form=form)

        # --- 6. Limit Text Length ---
        MAX_TEXT_LENGTH = 8000 # Consider making this configurable
        original_length = len(source_text)
        if original_length > MAX_TEXT_LENGTH:
            source_text = source_text[:MAX_TEXT_LENGTH]
            flash(f"Source text was long ({original_length} chars) and has been truncated to {MAX_TEXT_LENGTH} characters for processing.", "info")
            current_app.logger.info(f"Truncated source text from {original_length} to {len(source_text)} chars.")

        # --- 7. Call API and Process Results ---
        try:
            current_app.logger.info(f"Requesting {num_questions} questions from API for test '{title}'...")
            generated_q_dicts = handler.generate_questions(source_text, num_questions=num_questions)

            if not generated_q_dicts: # Checks for None or empty list
                flash("The AI did not return any questions based on the provided text. Try different text or simplify the request.", "warning")
                current_app.logger.warning(f"API returned no questions for test '{title}'.")
                return render_template('tests/generate.html', form=form)

            current_app.logger.info(f"API returned {len(generated_q_dicts)} potential questions.")

            # --- Create DB Objects ---
            valid_questions_created = 0
            new_test_def = TestDefinition(
                user_id=current_user.id,
                source_text_snippet=source_text[:300], # Store slightly longer snippet
                title=title
            )
            # Add *before* the loop in case of errors during question processing
            db.session.add(new_test_def)
            db.session.flush()

            # Process each dictionary from the API
            for i, q_data in enumerate(generated_q_dicts):
                try:
                    # Use the factory function (imported from utils)
                    q_obj = create_question_from_dict(q_data)

                    # Create the Question DB model instance
                    new_question = Question(
                        # test_definition=new_test_def, # Can assign relationship directly
                        test_definition_id=new_test_def.id, # Or assign FK after flush
                        question_index=i,
                        text=q_obj.text,
                        question_type=q_obj.question_type,
                        hint=getattr(q_obj, 'hint', None)
                    )
                    # Store type-specific info
                    if q_obj.question_type == 'multiple_choice':
                        new_question.options = q_obj.options # Uses JSON setter
                        new_question.correct_answer_info = q_obj.correct_answer_index # Uses JSON setter
                    elif q_obj.question_type == 'fill_in_the_blank':
                        new_question.correct_answer_info = q_obj.correct_answer # Uses JSON setter
                    elif q_obj.question_type == 'free_response':
                        new_question.suggested_answer = q_obj.suggested_answer

                    db.session.add(new_question)
                    valid_questions_created += 1

                except ValueError as e:
                    current_app.logger.warning(f"Skipping question {i+1} for test '{title}' due to parsing error: {e}. Data: {q_data}")
                except Exception as e:
                    # Catch any other unexpected errors during object creation
                    current_app.logger.error(f"Unexpected error creating question object {i+1} for test '{title}': {e}. Data: {q_data}", exc_info=True)
                    # Continue processing other questions

            # --- Final Checks and Commit ---
            if valid_questions_created == 0:
                # If API returned data but NONE could be processed
                flash("API returned data, but no valid questions could be processed into the required format. Please check the source text or try again.", "danger")
                db.session.rollback() # Rollback test definition creation
                current_app.logger.error(f"Failed to process any questions for test '{title}' after API returned {len(generated_q_dicts)} items.")
                return render_template('tests/generate.html', form=form)

            # Commit changes (TestDefinition and all valid Questions)
            db.session.commit()
            current_app.logger.info(f"Successfully created test '{title}' (ID: {new_test_def.id}) with {valid_questions_created} questions for user {current_user.id}.")
            flash(f"Successfully generated test '{title}' with {valid_questions_created} questions!", "success")

            # Report if some questions were skipped
            if valid_questions_created < len(generated_q_dicts):
                skipped_count = len(generated_q_dicts) - valid_questions_created
                flash(f"Warning: {skipped_count} item(s) returned by the API could not be processed due to formatting issues.", "warning")

            # Redirect to start the first attempt
            return redirect(url_for('tests.start_attempt', test_id=new_test_def.id))

        # --- Error Handling for API call or DB operations ---
        except AuthenticationError:
            # This specific error should ideally be caught by get_user_api_handler now
            flash("Authentication failed with OpenAI. Please check your API key in settings.", "danger")
            db.session.rollback() # Rollback any potential partial adds
            return redirect(url_for('settings.account_settings')) # Go to settings
        except (APIError, ValueError) as e: # Catch specific API/Value errors
            db.session.rollback()
            flash(f"Error during question generation: {e}", "danger")
            current_app.logger.error(f"API/Value error during question gen for user {current_user.id}: {e}")
        except Exception as e: # Catch unexpected errors during the process
            db.session.rollback()
            flash(f"An unexpected error occurred during test generation. Please try again.", "danger")
            current_app.logger.error(f"Unexpected error in generate_test for user {current_user.id}: {e}", exc_info=True)

        # If any exception occurred, re-render form
        return render_template('tests/generate.html', form=form)

    # --- Handle GET request or POST with validation errors ---
    elif request.method == 'POST':
        # Log validation errors if POST failed validation
        current_app.logger.warning(f"Test generation form validation failed: {form.errors}")

    return render_template('tests/generate.html', form=form)
# --- Route to Start a New Attempt ---
@bp.route('/<test_id>/start', methods=['GET']) # Changed to GET for link simplicity
@login_required
def start_attempt(test_id):
    test_def = TestDefinition.query.filter_by(id=test_id, user_id=current_user.id).first_or_404()

    # Create new attempt in DB
    new_attempt = Attempt(
        test_definition_id=test_def.id,
        user_id=current_user.id
    )
    db.session.add(new_attempt)
    db.session.commit() # Commit to get the ID

    # Store active attempt in session
    session['active_attempt_id'] = new_attempt.id
    current_app.logger.info(f"User {current_user.id} starting attempt {new_attempt.id} for test {test_id}")

    # Redirect to the first question
    return redirect(url_for('tests.view_question', attempt_id=new_attempt.id, question_index=0))


# --- Route to View/Answer a Question ---
@bp.route('/attempt/<attempt_id>/question/<int:question_index>', methods=['GET', 'POST'])
@login_required
def view_question(attempt_id, question_index):
    attempt = Attempt.query.filter_by(id=attempt_id, user_id=current_user.id).first_or_404()
    test_def = attempt.test_definition # Access via relationship
    questions = Question.query.filter_by(test_definition_id=test_def.id).order_by(Question.question_index).all()

    if attempt.is_complete:
        flash("This attempt is already complete.", "info")
        return redirect(url_for('tests.view_results', attempt_id=attempt.id))

    if not 0 <= question_index < len(questions):
        flash("Invalid question number.", "warning")
        return redirect(url_for('tests.view_question', attempt_id=attempt.id, question_index=attempt.current_question_index))

    # Ensure user isn't skipping ahead in this attempt
    if question_index > attempt.current_question_index:
        flash("Please answer questions in order.", "info")
        return redirect(url_for('tests.view_question', attempt_id=attempt.id, question_index=attempt.current_question_index))

    current_question = questions[question_index]
    question_id = current_question.id

    # Check if already answered in this attempt
    existing_answer = Answer.query.filter_by(attempt_id=attempt.id, question_id=question_id).first()

    if request.method == 'POST':
        if existing_answer:
            flash("You have already answered this question in this attempt.", "info")
            # Re-render showing feedback
            return render_template('tests/question.html',
                                   attempt_id=attempt.id,
                                   question_index=question_index,
                                   question=current_question,
                                   total_questions=len(questions),
                                   answer_details=existing_answer, # Pass DB object
                                   is_last_question=(question_index == len(questions) - 1))

        user_input = request.form.get('user_answer')
        if user_input is None:
            flash("Please provide an answer.", "warning")
            return redirect(url_for('tests.view_question', attempt_id=attempt.id, question_index=question_index))

        # --- Check Answer / Grade FR ---
        is_correct, score = check_answer_logic(current_question, user_input)
        explanation = None # Initialize explanation

        handler = get_user_api_handler()
        if not handler:
            # Allow proceeding without grading/explanation if handler fails? Or block?
            flash("API Handler unavailable. Cannot grade free response or get explanation.", "warning")
            if current_question.question_type == 'free_response': score = 0.0 # Default score if no handler
        else:
            # Grade FR if applicable
            if current_question.question_type == 'free_response':
                try:
                    current_app.logger.info(f"Grading FR for attempt {attempt.id}, Q {question_id}")
                    fr_score = handler.grade_free_response(
                        current_question.text,
                        current_question.suggested_answer,
                        user_input
                    )
                    score = fr_score
                except Exception as e:
                    current_app.logger.error(f"FR Grading error: {e}")
                    flash(f"Could not grade free response: {e}", "warning")
                    score = 0.0 # Default score on error

            # Generate Explanation
            try:
                current_app.logger.info(f"Generating explanation for attempt {attempt.id}, Q {question_id}")
                explanation = handler.generate_explanation(
                    current_question.text,
                    current_question.correct_answer_display,
                    user_input,
                    is_correct
                )
            except Exception as e:
                current_app.logger.error(f"Explanation error: {e}")
                explanation = f"Could not generate explanation: {e}"


        # --- Save Answer to DB ---
        new_answer = Answer(
            attempt_id=attempt.id,
            question_id=question_id,
            user_input=user_input,
            is_correct=is_correct,
            score=score if score is not None else 0.0, # Ensure score is not None
            explanation=explanation
        )
        db.session.add(new_answer)

        # --- Update Attempt State ---
        attempt.current_question_index = question_index + 1
        attempt.total_score += new_answer.score # Add score to total

        if attempt.current_question_index >= len(questions):
            attempt.is_complete = True
            attempt.timestamp_completed = datetime.now(timezone.utc)
            current_app.logger.info(f"Attempt {attempt.id} completed.")

        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"DB Error saving answer/attempt: {e}")
            flash("Error saving your answer. Please try again.", "danger")
            return redirect(url_for('tests.view_question', attempt_id=attempt.id, question_index=question_index))


        # --- Re-render showing feedback ---
        return render_template('tests/question.html',
                               attempt_id=attempt.id,
                               question_index=question_index,
                               question=current_question,
                               total_questions=len(questions),
                               answer_details=new_answer, # Pass the newly created answer
                               is_last_question=(question_index == len(questions) - 1))

    # --- GET Request ---
    return render_template('tests/question.html',
                           attempt_id=attempt.id,
                           question_index=question_index,
                           question=current_question,
                           total_questions=len(questions),
                           answer_details=existing_answer, # Pass if already answered
                           is_last_question=(question_index == len(questions) - 1))


# --- Route to View Results of an Attempt ---
@bp.route('/attempt/<attempt_id>/results')
@login_required
def view_results(attempt_id):
    attempt = Attempt.query.filter_by(id=attempt_id, user_id=current_user.id).first_or_404()
    test_def = attempt.test_definition

    if not attempt.is_complete:
        flash("This attempt is not yet complete.", "warning")
        return redirect(url_for('tests.view_question', attempt_id=attempt.id, question_index=attempt.current_question_index))

    # Fetch questions and their answers for this attempt
    questions = Question.query.filter_by(test_definition_id=test_def.id).order_by(Question.question_index).all()
    answers = Answer.query.filter_by(attempt_id=attempt.id).all()
    answers_dict = {ans.question_id: ans for ans in answers} # Map question_id to answer object

    results_questions = []
    for q in questions:
        results_questions.append({
            'definition': q,
            'attempt_details': answers_dict.get(q.id) # Get Answer object or None
        })

    # Get history of other completed attempts for this test definition by this user
    history = Attempt.query.filter(
        Attempt.test_definition_id == test_def.id,
        Attempt.user_id == current_user.id,
        Attempt.is_complete == True,
        Attempt.id != attempt.id # Exclude current attempt
    ).order_by(Attempt.timestamp_completed.desc()).all()

    return render_template('tests/results.html',
                           test_id=test_def.id, # Pass test_id for restart link
                           attempt=attempt,
                           results_questions=results_questions,
                           history=history)


# --- Route for Hints ---
@bp.route('/hint', methods=['POST'])
@login_required
def get_hint():
    # Requires question_id (from question definition)
    if not request.is_json: return jsonify({"error": "Request must be JSON"}), 400
    data = request.get_json()
    # test_id = data.get('test_id') # We don't strictly need test_id if we have question_id
    question_id = data.get('question_id')
    if not question_id: return jsonify({"error": "Missing 'question_id'"}), 400

    question = Question.query.get(question_id)
    if not question: return jsonify({"error": "Question not found"}), 404
    # Optional: Check if question belongs to a test the user created?
    # if question.test_definition.user_id != current_user.id: return jsonify({"error": "Forbidden"}), 403

    # Return cached hint if available
    if question.hint:
        current_app.logger.info(f"Returning cached hint for Q {question_id}")
        return jsonify({"hint": question.hint})

    handler = get_user_api_handler()
    if not handler: return jsonify({"error": "API handler unavailable."}), 503 # Service unavailable

    try:
        current_app.logger.info(f"Generating hint for Q {question_id}")
        hint_text = handler.generate_hint(question.text)

        # Cache hint in DB
        question.hint = hint_text
        db.session.commit()

        return jsonify({"hint": hint_text})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Hint generation error: {e}")
        return jsonify({"error": f"Error generating hint: {e}"}), 500
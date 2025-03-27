# api_handler.py
import os
import json
import time
import re # Import regex for cleaning CSS
from openai import OpenAI, APIError, RateLimitError, AuthenticationError

# ... (Constants remain the same) ...
DEFAULT_MODEL = "gpt-4o-mini"
MAX_RETRIES = 3
RETRY_DELAY = 5

class ChatGPTHandler:
    # ... (__init__ and _make_api_call remain the same) ...
    def __init__(self, api_key):
        if not api_key:
            raise ValueError("API key is required to initialize ChatGPTHandler.")
        try:
            self.client = OpenAI(api_key=api_key)
            self.client.models.list()
            print("OpenAI client initialized successfully.")
        except AuthenticationError:
            print("AuthenticationError: Invalid OpenAI API key.")
            raise ValueError("Invalid OpenAI API key provided.")
        except Exception as e:
            print(f"Error initializing OpenAI client: {e}")
            raise

    def _make_api_call(self, messages, validation_func=None, max_retries=MAX_RETRIES, is_json_mode=False):
        """Internal method for API calls with retry, validation, and optional JSON mode."""
        last_error = None
        for attempt in range(max_retries):
            try:
                print(f"Attempting API call ({attempt + 1}/{max_retries})...")
                completion_args = {
                    "model": DEFAULT_MODEL,
                    "messages": messages,
                    "temperature": 0.5,
                }
                # Use JSON mode if requested and model supports it (check OpenAI docs)
                # Note: JSON mode requires specific prompt instructions for the model
                if is_json_mode:
                    # Check if the selected model supports JSON mode, adjust if necessary
                    # For example, gpt-3.5-turbo-1106 and later support it.
                    # Might need to change DEFAULT_MODEL if it doesn't.
                    completion_args["response_format"] = {"type": "json_object"}
                    print("Using JSON mode for API call.")


                response = self.client.chat.completions.create(**completion_args)
                content = response.choices[0].message.content.strip()

                print(f"API Response received:\n{content[:200]}...")

                if validation_func:
                    is_valid, validation_details = validation_func(content)
                    if is_valid:
                        print("API response validated successfully.")
                        return content
                    else:
                        print(f"Validation failed for attempt {attempt + 1}: {validation_details}")
                        last_error = ValueError(f"API response failed validation: {validation_details}")
                        # Add feedback for retry if validation failed
                        messages.append({"role": "assistant", "content": content})
                        messages.append({"role": "user", "content": f"The previous response was invalid ({validation_details}). Please adhere strictly to the required format and try again."})

                else:
                    return content # No validation needed

            except (APIError, RateLimitError) as e:
                print(f"API Error on attempt {attempt + 1}: {e}")
                last_error = e
                delay = RETRY_DELAY * (attempt + 1) # Simple linear backoff
                if isinstance(e, RateLimitError):
                    print(f"Rate limit exceeded, waiting {delay*2}s...")
                    time.sleep(delay * 2)
                else:
                    print(f"Waiting {delay}s before retry...")
                    time.sleep(delay)
            except Exception as e:
                print(f"Unexpected error on attempt {attempt + 1}: {e}")
                last_error = e
                time.sleep(RETRY_DELAY * (attempt + 1))

            # Wait before retrying after validation failure
            if isinstance(last_error, ValueError) and attempt < max_retries - 1:
                print(f"Waiting {RETRY_DELAY}s before retrying after validation failure...")
                time.sleep(RETRY_DELAY)

        print(f"API call failed after {max_retries} retries.")
        if last_error:
            raise last_error # Raise the last error encountered (API or Validation)
        else:
            raise APIError("API call failed for an unknown reason after retries.")


    # --- Validation Functions ---
    def _validate_question_json(self, response_content):
        """Validates question JSON. Returns (bool, str_details)."""
        try:
            # Handle potential markdown ```json ... ```
            if response_content.startswith("```json"):
                response_content = re.sub(r"^```json\s*|\s*```$", "", response_content, flags=re.MULTILINE)

            data = json.loads(response_content)

            if not isinstance(data, dict):
                return False, "Response is not a JSON object."
            if 'questions' not in data:
                return False, "JSON missing 'questions' key."
            if not isinstance(data['questions'], list):
                return False, "'questions' is not a list."

            # --- Added Check: Iterate through questions ---
            for i, q_item in enumerate(data['questions']):
                if not isinstance(q_item, dict):
                    # Found an item that is not a dictionary (e.g., a string)
                    return False, f"Item at index {i} in 'questions' list is not a valid JSON object (got type {type(q_item)})."

                # Now we know q_item is a dict, perform previous checks
                required_keys = ('type', 'text', 'answer')
                if not all(k in q_item for k in required_keys):
                    return False, f"Question at index {i} missing required keys {required_keys}. Found: {q_item.keys()}"
                if q_item.get('type') == 'multiple_choice' and 'options' not in q_item:
                    return False, f"Multiple choice question at index {i} missing 'options'."
            # --- End Added Check ---

            return True, "Valid structure"
        except json.JSONDecodeError as e:
            # Provide more context on JSON errors
            error_pos = e.pos
            context_window = 20
            start = max(0, error_pos - context_window)
            end = min(len(e.doc), error_pos + context_window)
            context = e.doc[start:end]
            return False, f"Invalid JSON: {e} near position {error_pos} (context: '...{context}...')"
        except Exception as e:
            return False, f"Unexpected validation error: {e}"

    def _validate_css(self, response_content):
        """Basic validation for CSS. Returns (bool, str_details). Allows backticks but warns."""
        content = response_content.strip()
        details = []
        is_valid = True

        if not content:
            return False, "CSS response is empty."

        # Check for obvious non-CSS text
        if content.lower().startswith(("sure, here", "here is", "certainly", "okay,")):
            details.append("Contains introductory text.")
            is_valid = False # Fail on intro text

        # Check for basic structure, but don't fail solely on this if backticks are present
        if '{' not in content or '}' not in content or ':' not in content:
            if "```" not in content: # Only fail if no backticks AND no structure
                details.append("Lacks basic CSS structure ({, }, :).")
                is_valid = False

        # Warn about backticks, but don't fail the validation step here
        if "```" in content:
            details.append("Warning: Contains markdown backticks (will be cleaned).")
            # is_valid remains True if this is the only issue

        if not details:
            details.append("Passed basic validation.")

        return is_valid, " ".join(details)

    def _validate_score_json(self, response_content):
        """Validates score JSON. Expects {"score": float}. Returns (bool, str_details)."""
        try:
            # Handle potential markdown ```json ... ```
            if response_content.startswith("```json"):
                response_content = re.sub(r"^```json\s*|\s*```$", "", response_content, flags=re.MULTILINE)

            data = json.loads(response_content)
            if not isinstance(data, dict):
                return False, "Response is not a JSON object."
            if 'score' not in data:
                return False, "JSON missing 'score' key."
            score = data['score']
            if not isinstance(score, (int, float)):
                return False, f"'score' is not a number (got {type(score)})."
            if not (0.0 <= score <= 1.0):
                return False, f"'score' ({score}) is outside the valid range [0.0, 1.0]."
            return True, "Valid score format."
        except json.JSONDecodeError as e:
            return False, f"Invalid JSON: {e}. Response snippet: {response_content[:100]}"
        except Exception as e:
            return False, f"Unexpected validation error: {e}"

    # --- Generation Methods ---
    def generate_questions(self, text, num_questions=5, question_types=['multiple_choice', 'fill_in_the_blank', 'free_response']):
        """Generates study questions. Uses JSON mode."""
        # ... (Prompt remains largely the same, but ensure it asks for JSON object explicitly) ...
        type_string = ", ".join(question_types)
        prompt = f"""
Based on the following text, generate {num_questions} study questions...
Include a mix of the following types ONLY: {type_string}. DO NOT use any other type names like "text".

Format the output STRICTLY as a single JSON object containing a single key "questions".
The value of "questions" should be a JSON array.
Each element in the array MUST be a JSON object representing one question with the following keys:
- "type": A string, MUST be EXACTLY one of: "multiple_choice", "fill_in_the_blank", or "free_response".
- "text": A string containing the question text. For "fill_in_the_blank", include '___' as the placeholder.
- "options" (ONLY for "multiple_choice"): An array of strings representing the choices.
- "answer":
    - For "multiple_choice": The 0-based index (integer) or the exact string content of the correct option. Prefer the index.
    - For "fill_in_the_blank": A string representing the correct word(s) for the blank.
    - For "free_response": A brief suggested answer or key points (string). Use an empty string "" if not applicable.

Example formats MUST be followed precisely:
{{ "type": "multiple_choice", "text": "...", "options": ["...", "..."], "answer": 0 }}
{{ "type": "fill_in_the_blank", "text": "... ___ ...", "answer": "..." }}
{{ "type": "free_response", "text": "...", "answer": "..." }}

Ensure the entire output is ONLY the JSON object, starting with {{ and ending with }}. NO extra text, NO explanations, NO markdown.

Source Text:
---
{text[:3000]}
---
"""
        messages = [{"role": "system", "content": "You are a helpful assistant designed to create study questions. Respond ONLY with the requested JSON object."},
                    {"role": "user", "content": prompt}]

        try:
            # Request JSON mode
            response_content = self._make_api_call(messages, validation_func=self._validate_question_json, is_json_mode=True)

            # Clean potential markdown just in case JSON mode still adds it (less likely)
            if response_content.startswith("```json"):
                response_content = re.sub(r"^```json\s*|\s*```$", "", response_content, flags=re.MULTILINE)

            data = json.loads(response_content)
            questions_data = data.get('questions', []) # Get the list of dicts

            # --- REMOVED THE LOOP THAT CREATED Question OBJECTS ---
            # generated_questions = []
            # for q_data in questions_data:
            #     try:
            #         # This call is moved to the route
            #         # question = create_question_from_dict(q_data)
            #         # generated_questions.append(question)
            #         pass # Just validate structure was okay earlier
            #     except ValueError as e:
            #          print(f"Skipping question due to parsing error: {e}. Data: {q_data}")
            #     except Exception as e:
            #          print(f"Unexpected error creating question object: {e}. Data: {q_data}")

            print(f"API returned {len(questions_data)} potential questions.")
            # Return the raw list of dictionaries
            return questions_data


        except (APIError, ValueError, json.JSONDecodeError) as e:
            print(f"Error generating questions: {e}")
            raise e
        except Exception as e:
            print(f"An unexpected error occurred in generate_questions: {e}")
            raise ValueError("Failed to generate questions due to an unexpected error.")


    def generate_hint(self, question_text, context_text=""):
        # ... (Remains the same) ...
        prompt = f"""
        A student needs a hint for the following study question.
        Provide a helpful clue or piece of related information that guides them towards the answer, but **DO NOT give away the final answer directly**.
        The hint should make them think or recall the relevant concept. Keep the hint concise (1-2 sentences).

        Question:
        "{question_text}"
        """
        if context_text:
            prompt += f"\nRelevant context from the source material (optional):\n---\n{context_text[:500]}\n---\n"
        prompt += "\nHint:"

        messages = [{"role": "system", "content": "You are a helpful study assistant providing hints for questions without revealing the answer."},
                    {"role": "user", "content": prompt}]
        try:
            # No complex validation needed, just expect text back
            hint_text = self._make_api_call(messages, validation_func=None)
            print(f"Hint generated successfully for: {question_text[:50]}")
            return hint_text
        except APIError as e:
            print(f"Error generating hint: {e}")
            raise # Re-raise to be handled by the Flask route
        except Exception as e:
            print(f"An unexpected error occurred in generate_hint: {e}")
            raise ValueError("Failed to generate hint due to an unexpected error.")


    def generate_explanation(self, question_text, correct_answer_display, user_answer=None, is_correct=None):
        # ... (Remains the same) ...
        prompt = f"""
        Explain briefly (1-3 sentences) why the answer to the following question is correct.
        Focus on the core concept being tested.

        Question:
        "{question_text}"

        Correct Answer:
        "{correct_answer_display}"
        """
        # ... (Include user answer/status in prompt if available - same as before) ...
        if user_answer is not None and is_correct is not None:
            status = "correctly" if is_correct else "incorrectly"
            prompt += f'\nThe student answered "{user_answer}" ({status}). '
            if not is_correct:
                prompt += "Briefly clarify the misunderstanding if possible, based on the correct answer."
            else:
                prompt += "Reinforce why their understanding is correct."
        prompt += "\n\nExplanation:"

        messages = [{"role": "system", "content": "You are an educational assistant explaining the reasoning behind answers."},
                    {"role": "user", "content": prompt}]

        try:
            explanation_text = self._make_api_call(messages, validation_func=None)
            print(f"Explanation generated successfully for: {question_text[:50]}")
            if explanation_text.startswith('"') and explanation_text.endswith('"'):
                explanation_text = explanation_text[1:-1]
            return explanation_text
        except APIError as e:
            print(f"Error generating explanation: {e}")
            raise
        except Exception as e:
            print(f"An unexpected error occurred in generate_explanation: {e}")
            raise ValueError("Failed to generate explanation due to an unexpected error.")


    def generate_css_theme(self, theme_description):
        """Generates CSS rules based on a theme description. Cleans output."""
        prompt = f"""
        Generate CSS code ONLY to style a simple web application based on the following theme description.
        The application uses Bootstrap 5, so target common Bootstrap classes and standard HTML elements (body, .navbar, .btn, .btn-primary, .card, .alert, h1, p, a).
        Do NOT include any explanations or comments outside CSS comments (/* */).
        ABSOLUTELY NO MARKDOWN formatting like ```css or ```.
        The output must be PURE CSS code ONLY, suitable for direct embedding in a <style> tag.

        Theme Description: "{theme_description}"

        CSS Code:
        """
        messages = [{"role": "system", "content": "You are a CSS generator. Output ONLY valid CSS code based on the user's theme description. NO MARKDOWN."},
                    {"role": "user", "content": prompt}]

        try:
            # Use the updated CSS validation (warns on backticks, fails on intro text)
            css_code = self._make_api_call(messages, validation_func=self._validate_css)

            # --- Explicitly clean the output ---
            # Remove markdown code blocks (```css ... ``` or just ``` ... ```)
            cleaned_css = re.sub(r"^```[a-z]*\s*|\s*```$", "", css_code, flags=re.MULTILINE | re.IGNORECASE).strip()

            # Remove potential leading non-CSS text if validation missed it (less likely now)
            lines = cleaned_css.splitlines()
            first_meaningful_line = 0
            for i, line in enumerate(lines):
                if line.strip().startswith(('/', '{', '.', '#', '@', '*')) or ':' in line:
                    first_meaningful_line = i
                    break
            cleaned_css = "\n".join(lines[first_meaningful_line:])


            print(f"CSS theme generated and cleaned successfully for: {theme_description}")
            return cleaned_css

        except (APIError, ValueError) as e: # Catch validation errors too
            print(f"Error generating CSS theme: {e}")
            raise
        except Exception as e:
            print(f"An unexpected error occurred in generate_css_theme: {e}")
            raise ValueError("Failed to generate CSS theme due to an unexpected error.")

    def grade_free_response(self, question_text, suggested_answer, user_answer):
        """
        Uses API to grade a free-response answer against a suggested answer.

        Returns:
            float: Score between 0.0 and 1.0.
        """
        prompt = f"""
        Evaluate the student's answer to the following question based on the provided suggested answer.
        Determine how well the student's answer captures the key points or concepts of the suggested answer.
        Respond ONLY with a JSON object containing a single key "score", where the value is a floating-point number between 0.0 (completely incorrect/irrelevant) and 1.0 (perfectly correct/captures all key points).

        Question:
        "{question_text}"

        Suggested Answer:
        "{suggested_answer}"

        Student's Answer:
        "{user_answer}"

        JSON Response:
        """
        messages = [{"role": "system", "content": "You are an impartial grader evaluating student answers. Respond ONLY with a JSON object like {\"score\": float_value}."},
                    {"role": "user", "content": prompt}]

        try:
            # Use JSON mode and validation
            response_content = self._make_api_call(messages, validation_func=self._validate_score_json, is_json_mode=True)

            # Clean potential markdown just in case
            if response_content.startswith("```json"):
                response_content = re.sub(r"^```json\s*|\s*```$", "", response_content, flags=re.MULTILINE)

            data = json.loads(response_content)
            score = float(data['score'])
            print(f"Free response graded. Score: {score} for question: {question_text[:50]}...")
            return score

        except (APIError, ValueError, json.JSONDecodeError) as e:
            print(f"Error grading free response: {e}")
            # Decide on fallback score - 0.0 seems safest if grading fails
            return 0.0
        except Exception as e:
            print(f"An unexpected error occurred during free response grading: {e}")
            return 0.0 # Fallback score
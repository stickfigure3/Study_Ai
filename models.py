# models.py
import uuid
import string
import json # For storing list/dict data
from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin # Import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from encryption import encrypt_data, decrypt_data # Import encryption functions

db = SQLAlchemy() # Initialize SQLAlchemy

# --- Association Table (if needed) ---

# --- Main Models ---
class User(UserMixin, db.Model):
    # ... (User definition - keep as is) ...
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    encrypted_api_key = db.Column(db.String(512), nullable=True)
    api_key_set = db.Column(db.Boolean, default=False, nullable=False)
    test_definitions = db.relationship('TestDefinition', backref='creator', lazy=True, cascade="all, delete-orphan")
    attempts = db.relationship('Attempt', backref='user', lazy=True, cascade="all, delete-orphan")
    def set_password(self, password): self.password_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)
    def set_api_key(self, api_key):
        if api_key: self.encrypted_api_key = encrypt_data(api_key); self.api_key_set = True
        else: self.encrypted_api_key = None; self.api_key_set = False
    def get_api_key(self): return decrypt_data(self.encrypted_api_key) if self.encrypted_api_key else None
    def __repr__(self): return f'<User {self.username}>'


class TestDefinition(db.Model):
    # ... (TestDefinition definition - keep as is) ...
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    source_text_snippet = db.Column(db.Text, nullable=True)
    title = db.Column(db.String(200), nullable=True, default="Untitled Test")
    questions = db.relationship('Question', backref='test_definition', lazy=True, cascade="all, delete-orphan")
    attempts = db.relationship('Attempt', backref='test_definition', lazy=True, cascade="all, delete-orphan")
    @property
    def question_count(self): return len(self.questions)


class Question(db.Model):
    # ... (Question base class definition - keep as is) ...
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    test_definition_id = db.Column(db.String(36), db.ForeignKey('test_definition.id'), nullable=False)
    question_index = db.Column(db.Integer, nullable=False)
    text = db.Column(db.Text, nullable=False)
    question_type = db.Column(db.String(50), nullable=False)
    options_json = db.Column(db.Text, nullable=True)
    correct_answer_info_json = db.Column(db.Text, nullable=True)
    suggested_answer = db.Column(db.Text, nullable=True)
    hint = db.Column(db.Text, nullable=True)
    answers = db.relationship('Answer', backref='question', lazy=True, cascade="all, delete-orphan")
    @property
    def options(self): return json.loads(self.options_json) if self.options_json else []
    @options.setter
    def options(self, value): self.options_json = json.dumps(value) if value else None
    @property
    def correct_answer_info(self): return json.loads(self.correct_answer_info_json) if self.correct_answer_info_json else None
    @correct_answer_info.setter
    def correct_answer_info(self, value): self.correct_answer_info_json = json.dumps(value) if value is not None else None
    @property
    def correct_answer_display(self):
        q_type = self.question_type; info = self.correct_answer_info
        if q_type == 'multiple_choice':
            try:
                opts = self.options
                if isinstance(info, int) and 0 <= info < len(opts): return opts[info]
                elif isinstance(info, str):
                    if info in opts: return info
                    info_lower = info.lower()
                    for opt in opts:
                        if opt.lower() == info_lower: return opt
                return "N/A (Invalid Info)"
            except Exception: return "N/A (Error)"
        elif q_type == 'fill_in_the_blank': return str(info) if info is not None else "N/A"
        elif q_type == 'free_response': return self.suggested_answer or "No suggested answer."
        return "N/A"

# ---> ADD THE SUBCLASS DEFINITIONS HERE <---

# Note: These subclasses don't need extra DB columns if all varying data
# is stored in the Question base class (options_json, correct_answer_info_json, etc.)
# They primarily exist for the factory function to return specific types,
# although they *could* have specific methods later if needed.
# If they don't add any new attributes or methods beyond the base Question,
# you could even simplify the factory to just return Question instances
# and rely solely on the question_type string, but having distinct classes
# can be clearer.

class MultipleChoiceQuestion(Question):
    """Represents a multiple-choice question conceptually."""
    # You might add specific methods here later if needed
    pass

class FillInTheBlankQuestion(Question):
    """Represents a fill-in-the-blank question conceptually."""
    pass

class FreeResponseQuestion(Question):
    """Represents a free-response question conceptually."""
    pass

# ---> END OF ADDED SUBCLASSES <---


class Attempt(db.Model):
    # ... (Attempt definition - keep as is) ...
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    test_definition_id = db.Column(db.String(36), db.ForeignKey('test_definition.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    timestamp_started = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    timestamp_completed = db.Column(db.DateTime, nullable=True)
    total_score = db.Column(db.Float, default=0.0, nullable=False)
    is_complete = db.Column(db.Boolean, default=False, nullable=False)
    current_question_index = db.Column(db.Integer, default=0, nullable=False)
    answers = db.relationship('Answer', backref='attempt', lazy='dynamic', cascade="all, delete-orphan")
    @property
    def max_possible_score(self): return float(self.test_definition.question_count) if self.test_definition else 0.0


class Answer(db.Model):
    # ... (Answer definition - keep as is) ...
    id = db.Column(db.Integer, primary_key=True)
    attempt_id = db.Column(db.String(36), db.ForeignKey('attempt.id'), nullable=False)
    question_id = db.Column(db.String(36), db.ForeignKey('question.id'), nullable=False)
    user_input = db.Column(db.Text, nullable=True)
    is_correct = db.Column(db.Boolean, nullable=True)
    score = db.Column(db.Float, nullable=True)
    explanation = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    __table_args__ = (db.UniqueConstraint('attempt_id', 'question_id', name='_attempt_question_uc'),)


# --- Factory Function (Keep at the end) ---
def create_question_from_dict(data):
    """Factory function to create specific question objects."""
    # Now the classes MultipleChoiceQuestion, etc., are defined above

    q_type = data.get('type', '').lower()
    text = data.get('text', '')

    if not text:
        raise ValueError("Question data missing 'text' field.")

    if q_type == 'multiple_choice':
        options = data.get('options')
        answer_info = data.get('answer')
        if options is None or answer_info is None:
            raise ValueError("Multiple choice data missing 'options' or 'answer'.")
        # Create conceptual object (doesn't directly map to DB table beyond Question)
        # We need to extract info needed for the base Question DB model
        temp_obj = MultipleChoiceQuestion() # Use the class defined above
        temp_obj.text = text
        temp_obj.question_type = 'multiple_choice'
        temp_obj.options = options # Store options temporarily
        temp_obj.correct_answer_info = answer_info # Store raw answer info temporarily
        # Determine correct index for storage if possible (optional here, could do in route)
        try:
            opts = temp_obj.options
            if isinstance(answer_info, int) and 0 <= answer_info < len(opts): temp_obj.correct_answer_index = answer_info
            elif isinstance(answer_info, str):
                try: temp_obj.correct_answer_index = opts.index(answer_info)
                except ValueError: temp_obj.correct_answer_index = [o.lower() for o in opts].index(answer_info.lower())
            else: temp_obj.correct_answer_index = None # Indicate failure
        except: temp_obj.correct_answer_index = None # Indicate failure

        return temp_obj # Return the temporary object holding extracted data

    elif q_type == 'fill_in_the_blank':
        answer = data.get('answer')
        if answer is None:
            raise ValueError("Fill in the blank data missing 'answer'.")
        temp_obj = FillInTheBlankQuestion() # Use the class defined above
        temp_obj.text = text
        temp_obj.question_type = 'fill_in_the_blank'
        temp_obj.correct_answer = answer # Store answer temporarily
        temp_obj.correct_answer_info = answer # Also store in generic info field
        return temp_obj

    elif q_type == 'free_response' or q_type == 'text': # Handle 'text' as free_response
        suggested = data.get('suggested_answer', '')
        if suggested == '' and 'answer' in data:
            suggested = data.get('answer','')
        temp_obj = FreeResponseQuestion() # Use the class defined above
        temp_obj.text = text
        temp_obj.question_type = 'free_response' # Standardize type
        temp_obj.suggested_answer = suggested # Store suggested answer temporarily
        return temp_obj

    else:
        raise ValueError(f"Unsupported question type: {q_type}")
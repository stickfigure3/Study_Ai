# forms.py
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, TextAreaField, IntegerField, FileField
from wtforms.validators import DataRequired, Length, EqualTo, ValidationError, Optional, NumberRange, Email # Added Email
from flask_wtf.file import FileAllowed
from models import User # Import User model for validation

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=4, max=80)])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Sign In')

class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=4, max=80)])
    # email = StringField('Email', validators=[DataRequired(), Email()]) # Optional: Add email
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    password2 = PasswordField(
        'Repeat Password', validators=[DataRequired(), EqualTo('password', message='Passwords must match.')])
    submit = SubmitField('Register')

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user is not None:
            raise ValidationError('Please use a different username.')

    # def validate_email(self, email): # If using email
    #     user = User.query.filter_by(email=email.data).first()
    #     if user is not None:
    #         raise ValidationError('Please use a different email address.')


class SettingsForm(FlaskForm):
    api_key = StringField('OpenAI API Key', validators=[Optional(), Length(min=10)]) # Optional allows clearing it
    submit_api_key = SubmitField('Update API Key')

class ThemeForm(FlaskForm):
    theme_description = StringField('Theme Description', validators=[DataRequired(), Length(min=3, max=100)])
    submit_theme = SubmitField('Generate Theme')


class GenerateTestForm(FlaskForm):
    title = StringField('Test Title', validators=[Optional(), Length(max=200)])
    text_input = TextAreaField('Paste Text', validators=[Optional()])
    pdf_file = FileField('Upload PDF', validators=[
        Optional(),
        FileAllowed(['pdf'], 'PDF files only!')
    ])
    num_questions = IntegerField('Number of Questions', default=5, validators=[
        DataRequired(),
        NumberRange(min=1, max=25, message='Must be between 1 and 25 questions.')
    ])
    submit = SubmitField('Generate Questions')

    # Custom validation to ensure text or PDF is provided
    def validate(self, extra_validators=None):
        # Standard validation first
        if not super(GenerateTestForm, self).validate(extra_validators):
            return False
        # Custom check
        if not self.text_input.data and not self.pdf_file.data:
            msg = 'Please paste text or upload a PDF file.'
            self.text_input.errors.append(msg)
            self.pdf_file.errors.append(msg)
            return False
        return True
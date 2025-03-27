# app.py
import os
import uuid
import json
import string
from datetime import datetime, timezone
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, Blueprint
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, TextAreaField, IntegerField, FileField
from wtforms.validators import DataRequired, Length, EqualTo, ValidationError, Optional, NumberRange

# --- App Initialization ---
from config import Config
from models import db, User, TestDefinition, Question, Attempt, Answer # Import models
from api_handler import ChatGPTHandler, APIError, AuthenticationError
from utils import extract_text_from_pdf, extract_text_from_pdf # Assuming utils has PDF extractor
from encryption import encrypt_data, decrypt_data # Import encryption

# --- Flask Extensions ---
migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = 'auth.login' # Redirect to login page if @login_required fails
login_manager.login_message_category = 'info' # Flash message category

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Application Factory ---
def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    # --- Blueprints ---
    from routes.main import bp as main_bp
    app.register_blueprint(main_bp)

    from routes.auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    from routes.tests import bp as tests_bp
    app.register_blueprint(tests_bp, url_prefix='/tests')

    from routes.settings import bp as settings_bp
    app.register_blueprint(settings_bp, url_prefix='/settings')

    # --- Helper Functions (Context Processors, etc.) ---
    @app.context_processor
    def inject_user():
        # Make current_user available in all templates
        return dict(current_user=current_user)

    # --- Global Error Handlers (Optional) ---
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback() # Rollback session in case of DB error
        return render_template('500.html'), 500

    # --- API Handler Helper ---
    # This function now needs to be accessible within request context
    # We can define it here or pass 'app' context around carefully.
    # Or, better, get the key within the route where it's needed.

    return app

# --- Create App Instance ---
# This structure is better for Flask-Migrate and testing
app = create_app()

# --- Main Execution ---
if __name__ == '__main__':
    # Use Gunicorn for production, Flask dev server for local
    port = int(os.environ.get('PORT', 5003)) # Yet another port
    # Debug should be False in production (set via env var ideally)
    app.run(debug=os.environ.get('FLASK_DEBUG', 'True').lower() == 'true', host='0.0.0.0', port=port)
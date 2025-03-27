# config.py
import os
from dotenv import load_dotenv

load_dotenv() # Load environment variables from .env file

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'you-should-really-change-this'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///study_app.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- Updated ENCRYPTION_KEY loading ---
    ENCRYPTION_KEY = os.environ.get('ENCRYPTION_KEY')
    if not ENCRYPTION_KEY:
        # Raise a more critical error if the key is missing in production
        # For development, you might still want a warning, but it shouldn't proceed without a real key.
        raise ValueError("CRITICAL ERROR: ENCRYPTION_KEY environment variable not set. Generate one using Fernet.generate_key()")
    # --- End of update ---

    # OpenAI API Key is per-user
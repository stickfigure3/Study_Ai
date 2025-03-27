# encryption.py
from cryptography.fernet import Fernet, InvalidToken
from flask import current_app
import base64 # Import base64 for potential validation if needed

def get_fernet():
    """Initializes Fernet with the key from app config."""
    key_str = current_app.config.get('ENCRYPTION_KEY') # Get the key string from config
    if not key_str:
        raise ValueError("Encryption key not configured in the application.")

    try:
        # The key from .env should already be in the correct base64 format.
        # Fernet expects bytes, so encode the string.
        key_bytes = key_str.encode('utf-8')

        # Optional but recommended: Validate the key format before creating Fernet instance
        # This checks if it's valid base64 and 32 bytes long after decoding.
        decoded_key = base64.urlsafe_b64decode(key_bytes)
        if len(decoded_key) != 32:
            raise ValueError("Decoded encryption key is not 32 bytes long.")

        # If validation passes, create the Fernet instance with the original base64 bytes
        return Fernet(key_bytes)
    except (TypeError, ValueError, base64.binascii.Error) as e:
        # Catch errors during encoding, decoding, or if the key is invalid format
        raise ValueError(f"Invalid ENCRYPTION_KEY format in configuration: {e}")
    except Exception as e:
        # Catch any other unexpected errors during Fernet initialization
        raise ValueError(f"Error initializing Fernet: {e}")


def encrypt_data(data_str):
    """Encrypts a string."""
    if not data_str:
        return None
    f = get_fernet() # Get initialized Fernet instance
    return f.encrypt(data_str.encode('utf-8')).decode('utf-8') # Encrypt bytes, return string

def decrypt_data(encrypted_str):
    """Decrypts a string. Returns None if decryption fails."""
    if not encrypted_str:
        return None
    f = get_fernet() # Get initialized Fernet instance
    try:
        # Decrypt expects bytes, returns bytes
        decrypted_bytes = f.decrypt(encrypted_str.encode('utf-8'))
        return decrypted_bytes.decode('utf-8') # Decode bytes back to string
    except InvalidToken:
        current_app.logger.error("Failed to decrypt data: Invalid token (key mismatch or data corruption)")
        return None
    except Exception as e:
        current_app.logger.error(f"Failed to decrypt data: {e}")
        return None
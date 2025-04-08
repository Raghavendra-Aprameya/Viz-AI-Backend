import bcrypt
from cryptography.fernet import Fernet
from app.core.settings import settings

ENCRYPTION_KEY = settings.ENCRYPTION_KEY

if not ENCRYPTION_KEY:
    raise ValueError("ENCRYPTION_KEY is missing in environment variables!")

cipher = Fernet(ENCRYPTION_KEY)

def encrypt_string(string_value: str) -> str:
    return cipher.encrypt(string_value.encode()).decode()

def decrypt_string(encrypted_string_value: str) -> str:
    return cipher.decrypt(encrypted_string_value.encode()).decode()

def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

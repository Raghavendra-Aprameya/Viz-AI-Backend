import jwt
import datetime
from app.core.settings import settings  

# Load secret keys and settings
SECRET_KEY = settings.SECRET_KEY
REFRESH_SECRET_KEY = settings.REFRESH_SECRET_KEY
ALGORITHM = settings.ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES
REFRESH_TOKEN_EXPIRE_DAYS = settings.REFRESH_TOKEN_EXPIRE_DAYS

def create_access_token(user_id: int):
    """ Generate an access token """
    expire = datetime.datetime.utcnow() + datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),  # Store user ID in 'sub'
        "iat": datetime.datetime.utcnow(),
        "exp": expire
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def create_refresh_token(user_id: int):
    """ Generate a refresh token """
    expire = datetime.datetime.utcnow() + datetime.timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": str(user_id),  # Store user ID in 'sub'
        "iat": datetime.datetime.utcnow(),
        "exp": expire
    }
    return jwt.encode(payload, REFRESH_SECRET_KEY, algorithm=ALGORITHM)

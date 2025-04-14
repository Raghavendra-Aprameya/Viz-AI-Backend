"""
    This module contains the settings for the application.
"""
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """
    This class contains the settings for the application.
    """ 
    DB_URI: str
    SECRET_KEY: str
    REFRESH_SECRET_KEY: str 
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int
    REFRESH_TOKEN_EXPIRE_DAYS: int
    # LLM_URI: str
    ENCRYPTION_KEY: str
    class Config:
        """
        This class contains the configuration for the settings.
        """
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings(_env_file=".env", _env_file_encoding="utf-8")

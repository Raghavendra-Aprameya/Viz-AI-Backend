"""
Authentication Router

This module defines authentication-related routes for user registration, login, and token refresh.

Routes:
    - POST /register-super-admin: Register a new super admin user.
    - POST /login: Authenticate a user and return tokens.
    - POST /refresh-token: Refresh the access token using a refresh token.
"""


from fastapi import APIRouter, status, Response, Depends
from sqlalchemy.orm import Session

from app.schemas import UserRequest, UserResponse, LoginData
from app.services.authServices import register_user, login_user, refresh_token
from app.core.db import get_db

auth_router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

@auth_router.post("/register-super-admin", status_code=status.HTTP_201_CREATED, response_model=dict)
async def register(user: UserRequest, response: Response, db: Session = Depends(get_db)):
    """
    Register a new super admin user.

    Args:
        user (UserRequest): The user registration data.
        response (Response): FastAPI response object for setting headers/cookies.
        db (Session): SQLAlchemy database session dependency.

    Returns:
        dict: A dictionary containing a success message or authentication tokens.
    """
    return await register_user(user, response, db)


@auth_router.post("/login", response_model=dict)
async def login(login_data: LoginData, response: Response, db: Session = Depends(get_db)):
    """
    Authenticate a user and return access and refresh tokens.

    Args:
        login_data (LoginData): The user login credentials.
        response (Response): FastAPI response object for setting headers/cookies.
        db (Session): SQLAlchemy database session dependency.

    Returns:
        dict: A dictionary containing access and refresh tokens.
    """
    return await login_user(login_data, response, db)


@auth_router.post("/refresh-token", response_model=dict)
async def refresh_token_route(refresh_token_str: str, db: Session = Depends(get_db)):
    """
    Refresh an access token using a valid refresh token.

    Args:
        refresh_token_str (str): The refresh token string.
        db (Session): SQLAlchemy database session dependency.

    Returns:
        dict: A dictionary containing a new access token.
    """
    return await refresh_token(refresh_token_str, db)

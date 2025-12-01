"""
Authentication Router

This module defines authentication-related routes for user registration, login, and token refresh.

Routes:
    - POST /register-super-admin: Register a new super admin user.
    - POST /login: Authenticate a user and return tokens.
    - POST /refresh-token: Refresh the access token using a refresh token.
"""


from fastapi import APIRouter, status, Response, Depends, HTTPException
from sqlalchemy.orm import Session

from app.schemas import (
    UserRequest, 
    UserResponse, 
    LoginData,
    UpdateProfileRequest,
    ChangePasswordRequest,
    DeleteAccountRequest,
    UpdateProfileResponse,
    ChangePasswordResponse,
    DeleteAccountResponse
)
from app.services.authServices import (
    register_user, 
    login_user, 
    refresh_token,
    update_profile,
    change_password,
    delete_account
)
from app.core.db import get_db
from app.utils.token_parser import get_current_user
from uuid import UUID
# from app.utils.calculate_time import track_and_store_time
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


@auth_router.put("/profile/update", status_code=status.HTTP_200_OK, response_model=UpdateProfileResponse)
async def update_profile_route(
    data: UpdateProfileRequest,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    """
    Update user profile information (username and/or email).

    Args:
        data (UpdateProfileRequest): The profile update data.
        db (Session): SQLAlchemy database session dependency.
        token_payload (dict): Authenticated user's token payload.

    Returns:
        UpdateProfileResponse: Success message with updated user information.
    """
    user_id = UUID(token_payload.get("sub"))
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload"
        )
    
    return await update_profile(user_id, data, db)


@auth_router.put("/profile/change-password", status_code=status.HTTP_200_OK, response_model=ChangePasswordResponse)
async def change_password_route(
    data: ChangePasswordRequest,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    """
    Change user password.

    Args:
        data (ChangePasswordRequest): Contains current_password and new_password.
        db (Session): SQLAlchemy database session dependency.
        token_payload (dict): Authenticated user's token payload.

    Returns:
        ChangePasswordResponse: Success message.
    """
    user_id = UUID(token_payload.get("sub"))
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload"
        )
    
    return await change_password(user_id, data, db)


@auth_router.delete("/profile/delete-account", status_code=status.HTTP_200_OK, response_model=DeleteAccountResponse)
async def delete_account_route(
    data: DeleteAccountRequest,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    """
    Delete user account after password confirmation.

    Args:
        data (DeleteAccountRequest): Contains password for confirmation.
        db (Session): SQLAlchemy database session dependency.
        token_payload (dict): Authenticated user's token payload.

    Returns:
        DeleteAccountResponse: Success message.
    """
    user_id = UUID(token_payload.get("sub"))
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload"
        )
    
    return await delete_account(user_id, data, db)

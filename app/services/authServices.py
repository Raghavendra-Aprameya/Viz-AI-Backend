from fastapi import APIRouter, status, Depends, Response, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

import bcrypt
import jwt

from app.core.db import get_db
from app.core.settings import settings
from app.models.schema_models import UserModel  # SQLAlchemy ORM model
from app.schemas import LoginData, UserRequest, UserResponse
from app.utils.jwt import create_access_token, create_refresh_token
from app.core.db import engine
from app.models.schema_models import Base


async def register_user(user: UserRequest, response: Response, db: Session = None) -> dict:
    """
    Register a new user (super admin).

    Args:
        user (UserRequest): Contains the username, email, and password.
        response (Response): FastAPI response object, used to modify response headers.
        db (Session, optional): SQLAlchemy session. Required for database operations.

    Returns:
        dict: A success message with user info and authentication tokens.

    Raises:
        HTTPException: If the user already exists or another error occurs.
    """
    try:
        # Ensure DB tables are created (mostly for development/test environments)
        Base.metadata.create_all(engine)

        # Check if a user with the same username already exists
        existing_user = db.query(UserModel).filter(UserModel.username == user.username).first()
        if existing_user:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User already exists")

        # Hash the password securely
        salt = bcrypt.gensalt()
        hashed_password = bcrypt.hashpw(user.password.encode(), salt).decode()

        # Create and persist new user in DB
        new_user = UserModel(
            username=user.username,
            password=hashed_password,
            email=user.email
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        # Generate JWT tokens
        access_token = create_access_token(new_user.id)
        refresh_token = create_refresh_token(new_user.id)

        # Set successful response
        response.status_code = status.HTTP_201_CREATED

        return {
            "message": "User registered successfully",
            "user": UserResponse.from_orm(new_user),
            "access_token": access_token,
            "refresh_token": refresh_token
        }

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


async def login_user(login_data: LoginData, response: Response, db: Session = None) -> dict:
    """
    Log in a user by validating credentials and issuing new tokens.

    Args:
        login_data (LoginData): Contains the username and password.
        response (Response): FastAPI response object for setting cookies.
        db (Session, optional): SQLAlchemy session.

    Returns:
        dict: A success message with user info and tokens.

    Raises:
        HTTPException: If authentication fails or any error occurs.
    """
    if db is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                            detail="Database connection not provided")
    
    try:
        # Retrieve user by username
        user = db.query(UserModel).filter(UserModel.username == login_data.username).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User not found")

        # Compare hashed password
        if not bcrypt.checkpw(login_data.password.encode(), user.password.encode()):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid password")

        # Generate new tokens
        access_token = create_access_token(user.id)
        refresh_token = create_refresh_token(user.id)
        
        # Set secure HTTP-only cookies
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=True,
            samesite="strict"
        )
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=True,
            samesite="strict"
        )

        response.status_code = status.HTTP_200_OK

        return {
            "message": "Login successful",
            "user": UserResponse.from_orm(user),
            "access_token": access_token,
            "refresh_token": refresh_token
        }

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


async def refresh_token(refresh_token_str: str, db: Session = None) -> dict:
    """
    Generate a new access token using a valid refresh token.

    Args:
        refresh_token_str (str): JWT refresh token.
        db (Session, optional): SQLAlchemy session.

    Returns:
        dict: A dictionary with a new access token.

    Raises:
        HTTPException: If token is invalid, expired, or user does not exist.
    """
    if db is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                            detail="Database connection not provided")
    
    try:
        # Decode the JWT using the refresh token secret key
        payload = jwt.decode(refresh_token_str, settings.REFRESH_SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("sub")

        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")

        # Validate that the user exists
        user = db.query(UserModel).filter(UserModel.id == user_id).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

        # Create a new access token
        access_token = create_access_token(user.id)

        return {"access_token": access_token}
    
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired")

    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

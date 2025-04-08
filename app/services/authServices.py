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
    # if db is None:
    #     # This function is called directly from router, not through Depends
    #     raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
    #                        detail="Database connection not provided")
    
    try:
       

        Base.metadata.create_all(engine)
        existing_user = db.query(UserModel).filter(UserModel.username == user.username).first()
        if existing_user:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User already exists")

        # Securely hash the password
        salt = bcrypt.gensalt()
        hashed_password = bcrypt.hashpw(user.password.encode(), salt).decode()

        # Create new user
        new_user = UserModel(
            username=user.username,
            password=hashed_password,
            email=user.email
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        # Generate tokens with UUID
        access_token = create_access_token(new_user.id)
        refresh_token = create_refresh_token(new_user.id)

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
    if db is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                           detail="Database connection not provided")
    
    try:
        user = db.query(UserModel).filter(UserModel.username == login_data.username).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User not found")

        # Verify password
        if not bcrypt.checkpw(login_data.password.encode(), user.password.encode()):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid password")

        # Generate tokens with UUID
        access_token = create_access_token(user.id)
        refresh_token = create_refresh_token(user.id)
        
        # Set cookies using set_cookie method
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
    if db is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                           detail="Database connection not provided")
    
    try:
        payload = jwt.decode(refresh_token_str, settings.REFRESH_SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")

        user = db.query(UserModel).filter(UserModel.id == user_id).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    
        access_token = create_access_token(user.id)

        return {"access_token": access_token}
    
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired")

    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
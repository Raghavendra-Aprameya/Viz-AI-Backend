from fastapi import APIRouter, status, Response, Depends
from sqlalchemy.orm import Session

from app.schemas import UserRequest, UserResponse, LoginData
from app.services.authServices import register_user, login_user, refresh_token
from app.core.db import get_db

auth_router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

@auth_router.post("/register-super-admin", status_code=status.HTTP_201_CREATED, response_model=dict)
async def register(user: UserRequest, response: Response, db: Session = Depends(get_db)):
    return await register_user(user, response, db)

@auth_router.post("/login", response_model=dict)
async def login(login_data: LoginData, response: Response, db: Session = Depends(get_db)):
    return await login_user(login_data, response, db)

@auth_router.post("/refresh-token", response_model=dict)
async def refresh_token_route(refresh_token_str: str, db: Session = Depends(get_db)):
    return await refresh_token(refresh_token_str, db)
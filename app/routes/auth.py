from fastapi import APIRouter, status
from app.models.schema_models import UserModel
from app.services.authServices import register_user


router = APIRouter(prefix= "/api/v1/auth")

@router.post("/register",status_code= status.HTTP_201_CREATED)
async def register(user: UserModel):

    register_user(user)



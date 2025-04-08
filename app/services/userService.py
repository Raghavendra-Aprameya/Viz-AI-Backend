from fastapi import HTTPException, status, Depends, Path
from sqlalchemy.orm import Session

from uuid import UUID
import bcrypt

from app.core.db import get_db
from app.schemas import CreateUserProjectRequest, CreateUserProjectResponse
from app.utils.token_parser import get_current_user
from app.models.schema_models import UserProjectRoleModel, UserModel, RoleModel

async def create_user_project(
    data: CreateUserProjectRequest, 
    db: Session, 
    token_payload: dict,
    project_id: UUID
):
    try:
        user_id = UUID(token_payload.get("sub"))

        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
        
        # Check if role exists, if not create it
        role = db.query(RoleModel).filter(RoleModel.id == data.role_id).first()
        if not role:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Role with ID {data.role_id} does not exist"
            )
        
        # Check if username already exists
        existing_user = db.query(UserModel).filter(UserModel.username == data.username).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already exists"
            )
        
        # Check if email already exists
        existing_email = db.query(UserModel).filter(UserModel.email == data.email).first()
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already exists"
            )
        
        password = bcrypt.hashpw(data.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        new_user = UserModel(
            username=data.username,
            email=data.email,
            password=password
        )
        db.add(new_user)
        db.flush()  # Flush to get the new_user.id before creating user_project
        
        user_project = UserProjectRoleModel(
            user_id=new_user.id,  
            project_id=project_id,
            role_id=data.role_id
        )

        db.add(user_project)
        db.commit()
        db.refresh(user_project)
        db.refresh(new_user)

        
        user_project_role = {
            "id": user_project.user_id,  
            "user_id": user_project.user_id,
            "project_id": user_project.project_id,
            "role_id": user_project.role_id
        }
        

        return {
            "message": "User project created successfully",
            "user_project": user_project_role,
            "user": new_user
        }
    except Exception as e:
        db.rollback()  # Added rollback on error
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    
async def list_all_users_project(
    project_id: UUID,
    db: Session,
    token_payload: dict
):
    try:
        user_id = UUID(token_payload.get("sub"))

        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
        
        # Get all user-project-role mappings for the project
        user_project_roles = db.query(UserProjectRoleModel).filter(
            UserProjectRoleModel.project_id == project_id
        ).all()

        # Create response with all required fields
        users = []
        for upr in user_project_roles:
            user = db.query(UserModel).filter(UserModel.id == upr.user_id).first()
            if user:
                users.append({
                    "id": upr.user_id,  # Using user_id as id since it's unique in this context
                    "user_id": upr.user_id,
                    "project_id": upr.project_id,
                    "role_id": upr.role_id,
                    "username": user.username,
                    "password": user.password, # optional if we want to hide the password
                    "email": user.email,
                    "created_at": str(user.created_at)
                })

        return {
            "message": "Users retrieved successfully",
            "users": users
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
      
        
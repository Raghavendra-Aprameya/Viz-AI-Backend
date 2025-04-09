from fastapi import HTTPException, status, Depends, Path
from sqlalchemy.orm import Session

from uuid import UUID
import bcrypt

from app.core.db import get_db
from app.schemas import CreateUserProjectRequest, CreateUserProjectResponse, AddUserDashboardRequest, AddUserDashboardResponse, UpdateUserRequest
from app.utils.token_parser import get_current_user
from app.utils.access import check_add_user_access
from app.models.schema_models import UserProjectRoleModel, UserModel, RoleModel, UserDashboardModel, UserChartModel, DashboardModel, DashboardChartsModel, RolePermissionModel,PermissionModel


async def create_user_project(
    data: CreateUserProjectRequest, 
    db: Session, 
    token_payload: dict,
    project_id: UUID
):
    try:
        has_access = await check_add_user_access(db, token_payload, project_id)
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
      
async def add_user_to_dashboard(
    project_id: UUID,
    data: AddUserDashboardRequest,
    db: Session,
    token_payload: dict,
):
    try:
        user_id = UUID(token_payload.get("sub"))

        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
        
        # Check if user exists
        isUserExists = db.query(UserModel).filter(UserModel.id == data.user_id).first()
        if not isUserExists:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User does not exist")
        
        # Check if user has a role in the project
        user_project_role = db.query(UserProjectRoleModel).filter(
            UserProjectRoleModel.user_id == data.user_id,
            UserProjectRoleModel.project_id == project_id
        ).first()
        
        if not user_project_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User does not have a role in this project"
            )
        
        # Get role permissions
        role_permissions = db.query(RolePermissionModel).filter(
            RolePermissionModel.role_id == user_project_role.role_id
        ).all()
        
        permission_types = []
        for role_perm in role_permissions:
            permission_types.append(role_perm.permission.type)
            
        # Determine access levels based on role permissions
        can_read = "view_dashboard" in permission_types
        can_write = "create_dashboard" in permission_types
        can_delete = "delete_dashboard" in permission_types
            
        user_dashboard = UserDashboardModel(
            user_id=data.user_id,
            dashboard_id=data.dashboard_id,
            can_read=True,
            can_write=can_write,
            can_delete=can_delete
        )
        db.add(user_dashboard)
        db.commit()
        db.refresh(user_dashboard)
        
        return {
            "message": "User added to dashboard successfully",
            "user_dashboard": {
                "id": user_dashboard.user_id,  
                "user_id": user_dashboard.user_id,
                "dashboard_id": user_dashboard.dashboard_id,
                "can_read": user_dashboard.can_read,
                "can_write": user_dashboard.can_write,
                "can_delete": user_dashboard.can_delete
            }
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        
async def get_user_details(
    db: Session,
    token_payload: dict
):
    try:
        user_id = UUID(token_payload.get("sub"))
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

        user = db.query(UserModel).filter(UserModel.id == user_id).first()

        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        return {
            "message": "User details retrieved successfully",
            "user": {
                "id": str(user.id),
                "username": user.username,
                "email": user.email
            }
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        
async def update_user(
    project_id: UUID,
    user_id: UUID,
    data: UpdateUserRequest,
    db: Session,
    token_payload: dict
):
    try:
        # Get the user
        user = db.query(UserModel).filter(UserModel.id == user_id).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        # Update user fields if provided
        if data.username is not None:
            user.username = data.username
        if data.email is not None:
            user.email = data.email
        if data.password is not None:
            # Hash the password using bcrypt - using the same implementation as create_user_project
            password = bcrypt.hashpw(data.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            user.password = password

        # Update role if provided
        if data.role_id is not None:
            # Check if the role exists
            role = db.query(RoleModel).filter(RoleModel.id == data.role_id).first()
            if not role:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Role with ID {data.role_id} does not exist"
                )

            # Get the user's project role
            user_project_role = db.query(UserProjectRoleModel).filter(
                UserProjectRoleModel.user_id == user_id,
                UserProjectRoleModel.project_id == project_id
            ).first()

            if not user_project_role:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User project role not found")

            # Update the role
            user_project_role.role_id = data.role_id

        db.commit()

        # Get updated user details
        updated_user = db.query(UserModel).filter(UserModel.id == user_id).first()
        user_project_role = db.query(UserProjectRoleModel).filter(
            UserProjectRoleModel.user_id == user_id,
            UserProjectRoleModel.project_id == project_id
        ).first()

        return {
            "message": "User updated successfully",
            "user": {
                "id": updated_user.id,
                "username": updated_user.username,
                "email": updated_user.email
            },
            "user_project_role": {
                "user_id": user_project_role.user_id,
                "project_id": user_project_role.project_id,
                "role_id": user_project_role.role_id
            } if user_project_role else None
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        
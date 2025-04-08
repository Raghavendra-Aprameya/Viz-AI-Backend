from fastapi import Response, Depends, HTTPException, status, Request, Path
from sqlalchemy.orm import Session

from datetime import datetime
from uuid import UUID

from app.schemas import ProjectRequest, ConnectionRequest, CreateDashboardRequest
from app.core.db import get_db
from app.utils.token_parser import get_current_user

from app.models.schema_models import ProjectModel, DatabaseConnectionModel, UserProjectRoleModel, RoleModel, DashboardModel


async def create_project(
    project: ProjectRequest, 
    request: Request, 
    response: Response, 
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    try:
        user_id_str = token_payload.get("sub")

        if not user_id_str:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
        
        try:
            user_id = UUID(user_id_str)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid UUID format in token")
        
        project_name=db.query(ProjectModel).filter(ProjectModel.name == project.name).first()
        if project_name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Project name already exists")
        
        new_project = ProjectModel(
            name=project.name,
            description=project.description,
            super_user_id=user_id
        )

        db.add(new_project)
        db.flush()
        role_id = db.query(RoleModel).filter(RoleModel.name == "Project Owner").first().id

        # Add user to user project role table
        user_project_role = UserProjectRoleModel(
            user_id=user_id,
            project_id=new_project.id,
            role_id=role_id
        )
        db.add(user_project_role)
        db.commit()
        db.refresh(new_project)


        # Return dictionary with project data that can be serialized
        return {
            "message": "Project created successfully", 
            "project": {
                "id": new_project.id,
                "name": new_project.name,
                "description": new_project.description,
                "super_user_id": new_project.super_user_id,
                "created_at": new_project.created_at,
            }
        }

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    
async def get_projects(
    request: Request, 
    response: Response, 
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    try:
        user_id_str = token_payload.get("sub")

        if not user_id_str:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
            
        user_id = UUID(user_id_str)


            
        projects = db.query(ProjectModel).filter(ProjectModel.super_user_id == user_id).all()

        return {
            "message": "Projects retrieved successfully",
            "projects": [project for project in projects]
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

async def list_all_roles_project(
    project_id: UUID,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
   try:
    user_id = UUID(token_payload.get("sub"))

    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
    
    roles = db.query(UserProjectRoleModel).filter(UserProjectRoleModel.project_id == project_id).all()
    roles_list = []
    for role in roles:
        role_data = db.query(RoleModel).filter(RoleModel.id == role.role_id).first()
        roles_list.append({
            "id": role.role_id,
            "name": role_data.name,
            "description": role_data.description or ""
        })
        


    return {
        "message": "Roles retrieved successfully",
        "roles": roles_list
    }
   except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
   
async def create_dashboard(
    data: CreateDashboardRequest,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
    project_id: UUID = Path(..., description="Project ID to create dashboard for")
):
    try:
        user_id = UUID(token_payload.get("sub"))

        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
        
        dashboard_title=db.query(DashboardModel).filter(DashboardModel.title == data.title).first()
        if dashboard_title:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Dashboard title already exists")
        
        new_dashboard = DashboardModel(
            title=data.title,
            description=data.description,
            project_id=project_id,
            created_by=user_id
        )

        db.add(new_dashboard)
        db.commit()
        db.refresh(new_dashboard)

        return {
            "message": "Dashboard created successfully",
            "dashboard": new_dashboard
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
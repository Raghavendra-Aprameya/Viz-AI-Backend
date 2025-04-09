from fastapi import Response, Depends, HTTPException, status, Request, Path
from sqlalchemy.orm import Session

from datetime import datetime
from uuid import UUID

from app.schemas import ProjectRequest, ConnectionRequest, CreateDashboardRequest, CreateRoleRequest, UpdateProjectRequest, UpdateDashboardRequest, UpdateRoleRequest
from app.core.db import get_db
from app.utils.token_parser import get_current_user
from app.utils.access import check_create_role_access, check_project_create_access, check_dashboard_create_access
from app.models.schema_models import ProjectModel, DatabaseConnectionModel, UserProjectRoleModel, RoleModel, DashboardModel, PermissionModel, RolePermissionModel, UserDashboardModel


async def create_project(
    project: ProjectRequest, 
    request: Request, 
    response: Response, 
    db: Session ,
    token_payload: dict,
    
):
    try:
        has_access = await check_project_create_access(db,token_payload)
        
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
        db.refresh(user_project_role)

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
        
        # Get all roles for this project
        roles = db.query(RoleModel).join(
            UserProjectRoleModel, 
            RoleModel.id == UserProjectRoleModel.role_id
        ).filter(
            UserProjectRoleModel.project_id == project_id
        ).distinct().all()

        roles_list = []
        for role in roles:
            # Get permissions for each role
            permissions = db.query(PermissionModel).join(
                RolePermissionModel,
                PermissionModel.id == RolePermissionModel.permission_id
            ).filter(
                RolePermissionModel.role_id == role.id
            ).all()

            # Get permission IDs for this role
            permission_type = [permission.type for permission in permissions]

            roles_list.append({
                "id": role.id,
                "name": role.name,
                "description": role.description or "",
                "permissions": permission_type  # Include permission IDs
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
        has_access = await check_dashboard_create_access(db, token_payload, project_id)
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
    
async def list_all_permissions(
    db: Session = Depends(get_db),
    
):
    try:
        permissions = db.query(PermissionModel).all()
        return {
            "message": "Permissions retrieved successfully",
            "permissions": [permission for permission in permissions]
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    
async def create_role(
    data: CreateRoleRequest,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
    project_id: UUID = Path(..., description="Project ID to create role for")
):
    try:
        user_id = UUID(token_payload.get("sub"))

        has_access = await check_create_role_access(db, project_id,token_payload)

        

        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
        
        # Create new role
        new_role = RoleModel(
            name=data.name,
            description=data.description,
            project_id=project_id,
        )
        db.add(new_role)
        db.flush()
        
        # Process permissions
        for permission_id in data.permissions:
            permission_data = db.query(PermissionModel).filter(PermissionModel.id == permission_id).first()
            if not permission_data:
                db.rollback()
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Permission with ID {permission_id} not found")

            role_permission = RolePermissionModel(
                role_id=new_role.id,
                permission_id=permission_id
            )
            db.add(role_permission)
        
        db.commit()
        db.refresh(new_role)

        return {
            "message": "Role created successfully",
            "role": {
                "id": new_role.id,
                "name": new_role.name,
                "description": new_role.description,
                "project_id": new_role.project_id,
                "permissions": data.permissions
            }
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    
async def list_users_all_dashboard(
    project_id: UUID,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    try:
        user_id = UUID(token_payload.get("sub"))

        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
        
        dashboards = db.query(UserDashboardModel).filter(UserDashboardModel.user_id == user_id).all()
        dashboard_details = []
        for dashboard in dashboards:
            dashboard_data = db.query(DashboardModel).filter(DashboardModel.id == dashboard.dashboard_id).first()
            dashboard_details.append({
                "id": dashboard_data.id,  # Using id from DashboardModel
                "title": dashboard_data.title,
                "description": dashboard_data.description,
                "project_id": dashboard_data.project_id,
                "created_by": dashboard_data.created_by
            })
        
        return {
            "message": "Dashboard retrieved successfully",
            "dashboards": dashboard_details
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        
async def delete_dashboard(
    
    project_id: UUID,
    dashboard_id: UUID,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    try:
        user_id = UUID(token_payload.get("sub"))

        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
        
        dashboard = db.query(DashboardModel).filter(DashboardModel.id == dashboard_id).first()
        if not dashboard:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dashboard not found")
        
        db.delete(dashboard)
        db.commit()

        return {
            "message": "Dashboard deleted successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        
async def update_project(
    project_id: UUID,
    data: UpdateProjectRequest,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    try:
        user_id = UUID(token_payload.get("sub"))

        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
        
        project = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        
        # Only update fields that are provided in the request
        if data.name is not None:
            project.name = data.name
        if data.description is not None:
            project.description = data.description
            
        db.commit()
        db.refresh(project)

        return {
            "message": "Project updated successfully",
            "project": project
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    
async def delete_project(
    project_id: UUID,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    try:
        user_id = UUID(token_payload.get("sub"))

        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
        
        project = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        
        db.delete(project)
        db.commit()

        return {
            "message": "Project deleted successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


async def update_dashboard(
    dashboard_id: UUID,
    data: UpdateDashboardRequest,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    try:
        user_id = UUID(token_payload.get("sub"))

        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
        
        dashboard = db.query(DashboardModel).filter(DashboardModel.id == dashboard_id).first()
        if not dashboard:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dashboard not found")
        
        if data.title is not None:
            dashboard.title = data.title
        if data.description is not None:
            dashboard.description = data.description
        
        db.commit()
        db.refresh(dashboard)
        
        return {
            "message": "Dashboard updated successfully",
            "dashboard": dashboard
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
            
async def update_role(
    role_id: UUID,
    data: UpdateRoleRequest,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    try:
        user_id = UUID(token_payload.get("sub"))

        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
        
        role = db.query(RoleModel).filter(RoleModel.id == role_id).first()
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
        
        if data.name is not None:
            role.name = data.name
        if data.description is not None:
            role.description = data.description
        
        # Delete existing role permissions
        db.query(RolePermissionModel).filter(RolePermissionModel.role_id == role_id).delete()
        
        # Add new role permissions
        for permission_id in data.permissions:
            permission = db.query(PermissionModel).filter(PermissionModel.id == permission_id).first()
            if not permission:
                db.rollback()
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Permission with ID {permission_id} not found")
            
            role_permission = RolePermissionModel(
                role_id=role.id,
                permission_id=permission_id
            )
            db.add(role_permission)

        db.commit()
        db.refresh(role)
        
        return {
            "message": "Role updated successfully",
            "role": role
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))        

from operator import is_
from turtle import title
from pydantic import BaseModel, EmailStr
from typing import Optional, Any, List, Union, Dict
from uuid import UUID
from datetime import datetime
from dataclasses import dataclass, asdict
from enum import Enum


from sqlalchemy.orm import query
from app.models.schema_models import UserProjectRoleModel, UserModel, UserDashboardModel

class DBConnectionRequest(BaseModel):
    connection_name: str  
    connection_string: Optional[str] = None
    domain: Optional[str] = None
    db_type: Optional[str] = None
    api_key: Optional[str] = None
    password: Optional[str] = None
    host: Optional[str] = None
    db_name: Optional[str] = None 
    name: Optional[str] = None  
    grant_access : bool       


class DBConnectionResponse(BaseModel):
    db_entry_id: UUID


class DBConnectionListResponse(BaseModel):
    message: str
    connections: List[dict]

    class Config:
        from_attributes = True


class UserRequest(BaseModel):
    username: str
    password: str
    email: str
    


class LoginData(BaseModel):
    username: str
    password: str

class UserResponse(BaseModel):
    id: UUID
    username: str
    email: str

    class Config:
        from_attributes = True  # This allows Pydantic to work with SQLAlchemy models

class ProjectRequest(BaseModel):
    name: str  
    description: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True



class ProjectResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    super_user_id: UUID
    created_at: datetime
    
    
    class Config:
        from_attributes = True  # For Pydantic v2, this replaces orm_mode

class ConnectionRequest(BaseModel):
    project_id: UUID

class ProjectsResponse(BaseModel):
    message: str
    projects: List[ProjectResponse]

class UserProjectRole(BaseModel):
    id: UUID
    user_id: UUID
    project_id: UUID
    role_id: UUID

    class Config:
        from_attributes = True

class CreateUserProjectRequest(BaseModel):
    username: str
    email: str
    password: str
    role_id: UUID
    
class CreateUserProjectResponse(BaseModel):
    message: str
    user_project: UserProjectRole
    user: UserResponse

class UserProjectDetails(BaseModel):
    id: UUID
    user_id: UUID  
    project_id: UUID
    role_id: UUID
    username: str
    password: str
    email: str
    created_at: str

    class Config:
        from_attributes = True

class ListAllUsersProjectResponse(BaseModel):
    message: str
    users: List[UserProjectDetails]

    class Config:
        from_attributes = True

class RoleResponse(BaseModel):
    id: UUID
    name: str
    description: str
    permissions: List[str]

class PermissionResponse(BaseModel):
    id: UUID
    type: str
    

class ListAllRolesProjectResponse(BaseModel):
    message: str
    roles: List[RoleResponse]


    class Config:
        from_attributes = True

class CreateDashboardRequest(BaseModel):
    title: str
    description: Optional[str] = None
    

class DashboardResponse(BaseModel):
    id: UUID
    title: str
    description: Optional[str] = None
    project_id: UUID
    created_by: UUID
    

class CreateDashboardResponse(BaseModel):
    message: str
    dashboard: DashboardResponse

class PermissionResponse(BaseModel):
    id: UUID
    type: str

class ListAllPermissionsResponse(BaseModel):
    message: str
    permissions: List[PermissionResponse]

    class Config:
        from_attributes = True

class PermissionAssign(BaseModel):
    permission_id: UUID


class CreateRoleRequest(BaseModel):
    name: str
    description: Optional[str] = None
    permissions: List[UUID]


class RolePermissionResponse(BaseModel):
    id: UUID
    name: str
    description: str
    project_id: UUID
    permissions: List[UUID]

class CreateRoleResponse(BaseModel):
    message: str
    role: RolePermissionResponse

class AddUserDashboardRequest(BaseModel):
    user_ids: List[UUID]
    dashboard_id: UUID

class UserDashboardResponse(BaseModel):
    id: UUID
    user_id: UUID
    dashboard_id: UUID
    can_read: bool
    can_write: bool
    can_delete: bool

    class Config:
        from_attributes = True

class AddUserDashboardResponse(BaseModel):
    message: str
    user_dashboard: List[UserDashboardResponse]

class UserDashboardReponse(BaseModel):
    id: UUID
    title: str
    description: Optional[str] = None
    project_id: UUID
    created_by: UUID

    class Config:
        from_attributes = True
    

class ListAllUsersDashboardResponse(BaseModel):
    message: str
    dashboards: List[UserDashboardReponse]

    class Config:
        from_attributes = True



class DeleteDashboardResponse(BaseModel):
    message: str

class CreateProjectResponse(BaseModel):
    message: str
    project: dict

    class Config:
        from_attributes = True

class UpdateProjectRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

class UpdateDashboardRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None

class UpdateRoleRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    permissions: Optional[List[UUID]] = None

class DeleteRoleResponse(BaseModel):
    message: str

class UpdateUserRequest(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    role_id: Optional[UUID] = None
    password: Optional[str] = None

class UpdateDBConnectionRequest(BaseModel):
    connection_name: Optional[str] = None
    db_connection_string: Optional[str] = None
    db_schema: Optional[str] = None
    db_username: Optional[str] = None
    db_password: Optional[str] = None
    db_host_link: Optional[str] = None
    db_name: Optional[str] = None
    db_type: Optional[str] = None

class CreateSuperUserRequest(BaseModel):
    username: str
    email: str
    password: str
    is_super: bool = True
    

class BlackListTableNameRequest(BaseModel):
    """
    Represents a request to blacklist multiple table name.
    """
    table_name: List[UUID]
    role_id:UUID
    
class ReadDataRequest(BaseModel):
    """
    Represents a request to read data from a table.
    """
    connection_id: UUID

class ValidateChartAccessRequest(BaseModel):
    """
    Represents a request to validate chart access.
    """
    role_id: UUID
    table_name:List[str]

class RequestAccess(BaseModel):
    """
    Represents a request to validate chart access.
    """
    title: str
    query: str
    report: Optional[str] = None
    type: str
    relevance: Optional[str] = None
    is_time_based: Optional[bool] = None
    chart_type: str

class QueryRequest(BaseModel):
    """
    Pydantic model for chart generation request parameters.
    """
    db_type: str
    domain: str
    min_date: Optional[Union[datetime, str]] = None
    max_date: Optional[Union[datetime, str]] = None
    api_key: Optional[str] = None
    role: str
    
    def dict(self):
        """
        Convert the model to a dictionary, handling datetime objects.
        """
        data = super().dict()
        # Convert datetime objects to strings
        if isinstance(data.get('min_date'), datetime):
            data['min_date'] = data['min_date'].isoformat()
        if isinstance(data.get('max_date'), datetime):
            data['max_date'] = data['max_date'].isoformat()
        return data
    
class QueryExecutionRequest(BaseModel):
    query: str
class Nl2SQLChatRequest(BaseModel):
    nl_query: str
    api_key: Optional[str] 

class Nl2SQLChartResponse(BaseModel):
    status: str 
    sql_query: str 
    chart_id: UUID 
    

class ExecutionConfig(BaseModel):
    host: str = 'localhost'
    port: int = 8080
    user: str = 'admin'
    catalog: str = 'neondb'
    schema: str = 'public'

class TrinoQueryRequest(BaseModel):
    connection_ids: List[UUID]  
    role: str
    domain: str
    api_key: Optional[str] = None
    model_name: str = "gemini-1.5-pro"
    min_date: Optional[Union[datetime, str]] = None
    max_date: Optional[Union[datetime, str]] = None


class QueryDetail(BaseModel):
    sql: str
    chart_type: Optional[str] = None
    relevance: Optional[float] = None
    title: Optional[str] = None
    category: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    is_time_based:bool

class TrinoQueryResponse(BaseModel):
    queries: List[QueryDetail]
    min_date: Optional[str] = None
    max_date: Optional[str] = None

class AccessStatus(str, Enum):
    
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"

class UpdateRequestAccess(BaseModel):
    status: AccessStatus

class SaveChartRequest(BaseModel):
    """
    Represents a request to validate chart access.
    """
    title: str
    query: str
    report: Optional[str] = None
    type: str
    relevance: Optional[str] = None
    is_time_based: Optional[bool] = None
    chart_type: str

class SaveChartToDashboardRequest(BaseModel):
    """
    Represents a request to validate chart access.
    """
    title: str
    query: str
    report: Optional[str] = None
    type: str
    relevance: Optional[str] = None
    is_time_based: Optional[bool] = None
    chart_type: str
    dashboard_id: UUID

class UpdateFavoriteChartRequest(BaseModel):
    """
    Represents a request to validate chart access.
    """
    chart_id: UUID
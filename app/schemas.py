from pydantic import BaseModel
from typing import Optional,Union,List
from uuid import UUID
from datetime import datetime
from dataclasses import dataclass, asdict
from app.models.schema_models import UserProjectRoleModel, UserModel

class DBConnectionRequest(BaseModel):
    connection_name: str
    connection_string: Optional[str] = None
    db_type: str
    name: Optional[str] = None
    password: Optional[str] = None
    host: Optional[str] = None
    db_name: Optional[str] = None

class DBConnectionResponse(BaseModel):
    db_entry_id: UUID


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

class ListAllRolesProjectResponse(BaseModel):
    message: str
    roles: List[RoleResponse]

    class Config:
        from_attributes = True

class QueryRequest(BaseModel):
    db_type: str
    domain: str
    min_date: Optional[Union[datetime, str]] = None
    max_date: Optional[Union[datetime, str]] = None
    api_key: Optional[str] = None
    role:str


class QueryForExecutor(BaseModel):
    query: str
    explanation: str
    relevance: float
    is_time_based: bool
    chart_type: str


class QueriesForExecutorResponse(BaseModel):
    queries: List[QueryForExecutor]
    
class Nl2SQLChatRequest(BaseModel):
    nl_query: str
    api_key: Optional[str] 

class Nl2SQLChartResponse(BaseModel):
    status: str 
    sql_query: str 
    chart_id: UUID 
from sqlalchemy import Column, String, ForeignKey, DateTime, func, Text, Boolean, Double, BigInteger
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.dialects.postgresql import UUID
from uuid import uuid4

Base = declarative_base()

# User Model
class UserModel(Base):
    __tablename__ = 'user'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    username = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=True, onupdate=func.now())

    user_project_role = relationship("UserProjectRoleModel", back_populates="user", cascade="all, delete-orphan")
    api_key = relationship("ApiKeyModel", back_populates="user", uselist=False, cascade="all, delete-orphan")  # Ensures deletion

# API Key Model (For Users)
class ApiKeyModel(Base):
    __tablename__ = 'api_key'
    user_id = Column(UUID, ForeignKey("user.id"), primary_key=True)
    api_key = Column(String, nullable=False)

    user = relationship("UserModel", back_populates="api_key") 


# Project Model
class ProjectModel(Base):
    __tablename__ = 'project'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String, nullable=False)
    super_user_id = Column(UUID, ForeignKey("user.id"))
    description = Column(Text)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    user_project_role = relationship("UserProjectRoleModel", back_populates="project", cascade="all, delete-orphan")
    project_permission = relationship("ProjectPermissionModel", back_populates="project", cascade="all, delete-orphan")
    dashboards = relationship("DashboardModel", back_populates="project", cascade="all, delete-orphan")
    database_connections = relationship("DatabaseConnectionModel", back_populates="project", cascade="all, delete-orphan") 

# Role Model    
class RoleModel(Base):
    __tablename__ = 'role'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String, unique=True, nullable=False)
    description = Column(Text, nullable=True)

    user_project_role = relationship("UserProjectRoleModel", back_populates="role", cascade="all, delete-orphan")
    project_permission = relationship("ProjectPermissionModel", back_populates="role", cascade="all, delete-orphan")
    dashboard_permissions = relationship("DashboardPermissionModel", back_populates="role", cascade="all, delete-orphan")
    chart_permissions = relationship("ChartPermissionModel", back_populates="role", cascade="all, delete-orphan")

# User-Project-Role Mapping (Many-to-Many)
class UserProjectRoleModel(Base):
    __tablename__ = 'user_project_role'
    user_id = Column(UUID, ForeignKey("user.id"), primary_key=True)
    project_id = Column(UUID, ForeignKey("project.id"), primary_key=True)
    role_id = Column(UUID, ForeignKey("role.id"), primary_key=True)

    user = relationship("UserModel", back_populates="user_project_role")
    project = relationship("ProjectModel", back_populates="user_project_role")
    role = relationship("RoleModel", back_populates="user_project_role")

# Permission Model
class PermissionModel(Base):
    __tablename__ = 'permission'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    type = Column(String, nullable=False)
    
    project_permission = relationship("ProjectPermissionModel", back_populates="permission")
    chart_permissions = relationship("ChartPermissionModel", back_populates="permission")
    dashboard_permissions = relationship("DashboardPermissionModel", back_populates="permission")



# Project Permission Model (Mapping Roles to Project-Level Permissions)
class ProjectPermissionModel(Base):
    __tablename__ = 'project_permission'
    role_id = Column(UUID, ForeignKey("role.id"), primary_key=True)
    project_id = Column(UUID, ForeignKey("project.id"), primary_key=True)
    permission_id = Column(UUID, ForeignKey("permission.id"), primary_key=True)

    role = relationship("RoleModel", back_populates="project_permission")
    project = relationship("ProjectModel", back_populates="project_permission")
    permission = relationship("PermissionModel",back_populates="project_permission")

# Dashboard Model
class DashboardModel(Base):
    __tablename__ = 'dashboard'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    title = Column(String, nullable=False)
    project_id = Column(UUID, ForeignKey("project.id"), nullable=False)
    description = Column(Text)

    project = relationship("ProjectModel", back_populates="dashboards")
    dashboard_permissions = relationship("DashboardPermissionModel", back_populates="dashboard", cascade="all, delete-orphan")
    charts = relationship("DashboardChartsModel", back_populates="dashboard", cascade="all, delete-orphan")

# Dashboard Permission Model
class DashboardPermissionModel(Base):
    __tablename__ = 'dashboard_permission'
    role_id = Column(UUID, ForeignKey("role.id"), primary_key=True)
    dashboard_id = Column(UUID, ForeignKey("dashboard.id"), primary_key=True)
    permission_id = Column(UUID, ForeignKey("permission.id"), primary_key=True)

    role = relationship("RoleModel", back_populates="dashboard_permissions")
    dashboard = relationship("DashboardModel", back_populates="dashboard_permissions")
    permission = relationship("PermissionModel")

# Chart Model
class ChartModel(Base):
    __tablename__ = 'chart'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    title = Column(String, nullable=False)
    query = Column(Text, nullable=False)
    report = Column(Text, nullable=True)
    type = Column(String, nullable=False)
    relevance = Column(Double, nullable=False)
    is_time_based = Column(Boolean, nullable=False)
    chart_type = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    is_user_generated = Column(Boolean, nullable=False, default=False)

    chart_permissions = relationship("ChartPermissionModel", back_populates="chart", cascade="all, delete-orphan")
    dashboard_charts = relationship("DashboardChartsModel", back_populates="chart")

# Dashboard-Chart Relationship (Many-to-Many)
class DashboardChartsModel(Base):
    __tablename__ = 'dashboard_chart'
    dashboard_id = Column(UUID, ForeignKey("dashboard.id"), primary_key=True)
    chart_id = Column(UUID, ForeignKey("chart.id"), primary_key=True)

    dashboard = relationship("DashboardModel", back_populates="charts")
    chart = relationship("ChartModel", back_populates="dashboard_charts")

# Chart Permission Model
class ChartPermissionModel(Base):
    __tablename__ = 'chart_permission'
    role_id = Column(UUID, ForeignKey("role.id"), primary_key=True)
    chart_id = Column(UUID, ForeignKey("chart.id"), primary_key=True)
    permission_id = Column(UUID, ForeignKey("permission.id"), primary_key=True)

    role = relationship("RoleModel", back_populates="chart_permissions")
    chart = relationship("ChartModel", back_populates="chart_permissions")
    permission = relationship("PermissionModel", back_populates="chart_permissions")

# Database Connection Model (For External DBs)
class DatabaseConnectionModel(Base):
    __tablename__ = 'database_connection'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    db_connection_string = Column(Text, nullable=False)
    db_schema = Column(String, nullable=True)
    db_username = Column(String, nullable=True)
    db_password = Column(String, nullable=True)
    db_host_link = Column(String, nullable=True)
    db_name = Column(String, nullable=True)
    project_id = Column(UUID, ForeignKey("project.id"), nullable=False)

    project = relationship("ProjectModel", back_populates="database_connections")
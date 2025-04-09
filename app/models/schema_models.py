from sqlalchemy import Column, String, ForeignKey, DateTime, func, Text, Boolean, Double, BigInteger
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.dialects.postgresql import UUID
from uuid import uuid4
from app.core.base import Base



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
    api_key = relationship("ApiKeyModel", back_populates="user", uselist=False, cascade="all, delete-orphan")
    user_dashboard = relationship("UserDashboardModel", back_populates="user", cascade="all, delete-orphan")
    user_chart = relationship("UserChartModel", back_populates="user", cascade="all, delete-orphan")
    dashboards = relationship("DashboardModel", back_populates="user", cascade="all, delete-orphan")
    charts = relationship("ChartModel", back_populates="user", cascade="all, delete-orphan")
    projects = relationship("ProjectModel", back_populates="super_user", foreign_keys="ProjectModel.super_user_id")
    
class RolePermissionModel(Base):
    __tablename__ = 'role_permission'
    role_id = Column(UUID, ForeignKey("role.id"), primary_key=True)
    permission_id = Column(UUID, ForeignKey("permission.id"), primary_key=True)
    

    role = relationship("RoleModel", back_populates="role_permission")
    permission = relationship("PermissionModel", back_populates="role_permission")
    

class UserDashboardModel(Base):
    __tablename__ = 'user_dashboard'
    user_id = Column(UUID, ForeignKey("user.id",ondelete="CASCADE"), primary_key=True)
    dashboard_id = Column(UUID, ForeignKey("dashboard.id",ondelete="CASCADE"), primary_key=True)
    can_write = Column(Boolean, nullable=False, default=False)
    can_read = Column(Boolean, nullable=False, default=True)
    can_delete = Column(Boolean, nullable=False, default=False)

    user = relationship("UserModel", back_populates="user_dashboard")
    dashboard = relationship("DashboardModel", back_populates="user_dashboard")

class UserChartModel(Base):
    __tablename__ = 'user_chart'
    user_id = Column(UUID, ForeignKey("user.id",ondelete="CASCADE"), primary_key=True)
    chart_id = Column(UUID, ForeignKey("chart.id",ondelete="CASCADE"), primary_key=True)
    can_write = Column(Boolean, nullable=False, default=False)
    can_read = Column(Boolean, nullable=False, default=True)
    can_delete = Column(Boolean, nullable=False, default=False)

    user = relationship("UserModel", back_populates="user_chart")
    chart = relationship("ChartModel", back_populates="user_chart")
    
    

# API Key Model (For Users)
class ApiKeyModel(Base):
    __tablename__ = 'api_key'
    user_id = Column(UUID, ForeignKey("user.id",ondelete="CASCADE"), primary_key=True)
    api_key = Column(String, nullable=False)
    secret_key = Column(String, nullable=False)
    project_id = Column(UUID, ForeignKey("project.id",ondelete="CASCADE"), nullable=False)

    user = relationship("UserModel", back_populates="api_key") 
    project = relationship("ProjectModel", back_populates="api_key")

# Project Model
class ProjectModel(Base):
    __tablename__ = 'project'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String, nullable=False)
    super_user_id = Column(UUID, ForeignKey("user.id"))
    description = Column(Text)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    user_project_role = relationship("UserProjectRoleModel", back_populates="project", cascade="all, delete-orphan")
    api_key = relationship("ApiKeyModel", back_populates="project", cascade="all, delete-orphan")
    roles = relationship("RoleModel", back_populates="project", cascade="all, delete-orphan")
    super_user = relationship("UserModel", back_populates="projects", foreign_keys=[super_user_id])
    
    dashboards = relationship("DashboardModel", back_populates="project", cascade="all, delete-orphan")
    database_connections = relationship("DatabaseConnectionModel", back_populates="project", cascade="all, delete-orphan") 

# Role Model    
class RoleModel(Base):
    __tablename__ = 'role'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String, unique=True, nullable=False)
    description = Column(Text, nullable=True)
    project_id = Column(UUID, ForeignKey("project.id"), nullable=True)

    user_project_role = relationship("UserProjectRoleModel", back_populates="role", cascade="all, delete-orphan")
    role_permission = relationship("RolePermissionModel", back_populates="role", cascade="all, delete-orphan")
    project = relationship("ProjectModel", back_populates="roles")

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
    role_permission = relationship("RolePermissionModel", back_populates="permission",
                              cascade="all, delete-orphan")

# Dashboard Model
class DashboardModel(Base):
    __tablename__ = 'dashboard'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    title = Column(String, nullable=False)
    project_id = Column(UUID, ForeignKey("project.id"), nullable=False)
    description = Column(Text)
    created_by = Column(UUID, ForeignKey("user.id"), nullable=False)

    user = relationship("UserModel", back_populates="dashboards")
    project = relationship("ProjectModel", back_populates="dashboards")
    
    user_dashboard = relationship("UserDashboardModel", back_populates="dashboard")
    charts = relationship("DashboardChartsModel", back_populates="dashboard")


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
    user_chart = relationship("UserChartModel", back_populates="chart")
    created_by = Column(UUID, ForeignKey("user.id"), nullable=False)

    user = relationship("UserModel", back_populates="charts")
    dashboard_charts = relationship("DashboardChartsModel", back_populates="chart")

# Dashboard-Chart Relationship (Many-to-Many)
class DashboardChartsModel(Base):
    __tablename__ = 'dashboard_chart'
    dashboard_id = Column(UUID, ForeignKey("dashboard.id"), primary_key=True)
    chart_id = Column(UUID, ForeignKey("chart.id"), primary_key=True)

    dashboard = relationship("DashboardModel", back_populates="charts")
    chart = relationship("ChartModel", back_populates="dashboard_charts")


# Database Connection Model (For External DBs)
class DatabaseConnectionModel(Base):
    __tablename__ = 'database_connection'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    connection_name = Column(String, nullable=False)
    db_connection_string = Column(Text, nullable=False)
    db_schema = Column(String, nullable=True)
    db_username = Column(String, nullable=True)
    db_password = Column(String, nullable=True)
    db_host_link = Column(String, nullable=True)
    db_name = Column(String, nullable=True)
    project_id = Column(UUID, ForeignKey("project.id"), nullable=False)
    db_type = Column(String, nullable=True)

    project = relationship("ProjectModel", back_populates="database_connections")
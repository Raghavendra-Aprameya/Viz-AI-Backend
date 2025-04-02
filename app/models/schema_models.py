from sqlalchemy import Column, String, ForeignKey, DateTime, func, Text, Boolean, Double, BigInteger
from sqlalchemy.orm import relationship, Mapped, mapped_column, declarative_base
from sqlalchemy.dialects.postgresql import UUID
from uuid import uuid4

Base = declarative_base()

class UserModel(Base):
    __tablename__ = 'user'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    username = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=True, onupdate=func.now())
    
class ApiKeyModel(Base):
    __tablename__ = 'api_key'
    user_id = Column(UUID, ForeignKey("user.id"), primary_key=True)
    api_key = Column(String, nullable=False)

class ProjectModel(Base):
    __tablename__ = 'project'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String, nullable=False)
    super_user_id = Column(UUID, ForeignKey("user.id"))
    description = Column(Text)

class RoleModel(Base):
    __tablename__ = 'role'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String, unique=True, nullable=False)
    description = Column(Text, nullable=True)

class UserProjectRoleModel(Base):
    __tablename__ = 'user_project_role'
    user_id = Column(UUID, ForeignKey("user.id"), primary_key=True)
    project_id = Column(UUID, ForeignKey("project.id"), primary_key=True)
    role_id = Column(UUID, ForeignKey("role.id"), primary_key=True)
    
    user = relationship("UserModel", back_populates="user_project_role")
    project = relationship("ProjectModel", back_populates="user_project_role")
    role = relationship("RoleModel", back_populates="user_project_role")

class PermissionModel(Base):
    __tablename__ = 'permission'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    type = Column(String, nullable=False)

class ProjectPermissionModel(Base):
    __tablename__ = 'project_permission'
    role_id = Column(UUID, ForeignKey("role.id"), primary_key=True)
    project_id = Column(UUID, ForeignKey("project.id"), primary_key=True)
    permission_id = Column(UUID, ForeignKey("permission.id"), primary_key=True)
    
    project = relationship("ProjectModel",back_populates="project_permission")
    permission = relationship("PermissionModel",back_populates="project_permission")

class DashboardModel(Base):
    __tablename__ = 'dashboard'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    title = Column(String, nullable=False)
    project_id = Column(UUID, ForeignKey("project.id"), nullable=False)
    description = Column(Text)

class DashboardPermissionModel(Base):
    __tablename__ = 'dashboard_permission'
    role_id = Column(UUID, ForeignKey("role.id"), primary_key=True)
    dashboard_id = Column(UUID, ForeignKey("dashboard.id"), primary_key=True)
    permission_id = Column(UUID, ForeignKey("permission.id"), primary_key=True)
    
    dashboard = relationship("DashbaordModel",back_populates="dashboard_permission")
    permission = relationship("PermissionModel",back_populates="dashboard_permission")

class ChartModel(Base):
    __tablename__ = 'chart'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    title = Column(String, nullable=False)
    query = Column(Text, nullable=False)
    report = Column(Text, nullable=True)
    type = Column(String, nullable=False)

class DashboardChartsModel(Base):
    __tablename__ = 'dashboard_chart'
    dashboard_id = Column(UUID, ForeignKey("dashboard.id"), primary_key=True)
    chart_id = Column(UUID, ForeignKey("chart.id"), primary_key=True)
    
    dashboard = relationship("DashbaordModel",back_populates="dashboard_chart")
    chart = relationship("ChartModel",back_populates="dashboard_chart")

class ChartPermissionModel(Base):
    __tablename__ = 'chart_permission'
    role_id = Column(UUID, ForeignKey("role.id"), primary_key=True)
    chart_id = Column(UUID, ForeignKey("chart.id"), primary_key=True)
    permission_id = Column(UUID, ForeignKey("permission.id"), primary_key=True)
    
    chart = relationship("ChartModel",back_populates="chart_permission")
    permission = relationship("PermissionModel",back_populates="chart_permission")


class DatabaseConnectionModel(Base):
    __tablename__ = 'database_connection'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    db_connection_string = Column(Text, nullable=False)
    db_schema = Column(String, nullable=True)
    db_username = Column(String, nullable=False)
    db_password = Column(String, nullable=False)
    db_host_link = Column(String, nullable=False)
    db_name = Column(String, nullable=False)
    project_id = Column(UUID, ForeignKey("project.id"), nullable=False)

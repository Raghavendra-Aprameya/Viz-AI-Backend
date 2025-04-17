from sqlalchemy import (
    Column,
    String,
    ForeignKey,
    DateTime,
    func,
    Text,
    Boolean,
    Double,
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from uuid import uuid4
from app.core.base import Base


class UserModel(Base):
    """
    Represents a user in the system.
    """
    __tablename__ = 'user'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    username = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=True, onupdate=func.now())
    is_super = Column(Boolean, nullable=True, default=False)

    project_roles = relationship(
        "UserProjectRoleModel", back_populates="user", cascade="all, delete-orphan"
    )
    api_key = relationship(
        "ApiKeyModel", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    dashboards_shared = relationship(
        "UserDashboardModel", back_populates="user", cascade="all, delete-orphan"
    )
    charts_shared = relationship(
        "UserChartModel", back_populates="user", cascade="all, delete-orphan"
    )
    dashboards = relationship(
        "DashboardModel", back_populates="user", cascade="all, delete-orphan"
    )
    charts = relationship(
        "ChartModel", back_populates="user", cascade="all, delete-orphan"
    )
    projects = relationship(
        "ProjectModel", back_populates="super_user",
        foreign_keys="ProjectModel.super_user_id"
    )


class RolePermissionModel(Base):
    """
    Represents the relationship between roles and permissions.
    """
    __tablename__ = 'role_permission'

    role_id = Column(UUID(as_uuid=True), ForeignKey("role.id"), primary_key=True)
    permission_id = Column(UUID(as_uuid=True), ForeignKey("permission.id"), primary_key=True)

    role = relationship("RoleModel", back_populates="role_permissions")
    permission = relationship("PermissionModel", back_populates="role_permissions")

class UserDashboardModel(Base):
    """
    Represents the relationship between users and dashboards.
    """
    __tablename__ = 'user_dashboard'

    user_id = Column(UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"),
                     primary_key=True)
    dashboard_id = Column(UUID(as_uuid=True), ForeignKey("dashboard.id", ondelete="CASCADE"),
                          primary_key=True)
    can_write = Column(Boolean, nullable=False, default=False)
    can_read = Column(Boolean, nullable=False, default=True)
    can_delete = Column(Boolean, nullable=False, default=False)
    is_owner = Column(Boolean, nullable=True, default=False)
    is_favorite = Column(Boolean, nullable=True, default=False)


    user = relationship("UserModel", back_populates="dashboards_shared")
    dashboard = relationship("DashboardModel", back_populates="users")


class UserChartModel(Base):
    """
    Represents the relationship between users and charts.
    """
    __tablename__ = 'user_chart'

    user_id = Column(UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"),
                     primary_key=True)
    chart_id = Column(UUID(as_uuid=True), ForeignKey("chart.id", ondelete="CASCADE"),
                      primary_key=True)
    can_write = Column(Boolean, nullable=False, default=False)
    can_read = Column(Boolean, nullable=False, default=True)
    can_delete = Column(Boolean, nullable=False, default=False)
    is_favorite = Column(Boolean, nullable=True, default=False)

    user = relationship("UserModel", back_populates="charts_shared")
    chart = relationship("ChartModel", back_populates="users")


class ApiKeyModel(Base):
    """
    Represents an API key associated with a user.
    """
    __tablename__ = 'api_key'

    user_id = Column(UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"),
                     primary_key=True)
    api_key = Column(String, nullable=False)
    secret_key = Column(String, nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("project.id", ondelete="CASCADE"),
                        nullable=False)

    user = relationship("UserModel", back_populates="api_key")
    project = relationship("ProjectModel", back_populates="api_keys")


class ProjectModel(Base):
    """
    Represents a project in the system.
    """
    __tablename__ = 'project'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String, nullable=False)
    super_user_id = Column(UUID(as_uuid=True), ForeignKey("user.id"))
    description = Column(Text)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    project_roles = relationship(
        "UserProjectRoleModel", back_populates="project", cascade="all, delete-orphan"
    )
    api_keys = relationship(
        "ApiKeyModel", back_populates="project", cascade="all, delete-orphan"
    )
    roles = relationship(
        "RoleModel", back_populates="project", cascade="all, delete-orphan"
    )
    super_user = relationship("UserModel", back_populates="projects")
    dashboards = relationship(
        "DashboardModel", back_populates="project", cascade="all, delete-orphan"
    )
    database_connections = relationship(
        "DatabaseConnectionModel", back_populates="project", cascade="all, delete-orphan"
    )


class RoleModel(Base):
    """
    Represents a role in the system.
    """
    __tablename__ = 'role'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String, unique=True, nullable=False)
    description = Column(Text, nullable=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("project.id"), nullable=True)
    is_global = Column(Boolean, nullable=True, default=False)

    project_roles = relationship(
        "UserProjectRoleModel", back_populates="role", cascade="all, delete-orphan"
    )
    role_permissions = relationship(
        "RolePermissionModel", back_populates="role", cascade="all, delete-orphan"
    )
    project = relationship("ProjectModel", back_populates="roles")
    # Add this relationship to connect with RoleTableNameModel
    role_table_names = relationship(
        "RoleTableNameModel", back_populates="role", cascade="all, delete-orphan"
    )


class UserProjectRoleModel(Base):
    """
    Represents the mapping between users, projects, and roles.
    """
    __tablename__ = 'user_project_role'

    user_id = Column(UUID(as_uuid=True), ForeignKey("user.id"), primary_key=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("project.id"), primary_key=True)
    role_id = Column(UUID(as_uuid=True), ForeignKey("role.id"), primary_key=True)
    is_owner = Column(Boolean, nullable=True, default=False)

    user = relationship("UserModel", back_populates="project_roles")
    project = relationship("ProjectModel", back_populates="project_roles")
    role = relationship("RoleModel", back_populates="project_roles")


class PermissionModel(Base):
    """
    Represents a permission in the system.
    """
    __tablename__ = 'permission'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    type = Column(String, nullable=False)

    role_permissions = relationship(
        "RolePermissionModel", back_populates="permission", cascade="all, delete-orphan"
    )


class DashboardModel(Base):
    """
    Represents a dashboard in the system.
    """
    __tablename__ = 'dashboard'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    title = Column(String, nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("project.id"), nullable=False)
    description = Column(Text)
    created_by = Column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=False)
    user = relationship("UserModel", back_populates="dashboards")
    project = relationship("ProjectModel", back_populates="dashboards")
    users = relationship(
        "UserDashboardModel", 
        back_populates="dashboard", 
        cascade="all, delete-orphan",
        passive_deletes=True
    )
    charts = relationship(
        "DashboardChartsModel", 
        back_populates="dashboard", 
        cascade="all, delete-orphan"
    )

class ChartModel(Base):
    """
    Represents a chart in the system.
    """
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
    created_by = Column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=False)

    user = relationship("UserModel", back_populates="charts")
    users = relationship(
        "UserChartModel", back_populates="chart", cascade="all, delete-orphan"
    )
    dashboard_charts = relationship(
        "DashboardChartsModel", back_populates="chart", cascade="all, delete-orphan"
    )


class DashboardChartsModel(Base):
    """
    Represents the relationship between dashboards and charts.
    """
    __tablename__ = 'dashboard_chart'

    dashboard_id = Column(UUID(as_uuid=True), ForeignKey("dashboard.id"), primary_key=True)
    chart_id = Column(UUID(as_uuid=True), ForeignKey("chart.id"), primary_key=True)

    dashboard = relationship("DashboardModel", back_populates="charts")
    chart = relationship("ChartModel", back_populates="dashboard_charts")

class DatabaseConnectionModel(Base):
    """
    Represents a database connection in the system.
    """
    __tablename__ = 'database_connection'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    connection_name = Column(String, nullable=False)
    db_connection_string = Column(Text, nullable=False)
    db_schema = Column(String, nullable=True)
    db_username = Column(String, nullable=True)
    db_password = Column(String, nullable=True)
    db_host_link = Column(String, nullable=True)
    db_name = Column(String, nullable=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("project.id"), nullable=False)
    db_type = Column(String, nullable=True)
    consent_given = Column(Boolean, nullable=True, default=False)

    project = relationship("ProjectModel", back_populates="database_connections")

    connection_table_names = relationship(
        "ConnectionTableNameModel",
        back_populates="connection",
        cascade="all, delete-orphan"
    )

    related_databases = relationship(
        "RelatedDatabaseModel",
        back_populates="connection",
        cascade="all, delete-orphan",
        foreign_keys="[RelatedDatabaseModel.connection_id]"
    )

    def __repr__(self):
        return f"<DatabaseConnectionModel(id={self.id}, connection_name={self.connection_name}, db_type={self.db_type})>"


class ConnectionTableNameModel(Base):
    """
    Represents a table name in a database connection.
    """
    __tablename__ = 'connection_table_name'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    table_name = Column(String, nullable=False)
    connection_id = Column(UUID(as_uuid=True), ForeignKey("database_connection.id", ondelete="CASCADE"), nullable=False)

    connection = relationship("DatabaseConnectionModel", back_populates="connection_table_names")
    
    # Add this relationship to connect with RoleTableNameModel
    role_table_names = relationship(
        "RoleTableNameModel", 
        back_populates="connection_table_name", 
        cascade="all, delete-orphan"
    )


class RoleTableNameModel(Base):
    """
    Represents a table name in a role.
    """
    __tablename__ = 'role_table_name'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    role_id = Column(UUID(as_uuid=True), ForeignKey("role.id", ondelete="CASCADE"), nullable=False)
    table_name_id = Column(UUID(as_uuid=True), ForeignKey("connection_table_name.id", ondelete="CASCADE"), nullable=False)
    
    # Fix these relationships
    connection_table_name = relationship("ConnectionTableNameModel", back_populates="role_table_names")
    role = relationship("RoleModel", back_populates="role_table_names")


class RelatedDatabaseModel(Base):
    """
    Represents a related database in the system.
    This model connects two database connections as related.
    """
    __tablename__ = 'related_database'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    connection_id = Column(UUID(as_uuid=True), ForeignKey("database_connection.id", ondelete="CASCADE"), nullable=False)
    related_connection_id = Column(UUID(as_uuid=True), ForeignKey("database_connection.id", ondelete="CASCADE"), nullable=False)

    # Explicit relationships with foreign_keys specified
    connection = relationship(
        'DatabaseConnectionModel',
        foreign_keys=[connection_id],
        back_populates='related_databases'
    )

    related_connection = relationship(
        'DatabaseConnectionModel',
        foreign_keys=[related_connection_id],
        uselist=False
    )

    def __repr__(self):
        return f"<RelatedDatabaseModel(id={self.id}, connection_id={self.connection_id}, related_connection_id={self.related_connection_id})>"
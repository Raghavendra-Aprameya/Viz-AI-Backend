"""
Pydantic models for various request and response schemas used in the application.
These models define the structure of data exchanged between the client and server,
including validation rules and types.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from pydantic import BaseModel


class DBConnectionRequest(BaseModel):
    """
    Request model for creating or updating a database connection.

    Attributes:
        connection_name: Name of the database connection
        connection_string: Optional connection string for the database
        domain: Optional domain of the database
        db_type: Optional type of the database (e.g., PostgreSQL, MySQL)
        api_key: Optional API key for authentication
        password: Optional password for authentication
        host: Optional host address of the database
        db_name: Optional name of the database
        name: Optional alternative name for the connection
        consent_given: Optional flag indicating if consent is given for the connection
    """

    connection_name: str
    connection_string: Optional[str] = None
    db_description: Optional[str] = None
    domain: Optional[str] = None
    db_type: Optional[str] = None
    api_key: Optional[str] = None
    password: Optional[str] = None
    host: Optional[str] = None
    db_name: Optional[str] = None
    name: Optional[str] = None
    username: Optional[str] = None  # Optional username field for Oracle DB
    consent_given: Optional[bool] = False


# class DBConnectionResponse(BaseModel):
#     """
#     Response model for a database connection creation or update operation.

#     Attributes:
#         db_entry_id: UUID of the created or updated database connection
#     """

#     db_entry_id: UUID

class DBConnectionResponse(BaseModel):
    taskId: str
    tablesCount: int


class DBConnectionListResponse(BaseModel):
    """
    Response model for listing database connections.

    Attributes:
        message: Status message or description
        connections: List of database connection dictionaries
    """

    message: str
    connections: List[dict]

    class Config:
        from_attributes = True


class UserRequest(BaseModel):
    """
    Request model for creating a new user.

    Attributes:
        username: Username of the new user
        password: Password for the new user
        email: Email address of the new user
    """

    username: str
    password: str
    email: str


class LoginData(BaseModel):
    """
    Request model for user login.

    Attributes:
        username: Username for login
        password: Password for login
    """

    username: str
    password: str


class UserResponse(BaseModel):
    """
    Response model for user information.

    Attributes:
        id: UUID of the user
        username: Username of the user
        email: Email address of the user
    """

    id: UUID
    username: str
    email: str

    class Config:
        from_attributes = True  # This allows Pydantic to work with SQLAlchemy models


class ProjectRequest(BaseModel):
    """
    Request model for creating a new project.

    Attributes:
        name: Name of the project
        description: Optional description of the project
        created_at: Optional creation timestamp
    """

    name: str
    description: Optional[str] = None
    kpi_info: Optional[str] = None
    prod_desc: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ProjectResponse(BaseModel):
    """
    Response model for project information.

    Attributes:
        id: UUID of the project
        name: Name of the project
        description: Optional description of the project
        super_user_id: UUID of the project's super user
        created_at: Creation timestamp of the project
    """

    id: UUID
    name: str
    description: Optional[str] = None
    kpi_info: Optional[str] = None
    prod_desc: Optional[str] = None
    super_user_id: UUID
    created_at: datetime

    class Config:
        from_attributes = True  # For Pydantic v2, this replaces orm_mode


class ConnectionRequest(BaseModel):
    """
    Request model for establishing a connection to a project.

    Attributes:
        project_id: UUID of the project to connect to
    """

    project_id: UUID


class ProjectsResponse(BaseModel):
    """
    Response model for listing projects.

    Attributes:
        message: Status message or description
        projects: List of project responses
    """

    message: str
    projects: List[ProjectResponse]


class UserProjectRole(BaseModel):
    """
    Model representing a user's role in a project.

    Attributes:
        user_id: UUID of the user
        project_id: UUID of the project
        role_id: UUID of the role assigned to the user in the project
    """

    user_id: UUID
    project_id: UUID
    role_id: UUID

    class Config:
        from_attributes = True


class CreateUserProjectRequest(BaseModel):
    """
    Request model for creating a user in a project with a specific role.

    Attributes:
        username: Username of the new user
        email: Email address of the new user
        password: Optional password for the new user. If not provided, a temporary password will be generated.
        role_id: UUID of the role to assign to the user
    """

    username: str
    email: str
    password: Optional[str] = None
    role_id: UUID


class CreateUserProjectResponse(BaseModel):
    """
    Response model for creating a user in a project.

    Attributes:
        message: Status message or description
        user_project: Information about the user-project role association
        user: Information about the created user
    """

    message: str
    user_project: UserProjectRole
    user: UserResponse


class UserProjectDetails(BaseModel):
    """
    Model representing detailed information about a user in a project.

    Attributes:
        id: UUID of the user-project association
        user_id: UUID of the user
        project_id: UUID of the project
        role_id: UUID of the user's role in the project
        username: Username of the user
        password: Password of the user
        email: Email address of the user
        created_at: Creation timestamp of the user-project association
    """

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
    """
    Response model for listing all users in a project.

    Attributes:
        message: Status message or description
        users: List of user project details
    """

    message: str
    users: List[UserProjectDetails]

    class Config:
        from_attributes = True


class BlacklistedTable(BaseModel):
    """
    Model representing a blacklisted table.

    Attributes:
        table_name: Name of the blacklisted table
        table_id: UUID of the blacklisted table
    """

    table_name: str
    table_id: UUID


class RoleResponse(BaseModel):
    """
    Response model for role information including blacklisted tables.

    Attributes:
        id: UUID of the role
        name: Name of the role
        description: Description of the role
        permissions: List of permission strings
        blacklist: List of blacklisted tables for this role
    """

    id: UUID
    name: str
    description: str = ""
    permissions: List[str]
    blacklist: List[BlacklistedTable] = []  # Add this field


class ListAllRolesProjectResponse(BaseModel):
    """
    Response model for listing all roles in a project.

    Attributes:
        message: Status message or description
        roles: List of role responses
    """

    message: str
    roles: List[RoleResponse]


class PermissionResponse(BaseModel):
    """
    Response model for permission information.

    Attributes:
        id: UUID of the permission
        type: Type of the permission
    """

    id: UUID
    type: str

    class Config:
        from_attributes = True


class CreateDashboardRequest(BaseModel):
    """
    Request model for creating a dashboard.

    Attributes:
        title: Title of the dashboard
        description: Optional description of the dashboard
    """

    title: str
    description: Optional[str] = None
    kpi_info: Optional[str] = None


class DashboardResponse(BaseModel):
    """
    Response model for dashboard information.

    Attributes:
        id: UUID of the dashboard
        title: Title of the dashboard
        description: Optional description of the dashboard
        project_id: UUID of the project the dashboard belongs to
        created_by: UUID of the user who created the dashboard
    """

    id: UUID
    title: str
    description: Optional[str] = None
    kpi_info: Optional[str] = None
    project_id: UUID
    created_by: UUID


class CreateDashboardResponse(BaseModel):
    """
    Response model for creating a dashboard.

    Attributes:
        message: Status message or description
        dashboard: Information about the created dashboard
    """

    message: str
    dashboard: DashboardResponse


class ListAllPermissionsResponse(BaseModel):
    """
    Response model for listing all permissions.

    Attributes:
        message: Status message or description
        permissions: List of permission responses
    """

    message: str
    permissions: List[PermissionResponse]

    class Config:
        from_attributes = True


class PermissionAssign(BaseModel):
    """
    Model for assigning a permission.

    Attributes:
        permission_id: UUID of the permission to assign
    """

    permission_id: UUID


class CreateRoleRequest(BaseModel):
    """
    Request model for creating a role.

    Attributes:
        name: Name of the role
        description: Optional description of the role
        permissions: List of permission UUIDs to assign to the role
    """

    name: str
    description: Optional[str] = None
    permissions: List[UUID]


class RolePermissionResponse(BaseModel):
    """
    Response model for role with permissions information.

    Attributes:
        id: UUID of the role
        name: Name of the role
        description: Description of the role
        project_id: UUID of the project the role belongs to
        permissions: List of permission UUIDs assigned to the role
    """

    id: UUID
    name: str
    description: str
    project_id: UUID
    permissions: List[UUID]


class CreateRoleResponse(BaseModel):
    """
    Response model for creating a role.

    Attributes:
        message: Status message or description
        role: Information about the created role with permissions
    """

    message: str
    role: RolePermissionResponse


class AddUserDashboardRequest(BaseModel):
    """
    Request model for adding users to a dashboard.

    Attributes:
        user_ids: List of user UUIDs to add to the dashboard
        dashboard_id: UUID of the dashboard to add users to
    """

    user_ids: List[UUID]
    dashboard_id: UUID


class UserDashboardResponse(BaseModel):
    """
    Response model for user dashboard associations.

    Attributes:
        id: UUID of the user-dashboard association
        user_id: UUID of the user
        dashboard_id: UUID of the dashboard
        can_read: Whether the user can read the dashboard
        can_write: Whether the user can write to the dashboard
        can_delete: Whether the user can delete the dashboard
    """

    id: UUID
    user_id: UUID
    dashboard_id: UUID
    can_read: bool
    can_write: bool
    can_delete: bool

    class Config:
        from_attributes = True


class AddUserDashboardResponse(BaseModel):
    """
    Response model for adding users to a dashboard.

    Attributes:
        message: Status message or description
        user_dashboard: List of user dashboard associations created
    """

    message: str
    user_dashboard: List[UserDashboardResponse]


class UserDashboardReponse(BaseModel):
    """
    Response model for user dashboard information.

    Attributes:
        id: UUID of the dashboard
        title: Title of the dashboard
        description: Optional description of the dashboard
        project_id: UUID of the project the dashboard belongs to
        created_by: UUID of the user who created the dashboard
    """

    id: UUID
    title: str
    description: Optional[str] = None
    project_id: UUID
    created_by: UUID

    class Config:
        from_attributes = True


class ListAllUsersDashboardResponse(BaseModel):
    """
    Response model for listing all dashboards accessible to a user.

    Attributes:
        message: Status message or description
        dashboards: List of user dashboard responses
    """

    message: str
    dashboards: List[UserDashboardReponse]

    class Config:
        from_attributes = True


class DeleteDashboardResponse(BaseModel):
    """
    Response model for deleting a dashboard.

    Attributes:
        message: Status message or description
    """

    message: str


class CreateProjectResponse(BaseModel):
    """
    Response model for creating a project.

    Attributes:
        message: Status message or description
        project: Dictionary containing information about the created project
    """

    message: str
    project: dict

    class Config:
        from_attributes = True


class UpdateProjectRequest(BaseModel):
    """
    Request model for updating a project.

    Attributes:
        name: Optional new name for the project
        description: Optional new description for the project
    """

    name: Optional[str] = None
    description: Optional[str] = None
    kpi_info: Optional[str] = None
    prod_desc: Optional[str] = None


class UpdateProjectKpiInfoRequest(BaseModel):
    """
    Request model for updating only the project KPI info.
    """

    kpi_info: Optional[str] = None


class UpdateDashboardRequest(BaseModel):
    """
    Request model for updating a dashboard.

    Attributes:
        title: Optional new title for the dashboard
        description: Optional new description for the dashboard
    """

    title: Optional[str] = None
    description: Optional[str] = None
    kpi_info: Optional[str] = None


class UpdateRoleRequest(BaseModel):
    """
    Request model for updating a role.

    Attributes:
        name: Optional new name for the role
        description: Optional new description for the role
        permissions: Optional new list of permission UUIDs to assign to the role
    """

    name: Optional[str] = None
    description: Optional[str] = None
    permissions: Optional[List[UUID]] = None


class DeleteRoleResponse(BaseModel):
    """
    Response model for deleting a role.

    Attributes:
        message: Status message or description
    """

    message: str


class UpdateUserRequest(BaseModel):
    """
    Request model for updating a user.

    Attributes:
        username: Optional new username for the user
        email: Optional new email for the user
        role_id: Optional new role UUID to assign to the user
        password: Optional new password for the user
    """

    username: Optional[str] = None
    email: Optional[str] = None
    role_id: Optional[UUID] = None
    password: Optional[str] = None


class UpdateDBConnectionRequest(BaseModel):
    """
    Request model for updating a database connection.

    Attributes:
        connection_name: Optional new name for the connection
        db_connection_string: Optional new connection string
        db_schema: Optional new database schema
        db_username: Optional new database username
        db_password: Optional new database password
        db_host_link: Optional new database host link
        db_name: Optional new database name
        db_type: Optional new database type
    """

    connection_name: Optional[str] = None
    db_connection_string: Optional[str] = None
    db_schema: Optional[str] = None
    db_username: Optional[str] = None
    db_password: Optional[str] = None
    db_host_link: Optional[str] = None
    db_name: Optional[str] = None
    db_type: Optional[str] = None


class CreateSuperUserRequest(BaseModel):
    """
    Request model for creating a super user.

    Attributes:
        username: Username of the super user
        email: Email of the super user
        password: Password for the super user
        is_super: Whether the user should have super user privileges (defaults to True)
    """

    username: str
    email: str
    password: str
    is_super: bool = True


class BlackListTableNameRequest(BaseModel):
    """
    Request model to blacklist multiple table names for a specific role.

    Attributes:
        table_name: List of table UUIDs to blacklist
        role_id: UUID of the role to apply the blacklist to
    """

    table_name: List[UUID]
    role_id: UUID


class ReadDataRequest(BaseModel):
    """
    Request model to read data from a table via a specific connection.

    Attributes:
        connection_id: UUID of the database connection to use for reading data
    """

    connection_id: UUID


class ValidateChartAccessRequest(BaseModel):
    """
    Request model to validate a role's access to specific tables for charting.

    Attributes:
        role_id: UUID of the role to validate access for
        table_name: List of table names to validate access to
    """

    role_id: UUID
    table_name: List[str]


class RequestAccess(BaseModel):
    """
    Request model for requesting access to chart data.

    Attributes:
        title: Title of the chart
        query: SQL query for the chart
        report: Optional report context for the chart
        type: Type of the chart or data access (e.g., 'insight', 'metric', 'analysis')
        relevance: Relevance score (0.0 to 1.0)
        is_time_based: Optional flag indicating if the chart is time-based
        chart_type: Visual type of the chart
    """

    title: str
    query: str
    report: Optional[str] = None
    type: Optional[str] = "insight"
    relevance: float = 0.5
    is_time_based: Optional[bool] = None
    chart_type: str
    data_connection_id: UUID = None


class QueryRequest(BaseModel):
    """
    Pydantic model for chart generation request parameters.

    Attributes:
        db_type: Type of database to query
        domain: Domain context for the query
        min_date: Optional minimum date for time-based queries
        max_date: Optional maximum date for time-based queries
        api_key: Optional API key for authentication
        role: Role context for the query
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

        Returns:
            dict: Dictionary representation of the model with datetime objects
            converted to ISO format strings
        """
        data = super().dict()
        # Convert datetime objects to strings
        if isinstance(data.get("min_date"), datetime):
            data["min_date"] = data["min_date"].isoformat()
        if isinstance(data.get("max_date"), datetime):
            data["max_date"] = data["max_date"].isoformat()
        return data


class QueryExecutionRequest(BaseModel):
    """
    Request model for executing a SQL query.

    Attributes:
        query: SQL query string to execute
        from_date: Optional start date for filtering (YYYY-MM-DD format)
        to_date: Optional end date for filtering (YYYY-MM-DD format)
    """

    query: str
    from_date: Optional[str] = None
    to_date: Optional[str] = None


class Nl2SQLChatRequest(BaseModel):
    """
    Request model for natural language to SQL translation in a chat context.

    Attributes:
        nl_query: Natural language query to translate to SQL
        api_key: Optional API key for authentication
    """ 

    nl_query: str
    api_key: Optional[str]


class AccessStatus(str, Enum):
    """
    Enumeration of possible access request statuses.

    Values:
        APPROVED: Access request has been approved
        REJECTED: Access request has been rejected
    """

    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ChartStatus(str, Enum):
    """Enumeration of possible chart publication statuses."""

    DRAFT = "draft"
    PUBLISHED = "published"


class UpdateRequestAccess(BaseModel):
    """
    Request model for updating the status of an access request.

    Attributes:
        status: New status for the access request (APPROVED or REJECTED)
    """

    status: AccessStatus


class SaveChartRequest(BaseModel):
    """
    Request model for saving a chart.

    Attributes:
        title: Title of the chart
        query: SQL query for the chart
        report: Optional report context for the chart
        type: Type of the chart (e.g., 'insight', 'metric', 'analysis')
        relevance: Relevance score (0.0 to 1.0)
        is_time_based: Optional flag indicating if the chart is time-based
        chart_type: Visual type of the chart
    """

    title: str
    query: str
    report: Optional[str] = None
    type: Optional[str] = "insight"
    relevance: float = 0.5
    is_time_based: Optional[bool] = None
    chart_type: str
    status: ChartStatus = ChartStatus.DRAFT
    data_connection_id: UUID = None
    x_axis: Optional[str] = None
    y_axis: Optional[str] = None


class SaveChartToDashboardRequest(BaseModel):
    """
    Request model for saving a chart to a specific dashboard.

    Attributes:
        title: Title of the chart
        query: SQL query for the chart
        report: Optional report context for the chart
        type: Type of the chart (e.g., 'insight', 'metric', 'analysis')
        relevance: Relevance score (0.0 to 1.0)
        is_time_based: Optional flag indicating if the chart is time-based
        chart_type: Visual type of the chart
        dashboard_id: UUID of the dashboard to save the chart to
        data_connection_id: UUID of the database connection
    """

    title: str
    query: str
    report: Optional[str] = None
    type: Optional[str] = "insight"
    relevance: Optional[float] = None
    is_time_based: Optional[bool] = None
    chart_type: str
    status: ChartStatus = ChartStatus.PUBLISHED
    dashboard_id: UUID
    data_connection_id: UUID
    x_axis: Optional[str] = None
    y_axis: Optional[str] = None

class UpdateFavoriteChartRequest(BaseModel):
    """
    Request model for updating a chart's favorite status.

    Attributes:
        chart_id: UUID of the chart to update favorite status for
    """

    chart_id: UUID


class AddSpreadsheetRequest(BaseModel):
    """
    Request model for adding a spreadsheet as a data source.

    Attributes:
        connection_name: Name for the spreadsheet connection
        sheet_id: ID of the spreadsheet to connect to
    """

    connection_name: str
    sheet_id: str


class ExecutionConfig(BaseModel):
    """
    Configuration model for query execution settings.

    Attributes:
        host: Host address for query execution (default: 'localhost')
        port: Port number for query execution (default: 8080)
        user: User for query execution (default: 'admin')
        catalog: Catalog name for query execution (default: 'neondb')
        schema: Schema name for query execution (default: 'public')
    """

    host: str = "localhost"
    port: int = 8080
    user: str = "admin"
    catalog: str = "neondb"
    schema: str = "public"


class TrinoQueryRequest(BaseModel):
    """
    Request model for executing queries via Trino.

    Attributes:
        connection_ids: List of database connection UUIDs to use
        role: Role context for the query
        domain: Domain context for the query
        api_key: Optional API key for authentication
        model_name: Model name for AI-powered features (default: 'gemini-1.5-pro')
        min_date: Optional minimum date for time-based queries
        max_date: Optional maximum date for time-based queries
    """

    connection_ids: List[UUID]
    role: str
    domain: str
    api_key: Optional[str] = None
    model_name: str = "gemini-2.5-flash"
    min_date: Optional[Union[datetime, str]] = None
    max_date: Optional[Union[datetime, str]] = None


class QueryDetail(BaseModel):
    """
    Model representing detailed information about a query and its results.

    Attributes:
        sql: SQL query string
        chart_type: Optional type of chart to visualize the query results
        relevance: Optional relevance score of the query results
        title: Optional title for the query results
        category: Optional category for the query
        result: Optional dictionary containing the query results
        is_time_based: Whether the query is time-based
    """

    sql: str
    chart_type: Optional[str] = None
    relevance: Optional[float] = None
    title: Optional[str] = None
    category: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    is_time_based: bool


class TrinoQueryResponse(BaseModel):
    """
    Response model for Trino query execution results.

    Attributes:
        queries: List of query details with results
        min_date: Optional minimum date used in the queries
        max_date: Optional maximum date used in the queries
    """

    queries: List[QueryDetail]
    min_date: Optional[str] = None
    max_date: Optional[str] = None


class DashboardStatsResponse(BaseModel):
    """
    Response model for dashboard statistics.

    Attributes:
        total_projects: Total number of projects the user is part of
        active_dashboards: Total number of active dashboards the user has access to
        total_data_sources: Total number of data sources across all projects the user is part of
        total_team_members: Total number of team members across all projects the user is part of
    """

    total_projects: int
    active_dashboards: int
    total_data_sources: int
    total_team_members: int


class PinnedChartsCountResponse(BaseModel):
    """
    Response model for pinned charts count.

    Attributes:
        message: Status message
        pinned_charts_count: Total number of pinned (favorite) charts for the user
    """

    message: str
    pinned_charts_count: int


class BusinessInsightsRequest(BaseModel):
    """
    Request model for generating business insights.

    Note: Gemini API key is configured on the backend via environment variables.

    Attributes:
        database_connection_id: UUID of the database connection to analyze
    """

    database_connection_id: UUID


class KPIQuery(BaseModel):
    """
    Model representing a KPI query.

    Attributes:
        kpi_title: Title of the KPI
        description: Description of what the KPI measures
        sql_query: SQL query to calculate the KPI
    """

    kpi_title: str
    description: str
    sql_query: str


class QueryResult(BaseModel):
    """
    Model representing the result of a KPI query execution.

    Attributes:
        kpi_title: Title of the KPI
        description: Description of the KPI
        query: SQL query that was executed
        success: Whether the query executed successfully
        data: Query result data
        row_count: Number of rows returned
        error: Error message if query failed
    """

    kpi_title: str
    description: str
    query: str
    success: bool
    data: List[Dict[str, Any]]
    row_count: int
    error: Optional[str] = None


class Recommendation(BaseModel):
    """
    Model representing a business recommendation.

    Attributes:
        priority: Priority level (high, medium, low)
        title: Recommendation title
        description: Detailed description
    """

    priority: str
    title: str
    description: str
    reasoning: Optional[str] = None


class KeyMetricAnalysis(BaseModel):
    """
    Model representing analysis of a key metric.

    Attributes:
        kpi_name: Name of the KPI
        value_interpretation: Interpretation of the metric value
        business_impact: Business impact description
    """

    kpi_name: str
    value_interpretation: str
    business_impact: str
    reasoning: Optional[str] = None


class InsightPattern(BaseModel):
    """
    Model representing an identified insight or pattern with reasoning.
    """

    insight: str
    reasoning: Optional[str] = None


class Concern(BaseModel):
    """
    Model representing an area of concern with supporting reasoning.
    """

    concern: str
    reasoning: Optional[str] = None


class BusinessInsights(BaseModel):
    """
    Model representing comprehensive business insights.

    Attributes:
        executive_summary: Brief overview of key findings
        key_metrics: Analysis of key metrics
        insights_and_patterns: Identified patterns and trends
        recommendations: Actionable recommendations
        areas_of_concern: Metrics requiring attention
    """

    executive_summary: str
    reasoning: Optional[str] = None
    key_metrics: List[KeyMetricAnalysis]
    insights_and_patterns: List[InsightPattern]
    recommendations: List[Recommendation]
    areas_of_concern: List[Concern]


class BusinessInsightsResponse(BaseModel):
    """
    Response model for business insights generation.

    Attributes:
        message: Status message
        database_name: Name of the analyzed database
        database_type: Type of database (optional, defaults to "unknown")
        kpis_analyzed: Number of KPIs analyzed
        kpi_queries: List of generated KPI queries
        query_results: Results from query execution
        insights: AI-generated business insights
    """

    message: str
    database_name: str
    database_type: Optional[str] = "postgres"
    kpis_analyzed: int
    kpi_queries: List[KPIQuery]
    query_results: List[QueryResult]
    insights: BusinessInsights


class StrategicPriority(BaseModel):
    """
    Model representing a strategic priority.

    Attributes:
        rank: Priority ranking (1-5)
        title: Priority title
        description: Detailed description
        impact: Impact level (high, medium, low)
    """

    rank: int
    title: str
    description: str
    impact: str
    reasoning: Optional[str] = None


class RiskDetail(BaseModel):
    """
    Model representing a risk entry with reasoning.
    """

    risk: str
    reasoning: Optional[str] = None


class RiskAssessment(BaseModel):
    """
    Model representing risk assessment.

    Attributes:
        critical_risks: List of critical risks
        moderate_risks: List of moderate risks
    """

    critical_risks: List[RiskDetail]
    moderate_risks: List[RiskDetail]


class Opportunity(BaseModel):
    """
    Model representing a business opportunity.

    Attributes:
        title: Opportunity title
        description: Detailed description
        potential_impact: Expected business impact
    """

    title: str
    description: str
    potential_impact: str
    reasoning: Optional[str] = None


class PatternDetail(BaseModel):
    """
    Model representing a cross-database pattern with reasoning.
    """

    pattern: str
    reasoning: Optional[str] = None


class ConsolidatedInsights(BaseModel):
    """
    Model representing consolidated insights across databases.

    Attributes:
        overall_health_score: Overall business health (excellent, good, fair, poor)
        health_assessment: Detailed health assessment
        cross_database_patterns: Patterns identified across databases
        strategic_priorities: Top strategic priorities
        risk_assessment: Risk assessment
        opportunities: Business opportunities
    """

    overall_health_score: str
    health_assessment: str
    reasoning: Optional[str] = None
    cross_database_patterns: List[PatternDetail]
    strategic_priorities: List[StrategicPriority]
    risk_assessment: RiskAssessment
    opportunities: List[Opportunity]


class BusinessInsightRecord(BaseModel):
    """
    Serialized record for a persisted business insight.
    """

    id: UUID
    project_id: UUID
    user_id: UUID
    executive_summary: str
    key_metrics: Dict[str, Any]
    insights_and_patterns: Any
    recommendations: Any
    areas_of_concern: Any
    created_at: datetime


class LatestBusinessInsightResponse(BaseModel):
    """
    Response model for fetching the latest business insight.
    """

    message: str
    insight: BusinessInsightRecord




class DatabaseInsightSummary(BaseModel):
    """
    Model representing summary of insights for a single database.

    Attributes:
        database_id: UUID of the database
        database_name: Name of the database
        database_type: Type of database
        status: Analysis status (success, failed, skipped)
        kpis_analyzed: Number of KPIs analyzed
        successful_queries: Number of successful queries
        insights: Business insights (if successful)
        error: Error message (if failed)
    """

    database_id: str
    database_name: str
    database_type: str
    status: str
    kpis_analyzed: Optional[int] = None
    successful_queries: Optional[int] = None
    insights: Optional[BusinessInsights] = None
    error: Optional[str] = None


class ProjectInsightsResponse(BaseModel):
    """
    Response model for project-wide business insights.

    Attributes:
        message: Status message
        project_id: UUID of the project
        project_name: Name of the project
        total_databases_analyzed: Total number of databases in project
        successful_analyses: Number of successful database analyses
        database_insights: List of insights from each database
        consolidated_insights: Unified strategic insights across all databases
    """

    message: str
    project_id: str
    project_name: str
    total_databases_analyzed: int
    successful_analyses: int
    database_insights: List[DatabaseInsightSummary]
    consolidated_insights: ConsolidatedInsights


class ConnectionStatsResponse(BaseModel):
    """Response model for database connection statistics"""
    
    total_connections: int
    active_connections: int
    inactive_connections: int
    project_id: str


class ConnectionCheckResult(BaseModel):
    """Result of a single connection check"""
    
    connection_id: str
    connection_name: str
    status: bool
    last_checked: str
    error_message: Optional[str] = None


class ConnectionCheckResponse(BaseModel):
    """Response model for connection check endpoint"""
    
    message: str
    project_id: str
    total_checked: int
    successful_connections: int
    failed_connections: int
    results: List[ConnectionCheckResult]

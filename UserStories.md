
# Viz_AI – QA User Stories (Regular User)

## User Story: Login and Landing Page Access

**As a** registered user,  
**I want to** log in using the password sent to my email,  
**so that** I can access my personal dashboard and data.

#### Acceptance Criteria:
- [ ] User can log in using email and password.
- [ ] If credentials are correct, user is redirected to the Projects page.
- [ ] Login fails gracefully with appropriate message on incorrect credentials.

---
## User Story: First-Time User Project Creation

**As a** first-time user,  
**I want to** create a new project if I don’t have any,  
**so that** I can begin setting up my workspace.

#### Acceptance Criteria:
- [ ] If user has no projects, an empty state is shown.
- [ ] “Create Project” button is available and leads to a project creation flow.

---
## User Story: View Projects

**As a** logged-in user,  
**I want to** view a list of all projects I have access to,  
**so that** I can choose which one to work on.

#### Acceptance Criteria:
- [ ] User sees a list of accessible projects.
- [ ] Each project is clickable and navigates to its landing page.
- [ ] If the user has no projects, show an empty state with option to create a new one.

---

## User Story: View Project Landing Page

**As a** project member,  
**I want to** view my favourite dashboards and charts on the landing page,  
**so that** I can quickly access important visualizations.

#### Acceptance Criteria:
- [ ] Landing page shows user's favourite dashboards.
- [ ] The landing page also displays the user's favorite charts in a separate section(below the favourite dashboards).
- [ ] Clicking on a dashboard opens its charts view.

---

## User Story: View Dashboard Charts and Users

**As a** project member,  
**I want to** view all charts within a selected dashboard,  
**so that** I can understand the data representations associated with that dashboard.

#### Acceptance Criteria:
- [ ] Charts belonging to a dashboard are visible after clicking the dashboard.
- [ ] A “Manage/View Users” dropdown shows users assigned to the dashboard.
- [ ] Charts can be previewed in a modal or full-screen view.

---

## User Story: Handle Chart Access Restrictions

**As a** user without access to a chart,  
**I want to** send a request to my admin,  
**so that** I can request permission to view restricted content.

#### Acceptance Criteria:
- [ ] Blocked charts are visually distinguished (e.g., grayed out).
- [ ] Clicking a restricted chart shows a message and option to request access.
- [ ] Access requests are sent to project admins for approval.

---

## User Story: Add a Database Connection

**As a** user in a project,  
**I want to** add a database connection via URL or form fields,  
**so that** I can start generating insights from my data.

#### Acceptance Criteria:
- [ ] User can enter connection details manually or via hosted link.
- [ ] Database passwords are obscured so that they are not visible to anyone.
- [ ] Connection is verified and saved if successful.
- [ ] Connection can be edited or deleted later.

---

## User Story: View Available Datasources

**As a** user,  
**I want to** view all the datasources I’ve connected to a project,  
**so that** I can choose which one to use for chart generation.

#### Acceptance Criteria:
- [ ] User can access a Datasources page or dropdown.
- [ ] All previously added datasources are listed with name and type.
- [ ] Invalid or broken connections are marked appropriately.

---

## User Story: Switch Between Datasources

**As a** user,  
**I want to** switch between different datasources,  
**so that** I can generate charts from different datasets.

#### Acceptance Criteria:
- [ ] User can select a datasource from a dropdown or list.
- [ ] Selected datasource context is preserved when generating or querying charts.
- [ ] Chart generation uses the schema of the currently selected datasource.

---

## User Story: Edit or Delete a Datasource

**As a** user,  
**I want to** update or remove a datasource I previously added,  
**so that** I can manage outdated or incorrect connections.

#### Acceptance Criteria:
- [ ] Each datasource has edit and delete options.
- [ ] Editing a datasource allows changing connection parameters.
- [ ] Deleting a datasource prompts for confirmation and removes it cleanly.

---

## User Story: Enable Data Analysis Toggle

**As a** user adding a connection,  
**I want to** enable or disable the “Read your data” toggle,  
**so that** I can control whether AI uses my data to enhance query generation.

#### Acceptance Criteria:
- [ ] Toggle is visible during database connection setup.
- [ ] When enabled, user consents to data being analyzed.
- [ ] Toggle state is saved with the connection metadata.

---

## User Story: Generate Charts from Data

**As a** user,  
**I want to** select a datasource and auto-generate charts,  
**so that** I can visualize key insights without writing code.

#### Acceptance Criteria:
- [ ] User selects a valid datasource.
- [ ] “Generate Charts” button is enabled for selected datasource.
- [ ] Charts are generated via LLM and displayed in preview mode.
- [ ] User can save or assign charts to a dashboard.

---

## User Story: Create a Dashboard

**As a** user,  
**I want to** create a new dashboard,  
**so that** I can organize my charts meaningfully.

#### Acceptance Criteria:
- [ ] Dashboard creation form includes name and optional description.
- [ ] User can assign existing charts to the new dashboard.
- [ ] Dashboard appears in landing page and dashboards list after creation.

---

## User Story: Favorite Charts

**As a** user,  
**I want to** mark charts as favourites,  
**so that** I can access them quickly from my landing page.

#### Acceptance Criteria:
- [ ] Charts have a favourite toggle.
- [ ] Favourited charts appear in landing page and are saved to user profile.
- [ ] Unfavouriting removes them from favourites view.

---

## User Story: Query in Natural Language

**As a** user,  
**I want to** enter natural language queries on the Charts page,  
**so that** I can generate relevant SQL charts without knowing SQL.

#### Acceptance Criteria:
- [ ] A text input accepts natural language queries.
- [ ] System generates a chart using LLM response.
- [ ] User can preview and save generated charts.
      
---


## User Story: Preview Generated Charts

**As a** user,  
**I want to** preview the charts generated by the AI,  
**so that** I can decide whether to save or discard them.

#### Acceptance Criteria:
- [ ] Each generated chart is shown with a preview.
- [ ] User can click into a chart to view the query and chart type.

---

## User Story: Assign Charts to Dashboards

**As a** user,  
**I want to** assign a saved chart to one or more dashboards,  
**so that** it is organized and visible to others in the project.

#### Acceptance Criteria:
- [ ] After saving a chart, user can choose dashboards to assign it to.
- [ ] Assigned dashboards are shown in the chart details.
- [ ] Chart is visible in the corresponding dashboards after assignment.

---

## User Story: Export or Download Chart Data

**As a** user,  
**I want to** download the data behind a chart,  
**so that** I can use it for offline analysis or reports.

#### Acceptance Criteria:
- [ ] Each chart has an “Export” or “Download CSV” option.
- [ ] Clicking the option downloads the chart’s underlying dataset as CSV.
- [ ] Export respects data visibility and user permissions.
      
### User Story: Access Role Management Page
As a user with role management permissions,  
I want to access the Roles page,  
so that I can view and manage the roles within the project.

**Acceptance Criteria:**
- [ ] The "Roles" tab is visible in the sidebar or navigation.
- [ ] User sees a list of all roles in the project.
- [ ] Each role displays its name, description, and assigned permissions.
- [ ] Edit and delete buttons are visible if the user has edit/delete role permission.

---

### User Story: Add a New Role
As a user with permission to manage roles,  
I want to create a new role with specific permissions,  
so that I can define access levels for different project members.

**Acceptance Criteria:**
- [ ] "Add Role" button is available on the Roles page.
- [ ] Role creation form includes name, description, and permission selection.
- [ ] Table access restrictions (blacklisting) are available in the form.
- [ ] On submit, the new role appears in the role list with correct settings.

---

### User Story: Access User Management Page
As a user with user management permissions,  
I want to access the Users page,  
so that I can view all project members and manage their roles.

**Acceptance Criteria:**
- [ ] "Users" tab is visible and accessible.
- [ ] User list displays name, email, and assigned roles.
- [ ] Edit and delete actions are available if the user has respective permissions.

---

### User Story: Add a New User
As a user with permission to manage users,  
I want to add a new user to the project and assign roles,  
so that they can begin contributing with the correct access.

**Acceptance Criteria:**
- [ ] "Add User" button is available on the Users page.
- [ ] User creation form includes name, email, password, and role(s) selection.
- [ ] Form validation ensures email uniqueness and password strength.
- [ ] On submit, new user is added to the list and receives default project access.


# Super User Stories for Viz_AI

---

### **User Story: Login as Superuser**

**As a** superuser,  
**I want to** log in with credentials provided during app setup,  
**so that** I can initialize and manage the application setup.

#### Acceptance Criteria:
- [ ] Superuser can log in using the email and password configured by the developer.
- [ ] Superuser is directed to a project management landing page.
- [ ] If no projects exist, a prompt or empty state encourages project creation.

---

### **User Story: Create a Project**

**As a** superuser,  
**I want to** create new projects,  
**so that** I can manage separate workspaces with users, roles, and dashboards.

#### Acceptance Criteria:
- [ ] A “Create Project” form is accessible from the dashboard.
- [ ] Project name and optional description are entered.
- [ ] Project is listed after creation and becomes selectable.

---

### **User Story: Create a Role for a Project**

**As a** superuser,  
**I want to** create roles for a selected project,  
**so that** I can assign tailored permissions to different types of users.

#### Acceptance Criteria:
- [ ] Role form allows adding a name, description, and permission selection.
- [ ] Available permissions include chart, dashboard, project, datasource, and user actions.
- [ ] A dropdown for table blacklisting is available.
- [ ] Role is saved and visible in the roles list for that project.

---

### **User Story: Blacklist Tables for a Role**

**As a** superuser,  
**I want to** blacklist specific tables for a role,  
**so that** users with that role cannot access data from those tables.

#### Acceptance Criteria:
- [ ] Table selection dropdown is shown when creating or editing a role.
- [ ] Charts using blacklisted tables are automatically restricted for users with that role.
- [ ] Blocked users can send a request to access specific charts.

---

### **User Story: Add Users to a Project**

**As a** superuser,  
**I want to** add users to a project and assign them roles,  
**so that** they can participate according to their permissions.

#### Acceptance Criteria:
- [ ] A form allows entering name, email, password, and selecting a role.
- [ ] User is assigned to the selected project and listed in the user table.
- [ ] User list allows editing or deleting users.

---

### **User Story: Manage Roles and Users**

**As a** superuser,  
**I want to** view, edit, or delete roles and users,  
**so that** I can keep project access organized and up to date.

#### Acceptance Criteria:
- [ ] Roles and users are listed in respective tables per project.
- [ ] Each entry includes actions for edit and delete.
- [ ] Changes reflect in real time and enforce updated permissions.

---

### **User Story: Connect a Datasource as Admin**

**As a** superuser,  
**I want to** connect datasources to a project,  
**so that** I or other users can generate charts from them.

#### Acceptance Criteria:
- [ ] Same datasource form as regular users is available.
- [ ] Datasource appears in project’s datasource list after setup.
- [ ] Permissions to view or edit datasources follow assigned role rules.

---

### **User Story: Generate and Assign Charts/Dashboards**

**As a** superuser,  
**I want to** generate charts using connected datasources and assign them to dashboards,  
**so that** users see useful visuals immediately upon login.

#### Acceptance Criteria:
- [ ] Superuser can use the same chart generation interface as users.
- [ ] Dashboards can be created and edited.
- [ ] Charts can be added to any dashboard.
- [ ] Superuser can assign dashboards to specific users.

---

### **User Story: Manage Access Requests via Notifications**

**As a** superuser,  
**I want to** view and act on chart access requests from users,  
**so that** I can grant or deny visibility to restricted charts.

#### Acceptance Criteria:
- [ ] Notifications page lists all pending access requests.
- [ ] Each request shows user, chart, time of request, and reason if available.
- [ ] Superuser can approve or reject requests.
- [ ] Approved charts become visible to requesting users on next login.

---

### **User Story: View and Respond to Access Denied Requests**

**As a** user,  
**I want to** request access to charts I’m restricted from due to table blacklisting,  
**so that** I can potentially gain the required permissions.

#### Acceptance Criteria:
- [ ] Blocked charts show a “Request Access” button.
- [ ] Request is logged and visible to the admin in the Notifications tab.
- [ ] Admin response (approval or rejection) reflects in user’s chart access state.

---


### **User Story: View User Permissions**

**As a** superuser,  
**I want to** view the permissions assigned to a user,  
**so that** I can ensure they have the correct level of access.

#### Acceptance Criteria:
- [ ] User permissions are listed when viewing user details.
- [ ] Permissions are listed clearly, showing which roles they derive from.
- [ ] Changes to roles or permissions update in real-time.

---

### **User Story: Create a Role with Custom Permissions**

**As a** superuser,  
**I want to** create a custom role with specific permissions,  
**so that** I can define precise access for users in different project areas.

#### Acceptance Criteria:
- [ ] A new role creation form allows selecting individual permissions.
- [ ] Custom roles can be named and described with specific access settings.
- [ ] Permissions like “Create chart” or “Edit project” can be toggled on/off.

---

### **User Story: Edit User Roles**

**As a** superuser,  
**I want to** edit the roles assigned to an existing user,  
**so that** I can change their access when their responsibilities change.

#### Acceptance Criteria:
- [ ] The user’s role(s) can be modified from the user management page.
- [ ] New roles can be added, and existing roles can be removed.
- [ ] Permissions linked to updated roles are automatically applied.

---

### **User Story: Delete User from a Project**

**As a** superuser,  
**I want to** delete a user from a project,  
**so that** they no longer have access to the project or its data.

#### Acceptance Criteria:
- [ ] The user is removed from the project’s user list.
- [ ] All permissions and roles associated with the user are revoked.
- [ ] User no longer has access to the project upon their next login.

---

### **User Story: Reassign Users to Different Roles**

**As a** superuser,  
**I want to** reassign users to different roles within a project,  
**so that** I can update their responsibilities and permissions.

#### Acceptance Criteria:
- [ ] Users can be re-assigned roles from the user management page.
- [ ] The system notifies the user of their new role and updated permissions.
- [ ] Reassigning roles updates the user's permissions immediately.

---

### **User Story: Role Description for New Users**

**As a** superuser,  
**I want to** add a clear description for each role,  
**so that** users understand their responsibilities and the permissions they have.

#### Acceptance Criteria:
- [ ] Role descriptions are visible when adding or editing a role.
- [ ] Descriptions clearly explain the responsibilities and permissions granted by each role.
- [ ] Descriptions are shown to users when assigning roles.

---

### **User Story: Role-based Table Access Restrictions**

**As a** superuser,  
**I want to** restrict table access for specific roles,  
**so that** sensitive data is protected from unauthorized users.

#### Acceptance Criteria:
- [ ] A list of available tables is shown when editing role permissions.
- [ ] Each table can be blacklisted for a specific role to prevent access.
- [ ] Any chart based on a blacklisted table is automatically restricted for the user with that role.

---

### **User Story: Permission Inheritance for Role Changes**

**As a** superuser,  
**I want to** ensure that when roles are modified, all permission changes automatically propagate to all users with that role,  
**so that** I don't have to manually update every user’s permissions.

#### Acceptance Criteria:
- [ ] When a role’s permissions are updated, all users assigned to that role are immediately impacted.
- [ ] Changes in permissions are automatically reflected in each user’s access upon next login.
- [ ] Admins receive a notification when role changes occur, and users are informed of permission updates.

---


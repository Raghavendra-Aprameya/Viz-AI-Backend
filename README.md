# Viz-AI Backend

A robust FastAPI-based backend service for managing data visualization projects, dashboards, and user roles.

## Features

- **User Management**
  - User authentication and authorization
  - Role-based access control
  - Super user management
  - User-project associations

- **Project Management**
  - Create and manage projects
  - Project ownership tracking
  - Multi-user collaboration

- **Dashboard System**
  - Create and manage dashboards
  - User dashboard permissions
  - Dashboard sharing capabilities

- **Role & Permission System**
  - Granular permission control
  - Custom role creation
  - Role-based access management

- **Database Connections**
  - Multiple database support
  - Secure connection management
  - Connection string encryption

## Technology Stack

- **Framework**: FastAPI
- **Database**: PostgreSQL with SQLAlchemy ORM
- **Authentication**: JWT-based authentication
- **Migration**: Alembic
- **Security**: bcrypt for password hashing

## Prerequisites

- Python 3.9+
- PostgreSQL
- pip (Python package manager)

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd Viz-AI-Backend

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # For Unix/macOS
 ```
```

3. Install dependencies:
```bash
pip install -r requirements.txt
 ```

4. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
 ```

5. Run database migrations:
```bash
alembic upgrade head
 ```

## Running the Application
Start the development server:

```bash
uvicorn app.main:app --reload
 ```

The API will be available at http://localhost:8000

## API Documentation
Once the application is running, you can access:

- Swagger UI documentation: http://localhost:8000/docs
- ReDoc documentation: http://localhost:8000/redoc
## Project Structure
```plaintext
Viz-AI-Backend/
├── alembic/            # Database migrations
├── app/
│   ├── core/          # Core configuration
│   ├── models/        # Database models
│   ├── routes/        # API routes
│   ├── schemas/       # Pydantic models
│   ├── services/      # Business logic
│   └── utils/         # Utility functions
├── tests/             # Test cases
└── requirements.txt   # Project dependencies
 ```

## Contributing
1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## Dashboard Embed Feature (Domain-Locked)

### Overview
The embed feature allows dashboard owners to generate secure, **domain-locked** shareable links that render dashboards in an `<iframe>` on authorized external websites — **without requiring the viewer to log in**.

### Two-Phase Flow

**Phase A — App Registration (Home Page)**
1. User clicks "Create app" on the home page
2. Registers a company name + domain URL (e.g. `fedex.com`)
3. App appears in the "Registered Apps" section

**Phase B — Dashboard Allowed Domains + Embed Token**
1. User opens a dashboard and adds "Allowed domains" (selects registered apps)
2. "Create shareable link" is only enabled when ≥1 domain is attached
3. Token is generated with a snapshot of the allowed domains
4. When an iframe loads, the Origin header is checked against the snapshot
5. If the origin doesn't match → 403

### Architecture
```
Phase A:
  POST /api/v1/apps                          → Register app with domain
  GET  /api/v1/apps                          → List user's apps

Phase B:
  POST /api/v1/dashboards/:id/allowed-domains → Attach app domains to dashboard
  POST /api/v1/backend/dashboards/:id/share-token → Generate token (snapshots allowed_domains)

Runtime:
  GET /api/v1/embed/:token_id
    → Check Origin header against allowed_domains_snapshot → 403 if rejected
    → Validate token (active, not expired, HMAC matches)
    → Serve standalone HTML page with Chart.js
    → Each chart fetches data via GET /api/v1/embed/:token_id/data/:chart_id
```

### API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/v1/apps` | JWT | Create app registration |
| `GET` | `/api/v1/apps` | JWT | List apps for current user |
| `DELETE` | `/api/v1/apps/:app_id` | JWT | Soft delete app |
| `POST` | `/api/v1/dashboards/:id/allowed-domains` | JWT | Attach app domains to dashboard |
| `GET` | `/api/v1/dashboards/:id/allowed-domains` | JWT | List attached domains |
| `DELETE` | `/api/v1/dashboards/:id/allowed-domains/:app_id` | JWT | Remove domain from dashboard |
| `POST` | `/api/v1/backend/dashboards/:id/share-token` | JWT | Create or return existing token |
| `GET` | `/api/v1/backend/dashboards/:id/share-token` | JWT | Get existing token info |
| `DELETE` | `/api/v1/backend/dashboards/:id/share-token` | JWT | Revoke token (soft-delete) |
| `GET` | `/api/v1/embed/:token_id` | None | Render standalone embed HTML |
| `GET` | `/api/v1/embed/:token_id/data/:chart_id` | None | Serve chart data (token-gated) |

### Environment Variables

Add to `.env`:
```
EMBED_SERVER_SECRET="your-production-secret-here"
```
If not set, falls back to `SECRET_KEY`. **Must be changed in production.**

### Database Models

Three models are involved (run migrations manually after review):

```bash
alembic revision --autogenerate -m "add apps and dashboard_allowed_domains"
alembic upgrade head
```

1. **`apps`** — Registered external applications (company_name + domain_url)
2. **`dashboard_allowed_domains`** — Join table linking dashboards to allowed apps
3. **`share_tokens`** — Existing model + new `allowed_domains_snapshot` column (ARRAY)

### Security
- Tokens are signed with HMAC-SHA256 using `EMBED_SERVER_SECRET`
- **Domain-lock**: Origin header is checked against `allowed_domains_snapshot` on every request
- If Origin is null/missing (direct browser tab): allowed for testing
- If Origin doesn't match any allowed domain: returns 403
- Domain normalization is consistent: strips protocol, www., trailing slash, ports
- Tokens can be revoked (sets `is_active = false`, preserves audit trail)
- Optional expiry: 7, 30, or 90 days
- Full token is never logged (first 8 chars only)

### Frontend Integration

**Home Page (ProjectsView.tsx):**
- "Create App" button opens `CreateAppModal` with company name + domain URL
- Registered Apps section displays app cards with company name, domain, delete option

**Dashboard Header (DashboardDetailView.tsx):**
- `AllowedDomainsSection` shows attached domains as badges with add/edit/remove
- "Create shareable link" button is disabled until ≥1 domain is attached
- Tooltip: "Add at least one allowed domain first" when disabled

**Share Modal (ShareLinkModal.tsx):**
- Unchanged — displays embed URL, iframe snippet, copy buttons, expiry, revoke

### Logging
All operations are logged with `[APP]` or `[EMBED]` prefix at INFO level:
```
[APP][STEP 1] User abc12345... clicked "Create app"
[APP][STEP 2] App created — app_id: def67890..., domain: fedex.com
[APP][STEP 3] App list refreshed — 3 apps visible for user abc12345...
[EMBED][STEP 5] Allowed domains set for dashboard abc12345... — domains: ['fedex.com', 'dhl.com']
[EMBED][STEP 7] Token generated — token: xyz12345..., dashboard: abc12345..., domains: ['fedex.com']
[EMBED][STEP 10] Embed request — token: xyz12345..., origin: https://fedex.com
[EMBED][STEP 11] Origin check — origin: https://fedex.com, allowed: ['fedex.com'], result: allowed
[EMBED][STEP 12] Token validation — result: valid
```

## License
[Add your license information here]

## Support
For support, please contact developer@webknot.in
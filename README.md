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
## License
[Add your license information here]

## Support
For support, please contact developer@webknot.in
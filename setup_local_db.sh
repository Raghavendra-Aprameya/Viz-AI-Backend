#!/bin/bash

# Quick setup script for local PostgreSQL database
# Usage: ./setup_local_db.sh

set -e

echo "=========================================="
echo "Local PostgreSQL Setup Script"
echo "=========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Default values
DB_NAME="${DB_NAME:-vizai_db}"
DB_USER="${DB_USER:-vizai_user}"
DB_PASSWORD="${DB_PASSWORD:-vizai_password}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"

echo -e "${YELLOW}Database Configuration:${NC}"
echo "  Database Name: $DB_NAME"
echo "  Database User: $DB_USER"
echo "  Database Host: $DB_HOST"
echo "  Database Port: $DB_PORT"
echo ""

# Check if PostgreSQL is running
echo "Checking if PostgreSQL is running..."
if ! pg_isready -h "$DB_HOST" -p "$DB_PORT" > /dev/null 2>&1; then
    echo -e "${RED}✗ PostgreSQL is not running on $DB_HOST:$DB_PORT${NC}"
    echo "Please start PostgreSQL first:"
    echo "  macOS: brew services start postgresql"
    echo "  Linux: sudo systemctl start postgresql"
    exit 1
fi
echo -e "${GREEN}✓ PostgreSQL is running${NC}"
echo ""

# Create database and user
echo "Creating database and user..."
psql -h "$DB_HOST" -p "$DB_PORT" -U postgres -c "CREATE DATABASE $DB_NAME;" 2>/dev/null || echo "Database already exists"
psql -h "$DB_HOST" -p "$DB_PORT" -U postgres -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD';" 2>/dev/null || echo "User already exists"
psql -h "$DB_HOST" -p "$DB_PORT" -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;"
psql -h "$DB_HOST" -p "$DB_PORT" -U postgres -d "$DB_NAME" -c "GRANT ALL ON SCHEMA public TO $DB_USER;"
psql -h "$DB_HOST" -p "$DB_PORT" -U postgres -d "$DB_NAME" -c "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO $DB_USER;"
echo -e "${GREEN}✓ Database and user created${NC}"
echo ""

# Test connection
echo "Testing connection..."
if psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "SELECT 1;" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Connection successful${NC}"
else
    echo -e "${RED}✗ Connection failed${NC}"
    echo "You may need to update pg_hba.conf to allow local connections"
    exit 1
fi
echo ""

# Generate connection string
CONNECTION_STRING="postgresql://$DB_USER:$DB_PASSWORD@$DB_HOST:$DB_PORT/$DB_NAME"
echo -e "${GREEN}Connection String:${NC}"
echo "$CONNECTION_STRING"
echo ""

# Create .env.local.example
echo "Creating .env.local.example file..."
cat > .env.local.example << EOF
# Local PostgreSQL Database Configuration
DB_URI=$CONNECTION_STRING

# Keep your other environment variables from .env
# SECRET_KEY=...
# REFRESH_SECRET_KEY=...
# etc.
EOF
echo -e "${GREEN}✓ Created .env.local.example${NC}"
echo ""

echo "=========================================="
echo -e "${GREEN}Setup Complete!${NC}"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Copy .env.local.example to .env.local"
echo "2. Update your .env file with the DB_URI above"
echo "3. Run migrations: alembic upgrade head"
echo "4. Run migration script: python migrate_neon_to_local.py"
echo ""


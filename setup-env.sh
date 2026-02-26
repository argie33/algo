#!/bin/bash

# Setup script for Algo Stock Platform
# This script sets up PostgreSQL, initializes the database, and prepares the environment

set -e

echo "================================"
echo "Algo Stock Platform - Setup"
echo "================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running in WSL
if grep -qi microsoft /proc/version; then
    echo -e "${YELLOW}✓ Running in WSL2${NC}"
    IS_WSL=true
else
    IS_WSL=false
fi

# Step 1: Check dependencies
echo ""
echo "Step 1: Checking system dependencies..."
echo "=========================================="

# Check Node.js
if command -v node &> /dev/null; then
    NODE_VERSION=$(node --version)
    echo -e "${GREEN}✓ Node.js installed: $NODE_VERSION${NC}"
else
    echo -e "${RED}✗ Node.js not found. Please install Node.js 20.19+${NC}"
    exit 1
fi

# Check npm
if command -v npm &> /dev/null; then
    NPM_VERSION=$(npm --version)
    echo -e "${GREEN}✓ npm installed: $NPM_VERSION${NC}"
else
    echo -e "${RED}✗ npm not found${NC}"
    exit 1
fi

# Check Python
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version)
    echo -e "${GREEN}✓ Python3 installed: $PYTHON_VERSION${NC}"
else
    echo -e "${RED}✗ Python3 not found${NC}"
    exit 1
fi

# Step 2: Check PostgreSQL
echo ""
echo "Step 2: Checking PostgreSQL..."
echo "==============================="

if command -v psql &> /dev/null; then
    PG_VERSION=$(psql --version)
    echo -e "${GREEN}✓ PostgreSQL client installed: $PG_VERSION${NC}"
else
    echo -e "${YELLOW}⚠ PostgreSQL client not found${NC}"
    echo "  Installing PostgreSQL..."

    if [ "$IS_WSL" = true ]; then
        # For WSL, try to install without sudo first
        if sudo apt-get update && sudo apt-get install -y postgresql postgresql-contrib postgresql-client 2>/dev/null; then
            echo -e "${GREEN}✓ PostgreSQL installed${NC}"
        else
            echo -e "${RED}✗ Failed to install PostgreSQL${NC}"
            echo "  Try: sudo apt-get install postgresql postgresql-contrib"
            exit 1
        fi
    else
        echo -e "${RED}Please install PostgreSQL 16+ manually${NC}"
        exit 1
    fi
fi

# Check if PostgreSQL service is running
echo ""
if [ "$IS_WSL" = true ]; then
    if pgrep -x "postgres" > /dev/null; then
        echo -e "${GREEN}✓ PostgreSQL service is running${NC}"
    else
        echo -e "${YELLOW}⚠ PostgreSQL service not running${NC}"
        echo "  Attempting to start PostgreSQL..."

        if sudo service postgresql start &>/dev/null || sudo systemctl start postgresql &>/dev/null; then
            echo -e "${GREEN}✓ PostgreSQL service started${NC}"
            sleep 2
        else
            echo -e "${RED}✗ Could not start PostgreSQL service${NC}"
            echo "  Try: sudo service postgresql start"
            exit 1
        fi
    fi
fi

# Step 3: Initialize Database
echo ""
echo "Step 3: Initializing Database..."
echo "================================="

DB_USER="stocks"
DB_NAME="stocks"
DB_PORT="5432"

# Try to create database and user
echo "  Creating database and user..."

# Check if database exists
if psql -h localhost -U postgres -lqt 2>/dev/null | cut -d \| -f 1 | grep -qw $DB_NAME; then
    echo -e "${YELLOW}  ⚠ Database '$DB_NAME' already exists${NC}"
else
    # Create database and user
    if PGPASSWORD=postgres psql -h localhost -U postgres -c "CREATE DATABASE $DB_NAME;" 2>/dev/null; then
        echo -e "${GREEN}  ✓ Database created${NC}"
    else
        echo -e "${YELLOW}  ⚠ Could not create database (may already exist)${NC}"
    fi
fi

# Create user if doesn't exist
if PGPASSWORD=postgres psql -h localhost -U postgres -c "CREATE USER $DB_USER WITH ENCRYPTED PASSWORD 'bed0elAn';" 2>/dev/null; then
    echo -e "${GREEN}  ✓ User created${NC}"
else
    # User might already exist, try to update password
    PGPASSWORD=postgres psql -h localhost -U postgres -c "ALTER USER $DB_USER WITH ENCRYPTED PASSWORD 'bed0elAn';" 2>/dev/null || true
    echo -e "${YELLOW}  ⚠ User already exists (password updated)${NC}"
fi

# Grant privileges
PGPASSWORD=postgres psql -h localhost -U postgres -d $DB_NAME -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;" 2>/dev/null || true

echo "  Initializing schema..."
if PGPASSWORD=bed0elAn psql -h localhost -U $DB_USER -d $DB_NAME -f init-db.sql >/dev/null 2>&1; then
    echo -e "${GREEN}✓ Database schema initialized${NC}"
else
    echo -e "${RED}✗ Failed to initialize database schema${NC}"
    echo "  Try manually: psql -h localhost -U $DB_USER -d $DB_NAME -f init-db.sql"
    exit 1
fi

# Verify database
TABLE_COUNT=$(PGPASSWORD=bed0elAn psql -h localhost -U $DB_USER -d $DB_NAME -tc "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';" 2>/dev/null || echo "0")
TABLE_COUNT=$(echo $TABLE_COUNT | xargs)

if [ "$TABLE_COUNT" -gt 0 ]; then
    echo -e "${GREEN}✓ Database verified - $TABLE_COUNT tables created${NC}"
else
    echo -e "${RED}✗ Database verification failed${NC}"
    exit 1
fi

# Step 4: Install Node dependencies
echo ""
echo "Step 4: Installing Node.js Dependencies..."
echo "=========================================="

# Main webapp
cd /home/arger/algo/webapp
if [ -f "package.json" ]; then
    echo "  Installing main webapp dependencies..."
    npm install >/dev/null 2>&1 || true
fi

# Lambda backend
if [ -d "lambda" ]; then
    cd lambda
    echo "  Installing backend dependencies..."
    npm install >/dev/null 2>&1 || true
    cd ..
fi

# Frontend
if [ -d "frontend" ]; then
    cd frontend
    echo "  Installing frontend dependencies..."
    npm install >/dev/null 2>&1 || true
    cd ..
fi

# Frontend admin
if [ -d "frontend-admin" ]; then
    cd frontend-admin
    echo "  Installing admin frontend dependencies..."
    npm install >/dev/null 2>&1 || true
    cd ..
fi

cd /home/arger/algo

# Step 5: Install Python dependencies
echo ""
echo "Step 5: Installing Python Dependencies..."
echo "=========================================="

# Check if venv exists
if [ ! -d "venv" ]; then
    echo "  Creating Python virtual environment..."
    python3 -m venv venv
    echo -e "${GREEN}✓ Virtual environment created${NC}"
else
    echo -e "${GREEN}✓ Virtual environment exists${NC}"
fi

# Activate venv and install requirements
source venv/bin/activate 2>/dev/null || . venv/bin/activate

echo "  Installing Python packages..."
if [ -f "requirements.txt" ]; then
    pip install -q -r requirements.txt 2>/dev/null || echo -e "${YELLOW}⚠ Some Python packages may have failed to install${NC}"
fi

# Step 6: Environment Summary
echo ""
echo "================================"
echo "Setup Complete!"
echo "================================"
echo ""
echo "Database Configuration:"
echo "  Host: localhost"
echo "  Port: $DB_PORT"
echo "  Database: $DB_NAME"
echo "  User: $DB_USER"
echo "  Tables: $TABLE_COUNT"
echo ""
echo "Next Steps:"
echo ""
echo "1. Start PostgreSQL (if not running):"
echo "   sudo service postgresql start"
echo ""
echo "2. Start Backend Server:"
echo "   cd /home/arger/algo/webapp/lambda"
echo "   node index.js"
echo ""
echo "3. Start Frontend (in another terminal):"
echo "   cd /home/arger/algo/webapp/frontend"
echo "   npm run dev"
echo ""
echo "4. Load market data (in another terminal):"
echo "   cd /home/arger/algo"
echo "   source venv/bin/activate"
echo "   python3 loadstocksymbols.py"
echo ""
echo "================================"
echo -e "${GREEN}Your system is ready!${NC}"
echo "================================"

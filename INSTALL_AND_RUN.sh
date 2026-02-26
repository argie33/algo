#!/bin/bash

# ============================================
# INSTALL_AND_RUN.sh
# Run this in WSL bash - requires password input
# ============================================

set -e

echo "=================================================="
echo "ALGO STOCK PLATFORM - INSTALL & RUN"
echo "=================================================="
echo ""
echo "This script will:"
echo "1. Install PostgreSQL (requires your WSL password)"
echo "2. Create and initialize the database"
echo "3. Install all dependencies"
echo "4. Start all services"
echo "5. Load initial data"
echo ""
echo "Press Ctrl+C now if you don't want to proceed"
sleep 3

cd /home/arger/algo

# ============================================
# Step 1: Update system and install PostgreSQL
# ============================================
echo ""
echo "Step 1: Installing PostgreSQL..."
echo "You will be prompted for your WSL password"
echo ""

sudo apt-get update
sudo apt-get install -y postgresql postgresql-contrib postgresql-client

echo "PostgreSQL installation complete"
echo ""

# ============================================
# Step 2: Start PostgreSQL
# ============================================
echo "Step 2: Starting PostgreSQL service..."
sudo systemctl start postgresql
sudo systemctl enable postgresql
sleep 2

# Verify PostgreSQL is running
if pgrep postgres > /dev/null; then
    echo "✓ PostgreSQL is running"
else
    echo "✗ PostgreSQL failed to start"
    exit 1
fi

# ============================================
# Step 3: Initialize Database
# ============================================
echo ""
echo "Step 3: Initializing database..."

# Create database
sudo -u postgres psql -c "CREATE DATABASE stocks;" 2>/dev/null || echo "Database may already exist"

# Create user
sudo -u postgres psql -c "CREATE USER stocks WITH ENCRYPTED PASSWORD 'bed0elAn';" 2>/dev/null || echo "User may already exist"

# Grant privileges
sudo -u postgres psql -d stocks -c "GRANT ALL PRIVILEGES ON DATABASE stocks TO stocks;"

# Load schema
echo "Loading database schema..."
PGPASSWORD=bed0elAn psql -h localhost -U stocks -d stocks -f init-db.sql

# Verify
TABLE_COUNT=$(PGPASSWORD=bed0elAn psql -h localhost -U stocks -d stocks -tc "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';")
echo "✓ Database initialized with $TABLE_COUNT tables"

# ============================================
# Step 4: Install Node Dependencies
# ============================================
echo ""
echo "Step 4: Installing Node.js dependencies..."
cd /home/arger/algo/webapp

echo "  Backend..."
cd lambda
npm install
cd ..

echo "  Frontend..."
cd frontend
npm install
cd ..

echo "  Admin..."
cd frontend-admin
npm install
cd ..

echo "✓ Dependencies installed"

# ============================================
# Step 5: Install Python Dependencies
# ============================================
echo ""
echo "Step 5: Setting up Python environment..."
cd /home/arger/algo

if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

source venv/bin/activate
pip install -q -r requirements.txt

echo "✓ Python environment ready"

# ============================================
# Step 6: Summary
# ============================================
echo ""
echo "=================================================="
echo "✓ INSTALLATION COMPLETE!"
echo "=================================================="
echo ""
echo "To start everything, you need 3 separate terminals:"
echo ""
echo "TERMINAL 1 - Backend Server:"
echo "  cd /home/arger/algo/webapp/lambda"
echo "  node index.js"
echo ""
echo "TERMINAL 2 - Frontend (open new WSL terminal):"
echo "  cd /home/arger/algo/webapp/frontend"
echo "  npm run dev"
echo ""
echo "TERMINAL 3 - Data Loader (after backend ready):"
echo "  cd /home/arger/algo"
echo "  source venv/bin/activate"
echo "  python3 loadstocksymbols.py"
echo ""
echo "Then open: http://localhost:5173 in your browser"
echo "=================================================="

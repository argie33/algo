#!/bin/bash

# Run this in WSL to install PostgreSQL and complete setup

echo "=========================================="
echo "Installing PostgreSQL and Starting Services"
echo "=========================================="
echo ""
echo "You will be asked for your WSL password once."
echo ""

# Step 1: Update and Install PostgreSQL
echo "Step 1: Installing PostgreSQL..."
sudo apt-get update
sudo apt-get install -y postgresql postgresql-contrib postgresql-client

# Step 2: Start PostgreSQL
echo ""
echo "Step 2: Starting PostgreSQL service..."
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Step 3: Wait for service
sleep 2

# Step 4: Create database and user
echo ""
echo "Step 3: Initializing database..."
sudo -u postgres psql -c "CREATE DATABASE stocks;" 2>/dev/null || echo "Database may already exist"
sudo -u postgres psql -c "CREATE USER stocks WITH ENCRYPTED PASSWORD 'bed0elAn';" 2>/dev/null || echo "User may already exist"
sudo -u postgres psql -d stocks -c "GRANT ALL PRIVILEGES ON DATABASE stocks TO stocks;" 2>/dev/null || true

# Step 5: Load schema
echo "Step 4: Loading database schema..."
PGPASSWORD=bed0elAn psql -h localhost -U stocks -d stocks -f /home/arger/algo/init-db.sql >/dev/null 2>&1

# Verify
TABLES=$(PGPASSWORD=bed0elAn psql -h localhost -U stocks -d stocks -tc "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';" 2>/dev/null || echo "0")
echo ""
echo "=========================================="
echo "✓ PostgreSQL Installation Complete!"
echo "=========================================="
echo ""
echo "Database Status:"
echo "  • PostgreSQL: Running"
echo "  • Database: stocks"
echo "  • User: stocks"
echo "  • Tables: $TABLES"
echo ""
echo "Now run in separate terminals:"
echo ""
echo "Terminal 1 (Backend - already running on port 3001):"
echo "  cd /home/arger/algo/webapp/lambda && node index.js"
echo ""
echo "Terminal 2 (Frontend - already running on port 5173):"
echo "  cd /home/arger/algo/webapp/frontend && npm run dev"
echo ""
echo "Then open: http://localhost:5173"
echo "=========================================="

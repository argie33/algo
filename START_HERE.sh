#!/bin/bash

# ============================================
# START HERE - Complete Startup Guide
# ============================================
# This script guides you through starting everything

echo "=================================================="
echo "ALGO STOCK PLATFORM - STARTUP GUIDE"
echo "=================================================="
echo ""
echo "This script will help you:"
echo "1. Install PostgreSQL (requires your password)"
echo "2. Initialize the database"
echo "3. Start the backend server"
echo "4. Start the frontend"
echo "5. Load market data"
echo ""

# Check if PostgreSQL is installed
if ! command -v psql &> /dev/null; then
    echo "⚠️  PostgreSQL not found. Installing..."
    echo ""
    echo "You will be prompted for your WSL password."
    echo "Enter your password when prompted:"
    echo ""

    # Try to install PostgreSQL
    if sudo apt-get update && sudo apt-get install -y postgresql postgresql-contrib postgresql-client; then
        echo "✅ PostgreSQL installed successfully"
    else
        echo "❌ Failed to install PostgreSQL"
        echo ""
        echo "Manual fix: Run this in WSL terminal:"
        echo "  sudo apt-get update"
        echo "  sudo apt-get install -y postgresql postgresql-contrib postgresql-client"
        exit 1
    fi
else
    echo "✅ PostgreSQL is installed"
fi

# Start PostgreSQL
echo ""
echo "Starting PostgreSQL..."
if sudo systemctl start postgresql && sudo systemctl enable postgresql; then
    echo "✅ PostgreSQL started"
    sleep 2
else
    echo "⚠️  Could not start PostgreSQL with systemctl, trying service..."
    if sudo service postgresql start; then
        echo "✅ PostgreSQL started via service"
        sleep 2
    else
        echo "❌ Could not start PostgreSQL"
        exit 1
    fi
fi

# Initialize database
echo ""
echo "Initializing database..."
cd /home/arger/algo

if PGPASSWORD=bed0elAn psql -h localhost -U stocks -d stocks -c "SELECT 1;" >/dev/null 2>&1; then
    echo "✅ Database already initialized"
else
    echo "Creating database and schema..."

    # Create database if it doesn't exist
    sudo -u postgres psql -c "CREATE DATABASE stocks;" 2>/dev/null || true

    # Create user
    sudo -u postgres psql -c "CREATE USER stocks WITH ENCRYPTED PASSWORD 'bed0elAn';" 2>/dev/null || true

    # Grant privileges
    sudo -u postgres psql -d stocks -c "GRANT ALL PRIVILEGES ON DATABASE stocks TO stocks;" 2>/dev/null || true

    # Initialize schema
    if PGPASSWORD=bed0elAn psql -h localhost -U stocks -d stocks -f init-db.sql >/dev/null 2>&1; then
        echo "✅ Database schema initialized"
    else
        echo "❌ Failed to initialize schema"
        exit 1
    fi
fi

# Verify database
TABLE_COUNT=$(PGPASSWORD=bed0elAn psql -h localhost -U stocks -d stocks -tc "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';" 2>/dev/null || echo "0")
TABLE_COUNT=$(echo $TABLE_COUNT | xargs)
echo "✅ Database ready - $TABLE_COUNT tables"

echo ""
echo "=================================================="
echo "SERVICES STATUS:"
echo "=================================================="
echo ""
echo "✅ PostgreSQL: Ready on localhost:5432"
echo "⏸️  Backend:   Not started (will start next)"
echo "⏸️  Frontend:  Not started (will start after)"
echo ""

echo "=================================================="
echo "NEXT STEPS - Start in 3 Separate Terminals:"
echo "=================================================="
echo ""
echo "TERMINAL 1 - Backend Server:"
echo "  cd /home/arger/algo/webapp/lambda"
echo "  node index.js"
echo ""
echo "TERMINAL 2 - Frontend (open new WSL):"
echo "  cd /home/arger/algo/webapp/frontend"
echo "  npm run dev"
echo ""
echo "TERMINAL 3 - Admin Site (open another new WSL, optional):"
echo "  cd /home/arger/algo/webapp/frontend-admin"
echo "  npm run dev"
echo ""
echo "TERMINAL 4 - Load Data (after backend + DB are ready):"
echo "  cd /home/arger/algo"
echo "  source venv/bin/activate"
echo "  python3 loadstocksymbols.py"
echo ""
echo "=================================================="
echo "✅ Setup complete! Follow the Next Steps above."
echo "=================================================="

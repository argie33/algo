#!/bin/bash

# ============================================
# RUN_EVERYTHING.sh
# Complete automated startup for the platform
# ============================================

set -e

cd /home/arger/algo

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}ALGO STOCK PLATFORM - COMPLETE STARTUP${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════${NC}"
echo ""

# ============================================
# Step 1: PostgreSQL Setup
# ============================================
echo -e "${YELLOW}Step 1: Setting up PostgreSQL...${NC}"

# Try to start PostgreSQL (requires sudo but may not ask if passwordless)
sudo systemctl restart postgresql 2>/dev/null || sudo service postgresql restart 2>/dev/null || true
sleep 2

# Check connection
if PGPASSWORD=bed0elAn psql -h localhost -U stocks -d stocks -c "SELECT 1;" >/dev/null 2>&1; then
    echo -e "${GREEN}✓ PostgreSQL is running and accessible${NC}"
else
    echo -e "${YELLOW}⚠ PostgreSQL connection failed, attempting database setup...${NC}"

    # Try to initialize database
    sudo -u postgres psql -c "CREATE DATABASE stocks;" 2>/dev/null || true
    sudo -u postgres psql -c "CREATE USER stocks WITH ENCRYPTED PASSWORD 'bed0elAn';" 2>/dev/null || true
    sudo -u postgres psql -d stocks -c "GRANT ALL PRIVILEGES ON DATABASE stocks TO stocks;" 2>/dev/null || true

    # Initialize schema
    echo "  Initializing database schema..."
    PGPASSWORD=bed0elAn psql -h localhost -U stocks -d stocks -f init-db.sql >/dev/null 2>&1

    if PGPASSWORD=bed0elAn psql -h localhost -U stocks -d stocks -c "SELECT 1;" >/dev/null 2>&1; then
        echo -e "${GREEN}✓ Database initialized${NC}"
    else
        echo -e "${RED}✗ Database setup failed${NC}"
        echo ""
        echo "Manual fix needed. Run in WSL as root:"
        echo "  sudo systemctl start postgresql"
        echo "  sudo -u postgres psql -f /home/arger/algo/init-db.sql"
        exit 1
    fi
fi

TABLE_COUNT=$(PGPASSWORD=bed0elAn psql -h localhost -U stocks -d stocks -tc "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';" 2>/dev/null || echo "0")
TABLE_COUNT=$(echo $TABLE_COUNT | xargs)
echo -e "${GREEN}✓ Database ready - $TABLE_COUNT tables${NC}"

# ============================================
# Step 2: Install Dependencies
# ============================================
echo ""
echo -e "${YELLOW}Step 2: Installing Node.js dependencies...${NC}"

cd /home/arger/algo/webapp

if [ ! -d "lambda/node_modules" ]; then
    echo "  Installing backend dependencies..."
    cd lambda
    npm install >/dev/null 2>&1 &
    PID_BACKEND=$!
    cd ..
else
    PID_BACKEND=0
fi

if [ ! -d "frontend/node_modules" ]; then
    echo "  Installing frontend dependencies..."
    cd frontend
    npm install >/dev/null 2>&1 &
    PID_FRONTEND=$!
    cd ..
else
    PID_FRONTEND=0
fi

if [ ! -d "frontend-admin/node_modules" ]; then
    echo "  Installing admin dependencies..."
    cd frontend-admin
    npm install >/dev/null 2>&1 &
    PID_ADMIN=$!
    cd ..
else
    PID_ADMIN=0
fi

# Wait for installs
[ $PID_BACKEND -ne 0 ] && wait $PID_BACKEND
[ $PID_FRONTEND -ne 0 ] && wait $PID_FRONTEND
[ $PID_ADMIN -ne 0 ] && wait $PID_ADMIN

echo -e "${GREEN}✓ Dependencies installed${NC}"

# ============================================
# Step 3: Python Setup
# ============================================
echo ""
echo -e "${YELLOW}Step 3: Setting up Python environment...${NC}"

cd /home/arger/algo

if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo -e "${GREEN}✓ Virtual environment created${NC}"
fi

source venv/bin/activate

# Install requirements
if [ -f "requirements.txt" ]; then
    pip install -q -r requirements.txt 2>/dev/null || echo -e "${YELLOW}⚠ Some packages may not have installed${NC}"
fi

echo -e "${GREEN}✓ Python environment ready${NC}"

# ============================================
# Step 4: Start Services
# ============================================
echo ""
echo -e "${BLUE}════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}STARTING SERVICES${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════${NC}"
echo ""

# Start backend
echo -e "${YELLOW}Starting Backend Server (port 3001)...${NC}"
cd /home/arger/algo/webapp/lambda
timeout 10 node index.js > /tmp/backend.log 2>&1 &
PID_NODE=$!
sleep 3

if lsof -i :3001 >/dev/null 2>&1; then
    echo -e "${GREEN}✓ Backend running on http://localhost:3001${NC}"
else
    echo -e "${RED}✗ Backend failed to start${NC}"
    echo "Logs:"
    cat /tmp/backend.log
    exit 1
fi

# Start frontend
echo -e "${YELLOW}Starting Frontend (port 5173)...${NC}"
cd /home/arger/algo/webapp/frontend
timeout 10 npm run dev > /tmp/frontend.log 2>&1 &
PID_VITE=$!
sleep 4

if lsof -i :5173 >/dev/null 2>&1; then
    echo -e "${GREEN}✓ Frontend running on http://localhost:5173${NC}"
else
    echo -e "${RED}⚠ Frontend may not be ready yet${NC}"
fi

# Start admin frontend (background)
echo -e "${YELLOW}Starting Admin Frontend (port 5174)...${NC}"
cd /home/arger/algo/webapp/frontend-admin
timeout 10 npm run dev > /tmp/admin.log 2>&1 &
PID_ADMIN=$!
sleep 3

if lsof -i :5174 >/dev/null 2>&1; then
    echo -e "${GREEN}✓ Admin running on http://localhost:5174${NC}"
fi

# ============================================
# Step 5: Data Loading
# ============================================
echo ""
echo -e "${BLUE}════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}LOADING MARKET DATA${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════${NC}"
echo ""

cd /home/arger/algo
source venv/bin/activate

echo -e "${YELLOW}Loading stock symbols (Phase 1)...${NC}"
if timeout 300 python3 loadstocksymbols.py > /tmp/load_symbols.log 2>&1; then
    SYMBOL_COUNT=$(PGPASSWORD=bed0elAn psql -h localhost -U stocks -d stocks -tc "SELECT COUNT(*) FROM stock_symbols;" 2>/dev/null || echo "0")
    echo -e "${GREEN}✓ Loaded $SYMBOL_COUNT stock symbols${NC}"
else
    echo -e "${YELLOW}⚠ Symbol loading may have had issues${NC}"
    tail -20 /tmp/load_symbols.log
fi

echo ""
echo -e "${YELLOW}Loading daily prices (Phase 2a)...${NC}"
if timeout 600 python3 loadpricedaily.py > /tmp/load_prices.log 2>&1; then
    PRICE_COUNT=$(PGPASSWORD=bed0elAn psql -h localhost -U stocks -d stocks -tc "SELECT COUNT(*) FROM price_daily;" 2>/dev/null || echo "0")
    echo -e "${GREEN}✓ Loaded $PRICE_COUNT price records${NC}"
else
    echo -e "${YELLOW}⚠ Price loading may have had issues${NC}"
fi

echo ""
echo -e "${YELLOW}Loading fundamental metrics (Phase 2b)...${NC}"
if timeout 300 python3 loadfundamentalmetrics.py > /tmp/load_fundamentals.log 2>&1; then
    FUND_COUNT=$(PGPASSWORD=bed0elAn psql -h localhost -U stocks -d stocks -tc "SELECT COUNT(*) FROM fundamental_metrics;" 2>/dev/null || echo "0")
    echo -e "${GREEN}✓ Loaded $FUND_COUNT fundamental records${NC}"
else
    echo -e "${YELLOW}⚠ Fundamental loading may have had issues${NC}"
fi

echo ""
echo -e "${YELLOW}Loading technical indicators (Phase 2c)...${NC}"
if timeout 300 python3 loadtechnicalindicators.py > /tmp/load_technical.log 2>&1; then
    echo -e "${GREEN}✓ Technical indicators loaded${NC}"
else
    echo -e "${YELLOW}⚠ Technical loading may have had issues${NC}"
fi

echo ""
echo -e "${YELLOW}Loading buy/sell signals (Phase 2d)...${NC}"
if timeout 300 python3 loadbuysellDaily.py > /tmp/load_signals.log 2>&1; then
    SIGNAL_COUNT=$(PGPASSWORD=bed0elAn psql -h localhost -U stocks -d stocks -tc "SELECT COUNT(*) FROM buy_sell_daily;" 2>/dev/null || echo "0")
    echo -e "${GREEN}✓ Loaded $SIGNAL_COUNT buy/sell signals${NC}"
else
    echo -e "${YELLOW}⚠ Signal loading may have had issues${NC}"
fi

echo ""
echo -e "${YELLOW}Loading stock scores (Phase 2e)...${NC}"
if timeout 300 python3 loadstockscores.py > /tmp/load_scores.log 2>&1; then
    SCORE_COUNT=$(PGPASSWORD=bed0elAn psql -h localhost -U stocks -d stocks -tc "SELECT COUNT(*) FROM stock_scores;" 2>/dev/null || echo "0")
    echo -e "${GREEN}✓ Loaded $SCORE_COUNT stock scores${NC}"
else
    echo -e "${YELLOW}⚠ Score loading may have had issues${NC}"
fi

# ============================================
# Final Summary
# ============================================
echo ""
echo -e "${BLUE}════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✓ STARTUP COMPLETE!${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${GREEN}Services Running:${NC}"
echo "  • PostgreSQL (localhost:5432) - ✓"
echo "  • Backend API (localhost:3001) - $(lsof -i :3001 >/dev/null 2>&1 && echo "✓" || echo "✗")"
echo "  • Frontend (localhost:5173) - $(lsof -i :5173 >/dev/null 2>&1 && echo "✓" || echo "✗")"
echo "  • Admin (localhost:5174) - $(lsof -i :5174 >/dev/null 2>&1 && echo "✓" || echo "✗")"
echo ""
echo -e "${GREEN}Database Status:${NC}"
echo "  • Tables: $TABLE_COUNT"
echo "  • Stocks: $SYMBOL_COUNT"
echo "  • Prices: $PRICE_COUNT"
echo "  • Scores: $SCORE_COUNT"
echo ""
echo -e "${BLUE}Access Your Application:${NC}"
echo "  🌐 Main Site:   http://localhost:5173"
echo "  🔧 Admin Panel: http://localhost:5174"
echo "  📡 API:         http://localhost:3001"
echo ""
echo -e "${YELLOW}View Logs:${NC}"
echo "  • Backend:  tail -f /tmp/backend.log"
echo "  • Frontend: tail -f /tmp/frontend.log"
echo "  • Admin:    tail -f /tmp/admin.log"
echo ""
echo -e "${BLUE}════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}Ready to use! Open http://localhost:5173 in your browser${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════${NC}"

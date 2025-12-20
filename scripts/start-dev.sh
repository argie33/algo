#!/bin/bash

#######################################
# Development Environment Startup Script
# Starts both frontend (Vite) and backend (Express) servers
#######################################

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
BACKEND_PORT=3001
FRONTEND_PORT=5173
ADMIN_PORT=5174
BACKEND_DIR="webapp/lambda"
FRONTEND_DIR="webapp/frontend"
ADMIN_DIR="webapp/frontend-admin"
BACKEND_URL="http://localhost:$BACKEND_PORT"
FRONTEND_URL="http://localhost:$FRONTEND_PORT"
ADMIN_URL="http://localhost:$ADMIN_PORT"

# Cleanup on exit
cleanup() {
    echo -e "\n${YELLOW}Cleaning up...${NC}"
    if [ ! -z "$BACKEND_PID" ]; then
        kill $BACKEND_PID 2>/dev/null || true
    fi
    if [ ! -z "$FRONTEND_PID" ]; then
        kill $FRONTEND_PID 2>/dev/null || true
    fi
    if [ ! -z "$ADMIN_PID" ]; then
        kill $ADMIN_PID 2>/dev/null || true
    fi
    exit 0
}

trap cleanup EXIT INT TERM

#######################################
# Validation Functions
#######################################

check_node_version() {
    local min_version=$1
    local app_name=$2

    if ! command -v node &> /dev/null; then
        echo -e "${RED}✗ Node.js not found${NC}"
        return 1
    fi

    local node_version=$(node -v | cut -d'v' -f2 | cut -d'.' -f1)

    if [ "$node_version" -lt "$min_version" ]; then
        echo -e "${RED}✗ $app_name requires Node.js $min_version+, you have $(node -v)${NC}"
        return 1
    fi

    echo -e "${GREEN}✓ Node.js $(node -v)${NC}"
    return 0
}

check_port_available() {
    local port=$1
    local app_name=$2

    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo -e "${RED}✗ Port $port is already in use (required for $app_name)${NC}"
        echo -e "${YELLOW}  Try: lsof -ti:$port | xargs kill -9${NC}"
        return 1
    fi

    echo -e "${GREEN}✓ Port $port available${NC}"
    return 0
}

check_database() {
    # Read DB config from lambda/.env
    if [ ! -f "$BACKEND_DIR/.env" ]; then
        echo -e "${YELLOW}⚠ Backend .env not found${NC}"
        return 1
    fi

    # Extract DB credentials
    DB_HOST=$(grep "^DB_HOST=" "$BACKEND_DIR/.env" | cut -d'=' -f2)
    DB_USER=$(grep "^DB_USER=" "$BACKEND_DIR/.env" | cut -d'=' -f2)
    DB_NAME=$(grep "^DB_NAME=" "$BACKEND_DIR/.env" | cut -d'=' -f2)

    if ! command -v psql &> /dev/null; then
        echo -e "${YELLOW}⚠ PostgreSQL client not found (psql) - skipping DB check${NC}"
        return 0
    fi

    if psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -c "SELECT 1" >/dev/null 2>&1; then
        echo -e "${GREEN}✓ Database connection OK${NC}"
        return 0
    else
        echo -e "${YELLOW}⚠ Cannot connect to PostgreSQL at $DB_HOST${NC}"
        echo -e "${YELLOW}  Make sure PostgreSQL is running${NC}"
        return 1
    fi
}

wait_for_server() {
    local url=$1
    local max_attempts=30
    local attempt=0

    while [ $attempt -lt $max_attempts ]; do
        if curl -s "$url/health" >/dev/null 2>&1 || curl -s "$url" >/dev/null 2>&1; then
            return 0
        fi
        sleep 1
        attempt=$((attempt + 1))
    done

    return 1
}

#######################################
# Main Script
#######################################

echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Financial Dashboard - Development Startup Script${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}\n"

# Change to project root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"
cd "$PROJECT_ROOT"

echo -e "${BLUE}Checking prerequisites...${NC}\n"

# Check Node versions
echo "Node.js versions:"
check_node_version 18 "Backend" || exit 1
check_node_version 20 "Frontend" || exit 1

# Check ports
echo -e "\nPort availability:"
check_port_available $BACKEND_PORT "Backend" || exit 1
check_port_available $FRONTEND_PORT "Frontend" || exit 1
check_port_available $ADMIN_PORT "Admin Site" || exit 1

# Check database
echo -e "\nDatabase:"
check_database || true  # Non-fatal

echo -e "\n${BLUE}Starting services...${NC}\n"

# Start Backend
echo -e "${BLUE}→ Starting Backend (Express on port $BACKEND_PORT)${NC}"
cd "$PROJECT_ROOT/$BACKEND_DIR"

if [ ! -d "node_modules" ]; then
    echo "  Installing dependencies..."
    npm install >/dev/null 2>&1
fi

npm start > "$PROJECT_ROOT/logs/backend.log" 2>&1 &
BACKEND_PID=$!
echo -e "  PID: ${GREEN}$BACKEND_PID${NC}"

# Wait for backend to be ready
echo "  Waiting for backend to start..."
if wait_for_server "$BACKEND_URL"; then
    echo -e "  ${GREEN}✓ Backend ready${NC}"
else
    echo -e "  ${RED}✗ Backend failed to start${NC}"
    echo -e "  Check logs: ${YELLOW}cat logs/backend.log${NC}"
    exit 1
fi

sleep 1

# Start Frontend
echo -e "\n${BLUE}→ Starting Frontend (Vite on port $FRONTEND_PORT)${NC}"
cd "$PROJECT_ROOT/$FRONTEND_DIR"

if [ ! -d "node_modules" ]; then
    echo "  Installing dependencies..."
    npm install >/dev/null 2>&1
fi

npm run dev > "$PROJECT_ROOT/logs/frontend.log" 2>&1 &
FRONTEND_PID=$!
echo -e "  PID: ${GREEN}$FRONTEND_PID${NC}"
echo -e "  ${GREEN}✓ Frontend started${NC}"

sleep 1

# Start Admin Site
echo -e "\n${BLUE}→ Starting Admin Site (Vite on port $ADMIN_PORT)${NC}"
cd "$PROJECT_ROOT/$ADMIN_DIR"

if [ ! -d "node_modules" ]; then
    echo "  Installing dependencies..."
    npm install >/dev/null 2>&1
fi

npm run dev > "$PROJECT_ROOT/logs/admin.log" 2>&1 &
ADMIN_PID=$!
echo -e "  PID: ${GREEN}$ADMIN_PID${NC}"
echo -e "  ${GREEN}✓ Admin site started${NC}"

# Summary
echo -e "\n${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Development environment is running!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}\n"

echo -e "Frontend:  ${BLUE}$FRONTEND_URL${NC}"
echo -e "Admin:     ${BLUE}$ADMIN_URL${NC}"
echo -e "Backend:   ${BLUE}$BACKEND_URL${NC}\n"

echo -e "Logs:"
echo -e "  Backend:  ${YELLOW}logs/backend.log${NC}"
echo -e "  Frontend: ${YELLOW}logs/frontend.log${NC}"
echo -e "  Admin:    ${YELLOW}logs/admin.log${NC}\n"

echo -e "To stop: Press ${YELLOW}Ctrl+C${NC}\n"

# Keep script running
wait

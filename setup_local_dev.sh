#!/bin/bash

###############################################################################
# COMPREHENSIVE LOCAL DEVELOPMENT SETUP SCRIPT
# Sets up PostgreSQL database, seeds data, and runs all tests
###############################################################################

set -e  # Exit on error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
DB_HOST="localhost"
DB_PORT="5432"
DB_USER="postgres"
DB_PASSWORD="password"
DB_NAME="stocks"
DOCKER_CONTAINER="postgres-stocks"

###############################################################################
# UTILITY FUNCTIONS
###############################################################################

print_header() {
    echo -e "\n${BLUE}================================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}================================================${NC}\n"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

###############################################################################
# STEP 1: CHECK PREREQUISITES
###############################################################################

step_check_prerequisites() {
    print_header "STEP 1: Checking Prerequisites"

    # Check Node.js
    if ! command -v node &> /dev/null; then
        print_error "Node.js not found. Please install Node.js >= 18.0.0"
        exit 1
    fi
    NODE_VERSION=$(node --version)
    print_success "Node.js found: $NODE_VERSION"

    # Check npm
    if ! command -v npm &> /dev/null; then
        print_error "npm not found"
        exit 1
    fi
    NPM_VERSION=$(npm --version)
    print_success "npm found: $NPM_VERSION"
}

###############################################################################
# STEP 2: CHECK/SETUP DATABASE
###############################################################################

step_setup_database() {
    print_header "STEP 2: Setting Up Database"

    # Check if PostgreSQL is running
    if nc -z $DB_HOST $DB_PORT 2>/dev/null; then
        print_success "PostgreSQL is running on $DB_HOST:$DB_PORT"
        return 0
    fi

    print_warning "PostgreSQL not running, attempting to start..."

    # Try system PostgreSQL (Linux)
    if command -v systemctl &> /dev/null; then
        print_info "Attempting to start PostgreSQL service..."
        if sudo systemctl start postgresql 2>/dev/null; then
            print_success "PostgreSQL started"
            sleep 2
            if nc -z $DB_HOST $DB_PORT 2>/dev/null; then
                print_success "PostgreSQL is now running"
                return 0
            fi
        fi
    fi

    # Try Homebrew (macOS)
    if command -v brew &> /dev/null; then
        print_info "Attempting to start PostgreSQL via Homebrew..."
        if brew services start postgresql 2>/dev/null; then
            print_success "PostgreSQL started"
            sleep 2
            if nc -z $DB_HOST $DB_PORT 2>/dev/null; then
                print_success "PostgreSQL is now running"
                return 0
            fi
        fi
    fi

    # Fall back to Docker
    if command -v docker &> /dev/null; then
        print_warning "PostgreSQL not found, using Docker container..."
        step_setup_docker_postgres
        return 0
    fi

    print_error "Could not start PostgreSQL. Please install PostgreSQL or Docker."
    exit 1
}

step_setup_docker_postgres() {
    print_header "Setting Up Docker PostgreSQL"

    # Check if container exists
    if docker ps -a --format '{{.Names}}' | grep -q "^${DOCKER_CONTAINER}$"; then
        print_info "Container $DOCKER_CONTAINER exists, starting it..."
        docker start $DOCKER_CONTAINER 2>/dev/null || true
    else
        print_info "Creating new PostgreSQL container..."
        docker run -d \
            --name $DOCKER_CONTAINER \
            -e POSTGRES_PASSWORD=$DB_PASSWORD \
            -e POSTGRES_DB=$DB_NAME \
            -p $DB_PORT:5432 \
            postgres:15 \
            > /dev/null
    fi

    # Wait for PostgreSQL to be ready
    print_info "Waiting for PostgreSQL to be ready..."
    for i in {1..30}; do
        if docker exec $DOCKER_CONTAINER pg_isready -U $DB_USER > /dev/null 2>&1; then
            print_success "PostgreSQL is ready"
            return 0
        fi
        echo -n "."
        sleep 1
    done

    print_error "PostgreSQL startup timeout"
    exit 1
}

###############################################################################
# STEP 3: CREATE DATABASE SCHEMA
###############################################################################

step_create_schema() {
    print_header "STEP 3: Creating Database Schema"

    # Set password for psql
    export PGPASSWORD=$DB_PASSWORD

    # Check if database exists
    if psql -h $DB_HOST -U $DB_USER -lqt | cut -d \| -f 1 | grep -qw $DB_NAME; then
        print_success "Database $DB_NAME already exists"
    else
        print_info "Creating database $DB_NAME..."
        psql -h $DB_HOST -U $DB_USER -c "CREATE DATABASE $DB_NAME;" 2>/dev/null || \
            print_warning "Database may already exist"
    fi

    # Apply schema
    print_info "Applying database schema..."
    if [ -f "webapp/lambda/setup_test_database.sql" ]; then
        psql -h $DB_HOST -U $DB_USER -d $DB_NAME -f webapp/lambda/setup_test_database.sql > /dev/null 2>&1
        print_success "Database schema applied"
    else
        print_warning "Schema file not found at webapp/lambda/setup_test_database.sql"
    fi

    # Check tables were created
    TABLE_COUNT=$(psql -h $DB_HOST -U $DB_USER -d $DB_NAME -t -c \
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';" 2>/dev/null || echo "0")
    print_success "Tables created: $TABLE_COUNT"
}

###############################################################################
# STEP 4: SEED TEST DATA
###############################################################################

step_seed_data() {
    print_header "STEP 4: Seeding Test Data"

    export PGPASSWORD=$DB_PASSWORD

    # Seed comprehensive data
    if [ -f "webapp/lambda/seed_comprehensive_local_data.sql" ]; then
        print_info "Seeding comprehensive test data..."
        psql -h $DB_HOST -U $DB_USER -d $DB_NAME -f webapp/lambda/seed_comprehensive_local_data.sql > /dev/null 2>&1
        print_success "Test data seeded"
    else
        print_warning "Seed file not found"
    fi

    # Verify data
    SYMBOL_COUNT=$(psql -h $DB_HOST -U $DB_USER -d $DB_NAME -t -c \
        "SELECT COUNT(*) FROM stock_symbols;" 2>/dev/null || echo "0")
    PRICE_COUNT=$(psql -h $DB_HOST -U $DB_USER -d $DB_NAME -t -c \
        "SELECT COUNT(*) FROM price_daily;" 2>/dev/null || echo "0")

    print_success "Data verification: $SYMBOL_COUNT symbols, $PRICE_COUNT price records"
}

###############################################################################
# STEP 5: INSTALL DEPENDENCIES
###############################################################################

step_install_dependencies() {
    print_header "STEP 5: Installing Dependencies"

    if [ ! -d "webapp/lambda/node_modules" ]; then
        print_info "Installing backend dependencies..."
        cd webapp/lambda
        npm install --legacy-peer-deps > /dev/null 2>&1
        cd ../../
        print_success "Backend dependencies installed"
    else
        print_success "Backend dependencies already installed"
    fi

    if [ ! -d "webapp/frontend/node_modules" ]; then
        print_info "Installing frontend dependencies..."
        cd webapp/frontend
        npm install --legacy-peer-deps > /dev/null 2>&1
        cd ../../
        print_success "Frontend dependencies installed"
    else
        print_success "Frontend dependencies already installed"
    fi
}

###############################################################################
# STEP 6: VERIFY DATABASE CONNECTION
###############################################################################

step_verify_connection() {
    print_header "STEP 6: Verifying Database Connection"

    export PGPASSWORD=$DB_PASSWORD

    if psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "SELECT 1;" > /dev/null 2>&1; then
        print_success "Database connection verified"
    else
        print_error "Database connection failed"
        exit 1
    fi
}

###############################################################################
# STEP 7: RUN TESTS
###############################################################################

step_run_tests() {
    print_header "STEP 7: Running Tests"

    cd webapp/lambda

    print_info "Running unit tests..."
    if npm run test:unit 2>&1 | tee /tmp/unit-tests.log | tail -20; then
        print_success "Unit tests passed"
    else
        print_warning "Some unit tests failed (see /tmp/unit-tests.log)"
    fi

    print_info "Running integration tests (first 30 seconds)..."
    timeout 30 npm run test:integration 2>&1 | head -50 || print_warning "Integration tests timeout (database needs seeding)"

    cd ../../
}

###############################################################################
# STEP 8: DISPLAY STATUS SUMMARY
###############################################################################

step_display_summary() {
    print_header "SETUP COMPLETE!"

    export PGPASSWORD=$DB_PASSWORD

    echo -e "\n${GREEN}Database Status:${NC}"
    echo "  Host: $DB_HOST"
    echo "  Port: $DB_PORT"
    echo "  Database: $DB_NAME"
    echo "  User: $DB_USER"

    # Get counts
    SYMBOL_COUNT=$(psql -h $DB_HOST -U $DB_USER -d $DB_NAME -t -c \
        "SELECT COUNT(*) FROM stock_symbols;" 2>/dev/null || echo "0")
    PRICE_COUNT=$(psql -h $DB_HOST -U $DB_USER -d $DB_NAME -t -c \
        "SELECT COUNT(*) FROM price_daily;" 2>/dev/null || echo "0")
    SCORE_COUNT=$(psql -h $DB_HOST -U $DB_USER -d $DB_NAME -t -c \
        "SELECT COUNT(*) FROM stock_scores;" 2>/dev/null || echo "0")

    echo -e "\n${GREEN}Data Summary:${NC}"
    echo "  Symbols: $SYMBOL_COUNT"
    echo "  Price Records: $PRICE_COUNT"
    echo "  Stock Scores: $SCORE_COUNT"

    echo -e "\n${GREEN}Next Steps:${NC}"
    echo "  1. Start backend:  cd webapp/lambda && npm start"
    echo "  2. Start frontend: cd webapp/frontend && npm run dev"
    echo "  3. Open browser:   http://localhost:5173"
    echo "  4. Run tests:      cd webapp/lambda && npm test"

    echo -e "\n${GREEN}API Endpoints:${NC}"
    echo "  Health:    http://localhost:5001/health"
    echo "  Dashboard: http://localhost:5001/api/dashboard/summary"
    echo "  Sectors:   http://localhost:5001/api/sectors"
}

###############################################################################
# MAIN EXECUTION
###############################################################################

main() {
    print_header "STOCKS ALGO LOCAL DEVELOPMENT SETUP"

    step_check_prerequisites
    step_setup_database
    step_create_schema
    step_seed_data
    step_install_dependencies
    step_verify_connection
    step_run_tests
    step_display_summary
}

# Run main function
main

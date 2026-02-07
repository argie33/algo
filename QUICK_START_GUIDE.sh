#!/bin/bash
################################################################################
# QUICK START GUIDE: Financial Data Loading
# ============================================================================
# This script provides quick start commands for loading financial data locally
# Complete documentation: FINANCIAL_DATA_LOAD_PLAN.md
################################################################################

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
print_header() {
    echo -e "\n${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}\n"
}

print_step() {
    echo -e "${GREEN}[STEP]${NC} $1"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_info() {
    echo -e "${YELLOW}[INFO]${NC} $1"
}

# Main menu
show_menu() {
    print_header "FINANCIAL DATA LOADER - QUICK START"

    echo "1. Setup Database (Start PostgreSQL)"
    echo "2. Verify Database Connection"
    echo "3. Load CRITICAL Data (Foundation + Prices + Earnings)"
    echo "4. Load RECOMMENDED Data (+ Financial Statements)"
    echo "5. Load ALL Data (Full Comprehensive Load)"
    echo "6. Validate Database"
    echo "7. Show Database Statistics"
    echo "8. Clean Database (Reset)"
    echo "9. Run Daily Update"
    echo "0. Exit"
    echo ""
    read -p "Select option (0-9): " choice
}

# 1. Setup Database
setup_database() {
    print_header "STEP 1: STARTING POSTGRESQL"

    if ! command -v docker-compose &> /dev/null; then
        print_error "docker-compose not found. Please install Docker."
        return 1
    fi

    print_step "Starting PostgreSQL container..."
    cd /home/stocks/algo

    if docker-compose ps | grep -q "stocks_postgres"; then
        print_info "PostgreSQL container already running"
    else
        docker-compose up -d
        print_step "Waiting for PostgreSQL to be ready..."
        sleep 10
    fi

    if docker-compose ps | grep -q "healthy"; then
        print_success "PostgreSQL is healthy and ready"
    else
        print_error "PostgreSQL failed to start - check docker-compose logs"
        return 1
    fi
}

# 2. Verify Connection
verify_connection() {
    print_header "STEP 2: VERIFYING DATABASE CONNECTION"

    cd /home/stocks/algo

    print_step "Testing database connection..."

    if PGPASSWORD=stocks psql -h localhost -U stocks -d stocks -c "SELECT 1" > /dev/null 2>&1; then
        print_success "Successfully connected to database"

        # Show database info
        echo ""
        print_step "Database Information:"
        PGPASSWORD=stocks psql -h localhost -U stocks -d stocks << 'SQL'
\x off
\pset tuples_only on

SELECT 'Host: ' || 'localhost';
SELECT 'Port: ' || '5432';
SELECT 'User: ' || 'stocks';
SELECT 'Database: ' || 'stocks';
SELECT 'Tables: ' || COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';
\x on
SQL
    else
        print_error "Failed to connect to database"
        print_info "Try running: docker-compose up -d"
        return 1
    fi
}

# 3. Load Critical Data
load_critical() {
    print_header "STEP 3: LOADING CRITICAL DATA"
    print_info "This will load: Symbols, Sectors, Prices (5-60 min)"

    cd /home/stocks/algo

    print_step "Loading stock symbols..."
    python3 loadstocksymbols.py || { print_error "Failed to load symbols"; return 1; }
    print_success "Stock symbols loaded"

    print_step "Loading sectors..."
    python3 loadsectors.py || { print_error "Failed to load sectors"; return 1; }
    print_success "Sectors loaded"

    print_step "Loading daily prices (this may take 45+ minutes)..."
    python3 loadpricedaily.py || { print_error "Failed to load prices"; return 1; }
    print_success "Prices loaded"

    print_step "Loading earnings history..."
    python3 loadearningshistory.py || { print_error "Failed to load earnings"; return 1; }
    print_success "Earnings loaded"

    echo ""
    print_success "CRITICAL DATA LOAD COMPLETE!"
}

# 4. Load Recommended Data
load_recommended() {
    print_header "STEP 4: LOADING RECOMMENDED DATA"
    print_info "This will also load: Financial Statements, Analyst Data (60+ min)"

    cd /home/stocks/algo

    # First ensure critical is loaded
    if ! verify_connection; then
        return 1
    fi

    # Load additional price data
    print_step "Loading weekly prices..."
    python3 loadpriceweekly.py
    print_success "Weekly prices loaded"

    print_step "Loading monthly prices..."
    python3 loadpricemonthly.py
    print_success "Monthly prices loaded"

    # Load financial statements
    print_step "Loading annual income statements..."
    python3 loadannualincomestatement.py
    print_success "Annual income statements loaded"

    print_step "Loading quarterly balance sheets..."
    python3 loadquarterlybalancesheet.py
    print_success "Quarterly balance sheets loaded"

    # Load analyst data
    print_step "Loading analyst sentiment..."
    python3 loadanalystsentiment.py
    print_success "Analyst sentiment loaded"

    print_step "Loading news data..."
    python3 loadnews.py
    print_success "News loaded"

    echo ""
    print_success "RECOMMENDED DATA LOAD COMPLETE!"
}

# 5. Load All Data
load_all() {
    print_header "STEP 5: FULL COMPREHENSIVE DATA LOAD"
    print_info "This will load ALL 57 data loaders (3-4 hours)"

    read -p "Are you sure? This will take several hours. (y/N): " confirm
    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        print_info "Cancelled"
        return 0
    fi

    cd /home/stocks/algo

    local start_time=$(date +%s)

    # Phase 1: Foundation
    echo ""
    print_header "PHASE 1: FOUNDATION"
    python3 loadstocksymbols.py || { print_error "Phase 1 failed"; return 1; }
    python3 loadsectors.py || { print_error "Phase 1 failed"; return 1; }

    # Phase 2: Prices
    echo ""
    print_header "PHASE 2: PRICE DATA"
    python3 loadpricedaily.py || true
    python3 loadpriceweekly.py || true
    python3 loadpricemonthly.py || true
    python3 loadlatestpricedaily.py || true
    python3 loadlatestpriceweekly.py || true
    python3 loadlatestpricemonthly.py || true

    # Phase 3: Earnings
    echo ""
    print_header "PHASE 3: EARNINGS DATA"
    python3 loadearningshistory.py || true
    python3 loadearningsrevisions.py || true
    python3 loadearningssurprise.py || true
    python3 loadguidance.py || true

    # Phase 4A: Financial Statements
    echo ""
    print_header "PHASE 4A: FINANCIAL STATEMENTS"
    python3 loadannualincomestatement.py || true
    python3 loadannualbalancesheet.py || true
    python3 loadannualcashflow.py || true
    python3 loadquarterlyincomestatement.py || true
    python3 loadquarterlybalancesheet.py || true
    python3 loadquarterlycashflow.py || true
    python3 loadttmincomestatement.py || true
    python3 loadttmcashflow.py || true

    # Phase 4B: Sentiment
    echo ""
    print_header "PHASE 4B: SENTIMENT & ANALYST"
    python3 loadanalystsentiment.py || true
    python3 loadanalystupgradedowngrade.py || true
    python3 loadnews.py || true
    python3 loadsentiment.py || true
    python3 loadinsidertransactions.py || true

    # Phase 5: Scores
    echo ""
    print_header "PHASE 5: SCORES & METRICS"
    python3 loadfactormetrics.py || true
    python3 loadfundamentalmetrics.py || true
    python3 loadpositioningmetrics.py || true
    python3 loadstockscores.py || true

    # Phase 6: Technical
    echo ""
    print_header "PHASE 6: TECHNICAL INDICATORS"
    python3 loadbuyselldaily.py || true
    python3 loadbuysellweekly.py || true
    python3 loadbuysellmonthly.py || true
    python3 loadbuysell_etf_daily.py || true
    python3 loadbuysell_etf_weekly.py || true
    python3 loadbuysell_etf_monthly.py || true
    python3 loadrelativeperformance.py || true
    python3 loadseasonality.py || true
    python3 loadaaiidata.py || true
    python3 loadnaaim.py || true
    python3 loadsectorranking.py || true
    python3 loadindustryranking.py || true

    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    local minutes=$((duration / 60))

    echo ""
    print_success "FULL LOAD COMPLETE!"
    print_info "Total time: ${minutes} minutes"
}

# 6. Validate Database
validate_database() {
    print_header "VALIDATING DATABASE"

    cd /home/stocks/algo

    if ! verify_connection; then
        return 1
    fi

    PGPASSWORD=stocks psql -h localhost -U stocks -d stocks << 'SQL'
\x off
\pset format aligned
\pset tuples_only off

SELECT 'Data Validation Report' AS '';
SELECT '=====================' AS '';
SELECT '' AS '';

SELECT 'Stock Symbols' AS table_name,
       COUNT(*) as record_count,
       CASE WHEN COUNT(*) >= 5000 THEN '✓ OK' ELSE '✗ LOW' END as status
FROM stock_symbols

UNION ALL

SELECT 'ETF Symbols' AS table_name,
       COUNT(*) as record_count,
       CASE WHEN COUNT(*) >= 2000 THEN '✓ OK' ELSE '✗ LOW' END as status
FROM etf_symbols

UNION ALL

SELECT 'Sectors' AS table_name,
       COUNT(*) as record_count,
       CASE WHEN COUNT(*) >= 10 THEN '✓ OK' ELSE '✗ MISSING' END as status
FROM sectors

UNION ALL

SELECT 'Price Daily' AS table_name,
       COUNT(*) as record_count,
       CASE WHEN COUNT(*) >= 1000000 THEN '✓ OK' ELSE '✗ INCOMPLETE' END as status
FROM price_daily

UNION ALL

SELECT 'Earnings History' AS table_name,
       COUNT(*) as record_count,
       CASE WHEN COUNT(*) >= 50000 THEN '✓ OK' ELSE '✗ INCOMPLETE' END as status
FROM earnings_history

UNION ALL

SELECT 'Stock Scores' AS table_name,
       COUNT(*) as record_count,
       CASE WHEN COUNT(*) >= 1000 THEN '✓ OK' ELSE '✗ MISSING' END as status
FROM stock_scores

UNION ALL

SELECT 'Last Updated Tracking' AS table_name,
       COUNT(*) as record_count,
       '✓ OK' as status
FROM last_updated

ORDER BY table_name;

SELECT '' AS '';
SELECT 'Last Loader Runs:' AS '';
SELECT script_name, last_run
FROM last_updated
ORDER BY last_run DESC
LIMIT 15;
SQL
}

# 7. Show Database Statistics
show_statistics() {
    print_header "DATABASE STATISTICS"

    cd /home/stocks/algo

    if ! verify_connection; then
        return 1
    fi

    PGPASSWORD=stocks psql -h localhost -U stocks -d stocks << 'SQL'
\x off
\pset format aligned

SELECT 'Complete Database Statistics' AS '';
SELECT '=============================' AS '';
SELECT '' AS '';

SELECT tablename,
       pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size,
       n_live_tup AS row_count
FROM pg_stat_user_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

SELECT '' AS '';
SELECT 'Total Database Size:' AS metric,
       pg_size_pretty(pg_database_size('stocks')) AS size;
SQL
}

# 8. Clean Database
clean_database() {
    print_header "DATABASE CLEANUP WARNING"
    print_error "This will DELETE ALL DATA from the database!"

    read -p "Are you absolutely sure? Type 'YES' to confirm: " confirm
    if [[ "$confirm" != "YES" ]]; then
        print_info "Cancelled"
        return 0
    fi

    print_step "Resetting database..."

    cd /home/stocks/algo
    docker-compose down -v

    print_step "Restarting PostgreSQL..."
    docker-compose up -d
    sleep 10

    print_success "Database reset complete"
}

# 9. Daily Update
daily_update() {
    print_header "DAILY UPDATE"
    print_info "Updating latest prices and scores (10-20 min)"

    cd /home/stocks/algo

    print_step "Updating latest prices..."
    python3 loadlatestpricedaily.py || true
    print_success "Latest prices updated"

    print_step "Updating stock scores..."
    python3 loadstockscores.py || true
    print_success "Stock scores updated"

    print_success "DAILY UPDATE COMPLETE!"
}

# Main loop
main() {
    while true; do
        show_menu

        case $choice in
            1) setup_database ;;
            2) verify_connection ;;
            3) setup_database && verify_connection && load_critical ;;
            4) setup_database && verify_connection && load_critical && load_recommended ;;
            5) setup_database && verify_connection && load_all ;;
            6) validate_database ;;
            7) show_statistics ;;
            8) clean_database ;;
            9) daily_update ;;
            0)
                print_info "Goodbye!"
                exit 0
                ;;
            *)
                print_error "Invalid option"
                ;;
        esac

        read -p "Press Enter to continue..."
    done
}

# Run main if script is executed (not sourced)
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main
fi

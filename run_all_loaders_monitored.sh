#!/bin/bash
#
# Master Loader Script with Dependency Ordering and Monitoring
# Runs all loaders in correct dependency order with error tracking
#
# Phase 1: Foundation loaders (must run first - populate base tables)
# Phase 2: Metric loaders (depend on Phase 1)
# Phase 3: Derived loaders (depend on Phase 1-2)
#
# Usage: ./run_all_loaders_monitored.sh
# Logs: /tmp/loader-*.log (individual loader logs)

set -e

# Database configuration
export DB_HOST=${DB_HOST:-localhost}
export DB_PORT=${DB_PORT:-5432}
export DB_USER=${DB_USER:-stocks}
export DB_PASSWORD=${DB_PASSWORD:-bed0elAn}
export DB_NAME=${DB_NAME:-stocks}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logs directory
LOGS_DIR=/tmp
START_TIME=$(date +%s)

# Track failures
FAILED_LOADERS=()
SUCCESSFUL_LOADERS=()

log_info() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} ℹ️  $1"
}

log_error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} ❌ $1"
}

log_warning() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} ⚠️  $1"
}

run_loader() {
    local loader_name=$1
    local loader_script=$2

    log_info "Starting: $loader_name"

    if python3 "$loader_script" > "$LOGS_DIR/loader-${loader_name}.log" 2>&1; then
        log_info "✅ Completed: $loader_name"
        SUCCESSFUL_LOADERS+=("$loader_name")
        return 0
    else
        log_error "Failed: $loader_name (see $LOGS_DIR/loader-${loader_name}.log)"
        FAILED_LOADERS+=("$loader_name")
        return 1
    fi
}

check_prerequisites() {
    log_info "🔍 Checking prerequisites..."

    # Check database connection
    if ! psql -U "$DB_USER" -d "$DB_NAME" -c "SELECT 1" > /dev/null 2>&1; then
        log_error "Cannot connect to database $DB_NAME. Check DB_HOST, DB_USER, DB_PASSWORD"
        exit 1
    fi

    log_info "✅ Database connection verified"
}

run_phase_1() {
    log_info ""
    log_info "========================================="
    log_info "PHASE 1: Foundation Loaders"
    log_info "========================================="

    # These must run first - they populate critical base tables
    run_loader "loaddailycompanydata" "loaddailycompanydata.py" || log_warning "Phase 1 loader failed (non-critical)"
}

run_phase_2() {
    log_info ""
    log_info "========================================="
    log_info "PHASE 2: Metric Calculation Loaders"
    log_info "========================================="

    # Check if key_metrics has data (required for factor metrics)
    KEY_METRICS_COUNT=$(psql -U "$DB_USER" -d "$DB_NAME" -c "SELECT COUNT(*) FROM key_metrics" -t 2>/dev/null || echo 0)
    if [ "$KEY_METRICS_COUNT" -lt 100 ]; then
        log_warning "key_metrics has only $KEY_METRICS_COUNT records - skipping factor metrics"
        return
    fi

    # Factor metrics depends on key_metrics
    run_loader "loadfactormetrics" "loadfactormetrics.py" || log_warning "Metric loader failed (non-critical)"

    # Stock scores depends on factor metrics
    run_loader "loadstockscores" "loadstockscores.py" || log_warning "Stock scores loader failed (non-critical)"

    # Earnings metrics can run in parallel
    run_loader "loadearningsmetrics" "loadearningsmetrics.py" || log_warning "Earnings metrics loader failed (non-critical)"

    # Technical indicators
    run_loader "loadtechnicalindicators" "loadtechnicalindicators.py" || log_warning "Technical indicators loader failed (non-critical)"
}

run_phase_3() {
    log_info ""
    log_info "========================================="
    log_info "PHASE 3: Derived Data Loaders"
    log_info "========================================="

    # Earnings loaders (depend on earnings_estimates being populated)
    run_loader "loadearningshistory" "loadearningshistory.py" || log_warning "Earnings history loader failed (non-critical)"
    run_loader "loadearningsrevisions" "loadearningsrevisions.py" || log_warning "Earnings revisions loader failed (non-critical)"
    run_loader "loadguidance" "loadguidance.py" || log_warning "Guidance loader failed (non-critical)"

    # Signal loaders (depend on stock_scores)
    run_loader "loadbuyselldaily" "loadbuyselldaily.py" || log_warning "Buy/sell daily loader failed (non-critical)"
    run_loader "loadbuysellweekly" "loadbuysellweekly.py" || log_warning "Buy/sell weekly loader failed (non-critical)"
    run_loader "loadbuysellmonthly" "loadbuysellmonthly.py" || log_warning "Buy/sell monthly loader failed (non-critical)"

    # Sentiment loaders (independent)
    run_loader "loadfeargreed" "loadfeargreed.py" || log_warning "Fear/greed loader failed (non-critical)"
    run_loader "loadaaiidata" "loadaaiidata.py" || log_warning "AAII data loader failed (non-critical)"
    run_loader "loadnaaim" "loadnaaim.py" || log_warning "NAAIM loader failed (non-critical)"
}

print_summary() {
    log_info ""
    log_info "========================================="
    log_info "LOADER EXECUTION SUMMARY"
    log_info "========================================="

    END_TIME=$(date +%s)
    ELAPSED=$((END_TIME - START_TIME))

    log_info "Execution time: ${ELAPSED}s"
    log_info "Successful loaders: ${#SUCCESSFUL_LOADERS[@]}"
    log_info "Failed loaders: ${#FAILED_LOADERS[@]}"

    if [ ${#SUCCESSFUL_LOADERS[@]} -gt 0 ]; then
        log_info "✅ Completed:"
        printf '%s\n' "${SUCCESSFUL_LOADERS[@]}" | sed 's/^/   - /'
    fi

    if [ ${#FAILED_LOADERS[@]} -gt 0 ]; then
        log_error "❌ Failed:"
        printf '%s\n' "${FAILED_LOADERS[@]}" | sed 's/^/   - /'
    fi

    log_info ""
    if [ ${#FAILED_LOADERS[@]} -eq 0 ]; then
        log_info "✅ All loaders completed successfully!"
        return 0
    else
        log_warning "⚠️  Some loaders failed. Check logs in $LOGS_DIR"
        return 1
    fi
}

main() {
    log_info "🚀 Starting Master Loader Suite"
    log_info "Time: $(date)"
    log_info "Database: $DB_USER@$DB_HOST/$DB_NAME"

    check_prerequisites

    run_phase_1
    run_phase_2
    run_phase_3

    print_summary
}

# Run main
main

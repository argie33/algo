#!/bin/bash

################################################################################
# STOCK SCORES RECALCULATION - CLEAN DATA ONLY
# Recalculates all stock scores using ONLY real data (no fake defaults)
# Runs AFTER all data loaders complete
################################################################################

set -e

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Directories
ALGO_DIR="/home/stocks/algo"
LOG_DIR="/home/stocks/logs"

# Create log directory if needed
mkdir -p "$LOG_DIR"

# Timestamp for logs
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="$LOG_DIR/stock_scores_clean_$TIMESTAMP.log"

# Function to log messages
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1" | tee -a "$LOG_FILE"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a "$LOG_FILE"
}

log_header() {
    echo -e "${BLUE}$1${NC}" | tee -a "$LOG_FILE"
}

# Main execution
main() {
    # Show banner
    log_header "==========================================="
    log_header "📊  STOCK SCORES RECALCULATION"
    log_header "==========================================="
    log_info "Recalculating stock scores with REAL DATA ONLY"
    log_info "No fake defaults, no fallback values"
    log_info "Log file: $LOG_FILE"
    log_info "Starting: $(date '+%Y-%m-%d %H:%M:%S')"

    # Verify no loaders running
    log_info "Verifying no loaders are running..."
    running=$(pgrep -f "load.*\.py" | wc -l)
    if [ $running -gt 0 ]; then
        log_error "Found $running loader(s) still running - cannot recalculate"
        exit 1
    fi
    log_info "✅ No loaders running - safe to recalculate"

    # Run stock scores calculation
    log_header "\n==========================================="
    log_header "🧮 Running Stock Scores Calculation"
    log_header "==========================================="
    cd "$ALGO_DIR"

    if python3 loadstockscores.py >> "$LOG_FILE" 2>&1; then
        log_info "✅ Stock scores recalculated successfully"
    else
        log_error "❌ Stock scores recalculation failed - see log for details"
        tail -50 "$LOG_FILE"
        exit 1
    fi

    # Final report
    log_header "\n==========================================="
    log_header "✅ STOCK SCORES COMPLETE"
    log_header "==========================================="
    log_info "All stock scores recalculated with REAL DATA ONLY"
    log_info "Completed: $(date '+%Y-%m-%d %H:%M:%S')"
    log_info "Log file: $LOG_FILE"
}

# Run main
main

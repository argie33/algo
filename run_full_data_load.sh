#!/bin/bash
################################################################################
# FULL DATA LOAD - Complete Growth Metrics Pipeline
#
# This script runs the complete 4-stage data loading pipeline:
#   Stage 1: Annual Income Statements (45 min)
#   Stage 2: Quarterly Income Statements (45 min)
#   Stage 3: Supporting Financial Data (45 min)
#   Stage 4: Growth Metrics Calculation (30 min)
#
# Total time: ~3.5 hours
# Memory: Stable <400MB
# Result: +15,000-20,000 symbols with growth metrics
#
# Usage:
#   ./run_full_data_load.sh                    # Run all stages
#   ./run_full_data_load.sh --stage 1          # Run stage 1 only
#   ./run_full_data_load.sh --monitor          # Open monitoring terminal
#
################################################################################

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Load environment
if [ ! -f ".env.local" ]; then
    echo "❌ .env.local not found - cannot proceed"
    exit 1
fi

source .env.local

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Functions
print_header() {
    echo -e "\n${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}\n"
}

print_status() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

check_python() {
    if ! command -v python3 &> /dev/null; then
        print_error "python3 not found"
        exit 1
    fi
    print_status "Python3 available: $(python3 --version)"
}

check_database() {
    print_status "Database: $DB_HOST:$DB_PORT/$DB_NAME (user: $DB_USER)"

    # Try connecting
    if psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -c "SELECT 1;" > /dev/null 2>&1; then
        print_status "Database connection successful"
    else
        print_warning "Could not verify database connection"
    fi
}

run_stage() {
    local stage=$1
    local stage_name=$2
    local description=$3

    print_header "STAGE $stage: $description"

    start_time=$(date +%s)

    if python3 load_all_growth_data.py --stage "$stage"; then
        end_time=$(date +%s)
        duration=$((end_time - start_time))
        print_status "Stage $stage complete in $((duration/60)) minutes"
        return 0
    else
        print_error "Stage $stage failed"
        return 1
    fi
}

run_growth_metrics() {
    print_header "STAGE 4: Load All Growth Metrics"

    start_time=$(date +%s)

    if python3 load_all_growth_metrics.py --batch-size 500; then
        end_time=$(date +%s)
        duration=$((end_time - start_time))
        print_status "Growth metrics loaded in $((duration/60)) minutes"
        return 0
    else
        print_error "Growth metrics loading failed"
        return 1
    fi
}

show_plan() {
    echo ""
    echo "📋 EXECUTION PLAN"
    echo "   Stage 1: Annual Income Statements  → 45 min"
    echo "   Stage 2: Quarterly Income Statements → 45 min"
    echo "   Stage 3: Supporting Financial Data  → 45 min"
    echo "   Stage 4: Growth Metrics Calculation → 30 min"
    echo ""
    echo "   Total: ~3.5 hours"
    echo "   Active work: ~15 minutes"
    echo "   Expected result: +15,000-20,000 symbols with data"
    echo ""
}

# Main
main() {
    local stage_arg="${1:-all}"

    print_header "FULL DATA LOAD PIPELINE"

    # Checks
    check_python
    check_database

    # Show plan
    show_plan

    # Confirm
    if [ "$stage_arg" != "--skip-confirm" ]; then
        read -p "Ready to start? (yes/no): " confirm
        if [ "$confirm" != "yes" ]; then
            echo "Cancelled"
            exit 0
        fi
    fi

    echo ""
    echo "📊 Starting data load..."
    echo "   Logs: See output below"
    echo "   Execution log: load_all_growth_data_execution.json"
    echo ""

    # Run stages
    case $stage_arg in
        1)
            run_stage 1 "Annual Statements" "Annual Income Statements (4 years)"
            ;;
        2)
            run_stage 2 "Quarterly Statements" "Quarterly Income Statements (8 quarters)"
            ;;
        3)
            run_stage 3 "Supporting Data" "Cash Flow + Balance Sheet + Earnings"
            ;;
        4|growth)
            run_growth_metrics
            ;;
        all|--skip-confirm)
            print_header "RUNNING ALL STAGES"

            overall_start=$(date +%s)

            run_stage 1 "Annual" "Annual Income Statements" || true
            sleep 2

            run_stage 2 "Quarterly" "Quarterly Income Statements" || true
            sleep 2

            run_stage 3 "Supporting" "Supporting Financial Data" || true
            sleep 2

            run_growth_metrics || true

            overall_end=$(date +%s)
            total_time=$((overall_end - overall_start))

            print_header "PIPELINE COMPLETE"
            echo "Total time: $((total_time/60)) minutes $((total_time%60)) seconds"
            echo ""
            echo "📊 Verify results:"
            echo "   psql stocks -c \"SELECT COUNT(*) FROM growth_metrics WHERE date = CURRENT_DATE;\""
            echo ""
            echo "📈 Analyze improvement:"
            echo "   source .env.local && python3 analyze_growth_gaps.py"
            echo ""
            ;;
        --monitor)
            print_header "OPENING MONITORING TERMINALS"

            # Start background processes and monitoring in new terminals
            echo "Starting data load in background..."
            nohup bash -c 'source .env.local && python3 load_all_growth_data.py --stage all && python3 load_all_growth_metrics.py --batch-size 500' > load_pipeline.log 2>&1 &
            PID=$!
            echo "Pipeline PID: $PID"

            # Monitor log
            sleep 2
            tail -f load_pipeline.log
            ;;
        *)
            print_error "Unknown stage: $stage_arg"
            echo "Usage: $0 [1|2|3|4|all|--monitor]"
            exit 1
            ;;
    esac

    echo ""
    echo "✅ All done!"
}

# Run main
main "$@"

#!/bin/bash
# Monitor factor scores pipeline execution and data flow
#
# Usage:
#   ./scripts/monitor_factor_scores_pipeline.sh [--interval 60] [--aws]
#
# Checks:
#   1. Data loader status (% completion)
#   2. Financial data flow (SEC EDGAR income/balance sheet)
#   3. Metric loader coverage (quality, growth, value, positioning, stability)
#   4. Stock scores completeness
#   5. Data freshness
#
# Expected behavior:
#   - SEC EDGAR loaders run with parallelism=1-2 (no rate limiting)
#   - Metric loaders complete in 15-30 minutes (parallelism=2-4)
#   - Stock scores reaches 90%+ coverage
#   - Data freshness < 2 hours

set -e

INTERVAL=${1:-60}  # Default: check every 60 seconds
USE_AWS=${2:-"--local"}  # Default: use local database

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_header() {
    echo ""
    echo "================================================================================"
    echo "FACTOR SCORES PIPELINE MONITOR | $(date +'%Y-%m-%d %H:%M:%S')"
    echo "================================================================================"
}

print_status() {
    local status=$1
    local message=$2

    if [ "$status" = "PASS" ]; then
        echo -e "${GREEN}✓${NC} $message"
    elif [ "$status" = "WARN" ]; then
        echo -e "${YELLOW}⚠${NC} $message"
    else
        echo -e "${RED}✗${NC} $message"
    fi
}

check_loader_status() {
    echo ""
    echo "DATA LOADER STATUS:"
    echo "---"

    python3 << 'EOFPYTHON'
import sys
sys.path.insert(0, '.')
from utils.db.context import DatabaseContext

try:
    with DatabaseContext("read") as cur:
        cur.execute("""
            SELECT
                table_name,
                completion_pct,
                status,
                symbols_loaded,
                symbol_count
            FROM data_loader_status
            WHERE table_name IN (
                'income_statements', 'balance_sheets', 'cash_flow_statements',
                'quality_metrics', 'growth_metrics', 'value_metrics',
                'positioning_metrics', 'stability_metrics', 'stock_scores'
            )
            ORDER BY table_name
        """)

        for table_name, completion, status, symbols_loaded, symbol_count in cur.fetchall():
            if completion >= 90:
                symbol = "✓"
            elif completion >= 70:
                symbol = "⚠"
            else:
                symbol = "✗"

            print(f"  {symbol} {table_name:30} | {completion:6.1f}% | {symbols_loaded:5}/{symbol_count}")
except Exception as e:
    print(f"  ✗ Error: {e}")
EOFPYTHON
}

check_financial_data() {
    echo ""
    echo "FINANCIAL DATA FLOW (SEC EDGAR):"
    echo "---"

    python3 << 'EOFPYTHON'
import sys
sys.path.insert(0, '.')
from utils.db.context import DatabaseContext

try:
    with DatabaseContext("read") as cur:
        # Income statement data
        cur.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN revenue > 0 THEN 1 END) as with_revenue
            FROM annual_income_statement
            WHERE fiscal_year >= 2023
        """)

        total, with_revenue = cur.fetchone()
        pct = (with_revenue / total * 100) if total > 0 else 0

        if pct >= 50:
            symbol = "✓"
        elif pct >= 20:
            symbol = "⚠"
        else:
            symbol = "✗"

        print(f"  {symbol} Income statements: {total} rows, {with_revenue} with real revenue ({pct:.1f}%)")

        # Balance sheet data
        cur.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN total_assets > 0 THEN 1 END) as with_assets
            FROM annual_balance_sheet
            WHERE fiscal_year >= 2023
        """)

        total, with_assets = cur.fetchone()
        pct = (with_assets / total * 100) if total > 0 else 0

        if pct >= 50:
            symbol = "✓"
        elif pct >= 20:
            symbol = "⚠"
        else:
            symbol = "✗"

        print(f"  {symbol} Balance sheets: {total} rows, {with_assets} with real assets ({pct:.1f}%)")

except Exception as e:
    print(f"  ✗ Error: {e}")
EOFPYTHON
}

check_metric_coverage() {
    echo ""
    echo "METRIC COVERAGE:"
    echo "---"

    python3 << 'EOFPYTHON'
import sys
sys.path.insert(0, '.')
from utils.db.context import DatabaseContext

try:
    with DatabaseContext("read") as cur:
        tables = {
            'quality_metrics': 60,
            'growth_metrics': 60,
            'value_metrics': 80,
            'positioning_metrics': 70,
            'stability_metrics': 85,
        }

        for table_name, threshold in tables.items():
            cur.execute(f"""
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN data_unavailable = false OR data_unavailable IS NULL THEN 1 END) as available
                FROM {table_name}
            """)

            total, available = cur.fetchone()
            coverage = (available / total * 100) if total > 0 else 0

            if coverage >= threshold:
                symbol = "✓"
            elif coverage >= threshold * 0.8:
                symbol = "⚠"
            else:
                symbol = "✗"

            print(f"  {symbol} {table_name:25} | {coverage:6.1f}% (threshold: {threshold}%)")

except Exception as e:
    print(f"  ✗ Error: {e}")
EOFPYTHON
}

check_stock_scores() {
    echo ""
    echo "STOCK SCORES STATUS:"
    echo "---"

    python3 << 'EOFPYTHON'
import sys
sys.path.insert(0, '.')
from utils.db.context import DatabaseContext

try:
    with DatabaseContext("read") as cur:
        cur.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN composite_score IS NOT NULL THEN 1 END) as with_score,
                AVG(composite_score) as avg_score,
                MIN(composite_score) as min_score,
                MAX(composite_score) as max_score
            FROM stock_scores
        """)

        total, with_score, avg_score, min_score, max_score = cur.fetchone()
        coverage = (with_score / total * 100) if total > 0 else 0

        if coverage >= 90:
            symbol = "✓"
        elif coverage >= 70:
            symbol = "⚠"
        else:
            symbol = "✗"

        print(f"  {symbol} Coverage: {coverage:.1f}% ({with_score}/{total} stocks with scores)")

        if avg_score:
            print(f"     Score stats: avg={avg_score:.2f}, min={min_score:.2f}, max={max_score:.2f}")

except Exception as e:
    print(f"  ✗ Error: {e}")
EOFPYTHON
}

# Main loop
while true; do
    clear
    print_header
    check_loader_status
    check_financial_data
    check_metric_coverage
    check_stock_scores

    echo ""
    echo "================================================================================"
    echo "Next check in $INTERVAL seconds... (Ctrl+C to stop)"
    echo "================================================================================"

    sleep "$INTERVAL"
done

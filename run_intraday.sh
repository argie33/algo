#!/bin/bash
# Intraday refresh (every 90 min during market hours).
# Refreshes prices + market exposure + position monitoring.
# DOES NOT enter new trades (those wait for EOD signals).

set -e
cd "$(dirname "$0")"

LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S')]"
echo "$LOG_PREFIX === INTRADAY REFRESH ==="

# Quick patrol
python3 algo_data_patrol.py --quick > /dev/null 2>&1 || true

# Refresh intraday prices
if [ -f loadpricedaily.py ]; then
    python3 loadpricedaily.py --intraday 2>/dev/null || true
fi

# Refresh market exposure (so phase 2 of orchestrator has fresh state)
python3 algo_market_exposure.py > /dev/null 2>&1 || true

# Run orchestrator with --dry-run so we just monitor (no entries)
python3 algo_orchestrator.py --dry-run --quiet 2>&1 | tail -20

echo "$LOG_PREFIX === INTRADAY DONE ==="

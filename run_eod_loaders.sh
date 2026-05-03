#!/bin/bash
# End-of-Day loader pipeline
# Run after market close (5:30pm ET).
# Pre/post patrol gates ensure we don't trade on bad data.

set -e
cd "$(dirname "$0")"

LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S')]"
echo "$LOG_PREFIX === EOD LOADER PIPELINE STARTED ==="

# 1. Pre-load patrol
echo "$LOG_PREFIX 1. Pre-load patrol..."
if ! python3 algo_data_patrol.py --quick; then
    echo "$LOG_PREFIX PRE-LOAD PATROL CRITICAL FAILURES — aborting EOD"
    exit 1
fi

# 2. Load in dependency order
echo "$LOG_PREFIX 2. Loading EOD data..."

# Price + technicals + buy/sell (these are foundational)
if [ -f loadpricedaily.py ]; then
    python3 loadpricedaily.py || echo "$LOG_PREFIX WARN: loadpricedaily.py failed"
fi
if [ -f loadtechnicalsdaily.py ]; then
    python3 loadtechnicalsdaily.py || echo "$LOG_PREFIX WARN: loadtechnicalsdaily.py failed"
fi
if [ -f loadbuyselldaily.py ]; then
    python3 loadbuyselldaily.py || echo "$LOG_PREFIX WARN: loadbuyselldaily.py failed"
fi

# Computed metrics (depend on above)
echo "$LOG_PREFIX   - load_algo_metrics_daily.py"
python3 load_algo_metrics_daily.py || echo "$LOG_PREFIX WARN: algo_metrics failed"

# Sector / industry rotation
if [ -f loadsectorranking.py ]; then
    python3 loadsectorranking.py || echo "$LOG_PREFIX WARN: sector_ranking failed"
fi
if [ -f loadindustryranking.py ]; then
    python3 loadindustryranking.py || echo "$LOG_PREFIX WARN: industry_ranking failed"
fi

# Sector rotation signal (uses sector_ranking)
echo "$LOG_PREFIX   - algo_sector_rotation.py"
python3 algo_sector_rotation.py || echo "$LOG_PREFIX WARN: sector_rotation failed"

# Market exposure (last — depends on everything)
echo "$LOG_PREFIX   - algo_market_exposure.py"
python3 algo_market_exposure.py || echo "$LOG_PREFIX WARN: market_exposure failed"

# 3. Post-load patrol
echo "$LOG_PREFIX 3. Post-load patrol..."
python3 algo_data_patrol.py
PATROL_EXIT=$?

# 4. If patrol passed, run orchestrator
if [ $PATROL_EXIT -eq 0 ]; then
    echo "$LOG_PREFIX 4. Running orchestrator..."
    python3 algo_orchestrator.py
else
    echo "$LOG_PREFIX 4. SKIP orchestrator — patrol detected CRITICAL issues"
    exit 1
fi

echo "$LOG_PREFIX === EOD PIPELINE COMPLETE ==="

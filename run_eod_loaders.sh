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

# Phase 1: Foundation — price, technicals, Pine signals
echo "$LOG_PREFIX   1/6 loadpricedaily.py"
python3 loadpricedaily.py || echo "$LOG_PREFIX WARN: loadpricedaily.py failed"

echo "$LOG_PREFIX   2/6 loadtechnicalsdaily.py"
python3 loadtechnicalsdaily.py || echo "$LOG_PREFIX WARN: loadtechnicalsdaily.py failed"

echo "$LOG_PREFIX   3/6 loadbuyselldaily.py"
python3 loadbuyselldaily.py || echo "$LOG_PREFIX WARN: loadbuyselldaily.py failed"

# Phase 2: Computed metrics (require Phase 1 data)
echo "$LOG_PREFIX   4/6 load_algo_metrics_daily.py"
python3 load_algo_metrics_daily.py || echo "$LOG_PREFIX WARN: algo_metrics failed"

# Phase 3: Sector/industry ranks (require ETF + company_profile data)
echo "$LOG_PREFIX   5/6 loadsectorranking.py"
python3 loadsectorranking.py || echo "$LOG_PREFIX WARN: sector_ranking failed"

echo "$LOG_PREFIX   6/6 loadindustryranking.py"
python3 loadindustryranking.py || echo "$LOG_PREFIX WARN: industry_ranking failed"

# Sector rotation signal (uses sector_ranking)
echo "$LOG_PREFIX   - algo_sector_rotation.py"
python3 algo_sector_rotation.py || echo "$LOG_PREFIX WARN: sector_rotation failed"

# Market exposure (depends on everything above)
echo "$LOG_PREFIX   - algo_market_exposure.py"
python3 algo_market_exposure.py || echo "$LOG_PREFIX WARN: market_exposure failed"

# Swing trader scores (last — needs every input above)
echo "$LOG_PREFIX   - loadswingscores.py"
python3 loadswingscores.py || echo "$LOG_PREFIX WARN: swing_scores failed"

# 3. Post-load patrol
echo "$LOG_PREFIX 3. Post-load patrol..."
python3 algo_data_patrol.py
PATROL_EXIT=$?

# 3b. Automatic remediation on findings
echo "$LOG_PREFIX 3b. Auto-remediation..."
python3 algo_data_remediation.py || echo "$LOG_PREFIX WARN: remediation failed"

# 4. If patrol passed, run orchestrator
if [ $PATROL_EXIT -eq 0 ]; then
    echo "$LOG_PREFIX 4. Running orchestrator..."
    python3 algo_orchestrator.py
else
    echo "$LOG_PREFIX 4. SKIP orchestrator — patrol detected CRITICAL issues"
    exit 1
fi

echo "$LOG_PREFIX === EOD PIPELINE COMPLETE ==="

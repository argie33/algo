#!/bin/bash
# Extended backfill loader — refresh last N days of history
#
# Usage:
#   ./run_backfill_loaders.sh 180 AAPL,MSFT,TSLA
#   ./run_backfill_loaders.sh 90          # all symbols from stock_symbols table
#
# This script refetches the last N days of data by overriding the watermark.
# Useful for:
#   - Backtest prep (need 180+ days of history for statistically meaningful tests)
#   - Recovery from corrupted/partial loads
#   - Bootstrapping new metrics (trend_template, swing_scores)

set -e
cd "$(dirname "$0")"

BACKFILL_DAYS=${1:-180}
SYMBOLS=${2:-}

if [ "$BACKFILL_DAYS" -lt 1 ] || [ "$BACKFILL_DAYS" -gt 1825 ]; then
    echo "ERROR: BACKFILL_DAYS must be 1-1825 (5 years max)"
    exit 1
fi

LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S')]"
echo "$LOG_PREFIX === EXTENDED BACKFILL LOADER STARTED (${BACKFILL_DAYS}d) ==="

export BACKFILL_DAYS=$BACKFILL_DAYS

# Backfill core price and technical data
echo "$LOG_PREFIX 1. Backfilling price_daily (${BACKFILL_DAYS} days)..."
if [ -n "$SYMBOLS" ]; then
    python3 loadpricedaily.py --symbols "$SYMBOLS" --parallelism 4
else
    python3 loadpricedaily.py --parallelism 8
fi

echo "$LOG_PREFIX 2. Backfilling technical_data_daily..."
python3 loadtechnicalsdaily.py --parallelism 8

echo "$LOG_PREFIX 3. Backfilling buy_sell signals..."
python3 loadbuyselldaily.py --parallelism 4

# Backfill metrics that depend on prices (trend_template, swing_scores)
echo "$LOG_PREFIX 4. Backfilling signal_quality_scores..."
python3 loadswingscores.py --parallelism 8

echo "$LOG_PREFIX 5. Backfilling trend_template_data..."
python3 loadtrend.py --parallelism 4

echo "$LOG_PREFIX === BACKFILL COMPLETE ==="
echo "$LOG_PREFIX You can now run:"
echo "$LOG_PREFIX   python3 algo_orchestrator.py --backtest"

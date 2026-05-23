#!/bin/bash

# Entrypoint for ECS loader container
# Reads LOADER_FILE env var to determine which loader to run
# Supports LOADER_PARALLELISM for thread pool sizing

set -euo pipefail
cd /app

# Redirect all output to both stdout and stderr to ensure CloudWatch captures it
exec 2>&1

# Validate LOADER_FILE is set
if [ -z "$LOADER_FILE" ]; then
    echo "[ENTRYPOINT] ERROR: LOADER_FILE environment variable not set"
    exit 1
fi

# Validate loader file exists
if [ ! -f "loaders/$LOADER_FILE" ]; then
    echo "[ENTRYPOINT] ERROR: Loader file not found: loaders/$LOADER_FILE"
    ls -1 loaders/*.py
    exit 1
fi

# Export parallelism if set
if [ -n "$LOADER_PARALLELISM" ]; then
    export PARALLELISM=$LOADER_PARALLELISM
fi

# Logging to stdout
echo "[ENTRYPOINT] Starting loader: $LOADER_FILE"
echo "[ENTRYPOINT] LOADER_TYPE: ${LOADER_TYPE:-unset}"
echo "[ENTRYPOINT] Python: $(python3 --version 2>&1)"
echo "[ENTRYPOINT] Dir: $(pwd)"

# Build command with loader-specific arguments based on LOADER_TYPE
LOADER_ARGS=()
case "$LOADER_TYPE" in
    # Stock prices (all intervals + asset classes in one run)
    stock_prices_daily)
        LOADER_ARGS=("--interval" "1d,1wk,1mo" "--asset-class" "stock,etf")
        ;;
    # Parametrized signal loaders (daily/weekly/monthly timeframes)
    signals_daily)
        LOADER_ARGS=("--timeframe" "daily")
        ;;
    signals_weekly)
        LOADER_ARGS=("--timeframe" "weekly")
        ;;
    signals_monthly)
        LOADER_ARGS=("--timeframe" "monthly")
        ;;
    signals_etf_daily)
        LOADER_ARGS=("--timeframe" "daily" "--asset-class" "etf")
        ;;
    signals_etf_weekly)
        LOADER_ARGS=("--timeframe" "weekly" "--asset-class" "etf")
        ;;
    signals_etf_monthly)
        LOADER_ARGS=("--timeframe" "monthly" "--asset-class" "etf")
        ;;
    # Parametrized financial loaders (annual/quarterly periods)
    financials_annual_income|financials_annual_balance|financials_annual_cashflow)
        LOADER_ARGS=("--period" "annual")
        ;;
    financials_quarterly_income|financials_quarterly_balance|financials_quarterly_cashflow)
        LOADER_ARGS=("--period" "quarterly")
        ;;
    # TTM income/cashflow: rerun quarterly loader (TTM is derived from 4 quarters)
    financials_ttm_income)
        LOADER_ARGS=("--period" "quarterly")
        ;;
    financials_ttm_cashflow)
        LOADER_ARGS=("--period" "quarterly")
        ;;
esac

# Run loader with loader-specific arguments + any extra args passed in
echo "[ENTRYPOINT] Executing: python3 -u loaders/$LOADER_FILE ${LOADER_ARGS[@]} $@"
python3 -u "loaders/$LOADER_FILE" "${LOADER_ARGS[@]}" "$@"
EXIT_CODE=$?
echo "[ENTRYPOINT] Loader exited with code: $EXIT_CODE"
exit $EXIT_CODE

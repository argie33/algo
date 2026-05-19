#!/bin/bash

# Entrypoint for ECS loader container
# Reads LOADER_FILE env var to determine which loader to run
# Supports LOADER_PARALLELISM for thread pool sizing

set -x  # Enable debug mode to show all commands executed
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
echo "[ENTRYPOINT] LOADER_TYPE: $LOADER_TYPE"
echo "[ENTRYPOINT] DB_HOST=$DB_HOST, DB_PORT=$DB_PORT, DB_NAME=$DB_NAME"
echo "[ENTRYPOINT] Python: $(python3 --version 2>&1)"
echo "[ENTRYPOINT] Dir: $(pwd)"

# Build command with loader-specific arguments based on LOADER_TYPE
LOADER_ARGS=()
case "$LOADER_TYPE" in
    # Parametrized price loaders (1d/1wk/1mo intervals)
    stock_prices_daily|eod_bulk_refresh)
        LOADER_ARGS=("--interval" "1d")
        ;;
    stock_prices_weekly)
        LOADER_ARGS=("--interval" "1wk")
        ;;
    stock_prices_monthly)
        LOADER_ARGS=("--interval" "1mo")
        ;;
    etf_prices_daily)
        LOADER_ARGS=("--interval" "1d" "--asset-class" "etf")
        ;;
    etf_prices_weekly)
        LOADER_ARGS=("--interval" "1wk" "--asset-class" "etf")
        ;;
    etf_prices_monthly)
        LOADER_ARGS=("--interval" "1mo" "--asset-class" "etf")
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
esac

# Run loader with loader-specific arguments + any extra args passed in
echo "[ENTRYPOINT] Executing: python3 -u loaders/$LOADER_FILE ${LOADER_ARGS[@]} $@"
python3 -u "loaders/$LOADER_FILE" "${LOADER_ARGS[@]}" "$@"
EXIT_CODE=$?
echo "[ENTRYPOINT] Loader exited with code: $EXIT_CODE"
exit $EXIT_CODE

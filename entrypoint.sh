#!/bin/bash

# Entrypoint for ECS loader container
# Reads LOADER_FILE env var to determine which loader to run
# Supports LOADER_PARALLELISM for thread pool sizing
# Note: NOT using 'set -e' so we can catch all errors

cd /app

# Log function that writes to both stdout and stderr for CloudWatch capture
log_msg() {
    local msg="$1"
    echo "[ENTRYPOINT] $msg"
    echo "[ENTRYPOINT] $msg" >&2
}

# Validate LOADER_FILE is set
if [ -z "$LOADER_FILE" ]; then
    log_msg "ERROR: LOADER_FILE environment variable not set"
    log_msg "Usage: export LOADER_FILE=loadstocksymbols.py"
    exit 1
fi

# Validate loader file exists
if [ ! -f "loaders/$LOADER_FILE" ]; then
    log_msg "ERROR: Loader file not found: loaders/$LOADER_FILE"
    log_msg "Available loaders:"
    ls -1 loaders/*.py | sed 's|loaders/||' >&2
    exit 1
fi

# Export parallelism if set (loaders will read from env)
if [ -n "$LOADER_PARALLELISM" ]; then
    export PARALLELISM=$LOADER_PARALLELISM
fi

# Log environment and start
log_msg "Starting loader: $LOADER_FILE"
log_msg "Environment: DB_HOST=$DB_HOST DB_PORT=$DB_PORT DB_NAME=$DB_NAME LOADER_PARALLELISM=$LOADER_PARALLELISM"
log_msg "Python version: $(python3 --version 2>&1)"
log_msg "Working directory: $(pwd)"

# Run the loader with unbuffered output and explicit error handling
log_msg "Executing: python3 -u loaders/$LOADER_FILE"
if python3 -u "loaders/$LOADER_FILE" "$@"; then
    EXIT_CODE=0
    log_msg "Loader completed successfully (exit code 0)"
else
    EXIT_CODE=$?
    log_msg "Loader failed with exit code: $EXIT_CODE"
fi

log_msg "Entrypoint exiting with code: $EXIT_CODE"
exit $EXIT_CODE

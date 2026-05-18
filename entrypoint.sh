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
echo "[ENTRYPOINT] DB_HOST=$DB_HOST, DB_PORT=$DB_PORT, DB_NAME=$DB_NAME"
echo "[ENTRYPOINT] Python: $(python3 --version 2>&1)"
echo "[ENTRYPOINT] Dir: $(pwd)"

# Run loader
echo "[ENTRYPOINT] Executing: python3 -u loaders/$LOADER_FILE"
python3 -u "loaders/$LOADER_FILE" "$@"
EXIT_CODE=$?
echo "[ENTRYPOINT] Loader exited with code: $EXIT_CODE"
exit $EXIT_CODE

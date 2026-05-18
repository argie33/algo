#!/bin/bash

# Entrypoint for ECS loader container
# Reads LOADER_FILE env var to determine which loader to run
# Supports LOADER_PARALLELISM for thread pool sizing

set -x  # Enable debug mode to show all commands executed
cd /app

# Validate LOADER_FILE is set
if [ -z "$LOADER_FILE" ]; then
    echo "[ENTRYPOINT] ERROR: LOADER_FILE environment variable not set"  >&2
    exit 1
fi

# Validate loader file exists
if [ ! -f "loaders/$LOADER_FILE" ]; then
    echo "[ENTRYPOINT] ERROR: Loader file not found: loaders/$LOADER_FILE" >&2
    ls -1 loaders/*.py | sed 's|loaders/||' >&2
    exit 1
fi

# Export parallelism if set
if [ -n "$LOADER_PARALLELISM" ]; then
    export PARALLELISM=$LOADER_PARALLELISM
fi

# Simple logging directly to stderr
echo "[ENTRYPOINT] Starting loader: $LOADER_FILE" >&2
echo "[ENTRYPOINT] DB_HOST=$DB_HOST, DB_PORT=$DB_PORT, DB_NAME=$DB_NAME" >&2
echo "[ENTRYPOINT] Python: $(python3 --version 2>&1)" >&2
echo "[ENTRYPOINT] Dir: $(pwd)" >&2

# Run loader
echo "[ENTRYPOINT] Executing: python3 -u loaders/$LOADER_FILE" >&2
python3 -u "loaders/$LOADER_FILE" "$@"
EXIT_CODE=$?
echo "[ENTRYPOINT] Loader exited with code: $EXIT_CODE" >&2
exit $EXIT_CODE

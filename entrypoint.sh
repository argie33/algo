#!/bin/bash
set -e

# Entrypoint for ECS loader container
# Reads LOADER_FILE env var to determine which loader to run
# Supports LOADER_PARALLELISM for thread pool sizing

cd /app

# Validate LOADER_FILE is set
if [ -z "$LOADER_FILE" ]; then
    echo "ERROR: LOADER_FILE environment variable not set" >&2
    echo "Usage: export LOADER_FILE=loadstocksymbols.py" >&2
    exit 1
fi

# Validate loader file exists
if [ ! -f "loaders/$LOADER_FILE" ]; then
    echo "ERROR: Loader file not found: loaders/$LOADER_FILE" >&2
    echo "Available loaders:" >&2
    ls -1 loaders/*.py | sed 's|loaders/||' >&2
    exit 1
fi

# Export parallelism if set (loaders will read from env)
if [ -n "$LOADER_PARALLELISM" ]; then
    export PARALLELISM=$LOADER_PARALLELISM
fi

# Run the loader with any additional arguments
echo "Starting loader: $LOADER_FILE (parallelism: ${LOADER_PARALLELISM:-auto})"
python3 "loaders/$LOADER_FILE" "$@"

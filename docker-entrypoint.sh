#!/bin/bash
# Docker entrypoint for loader tasks
# Uses LOADER_FILE env var to determine which loader to run

set -e

# Log the environment for debugging
echo "=== Loader Task Configuration ==="
echo "LOADER_NAME: ${LOADER_NAME:-NOT SET}"
echo "LOADER_FILE: ${LOADER_FILE:-NOT SET}"
echo "LOADER_TYPE: ${LOADER_TYPE:-NOT SET}"
echo ""

# Use LOADER_FILE if set, otherwise default to loadpricedaily.py
LOADER_SCRIPT="${LOADER_FILE:-loadpricedaily.py}"

# Handle both absolute and relative paths
if [[ ! "$LOADER_SCRIPT" =~ ^/ ]]; then
    LOADER_SCRIPT="loaders/$LOADER_SCRIPT"
fi

# Verify the file exists
if [ ! -f "$LOADER_SCRIPT" ]; then
    echo "ERROR: Loader script not found: $LOADER_SCRIPT"
    echo "Available loaders:"
    ls loaders/load*.py loaders/*.py 2>/dev/null | grep -E '\.(py)$' | xargs -I {} basename {} | sort
    exit 1
fi

echo "Running loader: $LOADER_SCRIPT"
echo "=========================================="
echo ""

# Run the loader
exec python3 -u "$LOADER_SCRIPT" "$@"

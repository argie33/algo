#!/bin/bash
# Load environment variables and execute Python loader script
# This wrapper script ensures all environment variables are available to Python loaders

set -e

# Load production environment variables if they exist
if [ -f /home/stocks/algo/.env.production ]; then
    set -a
    source /home/stocks/algo/.env.production
    set +a
fi

# If no arguments provided, exit
if [ $# -eq 0 ]; then
    echo "Usage: $0 <python_script>"
    exit 1
fi

# Execute the Python script with all environment variables
exec python3 "$@"

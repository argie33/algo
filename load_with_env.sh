#!/bin/bash
# Load environment variables and execute Python loader script
# This wrapper script ensures all environment variables are available to Python loaders

# Change to repo directory
cd /home/stocks/algo

# Load production environment variables if they exist
if [ -f /home/stocks/algo/.env.production ]; then
    set -a
    . /home/stocks/algo/.env.production
    set +a
fi

# If no arguments provided, exit
if [ $# -eq 0 ]; then
    echo "Usage: $0 <python_script>"
    exit 1
fi

# If script argument doesn't have .py extension, add it
SCRIPT="$1"
if [[ "$SCRIPT" != *.py ]]; then
    SCRIPT="${SCRIPT}.py"
fi

# If script path is not absolute, make it relative to /home/stocks/algo
if [[ "$SCRIPT" != /* ]]; then
    SCRIPT="/home/stocks/algo/${SCRIPT}"
fi

# Execute the Python script with all environment variables
exec python3 "$SCRIPT"

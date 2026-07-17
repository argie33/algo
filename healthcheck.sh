#!/bin/bash
# ECS Health Check for Loader Tasks
# Validates that loader process is responding and making progress.
# Called every 30 seconds by ECS; if it fails 2x, task marked UNHEALTHY.

HEALTH_FILE="/tmp/loader_health_check"
TIMEOUT=60  # Mark unhealthy if file is older than 60 seconds

# Check if Python process is running
if ! pgrep -f 'python.*loaders/' > /dev/null; then
    echo "ERROR: No loader process found"
    exit 1
fi

# Check if health check file exists and is fresh
if [ ! -f "$HEALTH_FILE" ]; then
    echo "ERROR: Health check file not found"
    exit 1
fi

# Get age of health check file (in seconds)
current_time=$(date +%s)
file_time=$(stat -c %Y "$HEALTH_FILE" 2>/dev/null || stat -f %m "$HEALTH_FILE" 2>/dev/null)

if [ -z "$file_time" ]; then
    echo "ERROR: Cannot read health check file timestamp"
    exit 1
fi

age=$((current_time - file_time))

if [ $age -gt $TIMEOUT ]; then
    echo "ERROR: Health check stale (${age}s > ${TIMEOUT}s) - loader appears stuck"
    exit 1
fi

echo "OK: Loader healthy (age: ${age}s, threshold: ${TIMEOUT}s)"
exit 0

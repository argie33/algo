#!/bin/bash
# Direct test runner with interactive terminal
set -e

# Change to the test directory
cd "$(dirname "$0")"

# Build the containers
docker-compose build

# Run PostgreSQL in the background
docker-compose up -d postgres

# Wait a moment for PostgreSQL to start
echo "Waiting for PostgreSQL to start..."
sleep 5

# Run the test runner in interactive mode with TTY allocation
docker-compose run --rm test-runner python -u /app/run_direct_test.py

# Clean up after
docker-compose down

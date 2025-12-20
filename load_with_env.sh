#!/bin/bash
# Environment setup for loaders
export DB_HOST="localhost"
export DB_NAME="stocks"
export DB_USER="stocks"
export DB_PASSWORD="bed0elAn"
export DB_PORT="5432"

exec "$@"

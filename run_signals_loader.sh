#!/bin/bash
export DB_HOST=localhost
export DB_PORT=5432
export DB_USER=postgres
export DB_PASSWORD=password
export DB_NAME=stocks
python3 loadbuyselldaily.py 2>&1 | tee /tmp/generate_signals_fixed.log

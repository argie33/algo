#!/bin/bash
export DB_PASSWORD=bed0elAn
export DB_HOST=localhost
export DB_USER=stocks
export DB_NAME=stocks

echo "Starting essential loaders..."
echo

# Daily company data - loads key_metrics
echo "1. Loading daily company data (key_metrics)..."
python3 loaddailycompanydata.py
echo "Done"
echo

# Factor metrics - loads quality/growth/momentum/stability/value metrics
echo "2. Loading factor metrics..."
python3 loadfactormetrics.py
echo "Done"
echo

# Stock scores - loads composite scores
echo "3. Loading stock scores..."
python3 loadstockscores.py
echo "Done"

echo "Essential loaders complete!"

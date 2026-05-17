#!/bin/bash

echo "=========================================="
echo "LOADING CRITICAL DATA"
echo "=========================================="
echo ""

# Load company profiles
echo "[1/4] Loading company profiles..."
python3 loaders/loadcompanyprofile.py --parallelism 8 2>&1 | tail -5
echo ""

# Load earnings calendar
echo "[2/4] Loading earnings calendar..."
python3 loaders/load_earnings_calendar.py 2>&1 | tail -5
echo ""

# Load earnings history (has partial data)
echo "[3/4] Loading earnings history (should already be mostly loaded)..."
python3 loaders/loadearningshistory.py 2>&1 | tail -5
echo ""

# Verify data was loaded
echo "[4/4] Verifying data population..."
python3 audit_data_gaps.py 2>&1 | grep -A 20 "TABLE POPULATION"
echo ""

echo "=========================================="
echo "Data loading complete!"
echo "=========================================="

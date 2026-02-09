#!/bin/bash
# FINAL WORKING DATA LOADER
# Run this ONE command to load all data

set -e
LOG="/tmp/data_loader_$(date +%s).log"

{
  echo "╔════════════════════════════════════════════════════╗"
  echo "║  STARTING COMPLETE DATA RELOAD                     ║"
  echo "║  $(date)                             ║"
  echo "╚════════════════════════════════════════════════════╝"
  echo ""
  echo "📊 PHASE 1: Company Data (60-90 min)"
  echo "Loading from yfinance: PE, margins, ownership, short interest..."
  cd /home/stocks/algo
  python3 loaddailycompanydata.py
  
  echo ""
  echo "📊 PHASE 2: Factor Metrics (20-30 min)"
  echo "Calculating: quality, growth, stability, momentum, value..."
  python3 loadfactormetrics.py
  
  echo ""
  echo "📊 PHASE 3: Stock Scores (5 min)"
  echo "Computing: composite scores from all factors..."
  python3 loadstockscores.py
  
  echo ""
  echo "╔════════════════════════════════════════════════════╗"
  echo "║  ✅ COMPLETE - DATA LOADED SUCCESSFULLY            ║"
  echo "║  Website now has 100% real data                   ║"
  echo "╚════════════════════════════════════════════════════╝"
  
} 2>&1 | tee "$LOG"

echo "Log saved to: $LOG"

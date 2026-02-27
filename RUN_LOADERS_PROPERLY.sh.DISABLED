#!/bin/bash

# CORRECT DATA LOADING SEQUENCE FOR ALGO STOCK PLATFORM
# This runs loaders in dependency order with proper delays to avoid rate limiting

set -e

export PGPASSWORD="bed0elAn"
export DB_HOST="localhost"
export DB_USER="stocks"
export DB_PASSWORD="bed0elAn"
export DB_NAME="stocks"

cd /home/arger/algo

echo "╔════════════════════════════════════════════════════════════════════════════════╗"
echo "║     📊 DATA LOADING SEQUENCE - Run in AWS/CloudShell or Locally 📊             ║"
echo "╚════════════════════════════════════════════════════════════════════════════════╝"
echo ""

# ─── PHASE 1: CRITICAL DATA (no dependencies) ──────────────────────────────────
echo "═══════════════════════════════════════════════════════════════════════════════"
echo "PHASE 1: CRITICAL DATA (Must complete successfully)"
echo "═══════════════════════════════════════════════════════════════════════════════"
echo ""

# 1. Stock symbols (must load first - everything depends on this)
echo "▶️  [1/7] Loading stock symbols (4988 stocks)..."
if python3 loadstocksymbols.py 2>&1 | tail -5; then
  echo "✅ Stock symbols loaded"
else
  echo "❌ FAILED: loadstocksymbols.py - exiting"
  exit 1
fi
sleep 2

# 2. Historical prices (needed for technical indicators)
echo ""
echo "▶️  [2/7] Loading historical daily prices (this takes ~30-45 min in AWS)..."
echo "   Running: python3 loadpricedaily.py"
if timeout 3600 python3 loadpricedaily.py 2>&1 | tail -10; then
  echo "✅ Daily prices loaded"
else
  echo "⚠️  Price load timed out or failed (may have partial data)"
fi
sleep 2

# ─── PHASE 2: FINANCIAL DATA (required for growth/value metrics) ──────────────────
echo ""
echo "═══════════════════════════════════════════════════════════════════════════════"
echo "PHASE 2: FINANCIAL DATA (Feeds growth/value metric calculations)"
echo "═══════════════════════════════════════════════════════════════════════════════"
echo ""

# These load financial statements needed for growth and value metrics
echo "▶️  [3/7] Loading financial statements (annual, quarterly, earnings history)..."
for loader in loadannualincomestatement.py loadannualbalancesheet.py loadannualcashflow.py loadquarterlybalancesheet.py loadearningshistory.py; do
  if [ -f "$loader" ]; then
    echo "  - Loading: $loader"
    timeout 600 python3 "$loader" > /tmp/loader_$(echo $loader | sed 's/.py//' | cut -c1-30).log 2>&1 && echo "    ✓ Loaded" || echo "    ⚠️  Error (check /tmp/loader_*.log)"
    sleep 1
  fi
done
echo "✅ Financial data loaded"
sleep 2

# ─── PHASE 3: METRICS CALCULATION (depends on prices + financial data) ─────────────
echo ""
echo "═══════════════════════════════════════════════════════════════════════════════"
echo "PHASE 3: FACTOR METRICS (depends on prices + financial data)"
echo "═══════════════════════════════════════════════════════════════════════════════"
echo ""

# This uses prices + financial data to calculate all metrics
echo "▶️  [4/7] Calculating factor metrics (quality, growth, value, momentum, etc)..."
if timeout 1200 python3 loadfactormetrics.py 2>&1 | tail -20; then
  echo "✅ Factor metrics calculated"
else
  echo "⚠️  Factor metrics calculation failed or timed out"
fi
sleep 2

# ─── PHASE 4: TECHNICAL INDICATORS (depends on prices) ─────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════════════════════════════"
echo "PHASE 4: TECHNICAL INDICATORS (depends on prices)"
echo "═══════════════════════════════════════════════════════════════════════════════"
echo ""

echo "▶️  [5/7] Loading technical indicators..."
if timeout 600 python3 loadtechnicalindicators.py 2>&1 | tail -5; then
  echo "✅ Technical indicators loaded"
else
  echo "⚠️  Technical indicators load failed"
fi
sleep 2

# ─── PHASE 5: SIGNALS (depends on prices + technical indicators) ───────────────────
echo ""
echo "═══════════════════════════════════════════════════════════════════════════════"
echo "PHASE 5: BUY/SELL SIGNALS (depends on prices + technical indicators)"
echo "═══════════════════════════════════════════════════════════════════════════════"
echo ""

echo "▶️  [6/7] Loading buy/sell signals (daily)..."
if timeout 1200 python3 loadbuyselldaily.py 2>&1 | tail -5; then
  echo "✅ Buy/sell signals loaded"
else
  echo "⚠️  Buy/sell signals load failed"
fi
sleep 2

# ─── PHASE 6: OPTIONAL DATA ────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════════════════════════════"
echo "PHASE 6: OPTIONAL DATA (nice-to-have metrics)"
echo "═══════════════════════════════════════════════════════════════════════════════"
echo ""

echo "▶️  [7/7] Loading optional data (analyst sentiment, seasonality, etc)..."
for loader in loadstockscores.py loadanalystsentiment.py loadseasonality.py; do
  if [ -f "$loader" ]; then
    echo "  - Loading: $loader"
    timeout 300 python3 "$loader" > /tmp/loader_$(echo $loader | sed 's/.py//' | cut -c1-30).log 2>&1 && echo "    ✓ Loaded" || echo "    ⚠️  Error (check logs)"
    sleep 1
  fi
done
echo "✅ Optional data loaded"

# ─── SUMMARY ──────────────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════════════════════════════"
echo "✅ LOADING COMPLETE"
echo "═══════════════════════════════════════════════════════════════════════════════"
echo ""
echo "Database Status:"
psql -h localhost -U stocks -d stocks -c "
  SELECT 
    'Stock Symbols' as table_name, COUNT(*) as count FROM stock_symbols
  UNION ALL
  SELECT 'Stock Scores', COUNT(*) FROM stock_scores
  UNION ALL
  SELECT 'Prices (daily)', COUNT(*) FROM price_daily
  UNION ALL
  SELECT 'Buy/Sell Signals', COUNT(*) FROM buy_sell_daily
  UNION ALL
  SELECT 'Quality Metrics', COUNT(*) FROM quality_metrics
  UNION ALL
  SELECT 'Growth Metrics', COUNT(*) FROM growth_metrics
  UNION ALL
  SELECT 'Value Metrics', COUNT(*) FROM value_metrics
  ORDER BY count DESC;
" 2>/dev/null || echo "⚠️  Could not verify database (psql not available)"

echo ""
echo "✅ All loaders completed"
echo ""

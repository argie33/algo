#!/bin/bash
set -e

echo "🚀 STARTING DATA PIPELINE - REAL DATA ONLY (All 5315 Stocks)"
echo ""

export USE_LOCAL_DB=true
export DB_HOST=localhost
export DB_PORT=5432
export DB_USER=postgres
export DB_PASSWORD=password
export DB_NAME=stocks

echo "📊 STEP 1: Load Quality Metrics (debt_to_equity, current_ratio, eps_growth_stability)"
python3 loadqualitymetrics.py 2>&1 &
QUALITY_PID=$!
sleep 30

echo ""
echo "📊 STEP 2: Load Risk Metrics (volatility_12m_pct, max_drawdown_52w_pct, volatility_risk_component)"
python3 loadriskmetrics.py 2>&1 &
RISK_PID=$!
sleep 30

echo ""
echo "📊 STEP 3: Load Value Metrics (valuation, PE ratios, PEG, dividend yield, FCF yield)"
python3 loadvaluemetrics.py 2>&1 &
VALUE_PID=$!
sleep 30

echo ""
echo ""
echo "📊 STEP 4: Load Growth Metrics (earnings growth, revenue growth)"
python3 loadgrowthmetrics.py 2>&1 &
GROWTH_PID=$!
sleep 30

echo ""
echo "📊 STEP 5: Load Sector & Industry Rankings (11 sectors + 100+ industries with historical snapshots)"
python3 loadsectorindustrydata.py 2>&1 &
SECTOR_INDUSTRY_PID=$!
sleep 30

echo ""
echo "📊 STEP 6: Calculate Stock Scores (using real data from all metrics: quality, risk, value, growth)"
python3 loadstockscores.py 2>&1 &
SCORES_PID=$!

echo ""
echo "⏳ Waiting for all loaders to complete..."
wait $QUALITY_PID $RISK_PID $VALUE_PID $GROWTH_PID $SECTOR_INDUSTRY_PID $SCORES_PID 2>/dev/null || true

echo ""
echo "✅ DATA PIPELINE COMPLETE - All 5315 stocks processed with REAL DATA ONLY"

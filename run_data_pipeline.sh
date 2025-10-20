#!/bin/bash
set -e

echo "🚀 STARTING DATA PIPELINE - REAL DATA ONLY"
echo ""

export USE_LOCAL_DB=true
export DB_HOST=localhost
export DB_PORT=5432
export DB_USER=postgres
export DB_PASSWORD=password
export DB_NAME=stocks

echo "📊 STEP 1: Load Quality Metrics (debt_to_equity, current_ratio, eps_growth_stability)"
python3 loadqualitymetrics.py 2>&1 | head -50 &
QUALITY_PID=$!

sleep 30

echo ""
echo "📊 STEP 2: Load Risk Metrics (volatility_12m_pct, max_drawdown_52w_pct, volatility_risk_component)"
python3 loadriskmetrics.py 2>&1 | head -50 &
RISK_PID=$!

sleep 30

echo ""
echo "📊 STEP 3: Calculate Stock Scores (using real data from quality_metrics and risk_metrics)"
python3 loadstockscores.py 2>&1 | head -50 &
SCORES_PID=$!

echo ""
echo "⏳ Waiting for all loaders to complete..."
wait $QUALITY_PID $RISK_PID $SCORES_PID 2>/dev/null || true

echo ""
echo "✅ DATA PIPELINE COMPLETE"

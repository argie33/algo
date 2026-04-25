#!/bin/bash
echo "Starting critical data loaders..."
echo "=================================="

# Run in background
python loadpricedaily.py > /tmp/price-daily.log 2>&1 &
PRICE_PID=$!
echo "✓ loadpricedaily.py (PID: $PRICE_PID)"

python loadpriceweekly.py > /tmp/price-weekly.log 2>&1 &
PRICE_W_PID=$!
echo "✓ loadpriceweekly.py (PID: $PRICE_W_PID)"

python loadpricemonthly.py > /tmp/price-monthly.log 2>&1 &
PRICE_M_PID=$!
echo "✓ loadpricemonthly.py (PID: $PRICE_M_PID)"

python loadetfpricedaily.py > /tmp/etf-price-daily.log 2>&1 &
ETF_PRICE_PID=$!
echo "✓ loadetfpricedaily.py (PID: $ETF_PRICE_PID)"

python loadtechnicalindicators.py > /tmp/technical.log 2>&1 &
TECH_PID=$!
echo "✓ loadtechnicalindicators.py (PID: $TECH_PID)"

python loaddailycompanydata.py > /tmp/company.log 2>&1 &
COMPANY_PID=$!
echo "✓ loaddailycompanydata.py (PID: $COMPANY_PID)"

python loadannualincomestatement.py > /tmp/annual-income.log 2>&1 &
INCOME_PID=$!
echo "✓ loadannualincomestatement.py (PID: $INCOME_PID)"

python loadannualbalancesheet.py > /tmp/annual-balance.log 2>&1 &
BALANCE_PID=$!
echo "✓ loadannualbalancesheet.py (PID: $BALANCE_PID)"

python loadannualcashflow.py > /tmp/annual-cashflow.log 2>&1 &
CASHFLOW_PID=$!
echo "✓ loadannualcashflow.py (PID: $CASHFLOW_PID)"

python loadearningshistory.py > /tmp/earnings-history.log 2>&1 &
EARNINGS_PID=$!
echo "✓ loadearningshistory.py (PID: $EARNINGS_PID)"

python loadfactormetrics.py > /tmp/factor-metrics.log 2>&1 &
FACTOR_PID=$!
echo "✓ loadfactormetrics.py (PID: $FACTOR_PID)"

echo ""
echo "All loaders started. Waiting for completion..."
echo "Monitor logs in /tmp/*.log"
echo ""

wait $PRICE_PID $PRICE_W_PID $PRICE_M_PID $ETF_PRICE_PID $TECH_PID $COMPANY_PID $INCOME_PID $BALANCE_PID $CASHFLOW_PID $EARNINGS_PID $FACTOR_PID

echo ""
echo "✅ All loaders complete!"

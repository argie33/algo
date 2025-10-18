#!/bin/bash
# Quick diagnostic of what data is available for growth metrics

echo "======================================================================"
echo "GROWTH METRICS DATA AVAILABILITY DIAGNOSTIC"
echo "======================================================================"

echo ""
echo "1. KEY_METRICS TABLE (Revenue/EPS growth from yfinance):"
psql -h localhost -U postgres -d stocks -c "SELECT COUNT(*), COUNT(DISTINCT ticker) as symbols, AVG(revenue_growth_pct) as avg_rev_growth, AVG(earnings_growth_pct) as avg_eps_growth FROM key_metrics WHERE revenue_growth_pct IS NOT NULL OR earnings_growth_pct IS NOT NULL;" 2>/dev/null || echo "❌ Cannot connect to DB"

echo ""
echo "2. QUARTERLY_INCOME_STATEMENT TABLE:"
psql -h localhost -U postgres -d stocks -c "SELECT COUNT(*) as total_records, COUNT(DISTINCT symbol) as symbols, COUNT(DISTINCT item_name) as item_types FROM quarterly_income_statement;" 2>/dev/null

echo ""
echo "3. Available ITEM_NAMES in quarterly_income_statement:"
psql -h localhost -U postgres -d stocks -c "SELECT item_name, COUNT(*) as qty FROM quarterly_income_statement GROUP BY item_name ORDER BY qty DESC;" 2>/dev/null

echo ""
echo "4. QUARTERLY_CASH_FLOW TABLE:"
psql -h localhost -U postgres -d stocks -c "SELECT COUNT(*) as total_records, COUNT(DISTINCT symbol) as symbols, COUNT(DISTINCT item_name) as item_types FROM quarterly_cash_flow;" 2>/dev/null

echo ""
echo "5. Available ITEM_NAMES in quarterly_cash_flow:"
psql -h localhost -U postgres -d stocks -c "SELECT item_name, COUNT(*) as qty FROM quarterly_cash_flow GROUP BY item_name ORDER BY qty DESC LIMIT 10;" 2>/dev/null

echo ""
echo "6. QUARTERLY_BALANCE_SHEET TABLE:"
psql -h localhost -U postgres -d stocks -c "SELECT COUNT(*) as total_records, COUNT(DISTINCT symbol) as symbols, COUNT(DISTINCT item_name) as item_types FROM quarterly_balance_sheet;" 2>/dev/null

echo ""
echo "======================================================================"
echo "SUMMARY: This shows what raw data is available"
echo "If quarterly_* tables are empty: metrics will be NULL (NO FALLBACK!)"
echo "======================================================================"

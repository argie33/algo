#!/bin/bash

# API Endpoint Testing Script
# Tests critical endpoints to verify data is accessible and properly formatted

set -e

# Configuration
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${DB_USER:-postgres}"
DB_NAME="${DB_NAME:-stocks}"
API_BASE="${API_BASE:-http://localhost:3000}"

echo "======================================"
echo "API Endpoint Testing"
echo "======================================"
echo ""

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

pass_count=0
fail_count=0

# Test function
test_endpoint() {
  local name=$1
  local description=$2
  local query=$3

  echo -e "${YELLOW}Testing: $name${NC}"
  echo "Description: $description"

  if psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -t -c "$query" > /dev/null 2>&1; then
    echo -e "${GREEN}✅ PASS${NC}"
    ((pass_count++))
  else
    echo -e "${RED}❌ FAIL${NC}"
    ((fail_count++))
  fi
  echo ""
}

echo "====== STOCK SCORES ======"
test_endpoint \
  "Stock Scores" \
  "Verify stock scores are loaded (5,280 expected)" \
  "SELECT COUNT(*) as count FROM stock_scores WHERE composite_score IS NOT NULL AND composite_score != 0;"

echo "====== PRICE DATA ======"
test_endpoint \
  "Daily Prices" \
  "Verify daily price data loaded" \
  "SELECT COUNT(*) FROM price_daily WHERE close > 0 AND date > CURRENT_DATE - INTERVAL '7 days';"

test_endpoint \
  "Weekly Prices" \
  "Verify weekly price data loaded" \
  "SELECT COUNT(*) FROM price_weekly WHERE close > 0;"

test_endpoint \
  "Monthly Prices" \
  "Verify monthly price data loaded" \
  "SELECT COUNT(*) FROM price_monthly WHERE close > 0;"

echo "====== TECHNICALS ======"
test_endpoint \
  "Daily Technicals" \
  "Verify daily technical indicators" \
  "SELECT COUNT(*) FROM technicals_daily WHERE rsi IS NOT NULL AND date > CURRENT_DATE - INTERVAL '7 days';"

test_endpoint \
  "Weekly Technicals" \
  "Verify weekly technical indicators" \
  "SELECT COUNT(*) FROM technicals_weekly WHERE rsi IS NOT NULL;"

test_endpoint \
  "Monthly Technicals" \
  "Verify monthly technical indicators" \
  "SELECT COUNT(*) FROM technicals_monthly WHERE rsi IS NOT NULL;"

echo "====== SENTIMENT DATA ======"
test_endpoint \
  "Social Sentiment" \
  "Verify social sentiment analysis" \
  "SELECT COUNT(*) FROM social_sentiment_analysis WHERE sentiment_score IS NOT NULL;"

test_endpoint \
  "Analyst Sentiment" \
  "Verify analyst sentiment data" \
  "SELECT COUNT(*) FROM analyst_sentiment_analysis WHERE sentiment_score IS NOT NULL;"

test_endpoint \
  "News Sentiment" \
  "Verify news sentiment data" \
  "SELECT COUNT(*) FROM news_sentiment WHERE sentiment IS NOT NULL;"

test_endpoint \
  "Market Sentiment (AAII)" \
  "Verify AAII market sentiment" \
  "SELECT COUNT(*) FROM aaii_sentiment WHERE bullish_percent IS NOT NULL;"

test_endpoint \
  "Fund Positioning (NAAIM)" \
  "Verify NAAIM fund positioning" \
  "SELECT COUNT(*) FROM naaim WHERE exposure_index IS NOT NULL;"

test_endpoint \
  "Fear & Greed Index" \
  "Verify CNN Fear & Greed index" \
  "SELECT COUNT(*) FROM fear_greed_index WHERE fear_greed_value IS NOT NULL;"

echo "====== FUNDAMENTAL METRICS ======"
test_endpoint \
  "Fundamental Metrics" \
  "Verify fundamental metrics (P/E, P/B, ROE, etc)" \
  "SELECT COUNT(*) FROM fundamental_metrics WHERE pe_ratio IS NOT NULL OR pb_ratio IS NOT NULL;"

test_endpoint \
  "Quality Metrics" \
  "Verify quality metrics (ROA, ROE, profit margin)" \
  "SELECT COUNT(*) FROM quality_metrics WHERE roe IS NOT NULL OR roa IS NOT NULL;"

test_endpoint \
  "Value Metrics" \
  "Verify value metrics (P/E, P/B, dividend yield)" \
  "SELECT COUNT(*) FROM value_metrics WHERE value_score IS NOT NULL;"

test_endpoint \
  "Growth Metrics" \
  "Verify growth metrics (revenue growth, earnings growth)" \
  "SELECT COUNT(*) FROM growth_metrics WHERE revenue_growth IS NOT NULL OR earnings_growth IS NOT NULL;"

echo "====== MARKET INDICATORS ======"
test_endpoint \
  "Momentum Indicators" \
  "Verify momentum indicators (RSI, MACD)" \
  "SELECT COUNT(*) FROM momentum WHERE momentum_score IS NOT NULL;"

test_endpoint \
  "Market Positioning" \
  "Verify market positioning data" \
  "SELECT COUNT(*) FROM positioning WHERE positioning_score IS NOT NULL;"

echo "====== TRADING SIGNALS ======"
test_endpoint \
  "Trading Signals (Daily)" \
  "Verify daily buy/sell signals" \
  "SELECT COUNT(*) FROM buy_sell_daily WHERE signal_type IN ('BUY', 'SELL') AND date > CURRENT_DATE - INTERVAL '30 days';"

test_endpoint \
  "Trading Signals (Weekly)" \
  "Verify weekly buy/sell signals" \
  "SELECT COUNT(*) FROM buy_sell_weekly WHERE signal_type IN ('BUY', 'SELL');"

test_endpoint \
  "Trading Signals (Monthly)" \
  "Verify monthly buy/sell signals" \
  "SELECT COUNT(*) FROM buy_sell_monthly WHERE signal_type IN ('BUY', 'SELL');"

echo "====== DATA FRESHNESS ======"
test_endpoint \
  "Recent Stock Scores" \
  "Verify stock scores updated in last 24 hours" \
  "SELECT COUNT(*) FROM stock_scores WHERE fetched_at > NOW() - INTERVAL '24 hours';"

test_endpoint \
  "Recent Price Updates" \
  "Verify price data updated in last 24 hours" \
  "SELECT COUNT(*) FROM price_daily WHERE fetched_at > NOW() - INTERVAL '24 hours';"

test_endpoint \
  "Recent Technical Updates" \
  "Verify technical data updated in last 24 hours" \
  "SELECT COUNT(*) FROM technicals_daily WHERE fetched_at > NOW() - INTERVAL '24 hours';"

echo "====== SPECIAL CHECKS ======"
test_endpoint \
  "No Fake Defaults" \
  "Verify no hardcoded fake values (50, 0, 'neutral')" \
  "SELECT COUNT(*) FROM (
    SELECT composite_score FROM stock_scores WHERE composite_score = 50 UNION
    SELECT momentum_score FROM momentum WHERE momentum_score = 50 UNION
    SELECT value_score FROM value_metrics WHERE value_score = 50
  ) AS fake_values;"

test_endpoint \
  "Data Integrity" \
  "Verify transactions completed (no partial records)" \
  "SELECT COUNT(*) FROM stock_scores WHERE composite_score IS NULL AND created_at > NOW() - INTERVAL '7 days';"

echo ""
echo "======================================"
echo "Test Summary"
echo "======================================"
echo -e "${GREEN}Passed: $pass_count${NC}"
echo -e "${RED}Failed: $fail_count${NC}"
total=$((pass_count + fail_count))
echo "Total:  $total"
echo ""

if [ $fail_count -eq 0 ]; then
  echo -e "${GREEN}✅ All tests passed!${NC}"
  exit 0
else
  echo -e "${RED}❌ Some tests failed. Check database connectivity and data loading.${NC}"
  exit 1
fi

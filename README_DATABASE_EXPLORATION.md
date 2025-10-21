# Database Exploration Complete - Summary Report

## Overview
Complete database inventory created for the Stocks Algorithm platform. All tables, schemas, and data relationships documented.

## Files Created

### 1. DATABASE_INVENTORY.md (22KB)
**Full reference guide with complete table definitions**
- All 50+ tables documented with column types
- Primary keys and indexes listed
- Data loading pipeline documented
- Detailed query examples for each table
- Performance optimization tips

### 2. DATABASE_QUICK_REFERENCE.md
**Quick lookup guide for common operations**
- Most important 5 tables (stock_scores, price_daily, fear_greed_index, aaii_sentiment, naaim)
- Common query patterns with SQL examples
- Data freshness status
- Connection methods (local & AWS)
- Troubleshooting guide

### 3. DATABASE_SCHEMA_VISUAL.md
**Visual architecture and relationships**
- ASCII diagram of table relationships
- Data flow from loaders to API to UI
- Score calculation hierarchy
- Index strategy and performance expectations
- Daily update lifecycle

---

## Key Findings

### Critical Tables (Start Here)

1. **stock_scores** - The main scoring table
   - Primary data source for `/api/scores` endpoint
   - Daily updates, 50+ fields including composite/component scores
   - Contains JSONB inputs for detailed analysis
   - ~5000 stocks with 0-100 normalized scores

2. **price_daily** - Daily OHLCV data
   - Full historical data from yfinance
   - Indexed on (symbol, date) for fast queries
   - 90+ days typically available per stock

3. **Market Sentiment Tables**
   - `fear_greed_index` - CNN Fear & Greed (daily, 0-100 scale)
   - `aaii_sentiment` - Weekly investor sentiment (bullish/neutral/bearish %)
   - `naaim` - Daily professional exposure (0-100, 50=neutral)

4. **Metric Tables** (all have symbol + date as composite PK)
   - `quality_metrics` - ROE, margins, debt ratios
   - `growth_metrics` - Revenue/EPS CAGR, FCF growth
   - `momentum_metrics` - 12m/6m/3m momentum, price vs SMA
   - `risk_metrics` - Volatility, beta, max drawdown
   - `positioning_metrics` - Institutional/insider ownership, short interest

5. **Earnings History** - 4000+ quarterly earnings records
   - Actual vs estimate EPS data
   - Used to calculate PE ratios and earnings growth scores

### Database Architecture

**Type**: PostgreSQL (AWS RDS in production)

**Connection Methods**:
- Local: Environment variables (DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME)
- Production: AWS Secrets Manager (DB_SECRET_ARN)

**Schema Overview**:
- ~50 tables across multiple domains
- Reference tables (company_profile, stock_symbols)
- Daily data tables (price_daily, technical_data_daily)
- Metric tables (quality, growth, momentum, risk, positioning)
- Scoring table (stock_scores) - calculated daily from metrics
- Sentiment tables (fear_greed_index, aaii_sentiment, naaim)
- Supporting tables (earnings, news, analyst ratings)

### Data Pipeline

```
Data Sources (yfinance, FRED, CNN, APIs)
    ↓
Python Loaders (15+ scripts in /home/stocks/algo/)
    ↓
PostgreSQL Database
    ↓
Node.js Lambda Routes (/api/scores, /api/market/*)
    ↓
React Frontend UI
```

### Score Calculation
```
Individual Metrics → Normalized Scores (0-100)
  ├─ quality_metrics → quality_score
  ├─ growth_metrics → growth_score
  ├─ momentum_metrics → momentum_score
  ├─ positioning_metrics → positioning_score
  ├─ risk_metrics → stability_score
  └─ technical_data_daily → rsi, macd, sma

    ↓
    
Composite Score = Weighted Average
  ├─ momentum_score (25%)
  ├─ value_score (20%)
  ├─ quality_score (20%)
  ├─ growth_score (20%)
  ├─ positioning_score (10%)
  └─ sentiment_score (5%)
```

---

## Important Implementation Details

### Symbol Field Inconsistency
- `stock_scores`, `price_daily`, `technical_data_daily` → use `symbol`
- `company_profile`, `key_metrics`, `market_data` → use `ticker`
- When joining: `ON stock_scores.symbol = company_profile.ticker`

### Data Types
- Scores use `DECIMAL(5,2)` for exact values (0-100)
- Metrics use `DOUBLE PRECISION` for percentages/ratios
- Prices use `DOUBLE PRECISION` for calculations

### Primary Keys
- Most metric tables: composite `(symbol, date)`
- Sentiment tables: `date` only
- Stock scores: `symbol` only (latest snapshot)

### Indexes for Performance
- `price_daily`: (symbol, date) UNIQUE
- `stock_scores`: composite_score DESC, last_updated, score_date
- All metric tables: symbol index, date DESC index

---

## Data Update Frequency

| Table | Frequency | Source |
|-------|-----------|--------|
| price_daily | Daily (end of market) | yfinance |
| stock_scores | Daily | Calculated |
| technical_data_daily | Daily | Calculated |
| fear_greed_index | Daily | CNN (web scrape) |
| naaim | Daily | NAAIM API |
| aaii_sentiment | Weekly | AAII |
| quality_metrics | Weekly | Financial APIs |
| growth_metrics | Weekly | Financial APIs |
| earnings_history | Daily/Weekly | Financial APIs |

**Monitor freshness**: `SELECT script_name, last_run FROM last_updated ORDER BY last_run DESC`

---

## Common Query Patterns

### Get Top Stocks by Score
```sql
SELECT symbol, composite_score, momentum_score, value_score, 
       quality_score, growth_score, current_price
FROM stock_scores
ORDER BY composite_score DESC
LIMIT 50;
```

### Get Latest Price Data
```sql
SELECT DISTINCT ON (symbol)
  symbol, date, close, volume
FROM price_daily
WHERE date >= CURRENT_DATE - INTERVAL '5 days'
ORDER BY symbol, date DESC;
```

### Get Fundamentals with Scores
```sql
SELECT 
  ss.symbol, ss.composite_score, ss.current_price,
  cp.short_name, cp.sector,
  km.trailing_pe, km.forward_pe, km.dividend_yield
FROM stock_scores ss
LEFT JOIN company_profile cp ON ss.symbol = cp.ticker
LEFT JOIN key_metrics km ON ss.symbol = km.ticker
ORDER BY ss.composite_score DESC
LIMIT 50;
```

### Get Market Sentiment
```sql
SELECT 
  date, index_value, rating
FROM fear_greed_index
WHERE date >= CURRENT_DATE - INTERVAL '90 days'
ORDER BY date DESC;
```

---

## Performance Tips

1. Always filter by date: `WHERE date >= CURRENT_DATE - INTERVAL '90 days'`
2. Use LIMIT to avoid loading all 5000+ stocks
3. Specify columns, don't use SELECT *
4. Use DISTINCT ON for latest record per group
5. Avoid JOINing >3 large tables
6. Pre-calculate in stock_scores rather than in queries

---

## Troubleshooting Guide

### No Results from Query?
- Check date isn't in future: `WHERE date <= CURRENT_DATE`
- Verify symbol spelling (case-sensitive)
- Check if table exists: `SELECT * FROM information_schema.tables`
- Confirm data exists: `SELECT COUNT(*) FROM price_daily WHERE symbol = 'AAPL'`

### JOINs Too Slow?
- Filter by date first
- Limit to specific symbols
- Check EXPLAIN ANALYZE for query plan
- Avoid JOINing >2-3 large tables

### NULL Values in Results?
- Use COALESCE(): `COALESCE(value, 0)`
- Check if upstream table has data
- Verify column name spelling

### JSONB Returns NULL?
- Check key spelling in JSONB: `value_inputs->>'pe_ratio'`
- Cast to correct type: `::NUMERIC`
- Use COALESCE() for missing keys
- Verify JSONB column is populated

---

## File Locations

- **This exploration**: `/home/stocks/algo/DATABASE_EXPLORATION.md`
- **Full inventory**: `/home/stocks/algo/DATABASE_INVENTORY.md`
- **Quick reference**: `/home/stocks/algo/DATABASE_QUICK_REFERENCE.md`
- **Visual guide**: `/home/stocks/algo/DATABASE_SCHEMA_VISUAL.md`
- **Data loaders**: `/home/stocks/algo/load*.py`
- **API routes**: `/home/stocks/algo/webapp/lambda/routes/`
- **Database utils**: `/home/stocks/algo/webapp/lambda/utils/database.js`
- **Test fixtures**: `/home/stocks/algo/webapp/lambda/tests/fixtures/test-data.sql`

---

## Next Steps

1. **For API Development**: Start with `/api/scores` endpoint, use stock_scores table
2. **For Data Loading**: Check last_updated table before reloading data
3. **For Analysis**: Begin with stock_scores, then drill into specific metric tables
4. **For Debugging**: Check individual metric tables for NULL values
5. **For Performance**: Always filter by date and symbol when possible

---

## Database Connection Example

```javascript
// Node.js
const { query } = require('../utils/database');

// Get top stocks
const result = await query(`
  SELECT symbol, composite_score, momentum_score, value_score
  FROM stock_scores
  WHERE composite_score IS NOT NULL
  ORDER BY composite_score DESC
  LIMIT 50
`);

console.log(result.rows);
```

```python
# Python
import psycopg2
import json
import os

# Get config
db_config = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 5432)),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', 'password'),
    'dbname': os.getenv('DB_NAME', 'stocks')
}

# Connect and query
conn = psycopg2.connect(**db_config)
cur = conn.cursor()
cur.execute("SELECT symbol, composite_score FROM stock_scores ORDER BY composite_score DESC LIMIT 50")
results = cur.fetchall()
cur.close()
conn.close()
```

---

## Summary

Database exploration complete with comprehensive documentation:
- ✅ All 50+ tables identified and documented
- ✅ Schema structure and relationships mapped
- ✅ Data loading pipeline documented
- ✅ Common query patterns provided
- ✅ Performance optimization tips included
- ✅ Troubleshooting guide available
- ✅ Visual architecture diagrams created

Ready to build working queries and API endpoints!


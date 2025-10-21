# Database Documentation Index

Complete database exploration and documentation for the Stocks Algorithm platform.

## Quick Navigation

### For First-Time Users
Start here: **DATABASE_QUICK_REFERENCE.md**
- 5 most important tables
- Connection setup
- 5 essential query patterns
- Common troubleshooting

### For API Developers
Reference: **DATABASE_SCHEMA_VISUAL.md**
- Table relationships diagram
- Data flow architecture
- Score calculation hierarchy
- Index strategy

### For Detailed Analysis
Full Guide: **DATABASE_INVENTORY.md**
- All 50+ tables documented
- Complete column definitions
- All 15+ data loaders listed
- Comprehensive query examples

### For Overview
Summary: **README_DATABASE_EXPLORATION.md**
- Key findings summary
- Implementation details
- Data pipeline overview
- Troubleshooting guide

---

## Documents at a Glance

| Document | Size | Purpose | Audience |
|----------|------|---------|----------|
| **DATABASE_QUICK_REFERENCE.md** | 8KB | Quick lookup, common patterns | Developers, Engineers |
| **DATABASE_SCHEMA_VISUAL.md** | 26KB | Architecture, relationships, flow | Architects, Developers |
| **DATABASE_INVENTORY.md** | 22KB | Complete reference, all tables | Reference, Troubleshooting |
| **README_DATABASE_EXPLORATION.md** | 9KB | Summary, key findings | Project overview |

---

## The 5 Critical Tables

### 1. stock_scores
**Main scoring table - Primary API data source**
- Primary Key: `symbol`
- Daily updates with 50+ fields
- Scores: 0-100 normalized scale
- Contains JSONB with detailed components

```sql
SELECT symbol, composite_score, momentum_score, value_score, 
       quality_score, growth_score, current_price
FROM stock_scores
ORDER BY composite_score DESC
LIMIT 50;
```

### 2. price_daily
**Daily OHLCV data**
- Composite Key: `(symbol, date)` UNIQUE
- Full historical from yfinance
- 90+ days typically available
- Indexed for fast queries

```sql
SELECT symbol, date, open, high, low, close, volume
FROM price_daily
WHERE symbol = 'AAPL' AND date >= CURRENT_DATE - INTERVAL '90 days'
ORDER BY date DESC;
```

### 3. fear_greed_index
**Market sentiment (CNN daily)**
- Primary Key: `date`
- Range: 0-100 scale
- Ratings: Extreme Fear → Extreme Greed
- Daily web scrape

```sql
SELECT date, index_value, rating
FROM fear_greed_index
WHERE date >= CURRENT_DATE - INTERVAL '30 days'
ORDER BY date DESC;
```

### 4. aaii_sentiment
**Weekly investor sentiment**
- Primary Key: `date`
- Bullish/Neutral/Bearish percentages
- Professional association (AAII)
- Updates weekly

```sql
SELECT date, bullish_pct, neutral_pct, bearish_pct
FROM aaii_sentiment
WHERE date >= CURRENT_DATE - INTERVAL '90 days'
ORDER BY date DESC;
```

### 5. naaim
**Professional investor exposure**
- Primary Key: `date`
- 0-100 scale (50 = neutral)
- Daily from NAAIM API
- For positioning analysis

```sql
SELECT date, naaim_exposure
FROM naaim
WHERE date >= CURRENT_DATE - INTERVAL '30 days'
ORDER BY date DESC;
```

---

## Database Connection

### Local Development
```bash
export DB_HOST=localhost
export DB_PORT=5432
export DB_USER=postgres
export DB_PASSWORD=password
export DB_NAME=stocks
```

### Production (AWS)
```bash
export DB_SECRET_ARN=arn:aws:secretsmanager:region:account:secret:name
```

---

## Key Concepts

### Symbol Field Names
- Data tables use: `symbol`
- Company tables use: `ticker`
- Joining: `ON stocks.symbol = company.ticker`

### Score Normalization
- All scores: 0-100 scale
- Composite = weighted average
- Weights: momentum(25%), value(20%), quality(20%), growth(20%), positioning(10%)

### Data Types
- Scores: `DECIMAL(5,2)` (exact)
- Percentages: `DOUBLE PRECISION` (calculated)
- Dates: `DATE` (ISO format YYYY-MM-DD)

### Update Frequency
- Daily: prices, technical, fear_greed, naaim, earnings
- Weekly: quality, growth, aaii_sentiment
- On-demand: company_profile, key_metrics

---

## Query Performance

### Fast (< 100ms)
- Single symbol lookup
- Recent data (30 days)
- Indexed columns (symbol, date)

### Medium (100ms - 1s)
- Top 50 stocks
- Sector aggregations
- 90-day history

### Slow (> 1s)
- Full historical backtest
- Multi-table JOINs (>3 tables)
- Complex window functions

### Optimization Rules
1. Always filter by date
2. Use LIMIT to avoid full scans
3. Specify columns (not SELECT *)
4. Join ≤3 large tables
5. Use indexes on (symbol, date)

---

## Common Tasks

### Get Stock Rankings
```sql
SELECT symbol, composite_score, momentum_score, 
       value_score, quality_score, growth_score
FROM stock_scores
ORDER BY composite_score DESC
LIMIT 50;
```

### Get Company Fundamentals
```sql
SELECT 
  ss.symbol, cp.short_name, cp.sector,
  ss.composite_score, km.trailing_pe, km.dividend_yield
FROM stock_scores ss
LEFT JOIN company_profile cp ON ss.symbol = cp.ticker
LEFT JOIN key_metrics km ON ss.symbol = km.ticker
ORDER BY ss.composite_score DESC
LIMIT 50;
```

### Get Market Sentiment Trend
```sql
SELECT 
  date, 
  index_value as fear_greed,
  CASE 
    WHEN index_value < 30 THEN 'Fear'
    WHEN index_value < 50 THEN 'Neutral'
    ELSE 'Greed'
  END as sentiment
FROM fear_greed_index
WHERE date >= CURRENT_DATE - INTERVAL '90 days'
ORDER BY date DESC;
```

### Get Technical Analysis
```sql
SELECT symbol, date, rsi, macd, sma_20, sma_50, sma_200
FROM technical_data_daily
WHERE symbol = 'AAPL'
ORDER BY date DESC
LIMIT 30;
```

### Get Earnings History
```sql
SELECT symbol, quarter, eps_actual, eps_estimate, 
       ROUND(eps_surprise, 2) as surprise_pct
FROM earnings_history
WHERE symbol = 'AAPL'
AND quarter >= CURRENT_DATE - INTERVAL '24 months'
ORDER BY quarter DESC;
```

---

## Troubleshooting Checklist

| Issue | Solutions |
|-------|-----------|
| No results | Check date range, symbol spelling, table existence |
| Slow query | Add date filter, reduce symbols, check indexes |
| NULL values | Use COALESCE(), verify upstream data |
| JSONB NULL | Check key spelling, cast type, verify column populated |
| Wrong data | Verify join condition, check symbol vs ticker |

---

## Related Files

### Data Loaders
- Location: `/home/stocks/algo/load*.py`
- 15+ Python scripts that populate the database
- Each updates a `last_updated` table entry

### API Routes
- Location: `/home/stocks/algo/webapp/lambda/routes/`
- Node.js Lambda functions
- Main endpoints: scores, market, sectors, signals, dashboard

### Database Utilities
- Location: `/home/stocks/algo/webapp/lambda/utils/database.js`
- Connection pool management
- Query execution wrapper

### Test Fixtures
- Location: `/home/stocks/algo/webapp/lambda/tests/fixtures/test-data.sql`
- Sample data for local testing
- 5 stocks with 30 days of data

---

## Data Flow

```
Sources (yfinance, FRED, CNN, APIs)
    ↓
Python Loaders (15+ scripts)
    ↓
PostgreSQL Database (50+ tables)
    ↓
Node.js Routes (/api/scores, /api/market/*, etc)
    ↓
React UI (Stock Screener, Market Overview, Sectors)
```

---

## Support & References

### PostgreSQL Tips
- Date arithmetic: `CURRENT_DATE - INTERVAL '30 days'`
- Window functions: `LAG(), ROW_NUMBER(), RANK()`
- JSON extraction: `column->>'key'` then `::TYPE`
- Common patterns: `DISTINCT ON`, `GROUP BY`, `HAVING`

### Performance Analysis
- Explain plan: `EXPLAIN ANALYZE SELECT ...`
- Index usage: `\d+ table_name`
- Table size: `pg_total_relation_size('table_name')`
- Row count: `SELECT COUNT(*) FROM table_name`

### Useful Queries
```sql
-- Check data freshness
SELECT script_name, last_run FROM last_updated ORDER BY last_run DESC;

-- Count records by table
SELECT 'stock_scores' as table_name, COUNT(*) FROM stock_scores
UNION ALL
SELECT 'price_daily', COUNT(*) FROM price_daily
UNION ALL
SELECT 'fear_greed_index', COUNT(*) FROM fear_greed_index;

-- Find missing symbols
SELECT DISTINCT symbol FROM price_daily 
WHERE symbol NOT IN (SELECT symbol FROM stock_scores);

-- Check date range
SELECT MIN(date) as earliest, MAX(date) as latest FROM price_daily;
```

---

## Documentation Summary

Complete database documentation created with 4 complementary guides:

✅ **DATABASE_QUICK_REFERENCE.md** - Start here for quick lookups  
✅ **DATABASE_SCHEMA_VISUAL.md** - Visual architecture and relationships  
✅ **DATABASE_INVENTORY.md** - Complete reference documentation  
✅ **README_DATABASE_EXPLORATION.md** - Executive summary  

All files located in: `/home/stocks/algo/`

Ready to build robust database queries and API endpoints!


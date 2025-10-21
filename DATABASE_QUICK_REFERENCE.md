# Database Quick Reference Guide

## Essential Facts

### Database Type
- **PostgreSQL** (production AWS RDS)
- **Local Development**: `localhost:5432`

### Connection Methods
```bash
# Local (environment variables)
export DB_HOST=localhost
export DB_PORT=5432
export DB_USER=postgres
export DB_PASSWORD=password
export DB_NAME=stocks

# Production (AWS Secrets Manager)
export DB_SECRET_ARN=arn:aws:secretsmanager:...
```

---

## Most Important Tables

### 1. stock_scores
**The main scoring table - START HERE for stock analysis**
```sql
SELECT symbol, composite_score, momentum_score, value_score, 
       quality_score, growth_score, current_price
FROM stock_scores
ORDER BY composite_score DESC
LIMIT 50;
```
- Primary source for API `/api/scores` endpoint
- Daily updates from other metric tables
- Scores are 0-100 scale
- Contains JSONB columns with detailed component data

### 2. price_daily
**Daily price data for stocks**
```sql
SELECT symbol, date, open, high, low, close, adj_close, volume
FROM price_daily
WHERE symbol = 'AAPL'
ORDER BY date DESC
LIMIT 30;
```
- Full historical data via yfinance
- Updates daily via `loadpricedaily.py`
- Indexed on (symbol, date) for fast queries

### 3. fear_greed_index
**Market sentiment (0-100)**
```sql
SELECT date, index_value, rating
FROM fear_greed_index
ORDER BY date DESC LIMIT 10;
-- Ratings: "Extreme Fear", "Fear", "Neutral", "Greed", "Extreme Greed"
```

### 4. aaii_sentiment
**Weekly AAII investor sentiment**
```sql
SELECT date, bullish_pct, neutral_pct, bearish_pct
FROM aaii_sentiment
ORDER BY date DESC LIMIT 4;
```

### 5. naaim
**Daily professional investor exposure**
```sql
SELECT date, naaim_exposure
FROM naaim
WHERE date >= CURRENT_DATE - INTERVAL '30 days'
ORDER BY date DESC;
-- 0-100 scale: 0=net short, 50=neutral, 100=net long
```

---

## Key Metric Tables (All have symbol + date primary key)

### Company Quality
- `quality_metrics` - ROE, margins, debt ratio, etc.
- `growth_metrics` - Revenue/EPS CAGR, FCF growth, etc.
- `momentum_metrics` - Relative/absolute momentum
- `risk_metrics` - Volatility, beta, max drawdown

### Positioning
- `positioning_metrics` - Institutional/insider ownership, short interest

### Earnings
- `earnings_history` - Quarterly EPS actual vs estimate (4000+ records)

---

## Common Query Patterns

### Get Latest Scores for Top Stocks
```sql
SELECT symbol, composite_score, momentum_score, value_score, 
       quality_score, growth_score, current_price, last_updated
FROM stock_scores
WHERE composite_score IS NOT NULL
ORDER BY composite_score DESC
LIMIT 50;
```

### Compare Stock to Sector/Market Benchmarks
```sql
SELECT 
  ss.symbol, ss.value_score, ss.quality_score,
  -- Extract from JSONB
  (ss.value_inputs->>'pe_ratio')::NUMERIC as stock_pe,
  (ss.value_inputs->>'pb_ratio')::NUMERIC as stock_pb
FROM stock_scores ss
WHERE ss.symbol IN ('AAPL', 'MSFT', 'GOOGL');
```

### Get Price Changes
```sql
SELECT 
  symbol, date, close,
  LAG(close) OVER (PARTITION BY symbol ORDER BY date) as prev_close,
  ROUND(((close - LAG(close) OVER (PARTITION BY symbol ORDER BY date)) / 
         LAG(close) OVER (PARTITION BY symbol ORDER BY date) * 100)::NUMERIC, 2) as pct_change
FROM price_daily
WHERE date >= CURRENT_DATE - INTERVAL '5 days'
ORDER BY symbol, date DESC;
```

### Get Technical Indicators
```sql
SELECT symbol, date, rsi, macd, sma_20, sma_50, sma_200
FROM technical_data_daily
WHERE symbol = 'AAPL'
ORDER BY date DESC
LIMIT 20;
```

### Get Fundamentals
```sql
SELECT 
  cp.ticker, cp.short_name, cp.sector,
  km.trailing_pe, km.forward_pe, km.price_to_book, km.dividend_yield,
  md.market_cap
FROM company_profile cp
LEFT JOIN key_metrics km ON cp.ticker = km.ticker
LEFT JOIN market_data md ON cp.ticker = md.ticker
WHERE cp.ticker = 'AAPL';
```

### Get Market Sentiment Trend
```sql
SELECT 
  date,
  index_value as fear_greed,
  (SELECT ROUND(AVG(bullish_pct)::NUMERIC, 1) 
   FROM aaii_sentiment 
   WHERE date BETWEEN fg.date - INTERVAL '30 days' AND fg.date) as aaii_bullish_avg,
  (SELECT naaim_exposure 
   FROM naaim 
   WHERE date <= fg.date 
   ORDER BY date DESC LIMIT 1) as latest_naaim
FROM fear_greed_index fg
WHERE date >= CURRENT_DATE - INTERVAL '90 days'
ORDER BY date DESC;
```

---

## Data Freshness

| Table | Update Frequency | Last Check |
|-------|------------------|------------|
| price_daily | Daily (end of market) | via `last_updated` table |
| stock_scores | Daily | via `last_updated` table |
| fear_greed_index | Daily | via `last_updated` table |
| aaii_sentiment | Weekly | via `last_updated` table |
| naaim | Daily | via `last_updated` table |
| technical_data_daily | Daily | via `last_updated` table |
| quality_metrics | Weekly | via `last_updated` table |
| earnings_history | Daily/Weekly | via `last_updated` table |

**Check data freshness:**
```sql
SELECT script_name, last_run
FROM last_updated
ORDER BY last_run DESC;
```

---

## Common Issues & Solutions

### Issue: Query returns no results
**Solutions:**
1. Check date is not in future: `WHERE date <= CURRENT_DATE`
2. Check if table exists: `SELECT * FROM information_schema.tables WHERE table_name = 'xxx'`
3. Check symbol spelling (case-sensitive in some contexts)
4. Verify data exists for symbol: `SELECT COUNT(*) FROM price_daily WHERE symbol = 'AAPL'`

### Issue: JOINs are slow
**Solutions:**
1. Filter by date first: `WHERE date >= CURRENT_DATE - INTERVAL '30 days'`
2. Limit to few symbols: `WHERE symbol IN ('AAPL', 'MSFT')`
3. Avoid JOINing >3 large tables
4. Use `EXPLAIN ANALYZE` to check query plan

### Issue: NULL values in results
**Solutions:**
1. Use `COALESCE()`: `COALESCE(value, 0) as default_value`
2. Use `WHERE column IS NOT NULL`
3. Check if data exists in upstream tables

### Issue: JSONB extraction returns NULL
**Solutions:**
1. Verify JSONB key spelling: `value_inputs->>'pe_ratio'`
2. Cast to correct type: `(value_inputs->>'pe_ratio')::NUMERIC`
3. Use `COALESCE()` for missing keys
4. Check if JSONB column populated: `SELECT value_inputs FROM stock_scores LIMIT 1`

---

## Performance Tips

1. **Always use WHERE clause**: Filter by date or symbol
2. **Use LIMIT**: Don't select all 5000+ stocks unnecessarily
3. **Use indexes**: (symbol, date) indexes on metric tables
4. **Avoid SELECT ***: Specify columns needed
5. **Use DISTINCT ON** for latest record per group
6. **Pre-calculate** in stock_scores rather than in queries

---

## Useful Commands

### Check table size
```sql
SELECT pg_size_pretty(pg_total_relation_size('price_daily'));
```

### Check row count
```sql
SELECT COUNT(*) FROM price_daily;
```

### Check index effectiveness
```sql
SELECT schemaname, tablename, indexname 
FROM pg_indexes 
WHERE tablename = 'price_daily';
```

### Check table definition
```sql
\d price_daily
-- or
SELECT column_name, data_type FROM information_schema.columns 
WHERE table_name = 'price_daily';
```

### Monitor current connections
```sql
SELECT pid, usename, query FROM pg_stat_activity WHERE query != '';
```

---

## API Endpoints Using These Tables

- `/api/scores` - Uses `stock_scores` table
- `/api/market/data` - Uses `price_daily`, `market_data`, `company_profile`
- `/api/market/fear-greed` - Uses `fear_greed_index`
- `/api/market/sentiment/history` - Uses `aaii_sentiment`, `naaim`, sentiment tables
- `/api/market/breadth` - Uses `price_daily` for calculations
- `/api/sectors` - Uses `company_profile`, `stock_scores`

---

## File Locations

- **Loaders**: `/home/stocks/algo/load*.py`
- **Lambda Routes**: `/home/stocks/algo/webapp/lambda/routes/`
- **Test Fixtures**: `/home/stocks/algo/webapp/lambda/tests/fixtures/`
- **Database Utils**: `/home/stocks/algo/webapp/lambda/utils/database.js`

---

## Next Steps

1. **For API Development**: Use `/api/scores` endpoint as primary data source
2. **For Data Loading**: Check `last_updated` table before reloading
3. **For Analysis**: Start with `stock_scores` table, then drill into specific metrics
4. **For Debugging**: Check individual metric tables (quality, growth, etc.) for NULL values
5. **For Performance**: Always filter by date and symbol when possible


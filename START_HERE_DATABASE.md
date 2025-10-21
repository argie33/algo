# START HERE - Database Documentation

This folder contains comprehensive documentation of the database for the Stocks Algorithm platform.

## Quick Start (2 minutes)

1. **Read this file** (you are here)
2. **Open**: `DATABASE_DOCS_INDEX.md` - Navigation guide
3. **Pick your path** below based on your needs

---

## Your Path

### I want to query the database RIGHT NOW
**→ Go to**: `DATABASE_QUICK_REFERENCE.md`
- 5 critical tables with examples
- Copy-paste query patterns
- Troubleshooting tips

### I'm building an API endpoint
**→ Go to**: `DATABASE_SCHEMA_VISUAL.md`
- Architecture diagrams
- Table relationships
- Data flow from database to API

### I need the complete reference
**→ Go to**: `DATABASE_INVENTORY.md`
- All 50+ tables documented
- Every column listed
- Performance optimization

### I'm new to this project
**→ Go to**: `README_DATABASE_EXPLORATION.md`
- Project overview
- Key findings
- Data pipeline explanation

---

## The 5 Most Important Tables

```sql
-- 1. Stock Scores (START HERE)
SELECT symbol, composite_score, momentum_score FROM stock_scores LIMIT 10;

-- 2. Daily Prices
SELECT symbol, date, close FROM price_daily WHERE symbol = 'AAPL' LIMIT 10;

-- 3. Market Fear/Greed
SELECT date, index_value, rating FROM fear_greed_index LIMIT 10;

-- 4. Investor Sentiment
SELECT date, bullish_pct FROM aaii_sentiment LIMIT 10;

-- 5. Professional Exposure
SELECT date, naaim_exposure FROM naaim LIMIT 10;
```

---

## Key Facts

- **Type**: PostgreSQL database
- **Purpose**: Stock analysis and scoring
- **Tables**: 50+ (prices, scores, sentiment, fundamentals)
- **Update**: Daily for most tables
- **API Endpoint**: `/api/scores` (uses stock_scores table)

---

## Connection Setup

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
export DB_SECRET_ARN=arn:aws:secretsmanager:...
```

---

## One Critical Thing to Remember

**Symbol field names are inconsistent!**
- Use `symbol` for: stock_scores, price_daily, technical_data_daily
- Use `ticker` for: company_profile, key_metrics, market_data
- When joining: `ON stock_scores.symbol = company_profile.ticker`

---

## Common First Queries

### Get top 50 stocks by score
```sql
SELECT symbol, composite_score, momentum_score, value_score
FROM stock_scores
ORDER BY composite_score DESC
LIMIT 50;
```

### Get stock with full info
```sql
SELECT 
  ss.symbol, ss.composite_score, ss.current_price,
  cp.short_name, km.trailing_pe
FROM stock_scores ss
LEFT JOIN company_profile cp ON ss.symbol = cp.ticker
LEFT JOIN key_metrics km ON ss.symbol = km.ticker
WHERE ss.symbol = 'AAPL';
```

### Check data freshness
```sql
SELECT script_name, last_run
FROM last_updated
ORDER BY last_run DESC
LIMIT 10;
```

---

## Documentation Files

| File | Size | Purpose |
|------|------|---------|
| `DATABASE_DOCS_INDEX.md` | 8KB | Navigation hub |
| `DATABASE_QUICK_REFERENCE.md` | 8KB | Quick lookups |
| `DATABASE_SCHEMA_VISUAL.md` | 26KB | Architecture |
| `DATABASE_INVENTORY.md` | 22KB | Complete reference |
| `README_DATABASE_EXPLORATION.md` | 9KB | Summary |

**Total**: 65KB+ of comprehensive documentation

---

## Need Help?

| Question | Answer | Location |
|----------|--------|----------|
| Which tables should I use? | stock_scores (main), price_daily (prices), sentiment tables | DATABASE_QUICK_REFERENCE.md |
| How do I connect? | Environment variables or AWS Secrets | DATABASE_QUICK_REFERENCE.md |
| What's the schema? | 50+ tables with full definitions | DATABASE_INVENTORY.md |
| How do the tables relate? | ASCII diagrams with relationships | DATABASE_SCHEMA_VISUAL.md |
| What queries work? | Copy-paste examples provided | All documents |
| Why is my query slow? | Performance tips and optimization | DATABASE_SCHEMA_VISUAL.md |

---

## Data Pipeline Overview

```
yfinance + APIs + CNN web scrape
         ↓
    Python Loaders (15+ scripts)
         ↓
    PostgreSQL Database
         ↓
    Node.js API (/api/scores, etc)
         ↓
    React Frontend UI
```

---

## Next Steps

1. ✅ You read this file
2. → Open `DATABASE_DOCS_INDEX.md` for navigation
3. → Pick a documentation file based on your needs
4. → Try one of the query examples
5. → Build your API endpoint or analysis

---

## Pro Tips

1. Always filter by date: `WHERE date >= CURRENT_DATE - INTERVAL '90 days'`
2. All scores are 0-100 normalized
3. Check `last_updated` table for data freshness
4. Use indexes on (symbol, date) for speed
5. Pre-calculated data lives in `stock_scores` table

---

**Ready?** Open `DATABASE_DOCS_INDEX.md` next!


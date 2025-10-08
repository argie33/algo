# Actual Database Schema Reference

**Generated**: 2025-10-08
**Source**: Production database inspection

## Key Tables

### company_profile
**Primary Key**: `ticker` (VARCHAR(10))
**Key Columns**:
- ticker (VARCHAR(10)) - Primary key
- short_name (VARCHAR(100))
- long_name (VARCHAR(200))
- sector (VARCHAR(100))
- industry (VARCHAR(100))
- **NO market_cap column** - use market_data table instead

**Important**:
- Column is `ticker` NOT `symbol`
- Does NOT contain market_cap, price, volume

### market_data
**Primary Key**: `ticker` (VARCHAR(10))
**Foreign Key**: `ticker` REFERENCES company_profile(ticker)
**Key Columns**:
- ticker (VARCHAR(10)) - Primary key
- current_price (NUMERIC)
- volume (BIGINT)
- market_cap (BIGINT)
- previous_close (NUMERIC)
- regular_market_price (NUMERIC)

**Important**:
- Column is `ticker` NOT `symbol`
- Price column is `current_price` NOT `price`
- JOINs with company_profile: `ON cp.ticker = md.ticker`

### price_daily
**Key Columns**:
- symbol (VARCHAR)
- date (DATE)
- close (NUMERIC)
- volume (BIGINT)

**Important**:
- Column is `symbol` (matches company_profile.ticker)
- JOINs with company_profile: `ON cp.ticker = pd.symbol`

## Common JOIN Patterns

### company_profile + market_data
```sql
FROM company_profile cp
LEFT JOIN market_data md ON cp.ticker = md.ticker
```

### company_profile + price_daily
```sql
FROM company_profile cp
LEFT JOIN price_daily pd ON cp.ticker = pd.symbol
```

### All three tables
```sql
FROM company_profile cp
LEFT JOIN market_data md ON cp.ticker = md.ticker
LEFT JOIN price_daily pd ON cp.ticker = pd.symbol
```

## Schema Fixes Applied

### Commit c51e33d0e (2025-10-08)
- Fixed market.js: market_data uses ticker, current_price
- Fixed sectors.js: JOIN on ticker=ticker, use current_price
- Fixed backtest.js: company_profile uses ticker column
- Fixed market cap query to use market_data table

## Test Updates Needed

Tests must query:
- `company_profile.ticker` NOT `company_profile.symbol`
- `market_data.ticker` NOT `market_data.symbol`
- `market_data.current_price` NOT `market_data.price`
- Market cap from `market_data.market_cap` NOT `company_profile.market_cap`

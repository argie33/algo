# Market Endpoints Data Check

## Summary of Issues Fixed

### 1. Yield Curve Endpoint
**Problem**: Using wrong column names
- Was: `ticker` and `current_price`
- Fixed to: `symbol` and `price`

**Required Tables & Columns**:
- Table: `market_data`
- Symbols: `^TNX` (10-year), `^IRX` (3-month)
- Column: `price`

### 2. McClellan Oscillator Endpoint
**Status**: ✓ Correct
- Uses: `price_daily` table
- Columns: `date`, `open`, `close`
- Calculates: Advance/decline counts then EMA19 - EMA39

### 3. Sentiment Divergence Endpoint
**Status**: Needs Data Check
- Tables: `naaim`, `aaii_sentiment`
- Columns look correct but need to verify data exists

**NAAIM table columns**:
- `date`
- `naaim_number_mean` (professional bullish %)
- `bullish`
- `bearish`

**AAII table columns**:
- `date`
- `bullish` (%)
- `neutral` (%)
- `bearish` (%)

## Test Queries to Run

### Check if data exists:
```sql
-- Check market_data for yields
SELECT symbol, price, date FROM market_data
WHERE symbol IN ('^TNX', '^IRX')
ORDER BY date DESC LIMIT 5;

-- Check NAAIM data
SELECT date, naaim_number_mean, bullish, bearish
FROM naaim
ORDER BY date DESC LIMIT 5;

-- Check AAII data
SELECT date, bullish, neutral, bearish
FROM aaii_sentiment
ORDER BY date DESC LIMIT 5;

-- Check price_daily for breadth calculation
SELECT symbol, date, open, close
FROM price_daily
WHERE date >= CURRENT_DATE - INTERVAL '5 days'
ORDER BY date DESC LIMIT 100;
```

## Frontend API Calls to Test

1. **Yield Curve**: GET `/api/market/overview` → check `data.yield_curve`
2. **McClellan**: GET `/api/market/mcclellan-oscillator`
3. **Sentiment Divergence**: GET `/api/market/sentiment-divergence`

## Data Requirements

For all indicators to work:
- ✓ Market data with ^TNX and ^IRX symbols
- ✓ Daily price_daily entries with open/close
- ✓ NAAIM table with naaim_number_mean values
- ✓ AAII sentiment table with bullish/neutral/bearish percentages

## Fixes Applied

1. Fixed `market_data` queries to use `symbol` instead of `ticker`
2. Fixed `market_data` queries to use `price` instead of `current_price`
3. Verified McClellan Oscillator query structure
4. Verified sentiment divergence queries
5. Added proper error handling for missing data

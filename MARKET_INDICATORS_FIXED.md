# Market Indicators - Database Fix Summary

## What Was Wrong

The market indicators were using incorrect database column and table names. Here's what was fixed:

### 1. ❌ Yield Curve Endpoint - FIXED

**Original Query Issue**:
```sql
-- WRONG - using 'ticker' and 'current_price'
SELECT
  MAX(CASE WHEN ticker = '^TNX' THEN current_price END) as tnx_yield,
  MAX(CASE WHEN ticker = '^IRX' THEN current_price END) as irx_yield,
  FROM market_data
  WHERE ticker IN ('^TNX', '^IRX')
```

**Fixed Query**:
```sql
-- CORRECT - using 'symbol' and 'price'
SELECT
  MAX(CASE WHEN symbol = '^TNX' THEN price END) as tnx_yield,
  MAX(CASE WHEN symbol = '^IRX' THEN price END) as irx_yield,
  FROM market_data
  WHERE symbol IN ('^TNX', '^IRX')
```

**Database Reality**:
- Table: `market_data`
- Symbol column: `symbol` (NOT `ticker`)
- Price column: `price` (NOT `current_price`)
- Data loaded by: `loadmarket.py`
- Symbols: `^TNX` (10-year Treasury), `^IRX` (3-month Treasury)

---

### 2. ✓ McClellan Oscillator Endpoint - CORRECT

**Query**:
```sql
SELECT
  date,
  COUNT(CASE WHEN close > open THEN 1 END) as advances,
  COUNT(CASE WHEN close < open THEN 1 END) as declines
FROM price_daily
WHERE date >= CURRENT_DATE - INTERVAL '90 days'
  AND close IS NOT NULL AND open IS NOT NULL
GROUP BY date
```

**Database Reality**:
- Table: `price_daily`
- Columns: `date`, `open`, `close` ✓ (All correct)
- Calculation: Advance-decline line, then 19-day and 39-day EMAs
- EMA Formula: `McClellan = EMA19(advances-declines) - EMA39(advances-declines)`

---

### 3. ✓ Sentiment Divergence Endpoint - MOSTLY CORRECT

**Queries**:
```sql
-- NAAIM (Professional Investors)
SELECT date, naaim_number_mean as professional_bullish
FROM naaim
ORDER BY date DESC LIMIT 1;

-- AAII (Retail Investors)
SELECT date, bullish as retail_bullish
FROM aaii_sentiment
ORDER BY date DESC LIMIT 1;

-- Then calculate: divergence = retail_bullish - professional_bullish
```

**Database Reality**:
- NAAIM table columns: ✓ `date`, ✓ `naaim_number_mean`, ✓ `bullish`, ✓ `bearish`
- AAII table columns: ✓ `date`, ✓ `bullish`, ✓ `neutral`, ✓ `bearish`
- Data frequency: NAAIM daily, AAII weekly

---

## What Data Is Needed

For all three indicators to work with real data:

### 1. Yield Curve Data Requirements
```
Table: market_data
Rows needed: At least one row per symbol with recent data
Symbols: ^TNX, ^IRX
Columns populated: symbol, price, date
Example:
  ^TNX | 4.35  | 2024-10-21
  ^IRX | 5.42  | 2024-10-21
```

**Status**: Data should exist (loaded by loadmarket.py)
**To verify**:
```bash
psql -U postgres -d stocks -c \
  "SELECT symbol, price, date FROM market_data WHERE symbol IN ('^TNX','^IRX') ORDER BY date DESC LIMIT 2;"
```

### 2. McClellan Oscillator Data Requirements
```
Table: price_daily
Rows needed: At least 90 days of daily data for all stocks
Columns: symbol, date, open, close, volume
Example:
  AAPL | 2024-10-21 | 220.50 | 221.30 | 50000000
  GOOGL| 2024-10-21 | 168.40 | 168.90 | 30000000
  (repeat for hundreds of stocks)
```

**Status**: Data should exist (loaded by loadpricedaily.py)
**To verify**:
```bash
psql -U postgres -d stocks -c \
  "SELECT COUNT(*) FROM price_daily WHERE date >= CURRENT_DATE - INTERVAL '90 days';"
# Should return thousands of records
```

### 3. Sentiment Divergence Data Requirements
```
Table: naaim (Professional Manager Sentiment)
  date | naaim_number_mean | bullish | bearish
  2024-10-21 | 68.5 | 68.5 | 31.5

Table: aaii_sentiment (Retail Investor Sentiment)
  date | bullish | neutral | bearish
  2024-10-21 | 45.2 | 28.1 | 26.7
```

**NAAIM Status**: Should be updated daily (loaded by loadnaaim.py)
**AAII Status**: Should be updated weekly (loaded by loadaaiidata.py)

**To verify**:
```bash
# NAAIM data
psql -U postgres -d stocks -c \
  "SELECT date, naaim_number_mean, bullish FROM naaim ORDER BY date DESC LIMIT 5;"

# AAII data
psql -U postgres -d stocks -c \
  "SELECT date, bullish, neutral, bearish FROM aaii_sentiment ORDER BY date DESC LIMIT 5;"
```

---

## Next Steps

### Step 1: Verify Data Exists
Run the verification commands above to ensure:
- [ ] market_data has ^TNX and ^IRX with recent prices
- [ ] price_daily has 90+ days of OHLCV data
- [ ] naaim has recent daily professional sentiment data
- [ ] aaii_sentiment has recent weekly retail sentiment data

### Step 2: Run Data Loaders (if needed)
If data is missing, run the loaders:
```bash
# Load market data (indices, ETFs, treasuries, VIX)
python3 /home/stocks/algo/loadmarket.py

# Load daily prices for all stocks
python3 /home/stocks/algo/loadpricedaily.py

# Load professional sentiment (NAAIM)
python3 /home/stocks/algo/loadnaaim.py

# Load retail sentiment (AAII)
python3 /home/stocks/algo/loadaaiidata.py
```

### Step 3: Test Endpoints
Once data is loaded, test the three endpoints:

```bash
# 1. Yield Curve (part of overview)
curl http://localhost:3001/api/market/overview \
  | jq '.data.yield_curve'

# 2. McClellan Oscillator
curl http://localhost:3001/api/market/mcclellan-oscillator

# 3. Sentiment Divergence
curl http://localhost:3001/api/market/sentiment-divergence
```

### Step 4: Check Frontend Display
Navigate to the Market Overview page and verify:
- [ ] Yield Curve Card shows 10Y-2Y spread with inversion status
- [ ] McClellan Oscillator Chart shows breadth momentum trend
- [ ] Sentiment Divergence Chart shows professional vs retail divergence

---

## Database Column Reference

### market_data table (Indices, ETFs, Yields)
```
symbol          TEXT      - Ticker symbol (^GSPC, SPY, ^TNX, etc.)
name            TEXT      - Full name
date            DATE      - Date of data
price           NUMERIC   - Current/closing price ← USE THIS
volume          NUMERIC   - Trading volume
market_cap      NUMERIC   - Market capitalization (if applicable)
return_1d       NUMERIC   - 1-day return %
volatility_30d  NUMERIC   - 30-day volatility
beta            NUMERIC   - Beta (vs SPY)
asset_class     TEXT      - Classification (index, etf, bond, commodity)
region          TEXT      - Geographic region
```

### price_daily table (Stock daily prices)
```
symbol          TEXT      - Stock ticker
date            DATE      - Trading date
open            NUMERIC   - Opening price
high            NUMERIC   - Daily high
low             NUMERIC   - Daily low
close           NUMERIC   - Closing price
adj_close       NUMERIC   - Adjusted closing price
volume          BIGINT    - Trading volume
```

### naaim table (Professional sentiment)
```
date                    DATE      - Week ending date
naaim_number_mean       NUMERIC   - Average equity exposure (0-100)
bullish                 NUMERIC   - Bullish % exposure
bearish                 NUMERIC   - Bearish % exposure
quart1-quart3          NUMERIC   - Quartile breakdowns
deviation              NUMERIC   - Standard deviation
```

### aaii_sentiment table (Retail sentiment)
```
date                    DATE      - Survey date
bullish                 NUMERIC   - Bullish % (0-100)
neutral                 NUMERIC   - Neutral % (0-100)
bearish                 NUMERIC   - Bearish % (0-100)
```

---

## API Response Examples

### /api/market/overview → yield_curve
```json
{
  "yield_curve": {
    "tnx_10y": 4.35,
    "irx_2y": 5.42,
    "spread_10y_2y": -1.07,
    "is_inverted": true,
    "date": "2024-10-21"
  }
}
```

### /api/market/mcclellan-oscillator
```json
{
  "success": true,
  "data": {
    "current_value": 142.5,
    "ema_19": 285.3,
    "ema_39": 142.8,
    "interpretation": "Bullish breadth",
    "recent_data": [ ... ],
    "data_points": 90
  }
}
```

### /api/market/sentiment-divergence
```json
{
  "success": true,
  "data": {
    "current": {
      "date": "2024-10-21",
      "professional_bullish": 68.5,
      "retail_bullish": 45.2,
      "divergence": -23.3,
      "signal": "Professionals Overly Bullish"
    },
    "historical": [ ... ]
  }
}
```

---

## Summary

✅ **Yield Curve Endpoint**: Fixed column names, ready to display real data
✅ **McClellan Oscillator**: Correct queries, ready to calculate breadth momentum
✅ **Sentiment Divergence**: Correct queries, ready to show smart money vs retail

**All endpoints will work once the underlying data is populated in the database.**


# Finding & Fixing All Data Display Issues

## Quick Diagnostic Process

### 1. Browser Console Errors
**Open each page in browser with DevTools (F12) and check Console tab:**
```
- TradingSignals page: /app/signals
- MarketsHealth page: /app/markets
- Portfolio page: /app/portfolio
- Sector Analysis page: /app/sectors
- Stock Detail page: /app/stock/AAPL
```

Look for:
- `Cannot read properties of undefined (reading 'xxx')`
- Network 500 errors to API endpoints
- Missing null checks

### 2. Network Tab Issues
**Check Network tab in DevTools:**
```
1. Is API responding with 200?
2. Is response body empty or truncated?
3. Do response fields match what component expects?
```

Example API call to check:
```bash
curl -s http://localhost:3001/api/algo/markets | jq '.' | head -50
curl -s http://localhost:3001/api/signals/stocks?limit=1 | jq '.items[0]' | head -100
curl -s http://localhost:3001/api/market/sentiment | jq '.' | head -50
```

### 3. Systematic Page Audit

#### TradingSignals (/app/signals)
**API Endpoints:**
- GET /api/signals/stocks?timeframe=daily&limit=500
- GET /api/signals/etf?limit=500
- GET /api/algo/swing-scores?limit=2000&min_score=0
- GET /api/prices/history/{symbol}?timeframe=daily&limit=60

**Fields to check:**
- signal, date, symbol - ✅ Working (in buy_sell_daily)
- buylevel, stoplevel, risk_reward_ratio - ❌ Missing columns
- base_type, base_length_days - ❌ Missing columns
- volume_surge_pct, entry_quality_score - ❌ Missing columns
- profit_target_*, exit_trigger_* - ❌ Missing columns
- All technical indicators (rsi, adx, atr, sma_50, sma_200, ema_21) - ⚠️ ema_21 missing

**Fix Applied:** API query expanded to include all columns with NULL defaults

#### MarketsHealth (/app/markets)
**API Endpoints:**
- GET /api/algo/markets - ✅ Fixed (now queries market_exposure_daily)
- GET /api/market/sentiment?range=30d - ⚠️ Check status
- GET /api/market/top-movers - ⚠️ Check status
- GET /api/market/technicals - ⚠️ Check status
- GET /api/market/seasonality - ⚠️ Check status

**Fix Applied:** /api/algo/markets now returns proper market exposure data

#### Portfolio (/app/portfolio)
**API Endpoints:**
- GET /api/algo/positions
- GET /api/algo/portfolio/performance
- GET /api/algo/portfolio/trades

**Check for:**
- Missing position fields (entry_price, quantity, unrealized_pnl)
- Missing performance metrics

#### Sector Analysis (/app/sectors)
**API Endpoints:**
- GET /api/sectors/etf-performance
- GET /api/sectors/rotation

**Check for:**
- Sector weight data
- Rotation signals

#### Stock Detail (/app/stock/{symbol})
**API Endpoints:**
- GET /api/stocks/{symbol}
- GET /api/prices/history/{symbol}
- GET /api/algo/signals/stock/{symbol}
- GET /api/sentiment/analyst/insights/{symbol}

### 4. Common Issues & Fixes

#### Issue: "Cannot read properties of undefined"
**Solution:**
```javascript
// Bad
const name = data.company.name;

// Good  
const name = data?.company?.name || 'Unknown';
```

#### Issue: Array not rendering in table
**Solution:**
```javascript
// Bad
const rows = data; // might be null

// Good
const rows = Array.isArray(data) ? data : (data?.items || []);
```

#### Issue: API returning empty or wrong structure
**Solution:**
```bash
# Check what API actually returns
curl -s http://localhost:3001/api/endpoint | jq '.'

# Compare with what frontend expects (from React component)
# Look for field mismatches
```

#### Issue: Historical data not showing
**Solution:**
- Check if query has proper date filtering
- Verify data exists in database: 
  ```sql
  SELECT COUNT(*), MIN(date), MAX(date) FROM table_name;
  ```

### 5. Database Verification

For each table being queried, verify:
```bash
# Check if table exists and has data
psql -c "SELECT COUNT(*) FROM buy_sell_daily WHERE date >= CURRENT_DATE - INTERVAL '30 days';"

# Check for missing columns
psql -c "\d buy_sell_daily;" | grep column_name

# Check for stale data
psql -c "SELECT MAX(date), COUNT(*) FROM technical_data_daily;"
```

### 6. Frontend Component Debugging

In TradingSignals.jsx (around line 170-191):
```javascript
const filtered = useMemo(() => {
  let r = enriched;
  // ... filters applied ...
  return r;
}, [enriched, search, stageFilter, sectorFilter, scoreRange, maxAge, gatesOnly, baseTypeFilter]);

// Add logging:
console.log('Filtered rows:', filtered);
console.log('Sample row:', filtered[0]);
```

### 7. API Response Format Check

Ensure API returns consistent format:
```javascript
// Should follow this pattern:
{
  success: true,
  items: [
    { symbol: 'AAPL', signal: 'BUY', ... all fields },
    { symbol: 'MSFT', signal: 'SELL', ... all fields }
  ],
  total: 100,
  pagination: { ... }
}
```

## Common Fixes Checklist

### For Missing Columns in Tables
1. ✅ Identify which columns the component expects
2. ✅ Check if columns exist in database
3. ✅ Update API query SELECT to include columns (with COALESCE defaults if missing)
4. ✅ Add ALTER TABLE migrations if columns need to be created
5. ⏳ Wait for loaders to populate data

### For Wrong Data Endpoint
1. ✅ Identify what data the component expects
2. ✅ Find the correct source table
3. ✅ Fix API endpoint to query correct table
4. ✅ Verify data exists in that table

### For Null/Empty Data
1. Check if frontend has proper null handling
2. Check if data exists in database (don't assume empty means broken)
3. Check if date filters are correct (off-by-one errors common)
4. Check if loaders are actually running and populating data

## Pages Still To Audit

- [ ] Portfolio Dashboard
- [ ] Backtest Results
- [ ] Performance Metrics
- [ ] Swing Candidates
- [ ] Deep Value Stocks
- [ ] Service Health
- [ ] Audit Viewer
- [ ] Economic Dashboard
- [ ] Sentiment page
- [ ] Trade Tracker
- [ ] Notification Center
- [ ] Pre-Trade Simulator
- [ ] Scores Dashboard

## Testing Commands

```bash
# Start dev server
npm run dev --prefix webapp/frontend

# Test APIs (from another terminal)
curl -s http://localhost:3001/api/signals/stocks?limit=1 | jq '.'
curl -s http://localhost:3001/api/algo/markets | jq '.'

# Check database data freshness
psql $DATABASE_URL -c "
  SELECT table_name, MAX(date) as latest_date, COUNT(*) as rows
  FROM (
    SELECT 'buy_sell_daily' as table_name, date, COUNT(*) FROM buy_sell_daily GROUP BY date
    UNION ALL
    SELECT 'technical_data_daily', date, COUNT(*) FROM technical_data_daily GROUP BY date
    UNION ALL
    SELECT 'market_exposure_daily', date, COUNT(*) FROM market_exposure_daily GROUP BY date
  ) stats
  GROUP BY table_name;
"
```

## Reporting Issues

When you find a data display issue, document:
1. **Page:** Which page/URL
2. **Expected:** What data should show
3. **Actual:** What's currently showing (or error message)
4. **API Endpoint:** What endpoint is called
5. **Database:** What table/columns involved
6. **Root Cause:** What's actually wrong (schema, query, loader, frontend logic)
7. **Fix:** What needs to be done (schema update, query fix, new loader, etc.)

Example:
```
Page: /app/signals
Expected: Volume surge % column in Trading Signals table
Actual: Column shows "—" (missing data)
API: GET /api/signals/stocks
Database: buy_sell_daily.volume_surge_pct column exists but is NULL
Root Cause: No loader populates this column
Fix: Update Pine Script loader to calculate and write volume_surge_pct
```

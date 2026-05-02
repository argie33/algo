# PROPER API ARCHITECTURE - Clean & Right

## CURRENT PROBLEMS

### 1. Dead Endpoints (Not Called by Frontend)
```
price.js (7 endpoints) - UNUSED - Delete or clearly mark as for-future
earnings.js (7 endpoints) - UNUSED - Delete or clearly mark as for-future  
user.js (4 endpoints) - UNUSED - Delete (probably old auth system)
sectors.js (1 endpoint) - UNUSED - Delete
```

### 2. Bloated Endpoints (Too Many Variants)
```
market.js: 22 endpoints but only 8 are used
- Keep: overview, indices, technicals, sentiment, seasonality, correlation, top-movers, cap-distribution
- Delete: status, breadth, mcclellan-oscillator, distribution-days, volatility, indicators, internals, aaii, fear-greed, naaim, data, fresh-data, comprehensive-fresh, technicals-fresh

portfolio.js: 11 endpoints but not all used
- Check: which ones actually called?
```

### 3. Unclear File Organization
```
What's the difference between:
- /api/market/technicals vs /api/market/technicals-fresh
- /api/market/sentiment vs /api/market/fear-greed vs /api/market/aaii
- /api/signals/daily vs /api/signals/stocks vs /api/signals/etf
```

---

## WHAT FRONTEND ACTUALLY CALLS

### Market Endpoints (8 Used, 14 Dead)
```javascript
✅ /api/market/overview          - Complete market snapshot
✅ /api/market/indices           - Major indices
✅ /api/market/technicals        - Technical indicators
✅ /api/market/sentiment         - Fear/greed index
✅ /api/market/seasonality       - Seasonal patterns
✅ /api/market/correlation       - Asset correlations
✅ /api/market/top-movers        - Gainers/losers
✅ /api/market/cap-distribution  - Market cap breakdown
```

### Stock Endpoints (4 Used)
```javascript
✅ /api/stocks                   - List all stocks (paginated)
✅ /api/stocks/:symbol           - Individual stock detail
✅ /api/stocks/search            - Search by name/symbol
✅ /api/stocks/deep-value        - Ranked stocks
```

### Financial Endpoints (3 Used)
```javascript
✅ /api/financials/:symbol/balance-sheet
✅ /api/financials/:symbol/income-statement
✅ /api/financials/:symbol/cash-flow
```

### Signal Endpoints (3 Used)
```javascript
✅ /api/signals/daily            - Daily buy/sell signals
✅ /api/signals/weekly           - Weekly signals
✅ /api/signals/monthly          - Monthly signals
```

### Economic Endpoints (3 Used)
```javascript
✅ /api/economic/leading-indicators
✅ /api/economic/yield-curve-full
✅ /api/economic/calendar
```

### Portfolio Endpoints (2 Used)
```javascript
✅ /api/portfolio/metrics        - Performance metrics
✅ /api/trades                   - Trade history
```

### Health Endpoints (2 Used)
```javascript
✅ /api/health                   - System health
✅ /api/health/database          - Database health
```

### Contact Endpoints (2 Used)
```javascript
✅ /api/contact                  - Submit form (POST)
✅ /api/contact/submissions      - Get submissions (GET)
```

---

## IDEAL STRUCTURE

### Core Route Files to Keep (11)
```
1. market.js        - 8 endpoints (CLEAN market data)
2. stocks.js        - 4 endpoints (Stock data)
3. financials.js    - 3 endpoints (Financial statements)
4. signals.js       - 3 endpoints (Trading signals)
5. economic.js      - 3 endpoints (Economic data)
6. portfolio.js     - 2 endpoints (Portfolio data) [SIMPLIFY]
7. trades.js        - 1 endpoint (Trade history)
8. health.js        - 2 endpoints (Health checks)
9. diagnostics.js   - 1 endpoint (Diagnostics)
10. contact.js      - 2 endpoints (Contact/messages)
11. manual-trades.js - 3 endpoints (Manual trades for auth users)
```

### Remove These Files (4)
```
❌ price.js          - Not used by frontend
❌ earnings.js       - Not used by frontend
❌ user.js           - Not used by frontend (remove or mark as WIP)
❌ sectors.js        - Not used by frontend
```

### Total: ~34 Focused Endpoints
**Instead of:** 105 scattered endpoints with duplicates
**Result:** Clean, clear, maintainable API

---

## SPECIFIC CLEANUP ACTIONS

### 1. Market.js - Delete 14 Endpoints
**Keep only:**
- /overview (line 2605)
- /indices (line 1798)
- /technicals (line 2615)
- /sentiment (line 2792)
- /seasonality (line 948)
- /correlation (line 1527)
- /top-movers (line 3175)
- /cap-distribution (line 3212)

**Delete:**
- /status, /breadth, /mcclellan-oscillator, /distribution-days, /volatility, /indicators
- /internals, /aaii, /fear-greed, /naaim, /data, /fresh-data, /comprehensive-fresh, /technicals-fresh

**Result:** From 3200 lines → ~800 lines

### 2. Portfolio.js - Simplify (11 → 2 Endpoints)
Check which are actually called. Delete:
- Unused metrics endpoints
- API key management endpoints (if not used)
- Import/alpaca sync endpoints (if not used)

Keep only:
- /metrics (used)
- Need to verify what else is essential

### 3. Remove Dead Files
Delete entirely:
- webapp/lambda/routes/price.js
- webapp/lambda/routes/earnings.js
- webapp/lambda/routes/sectors.js
- Remove require statements from index.js

### 4. User.js - Decision
Either:
- Delete if it's old code
- OR move to separate auth-routes.js if actively being developed

---

## PROPER REST NAMING

### ✅ GOOD NAMING
```
GET /api/stocks              - List resources
GET /api/stocks/AAPL         - Get one resource
GET /api/stocks/search       - Search/filter  (acceptable query action)
POST /api/contact            - Create
DELETE /api/trades/:id       - Delete
```

### ❌ BAD NAMING
```
GET /api/market/technicals-fresh    ❌ Why "-fresh"? Use cache headers instead
GET /api/market/comprehensive-fresh ❌ Undefined, redundant
GET /api/market/status              ❌ Status is not data, belongs in /health
GET /api/stocks/quick/overview      ❌ "quick" is about performance, not API design
GET /api/market/data                ❌ Too vague
```

---

## RESPONSE CONSISTENCY CHECK

### ✅ Standard Format All Endpoints Must Use
```json
// List Response (paginated)
{
  "success": true,
  "items": [...],
  "pagination": {
    "limit": 50,
    "offset": 0,
    "total": 4966,
    "page": 1,
    "totalPages": 100,
    "hasNext": true,
    "hasPrev": false
  },
  "timestamp": "ISO-8601"
}

// Single Object
{
  "success": true,
  "data": {...},
  "timestamp": "ISO-8601"
}

// Error
{
  "success": false,
  "error": "Message",
  "timestamp": "ISO-8601"
}
```

### Verification
- [ ] All endpoints return `success` field
- [ ] All list endpoints use `items` key
- [ ] All singles use `data` key
- [ ] All responses have `timestamp`
- [ ] No weird variations like `data.data`

---

## PROPER ARCHITECTURE = CLEAN ENDPOINTS

### Benefits
1. **Clarity** - One endpoint per purpose
2. **Maintainability** - Easy to find what you need
3. **Performance** - Smaller file sizes, faster loads
4. **Documentation** - Clear which endpoints exist
5. **Quality** - No "fresh" or mystery endpoints
6. **Scalability** - Easy to add new endpoints without confusion

---

## ACTION PLAN

### Phase 1: Remove Dead Code (Today)
- [ ] Delete price.js (7 unused endpoints)
- [ ] Delete earnings.js (7 unused endpoints)
- [ ] Delete sectors.js (1 unused endpoint)
- [ ] Decide on user.js
- [ ] Remove requires and mounts from index.js

### Phase 2: Clean Market.js (Today)
- [ ] Delete 14 unused market endpoints
- [ ] Keep 8 core market endpoints
- [ ] Reduce from 3200 lines to ~800

### Phase 3: Audit Other Files
- [ ] Check portfolio.js - remove unused endpoints
- [ ] Check other routes - ensure only essential endpoints
- [ ] Verify response format consistency

### Phase 4: Test Everything
- [ ] Verify all 9 pages still work
- [ ] Run endpoint test suite
- [ ] Load test performance

---

## RESULT: PROPER ARCHITECTURE

**Current:** 105 scattered endpoints with duplicates, dead code, confusing naming
**Target:** ~34 focused, clean, essential endpoints with clear naming

**Status:** Ready to implement


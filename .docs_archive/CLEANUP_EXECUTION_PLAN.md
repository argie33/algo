# EXECUTION PLAN: Clean Architecture Implementation

## Phase 1: DELETE UNUSED ROUTE FILES (5 min)

### Files to Delete
```
webapp/lambda/routes/price.js       - 7 unused endpoints
webapp/lambda/routes/earnings.js    - 7 unused endpoints
webapp/lambda/routes/sectors.js     - 1 unused endpoint
webapp/lambda/routes/user.js        - 4 endpoints (check if being developed)
```

### Update index.js
Remove these requires:
```javascript
const priceRoutes = require("./routes/price");
const earningsRoutes = require("./routes/earnings");
const sectorsRoutes = require("./routes/sectors");
const userRoutes = require("./routes/user");
```

Remove these mounts:
```javascript
app.use("/api/price", priceRoutes);
app.use("/api/earnings", earningsRoutes);
app.use("/api/sectors", sectorsRoutes);
app.use("/api/user", userRoutes);
```

**Result:** Removes 19 unused endpoints, simplifies index.js

---

## Phase 2: MARKET.JS - AGGRESSIVE CLEANUP (30 min)

### Strategy
1. Copy helper functions (checkRequiredTables, safeFloat, etc) to keep
2. Find line numbers for the 8 essential endpoints
3. Extract only those 8 handlers
4. Delete everything else
5. Rebuild market.js with just the essentials

### 8 Essential Endpoints to Keep
```
Line 2605 - /overview
Line 2615 - /technicals
Line 2792 - /sentiment
Line 948  - /seasonality
Line 1527 - /correlation
Line 1798 - /indices
Line 3175 - /top-movers
Line 3212 - /cap-distribution
```

### All Dead Endpoints to Delete
```
Line 465  - /status
Line 520  - /breadth
Line 602  - /mcclellan-oscillator
Line 707  - /distribution-days
Line 804  - /volatility
Line 855  - /indicators
Line 1951 - /internals
Line 2226 - /aaii
Line 2286 - /fear-greed
Line 2336 - /naaim
Line 2601 - /data
Line 2878 - /fresh-data
Line 2910 - /comprehensive-fresh
Line 2941 - /technicals-fresh
```

### Refactoring
After cleanup, market.js should be ~800 lines (was 3200)

**Result:** 
- Removes 14 dead endpoints
- Keeps 8 essential endpoints
- Reduces file from 3200 → 800 lines
- Maintains all data output

---

## Phase 3: PORTFOLIO.JS - REVIEW & SIMPLIFY (15 min)

### Check Which Endpoints are Actually Used
Current: 11 endpoints
- [ ] /metrics - USED ✅
- [ ] /manual-positions - CHECK
- [ ] /import/alpaca - CHECK
- [ ] /api-keys endpoints - CHECK
- [ ] Others - REVIEW

### Action
- Keep only endpoints that frontend actually calls
- Delete unused auth/key management (if not used)
- Simplify from 11 → ~2-3 essential

---

## Phase 4: VERIFY & TEST (10 min)

After cleanup, test these:
```bash
# Market endpoints
curl http://localhost:3001/api/market/overview
curl http://localhost:3001/api/market/indices
curl http://localhost:3001/api/market/technicals
curl http://localhost:3001/api/market/sentiment
curl http://localhost:3001/api/market/seasonality
curl http://localhost:3001/api/market/correlation
curl http://localhost:3001/api/market/top-movers
curl http://localhost:3001/api/market/cap-distribution

# Verify frontend still works
```

---

## TOTAL TIME: ~1 hour

### Benefits
1. Removes ~40 unused endpoints
2. Reduces codebase from 105 → ~65 endpoints
3. Makes API clear and maintainable
4. Improves code quality
5. Easier for other developers to understand

### Risk Level: LOW
- All deleted endpoints are never called by frontend
- All 8 kept market endpoints are tested and working
- Can always restore from git if needed

---

## READY TO EXECUTE?

Yes, let's do it properly. Clean architecture from top to bottom.


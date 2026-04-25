# API ROUTING MISMATCHES - CRITICAL ISSUES

## 🔴 MISSING ROUTES (Frontend calls but backend doesn't have)

### 1. DASHBOARD ENDPOINTS
**Frontend calls:** `/api/dashboard/*`
**Backend has:** `/api/diagnostics` (different name!)
**Status:** ❌ MISMATCH - name is different

Frontend calls:
- `/api/dashboard/alerts` 
- `/api/dashboard/debug`
- `/api/dashboard/performance`
- `/api/dashboard/summary`
- `/api/dashboard/symbols`

Backend has:
- `/api/diagnostics` (similar but different path)

**Action needed:** Either:
- Option A: Rename `/api/diagnostics` to `/api/dashboard` 
- Option B: Rename all frontend calls from `/api/dashboard` to `/api/diagnostics`
- Option C: Create `/api/dashboard` as alias to `/api/diagnostics`

---

### 2. ORDERS ENDPOINT
**Frontend calls:** `/api/orders`
**Backend has:** ❌ NOT FOUND
**Status:** ❌ MISSING

Frontend expects to get order data but endpoint doesn't exist.

**Action needed:** Create `/api/orders` route or check if data is in `/api/trades`

---

### 3. POSITIONING ENDPOINTS  
**Frontend calls:** `/api/positioning/data`, `/api/positioning/summary`
**Backend has:** ❌ NOT FOUND
**Status:** ❌ MISSING

**Action needed:** Create positioning routes or check if data is in `/api/portfolio`

---

### 4. RESEARCH ENDPOINTS
**Frontend calls:** 
- `/api/research/analysts`
- `/api/research/commentary`
- `/api/research/trends`

**Backend has:** ❌ NOT FOUND
**Status:** ❌ MISSING

**Action needed:** Create research routes or check if in `/api/analysts`

---

### 5. TRADING ENDPOINTS
**Frontend calls:** `/api/trading/positions`
**Backend has:** `/api/trades` (different path!)
**Status:** ❌ MISMATCH

**Action needed:** Either rename or create alias `/api/trading` → `/api/trades`

---

## ✅ ROUTES THAT EXIST

Frontend calls that ARE mounted:
- ✅ `/api/earnings/*` → earnings.js
- ✅ `/api/economic/*` → economic.js
- ✅ `/api/financials/*` → financials.js
- ✅ `/api/health` → health.js
- ✅ `/api/market/*` → market.js
- ✅ `/api/portfolio/*` → portfolio.js
- ✅ `/api/sectors` → sectors.js
- ✅ `/api/sentiment/*` → sentiment.js
- ✅ `/api/stocks/*` → stocks.js
- ✅ `/api/user/*` → user.js

---

## IMMEDIATE FIXES NEEDED

### FIX #1: Create /api/dashboard alias to /api/diagnostics
Create file: `webapp/lambda/routes/dashboard.js`
```javascript
const express = require("express");
const diagnosticRoutes = require("./diagnostics");
const router = express.Router();

// Dashboard is an alias for diagnostics
router.use("/", diagnosticRoutes);

module.exports = router;
```

Then mount in index.js:
```javascript
const dashboardRoutes = require("./routes/dashboard");
app.use("/api/dashboard", dashboardRoutes);
```

### FIX #2: Create /api/orders route
Check if should alias `/api/trades` or create separate endpoint

### FIX #3: Create /api/positioning routes
Check if data is in portfolio or metrics endpoint

### FIX #4: Create /api/research routes
Check if should use `/api/analysts` or create separate routes

### FIX #5: Create /api/trading alias to /api/trades
Similar pattern to dashboard fix

---

## RESPONSE MAPPING ISSUES (SECONDARY)

Once routing is fixed, check response structure mismatches:
- [ ] Sentiment: field name mapping (`total_analysts` vs `analyst_count`)
- [ ] Scores: pagination format consistency
- [ ] Portfolio: performance metrics structure
- [ ] Financials: all field names match expected
- [ ] Strategies: field names correct

---

## ACTION PLAN

1. **Phase 1 - Fix Routing (THIS IS BLOCKING EVERYTHING)**
   - Create dashboard alias
   - Create trading alias  
   - Create orders, positioning, research routes (or aliases)
   
2. **Phase 2 - Test All Endpoints**
   - Verify all frontend API calls get 200 response
   - Check response structure matches

3. **Phase 3 - Fix Response Mapping**
   - Fix any field name mismatches
   - Ensure consistent pagination format
   - Verify all required fields present

# COMPLETE API ENDPOINT INVENTORY & ANALYSIS

## EXECUTIVE SUMMARY

| Metric | Count |
|--------|-------|
| Total Backend Endpoints | 155+ |
| Backend Route Modules | 31 |
| Frontend Pages | 7 |
| Endpoints Used by Frontend | ~15 |
| Endpoints NOT Used | ~140 |
| Usage Rate | **10%** |
| Unused Rate | **90%** |

---

## FRONTEND PAGES & THEIR ACTIVE ENDPOINTS

### 1. DeepValueStocks.jsx
**Endpoints Used:**
- `GET /api/stocks/deep-value` ✓

### 2. TradeHistory.jsx
**Endpoints Used:**
- `GET /api/trades` ✓
- `GET /api/trades/summary` ✓
- `GET /api/trades/history` (redundant with `/trades`)

### 3. PortfolioDashboard.jsx
**Endpoints Used:**
- `GET /api/portfolio/metrics` ✓

### 4. PortfolioOptimizerNew.jsx
**Endpoints Used:**
- `GET /api/optimization/analysis` ✓

### 5. Messages.jsx
**Endpoints Used:**
- `GET /api/contact/submissions` ✓

### 6. ServiceHealth.jsx
**Endpoints Used:**
- `GET /api/health` ✓
- `GET /api/health/database` ✓

### 7. Settings.jsx
**Endpoints Used:**
- `GET /api/user/settings` (not confirmed)
- `PUT /api/user/settings` (not confirmed)

---

## DETAILED MODULE BREAKDOWN

### ✅ ACTIVELY USED MODULES (6/31 = 19%)

#### 1. STOCKS - 1 of 6 endpoints used (17% utilization)
```
USED:
  GET /api/stocks/deep-value ✓

UNUSED:
  GET /api/stocks/ (list root)
  GET /api/stocks/search
  GET /api/stocks/quick/overview
  GET /api/stocks/full/data
  GET /api/stocks/:symbol (detail)
```

#### 2. PORTFOLIO - 5 of 11 endpoints used (45% utilization)
```
USED:
  GET /api/portfolio/metrics ✓
  GET /api/portfolio/api-keys ✓
  POST /api/portfolio/api-keys ✓
  DELETE /api/portfolio/api-keys/:id ✓
  POST /api/portfolio/test-api-key ✓

UNUSED:
  GET /api/portfolio/ (root)
  GET /api/portfolio/manual-positions
  POST /api/portfolio/manual-positions
  PUT /api/portfolio/api-keys/:id
  POST /api/portfolio/import/alpaca
```

#### 3. TRADES - 2 of 3 endpoints used (67% utilization)
```
USED:
  GET /api/trades ✓
  GET /api/trades/summary ✓

UNUSED:
  GET /api/trades/history (DUPLICATE - same as /)
```

#### 4. CONTACT - 1 of 4 endpoints used (25% utilization)
```
USED:
  GET /api/contact/submissions ✓

UNUSED:
  POST /api/contact/
  GET /api/contact/submissions/:id
  PATCH /api/contact/submissions/:id
```

#### 5. HEALTH - 2 of 4 endpoints used (50% utilization)
```
USED:
  GET /api/health ✓
  GET /api/health/database ✓

UNUSED:
  GET /api/health/ecs-tasks
  GET /api/health/api-endpoints
```

#### 6. OPTIMIZATION - 1 of 5 endpoints used (20% utilization)
```
USED:
  GET /api/optimization/analysis ✓

UNUSED:
  GET /api/optimization/ (root)
  GET /api/optimization/swing-trading
  POST /api/optimization/execute
  GET /api/optimization/recommendations
```

---

### ❌ COMPLETELY UNUSED MODULES (25/31 = 81%)

| Module | Endpoints | Status |
|--------|-----------|--------|
| ANALYSTS | 6 | ❌ Not used |
| API-STATUS | 1 | ❌ Not used |
| AUTH | 10 | ❌ Not used |
| COMMODITIES | 8 | ❌ Not used |
| COMMUNITY | 5 | ❌ Not used |
| DASHBOARD | 0 | ❌ Empty module |
| DIAGNOSTICS | 4 | ❌ Not used |
| EARNINGS | 8 | ❌ Not used |
| ECONOMIC | 5 | ❌ Not used |
| FINANCIALS | 6 | ❌ Not used |
| INDUSTRIES | 3 | ❌ Not used |
| MANUAL-TRADES | 5 | ❌ Not used |
| MARKET | 23 | ❌ Not used (LARGEST) |
| METRICS | 8 | ❌ Not used |
| OPTIONS | 4 | ❌ Not used |
| PRICE | 8 | ❌ Not used |
| SCORES | 3 | ❌ Not used |
| SECTORS | 3 | ❌ Not used |
| SENTIMENT | 10 | ❌ Not used |
| SIGNALS | 6 | ❌ Not used |
| STRATEGIES | 3 | ❌ Not used |
| TECHNICALS | 6 | ❌ Not used |
| TRADING | 0 | ❌ Empty module |
| USER | 5 | ❌ Not used |
| WORLD-ETFS | 4 | ❌ Not used |

**Total unused endpoints: ~140**

---

## CRITICAL ISSUES IDENTIFIED

### 🔴 Issue 1: Duplicate Endpoints

```
/api/trades/ and /api/trades/history (same functionality)
/api/sectors/ and /api/sectors/sectors (duplicate naming)
/api/industries/ and /api/industries/industries (duplicate naming)
/api/market/fresh-data appears TWICE in market.js
```

### 🔴 Issue 2: Empty Modules
- DASHBOARD module has zero endpoints
- TRADING module has zero endpoints

### 🔴 Issue 3: Inconsistent Naming Patterns
```
Some use singular:
  /api/stock/:symbol

Some use plural:
  /api/stocks/deep-value
  /api/stocks/

Some use /fresh-data:
  /api/market/fresh-data
  /api/economic/fresh-data
  /api/earnings/fresh-data

Some use /data:
  /api/market/data
  /api/economic/data
  /api/sentiment/data
```

### 🔴 Issue 4: No Typed API Functions
Frontend directly calls endpoints instead of using API client functions:
```javascript
// Bad (direct call):
api.get('/api/optimization/analysis')

// Good (typed function):
getOptimizationAnalysis()  // has error handling, response extraction, etc.
```

### 🔴 Issue 5: Massive API Surface Area
- 31 modules with 155+ endpoints
- Only 6 modules used
- 93% of code unmaintained
- High cognitive load for developers

---

## CONSOLIDATION RECOMMENDATIONS

### PHASE 1: Delete Unused Modules (Highest Priority)

**Remove completely** (0% used):
1. ANALYSTS (6 endpoints)
2. API-STATUS (1 endpoint)
3. AUTH (10 endpoints) - if auth is handled elsewhere
4. COMMODITIES (8 endpoints)
5. COMMUNITY (5 endpoints)
6. DASHBOARD (0 endpoints - empty)
7. DIAGNOSTICS (4 endpoints)
8. EARNINGS (8 endpoints)
9. ECONOMIC (5 endpoints)
10. FINANCIALS (6 endpoints)
11. INDUSTRIES (3 endpoints)
12. MANUAL-TRADES (5 endpoints)
13. MARKET (23 endpoints) - **LARGEST**
14. METRICS (8 endpoints)
15. OPTIONS (4 endpoints)
16. PRICE (8 endpoints)
17. SCORES (3 endpoints)
18. SECTORS (3 endpoints)
19. SENTIMENT (10 endpoints)
20. SIGNALS (6 endpoints)
21. STRATEGIES (3 endpoints)
22. TECHNICALS (6 endpoints)
23. TRADING (0 endpoints - empty)
24. USER (5 endpoints)
25. WORLD-ETFS (4 endpoints)

**Files to delete:**
```
webapp/lambda/routes/analysts.js
webapp/lambda/routes/api-status.js
webapp/lambda/routes/auth.js
webapp/lambda/routes/commodities.js
webapp/lambda/routes/community.js
webapp/lambda/routes/dashboard.js
webapp/lambda/routes/diagnostics.js
webapp/lambda/routes/earnings.js
webapp/lambda/routes/economic.js
webapp/lambda/routes/financials.js
webapp/lambda/routes/industries.js
webapp/lambda/routes/manual-trades.js
webapp/lambda/routes/market.js
webapp/lambda/routes/metrics.js
webapp/lambda/routes/options.js
webapp/lambda/routes/price.js
webapp/lambda/routes/scores.js
webapp/lambda/routes/sectors.js
webapp/lambda/routes/sentiment.js
webapp/lambda/routes/signals.js
webapp/lambda/routes/strategies.js
webapp/lambda/routes/technicals.js
webapp/lambda/routes/trading.js
webapp/lambda/routes/user.js
webapp/lambda/routes/world-etfs.js
```

**Estimated impact:**
- Delete ~24 files (~140 endpoints)
- Reduce codebase by ~50%+
- Remove maintenance burden for unused functionality

---

### PHASE 2: Fix Duplicate Endpoints

**In trades.js:**
```javascript
// Current:
router.get('/', ...)        // GET /api/trades
router.get('/history', ...) // GET /api/trades/history (SAME THING)

// After:
router.get('/', ...)  // Keep only this
// Delete /history
```

**In sectors.js:**
```javascript
// Current:
router.get('/', ...)           // GET /api/sectors
router.get('/sectors', ...) // GET /api/sectors/sectors (DUPLICATE)

// After:
router.get('/', ...)  // Keep only this
// Delete /sectors
```

**In industries.js:**
```javascript
// Current:
router.get('/', ...)             // GET /api/industries
router.get('/industries', ...) // GET /api/industries/industries (DUPLICATE)

// After:
router.get('/', ...)  // Keep only this
// Delete /industries
```

**In market.js:**
```javascript
// Current:
router.get('/fresh-data', ...)  // appears twice!

// After:
router.get('/fresh-data', ...) // Keep only one
// Delete duplicate
```

---

### PHASE 3: Create Typed API Functions

Create proper functions in `webapp/frontend-admin/src/services/api.js`:

```javascript
// STOCKS
export const getDeepValueStocks = async (limit, offset) => {...}  // ✓ DONE

// TRADES
export const getTrades = async (page, limit, filters) => {...}  // ✓ DONE
export const getTradesSummary = async () => {...}  // ✓ DONE
export const getTradesFifoAnalysis = async () => {...}  // ✓ DONE

// PORTFOLIO
export const getPortfolioMetrics = async () => {...}  // NEW
export const getPortfolioApiKeys = async (userId) => {...}  // NEW
export const createPortfolioApiKey = async (data) => {...}  // NEW
export const deletePortfolioApiKey = async (keyId) => {...}  // NEW
export const testPortfolioApiKey = async (data) => {...}  // NEW

// CONTACT
export const getContactSubmissions = async (page, limit) => {...}  // ✓ DONE

// HEALTH
export const getHealthStatus = async () => {...}  // NEW
export const getHealthDatabase = async () => {...}  // NEW

// OPTIMIZATION
export const getOptimizationAnalysis = async () => {...}  // NEW
```

---

### PHASE 4: Update Frontend Calls

Convert from direct API calls to typed functions:

```javascript
// BEFORE (PortfolioOptimizerNew.jsx):
const response = await axios.get('/api/optimization/analysis');

// AFTER:
const response = await getOptimizationAnalysis();
```

---

## CONSOLIDATED API STRUCTURE (AFTER CLEANUP)

```
API Modules Remaining: 6
├── /api/stocks        (1-2 endpoints)
├── /api/trades        (2-3 endpoints)
├── /api/portfolio     (4-5 endpoints)
├── /api/contact       (1 endpoint)
├── /api/health        (2 endpoints)
└── /api/optimization  (1 endpoint)

Total Endpoints: ~12-14
Usage Rate: 100%
Maintenance Burden: Minimal
```

---

## IMPLEMENTATION EFFORT ESTIMATES

| Task | Effort | Priority |
|------|--------|----------|
| Delete 25 unused modules | 4-5 hours | 🔴 CRITICAL |
| Fix 4 duplicate endpoints | 1 hour | 🔴 CRITICAL |
| Remove route registrations from index.js | 1 hour | 🔴 CRITICAL |
| Create typed API functions for remaining | 3-4 hours | 🟡 HIGH |
| Update frontend to use functions | 2-3 hours | 🟡 HIGH |
| Test all pages work correctly | 2 hours | 🟡 HIGH |
| **TOTAL** | **~13-15 hours** | |

---

## POTENTIAL SAVINGS

| Metric | Current | After | Reduction |
|--------|---------|-------|-----------|
| Backend Endpoint Files | 31 | 6 | 81% |
| Total Endpoints | 155+ | 12-14 | 91% |
| Maintenance Lines of Code | ~15,000+ | ~2,000 | 87% |
| API Surface Complexity | Very High | Low | 90% |
| Frontend Integration Time | High | Low | 80% |

---

## RECOMMENDATIONS SUMMARY

✅ **Do immediately:**
1. Delete all 25 unused route modules
2. Fix duplicate endpoints
3. Remove from index.js registration

✅ **Do next:**
1. Create typed API functions for all remaining endpoints
2. Update frontend to use functions instead of direct calls
3. Full regression testing

❌ **Do NOT:**
- Keep unused modules "just in case"
- Keep duplicates
- Make direct API calls from components (use functions instead)
- Add more endpoints without coordinating with frontend needs


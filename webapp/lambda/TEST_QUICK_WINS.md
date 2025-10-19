# Test Failures - Quick Wins Guide

## Current Status
- **Pass Rate:** 65.2% (2,192 of 3,360 tests)
- **Failure Rate:** 33.5% (1,126 tests failing)
- **Files Affected:** 158 of 223 test files

---

## 🎯 The Big 3 Quick Wins (Fix 80-90% of Failures)

### 🥇 #1: Assignment to Constant Variable
**Impact:** 612 tests (54% of all failures)
**Time:** 30 minutes
**Difficulty:** ⭐ Trivial

**The Problem:**
```javascript
const app = null;
beforeAll(() => {
  app = require("../../../server"); // ❌ TypeError!
});
```

**The Solution:**
```javascript
let app;
beforeAll(() => {
  app = require("../../../server"); // ✅ Works!
});
```

**9 Files to Fix:**
```
tests/integration/routes/strategyBuilder.integration.test.js
tests/integration/routes/alerts.integration.test.js
tests/integration/routes/backtest.integration.test.js
tests/integration/routes/positioning.integration.test.js
tests/integration/routes/recommendations.integration.test.js
tests/integration/routes/sectors.integration.test.js
tests/integration/routes/sentiment.integration.test.js
tests/integration/routes/signals.integration.test.js
tests/integration/routes/trades.integration.test.js
```

**Command to fix:**
```bash
# Search and replace in all files:
sed -i 's/const app = null;/let app;/g' tests/integration/routes/*.integration.test.js
```

---

### 🥈 #2: Missing `query` Mock
**Impact:** 396 tests (35% of all failures)
**Time:** 2-3 hours
**Difficulty:** ⭐⭐ Easy-Medium

**The Problem:**
```javascript
// File uses database.query() but doesn't mock it
ReferenceError: query is not defined
```

**The Solution:**
```javascript
// Add at top of test file:
jest.mock("../../utils/database", () => ({
  query: jest.fn(),
  getConnection: jest.fn(),
  closeDatabase: jest.fn()
}));

const { query } = require("../../utils/database");
```

**Top 10 Files (by impact):**
1. `tests/unit/routes/portfolio.test.js` - 98 tests
2. `tests/unit/routes/trades.test.js` - 75 tests
3. `tests/unit/utils/tradingModeHelper.test.js` - 40 tests
4. `tests/performance/api-load-testing.test.js` - 31 tests
5. `tests/integration/auth/api-key-integration.test.js` - 28 tests
6. `tests/integration/analytics/dashboard.test.js` - 26 tests
7. `tests/unit/routes/news.test.js` - 24 tests
8. `tests/integration/data-pipeline.integration.test.js` - 18 tests
9. `tests/integration/analytics/recommendations.test.js` - 17 tests
10. `tests/unit/utils/riskEngine.test.js` - 14 tests

**Strategy:** Fix highest-impact files first (top 5 covers 272 of 396 tests)

---

### 🥉 #3: Missing `req.connection.address()`
**Impact:** 338 tests (30% of all failures)
**Time:** 1-2 hours
**Difficulty:** ⭐⭐ Easy-Medium

**The Problem:**
```javascript
// Mock request missing connection.address()
TypeError: Cannot read properties of undefined (reading 'address')
```

**The Solution:**
```javascript
const mockRequest = {
  body: {},
  query: {},
  params: {},
  headers: {},
  connection: {
    address: jest.fn(() => ({ address: '127.0.0.1', port: 12345 }))
  }
};
```

**Top 10 Files (by impact):**
1. `tests/integration/middleware/security-headers.integration.test.js` - 41 tests
2. `tests/integration/errors/4xx-error-scenarios.integration.test.js` - 39 tests
3. `tests/integration/auth/auth-flow.integration.test.js` - 35 tests
4. `tests/integration/errors/5xx-server-errors.integration.test.js` - 30 tests
5. `tests/integration/middleware/responseFormatter-middleware.integration.test.js` - 27 tests
6. `tests/integration/middleware/errorHandler-middleware.integration.test.js` - 27 tests
7. `tests/integration/streaming/sse-streaming.integration.test.js` - 26 tests
8. `tests/integration/errors/malformed-request.integration.test.js` - 25 tests
9. `tests/integration/errors/timeout-handling.integration.test.js` - 20 tests
10. `tests/integration/services/cross-service-integration.test.js` - 19 tests

**Strategy:** Create reusable mock helper in test utils, apply to all files

---

## 🎁 Bonus Quick Wins (30-60 min work)

### #4: SecretsManagerClient (104 tests, 10 min)
```javascript
// Add to apiKeyService.test.js and economic.test.js:
jest.mock("@aws-sdk/client-secrets-manager", () => ({
  SecretsManagerClient: jest.fn(),
  GetSecretValueCommand: jest.fn()
}));
```

### #5: authenticateToken (78 tests, 20 min)
```javascript
// Add to 4 auth-related test files:
jest.mock("../../middleware/auth", () => ({
  authenticateToken: jest.fn((req, res, next) => next()),
  requireRole: jest.fn((role) => (req, res, next) => next()),
  optionalAuth: jest.fn((req, res, next) => next())
}));
```

### #6: FactorScoringEngine (42 tests, 15 min)
```javascript
// Add to screener.test.js and errorTracker.test.js:
jest.mock("../../utils/factorScoring", () => ({
  FactorScoringEngine: jest.fn().mockImplementation(() => ({
    calculateScore: jest.fn(),
    getFactors: jest.fn()
  }))
}));
```

---

## 📊 Expected Results

### After Fix #1 (30 min work):
- Pass rate: 65% → 83%
- Failing tests: 1,126 → 514
- **Impact:** 612 tests fixed

### After Fixes #1-2 (3-3.5 hours work):
- Pass rate: 65% → 94%
- Failing tests: 1,126 → ~200
- **Impact:** 1,008 tests fixed

### After Fixes #1-3 (4-6 hours work):
- Pass rate: 65% → 92-95%
- Failing tests: 1,126 → ~150-250
- **Impact:** 900-1,000 tests fixed

### After All 6 Fixes (6-8 hours work):
- Pass rate: 65% → 95%+
- Failing tests: 1,126 → <150
- **Impact:** 1,000+ tests fixed

---

## 🚀 Recommended Action Plan

**Phase 1: Critical (30 min) - DO THIS NOW**
1. Fix "Assignment to const" in 9 files
2. Run tests → expect 83% pass rate

**Phase 2: High Priority (2-3 hours)**
1. Add query mock to top 10 files (covers 271 tests)
2. Run tests → expect 90% pass rate
3. Add query mock to remaining 3 files
4. Run tests → expect 94% pass rate

**Phase 3: Cleanup (1-2 hours)**
1. Fix req.connection.address in top 10 files
2. Add bonus quick wins (#4-6)
3. Run tests → expect 95%+ pass rate

**Total Time:** 4-6 hours
**Total Impact:** 1,000+ tests fixed (89% → 65% → 95% pass rate improvement)

---

## 📝 Next Steps

1. Read this guide
2. Review detailed analysis in `TEST_FAILURE_ANALYSIS.md`
3. Start with Phase 1 (30 min)
4. Validate improvements with `npm test`
5. Continue to Phases 2-3 based on results

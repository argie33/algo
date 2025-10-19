# Test Failure Analysis - Top 3 Error Patterns

**Test Run Summary:** 659 failures out of 3,360 total tests (80.3% pass rate)

## TOP 3 MOST IMPACTFUL ERROR PATTERNS (Ranked by Quick-Win Potential)

---

### 1. MISSING AWS SDK MOCK IMPORTS
**Error Pattern:** `ReferenceError: SecretsManagerClient is not defined`

| Metric | Value |
|--------|-------|
| **Files Affected** | 1 |
| **Tests Failing** | 104 |
| **Total Impact** | 15.8% of all failures |
| **Example File** | `tests/unit/utils/apiKeyService.test.js` |

**Root Cause:**
```javascript
// Line 42 in apiKeyService.test.js
SecretsManagerClient.mockReturnValue(mockSecretsManager);
//  ^^^ Not imported - causes ReferenceError
```

The test mocks `@aws-sdk/client-secrets-manager` but never imports `SecretsManagerClient` or `CognitoJwtVerifier` classes that are referenced in the beforeEach() setup.

**Quick Fix (5 minutes):**
```javascript
// Add these imports after line 10:
const { SecretsManagerClient } = require("@aws-sdk/client-secrets-manager");
const { CognitoJwtVerifier } = require("aws-jwt-verify");
```

**Impact if Fixed:** 104 tests would pass (15.8% reduction in failures)

---

### 2. DATABASE QUERY MOCK RETURNING UNDEFINED
**Error Pattern:** `TypeError: Cannot read properties of undefined (reading 'rows')`

| Metric | Value |
|--------|-------|
| **Files Affected** | ~20 integration tests |
| **Tests Failing** | ~90+ |
| **Total Impact** | 13.7% of all failures |
| **Example Files** | `tests/integration/routes/recommendations.integration.test.js` (66 failures)<br>`tests/integration/utils/database-connection.integration.test.js` (44 failures) |

**Root Cause:**
Mock database query returns `undefined` instead of proper PostgreSQL result structure:
```javascript
// Current mock behavior
mockQuery.mockResolvedValue(undefined);
// Expected structure
mockQuery.mockResolvedValue({ rows: [], rowCount: 0 });
```

**Quick Fix (10 minutes):**
Update `__mocks__/utils/database.js` to return proper structure:
```javascript
const query = jest.fn().mockResolvedValue({
  rows: [],
  rowCount: 0,
  command: 'SELECT',
  fields: []
});
```

**Impact if Fixed:** ~90 tests would pass (13.7% reduction in failures)

---

### 3. AUTHENTICATION MIDDLEWARE BYPASS IN TESTS
**Error Pattern:** `Expected: 401, Received: 200` or `Expected: true (auth required), Received: false`

| Metric | Value |
|--------|-------|
| **Files Affected** | ~15 integration tests |
| **Tests Failing** | ~60-80 |
| **Total Impact** | 9-12% of all failures |
| **Example Files** | `tests/integration/routes/trades.integration.test.js` (40 failures)<br>`tests/integration/errors/4xx-error-scenarios.integration.test.js` (8 failures)<br>`tests/integration/routes/strategyBuilder.integration.test.js` (24 failures) |

**Root Cause:**
The `authenticateToken` middleware allows all requests through in test environment:
```javascript
// Current behavior in test mode
if (process.env.NODE_ENV === 'test') {
  req.user = { sub: 'test-user-123' };
  return next(); // Always passes!
}
```

**Quick Fix (15 minutes):**
Tests need to properly mock failed authentication:
```javascript
// In test setup
jest.mock('../../../middleware/auth', () => ({
  authenticateToken: (req, res, next) => {
    if (!req.headers.authorization) {
      return res.status(401).json({ error: 'Unauthorized' });
    }
    // ... validate token properly
  }
}));
```

**Impact if Fixed:** ~70 tests would pass (10.6% reduction in failures)

---

## COMBINED QUICK-WIN SUMMARY

| Fix | Time | Tests Fixed | % of Failures |
|-----|------|-------------|---------------|
| AWS SDK Imports | 5 min | 104 | 15.8% |
| Database Mock | 10 min | 90 | 13.7% |
| Auth Middleware | 15 min | 70 | 10.6% |
| **TOTAL** | **30 min** | **~264** | **40.1%** |

**Expected Result:** Fixing these 3 patterns would reduce failures from 659 to ~395, improving pass rate from 80.3% to **88.2%**

---

## FILES WITH MOST FAILURES (>40 tests each)

1. `tests/unit/utils/apiKeyService.test.js` - **104 failures** (AWS SDK imports)
2. `tests/unit/routes/portfolio.test.js` - **100 failures** (unknown pattern)
3. `tests/unit/middleware/auth.test.js` - **86 failures** (auth mock issues)
4. `tests/integration/routes/recommendations.integration.test.js` - **66 failures** (DB rows)
5. `tests/integration/utils/liveDataManager.test.js` - **64 failures** (unknown pattern)
6. `tests/unit/routes/performance.test.js` - **48 failures** (unknown pattern)
7. `tests/integration/utils/database-connection.integration.test.js` - **44 failures** (DB rows)
8. `tests/unit/routes/sectors.test.js` - **42 failures** (unknown pattern)
9. `tests/unit/routes/screener.test.js` - **42 failures** (unknown pattern)
10. `tests/integration/routes/trades.integration.test.js` - **40 failures** (auth bypass)

---

## RECOMMENDED PRIORITY

1. **IMMEDIATE (5 min):** Fix AWS SDK imports in apiKeyService.test.js → 104 tests pass
2. **HIGH (10 min):** Fix database mock structure → 90 tests pass
3. **MEDIUM (15 min):** Fix authentication middleware mocking → 70 tests pass

**Total time investment: 30 minutes for 40% failure reduction**

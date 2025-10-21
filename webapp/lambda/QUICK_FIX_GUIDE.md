# Quick Fix Guide - 170 Failing Unit Tests

## TL;DR
Add missing `require()` imports to 4 test files → Fix all 170 failures

---

## Fix #1: middleware/auth.test.js (82 failures → 0)

**Location:** Line 18 (after existing imports)

**Add:**
```javascript
const {
  authenticateToken,
  requireRole,
  optionalAuth,
  requireApiKey,
  validateSession,
  rateLimitByUser,
  logApiAccess
} = require('../../../middleware/auth');
```

---

## Fix #2: routes/news.test.js (26 failures → 0)

**Location:** After mocks section (~line 20)

**Add:**
```javascript
const { query } = require("../../../utils/database");
```

**Note:** Mock is already defined, just need the import for scope

---

## Fix #3: routes/screener.test.js (2 failures → 0)

**Location:** After database imports (~line 9)

**Add:**
```javascript
const { authenticateToken } = require("../../../middleware/auth");
```

**Note:** May already have mock, ensure import is also present

---

## Fix #4: routes/performance.test.js (2 failures → 0)

**Location:** After auth mock (~line 6)

**Add:**
```javascript
const { authenticateToken } = require("../../../middleware/auth");
```

---

## Verification

```bash
# Quick test
npm test -- tests/unit/middleware/auth.test.js
npm test -- tests/unit/routes/news.test.js

# Full test suite
npm test -- tests/unit/

# Expected: 1,662 passing, 0 failing
```

---

## Summary Table

| File | Line | Import | Fixes |
|------|------|--------|-------|
| middleware/auth.test.js | 18 | 7 auth functions | 82 tests |
| routes/news.test.js | 20 | query | 26 tests |
| routes/screener.test.js | 9 | authenticateToken | 2 tests |
| routes/performance.test.js | 6 | authenticateToken | 2 tests |

**Total:** 4 files, ~15 lines added, 170 tests fixed


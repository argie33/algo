# Test Failure Quick Fix Reference

## Problem Statement (30 seconds)
- 84 tests attempt real database initialization and hang for 200-800 seconds each
- 2 unit tests have incomplete mocks and hang for 600+ seconds each
- Total: 3.7-12.2 hours of test execution, 0-20% pass rate

## Solution (3 phases)

### Phase 1: Convert Integration Route Tests (CRITICAL)
**Time:** 4-6 hours | **Savings:** 6,700-27,000 seconds | **Impact:** 39-75%

Convert 34 files from this:
```javascript
const { initializeDatabase, closeDatabase } = require("../../../utils/database");
beforeAll(async () => {
  await initializeDatabase();  // ← WRONG - Real DB attempt
  app = require("../../../server");
});
```

To this:
```javascript
jest.mock("../../../utils/database", () => ({ query: jest.fn() }));
jest.mock("../../../middleware/auth", () => ({
  authenticateToken: jest.fn((req, res, next) => {
    req.user = { sub: "test-user-123" };
    next();
  }),
}));

const { query } = require("../../../utils/database");
beforeAll(() => {
  app = express();
  app.use(express.json());
  app.use("/api/sectors", sectorRouter);
});

beforeEach(() => {
  jest.clearAllMocks();
  query.mockImplementation((sql) => {
    if (sql.includes("sector")) {
      return Promise.resolve({ rows: [{ sector: "Tech" }] });
    }
    return Promise.resolve({ rows: [] }); // ← DEFAULT CASE CRITICAL
  });
});
```

**Files to Convert First:**
1. `/tests/integration/routes/sectors.integration.test.js` (218s) ← START HERE
2. `/tests/integration/routes/trades.integration.test.js` (200-300s)
3. `/tests/integration/routes/performance.integration.test.js` (200-300s)
4. Then apply to remaining 31 route tests

### Phase 2: Debug Slow Unit Tests (SECONDARY)
**Time:** 2-3 hours | **Savings:** 1,400+ seconds | **Impact:** 15%

Files:
- `/tests/unit/routes/trades.test.js` (842s - should be <1s)
- `/tests/unit/routes/performance.test.js` (623s - should be <1s)

Problem: Mock implementations incomplete, return undefined for unknown queries

Fix: Add comprehensive mock implementation:
```javascript
beforeEach(() => {
  jest.clearAllMocks();
  query.mockImplementation((sql, params) => {
    // Handle ALL expected query patterns
    if (sql.includes("stock_symbols")) {
      return Promise.resolve({ rows: [{ symbol: "AAPL" }] });
    }
    if (sql.includes("price_daily")) {
      return Promise.resolve({ rows: [{ price: 150.0 }] });
    }
    // DEFAULT CASE - CRITICAL
    return Promise.resolve({ rows: [] });
  });
});
```

### Phase 3: Fix Other Integration Tests (TERTIARY)
**Time:** 4-6 hours | **Savings:** 100-400 seconds | **Impact:** 5%

Same pattern as Phase 1 applied to:
- `/tests/integration/utils/*.test.js` (50+ files)
- `/tests/integration/services/*.test.js`
- `/tests/integration/middleware/*.test.js`
- All other dirs under `/tests/integration/`

## Quick Start

### Step 1: Verify The Problem
```bash
# Should take 200+ seconds (will timeout)
npm test -- tests/integration/routes/sectors.integration.test.js --verbose

# Should take 600+ seconds (will timeout)
npm test -- tests/unit/routes/performance.test.js --verbose
```

### Step 2: Start Phase 1
```bash
# 1. Copy one integration test to use as reference
cp tests/integration/routes/sectors.integration.test.js \
   tests/integration/routes/sectors.integration.test.js.backup

# 2. Convert to unit test pattern
# (Edit sectors.integration.test.js - see example above)

# 3. Verify it works now (<1 second)
npm test -- tests/integration/routes/sectors.integration.test.js --verbose

# 4. Repeat for 33 other route tests
```

### Step 3: Move to Phase 2
```bash
# Run slow unit tests individually
npm test -- tests/unit/routes/trades.test.js --verbose
npm test -- tests/unit/routes/performance.test.js --verbose

# Identify what SQL patterns they query for
grep -o "query(['\"]SELECT[^'\"]*['\"]" routes/trades.js | sort -u
grep -o "query(['\"]SELECT[^'\"]*['\"]" routes/performance.js | sort -u

# Add mock implementations for each pattern
```

### Step 4: Verify Results
```bash
# Run full suite (should be 5-8 minutes after all phases)
npm test 2>&1 | tail -50

# Check coverage is maintained
npm test -- --coverage

# Check specific suites
npm test -- tests/unit/routes/ --verbose
npm test -- tests/integration/routes/ --verbose
```

## Reference Examples

### Good Mock Pattern (alertstest.js)
```javascript
query.mockImplementation((sql, params) => {
  if (sql.includes('information_schema.tables')) {
    return Promise.resolve({ rows: [{ exists: true }] });
  }
  if (sql.includes('active_price_alerts')) {
    return Promise.resolve({
      rows: [{ id: 1, symbol: "AAPL", status: 'active' }]
    });
  }
  return Promise.resolve({ rows: [] }); // ← DEFAULT
});
```

### Bad Pattern (performance.test.js)
```javascript
// ❌ NO DEFAULT CASE - Returns undefined
query.mockResolvedValue(undefined);

// Routes hang waiting for undefined.rows to exist
```

### Database Init Pattern (Broken - 84 files)
```javascript
// ❌ NEVER DO THIS IN TESTS
beforeAll(async () => {
  await initializeDatabase();  // Tries real DB, times out
  app = require("../../../server");
});
```

## Key Files to Understand

| File | Purpose | Line | Problem |
|------|---------|------|---------|
| `/utils/database.js` | DB init logic | 242 | Attempts real connection in test |
| `/jest.config.js` | Jest config | 18 | testTimeout: 10000 (10s) |
| `/tests/unit/routes/alerts.test.js` | Good example | 32-70 | Proper mock implementation |
| `/tests/integration/routes/sectors.integration.test.js` | Broken example | 10-17 | Real DB init |

## Expected Timeline

| Phase | Duration | Savings | Status |
|-------|----------|---------|--------|
| **Current** | 3.7-12.2 hrs | - | Broken (tests timeout) |
| **After Phase 1** | 2.4-5 hrs | 6,700-27,000s | 39-75% improvement |
| **After Phase 2** | 2-4.6 hrs | +1,400s | 49-84% improvement |
| **After Phase 3** | 5-8 mins | +100-400s | 95%+ improvement |

## Common Mistakes to Avoid

### Mistake 1: Forgetting DEFAULT CASE
```javascript
// ❌ WRONG - Returns undefined for unknown queries
query.mockImplementation((sql) => {
  if (sql.includes("sector")) {
    return Promise.resolve({ rows: [] });
  }
  // NO DEFAULT - Routes hang
});

// ✅ RIGHT
query.mockImplementation((sql) => {
  if (sql.includes("sector")) {
    return Promise.resolve({ rows: [] });
  }
  return Promise.resolve({ rows: [] }); // DEFAULT
});
```

### Mistake 2: Missing jest.clearAllMocks()
```javascript
// ❌ WRONG - Mock state persists between tests
beforeEach(() => {
  query.mockImplementation(...);
});

// ✅ RIGHT
beforeEach(() => {
  jest.clearAllMocks();
  query.mockImplementation(...);
});
```

### Mistake 3: Not Mocking Auth Middleware
```javascript
// ❌ WRONG - Tests fail with 401 Unauthorized
// (forgot to mock authentication)

// ✅ RIGHT
jest.mock("../../../middleware/auth", () => ({
  authenticateToken: jest.fn((req, res, next) => {
    req.user = { sub: "test-user-123" };
    next();
  }),
}));
```

## Success Metrics

After all phases, you should see:

```
PASS  150 tests
Test Suites: 10 passed, 10 total
Tests: 150 passed, 150 total
Snapshots: 0 total
Time: 5-8 seconds
```

NOT:

```
TIMEOUT  integration tests
1 test taking 842 seconds
34 tests timing out at 10 seconds each
Total: 3.7-12.2 hours
```

## Debugging If Stuck

### Test Still Hangs (600+ seconds)
**Cause:** Mock returns undefined for some query pattern
**Fix:** Add more if statements to mockImplementation
```javascript
// Find what query hangs:
grep -r "query" routes/trades.js

// Add case for each:
if (sql.includes("pattern1")) return Promise.resolve({ rows: [] });
if (sql.includes("pattern2")) return Promise.resolve({ rows: [] });
return Promise.resolve({ rows: [] }); // DEFAULT
```

### Tests Fail With 401
**Cause:** Auth middleware not mocked
**Fix:** Add jest.mock() for auth middleware (see examples above)

### Tests Fail With Missing Table
**Cause:** Query mock doesn't handle schema validation
**Fix:** Add case for table checks:
```javascript
if (sql.includes("information_schema.tables")) {
  return Promise.resolve({ rows: [{ exists: true }] });
}
```

## Success Checklist

- [ ] Phase 1a: Convert sectors.integration.test.js (218s → <1s)
- [ ] Phase 1b: Verify conversion works
- [ ] Phase 1c: Apply pattern to 33 other route tests
- [ ] Phase 2a: Debug trades.test.js (842s → <1s)
- [ ] Phase 2b: Debug performance.test.js (623s → <1s)
- [ ] Phase 3: Fix 50+ utility/service/middleware tests
- [ ] Final: Run full suite in 5-8 minutes

## Support Resources

- Full analysis: `TEST_ANALYSIS_SUMMARY.md`
- File reference: `CRITICAL_TEST_FILES.txt`
- Examples: `/tests/unit/routes/alerts.test.js`
- Database util: `/utils/database.js` (lines 242-250)


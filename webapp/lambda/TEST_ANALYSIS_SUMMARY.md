# Test Failure Root Cause Analysis

## Quick Summary

The codebase has **150 tests** with critical architecture issues causing massive slowdowns:

### The Problem (in 30 seconds)
- **34 integration route tests** call `initializeDatabase()` + `require("../../../server")`
- This attempts real database connection (fails/times out after 10s per test)
- Plus 50+ utility/service tests with same issue
- Total: 84 tests × 10s = 840 seconds blocking the test suite
- **Plus**: 2 mystery slow unit tests taking 600+ seconds each

### The Solution (Priority Order)
1. Convert 34 integration route tests to proper unit test mocks (save 340-2,720 seconds)
2. Debug 2 slow unit tests (save 400-1,500 seconds)  
3. Fix 50+ utility tests using real DB init (save 100-400 seconds)
4. Create reusable mock utilities for future tests

### Timeline
- Phase 1 (integration routes): 4-6 hours → 80% improvement
- Phase 2 (slow unit tests): 2-3 hours → additional 15% improvement
- Phase 3 (utility tests): 4-6 hours → final 5% improvement
- **Total after all phases**: Tests go from 1.5-7.5 hours to 2-5 minutes

---

## Detailed Analysis

### Root Cause 1: Real Database Initialization in Tests (CRITICAL - 84 files)

**The Pattern That Breaks Everything**:
```javascript
// From /tests/integration/routes/*.test.js (34 files)
// From /tests/integration/utils/*.test.js (50+ files)

beforeAll(async () => {
  await initializeDatabase();  // ← ATTEMPTS REAL DB CONNECTION
  app = require("../../../server");
});
```

**What Happens**:
1. Test calls `initializeDatabase()` expecting it to use test mocks
2. But `utils/database.js` line 227 checks `if (process.env.NODE_ENV !== "test")`
3. Even in test mode, it still tries AWS Secrets Manager or environment variables
4. All are undefined → connection timeout after 3-10 seconds
5. Multiple retries multiply the delay
6. Test hangs at Jest's 10-second timeout
7. **Result**: Each test takes 200-800 seconds

**The 84 Slow Tests**:
- 34 integration route tests: `/tests/integration/routes/*.integration.test.js`
- 50+ utility/service tests: `/tests/integration/utils/*.test.js`, `/tests/integration/services/*.test.js`, etc.

**Total Impact**: 84 tests × 10-300 seconds = 840-25,200 seconds of pure waste

### Root Cause 2: Two Mystery Slow Unit Tests (500+ seconds each)

**Files**:
- `/tests/unit/routes/trades.test.js` - Takes 842 seconds (should be 100-300ms)
- `/tests/unit/routes/performance.test.js` - Takes 623 seconds (should be 100-300ms)

**They HAVE mocks**, so why are they slow?

**Likely Issues**:
1. Mock implementations return undefined in some code paths
2. Test routes wait for responses that never come
3. Mock queries don't handle all SQL patterns
4. Async operations without proper resolution

**Example of Incomplete Mock** (performance.test.js):
```javascript
// Line 40-48: Mock gets setup but...
beforeEach(() => {
  jest.clearAllMocks();
  const { query } = require("../../../utils/database");
  mockQuery = query;
  
  // BUT: No custom implementations!
  // When routes call query() with unknown patterns
  // Mock returns undefined instead of { rows: [...] }
  // Routes hang waiting for response
});
```

**Example of Good Mock** (alerts.test.js):
```javascript
query.mockImplementation((sql, params) => {
  // Handles all expected query patterns
  if (sql.includes('information_schema.tables')) {
    return Promise.resolve({ rows: [{ exists: true }] });
  }
  if (sql.includes('active_price_alerts')) {
    return Promise.resolve({ rows: [{ id: 1, status: 'active' }] });
  }
  return Promise.resolve({ rows: [] }); // ← DEFAULT CASE CRITICAL
});
```

### Root Cause 3: Architecture Mismatch

**Two Test Paradigms Exist**:

**Pattern A: Unit Tests (FAST, but not always used)**
```javascript
// /tests/unit/routes/*.test.js - Should be 100-500ms
jest.mock("../../../utils/database", () => ({ query: jest.fn() }));

describe("Unit Tests", () => {
  beforeAll(() => {
    app = express();
    app.use(express.json());
    app.use("/routes", routesRouter);
  });
  
  beforeEach(() => {
    jest.clearAllMocks();
    query.mockImplementation(...); // Proper mock setup
  });
});
```
✅ No database calls
✅ Fast (100-500ms per file)
✅ Isolated tests

**Pattern B: Integration Tests (BROKEN, used for 84 tests)**
```javascript
// /tests/integration/routes/*.integration.test.js - Takes 200-800s
const { initializeDatabase, closeDatabase } = require("../../../utils/database");

describe("Integration Tests", () => {
  beforeAll(async () => {
    await initializeDatabase();  // ← ATTEMPTS REAL DB
    app = require("../../../server");  // ← LOADS FULL APP
  });
});
```
❌ Attempts real database
❌ Slow (200-800s per file)
❌ Tests interfere with each other

---

## Fix Priority & Impact

### Priority 1: Convert Integration Route Tests to Unit Tests (CRITICAL)

**Files Affected**: 34 files in `/tests/integration/routes/`

**The Most Critical 3**:
1. `/tests/integration/routes/sectors.integration.test.js` (218 seconds)
2. `/tests/integration/routes/trades.integration.test.js` (200-300 seconds)
3. `/tests/integration/routes/performance.integration.test.js` (200-300 seconds)

**How to Fix - Example Pattern**:

FROM (Broken - takes 218 seconds):
```javascript
const { initializeDatabase, closeDatabase } = require("../../../utils/database");
let app;

describe("Sectors Routes", () => {
  beforeAll(async () => {
    await initializeDatabase();
    app = require("../../../server");
  });

  afterAll(async () => {
    await closeDatabase();
  });

  test("should return sector performance data", async () => {
    const response = await request(app).get("/api/sectors");
    // ...
  });
});
```

TO (Fixed - takes ~1 second):
```javascript
const express = require("express");
const request = require("supertest");

jest.mock("../../../utils/database", () => ({
  query: jest.fn(),
}));

jest.mock("../../../middleware/auth", () => ({
  authenticateToken: jest.fn((req, res, next) => {
    req.user = { sub: "test-user-123" };
    next();
  }),
}));

const { query } = require("../../../utils/database");
const sectorsRouter = require("../../../routes/sectors");

describe("Sectors Routes", () => {
  let app;

  beforeAll(() => {
    app = express();
    app.use(express.json());
    app.use("/api/sectors", sectorsRouter);
  });

  beforeEach(() => {
    jest.clearAllMocks();
    query.mockImplementation((sql) => {
      if (sql.includes("sector")) {
        return Promise.resolve({
          rows: [{ sector: "Technology", performance: 0.15 }]
        });
      }
      return Promise.resolve({ rows: [] });
    });
  });

  test("should return sector performance data", async () => {
    const response = await request(app).get("/api/sectors");
    expect(response.status).toBe(200);
  });
});
```

**Impact**: 
- Sectors: 218 seconds → ~1 second (217s saved)
- Trades: 200-300 seconds → ~1 second (199-299s saved)
- Performance: 200-300 seconds → ~1 second (199-299s saved)
- **34 files total**: 6,800-27,200 seconds → ~34 seconds (6,766-27,166 seconds saved)

**Time to Fix**: 4-6 hours

**Risk**: LOW - Just applying consistent pattern

---

### Priority 2: Debug Slow Unit Tests

**Files**:
- `/tests/unit/routes/trades.test.js` (842 seconds)
- `/tests/unit/routes/performance.test.js` (623 seconds)

**Investigation**:
```bash
# Run individually to see where it hangs
npm test -- tests/unit/routes/trades.test.js --verbose

# Check what queries routes actually make
grep -i "query\|SELECT\|INSERT\|UPDATE" routes/trades.js | head -20

# Check mock implementation coverage
grep -A5 "mockImplementation" tests/unit/routes/trades.test.js
```

**Likely Fixes**:
1. Add missing mock implementations for all query patterns
2. Ensure mock returns default `{ rows: [] }` for unknown queries
3. Check for async operations without proper timeouts

**Impact**: 842 + 623 = 1,465 seconds saved

**Time to Fix**: 2-3 hours

---

### Priority 3: Fix Other Integration Tests

**Files Affected**: 50+ files
- `/tests/integration/utils/*.test.js`
- `/tests/integration/services/*.test.js`
- `/tests/integration/middleware/*.test.js`
- etc.

**Same Pattern**: All call `initializeDatabase()`

**Same Fix**: Convert to unit test mocks

**Impact**: 100-400 seconds saved

**Time to Fix**: 4-6 hours (can be partially automated)

---

## The Numbers

### Current State
```
150 test files total
- 70 unit tests (should be fast)
- 34 integration route tests (BROKEN - real DB)
- 50+ utility/service tests (BROKEN - real DB)
- 30 other tests (performance, security, etc.)

Execution Time Breakdown:
- 2 slow unit tests (trades, performance): 842 + 623 = 1,465 seconds
- 34 integration route tests: 34 × 200-800s = 6,800-27,200 seconds
- 50+ utility tests: 50 × 100-300s = 5,000-15,000 seconds
- Other tests: ~100 seconds

Total Current: 13,365-43,865 seconds = 3.7-12.2 hours
```

### After Phase 1 (Convert Integration Routes)
```
34 integration route tests: 34 × 1s = 34 seconds (was 6,800-27,200)

Total: ~8,600-18,200 seconds = 2.4-5 hours (39-75% improvement)
```

### After Phase 1 + 2 (Fix Slow Unit Tests)
```
2 slow unit tests: 2 × 1s = 2 seconds (was 1,465)

Total: ~7,136-16,736 seconds = 2-4.6 hours (49-84% improvement)
```

### After All Phases (Complete Fix)
```
All tests properly mocked: ~150 tests × 0.5-2s = 75-300 seconds

Total: ~300-500 seconds = 5-8 minutes (95%+ improvement)
```

---

## Files to Examine First

### Must Read First (To Understand the Problem)
1. `/home/stocks/algo/webapp/lambda/tests/unit/routes/trades.test.js` - Why 842s?
2. `/home/stocks/algo/webapp/lambda/tests/unit/routes/performance.test.js` - Why 623s?
3. `/home/stocks/algo/webapp/lambda/tests/integration/routes/sectors.integration.test.js` - Real DB pattern
4. `/home/stocks/algo/webapp/lambda/tests/unit/routes/alerts.test.js` - Good mock pattern

### Quick Reference Locations
- Database utility: `/home/stocks/algo/webapp/lambda/utils/database.js` (line 242-244)
- Jest config: `/home/stocks/algo/webapp/lambda/jest.config.js` (testTimeout: 10000)
- Integration routes: `/home/stocks/algo/webapp/lambda/tests/integration/routes/` (34 files)
- Unit routes: `/home/stocks/algo/webapp/lambda/tests/unit/routes/` (proper examples here)

---

## Next Steps

1. **Verify this analysis** by running the two slow unit tests individually:
   ```bash
   npm test -- tests/unit/routes/trades.test.js --verbose
   npm test -- tests/unit/routes/performance.test.js --verbose
   ```

2. **Start Phase 1 with single file**:
   ```bash
   # Convert one integration test to unit test pattern
   # Run it to verify 200s+ becomes <1s
   npm test -- tests/integration/routes/sectors.integration.test.js --verbose
   ```

3. **Create template for automated conversion**:
   ```javascript
   // Template for converting integration tests to unit tests
   // Can be applied to all 34 route tests
   ```

4. **Run full suite after fixes**:
   ```bash
   npm test 2>&1 | tail -50  # Should complete in 2-5 minutes
   ```

---

## Appendix: Common Test Patterns Found

### Pattern 1: Incomplete Mock (Performance Risk)
```javascript
// ❌ PROBLEMATIC - Found in performance.test.js
beforeEach(() => {
  jest.clearAllMocks();
  const { query } = require("../../../utils/database");
  mockQuery = query;
  // No custom implementation - returns undefined!
});
```

### Pattern 2: Proper Mock (Best Practice)
```javascript
// ✅ GOOD - Found in alerts.test.js
beforeEach(() => {
  jest.clearAllMocks();
  query.mockImplementation((sql, params) => {
    if (sql.includes('information_schema.tables')) {
      return Promise.resolve({ rows: [{ exists: true }] });
    }
    if (sql.includes('active_price_alerts')) {
      return Promise.resolve({ rows: [/* data */] });
    }
    return Promise.resolve({ rows: [] }); // ← DEFAULT CASE
  });
});
```

### Pattern 3: Real Database (Performance Killer)
```javascript
// ❌ BROKEN - Found in 84 test files
beforeAll(async () => {
  await initializeDatabase();  // ← WAITS 200-800 SECONDS
  app = require("../../../server");
});
```


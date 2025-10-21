# Test Fix Quick Reference

## The Problem (30-second version)

Jest is configured for REAL database testing (production mode):
```javascript
// jest.config.js
setupFilesAfterEnv: ["<rootDir>/jest.setup.js"],  // Initializes REAL DB
clearMocks: false,                                 // Doesn't clear mocks
```

But unit tests try to MOCK the database:
```javascript
// signals.test.js, calendar.test.js, etc.
jest.mock("../../../utils/database", () => ({
  query: jest.fn()  // This mock is ignored!
}))
```

Result: Real database connection attempted → tests fail

---

## The Solution (Priority Order)

### 1. FIX jest.config.js (5 minutes)

**File**: `/home/stocks/algo/webapp/lambda/jest.config.js`

**Change**:
```javascript
// ADD THIS AFTER testEnvironment:
testEnvironment: "node",

// CHANGE THIS:
// FROM:
setupFilesAfterEnv: ["<rootDir>/jest.setup.js"],
testTimeout: 60000,
maxWorkers: 1,
clearMocks: false,
resetMocks: false,
restoreMocks: false,

// TO:
setupFilesAfterEnv: process.env.TEST_ENV === 'integration' ? ["<rootDir>/jest.setup.js"] : [],
testTimeout: process.env.TEST_ENV === 'integration' ? 60000 : 5000,
maxWorkers: process.env.TEST_ENV === 'integration' ? 1 : 4,
clearMocks: process.env.TEST_ENV !== 'integration',
resetMocks: process.env.TEST_ENV !== 'integration',
restoreMocks: process.env.TEST_ENV !== 'integration',
```

**Rationale**: Different settings for unit tests (mocked) vs integration tests (real DB)

---

### 2. FIX database.test.js (10 minutes)

**File**: `/home/stocks/algo/webapp/lambda/tests/unit/utils/database.test.js`

**Change**: Add proper cleanup in beforeEach
```javascript
beforeEach(async () => {
  jest.clearAllMocks();
  
  // CRITICAL: Reset database module cache to use mocks
  delete require.cache[require.resolve("../../../utils/database")];
  
  originalEnv = { ...process.env };
  // Setup successful Pool and client mocks BEFORE closing database
  mockPool.connect.mockResolvedValue(mockClient);
  // ... rest of setup
```

**Why**: Forces reimport of database module after mocks are defined

---

### 3. FIX signals.test.js (15 minutes)

**File**: `/home/stocks/algo/webapp/lambda/tests/unit/routes/signals.test.js`

**Change**: Replace sequential mocks with pattern matching
```javascript
// BEFORE (Lines 88-126):
mockQuery.mockResolvedValueOnce({ rows: [...schema...] });
mockQuery.mockResolvedValueOnce({ rows: [...data...] });
mockQuery.mockResolvedValueOnce({ rows: [{ total: 1 }] });

// AFTER:
mockQuery.mockImplementation((sql, params) => {
  // Schema introspection query
  if (sql.includes("information_schema.columns")) {
    return Promise.resolve({
      rows: [
        { column_name: "id" },
        { column_name: "symbol" },
        // ... all columns
      ]
    });
  }
  // Data query
  if (sql.includes("WHERE signal") && sql.includes("BUY")) {
    return Promise.resolve({
      rows: [{
        symbol: "AAPL",
        signal: "BUY",
        close: 150.0,
        // ... rest of row
      }]
    });
  }
  // Count query
  if (sql.includes("COUNT(*)")) {
    return Promise.resolve({ rows: [{ total: 1 }] });
  }
  return Promise.resolve({ rows: [] });
});
```

**Why**: Sequential mocks fail when real DB attempts different queries first

---

### 4. FIX apiKeyService.test.js (20 minutes)

**File**: `/home/stocks/algo/webapp/lambda/tests/unit/utils/apiKeyService.test.js`

**Change**: Add state cleanup
```javascript
beforeEach(() => {
  jest.clearAllMocks();
  originalEnv = { ...process.env };
  
  // NEW: Get service instance and reset state
  const service = __getServiceInstance();
  service.encryptionKey = null;
  service.jwtVerifier = null;
  service.circuitBreaker = { failures: 0, lastFailure: null, isOpen: false };
  service.jwtCircuitBreaker = { failures: 0, lastFailure: null, isOpen: false };
  
  // Set test environment
  process.env.NODE_ENV = "test";
  process.env.JWT_SECRET = "test-secret";
  
  // ... rest of setup (unchanged)
```

**Why**: Service maintains state from jest.setup.js initialization

---

### 5. FIX calendar.test.js (5 minutes)

**File**: `/home/stocks/algo/webapp/lambda/tests/unit/routes/calendar.test.js`

**Change**: Add database mock at top, ensure query responses match structure
```javascript
// AFTER Line 3, ADD:
const express = require("express");
const request = require("supertest");

// CRITICAL: Mock BEFORE any other code
const mockDatabase = {
  query: jest.fn().mockResolvedValue({ rows: [], rowCount: 0 }),
  closeDatabase: jest.fn(),
  initializeDatabase: jest.fn(),
  getPool: jest.fn(),
  transaction: jest.fn(),
  healthCheck: jest.fn(),
};

jest.mock("../../../utils/database", () => mockDatabase);

// Then rest of imports as-is...
```

**Why**: Mocks must be active before route imports

---

## Verification Commands

After making changes, run:

```bash
# 1. Test unit tests only
TEST_ENV=unit npm test -- database.test.js

TEST_ENV=unit npm test -- signals.test.js

TEST_ENV=unit npm test -- apiKeyService.test.js

TEST_ENV=unit npm test -- calendar.test.js

# 2. Run all unit tests
TEST_ENV=unit npm test

# 3. Verify integration tests still work
TEST_ENV=integration npm test -- tests/integration/

# 4. Run full test suite
npm test
```

---

## File-by-File Change Summary

| File | Line # | Change | Why |
|------|--------|--------|-----|
| jest.config.js | 24-36 | Add TEST_ENV conditionals | Skip real DB for unit tests |
| database.test.js | 63-77 | Add module cache clear | Force mock usage |
| signals.test.js | 88-126 | Replace sequential with pattern match | Real DB queries don't match |
| apiKeyService.test.js | 34-39 | Add service state reset | Service singleton from jest.setup |
| calendar.test.js | 3-11 | Reorganize mock definition | Ensure mocks active before route |

---

## Success Indicators

After fixes, you should see:
- ✓ database.test.js: 15+ tests pass
- ✓ signals.test.js: 30+ tests pass  
- ✓ apiKeyService.test.js: 50+ tests pass
- ✓ calendar.test.js: 10+ tests pass

No database connection errors in output

---

## If Something Still Fails

1. Check if TEST_ENV variable is set:
   ```bash
   echo $TEST_ENV
   TEST_ENV=unit npm test -- <test-file>  # Should be set
   ```

2. Verify mock is active:
   ```bash
   npm test -- --verbose <test-file> 2>&1 | grep "mock\|Mock"
   ```

3. Check if database module was reloaded:
   ```bash
   npm test -- --verbose <test-file> 2>&1 | grep "module cache"
   ```

4. Compare with working test (health.test.js):
   ```bash
   diff health.test.js <failing-test>.js
   ```

---

## Common Mistakes to Avoid

❌ **DON'T**: Use both jest.mock() AND real database in same test
```javascript
jest.mock("../../../utils/database", () => ({ ... }));
// Then in jest.setup.js:
await initializeDatabase();  // Conflict!
```

✅ **DO**: Choose one - either mock or real DB per test run
```bash
TEST_ENV=unit npm test    # Uses mocks
TEST_ENV=integration npm test  # Uses real DB
```

---

❌ **DON'T**: Forget to reset module cache
```javascript
// Mock won't be used if module already cached
jest.mock("../../../utils/database", () => ({ ... }));
const db = require("../../../utils/database"); // Gets OLD module!
```

✅ **DO**: Clear cache before importing
```javascript
delete require.cache[require.resolve("../../../utils/database")];
const db = require("../../../utils/database"); // Gets FRESH module with mocks
```

---

❌ **DON'T**: Use sequential mocks without validation
```javascript
mockQuery.mockResolvedValueOnce({ rows: [...] });  // Queue 1
mockQuery.mockResolvedValueOnce({ rows: [...] });  // Queue 2
// If real DB makes different queries first, queues are wrong!
```

✅ **DO**: Match on query patterns
```javascript
mockQuery.mockImplementation((sql, params) => {
  if (sql.includes("information_schema")) return {...};
  if (sql.includes("WHERE")) return {...};
  // Always handles all query types
});
```

---

## Estimated Time to Fix

- jest.config.js: 5 min
- database.test.js: 10 min
- signals.test.js: 15 min
- apiKeyService.test.js: 20 min
- calendar.test.js: 5 min
- **Testing & validation: 20 min**

**Total: ~75 minutes**


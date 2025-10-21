# Test Failure Analysis Report

## Executive Summary

The failing test files have a **critical architectural mismatch**:
- Tests are written to mock the database (unit test patterns)
- Jest configuration is set up for integration testing with the REAL database
- Result: Mocks are created but never used; code tries to connect to real database

## Files Analyzed

1. **signals.test.js** - Route tests with database mocks
2. **database.test.js** - Database utility tests with pg Pool mocks
3. **apiKeyService.test.js** - API key service tests with crypto/database mocks
4. **calendar.test.js** - Calendar route tests with database mocks

Plus reference files:
- **health.test.js** - Successful pattern (working tests)
- **auth.test.js** - Successful middleware test pattern
- **logger.test.js** - Successful utility test pattern

---

## Root Cause Analysis

### Jest Configuration Issue (jest.config.js)

```javascript
// CURRENT CONFIGURATION - Integration Testing Mode
setupFilesAfterEnv: ["<rootDir>/jest.setup.js"],  // Initializes REAL database
testTimeout: 60000,                               // For real DB queries
maxWorkers: 1,                                    // Serial execution
clearMocks: false,                                // Don't clear real connections
resetMocks: false,                                // Don't reset real functions
restoreMocks: false,                              // Don't restore real state
```

**Problem**: Jest setup file initializes REAL database connection, but unit tests mock database functions. The real DB initialization happens first, then mocks are ignored.

### Test File Pattern Mismatch

**signals.test.js Pattern** (Lines 8-12):
```javascript
const mockQuery = jest.fn();
jest.mock("../../../utils/database", () => ({
  query: mockQuery
}))
```

**Calendar.test.js Pattern** (Lines 4-11):
```javascript
jest.mock("../../../utils/database", () => ({
  query: jest.fn().mockResolvedValue({ rows: [], rowCount: 0 }),
  closeDatabase: jest.fn(),
  // ... etc
}));
```

**Expected by jest.setup.js** (jest.setup.js:40-50):
```javascript
// Initializes REAL database - expects NO mocks
const { initializeDatabase } = require('./utils/database');
await initializeDatabase();
```

---

## Common Failure Patterns by File

### 1. signals.test.js Failures

**Mock Pattern Used**:
- Single `mockQuery` function defined at module level
- Used with `.mockResolvedValueOnce()` sequentially
- Expects schema introspection queries followed by data queries

**Failure Pattern**:
```
✓ Should reject /api/signals/daily         PASS (no DB call)
✗ Should return formatted buy signals      FAIL (DB connection error)
   - Reason: Mock query never called
   - Actual: Route makes real DB connection attempt
```

**Mock Issues**:
- Line 89: `mockQuery.mockResolvedValueOnce()` sets up queue
- But route code calls real `query()` not the mock
- Schema introspection expects 3 sequential calls, but real DB has different structure

**Correct Pattern** (from health.test.js):
```javascript
const { query, initializeDatabase, getPool, healthCheck } = require('../../../utils/database');
// ... then use query directly:
query.mockResolvedValue({ rows: [], rowCount: 0 });
```

### 2. database.test.js Failures

**Mock Pattern Used**:
- Extensive mock setup at top (mockPool, mockClient objects)
- `jest.mock("pg")` to replace entire pg module
- `mockPoolConstructor.mockImplementation()` to return fake pool

**Failure Pattern**:
```
✗ Should initialize database          FAIL
   - Reason: Real pg connection attempted
   - Error: Cannot connect to localhost:5432
```

**Mock Issues**:
- mockPool/mockClient created but then `closeDatabase()` called (line 77)
- `closeDatabase()` uses real pool instance set by jest.setup.js
- Real pool takes precedence over module mock

**Correct Pattern**:
- pg mock must be set BEFORE jest.setup.js runs
- OR tests need setupFilesAfterEnv modified
- Database module maintains internal state that jest.setup.js controls

### 3. apiKeyService.test.js Failures

**Mock Pattern Used**:
- 8 separate jest.mock() calls at top
- Mock AWS SDK, crypto, database
- Complex setup with mockSecretsManager and mockJwtVerifier

**Failure Pattern**:
```
✗ Should store API key successfully   FAIL
   - Reason: mockQuery not intercepting calls
   - Error: Database connection failed
```

**Mock Issues**:
- Line 6: `jest.mock("../../../utils/database")`
- But database already initialized by jest.setup.js with REAL connection
- Database module singleton already instantiated
- Mock happens after initialization

**Correct Pattern**:
- Mock before jest.setup.js runs
- OR reinitialize mocked database before tests
- Service instance creation must use mocked dependencies

### 4. calendar.test.js Failures

**Mock Pattern Used**:
- Cleaner pattern than signals.test.js
- Mocks database with default empty responses
- Uses `query.mockResolvedValue()` per test

**Failure Pattern**:
```
✓ Should return calendar info         PASS (no DB call needed)
✗ Should return earnings calendar     FAIL (DB connection error)
   - Reason: mock() in calendar is last, but DB already connected
```

**Mock Issues**:
- Mock defined correctly (line 4-11)
- But routes still connect to real database
- Real pool already initialized by jest.setup.js

---

## Successful Test Patterns (Reference)

### health.test.js (WORKING)
```javascript
// 1. Mock FIRST
jest.mock("../../../utils/database", () => ({
  query: jest.fn().mockResolvedValue({ rows: [], rowCount: 0 }),
  initializeDatabase: jest.fn(),
  getPool: jest.fn(),
  healthCheck: jest.fn(),
}));

// 2. Import mocked functions
const { query, initializeDatabase, getPool, healthCheck } = require('../../../utils/database');

// 3. Import route AFTER mocking
const healthRoutes = require("../../../routes/health");

// 4. Use mocks in tests
beforeEach(() => {
  jest.clearAllMocks();
  // Mock responses
  initializeDatabase.mockResolvedValue();
  healthCheck.mockResolvedValue({ status: "healthy" });
});
```

**Why It Works**:
- Mock happens before route import
- Route code uses mocked database
- No real database connection attempted
- jest.setup.js still runs but isn't used by unit tests

### Key Difference: Route doesn't directly use database

```javascript
// health.test.js routes simple success path
// Doesn't query database directly in unit tests
// Uses initializeDatabase() mock which succeeds immediately
```

---

## Mock Pattern Issues Summary

| Issue | signals.test.js | database.test.js | apiKeyService.test.js | calendar.test.js |
|-------|-----------------|------------------|----------------------|------------------|
| Mock defined before import | ✓ | ✓ | ✓ | ✓ |
| Real DB connected first | ✗ FAIL | ✗ FAIL | ✗ FAIL | ✗ FAIL |
| Mock using correct pattern | Partial | Complex | Complex | ✓ |
| Sequential mock setup | ✓ | ✓ | ✓ | Partial |
| Routes import before mock | ✗ BUG | ✗ BUG | ✗ BUG | ✓ |
| Reset mocks properly | ✓ | ✓ | ✓ | ✓ |
| Mock responses realistic | Partial | ✓ | ✓ | ✓ |

---

## Fixes Needed (Priority Order)

### Priority 1: CRITICAL - Jest Configuration Fix
**Impact**: Unblocks all remaining tests
**Complexity**: Low
**File**: jest.config.js

Current problem: jest.setup.js initializes REAL database before tests run

**Solution**:
Option A - Use separate jest config for unit tests
Option B - Modify jest.setup.js to detect test type
Option C - Skip setup file for unit tests

```javascript
// jest.config.js modification needed:
setupFilesAfterEnv: process.env.TEST_TYPE !== 'unit' ? ["<rootDir>/jest.setup.js"] : undefined,
testTimeout: process.env.TEST_TYPE === 'unit' ? 5000 : 60000,
maxWorkers: process.env.TEST_TYPE === 'unit' ? undefined : 1,
clearMocks: process.env.TEST_TYPE === 'unit' ? true : false,
```

### Priority 2: HIGH - signals.test.js
**Impact**: Most complex test file
**Complexity**: Medium
**Issues**:
- Uses sequential mockQuery setup (fragile)
- Schema introspection mocking needs proper query matching
- Routes make real DB calls despite mocks

**Fixes**:
1. Ensure database mock is intercepted before route imports
2. Add matcher for schema queries
3. Validate sequential mock setup is exhaustive

### Priority 3: HIGH - database.test.js
**Impact**: Core utility tests
**Complexity**: High
**Issues**:
- pg module mock too late in lifecycle
- closeDatabase() conflicts with real state
- Module maintains singleton state

**Fixes**:
1. Reset module cache before mocking pg
2. Prevent jest.setup.js from initializing during database tests
3. Mock pg module in setupFilesAfterEnv instead of test file

### Priority 4: MEDIUM - apiKeyService.test.js
**Impact**: Security/encryption tests
**Complexity**: High
**Issues**:
- 8 dependent mocks required
- Service singleton keeps real state
- Crypto mocks complex

**Fixes**:
1. Mock all dependencies before service import
2. Clear service instance state in beforeEach
3. Ensure __getServiceInstance() returns clean state

### Priority 5: MEDIUM - calendar.test.js
**Impact**: Integration tests for calendar
**Complexity**: Low
**Issues**:
- Best mock pattern but still fails
- Real DB connection override

**Fixes**:
1. Force jest.setup.js skip for this test
2. Ensure query mock returns expected structure
3. Add earnings table mock structure

---

## Implementation Strategy

### Phase 1: Configuration (affects all)
1. Create jest.unit.config.js for unit tests
2. Modify jest.config.js to support both modes
3. Update npm test scripts

### Phase 2: Database Tests (enables others)
1. Fix database.test.js mock order
2. Add database state reset
3. Verify pg module mocking works

### Phase 3: Service Tests
1. Fix apiKeyService.test.js service instance handling
2. Add proper mock cleanup
3. Test with both real and mocked modes

### Phase 4: Route Tests
1. Fix signals.test.js mock sequencing
2. Fix calendar.test.js database override
3. Verify all sequential mocks work

---

## Code Snippets for Fixes

### Fix 1: Database Mock Order (database.test.js)
```javascript
// BEFORE: Mocks defined but jest.setup.js already connected
const mockPool = { ... };

// AFTER: Clear real database state first
beforeEach(async () => {
  jest.clearAllMocks();
  // CRITICAL: Reset database module cache
  delete require.cache[require.resolve("../../../utils/database")];
  // THEN re-import with mocks active
  const db = require("../../../utils/database");
  // Continue with test setup
});
```

### Fix 2: Signals Test Mock Matching (signals.test.js)
```javascript
// BEFORE: Sequential mocks fragile
mockQuery.mockResolvedValueOnce({ rows: [...] });  // Schema
mockQuery.mockResolvedValueOnce({ rows: [...] });  // Data
mockQuery.mockResolvedValueOnce({ rows: [...] });  // Count

// AFTER: Match query patterns
mockQuery.mockImplementation((sql, params) => {
  if (sql.includes("information_schema.columns")) {
    return Promise.resolve({ rows: [...schema...] });
  }
  if (sql.includes("WHERE signal")) {
    return Promise.resolve({ rows: [...data...] });
  }
  if (sql.includes("COUNT(*)")) {
    return Promise.resolve({ rows: [{ total: 1 }] });
  }
});
```

### Fix 3: Service Instance Reset (apiKeyService.test.js)
```javascript
// BEFORE: Service keeps real state
const service = __getServiceInstance();
service.secretsManager = mockSecretsManager;

// AFTER: Clean reset
beforeEach(() => {
  jest.clearAllMocks();
  const service = __getServiceInstance();
  service.encryptionKey = null;
  service.jwtVerifier = null;
  service.circuitBreaker = { failures: 0, lastFailure: null, isOpen: false };
  service.secretsManager = mockSecretsManager;
  clearCaches();
});
```

### Fix 4: Jest Configuration (jest.config.js)
```javascript
module.exports = {
  testEnvironment: "node",
  collectCoverage: false,
  
  // CHANGE: Conditionally load setup file
  setupFilesAfterEnv: process.env.TEST_ENV === 'integration' 
    ? ["<rootDir>/jest.setup.js"] 
    : [],
  
  testTimeout: process.env.TEST_ENV === 'integration' ? 60000 : 5000,
  maxWorkers: process.env.TEST_ENV === 'integration' ? 1 : 4,
  
  // For unit tests: clear mocks properly
  clearMocks: process.env.TEST_ENV !== 'integration',
  resetMocks: process.env.TEST_ENV !== 'integration',
  restoreMocks: process.env.TEST_ENV !== 'integration',
};
```

---

## Testing the Fixes

After applying fixes, validate:

```bash
# 1. Test unit tests in isolation
TEST_ENV=unit npm test -- database.test.js

# 2. Test with proper mocking
TEST_ENV=unit npm test -- signals.test.js

# 3. Test service mocking
TEST_ENV=unit npm test -- apiKeyService.test.js

# 4. Test all unit tests
TEST_ENV=unit npm test

# 5. Verify integration tests still work
TEST_ENV=integration npm test -- integration/
```

---

## Summary Table

| File | Root Cause | Severity | Fix Time | Impact |
|------|-----------|----------|----------|--------|
| jest.config.js | Real DB init before mocks | CRITICAL | 15 min | Unblocks all |
| database.test.js | Mock order, state management | HIGH | 30 min | Core util |
| signals.test.js | Sequential mock fragility | HIGH | 45 min | Route tests |
| apiKeyService.test.js | Service instance state | MEDIUM | 40 min | Security tests |
| calendar.test.js | DB override, structure | MEDIUM | 20 min | Route tests |

Total estimated fix time: ~150 minutes (2.5 hours)


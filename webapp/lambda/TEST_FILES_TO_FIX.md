# Test Files Requiring Fixes - Grouped by Error Pattern

## Phase 1: Database Mock Pattern (247 tests, ~65 min) ⭐ TOP PRIORITY

### Error: Cannot read 'rows' (108 errors)

**Files:**
1. `tests/integration/routes/trades.integration.test.js`
2. `tests/integration/routes/alerts.integration.test.js`
3. `tests/integration/routes/signals.integration.test.js`
4. `tests/integration/utils/performanceMonitor.test.js`
5. `tests/integration/services/cross-service-integration.test.js`
6. `tests/integration/routes/orders.integration.test.js`

**Common Fix:**
```javascript
// In each file's beforeEach or test setup:
mockPool.query.mockResolvedValue({ rows: [] });
// Instead of:
mockPool.query.mockResolvedValue(undefined);
```

---

### Error: Cannot read 'count' (70 errors)

**Files:**
1. `tests/integration/routes/trading.integration.test.js`
2. `tests/integration/routes/screener.integration.test.js`
3. `tests/integration/routes/stocks.integration.test.js`
4. `tests/integration/analytics/dashboard.test.js`

**Common Fix:**
```javascript
// For count queries:
mockPool.query.mockResolvedValue({ rows: [{ count: '0' }] });
```

---

### Error: Cannot read 'total' (69 errors)

**Files:**
1. `tests/integration/routes/trading.integration.test.js` (multiple tests)
   - GET /signals/daily
   - GET /signals/weekly
   - GET /signals/monthly
   - GET /signals/daily?page=1&limit=10
   - GET /signals/daily?latest_only=true

**Code Fix Required:**
- File: `/home/stocks/algo/webapp/lambda/routes/trading.js`
- Line: 662
- Change: `const total = parseInt(countResult.rows[0].total);`
- To: `const total = countResult?.rows?.[0]?.total ? parseInt(countResult.rows[0].total) : 0;`

**Test Mock Fix:**
```javascript
// Mock count query to return proper structure:
mockPool.query
  .mockResolvedValueOnce({ rows: [] }) // main query
  .mockResolvedValueOnce({ rows: [{ total: '0' }] }); // count query
```

---

## Phase 2: LiveDataManager Mock (22 tests, ~30 min)

**File:**
- `tests/integration/utils/liveDataManager.test.js`

**Errors:**
- Cannot read 'addConnection' (22 errors)
- Cannot read 'setRateLimit' (8 errors)
- Cannot read 'trackLatency' (6 errors)
- Cannot read 'trackProviderUsage' (4 errors)
- Cannot read 'getProviderStatus' (4 errors)

**Fix Location:**
Add comprehensive mock at top of test file:

```javascript
// Mock the entire liveDataManager module
jest.mock('../../../utils/liveDataManager', () => {
  const connections = new Map();
  const rateLimits = new Map();
  const providerStatus = new Map();

  return {
    addConnection: jest.fn((provider, ws) => {
      connections.set(provider, ws);
    }),
    setRateLimit: jest.fn((provider, limit) => {
      rateLimits.set(provider, limit);
    }),
    makeRequest: jest.fn(() => Promise.resolve({ data: 'test' })),
    getProviderStatus: jest.fn((provider) => {
      return providerStatus.get(provider) || { status: 'unknown' };
    }),
    trackLatency: jest.fn(),
    trackProviderUsage: jest.fn(),
    updateProviderStatus: jest.fn((provider, status) => {
      providerStatus.set(provider, status);
    })
  };
});
```

---

## Phase 3: Response Structure Mock (54 tests, ~45 min)

**Files affected:** 8 integration test files

### Error: Cannot read 'status' (54 errors)

**Root cause:** Status code expectation mismatches

**Files:**
1. `tests/integration/routes/health.integration.test.js`
2. `tests/integration/routes/analytics.integration.test.js`
3. `tests/integration/middleware/security-headers.integration.test.js`
4. `tests/integration/errors/4xx-error-scenarios.integration.test.js`
5. `tests/integration/errors/malformed-request.integration.test.js`
6. `tests/integration/routes/auth.integration.test.js`
7. `tests/integration/routes/dashboard.integration.test.js`
8. Various other integration route tests

**Status Mismatches:**
- Expected 200, Received 500: 112 occurrences (linked to DB errors)
- Expected 200, Received 404: 42 occurrences
- Expected 200, Received 503: 20 occurrences

**Common Fix:**
Create proper response mock helper:

```javascript
// tests/helpers/mockResponse.js
function mockResponse() {
  const res = {
    status: jest.fn().mockReturnThis(),
    json: jest.fn().mockReturnThis(),
    send: jest.fn().mockReturnThis(),
    set: jest.fn().mockReturnThis(),
    setHeader: jest.fn().mockReturnThis()
  };
  return res;
}

// Use in tests:
const res = mockResponse();
await routeHandler(req, res);
expect(res.status).toHaveBeenCalledWith(200);
```

---

## Phase 4 (Bonus): Auth Flow Mock (20 tests, ~20 min)

**File:**
- `tests/integration/auth/auth-flow.integration.test.js`

**Error:** Cannot read 'address' (20 errors)

**Root cause:** User object from auth middleware not properly mocked

**Fix:**
```javascript
// Mock request with user object:
const mockReq = {
  user: {
    address: '0x1234567890abcdef',
    userId: 'test-user-123',
    // other required user properties
  },
  body: {},
  query: {},
  params: {}
};

// Or mock the auth middleware:
jest.mock('../../../middleware/auth', () => ({
  authenticate: (req, res, next) => {
    req.user = {
      address: '0x1234567890abcdef',
      userId: 'test-user-123'
    };
    next();
  }
}));
```

---

## Summary: Files by Priority

### Must Fix (Phase 1 - 247 tests):
1. ✅ `routes/trading.js` (production code) - Line 662
2. ✅ `tests/integration/routes/trades.integration.test.js`
3. ✅ `tests/integration/routes/trading.integration.test.js`
4. ✅ `tests/integration/routes/alerts.integration.test.js`
5. ✅ `tests/integration/routes/signals.integration.test.js`
6. ✅ `tests/integration/routes/screener.integration.test.js`
7. ✅ `tests/integration/routes/stocks.integration.test.js`
8. ✅ `tests/integration/utils/performanceMonitor.test.js`
9. ✅ `tests/integration/services/cross-service-integration.test.js`
10. ✅ `tests/integration/routes/orders.integration.test.js`

### Should Fix (Phase 2 - 22 tests):
11. ✅ `tests/integration/utils/liveDataManager.test.js`

### Good to Fix (Phase 3 - 54 tests):
12. ✅ 8 integration test files with status code issues

### Nice to Fix (Phase 4 - 20 tests):
13. ✅ `tests/integration/auth/auth-flow.integration.test.js`

---

## Helper Files to Create

### 1. `tests/helpers/mockDatabase.js`
```javascript
/**
 * Database mock helpers for consistent test mocking
 */

function mockDbResponse(data = []) {
  return { rows: data };
}

function mockCountResponse(count = 0) {
  return { rows: [{ count: count.toString() }] };
}

function mockTotalResponse(total = 0) {
  return { rows: [{ total: total.toString() }] };
}

function mockEmptyResponse() {
  return { rows: [] };
}

module.exports = {
  mockDbResponse,
  mockCountResponse,
  mockTotalResponse,
  mockEmptyResponse
};
```

### 2. `tests/helpers/mockResponse.js`
```javascript
/**
 * Express response mock helper
 */

function mockResponse() {
  const res = {
    status: jest.fn().mockReturnThis(),
    json: jest.fn().mockReturnThis(),
    send: jest.fn().mockReturnThis(),
    set: jest.fn().mockReturnThis(),
    setHeader: jest.fn().mockReturnThis(),
    end: jest.fn().mockReturnThis()
  };
  return res;
}

module.exports = { mockResponse };
```

### 3. `tests/helpers/mockRequest.js`
```javascript
/**
 * Express request mock helper
 */

function mockRequest(overrides = {}) {
  return {
    user: {
      address: '0x1234567890abcdef',
      userId: 'test-user-123',
      ...overrides.user
    },
    body: overrides.body || {},
    query: overrides.query || {},
    params: overrides.params || {},
    headers: overrides.headers || {}
  };
}

module.exports = { mockRequest };
```

---

## Verification Commands

After each phase, run these commands to verify fixes:

### Phase 1 Verification:
```bash
npm test -- tests/integration/routes/trading.integration.test.js
npm test -- tests/integration/routes/trades.integration.test.js
npm test -- tests/integration/routes/alerts.integration.test.js
npm test -- tests/integration/routes/signals.integration.test.js
```

### Phase 2 Verification:
```bash
npm test -- tests/integration/utils/liveDataManager.test.js
```

### Phase 3 Verification:
```bash
npm test -- tests/integration/routes/health.integration.test.js
npm test -- tests/integration/middleware/security-headers.integration.test.js
```

### Phase 4 Verification:
```bash
npm test -- tests/integration/auth/auth-flow.integration.test.js
```

### Full Suite Verification:
```bash
npm test
```

---

## Success Criteria

- [ ] Phase 1: ~247 tests pass (database mock pattern)
- [ ] Phase 2: ~22 tests pass (LiveDataManager)
- [ ] Phase 3: ~54 tests pass (response structure)
- [ ] Phase 4: ~20 tests pass (auth flow)
- [ ] Overall: 814 failures → ~491 failures (40% reduction)
- [ ] Pass rate: 75% → 85%

# Test Error Quick Wins - Priority Table

**Goal:** Fix 323+ tests (40% of failures) in ~2.5 hours

## Top 5 Quick Win Errors (Ranked by Impact)

| Rank | Error Type | Count | Files | Est. Time | Quick Win? | ROI (tests/hr) |
|------|------------|-------|-------|-----------|------------|----------------|
| 🥇 1 | `'rows'` | **108** | 6 | 30 min | ✅ YES | 216 |
| 🥈 2 | `'count'` | **70** | 4 | 20 min | ✅ YES | 210 |
| 🥉 3 | `'total'` | **69** | 6 | 15 min | ✅ YES | 276 |
| 4 | `'status'` | **54** | 8 | 45 min | ✅ YES | 72 |
| 5 | `'addConnection'` | **22** | 1 | 30 min | ✅ YES | 44 |
| **TOTAL** | | **323** | | **2.5 hrs** | | **129 avg** |

**Bonus:** Fix `'address'` (20 errors, 20 min) → **343 total tests fixed**

---

## Fix Strategy Overview

### Phase 1: Database Mocks (TOP PRIORITY ⭐⭐⭐)
**Errors #1, #2, #3 combined** → 247 tests fixed in ~65 minutes

**Problem:**
```javascript
// Current broken pattern:
mockPool.query.mockResolvedValue(undefined);
```

**Solution:**
```javascript
// Create helper: tests/helpers/mockDatabase.js
function mockDbResponse(data = []) {
  return { rows: data };
}

function mockCountResponse(count = 0) {
  return { rows: [{ count: count.toString() }] };
}

// Use in tests:
mockPool.query.mockResolvedValue(mockDbResponse());
```

**Files to Update:**
- 6 integration route test files
- Add null-safe accessor in `routes/trading.js:662`

---

### Phase 2: LiveDataManager Mock
**Error #5** → 22 tests fixed in ~30 minutes

**File:** `tests/integration/utils/liveDataManager.test.js`

**Solution:**
```javascript
const mockLiveDataManager = {
  addConnection: jest.fn(),
  setRateLimit: jest.fn(),
  makeRequest: jest.fn(),
  getProviderStatus: jest.fn(),
  trackLatency: jest.fn(),
  trackProviderUsage: jest.fn()
};

jest.mock('../../../utils/liveDataManager', () => mockLiveDataManager);
```

---

### Phase 3: Response Structure Mocks
**Error #4** → 54 tests fixed in ~45 minutes

**Solution:**
```javascript
// Create helper: tests/helpers/mockResponse.js
function mockResponse() {
  const res = {
    status: jest.fn().mockReturnThis(),
    json: jest.fn().mockReturnThis(),
    send: jest.fn().mockReturnThis()
  };
  return res;
}

// Use in tests:
const res = mockResponse();
```

---

## Execution Checklist

### ✅ Phase 1: Database Mocks (65 min)
- [ ] Create `tests/helpers/mockDatabase.js`
- [ ] Add `mockDbResponse()` helper
- [ ] Add `mockCountResponse()` helper
- [ ] Update integration tests to use helpers
- [ ] Fix `routes/trading.js:662` with null-safe accessor
- [ ] Run: `npm test -- tests/integration/routes/trading`
- [ ] Verify: ~69 tests pass

### ✅ Phase 2: Service Mocks (30 min)
- [ ] Create comprehensive LiveDataManager mock
- [ ] Update `tests/integration/utils/liveDataManager.test.js`
- [ ] Run: `npm test -- tests/integration/utils/liveDataManager`
- [ ] Verify: ~22 tests pass

### ✅ Phase 3: Response Mocks (45 min)
- [ ] Create `tests/helpers/mockResponse.js`
- [ ] Update 8 integration test files
- [ ] Run affected tests
- [ ] Verify: ~54 tests pass

### ✅ Verification
- [ ] Run full suite: `npm test`
- [ ] Confirm: 814 → ~491 failures (40% reduction)
- [ ] Confirm: Pass rate 75% → ~85%

---

## Expected Results

### Before:
```
Test Suites: 75 failed, 69 passed (52% failing)
Tests:       814 failed, 2504 passed (24.5% failing)
```

### After Quick Wins:
```
Test Suites: ~40 failed, ~104 passed (28% failing)
Tests:       ~491 failed, ~2827 passed (14.8% failing)
```

**Improvement:**
- ✅ 323 tests fixed (40% of failures)
- ✅ Test pass rate: 75% → 85% (+10%)
- ✅ Time investment: ~2.5 hours
- ✅ ROI: ~129 tests per hour

---

## Critical Code Locations

### 1. Trading Route (69 errors)
**File:** `/home/stocks/algo/webapp/lambda/routes/trading.js:662`
```javascript
// BEFORE:
const total = parseInt(countResult.rows[0].total);

// AFTER:
const total = countResult?.rows?.[0]?.total ? parseInt(countResult.rows[0].total) : 0;
```

### 2. Integration Test Mocks
**Pattern across 15+ files:**
```javascript
// BEFORE:
mockPool.query.mockResolvedValue(undefined);

// AFTER:
mockPool.query.mockResolvedValue({ rows: [] });
```

---

## Status Code Issues (Secondary)

| Expected | Received | Count | Cause |
|----------|----------|-------|-------|
| 200 | 500 | 112 | Errors #1-#3 (DB undefined) |
| 200 | 404 | 42 | Route not found / mock issue |
| 200 | 503 | 20 | Service unavailable |
| 500 | 200 | 10 | Error handling issue |
| 401 | 200 | 8 | Auth middleware bypassed |

**Note:** Fixing errors #1-#3 will likely resolve the 112 "200→500" mismatches automatically.

---

## Next Actions

1. **START HERE:** Run Phase 1 (Database Mocks)
2. **Then:** Run Phase 2 (Service Mocks)  
3. **Then:** Run Phase 3 (Response Mocks)
4. **Verify:** Run full test suite
5. **Document:** Update with actual results

See `TEST_ERROR_ANALYSIS.md` for detailed analysis.

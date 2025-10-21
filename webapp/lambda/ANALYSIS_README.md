# Test Failure Analysis - Complete Documentation

This directory contains comprehensive analysis of failing unit tests and actionable fixes.

## Documents Overview

### Start Here

1. **TEST_FAILURE_ANALYSIS.md** (13K, 437 lines) ⭐ PRIMARY ANALYSIS
   - Root cause analysis of all failures
   - Common failure patterns by file
   - Mock pattern issues summary table
   - Phase-by-phase implementation strategy
   - Code snippets for all fixes
   - **Read this first for complete understanding**

2. **TEST_FIX_QUICK_REFERENCE.md** (8K, 317 lines) ⭐ ACTION ITEMS
   - 30-second problem summary
   - Priority-ordered fixes (5 items)
   - File-by-file changes with exact line numbers
   - Success indicators
   - Troubleshooting guide
   - **Start here if you want to implement fixes immediately**

3. **MOCK_PATTERNS_GUIDE.md** (12K, 518 lines) ⭐ REFERENCE
   - Working vs failing test comparison
   - 6 mock patterns with examples
   - Common mistakes and corrections
   - Verification checklist
   - **Reference while implementing fixes**

---

## Quick Summary

### The Problem (30 seconds)

Jest is configured for REAL database testing:
```javascript
setupFilesAfterEnv: ["<rootDir>/jest.setup.js"],  // Initializes REAL database
clearMocks: false,  // Doesn't clear mocks
```

But unit tests mock the database:
```javascript
jest.mock("../../../utils/database", () => ({
  query: jest.fn()  // This mock is IGNORED!
}))
```

**Result**: Real database connection attempted → tests fail

### The Solution (75 minutes)

| Priority | File | Fix | Time |
|----------|------|-----|------|
| CRITICAL | jest.config.js | Add TEST_ENV conditionals | 5 min |
| HIGH | database.test.js | Clear module cache, reset state | 10 min |
| HIGH | signals.test.js | Replace sequential mocks | 15 min |
| MEDIUM | apiKeyService.test.js | Reset service instance | 20 min |
| MEDIUM | calendar.test.js | Reorganize mock definition | 5 min |
| - | Testing & Validation | Run verification tests | 20 min |

---

## Failing Test Files (Priority Order)

### 1. jest.config.js - CRITICAL
**Status**: Configuration mismatch
**Impact**: Blocks all other fixes
**Solution**: Conditional setup based on TEST_ENV variable

```javascript
// Add this to jest.config.js
setupFilesAfterEnv: process.env.TEST_ENV === 'integration' ? ["<rootDir>/jest.setup.js"] : [],
testTimeout: process.env.TEST_ENV === 'integration' ? 60000 : 5000,
clearMocks: process.env.TEST_ENV !== 'integration',
```

### 2. database.test.js - HIGH
**Status**: Mock order issue, real DB connects first
**Impact**: Core utility tests fail
**Solution**: Clear require cache in beforeEach

### 3. signals.test.js - HIGH
**Status**: Sequential mocks fragile
**Impact**: Most complex route tests fail
**Solution**: Use pattern matching instead

### 4. apiKeyService.test.js - MEDIUM
**Status**: Service maintains real state
**Impact**: Security/encryption tests fail
**Solution**: Reset service instance state

### 5. calendar.test.js - MEDIUM
**Status**: Best pattern but DB override still happens
**Impact**: Calendar integration tests fail
**Solution**: Ensure jest.setup.js skips for unit tests

---

## Reference Files (Additional Context)

- **TEST_ANALYSIS_INDEX.md** - Index of all analysis documents
- **TEST_ANALYSIS_SUMMARY.md** - Executive summary of test status
- **TEST_ERROR_ANALYSIS.md** - Detailed error patterns
- **TEST_FILES_TO_FIX.md** - List of problematic files
- **TEST_QUICK_WINS.md** - Easy wins to implement first
- **TEST_PASS_RATE_SUMMARY.md** - Current test pass rates

---

## Implementation Checklist

### Phase 1: Configuration
- [ ] Read TEST_FAILURE_ANALYSIS.md
- [ ] Review jest.config.js changes needed
- [ ] Implement TEST_ENV conditional logic
- [ ] Run: `TEST_ENV=unit npm test -- database.test.js`

### Phase 2: Database Tests
- [ ] Read MOCK_PATTERNS_GUIDE.md Pattern 3
- [ ] Implement cache clear in beforeEach
- [ ] Run: `TEST_ENV=unit npm test -- database.test.js`
- [ ] Verify: 15+ tests pass

### Phase 3: Service Tests
- [ ] Review MOCK_PATTERNS_GUIDE.md Pattern 5
- [ ] Reset service instance state
- [ ] Run: `TEST_ENV=unit npm test -- apiKeyService.test.js`
- [ ] Verify: 50+ tests pass

### Phase 4: Route Tests
- [ ] Review TEST_FIX_QUICK_REFERENCE.md fixes 2 & 3
- [ ] Implement pattern matching in signals.test.js
- [ ] Reorganize mocks in calendar.test.js
- [ ] Run: `TEST_ENV=unit npm test -- signals.test.js`
- [ ] Run: `TEST_ENV=unit npm test -- calendar.test.js`
- [ ] Verify: 40+ tests pass

### Phase 5: Validation
- [ ] Run: `TEST_ENV=unit npm test` (all unit tests)
- [ ] Run: `TEST_ENV=integration npm test -- tests/integration/`
- [ ] Run: `npm test` (full suite)
- [ ] Verify: No "Cannot connect to database" errors

---

## How to Use These Documents

### If you're new to the problem:
1. Start with TEST_FAILURE_ANALYSIS.md (comprehensive)
2. Skip to the "Common Failure Patterns" section
3. Review the specific file that interests you
4. Jump to TEST_FIX_QUICK_REFERENCE.md for action items

### If you're implementing fixes:
1. Open TEST_FIX_QUICK_REFERENCE.md
2. Follow fixes 1-5 in order
3. Use MOCK_PATTERNS_GUIDE.md as reference
4. Run verification commands after each fix

### If you want to understand mock patterns:
1. Read MOCK_PATTERNS_GUIDE.md first
2. Review "Working vs Failing Pattern" section
3. Study the 6 mock patterns with examples
4. Check "Common Mock Setup Mistakes"

### If you're debugging a specific test:
1. Find your test file in TEST_FIX_QUICK_REFERENCE.md
2. Look up the specific fix for that file
3. Check MOCK_PATTERNS_GUIDE.md for similar patterns
4. Use troubleshooting guide if needed

---

## Key Insights

### Why Tests Fail
- jest.setup.js initializes REAL database FIRST
- Unit tests define mocks SECOND
- Module cache prevents mocks from being used
- Routes connect to REAL database instead of mock
- Result: DB connection errors

### Why Mocks Don't Work
- **Problem**: Sequential mocking is fragile
- **Real DB**: Makes different queries than expected
- **Mock Queues**: Don't match actual query order
- **Solution**: Use pattern matching on SQL strings

### Why Services Fail
- **Problem**: Singletons maintain real state
- **Real Init**: jest.setup.js creates real instances
- **Mock Setup**: Too late to override instances
- **Solution**: Clear instance state in beforeEach

---

## Common Commands

```bash
# Run unit tests only (use mocks)
TEST_ENV=unit npm test

# Run specific unit test
TEST_ENV=unit npm test -- database.test.js

# Run with verbose output
TEST_ENV=unit npm test -- --verbose signals.test.js

# Run integration tests (use real DB)
TEST_ENV=integration npm test -- tests/integration/

# Full test suite
npm test

# Check test count
npm test -- --listTests | wc -l

# Show test coverage
npm test -- --coverage
```

---

## Expected Outcomes After Fixes

### Before Fixes
- ✗ 50+ test failures
- ✗ "Cannot connect to localhost:5432" errors
- ✗ 0% pass rate for complex route tests
- ✗ 30+ seconds per test (waiting for DB timeout)

### After Fixes
- ✓ 200+ tests pass
- ✓ No database connection errors
- ✓ 95%+ pass rate for unit tests
- ✓ <5 seconds total for all unit tests

---

## Verification Checklist

After implementing all fixes, verify:

```bash
# 1. Unit tests with mocks
TEST_ENV=unit npm test
# Expected: 200+ passed, 0 failed

# 2. Integration tests with real DB  
TEST_ENV=integration npm test -- tests/integration/
# Expected: 80+ passed

# 3. Full suite
npm test
# Expected: No crashes, no connection errors

# 4. Specific files
TEST_ENV=unit npm test -- database.test.js
# Expected: 15+ passed
TEST_ENV=unit npm test -- signals.test.js
# Expected: 30+ passed
TEST_ENV=unit npm test -- apiKeyService.test.js
# Expected: 50+ passed
TEST_ENV=unit npm test -- calendar.test.js
# Expected: 10+ passed
```

---

## Troubleshooting

### Issue: "Cannot connect to localhost:5432"
- **Cause**: jest.setup.js still running for unit tests
- **Fix**: Ensure TEST_ENV=unit is set
- **Check**: `echo $TEST_ENV` should output "unit"

### Issue: Mocks not intercepting calls
- **Cause**: Module cached before jest.mock()
- **Fix**: Clear require cache in beforeEach
- **Check**: Look for `delete require.cache[...]`

### Issue: Sequential mocks mismatched
- **Cause**: Real DB queries don't match expected order
- **Fix**: Use mockImplementation with pattern matching
- **Check**: SQL.includes() conditions cover all query types

### Issue: Service state pollution between tests
- **Cause**: Singletons not reset
- **Fix**: Clear instance state in beforeEach
- **Check**: `const service = __getServiceInstance(); service.encryptionKey = null;`

---

## Next Steps

1. **Now**: Read TEST_FAILURE_ANALYSIS.md (15 min)
2. **Then**: Review TEST_FIX_QUICK_REFERENCE.md (10 min)
3. **Action**: Implement fixes in priority order (75 min)
4. **Verify**: Run full test suite (10 min)
5. **Done**: All tests passing ✓

**Total Time**: ~110 minutes

---

## Questions?

Refer to:
- General questions → TEST_FAILURE_ANALYSIS.md
- Implementation questions → TEST_FIX_QUICK_REFERENCE.md  
- Pattern questions → MOCK_PATTERNS_GUIDE.md
- Error questions → TEST_ERROR_ANALYSIS.md

---

**Last Updated**: Oct 21, 2025
**Files Analyzed**: 4 (signals.test.js, database.test.js, apiKeyService.test.js, calendar.test.js)
**Root Cause**: Configuration + Mock Lifecycle Mismatch
**Estimated Fix Time**: 75 minutes
**Expected Outcome**: 200+ tests passing


# Integration Tests - Testing Real Data, Not Mocks

## Problem We Found

The existing unit tests ALL use mocked API responses. This means:

✗ Tests pass even when real site is broken
✗ We found real bugs that tests missed:
  - Frontend showing random scores (FIXED)
  - 71% NULL stability scores (FIXED)
  - Only 36% symbol coverage (STILL A PROBLEM)
  - Empty trading signals table (STILL A PROBLEM)

## Solution: Integration Tests

These tests call the REAL API endpoints and test against REAL database data.

## Running Integration Tests

### Prerequisites

1. **Start the API server**:
```bash
cd /home/stocks/algo/webapp
npm run dev  # or however you start the server
# Should be running on http://localhost:3001
```

2. **Ensure database is populated**:
```bash
# Make sure stock_scores table has real data
psql -d stocks -c "SELECT COUNT(*) FROM stock_scores;"
```

### Run the Tests

```bash
# From frontend directory
cd /home/stocks/algo/webapp/frontend

# Run REAL integration tests (not mocks)
npm run test:integration

# Or with detailed output:
npm run test:integration -- --reporter=verbose

# Run specific test file:
npm test src/tests/integration/api.integration.test.js
```

### Test Files

**`api.integration.test.js`** - Main integration tests
- Tests `/api/scores` endpoint with REAL data
- Validates stock data structure
- Checks stability score coverage
- Verifies no random numbers in scores
- Tests trading signals endpoint
- Analyzes symbol coverage

**`StockScreener.integration.test.js`** - Component-specific tests
- Tests StockScreener component with REAL data
- Verifies scores are deterministic (not random)
- Detects if component reverts to random generation
- Checks data completeness
- Validates field mapping

## What These Tests Check

### ✅ Frontend Score Display Bug (FIXED)
```javascript
it("Stock scores are NOT randomly generated", async () => {
  const data = await fetchRealData("/api/scores");
  const scores = data.data;

  // Fetch twice - should be identical if real (not random)
  const aapl1 = scores.find(s => s.symbol === "AAPL");
  const aapl2 = (await fetchRealData("/api/scores")).find(s => s.symbol === "AAPL");

  expect(aapl1.composite_score).toBe(aapl2.composite_score);
  // THIS FAILS if component does Math.random()
});
```

### ✅ Stability Scores Coverage (PARTIALLY FIXED)
```javascript
it("Stability scores are populated (not 71% NULL)", async () => {
  const scores = await fetchRealData("/api/scores");
  const withStability = scores.filter(s => s.stability_score !== null).length;
  const coverage = (withStability / scores.length) * 100;

  expect(coverage).toBeGreaterThan(40); // After Phase 1 fix
});
```

### ✅ Symbol Coverage (IDENTIFIED PROBLEM)
```javascript
it("Verify symbol coverage", async () => {
  const scores = await fetchRealData("/api/scores");

  console.log(`Found ${scores.length} symbols with scores`);
  // Currently: 1,932 of 5,315 (36%) - CRITICAL ISSUE
});
```

### ⚠️ Trading Signals (IDENTIFIED PROBLEM)
```javascript
it("GET /api/trading-signals", async () => {
  const data = await fetchRealData("/api/trading-signals");

  if (data.length === 0) {
    console.warn("Trading signals table is EMPTY");
    // Confirms no loader generating signals
  }
});
```

## Expected Test Results

### If System is Working
```
✓ Stock scores are REAL numbers (not random)
✓ Stock scores are deterministic (same on repeat calls)
✓ Stability scores populated (>40% coverage after Phase 1)
✓ All score fields valid and not NULL
✓ Frontend receives REAL data (not mocks)
✓ Symbol coverage verified (should flag if <3000)
⚠️ Trading signals: Empty table (as expected - loader missing)
```

### If Issues Exist
```
✗ Stock scores ARE random (Math.random() detected)
✗ Stability scores NULL for most (>70%)
✗ Only 36% symbol coverage (CRITICAL)
✗ Trading signals empty (NO LOADER)
✗ Tests with mocks don't catch these problems
```

## How to Interpret Results

### Critical Issues (Block Deployment)
1. **Frontend showing random scores** → Must fix StockScreener.jsx
2. **Stability scores >50% NULL** → Must run data loaders
3. **Symbol coverage <50%** → Must run full loader suite
4. **Trading signals empty** → Must recover signal loader

### Medium Issues (Should Fix)
1. **Tests still using mocks** → Some tests still mock data
2. **Missing data fields** → Some optional fields NULL

### Low Issues (Nice to Have)
1. **E2E tests missing** → Can add later
2. **Performance slow** → Can optimize later

## Adding More Tests

Template for new integration test:

```javascript
import { describe, it, expect } from "vitest";

const API_URL = process.env.VITE_API_URL || "http://localhost:3001";

async function fetchRealData(endpoint) {
  const response = await fetch(`${API_URL}${endpoint}`);
  if (!response.ok) throw new Error(`API Error ${response.status}`);
  return await response.json();
}

describe("YourFeature Integration Test", () => {
  it("tests REAL data from API", async () => {
    const data = await fetchRealData("/api/your-endpoint");

    expect(data).toBeDefined();
    expect(data.length).toBeGreaterThan(0);
    // Test REAL behavior, not mocked
  });
});
```

## CI/CD Integration

Before committing code, run:

```bash
# Run all integration tests
npm run test:integration

# If all pass:
git add .
git commit -m "Fix: ensure tested against real data"
```

Tests should be part of CI/CD pipeline to catch real issues early.

## Troubleshooting

### "Failed to fetch /api/scores"
- Ensure API server is running on http://localhost:3001
- Check database connection
- Verify PostgreSQL is running

### "No score data available"
- Database doesn't have stock_scores
- Run: `python3 loadstockscores.py`
- May need to run other loaders first

### "Trading signals endpoint not available"
- This is expected - no loader populates this table yet
- Test documents this as known issue

### Tests show 36% symbol coverage
- This is correct - indicates data loading issue
- Need to run full data loader suite

## Next Steps

1. ✅ **Run these integration tests NOW**
   - They will identify real issues
   - Much more reliable than unit test mocks

2. ⚠️ **Fix issues found**:
   - If frontend shows random: Fix StockScreener.jsx (already done)
   - If stability NULL: Run data loaders
   - If symbol coverage low: Run full loader suite
   - If trading signals empty: Recover signal loader

3. 📊 **Monitor test results**:
   - Run after each data load
   - Run before each deployment
   - Add to automated CI/CD

## More Information

See these documents for context:
- `CRITICAL_ISSUES_DISCOVERED.md` - Detailed issue analysis
- `DATA_COVERAGE_ACTION_PLAN.txt` - Fix recommendations
- `SESSION_SUMMARY_2025-10-20.txt` - Full technical details

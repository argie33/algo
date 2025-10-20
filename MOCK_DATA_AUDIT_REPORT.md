# Mock Data & Hardcoded Values Audit Report

**Generated:** 2025-10-19
**Scope:** Complete codebase analysis for mock values, hardcoded data, and fallback mechanisms
**Status:** CRITICAL ISSUES FOUND - Production code contains mock data and hardcoded fallbacks

---

## Executive Summary

### Critical Findings
- **CRITICAL**: Hardcoded sentiment/positioning scores in production Python loader (`loadstockscores.py`)
- **CRITICAL**: Mock authentication bypass tokens in production middleware
- **CRITICAL**: Hardcoded test user IDs in production sync scripts
- **HIGH**: Mock email message IDs returned in production alerting system
- **HIGH**: Hardcoded fallback values in risk calculation engine
- **MEDIUM**: Score fallback operators (`|| 0`) in frontend creating fake 0 scores

### Issues Breakdown
| Severity | Count | Category | Impact |
|----------|-------|----------|--------|
| CRITICAL | 4 | Production Data Corruption | Users see fake scores and data |
| HIGH | 3 | Security/Reliability | Authentication bypass, unreliable calculations |
| MEDIUM | 12 | User Experience | Misleading zero values displayed |
| LOW | ~50 | Test Infrastructure | Acceptable test patterns |

---

## CRITICAL Issues (Production Code)

### 1. Hardcoded Stock Scores - CRITICAL
**File:** `/home/stocks/algo/webapp/lambda/loadstockscores.py:354-355`

```python
# Positioning and Sentiment Scores (placeholder values for now)
positioning_score = 70.0  # Default neutral score
sentiment_score = 70.0  # Default neutral score
```

**Impact:**
- ALL stocks get fake positioning_score = 70.0
- ALL stocks get fake sentiment_score = 70.0
- Composite scores corrupted (includes 15% fake data: 7.5% positioning + 7.5% sentiment)
- Users making investment decisions based on **FAKE SCORES**

**Evidence:**
```python
# Line 359-365: Composite calculation using fake scores
composite_score = (
    momentum_score * 0.25 +
    value_score * 0.20 +
    quality_score * 0.20 +
    growth_score * 0.20 +
    positioning_score * 0.075 +  # ❌ ALWAYS 70.0
    sentiment_score * 0.075       # ❌ ALWAYS 70.0
)
```

**Remediation:**
```python
# Option 1: Calculate from real data or set to None
positioning_score = calculate_positioning_score(symbol) if has_positioning_data(symbol) else None
sentiment_score = calculate_sentiment_score(symbol) if has_sentiment_data(symbol) else None

# Option 2: Exclude from composite if not available
if positioning_score is None or sentiment_score is None:
    # Recalculate composite with only available factors
    composite_score = calculate_composite_without_missing_factors(...)
```

**Severity:** CRITICAL - Production data corruption
**Priority:** P0 - Fix immediately

---

### 2. Mock Authentication Bypass - CRITICAL SECURITY
**File:** `/home/stocks/algo/webapp/lambda/middleware/auth.js:65-89`

```javascript
// PRODUCTION CODE ACCEPTS TEST TOKENS!
if (token === "dev-bypass-token" || token === "test-token" || token === "mock-access-token") {
  const userId = token === "dev-bypass-token" ? "dev-user-bypass" :
                 token === "mock-access-token" ? "mock-user-123" : "test-user-123";
  req.user = {
    id: userId,
    sub: userId,
    email: token === "dev-bypass-token" ? "dev-bypass@example.com" : "...",
    role: "admin",  // ❌ GRANTS ADMIN ACCESS!
  };
  return next();
}
```

**Impact:**
- Anyone can authenticate with "dev-bypass-token" and get **ADMIN** access
- Production endpoints accept hardcoded test tokens
- Massive security vulnerability

**Remediation:**
```javascript
// ONLY allow test tokens in test environment
if (process.env.NODE_ENV === 'test' &&
    (token === "test-token" || token === "mock-access-token")) {
  // Test-only authentication
  req.user = { ... };
  return next();
}

// NEVER allow dev-bypass-token in production
if (token === "dev-bypass-token") {
  if (process.env.NODE_ENV === 'production') {
    throw new Error('Invalid authentication token');
  }
  // Only in development
}
```

**Severity:** CRITICAL - Security vulnerability
**Priority:** P0 - Fix immediately before deployment

---

### 3. Hardcoded Test Users in Production Sync - CRITICAL
**File:** `/home/stocks/algo/webapp/lambda/sync_portfolio.js:85-98`

```javascript
// Test users hardcoded in production sync logic!
const testUsers = ['default_user', 'dev-user-bypass', 'test-user-123', 'mock-user-123'];

for (const userId of testUsers) {
  const insertTransactions = `
    INSERT INTO portfolio_transactions (symbol, transaction_type, quantity, price, ...) VALUES
    ('AAPL', 'BUY', 100.00, 150.00, 15000.00, ..., $1, 'manual'),
    ('MSFT', 'BUY', 50.00, 400.00, 20000.00, ..., $1, 'manual'),
    ...
  `;
  await query(insertTransactions, [userId]);
}
```

**Impact:**
- Production database polluted with fake test users
- Hardcoded stock transactions (AAPL, MSFT, GOOGL, TSLA, AMZN)
- Fake portfolio data inserted on every sync

**Remediation:**
```javascript
// ONLY insert test data in local/test environments
if (environment === 'local' || environment === 'test') {
  // Test data logic here
} else {
  // Production: NO test data insertion
  console.log('Production environment - skipping test data');
}
```

**Severity:** CRITICAL - Data corruption
**Priority:** P0 - Fix immediately

---

### 4. API Key Service Test Token Bypass - CRITICAL
**File:** `/home/stocks/algo/webapp/lambda/utils/apiKeyService.js:90-119`

```javascript
// Production code accepts test tokens!
if (token === "test-token") {
  return { sub: "test-user-123", email: "test@example.com", username: "test-user" };
}
if (token === "dev-bypass-token") {
  return { sub: "dev-user-bypass", email: "dev-bypass@example.com", username: "dev-user" };
}
```

**Impact:**
- API key verification bypassed with hardcoded tokens
- Unauthorized access to user data

**Remediation:**
```javascript
// Only allow test tokens in test environment
if (process.env.NODE_ENV === 'test') {
  if (token === "test-token") {
    return { sub: "test-user-123", ... };
  }
}
// Production: strict JWT verification only
```

**Severity:** CRITICAL - Security bypass
**Priority:** P0 - Fix immediately

---

## HIGH Severity Issues

### 5. Mock Email Message IDs - HIGH
**File:** `/home/stocks/algo/webapp/lambda/utils/alertSystem.js:615,632`

```javascript
// Returns mock IDs in production when services not configured!
console.log("📧 DEV: Email would be sent with SES:", { ... });
return { success: true, messageId: "dev-mock-message-id" };  // ❌ FAKE SUCCESS

console.log("📧 DEV: SendGrid not configured, email would be sent:", ...);
return { success: true, messageId: "dev-sendgrid-mock-id" };  // ❌ FAKE SUCCESS
```

**Impact:**
- Production code reports "success" but emails NOT sent
- Users think alerts were sent but they weren't
- Silent failures in production

**Remediation:**
```javascript
// Fail explicitly if email service not configured
if (!process.env.AWS_SES_CONFIGURED) {
  throw new Error('Email service not configured - cannot send alert');
}

// Don't return fake success
if (!emailSent) {
  return { success: false, error: 'Email service unavailable' };
}
```

**Severity:** HIGH - Silent failures
**Priority:** P1 - Fix before production use

---

### 6. Risk Engine Hardcoded Fallbacks - HIGH
**File:** `/home/stocks/algo/webapp/lambda/utils/riskEngine.js:220-222`

```javascript
// Hardcoded fallback values in risk calculations!
positions = portfolio.map(pos => ({
  symbol: pos.symbol || "TEST",
  quantity: pos.quantity || 100,              // ❌ Fake quantity
  current_price: pos.current_price || pos.currentPrice || 100,  // ❌ Fake price
  total_value: pos.total_value || pos.value ||
    (pos.quantity * (pos.current_price || pos.currentPrice || 100)) || 10000  // ❌ Fake value
}));
```

**Impact:**
- VaR (Value at Risk) calculated with fake data
- Risk metrics meaningless if using fallback values
- Users get incorrect risk assessments

**Remediation:**
```javascript
// Validate required data instead of using fallbacks
positions = portfolio.map(pos => {
  if (!pos.symbol || !pos.quantity || !pos.current_price) {
    throw new Error(`Invalid position data for ${pos.symbol || 'unknown'}`);
  }
  return {
    symbol: pos.symbol,
    quantity: pos.quantity,
    current_price: pos.current_price,
    total_value: pos.total_value || (pos.quantity * pos.current_price)
  };
});
```

**Severity:** HIGH - Unreliable calculations
**Priority:** P1 - Fix before production

---

### 7. Hardcoded Backtest Example Symbols - HIGH
**File:** `/home/stocks/algo/webapp/lambda/routes/backtest.js:402`

```javascript
// Example backtest uses hardcoded symbols
symbols: ["AAPL", "MSFT", "GOOGL"],
```

**Impact:**
- Not dynamic based on user selection
- Documentation/example only (lower severity than actual data)

**Remediation:**
```javascript
// Use user-provided symbols or fetch from database
symbols: req.body.symbols || await getPopularSymbols()
```

**Severity:** HIGH - Poor UX
**Priority:** P2 - Fix in next iteration

---

## MEDIUM Severity Issues

### 8. Frontend Score Fallbacks - MEDIUM
**Files:** Multiple frontend files

**Pattern found in:**
- `/home/stocks/algo/webapp/frontend/src/pages/ScoresDashboard.jsx:271-276`
- `/home/stocks/algo/webapp/frontend/src/pages/StockDetail.jsx:1978,2117,2165`
- `/home/stocks/algo/webapp/frontend/src/pages/TradingSignals.jsx:213`

```javascript
// Frontend creates fake 0 scores
quality: avg(stocks.map(s => s.quality_score || 0).filter(v => v > 0)),
momentum: avg(stocks.map(s => s.momentum_score || 0).filter(v => v > 0)),
value: avg(stocks.map(s => s.value_score || 0).filter(v => v > 0)),
```

**Impact:**
- Displays "0" for missing scores instead of "N/A"
- Users see fake scores in UI
- Charts/averages include fake zeros before filtering

**Note:** Some instances have `.filter(v => v > 0)` which mitigates the issue by removing zeros before averaging, but initial mapping still creates fake data.

**Remediation:**
```javascript
// Option 1: Display N/A for missing data
quality: stock.quality_score ?? "N/A"

// Option 2: Filter nulls before averaging
quality: avg(stocks.map(s => s.quality_score).filter(v => v != null))

// Option 3: Use optional chaining and nullish coalescing
score: stockScores?.data?.data?.momentum_score ?? null
```

**Severity:** MEDIUM - Misleading UI
**Priority:** P2 - Fix in next release

---

### 9. Hardcoded Tech Stocks List - MEDIUM
**File:** `/home/stocks/algo/webapp/frontend/src/pages/Portfolio.jsx:1226`

```javascript
const techStocks = ["AAPL", "MSFT", "GOOGL", "META", "TSLA"];
```

**Impact:**
- Not dynamic, doesn't reflect current tech sector leaders
- Hardcoded categorization

**Remediation:**
```javascript
// Fetch from sector data
const techStocks = await api.getSectorStocks('Technology');
```

**Severity:** MEDIUM - Static data
**Priority:** P3 - Enhancement

---

## LOW Severity Issues (Test Infrastructure - Acceptable)

### Test Data Patterns (Acceptable for Tests)
The following patterns are ACCEPTABLE as they're only used in test files:

1. **Test Symbols:** `["AAPL", "MSFT", "GOOGL"]` in test files
2. **Mock User IDs:** `test-user-123` in test files
3. **Test Quantities:** `quantity: 100` in test files
4. **Test Prices:** `current_price: 150` in test files

**Files:**
- `/home/stocks/algo/webapp/lambda/tests/**/*.test.js`
- `/home/stocks/algo/webapp/frontend/src/tests/**/*.test.jsx`

**Status:** ✅ ACCEPTABLE - These are proper test fixtures

---

## Configuration Constants (Acceptable)

### Default Configuration Values
**Files:**
- `/home/stocks/algo/config.py:23,51,61`
- `/home/stocks/algo/config.js:132,152,161`

```python
EARNINGS_STABILITY_DEFAULT = 0.50  # ✅ Named constant for configuration
VALUATION_NEUTRAL_SCORE = 50.0     # ✅ Named constant for configuration
SENTIMENT_SCORE_DEFAULT = 50.0     # ✅ Named constant for configuration
```

**Status:** ✅ ACCEPTABLE - These are properly documented configuration defaults

---

## Technical Indicators (Acceptable)

### RSI/Technical Calculations
**Pattern:** `= 100 - (100 / (1 + rs))`

**Files:** Multiple Python loaders
- `/home/stocks/algo/loadstockscores.py:231`
- `/home/stocks/algo/loadtechnicalsdaily.py:110`
- `/home/stocks/algo/loadtechnicalsmonthly.py:97`

**Status:** ✅ ACCEPTABLE - Standard RSI formula, not fake data

### Moving Averages
**Pattern:** `MA_LENGTH = 50`, `window=50`, `sma_50`

**Status:** ✅ ACCEPTABLE - Standard 50-day moving average window

---

## Summary Statistics

### Issue Distribution by Type
```
Critical Production Issues:    4
High Severity Issues:          3
Medium Severity Issues:        12
Low Severity (Acceptable):     ~50
```

### Files Requiring Immediate Fix
1. `/home/stocks/algo/webapp/lambda/loadstockscores.py` - Lines 354-355
2. `/home/stocks/algo/webapp/lambda/middleware/auth.js` - Lines 65-89
3. `/home/stocks/algo/webapp/lambda/sync_portfolio.js` - Lines 85-108
4. `/home/stocks/algo/webapp/lambda/utils/apiKeyService.js` - Lines 90-119
5. `/home/stocks/algo/webapp/lambda/utils/alertSystem.js` - Lines 615, 632
6. `/home/stocks/algo/webapp/lambda/utils/riskEngine.js` - Lines 220-222

---

## Remediation Roadmap

### Phase 1: Critical Security Fixes (P0 - Immediate)
**Timeline:** Before ANY production deployment

1. **Remove auth bypass tokens** in production (auth.js, apiKeyService.js)
2. **Remove test user injection** in sync_portfolio.js
3. **Add environment checks** for all test-only code paths

### Phase 2: Critical Data Fixes (P0 - Immediate)
**Timeline:** Before next data load

1. **Fix hardcoded scores** in loadstockscores.py
   - Calculate real positioning scores from positioning data
   - Calculate real sentiment scores from news/social data
   - Set to NULL if data unavailable
   - Adjust composite score calculation to handle missing factors

2. **Fix risk engine fallbacks** in riskEngine.js
   - Validate required position data
   - Throw errors instead of using fake values
   - Update callers to handle validation errors

### Phase 3: High Priority Fixes (P1 - Next Sprint)
**Timeline:** Within 2 weeks

1. **Fix alert system** to fail explicitly when not configured
2. **Replace hardcoded examples** with dynamic data
3. **Add data validation** across all loaders

### Phase 4: Medium Priority Fixes (P2 - Next Release)
**Timeline:** Within 1 month

1. **Frontend score display** - Replace `|| 0` with `?? "N/A"`
2. **Dynamic stock lists** - Replace hardcoded symbols
3. **Improve error messaging** for missing data

---

## Testing Requirements

### Before Deployment
1. ✅ Verify NO test tokens accepted in production
2. ✅ Verify NO fake scores in database
3. ✅ Verify NO test users in production database
4. ✅ Verify alert system fails gracefully when not configured
5. ✅ Verify risk calculations fail with invalid data instead of using fallbacks

### Validation Queries
```sql
-- Check for fake scores
SELECT COUNT(*) FROM stock_scores
WHERE positioning_score = 70.0 AND sentiment_score = 70.0;

-- Should return 0 after fix

-- Check for test users
SELECT * FROM users WHERE user_id IN
  ('default_user', 'dev-user-bypass', 'test-user-123', 'mock-user-123');

-- Should return 0 in production
```

---

## Monitoring Recommendations

### Add Alerts For:
1. Authentication using test tokens in production
2. Scores with NULL values (track % of missing data)
3. Email send failures (currently silent)
4. Risk calculations with missing position data

### Metrics to Track:
- % of stocks with complete score data
- % of stocks with positioning data
- % of stocks with sentiment data
- Email delivery success rate
- Authentication failures from invalid tokens

---

## Conclusion

**RECOMMENDATION:** DO NOT DEPLOY TO PRODUCTION until Critical (P0) issues are resolved.

The codebase contains multiple critical issues where production code uses mock data, hardcoded values, and security bypasses. While test infrastructure properly uses test data, several production code paths contain dangerous fallbacks and fake values that will corrupt user data and create security vulnerabilities.

**Priority Actions:**
1. Immediately fix authentication bypasses
2. Remove test user injection from production sync
3. Fix hardcoded sentiment/positioning scores
4. Add environment-based guards for all test-only code
5. Implement proper error handling instead of silent fallbacks

**Total Estimated Effort:** 16-24 hours for all Critical + High issues

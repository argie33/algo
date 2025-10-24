# Hardcoded Data - Complete Action Plan

## 🚨 Executive Summary

**Status**: Comprehensive audit completed - **3 CRITICAL issues found** that are serving fake data to users.

Your codebase has **12 instances of hardcoded/mock data**, with **3 critical issues** where users are actively seeing fabricated financial information. These could lead to bad trading decisions.

---

## 🔴 CRITICAL - MUST FIX IMMEDIATELY

### 1. Sentiment Loader Generates Random Fake Data
**File**: `/home/stocks/algo/loadsentiment.py` (Lines 240-331)
**Severity**: **CRITICAL** ⚠️

**The Problem**:
Users see sentiment scores that are **completely fabricated** random numbers:

```python
# Lines 240-331: Generates fake random data!
data['reddit_sentiment_score'] = np.random.normal(0.1, 0.3)  # FAKE!
data['search_volume_index'] = np.random.randint(0, 100)      # FAKE!
data['search_trend_7d'] = np.random.normal(0.0, 0.1)         # FAKE!
```

**Impact**:
- ❌ Users trust sentiment scores that are random numbers
- ❌ Could influence bad trading decisions
- ❌ No validation that data is real vs fake
- ❌ Database stores random data, appears legitimate

**What To Do**:

**Option A: Implement Real APIs** (Best)
```
1. Setup Reddit API (PRAW library) - get real mention counts & sentiment
2. Setup Google Trends API - get real search volume data
3. Setup NewsAPI or FinancialModelingPrep - get real news sentiment
4. Replace random generation with real API calls
```

**Option B: Disable For Now** (Quick fix)
```
1. Comment out or remove sentiment loader
2. Set all sentiment fields to NULL in database
3. Add database migration to clear fake data
4. Display "Sentiment data unavailable" instead of fake scores
```

**RECOMMENDED**: Option B for now, plan Option A for future

---

### 2. Economic Correlation Matrix - Hardcoded 0.5
**File**: `/home/stocks/algo/webapp/lambda/routes/economic.js` (Lines 808-820)
**Severity**: **CRITICAL** ⚠️

**The Problem**:
```javascript
// ALL non-diagonal correlations are hardcoded to 0.5:
if (i === j) {
  correlationMatrix[series1][series2] = 1.0;  // Correct (self-correlation)
} else {
  correlationMatrix[series1][series2] = 0.5;  // ALWAYS 0.5! WRONG!
}
```

**Example of What Users See**:
```
Correlation Matrix:
                GDP    Inflation  Unemployment
GDP            1.00      0.50       0.50
Inflation      0.50      1.00       0.50
Unemployment   0.50      0.50       1.00
```

**Reality**: These correlations are completely different! They're not always 0.50.

**Impact**:
- ❌ Economic analysis is meaningless
- ❌ Diversification advice based on fake correlations
- ❌ Risk calculations are completely wrong
- ❌ Users make bad decisions based on fake data

**What To Do**:
```javascript
// BEFORE (broken):
correlationMatrix[series1][series2] = 0.5;

// AFTER (real):
const pearsonCorr = calculatePearsonCorrelation(
  economicData[series1],
  economicData[series2]
);
correlationMatrix[series1][series2] = pearsonCorr.toFixed(3);
```

**Steps**:
1. Query `economic_data` table for both series
2. Find overlapping date ranges
3. Calculate Pearson correlation coefficient on the values
4. Return actual correlation (-1.0 to 1.0)

---

### 3. Market Correlation Matrix - Hardcoded 0.6/0.7/0.4/0.1
**File**: `/home/stocks/algo/webapp/lambda/routes/market.js` (Lines 5000-5043)
**Severity**: **CRITICAL** ⚠️

**The Problem**:
```javascript
// Correlations hardcoded based on symbol PATTERNS, not real data:
if (isTech1 && isTech2) {
  correlation = 0.6;  // All tech stocks assumed 0.6 correlated
} else if (isETF1 && isETF2) {
  correlation = 0.7;  // All ETFs assumed 0.7 correlated
} else if ((isTech1 && isETF2) || (isETF1 && isTech2)) {
  correlation = 0.4;  // Tech/ETF mix assumed 0.4 correlated
} else {
  correlation = 0.1;  // Everything else assumed 0.1 correlated
}
```

**Example**:
- Tesla (TSLA) + Nvidia (NVDA) = 0.6 (hardcoded, not real)
- SPY + QQQ = 0.7 (hardcoded, actually ~0.95!)
- TSLA + SPY = 0.4 (hardcoded, varies significantly)

**Impact**:
- ❌ Portfolio correlation analysis is fake
- ❌ Risk calculations are wrong
- ❌ Diversification recommendations are incorrect
- ❌ Users build poorly diversified portfolios based on fake correlations

**What To Do**:
```javascript
// BEFORE (broken):
correlation = 0.6;  // Hardcoded

// AFTER (real):
const returns1 = calculateReturns(prices1);
const returns2 = calculateReturns(prices2);
const correlation = calculatePearsonCorrelation(returns1, returns2);
```

**Steps**:
1. Query `price_daily` for both symbols
2. Calculate daily returns: (close[t] - close[t-1]) / close[t-1]
3. Calculate Pearson correlation of returns
4. Cache results (correlation is stable over time)

---

## 🟠 HIGH SEVERITY - SHOULD FIX

### 4. News Analyzer - Returns Hardcoded 0.5
**File**: `/home/stocks/algo/webapp/lambda/utils/newsAnalyzer.js` (Line 315)
**Issue**: When news analysis fails, returns neutral 0.5 instead of NULL
**Fix**: Return `null` or `undefined` to indicate missing data

---

### 5. Sentiment Engine - Returns Hardcoded 0.5
**File**: `/home/stocks/algo/webapp/lambda/utils/sentimentEngine.js` (Line 98)
**Issue**: Default sentiment is 0.5 (neutral) instead of NULL
**Fix**: Return `null` to indicate missing data

---

### 6. Positioning Loader - All Holders Get 0.5 Quality
**File**: `/home/stocks/algo/loadpositioning.py` (Line 210)
**Issue**: All institutional holders assigned default 0.5 quality
**Fix**: Implement real holder quality scoring based on:
- Holder AUM (larger = better)
- Track record (historical returns)
- Reputation/category
- Concentration risk

---

## 🟡 MEDIUM SEVERITY - NICE TO HAVE

### 7. Score Confidence - All 90.0
**File**: `/home/stocks/algo/loadscores.py` (Lines 307, 333, 357, 383, 409, 435)
**Status**: Acceptable as default, but could be enhanced
**Current**: All scores get 90% confidence
**Better**: Calculate confidence based on:
- Data completeness (0-100%)
- Number of indicators available
- Data recency
- Calculation complexity

---

## Implementation Priority

### Week 1: CRITICAL Fixes
```
[ ] 1. Disable sentiment loader fake data generation
[ ] 2. Fix economic correlation matrix
[ ] 3. Fix market correlation matrix
```

### Week 2: HIGH Fixes
```
[ ] 4. Fix newsAnalyzer fallback to NULL
[ ] 5. Fix sentimentEngine fallback to NULL
[ ] 6. Fix positioning holder quality scoring
```

### Week 3: MEDIUM Enhancements
```
[ ] 7. Enhance confidence score calculations
```

---

## Testing Plan

After each fix, verify:

1. **Correlation Tests**:
   ```bash
   # Test API endpoints return real values
   curl http://localhost/api/market/correlation
   # Should see varied correlations (0.1 to 0.9), not all 0.5
   ```

2. **Sentiment Tests**:
   ```bash
   # Check sentiment table
   SELECT DISTINCT reddit_sentiment_score FROM sentiment
   # Should see empty/NULL, not random values
   ```

3. **Database Cleanup**:
   ```sql
   -- After fixing sentiment loader, clean old fake data:
   DELETE FROM sentiment
   WHERE date < '2025-10-23'  -- Before fix date
   ```

---

## Summary of Changes Needed

| Issue | File | Current | Should Be | Priority |
|-------|------|---------|-----------|----------|
| Sentiment Random | loadsentiment.py | Random numbers | Real APIs or NULL | CRITICAL |
| Economic Corr | economic.js | 0.5 always | Real correlation | CRITICAL |
| Market Corr | market.js | 0.6/0.7/0.4/0.1 | Real correlation | CRITICAL |
| News Fallback | newsAnalyzer.js | 0.5 | NULL | HIGH |
| Sentiment Fallback | sentimentEngine.js | 0.5 | NULL | HIGH |
| Holder Quality | loadpositioning.py | 0.5 always | Real quality score | HIGH |
| Confidence | loadscores.py | 90.0 always | Data-based | MEDIUM |

---

## Verification Commands

Run these after each fix to verify real data:

```bash
# Check sentiment doesn't have random numbers
sqlite3 database.db "SELECT DISTINCT reddit_sentiment_score FROM sentiment ORDER BY RANDOM() LIMIT 5"

# Check correlations are varied
curl http://localhost/api/market/correlation?symbols=SPY,QQQ,DIA,IWM | jq '.correlation_matrix'

# Check correlations from economic endpoints
curl http://localhost/api/economic/correlation | jq '.data.correlation'

# Verify no hardcoded 0.5 in responses
grep -r "\"0.5\"" webapp/lambda/routes/*.js
```

---

## Next Steps

1. **Immediately**: Decide on sentiment loader approach (Option A or B)
2. **Today**: Fix correlation matrices (both economic and market)
3. **This Week**: Fix fallback values (newsAnalyzer, sentimentEngine)
4. **This Month**: Implement real holder quality and enhanced confidence

This ensures users see **real data only**, preventing bad trading decisions based on fabricated information.


# Exposure Score AAII Factor Audit - Session 361

## Executive Summary

The AAII sentiment factor has **3 critical issues**:
1. **DATA CORRUPTION (100x underflow)** - All values in database are 0.3-0.4% instead of 30-40%
2. **SCORING LOGIC IS BACKWARDS** - Current formula is NOT contrarian; both bullish and bearish extremes get same high score
3. **DEAD CODE** - Better contrarian implementation exists but is never used

**Impact:** AAII always scores 0/3 pts currently. Even with perfect data, the non-contrarian formula and dead code mean it never works as intended.

---

## Finding 1: Data Corruption (100x Underflow)

### Current Database State
```
Date         Bullish  Bearish  Neutral  Spread  Status
2026-07-23   0.3%     0.4%     0.3%     -0.1    ← All spreads near zero
2026-07-16   0.4%     0.3%     0.2%     +0.1
2026-07-09   0.4%     0.4%     0.3%     -0.0
(all rows similar - impossibly small values)
```

### What Correct AAII Data Should Look Like
```
Historical range: 15-55% per sentiment (real AAII survey results)
Example week: Bullish=45%, Bearish=25%, Neutral=30% (realistic spread of +20)
```

### The Problem
- All current values are 0.2-0.5% (should be 20-50%)
- Off by exactly 100x factor
- Makes all spreads near zero (-0.2 to +0.1)
- Causes the factor to always score 0 points

### Scoring Impact
```
Current corrupted data:
  Bull=0.3%, Bear=0.4%, Spread=-0.1
  Score = min(100, max(0, (abs(-0.1) - 15) * 5))
  Score = max(0, -74.75) = 0.0 pts / 3

With correct data (Bull=35%, Bear=25%, Spread=+10):
  Score = min(100, max(0, (abs(10) - 15) * 5))
  Score = max(0, -25) = 0.0 pts / 3  ← Still 0! (needs spread >= 15)

With extreme data (Bull=55%, Bear=15%, Spread=+40):
  Score = min(100, max(0, (abs(40) - 15) * 5))
  Score = min(100, 125) = 100 pts / 3
```

**Root Cause:** Likely a unit conversion bug in `loaders/load_aaii_sentiment.py` when parsing Excel percentages. Needs investigation of the Excel parsing logic.

---

## Finding 2: Scoring Logic is NOT Contrarian

### Current Implementation (market_factor_calculator.py:548)
```python
spread = bull - bear
score = min(100, max(0, (abs(spread) - 15) * 5))
```

### The Problem: Both Extremes Get Same Score
```
Extreme Bullish (Bull=55%, Bear=15%):
  Spread = +40
  Score = (abs(40) - 15) * 5 = 100 pts ← HIGH score for bullish sentiment

Extreme Bearish (Bull=15%, Bear=55%):
  Spread = -40
  Score = (abs(-40) - 15) * 5 = 100 pts ← HIGH score for bearish sentiment

Result: BOTH extremes score 100/100 pts
This is the OPPOSITE of contrarian!
```

### Proper Contrarian Scoring
In true contrarian analysis:
- **Extreme bearish** (when everyone is scared) should give **HIGH exposure score** (bullish signal) 
- **Extreme bullish** (when everyone is greedy) should give **LOW exposure score** (bearish signal)

Example from dead code (`algo/risk/factors/aaii_sentiment_factor.py`):
```python
# Extremely bearish (spread < -15) = bullish signal
if spread < -15:
    score = 75 + min(10, abs(spread + 15) / 5)  # 75-85 pts (HIGH)
    
# Extremely bullish (spread > 15) = bearish signal  
elif spread > 15:
    score = 25 - min(10, (spread - 15) / 5)  # 15-25 pts (LOW)
    
# Neutral range
else:
    score = 50  # Middle ground
```

### Documentation Claims vs Reality
Header comment in `market_exposure.py` line 22:
```
3pt  AAII SENTIMENT        contrarian at extremes only (±15+ spread; neutral in middle range)
```

**What it claims:** Contrarian at extremes (bearish → high score, bullish → low score)  
**What it actually does:** Non-contrarian absolute value scaling (both extremes → high score)

---

## Finding 3: Dead Code - Better Implementation Never Used

### File: `algo/risk/factors/aaii_sentiment_factor.py`
- Proper contrarian implementation  
- Never instantiated or imported except as dead code in `__init__.py`
- Has correct logic that differs from `MarketFactorCalculator.aaii()`

### Why It Matters
Two implementations of AAII scoring exist with different logic:

| Aspect | MarketFactorCalculator | AAIISentimentFactor |
|--------|------------------------|---------------------|
| Used? | ✅ YES (active) | ❌ NO (dead code) |
| Spread=-40 | 100 pts | ~80 pts (contrarian) |
| Spread=+40 | 100 pts | ~20 pts (contrarian) |
| Spread=0 | 0 pts | 50 pts (neutral) |

The dead code version is actually the right approach.

---

## Finding 4: Minimal Weight (Not a Showstopper)

### AAII in Context of 12-Factor Composite
```
Exposure Score = 12 factors, 100 pts total

Factor Weights:
  Trend 30-week:        15 pts
  SPY momentum:         10 pts
  Breadth 200-DMA:      10 pts
  Selling pressure:     10 pts
  VIX regime:           10 pts
  Credit spreads:       10 pts
  Put/call ratio:        8 pts
  New highs-lows:        7 pts
  A/D line:              6 pts
  Breadth 50-DMA:        6 pts
  NAAIM:                 5 pts
  AAII SENTIMENT:        3 pts ← Only 3%
```

**Impact:** Even perfect AAII factor can only change exposure by 0-3 percentage points.  
Currently broken, it contributes 0. If fixed, contributes max 3.

---

## Data Quality Timeline

### Questions
1. **When did the 100x underflow start?** Check loader git history
2. **Is this from Excel parsing or AAII data itself?** Need loader debugging
3. **How long has AAII scored 0?** Check market_exposure_daily.factors history

### What Needs Investigation
```python
# In loaders/load_aaii_sentiment.py:
df[col] = pd.to_numeric(df[col], errors="coerce")  # Line 265
# Are percentages coming in as 0.003 (fraction) instead of 0.3 (percent)?
# Check if AAII Excel format changed or if parsing logic is wrong
```

---

## Recommendations

### Priority 1: Fix Data Corruption
1. Audit AAII Excel file parsing in `load_aaii_sentiment.py`
2. Verify input data format (is AAII sending 0.003 or 0.3?)
3. Check if there's a 100x scaling bug in the parser
4. Backfill correct AAII data once source is identified

### Priority 2: Fix Scoring Logic
Choose one:
- **Option A:** Replace with `AAIISentimentFactor` implementation (proper contrarian scoring)
- **Option B:** Fix `MarketFactorCalculator.aaii()` to do proper contrarian logic:
  ```python
  if spread < -15:  # Many bears = bullish signal
      score = 75 + min(10, abs(spread + 15) / 5)
  elif spread > 15:  # Many bulls = bearish signal
      score = 25 - min(10, (spread - 15) / 5)
  else:
      score = 50  # Neutral
  ```

### Priority 3: Remove Dead Code
- Delete unused `AAIISentimentFactor` class unless it's being preserved as reference

### Priority 4: Update Documentation
- Align header comments with actual implementation
- Document that AAII is only 3 pts (very small impact)
- Note the 15-point threshold needed to affect score

---

## Code Paths Reviewed

**Data Loading:**
- `loaders/load_aaii_sentiment.py` - Fetches AAII via Playwright, parses Excel

**Scoring (Active):**
- `algo/risk/market_factor_calculator.py:532-566` - aaii() method with non-contrarian formula
- `algo/risk/market_exposure.py:559` - Calls calculator.aaii()

**Scoring (Dead Code):**
- `algo/risk/factors/aaii_sentiment_factor.py` - Proper contrarian implementation (never used)

**Dashboard Display:**
- `dashboard/panels/exposure.py:187-199` - Shows AAII bullish/bearish percentages

---

## Summary Table

| Issue | Severity | Status | Impact |
|-------|----------|--------|--------|
| Data 100x underflow | CRITICAL | Confirmed | AAII always 0/3 pts |
| Non-contrarian scoring | HIGH | Confirmed | Wrong signal direction |
| Dead code alternatives | MEDIUM | Confirmed | Tech debt |
| Low weight (3pts) | LOW | By design | Max ±3pt swing |

**Overall:** AAII factor is currently non-functional due to data corruption and wrong scoring logic. Needs fixing before it can contribute meaningfully to exposure score.

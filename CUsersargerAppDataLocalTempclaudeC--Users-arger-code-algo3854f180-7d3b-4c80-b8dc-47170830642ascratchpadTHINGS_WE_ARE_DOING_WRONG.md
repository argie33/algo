# Data Loading - Things We Are Doing Wrong

## Problem 1: We're Loading Data for the Wrong Universe

**Current state:**
- price_daily: 10,929 symbols (delisted, ETFs, indices)
- annual_income_statement: 5,796 symbols (more than we score)
- stock_scores: 5,476 symbols (what we actually use)

**What this means:**
- **5,453 extra symbols** with price data we never score
- **~330 symbols** with SEC data we never use
- **5,158 ETFs** we load prices for, then filter out during scoring
- Massive wasted data loading

**Why this is wrong:**
- Inefficient (loading 2x data we don't use)
- Confusing (undefined universe boundaries)
- Error-prone (unclear what should/shouldn't be loaded)

---

## Problem 2: ETFs and Special Entities Are In Scoring Universe

**Current:**
- 5 ETFs in stock_scores: SPY, QQQ, IWM, EFA, AGG
- 6 special entities: ADIG, BANL, ILLR, SDOT, STLN, TWO (REITs, shell companies)
- These have NO SEC income statements (no PE ratio possible)

**Why this is wrong:**
- You can't compute fundamental scores for indices/ETFs (no earnings, no debt ratios)
- These shouldn't be in a "stock score" table at all
- They're polluting the data—creating 591 "missing value score" entries

**The fix:**
- Remove ETFs from stock_scores BEFORE loading
- Decide on special entities: exclude if no fundamentals, or clearly mark as non-scoreable

---

## Problem 3: Mismatched Data Loading Scope

**We're loading:**
1. Prices for 10,929 symbols ✓ (ok—market data is universal)
2. SEC data for 5,796 symbols (but only 5,476 in scores)
3. Analyst estimates for 3,979 symbols (72.7% coverage)
4. 13F data for 3,365 symbols (61.4% coverage)
5. Scores computed for 5,476 symbols

**The problem:**
- No clear universe definition
- Each loader has different assumptions about what it's loading for
- Creates gaps when loaders don't align

**Correct approach:**
```
Define Universe → Load Only For That → Fill Gaps Intentionally
5,476 stocks
  ├─ Load SEC data (if available)
  ├─ Load prices (always available)
  ├─ Load analyst estimates (if available—72% coverage OK)
  └─ Load ownership (if available—61% coverage OK)
```

---

## Problem 4: Unclear Data Quality Standards

**What we're doing now:**
- Load whatever data is available
- Try to compute scores even if data is partial
- Use fallbacks and validation gates inconsistently
- Mark as "unavailable" when it doesn't meet arbitrary thresholds

**What we should do:**
- Define MINIMUM DATA REQUIREMENTS upfront:
  - VALUE score: PE ratio (SEC or analyst forward PE)
  - GROWTH score: 2+ years historical revenue/EPS (SEC only)
  - QUALITY score: ROE, margins, debt ratios (SEC only)
  - MOMENTUM score: 30+ days of price history + technical
  - POSITIONING score: 13F + insider holdings (if available, else NULL)

**Then:**
- Only compute score if minimum data is available
- Use consistent methodology (no ad-hoc fallbacks)
- Exclude stocks that don't meet minimum standards

---

## Problem 5: Analyst Data Strategy is Backwards

**What we're doing:**
- Load analyst estimates (3,979 symbols = 72.7%)
- Try to use them as fallback for missing SEC data
- Have inconsistent validation gates that sometimes count them, sometimes don't

**What we should do:**
- **Analyst data is NOT a fallback for SEC**
- **Analyst data IS a forward-looking signal** (different from historical growth)
- Use analyst forward PE / estimate revisions as SEPARATE inputs
- Don't try to patch missing SEC data with analyst estimates

---

## Problem 6: Positioning Metrics Incomplete by Design

**Current:**
- 13F data: 3,365 symbols (61.4%)
- Insider data: 5,481 symbols (100%—but mostly empty)
- Short interest: missing for OTC/small-cap (expected)

**Wrong approach:**
- Only create positioning_metrics row if ALL three components available
- This leaves 640 stocks with no positioning data

**Right approach:**
- Create positioning_metrics for ALL symbols
- Use NULLs for missing components (institutional=NULL, insider=NULL, short=NULL)
- Let the scoring logic handle partial data
- Be transparent: "no 13F data for this OTC stock" vs. "no positioning score computed"

---

## What We Should Do Instead

### Step 1: Define the Real Universe
```python
# Only score stocks that:
1. Are NOT ETFs (use etf_symbols table to filter)
2. Are NOT indices
3. Are NOT delisted (check if price_daily has recent data)
4. Have SEC data OR analyst estimates available
```

### Step 2: Define Data Requirements Per Score

**VALUE score requires:**
- ✓ Current price (price_daily)
- ✓ Either: (PE ratio from SEC) OR (forward PE from analyst)
- ✓ Exclude: no data at all

**GROWTH score requires:**
- ✓ 2+ years SEC income statement history
- ✓ Exclude: pre-revenue, no historical data
- ✗ Don't use analyst estimates as "growth"

**QUALITY score requires:**
- ✓ Latest SEC financials (balance sheet + income statement)
- ✓ Exclude: no SEC data

**MOMENTUM score requires:**
- ✓ 30+ days price history
- ✓ Technical indicators (almost all stocks have this)

**POSITIONING score requires:**
- ✓ Create row for ALL stocks
- ✓ NULL out components that don't exist
- ✓ Be transparent about what's available

### Step 3: Load Only for Target Universe

```
Primary Universe: 5,476 stocks
├─ prices: Load for all (10,929 symbols acceptable, filter at query time)
├─ SEC data: Load if exists (natural filtering)
├─ analyst data: Load if exists (72% coverage is OK)
├─ 13F/insider: Load if exists (61% coverage is OK)
└─ scoring: Only for stocks that meet MINIMUM requirements
```

### Step 4: Be Transparent About Gaps

Instead of trying to patch with fallbacks:
```
Stock SPYXX (made-up SPAC):
  - NO SEC data → value_score = NULL (by design)
  - NO analyst estimates → forward_pe = NULL
  - Result: "Insufficient valuation data—not scoreable"
  
Stock AAPL:
  - SEC PE = 43.91
  - SEC growth = 15.2% (3-year)
  - Analyst forward PE = 41.5
  - Result: "Full data available"

Stock SMALLCAP:
  - NO 13F data → institutional_ownership = NULL
  - No insider filings → insider_pct = NULL
  - Result: "Positioning metrics unavailable for this OTC stock"
```

---

## Summary: The Right Way

1. **Define universe explicitly** (not "whatever we loaded")
2. **Load from authoritative sources only** (SEC for fundamentals, not yfinance/analyst fallbacks)
3. **Exclude non-scoreable symbols** (ETFs, indices, shells with no data)
4. **Use clear minimum requirements** (not arbitrary validation gates)
5. **Be transparent about limitations** (show why data is missing, don't hide it)
6. **Don't force scores on incomplete data** (better to have 4,500 good scores than 5,476 mediocre ones)

This is how you build a system a trading algo can TRUST.


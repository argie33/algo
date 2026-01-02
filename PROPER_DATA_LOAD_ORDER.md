# Proper Data Loading Order - DO NOT SKIP STEPS

**Current Status:**
- ❌ Step 1: loaddailycompanydata.py - NOT DONE (earnings table is EMPTY)
- ❌ Step 2: loadstockscores.py - Partially done (but incomplete without earnings)

---

## Correct Sequence (REQUIRED)

### **STEP 1: Load Company Data + Earnings** (CRITICAL - MUST DO FIRST)
```bash
python3 loaddailycompanydata.py
```

**What this populates:**
- ✅ company_profile (ticker info)
- ✅ earnings (CRITICAL for P/E, earnings growth)
- ✅ earnings_estimate_trends
- ✅ earnings_estimates
- ✅ revenue_estimates
- ✅ positioning_metrics (institutional, insider ownership)
- ✅ institutional_positioning
- ✅ insider_transactions
- ✅ insider_roster

**Time:** 45-90 minutes (5,300 stocks, ~1 API call per stock)
**Output:** ~50,000+ earnings rows, ~5,000+ stocks with positioning data

---

### **STEP 2: Load Stock Scores** (WITH EARNINGS DATA)
```bash
python3 loadstockscores.py
```

**What this calculates:**
- ✅ value_score (uses P/E from earnings - ONLY WORKS IF earnings table populated)
- ✅ quality_score (uses earnings quality metrics)
- ✅ growth_score (uses earnings growth - ONLY WORKS IF earnings table populated)
- ✅ momentum_score (technical momentum)
- ✅ stability_score (volatility, beta)
- ✅ positioning_score (institutional ownership - ONLY WORKS IF positioning table populated)
- ✅ composite_score (weighted average of all 7)

**Time:** 10-20 minutes (uses pre-calculated metrics)
**Output:** 5,300 stock scores with all 7 factors

---

## Why Order Matters

### Without earnings data:
- ❌ P/E ratio missing for 46% of stocks
- ❌ PEG ratio missing for 83% of stocks
- ❌ Earnings growth scores incomplete
- ❌ Value metrics sparse (54% coverage instead of 95%+)
- ❌ Scores are incomplete

### With earnings data:
- ✅ P/E ratio available for 90%+ of stocks
- ✅ PEG ratio available for 80%+ of stocks
- ✅ Earnings growth scores complete
- ✅ Value metrics comprehensive
- ✅ All 7 factor scores properly calculated

---

## Starting Now

Running in correct order:
1. **loaddailycompanydata.py** → populate earnings (FIRST)
2. **loadstockscores.py** → calculate scores (SECOND)

Let's go!

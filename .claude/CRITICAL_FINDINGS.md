# 🚨 CRITICAL FINDINGS — SESSION 2026-05-17

## Issue #1: Trade Generation Pipeline Completely Stalled

### Evidence
- **buy_sell_daily:** 215 BUY signals on 2026-05-15
- **algo_trades:** 1 record (SPY external, imported from Alpaca)
- **Root Cause:** FilterPipeline is rejecting ALL signals

### Why All Signals Are Rejected

**Signal Generation (`loadbuyselldaily.py`):**
- Generates BUY signals when RSI < 30 (permissive, all stages)
- No stage filtering during generation

**FilterPipeline Stage Filter (Phase 5):**
- Line 204-208: `if stage_number != 2: SKIP`
- **ONLY accepts Weinstein Stage 2** (established uptrend)
- All Stage 1 (early), Stage 4 (distribution) signals REJECTED

**Data Shows:**
```
Sample signals from 2026-05-15:
  BBIB    | Stage 4 | ✗ REJECTED (not Stage 2)
  BBDO    | Stage 1 | ✗ REJECTED (not Stage 2)
  CGHM    | Stage 4 | ✗ REJECTED (not Stage 2)
  CGMU    | Stage 4 | ✗ REJECTED (not Stage 2)
  ...
  (ALL 215 signals checked, most are NOT Stage 2)
```

### The Waterfall

```
215 BUY signals
  ├─ PRE-TIER: earnings blackout, signal age
  ├─ TIER 1: no trend data
  ├─ TIER 2: NO STAGE 2 CONFIRMATION ← ALL FILTERED HERE
  ├─ TIER 3: trend template
  ├─ TIER 4: signal quality
  ├─ TIER 5: portfolio fit
  └─ RESULT: 0 qualified trades → 0 entries
```

### Impact
- Orchestrator cannot validate strategy
- Cannot measure paper trading performance
- System appears non-functional (no trades = broken)

---

## Issue #2: Signal-to-Stage Mismatch

### Problem
- **Signal Generator** produces signals across all stages (no filtering)
- **Orchestrator** wants ONLY Stage 2 entries
- **No bridge/configuration** to align them

### Options to Fix
1. **Restrict signal generation** to Stage 2 only (`loadbuyselldaily.py`)
2. **Relax FilterPipeline** to accept multiple stages
3. **Add configuration flag** to control which stages to trade
4. **Add stage-specific tier to signal generator** (generate stage-aware signals)

### Recommendation
**Option 1: Restrict signal generation to Stage 2**
- Reduces noise in buy_sell_daily
- Lets FilterPipeline be pure confirmation/validation
- Simpler, fewer moving parts
- Could add Stage field to config for flexibility later

---

## Issue #3: Additional Concerns (Discovered During Assessment)

### Coverage Gaps
- 19.2% of registered stocks have price data (1,953 / 10,167)
- 17.5% of stocks have signals (1,780 / 10,167)
- **Question:** Why are 8,214 stocks registered but without data?
- **Action:** Determine if registering all stocks or trimming to active set

### Data Quality (Good News ✅)
- 6.5M rows, 122 tables
- Scores complete (9,989 stocks, 0 NULLs)
- Price data fresh (through 2026-05-15)
- Signals being generated (215/119 BUY/SELL)
- Economic data current

### Calculation Verification Needed
- Stock score weighting (20% momentum, 19% growth, etc.) — looks reasonable
- Signal filters (60% close in range, 1.25x volume ratio) — reasonable
- Swing score thresholds (min 60.0) — may be too strict?
- Market stage requirements — Stage 2 only appropriate?

---

## 🎯 IMMEDIATE ACTIONS (Next 4 Hours)

### CRITICAL FIX #1: Restore Trade Generation
**Task:** Modify `loadbuyselldaily.py` to filter signals to Stage 2 only

```python
# In _generate_signal_row():
stage_info = trend_data.get(date_val, {})
stage = stage_info.get('stage_number')
if stage != 2:  # Only generate signals for Stage 2
    return None
```

**Expected Result:**
- buy_sell_daily will have fewer but higher-quality signals
- FilterPipeline won't reject all signals
- Trades will be generated from qualified signals
- Orchestrator becomes functional

**Validation:**
- Rerun loadbuyselldaily.py
- Check buy_sell_daily row count (should drop significantly)
- Rerun orchestrator
- Verify algo_trades gets new entries

---

### CRITICAL FIX #2: Validate Signal Quality
**Task:** Run orchestrator with verbose logging to see tier pass-through

```
TIER PASS-THROUGH:
  T1 Data Quality: X/N
  T2 Market Health: X/N
  T3 Trend Template: X/N
  T4 Signal Quality: X/N
  T5 Portfolio: X/N
```

**If many pass Tier 1-5 but fail advanced filters:**
- Advanced filter thresholds may be too strict
- Check swing score (default 60.0) — too high?
- Check market exposure tier settings

---

### CRITICAL FIX #3: Coverage Audit
**Task:** Understand why 8,214 stocks have no data

```sql
SELECT status, COUNT(*) 
FROM stock_symbols 
GROUP BY status;  -- Check what status these stocks have

SELECT COUNT(DISTINCT symbol) 
FROM stock_symbols ss
WHERE NOT EXISTS (SELECT 1 FROM price_daily WHERE symbol = ss.symbol);
-- How many registered stocks have literally zero price data?
```

**Hypothesis:**
- Some stocks are for international/historical tracking
- Some are delisted or low-volume
- Some should be excluded from active trading

**Action:**
- Document coverage decisions
- Consider filtering registry to only active, liquid stocks
- Or accept that many stocks won't have signals

---

## 📊 System Readiness Update

| Component | Before Fix | After Fix | Notes |
|-----------|-----------|-----------|-------|
| **Trade Generation** | 🔴 0/215 | 🟢 TBD | Depends on Stage 2 signal count |
| **Signal Filtering** | 🔴 100% rejected | 🟡 TBD | Need to see tier pass-through |
| **Data Freshness** | 🟢 Good | 🟢 Good | No change |
| **Coverage** | 🔴 19.2% | ⚠️ TBD | Decision pending |
| **Overall** | 🔴 2/10 | 🟡 5-6/10 | Depends on fixes |

---

## NEXT SESSION AGENDA

1. **Implement Fix #1:** Stage 2 signal generation
2. **Validate Fix #1:** Rerun orchestrator, verify trades
3. **Analyze Fix #2:** Understand tier pass-through
4. **Address Fix #2:** Adjust thresholds if needed
5. **Document Fix #3:** Coverage strategy

---

## KEY QUESTIONS FOR USER

1. **Stage filtering:** Is Stage 2-only correct for swing trading? Or should we include other stages?
2. **Stock coverage:** Should we trim registry to only active/liquid stocks? Or keep all?
3. **Swing score threshold:** Is 60.0 too strict? What's the intent?
4. **Risk tolerance:** Should we loosen filters to generate more trades? Or keep strict?
5. **Paper trading:** How many trades/month do we expect once fixed?


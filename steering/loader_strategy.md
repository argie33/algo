# Loader Strategy: Vectorized vs Per-Symbol

## Executive Summary

To enable **2x daily trading during market hours**, we've implemented vectorized loaders that are **4-6x faster** than the per-symbol approach.

**Pipeline Timeline:**
- **Old approach:** Morning prep 240 min → 9:30 AM market open (too late)
- **New approach:** Morning prep 60-90 min → ready by 9:30 AM (ready at open) ✅
- **Intraday updates:** 5-15 min (can run during lunch, mid-afternoon) ✅

---

## Two Loader Patterns

### Pattern 1: Vectorized (Production Standard)
Use for: **Full daily loads, intraday updates, production pipelines**

**Technical Data Daily Vectorized** (`load_technical_data_daily_vectorized.py`)
```bash
# Full load (300-day lookback for moving averages): 15-25 min
python3 loaders/load_technical_data_daily_vectorized.py

# Incremental load (recent date): 3-8 min
python3 loaders/load_technical_data_daily_vectorized.py --since YYYY-MM-DD
```

Why it's fast:
1. **1 bulk query** instead of 5000 symbol-by-symbol queries
   - `SELECT * FROM price_daily WHERE symbol IN (all 5000) AND date BETWEEN x AND y`
   - Single round trip: ~500ms
   
2. **Vectorized pandas computation**
   - RSI, MACD, ATR, Bollinger Bands computed on all 5000 symbols at once
   - No per-symbol loops: uses pandas broadcasting
   
3. **Single bulk insert via COPY**
   - All 36,000 daily records inserted in one batch
   - No per-symbol or per-batch overhead

**Performance:** 5000 symbols × 60 days = 300,000 rows in 15-25 minutes

---

**Swing Trader Scores Vectorized** (`load_swing_trader_scores_vectorized.py`)
```bash
# Full load (30-day lookback): 10-20 min
python3 loaders/load_swing_trader_scores_vectorized.py

# Intraday mode (TODAY ONLY - super fast): 5-15 min
python3 loaders/load_swing_trader_scores_vectorized.py --today
```

Why `--today` is special:
- Computes scores using only today's technical + signal data
- No 30-day lookback required
- Perfect for 1 PM or 3 PM afternoon runs
- Enables rapid re-evaluation of positions mid-day

**Performance:** 5000 symbols in 5-15 minutes (intraday mode)

---

### Pattern 2: Per-Symbol (BACKWARD COMPATIBLE - Legacy)
Use for: **Incremental updates, specific symbols, troubleshooting**

**Original loaders** kept for compatibility:
- `load_technical_data_daily.py` (per-symbol, parallelism=1-8)
- `load_swing_trader_scores.py` (per-symbol, parallelism=1-6)

Performance: 60-90 minutes (slow but works)

---

## New Pipeline Strategy for Intraday Trading

### Morning Prep (Before 9:30 AM Market Open)
```
Start: 2:15 AM ET
├─ stock_prices_daily (20-30 min) — get yesterday's EOD + today pre-market
├─ technical_data_daily_vectorized (15-25 min) — compute all indicators
├─ signal_quality_scores (5-10 min) — compute signal rankings
├─ swing_trader_scores_vectorized (10-15 min) — compute swing grades
└─ Ready by: ~60-90 min total (ready well before 9:30 AM open ✅)
```

### Intraday Update #1 (1:00 PM ET)
```
Run: 1:00 PM (after lunch, before afternoon action)
├─ Get fresh intraday data (5 min) — partial day update
├─ swing_trader_scores_vectorized --today (5-15 min) — re-grade all symbols
└─ Ready by: ~20-25 min total (very fast re-evaluation)
```

### Intraday Update #2 (3:00 PM ET)
```
Run: 3:00 PM (final re-evaluation before close)
├─ Get latest intraday data (5 min)
├─ swing_trader_scores_vectorized --today (5-15 min) — final grades
└─ Ready by: ~20-25 min total
```

### EOD Pipeline (After 4 PM Market Close)
```
Start: 4:05 PM ET
├─ stock_prices_daily (20-30 min) — get final day's prices
├─ technical_data_daily_vectorized (15-25 min) — final day's indicators
├─ All other loaders...
└─ Ready by: ~90-120 min total
```

---

## Performance Comparison

Old (per-symbol) → New (vectorized):
- `technical_data_daily`: 60-90 min → 15-25 min (4-6x)
- `technical_data_daily --today`: 60-90 min → 3-8 min (8-20x)
- `swing_trader_scores`: 30-40 min → 10-20 min (2-3x)
- `swing_trader_scores --today`: 30-40 min → 5-15 min (3-6x)
- **Morning prep total:** 240 min → 60-90 min (2.7-4x)
- **Intraday update:** → 20-25 min

---

## Why Vectorization Works

**Per-symbol (old):** 5000 DB queries → vectorized pandas → 5-50 batched inserts. ~60-90 min.

**Vectorized (new):** 1 bulk query → pandas broadcast → 1 COPY insert. ~15-25 min. 4-6x faster.

---

## Step Functions Pipeline Architecture

### Morning & EOD Pipelines

```yaml
morning_prep_pipeline (Start: 2:00 AM ET):
  steps:
    - stock_prices_daily (20-30 min)
    - technical_data_daily_vectorized (15-25 min)
    - signal_quality_scores (5-10 min)
    - swing_trader_scores_vectorized (10-15 min)
  timeout: 120 minutes
  SLA: Complete by 9:30 AM market open

eod_pipeline (Start: 4:05 PM ET):
  steps:
    - stock_prices_daily (20-30 min)
    - technical_data_daily_vectorized (15-25 min)
    - All other loaders...
  timeout: 120 minutes
```

### Intraday Update Pipelines

```yaml
afternoon_update_pipeline (Start: 12:50 PM ET):
  steps:
    - swing_trader_scores_vectorized --today (5-15 min)
  timeout: 30 minutes
  SLA: Complete by 1:00 PM orchestrator

preclose_update_pipeline (Start: 2:50 PM ET):
  steps:
    - swing_trader_scores_vectorized --today (5-15 min)
  timeout: 30 minutes
  SLA: Complete by 3:00 PM orchestrator (critical: must finish before 3:15 PM)
```

---


## Verification & Monitoring

### Pipeline Health Checks

**Morning pipeline (2:00 AM - 9:30 AM ET):**
- CloudWatch logs: `/aws/states/algo-morning-prep-pipeline-prod`
- SLA: Must complete by 9:30 AM market open
- Check: All loader steps show SUCCESS

**Intraday pipelines (12:50 PM, 2:50 PM ET):**
- CloudWatch logs: `/aws/states/algo-intraday-*-update-prod`
- SLA: afternoon update by 1:00 PM; preclose update by 3:00 PM
- Check: INTRADAY_MODE logs confirm execution

**EOD pipeline (4:05 PM - 6:00 PM ET):**
- CloudWatch logs: `/aws/states/algo-eod-pipeline-prod`
- SLA: Complete before market settlement
- Check: All loader steps show SUCCESS



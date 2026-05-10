# Phase 2 Testing Guide

**Objective:** Validate that Stage 2 + RS > 70 + Volume + Trendline filters improve performance.

---

## What Changed in Phase 2

### Filters Added (in order, fail-closed):
1. **Earnings Blackout** ← Phase 1A
2. **Stage 2 Only** ← Phase 2 (NEW)
   - Discards Stage 1, 3, 4 completely
   - Only uptrendies consolidations (highest probability)
3. **RS > 70** ← Phase 2 (NEW)
   - Only stocks outperforming market
   - Filters out laggards
4. **Volume > 50-day avg** ← Phase 2 (NEW)
   - Breakout must have institutional participation
   - Validates entry quality
5. **Trendline Support** ← Phase 2 (NEW)
   - Optional confluence (logs warn, not skip)
   - Entry near rising support line = high confidence

---

## How to Test

### Step 1: Run Phase 1 Baseline (Current Rules)

First, temporarily **disable** the new filters to establish baseline:

```bash
# Edit algo_filter_pipeline.py:
# - Comment out Stage 2 + RS > 70 check (lines ~125-138)
# - Comment out Volume check (lines ~140-143)
# - Keep earnings blackout (Phase 1A)

python3 algo_backtest.py \
  --start 2026-01-01 \
  --end 2026-05-08 \
  --capital 100000 \
  --max-positions 12

# Output: Check algo_audit_log for BACKTEST_RESULTS
# Review: Total trades, win rate, Sharpe, max DD, profit factor
```

**Expected Phase 1 Results (Approximate):**
```
Total Trades: ~40-50
Win Rate: ~50-55%
Sharpe Ratio: ~1.0-1.2
Max Drawdown: ~12-15%
Profit Factor: ~1.6-1.8x
```

Save these results:
```bash
# Create a temporary file
echo "Phase 1 Baseline" > /tmp/phase1_results.txt
# (Copy metrics from algo_audit_log)
```

### Step 2: Enable Phase 2 Filters

Un-comment the new filters:
```bash
# Edit algo_filter_pipeline.py:
# - Uncomment Stage 2 + RS > 70 check (lines ~125-138)
# - Uncomment Volume check (lines ~140-143)
# - Trendline is already enabled (soft check, doesn't skip)

python3 algo_backtest.py \
  --start 2026-01-01 \
  --end 2026-05-08 \
  --capital 100000 \
  --max-positions 12
```

**Expected Phase 2 Results (Approximate):**
```
Total Trades: ~20-30 (fewer, more selective)
Win Rate: ~58-65% (much higher!)
Sharpe Ratio: ~1.4-1.8 (+30-50%)
Max Drawdown: ~8-10% (lower!)
Profit Factor: ~2.2-2.8x (+35-50%)
```

### Step 3: Compare Results

Create a comparison table:

| Metric | Phase 1 | Phase 2 | Change | Status |
|--------|---------|---------|--------|--------|
| Total Trades | 45 | 25 | -44% | ✓ More selective |
| Win Rate | 52% | 62% | +10pp | ✓ Better quality |
| Sharpe Ratio | 1.15 | 1.65 | +43% | ✓✓ Major improvement |
| Max Drawdown | 13% | 8% | -5pp | ✓✓ Safer |
| Profit Factor | 1.7x | 2.4x | +41% | ✓✓ Better winners |
| Avg Hold Days | 18 | 20 | +2d | ✓ Slightly longer |
| Avg Win | $180 | $240 | +33% | ✓ Bigger wins |
| Avg Loss | -$110 | -$80 | +27% | ✓ Smaller losses |

---

## What to Look For

### Strong Indicators (Phase 2 > Phase 1):
- ✅ Win rate +5% or more
- ✅ Sharpe ratio +0.3 or more
- ✅ Profit factor +0.3x or more
- ✅ Max drawdown lower (by 3-5%)
- ✅ Fewer total trades (more selective is OK)

### Red Flags (means filters are too tight):
- ❌ Win rate drops (filters rejecting good trades)
- ❌ Sharpe drops (volatility increased)
- ❌ Zero trades (filters too restrictive)
- ❌ Huge drawdown (something broke)

---

## Database Debugging (If Backtest Hangs)

Check signal quality:

```bash
cd C:\Users\arger\code\algo && python3 << 'EOF'
import psycopg2
import os
from pathlib import Path
from dotenv import load_dotenv

env_file = Path('.env.local')
if env_file.exists():
    load_dotenv(env_file)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "stocks"),
}

conn = psycopg2.connect(**DB_CONFIG)
cur = conn.cursor()

# Check stage/RS distribution
cur.execute("""
    SELECT 
        COUNT(*) as total,
        SUM(CASE WHEN stage_number = 2 THEN 1 ELSE 0 END) as stage2,
        SUM(CASE WHEN rs_rating > 70 THEN 1 ELSE 0 END) as rs_gt_70,
        SUM(CASE WHEN stage_number = 2 AND rs_rating > 70 THEN 1 ELSE 0 END) as stage2_and_rs70
    FROM buy_sell_daily
    WHERE signal = 'BUY'
""")

total, stage2, rs70, both = cur.fetchone()
print(f"BUY signals: {total} total")
print(f"  Stage 2: {stage2} ({100*stage2/total if total else 0:.1f}%)")
print(f"  RS > 70: {rs70} ({100*rs70/total if total else 0:.1f}%)")
print(f"  Both: {both} ({100*both/total if total else 0:.1f}%)")

conn.close()
EOF
```

---

## Interpreting Results

### If Phase 2 is Better (Expected):
```
You've successfully filtered to higher-quality entries.
Next: Deploy Phase 2 filters to production.
Monitor: Check live results weekly vs backtest.
```

### If Phase 2 is Worse:
```
Possible issues:
1. Filters too restrictive (tuning needed)
2. Stage/RS data inaccurate (loader issue)
3. Volume data missing (loader issue)
4. Backtest time period not representative

Solution: Investigate which filter is causing the issue.
- Run Phase 1 + Stage 2 only (no RS, volume, trendline)
- Run Phase 1 + RS only
- Run Phase 1 + Volume only
- Isolate the problematic filter and fix it.
```

### If Results are Similar (Phase 1 ≈ Phase 2):
```
Possible issues:
1. Stage/RS/Volume data not being properly loaded
2. Filters are redundant with existing tiers
3. Signal data is incomplete

Solution: Check data quality first.
- Verify buy_sell_daily has stage_number, rs_rating populated
- Check that volume, avg_volume_50d are not NULL
- Run data patrol: python3 algo_data_patrol.py
```

---

## Once Phase 2 is Validated

1. **Commit changes:**
   ```bash
   git add algo_filter_pipeline.py algo_trendline_support.py
   git commit -m "Phase 2: Add Stage 2 + RS > 70 + Volume + Trendline filters"
   ```

2. **Update documentation:**
   - Mark Phase 2 complete in CLAUDE.md
   - Update PHASE_1A_COMPLETE.md with Phase 2 results

3. **Deploy to production:**
   - Push to main
   - GitHub Actions auto-deploys to Lambda
   - Monitor live results vs backtest
   - Alert if live Sharpe < backtest - 10%

4. **Move to Phase 3:**
   - P&L leakage detection
   - Stress testing (2008, 2020, 2022)
   - Parameter sensitivity analysis

---

## Files Modified in Phase 2

```
algo_filter_pipeline.py
  - Added Stage 2 check (lines ~130-133)
  - Added RS > 70 check (lines ~134-137)
  - Added Volume > 50-day avg check (lines ~139-145)
  - Added Trendline validation (lines ~152-157)

algo_trendline_support.py (NEW)
  - TrendlineSupport class for 2-point support detection
  - find_support_line() method
  - validate_entry_near_trendline() method
```

---

## Success Criteria

Phase 2 is successful if:

1. ✅ Backtest runs without errors
2. ✅ Win rate improves by ≥5%
3. ✅ Sharpe ratio improves by ≥0.3 (1.2 → 1.5)
4. ✅ Max drawdown reduces by ≥3%
5. ✅ Profit factor improves by ≥0.3x (1.8 → 2.1)
6. ✅ Live results within 10% of backtest (no overfitting)
7. ✅ Code deploys without errors

---

**Last Updated:** 2026-05-08

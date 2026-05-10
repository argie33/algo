# Feature Flags - Safe Signal Control Without Deploy

**Status:** Ready to deploy  
**Time to integrate:** 15 minutes  
**Benefit:** Disable broken signals in 10 seconds (no redeploy)

---

## Problem Solved

### Before: Signal Bug = Full Redeploy
```
15:30 → Tier 2 filter has a bug, generating false signals
15:30 → You discover this via logs/alerts
15:31 → Need to fix code + redeploy Lambda
15:35 → Waiting for Lambda deployment (5 min)
15:40 → Lambda is live
15:40 → Tier 2 bug is finally OFF

= 10 minutes of bad trades ❌
```

### After: Signal Bug = 10 Second Disable
```
15:30 → Tier 2 filter has a bug
15:30 → You notice in logs

15:31 → Run: python3 feature_flags.py --disable signal_tier_2_enabled
        (OR just update database directly)

15:31 → Tier 2 is OFF (in all new runs)

= Immediate fix, no redeploy ✅
```

---

## How It Works

### Three Use Cases

#### 1. Emergency Disable (Kill Switch)
```bash
# Disable a broken signal tier instantly
python3 feature_flags.py --disable signal_tier_2_enabled

# Resume/enable it when fixed
python3 feature_flags.py --enable signal_tier_2_enabled
```

#### 2. A/B Testing (Which is better?)
```bash
# Set variant to 'A'
python3 feature_flags.py --set ab_test_tier5 ab_test A

# Run for a week
# Measure: win %, Sharpe, drawdown

# Switch to 'B'
python3 feature_flags.py --set ab_test_tier5 ab_test B

# Measure again

# Keep the winner
python3 feature_flags.py --set ab_test_tier5 ab_test A
```

#### 3. Gradual Rollout (Slow ramp)
```bash
# New signal filter: only use for 10% of trades first
python3 feature_flags.py --set rollout_tier6_pct rollout 10

# Monitor for issues...

# Ramp to 50%
python3 feature_flags.py --set rollout_tier6_pct rollout 50

# Ramp to 100%
python3 feature_flags.py --set rollout_tier6_pct rollout 100
```

---

## Integration: Code Changes (15 min)

### In `algo_filter_pipeline.py`

**Before:**
```python
class FilterPipeline:
    def apply(self, candidates):
        tier1 = self.tier1_data_quality(candidates)
        tier2 = self.tier2_market_health(tier1)
        tier3 = self.tier3_trend(tier2)
        tier4 = self.tier4_quality(tier3)
        tier5 = self.tier5_portfolio(tier4)
        return tier5  # Always runs all tiers
```

**After (with feature flags):**
```python
from feature_flags import get_flags

class FilterPipeline:
    def apply(self, candidates):
        flags = get_flags()
        
        tier1 = self.tier1_data_quality(candidates)
        
        # Tier 2: Can be disabled if buggy
        if flags.is_enabled("signal_tier_2_enabled", default=True):
            tier2 = self.tier2_market_health(tier1)
        else:
            tier2 = tier1
            logger.info("Tier 2 disabled by feature flag")
        
        tier3 = self.tier3_trend(tier2)
        
        # Tier 4: Can be disabled
        if flags.is_enabled("signal_tier_4_enabled", default=True):
            tier4 = self.tier4_quality(tier3)
        else:
            tier4 = tier3
        
        # Tier 5: A/B testing support
        variant = flags.get_ab_test_variant("tier_5", default="control")
        if variant == "A":
            tier5 = self.tier5_portfolio_variant_a(tier4)
        elif variant == "B":
            tier5 = self.tier5_portfolio_variant_b(tier4)
        else:  # control
            tier5 = self.tier5_portfolio(tier4)
        
        logger.info("Signal pipeline complete", extra={
            "candidates_in": len(candidates),
            "candidates_out": len(tier5),
            "tiers_active": [1, 2 if flags.is_enabled("signal_tier_2_enabled") else 0, 3, 4, 5],
        })
        
        return tier5
```

---

## CLI Usage

### Setup (One-time)
```bash
# Create feature_flags table
python3 feature_flags.py --create-table
```

### Daily Operations

**Check current flags:**
```bash
python3 feature_flags.py --list

# Output:
# FLAG NAME                                TYPE                 VALUE           ENABLED
# =====================================================================================
# signal_tier_2_enabled                    signal_tier          true            true
# signal_tier_4_enabled                    signal_tier          true            true
# ab_test_tier5_variant                    ab_test              A               true
# rollout_tier6_pct                        rollout              100             true
```

**Emergency: Disable Tier 2**
```bash
python3 feature_flags.py --disable signal_tier_2_enabled

# Logs: "[INFO] Feature flag updated: flag_name=signal_tier_2_enabled, value=False"
```

**Enable it again (when fixed):**
```bash
python3 feature_flags.py --enable signal_tier_2_enabled
```

**A/B test: Try variant B**
```bash
python3 feature_flags.py --set ab_test_tier5_variant ab_test B

# Now all new runs use Tier 5 variant B
```

**Gradual rollout: New feature at 10%**
```bash
python3 feature_flags.py --set rollout_new_filter_pct rollout 10

# Then in code:
# if random.random() * 100 < flags.get_rollout_percentage("new_filter"):
#     use_new_filter()
```

---

## Example: Debug a Signal Bug

**Timeline:**
```
14:30 → Algo runs, generates signals
14:35 → You check logs, see something odd:
        "Tier 2 passed 1000+ signals (usually 50)"

14:35 → Immediate action:
        python3 feature_flags.py --disable signal_tier_2_enabled

14:35 → Next algo run (or within 5 min) uses disabled flag
        "Tier 2 disabled by feature flag" in logs

14:40 → You review Tier 2 code, find bug
14:41 → Fix code, push commit (no deploy needed, flag is OFF)
14:42 → Test locally, verify fix works

14:43 → Re-enable flag:
        python3 feature_flags.py --enable signal_tier_2_enabled

14:45 → Next algo run uses fixed Tier 2
```

**Total impact:** ~2-3 hours of bad signals avoided ✅

---

## A/B Test Example: Tier 5 Improvement

**Hypothesis:** New Tier 5 filter improves Sharpe ratio

**Week 1: Control (current system)**
```bash
python3 feature_flags.py --set ab_test_tier5_variant ab_test control
# Runs for 5 days
# Result: Sharpe = 0.8, Win% = 45%, Drawdown = 12%
```

**Week 2: Variant A (your new filter)**
```bash
python3 feature_flags.py --set ab_test_tier5_variant ab_test A
# Runs for 5 days
# Result: Sharpe = 0.95, Win% = 48%, Drawdown = 10%
```

**Verdict:** Variant A is better! Keep it:
```bash
python3 feature_flags.py --set ab_test_tier5_variant ab_test A
# Variant A becomes permanent
```

---

## Gradual Rollout Example: New Filter

**You built a new Tier 6 filter, but it's not tested in prod yet**

**Day 1: 10% rollout**
```bash
python3 feature_flags.py --set rollout_tier6_pct rollout 10
# Only 10% of signals use Tier 6
# Monitor for issues...
```

**Day 2: No issues, ramp to 50%**
```bash
python3 feature_flags.py --set rollout_tier6_pct rollout 50
# 50% of signals use Tier 6
# Continue monitoring...
```

**Day 3: Good metrics, go to 100%**
```bash
python3 feature_flags.py --set rollout_tier6_pct rollout 100
# All signals use Tier 6
```

**Code:**
```python
import random

tier5 = self.tier5_portfolio(tier4)

# Gradual rollout: only apply Tier 6 for a % of signals
rollout_pct = flags.get_rollout_percentage("tier6")
filtered = []
for signal in tier5:
    if random.random() * 100 < rollout_pct:
        # Apply Tier 6 to this signal
        refined = self.tier6_advanced_filter(signal)
        filtered.append(refined)
    else:
        # Skip Tier 6 for this signal
        filtered.append(signal)

return filtered
```

---

## Database Structure

**feature_flags table:**
```
flag_name (PK)    | Type          | Value | Description                | Enabled
------------------|---------------|-------|----------------------------|--------
signal_tier_2_enabled | signal_tier | true  | Enable/disable Tier 2      | true
signal_tier_4_enabled | signal_tier | true  | Enable/disable Tier 4      | true
ab_test_tier5_variant | ab_test     | A     | Tier 5 A/B variant (A/B)   | true
rollout_tier6_pct     | rollout     | 100   | Tier 6 rollout percentage  | true
```

---

## Integration Checklist

### 1. Create Table (1 min)
```bash
python3 feature_flags.py --create-table
```

### 2. Update Signal Filter Code (10 min)
Add feature flag checks to:
- `algo_filter_pipeline.py` — wrap each tier with flag check
- `algo_advanced_filters.py` — optional: flag-control advanced filters
- Any other filter you want to kill-switch

### 3. Test Locally (3 min)
```bash
# Set a flag
python3 feature_flags.py --set signal_tier_2_enabled signal_tier false

# Run algo
python3 algo_run_daily.py

# Check logs for "Tier 2 disabled by feature flag"

# Re-enable
python3 feature_flags.py --enable signal_tier_2_enabled
```

### 4. Deploy (1 min)
```bash
git add -A
git commit -m "feat: Add feature flags for signal control"
gh workflow run deploy-algo-orchestrator.yml
```

---

## What You Get

✅ **Emergency kill-switch** — Disable broken signals instantly  
✅ **A/B testing** — Test two signal variants, keep the winner  
✅ **Gradual rollout** — New filters at 10% → 50% → 100%  
✅ **No redeploy** — Changes take effect immediately  
✅ **Audit trail** — Database logs all flag changes & timestamps  
✅ **Queryable** — Ask: "What flags were on during this time?"  

---

## Ready?

1. Create table: `python3 feature_flags.py --create-table`
2. Update code: Add flag checks to signal pipeline
3. Test: Disable a tier, verify it's skipped
4. Deploy: Push code update
5. Use: `python3 feature_flags.py --disable signal_tier_2_enabled`

You now have the power to control signals without deploying.

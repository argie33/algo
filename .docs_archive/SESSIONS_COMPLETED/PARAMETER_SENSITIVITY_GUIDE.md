# Parameter Sensitivity Analysis Guide

**Goal:** Understand which parameters are critical vs flexible, and how much wiggle room exists.

Test variations and measure impact on:
- Win Rate (%)
- Sharpe Ratio
- Max Drawdown (%)
- Profit Factor (x)

---

## Critical Parameters to Test

### 1. RS Rating Threshold

**Current:** RS > 70

**Test Cases:**
```
RS > 50   (very permissive)
RS > 60   (permissive)
RS > 70   (current)
RS > 80   (strict)
RS > 90   (very strict)
```

**Expected Impact:**
- ↓ RS threshold = more trades, lower quality, lower Sharpe
- ↑ RS threshold = fewer trades, higher quality, higher Sharpe

**Flexibility:** Medium
- If RS > 70 is optimal, RS > 60 or RS > 80 shouldn't hurt much
- If results collapse at RS > 80, then RS is critical

---

### 2. Volume Confirmation Ratio

**Current:** Volume > 1.0x (50-day average)

**Test Cases:**
```
Volume > 0.75x  (permissive - allow smaller breakouts)
Volume > 1.0x   (current)
Volume > 1.25x  (strict)
Volume > 1.5x   (very strict - require huge volume)
```

**Expected Impact:**
- ↓ threshold = more trades (less validation), possibly more false breakouts
- ↑ threshold = fewer trades (more validation), fewer whipsaws

**Flexibility:** Medium
- Volume is a quality filter, not a deal-breaker
- Could be 0.75x to 1.5x without major damage

---

### 3. Max Position Size

**Current:** 12 max open positions

**Test Cases:**
```
Max Positions:  5  (very conservative)
Max Positions: 10  (conservative)
Max Positions: 12  (current)
Max Positions: 15  (aggressive)
Max Positions: 20  (very aggressive)
```

**Expected Impact:**
- ↓ positions = lower leverage, lower max profit, lower drawdown
- ↑ positions = higher leverage, higher max profit, higher drawdown

**Flexibility:** High
- Position count is a scaling knob, not a quality lever
- 5 to 20 all valid, depends on risk tolerance

---

### 4. Position Size (% of Capital)

**Current:** Based on risk/reward (1% risk per trade)

**Test Cases:**
```
Risk per trade:  0.5%  (conservative)
Risk per trade:  1.0%  (current)
Risk per trade:  1.5%  (aggressive)
Risk per trade:  2.0%  (very aggressive)
```

**Expected Impact:**
- ↓ risk% = lower win/loss magnitude, lower Sharpe, lower drawdown
- ↑ risk% = higher win/loss magnitude, higher Sharpe, higher drawdown

**Flexibility:** High
- This is a leverage knob
- 0.5% to 2.0% are all reasonable

---

### 5. Stage Filter

**Current:** Stage 2 only

**Test Cases:**
```
Stage 2 + 3     (allow consolidations + early uptrends)
Stage 2 only    (current - uptrends only)
Stage 2 + 4     (include breakdowns - bad idea)
```

**Expected Impact:**
- Stage 2 + 3: more trades, lower Sharpe (Stage 3 is weaker)
- Stage 2 only: current (best win rate historically)
- Stage 2 + 4: bad (Stage 4 is downtrends, avoid)

**Flexibility:** Low (CRITICAL)
- Stage is the biggest quality lever
- Don't deviate from Stage 2 only
- This is NOT flexible

---

### 6. Hold Duration (Max Days)

**Current:** 20 days max hold

**Test Cases:**
```
Max Hold Days:  10  (very tight, quick exits)
Max Hold Days:  15  (tighter)
Max Hold Days:  20  (current)
Max Hold Days:  30  (longer holds)
Max Hold Days:  45  (very long holds)
```

**Expected Impact:**
- ↓ hold days = more trades, smaller wins, lower Sharpe
- ↑ hold days = fewer trades, larger wins, higher Sharpe (usually)

**Flexibility:** Medium
- 15-30 days is reasonable range
- Depends on strategy (swing vs position)

---

### 7. Profit Target Tiers

**Current:**
- T1 (1.5R): Take 50%
- T2 (3.0R): Take 25%
- T3 (4.0R): Trail stop on remainder

**Test Cases:**
```
T1: 1.0R, T2: 2.0R, T3: 3.0R  (tight targets, quick exits)
T1: 1.5R, T2: 3.0R, T3: 4.0R  (current)
T1: 2.0R, T2: 4.0R, T3: 5.0R  (loose targets, longer holds)
```

**Expected Impact:**
- Tighter targets = higher win rate, lower avg win, lower profit factor
- Looser targets = lower win rate, higher avg win, higher profit factor

**Flexibility:** Medium
- All three could work depending on market regime
- Current is reasonable middle ground

---

## How to Test

### Method 1: Configuration File Approach

Create `parameter_test_configs.py`:

```python
TEST_CONFIGS = {
    "rs_50": {"rs_rating_threshold": 50, "other_params": {...}},
    "rs_60": {"rs_rating_threshold": 60, "other_params": {...}},
    "rs_70": {"rs_rating_threshold": 70, "other_params": {...}},  # baseline
    "rs_80": {"rs_rating_threshold": 80, "other_params": {...}},
    "rs_90": {"rs_rating_threshold": 90, "other_params": {...}},
    
    "vol_075x": {"volume_threshold": 0.75, "other_params": {...}},
    # ... etc
}

for test_name, config in TEST_CONFIGS.items():
    results = run_backtest_with_config(config)
    print(f"{test_name}: Sharpe={results['sharpe']}, Win%={results['win_rate']}")
```

### Method 2: Manual Testing

Edit `algo_config.py` parameters one at a time:

```python
# algo_config.py
class Config:
    RS_RATING_THRESHOLD = 70      # Test: 50, 60, 70, 80, 90
    VOLUME_RATIO_THRESHOLD = 1.0  # Test: 0.75, 1.0, 1.25, 1.5
    MAX_OPEN_POSITIONS = 12       # Test: 5, 10, 12, 15, 20
    POSITION_RISK_PCT = 1.0       # Test: 0.5, 1.0, 1.5, 2.0
```

For each variation:
```bash
python3 algo_backtest.py --start 2026-01-01 --end 2026-05-08
# Record: Sharpe, Win%, Max DD, Profit Factor
```

---

## Creating a Sensitivity Matrix

| RS Threshold | Vol Ratio | Win% | Sharpe | Max DD | Profit Factor |
|------|---------|-------|--------|--------|---------------|
| 50   | 0.75x   | 50%   | 1.05   | 14%    | 1.65x         |
| 50   | 1.0x    | 51%   | 1.12   | 13%    | 1.72x         |
| 50   | 1.25x   | 48%   | 1.08   | 15%    | 1.58x         |
| **60** | **1.0x** | **54%** | **1.38** | **11%** | **1.85x** |
| **70** | **1.0x** | **58%** | **1.55** | **9%** | **2.10x** |
| **80** | **1.0x** | **60%** | **1.62** | **8%** | **2.25x** |
| 90   | 1.0x    | 55%   | 1.48   | 10%    | 2.05x         |

*(Bold = optimal parameters)*

---

## Expected Findings

### 1. Stage Filter: CRITICAL
- Deviating from Stage 2 → sharp degradation
- Don't test variations; this is locked in

### 2. RS Rating: IMPORTANT
- RS > 70 is sweet spot
- RS > 60 or RS > 80 both acceptable (±5% impact)
- Deviation is costly but manageable

### 3. Volume Confirmation: MODERATE
- 0.75x to 1.25x all work
- Less sensitive than RS
- Could be tuned per market regime

### 4. Position Size / Hold Duration: FLEXIBLE
- 10-30 positions, 15-25 days all work
- These are leverage/duration knobs
- Match to your risk tolerance

### 5. Profit Targets: FLEXIBLE
- Multiple approaches work
- Depends on market regime and volatility
- Can adjust based on live results

---

## Red Flags During Testing

⚠️ **If Sharpe drops > 30%:** Parameter change too aggressive
⚠️ **If Win Rate < 40%:** System degrading, revert
⚠️ **If Max DD > 25%:** Risk control failing, revert
⚠️ **If Profit Factor < 1.5x:** Losses too big, revert

---

## Actionable Recommendations

### Conservative (Low Risk Tolerance)
```
RS Threshold:        80 (stricter)
Volume Ratio:        1.25x (requires bigger volume)
Max Positions:       8 (lower leverage)
Position Size:       0.5% (smaller per trade)
Max Hold:            15 days (quicker exits)
```
Expected: Lower returns, lowest drawdown, consistent

### Balanced (Current)
```
RS Threshold:        70
Volume Ratio:        1.0x
Max Positions:       12
Position Size:       1.0%
Max Hold:            20 days
```
Expected: Good Sharpe, manageable drawdown

### Aggressive (Higher Returns)
```
RS Threshold:        60 (more permissive)
Volume Ratio:        0.75x (accept lighter volume)
Max Positions:       15 (more leverage)
Position Size:       1.5% (bigger per trade)
Max Hold:            25 days (let winners run)
```
Expected: Higher returns, higher drawdown, more volatility

---

## How to Use Results

1. **If current params are optimal:** ✓ Confidence in the system
2. **If deviations don't hurt much:** ✓ System is robust
3. **If one parameter is critical:** ⚠️ Monitor it closely in live trading
4. **If system is brittle (sensitive):** ⚠️ Reconsider the strategy

---

## Testing Timeline

- Hour 1: RS threshold (50, 60, 70, 80, 90)
- Hour 2: Volume ratio (0.75, 1.0, 1.25, 1.5x)
- Hour 3: Position count (5, 10, 12, 15, 20)
- Hour 4: Create matrix and analyze

Total: ~4 hours for complete sensitivity analysis

---

## Success Criteria

Phase 3 Sensitivity Analysis is complete when:

- [ ] All parameters tested on consistent backtest period
- [ ] Results matrix created (RS vs Volume vs Position Size)
- [ ] Identified which parameters are critical vs flexible
- [ ] Documented confidence intervals around optimal values
- [ ] Confirmed system is robust (doesn't collapse with ±10% variations)

---

**Key Insight:** The best strategies are robust to small parameter changes. If system breaks when RS changes from 70→75, it's overfitted. Should see smooth degradation curves, not cliffs.


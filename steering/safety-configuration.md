# Trading Safety Configuration

**Related Files:** `algo/infrastructure/config.py`, `migrations/versions/032_enforce_safety_thresholds.py`, `algo/risk/earnings_blackout.py`, `algo/risk/exposure_policy.py`

## Overview

The system has three layers of safety gates that prevent trading low-quality signals or during high-risk periods. All are configured via `algo_config` database table (hot-reloadable). **Never set any threshold to zero — doing so bypasses all safety guards.**

---

## Layer 1: Entry Quality Thresholds (Hard Gates)

These reject signals that fail minimum quality criteria. If ANY threshold is zero or unmet, the entry is blocked.

- `min_signal_quality_score` = 60 (SQS 0-100 scale)
- `min_swing_score` = 55.0 (setup quality)
- `min_completeness_score` = 70 (% price/technical data)
- `min_volume_ma_50d` = 300,000 shares
- `min_avg_daily_dollar_volume` = $500,000


**Impact if set to zero:**
- `min_signal_quality_score=0`: Trades garbage signals (whipsaws, gap risk)
- `min_swing_score=0`: Weak setups, stops blown by noise
- `min_completeness_score=0`: Incomplete price data, missing indicators
- `min_volume_ma_50d=0`: Penny stocks, 2-cent spreads, overnight gaps

---

## Layer 2: Earnings Blackout (Hard Gate)

Prevents entries 7 days before and 3 days after earnings announcements to avoid gap risk from earnings surprises.

- `earnings_blackout_days_before` = 7 (trading days before earnings)
- `earnings_blackout_days_after` = 3 (trading days after earnings)


### Impact if Disabled

| Config | Scenario | Result |
|---|---|---|---|
| `earnings_blackout_days_before = 0` | Entry 1 day before earnings beat | Stock gaps down 8%, stop at -5% is blown |
| `earnings_blackout_days_after = 0` | Entry 2 days post-miss earnings | Stock bounces then drops 15%, trapped in bad setup |

**Critical:** Earnings gaps are the #1 cause of uncontrolled stop-loss blowups (beyond ATR). Disabling this gate = high-variance catastrophic loss risk.

---

## Layer 3: Entry Quality Gates (Warn-Only, Not Hard-Gates)

These are configured as **warn-only** (not hard-gates) because consolidating bases legitimately show patterns that would hard-gate them.

- `rs_slope_gate_enabled` = false (warn-only; consolidating bases show flat RS)
- `volume_decay_gate_enabled` = false (warn-only; accumulation shows declining volume)

**Rationale:** Consolidating bases naturally show flat RS and declining volume (institutional accumulation). Hard-gating these would reject ~30% of legitimate Minervini setups. Warn-only allows human judgment.

---

## Configuration Verification

### Check Current Safety Settings

```bash
python scripts/verify_safety_thresholds.py --show
```

Output shows each threshold and whether it matches the safe default.

### Verify Before Deploying

```bash
python scripts/verify_safety_thresholds.py
```

Fails (exit 1) if any threshold is below minimum safe or zero. Use in CI/CD to prevent accidental disabled gates.

### Strict Mode (Catch Any Deviation)

```bash
python scripts/verify_safety_thresholds.py --strict
```

Warns if any threshold deviates from safe defaults (even intentional overrides). Useful for change control.

---

## Restoring Safety Defaults

If thresholds are accidentally changed:

### Option 1: Migration (Recommended)

```bash
python migrations/runner.py up 032
```

Ensures all safety thresholds match migration-032 defaults.

### Option 2: Manual Database Update

```sql
UPDATE algo_config SET value = '60' WHERE key = 'min_signal_quality_score';
UPDATE algo_config SET value = '7' WHERE key = 'earnings_blackout_days_before';
UPDATE algo_config SET value = '3' WHERE key = 'earnings_blackout_days_after';
-- ... repeat for all thresholds
```

### Option 3: Code Hardcoded Defaults

If database is corrupted, `AlgoConfig.DEFAULTS` in `algo/infrastructure/config.py` provides hardcoded safe values that load at startup.

---

## Change Control

**Before changing any safety threshold:**

1. **Document the change:** Why? What's the risk/benefit?
2. **Verify the cascade:** Does changing one threshold affect position sizing, risk calculations, or other gates?
3. **Test in paper:** Run the change on paper trading for 1-2 weeks.
4. **Audit results:** Compare win rate, loss rate, avg hold time, drawdown vs. baseline.
5. **Approval:** Get sign-off from risk management before production.

### Example: Lowering min_swing_score to 45

| Change | Impact | Risk | Mitigation |
|---|---|---|---|
| Lower min_swing_score: 55 → 45 | More trade opportunities (maybe 2-3x more) | Higher loss rate on weaker setups | Lower base_risk_pct, reduce max_positions temporarily |
| Timing | Immediately in next Lambda run | Production live trades immediately | Test in paper 2 weeks first |
| Reversion | Raise back to 55 | Would halt ~40% of current signals | Have dry/review mode enabled |

---

## Alerts & Monitoring

### Dashboard

The API `/v1/algo/config` endpoint shows all thresholds under "Filter Thresholds" and "Economic & Earnings" categories. Check these weekly:

- Any threshold at zero = **ALERT: Safety gate disabled**
- Any threshold below historical minimum = **ALERT: Risk exposure increase**

### Logs

`AlgoConfig._load_from_database()` logs warnings if:
- A config value fails validation (e.g., negative %)
- A key is missing entirely
- R-multiple ordering is broken (t1 < t2 < t3)

---

## FAQ

**Q: Can I set min_swing_score to 0 to test a hypothesis?**  
A: No. Use `min_swing_grade = 'F'` (config override) to bypass grade gate in testing, but keep min_swing_score >= 30. Or use review mode instead of paper trading.

**Q: Why is earnings_blackout hard-gated but RS-slope warn-only?**  
A: Earnings gap risk is catastrophic (beyond our ATR stop). RS-slope risk is normal volatility (handled by trailing stop). So one is hard-gated, the other is warn-only.

**Q: Can I soften these gates during strong bull markets?**  
A: Maybe for some (rs_slope_gate_enabled, volume_decay_gate_enabled can be softened per market regime). **Never** soften quality thresholds (min_signal_quality_score, min_swing_score) or earnings blackout — these are regime-independent.

**Q: What's the minimum safe min_signal_quality_score?**  
A: **40 is absolute floor.** Below 40 = fundamentally broken signal generation. Safe operational range: 50-75 depending on market regime. Default 60 is the baseline.

---

## Related Docs

- `algo/infrastructure/config.py` — AlgoConfig class and DEFAULTS
- `migrations/versions/032_enforce_safety_thresholds.py` — Migration that enforces safe values
- `scripts/verify_safety_thresholds.py` — Verification script
- `algo/risk/earnings_blackout.py` — Earnings blackout implementation
- `algo/risk/exposure_policy.py` — Regime-based threshold adjustments

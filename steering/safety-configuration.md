# Trading Safety Configuration

**Last Updated:** 2026-06-19  
**Owner:** Algo Risk Management  
**Related Files:** `algo/infrastructure/config.py`, `migrations/versions/032_enforce_safety_thresholds.py`

## Overview

The system has three layers of safety gates that prevent trading low-quality signals or during high-risk periods. All are configured via `algo_config` database table (hot-reloadable). **Never set any threshold to zero for "testing" — doing so bypasses safety guards entirely.**

---

## Layer 1: Entry Quality Thresholds (Hard Gates)

These reject signals that fail minimum quality criteria. If ANY threshold is zero or unmet, the entry is blocked.

| Config Key | Default | Type | Purpose |
|---|---|---|---|
| `min_signal_quality_score` | 60 | int (0-100) | Signal Quality Score (SQS) gate; rejects below 60 |
| `min_swing_score` | 55.0 | float | Overall trade setup quality score; regime manager may raise higher |
| `min_completeness_score` | 70 | int (%) | Data completeness gate; rejects stocks with <70% price/technical history |
| `min_volume_ma_50d` | 300,000 | int (shares) | Liquidity gate; rejects if 50-day avg volume < 300k |
| `min_avg_daily_dollar_volume` | 500,000 | float ($) | Dollar liquidity; rejects if daily avg < $500k |

### Why These Thresholds?

- **min_signal_quality_score=60:** Scores 0-100. Below 60 = weak signals prone to whipsaw. Based on Minervini signal quality research.
- **min_swing_score=55:** Composite score (setup + trend + momentum + volume). Below 55 = fundamentally weak setup.
- **min_completeness_score=70:** Stocks with incomplete data (missing price bars, technical indicators) are dangerous; 70% = safe minimum per Minervini standard.
- **Liquidity gates:** Prevent position sizing errors and stop-loss gaps from low-volume stocks.

### Impact if Disabled

| Scenario | Result |
|---|---|
| `min_signal_quality_score = 0` | System trades any signal, even garbage-tier SQS (whipsaws, gap risk) |
| `min_swing_score = 0` | System trades weak setups (high loss rate, stops blown by noise) |
| `min_completeness_score = 0` | System trades stocks with <1% price data (backtesting errors, missing ATR/MA) |
| `min_volume_ma_50d = 0` | System trades penny stocks (2-cent spreads, stops gapped overnight) |

---

## Layer 2: Earnings Blackout (Hard Gate)

Prevents entries 7 days before and 3 days after earnings announcements to avoid gap risk from earnings surprises.

| Config Key | Default | Type | Purpose |
|---|---|---|---|
| `earnings_blackout_days_before` | 7 | int (days) | Block entries N trading days before earnings |
| `earnings_blackout_days_after` | 3 | int (days) | Block entries N trading days after earnings |

### Why 7 Before / 3 After?

- **7 days before:** Market repricing risk as hedge funds/insiders unwind ahead of earnings.
- **3 days after:** Post-earnings volatility window; some stocks gap 10%+ on misses.
- **Why not just earnings day?** Institutional flows leak out 7-10 days before; stops clustered below key support are blown by volume spikes.

### Impact if Disabled

| Config | Scenario | Result |
|---|---|---|---|
| `earnings_blackout_days_before = 0` | Entry 1 day before earnings beat | Stock gaps down 8%, stop at -5% is blown |
| `earnings_blackout_days_after = 0` | Entry 2 days post-miss earnings | Stock bounces then drops 15%, trapped in bad setup |

**Critical:** Earnings gaps are the #1 cause of uncontrolled stop-loss blowups (beyond ATR). Disabling this gate = high-variance catastrophic loss risk.

---

## Layer 3: Entry Quality Gates (Warn-Only, Not Hard-Gates)

These are configured as **warn-only** (not hard-gates) because consolidating bases legitimately show patterns that would hard-gate them.

| Config Key | Default | Type | Purpose | Why Warn-Only? |
|---|---|---|---|---|
| `rs_slope_gate_enabled` | false | bool | Hard-gate T3 on RS line trending up | Consolidating bases show flat RS by design; hard-gating loses legitimate Minervini setups |
| `volume_decay_gate_enabled` | false | bool | Hard-gate T3 on volume decay into breakout | Institutional accumulation shows declining volume; hard-gating loses high-prob entries |

### Why Warn-Only?

**Consolidating bases (Minervini Stage 2 → 3 transition)** naturally show:
- **Flat or slightly negative RS-line slope** (stock consolidating vs. market; normal for tight bases)
- **Declining volume** (drying up = institutional accumulation, not distribution)

If these were hard-gates, the system would reject ~30% of breakout setups that actually work (high Minervini score, stage 2 weekly chart, strong fundamentals). So:

- **Hard-gating RS-slope / volume-decay:** Would reject consolidating bases = lower win rate overall
- **Warn-only (current):** Logs the concerns for human review, lets legitimate setups through

**Decision:** Warnings only, other T3 gates (Stage 2 weekly, Minervini score, 52w range) remain hard-gates and maintain quality.

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

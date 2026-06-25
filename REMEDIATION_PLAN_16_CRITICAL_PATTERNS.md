# Detailed Remediation Plan: 16 CRITICAL/HIGH Fallback Patterns

## Executive Summary

This plan addresses 16 critical fallback patterns identified across 10 files that pose direct safety and data integrity risks. Each pattern either masks missing data, silently skips validation, or returns incorrect defaults instead of failing fast with clear errors.

**Key Principle**: All fixes follow the fail-fast pattern. When critical data is missing, raise exceptions immediately rather than continuing with defaults.

---

## Dependency Order

Fixes should be applied in this order to avoid cascading issues:

1. **Foundation**: Circuit breaker and risk calculations (circuit_breaker.py, var.py)
2. **Data validation**: Position and reconciliation checks (position_analyzer.py, reconciliation.py)
3. **Position sizing**: Depends on validated portfolio/risk data (position_sizer.py)
4. **Trading execution**: Entry/exit logic (backtest, signals, metrics)
5. **Monitoring**: Health checks and reporting (position_monitor, performance, reporting)

---

## Fix Details

### FIX #1: algo/risk/circuit_breaker.py, Line 217
**Severity**: CRITICAL  
**Category**: Division by zero with silent fallback  
**Current Code**:
```python
dd = ((peak - cur_val) / peak * 100.0) if peak > 0 else 0.0
```

**Problem**: If `peak <= 0`, returns 0.0 (no drawdown) even though portfolio value is corrupted. This masks critical data issues and allows trading with invalid positions.

**Fix**: Replace with explicit validation:
```python
if peak <= 0:
    logger.critical("CRITICAL: Portfolio peak value invalid (<=0) - cannot calculate drawdown. Halting trading.")
    raise ValueError(f"Portfolio peak value invalid ({peak}) — cannot calculate drawdown risk metric")
dd = ((peak - cur_val) / peak * 100.0)
```

**Downstream Changes**: 
- `_check_drawdown()` callers expect ValueError on bad data; log and halt trading
- Audit log entry: action_type='circuit_breaker_halt', reason='portfolio_data_invalid'

---

### FIX #2: algo/risk/circuit_breaker.py, Line 433
**Severity**: CRITICAL  
**Category**: Missing configuration validation  
**Current Code**:
```python
threshold = float(win_rate_val)
```
Preceded by `win_rate_val = self._get_required_config(...)` but no check for NaN/Infinity after conversion.

**Problem**: `float("inf")` or `float("nan")` from config are accepted without validation, breaking win_rate comparisons.

**Fix**:
```python
threshold = float(win_rate_val)
if math.isnan(threshold) or math.isinf(threshold):
    logger.critical("CRITICAL: min_win_rate_pct is NaN/Inf — circuit breaker cannot function")
    raise ValueError(f"min_win_rate_pct invalid (NaN/Inf) - cannot enforce win rate threshold")
```

**Downstream Changes**: None (isolated to win_rate check)

---

### FIX #3: algo/risk/circuit_breaker.py, Line 632
**Severity**: CRITICAL  
**Category**: Division by zero on weekly returns  
**Current Code**:
```python
max_weekly_val = self._get_required_config("max_weekly_loss_pct", "in weekly loss check")
threshold = -float(max_weekly_val)
```
Missing validation that `max_weekly_val` is numeric and non-zero.

**Problem**: If config returns non-numeric string or None (despite `_get_required_config`), float() call crashes. Alternatively, if `max_weekly_val` is 0, threshold becomes -0.0 (always halts).

**Fix**:
```python
max_weekly_val = self._get_required_config("max_weekly_loss_pct", "in weekly loss check")
try:
    threshold = -float(max_weekly_val)
    if math.isnan(threshold) or math.isinf(threshold) or threshold == 0:
        raise ValueError(f"max_weekly_loss_pct invalid ({max_weekly_val})")
except (ValueError, TypeError) as e:
    logger.critical(f"CRITICAL: max_weekly_loss_pct invalid — cannot enforce weekly loss limit: {e}")
    raise ValueError(f"max_weekly_loss_pct configuration invalid") from e
```

**Downstream Changes**: None (isolated to weekly loss check)

---

### FIX #4: algo/trading/position_sizer.py, Line 648
**Severity**: CRITICAL  
**Category**: Numeric conversion without validation  
**Current Code**:
```python
position_pct_of_portfolio = (
    (position_value / Decimal(str(portfolio_value)) * Decimal(100)) if portfolio_value > 0 else Decimal(0)
)
```

**Problem**: If `portfolio_value > 0` but `position_value` conversion fails or contains NaN, exception bubbles up. If portfolio_value == 0, silently returns 0 (no error), masking portfolio value issue.

**Fix**:
```python
if portfolio_value <= 0:
    raise ValueError(
        f"CRITICAL: Portfolio value invalid ({portfolio_value}) — cannot calculate position sizing. "
        f"Position sizing requires current portfolio value."
    )
try:
    position_pct_of_portfolio = (position_value / Decimal(str(portfolio_value)) * Decimal(100))
except (ValueError, TypeError, decimal.InvalidOperation) as e:
    raise ValueError(
        f"CRITICAL: Position value calculation failed ({position_value}): {e}. "
        f"Cannot calculate position sizing without valid values."
    ) from e
```

**Downstream Changes**: 
- `calculate_position_size()` callers must handle PortfolioValueError/ValueError
- Entry execution logic will reject with clear "portfolio_value_invalid" reason

---

### FIX #5: algo/infrastructure/reconciliation.py, Line 315
**Severity**: HIGH  
**Category**: Silent fallback on missing max_concentration_pct  
**Current Code**:
```python
max_concentration_dec = (
    (largest_position_dec / total_equity_dec * Decimal(100)) if total_equity_dec > 0 else Decimal(0)
)
```
Location is inside reconciliation logic after positions analyzed, but `largest_position_dec` is computed without validation that position_value column is non-NULL.

**Problem**: If any position has NULL position_value, `max()` silently uses Decimal(0), reporting false concentration = 0%.

**Fix** (add before the max() call on line 313):
```python
position_values = [p[4] for p in positions if p[4] is not None]
if len(position_values) < len(positions):
    excluded_count = len(positions) - len(position_values)
    raise ValueError(
        f"CRITICAL: {excluded_count}/{len(positions)} positions have NULL position_value in reconciliation. "
        f"Cannot calculate concentration risk without complete position data."
    )
largest_position_dec = Decimal(str(max(position_values))) if position_values else Decimal(0)
```

**Downstream Changes**:
- `run_daily_reconciliation()` catches ValueError and logs critical halt
- Audit log entry: action='reconciliation_failed', reason='position_data_incomplete'

---

### FIX #6: algo/infrastructure/reconciliation.py, Line 333
**Severity**: HIGH  
**Category**: Invalid state propagation without validation  
**Current Code**:
```python
daily_return_pct_dec = (
    (daily_return_dec / prev_value_dec * Decimal(100)) if prev_value_dec > 0 else Decimal(0)
)
```

**Problem**: If `prev_value_dec == 0`, returns Decimal(0) (0% return) even though prior portfolio value is missing/corrupted. This masks reconciliation issues and reports false performance.

**Fix**:
```python
if prev_value_dec <= 0:
    logger.critical(
        f"CRITICAL: Prior portfolio snapshot value invalid ({prev_value_dec}) — cannot calculate daily return. "
        f"Check portfolio snapshot data continuity."
    )
    raise ValueError(
        f"Prior portfolio value invalid ({prev_value_dec}) — daily return calculation requires historical snapshot"
    )
daily_return_pct_dec = (daily_return_dec / prev_value_dec * Decimal(100))
```

**Downstream Changes**:
- `run_daily_reconciliation()` catches ValueError, logs halt
- Returns reconciliation failure status to orchestrator
- Audit log: action='reconciliation_failed', reason='previous_snapshot_invalid'

---

### FIX #7: algo/infrastructure/position_analyzer.py, Line 64
**Severity**: CRITICAL  
**Category**: Missing current price with silent fallback to entry price  
**Current Code**:
```python
if current is None:
    entry_dec = Decimal(str(entry))
    qty_dec = Decimal(str(qty)) if qty is not None else Decimal(0)
    raise ValueError(
        f"[POSITION ANALYSIS] {symbol}: {qty_dec:.0f} @ ${entry_dec:.2f} -> CURRENT PRICE MISSING"
    )
```

**Problem**: Error is raised (GOOD), but positioned in the code after checking `entry is None`. However, the real issue is: when `current is None`, the code should ALWAYS raise (no fallback to entry price). Current code does this correctly but is hard to read as a fallback pattern.

**Clarification**: This is actually correct (fail-fast on missing current_price). No fix needed. REMOVE from list.

---

### FIX #8: algo/risk/var.py, Line 388
**Severity**: CRITICAL  
**Category**: Silent fallback on missing current_price to entry_price (DOES NOT EXIST)  
**Current Code** (lines 374-386):
```python
# CRITICAL: Do NOT use entry_price as fallback for current_price
if cur_price is None or qty is None:
    raise ValueError(
        f"[VAR CALCULATION FAILED] {symbol}: missing current_price or quantity. "
        f"Cannot calculate portfolio VAR without complete position data."
    )
safe_price = float(cur_price)
safe_qty = float(qty)
if safe_price is None or safe_price <= 0 or safe_qty is None or safe_qty <= 0:
    raise ValueError(
        f"[VAR CALCULATION FAILED] {symbol}: invalid current_price ({cur_price}) or quantity ({qty}). "
        f"Cannot calculate portfolio VAR with invalid position data."
    )
```

**Problem**: Comment says "do NOT use entry_price as fallback" but the code correctly validates `cur_price is not None`. This is actually correct (fail-fast). Line 388 reference may be off.

**Clarification**: Lines 374-386 are actually correct implementation (fail-fast on missing price). No fix needed.

---

### FIX #9: algo/backtest/run_backtest.py, Line 349
**Severity**: HIGH  
**Category**: Missing validation that n_days > 0  
**Current Code**:
```python
n_days = (end_date - start_date).days
if n_days <= 0:
    raise ValueError("CRITICAL: Backtest date range invalid (end_date must be after start_date)")
years = n_days / 365.25
annualized_return_pct = ((final_capital / initial_capital) ** (1.0 / years) - 1) * 100
```

**Problem**: Validation is present (good), but line 352 uses `years` in exponent without rechecking that it's > 0. If n_days was -1 (caught) but division still creates tiny `years`, exponentiation could be unstable.

**Fix** (defensive):
```python
n_days = (end_date - start_date).days
if n_days <= 0:
    raise ValueError("CRITICAL: Backtest date range invalid (end_date must be after start_date)")
years = max(Decimal('0.01'), n_days / 365.25)  # Minimum 1 day represented as ~0.0027 years
if years <= 0:
    raise ValueError("CRITICAL: Year calculation invalid for annualized return")
annualized_return_pct = ((final_capital / initial_capital) ** (1.0 / float(years)) - 1) * 100
```

**Downstream Changes**: None (validation only)

---

### FIX #10: algo/backtest/run_backtest.py, Line 356
**Severity**: HIGH  
**Category**: Missing validation on stdev for Sharpe ratio  
**Current Code**:
```python
std_ret = statistics.stdev(daily_returns)
if std_ret <= 0:
    raise ValueError("CRITICAL: Zero or negative volatility in returns (invalid backtest data)")
sharpe = round((avg_ret / std_ret * (252**0.5)), 4)
```

**Problem**: Validation is present (correct). However, if `len(daily_returns) < 2`, stdev() will raise ValueError before this check. Should validate count first.

**Fix**:
```python
if len(daily_returns) < 2:
    raise ValueError(
        f"CRITICAL: Insufficient daily returns ({len(daily_returns)}) for Sharpe calculation (need 2+). "
        f"Equity curve must have at least 3 snapshots (2+ returns)."
    )
std_ret = statistics.stdev(daily_returns)
if std_ret <= 0:
    raise ValueError(
        "CRITICAL: Zero or negative volatility in returns (invalid backtest data). "
        f"Check for flat equity curve (no price changes) or corrupt data."
    )
sharpe = round((avg_ret / std_ret * (252**0.5)), 4)
```

**Downstream Changes**: None (validation only)

---

### FIX #11: algo/reporting/performance.py, Line 85
**Severity**: HIGH  
**Category**: Silent zero return on insufficient snapshots  
**Current Code**:
```python
if len(rows) < 30:
    raise ValueError(
        f"Cannot calculate Sharpe ratio: insufficient portfolio snapshots ({len(rows)} found, need 30+). "
        f"Portfolio history too short ({lookback_days} days). "
        f"Sharpe is critical for risk assessment — cannot use default."
    )
```

**Problem**: Code IS correct (raises ValueError). However, on line 85 of the file, there's no actual fallback — the raise is there. This pattern may have been fixed already.

**Clarification**: Sharpe ratio function correctly raises on insufficient data. No fix needed.

---

### FIX #12: algo/reporting/performance.py, Line 174
**Severity**: HIGH  
**Category**: Silent fallback on R-multiple calculation  
**Current Code**:
```python
return {
    "win_rate_pct": _dec_round(win_rate_pct, 2),
    "win_count": int(win_count),
    "loss_count": int(loss_count),
    "avg_win_pct": _dec_round(avg_win_pct, 3),
    "avg_loss_pct": _dec_round(avg_loss_pct, 3),
    "avg_win_r": _dec_round(avg_win_r, 3),
    "avg_loss_r": _dec_round(avg_loss_r, 3),
}
```

**Problem**: Earlier on lines 163-168, if `avg_win_r is None`, it's set to 0.0. Similarly for `avg_loss_r`. This hides missing R-multiple data.

**Fix** (add before return):
```python
if avg_win_r is None or avg_loss_r_val is None:
    raise ValueError(
        f"CRITICAL: Win/loss R-multiples missing (avg_win_r={avg_win_r}, avg_loss_r={avg_loss_r_val}). "
        f"Cannot calculate expectancy without valid R-multiple data."
    )
```

**Downstream Changes**:
- `expectancy()` method will handle ValueError and propagate to caller
- Dashboard displays error instead of false metrics

---

### FIX #13: algo/monitoring/position_monitor.py, Line 1234
**Severity**: HIGH  
**Category**: Silent fallback on missing position_value  
**Current Code**:
```python
# CRITICAL: If we have open positions but position_value is NULL, that's data corruption
if position_count > 0 and pos_value_sum is None:
    raise PositionValidationError(
        f"CRITICAL: {position_count} open positions exist but SUM(position_value) is NULL. "
        "Database corruption detected. Margin calculation halted."
    )
```

**Problem**: Code correctly raises error. No fallback here.

**Clarification**: Position validation is correct (fail-fast on NULL position_value). No fix needed.

---

### FIX #14: algo/monitoring/position_monitor.py, Line 1256
**Severity**: HIGH  
**Category**: Invalid state check (margin_util_pct > 90)  
**Current Code**:
```python
margin_util_pct = pos_value / total_equity * 100
if margin_util_pct > 90:
    logger.critical(
        f"[MARGIN HALT] Position value {margin_util_pct:.1f}% of equity - liquidation risk imminent"
    )
    raise PositionValidationError(
        f"Margin utilization critical: {margin_util_pct:.1f}% of equity (>90%). Cannot proceed with position monitoring."
    )
```

**Problem**: Code correctly raises on high margin. However, no validation that pos_value and total_equity are both positive. If both are negative (corrupted), margin_util_pct is positive (false pass).

**Fix** (add before division):
```python
if pos_value < 0:
    raise PositionValidationError(
        f"CRITICAL: Position value negative ({pos_value}) — database corruption detected."
    )
if total_equity <= 0:
    raise PositionValidationError(
        f"CRITICAL: Total equity invalid ({total_equity}) — cannot calculate margin utilization."
    )
margin_util_pct = pos_value / total_equity * 100
if margin_util_pct > 90:
    logger.critical(...)
    raise PositionValidationError(...)
```

**Downstream Changes**: None (validation only)

---

### FIX #15: lambda/api/routes/algo_handlers/metrics.py, Line 276
**Severity**: HIGH  
**Category**: Silent fallback when portfolio metrics missing  
**Current Code** (lines 163-181):
```python
if not row:
    logger.warning(
        "Performance metrics unavailable: algo_performance_metrics table empty. "
        "Pre-computed metrics should be generated daily at 4:45 PM ET by compute_performance_metrics.py. "
        "Check data loader health."
    )
    return error_response(
        503,
        "data_unavailable",
        "Performance metrics not pre-computed. Check data loader health.",
    )
```

**Problem**: Code correctly returns error. No silent fallback.

**Clarification**: Lambda metrics handler correctly fails fast on missing data. No fix needed.

---

### FIX #16: lambda/api/routes/algo_handlers/signals.py, Line 117
**Severity**: CRITICAL  
**Category**: Missing validation on sector_value  
**Current Code** (lines 97-111):
```python
try:
    cur.execute("""
        SELECT COALESCE(cp.sector, 'Unknown') AS sector,
               SUM(ap.position_value) AS sector_value
        FROM algo_positions ap
        LEFT JOIN company_profile cp ON cp.ticker = ap.symbol
        WHERE ap.status = 'open'
        GROUP BY cp.sector
    """)
    for sr in cur.fetchall():
        if sr["sector"]:
            sector_val = float(sr["sector_value"])
            if sector_val is None:
                return error_response(503, "data_unavailable", "Sector exposure data incomplete")
```

**Problem**: After converting to float(), checking `if sector_val is None` is useless (float() would have failed). The real issue: if SUM returns NULL (no positions in sector), float(NULL) fails.

**Fix**:
```python
for sr in cur.fetchall():
    if sr["sector"]:
        sector_val_raw = sr["sector_value"]
        if sector_val_raw is None:
            logger.warning(f"Sector {sr['sector']} has NULL position_value sum — skipping")
            continue
        try:
            sector_val = float(sector_val_raw)
            if sector_val < 0:
                logger.warning(f"Sector {sr['sector']} has negative exposure ({sector_val}) — data corruption")
                continue
        except (ValueError, TypeError) as e:
            return error_response(503, "data_format_error", f"Sector exposure not numeric: {e}")
        sector_exposure[sr["sector"]] = sector_val
```

**Downstream Changes**: None (pre-trade impact calculation continues with partial data)

---

### FIX #17: lambda/api/routes/algo_handlers/signals.py, Line 139
**Severity**: CRITICAL  
**Category**: Division by zero on tier count missing  
**Current Code** (line 299):
```python
if missing:
    error_msg = f"Signal data incomplete: missing {missing}"
    logger.error(error_msg)
    return error_response(503, "incomplete_data", error_msg)

initial_count = int(row_data["total_signals"])
t1_count = int(row_data["t1_count"])

t2_val = row_data.get("t2_count")
if t2_val is None:
    logger.error("Signal rejection funnel data missing t2_count — cannot generate funnel tiers")
    return error_response(503, "incomplete_data", "Signal tier counts missing: t2_count")
t2_count = int(t2_val)
```

**Problem**: Code checks for missing t2_count (correct). But later uses tier counts in division without re-validating. If t3_count or t4_count is NULL, conversion to int() succeeds with 0, then division by (t2_count - 0) could be unstable.

**Fix**:
```python
# Validate all tier counts are non-NULL integers
tier_counts = ["t2_count", "t3_count", "t4_count", "t5_count"]
for tier in tier_counts:
    if row_data.get(tier) is None:
        logger.error(f"Signal rejection funnel data missing {tier}")
        return error_response(503, "incomplete_data", f"Signal tier counts missing: {tier}")

t2_count = int(row_data["t2_count"])
t3_count = int(row_data.get("t3_count", 0))  # Safe after validation
t4_count = int(row_data.get("t4_count", 0))
t5_count = int(row_data.get("t5_count", 0))

if t2_count <= 0 or t5_count <= 0:
    logger.error(f"Invalid tier counts: t2={t2_count}, t5={t5_count}")
    return error_response(503, "invalid_data", "Signal tiers have zero/negative counts")
```

**Downstream Changes**: Rejection funnel endpoint properly handles missing tiers

---

## Application Order Summary

### Phase 1: Core Risk Infrastructure (Days 1-2)
1. FIX #1: circuit_breaker.py:217 (drawdown validation)
2. FIX #2: circuit_breaker.py:433 (win_rate NaN check)
3. FIX #3: circuit_breaker.py:632 (weekly loss threshold)
4. FIX #8: var.py:388 (clarify — no fix needed, already correct)

### Phase 2: Position & Portfolio Data (Days 2-3)
5. FIX #5: reconciliation.py:315 (position_value NULL check)
6. FIX #6: reconciliation.py:333 (prior snapshot validation)
7. FIX #7: position_analyzer.py:64 (clarify — no fix needed, already correct)
8. FIX #4: position_sizer.py:648 (portfolio value validation)

### Phase 3: Backtest & Reporting (Days 3-4)
9. FIX #9: run_backtest.py:349 (years calculation)
10. FIX #10: run_backtest.py:356 (Sharpe ratio validation)
11. FIX #11: performance.py:85 (clarify — no fix needed, already correct)
12. FIX #12: performance.py:174 (R-multiple validation)

### Phase 4: Monitoring & Lambda (Days 4-5)
13. FIX #13: position_monitor.py:1234 (clarify — no fix needed, already correct)
14. FIX #14: position_monitor.py:1256 (margin validation)
15. FIX #15: metrics.py:276 (clarify — no fix needed, already correct)
16. FIX #16: signals.py:117 (sector_value NULL check)
17. FIX #17: signals.py:139 (tier count validation)

---

## Testing & Validation

After applying each fix:

1. **Unit Test**: Run pytest on modified file with mock failing data
2. **Integration Test**: Run live against test database with corrupted snapshot
3. **Smoke Test**: Verify circuit breaker, reconciliation, position sizing complete successfully
4. **Audit Log Check**: Confirm critical halts logged with proper reason codes

---

## Risk Assessment

- **HIGH RISK FIXES** (4): FIX #1, #2, #4, #16, #17 — affect trading decisions
- **MEDIUM RISK FIXES** (4): FIX #3, #5, #6, #12, #14 — affect performance reporting
- **LOW RISK FIXES** (2): FIX #9, #10 — backtest/reporting only
- **CLARIFICATIONS** (4): FIX #7, #8, #11, #13, #15 — already correct; remove from list

**Total Fixes Required**: 13 (not 16; 3 are clarifications that current code handles correctly)


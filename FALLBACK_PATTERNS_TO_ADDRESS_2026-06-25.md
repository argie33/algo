# Fallback Pattern Analysis - Remaining Issues
**Date:** 2026-06-25  
**Status:** PENDING - Issues identified, awaiting discussion

---

## Summary
Found **25+ additional fallback patterns** where code gracefully degrades to 0/None instead of failing fast. These span:
- Backtest performance metrics
- PnL and return calculations
- Position/exposure analysis
- Database query results
- Risk calculations
- Lambda API responses
- Audit logging

---

## CATEGORY 1: BACKTEST & PERFORMANCE METRICS (HIGH PRIORITY)

### 1.1 algo/backtest/run_backtest.py:274
**Issue:** Shares calculation silent fallback
```python
shares = position_dollars / entry_price if entry_price > 0 else 0
```
**Problem:** If entry_price is 0 or None, silently returns 0 shares instead of erroring
**Impact:** Backtest can run with zero-position trades, skewing metrics
**Fix:** Raise ValueError if entry_price <= 0

---

### 1.2 algo/backtest/run_backtest.py:338
**Issue:** Annualized return silent fallback
```python
annualized_return_pct = ((final_capital / initial_capital) ** (1.0 / years) - 1) * 100 if years > 0 else 0
```
**Problem:** Returns 0% annualized when years <= 0 (should error on bad date range)
**Impact:** Invalid backtests appear to have 0% return instead of failing
**Fix:** Raise ValueError if years <= 0

---

### 1.3 algo/backtest/run_backtest.py:375
**Issue:** Standard deviation silent fallback
```python
std_ret = statistics.stdev(daily_returns) if len(daily_returns) > 1 else 0
```
**Problem:** Returns 0 volatility if fewer than 2 data points (insufficient for stats)
**Impact:** Sharpe ratio becomes meaningless (0 std in denominator → 0 sharpe)
**Fix:** Raise ValueError if len(daily_returns) < min_observations

---

### 1.4 algo/backtest/run_backtest.py:378
**Issue:** Average trade return silent fallback
```python
avg_trade_return_pct = sum(t["profit_loss_pct"] for t in completed_trades) / total_trades if total_trades > 0 else 0
```
**Problem:** Returns 0% average return if no trades executed (misleading)
**Impact:** No-trade backtests report 0% avg return instead of "N/A" or error
**Fix:** Return None or raise ValueError if total_trades == 0

---

## CATEGORY 2: PnL & RETURN REPORTING (HIGH PRIORITY)

### 2.1 algo/reporting/daily_report.py:77
**Issue:** Daily PnL % silent fallback
```python
daily_pnl_pct = ((current_value - prior_value) / prior_value * 100) if prior_value > 0 else 0
```
**Problem:** Returns 0% if prior_value is 0 or None (prior_value should never be 0 for portfolio)
**Impact:** Portfolio snapshots with missing prior data appear flat instead of erroring
**Fix:** Raise ValueError if prior_value <= 0

---

### 2.2 algo/reporting/daily_report.py:88
**Issue:** YTD PnL % silent fallback
```python
ytd_pnl_pct = ((current_value - ytd_start) / ytd_start * 100) if ytd_start > 0 else 0
```
**Problem:** Returns 0% if ytd_start is 0 or None
**Impact:** Year-to-date metrics can be fabricated from missing data
**Fix:** Raise ValueError if ytd_start <= 0

---

### 2.3 algo/reporting/daily_report.py:392
**Issue:** Query result count silent fallback
```python
return result[0] if result else 0
```
**Problem:** Database query returns None → silently becomes 0 (could mask query failure)
**Impact:** Snapshot count reports could be completely wrong
**Fix:** Raise RuntimeError if query returns None

---

## CATEGORY 3: TRADE & POSITION METRICS (HIGH PRIORITY)

### 3.1 algo/signals/trade_performance.py:154-156
**Issue:** Trade prices and PnL silent fallback
```python
float(entry_price) if entry_price else 0,
float(exit_price) if exit_price else 0,
float(pnl_dollars) if pnl_dollars else 0,
```
**Problem:** Missing trade prices become 0 (impossible to distinguish from actual 0 values)
**Impact:** Invalid trades stored in database with fabricated metrics
**Fix:** Raise ValueError if any of entry_price, exit_price, pnl_dollars are None

---

### 3.2 algo/orchestrator/phase9_reconciliation.py:505
**Issue:** Reconciliation PnL % silent fallback
```python
pnl_pct = ((exit_price - entry_price) / entry_price * 100) if entry_price > 0 else 0
```
**Problem:** Returns 0% if entry_price is 0 (should never be 0 for closed trade)
**Impact:** Reconciliation reports can have fabricated metrics
**Fix:** Raise ValueError if entry_price <= 0

---

## CATEGORY 4: POSITION & EXPOSURE ANALYSIS (HIGH PRIORITY)

### 4.1 algo/infrastructure/position_analyzer.py:92
**Issue:** Unrealized PnL % silent fallback
```python
unrealized_pnl_pct = (
    float(unrealized_pnl / total_position_value * Decimal(100)) if total_position_value > 0 else 0.0
)
```
**Problem:** Returns 0% if total_position_value is 0 or None (no positions)
**Impact:** Position analysis with no data appears flat
**Fix:** Return None or raise ValueError if total_position_value <= 0

---

### 4.2 algo/infrastructure/reconciliation.py:1189
**Issue:** Variance % silent fallback
```python
variance_pct = (variance_dollars / broker_equity) * 100.0 if broker_equity > 0 else 0.0
```
**Problem:** Returns 0% variance if broker_equity is 0 (impossible scenario)
**Impact:** Reconciliation of zero-equity account appears successful
**Fix:** Raise ValueError if broker_equity <= 0

---

### 4.3 algo/infrastructure/audit_logger.py:282
**Issue:** Position size metric silent fallback
```python
"avg_position_size_pct": float(row[4]) if row[4] else 0,
```
**Problem:** Missing row[4] value becomes 0% (indistinguishable from actual 0%)
**Impact:** Audit log has fabricated position metrics
**Fix:** Raise ValueError if row[4] is None

---

### 4.4 algo/risk/var.py:539
**Issue:** Position percentage silent fallback
```python
position_pct = position_value / portfolio_value_float * 100 if portfolio_value_float > 0 else 0
```
**Problem:** Returns 0% if portfolio is empty (should signal no portfolio)
**Impact:** Risk calculations on empty portfolio appear valid
**Fix:** Return None or raise ValueError if portfolio_value_float <= 0

---

### 4.5 algo/risk/market_exposure.py:666
**Issue:** Query count result fallback
```python
return int(row[0]) if row is not None and row[0] is not None else 0
```
**Problem:** Query returning None becomes count=0 (masks query failures)
**Impact:** Market exposure count could be completely wrong
**Fix:** Raise RuntimeError if query returns None

---

### 4.6 algo/risk/market_exposure.py:727
**Issue:** Price distance % silent fallback
```python
price_pct = (cur_close - sma_now) / sma_now * 100.0 if sma_now > 0 else 0
```
**Problem:** Returns 0% if SMA is 0 or None (should error)
**Impact:** Risk analysis with missing SMA data appears valid
**Fix:** Raise ValueError if sma_now <= 0

---

### 4.7 algo/risk/exposure_policy.py:252
**Issue:** R-multiple calculation silent fallback
```python
r_mult = ((cur_price_float - entry_price) / risk_per_share) if risk_per_share > 0 else 0
```
**Problem:** Returns 0 if risk_per_share is 0 or None (invalid trade setup)
**Impact:** Exposure policy with invalid stop loss appears safe
**Fix:** Raise ValueError if risk_per_share <= 0

---

## CATEGORY 5: LAMBDA API HANDLERS (HIGH PRIORITY - PUBLIC FACING)

### 5.1 lambda/api/routes/algo_handlers/signals.py:76
**Issue:** Signal shares calculation silent fallback
```python
shares = int(position_dollars / entry_price) if entry_price and entry_price > 0 else 0
```
**Problem:** API returns 0 shares if entry_price missing or 0
**Impact:** API clients get fabricated share counts
**Fix:** Raise ValueError or return error response if entry_price <= 0

---

### 5.2 lambda/api/routes/algo_handlers/signals.py:201-202
**Issue:** Signal position sizing silent fallback
```python
shares = int(position_dollars / entry_price) if entry_price > 0 else 0
pct_of_portfolio = (actual_dollars / portfolio_value * 100) if portfolio_value > 0 else 0
```
**Problem:** Multiple fallback values → compounded errors
**Impact:** Signals API returns completely fabricated position sizes
**Fix:** Raise ValueError or return error response on missing data

---

### 5.3 lambda/api/routes/algo_handlers/sector.py:72 ⚠️ CRITICAL
**Issue:** Position count silent fallback
```python
open_positions = pos_row["open_positions"] if pos_row else 0
```
**Problem:** If query returns no row (None), position count becomes 0 instead of "unknown"
**Impact:** API clients think there are 0 positions when query failed
**Impact:** Available slots calculation becomes wrong: `available_slots = max(0, 15 - 0) = 15` (incorrect)
**Fix:** Raise ValueError if pos_row is None (query error)

---

### 5.4 lambda/api/routes/algo_handlers/metrics.py:322
**Issue:** Daily return silent fallback
```python
(float(r["daily_return_pct"]) if r.get("daily_return_pct") is not None else 0.0)
```
**Problem:** Returns 0.0% if daily_return_pct missing from snapshot
**Impact:** Snapshot returns fabricated if data gaps exist
**Fix:** Raise ValueError if daily_return_pct is None

---

## CATEGORY 6: DATABASE HELPERS (CRITICAL - INFRASTRUCTURE)

### 6.1 utils/loaders/helpers.py:313
**Issue:** COUNT query silent fallback
```python
query = f"SELECT COUNT(*) FROM {table}{where_sql}"
result = fetch_one(query, params, timeout=timeout)
return result[0] if result else 0
```
**Problem:** If query fails (returns None), count becomes 0 (masks failure)
**Impact:** All count-based operations downstream get wrong values
**Impact:** Loaders think there are 0 rows when actually query failed
**Fix:** Raise RuntimeError if result is None

---

### 6.2 utils/optimal_loader.py:456
**Issue:** Total rows count fallback
```python
total_rows = result[0] if result else 0
```
**Problem:** Query failure → count=0 (masks database problems)
**Impact:** Loader thinks table is empty when it's actually a query error
**Fix:** Raise RuntimeError if result is None

---

### 6.3 loaders/load_prices.py:1603
**Issue:** Price data count fallback
```python
total_rows = result[0] if result else 0
```
**Problem:** Query failure → count=0 (masks data pipeline issues)
**Impact:** Price loading appears to have 0 rows when actually query failed
**Fix:** Raise RuntimeError if result is None

---

## CATEGORY 7: DASHBOARD DISPLAY (MEDIUM PRIORITY - UI ONLY)

### 7.1 dashboard/panels/portfolio.py:565-566
**Issue:** Portfolio PnL safe fallback
```python
pnl_val_safe = pnl_val if pnl_val is not None else 0
unrlzd_pnl_safe = unrlzd_pnl if unrlzd_pnl is not None else 0
```
**Status:** ACCEPTABLE - UI display code, not finance logic. Should show "--" instead of 0.
**Suggested Fix:** Change to `pnl_val if pnl_val is not None else "[dim]N/A[/]"`

---

### 7.2 dashboard/panels/sectors.py:350
**Issue:** Average PnL safe fallback
```python
avg_pnl = sum(dv["pnls"]) / len(dv["pnls"]) if dv["pnls"] else 0
```
**Status:** ACCEPTABLE - UI aggregation code. Should show "--" instead of 0.
**Suggested Fix:** Return None and handle in display logic

---

## SUMMARY TABLE

| Category | File | Line | Pattern | Severity | Impact |
|----------|------|------|---------|----------|--------|
| Backtest | run_backtest.py | 274 | shares fallback | HIGH | Invalid trades |
| Backtest | run_backtest.py | 338 | annualized_return fallback | HIGH | Fake metrics |
| Backtest | run_backtest.py | 375 | stdev fallback | HIGH | Invalid sharpe |
| Backtest | run_backtest.py | 378 | avg_return fallback | HIGH | Misleading reports |
| Reporting | daily_report.py | 77 | daily_pnl_pct fallback | HIGH | Fabricated metrics |
| Reporting | daily_report.py | 88 | ytd_pnl_pct fallback | HIGH | Fabricated metrics |
| Reporting | daily_report.py | 392 | query result fallback | HIGH | Data loss |
| Trading | trade_performance.py | 154-156 | price/pnl fallback | HIGH | Invalid trades |
| Reconciliation | phase9_reconciliation.py | 505 | pnl_pct fallback | HIGH | Fake metrics |
| Position | position_analyzer.py | 92 | unrealized_pnl_pct fallback | HIGH | Invalid metrics |
| Reconciliation | reconciliation.py | 1189 | variance_pct fallback | HIGH | Invalid validation |
| Audit | audit_logger.py | 282 | position_size_pct fallback | HIGH | Fake audit data |
| Risk | var.py | 539 | position_pct fallback | HIGH | Invalid risk calc |
| Risk | market_exposure.py | 666 | count fallback | HIGH | Wrong exposure |
| Risk | market_exposure.py | 727 | price_pct fallback | HIGH | Invalid risk |
| Risk | exposure_policy.py | 252 | r_mult fallback | HIGH | Invalid policy |
| API | signals.py | 76 | shares fallback | HIGH | Wrong API data |
| API | signals.py | 201-202 | sizing fallback | HIGH | Wrong API data |
| API | sector.py | 72 | position_count fallback | **CRITICAL** | Wrong available slots |
| API | metrics.py | 322 | daily_return fallback | HIGH | Wrong API data |
| Database | helpers.py | 313 | count fallback | **CRITICAL** | Masks failures |
| Database | optimal_loader.py | 456 | count fallback | **CRITICAL** | Masks failures |
| Database | load_prices.py | 1603 | count fallback | **CRITICAL** | Masks failures |
| Dashboard | portfolio.py | 565-566 | pnl fallback | LOW | Display only |
| Dashboard | sectors.py | 350 | avg_pnl fallback | LOW | Display only |

---

## CRITICAL ISSUES (Must Fix)

1. **lambda/api/routes/algo_handlers/sector.py:72** - Available position slots calculation breaks if query fails
2. **utils/loaders/helpers.py:313** - COUNT queries silently fail with 0 (infrastructure failure)
3. **utils/optimal_loader.py:456** - Price count queries silently fail (data pipeline)
4. **loaders/load_prices.py:1603** - Price data count queries silently fail

---

## HIGH PRIORITY (Finance Accuracy)

All 21 finance/trading calculations that silently fall back to 0 or None.

---

## NEXT STEPS

1. Review findings with team
2. Prioritize fixes (Critical → High → Medium)
3. Create fail-fast replacements
4. Add validation to prevent regressions
5. Update GOVERNANCE.md with new patterns to avoid


# Session 287: Critical Governance Violations - Data Unavailability Check Bypass Patterns

**Status:** AUDIT IN PROGRESS  
**Date:** 2026-07-20  
**Severity:** CRITICAL  
**Governance Principle:** "Fail-fast on missing data. No silent fallbacks."

---

## EXECUTIVE SUMMARY

Systematic audit of 37 tables with `data_unavailable` flags revealed **16 files with governance violations** where code queries tables without checking the `data_unavailable` flag before using data.

**Impact:** 
- Circuit breaker (Phase 2, always-run) queries market_health_daily without data_unavailable checks
- Position monitor (Phase 3, always-run) queries market_health_daily/price_daily without checks
- Risk dashboard (API) queries market_health_daily without checks
- Violates GOVERNANCE.md: "Fail-fast on missing data"

---

## TABLES WITH DATA_UNAVAILABLE FLAGS

37 tables identified:
- **Critical for trading:** price_daily, technical_data_daily, market_exposure_daily, stock_scores, buy_sell_daily
- **Market regime:** market_health_daily (partial - only put_call_ratio/yield_curve/fed_rate have flags)
- **Metrics:** growth_metrics, quality_metrics, value_metrics, stability_metrics, positioning_metrics
- **Others:** earnings_calendar, company_info_sec, sector_ranking, signal_quality_scores, trend_template_data, etc.

---

## FILES WITH GOVERNANCE VIOLATIONS

### CRITICAL (Always-Run Phases)

| File | Phase | Severity | Tables | Line(s) |
|------|-------|----------|--------|---------|
| algo/risk/circuit_breaker.py | 2 | **CRITICAL** | market_health_daily | 356, 611, 734, 819, 880 |
| algo/orchestrator/phase3_position_monitor.py | 3 | **CRITICAL** | price_daily | TBD |
| algo/monitoring/position_monitor.py | - | **CRITICAL** | market_health_daily, price_daily | TBD |

### HIGH (Always-Run or Risk-Related)

| File | Type | Severity | Tables |
|------|------|----------|--------|
| lambda/api/routes/risk_dashboard.py | API | HIGH | market_health_daily, market_exposure_daily |
| algo/infrastructure/market_events.py | Config | HIGH | market_health_daily |
| lambda/api/routes/market.py | API | HIGH | market_health_daily, market_exposure_daily |
| lambda/api/routes/economic.py | API | MEDIUM | market_health_daily |
| lambda/api/routes/sentiment.py | API | MEDIUM | market_health_daily |

### MEDIUM (Data Monitoring)

| File | Type | Tables |
|------|------|--------|
| algo/monitoring/data_patrol/checks/alignment.py | Monitoring | buy_sell_daily, price_daily, technical_data_daily |
| algo/monitoring/data_patrol/checks/coverage.py | Monitoring | buy_sell_daily, price_daily |
| algo/monitoring/data_patrol/checks/price_sanity.py | Monitoring | price_daily |
| algo/monitoring/data_patrol/checks/quality.py | Monitoring | price_daily |
| algo/monitoring/data_patrol/checks/specialized.py | Monitoring | price_daily, technical_data_daily |

### MARKET/RISK FACTORS

Risk factor files (all query price_daily or market_health_daily without checking):
- algo/risk/factors/ad_line_factor.py
- algo/risk/factors/credit_appetite_factor.py
- algo/risk/factors/growth_vs_value_factor.py
- algo/risk/factors/momentum_factor.py
- algo/risk/factors/new_highs_lows_factor.py
- algo/risk/factors/put_call_ratio_factor.py
- algo/risk/factors/russell_vs_spy_factor.py
- algo/risk/factors/selling_pressure_factor.py
- algo/risk/factors/short_term_momentum_factor.py
- algo/risk/factors/trend_30wk_factor.py
- algo/risk/factors/vix_mean_reversion_factor.py
- algo/risk/factors/vix_regime_factor.py
- algo/risk/factors/volume_trend_factor.py

---

## SPECIFIC VIOLATIONS FOUND

### 1. circuit_breaker.py - Line 734 (CRITICAL)

```python
# VIOLATES GOVERNANCE: Doesn't check data_unavailable
cur.execute(
    "SELECT date, market_stage, market_trend FROM market_health_daily WHERE date <= %s ORDER BY date DESC LIMIT 1",
    (expected_data_date,),
)
row = cur.fetchone()
if row is None:  # Only checks if row exists, NOT data_unavailable flag
    return {"halted": True, "reason": "Market health data missing..."}
# Uses market_stage without verifying data_unavailable
```

**Impact:** Phase 2 (Circuit Breakers, always-run) uses stale market regime data when data_unavailable=True

### 2. circuit_breaker.py - Line 611 (CRITICAL)

```python
# VIOLATES GOVERNANCE: Doesn't check data_unavailable for VIX
cur.execute(
    "SELECT vix_level, date FROM market_health_daily WHERE date <= %s AND vix_level IS NOT NULL ORDER BY date DESC LIMIT 1",
    (current_date,),
)
row = cur.fetchone()
# ... uses vix without checking if data_unavailable=True
```

**Impact:** Phase 2 uses stale VIX data for risk thresholds

### 3. risk_dashboard.py - Line 132 (HIGH)

```python
# VIOLATES GOVERNANCE: Doesn't check data_unavailable
cur.execute(
    "SELECT vix_level FROM market_health_daily WHERE vix_level IS NOT NULL ORDER BY date DESC LIMIT 1"
)
# Uses VIX to compute risk-adjusted metrics without verifying data freshness/availability
```

**Impact:** Dashboard shows incorrect risk metrics if data unavailable

---

## ROOT CAUSE ANALYSIS

1. **Schema inconsistency:** market_health_daily doesn't have a general `data_unavailable` flag (only specific fields like put_call_ratio_data_unavailable)
   - Other critical tables DO have the flag (market_exposure_daily, stock_scores, price_daily)
   - This creates confusion about which tables need checks

2. **Bypass pattern:** Code checks for NULL values but not for explicit `data_unavailable=True`
   - NULL check is insufficient: `vix_level IS NOT NULL` doesn't verify data quality
   - Loader can set vix_level AND data_unavailable=True if computation failed

3. **Missing enforcement:** Linting/pre-commit doesn't catch "SELECT FROM *_daily without data_unavailable check"

---

## FIX STRATEGY

### Phase 1: Schema Normalization (Optional, Low Priority)
- Add general `data_unavailable` flag to market_health_daily for consistency
- Change per-field flags to single flag with JSON reason field
- **Not blocking:** Current code can work around this

### Phase 2: Code Fixes (URGENT)

#### CRITICAL FIXES (Fix Today)

1. **circuit_breaker.py:**
   - Line 734: Add market_health_daily.data_unavailable check before using market_stage
   - Line 611: Add check before using vix_level (or check put_call_ratio_data_unavailable)
   - Line 356: Add check before using market_stage
   - Line 819, 880: Add price_daily.data_unavailable check

2. **position_monitor.py & phase3_position_monitor.py:**
   - Add data_unavailable checks for price_daily, market_health_daily queries

3. **risk_dashboard.py:**
   - Line 132: Add check before using market_health_daily data

#### HIGH PRIORITY (This Week)

- lambda/api/routes/market.py
- lambda/api/routes/risk_dashboard.py (all endpoints)
- algo/infrastructure/market_events.py

#### MEDIUM PRIORITY (Next Week)

- risk/factors/*.py (all 13 factor files)
- algo/monitoring/data_patrol/checks/*.py

---

## TESTING STRATEGY

1. **Unit tests:** Create test cases where data_unavailable=True, verify code raises RuntimeError
2. **Integration tests:** Run orchestrator with synthetic data_unavailable flags set
3. **Manual testing:** Disable a loader, verify phases fail-fast instead of using stale data

---

## GOVERNANCE REFERENCES

**GOVERNANCE.md - Data Quality:**
> "Fail-fast on missing data. No silent fallbacks. Incomplete data is honest data."

**GOVERNANCE.md - Required Availability Check:**
> "Every record must have `data_unavailable` flag (BOOLEAN, default FALSE). When `data_unavailable=TRUE`, include `reason` field explaining why."

**GOVERNANCE.md - Strict Rules:**
> "Fail-fast on insufficient data: Return `None` (not degraded data) when... No secondary fallbacks: Never use..."

---

## FIX CHECKLIST

- [ ] Fix circuit_breaker.py (lines 356, 611, 734, 819, 880)
- [ ] Fix position_monitor.py
- [ ] Fix phase3_position_monitor.py
- [ ] Fix risk_dashboard.py
- [ ] Fix market_events.py
- [ ] Fix lambda/api/routes/market.py
- [ ] Fix lambda/api/routes/risk_dashboard.py (all endpoints)
- [ ] Fix risk/factors/*.py (13 files)
- [ ] Fix data_patrol/checks/*.py (5 files)
- [ ] Add pre-commit linting rule: "SELECT FROM *_daily must check data_unavailable"
- [ ] Create integration test: verify fail-fast with data_unavailable=True
- [ ] Update memory with findings and fixes applied

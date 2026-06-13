# FINANCIAL DATA INTEGRITY AUDIT
**Completed:** 2026-06-13  
**Scope:** Complete codebase scan for fake fallbacks, placeholder values, mock data, and integrity risks

---

## CRITICAL FINDINGS (Financial Data Can Be Compromised)

### 1. ⚠️ CRITICAL: Hardcoded Placeholder Values in Buy/Sell Signal Generation
**File:** `loaders/load_buy_sell_daily.py:335-340`  
**Issue:** Uses `999999` as fake default value to detect missing "low" prices in swing low detection logic
```python
lookback_ok = all(rows[k].get("low", 999999) is not None and
                 (rows[k].get("low", 999999) > rows[j].get("low", 999999) or k >= j)
                 for k in range(max(0, j-3), j))
```
**Impact:** If a historical low price is truly missing from database, this fake 999999 value is used in comparisons, incorrectly inflating perceived price floors for stop loss calculation.
**Risk:** Wrong stop loss levels → incorrect position sizing → financial losses
**Status:** ACTIVE - affects all BUY/SELL signals generated

---

### 2. ⚠️ CRITICAL: Value Capping at Database Limits Causes Silent Data Loss
**File:** `loaders/load_buy_sell_daily.py:373` and multiple technical loaders  
**Issue:** Volume surge percentage capped at 9999% (database DECIMAL(8,4) limit)
```python
vol_surge = round(min(raw_surge, 9999.0), 2)  # Line 373
```
**Details:**
- `load_buy_sell_daily.py:500`: `_DECIMAL84_MAX = 9999.9999`
- `load_technical_data_daily.py:217`: ROC capped at ±9999.9999
- `load_technical_data_daily_vectorized.py:180`: Same ROC capping
- High-priced stocks (ASML=$3000+, BLK=$1000+) can trigger extreme metrics
- Example: 15000% volume surge on ASML gets silently capped to 9999%

**Impact:** Extreme market conditions (panics, breakout moves) are masked as less severe
**Risk:** Signal quality degraded during volatile periods when they're most important
**Status:** ACTIVE - affects all technical signals

---

### 3. ⚠️ CRITICAL: Fallback Registry Allows All-Zero Fake Metrics to Reach Users
**File:** `utils/fallback_registry.py:224-251`  
**Issue:** Hardcoded all-zero performance metrics returned when both API and cache fail
```python
FallbackStep(
    name="hardcoded_defaults",
    priority=2,
    description="All-zero placeholder metrics: total_trades=0, win_rate=0%, ...",
    logs_with="[METRICS] CRITICAL - using hardcoded defaults (all zeros)",
    hardcoded_values={
        "total_trades": 0,
        "winning_trades": 0,
        "win_rate_pct": 0.0,
        "profit_factor": 0.0,
        "sharpe_ratio": 0.0,
        "max_drawdown_pct": 0.0,
        ...
    }
)
```
**Current Usage:**
- `lambda/api/routes/algo.py:672`: Returns hardcoded defaults on metrics failure
- Dashboard panels (lines 644, 763, 924, 1951) detect and warn about this but still display it

**Impact:** Users see zeros instead of real P&L; cannot differentiate between "no data" and "bad performance"
**Risk:** Misleading dashboard display; false confidence in algo performance
**Status:** ACTIVE - documented to occur "rarely" but with no time bounds

---

### 4. ⚠️ HIGH: Inconsistent Hardcoded Defaults for Missing Data
**File:** `algo/algo_data_patrol.py:69, 182`  
**Issue:** Falls back to hardcoded default (7 days) if data freshness config not found
```python
max_days = self._get_config_value(cur, config_key, 7)  # Default to 7 days if config missing
```
**Problem:** If `algo_config` table is corrupted or deleted:
- Stale data threshold defaults to arbitrary 7 days
- No way to tell if 7 days is correct for this environment
- Config load failures are hidden

**Status:** MEDIUM - fallback prevents crashes but uses unvalidated defaults

---

### 5. ⚠️ HIGH: Multiple Placeholder/Mock Values in Signal Calculations
**File:** `loaders/load_trend_criteria_data.py:197`  
**Issue:** Fallback magic number 999.0 for consolidation range calculation
```python
rng = (recent.max() - recent.min()) / mean_price if mean_price > 0 else 999.0
```
**Impact:** If recent price data unavailable, returns fake 999.0 range → breaks consolidation detection

**File:** `loaders/load_technical_data_daily.py:176`  
**Issue:** Returns 999 as age if data source age calculation fails
```python
return 999  # Fallback age if exception occurs
```
**Impact:** Age-based filtering can't distinguish between "999 days old" (real return) vs. "error state"

---

## HIGH PRIORITY FINDINGS (Data Integrity Risk)

### 6. ⚠️ FALLBACK DATA DETECTION IS PRESENT BUT INCOMPLETE
**Files:** `tools/dashboard/panels.py` (multiple locations), `tools/dashboard/dashboard-dev.py:1068`  
**Status:** Dashboard checks for `_is_placeholder` and `_is_fallback_data` flags and displays red borders/warnings
**Problem:** 
- Fallback flags are set in some places but not all
- API endpoint may return fallback data without these flags in some code paths
- No centralized enforcement that ALL fallback data is marked

**Checked Locations:**
- ✅ `tools/dashboard/panels.py:647` - positions fallback detection
- ✅ `tools/dashboard/panels.py:763` - buy signals fallback detection
- ✅ `tools/dashboard/panels.py:924` - recent trades fallback detection
- ✅ `tools/dashboard/panels.py:1951` - expanded signals fallback detection
- ✅ `tools/dashboard/dashboard-dev.py:1068` - performance fallback detection

---

### 7. ⚠️ SEC EDGAR CLIENT HARDCODED FALLBACK TICKER CACHE
**File:** `utils/sec_edgar_client.py:75-394, 908-910`  
**Issue:** 10,365+ ticker-to-CIK mappings are hardcoded as fallback
```python
_FALLBACK_TICKERS = {
    "AAPL": "0000320193",
    "MSFT": "0000789019",
    ...  # 10,365+ entries hardcoded
}
```
**When Used:** When SEC Edgar API is unavailable  
**Risk:** 
- Hardcoded cache can become stale (new symbols not added until code deploys)
- Unknown which version of CIK mappings is baked in
- No version control or timestamp on hardcoded data
- Ticker reclassifications not reflected

**Status:** MEDIUM - fallback is explicit, but staleness not managed

---

### 8. ⚠️ REALTIME PRICES FALLBACK TO STALE DAILY PRICES
**File:** `algo/algo_realtime_prices.py:214-220, 80`  
**Issue:** Outside market hours, realtime prices fallback to cached/daily prices
```python
if not self.is_market_hours():
    return self._get_fallback_prices(symbols)  # Returns cached or daily prices
```
**Risk:** Pre-market or after-hours signals use stale daily closes, not realtime prices
**Status:** MEDIUM - fallback is necessary (market closed) but users must understand staleness

---

### 9. ⚠️ ALPACA POSITION SYNC FALLBACK DATA TRACKING
**File:** `algo/algo_position_monitor.py:321-322`  
**Issue:** Position monitor tracks price sources but doesn't prevent fallback use in calculations
```python
'price_source': price_metadata.get('source', 'daily'),  # Issue #33: Fallback indicator
'price_is_fallback': price_metadata.get('is_fallback', False),  # Issue #33: Mark fallback
```
**Risk:** Even though fallback is marked, position P&L calculations proceed with stale data
**Status:** MEDIUM - marked but not prevented

---

### 10. ⚠️ SQL QUERY PLACEHOLDERS VS. DATA PLACEHOLDERS (Not a risk, correct usage)
**Files:** Multiple loaders use SQL `%s` placeholders correctly
**Status:** ✅ GOOD - proper parameterized queries throughout codebase

---

## MEDIUM PRIORITY FINDINGS (Data Quality Issues)

### 11. Stop Loss Calculation Uses Hardcoded Percentages
**File:** `loaders/load_buy_sell_daily.py:353, 362, 400, 417, 424`  
**Issue:** Fallback stop loss: 8% default when swing low not found
```python
stoplevel = round(close * 0.92, 4)  # 8% default fallback
```
**Risk:** Not a "fake" value but hardcoded assumption—may not fit all market conditions
**Status:** MEDIUM - by design, but risk if system never finds proper swing lows

---

### 12. Daily Report Uses "N/A" Instead of Zeros (Good)
**File:** `algo/algo_daily_report.py:265-300`  
**Status:** ✅ CORRECT - explicitly avoids fake zeros, uses "N/A" for missing data:
```python
logger.warning(f"Daily P&L missing for {report['date']} — using N/A instead of fake 0")
```
**Note:** This is the right pattern—should be replicated elsewhere

---

### 13. Signal Pattern Fallback Stop Loss
**File:** `algo/signals/signal_patterns.py:407`  
**Issue:** 3-week timeframe (3WT) signals have fallback to 8% stop
```python
if twt.get('is_3wt') and method == 'fallback_8pct':
```
**Status:** MEDIUM - documented as fallback but magic 8% hardcoded

---

## LOW PRIORITY FINDINGS (Documentation/Code Quality)

### 14. Feature Flag A/B Test Defaults
**File:** `utils/feature_flags.py:167, 199, 341`  
**Issue:** Default A/B test variant is "control"
```python
def get_ab_test_variant(self, test_name: str, default: str = "control") -> str:
```
**Status:** LOW - default is reasonable, but document why "control" chosen

---

### 15. Config Default Parallelism
**File:** `utils/loader_config.py:326`  
**Issue:** Default parallelism for loaders is 1 if not configured
```python
def get_default_parallelism(loader_name: str, fallback: int = 1) -> int:
```
**Status:** LOW - safe default, prevents resource exhaustion

---

## AUDIT SCRIPT VERIFICATION

**File:** `scripts/audit-data-flow.py`  
**Purpose:** Scans for undocumented fallback patterns  
**Coverage:** Detects `_is_fallback_data`, `_is_placeholder`, fallback logging, trigger enums
**Status:** ✅ GOOD - audit tool exists but needs periodic runs

---

## SUMMARY TABLE

| Issue | File | Severity | Detected | Marked | Root Cause |
|-------|------|----------|----------|--------|-----------|
| 999999 low placeholder | load_buy_sell_daily.py:335 | 🔴 CRITICAL | ✅ Yes | ❌ No flag | Missing data handling |
| Value capping 9999.9999 | load_buy_sell_daily.py:373 | 🔴 CRITICAL | ✅ Yes | ❌ Silent loss | DB constraint |
| All-zero metrics fallback | fallback_registry.py:229 | 🔴 CRITICAL | ✅ Yes | ✅ Flagged | API failure path |
| Hardcoded config defaults | algo_data_patrol.py:182 | 🟠 HIGH | ✅ Yes | ❌ No flag | Config load failure |
| 999.0 consolidation fallback | load_trend_criteria_data.py:197 | 🟠 HIGH | ✅ Yes | ❌ No flag | Missing price data |
| Age 999 fallback | load_technical_data_daily.py:176 | 🟠 HIGH | ✅ Yes | ❌ No flag | Calc exception |
| Incomplete fallback marking | panels.py (5 locations) | 🟠 HIGH | ✅ Yes | ⚠️ Partial | Code paths uncovered |
| SEC hardcoded cache | sec_edgar_client.py:75 | 🟠 HIGH | ✅ Yes | ✅ Documented | Staleness risk |
| Realtime→daily fallback | algo_realtime_prices.py:80 | 🟠 HIGH | ✅ Yes | ✅ Marked | Market hours logic |
| Hardcoded 8% stop loss | load_buy_sell_daily.py:353 | 🟡 MEDIUM | ✅ Yes | ⚠️ Comment | Design choice |

---

## RECOMMENDATIONS (Ordered by Impact)

### IMMEDIATE (Today)
1. **Fix line 335-340 in load_buy_sell_daily.py**: Replace 999999 placeholder with proper None handling or require complete data
   - Don't use fake high values in comparisons
   - Reject signal generation if lows are missing instead

2. **Audit capping logic**: Document why 9999.9999 cap exists and consider skipping signals when values exceed it
   - Add `_value_capped` flag to signals showing which metrics hit the cap
   - Users need to know when metrics are truncated

3. **Verify fallback marking in all API code paths**: Ensure `_is_fallback_data` is set on EVERY fallback return
   - Grep for all fallback paths in `lambda/api/routes/*.js`
   - Add unit tests that fallback responses have the flag

### THIS WEEK  
4. **Create fallback data integration test**: Verify dashboard correctly displays fallback warnings
   - Test that all 5 dashboard panel locations show red borders when fallback detected
   - Test that users cannot place orders when data is fallback

5. **Document signal rejection reasons**: When signals are rejected due to missing data, log detailed reasons
   - Check `signal_rejection_log` table has proper categories
   - Verify Phase 5 can filter by rejection reason

6. **Configuration defaults audit**: Map all hardcoded defaults (7 days, 8%, 20.0, etc.)
   - Create `config/defaults_registry.md` documenting every hardcoded value
   - For each: why chosen, when fallback, what acceptable range is

### THIS MONTH
7. **Implement data provenance tracking**: Every financial number should know its source
   - Add `_data_source`, `_data_age`, `_is_estimated`, `_is_fallback` to all API responses
   - Dashboard must display source quality prominently

8. **Remove or version hardcoded fallback caches**: SEC ticker cache, fallback metrics
   - Either fetch fresh on startup or clearly version the data
   - Add TTL and staleness warnings

9. **Audit all swing low/high logic**: If input data is incomplete, what are the consequences?
   - Can system generate valid signals with 50% missing historical data?
   - What's the minimum lookback window needed for valid detection?

### ONGOING
10. **Run audit script weekly**: `scripts/audit-data-flow.py` should be part of CI/CD
11. **Monitor fallback usage**: Alert if performance metrics fallback triggered more than 1× per day
12. **Version all configuration defaults**: No magic numbers, all in `config/algo_config.py` with documented reasoning

---

## FILES TO REVIEW IMMEDIATELY

1. ✋ `loaders/load_buy_sell_daily.py:335-340` — Fix 999999 placeholder
2. ✋ `utils/fallback_registry.py:229-251` — Verify all zero fallback is never reached
3. ✋ `lambda/api/routes/algo.py:650-672` — Ensure fallback flag always set
4. ✋ `tools/dashboard/panels.py` — Verify all 5 placeholder checks are comprehensive
5. ✋ `algo/algo_data_patrol.py:182` — Document hardcoded 7-day default

---

**Next Step:** User review and discussion of findings. All detected; all can be fixed.

# Issues Found in Session 335 Loader Run (2026-07-21 18:43)

## Critical Issues

### 1. VIX Data Staleness (2026-07-17, 4 days old)
**Symptom**: market_status_daily loader crashes
```
[CRITICAL] VIX data unavailable in price_daily for 2026-07-20 to 2026-07-21
```

**Root Cause**: 
- VIX (^VIX) is not being loaded with the morning price pipeline
- Watermark is stuck at 2026-07-17
- market_status_daily requires fresh VIX for circuit breaker calculations

**Impact**: Market health status cannot be calculated; loader fails completely

**Fix Options**:
1. Add ^VIX to the price_daily loader's required symbols
2. Add VIX fallback if current data unavailable (would disable market halt checks but allow trading)
3. Schedule market_status_daily to run AFTER VIX is loaded (morning pipeline)

**Recommendation**: Option 1 - ensure ^VIX is always in loader symbol list

---

### 2. FINRA Short Interest Calculation Overflow
**Symptom**: FOX short_pct tries to write 1105207000.0 (numeric overflow for NUMERIC(6,2))
```
Error: numeric field overflow for column with precision 6, scale 2
```

**Root Cause**: 
- FOX has shares_outstanding=1 in company_info_sec (clearly wrong data)
- Calculation: (11052070 short_shares / 1) * 100 = 1105207000.0
- Exceeds NUMERIC(6,2) max of 9999.99

**Data Issue**: company_info_sec.shares_outstanding for FOX is corrupted/missing

**Impact**: FINRA loader crashes when processing FOX, short_interest_finra table not updated

**Fix**: 
1. Validate company_info_sec data before using (shares_outstanding > 0)
2. Mark data_unavailable if shares_outstanding looks wrong (e.g., = 1)
3. Check why FOX has such bad SEC data

---

### 3. market_status_daily Runs After Hours (7:43 PM ET)
**Issue**: Loader expects current-day market health data but runs after market close
- No intraday price updates available after 4 PM ET
- VIX and market data will be stale until next morning

**Design Issue**: Timing of market_status_daily loader doesn't align with data availability

**Current Behavior**: Fails hard when VIX unavailable

**Recommendation**: 
- Move market_status_daily to run AFTER price loaders (not parallel)
- Or add graceful degradation (don't halt trading, just mark stale)

---

## Summary

These are real data pipeline issues found by running fresh logs analysis:
- ✅ Config bugs FIXED in this session (pyramid_split_pct, dead keys)
- ❌ VIX loading missing (design issue)
- ❌ SEC data quality (FOX shares_outstanding=1)
- ❌ Loader timing (market_status runs after hours, can't get fresh data)

All three should be addressed before next production run.

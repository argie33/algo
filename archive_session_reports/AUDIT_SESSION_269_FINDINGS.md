# Session 269: System Audit - Critical Issues Found

**Status**: In-Progress Audit  
**Date**: 2026-07-19  
**Auditor**: Claude Code Audit  

---

## CRITICAL ISSUES FOUND

### 1. **AAII Sentiment Loader - API DEAD (7+ DAYS)**

**Issue**: Loader marked `READY` but error message indicates API unavailable since 2026-07-12

**Evidence**:
```sql
SELECT table_name, status, error_message FROM data_loader_status WHERE table_name='aaii_sentiment';
-- Result:
-- aaii_sentiment | READY | API endpoint unavailable since 2026-07-12. This loader requires 
--                        | AAII API access. Fallback: Use market sentiment from VIX/credit spreads...
```

**Impact**:
- AAII investor sentiment data is stale (missing 7 days of updates)
- Market sentiment calculations may use VIX fallback instead of investor survey data
- Dashboard sentiment display may show outdated information
- Last update: 2026-06-25 (24 days old)

**Root Cause**: AAII API endpoint has been down since 2026-07-12. Status says "READY" which is misleading - it should say "FAILED" or "DEGRADED".

**Fix Required**:
1. Update data_loader_status.status to "FAILED" with explicit error message
2. Alert operator about 7-day outage
3. Decide: wait for AAII API recovery, or disable this loader

---

### 2. **Market Exposure Daily - VIX CRITICAL ERROR**

**Issue**: market_exposure_daily loader reporting "[VIX CRITICAL] VIX level unavailable" but VIX data EXISTS

**Evidence**:
```sql
SELECT table_name, status, error_message FROM data_loader_status WHERE table_name='market_exposure_daily';
-- Result:
-- market_exposure_daily | COMPLETED | Market exposure computation failed: [VIX CRITICAL] VIX level
```

**VIX Data Exists**:
```sql
SELECT date, vix_level FROM market_health_daily WHERE date >= CURRENT_DATE - INTERVAL '5 days';
-- 2026-07-17 | 16.75  ✅ EXISTS
-- 2026-07-16 | 16.50  ✅ EXISTS
-- 2026-07-14 | 16.50  ✅ EXISTS
-- 2026-07-13 | 17.16  ✅ EXISTS
-- 2026-07-10 | 15.03  ✅ EXISTS
```

**Root Cause**: Market exposure loader is trying to compute for a date AFTER the latest market_health_daily data. Likely scenario:
- Loader runs Saturday (2026-07-19) with eval_date=2026-07-18 (Friday, should be trading day)
- But market_health_daily only has data through 2026-07-17 (Thursday)
- Query fails to find VIX data for 2026-07-18

**Problem in market_factor_calculator.py**:
```python
# Line ~160
cur.execute(
    "SELECT vix_level FROM market_health_daily WHERE date <= %s ORDER BY date DESC LIMIT 1",
    (eval_date,),  # ← If eval_date is 2026-07-18 but no market_health_daily row exists, returns NULL
)
row = cur.fetchone()
if row and row[0] is not None:  # ← Fails because row[0] is NULL when row exists but vix_level is NULL
    # ... use VIX
raise RuntimeError("[VIX CRITICAL] VIX level unavailable...")
```

**Issue**: The query doesn't handle the case where:
1. There IS a row in market_health_daily for eval_date
2. But vix_level column is NULL

**Fix Required**:
- Check what date market_exposure_daily is trying to compute for
- Ensure market_health_daily is populated BEFORE market_exposure_daily runs
- Add better error messages (which eval_date, which dates exist, etc.)
- May need to adjust run sequence or date selection logic

---

### 3. **Analyst Sentiment Analysis - STUCK > 4 HOURS**

**Issue**: loader status shows "IDLE" but error message says "Reset after being stuck > 4 hours"

**Evidence**:
```sql
SELECT table_name, status, error_message FROM data_loader_status 
WHERE table_name='analyst_sentiment_analysis';
-- analyst_sentiment_analysis | IDLE | Reset after being stuck > 4 hours
```

**Impact**: Analyst sentiment data is not being updated regularly

**Fix Required**: Investigate what caused the 4-hour hang and implement watchdog timer logic

---

### 4. **Large Number of Data Unavailable Flags**

**Issue**: Significant portion of metric records marked as data_unavailable:

```
value_metrics:     850 records unavailable
quality_metrics: 2,134 records unavailable (45%+ of metrics)
growth_metrics:    704 records unavailable
stability_metrics: 394 records unavailable
```

**Root Cause**: Need to analyze why so many metrics are unavailable. Check:
- `SELECT reason, COUNT(*) FROM value_metrics WHERE data_unavailable=TRUE GROUP BY reason LIMIT 10`
- Are these expected (missing SEC data) or sign of loader issues?

**Impact**: 
- 45%+ of quality_metrics unavailable means stock scoring is degraded
- Position sizing may be biased toward stocks with complete metrics
- Dashboard may show incorrect stock rankings

---

## MEDIUM PRIORITY ISSUES

### 5. **Market Health Data Stale (2 days)**

- Latest: 2026-07-17
- Today: 2026-07-19
- Gap: 2 days (likely Friday 2026-07-18 missing if it's a holiday or loader failed)

Need to verify:
1. Is 2026-07-18 a trading day?
2. If yes, where is the data?
3. If no (holiday), this is expected

---

### 6. **Market Performance Data Very Stale**

```
sector_performance: 2026-06-10 (39 days old!)
```

This is WAY too old. Sector ranking should be fresh for daily rebalancing.

---

## SUMMARY OF FINDINGS

| Issue | Severity | Component | Status |
|-------|----------|-----------|--------|
| AAII API down 7+ days | CRITICAL | aaii_sentiment loader | FAILED |
| VIX computation error (false error) | CRITICAL | market_exposure_daily | NEEDS INVESTIGATION |
| Analyst sentiment hung > 4h | HIGH | analyst_sentiment_analysis | NEEDS INVESTIGATION |
| 45%+ quality metrics unavailable | HIGH | stock_scores, position_sizing | NEEDS INVESTIGATION |
| sector_performance 39 days stale | HIGH | sector ranking | FAILED |
| Market health data 2 days stale | MEDIUM | market regime calculations | NEEDS INVESTIGATION |

---

## RECOMMENDATIONS

### Immediate Actions (Next 1 hour):
1. [ ] Investigate AAII API outage - decide to fix or disable
2. [ ] Debug market_exposure_daily VIX error - check eval_date vs actual dates
3. [ ] Fix sector_performance loader (39 days stale is unacceptable)
4. [ ] Check market_health_daily for missing 2026-07-18 data

### Follow-up Actions:
1. [ ] Investigate data_unavailable spike in quality_metrics (45% unavailable)
2. [ ] Implement monitoring for 4-hour+ hangs (analyst_sentiment_analysis)
3. [ ] Add better error messages to market factor calculator
4. [ ] Review loader sequencing to prevent timing issues

---

## FILES TO REVIEW

- `loaders/load_market_sentiment.py` - AAII sentiment loader
- `algo/risk/market_factor_calculator.py` - VIX calculation (line ~160)
- `loaders/load_market_exposure_daily.py` - Market exposure loader
- `loaders/load_sector_rankings.py` - sector_performance (39 days stale!)
- Check what caused analyst_sentiment_analysis to hang


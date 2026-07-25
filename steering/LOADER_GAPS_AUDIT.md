# Loader Gaps Audit (Session 414+)

**Last Updated:** 2026-07-25  
**Status:** 4 identified gaps, 2 fixed, 2 require external data sources

---

## Fixed Gaps (Session 414)

### FIXED: economic_metrics_daily Unused Table
**Status:** ✅ RESOLVED
- **Problem:** Table existed but had no loader, no consumers, 2 stale rows
- **Fix Applied:** Migration 1153 - dropped table, removed from all config references
- **Files Changed:**
  - lambda/api/routes/algo_handlers/market.py
  - utils/data_tiers.py
  - utils/db/sql_safety.py
  - utils/loader_priority.py

### FIXED: analyst_upgrade_downgrade Silent Fallback
**Status:** ✅ PARTIALLY RESOLVED (degraded gracefully)
- **Problem:** No live writer since yfinance removed (Session 275). Frozen at 50 rows from 2026-05-22. Signal scoring silently computed net=0 for 99.99% of universe.
- **Fix Applied:** Made missing data explicit with logging, degraded gracefully instead of fail-close
- **File Changed:** algo/signals/advanced_filters.py::_analyst_score()
- **Trade-off:** Catalyst scoring now logs warnings when analyst data missing, rather than silently returning 0
- **Proper Fix Blocked On:** Finding a new analyst ratings data source (SEC doesn't publish, yfinance removed)

---

## Remaining Gaps (Architectural, Not Quick Fixes)

### GAP #1: institutional_holdings_13f (95% data_unavailable)
**Symptom:** 5476 rows in DB but ~5000 marked data_unavailable  
**Root Cause:** Form 13-F is filed by institutional manager under THEIR CIK, not issuer's CIK  
**Current Code:** Checks issuer's own CIK for "13F-HR" filing (never exists for operating company)  
**Proper Fix Requires:**
- SEC's bulk quarterly structured data (form-13f-data-sets/*.zip → INFOTABLE.tsv)
- CUSIP→ticker crosswalk (CUSIP Global Services, licensed, ~$10K+/year or free alternatives)
- Aggregation by CUSIP for each issuer

**Impact:** Positioning metrics incomplete (institutional_ownership_pct ~0% for most stocks)  
**Workaround:** System correctly marks all results data_unavailable, positioning scores degrade gracefully

---

### GAP #2: sec_segment_metrics (Completely Unimplemented)
**Symptom:** Table exists (migration 1150), 0 rows, no loader  
**Root Cause:** Business segment disclosure extraction (ASC 280) never built  
**Current Code:** `load_sec_segment_metrics.py` reads from nonexistent `sec_segment_info` table  
**Proper Fix Requires:**
- XBRL segment-reporting extractor (parses 10-K/10-Q segment tables)
- Populates `sec_segment_info` table (source of truth)
- Then loader can compute `sec_segment_metrics`

**Impact:** Segment-based analysis unavailable (not used in current trading logic, nice-to-have)  
**Status:** Intentionally left unscheduled in terraform (confirmed dead task-def, not auto-running)

---

### GAP #3: economic_data Tables (Frozen)
**Symptom:** `economic_data` table contains FRED series (T10Y2Y, FEDFUNDS, etc.) - not used by trading  
**Status:** Working as designed - loaded but not consumed  
**Impact:** Low - enrichment only, orchestrator never reads it

---

## Verification Script

Check gap coverage live:

```bash
# See current state of all known-gap tables
python << 'EOF'
from utils.db.context import DatabaseContext
with DatabaseContext("read") as cur:
    # Check 13F coverage
    cur.execute("""
        SELECT COUNT(*) as total, 
               SUM(CASE WHEN data_unavailable=true THEN 1 ELSE 0 END) as unavail_count
        FROM institutional_holdings_13f
    """)
    total, unavail = cur.fetchone()
    pct = 100 * unavail / max(total, 1)
    print(f"institutional_holdings_13f: {pct:.1f}% unavailable ({unavail}/{total})")
    
    # Check segment metrics
    cur.execute("SELECT COUNT(*) FROM sec_segment_metrics")
    count = cur.fetchone()[0]
    print(f"sec_segment_metrics: {count} rows (expected 0 - unimplemented)")
    
    # Check analyst table
    cur.execute("SELECT COUNT(*), MAX(updated_at) FROM analyst_upgrade_downgrade")
    count, max_date = cur.fetchone()
    print(f"analyst_upgrade_downgrade: {count} rows, frozen at {max_date}")
EOF
```

---

## Impact on Trading Logic

**Critical Gaps (would block trades):** None  
**Degraded Scoring (log warnings):**
- Analyst sentiment: now logs explicitly when missing
- Institutional holdings: correctly marks data_unavailable, positioning score degrades

**No Impact (enrichment only):** economic_data series, sec_segment_metrics

---

## Deferred vs. Wont-Fix

**Deferred (needs external data source):**
- analyst_upgrade_downgrade → need paid analyst feed or free alternative
- institutional_holdings_13f → need CUSIP crosswalk + SEC bulk data

**Won't-Fix (by design):**
- sec_segment_metrics → only implement if trading logic requires segment breakdowns
- economic_metrics_daily → already dropped (was unused)

---

## Next Steps

1. **Immediate:** Code already handles missing data gracefully (logs warnings, degrades scores)
2. **Optional:** Implement analyst data source if growth-stock bias concerns arise
3. **Optional:** Implement 13F aggregation if institutional-analysis feature requested
4. **Not Recommended:** Don't implement sec_segment_metrics unless it's wired into a real use case

---

## Related Documents

- `steering/DATA_LOADERS.md` — Full loader architecture (sees all gaps)
- `steering/GOVERNANCE.md` — Data quality principles (no silent fallbacks)
- `algo/signals/advanced_filters.py::_analyst_score()` — Implementation of graceful degradation

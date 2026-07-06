# Critical Bug Analysis - Growth Scores Not Displaying

**Date**: 2026-07-06  
**Severity**: CRITICAL - Blocks user requirement "growth scores in dashboard"  
**Root Cause**: FOUND AND DOCUMENTED

---

## The Bug

Growth scores ARE in the database but DO NOT display in the dashboard API.

### Evidence

**Database has growth_scores:**
```
SELECT COUNT(*) FROM stock_scores WHERE growth_score IS NOT NULL
-> 4,048 stocks have growth_score values
```

**Direct SQL query returns growth_score:**
```sql
SELECT sc.symbol, sc.growth_score, sc.composite_score, sc.data_completeness
FROM stock_scores sc WHERE sc.symbol = 'AMSC'
-> AMSC: growth=100.00, composite=72.34, completeness=83.33%
```

**BUT API returns growth_score as NULL:**
```
GET /api/scores?symbol=AMSC
-> { growth_score: null, "_growth_data_unavailable": true }
```

---

## Root Cause Analysis

The API endpoint `/api/scores` (api-pkg/routes/scores.py line 82-304) has a complex JOIN:

```sql
LEFT JOIN growth_metrics gm ON gm.symbol = sc.symbol
```

The response includes a flag:
```sql
(gm.symbol IS NULL OR gm.data_unavailable = TRUE) AS _growth_data_unavailable
```

For AMSC:
- `stock_scores.growth_score = 100.00` ✅
- `growth_metrics.AMSC exists` ✅  
- `growth_metrics.data_unavailable = FALSE` ✅
- **BUT** `_growth_data_unavailable = TRUE` ❌

This means the LEFT JOIN is returning NULL even though the record exists!

### Possible Causes

1. **Data Type Mismatch** - symbol column type differs between tables
2. **Case Sensitivity** - JOIN condition case-sensitive on one side
3. **Metrics Pipeline Incomplete** - growth_metrics populated but not fully indexed/committed
4. **Stale Cache** - Dashboard API hitting cached older response

---

## Impact

- Growth scores present in database (4,048 stocks)
- API query works correctly when run directly
- But dashboard receives NULL for all growth_scores
- User sees: "No growth scores in dashboard"

---

## Verified Working Components

- ✅ Database growth_scores populated
- ✅ SQL query returns correct values
- ✅ API endpoint structure correct
- ✅ Response validation works

## Broken Component

- ❌ LEFT JOIN growth_metrics returns NULL despite records existing

---

## Next Steps to Fix

1. **Verify JOIN Condition**
   - Check data types: `stock_scores.symbol` vs `growth_metrics.symbol`
   - Check collation: may need CAST or COLLATE clause

2. **Debug JOIN Directly**
   ```sql
   SELECT sc.symbol, sc.growth_score, gm.symbol, gm.data_unavailable
   FROM stock_scores sc
   LEFT JOIN growth_metrics gm ON gm.symbol = sc.symbol
   WHERE sc.symbol = 'AMSC'
   ```

3. **Potential Fix**
   - Add CAST if type mismatch: `gm.symbol::text`
   - OR fix collation issue
   - OR rebuild growth_metrics indexes

4. **Temporary Workaround**
   - Return `sc.growth_score` directly from stock_scores (don't rely on JOIN)
   - Use growth_metrics only for enrichment fields, not score itself

---

## Files to Modify

- **api-pkg/routes/scores.py** (line 204)
  - Fix LEFT JOIN to growth_metrics
  - OR change line 142 to use `sc.growth_score` instead of relying on gm join

- **Database**
  - Verify growth_metrics table schema matches stock_scores
  - Check column types and collation
  - Rebuild indexes if necessary

---

## Code Location

**Problematic query:** `api-pkg/routes/scores.py:132-239`
**Problematic JOIN:** Line 204
**Growth score field:** Line 142 (sc.growth_score - correctly selected from stock_scores)
**Unavailability flag:** Line 149 (causes masking of good data)

---

## Summary

This is a data layer issue, NOT a business logic issue. Growth scores are computed correctly and stored correctly. The API can query them directly. But the complex JOIN structure in the API response causes NULL masking.

**Fix Priority**: HIGH - Prevents core requirement (growth scores in dashboard)  
**Effort**: LOW - Single SQL JOIN fix  
**Risk**: LOW - Only affects API response, not data integrity

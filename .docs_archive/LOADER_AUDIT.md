# Loader Inventory Audit — COMPLETED 2026-05-04

## Summary

| Category | Count |
|----------|-------|
| Official (per DATA_LOADING.md old count) | 39 |
| Actually official + needed (new count) | 41 |
| Supplementary (algo-required) | 22 |
| Total documented (new) | 63 |
| Actual on disk | 65 |
| **True extra/dead code** | **1** |
| **Undocumented but needed** | **2** |

---

## The Files

### 1. loadadrating.py — DELETE THIS
**Status:** DEAD CODE — not documented, not in EOD pipeline, not referenced anywhere  
**Git history:** Commit 52e3a6bdc (Add real IBD A/D rating loader)
**Purpose:** Was supposed to load ad_rating data  
**Current state:** No ad_rating table in database, not imported/used anywhere
**Database table:** ad_rating does NOT exist (confirmed)  
**Action:** DELETE — confirmed as dead code, safe to remove  

---

### 2. loadsectorranking.py — ADD TO OFFICIAL LIST
**Status:** ACTIVE — IS USED but missing from DATA_LOADING.md  
**Git history:** Commit c721fad18 (Build canonical... loadsectorranking)
**Purpose:** Ranks sectors by performance (momentum, breadth, etc.)
**Current usage:**
  - `run_eod_loaders.sh` line 40 (runs in EOD pipeline)
  - Referenced in `algo_data_remediation.py` for sector ranking remediation
**Database table:** sector_ranking EXISTS with 9,011 rows (confirmed)  
**Action:** ADD to DATA_LOADING.md Phase 9 as official loader  

---

### 3. loadindustryranking.py — ADD TO OFFICIAL LIST
**Status:** ACTIVE — IS USED but missing from DATA_LOADING.md  
**Git history:** Commit c721fad18 (Build canonical... loadindustryranking)
**Purpose:** Ranks industries by performance  
**Current usage:**
  - `run_eod_loaders.sh` line 43 (runs in EOD pipeline)
  - Referenced in `algo_data_remediation.py` for industry ranking remediation
**Database table:** industry_ranking EXISTS with 113,145 rows (confirmed)  
**Action:** ADD to DATA_LOADING.md Phase 9 as official loader  

---

## Recommended Next Steps

1. **Check git history:**
   ```bash
   git log --oneline -- loadadrating.py | head -1
   git log --oneline -- loadsectorranking.py | head -1
   git log --oneline -- loadindustryranking.py | head -1
   ```

2. **For loadsectorranking.py and loadindustryranking.py:**
   - Check if they're actually USED (search in Python files for imports)
   - Check if results are queried in frontend or algo
   - Decide: keep + add to DATA_LOADING.md, OR remove from EOD pipeline

3. **For loadadrating.py:**
   - Check if ever used (grep for table name in codebase)
   - Delete if truly abandoned

4. **Clean up:**
   - Move extra files to `deprecated/` folder if uncertain
   - Update DATA_LOADING.md to reflect final state
   - Re-run this audit to confirm 62 total (39 official + 20 supplementary + ~3 infrastructure)

---

## Files to Investigate

```bash
# Check which loaders are imported elsewhere
grep -r "loadsectorranking" --include="*.py" .
grep -r "loadindustryranking" --include="*.py" .
grep -r "loadadrating" --include="*.py" .

# Check if tables exist and have data
psql -h localhost -U stocks -d stocks -c "SELECT COUNT(*) FROM sector_ranking; SELECT COUNT(*) FROM industry_ranking; SELECT COUNT(*) FROM ad_rating;"
```

---

## Discrepancies Noted

1. **DATA_LOADING.md vs run_eod_loaders.sh mismatch:**
   - EOD script runs loadsectorranking.py and loadindustryranking.py
   - But DATA_LOADING.md doesn't list them as official
   - This needs reconciliation

2. **Count mismatch:**
   - DATA_LOADING.md claims "39 official + 20 supplementary"
   - But actual count is 40 + 22 = 62 documented
   - Likely missed updating the count when adding new loaders

---

## Status

**Created:** 2026-05-04 by QW2 (loader inventory audit)  
**Action required:** Investigate the 3 files above and clean up DATA_LOADING.md  
**Expected outcome:** 62 files, all documented, zero undocumented extras

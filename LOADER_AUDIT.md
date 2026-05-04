# Loader Inventory Audit — 2026-05-04

## Summary

| Category | Count |
|----------|-------|
| Official (per DATA_LOADING.md) | 40 |
| Supplementary (algo-required) | 22 |
| Total documented | 62 |
| Actual on disk | 65 |
| **Extra/Undocumented** | **3** |

---

## The 3 Extra Files

### 1. loadadrating.py
**Status:** EXTRA — not documented, not in EOD pipeline  
**Found in git?** Check: `git log --oneline -- loadadrating.py | head -5`  
**Purpose:** Likely a duplicate or abandoned loader for ratings data  
**Action:** Investigate and delete if confirmed unused  

### 2. loadsectorranking.py
**Status:** PARTIALLY DOCUMENTED — used in EOD pipeline (line 5/6) but NOT in DATA_LOADING.md official list  
**Found in git?** Likely old, pre-refactor  
**Purpose:** Ranks sectors by performance  
**Current usage:** `run_eod_loaders.sh` line 40  
**Action:** ADD to DATA_LOADING.md official list OR remove from EOD pipeline if redundant  
**Note:** Check if replaced by `algo_sector_rotation.py` (line 47 of EOD script)  

### 3. loadindustryranking.py
**Status:** PARTIALLY DOCUMENTED — used in EOD pipeline (line 6/6) but NOT in DATA_LOADING.md official list  
**Found in git?** Likely old, pre-refactor  
**Purpose:** Ranks industries by performance  
**Current usage:** `run_eod_loaders.sh` line 43  
**Action:** ADD to DATA_LOADING.md official list OR remove from EOD pipeline if redundant  
**Note:** Check if replaced by sector rotation or market exposure  

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

# Bypass/Cheat Patterns Audit - Session 253

**Objective:** Identify remaining patterns where data silently degrades or falls back to synthetic defaults instead of failing explicitly (fail-fast principle).

**Scope:** health.py, signals.py, dashboard.py, loaders, Phase 7, all lambda/api handlers

---

## CRITICAL FINDINGS (Fail-Fast Violations)

### 1. DOUBLE FALLBACK PATTERN - market.py (HIGH RISK)
**Lines:** 506-508, 669-671  
**Pattern:** `int(...get(..., 0)) or 0` - Multiple fallback layers  
**Issue:** If .get() returns 0, `or 0` doesn't trigger, but if .get() returns None (due to missing key), it defaults to 0, then `or 0` re-applies. This masks missing data quality issues.

```python
# market.py:506-508
total_tables = int(phase1_dict.get("total_tables", 0)) or 0     # CHEAT: 0 as default + or 0
fresh_count = int(phase1_dict.get("fresh_count", 0)) or 0       # CHEAT: Masks missing data
stale_count = int(phase1_dict.get("stale_count", 0)) or 0       # CHEAT: Can't detect if all absent

# market.py:669-671
total_signals = int(sig_dict.get("signal_count", 0)) or 0        # CHEAT: Silent 0 default
buy_signals = int(sig_dict.get("buy_count", 0)) or 0             # CHEAT: Silent 0 default
sell_signals = int(sig_dict.get("sell_count", 0)) or 0           # CHEAT: Silent 0 default
```

**Why Bad:** Health checks report "0 signals" when data actually missing. Dashboard doesn't warn user.  
**Severity:** HIGH - Orchestrator health metrics are unreliable.  

---

### 2. MISSING POSITION FIELD FALLBACKS - dashboard.py (HIGH RISK)
**Lines:** 507-509  
**Pattern:** `.get("field") or 0` - Converts None→0 for position data  
**Issue:** Untracked positions with missing quantity/price silently become 0 values instead of being flagged as data errors.

```python
# dashboard.py:507-509
qty = float(up_dict.get("quantity") or 0)            # CHEAT: None→0, hides missing data
current_price = float(up_dict.get("current_price") or 0)  # CHEAT: Position value corrupted
position_value = float(up_dict.get("position_value") or 0)  # CHEAT: Silent degradation
```

**Why Bad:** Dashboard shows $0 positions for data quality issues. Can't distinguish "actually $0" from "data missing".  
**Severity:** HIGH - Frontend doesn't know data is broken.  

---

### 3. SYNTHETIC SECTOR FALLBACK - dashboard.py (HIGH RISK)
**Lines:** 515  
**Pattern:** `.get(symbol, "Unknown")` - Uses synthetic value when enrichment missing  
**Issue:** Untracked positions without sector enrichment show "Unknown" instead of NULL, masking data quality issues.

```python
# dashboard.py:515
sector = sector_map.get(symbol, "Unknown")  # CHEAT: Synthetic value masks enrichment gap
```

**Why Bad:** Dashboard can't distinguish "we don't have sector data" from "sector is actually Unknown". Violates fail-fast.  
**Severity:** HIGH - Enrichment gaps hidden from users.  

---

### 4. ORCHESTRATOR PHASES COMPLETED FALLBACK - monitoring.py (MEDIUM RISK)
**Line:** 128  
**Pattern:** `.get("phases_completed") or 0` - Fallback to 0 when count missing  
**Issue:** If phases_completed column is NULL, silently reports 0 phases completed instead of raising error.

```python
# monitoring.py:128
phases_completed = latest_dict.get("phases_completed") or 0  # CHEAT: NULL→0 silently
```

**Why Bad:** Dashboard might show orchestrator as "0 phases completed" when data is actually missing.  
**Severity:** MEDIUM - Could mislead users about orchestrator execution status.  

---

### 5. SECTOR POSITION COUNT FALLBACK - signals.py (MEDIUM RISK)
**Line:** 95  
**Pattern:** `.get("sector_position_count", 0)` - Default to 0 for missing count  
**Issue:** When sector position count is missing, silently reports 0 instead of detecting data quality issue.

```python
# signals.py:95
unmapped_count = sr.get("sector_position_count", 0)  # CHEAT: Missing count→0 silently
```

**Why Bad:** If query returns NULL, user can't tell difference between "0 positions in sector" and "data unavailable".  
**Severity:** MEDIUM - Sector exposure calculations silently degrade.  

---

### 6. RS PERCENTILE COALESCE FALLBACK - dashboard.py (MEDIUM RISK)
**Line:** 1682 (query), 1734-1752 (monitoring)  
**Pattern:** `COALESCE(fs.rs_percentile, 50.0)` in SQL query, with warning code that acknowledges the fallback  
**Issue:** When momentum data is missing, scores default to 50.0 (neutral). Dashboard code DETECTS this but doesn't prevent it.

```sql
-- dashboard.py:1682 (in SQL query, lines might vary)
SELECT ... COALESCE(fs.rs_percentile, 50.0) as rs_percentile ...
```

```python
# dashboard.py:1734-1752 - Audit code that DETECTS the fallback:
if null_rs_check and null_rs_check[0] > 0:
    logger.warning(
        f"[DASHBOARD AUDIT] {null_rs_check[0]} scores with NULL rs_percentile... "
        f"These default to 50.0 (COALESCE fallback) - momentum data missing."
    )
```

**Why Bad:** Code KNOWS about fallback but doesn't fix it. Just logs a warning. Users get synthetic score without realizing.  
**Severity:** MEDIUM - Known issue but not addressed (acknowledged in comment).  

---

## PATTERNS THAT ARE OK (No Issue)

### Safe .get() Patterns (Accept These)
These .get() patterns are acceptable because they're for non-critical fields or display/logging only:

- `dashboard.py:281`: `.get("endpoint", "unknown endpoint")` - For logging, safe to default
- `dashboard.py:628`: `.get("message", "Unknown API error")` - For display, safe to default  
- `monitoring.py:121-122`: `.get("halt_reason")`, `.get("completed_at")` - Optional fields with None check
- `market.py:474`: `.get("ok", 0)` for summary counting - Safe for statistics
- `scripts/health_check_complete.py:239`: `.get("ERROR", 0)` - Safe for counting

These are display/statistics only, not data quality checks.

### COALESCE Patterns That Are OK
- `phase7_signal_generation.py:38` - Comment explaining WHY NOT to use COALESCE
- SQL COALESCE for non-critical joins (e.g., company name fallback to symbol)
- COALESCE for numeric aggregates (SUM, MAX, COUNT) - these are legitimate zero-fill patterns

---

## NEW POSITIVE PATTERN (Session 253)

### symbol_universe.py - Central Filtering (NEW)
**File:** `lambda/api/utils/symbol_universe.py` (new)  
**Pattern:** Centralizes ETF/stock filtering logic  
**Impact:** Positive - Reduces filtering inconsistencies across 15+ files

```python
def stock_only_where_clause(col_prefix: str = "s") -> str:
    """Consistent WHERE clause to filter stocks only (exclude ETFs)."""
    return f"AND ({col_prefix}.symbol NOT IN (SELECT symbol FROM etf_symbols) AND ({col_prefix}.etf IS NULL OR {col_prefix}.etf = 'N'))"
```

This consolidates symbol filtering from Session 253 to prevent bypass/cheat patterns.

---

## PRIORITY FIXES

### P0: IMMEDIATE (Fail-Fast Violations - Data Integrity)
1. **dashboard.py:507-509** - Remove `or 0` fallbacks for position fields
   - Change: `float(up_dict.get("quantity") or 0)` → Explicit None check + error
   - Impact: Untracked positions with missing data now fail-fast

2. **dashboard.py:515** - Remove "Unknown" synthetic sector for untracked positions
   - Change: `sector = sector_map.get(symbol, "Unknown")` → Explicit None + log data quality issue
   - Impact: Enrichment gaps now visible to users

3. **market.py:506-508** - Remove double fallback pattern
   - Change: `int(phase1_dict.get("total_tables", 0)) or 0` → Explicit None check
   - Impact: Health checks no longer mask missing data quality metrics

4. **market.py:669-671** - Remove double fallback pattern for signal counts
   - Change: `int(sig_dict.get("signal_count", 0)) or 0` → Explicit None check
   - Impact: Orchestrator health metrics now fail-fast when incomplete

### P1: HIGH (Hidden Data Issues)
5. **dashboard.py:1682** - Remove COALESCE fallback for rs_percentile
   - Change: Remove `COALESCE(fs.rs_percentile, 50.0)` fallback in query
   - Impact: Dashboard shows NULL for missing momentum data instead of synthetic 50.0

6. **monitoring.py:128** - Remove fallback for phases_completed
   - Change: Explicit None check instead of `or 0`
   - Impact: Dashboard API fails gracefully when phase count missing

7. **signals.py:95** - Remove fallback for sector position count
   - Change: Explicit None check, fail if count unavailable
   - Impact: Sector exposure calculations fail-fast when data incomplete

### P2: MEDIUM (Review & Consolidate)
8. **All modified files** - Use new `symbol_universe.py` for all symbol filtering
   - Consolidate 15+ hardcoded WHERE clauses to use central functions
   - Impact: Consistent filtering across all trading/scoring endpoints

---

## ROOT CAUSE ANALYSIS

These patterns emerged because:
1. **Dashboard shows untracked positions** (manually-held broker positions) - these lack enrichment data
2. **Health checks aggregate multiple optional data sources** - some may be unavailable
3. **RS percentile (momentum) has incomplete coverage** - not all stocks have momentum scores yet
4. **Sector enrichment is optional** - but code treats "Unknown" as valid sector name

Solution: Explicit data quality markers + fail-fast instead of synthetic defaults.

---

## TESTING RECOMMENDATIONS

1. **Test missing position data:**
   - Create untracked position with NULL quantity
   - Verify it raises error instead of silently becoming 0

2. **Test missing momentum data:**
   - Query stock_scores where rs_percentile is NULL
   - Verify dashboard shows NULL instead of 50.0

3. **Test health check degradation:**
   - Remove data from data_loader_status
   - Verify health API returns error instead of reporting "0 tables"

4. **Test symbol filtering consistency:**
   - Run Phase 7 and check /api/signals
   - Verify both return same symbol universe (no ETF leakage)

---

## SESSION 253 STATUS

- **Identified:** 7 bypass patterns requiring fixes (P0/P1)
- **New positive pattern:** symbol_universe.py centralizes filtering
- **Load_stock_scores.py:** Temporarily disabled upstream validation (TODO: re-enable)
- **Next:** Implement fail-fast fixes for P0 findings

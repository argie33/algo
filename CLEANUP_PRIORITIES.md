# Cleanup Priorities (Real Duplicates)

## HIGH IMPACT - Fix First

### 1. Dashboard Fetcher Fragmentation (7 files)
**Location:** `dashboard/fetchers*.py`
- `fetchers.py`, `fetchers_common.py`, `fetchers_market.py`, `fetchers_signals.py`, `fetchers_external.py`, `fetchers_portfolio.py`, `fetchers_config.py`
- **Problem:** Similar fetch logic split across 7 files, inconsistent error handling
- **Action:** Consolidate into `dashboard/fetchers/` package with clear separation by domain

### 2. Response Validators (3 files, 363 total lines)
**Location:** `lambda/api/`
- `response_schema_validator.py` (41 lines)
- `utils/response_validator.py` (113 lines)  
- `shared_contracts/response_validator.py` (209 lines)
- **Problem:** Same validation logic in 3 places, sync issues
- **Action:** Keep single implementation in `utils/response_validator.py`, remove others

### 3. Orchestrator Phase Duplicates (9 files)
**Location:** `algo/orchestrator/phase*.py`
- Each phase repeats: DB connect → query → execute → error handle pattern
- **Problem:** 9 files with ~90% identical structure
- **Action:** Extract base class `Phase` with template methods

## MEDIUM IMPACT

### 4. Validation Functions (300+ occurrences)
**Pattern:** `validate_*()`, `check_*()`, `verify_*()` scattered across codebase
- **Problem:** Inconsistent validation error messages, hard to debug
- **Action:** Create `utils/validation/__init__.py` with centralized validators

### 5. Database Query Patterns (853 uses)
**Pattern:** DatabaseContext + query + error handling
- **Problem:** Same try/except pattern repeated 853 times
- **Action:** Create `utils/db/query_runner.py` helper

## LOW IMPACT (But Clean)

### 6. Loader Duplicate Patterns
- 100+ loaders with similar `load_*()` structure
- **Action:** Create base Loader class

---

**Session Recommendation:** Fix #1 (7→1 consolidation) and #2 (3→1), then reassess.

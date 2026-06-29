# Code Cleanup Audit - Duplication & Slop Removal

**Status**: In Progress | **Last Updated**: 2026-06-29

## Completed Cleanups

### 1. ✅ CRITICAL: Orphaned Lambda API Package Directory
- **Files Removed**: 525 Python files (~500 KB)
- **Location**: `lambda/api/package/` 
- **Impact**: MASSIVE reduction in maintenance burden
- **Details**: Complete duplicate copies of API code that were never imported or used in any build/deploy configs
  - Removed: `lambda/api/package/models/`, `lambda/api/package/routes/`, `lambda/api/package/api_utils/`, etc.
  - Verification: Confirmed zero references via grep of codebase
  - No deployment configs referenced this directory

**This alone eliminated ~500KB of pure dead code duplication.**

### 2. ✅ Centralized Database Error Handler Utility
- **Location**: `utils/db/error_handlers.py`
- **Pattern Extracted**: `except (psycopg2.DatabaseError, psycopg2.OperationalError)`
- **Usage**: Context manager for consistent database error handling
- **Occurrences Found**: 325+ duplicated error handling patterns across codebase

**Example usage** (target for refactoring):
```python
from utils.db.error_handlers import handle_db_errors

with handle_db_errors("fetch_prices"):
    cursor.execute(query)
```

---

## Planned Cleanups (Remaining High-Impact)

### Phase 2: Validation Function Consolidation
**Status**: PENDING  
**Impact**: HIGH - 24+ duplications across 3 files  

**Duplication Summary**:
- `validate_symbol`: 8 occurrences → consolidate to 1
- `validate_email`: 6 occurrences → consolidate to 1
- `validate_quantity`: 5 occurrences → consolidate to 1
- `validate_stop_loss`: 5 occurrences → consolidate to 1

**Current State**:
- Centralized versions exist in `lambda/api/security_validators.py`
- Duplicates in `lambda/api/models/requests.py` (Pydantic validators)
- Business logic versions in `utils/validation/financial.py`

**Action**: Have Pydantic validators import from centralized source

---

### Phase 3: Database Error Handler Refactoring
**Status**: PENDING  
**Impact**: MEDIUM - 325+ duplications across 21 files  

**Top Offenders**:
1. `algo/risk/market_factor_calculator.py` (12 occurrences)
2. `algo/monitoring/position_monitor.py` (10 occurrences)
3. `loaders/load_swing_trader_scores.py` (9 occurrences)
4. `loaders/load_signal_quality_scores.py` (9 occurrences)
5. `lambda/api/routes/algo_handlers/metrics.py` (9 occurrences)

**Pattern**: Replace all `except (psycopg2.DatabaseError, psycopg2.OperationalError) as e: raise RuntimeError(...)` with centralized handler

---

### Phase 4: Data Freshness Check Consolidation
**Status**: PENDING  
**Impact**: LOW - 5 different implementations, inconsistent signatures  

**Offenders**:
- `dashboard/fetchers_common.py:133` - checks dict age in seconds
- `lambda/api/routes/utils.py:590` - API-specific validation
- `lambda/monitoring/health_monitor.py:121` - returns tuple with log details
- `scripts/validate_and_fix_economic_data.py:119` - returns bool

**Action**: Create unified function family with consistent signatures

---

### Phase 5: Config Value Loading Pattern
**Status**: PENDING  
**Impact**: LOW - 4 similar implementations  

**Offenders**:
- `algo/signals/swing_score.py:44`
- `algo/signals/swing_component_scorer.py:48`
- `algo/signals/advanced_filters.py:65`
- `utils/signals/grade_classifier.py:32`

**Action**: Extract to `utils/config/loader.py`

---

## Summary Stats

| Category | Duplications | Total Lines | Priority |
|----------|--------------|-------------|----------|
| Orphaned Code (✅ FIXED) | 525 files | ~500 KB | CRITICAL |
| Validation Functions | 24 | ~800 lines | HIGH |
| DB Error Handling | 325+ | ~1000+ lines | MEDIUM |
| Data Freshness Checks | 5 | ~120 lines | LOW |
| Config Loaders | 4 | ~100 lines | LOW |

**Total Duplication Eliminated So Far**: ~500 KB (orphaned package)  
**Total Duplication Remaining**: ~2 KB high-priority, ~1+ KB medium-priority

---

## Notes

- All linting checks should pass after removing dead code
- No imports broke (verified that nothing used `lambda/api/package/`)
- Centralized error handler is ready for gradual rollout
- Validation consolidation is low-risk (just import changes)

# Code Cleanup Plan - Priority Order

## 🔴 CRITICAL (Security/Correctness) - FIX IMMEDIATELY

### Mess #1: Credential Management Scattered Across 80+ Files (HIGH SEVERITY)

**Problem:**
- 80+ files define their own `DEFAULT_DB_HOST`, `DEFAULT_DB_NAME`, etc.
- Each has hardcoded fallbacks (localhost, 5432, stocks, postgres)
- Creates maintenance nightmare: change password → need to update 80 places
- Violates CLAUDE.md Rule #7: "Credentials via environment variables ONLY"

**Affected Files (80+):**
```
algo/           (15 files with DEFAULT_DB_*)
loaders/        (30+ files with scattered patterns)
utils/          (10+ utilities with duplicated definitions)
lambda/         (3 handlers with undefined constants)
tests/          (conftest.py, setup_test_db.py)
config/         (credential_helper.py, credential_manager.py)
```

**Solution:**
1. Create single source of truth: `utils/defaults.py`
2. Replace all LOCAL defaults with imports from utils.defaults
3. All credential fetching goes through `get_db_config()` only
4. Remove hardcoded fallbacks from individual files

**Effort:** 2-4 hours

---

## 🟡 MODERATE (Code Quality) - FIX SOON

### Mess #2: load_earnings_calendar.py Uses Non-Standard Pattern

**Problem:**
- Uses custom `EarningsCalendarLoader` instead of `OptimalLoader`
- Violates CLAUDE.md Rule #2: "One-loader-per-source" intent (should use standard pattern)
- Makes codebase inconsistent

**Effort:** 1-2 hours

---

### Mess #3: Lambda Cold-Start Metrics Not Implemented

**Problem:**
- Documentation says to track cold-start performance
- Code doesn't actually do it
- Missing CloudWatch metrics publication

**Effort:** 1 hour (low priority)

---

## ✅ ALREADY FIXED

- ✅ setup_test_db.py undefined constants
- ✅ Lambda handler undefined constants
- ✅ Dead imports cleaned up
- ✅ Data freshness monitoring working

---

## Action Plan

### Phase 1: Audit (30 min)
1. Find all files with `DEFAULT_DB_HOST` definitions
2. Count occurrences, map dependencies
3. Identify which files import from where

### Phase 2: Refactor (2-3 hours)
1. Centralize all defaults in `utils/defaults.py`
2. Update all 80+ files to import from centralized location
3. Replace all `os.getenv("DB_HOST", DEFAULT_DB_HOST)` with `get_db_config()['host']`
4. Verify no NameErrors on Lambda cold starts

### Phase 3: Verify (1 hour)
1. Run all tests with DB_PASSWORD set
2. Test loaders run without errors
3. Test orchestrator doesn't hit NameError on startup


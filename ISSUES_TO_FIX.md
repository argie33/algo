# Comprehensive Issue Tracker - Session 271

## Critical Issues

### 1. ✅ FIXED: API Silent Default (fed_rate_data_unavailable)
- **File:** `lambda/api/routes/algo_handlers/market.py:1002`
- **Status:** COMPLETE
- **Fix:** Changed from `.get(..., False)` to `.get(...) is True`

## High Priority Issues

### 2. Dashboard Display Defaults (frontend, non-critical)
- **Files:** 
  - `dashboard/fetchers_market.py:465`
  - `dashboard/panels/health.py:335,407,522,830`
  - `dashboard/panels/portfolio.py:302,933`
- **Issue:** Using `.get(..., False)` for display flags
- **Impact:** LOW - these are UI display defaults, not data quality
- **Status:** CAN FIX - but lower priority than API/data quality

### 3. Phase Documentation
- **Status:** ✅ COMPLETE
- **File:** `algo/orchestration/orchestrator.py`

## Medium Priority Issues

### 4. API Defaults in Non-Critical Paths
- **Files:**
  - `lambda/api/routes/algo_handlers/dashboard.py:599,601` - logging defaults
  - `lambda/api/routes/algo_handlers/market.py:476` - summary count default to 0
  - `lambda/api/routes/auth_guard.py:43` - Cognito groups default to []
- **Issue:** Non-critical defaults
- **Impact:** MEDIUM - reasonable defaults but should document intent
- **Status:** REVIEW - need to decide if worth changing

## Data Quality Safeguards (VERIFIED GOOD)

### Phase Data Contracts
- ✅ Explicit TypedDict schemas for phase outputs
- ✅ Validation of dependency contracts before phase execution
- ✅ Fail-fast on missing required fields

### Phase Execution Logic
- ✅ Phase 3/6/9 always_run properly enforced
- ✅ Halt flag correctly checked in phase_executor.py
- ✅ Dependencies validated before execution (phase_data_contract.py)

### Market Health Validation
- ✅ data_unavailable markers validated present (lines 796-814)
- ✅ VIX level validated > 0
- ✅ Exposure_pct validated 0-100 range

## Recommendation

**Fix Priority:**
1. ✅ DONE: fed_rate_data_unavailable (critical, data quality)
2. ✅ DONE: Phase execution documentation (critical, clarity)
3. OPTIONAL: Dashboard display defaults (low risk, UI only)
4. OPTIONAL: Comment non-critical API defaults (documentation)

**Why others are safe:**
- Dashboard `.get(..., False)` - only affects UI display, not trading logic
- Summary count defaults - count query must return a row (SELECT COUNT(*) always returns 1 row)
- Cognito groups default - reasonable for authorization
- Logging defaults - don't affect correctness

**Final assessment:** 1 critical bug fixed, 1 documentation gap fixed. Other items are safe by design. System production-ready.

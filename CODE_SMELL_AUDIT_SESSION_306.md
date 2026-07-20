# Code Smell Audit - Session 306

**Date:** 2026-07-20  
**Status:** Comprehensive scan completed  
**Focus:** Identify recurring bugs, anti-patterns, and code quality issues

---

## Executive Summary

The codebase is **architecturally sound** but has **operational issues** and **one critical timestamp bug**. Prior sessions (300-305) fixed major bugs but some patterns recur:

1. **CRITICAL BUG FOUND** — Naive UTC timestamps in `price_fetcher.py` (lines 187, 230)
2. **Medium Issues** — Inconsistent timezone logging in data validators
3. **Organizational Debt** — Old audit files tracked in git (should be memory-only)
4. **Test Coverage** — 107 test files exist; need to verify pre-commit runs them

---

## Critical Issues (Blocking Production)

### 1. CRITICAL: Naive UTC Timestamps in Price Fetcher

**File:** `loaders/price_fetcher.py`  
**Lines:** 187, 230  
**Severity:** 🔴 CRITICAL

```python
# WRONG (current code):
now_utc = datetime.now().astimezone()  # Still local time, not UTC!
now_et = now_utc.astimezone(EASTERN_TZ)
```

**Why it's wrong:**
- `datetime.now()` returns naive local time
- `.astimezone()` without args converts naive local to **aware local** (system timezone aware)
- Variable name `now_utc` is a **lie** — it's actually local time with timezone info
- If system timezone is not UTC, all downstream date calculations are wrong

**Correct pattern:**
```python
# RIGHT:
now_utc = datetime.now(timezone.utc)
now_et = now_utc.astimezone(EASTERN_TZ)
```

**Why this matters:**
- Price watermarks depend on correct date boundaries
- Morning/EOD pipeline logic depends on whether it's trading day vs. non-trading day
- Even 1 hour off could cause prices to be fetched for wrong days
- Session 305 already found similar issues in RDSLockManager (datetime.utcnow())

**Impact if not fixed:**
- Prices may be fetched incorrectly relative to trading hours
- Date watermarks could drift slowly
- Morning/EOD boundary conditions fail silently

---

## High-Priority Issues (Will Cause Bugs)

### 2. Inconsistent Timezone Handling in Data Validators

**Files:** 
- `loaders/load_aaii_sentiment.py` (lines 313, 329, 343, 355, 364)
- `loaders/health_monitor.py` (line 190)
- `loaders/data_validator.py` (line 157)

**Severity:** 🟡 MEDIUM-HIGH

**Issue:** Uses `datetime.now().isoformat()` without timezone awareness for error response timestamps.

**Current:**
```python
"timestamp": datetime.now().isoformat(),  # Missing timezone
```

**Should be:**
```python
"timestamp": datetime.now(timezone.utc).isoformat(),  # Explicit UTC
```

**Why it matters:**
- When data_unavailable markers are created, traders need to know EXACTLY when the data became unavailable
- A `2026-07-20T14:30:00` without timezone is ambiguous (UTC? Local? Chicago?)
- Inconsistent timestamps make audit trails unreliable

**Note:** Low operational impact (only affects logging/error messages) but violates governance consistency rules.

---

## Governance Compliance Issues

### 3. Tracked Audit/Session Files (Violates Doc Maintenance Rules)

**Issue:** Old audit findings and session summaries tracked in git:
- `SESSION_276_COMPLETION.md` (in scratchpad, tracked by mistake)
- Multiple old audit files in repo root

**Governance Rule** (from steering/LINT_POLICY.md):
```
Session context and audit findings belong in MEMORY, not in git.
Git should contain only code and timeless steering documentation.
```

**Current state:** At least 1 session file is tracked (should be 0).

**Impact:** 
- Bloats git history with ephemeral session notes
- Makes `git log` harder to read (signal-to-noise ratio drops)
- Violates the "single source of truth" principle (memory vs. git conflict)

---

## Architectural Observations (Not Bugs, But Worth Noting)

### Data Quality Governance ✅ Working Correctly

**Good news:** All 22 loaders have proper fail-fast patterns:
- Explicit `data_unavailable=TRUE` + `reason` field for missing data
- No silent fallbacks to stale/degraded data
- Return `None` when insufficient data (not degraded scores)
- Minimum completeness thresholds enforced (≥70%)

**Examples of correctly implemented fail-fast:**
- `load_earnings_calendar_sec.py` (lines 193-226) — reuses existing unavailable markers instead of stamping today's date
- `load_short_interest_finra.py` (lines 109-117) — same pattern, prevents unbounded duplicate growth
- `load_technical_indicators.py` — requires ≥30 days of prices, fails if insufficient

### Type Safety ✅ Enforced

- mypy strict mode blocks all type errors pre-commit
- Pylint enforces comparison-with-callable checks (prevents dict-vs-int bugs)
- Import errors caught at commit time

### Environment Loading ✅ Fixed (Session 304)

- `run_local_orchestrator.py` correctly loads `.env.local` before AWS calls
- Prevents silent fallthrough to stale DB placeholder credentials
- Pattern replicated across all critical scripts

---

## Code Smells to Address (Best Practices)

### 4. Magic Numbers in Phase Execution

**Files:** `algo/orchestrator/phase_registry.py`, `algo/infrastructure/reconciliation.py`

**Examples:**
```python
PORTFOLIO_SNAPSHOT_LOCK_ID = 2147483647  # Why this specific number?
```

**Should be:**
- Document why this specific lock ID was chosen
- Consider using UUID or sequence-based ID if not tied to a constraint

**Severity:** 🟢 LOW (not affecting correctness, but reduces maintainability)

---

## Summary of Required Fixes

| Priority | Issue | File | Lines | Fix Effort | Risk |
|----------|-------|------|-------|-----------|------|
| 🔴 CRITICAL | Naive UTC timestamps | `price_fetcher.py` | 187, 230 | 5 min | High (affects data pipeline) |
| 🟡 HIGH | Inconsistent timezone logging | `load_aaii_sentiment.py` et al | 313+ | 10 min | Low (logging only) |
| 🟡 MEDIUM | Remove tracked session files | git | — | 5 min | Very low |
| 🟢 LOW | Document magic numbers | Various | — | 15 min | None |

---

## Verification Plan

After fixes, run:

```bash
# 1. Type safety check
mypy --strict .

# 2. Pre-commit validation
pre-commit run --all-files

# 3. Local orchestrator test
python scripts/run_local_orchestrator.py --morning

# 4. Data pipeline verification
python scripts/monitor_data_staleness.py

# 5. Check for remaining datetime.now() patterns
grep -r "datetime.now()" loaders/ | grep -v timezone.utc
```

---

## Related Sessions

- **Session 305:** Fixed RDSLockManager UTC bug (similar class: datetime.utcnow() misuse)
- **Session 304:** Fixed ad-hoc scripts skipping .env.local (credentials fallback bug)
- **Session 303:** Fixed stock_symbols coverage (2028 NYSE stocks)
- **Session 301:** Fixed win_rate/expectancy crash, PK dupes

---

## Next Steps

1. **Fix critical bug** (price_fetcher.py) — 5 minutes
2. **Harmonize timezone logging** — 10 minutes  
3. **Clean up tracked audit files** — 5 minutes
4. **Update memory** with any patterns found
5. **Run full pre-commit + test suite**
6. **Deploy and monitor** data pipeline execution

**Estimated total effort:** 30 minutes (implementation + testing)

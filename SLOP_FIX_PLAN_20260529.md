# Slop Fix Implementation Plan — 2026-05-29

## PHASE A: Consolidate DatabaseContext (1 hour)

### Step A1: Refactor utils/database_context.py
**Goal:** Remove dependency on get_db_connection(). DatabaseContext becomes THE gateway to the database.

**Current state:**
```python
from utils.db_connection import get_db_connection
...
def __enter__(self):
    self.conn = get_db_connection(timeout=self.timeout)
```

**Target state:**
```python
# DatabaseContext calls psycopg2.connect() directly
# Inherits robust error handling from the old get_db_connection() logic
```

**Changes:**
1. Copy the robust connection logic from get_db_connection() into DatabaseContext.__enter__()
2. Keep the diagnostic logging from db_connection.py (it's valuable)
3. Remove the import: `from utils.db_connection import get_db_connection`
4. Verify DatabaseContext still uses proper timeout, retry, cursor_factory

**Implementation details:**
- getaddrinfo() timeout handling (socket.setdefaulttimeout)
- DNS resolution diagnostics (valuable for Lambda debugging)
- Retry logic (max_retries)
- TrackedConnection wrapper (connection monitoring)
- Statement timeout configuration

**After fix:**
- DatabaseContext is self-contained
- get_db_connection() becomes internal/legacy (only utils/database_context.py can import it if needed)
- All 65 existing DatabaseContext users continue working (no API change)

---

## PHASE B: Migrate 10 Files from get_db_connection() to DatabaseContext (2-3 hours)

### List of Files to Migrate

| File | Usage Type | Fix |
|------|-----------|-----|
| `algo/algo_position_monitor.py` | Direct import | Replace with DatabaseContext |
| `algo/algo_pyramid.py` | Direct import | Replace with DatabaseContext |
| `algo/algo_var.py` | Direct import | Replace with DatabaseContext |
| `algo/orchestrator/phase4_exit_execution.py` | Direct import | Replace with DatabaseContext |
| `utils/loader_helpers.py` | Direct import | Replace with DatabaseContext |
| `utils/optimal_loader.py` | Direct import | Replace with DatabaseContext |
| `lambda/api/lambda_function.py` | Lines 35 + 95 | Remove old import, use existing DatabaseContext |
| `scripts/fix_broken_migrations.py` | In string | Remove file (Phase D) |
| `scripts/migrate_db_connections.py` | In string | Remove file (Phase D) |

### Template for Each File

#### Step B1: algo/algo_position_monitor.py
**Current:**
```python
from utils.db_connection import get_db_connection
...
conn = get_db_connection()
cur = conn.cursor()
cur.execute(...)
```

**Target:**
```python
from utils.database_context import DatabaseContext
...
with DatabaseContext() as cur:
    cur.execute(...)
```

**Changes:**
1. Remove: `from utils.db_connection import get_db_connection`
2. Add: `from utils.database_context import DatabaseContext`
3. Replace all `conn = get_db_connection(); cur = conn.cursor()` with `with DatabaseContext() as cur:`
4. Remove manual cur.close() and conn.close() (context manager handles it)

#### Step B2: algo/algo_pyramid.py
Same pattern as B1

#### Step B3: algo/algo_var.py
Same pattern as B1

#### Step B4: algo/orchestrator/phase4_exit_execution.py
Same pattern as B1

#### Step B5: utils/loader_helpers.py
Same pattern as B1

#### Step B6: utils/optimal_loader.py
Same pattern as B1

#### Step B7: lambda/api/lambda_function.py
**Current:**
```python
from utils.database_context import DatabaseContext
from utils.db_connection import get_db_connection
...
def test_db_connection():
    conn = get_db_connection()
```

**Target:**
```python
from utils.database_context import DatabaseContext
# Remove: from utils.db_connection import get_db_connection
...
def test_db_connection():
    with DatabaseContext() as cur:
        cur.execute("SELECT 1")
```

**Changes:**
1. Remove line 35: `from utils.db_connection import get_db_connection`
2. Replace test_db_connection() function to use DatabaseContext

---

## PHASE C: Fix algo/algo_config.py (30 minutes)

**Current:**
```python
def _load_from_database(self):
    ...
    conn = get_db_connection(timeout=15)
    cur = conn.cursor()
```

**Target:**
```python
def _load_from_database(self):
    ...
    with DatabaseContext(timeout=15) as cur:
        cur.execute(...)
```

**Changes:**
1. Ensure DatabaseContext import exists (already present: line 15)
2. Replace lines 242-278 (manual connection handling) with DatabaseContext context manager
3. Remove manual cur.close() / conn.close() calls
4. Remove unused variables from finally block

---

## PHASE D: Delete Dead Migration Scripts (15 minutes)

**Files to delete:**
1. `scripts/migrate_db_connections.py`
2. `scripts/fix_missing_imports.py`
3. `scripts/fix_broken_migrations.py`

**Why:** These were one-time cleanup scripts from the Phase 1 DatabaseContext migration. No longer needed.

**Verification:** 
```bash
grep -r "migrate_db_connections\|fix_missing_imports\|fix_broken_migrations" --include="*.py" --include="*.yml"
```
Should return nothing (or only the files themselves being deleted).

---

## PHASE E: Investigate Unused Helpers (30 minutes)

### E1: utils/db_retry_helper.py
**Action:** 
```bash
grep -r "db_retry_helper\|from utils.db_retry" --include="*.py"
```
If no results: DELETE
If used: DOCUMENT usage

### E2: utils/feature_flags.py
**Action:**
```bash
grep -r "feature_flags\|from utils.feature_flags" --include="*.py"
```
If no results: DELETE (or move to archive)
If used: DOCUMENT usage and verify it aligns with steering doc

---

## PHASE F: Quality Polish (30 minutes)

### F1: Bare exceptions in workflows
**Files:**
- `.github/workflows/deploy-all-infrastructure.yml`
- `.github/workflows/deploy-code.yml`

**Action:** Replace `except:` with `except Exception as e:` and log the error

### F2: Configuration Architecture Documentation
**Action:** Read through config/ and algo_config.py, verify separation is clear:
- `config/credential_manager.py` — AWS Secrets Manager + env vars
- `config/alpaca_config.py` — Alpaca-specific (paper vs live mode)
- `config/credential_validator.py` — Validation logic
- `algo/algo_config.py` — Trading parameters (hot-reload from DB)

**Verification:** Is each module's responsibility clearly documented?

---

## Testing & Verification

### After Each Phase

Run:
```bash
python -m pytest tests/ -v
```

Check for:
- [ ] All 40 tests pass
- [ ] No import errors
- [ ] No hanging imports (10+ second delays)

### Final Verification (After All Phases)

```bash
# 1. Check no more get_db_connection imports except internally
grep -r "from utils.db_connection import" --include="*.py" . | grep -v "utils/database_context.py" | grep -v __pycache__
# Expected: NO RESULTS

# 2. Verify DatabaseContext is the gateway
grep -c "DatabaseContext" loaders/load_*.py algo/*.py lambda/api/*.py utils/*.py
# Expected: Many matches (65+ files)

# 3. Run tests
pytest tests/ -v
# Expected: 40/40 passing

# 4. Check orchestrator imports
python -c "from algo.algo_orchestrator import AlgoOrchestrator; print('✓ Orchestrator imports OK')"

# 5. Check API imports
python -c "from lambda.api.lambda_function import handler; print('✓ API imports OK')"
```

---

## Git Commit Plan

### Commit 1: Phase A (DatabaseContext consolidation)
```
refactor: consolidate DatabaseContext to eliminate utils.db_connection dependency

- Move connection logic from get_db_connection() into DatabaseContext.__enter__()
- DatabaseContext now the sole gateway to database
- Retains robust error handling and diagnostic logging
- All 65 existing DatabaseContext users unaffected (no API change)
```

### Commit 2: Phase B (Migrate 10 files)
```
refactor: migrate 10 files from get_db_connection() to DatabaseContext

Files migrated:
- algo/algo_position_monitor.py
- algo/algo_pyramid.py
- algo/algo_var.py
- algo/orchestrator/phase4_exit_execution.py
- utils/loader_helpers.py
- utils/optimal_loader.py
- lambda/api/lambda_function.py

All use consistent DatabaseContext pattern.
```

### Commit 3: Phase C (algo_config fix)
```
refactor: algo_config.py use DatabaseContext for consistency

- Replace get_db_connection() with DatabaseContext in _load_from_database()
- Aligns with existing set() and initialize_defaults() methods
```

### Commit 4: Phase D (Delete dead scripts)
```
chore: remove one-time database migration scripts

Deleted:
- scripts/migrate_db_connections.py
- scripts/fix_missing_imports.py
- scripts/fix_broken_migrations.py

These were Phase 1 cleanup scripts, no longer needed.
```

### Commit 5: Phase E (Cleanup)
```
chore: remove unused utility modules

Deleted or documented:
- utils/db_retry_helper.py (unused)
- utils/feature_flags.py (verify usage)
```

### Commit 6: Phase F (Quality)
```
chore: improve error handling in workflows and documentation

- Replace bare except clauses in GitHub Actions workflows
- Improve configuration architecture documentation
```

---

## Rollback Plan

If tests fail after any phase:
1. `git reset --hard HEAD~1`
2. Fix the issue
3. Re-commit

Each commit is independently testable. No cross-commit dependencies.

---

## Success Criteria

- [ ] All 40 tests pass
- [ ] Zero imports of `utils.db_connection` from production code
- [ ] Zero imports of `get_db_connection()` from production code
- [ ] DatabaseContext is THE sole gateway (verified by grep)
- [ ] No bare except clauses in production code
- [ ] Dead scripts removed
- [ ] Configuration architecture clear and documented


# Codebase Audit Report - 2026-05-09

## Executive Summary
Found 150+ stale/duplicate/partially-done files creating significant cleanup burden. Work spans multiple initialization patterns, deployment approaches, and test artifacts. This explains "junk lingering around" phenomenon.

---

## CRITICAL ISSUES (Fix First)

### 1. DATABASE SCHEMA MISMATCH ⚠️ BLOCKING
**Files involved:**
- `init_db.sql` (1,080 lines) — Local dev: "comprehensive 60+ tables"
- `terraform/modules/database/init.sql` (112 lines) — AWS: minimal schema
- `init_database.py` (1,926 lines) — Python init with CREATE TABLE statements

**Problem:** Local and AWS have DIFFERENT schemas. This breaks dev-to-prod parity.

**Impact:** All debug SQL files exist because of this mismatch
- `check_data_issues.sql` (debug query for schema issues)
- `verify-schema.sql` (debug/testing to check which exists)
- `verify_data_loaded.sql` (debug)
- `schema-migration.sql`, `schema_migration_current.sql`, `timescaledb_migration.sql` (migration attempts)

**Resolution needed:** Unify schemas and choose ONE init pattern.

---

### 2. MULTIPLE DATABASE INITIALIZATION PATTERNS ⚠️
**Pattern 1: Docker-compose (Local Dev)**
- Uses: `init_db.sql` (1,080 lines, 60+ tables)
- Defined in: `docker-compose.yml`
- Scope: Local development only

**Pattern 2: Terraform (AWS Deployment)**
- Uses: `terraform/modules/database/init.sql` (112 lines, minimal)
- Defined in: `terraform/modules/database/main.tf`
- Scope: Production deployment

**Pattern 3: Python Script (Deprecated?)**
- Uses: `init_database.py` (1,926 lines, dynamic table creation)
- Status: Unclear if still used
- Scope: Unknown

**Pattern 4: Setup Scripts (Unclear)**
- `scripts/init_db_local.sh` — for what?
- `terraform/modules/database/db_init_lambda.py` — initialization Lambda?
- `setup_timescaledb_local.sh` — optional TimescaleDB setup
- `webapp/lambda/scripts/setup-local-data.sh` — test data setup
- `tests/setup_test_db.py` — test infrastructure

**Problem:** 5+ different ways to init the database. No clear "source of truth."

---

### 3. DOCKER DEPLOYMENT OBSOLESCENCE ⚠️
**Files:** 75+ `Dockerfile.*` at root level

```
Dockerfile.aaiidata
Dockerfile.alpacaportfolio
Dockerfile.analystsentiment
Dockerfile.annualbalancesheet
... (65 more loader-specific Dockerfiles)
Dockerfile.stocksymbols
Dockerfile.swingscores
Dockerfile.ttmcashflow
Dockerfile.ttmincomestatement
```

**Context:**
- These are individual Dockerfiles for each data loader
- Modern deployment: Terraform + ECS task definitions (no individual Dockerfiles per loader)
- These are remnants of OLD Docker-based loader architecture

**Status:** SUPERSEDED by Terraform ECS task definitions in `terraform/modules/loaders/`

**Action:** Should be deleted — not used in current Terraform deployment

---

## SECONDARY ISSUES (Fix Next)

### 4. BACKTEST DUPLICATE FILES
Files that look similar:
- `backtest.py` (623 lines)
- `algo_backtest.py` (620 lines)
- `backtest_compare.py` (6.1K)
- `algo_phase2_backtest_comparison.py` (336 lines)

**Problem:** Unclear which is "source of truth" or if all are needed

---

### 5. OLD TEST OUTPUT FILES (Delete)
```
api-test.json (993B) — old test output
api-test.log (103KB) — old test output
comprehensive-test-report.json (6.1K) — old test output
orchestrator_test.log (13K) — old test output
orchestrator_final_test.log (359B) — old test output
orchestrator_run.log (6.0K) — old test output
orchestrator_run2.log (6.0K) — old test output
orchestrator_verification.log (359B) — old test output
real-browser-test-report.json (1.6K) — old test output
test-algo-dashboard.js (2.6K) — old API test
test-protected-routes.js (3.3K) — old API test
test-proxy.js (1.7K) — old API test
test-real-browser.js (8.0K) — old API test
```

**Total:** ~148KB of old test run artifacts

---

### 6. BOOTSTRAP ARTIFACT (Delete)
- `awscliv2.zip` (67MB) — AWS CLI installer, used once for bootstrap, not needed

---

### 7. STRESS TEST DUPLICATION
- `algo_stress_test.py` — stress testing
- `algo_stress_test_runner.py` — stress test wrapper
- `paper_mode_testing.py` — paper mode validation

**Problem:** Unclear which is active; appear to be from development phase

---

### 8. INCOMPLETE/PARTIAL IMPLEMENTATIONS
- `migrate_timescaledb.py` — TimescaleDB migration (not active?)
- `algo_phase2_backtest_comparison.py` — Phase 2 work (completed months ago?)
- Multiple loader-related setup scripts with unclear status

---

## FILES ALREADY DELETED (Phase 1 ✅)
- 15 debug/triage shell scripts
- 4 cleanup Python scripts
- 18 session audit markdown files
- `__pycache__` directory

---

## REMAINING SQL FILES STATUS

### KEEP (Actively Used)
- ✅ `create_loader_sla_table.sql` — referenced in audit_dashboard.py, data_quality_validator.py, loader_sla_tracker.py
- ✅ `refresh_materialized_views.sql` — operational maintenance

### DELETE (Debug/Superseded)
- ❌ `check_data_issues.sql` — debug query for schema issues
- ❌ `verify-schema.sql` — debug/testing
- ❌ `verify_data_loaded.sql` — debug query
- ❌ `schema-migration.sql` — old migration
- ❌ `schema_migration_current.sql` — old migration  
- ❌ `timescaledb_migration.sql` — conditional migration, not active

---

## CLEANUP ROADMAP

### Phase 1: ✅ DONE
- Deleted 15 debug shell scripts
- Deleted 4 cleanup Python scripts
- Deleted 18 session audit markdown files
- Deleted `__pycache__`

### Phase 2: DATABASE SCHEMA (CRITICAL - Do This Next)
1. Decide: Should AWS use full 60+ table schema or minimal?
2. Make `init_db.sql` and `terraform/modules/database/init.sql` consistent
3. Remove unused database init patterns (Python script? Local shell scripts?)
4. Delete old SQL migration files (schema-migration.sql, etc.)
5. Verify docker-compose.yml and Terraform both use same init source

### Phase 3: DOCKERFILE CLEANUP
1. Verify Terraform is using ECS task definitions (not individual Dockerfiles)
2. Delete all 75+ Dockerfile.* files (superseded by Terraform)
3. Keep: `Dockerfile` (main), `webapp/lambda/Dockerfile`

### Phase 4: TEST ARTIFACTS & BOOTSTRAP
1. Delete all .log, .json test output files (148KB)
2. Delete `awscliv2.zip` (67MB) — bootstrap artifact
3. Delete old API test files (test-*.js)

### Phase 5: DEDUPLICATION
1. Resolve backtest.py vs algo_backtest.py
2. Resolve stress test duplication
3. Audit `init_database.py` — still needed or superseded?

### Phase 6: STALE SCRIPTS
1. Review `migrate_timescaledb.py` — still active?
2. Review `algo_phase2_*` files — completed work?
3. Review test setup scripts — which is source of truth?

---

## BY THE NUMBERS

**What we've deleted so far:** 37 files (mostly junk)

**What needs cleanup:**
- 75 Dockerfiles (obsolete)
- 9 test artifact files
- 1 bootstrap file (67MB!)
- 6 old SQL migrations
- ~15 ambiguous init/setup scripts
- 4+ backtest duplicates
- 2-3 stress test duplicates

**Estimated recovery:** ~70MB+ storage, 100+ files, significant token savings during future grepping

---

## NEXT IMMEDIATE STEPS

**Before proceeding with Phase 2-6, need clarification:**
1. Should AWS RDS have the 60+ table schema (comprehensive) or minimal schema?
2. Is `init_database.py` still being used, or fully replaced by SQL init files?
3. Are the 75 Dockerfile.* files truly obsolete (all deployed via Terraform)?
4. Can we delete all the old test output files safely?


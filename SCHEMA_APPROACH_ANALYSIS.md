# Database Schema Management - Best Practice Analysis

## Current State
- **init_database.py**: 109 tables, Python "schema as code" (AUTHORITATIVE)
- **init_db.sql**: 53 tables (incomplete, used by docker-compose)
- **terraform/modules/database/init.sql**: 6 tables (broken, used by Terraform Lambda)
- **Multiple execution paths**: Python script, SQL files, Lambda, Docker
- **No versioning**: No migration tracking, no way to know which version is deployed

---

## Industry Best Practices for Database Schema

### Option A: Migration Framework (Flyway/Liquibase style)
**How it works:**
- V001_initial_schema.sql — Create all 109 tables
- V002_add_indexes.sql — Add performance indexes
- V003_add_audit_tables.sql — Add audit tracking
- Each is version-controlled, idempotent, ordered
- Database tracks which migrations have run (schema_migrations table)

**Pros:**
- Industry standard across teams
- Clear version history and rollback capability
- Works in all environments consistently
- Scalable as schema grows
- Easy to audit what changed and when

**Cons:**
- Requires migration tool setup
- More complex initially
- Overkill if schema rarely changes

---

### Option B: Application-Driven Schema (SQLAlchemy/Alembic)
**How it works:**
- Python application manages schema via ORM
- alembic creates migration scripts
- Application checks schema version on startup
- Migrations run automatically if needed

**Pros:**
- Truly single source of truth (Python ORM models)
- Self-healing (app ensures schema exists)
- Language-native (Python developers understand it)
- Works in all environments (local dev, tests, AWS)
- Can integrate with credential_manager

**Cons:**
- Requires SQLAlchemy ORM refactoring
- Less transparent to DBA/ops teams
- Harder to manually inspect database

---

### Option C: Infrastructure as Code (Terraform) Only
**How it works:**
- All schema defined in Terraform SQL files
- Terraform manages creation and updates
- Infrastructure layer owns the schema

**Pros:**
- Everything in version control (Terraform)
- Clear IaC ownership
- Works for AWS-only deployments

**Cons:**
- Local dev breaks (docker-compose can't use Terraform)
- Dual maintenance (Terraform + init_database.py)
- Can't easily seed test data
- Complex to manage across environments

---

### Option D: Hybrid (Best for Your Stack)
**Recommended Approach:**

1. **Keep init_database.py as AUTHORITATIVE source**
   - Single source of truth
   - "Schema as code" in Python
   - Can be imported and tested

2. **Extract SQL from init_database.py and version it**
   - Create `migrations/V001_initial_schema.sql` with all 109 tables
   - Extract the SCHEMA constant to pure SQL
   - Maintain one-way sync: init_database.py → migrations/V001_*.sql

3. **Use migrations approach for future changes**
   - New schema changes become `migrations/V002_*.sql`
   - Database tracks which migration version is deployed
   - AWS, local dev, tests all use same migration scripts

4. **Initialization flow:**
   - **Local dev (docker-compose)**: Runs init_database.py on startup OR mounts migrations/V001_*.sql
   - **AWS (Terraform)**: Lambda runs migrations in order (check migration table, run pending)
   - **Tests**: init_database.py or migrations in transaction (rollback after)

**Implementation steps:**
```
1. Export init_database.py SCHEMA → migrations/V001_initial_schema.sql
2. Create migrations table: CREATE TABLE IF NOT EXISTS schema_migrations (...)
3. Update db_init_lambda.py to run migrations instead of raw SQL
4. Update docker-compose to run migrations
5. Add migration runner to tests/setup_test_db.py
```

---

## Other Schema Management Issues Found

### 1. **Duplicate init files**
- `init_database.py` (Python)
- `init_db.sql` (SQL, incomplete)
- `setup_timescaledb_local.sh` (Shell wrapper)
- `scripts/init_db_local.sh` (Another shell script)
- `terraform/modules/database/db_init_lambda.py` (Lambda)
- `webapp/lambda/scripts/setup-local-data.sh` (Test data)
- `tests/setup_test_db.py` (Test-specific)

**Problem:** 7 different ways to initialize or set up the database

### 2. **No schema version tracking**
- Can't tell if AWS schema is in sync with local dev
- Can't safely add columns/tables (might break running Lambdas)
- No rollback capability

### 3. **No data seed/fixture management**
- Tests create their own fixtures
- No standard way to seed test data
- No way to validate schema consistency

### 4. **Hardcoded credentials in init scripts**
- init_database.py references credential_manager (good)
- But docker-compose uses environment variables
- Terraform Lambda gets them from Secrets Manager
- **Inconsistent credential handling**

---

## Recommendation: Hybrid Migration Approach

**This is what I recommend for "ULTRA BEST PRACTICE":**

### Phase 1: Establish Migration Framework
1. Create `migrations/` directory with V001_initial_schema.sql
2. Create `schema_migrations` table in database
3. Build simple migration runner in Python (90 lines, no external deps needed)

### Phase 2: Unify Initialization
1. Remove duplicate init scripts
2. Single entry point: `python run_migrations.py`
3. Works for local dev, AWS (via Lambda), tests

### Phase 3: Consistent Credential Handling
1. All paths use credential_manager
2. No hardcoded secrets
3. Works in all environments

### Result:
- ✅ Single source of truth for schema (migrations directory)
- ✅ Version tracking (which migrations have run)
- ✅ Works in all environments
- ✅ Self-healing (application checks and runs pending migrations)
- ✅ Safe schema changes (can rollback if needed)
- ✅ Easy testing (migrations in transaction)
- ✅ Industry standard approach

---

## What Should We Do?

**Option 1: Full Migration Framework** (Best long-term)
- Implement Flyway-style versioned migrations
- Single `run_migrations.py` script for all environments
- More upfront work, but much better for scale

**Option 2: Simplified Hybrid** (Pragmatic, fast)
- Keep init_database.py
- Extract SCHEMA to init_db.sql (all 109 tables)
- Use same file everywhere (docker-compose + Terraform)
- Add simple migration tracking table for future changes
- Quick win, addresses current issue

**Option 3: Keep Current (Not recommended)**
- Unify the three files somehow
- Still fragile, still no versioning

**My recommendation:** **Option 1** - Worth the effort to do it right now, saves pain later.


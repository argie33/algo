# Actual Deployment & Initialization Flow Analysis

## Current AWS Deployment Flow (What's Actually Happening)

### Step 1: Terraform Deploys Infrastructure
```
terraform apply
  ↓
Creates RDS instance (empty database)
  ↓
Creates temporary db_init Lambda with db_init_lambda.py
  ↓
Invokes db_init Lambda via local-exec provisioner
  ↓
db_init Lambda reads init.sql and executes it
  ↓
Database now has 6 tables (INCOMPLETE!)
  ↓
Terraform completes
```

### Step 2: algo_orchestrator Lambda Runs (Scheduled via EventBridge)
```
EventBridge triggers algo_orchestrator Lambda at 5:30pm ET
  ↓
algo_orchestrator starts up
  ↓
Checks: SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public'
  ↓
Finds 6 tables (>= 3), so thinks schema is initialized
  ↓
Skips init_database.main() call
  ↓
Tries to use tables #7-109 that don't exist
  ↓
CRASHES with "table not found" error
```

### Local Development Flow (What Works)
```
docker-compose up
  ↓
PostgreSQL starts with init_db.sql mounted
  ↓
Runs init_db.sql (53 tables, still incomplete!)
  ↓
Developer runs: python init_database.py
  ↓
init_database.py creates missing tables (total 109)
  ↓
Works locally
```

### CI/CD Testing Flow (What Works)
```
pytest
  ↓
Runs: python init_database.py (twice: stocks and stocks_test)
  ↓
Creates all 109 tables
  ↓
Tests run successfully
```

---

## The Core Problem

### Three Incomplete Schema Definitions
1. **init_database.py** → 109 tables (AUTHORITATIVE)
2. **init_db.sql** → 53 tables (incomplete)
3. **terraform/modules/database/init.sql** → 6 tables (broken)

### Why They're Out of Sync
- init_database.py is the "source of truth" Python code
- Someone extracted partial SQL to init_db.sql
- Someone extracted even less SQL to Terraform
- Nobody kept them in sync as code evolved

### Why AWS Fails
- Terraform only runs with 6 tables
- algo_orchestrator sees 6 tables and skips initialization
- Code needs 109 tables → crashes

---

## The Real Constraint

**algo_orchestrator.py imports init_database and expects to call it:**
```python
if table_count >= 3:
    if self.verbose:
        logger.info("  [SCHEMA] Database schema already initialized")
    return

if self.verbose:
    logger.info("  [SCHEMA] Initializing database schema...")

import init_database
init_database.main()
```

This means:
- init_database.py MUST be available in algo_orchestrator Lambda
- OR database must be pre-initialized with all 109 tables
- OR this check is wrong/incomplete

---

## Solution Options

### Option A: Pre-initialize Complete Schema in Terraform
**Terraform's db_init Lambda handles all initialization**

Steps:
1. Extract all 109 tables from init_database.py → init.sql
2. Terraform db_init Lambda runs init.sql (once, during deployment)
3. Database has complete schema when algo_orchestrator starts
4. algo_orchestrator's init_database check still runs, finds all tables, skips init
5. Everything works

**Pros:**
- Clean separation: Terraform = infrastructure, Lambda = application
- Database initialized before algo_orchestrator runs
- No need to include init_database.py in Lambda package
- Idempotent (IF NOT EXISTS on all CREATE TABLE statements)

**Cons:**
- init_database.py becomes "reference only", not the deployed source
- Risk of drift if init_database.py and init.sql get out of sync again

---

### Option B: Package init_database.py in algo_orchestrator Lambda
**Application manages its own schema initialization**

Steps:
1. Copy init_database.py to lambda-deploy/
2. Include it in algo_orchestrator Lambda package
3. algo_orchestrator imports and runs it on startup
4. Single source of truth: init_database.py is deployed code
5. Works in all contexts (local, test, AWS)

**Pros:**
- True single source of truth (init_database.py)
- Deployment is self-healing (if schema missing, app creates it)
- Works anywhere Python runs

**Cons:**
- Lambda package includes Python code for schema (not typical IaC pattern)
- Harder to debug database-level issues (schema not in Terraform)
- Requires init_database.py to handle being in Lambda (credentials, environment)
- credential_manager must work in Lambda context

---

### Option C: Hybrid - Both (Safest for Production)
**Pre-initialize with Terraform, but allow app to self-heal**

Steps:
1. Extract init_database.py → init.sql with 109 tables
2. Terraform db_init Lambda runs init.sql (initialization)
3. Include init_database.py in algo_orchestrator Lambda (self-healing)
4. algo_orchestrator runs init on startup, but it's idempotent
5. If something is missing, app creates it; if everything exists, skips

**Pros:**
- Robust: works even if Terraform init fails
- Self-healing: missing schema created by app
- Clear ownership: IaC for infrastructure, code for schema
- Can recover from partial failures

**Cons:**
- Two places manage schema (Terraform + Python)
- Risk of divergence if not kept in sync

---

## Past Pain Points (Why This Happened)

1. **Started with Python-only approach**
   - init_database.py was created and worked locally

2. **Added AWS/Terraform**
   - Someone manually extracted partial SQL for Terraform
   - Didn't keep in sync with Python

3. **Code evolved**
   - Developers added tables to init_database.py
   - Nobody updated the SQL files
   - Schema drifted over time

4. **Multiple initialization paths**
   - Local: init_database.py
   - Tests: init_database.py
   - AWS: Terraform SQL
   - They diverged → system broke

---

## What Should We Choose?

This depends on your architectural preference:

**Option A** = "Infrastructure owns schema" (traditional DevOps/Terraform-first)
**Option B** = "Application owns schema" (modern Python/ORM-first)
**Option C** = "Both collaborate" (safest, most defensive)

**Recommendation for a NEW greenfield project:**
- **Go with Option B or C**
- Application code should own schema
- Makes it testable, maintainable, self-healing
- Less bureaucracy (no separate Terraform schema updates)
- Especially good for Python-heavy applications

**But if your team prefers Option A:**
- Keep all schema in Terraform/SQL
- Extract init_database.py to pure SQL
- Keep one source of truth: init.sql
- Deploy it, don't need to touch it after

---

## Decision Point

**What matters most to your team?**

1. **"Schema is infrastructure"** → Option A (Terraform owns it all)
2. **"Schema is code"** → Option B (Application owns it)
3. **"Both matter"** → Option C (Hybrid, safest)

Once you pick, I can implement it cleanly and ensure local dev, tests, and AWS all use the same approach.


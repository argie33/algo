# Phase 1 Deployment: Complete Action Plan

**Status:** Ready for implementation  
**Prerequisites:** Fix schema sync issue first  
**Timeline:** 2 hours today + 1 hour for Terraform validation

---

## Executive Summary

You have:
✅ Phase 1 modules (3 Python files, 764 lines, 12 tests passing)  
✅ Phase 1 schema additions (5 new tables)  
✅ Updated loader (loadpricedaily.py integrated)  
⚠️ Schema deployment infrastructure issue (Terraform using stale init.sql)

**Before deploying Phase 1, we must fix the schema sync issue.**

---

## The Right Way (What We'll Do)

### 1. Fix Schema Sync (30 min)
**File:** `terraform/modules/database/main.tf`

Change lines 476 and 489 from:
```hcl
file("${path.module}/init.sql")
```

To:
```hcl
file("${path.module}/../../init_db.sql")
```

This makes Terraform read from the authoritative `./init_db.sql` instead of stale Terraform copy.

### 2. Validate Locally (15 min)
```bash
# Stop any running containers
docker-compose down

# Start fresh with corrected schema
docker-compose up

# Verify all Phase 1 tables exist
psql -h localhost -U stocks -d stocks -c "\dt data_"
# Should show: 5 new tables
#   - data_loader_runs
#   - data_provenance_log
#   - data_provenance_errors
#   - signal_tick_validation
#   - data_freshness_report
```

### 3. Validate Terraform (15 min)
```bash
cd terraform
terraform plan -var-file=terraform.tfvars
# Review plan output - should reference full init_db.sql
```

### 4. Document the Pattern (15 min)
Create `SCHEMA_MANAGEMENT_POLICY.md` explaining:
- ✅ Single source of truth: `./init_db.sql`
- ✅ Used by: docker-compose (local) + Terraform Lambda (AWS)
- ✅ How to add schema: Edit `./init_db.sql`, both environments get it
- ✅ How to test: Local first (docker-compose), then push to AWS

### 5. Deploy Phase 1 (1 hour)
```bash
# Commit the fix
git add terraform/modules/database/main.tf
git rm terraform/modules/database/init.sql  # Delete stale file
git commit -m "fix: Use root init_db.sql as single source of truth for DB schema"

# Push to trigger deployment
git push origin main

# Terraform will:
# 1. Read ./init_db.sql (1,080 lines with Phase 1 tables)
# 2. Update Lambda function with complete schema
# 3. On next Lambda invocation, create all Phase 1 tables in AWS RDS

# Monitor Terraform output:
# - Should see db_init_lambda_zip including schema.sql
# - Should see Lambda function updated
```

---

## What Each Environment Gets

### After This Fix

**Local Development:**
```
docker-compose up
  └─ PostgreSQL reads: ./init_db.sql
  └─ Gets: Full schema + Phase 1 tables
  └─ Startup: ~3 seconds
  └─ Can: Test loaders, run Phase 1 code, everything works locally ✅
```

**AWS Deployment:**
```
Terraform apply
  └─ Lambda zips: ./init_db.sql → schema.sql
  └─ On first Lambda invoke: Creates Phase 1 tables in RDS
  └─ Gets: Full schema + Phase 1 tables
  └─ Same schema as local ✅
```

**Result:** Local = AWS ✅

---

## Phase 1 Integration Steps

### Step 1: Fix Schema Sync
**Time:** 30 min  
**Files:** terraform/modules/database/main.tf  
**Action:** Change 2 file paths

### Step 2: Validate Locally
**Time:** 15 min  
**Command:** `docker-compose up && psql ... -c "\dt data_"`  
**Expectation:** 5 new Phase 1 tables visible

### Step 3: Validate Terraform
**Time:** 15 min  
**Command:** `terraform plan`  
**Expectation:** Plan shows updated Lambda function

### Step 4: Deploy
**Time:** 5 min  
**Command:** `git push origin main`  
**Trigger:** GitHub Actions runs deploy workflow

### Step 5: Verify AWS
**Time:** 15 min  
**Query:** Check RDS for Phase 1 tables

```sql
SELECT table_name 
FROM information_schema.tables 
WHERE table_name LIKE 'data_%'
ORDER BY table_name;

-- Should see:
-- data_freshness_report
-- data_loader_runs
-- data_provenance_errors
-- data_provenance_log
-- signal_tick_validation
```

---

## Parallel Work: Update Remaining Loaders

While Phase 1 schema deploys to AWS:

**Update remaining 15 loaders** (following `loadpricedaily.py` pattern):

1. **Price loaders** (3): loadpriceweekly, loadpricemonthly, loadetfpricedaily  
2. **Signal loaders** (3): loadbuyselldaily, loadbuyselweekly, loadbuyselmonthly  
3. **Score loaders** (2+): loadtechnicalsdaily, loadstockscores, etc.

Each takes ~30-45 min (copy pattern, adapt table name).

---

## Documentation Updates

Create `SCHEMA_MANAGEMENT_POLICY.md`:

```markdown
# Schema Management Policy

## Single Source of Truth
- **File:** ./init_db.sql
- **Authority:** This is the canonical schema definition
- **Maintenance:** Edit ONLY this file

## Where It's Used

### Local (docker-compose)
- Mounted: ./init_db.sql → /docker-entrypoint-initdb.d/01-init.sql
- Executed: PostgreSQL startup
- When: docker-compose up

### AWS (Terraform)
- Read: terraform/modules/database/main.tf line 476, 489
- Archived: Into Lambda zip as schema.sql
- Executed: db_init_lambda.py after RDS ready
- When: terraform apply

## How to Add Tables

1. Edit ./init_db.sql
2. Test locally: docker-compose up
3. Push to main
4. Terraform auto-deploys to AWS
5. Both environments get same schema ✅

## Validation

Local:
```bash
psql -h localhost -U stocks -d stocks -c "\dt"
```

AWS (after terraform apply):
```sql
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public';
```

Should be identical ✅
```

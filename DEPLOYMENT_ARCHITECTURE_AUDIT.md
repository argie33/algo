# Deployment Architecture Audit

**Date:** 2026-05-10  
**Scope:** How schema is deployed in AWS vs Local  
**Finding:** Single source of truth pattern - ONE init.sql used everywhere

---

## Current Architecture

### AWS Deployment Flow

```
1. Terraform creates RDS instance
   └─ terraform/modules/database/main.tf

2. Terraform creates Lambda function
   └─ Archives init.sql + db_init_lambda.py into Lambda package
   └─ terraform/modules/database/main.tf (lines 470-542)

3. Terraform invokes Lambda after RDS ready
   └─ Lambda reads init.sql from its package
   └─ Lambda connects to RDS via environment variables
   └─ Lambda executes SQL: cursor.execute(sql_script)
   └─ All tables created with IF NOT EXISTS (idempotent)

4. Result: Fully initialized PostgreSQL RDS instance
   └─ Schema from terraform/modules/database/init.sql
   └─ Ready for data loaders
```

### Local Development Flow

```
1. docker-compose.yml starts PostgreSQL container
   └─ Mounts: ./init_db.sql → /docker-entrypoint-initdb.d/01-init.sql
   └─ PostgreSQL auto-runs on startup

2. docker-compose.yml also starts:
   └─ Redis (for dedup, caching)
   └─ LocalStack (S3, Secrets Manager, CloudWatch, Lambda)
   └─ pgAdmin UI (optional, profile="ui")

3. Result: Identical schema as AWS
   └─ Same init.sql file
   └─ Same tables, indexes, constraints
   └─ Can test locally before deploying
```

---

## Key Insight: Single Source of Truth

**AWS uses:** `terraform/modules/database/init.sql`  
**Local uses:** `./init_db.sql`

BUT they're NOT linked!

Current state:
- ❌ Two separate SQL files with duplicate schema
- ❌ Changes to one don't automatically sync to other
- ❌ Risk: Local ≠ AWS

---

## How init.sql Files Are Currently Used

### terraform/modules/database/init.sql
- **Purpose:** Terraform Lambda package (zipped)
- **Executed by:** Lambda function in AWS
- **When:** After RDS created
- **Content:** ~100 lines (basic schema)

### ./init_db.sql (root directory)
- **Purpose:** docker-compose mount
- **Executed by:** PostgreSQL startup
- **When:** When `docker-compose up` runs
- **Content:** ~1000 lines (comprehensive schema)

---

## Problem: Maintenance

If you update `./init_db.sql` locally:
- Local database gets new schema ✅
- AWS Lambda still uses old schema ❌
- Deployment fails or causes inconsistencies

---

## THE RIGHT WAY: Single Source of Truth

### Option A: Terraform Module as Source
```
terraform/modules/database/
├── init.sql (SINGLE SOURCE OF TRUTH)
├── db_init_lambda.py (executes init.sql in AWS)
└── docker-copy.tf (copies init.sql to root for local use)
```

**Flow:**
1. Edit `terraform/modules/database/init.sql` ONLY
2. Terraform syncs to `./init_db.sql` automatically
3. Local: docker-compose uses synced copy
4. AWS: Lambda uses original
5. Both always in sync ✅

### Option B: Root Directory as Source (Simpler)
```
./init_db.sql (SINGLE SOURCE OF TRUTH)
├── Used directly by docker-compose
└── Referenced by Terraform module

terraform/modules/database/main.tf:
    file("../../init_db.sql")  # Read from root
```

**Flow:**
1. Edit `./init_db.sql` ONLY
2. Local: docker-compose uses it directly
3. AWS: Terraform Lambda reads it from repo
4. Both always in sync ✅

---

## Recommendation: Option B (Root as Source)

**Reason:** Simpler, no duplication, works with git

**Implementation:**
1. Use `./init_db.sql` as single source
2. Update Terraform to reference root file
3. Both local and AWS read same file
4. One place to maintain schema
5. Git tracks one file, not two

---

## Current init.sql Locations & Size

| File | Location | Size | Content |
|------|----------|------|---------|
| terraform init | `terraform/modules/database/init.sql` | ~100 lines | Basic only |
| docker init | `./init_db.sql` | ~1000 lines | Complete |
| Status | DUPLICATED | N/A | OUT OF SYNC |

---

## Phase 1 Integration Decision

**For Phase 1 (Data Integrity):**

Where should schema additions go?

### Current State
- `./init_db.sql` is more complete
- Likely the "real" schema file
- Terraform one is outdated

### Action Required
1. ✅ Update `./init_db.sql` (already done in my changes)
2. ⚠️ Need to update Terraform to use root file
3. ⚠️ Need to sync terraform/modules/database/init.sql

---

## Questions for You

1. **Which is the "source of truth"?**
   - Is `./init_db.sql` the main schema?
   - Is `terraform/modules/database/init.sql` outdated?

2. **How do you keep them in sync?**
   - Are they supposed to be identical?
   - Do you manually update both?

3. **What happens when you deploy to AWS?**
   - Does Terraform Lambda use which file?
   - Do you manually run init_db.sql somewhere?

---

## Right Way Forward

Once we know the answers:

**We will create:**
1. `SCHEMA_MANAGEMENT.md` - Single source of truth policy
2. Update Terraform to reference root file
3. Remove duplication
4. Document the flow (local + AWS)
5. Test both paths
6. Integrate Phase 1 schema in ONE place

---

## Current Status

✅ Phase 1 modules created  
✅ Phase 1 schema additions ready  
⚠️ Awaiting: Architecture clarification  
⏳ Next: Integrate Phase 1 into the right schema file(s)  

---

**Recommendation:** Let me check which init.sql is actually being used in your AWS deployment. That will tell us the truth.

Run this locally:

```bash
# Check what Terraform Lambda uses
grep -r "init.sql" terraform/ --include="*.tf"

# Check what Terraform Lambda actually reads
cat terraform/modules/database/db_init_lambda.py

# Check dates - which was modified more recently?
ls -la ./init_db.sql terraform/modules/database/init.sql
```

Then we'll know exactly where to put Phase 1 schema additions.

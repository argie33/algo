# Critical: Schema Sync Issue & Fix Plan

**Status:** 🔴 ISSUE FOUND  
**Severity:** HIGH - AWS deploying with OLD schema  
**Date:** 2026-05-10

---

## The Problem

### File Analysis

| File | Size | Lines | Modified | Usage |
|------|------|-------|----------|-------|
| `./init_db.sql` | 36,342 bytes | 1,080 lines | 2026-05-09 22:58 | **REAL schema** |
| `terraform/modules/database/init.sql` | 4,001 bytes | 112 lines | 2026-05-09 03:52 | **STALE schema** |

### What's Happening

**Local Development:**
```
docker-compose.yml
  └─ mounts → ./init_db.sql
  └─ 1,080 lines ✅ COMPLETE schema
```

**AWS Deployment:**
```
terraform/modules/database/main.tf:476-489
  └─ file("${path.module}/init.sql")
  └─ Reads: terraform/modules/database/init.sql
  └─ 112 lines ❌ OLD, INCOMPLETE schema
```

### Consequence

- **Local:** Full schema with all tables, indexes, triggers
- **AWS:** Minimal schema with only basic tables

**Result:** Code tested locally works, breaks in AWS due to missing tables!

---

## Why This Happened

1. Someone created complete schema in `./init_db.sql`
2. Terraform was already set up with `terraform/modules/database/init.sql`
3. They weren't synced
4. Terraform still references the old one

---

## The Fix: Single Source of Truth

### Solution: Use Root Directory as Source

**Change Terraform from:**
```hcl
file("${path.module}/init.sql")
```

**To:**
```hcl
file("${path.module}/../../init_db.sql")  # Read from root
```

**Why:**
- Root `./init_db.sql` is actively maintained (1,080 lines)
- Terraform `init.sql` is stale (112 lines)
- Root directory is in git, version controlled
- Single point of maintenance

---

## Implementation Steps

### Step 1: Update Terraform Main
**File:** `terraform/modules/database/main.tf`

**Current (lines 475-489):**
```hcl
source {
  content  = file("${path.module}/init.sql")
  filename = "schema.sql"
}

# ...

source {
  content = templatefile("${path.module}/db_init_lambda.py", {
    # ...
    sql_content  = file("${path.module}/init.sql")
  })
  filename = "lambda_function.py"
}
```

**Change to:**
```hcl
source {
  content  = file("${path.module}/../../init_db.sql")
  filename = "schema.sql"
}

# ...

source {
  content = templatefile("${path.module}/db_init_lambda.py", {
    # ...
    sql_content  = file("${path.module}/../../init_db.sql")
  })
  filename = "lambda_function.py"
}
```

### Step 2: Delete Stale File
```bash
# After updating Terraform and testing locally
rm terraform/modules/database/init.sql

# Update git
git rm terraform/modules/database/init.sql
git add terraform/modules/database/main.tf
git commit -m "fix: Use single source of truth for DB schema - root init_db.sql"
```

### Step 3: Test Locally
```bash
# Verify local still works with init_db.sql
docker-compose down
docker-compose up --build

# Check PostgreSQL has all tables
psql -h localhost -U stocks -d stocks -c "\dt"
# Should show 60+ tables from ./init_db.sql
```

### Step 4: Validate Terraform
```bash
# Verify Terraform reads correct file
cd terraform
terraform plan -var-file=terraform.tfvars

# Look for plan output showing correct schema size
# (should be large, containing all Phase 1 tables if we added them)
```

---

## Phase 1 Integration (Depends on This Fix)

Phase 1 schema additions need to go in **ONE place:**

### After Fix is Applied
```
./init_db.sql (SINGLE SOURCE)
├── Existing 1,080 lines ✅
├── Phase 1 additions (5 new tables)
└── Used by:
    ├── docker-compose (local)
    ├── Terraform Lambda (AWS)
    └─ Git (version control)
```

### Before Fix
- Can't safely add Phase 1 to `./init_db.sql` without syncing to Terraform
- Can't add to Terraform file without overwriting local changes
- Risk of deploying incomplete schema to AWS

---

## Deployment Checklist

- [ ] Read this document completely
- [ ] Confirm root `init_db.sql` is the "real" schema
- [ ] Update terraform/modules/database/main.tf (2 lines changed)
- [ ] Test locally: `docker-compose up`
- [ ] Validate schema exists: `psql ... -c "\dt"`
- [ ] Validate Terraform: `terraform plan`
- [ ] Delete terraform/modules/database/init.sql
- [ ] Create commit with Terraform changes
- [ ] Test next deploy to AWS

---

## After Fix: Phase 1 Integration

Once this is fixed:

1. Phase 1 schema additions go into `./init_db.sql`
2. Local development auto-gets them (docker-compose mounts)
3. AWS auto-gets them (Terraform reads from root)
4. One place to maintain
5. No duplication or sync issues

---

## Questions to Confirm

1. Is `./init_db.sql` definitely the authoritative schema?
2. Has anyone intentionally kept `terraform/modules/database/init.sql` separate?
3. When you deployed to AWS last, did it use all the tables from `./init_db.sql`?

If answer to all 3 is YES/NO/NO, then the fix is straightforward.

---

## Timeline

**Today:**
1. Apply this fix (30 min)
2. Test locally (15 min)
3. Validate Terraform (15 min)

**Next Deploy:**
1. Push changes
2. Run Terraform (uses correct schema)
3. Phase 1 schema available both locally and AWS

---

**Status:** Ready for implementation pending your confirmation


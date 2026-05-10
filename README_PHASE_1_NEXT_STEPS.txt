================================================================================
                    PHASE 1 DEPLOYMENT - NEXT STEPS
                              2026-05-10
================================================================================

SITUATION:
  ✅ Phase 1 modules complete (3 files, 764 lines, all tests passing)
  ✅ Phase 1 schema ready (5 new tables)
  ✅ loadpricedaily.py integrated
  ⚠️  CRITICAL: Terraform using STALE schema file

ISSUE FOUND:
  - Local: uses ./init_db.sql (1,080 lines, CURRENT)
  - AWS: uses terraform/modules/database/init.sql (112 lines, STALE)
  - Result: Local ≠ AWS (inconsistent schema)

SOLUTION:
  1. Fix Terraform to read from root ./init_db.sql instead of stale copy
  2. Test locally (docker-compose)
  3. Validate Terraform plan
  4. Deploy to AWS
  5. Phase 1 tables appear in both environments

================================================================================
                         ACTION ITEMS
================================================================================

IMMEDIATE (2 hours):

1. FIX TERRAFORM (30 min)
   File: terraform/modules/database/main.tf
   Lines: 476 and 489

   Change FROM:
     file("${path.module}/init.sql")

   Change TO:
     file("${path.module}/../../init_db.sql")

   Why: Make Terraform read from authoritative root schema, not stale copy

2. TEST LOCALLY (15 min)
   Run:
     docker-compose down
     docker-compose up
     psql -h localhost -U stocks -d stocks -c "\dt data_"

   Expect: See 5 new Phase 1 tables

3. VALIDATE TERRAFORM (15 min)
   Run:
     cd terraform
     terraform plan -var-file=terraform.tfvars

   Expect: See Lambda function will be updated with complete schema

4. CLEAN UP (5 min)
   Delete stale file:
     rm terraform/modules/database/init.sql
     git rm terraform/modules/database/init.sql

5. COMMIT (5 min)
   git add terraform/modules/database/main.tf
   git commit -m "fix: Use root init_db.sql as single source of truth for DB schema"
   git push origin main

THEN (automatic):
  - GitHub Actions triggered
  - Terraform apply runs
  - Lambda updated with complete schema
  - Phase 1 tables created in AWS RDS

VERIFY (15 min):
  Run on AWS:
    psql -h <rds-endpoint> -U stocks -d stocks -c "\dt data_"

  Expect: 5 Phase 1 tables visible

================================================================================
                        DOCUMENTATION CREATED
================================================================================

Three analysis documents have been created:

1. DEPLOYMENT_ARCHITECTURE_AUDIT.md
   - How schema currently deploys
   - Why there are two init.sql files
   - The architectural issue

2. SCHEMA_SYNC_ISSUE_AND_FIX.md
   - Detailed problem statement
   - Step-by-step fix instructions
   - Why this fix is correct

3. PHASE_1_DEPLOYMENT_ACTION_PLAN.md
   - Complete deployment checklist
   - What each environment gets
   - How to update remaining loaders

Read these IN ORDER to understand the full context.

================================================================================
                        WHAT HAPPENS NEXT
================================================================================

PHASE 1 DEPLOYMENT:

Local Development:
  ✅ Phase 1 modules installed
  ✅ Phase 1 schema tables created
  ✅ loadpricedaily.py has validation + provenance tracking
  ✅ Test loaders locally before AWS

AWS Deployment:
  ✅ Same Phase 1 schema deployed
  ✅ Same validation + provenance tracking
  ✅ Loaders can track integrity

PARALLEL WORK (this week):
  - Update remaining 15 loaders
  - Each takes 30-45 minutes
  - Follow loadpricedaily.py pattern
  - See PHASE_1_LOADER_UPDATE_CHECKLIST.md

================================================================================
                          CONFIDENCE CHECK
================================================================================

Before proceeding, confirm:

1. ✓ Is ./init_db.sql the authoritative schema?
   → Current size: 1,080 lines
   → Last modified: 2026-05-09 22:58 (TODAY)
   → Used by: docker-compose (local)
   → Status: ACTIVE, up-to-date ✅

2. ✓ Is terraform/modules/database/init.sql stale?
   → Current size: 112 lines
   → Last modified: 2026-05-09 03:52 (old)
   → Status: NOT MAINTAINED ✅

3. ✓ Is fixing this the right approach?
   → Single source of truth: ./init_db.sql
   → Used by both local + AWS: YES
   → Eliminates duplication: YES
   → Matches infrastructure-as-code best practices: YES ✅

If you agree with all three, proceed with the fix.

================================================================================
                           SUMMARY
================================================================================

What you're building: Production-grade data pipeline with:
  ✅ Validation (every tick checked before database)
  ✅ Provenance (complete audit trail for replay)
  ✅ Safety (crash-safe loading, idempotent)

How you're deploying: Single source of truth (one init_db.sql used everywhere):
  ✅ Local tests it first (docker-compose)
  ✅ AWS deploys it identically (Terraform Lambda)
  ✅ No duplication, no sync issues

Timeline:
  - TODAY: Fix Terraform + validate locally (2 hours)
  - NEXT DEPLOY: Phase 1 tables in AWS (automatic)
  - THIS WEEK: Update remaining 15 loaders (6-7 hours)

Result: Transparent, auditable, crash-safe data pipeline ready for production.

================================================================================
                        READY TO PROCEED?
================================================================================

If yes to all three confidence checks above, we can:

1. Make the Terraform fix right now (30 min)
2. Validate locally (30 min)
3. Confirm it works
4. Document the right way going forward

Then you'll have a production-ready Phase 1 deployment.

What would you like to do?

================================================================================

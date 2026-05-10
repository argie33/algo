# Terraform Blocking Resources Fix - Execution Checklist

**Date Started:** 2026-05-08
**Target Completion:** 2026-05-08
**Precision Level:** Maximum (zero tolerance for errors)

---

## PHASE 0: PRE-FLIGHT VERIFICATION

### Checkpoint 0.1: Verify Current State
- [ ] Confirm git status is clean (or document pending changes)
- [ ] Verify CLAUDE.md and memory are up to date
- [ ] Confirm AWS credentials are configured
- [ ] Document baseline time

### Checkpoint 0.2: Baseline Resource Inventory
- [ ] List all IAM roles starting with "stocks-"
- [ ] List all CloudFront OACs
- [ ] List all CloudFormation stacks
- [ ] Document terraform state version
- [ ] Save screenshots/logs of current state

### Checkpoint 0.3: Backup & Safety
- [ ] Create backup of terraform state
- [ ] Create backup of current git branch state
- [ ] Verify rollback procedure is documented
- [ ] Have contact info ready if AWS support needed

---

## PHASE 1: EXECUTE CLEANUP WORKFLOW

### Checkpoint 1.1: Dry-Run Verification
- [ ] Trigger cleanup workflow with verify_only=true
- [ ] Wait for completion
- [ ] Review output: which roles were found?
- [ ] Verify list matches all 11 expected roles
- [ ] Document findings

### Checkpoint 1.2: Execute Deletion
- [ ] Trigger cleanup workflow with verify_only=false
- [ ] Monitor workflow in real-time
- [ ] Watch for each phase:
  - [ ] Phase 1: Policy deletion (inline)
  - [ ] Phase 2: Policy deletion (managed)
  - [ ] Phase 3: Role deletion
  - [ ] Phase 4: OAC deletion
- [ ] Note any failures and retry counts
- [ ] Document exact time of completion

### Checkpoint 1.3: Post-Cleanup Verification
- [ ] Workflow shows "✅ SUCCESS: All blocking resources cleaned up!"
- [ ] Manually verify all 11 roles are deleted (AWS CLI or console)
- [ ] Manually verify all OACs are deleted
- [ ] Check terraform state hasn't changed
- [ ] Document final cleanup state

### Checkpoint 1.4: Wait & Observe
- [ ] Wait 30 seconds (AWS eventual consistency)
- [ ] Re-run verification one more time
- [ ] Ensure no resources magically reappeared
- [ ] Take final screenshot of clean state

---

## PHASE 2: UPDATE TERRAFORM CODE

### Checkpoint 2.1: Identify All Role Definitions
- [ ] Find all aws_iam_role definitions in terraform modules
- [ ] Create list with file paths and line numbers
- [ ] Identify naming pattern for each
- [ ] Document current vs. desired names

### Checkpoint 2.2: Update IAM Module (iam/main.tf)

**Role:** stocks-github-actions-dev
- [ ] File: terraform/modules/iam/main.tf, line ~37
- [ ] Current: `name = "${var.project_name}-github-actions-${var.environment}"`
- [ ] Change to: `name = "${var.project_name}-svc-github-actions-${var.environment}"`
- [ ] Verify syntax is correct
- [ ] Document change

### Checkpoint 2.3: Update Services Module (services/main.tf)

**Role:** stocks-api-dev-role
- [ ] File: terraform/modules/services/main.tf, line ~17
- [ ] Current: `name = "${local.api_lambda_name}-role"`
- [ ] Change to: `name = "${var.project_name}-svc-api-${var.environment}"`
- [ ] Verify references to this role name don't break
- [ ] Document change

### Checkpoint 2.4: Update Algo Module (algo/main.tf)

**Role:** stocks-algo-dev-role
- [ ] File: terraform/modules/algo/main.tf, line ~15
- [ ] Current: `name = "${var.project_name}-algo-lambda-role"`
- [ ] Change to: `name = "${var.project_name}-svc-algo-${var.environment}"`
- [ ] Verify all references are updated
- [ ] Document change

### Checkpoint 2.5: Update Loaders Module (loaders/main.tf)

**Role:** stocks-eventbridge-run-task-role
- [ ] File: terraform/modules/loaders/main.tf, line ~15
- [ ] Current: `name = "${var.project_name}-eventbridge-run-task-role"`
- [ ] Change to: `name = "${var.project_name}-svc-eventbridge-run-task-${var.environment}"`
- [ ] Verify all references are updated
- [ ] Document change

### Checkpoint 2.6: Find & Update Additional Roles
- [ ] Search for remaining 7 role definitions
- [ ] File: terraform/modules/compute/main.tf (bastion role)
- [ ] File: terraform/modules/database/main.tf (RDS monitoring role)
- [ ] Update each one following new naming pattern
- [ ] Document all changes

### Checkpoint 2.7: Terraform Syntax Validation
- [ ] Run: `terraform -C terraform validate`
- [ ] Should output: "Success! The configuration is valid."
- [ ] If errors: document and fix
- [ ] Take screenshot of validation success

### Checkpoint 2.8: Terraform Plan (Dry-Run)
- [ ] Run: `terraform -C terraform plan -var-file=terraform.tfvars -out=tfplan`
- [ ] Review output for:
  - [ ] No "EntityAlreadyExists" errors
  - [ ] No references to old role names
  - [ ] Plan shows ~45 resources to add/change
  - [ ] No unexpected deletions
- [ ] Document plan summary
- [ ] Save plan file

### Checkpoint 2.9: Code Review Changes
- [ ] Review each file change made
- [ ] Verify no syntax errors were introduced
- [ ] Verify variable references are correct
- [ ] Verify all role names follow new pattern consistently
- [ ] Check for any hardcoded old role names (must fix)

### Checkpoint 2.10: Git Commit
- [ ] Stage all terraform changes: `git add terraform/`
- [ ] Create commit: `git commit -m "Fix: Rename IAM roles to new naming pattern to prevent conflicts"`
- [ ] Verify commit was created: `git log -1`
- [ ] Document commit hash

### Checkpoint 2.11: Push to Main
- [ ] Push: `git push origin main`
- [ ] Verify push succeeded
- [ ] Check GitHub: new commit appears on main branch
- [ ] Document push completion time

---

## PHASE 3: TEST TERRAFORM DEPLOYMENT

### Checkpoint 3.1: Verify Terraform Apply Workflow
- [ ] Wait for terraform-apply.yml to trigger (should auto-run on push)
- [ ] OR manually trigger: `gh workflow run terraform-apply.yml --repo argie33/algo`
- [ ] Monitor workflow logs in real-time
- [ ] Watch for each step:
  - [ ] Checkout code
  - [ ] Setup terraform
  - [ ] Targeted cleanup (should find no resources)
  - [ ] Bootstrap AWS prerequisites
  - [ ] Comprehensive cleanup (should find no resources)
  - [ ] Configure AWS credentials (OIDC)
  - [ ] Delete VPCs (cleanup phase)
  - [ ] Delete orphaned resources
  - [ ] Terraform init
  - [ ] Terraform validate
  - [ ] Terraform plan
  - [ ] Terraform apply

### Checkpoint 3.2: Monitor Terraform Init
- [ ] Watch for: "Terraform has been successfully configured!"
- [ ] Verify no errors about state file
- [ ] Note backend bucket is working
- [ ] Document init time

### Checkpoint 3.3: Monitor Terraform Validate
- [ ] Watch for: "Success! The configuration is valid."
- [ ] No syntax errors
- [ ] No variable errors
- [ ] Document validation time

### Checkpoint 3.4: Monitor Terraform Plan
- [ ] Watch for resource count
- [ ] Should see ~45 resources to create
- [ ] NO "EntityAlreadyExists" errors
- [ ] NO references to deleted role names
- [ ] All new role names use "svc-" prefix
- [ ] Document plan output

### Checkpoint 3.5: Monitor Terraform Apply
- [ ] Watch each resource creation
- [ ] Verify no errors occur
- [ ] Watch for completion message
- [ ] Note: may take 10-15 minutes
- [ ] Document apply time and summary

### Checkpoint 3.6: Verify Workflow Completion
- [ ] Workflow should show: ✅ All steps passed
- [ ] No failed steps
- [ ] No timeouts
- [ ] Document completion time

### Checkpoint 3.7: Check Terraform State
- [ ] Run: `aws s3 cp s3://stocks-terraform-state-*/terraform.tfstate ./`
- [ ] Verify state file is valid JSON
- [ ] Verify all new resources are in state
- [ ] Verify no old role names in state
- [ ] Document state verification

---

## PHASE 4: DEPLOY FULL INFRASTRUCTURE

### Checkpoint 4.1: Trigger Full Deployment
- [ ] Run: `gh workflow run deploy-all-infrastructure.yml --repo argie33/algo --input skip_bootstrap=true`
- [ ] Document trigger time
- [ ] Get workflow run URL

### Checkpoint 4.2: Monitor Stage 1 - Bootstrap
- [ ] Status: Running or SKIPPED (expected since we skipped)
- [ ] Document outcome

### Checkpoint 4.3: Monitor Stage 2 - Core Infrastructure
- [ ] Watch for: "Deploy Core Infrastructure" job
- [ ] Should complete in ~3-5 minutes
- [ ] Verify no errors
- [ ] Check output:
  - [ ] VPC created
  - [ ] Subnets created (3 public, 3 private)
  - [ ] ECR repository created
  - [ ] S3 buckets created (5-6 total)
  - [ ] Security groups created
- [ ] Document completion

### Checkpoint 4.4: Monitor Stage 3 - Data Infrastructure
- [ ] Watch for: "Deploy Data Infrastructure" job
- [ ] Should complete in ~8-10 minutes
- [ ] Verify no errors
- [ ] Check output:
  - [ ] RDS instance created
  - [ ] ECS cluster created
  - [ ] Secrets Manager entries created
  - [ ] IAM roles created (with new names)
- [ ] Document completion

### Checkpoint 4.5: Monitor Stage 4 - Webapp
- [ ] Watch for: "Deploy Webapp" job
- [ ] Should complete in ~3-5 minutes
- [ ] Verify no errors
- [ ] Check output:
  - [ ] Lambda function created
  - [ ] API Gateway created
  - [ ] CloudFront distribution created
  - [ ] Cognito user pool created
- [ ] Document completion

### Checkpoint 4.6: Monitor Stage 5 - Loaders
- [ ] Watch for: "Deploy Loaders" job
- [ ] Should complete in ~2-3 minutes
- [ ] Verify no errors
- [ ] Check output:
  - [ ] 65 ECS task definitions created
  - [ ] EventBridge rules created
  - [ ] No IAM role conflicts
- [ ] Document completion

### Checkpoint 4.7: Monitor Stage 6 - Algo Orchestrator
- [ ] Watch for: "Deploy Algo Orchestrator" job
- [ ] Should complete in ~1-2 minutes
- [ ] Verify no errors
- [ ] Check output:
  - [ ] Lambda function created
  - [ ] EventBridge scheduler created
  - [ ] SNS topic created
  - [ ] CloudWatch logs configured
- [ ] Document completion

### Checkpoint 4.8: Monitor Summary
- [ ] Watch for: "Deployment Summary" job
- [ ] All jobs should show: ✅ Complete
- [ ] No failed jobs
- [ ] Deployment took total: ~20-30 minutes
- [ ] Document final deployment time

---

## PHASE 5: VERIFY COMPLETE SYSTEM

### Checkpoint 5.1: Verify All CloudFormation Stacks
- [ ] Run AWS command to list stacks
- [ ] All 6 stacks should be CREATE_COMPLETE:
  - [ ] stocks-bootstrap
  - [ ] stocks-core
  - [ ] stocks-data
  - [ ] stocks-webapp-dev
  - [ ] stocks-loaders
  - [ ] stocks-algo-dev
- [ ] Document stack status

### Checkpoint 5.2: Verify IAM Roles Exist with New Names
- [ ] List all roles: `aws iam list-roles`
- [ ] Verify these exist (with new naming):
  - [ ] stocks-svc-github-actions-dev
  - [ ] stocks-svc-api-dev
  - [ ] stocks-svc-algo-dev
  - [ ] stocks-svc-eventbridge-run-task-dev
  - [ ] (and others with svc- prefix)
- [ ] Verify NO old role names exist
- [ ] Document all roles found

### Checkpoint 5.3: Verify Lambda Functions
- [ ] Check API Lambda:
  - [ ] Name: stocks-api-dev
  - [ ] Runtime: Python 3.11
  - [ ] Status: Active
  - [ ] Role: stocks-svc-api-dev
- [ ] Check Algo Lambda:
  - [ ] Name: stocks-algo-dev
  - [ ] Runtime: Python 3.11
  - [ ] Status: Active
  - [ ] Role: stocks-svc-algo-dev
- [ ] Document Lambda status

### Checkpoint 5.4: Verify RDS Database
- [ ] Check RDS instance:
  - [ ] Name: stocks-db
  - [ ] Engine: PostgreSQL 13.7
  - [ ] Status: Available
  - [ ] Backup retention: 5 days
- [ ] Attempt connection:
  - [ ] Command: `psql -h <RDS_ENDPOINT> -U stocks -d stocks -c "SELECT 1;"`
  - [ ] Should return: `1` (success)
- [ ] Document RDS status and connectivity

### Checkpoint 5.5: Verify ECS Cluster
- [ ] Check ECS cluster:
  - [ ] Name: stocks-cluster
  - [ ] Status: Active
  - [ ] Task definitions: 65+ created
- [ ] List running tasks:
  - [ ] Command: `aws ecs list-tasks --cluster stocks-cluster`
  - [ ] May be empty (loaders run on schedule)
- [ ] Document ECS status

### Checkpoint 5.6: Verify EventBridge Scheduler
- [ ] List schedules:
  - [ ] Command: `aws scheduler list-schedules --region us-east-1`
  - [ ] Should see: stocks-algo-schedule
  - [ ] Status: ENABLED
  - [ ] Schedule: cron(30 21 ? * MON-FRI *) (5:30pm ET)
- [ ] Document EventBridge status

### Checkpoint 5.7: Verify S3 Buckets
- [ ] List buckets:
  - [ ] stocks-webapp-dev (frontend)
  - [ ] stocks-code (deployment artifacts)
  - [ ] stocks-data-loading (data staging)
  - [ ] stocks-lambda-artifacts (Lambda code)
  - [ ] stocks-terraform-state (terraform backend)
- [ ] Verify versioning enabled on terraform-state bucket
- [ ] Document S3 status

### Checkpoint 5.8: Verify CloudFront Distribution
- [ ] Check CloudFront distribution:
  - [ ] Status: Deployed
  - [ ] Origin: S3 bucket for frontend
  - [ ] Caching: Enabled
- [ ] Verify Origin Access Control:
  - [ ] Should be created by terraform
  - [ ] Should be properly linked
- [ ] Document CloudFront status

### Checkpoint 5.9: Verify API Gateway
- [ ] Check API Gateway:
  - [ ] Name: stocks-api
  - [ ] Stage: dev
  - [ ] Status: Active
- [ ] List routes:
  - [ ] /api/stocks/*
  - [ ] /api/signals/*
  - [ ] /api/portfolio/*
- [ ] Document API Gateway status

### Checkpoint 5.10: Verify CloudWatch Logs
- [ ] Check log groups created:
  - [ ] /aws/lambda/stocks-api-dev
  - [ ] /aws/lambda/stocks-algo-dev
  - [ ] /ecs/stocks-cluster
  - [ ] /aws/rds/instance/stocks-db/postgresql
- [ ] Verify retention is set
- [ ] Document CloudWatch status

---

## PHASE 6: FINAL VERIFICATION & DOCUMENTATION

### Checkpoint 6.1: Create Final Status Report
- [ ] Document all resources created
- [ ] List all IAM roles with new names
- [ ] Verify terraform state is consistent
- [ ] Take final screenshot of AWS console showing clean state
- [ ] Document completion date and time

### Checkpoint 6.2: Update Memory
- [ ] Update memory/aws_deployment_state_2026_05_08.md with:
  - [ ] All new IAM role names
  - [ ] Deployment completion time
  - [ ] All stacks deployed
  - [ ] No more blocking resources
- [ ] Update MEMORY.md index
- [ ] Commit memory updates

### Checkpoint 6.3: Update CLAUDE.md
- [ ] Note: Terraform blocking resources fixed
- [ ] Add link to TERRAFORM_BLOCKING_RESOURCES_FIX.md
- [ ] Update any related references
- [ ] Commit CLAUDE.md update

### Checkpoint 6.4: Create Summary Commit
- [ ] All changes committed to git
- [ ] All workflows completed successfully
- [ ] All resources created and verified
- [ ] Final push to main branch
- [ ] Document final commit hash

### Checkpoint 6.5: Declare Success
- [ ] All 11 IAM roles deleted ✅
- [ ] All CloudFront OACs deleted ✅
- [ ] Terraform code updated ✅
- [ ] Full infrastructure deployed ✅
- [ ] All systems verified ✅
- [ ] No blocking resources remain ✅

---

## SIGN-OFF

**Executed by:** _________________
**Date Completed:** _________________
**Time Spent:** _________________
**Issues Encountered:** None / [List any]
**Rollback Needed:** No / Yes (document if yes)
**Production Ready:** ✅ YES

---

## NOTES

Document any notes, observations, or learnings below:


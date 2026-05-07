# Terraform Deployment Guide — Clean Infrastructure

## Problem We Solved

**Root Cause of VPC Accumulation:**
When Terraform deployments failed or were incomplete, they left orphaned AWS resources (VPCs, subnets, security groups) without proper state tracking. These accumulated until hitting the 5 VPC limit.

**Why It Happened:**
1. Module dependencies were hard-coded without conditionals
2. When `create_vpc=false` (reusing existing VPCs), the core module wouldn't deploy
3. Other modules tried to reference `module.core[0]` which didn't exist
4. This caused cascading failures, leaving partially created resources

## Fixes Applied

### 1. Fixed Terraform Module Dependencies
**File:** `terraform/main.tf`
- Changed: `depends_on = [module.core[0]]` 
- To: `depends_on = var.create_vpc ? [module.core[0]] : []`
- **Effect:** Modules only depend on other modules if those modules are actually created

### 2. Made Security Group Variables Optional
**File:** `terraform/modules/data_infrastructure/variables.tf`
- Changed `rds_sg_id` and `ecs_tasks_sg_id` from required strings to `optional(string)`
- **Effect:** Can pass `null` when core module doesn't create them

### 3. Added Fallback Security Group Creation
**File:** `terraform/modules/data_infrastructure/main.tf`
- Added automatic SG creation if not provided from core module
- **Effect:** data_infrastructure module is now self-contained and works with or without core module

### 4. Added Concurrency Control
**File:** `.github/workflows/deploy-terraform.yml`
- Added: `concurrency: { group: terraform-deploy, cancel-in-progress: false }`
- **Effect:** Only one Terraform deployment can run at a time (prevents state lock conflicts)

### 5. Fixed VPC Deletion Script
**File:** `delete-old-vpcs.sh`
- Fixed RDS/ElastiCache filtering to only target resources in specific VPC
- Fixed VPC peering/VPN to target only resources related to target VPC
- Fixed EIP filtering by VPC association
- Improved security group rule revocation using Python for reliability
- Added better error diagnostics

## Proper Deployment Sequence

### Fresh Deployment (create_vpc=true) — RECOMMENDED
```bash
# From main branch with all fixes in place
git push origin main
# This triggers deploy-terraform.yml which:
# 1. Creates new VPC
# 2. Creates core infrastructure (ECR, S3, security groups)
# 3. Creates data infrastructure (RDS, ECS, Secrets Manager)
# 4. Creates loaders, webapp, algo modules
```

### Never Do This
```bash
# ❌ Manual VPC deletion followed by Terraform deploy
# → Orphans resources, breaks state tracking

# ❌ Setting create_vpc=false without proper existing resources
# → Terraform fails, leaves partials behind

# ❌ Deploying with VPC limit already at 5 using VPC reuse logic
# → Causes module reference errors and failures
```

## Emergency VPC Cleanup (If Needed)

Only after fixing Terraform code:
```bash
# Trigger the cleanup workflow
gh workflow run delete-vpcs.yml

# This will:
# 1. List non-default VPCs
# 2. Delete all AWS resources in each VPC in proper order
# 3. Report which VPCs successfully deleted
# 4. Show diagnostics for any blockers remaining

# View logs to see what's blocking deletion
# Fix those resources manually if needed
```

## Prevention Going Forward

### Never Reuse VPCs
The current Terraform design supports VPC reuse (`create_vpc=false`) but it's fragile:
- Requires existing subnets, routes, security groups
- Core module doesn't deploy, breaking dependency chain
- Any failure leaves orphaned resources

**Recommendation:** Always create fresh infrastructure. Cost of VPC cleanup when limit is hit is lower than supporting VPC reuse logic.

### Always Use Terraform for Cleanup
- Never delete AWS resources manually
- Let Terraform manage dependencies (`terraform destroy`)
- If Terraform state is lost, use `terraform import` to recover

### State Lock Management
- Terraform uses DynamoDB lock table: `terraform-lock-us-east-1`
- If locks persist (dead deployment), manually delete lock records
- Never use `terraform apply -lock=false` except for `import` operations

## Deployment Checklist

Before deploying:
- [ ] All Terraform modules have conditional `depends_on`
- [ ] No hard-coded module references (e.g., `module.core[0]` without `create_vpc` check)
- [ ] Concurrency group set in workflow
- [ ] GitHub secrets configured: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_ACCOUNT_ID`
- [ ] No other Terraform deployments in progress (concurrency prevents this)
- [ ] Branch is up to date with main: `git pull origin main`

After deployment:
- [ ] All stacks deployed successfully (check CloudFormation console)
- [ ] Terraform state file has complete resource list: `terraform state list | wc -l`
- [ ] VPC count below limit: `aws ec2 describe-vpcs --query 'length(Vpcs)' --output text` (should be < 5)

## Troubleshooting

### "Error acquiring the state lock"
**Cause:** Previous deployment crashed and left lock
**Fix:** 
```bash
# Check lock
aws dynamodb scan --table-name terraform-lock-us-east-1 --region us-east-1

# Delete lock (ONLY if deployment is truly dead)
aws dynamodb delete-item --table-name terraform-lock-us-east-1 \
  --key '{"LockID": {"S": "stocks/terraform.tfstate"}}' --region us-east-1

# Retry deployment
gh workflow run deploy-terraform.yml
```

### "No module named 'core'"
**Cause:** Referencing `module.core[0]` when `create_vpc=false`
**Fix:** Check main.tf - all module references must be conditional

### VPC deletion still failing
**Cause:** Some AWS resource type not handled in cleanup script
**Check logs:** `gh run view <run_id> --log | grep "⚠️"`
**Fix:** Add cleanup step for that resource type to `delete-old-vpcs.sh`

## Architecture After Fixes

```
Deployment Flow (create_vpc=true):
├── Bootstrap (OIDC - optional, once-only)
└── Core (VPC, ECR, S3, Subnets, Security Groups)
    ├── Data Infrastructure (RDS, ECS, Secrets)
    │   ├── Loaders (Task Definitions)
    │   ├── Webapp (Lambda, CloudFront)
    │   └── Algo (Lambda Scheduler)

Reuse Flow (create_vpc=false):
├── [No Core]
└── Data Infrastructure (creates own security groups)
    ├── Loaders
    ├── Webapp
    └── Algo

Cleanup Flow:
├── Loaders (delete tasks)
├── Webapp (delete Lambda, CloudFront)
├── Algo (delete Lambda)
├── Data Infrastructure (delete RDS, ECS)
├── Core (delete VPC resources)
└── [Manual: Delete VPCs via delete-vpcs.sh if needed]
```

---

**Last Updated:** 2026-05-07
**Status:** Ready for deployment with all dependency fixes applied

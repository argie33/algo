# Terraform Module Dependencies & Variable Flow

**This document shows exactly what each module needs from others. When things break, check this first.**

## Dependency Chain (Top → Bottom = Deploy Order)

```
┌─────────────────────┐
│  1. BOOTSTRAP       │  Creates: OIDC provider, GitHub Actions role
│                     │  Exports: oidc_provider_arn, github_deploy_role_arn
│                     │  Depends On: Nothing
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  2. CORE            │  Creates: VPC, networking, S3, ECR
│                     │  Exports: 9 outputs (vpc_id, subnet_ids, ecr_uri, etc.)
│                     │  Depends On: Bootstrap (optional)
└──────────┬──────────┘
           │
           ├─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┐
           │                               │
           ▼                               ▼
┌─────────────────────┐        (parallel)
│  3. DATA_INFRA      │
│                     │  Creates: RDS, ECS, Secrets
│                     │  Exports: 8 outputs (db_endpoint, ecs_cluster_arn, etc.)
│                     │  Needs from Core:
│                     │  ├─ vpc_id
│                     │  ├─ private_subnet_ids
│                     │  └─ rds_sg_id
│                     │  
│                     │  Needs from Bootstrap: Nothing
└─────┬───┬───┬──────┘
      │   │   │
      ▼   ▼   ▼
    4A  4B  4C  (all parallel, all need data_infrastructure)

┌─────────────────────┐
│  4A. LOADERS        │  Creates: ECS task defs, EventBridge
│                     │  Needs from Core:
│                     │  ├─ ecr_repository_uri
│                     │  ├─ vpc_id
│                     │  └─ private_subnet_ids
│                     │  Needs from Data_Infrastructure:
│                     │  ├─ ecs_cluster_name
│                     │  ├─ ecs_cluster_arn
│                     │  ├─ db_secret_arn
│                     │  ├─ ecs_tasks_sg_id
│                     │  └─ task_execution_role_arn
└─────────────────────┘

┌─────────────────────┐
│  4B. WEBAPP         │  Creates: Lambda, API GW, CloudFront, Cognito
│                     │  Needs from Core:
│                     │  └─ code_bucket_name
│                     │  Needs from Data_Infrastructure:
│                     │  └─ db_secret_arn
└─────────────────────┘

┌─────────────────────┐
│  4C. ALGO           │  Creates: Lambda scheduler, EventBridge
│                     │  Needs from Core:
│                     │  ├─ algo_artifacts_bucket_name
│                     │  └─ code_bucket_name
│                     │  Needs from Data_Infrastructure:
│                     │  └─ db_secret_arn
└─────────────────────┘
```

---

## Variable Flow: What Each Module Provides

### BOOTSTRAP Outputs
```hcl
output "oidc_provider_arn"          = aws_iam_openid_connect_provider.github.arn
output "github_deploy_role_arn"     = aws_iam_role.github_actions.arn
output "github_deploy_role_name"    = aws_iam_role.github_actions.name
```

**Used By:** 
- Core (optional, for future OIDC)
- Loaders (if using OIDC)
- Webapp (if using OIDC)

---

### CORE Outputs (CRITICAL - Everything depends on these)
```hcl
output "vpc_id"                     = aws_vpc.main.id
output "public_subnet_ids"          = aws_subnet.public[*].id
output "private_subnet_ids"         = aws_subnet.private[*].id
output "ecr_repository_uri"         = aws_ecr_repository.main.repository_url
output "cf_templates_bucket_name"   = aws_s3_bucket.cf_templates.id
output "code_bucket_name"           = aws_s3_bucket.code.id
output "algo_artifacts_bucket_name" = aws_s3_bucket.algo_artifacts.id
output "bastion_sg_id"              = aws_security_group.bastion.id
output "vpce_sg_id"                 = aws_security_group.vpce.id
output "ecs_tasks_sg_id"            = aws_security_group.ecs_tasks.id
output "rds_sg_id"                  = aws_security_group.rds.id
```

**Used By:**
- Data_Infrastructure: vpc_id, private_subnet_ids, rds_sg_id
- Loaders: ecr_repository_uri, vpc_id, private_subnet_ids
- Webapp: code_bucket_name
- Algo: algo_artifacts_bucket_name, code_bucket_name

---

### DATA_INFRASTRUCTURE Outputs (CRITICAL - Loaders/Webapp/Algo depend on these)
```hcl
output "db_endpoint"                = aws_db_instance.main.address
output "db_port"                    = aws_db_instance.main.port
output "db_name"                    = aws_db_instance.main.db_name
output "db_secret_arn"              = aws_secretsmanager_secret.db_secret.arn
output "ecs_cluster_name"           = aws_ecs_cluster.main.name
output "ecs_cluster_arn"            = aws_ecs_cluster.main.arn
output "task_execution_role_arn"    = aws_iam_role.ecs_task_execution_role.arn
output "ecs_tasks_sg_id"            = ??? (NOT EXPORTED - FIX THIS!)
output "sns_topic_arn"              = aws_sns_topic.alerts.arn
```

**ISSUE: ecs_tasks_sg_id output is wrong in current code. Shows: `"var.ecs_tasks_sg_id"` instead of actual security group ID.**

---

### LOADERS Outputs
```hcl
output "state_machine_arn"  = (placeholder - needs Step Functions)
```

**Provides:** EventBridge scheduled rules for loaders

**Note:** This module is skeleton. Needs implementation.

---

### WEBAPP Outputs
```hcl
output "api_endpoint"              = (Lambda URL)
output "cloudfront_domain"         = (CloudFront domain)
output "website_url"               = (Public website URL)
output "cognito_user_pool_id"      = (User pool ID)
output "cognito_client_id"         = (Client ID)
output "frontend_bucket_name"      = aws_s3_bucket.frontend.id
```

**Provides:** Cognito credentials for frontend

**Note:** This module is skeleton. Needs implementation.

---

### ALGO Outputs
```hcl
output "lambda_arn"         = (Lambda function ARN)
output "schedule_arn"       = (EventBridge rule ARN)
output "alert_topic_arn"    = (SNS topic ARN)
```

**Provides:** Orchestrator function

**Note:** This module is skeleton. Needs implementation.

---

## Variable Passing: How Data Flows Through

### Example 1: Core → Data_Infrastructure
```hcl
# Root main.tf
module "data_infrastructure" {
  source = "./modules/data_infrastructure"
  
  vpc_id                = module.core[0].vpc_id              ← Core exports this
  private_subnet_ids    = module.core[0].private_subnet_ids  ← Core exports this
  rds_sg_id             = ???                                 ← Core.outputs says "rds_sg_id" exists
}

# data_infrastructure/variables.tf
variable "vpc_id" { type = string }
variable "private_subnet_ids" { type = list(string) }
variable "rds_sg_id" { type = string }

# data_infrastructure/main.tf
resource "aws_rds_instance" "main" {
  vpc_security_group_ids = [var.rds_sg_id]  ← Uses the variable
}
```

### Example 2: Data_Infrastructure → Loaders
```hcl
# Root main.tf
module "loaders" {
  source = "./modules/loaders"
  
  ecs_cluster_name          = module.data_infrastructure[0].ecs_cluster_name
  ecs_cluster_arn           = module.data_infrastructure[0].ecs_cluster_arn
  db_secret_arn             = module.data_infrastructure[0].db_secret_arn
  task_execution_role_arn   = module.data_infrastructure[0].task_execution_role_arn
  ecs_tasks_sg_id           = module.data_infrastructure[0].ecs_tasks_sg_id  ← BROKEN!
}

# loaders/variables.tf
variable "ecs_cluster_name" { type = string }
variable "db_secret_arn" { type = string; sensitive = true }
variable "ecs_tasks_sg_id" { type = string }

# loaders/main.tf
resource "aws_cloudwatch_event_target" "market_indices" {
  ecs_target {
    cluster        = var.ecs_cluster_name      ← Uses the variable
    task_definition = aws_ecs_task_definition.market_indices.arn
  }
}
```

---

## Known Issues to Fix

### Issue 1: data_infrastructure outputs.tf has wrong ecs_tasks_sg_id
**File:** `terraform/modules/data_infrastructure/outputs.tf`
**Line:** 29
**Current:** `output "ecs_tasks_sg_id" { value = "var.ecs_tasks_sg_id" }`
**Should be:** `output "ecs_tasks_sg_id" { value = ??? }`

**Problem:** We import ecs_tasks_sg_id as a variable, but should it come from Core or be created here?
**Solution:** Check if we should create it or import it from Core.

### Issue 2: Missing rds_sg_id in data_infrastructure/variables.tf
**File:** `terraform/modules/data_infrastructure/variables.tf`
**Problem:** main.tf passes rds_sg_id from core, but it's not defined as a variable
**Solution:** Add `variable "rds_sg_id" { type = string }`

### Issue 3: Loaders module ecs_tasks_sg_id source unclear
**File:** `terraform/modules/loaders/main.tf`
**Problem:** Uses var.ecs_tasks_sg_id but unclear if it's created or imported
**Solution:** Clarify where this comes from

---

## Cross-Module References Checklist

When a module needs something from another, verify:

- [ ] **Export exists:** Is it in the source module's outputs.tf?
- [ ] **Variable defined:** Is it in the target module's variables.tf?
- [ ] **Passed correctly:** Is it passed in main.tf with correct syntax?
- [ ] **Type matches:** Is the type (string/list/map) consistent?
- [ ] **Index correct:** If conditional deploy, is [0] in the right place?
- [ ] **Sensitive marked:** If it's a secret, is sensitive = true on both sides?

---

## Testing Variable Flow

### Test 1: Check Core exports exist
```bash
grep -n "output" terraform/modules/core/outputs.tf
# Should see: vpc_id, ecr_repository_uri, code_bucket_name, algo_artifacts_bucket_name, etc.
```

### Test 2: Check Data_Infrastructure imports them
```bash
grep -n "module.core\[0\]" terraform/main.tf
# Should see references like: module.core[0].vpc_id
grep -n "variable \"vpc_id\"" terraform/modules/data_infrastructure/variables.tf
# Should see: variable "vpc_id" { type = string }
```

### Test 3: Check Data_Infrastructure exports to Loaders
```bash
grep -n "output" terraform/modules/data_infrastructure/outputs.tf
# Should see: ecs_cluster_name, ecs_cluster_arn, db_secret_arn
grep -n "module.data_infrastructure\[0\]" terraform/main.tf
# Should see references in loaders module
grep -n "variable \"ecs_cluster_name\"" terraform/modules/loaders/variables.tf
# Should see: variable "ecs_cluster_name" { type = string }
```

---

## When Module Deployment Fails

### Step 1: Identify the module
```
Error in module "loaders" means the loaders module failed
Error in module "data_infrastructure" means data_infra failed
```

### Step 2: Check what it needed from previous module
```
Q: What does loaders need?
A: ecs_cluster_name, ecs_cluster_arn, db_secret_arn, task_execution_role_arn, ecs_tasks_sg_id

Q: Where does it get them?
A: module.data_infrastructure[0].XXXXX

Q: Did data_infrastructure deploy successfully?
A: Check if ecs_cluster_arn exists in AWS
```

### Step 3: Verify the reference chain
```
loaders needs ecs_cluster_arn
← Passed from data_infrastructure[0].ecs_cluster_arn
← Defined in data_infrastructure/outputs.tf as aws_ecs_cluster.main.arn
← Created by aws_ecs_cluster resource in data_infrastructure/main.tf
← Uses variables from data_infrastructure/variables.tf
```

If any link is broken, the whole chain fails.

---

## "Can't Reference Each Other" Prevention

### Rule 1: No Circular Dependencies
```
WRONG:
module "a" { depends_on = [module.b] }
module "b" { depends_on = [module.a] }

RIGHT:
module "a" { }
module "b" { depends_on = [module.a] }
module "c" { depends_on = [module.b] }
```

### Rule 2: All References Must Be Exported
```
WRONG:
resource "aws_vpc" "main" { ... }
# No output defined

# Root tries to use it:
module.core[0].vpc_id  ← ERROR: output doesn't exist!

RIGHT:
resource "aws_vpc" "main" { ... }
output "vpc_id" { value = aws_vpc.main.id }

# Root uses it:
module.core[0].vpc_id  ← OK: output exists!
```

### Rule 3: All Imported Variables Must Be Defined
```
WRONG:
# loaders/main.tf uses var.ecs_cluster_name
# But loaders/variables.tf doesn't define it

RIGHT:
# loaders/variables.tf
variable "ecs_cluster_name" { type = string }

# loaders/main.tf
resource ... { name = var.ecs_cluster_name }
```

### Rule 4: Types Must Match
```
WRONG:
# data_infrastructure/outputs.tf
output "db_port" { value = aws_db_instance.main.port }  ← number type

# loaders/variables.tf
variable "db_port" { type = string }  ← expects string!

RIGHT: Keep types consistent
```

---

## Quick Sanity Checks

Before deploying, verify:

```bash
# 1. All modules have outputs.tf
ls terraform/modules/*/outputs.tf

# 2. All modules have variables.tf
ls terraform/modules/*/variables.tf

# 3. No typos in module references
grep -o "module\.[a-z_]*\[0\]\.[a-z_]*" terraform/main.tf

# 4. All referenced outputs exist
# Grep module.X[0].Y and verify Y is in module X's outputs.tf

# 5. All variables are defined
# Grep var.X and verify X is in variables.tf
```

---

## When We Debug Live

I'll check:
1. ✅ Which module failed to deploy?
2. ✅ What error did it throw?
3. ✅ What was it trying to create?
4. ✅ What variables did it need?
5. ✅ Did the previous module export those variables?
6. ✅ Is the reference syntax correct?
7. ✅ Does the type match?

Then:
- Edit the Terraform code to fix
- `git push` triggers new workflow
- Monitor the fix

---

**Status:** Dependencies documented. Ready to debug.
**Next:** Deploy and watch for reference issues.

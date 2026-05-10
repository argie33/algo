# Terraform Infrastructure Review - Comprehensive Audit

**Date:** 2026-05-08  
**Status:** Multiple critical and high-priority issues identified  
**Blockers:** 6 critical issues must be fixed before deployment

---

## Critical Issues (Block Deployment)

### 1. ⚠️ CRITICAL: Terraform State Bucket ARN Mismatch
**Location:** `terraform/modules/bootstrap/main.tf:149-150`  
**Severity:** CRITICAL - Breaks Terraform state management  
**Problem:**
```hcl
# Bootstrap creates this:
resource "aws_s3_bucket" "terraform_state" {
  bucket = "${var.project_name}-terraform-state-${var.environment}"
}

# But IAM policy references:
"arn:aws:s3:::terraform-state-${var.aws_account_id}"
"arn:aws:s3:::terraform-state-${var.aws_account_id}/*"
```
**Impact:** GitHub Actions cannot access Terraform state. Deployments will fail immediately.

**Fix:**
```hcl
# In bootstrap/main.tf policy, line 149-150:
"arn:aws:s3:::${var.project_name}-terraform-state-${var.environment}",
"arn:aws:s3:::${var.project_name}-terraform-state-${var.environment}/*"
```

---

### 2. ⚠️ CRITICAL: DynamoDB Lock Table Name Mismatch
**Location:** `terraform/modules/bootstrap/main.tf:162`  
**Severity:** CRITICAL - State locking will fail  
**Problem:**
```hcl
# Bootstrap creates:
name = "${var.project_name}-terraform-locks"  # e.g., "stocks-terraform-locks"

# But policy references:
"arn:aws:dynamodb:*:${var.aws_account_id}:table/terraform-state-lock"
```
**Impact:** GitHub Actions cannot acquire state locks, causing concurrent apply failures.

**Fix:**
```hcl
# Line 162 in bootstrap/main.tf policy:
"arn:aws:dynamodb:${var.aws_region}:${var.aws_account_id}:table/${var.project_name}-terraform-locks"
```

---

### 3. ⚠️ CRITICAL: Duplicate GitHub OIDC Provider & Role Definitions
**Location:** `terraform/main.tf:5-15` vs `terraform/modules/bootstrap/main.tf:80-127`  
**Severity:** CRITICAL - Resource conflicts  
**Problem:**
- Bootstrap module creates OIDC provider: `aws_iam_openid_connect_provider.github`
- IAM module tries to DATA source it: `data "aws_iam_openid_connect_provider" "github_existing"`
  - But data source has no error handling if it doesn't exist
  - If bootstrap fails, IAM module fails
- Bootstrap creates role: `github_actions` with `svc-github-actions-deploy`
- IAM module creates role: `github_actions` with `svc-github-actions`
  - Different names, but both claim to be the GitHub Actions role
  - Root module passes IAM module's role to services

**Impact:** 
- If bootstrap runs first: creates provider, IAM module data source succeeds
- If IAM module runs first (or bootstrap fails): terraform apply hangs trying to find non-existent data source
- Creates two separate GitHub Actions roles with different permissions
- Unclear which one is actually used by GitHub Actions

**Fix:**
Option A (Recommended): Move OIDC provider to IAM module with conditional creation:
```hcl
# In terraform/modules/iam/main.tf
resource "aws_iam_openid_connect_provider" "github" {
  count           = var.create_github_oidc ? 1 : 0
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [
    "6938fd4d98bab03faadb97b34396831e3780aea1",
    "1b511abead59c6ce207077c0bf4113469e1f0b03"
  ]
}

# Then reference it:
principals {
  identifiers = [
    var.create_github_oidc ? aws_iam_openid_connect_provider.github[0].arn : 
    "arn:aws:iam::${var.aws_account_id}:oidc-provider/token.actions.githubusercontent.com"
  ]
}
```

---

### 4. ⚠️ CRITICAL: Lambda Role Duplication
**Location:** `terraform/modules/iam/main.tf:603-650` vs `terraform/modules/services/main.tf:21-77`  
**Severity:** CRITICAL - Resource conflicts and unclear permissions  
**Problem:**
- IAM module defines `aws_iam_role.lambda_api` (lines 603-650)
- Services module redefines `aws_iam_role.api_lambda` (lines 21-40)
- They use different naming conventions and may have conflicting policies
- Root main.tf passes `module.iam.lambda_api_role_arn` to services, but services creates its own

**Impact:** 
- Services module's role shadows IAM module's role
- Unclear which role is actually attached to the Lambda
- Duplicate policies may conflict
- Maintenance nightmare

**Fix:** Choose one source. Recommendation: Keep roles in IAM module only:
1. Remove `aws_iam_role.api_lambda` from services/main.tf (lines 21-40)
2. Services module receives role ARN as variable from IAM module
3. Services module only attaches policies to inherited role ARN

---

### 5. ⚠️ CRITICAL: Missing Lambda Permission for API Gateway
**Location:** `terraform/modules/services/main.tf:193-199`  
**Severity:** CRITICAL - API Gateway cannot invoke Lambda  
**Problem:**
```hcl
resource "aws_apigatewayv2_integration" "api_lambda" {
  api_id           = aws_apigatewayv2_api.main.id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.api.invoke_arn
}
# MISSING: aws_lambda_permission for API Gateway!
```

**Impact:** API Gateway will return 403 Forbidden even if Lambda is working correctly.

**Fix:** Add after line 199:
```hcl
resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}
```

---

### 6. ⚠️ CRITICAL: Missing NAT Gateway for Private Subnets
**Location:** `terraform/modules/vpc/main.tf:84-98`  
**Severity:** CRITICAL - Private resources cannot reach internet  
**Problem:**
```hcl
resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id
  # NO ROUTES TO INTERNET
}
```

**Impact:** 
- Lambda in private subnets: cannot call external APIs, fetch packages from PyPI, etc.
- ECS tasks in private subnets: cannot pull images from external registries (even with VPC endpoints, they need internet for auth)
- RDS: cannot reach external services
- ANY outbound internet traffic will fail

**Fix:** Add NAT Gateway or NAT Instance:
```hcl
# Allocate Elastic IP for NAT
resource "aws_eip" "nat" {
  count  = length(var.public_subnet_cidrs)
  domain = "vpc"
  tags = merge(var.common_tags, { Name = "${var.project_name}-nat-eip-${count.index + 1}" })
}

# NAT Gateway in public subnet
resource "aws_nat_gateway" "main" {
  count         = length(var.public_subnet_cidrs)
  allocation_id = aws_eip.nat[count.index].id
  subnet_id     = aws_subnet.public[count.index].id
  tags = merge(var.common_tags, { Name = "${var.project_name}-nat-${count.index + 1}" })
  depends_on = [aws_internet_gateway.main]
}

# Route from private to NAT
resource "aws_route" "private_nat" {
  route_table_id         = aws_route_table.private.id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.main[0].id
}
```

---

## High-Priority Issues (Strongly Recommend Fix)

### 7. 🔴 HIGH: RDS Parameter Group Log Statement Set to "all"
**Location:** `terraform/modules/database/main.tf:98-100`  
**Severity:** HIGH - Security & Performance  
**Problem:**
```hcl
parameter {
  name  = "log_statement"
  value = "all" # Comment says "remove for prod"
}
```
**Impact:**
- Logs EVERY SQL statement, including those with sensitive data (passwords in queries)
- Massive CloudWatch Logs volume and cost
- Performance degradation from excessive logging
- Compliance violation (logs may contain PII)

**Fix:**
```hcl
parameter {
  name  = "log_statement"
  value = var.rds_log_statement  # Set to "none" in prod via tfvars
}

# Add variable:
variable "rds_log_statement" {
  description = "PostgreSQL log_statement setting (all, none, ddl, mod)"
  type        = string
  default     = "none"
}
```

---

### 8. 🔴 HIGH: S3 Bucket Policy Uses Overly Broad Principal
**Location:** `terraform/modules/storage/main.tf:326-354`  
**Severity:** HIGH - Security  
**Problem:**
```hcl
"Principal": {
  "AWS": "*"  # ← ALLOWS ANYONE WITH SOURCE ACCOUNT
}
```
Even with the source account condition, this is too permissive.

**Fix:**
```hcl
"Principal": {
  "AWS": [
    aws_iam_role.ecs_task.arn,
    aws_iam_role.lambda_api.arn
  ]
}
```

---

### 9. 🔴 HIGH: Missing Bastion → RDS Security Group Rules
**Location:** `terraform/modules/vpc/main.tf:151-158`  
**Severity:** HIGH - Cannot debug database  
**Problem:**
The RDS security group allows PostgreSQL from ECS tasks and Bastion, but only if Bastion is enabled. If Bastion is disabled, there's no way to debug database issues.

**Fix:** Keep bastion rules but make them clearer:
```hcl
# Allow from Bastion if enabled
dynamic "ingress" {
  for_each = var.bastion_sg_enabled ? [1] : []
  content {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.bastion[0].id]
    description     = "PostgreSQL from Bastion (for debugging)"
  }
}
```

---

### 10. 🟡 MEDIUM: KMS Endpoint Missing
**Location:** `terraform/modules/vpc/main.tf` (missing)  
**Severity:** MEDIUM - Services cannot decrypt secrets  
**Problem:**
VPC has endpoints for Secrets Manager, but no KMS endpoint. Services in private subnets will need to traverse internet to reach KMS for decryption.

**Fix:**
```hcl
resource "aws_vpc_endpoint" "kms" {
  vpc_id              = aws_vpc.main.id
  service_name        = "com.amazonaws.${var.aws_region}.kms"
  vpc_endpoint_type   = "Interface"
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  subnet_ids          = aws_subnet.private[*].id
  private_dns_enabled = true

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-kms-endpoint"
  })
}
```

---

## Medium-Priority Issues (Should Fix)

### 11. 🟡 MEDIUM: API Lambda Created Without Actual Code
**Location:** `terraform/modules/services/main.tf:122-131`  
**Severity:** MEDIUM - Placeholder will break in production  
**Problem:**
```hcl
data "archive_file" "api_lambda" {
  source {
    content = "import json\ndef handler(event, context):\n    return {'statusCode': 200...}"
    filename = "index.py"
  }
}
```
A placeholder Python handler is embedded. Production deployments will override this, but it creates confusion.

**Fix:** Document that actual code must be deployed separately:
```hcl
# Either use data source from actual code file:
data "archive_file" "api_lambda" {
  type        = "zip"
  source_dir  = "${path.root}/../src/api-lambda"  # Real code
  output_path = "${path.module}/.terraform_api_lambda.zip"
}

# Or require code as module input
variable "api_lambda_code_path" {
  description = "Path to API Lambda code directory"
  type        = string
}
```

---

### 12. 🟡 MEDIUM: Incomplete API Gateway Configuration
**Location:** `terraform/modules/services/main.tf:176-199`  
**Severity:** MEDIUM - API Gateway not fully wired  
**Problem:**
- Creates API Gateway but no routes defined
- No stage configuration
- No API key or throttling
- CloudWatch logging not enabled

**Fix:** Add:
```hcl
# Create default route
resource "aws_apigatewayv2_route" "default" {
  api_id             = aws_apigatewayv2_api.main.id
  route_key          = "ANY /{proxy+}"
  target             = "integrations/${aws_apigatewayv2_integration.api_lambda.id}"
}

# Create stage
resource "aws_apigatewayv2_stage" "main" {
  api_id      = aws_apigatewayv2_api.main.id
  name        = var.api_gateway_stage_name
  auto_deploy = true
  
  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_gateway.arn
    format = jsonencode({
      requestId      = "$context.requestId"
      ip             = "$context.identity.sourceIp"
      requestTime    = "$context.requestTime"
      httpMethod     = "$context.httpMethod"
      resourcePath   = "$context.resourcePath"
      status         = "$context.status"
      protocol       = "$context.protocol"
      responseLength = "$context.responseLength"
    })
  }
  
  throttle_settings {
    rate_limit  = 2000
    burst_limit = 5000
  }
}
```

---

### 13. 🟡 MEDIUM: VPC Endpoint Security Group Overly Restrictive
**Location:** `terraform/modules/vpc/main.tf:188-215`  
**Severity:** MEDIUM - May block legitimate traffic  
**Problem:**
```hcl
# Only allows from VPC CIDR (443)
ingress {
  from_port   = 443
  to_port     = 443
  protocol    = "tcp"
  cidr_blocks = [aws_vpc.main.cidr_block]
}
```
This assumes all services are within the VPC CIDR range. Lambda cold starts in private subnets with ENI creation might fail.

**Fix:** Allow from security groups instead:
```hcl
# From ECS tasks
ingress {
  from_port       = 443
  to_port         = 443
  protocol        = "tcp"
  security_groups = [aws_security_group.ecs_tasks.id]
  description     = "From ECS tasks"
}

# From Lambda (same SG as ECS tasks)
# Already covered above since both use ecs_tasks SG
```

---

### 14. 🟡 MEDIUM: Missing CloudFormation Namespace in Bootstrap
**Location:** `terraform/modules/bootstrap/main.tf:148-151`  
**Severity:** MEDIUM - State management confusion  
**Problem:**
Bootstrap policy references:
```hcl
"arn:aws:s3:::terraform-state-${var.aws_account_id}"
```
But actual bucket is:
```hcl
bucket = "${var.project_name}-terraform-state-${var.environment}"
```

Also, CLAUDE.md mentions "CloudFormation deployment" but this is pure Terraform. Need clarity on whether CloudFormation is actually used.

**Fix:** Verify in CLAUDE.md - if CloudFormation is not used, remove those references from bootstrap policy.

---

### 15. 🟡 MEDIUM: Missing Versions Lock for Providers
**Location:** `terraform/versions.tf:8-12`  
**Severity:** MEDIUM - Reproducibility  
**Problem:**
```hcl
aws = {
  source  = "hashicorp/aws"
  version = "~> 5.0"  # Allows 5.0 to 5.99.x
}
```
This allows provider version drift. Better to pin to specific version or use `>= 5.0, < 6.0`.

**Fix:**
```hcl
version = ">= 5.0, < 6.0"
# Or even better, pin to minor:
version = "~> 5.40"  # Allows patch updates only
```

---

## Low-Priority Issues (Nice to Have)

### 16. 🟢 LOW: Missing Outputs Documentation
**Severity:** LOW - Operational  
**Problem:** Root outputs.tf exists but doesn't export important values (RDS endpoint, API endpoint, etc.)

**Fix:** Export:
```hcl
output "rds_endpoint" {
  value = module.database.rds_endpoint
}

output "api_endpoint" {
  value = module.services.api_endpoint
}

output "frontend_bucket" {
  value = module.storage.frontend_bucket_name
}
```

---

### 17. 🟢 LOW: Inconsistent Resource Naming
**Severity:** LOW - Code clarity  
**Problem:**
- Bootstrap uses `svc-github-actions-deploy`
- IAM uses `svc-github-actions`
- Services uses `api_lambda` vs IAM uses `lambda_api`

**Fix:** Standardize on one naming convention across all modules.

---

### 18. 🟢 LOW: Missing Terraform Validation Errors
**Severity:** LOW - Prevention  
**Problem:** `terraform validate` doesn't catch the S3/DynamoDB name mismatches because they're in IAM policies, not resource references.

**Fix:** Add custom validation:
```hcl
variable "terraform_state_bucket_name" {
  description = "Terraform state bucket name"
  type        = string
  default     = ""  # Computed in locals
}

# Compute it once in locals.tf and reference everywhere
locals {
  terraform_state_bucket = "${var.project_name}-terraform-state-${var.environment}"
  terraform_locks_table  = "${var.project_name}-terraform-locks"
}
```

---

## Pre-Deployment Checklist

- [ ] **FIX CRITICAL:** Correct S3 bucket ARN in bootstrap policy
- [ ] **FIX CRITICAL:** Correct DynamoDB table name in bootstrap policy  
- [ ] **FIX CRITICAL:** Resolve OIDC provider duplication (bootstrap vs IAM module)
- [ ] **FIX CRITICAL:** Remove duplicate Lambda role from services module
- [ ] **FIX CRITICAL:** Add Lambda permission for API Gateway invocation
- [ ] **FIX CRITICAL:** Add NAT Gateway for private subnet internet access
- [ ] **FIX:** Change RDS log_statement from "all" to "none" for non-dev environments
- [ ] **FIX:** Add KMS VPC endpoint
- [ ] **FIX:** Complete API Gateway configuration (routes, stage, logging)
- [ ] **VERIFY:** Bootstrap module runs before main infrastructure
- [ ] **VERIFY:** GitHub OIDC provider is created exactly once
- [ ] **VERIFY:** All IAM roles have correct permissions scoped to resources
- [ ] **TEST:** Run `terraform validate` and `terraform fmt -check`
- [ ] **TEST:** Run `terraform plan` and review all proposed changes
- [ ] **TEST:** Verify Lambda can call API Gateway after deployment
- [ ] **TEST:** Verify private subnets have internet access via NAT

---

## Deployment Order

1. **Bootstrap phase** (one-time): Create Terraform state bucket and OIDC provider
2. **Main infrastructure**: All other modules
3. **Post-deployment**: Upload actual Lambda code, seed database, etc.

---

## Cost Impact

- Adding NAT Gateway: ~$45/month per NAT Gateway + data transfer costs
- Adding KMS endpoint: ~$7/month
- Increased CloudWatch logging (if RDS logging set to "all"): $1+/GB/month

**Estimated monthly increase:** ~$50 for 2 NAT Gateways + 1 KMS endpoint

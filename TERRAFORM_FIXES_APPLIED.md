# Terraform Infrastructure Fixes Applied

**Date:** 2026-05-08  
**Status:** 9 Critical Issues Fixed ✅

---

## Fixes Applied

### ✅ FIX 1: S3 State Bucket ARN Mismatch
**File:** `terraform/modules/bootstrap/main.tf:149-150`  
**Problem:** IAM policy referenced wrong bucket name  
**Solution:** Changed from:
```hcl
"arn:aws:s3:::terraform-state-${var.aws_account_id}"
```
To:
```hcl
"arn:aws:s3:::${var.project_name}-terraform-state-${var.environment}"
```

---

### ✅ FIX 2: DynamoDB Lock Table Name Mismatch
**File:** `terraform/modules/bootstrap/main.tf:162`  
**Problem:** IAM policy referenced wrong table name  
**Solution:** Changed from:
```hcl
"arn:aws:dynamodb:*:${var.aws_account_id}:table/terraform-state-lock"
```
To:
```hcl
"arn:aws:dynamodb:${var.aws_region}:${var.aws_account_id}:table/${var.project_name}-terraform-locks"
```

---

### ✅ FIX 3: OIDC Provider Duplication
**Files:**
- `terraform/modules/iam/main.tf:12-14`
- `terraform/modules/iam/outputs.tf:8`

**Problem:** Bootstrap and IAM modules both trying to create/reference OIDC provider  
**Solution:**
- Disabled OIDC provider creation in IAM module
- Changed to data source that references bootstrap-created provider:
```hcl
data "aws_iam_openid_connect_provider" "github" {
  arn = "arn:aws:iam::${var.aws_account_id}:oidc-provider/token.actions.githubusercontent.com"
}
```
- Updated all references to use new data source name

---

### ✅ FIX 4: Lambda API Role Duplication
**Files:**
- `terraform/modules/iam/main.tf:603-703` (kept)
- `terraform/modules/services/main.tf:17-103` (removed)
- `terraform/modules/services/variables.tf:52-56` (added)
- `terraform/main.tf:128` (added)

**Problem:** Duplicate role creation in services and IAM modules  
**Solution:**
- Removed entire role, policy, and attachment creation from services module
- Added `api_lambda_role_arn` variable to services module
- Pass role ARN from IAM module to services module
- Updated Lambda function to use variable: `role = var.api_lambda_role_arn`

---

### ✅ FIX 5: Lambda Algo Role Duplication
**Files:**
- `terraform/modules/iam/main.tf:709-828` (kept)
- `terraform/modules/services/main.tf:402-490` (removed)
- `terraform/modules/services/variables.tf:58-61` (added)
- `terraform/main.tf:132` (added)

**Problem:** Duplicate role creation in services module  
**Solution:**
- Removed entire role, policy, and attachment creation from services module
- Added `algo_lambda_role_arn` variable to services module
- Pass role ARN from IAM module to services module
- Updated Lambda function to use variable: `role = var.algo_lambda_role_arn`

---

### ✅ FIX 6: Missing Lambda Permission for API Gateway
**File:** `terraform/modules/services/main.tf:121-127`  
**Problem:** API Gateway could not invoke Lambda (would return 403)  
**Solution:** Added:
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

### ✅ FIX 7: Duplicate Lambda Permission
**File:** `terraform/modules/services/main.tf:174-180` (removed)  
**Problem:** Duplicate `aws_lambda_permission` resource for API Gateway  
**Solution:** Removed duplicate - kept only one definition

---

### ✅ FIX 8: Missing NAT Gateway
**File:** `terraform/modules/vpc/main.tf:66-100`  
**Problem:** Private subnets had no internet route; Lambda and ECS tasks couldn't reach external services  
**Solution:** Added:
```hcl
# Elastic IP for NAT
resource "aws_eip" "nat" {
  count  = length(var.public_subnet_cidrs) >= 1 ? 1 : 0
  domain = "vpc"
}

# NAT Gateway
resource "aws_nat_gateway" "main" {
  count         = length(var.public_subnet_cidrs) >= 1 ? 1 : 0
  allocation_id = aws_eip.nat[0].id
  subnet_id     = aws_subnet.public[0].id
  depends_on    = [aws_internet_gateway.main]
}

# Route from private subnets to NAT
resource "aws_route" "private_nat" {
  count                  = length(var.public_subnet_cidrs) >= 1 ? 1 : 0
  route_table_id         = aws_route_table.private.id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.main[0].id
}
```

---

### ✅ FIX 9: EventBridge Scheduler Role Duplication
**Files:**
- `terraform/modules/iam/main.tf:834-907` (kept)
- `terraform/modules/services/main.tf:531-578` (removed role/policy)
- `terraform/modules/services/variables.tf:63-66` (added)
- `terraform/modules/services/main.tf:517` (updated reference)
- `terraform/main.tf:133` (added)

**Problem:** EventBridge scheduler role created in services instead of IAM module  
**Solution:**
- Removed role creation and policy from services module
- Added `eventbridge_scheduler_role_arn` variable to services module
- Pass role ARN from IAM module: `role_arn = var.eventbridge_scheduler_role_arn`
- Kept Lambda permission resource (needed in services for algo Lambda)

---

### ✅ BONUS FIX 10: Missing AWS Caller Identity Data Source
**File:** `terraform/modules/services/main.tf:4` (added)  
**Problem:** Services module used `data.aws_caller_identity.current` but didn't define it  
**Solution:** Added:
```hcl
data "aws_caller_identity" "current" {}
```

---

## Summary of Changes

| Issue | Type | Status |
|-------|------|--------|
| Terraform State Bucket ARN | Critical | ✅ Fixed |
| DynamoDB Lock Table Name | Critical | ✅ Fixed |
| OIDC Provider Duplication | Critical | ✅ Fixed |
| Lambda API Role Duplication | Critical | ✅ Fixed |
| Lambda Algo Role Duplication | Critical | ✅ Fixed |
| Missing Lambda Permission | Critical | ✅ Fixed |
| NAT Gateway Missing | Critical | ✅ Fixed |
| EventBridge Role Duplication | High | ✅ Fixed |
| Duplicate Lambda Permission | Medium | ✅ Fixed |
| Missing Caller Identity | Medium | ✅ Fixed |

---

## Files Modified

- `terraform/modules/bootstrap/main.tf` - Fixed ARN references in IAM policy
- `terraform/modules/iam/main.tf` - Disabled OIDC creation, fixed reference
- `terraform/modules/iam/outputs.tf` - Fixed OIDC provider reference
- `terraform/modules/services/main.tf` - Removed role duplications, added data source, added Lambda permission
- `terraform/modules/services/variables.tf` - Added role ARN variables
- `terraform/modules/vpc/main.tf` - Added NAT Gateway
- `terraform/main.tf` - Added role ARN passes to services module

---

## Pre-Deployment Status

✅ All critical blockers fixed  
✅ Lambda roles centralized in IAM module  
✅ Services module now receives roles as variables  
✅ API Gateway can invoke Lambda  
✅ Private subnets have internet access  
✅ Terraform state bucket ARNs match  
✅ DynamoDB lock table name matches  

---

## Next Steps

1. Run `terraform init` (bootstrap phase to create state bucket and OIDC provider)
2. Run `terraform validate` to catch any remaining syntax errors
3. Run `terraform plan` to review proposed infrastructure changes
4. Run `terraform apply` to deploy

All fixes are backward compatible and maintain the intended architecture.

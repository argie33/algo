# AWS Cost Optimization Audit - algo

**Date**: 2026-06-13  
**Goal**: Identify and eliminate AWS waste  
**Current Setup**: Dev/staging environment, single RDS instance, Lambda APIs, ECS loaders, CloudFront

---

## QUICK WINS (Implement Immediately)

### 1. Reduce CloudWatch Log Retention ⭐⭐⭐
**Current**: 30 days for all logs  
**Recommended**: Tiered approach based on log type  

| Log Group | Current | Recommended | Savings |
|-----------|---------|------------|---------|
| ECS Cluster `/ecs/stocks-cluster` | 30 days | 7 days | ~$8-12/month |
| Lambda logs `/aws/lambda/*` | 30 days | 7 days | ~$5-8/month |
| RDS PostgreSQL logs | 30 days | 7 days | ~$3-5/month |
| API Gateway logs | 7 days | 7 days | ✓ Already optimized |
| Bastion SSM logs | 30 days | 7 days (if needed) | ~$2-3/month |
| Data freshness monitor | 30 days | 7 days | ~$2/month |

**Total Monthly Savings**: **$20-30/month** ($240-360/year)  
**Effort**: 5 minutes (update `terraform/variables.tf` line 798)

**Action**: Change `cloudwatch_log_retention_days` from 30 to 7 in terraform.tfvars or via Terraform variable.

```hcl
variable "cloudwatch_log_retention_days" {
  default = 7  # Was: 30
}
```

---

### 2. Disable VPC Endpoints (If Not Used) ⭐⭐⭐
**Current**: Enabled for S3, Secrets Manager, ECR, CloudWatch Logs, SNS, DynamoDB  
**Cost Per Endpoint**: $7.20/month per VPC endpoint + data transfer costs  
**Total Cost**: ~$43-50/month (6 endpoints × $7.20)

**When to Keep**:
- ✓ S3 endpoint (prevents NAT Gateway data charges for S3 access)
- ✓ Secrets Manager endpoint (security best practice for prod)
- ✓ DynamoDB endpoint (prevents NAT Gateway charges)

**When to Remove** (for dev/testing):
- ✗ ECR endpoint (use NAT Gateway instead, cheaper for dev)
- ✗ CloudWatch Logs endpoint (VPC doesn't require endpoint for CloudWatch)
- ✗ SNS endpoint (rarely used from ECS, not critical)

**Recommendation for Dev/Staging**: Disable all except S3 and Secrets Manager

**Savings**: ~$28-36/month ($336-432/year)  
**Effort**: Change terraform variable

```hcl
variable "enable_vpc_endpoints" {
  default = false  # Or create granular control per endpoint type
}
```

---

### 3. Disable Enhanced RDS Monitoring ⭐⭐
**Current**: 60-second granularity Enhanced Monitoring enabled  
**Cost**: ~$8-10/month per RDS instance  
**Impact**: Lose fine-grained OS metrics; CloudWatch native metrics (CPU, storage, connections) still available

**Recommendation**: Disable Enhanced Monitoring in dev (keep CloudWatch metrics only)

**Action**: In `terraform/modules/database/main.tf` line 105

```hcl
monitoring_interval = 0  # Was: 60
```

**Savings**: ~$8-10/month ($96-120/year)

---

### 4. Reduce API Gateway Log Retention (Minimal Logs)
**Current**: 7 days (already optimized)  
**Alternative**: Use CloudTrail instead of API Gateway logging if only need audit trail  
**Status**: Already good, no change needed

---

## MEDIUM PRIORITY (Review and Decide)

### 5. S3 Versioning Cost Trade-off ⭐⭐
**Current**: Versioning enabled on all S3 buckets  
**Cost**: Stores all versions of deleted/overwritten objects  
**Impact**: 
- `code-bucket` (90-day expiration): Moderate waste (~$2-3/month)
- `data-loading-bucket` (30-day expiration): Minimal waste (~$1-2/month)
- `frontend-bucket`: Minimal if static files don't change frequently

**Options**:
1. Keep versioning (current, safer)
2. Disable versioning on code/data buckets, keep frontend (recommended for cost)
3. Use Object Lock instead of versioning (adds cost)

**Recommendation**: Disable versioning on code-bucket and data-loading-bucket  
**Savings**: ~$3-5/month ($36-60/year)  
**Trade-off**: Can't recover previous versions if accidentally deleted

---

### 6. RDS Parameter Tuning
**Current Configuration Issues**:
- `statement_timeout = 900000ms` (15 minutes) is high for API requests
  - Problem: Slow queries hang entire connection pool
  - Should be per-request via `SET statement_timeout` instead

**Recommendation**: 
- Keep cluster default at `30000ms` (30s)
- API handler sets 30s per request
- Batch loaders can override to 5 minutes for their specific queries

**Potential Savings**: Small (~$0.5/month by preventing connection exhaustion)

---

### 7. Disable Unused Security Monitoring (If Dev)
**Current** (from terraform modules):
- CloudTrail: Tracks all API calls → CloudWatch Logs/S3
- GuardDuty: ~$5-10/month (threat detection)
- AWS Config: ~$1/month (compliance tracking)
- VPC Flow Logs: ~$5-10/month (network traffic logs)

**Recommendation for DEV**:
- ✓ Keep CloudTrail (minimal cost, essential for audit)
- ✗ Disable GuardDuty (unnecessary for dev)
- ✗ Disable AWS Config (not needed for dev)
- ✗ Disable VPC Flow Logs (for non-prod only)

**Savings**: ~$15-20/month ($180-240/year)  
**Effort**: Set variables to false

```hcl
guardduty_enabled     = false
aws_config_enabled    = false
vpc_flow_logs_enabled = false
```

---

## LOWER PRIORITY (Validate First)

### 8. RDS Instance Right-Sizing
**Current**: `db.t4g.small` (~$29/month)
**Alternative**: `db.t4g.micro` (~$12/month, if load supports)

**Risk**: t4g.micro has 1 vCPU and 1 GB memory. May not support:
- 24 concurrent loader connections
- API queries with 5000+ symbols

**Recommendation**: Keep t4g.small for now. If load analysis shows <50% CPU/memory, consider downgrade.

**Status**: Monitor and revisit after 2 weeks

---

### 9. RDS Backup Retention
**Current**: 30 days  
**Alternative**: 7 days for dev (30 days for prod)

**Cost per 1 GB-month**: ~$0.023  
**Impact**: Minimal (~$1-2/month savings)

**Recommendation**: Keep 30 days (good for disaster recovery testing)

---

### 10. Lambda Configuration
**Current**:
- API Lambda: 256 MB (good, well-sized)
- Algo Lambda: 512 MB (good)
- Bastion Stop Lambda: Minimal cost (~$0.01/month)
- No provisioned concurrency (good for cost)

**Status**: Well-optimized, no changes needed

---

### 11. ECS Spot Strategy
**Current**: 80% Fargate Spot, 20% on-demand (4:1 ratio)  
**Cost Savings**: ~40-50% vs pure on-demand

**Recommendation**: Keep. Already optimized.

---

## COST SUMMARY

### Quick Wins (Implement This Week)
| Item | Monthly Savings | Annual | Effort |
|------|-----------------|--------|--------|
| CloudWatch retention 30→7 days | $20-30 | $240-360 | 5 min |
| Disable 4 VPC endpoints | $28-36 | $336-432 | 10 min |
| Disable RDS Enhanced Monitoring | $8-10 | $96-120 | 5 min |
| **Subtotal** | **$56-76** | **$672-912** | **20 min** |

### Review & Decide
| Item | Monthly Savings | Annual | Effort |
|------|-----------------|--------|--------|
| Disable S3 versioning (2 buckets) | $3-5 | $36-60 | 10 min |
| Disable unused security monitoring | $15-20 | $180-240 | 10 min |
| **Subtotal** | **$18-25** | **$216-300** | **20 min** |

### **Total Potential Savings: $74-101/month ($888-1,212/year)**

---

## DETAILED IMPLEMENTATION STEPS

### Step 1: Reduce CloudWatch Retention (5 minutes)
**File**: `terraform/variables.tf` line 798

```hcl
# Change this:
variable "cloudwatch_log_retention_days" {
  default = 30

# To this:
variable "cloudwatch_log_retention_days" {
  default = 7
```

**Deploy**: 
```bash
terraform plan -var cloudwatch_log_retention_days=7
terraform apply
```

**Verification**: 
```bash
aws logs describe-log-groups --query 'logGroups[*].[logGroupName,retentionInDays]'
```

---

### Step 2: Disable Non-Critical VPC Endpoints (10 minutes)
**File**: `terraform/variables.tf` line 99

**Option A - Simple**: Disable all VPC endpoints
```hcl
variable "enable_vpc_endpoints" {
  default = false  # Was: true
}
```

**Option B - Granular** (Better): Update `terraform/modules/vpc/main.tf` to selectively create endpoints:

```hcl
# Keep only critical endpoints:
locals {
  vpc_endpoints = {
    s3 = var.enable_s3_endpoint              # true
    dynamodb = var.enable_dynamodb_endpoint  # true
    secretsmanager = var.enable_secrets_endpoint  # true (for Secrets Manager access)
  }
  
  # Remove from endpoints:
  # ecr.dkr (use NAT Gateway instead)
  # logs (VPC doesn't require it)
  # sns (rarely used)
}
```

**Deploy**:
```bash
terraform plan -var enable_vpc_endpoints=false
terraform apply
```

---

### Step 3: Disable RDS Enhanced Monitoring (5 minutes)
**File**: `terraform/modules/database/main.tf` line 105

```hcl
# Change this:
monitoring_interval = 60

# To this:
monitoring_interval = 0  # Disable, keep CloudWatch native metrics
```

**Deploy**:
```bash
terraform apply
```

**Verification**: CloudWatch metrics still available:
- CPUUtilization
- DatabaseConnections
- FreeableMemory
- ReadIOPS, WriteIOPS

---

### Step 4: Disable Security Monitoring (Dev Only) (10 minutes)
**File**: `terraform/variables.tf`

```hcl
variable "cloudtrail_enabled" {
  default = true   # Keep for audit trail
}

variable "guardduty_enabled" {
  default = false  # Disable: ~$5-10/month
}

variable "aws_config_enabled" {
  default = false  # Disable: ~$1/month
}

variable "vpc_flow_logs_enabled" {
  default = false  # Disable: ~$5-10/month
}
```

**Deploy**:
```bash
terraform plan \
  -var guardduty_enabled=false \
  -var aws_config_enabled=false \
  -var vpc_flow_logs_enabled=false
terraform apply
```

---

## IMPLEMENTATION TIMELINE

**Phase 1 (Today - HIGH IMPACT)**
- [ ] CloudWatch retention: 30→7 days
- [ ] Disable 4 VPC endpoints (or set enable_vpc_endpoints=false)
- [ ] Disable RDS Enhanced Monitoring
- **Expected savings**: $56-76/month

**Phase 2 (Next 7 days - REVIEW)**
- [ ] Disable S3 versioning on code/data buckets (keep on frontend)
- [ ] Disable unused security monitoring (GuardDuty, AWS Config, VPC Flow Logs)
- **Expected savings**: $18-25/month (if approved)

**Phase 3 (Ongoing - MONITOR)**
- [ ] Track RDS CPU/memory for 2 weeks before considering downgrade to t4g.micro
- [ ] Monitor Lambda invocation rates; consider consolidation if underutilized
- [ ] Review S3 storage trends monthly

---

## NOTES

1. **This is a DEV environment**: More aggressive cost-cutting is safe here. For production, keep redundancy and monitoring.

2. **VPC Endpoint Removal**: If you later need private access to AWS services, re-enable selectively.

3. **CloudWatch Logs**: 7-day retention is still sufficient for debugging recent issues. Older issues can be reviewed in CloudWatch Insights historical queries (if needed).

4. **No Functional Impact**: All these changes are infrastructure-only; no code changes needed.

5. **Automated**: All changes via Terraform; can be reverted easily.

---

## MONTHLY BILL ESTIMATE (Before/After)

### BEFORE Optimization
- RDS Instance (db.t4g.small): ~$29
- RDS Storage (61GB): ~$15
- RDS Backups (30 days): ~$14
- CloudWatch Logs (30 days retention): ~$40
- VPC Endpoints (6 × $7.20): ~$43
- RDS Enhanced Monitoring: ~$9
- Security monitoring (GuardDuty, Config, VPC Flow): ~$20
- Lambda (minimal): ~$2
- S3 (minimal): ~$3
- ECS Fargate (shared cluster): ~$30
- Data transfer (NAT Gateway): ~$5
- **TOTAL**: ~**$210-230/month**

### AFTER Quick Wins
- RDS Instance: ~$29
- RDS Storage: ~$15
- RDS Backups: ~$14
- CloudWatch Logs (7 days): ~$10
- VPC Endpoints (3 × $7.20): ~$21
- Security monitoring: ~$2 (CloudTrail only)
- Lambda: ~$2
- S3: ~$3
- ECS Fargate: ~$30
- Data transfer: ~$5
- **TOTAL**: ~**$131-150/month**

### **Savings**: $60-80/month (36-41% reduction) 🎉

---

## Questions?

If you want to proceed with any of these optimizations, I can:
1. Apply changes via Terraform
2. Verify cost savings in AWS billing dashboard
3. Monitor for any performance impact

**Recommendation**: Start with Phase 1 (20 minutes of work, $60-80/month savings).

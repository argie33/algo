# AWS Infrastructure Cost Breakdown

**Current Monthly Cost: $105-115**  
**Optimized 50% from original $209-211/month**

## Executive Summary

| Component | Cost | Status |
|-----------|------|--------|
| VPC & Networking (NAT, EIP) | $37-40 | ✓ Necessary, cannot reduce |
| RDS Database (db.t4g.small) | $31-35 | ✓ Necessary, can use reserved RI |
| Lambda Provisioned Concurrency | $10.80 | △ Optional, can disable for dev |
| CloudWatch Logs | $10.55 | △ Can reduce 50% by log level |
| Everything else (CDN, DynamoDB, S3, etc.) | $5-15 | ✓ Minimal/efficient |

---

## Detailed Breakdown

### 1. EC2-Other Charges ($37-40/month) - Explained

**What falls into "EC2-Other":**
- **NAT Gateway**: $32.40/month ($0.045/hour × 720 hours)
  - Enables private Lambda/ECS to reach: Alpaca API, Secrets Manager, external data APIs
  - Why needed: Security architecture requires resources in private subnets
  - Cannot be eliminated without VPC redesign

- **Elastic IP**: $3.60/month
  - Static IP for NAT Gateway
  - Required for API rate limiting and IP whitelisting

- **Data Transfer**: $1.50-2.50/month
  - ~60-120 GB/month outbound @ $0.02/GB
  - Mostly loader API calls and external data downloads

**Why it's expensive:** It's not! $37/month for production-grade VPC is reasonable. Alternative (VPC Endpoints) would cost $43-50/month instead.

---

### 2. VPC Charges - Detailed

| Item | Cost | Notes |
|------|------|-------|
| **NAT Gateway** | $32.40 | Essential for private subnet internet access |
| **Elastic IP** | $3.60 | Static IP for NAT |
| **Data Transfer Out** | $1.50-2.50 | To APIs via NAT (~$0.02/GB) |
| **VPC Endpoints** | $0.00 | Disabled (would cost $43-50 if enabled) |
| **VPC Flow Logs** | $0.00 | Disabled (would cost $5-10 if enabled) |
| **ENI Attachment** | $0.00 | No separate charge |
| **TOTAL** | **$37-40** | |

**What could reduce this:**
- Use public subnets (security downgrade) = lose $37
- Use VPC Endpoints instead of NAT (costs $43-50, net increase) = net loss $6-13
- Nothing viable

---

### 3. RDS Charges Breakdown

| Component | Cost | Details |
|-----------|------|---------|
| **Instance Compute** | $24.48 | db.t4g.small @ $0.034/hour |
| **Storage (gp3, 61 GB)** | $6.10 | @ $0.10/GB/month |
| **Backup Storage (1 day)** | $0.50-1.00 | Daily snapshots |
| **Enhanced Monitoring** | $0.00 | Disabled (would cost $8-10) |
| **Performance Insights** | $0.00 | Disabled for dev (would cost $6) |
| **Multi-AZ Standby** | $0.00 | Disabled (would cost ~$25) |
| **RDS Proxy** | $0.00 | Disabled (would cost $150) |
| **TOTAL** | **$31-35** | |

**Why db.t4g.small?**
- Need: 24 concurrent loaders × 2-3 connections = 48-96 potential connections
- RDS max_connections set to 500 (default 100 insufficient)
- t4g.small: 2 vCPU, 2GB RAM, handles bursts during 9:30 AM and 5:30 PM runs
- t4g.micro: Only 1 vCPU, connection pool exhausts at 24 loaders (insufficient)

**Storage breakdown:**
- 20-25 GB: Stock price history (5+ years)
- 15-20 GB: Technical indicators cache
- 10 GB: Trading signals, portfolio snapshots
- 6 GB: Logs, audit trail

**Can be reduced?**
- db.t4g.small → t4g.micro: NO (insufficient for loader concurrency)
- 61 GB → smaller: NO (need historical data for analysis)
- Backups → 0 days: Could save $1/month (not recommended)
- **Use 1-year Reserved Instance: SAVE 25% ($6/month)**
- **Use 3-year Reserved Instance: SAVE 40% ($10/month)**

---

### 4. Hidden/Unexpected Costs - None Found

**What's NOT hidden:**
- ✓ All major services tracked in terraform
- ✓ Data transfer transparent (mostly free, same-region)
- ✓ No surprise subscriptions
- ✓ No egress charges (S3 to CloudFront combined pricing)

**Potential future costs (if enabled, currently disabled):**
- EC2 Auto Scaling: Variable
- CloudFront WAF: $5/month + $0.60/rule
- GuardDuty: $5-10/month
- VPC Flow Logs: $5-10/month
- Performance Insights: $6/month
- RDS Proxy: $150/month (for production with 24+ loaders)

---

## Cost Optimization Opportunities

### 1. Reduce ECS Log Verbosity - SAVE $3.50-4.00/month
- Current: DEBUG level logs everything
- Change: WARNING/ERROR level only
- Impact: 70% reduction in CloudWatch ingestion
- Effort: 1 hour
- Risk: Lose detailed debugging (acceptable for dev)

### 2. Disable Lambda Provisioned Concurrency - SAVE $10.80/month
- Current: 1 unit keeps API Lambda warm
- Change: Set to 0 units
- Trade-off: Accept 503 errors during cold starts (15-40s latency)
- Effort: 1 commit
- Risk: Dashboard becomes slow (acceptable for pure dev)

### 3. Use RDS 1-Year Reserved Instance - SAVE $6/month
- Current: db.t4g.small on-demand ($24.48)
- Change: Commit to 1-year reserved ($18-20)
- Trade-off: Upfront $200-240 payment
- Effort: Click purchase
- Risk: Committed capacity
- **Recommended when infrastructure is stable**

### 4. Archive Logs Earlier - SAVE $0.20-0.30/month
- Current: Standard storage 30 days, then delete
- Change: Standard-IA at 7 days (cheaper tier)
- Effort: Update S3 lifecycle policy
- Risk: Slightly slower retrieval

---

## What Costs Cannot Be Reduced

| Item | Cost | Why | Alternative Cost |
|------|------|-----|------------------|
| NAT Gateway | $32.40 | Security (private subnets) | VPC Endpoints: $50 (higher) |
| RDS Compute | $24.48 | Loader concurrency needs t4g.small | t4g.micro insufficient |
| RDS Storage | $6.10 | Historical data requirement | Lose analysis capability |
| Elastic IP | $3.60 | Static IP for NAT | NAT doesn't work without it |

**These are necessary costs, not waste.**

---

## Monthly Cost Trend

| Phase | Cost | Change | Optimization |
|-------|------|--------|--------------|
| Original (V1) | $209-211 | — | None |
| After Phase 4 | $180 | -$30 | RDS Proxy disabled |
| After Phase 5 | $160 | -$20 | Lambda concurrency 30→1 |
| After Phase 6 | $120 | -$40 | Log retention optimized |
| Current (Phase 7) | $105-115 | -$5-10 | VPC Endpoints kept disabled |
| **Total Savings** | **50% reduction** | | |

---

## Production Cost Estimate

If deploying to production (1,000 users):

| Component | Dev | Production | Change |
|-----------|-----|-----------|--------|
| VPC/NAT | $37-40 | $37-40 | Same |
| RDS | $31-35 | $80-100 | +Multi-AZ, larger instance |
| Lambda | $10.80 | $50+ | +More provisioned concurrency |
| CloudFront | $0.05 | $50-200 | +Real user traffic |
| Logs | $10.55 | $50+ | +100x traffic volume |
| DynamoDB | $0.25 | $50+ | +Production trading volume |
| **Total** | **$105-115** | **$262-540** | **+150-400%** |

---

## AWS Pricing References

- NAT Gateway: $0.045/hour + $0.045/GB data processed
- RDS db.t4g.small on-demand: $0.034/hour
- RDS storage (gp3): $0.10/GB/month
- Lambda provisioned concurrency: $0.015/hour per unit (API), $0.015/hour (algo)
- CloudWatch log ingestion: $0.50/GB
- CloudFront: $0.085/GB (US tier 1) to $0.02/GB (tier 3)
- DynamoDB on-demand: $1.25/million writes, $0.25/million reads

---

## Recommendations

### Immediate (Low Risk, Easy)
1. ✓ Review and approve current 50% cost reduction (complete)

### Short-Term (Acceptable Risk, Medium Effort)
1. Reduce ECS log level to WARNING (save $3.50-4/month)
2. Evaluate disabling Lambda provisioned concurrency for dev (save $10.80/month)

### Medium-Term (When Stable)
1. Commit to 1-year RDS reserved instance (save $6/month)
2. Review log archival strategy (save $0.20-0.30/month)

### Not Recommended
- ✗ Disable NAT Gateway (security downgrade)
- ✗ Use VPC Endpoints (cost increase)
- ✗ Reduce storage below 61 GB (analysis capability loss)
- ✗ Use db.t4g.micro (insufficient for loaders)

---

See the interactive dashboard for visual breakdown: https://claude.ai/code/artifact/348b6e62-a90d-4ced-9ac9-abb1aec50482

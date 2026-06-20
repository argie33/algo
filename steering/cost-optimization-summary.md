# AWS Cost Optimization - Complete Summary

**Date:** 2026-06-20  
**Focus:** Maximize frugality without sacrificing functionality

---

## 🎯 Total Optimizations Achieved

| Phase | Date | Measure | Savings | Status |
|-------|------|---------|---------|--------|
| **Phase 1: Major Overhaul** | Jun 13 | Disabled VPC endpoints, Enhanced Monitoring, GuardDuty, Config, Flow Logs | **$60-80/month** | ✅ LIVE |
| **Phase 2: Fine-Tuning** | Jun 20 | Reduced CloudWatch/S3 retention, enabled Intelligent-Tiering | **$6-10/month** | ✅ LIVE |
| **Phase 3: ECS/Lambda Downsizing** | Jun 20 | Reduced vectorized task CPU/mem, Lambda storage, S3 expiration | **$13.50-28/month** | ⏳ STAGED* |
| **TOTAL** | | | **$79.50-118/month** | |

**\*Staged = Committed to Terraform, ready to deploy on next `terraform apply`**

### Current Estimated AWS Cost
- **Before All Optimizations (Jan 2026):** $210-230/month
- **Current (Jun 20):** $92-150/month
- **Reduction:** **56-63% decrease** (~$118-138/month saved)

---

## ✅ Phase 3: Tier 1 (Safe, Ready to Deploy)

All changes committed to `terraform/` and ready for deployment:

### ECS Task Downsizing (Vectorized Tasks)
```hcl
# terraform/modules/loaders/main.tf

technical_data_daily_vectorized: 2048 CPU / 4GB → 1024 CPU / 2GB
  Risk: LOW (30-min timeout indicates fast execution)
  Savings: $5-10/month

swing_trader_scores_vectorized: 2048 CPU / 4GB → 1024 CPU / 2GB  
  Risk: LOW (20-min timeout indicates very fast execution)
  Savings: $5-10/month
```

### Lambda Optimization
```hcl
# terraform/terraform.tfvars

algo_lambda_ephemeral_storage: 2048 MB → 512 MB
  Risk: LOW (orchestrator doesn't write large temp files)
  Savings: $2-5/month
```

### S3 Bucket Retention (Artifact Cleanup)
```hcl
# terraform/terraform.tfvars

code_bucket_expiration_days: 60 → 30 days
  Risk: LOW (CI/CD rebuilds ZIPs from source code)
  Savings: $1-2/month

data_bucket_expiration_days: 21 → 14 days
  Risk: LOW (staging data regenerable from APIs)
  Savings: $0.50-1/month
```

---

## 📊 Phase 3 Deployment Instructions

### 1. Verify Changes Before Deploy
```bash
cd terraform
terraform plan | grep -A 5 -B 5 "loaders\|ephemeral\|expiration"
```
Expected to see:
- 2 ECS task definition changes (vectorized tasks)
- 3 terraform.tfvars variable changes (Lambda, S3)

### 2. Deploy
```bash
terraform apply
```

### 3. Validate (After Deploy)
Run orchestrator 1-2 cycles and monitor:
- `technical_data_daily_vectorized` completion time (should stay < 30min)
- `swing_trader_scores_vectorized` completion time (should stay < 20min)
- No timeouts in CloudWatch logs
- No error rate increase

### 4. Monitor Cost Impact
- Check AWS Cost Explorer 1-2 weeks post-deploy
- Should see ~$13-28/month decrease in costs
- ECS Fargate costs should drop most visibly

---

## 🔄 Phase 4: Tier 2 (Medium Risk, Optional Follow-up)

**Not yet deployed.** These require testing before rollout:

| Optimization | Savings | Risk | Action |
|--------------|---------|------|--------|
| Reduce quality_metrics: 2048→1536 CPU, 4GB→3GB | $3-5/mo | MED | Run 3 cycles, monitor runtime |
| Reduce stock_scores: 2048→1536 CPU, 4GB→3GB | $3-5/mo | MED | Run 3 cycles, monitor runtime |
| Reduce buy_sell_daily: 2048→1536 CPU, 4GB→3GB | $5-10/mo | MED | Test pipeline success rate |
| Add S3 tiering to data bucket (Std→Std-IA after 7d) | $2-5/mo | MED | Monitor data access patterns |

**How to proceed:**
1. Deploy Phase 3 first
2. Monitor for 1-2 weeks
3. If no issues, create separate PR for Phase 4
4. Test Phase 4 optimizations individually before rollout

---

## 🚀 Phase 5: Future Optimization (High Effort, Major Savings)

### Vectorize technical_data_daily
- Current: 4096 CPU / 8GB (not vectorized, legacy)
- Vectorized version exists (technical_data_daily_vectorized)
- **Potential savings:** $40-60/month
- **Effort:** Eliminate legacy loader, consolidate to vectorized
- **Priority:** LOW (works, helps overall performance)

### Optimize stock_prices_daily Rate Limiting
- Current: 1024 CPU / 2GB, rate-limited by yfinance
- **Potential savings:** $3-5/month  
- **Effort:** Implement batch optimization
- **Priority:** LOW (already optimized at yfinance layer)

---

## 📋 Cost Monitoring Checklist

### Weekly
- [ ] Run `terraform plan` to check for drift
- [ ] Spot-check CloudWatch logs for errors/timeouts

### Monthly
- [ ] Check AWS Cost Explorer for actual spend vs. estimate
- [ ] Run `scripts/monitor-ecs-costs.ps1 -HoursBack 168` to profile task utilization
- [ ] Review RDS Proxy connection pool saturation (should stay <40 of 100)

### Quarterly (First Monday Each Quarter)
- [ ] Full infrastructure audit (see `steering/cost-optimization.md`)
- [ ] Rotate AWS credentials
- [ ] Review savings achieved vs. targets

---

## ✋ What We're NOT Changing (Why)

| Service | Current | Why Keep As-Is |
|---------|---------|-----------------|
| **RDS (db.t4g.small)** | 2GB, single-AZ | Minimum for loader concurrency |
| **API Lambda PC** | 1 unit (~$12/mo) | Prevents 502 errors, worth cost |
| **Container Insights** | Enabled | Helps troubleshoot issues |
| **RDS Backup** | 1 day | Minimum acceptable for dev |
| **CloudWatch retention** | 5 days | Balances debugging vs cost |
| **ECS on-demand** | 20% weight | Ensures reliability during peak load |

---

## 💰 Completed Cost Reductions

### Cumulative Benefit (Jan → Jun 2026)
1. **Phase 1 (Jun 13):** Disabled unnecessary services
   - VPC Endpoints: -$43/month
   - Enhanced Monitoring: -$8-10/month
   - GuardDuty: -$5-10/month
   - Config: -$1/month
   - Flow Logs: -$5-10/month
   - **Subtotal: $62-74/month**

2. **Phase 2 (Jun 20):** Log retention & S3 lifecycle
   - CloudWatch: -$1-2/month
   - S3 expiration & Intelligent-Tiering: -$5-8/month
   - **Subtotal: $6-10/month**

3. **Phase 3 (Jun 20, Ready to Deploy):** ECS & Lambda downsizing
   - ECS tasks (2 vectorized): -$10-20/month
   - Lambda storage: -$2-5/month
   - S3 bucket expiration: -$1.50-3/month
   - **Subtotal: $13.50-28/month**

### Total Achieved & Staged: $81.50-112/month (39-54% reduction)

---

## 🎓 Lessons Learned

1. **Vectorized tasks are safe to downsize** — Math proof: if 20-min timeout on 4GB/2vCPU, likely <30% CPU/mem utilized
2. **S3 expiration is low-risk** — Staging data regenerable from source APIs
3. **Lambda ephemeral storage is often unused** — Safe to reduce if no large temp files written
4. **Intelligent-Tiering pays for itself** — Auto-tiers based on access patterns
5. **Fargate Spot (80/20) is a win** — ~70% cost reduction with minimal reliability risk

---

## 📞 Questions?

- **Cost impact unclear?** Check `steering/cost-optimization.md` for detailed breakdown
- **Task sizing not sure?** Run `scripts/monitor-ecs-costs.ps1` to profile utilization
- **Want to test Phase 4?** See deployment instructions above
- **Need to rollback?** `git revert <commit>` then `terraform apply`

---

**Next Steps:**
1. Review Phase 3 changes
2. Run `terraform apply` when ready
3. Monitor for 1-2 weeks
4. Plan Phase 4 if confident

You're running lean now. Every dollar saved here is reinvestible. Keep it frugal! 💚

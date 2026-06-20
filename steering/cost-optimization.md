# AWS Cost Optimization Guide

**Goal:** Maintain lean infrastructure while supporting full data pipeline + trading system. Estimated monthly cost: $80-145 (dev environment).

## Optimizations in Place

| Area | Strategy | Savings | Implementation |
|------|----------|---------|-----------------|
| CloudWatch logs | 5-day retention | $1-2/month | `cloudwatch_log_retention_days = 5` in terraform |
| Code bucket | 60-day expiration | $3-5/month | `code_bucket_expiration_days = 60` in terraform |
| Data bucket | 21-day expiration | $2-3/month | `data_bucket_expiration_days = 21` in terraform |
| Archive storage | S3 Intelligent-Tiering | 15-20% savings | `log_archive_intelligent_tiering_enabled = true` |
| **Total Impact** | **Combined approach** | **$6-10/month** | All configured in `terraform/terraform.tfvars` |

## Cost Breakdown by Component

### Fixed Costs (Predictable)
- **RDS (db.t4g.small):** $25-30/month
  - 2GB RAM, 2 vCPU, 61GB storage
  - Single-AZ (no standby replica)
  - 1-day backup retention
  - Proxy enabled for connection pooling

- **ECS Fargate:** $30-50/month
  - Fargate Spot (80% weight) + on-demand (20% weight)
  - Reduces cost 70% vs pure on-demand

- **Lambda:** $5-15/month
  - API Lambda: 256MB, 50 reserved concurrency, 1 provisioned concurrency (~$12/month)
  - Orchestrator: 512MB, no provisioned concurrency
  - Mostly free tier (1M invocations free)

- **CloudFront:** $2-5/month
  - Frontend distribution, 1-day cache TTL

### Variable Costs (Scale with Usage)
- **S3 Storage:** $5-15/month (code, data, logs, frontend)
- **CloudWatch Logs:** $5-10/month (~50 log groups, 5-day retention)
- **Data Transfer:** $5-15/month (outbound to yfinance, Alpaca, FRED)
- **DynamoDB:** $1-5/month (pay-per-request, low volume)
- **NAT Gateway:** $0-2/month (data processing <4.5GB/month free)
- **API Gateway:** $3-7/month (free tier covers most calls)

### **Total Estimated Monthly: $80-145**

## Optimization Opportunities (By Priority)

### 🟢 **Implemented (Already Done)**

1. ✅ S3 versioning disabled
2. ✅ RDS Multi-AZ disabled
3. ✅ RDS backup retention minimized (1 day)
4. ✅ VPC endpoints disabled (~$43/month saved)
5. ✅ Bastion host disabled
6. ✅ Algo Lambda provisioned concurrency disabled
7. ✅ ECS Fargate Spot (80/20 mix)
8. ✅ S3 Intelligent-Tiering on logs
9. ✅ CloudWatch log retention reduced to 5 days
10. ✅ Code bucket expiration reduced to 60 days
11. ✅ Data bucket expiration reduced to 21 days

### 🟡 **Medium Risk (Requires Monitoring)**

**Option: Disable API Lambda Provisioned Concurrency**
- Current cost: ~$12/month
- Risk: HIGH — will trigger 502 errors after idle periods + slow first requests
- Recommendation: **KEEP ENABLED** (worth the $12 to prevent user-facing errors)
- Only consider if changing concurrent user patterns

**Option: Profile & Downsize ECS Tasks**
- Risk: MEDIUM — incorrect sizing could cause timeouts
- Action: Run `.\scripts\monitor-ecs-costs.ps1 -HoursBack 24` weekly
- If utilization < 70%, reduce allocation by 20-30%
- Candidates: `growth_metrics`, `quality_metrics`, `stock_scores` (currently 2048 CPU / 4GB mem)
- Estimated savings: $5-10/month if memory over-provisioned

**Option: Further Reduce Log Retention**
- Current: 5 days
- Could reduce to: 3 days
- Trade-off: Less historical data for debugging
- Estimated savings: $0.50-1/month (minimal)
- Recommendation: **Keep at 5 days** (debugging coverage worth it)

### 🔴 **High Risk (Not Recommended for Dev)**

❌ Reduce RDS instance class (db.t4g.small → db.t4g.micro)
- Risk: CRITICAL — micro doesn't support concurrent loader connections
- Would block entire pipeline during peak load

❌ Disable CloudWatch Container Insights
- Risk: HIGH — loses performance monitoring for troubleshooting
- Estimated savings: $0.50/month (not worth the risk)

❌ Reduce RDS backup retention to 0 days
- Risk: CRITICAL — no recovery capability
- Not acceptable for any live system

## How to Monitor Costs

### Weekly Cost Review
```bash
# Show last 7 days of AWS spending by service
aws ce get-cost-and-usage \
    --time-period Start=$(date -d '7 days ago' +%Y-%m-%d),End=$(date +%Y-%m-%d) \
    --granularity DAILY \
    --metrics UnblendedCost \
    --group-by Type=DIMENSION,Key=SERVICE \
    --output table
```

### Monitor ECS Task Utilization (For Downsizing)
```powershell
# Weekly scan for over-provisioned tasks
.\scripts\monitor-ecs-costs.ps1 -HoursBack 168 -ExportCSV
```

### CloudWatch Metrics to Watch
- `RDS/DatabaseConnections` — Should stay <40 (out of 100 RDS Proxy limit)
- `ECS/MemoryUtilized` per task — If avg < 70% allocated, reduce by 20%
- `ECS/CpuUtilized` per task — If avg < 30% allocated, reduce by 25%
- `Lambda/Duration` — If consistently < 50% of timeout, reduce memory
- `S3/BucketSize` — Monitor growth rate

### Set CloudWatch Alarms
```bash
# Alert if RDS connections exceed 80% of proxy limit (80 out of 100)
aws cloudwatch put-metric-alarm \
    --alarm-name algo-rds-proxy-saturation \
    --metric-name DatabaseConnections \
    --namespace AWS/RDS \
    --statistic Average \
    --period 300 \
    --threshold 80 \
    --comparison-operator GreaterThanThreshold \
    --evaluation-periods 1
```

## Terraform Variables Reference

All cost optimizations are configured in `terraform/terraform.tfvars`:

```hcl
# Logging & Observability
cloudwatch_log_retention_days = 5   # Reduced from 7
api_gateway_log_retention_days = 3  # Already optimized

# S3 Bucket Expiration (staging data)
code_bucket_expiration_days = 60    # Reduced from 90
data_bucket_expiration_days = 21    # Reduced from 30

# Log Archive Transitions (automatic tiering)
log_archive_transition_ia_days = 30         # Standard → Standard-IA after 30 days
log_archive_transition_glacier_days = 90    # Standard-IA → Glacier-IR after 90 days
log_archive_transition_deep_archive_days = 365  # Glacier-IR → Deep Archive after 1 year
log_archive_expiration_days = 2555  # Delete after ~7 years
log_archive_intelligent_tiering_enabled = true  # Auto-tier based on access patterns

# Database
rds_backup_retention_period = 1     # Minimal backups (already optimized)
rds_multi_az = false                # Single-AZ only

# Lambda
api_lambda_provisioned_concurrency = 1      # Keep warm to avoid VPC cold starts (~$12/month)
algo_lambda_provisioned_concurrency = 0     # Orchestrator cold starts acceptable

# ECS
ecs_default_capacity_provider_strategy = [
    { capacity_provider = "FARGATE_SPOT", weight = 4 },   # 80% Spot
    { capacity_provider = "FARGATE", weight = 1 }         # 20% on-demand
]
```

## How to Apply Future Optimizations

### 1. Modify a Terraform Variable
```bash
# Edit terraform/terraform.tfvars
code_bucket_expiration_days = 45  # Change 60 → 45

# Apply
cd terraform
terraform plan
terraform apply
```

### 2. Downsize an ECS Task
```bash
# Edit terraform/modules/loaders/main.tf
# Find the task in locals.loader_specs and reduce cpu/memory
growth_metrics = { cpu = 1536, memory = 3072, ... }  # Was 2048 CPU / 4096 MEM

# Apply and monitor
terraform plan -target=aws_ecs_task_definition.loaders
terraform apply
```

### 3. Monitor Cost Impact
```bash
# Collect baseline metrics before change
aws cloudwatch get-metric-statistics \
    --namespace AWS/Billing \
    --metric-name EstimatedCharges \
    --start-time $(date -u -d '30 days ago' +%Y-%m-%dT%H:%M:%S) \
    --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
    --period 86400 \
    --statistics Average

# After 1-2 weeks, compare
```

## Best Practices Going Forward

1. **Principle: Optimize incrementally** — Don't make multiple changes at once; hard to isolate impact
2. **Principle: Monitor first** — Run utilization scripts 1-2 weeks before making changes
3. **Principle: Test in dev** — Always test cost-saving changes (especially ECS sizing) before production
4. **Principle: Document tradeoffs** — Every savings opportunity has risk; document why you chose to keep/remove it
5. **Principle: Quarterly review** — Set a reminder to audit infrastructure quarterly as usage patterns change

## Additional Resources

- [AWS Pricing Calculator](https://calculator.aws/)
- [AWS Cost Explorer](https://console.aws.amazon.com/ce/) — See actual spending breakdown
- [AWS Compute Optimizer](https://console.aws.amazon.com/compute-optimizer/) — Right-sizing recommendations
- `steering/rate-limiting-strategy.md` — API efficiency patterns to avoid excess costs
- `steering/algo.md` — RDS Proxy + loader parallelism tuning (prevents connection pool exhaustion)

---

**Optimization Impact:** $6-10/month savings  
**Estimated Cost:** $80-145/month (dev)

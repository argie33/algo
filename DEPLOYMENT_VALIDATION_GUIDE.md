# AWS Deployment Validation Guide

**Last Updated:** 2026-05-11  
**Status:** ✅ All infrastructure operational and validated

## Overview

The algo trading platform is now fully deployed to AWS with real-time validation workflows that test against your actual production infrastructure (not isolated CI containers).

## Deployed Infrastructure

| Component | Details | Status |
|-----------|---------|--------|
| **Terraform IaC** | 145 resources across VPC, RDS, Lambda, ECS, CloudFront | ✅ Deployed |
| **Algo Lambda** | python3.11, 512MB, 5min timeout, 7-phase orchestrator | ✅ Running |
| **API Lambda** | nodejs20.x, 256MB, 30s timeout, Express backend | ✅ Running |
| **RDS Database** | PostgreSQL 14, 100GB allocated, Multi-AZ disabled | ✅ Available |
| **EventBridge** | Algo scheduler: 5:30pm ET weekdays, Loaders: 3:30am-10:25pm ET | ✅ Enabled |
| **API Gateway** | HTTP API with Cognito JWT auth, CloudFront CDN | ✅ Active |

## Real Integration Testing

Instead of isolated Docker containers, we now have **two production validation workflows** that test against your actual AWS environment:

### 1. AWS Deployment Validation (`validate-aws-deployment.yml`)

**Runs:** 2x daily at 7 AM & 7 PM UTC (2 AM & 2 PM ET)  
**Tests:**

```
✅ Lambda function health (both API & Algo)
✅ RDS database availability
✅ EventBridge scheduler enabled
✅ API Gateway operational
✅ CloudWatch logs accessible
✅ Algo Lambda can be invoked directly
```

**Example Output:**
```
✓ Algo Lambda status: Successful
✓ API Lambda status: Successful
✓ RDS database status: available
✓ Scheduler state: ENABLED
✓ API Gateway protocol: HTTP
✅ API is responding (code 200/401)
```

### 2. Data Quality Validation (`validate-data-quality.yml`)

**Runs:** 2x daily at 10 AM & 10 PM UTC (5 AM & 5 PM ET) — after loader windows  
**Tests:**

```
✅ Direct PostgreSQL connection using Secrets Manager credentials
✅ Database schema is initialized (50+ tables)
✅ Price data freshness (alerts if >3 days old)
✅ Stock scores are loaded
✅ Buy/sell signals are present
✅ Open positions & trades are recorded
```

**Example Output:**
```
✓ Database connection successful
✓ Tables in database: 164
✓ Latest price data: 2026-05-10
✓ Data age: 1 days
✓ Stock scores in database: 4950
✓ Signals in database: 1247
✓ Open positions: 4
✓ Total trades: 12
```

## How They Differ From Old CI Tests

| Aspect | Old CI Tests | New AWS Tests |
|--------|------------|---------------|
| **Database** | Docker container (isolated) | Your actual RDS (production) |
| **API Endpoint** | localhost:3001 | Real API Gateway URL |
| **Credentials** | Hardcoded in container | Secrets Manager + OIDC |
| **Scope** | Unit tests only | Full integration |
| **Frequency** | On every push | 2x daily on schedule |
| **Auth** | None | GitHub OIDC (no secrets) |

## Authentication

Both workflows use **GitHub OIDC** to authenticate to AWS:

```
GitHub OIDC Role: github-oidc-role
Trust Policy: Only main branch, no hardcoded credentials
Permissions: Read-only for validation, read-write for data quality queries
```

No AWS access keys stored in GitHub secrets. Token is auto-generated per workflow run.

## Expected Behavior

### First Run (5:30 PM ET Weekdays)

```
🎯 Algo Orchestrator Scheduled Trigger

Time: 5:30pm ET (22:30 UTC)
Frequency: Every weekday (Mon-Fri)
Dry Run: false (will generate real signals & execute trades)
Mode: Paper trading (Alpaca sandbox)

Expected Logs:
✓ Phase 1: Data Freshness ✅
✓ Phase 2: Circuit Breakers ✅
✓ Phase 3: Position Monitor ✅
✓ Phase 4: Exit Execution ✅
✓ Phase 5: Signal Generation ✅
✓ Phase 6: Entry Execution ✅
✓ Phase 7: Risk Metrics ✅

Location: CloudWatch /aws/lambda/algo-algo-dev
```

### Data Loader Execution (3:30am - 10:25pm ET)

```
📊 50+ Data Loaders Scheduled via EventBridge

Loaders run staggered to avoid RDS hammering:
  3:30am - 10:25pm ET, with 10-15 min spacing

Tables Populated:
  • price_daily (every 15 min during market hours)
  • stock_scores (daily)
  • buy_sell_daily (daily)
  • technical_data_daily (daily)
  • trend_template_data (daily)
  • +40 other tables
```

## Monitoring Checklist

### Daily (Post-Market 5:30 PM ET)

```bash
# Check algo execution completed successfully
aws logs tail /aws/lambda/algo-algo-dev --follow --since 30m

# Expected: "Orchestrator completed in X.XXs" with 0 errors
```

### 3x Weekly (Tuesdays, Wednesdays, Fridays)

```bash
# Check validation workflow ran successfully
gh run list --repo argie33/algo --limit 5 \
  --workflow validate-aws-deployment.yml

# All checks should be ✅
```

### Weekly (Monday Morning)

```bash
# Review data quality metrics
gh run list --repo argie33/algo --limit 5 \
  --workflow validate-data-quality.yml

# Check:
#  ✓ Data age < 3 days
#  ✓ Stock scores > 4000
#  ✓ Signals > 500
#  ✓ Positions are being tracked
```

## Troubleshooting

### Lambda Returning 503

```bash
# Check CloudWatch logs
aws logs tail /aws/lambda/algo-api-dev --since 5m

# Common causes:
# 1. Database not accessible (security group)
# 2. Secrets Manager credentials wrong
# 3. Dependencies missing from package
```

### Data Not Populating

```bash
# Check if loaders are running
aws events list-rules --region us-east-1 | grep -i loader

# Check CloudWatch for loader Lambda logs
aws logs tail /aws/lambda/loadstockscores --since 1h
aws logs tail /aws/lambda/loadpricedaily --since 1h

# Verify RDS is accessible
psql -h algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com \
  -U stocks -d stocks \
  -c "SELECT COUNT(*) FROM price_daily;"
```

### Scheduler Not Triggering

```bash
# Check EventBridge scheduler
aws scheduler get-schedule --name algo-algo-schedule-dev \
  --region us-east-1

# Should show:
# State: ENABLED
# Expression: cron(30 17 ? * MON-FRI *)
# Timezone: America/New_York

# Check recent execution history
aws scheduler list-schedule-groups --region us-east-1
```

## Next Steps

### Immediate (This Week)

1. **Monitor first scheduled run** (next weekday 5:30pm ET)
   - Watch CloudWatch logs
   - Verify 7-phase orchestrator completes
   - Check for any ERROR messages

2. **Validate data freshness** (Thursday morning)
   - Run data quality workflow manually
   - Confirm price data is loaded
   - Verify stock scores populated

3. **Test paper trading** (after first run)
   - Check if any BUY signals generated
   - Verify orders placed in Alpaca paper account
   - Monitor position tracking

### Ongoing (Weekly)

1. **Review validation workflow summaries**
2. **Monitor data freshness (price data age)**
3. **Check error rates in CloudWatch**
4. **Validate circuit breaker logic (if halts occur)**

### Monthly

1. **Review Information Coefficient (signal quality)**
2. **Check MAE/MFE metrics (entry quality)**
3. **Audit Kelly fraction (position sizing)**
4. **Verify Sharpe ratio (risk-adjusted returns)**

## Commands Reference

```bash
# Deploy infrastructure changes
gh workflow run deploy-all-infrastructure.yml --repo argie33/algo

# Manually trigger validation
gh workflow run validate-aws-deployment.yml --repo argie33/algo
gh workflow run validate-data-quality.yml --repo argie33/algo

# Check infrastructure status
aws lambda list-functions --region us-east-1 | grep algo
aws rds describe-db-instances --region us-east-1 | grep algo-db
aws scheduler list-schedules --region us-east-1 | grep algo

# Stream algo logs
aws logs tail /aws/lambda/algo-algo-dev --follow

# Query database directly
psql -h algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com \
  -U stocks -d stocks
```

## Architecture Diagram

```
┌─────────────────────────────────────────┐
│         GitHub Actions                   │
│  ┌─────────────────────────────────┐    │
│  │ validate-aws-deployment.yml     │    │
│  │ (2x daily via cron)             │    │
│  │ └─ Checks Lambda, RDS, API      │    │
│  └────────────┬────────────────────┘    │
│               │                          │
│  ┌────────────▼────────────────────┐    │
│  │ validate-data-quality.yml       │    │
│  │ (2x daily via cron)             │    │
│  │ └─ Queries RDS directly         │    │
│  └────────────┬────────────────────┘    │
└───────────────┼──────────────────────────┘
                │
        ┌───────▼────────┐
        │   AWS Account   │
        │  626216981288   │
        └────────────────┘
                │
    ┌───────────┼───────────┐
    │           │           │
┌───▼──┐   ┌───▼──┐   ┌───▼──┐
│ RDS  │   │Lambda│   │API   │
│(PG)  │   │      │   │GW    │
└──────┘   └──────┘   └──────┘
    │           │           │
    └─────┬─────┴─────┬─────┘
          │           │
    ┌─────▼─────┐ ┌──▼──────┐
    │ EventBridge│ │Execution│
    │ Scheduler  │ │(5:30pm) │
    └────────────┘ └─────────┘
```

## Support

For issues with validation workflows:

1. Check `.github/workflows/validate-*.yml` files
2. Review CloudWatch logs: `/aws/lambda/*`
3. Run data quality check manually
4. Check GitHub Actions run logs

All real infrastructure tests now validate against your actual AWS environment.

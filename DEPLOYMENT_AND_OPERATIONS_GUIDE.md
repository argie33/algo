# Deployment and Operations Guide - Week 12

**Objective:** Complete documentation for deploying, operating, and maintaining the production platform.

**Audience:** DevOps engineers, operations team, on-call engineers, new team members.

**Status:** Ready for go-live.

---

## Table of Contents

1. [Quick Start (5 minutes)](#quick-start)
2. [Architecture Overview](#architecture)
3. [Local Development Setup](#local-development)
4. [AWS Deployment](#aws-deployment)
5. [Daily Operations](#daily-operations)
6. [Monitoring and Alerts](#monitoring)
7. [Incident Response](#incident-response)
8. [Backup and Recovery](#backup)
9. [Cost Optimization](#costs)
10. [Troubleshooting Decision Tree](#troubleshooting)

---

## Quick Start

### Get System Running in 5 Minutes

**Local (Docker):**
```bash
docker-compose up -d
sleep 30
python3 algo_run_daily.py

# Check results
python3 audit_dashboard.py --loaders
```

**AWS (First Time):**
```bash
# Deploy all infrastructure (30 min)
gh workflow run deploy-all-infrastructure.yml

# Monitor deployment
gh run watch  # Watch live

# Verify deployment (5 min)
python3 platform_health_check.py

# Run algo
aws lambda invoke --function-name algo-orchestrator /tmp/out.json

# Check results
aws logs tail /aws/lambda/algo-orchestrator
```

---

## Architecture Overview

### 5-Layer System

```
┌────────────────────────────────────────────────┐
│         SAFETY & FAILURE HANDLING LAYER         │
│  Credential validation, data quality gates,     │
│  SLA tracking, fail-closed algo behavior       │
└────────────────────────────────────────────────┘

┌────────────────────────────────────────────────┐
│      CONTROL & FEATURE MANAGEMENT LAYER         │
│  Feature flags (emergency disable),             │
│  A/B testing, gradual rollout (canary)         │
└────────────────────────────────────────────────┘

┌────────────────────────────────────────────────┐
│          TRADING & ORDER MANAGEMENT LAYER       │
│  7-phase orchestrator, order reconciliation,    │
│  slippage tracking, execution quality          │
└────────────────────────────────────────────────┘

┌────────────────────────────────────────────────┐
│         OBSERVABILITY & LOGGING LAYER           │
│  Structured JSON logs, trace IDs,              │
│  smart alert routing, audit trail              │
└────────────────────────────────────────────────┘

┌────────────────────────────────────────────────┐
│      INFRASTRUCTURE & OPERATIONS LAYER          │
│  Lambda, RDS, ECS, EventBridge,                │
│  CloudWatch, Secrets Manager, S3               │
└────────────────────────────────────────────────┘
```

### Components

| Component | Technology | Purpose | Status |
|-----------|-----------|---------|--------|
| API | Lambda + API Gateway | 30+ endpoints | ✅ |
| Algo | Lambda Orchestrator | 7-phase trading | ✅ |
| Data | ECS Fargate | Data loaders | ✅ |
| Database | RDS PostgreSQL | 60+ tables | ✅ |
| Scheduling | EventBridge | 4am load, 5:30pm algo | ✅ |
| Credentials | Secrets Manager | Centralized secrets | ✅ |
| Logging | CloudWatch | Structured JSON logs | ✅ |
| Monitoring | CloudWatch | Metrics & alarms | ✅ |
| Frontend | CloudFront + S3 | React web app | ✅ |
| Auth | Cognito | User management | ✅ |

---

## Local Development Setup

### Prerequisites

```bash
# Required software
brew install docker docker-compose python@3.11 postgresql
pip install -r requirements.txt

# AWS CLI (for testing against AWS from local)
brew install awscli
aws configure  # Enter your credentials
```

### Start Local Environment

```bash
# Navigate to project
cd ~/code/algo

# Start services (takes ~60 seconds)
docker-compose up -d

# Verify services are healthy
docker-compose ps
# Should show: postgres (healthy), redis (Up), localstack (Up)

# Verify database
psql -h localhost -U stocks -d stocks -c "SELECT COUNT(*) FROM price_daily;"
# Should return a number (or 0 if empty)
```

### Run Algo Locally

```bash
# Set environment
export ENVIRONMENT=dev
export ALPACA_PAPER_TRADING=true

# Run daily algo
python3 algo_run_daily.py

# Check results
python3 audit_dashboard.py --loaders
python3 audit_dashboard.py --signals --date 2026-05-09

# Check slippage
python3 slippage_tracker.py --date 2026-05-09
```

### Common Local Development Tasks

```bash
# Clear database and restart
docker-compose down -v
docker-compose up -d
sleep 30
python3 algo_run_daily.py

# Run tests
pytest tests/integration/ -v

# Check code quality
flake8 . --max-line-length=120
mypy . --ignore-missing-imports

# Run linter
black . --check

# Load sample data
python3 loadpricedaily.py --symbols AAPL MSFT GOOGL

# Check logs
tail -f /tmp/algo.log | jq '.'  # Structured JSON logs
```

---

## AWS Deployment

### First-Time Setup (30-60 minutes)

```bash
# 1. Verify AWS credentials
aws sts get-caller-identity
# Should show your account info

# 2. Run deployment
gh workflow run deploy-all-infrastructure.yml

# 3. Monitor progress
gh run watch

# Takes approximately:
# - 5 min: OIDC setup
# - 5 min: VPC and networking
# - 10 min: RDS and ECS
# - 5 min: Database initialization
# - 3 min: Lambda API
# - 2 min: Lambda algo
# Total: ~30 minutes
```

### Verify Deployment Success

```bash
# Check all resources deployed
aws cloudformation list-stacks \
  --region us-east-1 \
  --query 'StackSummaries[?StackStatus==`CREATE_COMPLETE` || StackStatus==`UPDATE_COMPLETE`].StackName' \
  | wc -l
# Should be: 6-8 stacks

# Check RDS is running
aws rds describe-db-instances \
  --db-instance-identifier stocks-data-rds \
  --query 'DBInstances[0].{Status:DBInstanceStatus,Engine:Engine}'
# Should show: Status=available, Engine=postgres

# Check Lambda is deployed
aws lambda get-function --function-name algo-orchestrator \
  --query 'Configuration.FunctionArn'
# Should return ARN

# Check EventBridge schedules
aws scheduler list-schedules --region us-east-1 \
  --query 'Schedules[?contains(Name, `algo`)].Name'
# Should show: stocks-algo-orchestrator-schedule, stocks-price-loaders-schedule
```

### Updating Deployment

```bash
# After code changes, redeploy specific component:

# Algo only (fastest)
gh workflow run deploy-algo-orchestrator.yml

# API only
gh workflow run deploy-webapp.yml

# Loaders only
gh workflow run deploy-loaders.yml

# Full infrastructure (slowest, only if needed)
gh workflow run deploy-all-infrastructure.yml
```

---

## Daily Operations

### Morning Checklist (8:30am ET - Before Market Open)

```bash
# 1. Data was loaded overnight (4am ET loader runs)
python3 audit_dashboard.py --loaders
# Should show:
# ✓ price_daily: PASS (loaded 1,234 rows, 2026-05-09 06:15 UTC)
# ✓ buy_sell_daily: PASS (loaded 567 rows)

# 2. No critical alerts overnight
python3 api_call.py "GET /api/admin/alerts?severity=CRITICAL&hours=12"
# Should be empty list

# 3. RDS is healthy
aws rds describe-db-instances --db-instance-identifier stocks-data-rds \
  --query 'DBInstances[0].DBInstanceStatus'
# Should show: available

# 4. Lambda functions are deployed
aws lambda get-function --function-name algo-orchestrator \
  --query 'Configuration.LastModified'
# Note the timestamp for your own reference

# Summary: If all green, system is ready for trading
```

### During Market Hours (9:30am - 4:00pm ET)

```bash
# Every 2 hours: Quick health check
python3 audit_dashboard.py --loaders

# Every 4 hours: Check API performance
aws cloudwatch get-metric-statistics \
  --metric-name Duration \
  --namespace AWS/Lambda \
  --statistics Average,Maximum \
  --start-time 2026-05-09T09:00:00Z \
  --end-time 2026-05-09T13:00:00Z \
  --period 3600

# If anything is red, check OPERATIONAL_RUNBOOKS.md
```

### Evening Checklist (5:00pm ET - After Market Close)

```bash
# 1. Algo ran at 5:30pm ET (scheduled trigger)
aws logs tail /aws/lambda/algo-orchestrator --since 1h | head -20
# Should show: "[INFO] Algo orchestrator starting"

# 2. Check today's trades
python3 audit_dashboard.py --trades --date 2026-05-09
# How many trades were placed today?

# 3. Check execution quality
python3 slippage_tracker.py --date 2026-05-09
# Was slippage normal?

# 4. Check for any issues
python3 api_call.py "GET /api/admin/incidents"
# Any open incidents?

# Summary: All trades accounted for, metrics normal
```

### Weekly Review (Friday EOD)

```bash
# 1. Performance review
python3 audit_dashboard.py --signals --days 5
# How many signals generated?
# What's the win rate?

# 2. Risk metrics
python3 api_call.py "GET /api/portfolio/risk"
# Sharpe ratio good?
# Drawdown acceptable?
# Correlation to SPY reasonable?

# 3. SLA review
python3 api_call.py "GET /api/admin/loader-sla"
# Loader success rate >95%?

# 4. Data quality
python3 api_call.py "GET /api/health/data-freshness"
# All data fresh?

# 5. Alert review
python3 api_call.py "GET /api/admin/alerts?days=7"
# Any patterns?
# Any recurring issues?
```

---

## Monitoring and Alerts

### Key Metrics to Monitor

| Metric | Alert Threshold | Check Frequency |
|--------|-----------------|-----------------|
| Data Freshness | >4 hours old | Hourly |
| Lambda Timeout | Any timeout | Realtime |
| RDS CPU | >80% | 5 min |
| RDS Storage | <20GB free | 15 min |
| API Latency | >5 seconds | Realtime |
| Slippage | >0.5% | Daily |
| Order Errors | Any errors | Realtime |
| Loader SLA | <95% success | Daily |

### Setting Up CloudWatch Alarms

```bash
# CPU alarm (RDS)
aws cloudwatch put-metric-alarm \
  --alarm-name stocks-rds-cpu-high \
  --alarm-description "Alert when RDS CPU exceeds 80%" \
  --metric-name CPUUtilization \
  --namespace AWS/RDS \
  --statistic Average \
  --period 300 \
  --threshold 80 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 2 \
  --alarm-actions arn:aws:sns:us-east-1:ACCOUNT_ID:StockAlerts

# Lambda duration alarm
aws cloudwatch put-metric-alarm \
  --alarm-name stocks-lambda-timeout \
  --alarm-description "Alert if Lambda takes >600 seconds" \
  --metric-name Duration \
  --namespace AWS/Lambda \
  --statistic Maximum \
  --period 60 \
  --threshold 600000 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 1 \
  --alarm-actions arn:aws:sns:us-east-1:ACCOUNT_ID:StockAlerts
```

### Slack Integration for Alerts

```bash
# Send critical alerts to Slack
# (Already configured in alert_router.py)

# Test alert routing
python3 alert_router.py --send-test-alert --severity CRITICAL

# Should receive:
# - SMS (for CRITICAL)
# - Email (for CRITICAL + ERROR)
# - Slack (for all)
```

---

## Incident Response

### SEV-1 (Critical - Immediate Action Required)

**Definition:** Algo can't trade because data missing or order placement broken.

**Response Time:** <5 min to diagnose, <30 min to recover

**Action:**
```bash
# 1. Acknowledge
echo "Incident acknowledged at $(date)" >> /tmp/incident.log

# 2. Check symptom
python3 audit_dashboard.py --loaders

# 3. Use appropriate runbook
python3 OPERATIONAL_RUNBOOKS.md  # See runbooks section

# 4. Fix and verify
# (Use specific recovery procedure)

# 5. Log for post-mortem
echo "{incident details}" >> /tmp/incidents.json

# 6. Schedule post-mortem (within 24 hours)
```

### SEV-2 (Significant - Urgent Action)

**Definition:** Trading degraded (slow, high slippage, etc).

**Response Time:** <15 min to diagnose, <2 hours to recover

**Action:**
```bash
# 1. Acknowledge
# 2. Gather context (logs, metrics)
# 3. Implement mitigation (feature flag, disable tier)
# 4. Schedule post-mortem (within 1 week)
```

### SEV-3 (Minor - Scheduled Action)

**Definition:** System degradation but no impact on trading.

**Response Time:** Next business day

**Action:**
```bash
# 1. Log the issue
# 2. Schedule investigation
# 3. No emergency post-mortem
```

---

## Backup and Recovery

### Automated Backups

```bash
# RDS automated backups (7-day retention)
aws rds describe-db-instances --db-instance-identifier stocks-data-rds \
  --query 'DBInstances[0].BackupRetentionPeriod'
# Should show: 7

# Check most recent backup
aws rds describe-db-snapshots \
  --db-instance-identifier stocks-data-rds \
  --query 'DBSnapshots[0].{CreateTime:SnapshotCreateTime,Status:Status}'
```

### Manual Backup (Before Major Changes)

```bash
# Create manual snapshot
aws rds create-db-snapshot \
  --db-instance-identifier stocks-data-rds \
  --db-snapshot-identifier stocks-backup-2026-05-09

# Monitor creation
aws rds describe-db-snapshots \
  --db-snapshot-identifier stocks-backup-2026-05-09 \
  --query 'DBSnapshots[0].{Status:Status,PercentProgress:PercentProgress}'

# Should complete in 5-10 minutes
```

### Restore from Backup

```bash
# If database is corrupted or deleted:

# 1. Restore from snapshot
aws rds restore-db-instance-from-db-snapshot \
  --db-instance-identifier stocks-data-restored \
  --db-snapshot-identifier stocks-backup-2026-05-09

# 2. Wait for restore (10-15 minutes)

# 3. Update applications to point to new DB
# Change: DB_HOST=stocks-data-restored (in env)

# 4. Verify data integrity
psql -h stocks-data-restored.xxx.us-east-1.rds.amazonaws.com \
  -U stocks -d stocks -c "SELECT COUNT(*) FROM price_daily;"

# 5. Once verified, delete old broken instance
aws rds delete-db-instance --db-instance-identifier stocks-data-rds --skip-final-snapshot

# 6. Rename restored to original
# (Or update all config to use new name)
```

---

## Cost Optimization

### Current Costs (Monthly)

| Component | Cost | Optimization |
|-----------|------|--------------|
| RDS (61GB) | ~$50 | Multi-AZ disable for dev |
| Lambda API | ~$5 | Provisioned concurrency not needed |
| Lambda Algo | ~$2 | Current memory fine |
| ECS Loaders | ~$15 | Spot instances would save 70% |
| CloudFront | ~$2 | CDN caching excellent |
| S3 | <$1 | Minimal storage |
| **Total** | **~$75** | Could optimize to ~$40 |

### Cost-Saving Measures

```bash
# 1. Use RDS Savings Plan (1-year commitment)
# Saves ~20% on RDS costs (~$10/month)
# Verify: aws ec2 describe-reserved-db-instances

# 2. Use ECS Spot instances for loaders
# Saves ~70% on compute (~$10/month)
# Current: on-demand, switch to spot

# 3. Enable S3 lifecycle policies
# Archive old logs after 30 days
# Minimal savings but good practice

# 4. Monitor CloudWatch spending
aws ce get-cost-and-usage \
  --time-period Start=2026-04-09,End=2026-05-09 \
  --granularity MONTHLY \
  --metrics BlendedCost \
  --group-by Type=SERVICE

# See which services are expensive
```

---

## Troubleshooting Decision Tree

```
START: "Something's wrong"
│
├─ Is the algo running?
│  NO → Check EventBridge schedule (runbook: check Lambda logs)
│  YES ↓
├─ Are signals being generated?
│  NO → Data load problem (runbook: data load fails)
│  YES ↓
├─ Are orders being placed?
│  NO → Signal quality problem (runbook: signal quality degraded)
│  YES ↓
├─ Are orders being filled?
│  NO → Alpaca problem (check Alpaca status page, runbook: stuck orders)
│  YES ↓
├─ Are trades profitable?
│  NO → Strategy issue (not operational, check signal quality)
│  YES ↓
└─ System is healthy ✓

For any issue, check corresponding runbook:
- Data problems → OPERATIONAL_RUNBOOKS.md: Data Load section
- Signal problems → OPERATIONAL_RUNBOOKS.md: Signal Quality section
- Order problems → OPERATIONAL_RUNBOOKS.md: Order sections
- System problems → OPERATIONAL_RUNBOOKS.md: Lambda/Database sections
```

---

## Team Runbook Quick Reference

```
┌─────────────────────────────────────────────┐
│ STOCKS TRADING PLATFORM - OPERATIONS CARD    │
├─────────────────────────────────────────────┤
│ EMERGENCIES                                  │
│ • Data missing → python3 audit_dashboard.py │
│ • Order stuck → python3 order_reconciler.py │
│ • Lambda timeout → aws logs tail ...         │
│ • RDS down → aws rds reboot-db-instance ...│
│                                              │
│ DAILY CHECKLIST (8:30am ET)                 │
│ python3 audit_dashboard.py --loaders        │
│ aws rds describe-db-instances ...           │
│ curl https://api/health                     │
│                                              │
│ ALERTS                                       │
│ CRITICAL → SMS + Email + Slack              │
│ ERROR → Email + Slack                       │
│ WARNING → Slack only                        │
│                                              │
│ RUNBOOKS                                     │
│ • OPERATIONAL_RUNBOOKS.md (10+ scenarios)   │
│ • INCIDENT_RESPONSE_PROCESS.md (post-mort) │
│ • CANARY_DEPLOYMENT_PROCESS.md (releases)  │
│                                              │
│ CONTACTS                                     │
│ • Platform team: #stocks-platform Slack     │
│ • On-call: See rotation doc                 │
│ • AWS Support: Case management               │
└─────────────────────────────────────────────┘
```

---

## Success Criteria - You're Ready for Production When:

✅ **Safety:**
- [ ] All credentials secured (no plaintext)
- [ ] Data quality validated at entry
- [ ] Algo fails closed (won't trade on bad data)
- [ ] Orders reconciled with broker
- [ ] Slippage tracked and normal

✅ **Observability:**
- [ ] All errors logged with trace IDs
- [ ] Alerts route correctly (SMS for CRITICAL only)
- [ ] Audit trail captures all actions
- [ ] Metrics queryable for analysis

✅ **Operations:**
- [ ] Runbooks documented for 10+ scenarios
- [ ] Incidents have post-mortem process
- [ ] Canary deployment process in place
- [ ] Team trained on procedures

✅ **Reliability:**
- [ ] All 26 integration tests pass
- [ ] No data loss under failure
- [ ] Recovery procedures tested
- [ ] Metrics within baseline ranges

✅ **Performance:**
- [ ] Lambda duration <20s
- [ ] API latency <2s
- [ ] RDS queries <200ms
- [ ] Slippage <0.1%

---

**You have everything you need. Go trade with confidence.**

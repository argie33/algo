# Phase 4: CloudWatch Monitoring - Deployment Guide

## Overview

This guide walks through deploying Phase 4 CloudWatch monitoring to your AWS environment.

**Timeline:** ~2-3 hours for full deployment + testing  
**Environments:** dev (required), staging (recommended), prod (with extra validation)  

---

## Pre-Deployment Checklist

### Prerequisites

- [ ] AWS CLI installed and configured
- [ ] Python 3.8+ (for Python setup script)
- [ ] IAM permissions: `logs:*`, `cloudwatch:*`, `sns:*`, `sts:GetCallerIdentity`
- [ ] Access to CloudWatch Logs console
- [ ] Team Slack workspace (for alerts)
- [ ] PagerDuty account (for critical alerts)

### Verification

```bash
# Verify AWS credentials
aws sts get-caller-identity

# Verify log groups exist
aws logs describe-log-groups \
  --query 'logGroups[?contains(logGroupName, `algo`)].logGroupName' \
  --output table
```

---

## Deployment Steps

### Step 1: Review Configuration

```bash
cat monitoring/PHASE4_MONITORING_CONFIG.md
```

Verify thresholds:
- Data Unavailable: 5+ in 5 minutes
- Validation Errors: 10+ in 5 minutes
- Circuit Breaker: ANY (1+)
- Data Staleness: 3+ in 5 minutes

### Step 2: Dry-Run (Recommended)

```bash
# Option A: Bash
chmod +x monitoring/PHASE4_CLOUDWATCH_SETUP.sh
./monitoring/PHASE4_CLOUDWATCH_SETUP.sh --dry-run --environment dev

# Option B: Python
pip install boto3
python monitoring/phase4_setup.py --dry-run --environment dev
```

### Step 3: Deploy to Dev

```bash
# Option A: Bash
./monitoring/PHASE4_CLOUDWATCH_SETUP.sh --environment dev

# Option B: Python
python monitoring/phase4_setup.py --environment dev
```

Expected output shows:
- 8 metric filters created
- 5 metric alarms created
- 2 composite alarms created
- 2 SNS topics created
- Log retention policies set

### Step 4: Verify Deployment

```bash
# List metric filters
aws logs describe-metric-filters \
  --log-group-name "/aws/lambda/algo-api-dev" \
  --query 'metricFilters[*].filterName' \
  --output text

# List alarms
aws cloudwatch describe-alarms \
  --query "MetricAlarms[?contains(AlarmName, 'algo-')].AlarmName" \
  --output text

# Verify SNS topics
aws sns list-topics \
  --query "Topics[?contains(TopicArn, 'algo-')].TopicArn" \
  --output text
```

### Step 5: Configure SNS Subscriptions

Follow PHASE4_SNS_SETUP.md:

```bash
cat monitoring/PHASE4_SNS_SETUP.md
```

Key steps:
1. Create Slack webhook integration
2. Subscribe Slack to alerts topic
3. Add team email to alerts topic
4. Configure PagerDuty for critical topic

### Step 6: Deploy Dashboard

```bash
aws cloudwatch put-dashboard \
  --dashboard-name "algo-failfast-dev" \
  --dashboard-body "file://monitoring/PHASE4_CLOUDWATCH_DASHBOARD.json"

# Verify
aws cloudwatch list-dashboards \
  --query 'DashboardEntries[?contains(DashboardName, `algo-failfast`)].DashboardName' \
  --output text
```

### Step 7: Test Monitoring

```bash
bash monitoring/PHASE4_TESTING_STEPS.md
```

Key tests:
- Verify metric filters exist
- Emit test log events
- Verify metrics appear
- Trigger alarms
- Verify SNS notifications

---

## Staging & Production Rollout

### Prerequisites for Staging

- [ ] Phase 4 metrics verified in dev for 24+ hours
- [ ] No false positives from dev baseline
- [ ] Team trained on new alerts
- [ ] Escalation contacts configured

### Staged Rollout

1. **Deploy to staging:**
   ```bash
   ./monitoring/PHASE4_CLOUDWATCH_SETUP.sh --environment staging
   ```

2. **Test for 24-48 hours**

3. **Deploy to production:**
   ```bash
   ./monitoring/PHASE4_CLOUDWATCH_SETUP.sh --environment prod
   ```

4. **Enable PagerDuty for production**

---

## Threshold Tuning

After 1-2 weeks, analyze baseline and adjust thresholds if needed.

### Find Baseline

```bash
aws cloudwatch get-metric-statistics \
  --namespace "Algo/FailFast" \
  --metric-name "DataUnavailableErrors" \
  --start-time "$(date -u -d '7 days ago' +%Y-%m-%dT%H:%M:%SZ)" \
  --end-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --period 300 \
  --statistics Average,Max
```

### Adjust Threshold

```bash
aws cloudwatch put-metric-alarm \
  --alarm-name "algo-data-unavailability-alert-dev" \
  --threshold 10 \
  # ... (keep other parameters)
```

---

## Rollback Procedure

### Option 1: Disable Individual Alarms

```bash
aws cloudwatch disable-alarm-actions \
  --alarm-names "algo-data-unavailability-alert-dev"

# Later, re-enable
aws cloudwatch enable-alarm-actions \
  --alarm-names "algo-data-unavailability-alert-dev"
```

### Option 2: Delete All Phase 4 Resources

```bash
#!/bin/bash
ENVIRONMENT="dev"

# Delete alarms
for alarm in $(aws cloudwatch describe-alarms \
  --query 'MetricAlarms[?contains(AlarmName, `algo-`)].AlarmName' \
  --output text); do
  aws cloudwatch delete-alarms --alarm-names "$alarm"
done

# Delete composite alarms
for alarm in $(aws cloudwatch describe-alarms \
  --query 'CompositeAlarms[?contains(AlarmName, `algo-`)].AlarmName' \
  --output text); do
  aws cloudwatch delete-alarms --alarm-names "$alarm"
done

# Delete metric filters
for lg in "/aws/lambda/algo-api-${ENVIRONMENT}" "/aws/lambda/algo-algo-${ENVIRONMENT}"; do
  for filter in $(aws logs describe-metric-filters \
    --log-group-name "$lg" \
    --query 'metricFilters[*].filterName' \
    --output text); do
    aws logs delete-metric-filter --log-group-name "$lg" --filter-name "$filter"
  done
done

# Delete dashboard
aws cloudwatch delete-dashboards --dashboard-names "algo-failfast-${ENVIRONMENT}"
```

---

## Post-Deployment Validation

- [ ] All 8 metric filters created
- [ ] All 5 metric alarms created
- [ ] All 2 composite alarms created
- [ ] SNS topics exist with subscriptions
- [ ] CloudWatch dashboard displays metrics
- [ ] Test log events generate metric data
- [ ] Alarms transition to ALARM state when threshold exceeded
- [ ] SNS notifications received for test alarms
- [ ] Runbooks accessible to team
- [ ] On-call team trained

---

## Support

For deployment issues, see:
- Setup: PHASE4_CLOUDWATCH_SETUP.sh or phase4_setup.py
- Testing: PHASE4_TESTING_STEPS.md
- Alerts: PHASE4_OPERATOR_RUNBOOKS.md
- SNS: PHASE4_SNS_SETUP.md

---

**Last Updated:** 2026-07-04

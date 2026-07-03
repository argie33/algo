# Phase 4: CloudWatch Monitoring - Testing & Verification

## Overview

Step-by-step instructions to verify Phase 4 CloudWatch monitoring is working correctly.

**Timeline:** ~45 minutes for full verification

---

## Pre-Test Checklist

```bash
# Verify AWS credentials
aws sts get-caller-identity

# Verify log groups exist
aws logs describe-log-groups --query 'logGroups[?contains(logGroupName, `algo`)].logGroupName' --output table
```

---

## Test 1: Verify Metric Filters Exist

### Step 1a: List metric filters

```bash
aws logs describe-metric-filters \
  --log-group-name "/aws/lambda/algo-api-dev" \
  --query 'metricFilters[*].[filterName, filterPattern]' \
  --output table
```

Expected filters:
- DataUnavailableErrors
- ValidationErrors
- DataStalenessErrors
- HardeningErrors
- AllErrors

### Step 1b: Verify CircuitBreakerHalts filter

```bash
aws logs describe-metric-filters \
  --log-group-name "/aws/lambda/algo-circuit-breaker-dev" \
  --query 'metricFilters[*].filterName' \
  --output text
```

Expected: CircuitBreakerHalts

---

## Test 2: Generate Test Events & Verify Metrics

### Step 2a: Create test log stream

```bash
LOG_GROUP="/aws/lambda/algo-api-dev"
TEST_STREAM="test-phase4-$(date +%s)"

aws logs create-log-stream \
  --log-group-name "$LOG_GROUP" \
  --log-stream-name "$TEST_STREAM"

echo "Created test stream: $TEST_STREAM"
```

### Step 2b: Emit test events

```bash
TIMESTAMP=$(date +%s000)

# Test 1: Data Unavailable
aws logs put-log-events \
  --log-group-name "$LOG_GROUP" \
  --log-stream-name "$TEST_STREAM" \
  --log-events "[{\"message\":\"[FAIL_FAST] data_unavailable: true\",\"timestamp\":$TIMESTAMP}]"

# Test 2: Validation Error
TIMESTAMP=$((TIMESTAMP + 1000))
aws logs put-log-events \
  --log-group-name "$LOG_GROUP" \
  --log-stream-name "$TEST_STREAM" \
  --log-events "[{\"message\":\"[HARDENING] validation error: Cannot convert None to float\",\"timestamp\":$TIMESTAMP}]"

# Test 3: Data Staleness
TIMESTAMP=$((TIMESTAMP + 1000))
aws logs put-log-events \
  --log-group-name "$LOG_GROUP" \
  --log-stream-name "$TEST_STREAM" \
  --log-events "[{\"message\":\"[DATA QUALITY] stale: true\",\"timestamp\":$TIMESTAMP}]"

# Test 4: Hardening Error
TIMESTAMP=$((TIMESTAMP + 1000))
aws logs put-log-events \
  --log-group-name "$LOG_GROUP" \
  --log-stream-name "$TEST_STREAM" \
  --log-events "[{\"message\":\"[HARDENING] error: Invalid schema\",\"timestamp\":$TIMESTAMP}]"

echo "Waiting 2 minutes for metrics to propagate..."
sleep 120
```

### Step 2c: Verify metrics appeared

```bash
# Check DataUnavailableErrors
aws cloudwatch get-metric-statistics \
  --namespace "Algo/FailFast" \
  --metric-name "DataUnavailableErrors" \
  --start-time "$(date -u -d '5 minutes ago' +%Y-%m-%dT%H:%M:%SZ)" \
  --end-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --period 300 \
  --statistics Sum \
  --output table

# Check ValidationErrors
aws cloudwatch get-metric-statistics \
  --namespace "Algo/FailFast" \
  --metric-name "ValidationErrors" \
  --start-time "$(date -u -d '5 minutes ago' +%Y-%m-%dT%H:%M:%SZ)" \
  --end-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --period 300 \
  --statistics Sum \
  --output table
```

Expected: Each metric should show at least 1 datapoint

---

## Test 3: Verify Alarms Exist

### Step 3a: List all alarms

```bash
aws cloudwatch describe-alarms \
  --query "MetricAlarms[?contains(AlarmName, 'algo-')].[ AlarmName, MetricName, Threshold]" \
  --output table
```

Expected alarms:
- algo-data-unavailability-alert-dev (threshold 5)
- algo-validation-error-alert-dev (threshold 10)
- algo-circuit-breaker-halt-dev (threshold 1)
- algo-data-staleness-alert-dev (threshold 3)
- algo-hardening-error-alert-dev (threshold 15)

### Step 3b: Verify SNS actions

```bash
aws cloudwatch describe-alarms \
  --alarm-names "algo-data-unavailability-alert-dev" \
  --query 'MetricAlarms[0].AlarmActions' \
  --output text
```

Expected: SNS topic ARN

---

## Test 4: Trigger Alarms

### Step 4a: Generate high-volume test events

```bash
LOG_GROUP="/aws/lambda/algo-api-dev"
VOLUME_TEST_STREAM="test-high-volume-$(date +%s)"

aws logs create-log-stream \
  --log-group-name "$LOG_GROUP" \
  --log-stream-name "$VOLUME_TEST_STREAM"

# Generate 10 data unavailable errors (exceeds threshold of 5)
TIMESTAMP=$(date +%s000)
for i in {1..10}; do
  TIMESTAMP=$((TIMESTAMP + 100))
  aws logs put-log-events \
    --log-group-name "$LOG_GROUP" \
    --log-stream-name "$VOLUME_TEST_STREAM" \
    --log-events "[{\"message\":\"[FAIL_FAST] Test $i: data_unavailable: true\",\"timestamp\":$TIMESTAMP}]" \
    2>/dev/null || true
done

echo "Emitted 10 data unavailable errors"
echo "Waiting 5 minutes for alarm to evaluate..."
sleep 300

# Check alarm state
aws cloudwatch describe-alarms \
  --alarm-names "algo-data-unavailability-alert-dev" \
  --query 'MetricAlarms[0].[AlarmName, StateValue]' \
  --output text
```

Expected: Alarm state changes to ALARM

---

## Test 5: Verify Dashboard

### Step 5a: Create dashboard

```bash
aws cloudwatch put-dashboard \
  --dashboard-name "algo-failfast-dev" \
  --dashboard-body "file://monitoring/PHASE4_CLOUDWATCH_DASHBOARD.json"
```

### Step 5b: Verify in console

1. Open CloudWatch console
2. Navigate to Dashboards
3. Open algo-failfast-dev
4. Verify all widgets load

---

## Test 6: Circuit Breaker Alert (CRITICAL)

```bash
TIMESTAMP=$(date +%s000)
LOG_GROUP="/aws/lambda/algo-circuit-breaker-dev"
CB_TEST_STREAM="test-cb-$(date +%s)"

aws logs create-log-stream \
  --log-group-name "$LOG_GROUP" \
  --log-stream-name "$CB_TEST_STREAM" 2>/dev/null || true

aws logs put-log-events \
  --log-group-name "$LOG_GROUP" \
  --log-stream-name "$CB_TEST_STREAM" \
  --log-events "[{\"message\":\"[CIRCUIT_BREAKER] HALTING TRADING - portfolio drawdown -15.5%\",\"timestamp\":$TIMESTAMP}]"

echo "Waiting 2 minutes..."
sleep 120

# Verify metric appeared
aws cloudwatch get-metric-statistics \
  --namespace "Algo/FailFast" \
  --metric-name "CircuitBreakerHalts" \
  --start-time "$(date -u -d '5 minutes ago' +%Y-%m-%dT%H:%M:%SZ)" \
  --end-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --period 300 \
  --statistics Sum \
  --output json

# Verify alarm triggered
aws cloudwatch describe-alarms \
  --alarm-names "algo-circuit-breaker-halt-dev" \
  --query 'MetricAlarms[0].[AlarmName, StateValue]' \
  --output text
```

---

## Test 7: Cleanup

```bash
# Delete test log streams
aws logs delete-log-stream \
  --log-group-name "/aws/lambda/algo-api-dev" \
  --log-stream-name "$TEST_STREAM" 2>/dev/null || true

aws logs delete-log-stream \
  --log-group-name "/aws/lambda/algo-api-dev" \
  --log-stream-name "$VOLUME_TEST_STREAM" 2>/dev/null || true

aws logs delete-log-stream \
  --log-group-name "/aws/lambda/algo-circuit-breaker-dev" \
  --log-stream-name "$CB_TEST_STREAM" 2>/dev/null || true

echo "Cleaned up test streams"
```

---

## Success Criteria

- [ ] All 6 metric filters appear in log groups
- [ ] Test events generate metrics
- [ ] All 5 metric alarms exist
- [ ] All 2 composite alarms exist
- [ ] SNS topics have alarm actions
- [ ] Dashboard exists and displays widgets
- [ ] Test events trigger alarms
- [ ] Metrics appear in real-time

---

## Troubleshooting

### Metrics don't appear after 2 minutes

1. Verify log pattern matches actual messages
2. Check metric filter in CloudWatch console
3. Verify log events were actually written

### Alarm doesn't trigger

1. Verify threshold is correct
2. Ensure evaluation period has passed (usually 5 min)
3. Check if alarm actions are configured

### SNS notifications not received

1. Verify topic subscriptions
2. Test SNS directly:
   ```bash
   aws sns publish \
     --topic-arn "arn:aws:sns:us-east-1:ACCOUNT_ID:algo-alerts-dev" \
     --subject "Test" \
     --message "Test message"
   ```

---

**Last Updated:** 2026-07-04

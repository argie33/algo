# Phase 4: Monitoring Configuration - Fail-Fast Error Alerting

## Objective
Monitor new fail-fast error patterns introduced in Phase 4 and Phase 3:
- Data unavailable errors (loaders, calculators)
- Validation failures
- Circuit breaker halts
- Stale data conditions

## CloudWatch Monitoring Strategy

### 1. Log Patterns to Monitor

#### Pattern 1: Data Unavailable Errors
```
[FAIL_FAST] ... data_unavailable: true
[HARDENING] ... Data unavailable: ...
```

**Alert Threshold**: 5+ occurrences in 5 minutes  
**Severity**: WARNING  
**Action**: Investigate data loader status

#### Pattern 3: Circuit Breaker Halts
```
[CIRCUIT_BREAKER] ... HALTING TRADING
```

**Alert Threshold**: Any occurrence  
**Severity**: CRITICAL  
**Action**: Immediate investigation and manual override authority

#### Pattern 4: Data Staleness
```
[DATA QUALITY] ... stale: true
```

**Alert Threshold**: 3+ occurrences in 5 minutes  
**Severity**: WARNING  
**Action**: Investigate loader/data source issues

### 2. Metric-Based Alarms

#### Alarm 1: Data Unavailability Rate
- **Metric**: `DataUnavailableErrors` count
- **Threshold**: > 10 per minute
- **Duration**: 5 minutes
- **Action**: SNS notification

#### Alarm 3: Circuit Breaker Halt
- **Metric**: `CircuitBreakerHalt` count
- **Threshold**: > 0 (any halt)
- **Duration**: Immediate
- **Action**: CRITICAL SNS + Page on-call

#### Alarm 4: Data Staleness
- **Metric**: `DataStalenessErrors` count
- **Threshold**: > 3 per 5 minutes
- **Duration**: 5 minutes
- **Action**: SNS notification

## Implementation Plan

### Step 1: Create Log Groups (Already in CloudWatch)
- ✅ `/aws/lambda/algo-api-dev` - API Lambda logs
- ✅ `/aws/lambda/algo-algo-dev` - Orchestrator logs
- ✅ `/aws/lambda/algo-circuit-breaker-dev` - Circuit breaker logs

### Step 2: Create Metric Filters
For each pattern, create a metric filter:

```bash
aws logs put-metric-filter \
  --log-group-name /aws/lambda/algo-api-dev \
  --filter-name DataUnavailableErrors \
  --filter-pattern '[... "data_unavailable" = true, ...]' \
  --metric-transformations metricName=DataUnavailableErrors,metricValue=1
```

### Step 3: Create CloudWatch Alarms
For each metric, create an alarm:

```bash
aws cloudwatch put-metric-alarm \
  --alarm-name DataUnavailabilityAlert \
  --metric-name DataUnavailableErrors \
  --threshold 10 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 1 \
  --period 300 \
  --alarm-actions arn:aws:sns:us-east-1:...:alerts
```

### Step 4: Create CloudWatch Dashboard
- Widget 1: Error rate over time
- Widget 2: Error type breakdown (pie chart)
- Widget 3: Errors by endpoint (bar chart)
- Widget 4: Circuit breaker halt history (timeline)
- Widget 5: Data staleness timeline

### Step 5: SNS Notifications
Configure routing:
- **CRITICAL** (Circuit breaker) → Page on-call
- **WARNING** (Data unavailable) → Slack #alerts
- **INFO** (Metrics) → CloudWatch Dashboard only

## Alerting Rules

### When to Alert (and why)

| Event | Alert? | Reason | Action |
|-------|--------|--------|--------|
| 1x data unavailable | No | Normal during startup | Monitor |
| 5+ in 5min | Yes | Sustained issue | Investigate loader |
| Circuit breaker halt | Yes | Trading blocked | Manual override |
| Hardening error | Yes | Data validation failure | Check transformations |
| Stale data (market open) | Yes | Critical for trading | Page on-call |
| Stale data (market closed) | No | Expected | Monitor |

## Testing Alerts

### Test 1: Verify metric filter works
```bash
# Emit test log message with pattern
echo '[FAIL_FAST] Test data_unavailable: true' | \
  aws logs put-log-events \
  --log-group-name /aws/lambda/algo-api-dev \
  --log-stream-name test

# Wait 1 minute for metric to appear
aws cloudwatch get-metric-statistics \
  --metric-name DataUnavailableErrors \
  --start-time 2026-07-03T00:00:00Z \
  --end-time 2026-07-03T01:00:00Z \
  --period 300
```

### Test 2: Verify alarm triggers
```bash
# Generate enough events to trigger alarm
for i in {1..15}; do
  echo "Test error $i" >> test.log
done

# Wait 5 minutes, verify alarm state changed to ALARM
aws cloudwatch describe-alarms --alarm-names DataUnavailabilityAlert
```

## Monitoring Dashboard

Create CloudWatch Dashboard with:

```json
{
  "widgets": [
    {
      "type": "metric",
      "properties": {
        "metrics": [
          ["AWS/Lambda", "DataUnavailableErrors"],
          ["AWS/Lambda", "CircuitBreakerHalts"],
          ["AWS/Lambda", "DataStalenessErrors"],
          ["AWS/Lambda", "HardeningErrors"]
        ],
        "period": 300,
        "stat": "Sum",
        "region": "us-east-1",
        "title": "Fail-Fast Errors"
      }
    },
    {
      "type": "log",
      "properties": {
        "query": "fields @timestamp, @message | filter @message like /data_unavailable/ | stats count() by bin(5m)",
        "region": "us-east-1",
        "title": "Data Unavailability Timeline"
      }
    }
  ]
}
```

## Success Metrics

| Metric | Target |
|--------|--------|
| Alert coverage | 100% of fail-fast patterns |
| False positive rate | < 2% |
| Alert latency | < 2 minutes from event |
| On-call response time | < 5 minutes |
| Dashboard uptime | > 99.9% |

## Rollout Plan

### Week 1: Setup & Validation
- [ ] Create metric filters
- [ ] Create alarms
- [ ] Validate with test events
- [ ] Setup SNS routing

### Week 2: Tuning & Alerts
- [ ] Adjust thresholds based on baseline
- [ ] Test alerting paths (email, Slack, page)
- [ ] Document runbook for each alert

### Week 3: Production
- [ ] Enable all alerts
- [ ] Monitor for false positives
- [ ] Adjust thresholds as needed

## Runbook Templates

### Alert: DataUnavailabilityAlert
**Severity**: WARNING  
**Trigger**: > 10 data unavailable errors in 5 minutes

**Investigation Steps**:
1. Check which loader is failing (look in logs)
2. Verify data source availability
3. Check if market is open (expected on weekends)
4. Restart loader if needed

**Resolution**:
- [ ] Fix data source issue
- [ ] Restart affected loader
- [ ] Verify data freshness recovered
- [ ] Close alert

### Alert: CircuitBreakerHalt
**Severity**: CRITICAL  
**Trigger**: Any circuit breaker halt event

**Investigation Steps**:
1. Immediately page on-call engineer
2. Check circuit breaker logs for halt reason
3. Verify market conditions (not a circuit halt)
4. Check portfolio drawdown

**Resolution**:
- [ ] Diagnose halt cause
- [ ] Fix underlying issue
- [ ] Manual override if needed
- [ ] Document incident
- [ ] Close alert

## Success Criteria

Phase 4 is complete when:
- ✅ All fail-fast patterns have metric filters
- ✅ All critical alerts configured and tested
- ✅ Alert routing verified (SNS → email/Slack/page)
- ✅ CloudWatch dashboard created
- ✅ Runbooks documented
- ✅ Team trained on new alerts
- ✅ 0 missed alerts in 1 week of monitoring

---

**Phase 4 Status**: Ready for Implementation  
**Implementation Time**: 2-4 hours  
**Deployment Date**: 2026-07-04 (post-testing)

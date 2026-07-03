# Phase 4: Operator Runbooks

## Overview

Step-by-step runbooks for on-call engineers to diagnose and resolve Phase 4 monitoring alerts.

**Emergency Contact:** Email/SMS alerts  
**SLAs:** CRITICAL 5 min, WARNING 15 min

---

## Runbook: Circuit Breaker Halt (CRITICAL)

**Severity:** CRITICAL - Trading is blocked  
**SLA:** Respond within 5 minutes

### What Triggered This

A circuit breaker has halted all trading due to a detected risk condition.

### Immediate Actions (< 2 minutes)

1. Page the incident commander
2. Check circuit breaker logs

```bash
aws logs tail /aws/lambda/algo-circuit-breaker-dev --follow --since 15m | grep "HALTING"
```

### Investigation (2-5 minutes)

1. **Check halt reason:**
   ```bash
   aws logs tail /aws/lambda/algo-circuit-breaker-dev --follow --since 30m | grep "CIRCUIT_BREAKER"
   ```

2. **Determine if legitimate:**
   - Portfolio drawdown > 15%? (Check market conditions)
   - Daily loss threshold? (Check position P&L)
   - Consecutive losses? (Check trade history)

3. **Check market conditions:**
   - Is NYSE/NASDAQ halted?
   - Check VIX level
   - Check major financial news

### Resolution

**Path A: Market condition → Wait for recovery**

**Path B: Data issue → Restart loader**

```bash
aws lambda invoke \
  --function-name algo-data-loader-dev \
  --payload '{"force_refresh": true}' \
  response.json
```

**Path C: Risk threshold too tight → Review and adjust**

### Completion

- [ ] Root cause identified
- [ ] Action taken (wait/restart/adjust)
- [ ] Alert cleared
- [ ] Incident documented

---

## Runbook: Data Unavailability (WARNING)

**Severity:** WARNING  
**SLA:** Respond within 15 minutes

### What Triggered This

Data loaders are reporting missing upstream data.

### Quick Diagnosis

```bash
# Find which loader is failing
aws logs tail /aws/lambda/algo-api-dev --since 30m | grep "data_unavailable"

# Check data freshness
# In database: SELECT * FROM loader_execution_log ORDER BY start_time DESC LIMIT 5;
```

### Check Common Loaders

**SEC Filings:**
```bash
aws logs tail /aws/lambda/algo-api-dev --since 30m | grep -i "sec.*error\|sec.*fail"
```

**Price/Volume:**
```bash
aws logs tail /aws/lambda/algo-api-dev --since 30m | grep -i "price.*error\|yfinance"
```

**Earnings:**
```bash
aws logs tail /aws/lambda/algo-api-dev --since 30m | grep -i "earnings.*error"
```

### Common Causes & Fixes

**Rate limit exceeded:** Implement backoff (usually automatic)

**Data source unavailable:** 
1. Check upstream service status
2. Verify network connectivity
3. Wait for recovery if external service

**Missing records:**
1. Check if new IPOs (expected)
2. Restart loader:
   ```bash
   aws lambda invoke \
     --function-name algo-data-loader-dev \
     --payload '{"loaders": ["SEC"], "force_refresh": true}' \
     response.json
   ```

### Completion

- [ ] Loader identified
- [ ] Loader restarted if needed
- [ ] Verify data freshness recovered
- [ ] Alert cleared

---

## Runbook: Data Staleness (WARNING)

**Severity:** WARNING  
**SLA:** Respond within 15 minutes (during market hours)

### What Triggered This

Market data is older than expected.

### Quick Check

```bash
# Is market open?
date
# Market hours: 9:30am - 4pm ET, Mon-Fri
```

**If market closed:** Dismiss alert (expected)  
**If market open:** Investigate

### Diagnosis

```bash
# Check data freshness
# In database:
# SELECT MAX(data_timestamp) FROM price_data WHERE data_timestamp > NOW() - INTERVAL '1 hour';

# Check loader status
aws logs tail /aws/lambda/algo-api-dev --since 30m | grep "price"
```

### Resolution

1. Check if price loader ran recently
2. If not, restart:
   ```bash
   aws lambda invoke \
     --function-name algo-price-loader-dev \
     --payload '{"force_refresh": true}' \
     response.json
   ```

3. Wait 2 minutes
4. Verify data freshness recovered

### Completion

- [ ] Determined if market open
- [ ] Loader restarted if needed
- [ ] Data freshness verified
- [ ] Alert cleared

---

## Runbook: Hardening Errors (WARNING)

**Severity:** WARNING  
**SLA:** Respond within 15 minutes

### What Triggered This

API hardening validation (Phase 3.5) is detecting errors.

### Diagnosis

```bash
# See error details
aws logs tail /aws/lambda/algo-api-dev --since 30m | grep "HARDENING"
```

### Resolution

Follow Validation Errors runbook above - usually same root cause.

---

## Runbook: Data Quality Crisis (CRITICAL)

**Severity:** CRITICAL - Missing AND stale data  
**SLA:** Respond within 5 minutes

### What Triggered This

**CRITICAL:** Both data unavailable AND data staleness detected simultaneously.

### Immediate Actions

1. Page incident commander immediately
2. Disable trading (if safe):
   ```bash
   # In database:
   # UPDATE algo_config SET trading_enabled = false WHERE name = 'system_wide_trading_gate';
   ```

3. Gather metrics:
   ```bash
   aws cloudwatch get-metric-statistics \
     --namespace "Algo/FailFast" \
     --metric-name "DataUnavailableErrors" \
     --start-time "$(date -u -d '30 minutes ago' +%Y-%m-%dT%H:%M:%SZ)" \
     --end-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
     --period 300 \
     --statistics Sum
   ```

### Investigation

1. **Check all data loaders:**
   ```bash
   aws logs tail /aws/lambda/algo-api-dev --since 30m
   ```

2. **Check database connectivity:**
   ```bash
   # From Lambda:
   # psql postgresql://user:pass@host:5432/algo -c "SELECT 1;"
   ```

3. **Check AWS service health:**
   - Lambda running?
   - RDS accessible?
   - Network/VPC working?

### Resolution Paths

**Database connection lost:**
```bash
aws rds describe-db-instances --query 'DBInstances[0].DBInstanceStatus'

# If down, reboot:
aws rds reboot-db-instance --db-instance-identifier algo-db-dev
```

**Lambda runtime issue:**
```bash
# Check function
aws lambda get-function --function-name algo-data-loader-dev
```

**Upstream data source down:**
- Check status pages
- Verify network can reach external APIs

### Post-Crisis

1. **Verify data quality:**
   ```bash
   # In database:
   # SELECT COUNT(*) total, COUNT(*) FILTER (WHERE data_unavailable = true) 
   # FROM scoring_results WHERE calc_date = CURRENT_DATE;
   # Should have < 5% unavailable
   ```

2. **Re-enable trading:**
   ```bash
   # UPDATE algo_config SET trading_enabled = true WHERE name = 'system_wide_trading_gate';
   ```

3. **Document incident**

### Completion

- [ ] Trading disabled if needed
- [ ] All loaders checked
- [ ] Root cause fixed
- [ ] Data quality verified
- [ ] Trading re-enabled
- [ ] Incident documented

---

## Escalation Path

If unresolved within SLA:

1. **5 min (CRITICAL):** Page team lead
2. **15 min (CRITICAL):** Page incident commander  
3. **15 min (WARNING):** Page team lead
4. **30 min (WARNING):** Page incident commander

---

## On-Call Responsibilities

- [ ] Respond to pages within 2 minutes
- [ ] Follow appropriate runbook
- [ ] Document actions taken
- [ ] Escalate if needed
- [ ] Post-incident report within 2 hours

---

## Useful Commands Reference

```bash
# Set environment
export ENVIRONMENT="dev"

# Check metric in real-time
aws cloudwatch get-metric-statistics \
  --namespace "Algo/FailFast" \
  --metric-name "DataUnavailableErrors" \
  --start-time "$(date -u -d '5 minutes ago' +%Y-%m-%dT%H:%M:%SZ)" \
  --end-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --period 60 \
  --statistics Sum

# Tail logs in real-time
aws logs tail /aws/lambda/algo-api-${ENVIRONMENT} --follow --since 10m

# Get function details
aws lambda get-function-configuration --function-name algo-api-${ENVIRONMENT}

# Reset alarm state
aws cloudwatch set-alarm-state \
  --alarm-name "algo-data-unavailability-alert-dev" \
  --state-value OK \
  --state-reason "Manual reset after resolution"
```

---

**Last Updated:** 2026-07-04

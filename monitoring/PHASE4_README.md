# Phase 4: CloudWatch Monitoring Setup

## What is Phase 4?

Phase 4 implements comprehensive CloudWatch monitoring for fail-fast error patterns introduced in Phase 3.5 (API hardening) and Phase 4 (validation enforcement).

**Key Principle:** Detect data quality and trading safety failures in real-time, with automated alerting to on-call engineers.

### Why Phase 4?

Without monitoring:
- Silent failures: Loaders fail silently, scores use stale/incomplete data
- Delayed detection: Hours before ops team notices trading is halted
- No visibility: Can't tell if problem is data, API, or infrastructure

With Phase 4:
- Immediate alerts: < 5 min from failure to notification
- Clear diagnostics: Metrics show exactly which error type and when
- Automated routing: Critical alerts page on-call, warnings go to Slack
- Dashboard: Real-time view of system health

---

## Quick Start

### 1. Review Configuration

```bash
cat monitoring/PHASE4_MONITORING_CONFIG.md
```

Understand what errors we're monitoring and alert thresholds.

### 2. Deploy (Pick One)

#### Option A: Bash Script (Recommended)

```bash
./monitoring/PHASE4_CLOUDWATCH_SETUP.sh --environment dev
```

#### Option B: Python Script

```bash
python monitoring/phase4_setup.py --environment dev
```

### 3. Configure SNS

```bash
# Subscribe team to alert topics
cat monitoring/PHASE4_SNS_SETUP.md
```

### 4. Test Monitoring

```bash
# Verify everything works
cat monitoring/PHASE4_TESTING_STEPS.md
```

### 5. Deploy Dashboard

```bash
aws cloudwatch put-dashboard \
  --dashboard-name "algo-failfast-dev" \
  --dashboard-body "file://monitoring/PHASE4_CLOUDWATCH_DASHBOARD.json"
```

---

## What Gets Created

### Metric Filters (8)

These detect specific error patterns in CloudWatch Logs:

| Filter | Pattern | Namespace |
|--------|---------|-----------|
| DataUnavailableErrors | [FAIL_FAST] data_unavailable: true | Algo/FailFast |
| ValidationErrors | [HARDENING] validation error | Algo/FailFast |
| CircuitBreakerHalts | [CIRCUIT_BREAKER] HALTING TRADING | Algo/FailFast |
| DataStalenessErrors | [DATA QUALITY] stale: true | Algo/FailFast |
| HardeningErrors | [HARDENING] error | Algo/FailFast |

### CloudWatch Alarms (5 Metric + 2 Composite)

**Metric Alarms:** Data unavailability, Validation errors, Circuit breaker halt, Data staleness, Hardening errors

**Composite Alarms:** Data quality crisis (CRITICAL), API unhealthy (WARNING)

### SNS Topics (2)

- algo-alerts-dev → Slack #alerts + Email (WARNING)
- algo-critical-dev → PagerDuty + SMS (CRITICAL)

### CloudWatch Dashboard (1)

algo-failfast-dev with 14 widgets showing error trends and timelines

---

## File Structure

| File | Purpose |
|------|---------|
| PHASE4_README.md | This file - overview and quick start |
| PHASE4_MONITORING_CONFIG.md | Alert thresholds and log patterns |
| PHASE4_DEPLOYMENT_GUIDE.md | Step-by-step deployment |
| PHASE4_CLOUDWATCH_SETUP.sh | Bash setup script |
| phase4_setup.py | Python setup script |
| PHASE4_CLOUDWATCH_DASHBOARD.json | Dashboard configuration |
| PHASE4_SNS_SETUP.md | SNS subscription guide |
| PHASE4_TESTING_STEPS.md | Verification tests |
| PHASE4_OPERATOR_RUNBOOKS.md | Incident response |
| PHASE4_INDEX.md | File index and workflows |

---

## Alert Runbooks Summary

When paged:

**Circuit Breaker Halt (CRITICAL):** See PHASE4_OPERATOR_RUNBOOKS.md - trading halted, investigate within 5 min

**Data Unavailability (WARNING):** See PHASE4_OPERATOR_RUNBOOKS.md - loaders failing, respond within 15 min

**Validation Errors (WARNING):** See PHASE4_OPERATOR_RUNBOOKS.md - schema mismatch, respond within 15 min

**Data Staleness (WARNING):** See PHASE4_OPERATOR_RUNBOOKS.md - stale data, respond within 15 min

**Data Quality Crisis (CRITICAL):** See PHASE4_OPERATOR_RUNBOOKS.md - missing AND stale data, respond within 5 min

---

## See Also

- PHASE4_DEPLOYMENT_GUIDE.md - Deployment steps
- PHASE4_OPERATOR_RUNBOOKS.md - Incident procedures
- steering/GOVERNANCE.md - Fail-fast principles

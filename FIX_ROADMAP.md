# Fix Roadmap - Prioritized Action Plan

**Timeline**: 7-10 hours total work  
**Target**: Production ready by 2026-08-01

---

## THIS WEEK (7 hours)

These fixes must be completed before go-live. All involve verification and script creation.

### Step 1: Create System Diagnostics Script (1 hour)
**Priority**: CRITICAL  
**Enables**: Validation of all other fixes

```bash
# File: scripts/comprehensive_diagnostics.py
# Creates a complete system health check covering:
# - Database connection pool
# - Lock status and health
# - Loader performance/recent runs
# - Data consistency
# - Configuration validation
# - Recent errors (24h)

# After creation, run:
python scripts/comprehensive_diagnostics.py
# Should have 0 HIGH severity issues
```

**Acceptance**: Script runs, returns no HIGH severity alerts

---

### Step 2: Verify Loader Scheduler (30 min)
**Priority**: CRITICAL  
**Blocks**: Production launch

```bash
# Check if orchestrator_scheduler.py is set up correctly
cat scripts/orchestrator_scheduler.py

# Verify EventBridge/cron is configured
python scripts/orchestrator_scheduler.py --verify

# Expected output:
# ✓ Scheduler configured for 4-6 hour intervals
# ✓ Next run scheduled: [timestamp]
# ✓ Recent runs: [list of successful runs]
```

**Acceptance**: Scheduler configured and verified operational

---

### Step 3: Test Alert Channels (30 min)
**Priority**: CRITICAL  
**Blocks**: Production launch

```bash
# Test email alerting
python -c "
import os, smtplib
# Send test email to ALERT_EMAIL_TO
# Verify receipt in inbox
"

# Test SNS alerting (if AWS configured)
python -c "
import boto3
sns = boto3.client('sns')
# Send test message to ALERTS_SNS_TOPIC
# Verify receipt
"

# Expected:
# ✓ Email received within 2 minutes
# ✓ SNS message received within 30 seconds
# ✓ Message formatting correct
```

**Acceptance**: Both channels receive test messages successfully

---

### Step 4: Audit High-Completeness Stocks (1.5 hours)
**Priority**: HIGH  
**Impact**: Affects 6 stocks with suppressed quality scores

**Stocks**: BAR, GRN, BCH, AZUL, GAIN, AEM

```bash
# For each stock, verify:

# 1. Check ticker→CIK mapping
SELECT ticker, cik FROM sec_mappings WHERE ticker IN ('BAR','GRN','BCH','AZUL','GAIN','AEM');

# 2. Check if SEC data exists
SELECT * FROM quality_metrics 
WHERE ticker = 'BAR' LIMIT 1;

# 3. Check loader logs for failures
SELECT * FROM loader_execution_log 
WHERE loader_name LIKE 'quality_metrics' 
AND status = 'failed'
ORDER BY started_at DESC;

# 4. If missing, re-run specific loader
python scripts/run_loader.py quality_metrics BAR

# 5. Verify data now loads
SELECT COUNT(*) FROM quality_metrics WHERE ticker = 'BAR';
```

**Acceptance**: All 6 stocks have ≥90% completeness AND quality score not suppressed

---

### Step 5: Verify Institutional Holdings Data (1.5 hours)
**Priority**: HIGH  
**Impact**: 2,000 missing metric instances

```bash
# 1. Check if table exists and has data
SELECT COUNT(*) FROM institutional_holdings_13f;

# 2. Check schema
DESCRIBE institutional_holdings_13f;
# Should have: ticker, date, top_10_institutions_pct, institutional_holders_count

# 3. Check if data is recent
SELECT MAX(date) FROM institutional_holdings_13f;

# 4. Test query used in API
SELECT ticker, top_10_institutions_pct, institutional_holders_count 
FROM institutional_holdings_13f 
WHERE ticker = 'AAPL' 
ORDER BY date DESC 
LIMIT 1;

# 5. If no data, check loader status
SELECT * FROM loader_execution_log 
WHERE loader_name = 'institutional_holdings_13f'
ORDER BY started_at DESC LIMIT 5;

# 6. If failed, troubleshoot:
python scripts/run_loader.py institutional_holdings_13f --verbose
```

**Acceptance**: Table has data, queries work, at least 500 stocks have current data

---

### Step 6: Run Comprehensive Diagnostics (30 min)
**Priority**: CRITICAL  
**Final verification before launch**

```bash
# After all fixes, run final diagnostics
python scripts/comprehensive_diagnostics.py --focus database,locks,loaders,consistency,config

# Expected output:
# ✓ Database pool health: OK
# ✓ Lock status: 0 stale locks
# ✓ Loader performance: All recent runs successful
# ✓ Data consistency: No mismatches
# ✓ Configuration: All values correct
# ✓ Recent errors: None in last 24h
```

**Acceptance**: All checks pass, 0 HIGH severity issues

---

## NEXT WEEK (8-10 hours)

These are important but can be deferred if needed for launch.

### Step 7: Create Stale Lock Cleanup Script (1 hour)
**File**: scripts/cleanup_stale_locks.py
**Priority**: HIGH  
**Impact**: Prevents stale locks from blocking loaders

```bash
# Create cleanup_stale_locks.py with:
# - Detect locks older than 2 hours
# - Verify process is dead (check PID)
# - Dry-run mode for safe preview
# - Alert on cleanup

# Test it:
python scripts/cleanup_stale_locks.py --dry-run
# Should show any stale locks found (should be 0)

# Make it a scheduled daily task:
# 0 */6 * * * python scripts/cleanup_stale_locks.py
```

**Acceptance**: Script runs, handles edge cases, ready for scheduling

---

### Step 8: Setup Production Monitoring Script (2 hours)
**File**: scripts/setup_production_monitoring.py
**Priority**: HIGH  
**Impact**: Automated daily health checks

```bash
# Create setup_production_monitoring.py with checks for:
# - Position quantities (detect negatives, fractional shares)
# - Stale lock accumulation
# - Data freshness (prices, signals)
# - Portfolio reconciliation
# - Error logs

# Test it:
python scripts/setup_production_monitoring.py --component positions
python scripts/setup_production_monitoring.py --component freshness
python scripts/setup_production_monitoring.py --component reconciliation

# Schedule for daily runs:
# 0 6 * * * python scripts/setup_production_monitoring.py --alert

# Should produce:
# ✓ Position summary (all quantities valid)
# ✓ Freshness summary (all data <24h old)
# ✓ Lock summary (no stale locks)
# ✓ Reconciliation summary (portfolio balanced)
```

**Acceptance**: Script runs daily, detects issues, alerts configured

---

### Step 9: Create Position Quantity Bug Fix Script (2 hours)
**File**: scripts/fix_position_quantities.py
**Priority**: HIGH  
**Impact**: Emergency correction if quantity mismatches occur

```bash
# Create fix_position_quantities.py with:
# - Detect negative quantities
# - Detect fractional shares (stock split bugs)
# - Review trade history for diagnosis
# - Dry-run and --fix modes

# Test it:
python scripts/fix_position_quantities.py --dry-run
# Should show 0 issues (if system is healthy)

# If issues found:
python scripts/fix_position_quantities.py --fix
# Should log all corrections with reason

# Make available for on-call use
```

**Acceptance**: Script handles edge cases, tested with dry-run

---

### Step 10: Create Stale Lock Detection Alerts (2 hours)
**Priority**: HIGH  
**Impact**: Proactive detection of blocking locks

```bash
# Integrate into daily monitoring:
# - Query loader_locks table every hour
# - Alert if any lock >2 hours old
# - Include owner, resource, start time
# - Auto-cleanup option

# Add to monitoring script:
python scripts/setup_production_monitoring.py --component locks
```

**Acceptance**: Alerts configured and tested

---

### Step 11: Database Schema Mapping (1.5 hours)
**Priority**: MEDIUM  
**Impact**: Ensures all scripts work with actual schema

```bash
# Review actual database schema
python -c "
from utils.db.models import *
# Document all table names and key fields
"

# Map against script assumptions:
# - loader_locks table (or equivalent)
# - positions table
# - price_daily table
# - portfolio_metrics table
# - buy_sell_daily table
# - trade_log table

# Update all scripts to use correct table names
```

**Acceptance**: All scripts tested against actual schema

---

## OPTIONAL (If time permits)

### Additional Improvements
1. **Dashboard Enhancement** (1-2 hours)
   - Add "Data Last Updated" timestamp to all panels
   - Show "SEC data unavailable" explanation on hover
   - Add refresh timestamp to health panel

2. **Monitoring Integration** (2-3 hours)
   - Send daily summary email
   - Create Slack/Teams alerts
   - Dashboard of key metrics

3. **Documentation** (2-3 hours)
   - Create production runbook
   - Document common issues and fixes
   - Create escalation procedures

---

## Success Criteria - Must Complete THIS WEEK

- ✓ System diagnostics script created and runs with 0 HIGH issues
- ✓ Loader scheduler verified operational  
- ✓ Alert channels tested and working
- ✓ High-completeness stocks audited and verified
- ✓ Institutional holdings data verified
- ✓ All stress tests still passing
- ✓ execution_mode = 'paper' confirmed

---

## Launch Checklist (Before Aug 1)

- [ ] All THIS WEEK tasks completed
- [ ] Comprehensive diagnostics runs clean
- [ ] 3/3 stress tests passed
- [ ] execution_mode = 'paper'
- [ ] All alert channels tested
- [ ] Stale locks cleared
- [ ] Database backup taken
- [ ] Monitoring scripts deployed
- [ ] On-call runbook ready

---

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Loader scheduler fails | Daily manual verification until proven reliable |
| Alert channels down | Check every 2 hours during first week |
| Stale locks accumulate | Daily cleanup script, alerts on age >2h |
| Data goes stale | Monitoring script alerts <24h freshness threshold |
| Position quantity bugs | Monitoring script detects daily, fix script available |

---

**Created**: 2026-07-31  
**Status**: ACTIVE - Ready for implementation  
**Estimated Completion**: 2026-08-01 (7 hours THIS WEEK)  
**Additional Work**: 8-10 hours NEXT WEEK for monitoring setup

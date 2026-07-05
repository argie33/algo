# Monday Morning Pre-Market Validation Checklist (2026-07-07)

**Status: READY FOR 9:30 AM MARKET OPEN**

This checklist verifies that all critical infrastructure, data, and trading systems are operational before market hours. Run **between 8:00-9:15 AM ET** on trading days.

---

## 🔴 CRITICAL BLOCKERS (Must Pass Before Trading)

### 1. Database Connectivity
```bash
python -c "
from utils.db.connection import get_db_connection
try:
    conn = get_db_connection(timeout=10)
    conn.close()
    print('✓ Database connected')
except Exception as e:
    print(f'✗ Database error: {e}')
    exit(1)
"
```
**Expected:** ✓ Database connected  
**If failed:** Contact AWS admin to verify RDS/RDS Proxy status

### 2. Critical Data Freshness (< 24h old)
**Expected:** market_exposure_daily and signal_quality_scores available  
**If failed:** Run: `python scripts/fix_data_pipeline.py --sector-ranking --market-exposure`

### 3. Alpaca Broker Connection (Paper Trading)
**Expected:** ✓ Alpaca connected  
**If failed:** Verify ALPACA_API_KEY and ALPACA_SECRET_KEY in AWS Secrets Manager

### 4. Orchestrator Lambda Function
**Expected:** ✓ Orchestrator Lambda responding  
**If failed:** Check `/aws/lambda/algo-orchestrator` CloudWatch logs

### 5. API Lambda Function
**Expected:** ✓ API Lambda responding  
**If failed:** Check `/aws/lambda/algo-api-dev` CloudWatch logs

---

## 🟡 PRE-MARKET WARNINGS (Non-Blocking but Important)

### 6. Dashboard Data Freshness
Run: `python -m dashboard.diagnose_dashboard --verbose`  
**Expected:** Max 1-2 error endpoints, critical data < 1 minute old

### 7. Position Reconciliation
**Expected:** Alpaca positions ≈ Algo trades open count (within 1-2)  
**If warning:** Manual orchestrator test trigger in AWS Lambda console

### 8. Circuit Breaker Status
**Expected:** ✓ Circuit breaker: OK (all clear)  
**If warning:** Review `steering/OPERATIONS.md` → Circuit Breaker Monitoring section

---

## 📋 MANUAL PRE-MARKET STEPS (9:00-9:15 AM)

1. **Verify Paper Trading Mode**
   - Should show: `alpaca_paper_trading = true` in terraform/terraform.tfvars

2. **Check EventBridge Rules are Enabled**
   - `aws events list-rules --region us-east-1 --name-prefix algo-orchestrator`
   - Should show: ENABLED for all orchestrator rules

3. **Verify Last Orchestrator Run**
   - Check CloudWatch logs for recent success message (within 10 min if market open)

---

## 🟢 GO/NO-GO DECISION (9:15 AM)

- **All CRITICAL blockers pass → GO** — Market open ready
- **1+ CRITICAL blocker fails → NO-GO** — Debug & fix before 9:30 AM
- **All PRE-MARKET warnings pass → Trading smooth**
- **1+ PRE-MARKET warning fails → Monitor closely, be ready to halt**

---

## 🆘 EMERGENCY PROCEDURES

**If orchestrator hung at 9:20 AM:**
1. Kill hung ECS tasks: `aws ecs list-tasks --cluster algo-cluster --desired-status RUNNING`
2. Manually trigger orchestrator Lambda Test button in AWS console

**If Alpaca connection fails:**
1. Verify keys: `aws secretsmanager get-secret-value --secret-id alpaca-keys`

**If database is down:**
1. Check RDS: `aws rds describe-db-instances`
2. Check RDS Proxy status

---

**Checklist created:** 2026-07-04 (Friday evening recovery)  
**Last validated:** N/A (run before each trading day)  
**Reference:** steering/GOVERNANCE.md, steering/OPERATIONS.md

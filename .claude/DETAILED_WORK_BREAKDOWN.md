# Complete Work Breakdown - Executable Tasks

**Last Updated:** 2026-05-17 09:55 UTC  
**Data Loaders Status:** 🔄 Running (10+/23 tiers, ~30-45 min remaining)

---

## 🟢 CAN DO NOW (While Data Loaders Run) - ~2-3 Hours

### Category 1: TERRAFORM VALIDATION & DEPLOYMENT PREP
**Time:** 15-20 min | **Why now:** Doesn't depend on data

- [ ] **Terraform Format & Syntax**
  ```bash
  cd terraform && terraform fmt -recursive .
  terraform validate
  ```
  - [ ] No formatting errors
  - [ ] Schema validation passes
  - [ ] All modules found

- [ ] **Terraform Variables Check**
  - [ ] All required variables defined in terraform.tfvars
  - [ ] DB password variables set correctly
  - [ ] Alpaca credentials accessible via Secrets Manager references
  - [ ] Region correct (us-east-1)

- [ ] **Review GitHub Actions Workflow**
  - [ ] `.github/workflows/deploy-all-infrastructure.yml` exists
  - [ ] Terraform commands correct (plan → apply)
  - [ ] Secrets properly referenced (not hardcoded)

---

### Category 2: LAMBDA CODE VALIDATION
**Time:** 15-20 min | **Why now:** Can test locally

- [ ] **Lambda Syntax Check**
  ```bash
  python3 -m py_compile lambda/api/lambda_function.py
  python3 -m py_compile lambda/algo_orchestrator/lambda_function.py
  ```
  - [ ] All compile without errors
  - [ ] No import errors
  - [ ] Handler functions exist

- [ ] **Lambda Response Format**
  - [ ] All success responses have: statusCode, headers, body
  - [ ] All error responses consistent
  - [ ] JSON is properly formatted
  - [ ] No raw exceptions in responses

- [ ] **Lambda Requirements Check**
  ```bash
  cat lambda/api/requirements.txt | sort
  ```
  - [ ] All dependencies listed
  - [ ] Versions pinned or flexible
  - [ ] No duplicates
  - [ ] psycopg2, boto3 present

---

### Category 3: EXCEPTION HANDLING PATTERNS
**Time:** 15-20 min | **Why now:** Can review code

- [ ] **5-Level Exception Pattern**
  - [ ] All 70 API methods have:
    1. UndefinedTable → 503
    2. UndefinedColumn → 503  
    3. OperationalError → 503
    4. DatabaseError → 500
    5. Exception → 500

- [ ] **Error Response Format**
  - [ ] All use consistent JSON structure
  - [ ] No raw exception text leaked
  - [ ] Status codes match HTTP standards
  - [ ] Operation names logged

---

### Category 4: IMPORT CONSISTENCY
**Time:** 10-15 min | **Why now:** Can scan code

- [ ] **Entry Point sys.path Check**
  ```bash
  grep "sys.path.insert" algo/algo_orchestrator.py
  grep "sys.path.insert" loaders/*.py | wc -l
  ```
  - [ ] Present in all loaders
  - [ ] Present in orchestrator
  - [ ] Pattern consistent

- [ ] **load_env() Calls**
  ```bash
  grep "load_env()" algo/algo_orchestrator.py utils/init_database.py
  ```
  - [ ] Called after import in main modules
  - [ ] Before accessing environment variables

---

### Category 5: DATABASE SCHEMA REVIEW
**Time:** 10-15 min | **Why now:** Can review schema code

- [ ] **init_database.py Review**
  - [ ] Is AUTHORITATIVE source
  - [ ] All 127 tables defined
  - [ ] CREATE IF NOT EXISTS (idempotent)
  - [ ] Primary/foreign keys correct

- [ ] **Loader Tier Dependency Map**
  - [ ] Tier 0 (symbols): Independentant
  - [ ] Tier 1 (prices): Depends on symbols
  - [ ] Tier 2-4 (indicators): Depend on prices
  - [ ] No circular dependencies

---

### Category 6: API DOCUMENTATION
**Time:** 15-20 min | **Why now:** Can document without data

- [ ] **Create Endpoint Reference**
  ```
  GET /api/algo/status - Current algo state
  GET /api/signals/stocks - BUY/SELL signals
  GET /api/prices/{symbol} - Price history
  GET /api/portfolio/positions - Open positions
  GET /api/performance/pnl - P&L calculations
  ```

- [ ] **Error Code Documentation**
  - [ ] 503 = Transient (data loading, connection issues)
  - [ ] 500 = Permanent (code bugs)
  - [ ] Document when each appears

---

### Category 7: SECURITY AUDIT
**Time:** 15-20 min | **Why now:** Can review code

- [ ] **No Hardcoded Credentials**
  ```bash
  grep -r "password\|secret\|token" --include="*.py" | grep "= ['\"]"
  ```
  - [ ] Should find ZERO results
  - [ ] All from env vars or Secrets Manager

- [ ] **Credential Rotation Plan**
  - [ ] DB password: 30-day cycle (next: 2026-06-17)
  - [ ] API keys: 90-day cycle (next: 2026-08-17)
  - [ ] AWS keys: 30-day cycle (next: ~2026-06-10)

- [ ] **GitHub Secrets Verification**
  - [ ] All 26+ secrets present
  - [ ] .env.local in .gitignore
  - [ ] No credentials in git history

---

### Category 8: MONITORING PLANNING
**Time:** 15-20 min | **Why now:** Can plan without deployment

- [ ] **CloudWatch Alarms (Plan Only)**
  - [ ] Lambda error rate > 1%
  - [ ] Lambda duration > 30s
  - [ ] RDS CPU > 80%
  - [ ] Data freshness > 24h

- [ ] **Custom Metrics Plan**
  - [ ] Data freshness per symbol
  - [ ] Loader execution duration
  - [ ] API response times
  - [ ] Error rate by type

- [ ] **Dashboard Layout**
  - [ ] System health metrics
  - [ ] Data freshness status
  - [ ] Business metrics (signals, trades)

---

### Category 9: ORCHESTRATOR TESTING
**Time:** 10-15 min | **Why now:** Can test with --dry-run

- [ ] **Run Dry-Run Multiple Times**
  ```bash
  python3 algo/algo_orchestrator.py --dry-run
  python3 algo/algo_orchestrator.py --dry-run
  python3 algo/algo_orchestrator.py --dry-run
  ```
  - [ ] All 3 runs produce identical results
  - [ ] No state mutations
  - [ ] Logs are consistent

- [ ] **Phase Isolation Check**
  - [ ] Each phase can run independently
  - [ ] Phase 1 (data freshness) works
  - [ ] Phase 2 (circuit breakers) works
  - [ ] Phases 3-7 work with empty portfolio

---

### Category 10: ALPACA INTEGRATION
**Time:** 10-15 min | **Why now:** Can review code

- [ ] **Credentials Check**
  - [ ] APCA_API_KEY_ID set
  - [ ] APCA_API_SECRET_KEY set
  - [ ] Base URL = paper-api.alpaca.markets
  - [ ] Paper trading enabled

- [ ] **Code Review**
  ```bash
  grep -r "alpaca\|REST(" --include="*.py" algo/ | head -10
  ```
  - [ ] Error handling present
  - [ ] Timeouts configured
  - [ ] Retry logic present
  - [ ] No infinite waits

---

### Category 11: TEST SCRIPT CREATION
**Time:** 20-30 min | **Why now:** Can write code

**Create:** test_api_local.py
```python
#!/usr/bin/env python3
import requests
endpoints = [
  '/api/algo/status',
  '/api/signals/stocks',
  '/api/prices/AAPL',
  '/api/portfolio/positions',
  '/api/performance/pnl'
]
for ep in endpoints:
  r = requests.get(f'http://localhost:5000{ep}')
  assert r.status_code == 200, f"{ep} returned {r.status_code}"
  print(f"✓ {ep}")
```

**Create:** test_database_health.py
```python
#!/usr/bin/env python3
import psycopg2
conn = psycopg2.connect(...)
queries = {
  'stock_symbols': 'SELECT COUNT(*) FROM stock_symbols',
  'price_daily': 'SELECT COUNT(*) FROM price_daily',
  'price_nulls': 'SELECT COUNT(*) FROM price_daily WHERE open IS NULL'
}
for name, query in queries.items():
  cur = conn.cursor()
  cur.execute(query)
  result = cur.fetchone()[0]
  print(f"{name}: {result}")
```

---

### Category 12: DOCUMENTATION
**Time:** 20-30 min | **Why now:** Can write

**Create:**
- [ ] QUICK_START.md (how to run locally)
- [ ] TROUBLESHOOTING.md (common issues + fixes)
- [ ] DEPLOYMENT_CHECKLIST.md (pre/during/post deploy)
- [ ] OPERATIONAL_RUNBOOK.md (daily/weekly/monthly tasks)
- [ ] API_DOCUMENTATION.md (all endpoints + errors)

---

## 🟡 AFTER DATA LOADS COMPLETE (~2.5 hours)

**Must Wait For:** Fresh data in database

- [ ] Test API endpoints (need data)
- [ ] Validate record counts
- [ ] Run data quality checks
- [ ] Check data freshness

---

## 🔴 AFTER AWS DEPLOYMENT

**Must Wait For:** Lambda deployed to AWS

- [ ] Test Lambda endpoints
- [ ] Verify cold-start performance
- [ ] Check CloudWatch logs
- [ ] Monitor orchestrator execution

---

## ⏱️ TOTAL TIME BREAKDOWN

| Phase | Time | Parallel? |
|-------|------|-----------|
| Terraform validation | 15 min | YES |
| Lambda validation | 15 min | YES |
| API docs + test scripts | 35 min | YES |
| Audits + review | 40 min | YES |
| **CAN DO NOW (parallel)** | **2-3 hours** | ✅ YES |
| Wait for data loads | 30-45 min | (automatic) |
| API testing with data | 20 min | ⏸️ |
| AWS deployment | 20 min | ⏸️ |
| Post-deploy testing | 30 min | ⏸️ |
| **TOTAL** | **3.5-4 hours** | - |

---

## 🎯 RECOMMENDED EXECUTION

**RIGHT NOW (Parallel to data loaders):**
1. Run: Terraform format & validate
2. Create: Test scripts
3. Create: API documentation
4. Review: Exception handlers
5. Check: Security (no hardcoded creds)
6. Run: Orchestrator --dry-run tests
7. Create: Runbooks & documentation

**RESULT:** By the time data loads finish, everything else is ready for deployment.

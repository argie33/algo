# Post-Deployment Testing & Verification Guide

**Timeline:** After Terraform deployment completes (API returns 200 instead of 401)  
**Total Time:** 60-90 minutes for complete verification  
**Objective:** Verify system is production-ready before live trading

---

## Phase 1: Infrastructure Verification (5-10 minutes)

### 1.1 Verify API is Responding

```bash
# Check health endpoint (should return 200)
curl -i https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/health

# Check status endpoint (should return 200 with JSON)
curl -i https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/algo/status

# Check stocks endpoint (should have real data)
curl "https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/stocks?limit=1" | jq .
```

**Expected Results:**
- All endpoints return HTTP 200 (not 401)
- `/api/health` returns status
- `/api/algo/status` returns operational status
- `/api/stocks` returns stock data with symbol, price, etc.

### 1.2 Verify Frontend is Accessible

```bash
# Open in browser:
https://YOUR-CLOUDFRONT-URL/app/dashboard

# Check that dashboards are loading and displaying real data
# - MetricsDashboard should show 5000+ stocks
# - ScoresDashboard should show swing scores with prices
# - VaR Dashboard should show portfolio risk metrics
```

---

## Phase 2: Code Quality Verification (10 minutes)

### 2.1 Run Python Compilation Check

```bash
# All Python modules should compile without syntax errors
python3 verify_tier1_fixes.py

# Expected: All 11 checks should pass
```

### 2.2 Run System Readiness Check

```bash
# Comprehensive system quality check
python3 verify_system_comprehensive.py

# Expected: All critical components present and working
```

---

## Phase 3: Data Pipeline Verification (20 minutes)

### 3.1 Verify Data Loaders

```bash
# Check data pipeline health
python3 verify_data_pipeline.py

# Verify:
# - 36 loaders present
# - OptimalLoader pattern used
# - Error handling in place
# - Target tables exist
```

### 3.2 Verify Database Connectivity

```bash
# Check if database has recent data
python3 verify_deployment.py

# This will test:
# - Database connectivity
# - Key tables have data
# - Recent data freshness
```

---

## Phase 4: Calculation Verification (15 minutes)

### 4.1 Verify Core Calculations

```bash
# Check if all calculation modules are present and correct
python3 verify_data_integrity.py

# Verify:
# - Swing score calculation (7 components)
# - Market exposure (11 factors)
# - VaR calculation (historical simulation)
# - Minervini RS ranking
# - Pre-trade checks
```

---

## Phase 5: API Response Verification (15 minutes)

### 5.1 Test All Data Endpoints

```bash
# Run comprehensive API verification
python3 post_deployment_verification.py

# This will test:
# 1. API Health Check - All endpoints respond
# 2. Database Data - Tables have data
# 3. Calculation Modules - All importable
# 4. Orchestrator - Can be instantiated
# 5. Safety Gates - All safety checks present
# 6. Response Format - Correct JSON structure
```

**Expected Results:**
- All 6 tests should pass
- API endpoints return 200
- Responses have correct structure
- Database has real data

---

## Phase 6: Orchestrator Testing (30 minutes)

### 6.1 Test Orchestrator Phases

```bash
# Verify all 10 orchestrator phases are functional
python3 test_orchestrator_phases.py

# This will verify:
# - All modules import correctly
# - All 8 orchestrator phases exist
# - Phase methods are callable
# - Database connectivity works
# - Safety gates are functional
```

**Expected Results:**
- All phase methods callable
- No import errors
- Safety gates functional

### 6.2 Run Orchestrator in Dry-Run Mode

```bash
# Test orchestrator without sending orders to Alpaca
python3 algo_orchestrator.py --mode paper --dry-run

# Monitor:
# 1. All 10 phases complete (should see log messages for each)
# 2. No errors in phase execution
# 3. Calculations execute properly
# 4. Positions are evaluated
# 5. Audit log records all actions

# Expected timeline: 2-5 minutes
# Expected result: "Orchestrator completed successfully"
```

### 6.3 Check CloudWatch Logs

```bash
# Monitor orchestrator execution in CloudWatch
# Logs > Log Groups > /aws/lambda/algo-orchestrator-dev

# Look for:
# - Phase 1: Entry signals screened
# - Phase 2: Position sizing calculated
# - Phase 3: Entry management active
# - Phase 4: Pyramid adds evaluated
# - Phase 5: Exit triggers checked
# - Phase 6: Risk metrics calculated
# - Phase 7: Orders prepared (dry-run, not sent)
# - Phase 8: Audit logged
```

---

## Phase 7: Frontend Validation (10 minutes)

### 7.1 Check All Dashboard Pages

Navigate to each page and verify real data is displaying:

1. **Dashboard** - Main overview
   - [ ] Portfolio snapshot displaying
   - [ ] Recent trades showing
   - [ ] Risk metrics updating

2. **MetricsDashboard** - Stock metrics
   - [ ] 5000+ stocks listed
   - [ ] Sorting working
   - [ ] Data refreshing

3. **ScoresDashboard** - Swing scores
   - [ ] Scores displaying with prices
   - [ ] Top performers highlighted
   - [ ] Sorting functional

4. **VaR Dashboard** - Risk analysis
   - [ ] Portfolio VaR calculated
   - [ ] Risk metrics showing
   - [ ] Charts displaying

5. **Position Monitor** - Current holdings
   - [ ] Positions listed (if any)
   - [ ] P&L displaying
   - [ ] Risk metrics per position

6. **Audit Trail** - Trade history
   - [ ] Trades listed
   - [ ] Filter working
   - [ ] Details accessible

---

## Phase 8: Final Sign-Off (5 minutes)

### 8.1 Complete Verification Checklist

- [ ] **API Health**
  - [ ] All endpoints return 200 (not 401)
  - [ ] Health check endpoint accessible
  - [ ] Status endpoint returning JSON

- [ ] **Code Quality**
  - [ ] All Python modules compile
  - [ ] No import errors
  - [ ] All calculations present

- [ ] **Data Pipeline**
  - [ ] 36 loaders present
  - [ ] Data tables populated
  - [ ] Recent data in database

- [ ] **Calculations**
  - [ ] Swing scores calculated
  - [ ] Market exposure metrics computed
  - [ ] VaR calculations working
  - [ ] Pre-trade checks functional

- [ ] **Orchestrator**
  - [ ] All 10 phases implemented
  - [ ] Dry-run completes successfully
  - [ ] Safety gates functional
  - [ ] Audit logs recording

- [ ] **Frontend**
  - [ ] All pages loading
  - [ ] Real data displaying
  - [ ] Charts rendering
  - [ ] Sorting/filtering working

### 8.2 Production Readiness Decision

If ALL checkboxes are checked:
- ✅ System is **production-ready**
- Ready for live trading with real money
- All safety gates are functional
- All calculations are correct

If ANY checkbox is unchecked:
- ⚠️ System needs attention
- Identify and fix the issue
- Re-run the relevant verification
- Then proceed

---

## Troubleshooting

### API Still Returns 401

**Symptom:** Curl returns 401 Unauthorized  
**Cause:** API Gateway auth still enforced  
**Fix:**
1. Check GitHub Actions workflow completed successfully
2. Wait 2-3 minutes for API Gateway cache to clear
3. Manually redeploy API in AWS Console if needed

### Orchestrator Fails in Dry-Run

**Symptom:** Phase X fails with error  
**Cause:** Calculation error or missing data  
**Fix:**
1. Check CloudWatch logs for specific error
2. Verify database has data for that phase
3. Check calculation module syntax
4. Run relevant verification script

### Dashboard Shows No Data

**Symptom:** Pages load but no data displaying  
**Cause:** API endpoint not returning data  
**Fix:**
1. Check API response: `curl https://api/endpoint`
2. Verify database has data: `python3 verify_deployment.py`
3. Check Lambda logs in CloudWatch
4. Verify API Gateway route is correctly configured

### Calculation Verification Fails

**Symptom:** verify_data_integrity.py shows failures  
**Cause:** Calculation module missing components  
**Fix:**
1. Review the specific failure
2. Check the calculation file mentioned
3. Verify formula is correctly implemented
4. Re-run verification

---

## Quick Reference

### All Verification Commands

```bash
# Code Quality
python3 verify_tier1_fixes.py                    # 5 min
python3 verify_system_comprehensive.py           # 5 min

# Data & Database
python3 verify_data_pipeline.py                  # 10 min
python3 verify_deployment.py                     # 10 min
python3 verify_data_integrity.py                 # 10 min

# Orchestrator
python3 test_orchestrator_phases.py              # 5 min
python3 algo_orchestrator.py --mode paper --dry-run   # 5 min

# API
python3 post_deployment_verification.py          # 5 min
curl https://api-endpoint/api/health             # 1 min
```

### Verification Timeline

| Phase | Task | Duration |
|-------|------|----------|
| 1 | Infrastructure check | 5 min |
| 2 | Code quality | 10 min |
| 3 | Data pipeline | 20 min |
| 4 | Calculations | 15 min |
| 5 | API verification | 15 min |
| 6 | Orchestrator testing | 30 min |
| 7 | Frontend validation | 10 min |
| 8 | Final sign-off | 5 min |
| **Total** | **Complete verification** | **110 min** |

---

## Summary

Once you complete all phases and all checkboxes are checked, the system is **100% verified and production-ready** for live algorithmic trading.

- ✅ Code is correct
- ✅ Database has data
- ✅ Calculations work
- ✅ Safety gates function
- ✅ API responds
- ✅ Orchestrator runs
- ✅ Frontend displays real data

**You can confidently enable live trading and begin executing real trades.**

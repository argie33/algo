# ACTION PLAN: From "Almost Working" to "Production Ready"

Created: 2026-05-17  
Goal: Complete all verification and fixes needed before live trading  
Total Time: ~6 hours of focused work (in phases)  
Status: Ready to execute

---

## QUICK REFERENCE: WHAT TO DO RIGHT NOW

1. **Next 15 minutes:** Check if Terraform deployment completed
2. **Next 1 hour:** Verify API is responding (401 blocker fixed)
3. **Next 30 minutes:** Verify loaders executed (data in database)
4. **Next 2 hours:** Spot-check calculations + test API endpoints
5. **Next 2 hours:** Test all frontend pages
6. **This week:** Fix security + performance issues

---

## PHASE 1: UNBLOCK API (15 MINUTES)

**Step 1: Check if Terraform deployment completed**
Go to: https://github.com/argie33/algo/actions
Look for "Deploy All Infrastructure" workflow
- If Success (🟢): Continue to Step 2
- If Running (🟠): Wait 10-15 minutes
- If Failed (🔴): Read error logs

**Step 2: Verify API endpoint**
```bash
curl -i https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/algo/status

# Expected: HTTP/1.1 200 OK
# NOT 401 Unauthorized
```

---

## PHASE 2: VERIFY DATA LOADING (30 MINUTES)

**Step 1: Run loader validation**
```bash
python3 tests/integration/test_loader_validation.py

# Check:
# - loader_execution_history shows today's date
# - price_daily has 5000+ stocks
# - stock_scores has today's data
```

---

## PHASE 3: SPOT-CHECK CALCULATIONS (45 MINUTES)

**Test these 5 stocks:**
MSFT, AAPL, NVDA, XLK, TSLA

**Verify:**
1. Minervini scores (0-100, MSFT/AAPL high, XLK lower)
2. Swing scores (components add up correctly)
3. Market exposure (reasonable values)
4. VaR (95% confidence, CVaR >= VaR)

---

## PHASE 4: TEST API ENDPOINTS (1 HOUR)

```bash
# Test key endpoints
curl https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/algo/status
curl 'https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/stocks?limit=5'
curl 'https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/scores/stockscores?limit=5'

# Expected: All return HTTP 200, valid JSON
```

---

## PHASE 5: TEST FRONTEND PAGES (1-2 HOURS)

**Critical pages to test:**
- MetricsDashboard
- ScoresDashboard
- PortfolioHealth
- VaRDashboard
- SignalsFeed

**Check for each:**
- [ ] Page loads
- [ ] Data displays
- [ ] Charts render
- [ ] No console errors (F12)

---

## PHASE 6: FULL ORCHESTRATOR TEST (30 MINUTES)

```bash
# Test execution without trading
python3 algo_orchestrator.py --mode paper --dry-run

# Expected: All 7 phases complete
```

---

## PHASE 7: SECURITY & PERFORMANCE (THIS WEEK)

```bash
# Fix npm vulnerabilities
npm audit fix

# Verify performance
# Dashboard should load < 2 seconds
```

---

## FINAL SIGN-OFF CHECKLIST

Before live trading:
- [ ] Phase 1: API returns 200 (not 401)
- [ ] Phase 2: Data loaded today
- [ ] Phase 3: Calculations verified
- [ ] Phase 4: API endpoints working
- [ ] Phase 5: Frontend pages working
- [ ] Phase 6: Orchestrator runs
- [ ] Phase 7: Security issues fixed

If all checked: **YOU'RE READY FOR LIVE TRADING** 🎉

---

For detailed step-by-step instructions with troubleshooting, see:
- AUDIT_SUMMARY.md (overview)
- COMPREHENSIVE_AUDIT_FINDINGS.md (detailed)

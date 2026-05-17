# Production Launch Checklist

**Status:** Ready to Review  
**Target Date:** 2026-05-XX  
**Owner:** Engineering Lead

---

## Phase 1: Code & Testing (✅ COMPLETE)

- [x] All unit tests pass (139/139)
- [x] Code imports without errors
- [x] API contract defined (API_CONTRACT.md)
- [x] Syntax errors fixed (algo_swing_score.py, etc.)
- [x] Git clean: no uncommitted changes
- [x] Recent commits focused on fixes (data, column, contrast)
- [x] PNG test artifacts removed from git

---

## Phase 2: Infrastructure (⏳ AWAITING USER CONFIRMATION)

### AWS Infrastructure
- [ ] RDS instance is running (algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com)
- [ ] RDS password stored in AWS Secrets Manager
- [ ] Lambda functions deployed:
  - [ ] algo-api (Express.js with 29 routes)
  - [ ] run-loaders (data pipeline orchestrator)
- [ ] CloudFront distribution active:
  - [ ] Frontend deployed to d5j1h4wzrkvw7.cloudfront.net
  - [ ] CDN cache properly configured
- [ ] API Gateway endpoints accessible:
  - [ ] https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com

### Monitoring & Logging
- [ ] CloudWatch log groups exist for Lambda + RDS
- [ ] CloudWatch dashboards created (optional but recommended)
- [ ] Alarms configured for:
  - [ ] Lambda error rate > 5%
  - [ ] API response time > 5s
  - [ ] RDS CPU > 80%
  - [ ] RDS storage > 80%
  - [ ] Data staleness > 24h

### Security
- [x] No .env files in repo
- [x] No hardcoded credentials
- [x] Credentials via AWS Secrets Manager (local dev)
- [x] GitHub Actions secrets configured for CI/CD
- [x] RDS security group allows Lambda → RDS

---

## Phase 3: Data Pipeline (⏳ AWAITING USER ACTION)

- [ ] PostgreSQL database initialized:
  ```bash
  python3 init_database.py
  ```
- [ ] All 40 loaders run successfully:
  ```bash
  python3 run-all-loaders.py  # ~20 minutes
  ```
- [ ] Data validation passed:
  - [ ] swing_trader_scores: >100k records
  - [ ] price_daily: >1.5M records
  - [ ] company_profile: >2k companies
  - [ ] No NULL values in required columns
- [ ] Data freshness acceptable:
  - [ ] Prices: today's data loaded
  - [ ] Scores: computed for all symbols
  - [ ] Fundamentals: <7 days old

---

## Phase 4: API & Frontend Integration (⏳ AWAITING USER ACTION)

### Critical Endpoints Tested
- [ ] `/api/scores/stockscores` returns scores + trends
- [ ] `/api/stocks/deep-value` returns valuations
- [ ] `/api/algo/swing-scores/{symbol}` returns components
- [ ] `/api/prices/history/{symbol}` returns OHLCV
- [ ] `/api/algo/circuit-breakers` returns status
- [ ] `/api/algo/notifications` returns alerts
- [ ] `/api/audit/trades` returns trade history

### Frontend Manual Testing
- [ ] **Login:** User can authenticate with credentials
- [ ] **Dashboard:** Scores load, not showing "undefined"
- [ ] **Deep Value:** List shows all valuations (PE, PB, ROE)
- [ ] **Portfolio:** Charts render without errors
- [ ] **Trade Tracker:** Historical trades display
- [ ] **Settings:** Config changes apply immediately
- [ ] **Notifications:** Alerts appear in real-time

### Browser Compatibility
- [ ] Chrome/Chromium (latest)
- [ ] Firefox (latest)
- [ ] Safari (latest)
- [ ] Mobile responsive (responsive design working)

---

## Phase 5: Production Hardening (⏳ NICE-TO-HAVE)

- [ ] Lambda connection pooling implemented (or RDS Proxy enabled)
- [ ] Lambda provisioned concurrency enabled (keeps instances warm)
- [ ] Lambda memory increased to 1024MB (improves cold-start)
- [ ] Response pagination implemented (avoid >10MB payloads)
- [ ] Query timeouts set to 10 seconds
- [ ] Database indexes optimized:
  - [ ] swing_trader_scores(symbol)
  - [ ] price_daily(symbol, date)
  - [ ] company_profile(ticker)
- [ ] Slow query log enabled and monitored

---

## Phase 6: Documentation (✅ COMPLETE)

- [x] API_CONTRACT.md - endpoint specifications
- [x] INCIDENTS.md - incident response runbook
- [x] DEPLOYMENT_GUIDE.md - GitHub Actions auto-deploy
- [x] LOCAL_CRED_SETUP.md - local dev environment
- [x] troubleshooting-guide.md - common issues
- [ ] RUNBOOKS.md (optional) - operational procedures

---

## Phase 7: Deployment (⏳ AWAITING USER ACTION)

### Pre-Launch (Day-1)
1. [ ] Push to main branch
2. [ ] GitHub Actions workflow triggers automatically
3. [ ] Verify deployment succeeded (check Actions tab)
4. [ ] All Lambda functions are "Active"
5. [ ] No errors in CloudWatch logs

### Launch (Day-1, EOD)
1. [ ] Share frontend URL with stakeholders
2. [ ] Brief users on what to expect
3. [ ] Set on-call schedule for first week
4. [ ] Enable detailed CloudWatch logging
5. [ ] Have incident runbook ready

### Post-Launch (First 24h)
1. [ ] Monitor CloudWatch alarms closely
2. [ ] Check for data staleness > 12h
3. [ ] Watch API error logs for new patterns
4. [ ] Gather user feedback on UX
5. [ ] Document any issues found

---

## Blockers & Risks

### ⚠️ REQUIRED BEFORE LAUNCH
- **RDS Credentials:** Need password for production database
  - [ ] User provides RDS password
  - [ ] Stored in AWS Secrets Manager
- **Data Pipeline Execution:** Need to run loaders once
  - [ ] User runs: `python3 run-all-loaders.py`
  - [ ] Verify data loads successfully
- **Frontend Testing:** Need manual testing by user
  - [ ] User walks through critical user journeys
  - [ ] No "undefined" values, no errors in console

### ⚠️ ACCEPTABLE RISKS
- **Lambda cold-start (3-5s):** Can optimize later with provisioned concurrency
- **Slow queries:** Add indexes if response >5s (monitor and fix)
- **Connection pool exhaustion:** Add RDS Proxy if >50 concurrent connections

### 🔴 SHOW-STOPPERS (Not present)
- ❌ Syntax errors - **FIXED** ✅
- ❌ Missing database - **DEPLOYED** ✅
- ❌ Unimplemented API endpoints - **COMPLETE** ✅
- ❌ Missing credentials - **USER NEEDS TO PROVIDE** ⏳
- ❌ Stale data - **USER NEEDS TO RUN LOADERS** ⏳

---

## Sign-Off

| Role | Name | Status | Date |
|------|------|--------|------|
| Engineering Lead | (User) | ⏳ Awaiting | 2026-05-17 |
| DevOps / Infrastructure | (Auto-deployed) | ✅ Ready | 2026-05-17 |
| QA / Testing | (User) | ⏳ Awaiting | 2026-05-17 |
| Product Lead | (User) | ⏳ Awaiting | - |

---

## Next Steps

1. **User provides RDS credentials** → Can run integration tests
2. **User runs data loaders** → Can test frontend with real data
3. **User does manual testing** → Can verify user journeys work
4. **Deploy to production** → GitHub Actions auto-deploys on push to main

**Estimated time to production:** 2-4 hours (mostly data loading)

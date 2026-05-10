# 📋 WORK QUEUE - Prioritized Tasks

**Current Status**: Frontend fully working ✅ | Backend healthy ✅ | Ready for feature completion

---

## 🔴 TIER 1: BLOCKING ISSUES (Need to fix TODAY)

### P1.1: Authentication Not Wired Up
- **Problem**: Using mock auth, real Cognito not configured
- **Why It Matters**: Can't verify user identity for real trading
- **Effort**: 2-3 hours
- **Steps**:
  1. Create AWS Cognito user pool
  2. Add credentials to `.env.local`
  3. Test login flow works
  4. Verify auth context detects real users
- **File**: `webapp/frontend/src/contexts/AuthContext.jsx`
- **Status**: ⏳ Not started

### P1.2: Alpaca Trading Credentials Missing
- **Problem**: `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` not in `.env.local`
- **Why It Matters**: Algo can't execute trades without credentials
- **Effort**: 15 minutes
- **Steps**:
  1. Get Alpaca paper trading keys from dashboard
  2. Add to `.env.local`:
     ```
     ALPACA_API_KEY=xxxxx
     ALPACA_SECRET_KEY=xxxxx
     ALPACA_BASE_URL=https://paper-trading.alpaca.markets
     ```
  3. Restart backend
  4. Verify in logs: "Alpaca scheduler initialized"
- **Status**: ⏳ Not started

### P1.3: EventBridge Data Loading Not Running
- **Problem**: Scheduled data loaders configured but not triggering
- **Current**: Must manually run `python3 loadpricedaily.py`
- **Why It Matters**: Market data becomes stale, traders miss new prices
- **Effort**: 30 minutes
- **Steps**:
  1. Check EventBridge scheduler status:
     ```bash
     aws scheduler list-schedules --region us-east-1 --query 'Schedules[?contains(Name, `algo`)]'
     ```
  2. Verify Lambda IAM role has permissions for: `scheduler:*`, `lambda:InvokeFunction`
  3. Test trigger manually:
     ```bash
     aws scheduler get-schedule --name algo-scheduled-run --region us-east-1
     ```
  4. If broken, update Terraform and redeploy
- **File**: `terraform/modules/scheduler/main.tf`
- **Status**: ⏳ Not started

### P1.4: Verify Database Schema Integrity
- **Problem**: Some columns missing that queries expect
- **Current Errors**:
  - `column "index_value" does not exist` (fear_greed_index)
  - `function to_timestamp(date, unknown) does not exist`
- **Why It Matters**: APIs fail with cryptic errors
- **Effort**: 1 hour
- **Steps**:
  1. Run schema validation:
     ```sql
     SELECT table_name, column_name FROM information_schema.columns 
     WHERE table_name IN ('fear_greed_index', 'aaii_sentiment', 'distribution_days')
     ORDER BY table_name;
     ```
  2. Compare with routes that query these tables
  3. Run missing migrations if needed
  4. Test endpoints that use these tables
- **Status**: ⏳ Not started

---

## 🟠 TIER 2: HIGH IMPACT (Fix THIS WEEK)

### P2.1: Manual Trade Entry Integration
- **Problem**: Trade Tracker shows UI but can't actually submit trades
- **Why It Matters**: Users can only view algo trades, can't trade manually
- **Effort**: 2-3 hours
- **Status**: Code has TODO comment
- **Files**:
  - `webapp/frontend/src/pages/TradeTracker.jsx`
  - Backend: `/api/trades` POST handler
- **Steps**:
  1. Add form submission handler
  2. Wire to POST `/api/trades` endpoint
  3. Add success/error handling
  4. Test with browser dev tools

### P2.2: API Error Response Standardization
- **Problem**: Some endpoints return inconsistent error formats
- **Why It Matters**: Frontend error handling can miss failures
- **Effort**: 1-2 hours
- **Audit**: `webapp/lambda/routes/*.js` for error responses
- **Steps**:
  1. Audit all 25+ endpoints
  2. Ensure consistent `{success: false, error: "..."}` format
  3. Use correct HTTP status codes (400/404/500 as appropriate)
  4. Test error cases

### P2.3: Database Performance Optimization
- **Problem**: Some queries slower than ideal (782ms observed on technicals query)
- **Why It Matters**: Pages load slower than they could
- **Effort**: 2-4 hours
- **Options**:
  - Option A: Enable TimescaleDB on RDS (10-100x speedup for time-series)
  - Option B: Add Redis caching layer
  - Option C: Optimize queries with better indexes
- **Recommendation**: Try Option C first (fast), then Option A

### P2.4: CORS Error Investigation
- **Problem**: Intermittent "Not allowed by CORS" errors in logs
- **Why It Matters**: Some requests fail unexpectedly
- **Effort**: 1-2 hours
- **Debug Steps**:
  1. Check CORS logs from next 100 requests
  2. Identify pattern (which endpoints, origins)
  3. Trace through CORS middleware logic
  4. Fix root cause

### P2.5: Settings Page Persistence
- **Problem**: Theme preference changes don't persist
- **Why It Matters**: User preferences reset on reload
- **Effort**: 1 hour
- **Steps**:
  1. Create `/api/settings` endpoint to store user prefs
  2. Wire Settings page to save/load
  3. Persist to database

---

## 🟡 TIER 3: NICE TO HAVE (Do when have time)

### P3.1: Real-Time Data Updates
- **Why**: Pages would update automatically instead of requiring reload
- **Effort**: 4-6 hours
- **Approach**: WebSocket connection to backend
- **Impact**: Medium (UX improvement)

### P3.2: Search & Filter UI
- **Why**: Users can find specific stocks/trades faster
- **Effort**: 2-3 hours per page
- **Impact**: Medium (UX improvement)

### P3.3: Data Export to CSV/Excel
- **Why**: Users can analyze data offline
- **Effort**: 2 hours
- **Impact**: Low (nice to have)

### P3.4: Test Suite Fixes
- **Why**: CI/CD pipeline clean
- **Effort**: 2-3 hours
- **Files**: `tests/unit/components/ui/tabs.test.jsx` (main issue)
- **Impact**: Low (dev experience)

---

## 📊 DATA ISSUES (Track separately)

### D1: Data Freshness Monitoring
- Missing: Automated check if data > 24 hours old
- Add: Scheduled task that alerts if data stale

### D2: Stage 2 Price Data Gap
- BRK.B, LEN.B, WSO.B missing today's prices
- Run: `python3 loadpricedaily.py --symbols BRK.B,LEN.B,WSO.B`

### D3: Distribution Days Table
- Returns empty when it should have data
- Check: Is this table being populated? Is data available?

---

## 🚀 RECOMMENDED SCHEDULE

**Day 1 (Today):**
- [ ] P1.2 - Add Alpaca credentials (15 min)
- [ ] P1.1 - Start Cognito setup (can be async)
- [ ] P1.3 - Verify EventBridge (30 min)
- [ ] P1.4 - Check database schema (30 min)

**Day 2:**
- [ ] P2.1 - Manual trade entry (2 hours)
- [ ] P2.2 - Error standardization (1-2 hours)
- [ ] P2.3 - Performance optimization (2 hours)

**Day 3:**
- [ ] P2.4 - CORS investigation
- [ ] P2.5 - Settings persistence
- [ ] P3.1 - Start real-time updates

---

## ✅ WHAT'S DONE

Frontend:
- ✅ All 13 dashboard pages working
- ✅ 0 console errors
- ✅ 131 successful API calls across all pages
- ✅ Protected routes functional
- ✅ Type safety in all components

Backend:
- ✅ API is healthy
- ✅ Database connected and healthy
- ✅ 360 indexes in place
- ✅ 3.8M+ price records
- ✅ 25+ endpoints working

Infrastructure:
- ✅ RDS PostgreSQL running
- ✅ Lambda functions deployed
- ✅ CloudFront CDN operational
- ✅ VPC networking complete

---

## 🎯 SUCCESS CRITERIA FOR EACH TIER

**Tier 1 Success**: 
- Auth works with real users
- Alpaca executing paper trades
- EventBridge loading data automatically
- All database queries succeed

**Tier 2 Success**:
- Manual trade entry works
- All APIs consistent error format
- Queries respond in <200ms
- Settings persist across sessions

**Tier 3 Success**:
- Real-time updates flowing
- Full text search on all lists
- Can export all data to CSV
- Tests all passing

---

## 💾 Files to Prioritize

Most impactful files to review:
1. `webapp/frontend/src/contexts/AuthContext.jsx` — Auth logic
2. `webapp/lambda/routes/trades.js` — Trade execution
3. `webapp/lambda/index.js` — Database & error handling
4. `terraform/modules/scheduler/` — EventBridge config
5. `.env.local` — Credentials

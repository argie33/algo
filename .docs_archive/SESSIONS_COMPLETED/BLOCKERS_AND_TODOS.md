# 🚨 BLOCKERS & WORK IN PROGRESS

Last updated: 2026-05-09 after comprehensive frontend audit

## Summary
- ✅ **Frontend**: All 13 pages rendering without errors
- ⚠️ **Backend**: Some database and infrastructure issues
- 🔴 **Data**: Missing or stale in several areas
- ⚠️ **Features**: Some partially implemented or missing

---

## 🔴 CRITICAL BLOCKERS (Must Fix to Go Live)

### 1. **Authentication Not Working**
- **Issue**: Dev auth fallback is active, real Cognito is not configured
- **Location**: `webapp/frontend/src/contexts/AuthContext.jsx`
- **Impact**: Cannot verify user identity, all trades appear anonymous
- **Status**: Mock auth working, real auth not set up
- **Fix Required**: Wire up Cognito with real credentials

### 2. **EventBridge Data Loading Not Active**
- **Issue**: Scheduled data loaders not running on EventBridge
- **Current State**: Manual trigger only via `python3 loadpricedaily.py`
- **Scheduled**: cron(0 22 ? * MON-FRI *) — not triggering
- **Impact**: Market data may be stale
- **Status**: Infrastructure in place, scheduler not firing
- **Fix Required**: Verify EventBridge IAM permissions and trigger

### 3. **Database Schema Issues**
- **Errors Observed**:
  - `column "index_value" does not exist` — fear_greed_index table missing column
  - `function to_timestamp(date, unknown) does not exist` — data type mismatch
  - Distribution days table may be empty or have missing indexes
- **Impact**: Some API endpoints fail silently or return empty
- **Fix Required**: Run database migrations, verify schema

### 4. **Missing Price Data — Stage 2 Gap**
- **Issue**: BRK.B, LEN.B, WSO.B in database but missing today's prices
- **Impact**: Pages showing these stocks will have stale data
- **Status**: Known limitation
- **Fix Required**: Run data loader for these symbols

### 5. **Alpaca Integration Not Configured**
- **Current State**: Paper trading credentials not loaded
- **Log Shows**: "⚠️ Alpaca credentials not configured - scheduler skipped"
- **File**: `.env.local` missing ALPACA_* variables
- **Impact**: Trading features disabled, algo cannot execute trades
- **Fix Required**: Add Alpaca API credentials to `.env.local`

---

## ⚠️ HIGH PRIORITY (Should Fix Before Production)

### 6. **CORS Configuration Too Strict (At Times)**
- **Issue**: Backend logs show "Error: Not allowed by CORS" intermittently
- **Current**: Explicit allowlist includes localhost:5173, but errors still occur
- **Possible Cause**: Request failure triggering CORS check on error handler
- **Impact**: Some requests fail with cryptic CORS errors
- **File**: `webapp/lambda/index.js:240-291`
- **Fix**: Verify CORS logic doesn't trigger on internal errors

### 7. **Database Performance Not Optimized**
- **Missing**: TimescaleDB for time-series data
- **Current**: Standard PostgreSQL indexes (created but not optimized)
- **Status**: Database optimization script exists but not integrated
- **Impact**: Market Overview and similar heavy queries may be slow
- **Fix**: Enable TimescaleDB or add query caching layer

### 8. **API Error Responses Inconsistent**
- **Issue**: Some endpoints return `{success: false, error: "..."}` on 404
- **Others**: Return proper HTTP 404 with error body
- **Impact**: Frontend error handling may miss some failures
- **Files to Check**: 
  - `webapp/lambda/routes/market.js` — just fixed distribution-days, check others
  - `webapp/lambda/utils/apiResponse.js`

### 9. **Manual Trade Entry Not Implemented**
- **Issue**: Trade Tracker shows "TODO: integrate with actual trade entry flow"
- **File**: `webapp/frontend/src/pages/TradeTracker.jsx`
- **Impact**: Can't manually enter trades, only view algo trades
- **Status**: UI built, backend integration missing
- **Fix**: Wire up POST `/api/trades` endpoint

### 10. **RDS Publicly Accessible (Security Risk)**
- **Current**: 0.0.0.0/0 allowed
- **Status**: Intentional for development, must fix before production
- **Fix**: Restrict to VPC or specific IPs in production

---

## 📋 MEDIUM PRIORITY (Nice to Have, Improves UX)

### 11. **No Real-Time Data Updates**
- **Issue**: Pages don't auto-refresh when new data arrives
- **Current**: Manual page reload required
- **Status**: WebSocket infrastructure exists but not connected
- **Fix**: Wire up real-time updates via WebSocket

### 12. **Search/Filter Not Fully Implemented**
- **Issue**: Many list pages missing search functionality
- **Current**: Static lists only
- **Files**: 
  - `pages/ScoresDashboard.jsx`
  - `pages/TradeTracker.jsx`
- **Fix**: Add search/filter UI and backend support

### 13. **No Data Export Feature**
- **Issue**: Can't export data to CSV/Excel
- **Impact**: Users can't analyze data offline
- **Status**: Not implemented
- **Fix**: Add export endpoints and UI buttons

### 14. **Settings Page Has No Backend Integration**
- **Issue**: Can change theme locally but settings don't persist
- **File**: `pages/Settings.jsx`
- **Fix**: Wire up to `/api/settings` endpoint

### 15. **Test Coverage Incomplete**
- **TODOs Found**:
  - "Fix test isolation for localStorage-based tests"
  - "Fix DOM querying - TabsContent not being found properly"
  - "Fix tab switching logic - multiple MuiTabs issue"
  - "Fix axios mocking for error handling tests"
- **Status**: Unit tests exist but have failing cases
- **Fix**: Debug and fix test suite

---

## 🔧 INFRASTRUCTURE & DEPLOYMENT

### 16. **Lambda Not in VPC**
- **Current**: Lambda has direct internet access
- **Status**: Intentional for development
- **Security**: Should move to VPC with NAT gateway for production
- **Fix**: Update Terraform to place Lambda in VPC

### 17. **No Automated Backups for RDS**
- **Current**: 7-day retention configured
- **Missing**: No backup testing, no restore playbook
- **Fix**: Document backup/restore procedure

### 18. **Monitoring & Alerting Minimal**
- **Missing**:
  - CloudWatch dashboards for API latency
  - SNS alerts for Lambda failures
  - Database connection pool monitoring
- **Impact**: Can't detect issues proactively
- **Fix**: Set up monitoring infrastructure

### 19. **No Load Testing Done**
- **Issue**: Unknown how many concurrent users system can handle
- **Impact**: May have issues when traffic spikes
- **Fix**: Run load tests and identify bottlenecks

---

## 📊 DATA QUALITY ISSUES

### 20. **Empty or Incomplete Tables**
- **Observations**:
  - Distribution days table: Returns empty `{}`
  - Fear & Greed: Some dates missing
  - AAII Sentiment: Possible gaps
- **Impact**: Pages show partial data
- **Fix**: Run full data loader refresh

### 21. **No Data Freshness Monitoring**
- **Issue**: No automatic alert if data becomes stale
- **Current**: Manual check via API diagnostics endpoint
- **Fix**: Add scheduled check that alerts if data > 24 hours old

---

## 📝 DOCUMENTATION & RUNBOOKS

### 22. **No Incident Runbook**
- **Missing**: Step-by-step procedures for common failures:
  - Database connection down
  - API Lambda failing
  - Data loader stuck
  - Algotrade stopped without reason
- **Status**: Described in code comments, not in ops docs
- **Fix**: Create `INCIDENT_RUNBOOK.md`

### 23. **API Documentation Incomplete**
- **Current**: ~5 endpoints documented
- **Needed**: All 25+ endpoints with:
  - Request/response examples
  - Error codes
  - Rate limits
- **Fix**: Auto-generate from code comments or use Swagger

---

## 🧪 KNOWN TEST FAILURES

### 24. **React Tab Component Tests Failing**
- **File**: `tests/unit/components/ui/tabs.test.jsx`
- **Issues**:
  - DOM querying not finding TabsContent
  - Tab switching logic broken (multiple MuiTabs)
- **Fix**: Debug test setup or refactor component

### 25. **Mobile Responsiveness Tests Skipped**
- **File**: `tests/component/MobileResponsiveness.test.jsx`
- **Status**: localStorage test isolation broken
- **Fix**: Fix test setup and re-enable

---

## 🎯 IMPLEMENTATION PRIORITIES

If limited time, fix in this order:

1. **CRITICAL** (blocks going live):
   - ✅ Frontend errors (DONE)
   - 🔴 Authentication setup
   - 🔴 EventBridge data loading
   - 🔴 Database schema validation
   - 🔴 Alpaca credentials

2. **HIGH** (makes system usable):
   - Manual trade entry
   - API error consistency
   - Database performance (caching)
   - CORS issue investigation

3. **MEDIUM** (nice to have):
   - Real-time updates
   - Search/filter
   - Settings persistence
   - Test suite fixes

4. **LOW** (doesn't block):
   - Data export
   - Advanced monitoring
   - RDS VPC migration (for prod)

---

## 📌 NEXT STEPS

Recommended immediate actions:

1. **Configure Alpaca** — Add credentials to `.env.local`
   ```bash
   ALPACA_API_KEY=your_key
   ALPACA_SECRET_KEY=your_secret
   ALPACA_BASE_URL=https://paper-trading.alpaca.markets
   ```

2. **Verify EventBridge** — Check if scheduler is active
   ```bash
   aws scheduler list-schedules --region us-east-1
   ```

3. **Run Database Schema Check**
   ```bash
   psql -h localhost -U stocks -d stocks < webapp/lambda/migrations/optimize-database-indexes.sql
   ```

4. **Set Up Cognito** — Wire real authentication
   - Create user pools
   - Add frontend config
   - Test login flow

5. **Load Missing Data** — Refresh price data
   ```bash
   python3 loadpricedaily.py
   ```

---

## 🔍 How to Investigate

For any issue, start here:

1. **Check logs**: `tail -f /aws/lambda/algo-orchestrator`
2. **Run diagnostics**: `curl http://localhost:3001/api/diagnostics`
3. **Check database**: `psql -h localhost -U stocks -d stocks -c "SELECT * FROM mv_latest_prices LIMIT 5;"`
4. **Monitor processes**: `docker ps` / AWS Lambda console
5. **Review code**: Search for error message in codebase

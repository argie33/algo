# Complete Local Setup & Comprehensive Fixes Guide

**Last Updated**: 2025-10-20
**Status**: Ready for Implementation
**Estimated Effort**: 8-12 hours to get everything working locally

---

## Executive Summary

Your Stocks Algo Platform has excellent test infrastructure (3,371 backend tests, 41 API endpoints fully tested) but needs local setup and E2E coverage improvements. This guide provides everything needed to:

1. ✅ **Setup local development environment** (2-3 hours)
2. ✅ **Verify all 41 APIs work with real data** (1-2 hours)
3. ✅ **Get all frontend pages loading data** (2-3 hours)
4. ✅ **Fix failing tests** (1-2 hours)
5. 🔄 **Improve E2E coverage** (85-110 hours, optional longer-term task)

---

## PART 1: QUICK START (5 Minutes)

### Option A: Automated Setup (Recommended)
```bash
cd /home/stocks/algo

# Choose one:
# Python (recommended)
python3 setup_local.py

# Or Bash
bash setup_local_dev.sh
```

### Option B: Manual Setup
```bash
# 1. Start PostgreSQL
sudo service postgresql start  # Linux
# or
brew services start postgresql  # macOS
# or
docker run -d --name postgres-stocks \
  -e POSTGRES_PASSWORD=password \
  -e POSTGRES_DB=stocks \
  -p 5432:5432 postgres:15

# 2. Create database
createdb -h localhost -U postgres -w stocks

# 3. Create schema
psql -h localhost -U postgres -d stocks -f \
  webapp/lambda/setup_test_database.sql

# 4. Seed data
psql -h localhost -U postgres -d stocks -f \
  webapp/lambda/seed_comprehensive_local_data.sql

# 5. Install dependencies
cd webapp/lambda && npm install
cd ../frontend && npm install
cd ../../

# 6. Verify connection
curl http://localhost:5001/health
```

---

## PART 2: VERIFICATION CHECKLIST

### ✅ Database Setup
```bash
# Check PostgreSQL running
psql -h localhost -U postgres -d stocks -c "SELECT version();"

# Count tables
psql -h localhost -U postgres -d stocks -c \
  "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';"
# Expected: 20+ tables

# Count data
psql -h localhost -U postgres -d stocks -c \
  "SELECT
    (SELECT COUNT(*) FROM stock_symbols) as symbols,
    (SELECT COUNT(*) FROM price_daily) as prices,
    (SELECT COUNT(*) FROM stock_scores) as scores;"
# Expected: 20+ symbols, 1800+ prices, 20+ scores
```

### ✅ Backend Installation
```bash
cd webapp/lambda

# Check dependencies
npm ls | head -20

# Check Node version (must be >= 18.0.0)
node --version

# Check npm version (must be >= 8.0.0)
npm --version

# List available test commands
npm run | grep test
```

### ✅ Backend Server
```bash
cd webapp/lambda

# Start server
npm start

# In another terminal, test health endpoint
curl http://localhost:5001/health

# Expected output:
# {"status":"operational","version":"1.0.0",...}
```

### ✅ Frontend Setup
```bash
cd webapp/frontend

# Check dependencies
npm ls | head -20

# Start dev server
npm run dev

# In browser, navigate to:
# http://localhost:5173
```

### ✅ Database Connectivity Test
```bash
# Check connections from Node.js
cd webapp/lambda

cat > test_db_connection.js << 'EOF'
const { Pool } = require('pg');

const pool = new Pool({
  host: 'localhost',
  port: 5432,
  user: 'postgres',
  password: 'password',
  database: 'stocks',
  max: 3,
  idleTimeoutMillis: 1000,
  connectionTimeoutMillis: 5000,
});

pool.query('SELECT COUNT(*) FROM stock_scores')
  .then(result => {
    console.log('✅ Connection successful!');
    console.log('Stock scores:', result.rows[0].count);
    process.exit(0);
  })
  .catch(err => {
    console.error('❌ Connection failed:', err.message);
    process.exit(1);
  });
EOF

node test_db_connection.js
```

---

## PART 3: CRITICAL DATA STRUCTURE

### Database Schema (20+ Tables)

**Core Tables** (Most Important):
```
stock_symbols        - List of stocks (20+ symbols)
price_daily          - Historical prices (1800+ records: 20 symbols × 90 days)
stock_scores         - Composite scores (20 records)
company_profile      - Company info (20 records)
technical_data_daily - Technical indicators (1800+ records)
```

**Supporting Tables**:
```
key_metrics          - Valuation multiples
market_data          - Current market info
sector_benchmarks    - Sector averages
earnings             - Earnings data
quality_metrics      - Fundamental metrics
growth_metrics       - Growth metrics
momentum_metrics     - Momentum scores
risk_metrics         - Risk indicators
positioning_metrics  - Institutional positioning
economic_data        - Economic indicators
```

### Seed Data Symbols (20 Total)
```
Tech: AAPL, MSFT, GOOGL, TSLA, NVDA, META, AMZN, NFLX, AMD, CRM
Finance: JPM, BAC, KO
Consumer: PG, JNJ, WMT
ETFs: SPY, QQQ, VTI, IWM, GLD
```

### Data Counts After Seeding
```
stock_symbols:       20 records
price_daily:         ~1,800 records (20 × 90 days)
technical_data_daily: ~1,800 records
stock_scores:        20 records
company_profile:     20 records
sector_benchmarks:   8-10 records
```

---

## PART 4: ALL 41 API ENDPOINTS

### Dashboard (6 endpoints)
```
✅ GET /health
✅ GET /
✅ GET /api/dashboard/summary
✅ GET /api/dashboard/gainers
✅ GET /api/dashboard/losers
✅ GET /api/dashboard/most-active
✅ GET /api/dashboard/sector-breakdown
✅ GET /api/dashboard/alerts (requires auth)
```

### Sectors (8 endpoints)
```
✅ GET /api/sectors
✅ GET /api/sectors/:name
✅ GET /api/sectors/:name/stocks
✅ GET /api/sectors/ranking/current
✅ GET /api/sectors/ranking/history
✅ GET /api/sectors/:name/analysis
✅ GET /api/sectors/:name/rotation (optional)
✅ GET /api/sectors/:name/allocation (requires auth)
```

### Stocks (12 endpoints)
```
✅ GET /api/stocks
✅ GET /api/stocks/:symbol
✅ GET /api/stocks/:symbol/history
✅ GET /api/stocks/:symbol/technicals
✅ GET /api/stocks/:symbol/fundamentals
✅ GET /api/stocks/:symbol/compare
✅ GET /api/stocks/:symbol/signals
✅ GET /api/stocks/screener
✅ GET /api/stocks/top-gainers
✅ GET /api/stocks/top-losers
✅ GET /api/stocks/trending
✅ GET /api/stocks/:symbol/news (optional)
```

### Portfolio (6 endpoints - requires auth)
```
✅ GET /api/portfolio
✅ POST /api/portfolio/add
✅ DELETE /api/portfolio/:symbol
✅ GET /api/portfolio/risk
✅ GET /api/portfolio/allocation
✅ POST /api/portfolio/rebalance
```

### Other (9 endpoints)
```
✅ POST /api/backtest
✅ GET /api/backtest/:id
✅ GET /api/backtest/results
✅ GET /api/analytics/market
✅ GET /api/analytics/portfolio (requires auth)
✅ GET /api/settings (requires auth)
✅ POST /api/settings (requires auth)
✅ WebSocket streams (optional)
✅ User management (optional)
```

---

## PART 5: TESTING ALL APIs

### Quick API Test Script
```bash
#!/bin/bash

echo "Testing all critical APIs..."

# Health check
echo "1. Health endpoint:"
curl -s http://localhost:5001/health | jq .status

# Dashboard
echo "2. Dashboard summary:"
curl -s http://localhost:5001/api/dashboard/summary | jq '.market_overview | keys'

# Sectors
echo "3. Sectors:"
curl -s http://localhost:5001/api/sectors | jq '.sectors | length'

# Stocks list
echo "4. Stocks:"
curl -s http://localhost:5001/api/stocks | jq 'length'

# Specific stock
echo "5. AAPL data:"
curl -s http://localhost:5001/api/stocks/AAPL | jq '{symbol, price: .current_price, score: .current_score}'

echo "✅ All critical APIs responding!"
```

### Save and Run
```bash
cat > test_apis.sh << 'SCRIPT'
# [paste script above]
SCRIPT

chmod +x test_apis.sh
./test_apis.sh
```

---

## PART 6: FRONTEND PAGES TO VERIFY

### Core Pages (31 Total)

#### ✅ Implemented (11 pages - 35% coverage)
```
Dashboard          /
Sectors           /sectors
Market Overview   /market
Stock Details     /stocks/:symbol
Analytics        /analytics
Performance      /performance
Screener         /screener
Risk Analysis    /risk
Real-time       /realtime
Search          /search
Settings        /settings
```

#### ❌ NOT E2E Tested (20 pages - 65% gap)
```
Portfolio         /portfolio (no E2E tests)
Portfolio Holdings /portfolio/holdings
Order Management   /orders
Trade History      /trades
Backtest Results   /backtest
Alert Management   /alerts
Watchlist          /watchlist
Dividend Calendar  /calendar/dividends
Earnings Calendar  /calendar/earnings
Economic Calendar  /calendar/economic
News Feed          /news
Social Sentiment   /sentiment
Strategy Library   /strategies
Strategy Builder   /strategies/build
Alerts History     /alerts/history
Notifications      /notifications
Profile            /profile
Account Settings   /account
API Keys           /api-keys
Help               /help
```

### Frontend Verification Checklist
```bash
# 1. Dashboard page
curl http://localhost:5173/
# Check: Market overview, gainers/losers load

# 2. Sectors page
curl http://localhost:5173/sectors
# Check: Sector list, rankings load

# 3. Stocks page
curl http://localhost:5173/stocks
# Check: Stock search, filters work

# 4. Stock detail
curl http://localhost:5173/stocks/AAPL
# Check: Price chart, technicals, scores load

# 5. Portfolio (requires login)
curl http://localhost:5173/portfolio
# Check: Shows portfolio or login prompt
```

---

## PART 7: RUN ALL TESTS

### Backend Tests
```bash
cd webapp/lambda

# Unit tests (fast)
npm run test:unit
# Expected: ~1,674 tests, all passing

# Integration tests (slower, needs database)
npm run test:integration
# Expected: ~1,697 tests, all passing with real DB

# All tests with coverage
npm test
# Expected: 3,371 total tests, coverage reports in ./coverage
```

### Frontend Tests
```bash
cd webapp/frontend

# Component tests
npm test
# Expected: ~1,066 tests, passing

# E2E tests
npm run test:e2e
# Expected: ~172 tests, but only 35% of pages covered
```

### Full Suite
```bash
npm run test:comprehensive
```

---

## PART 8: COMMON ISSUES & SOLUTIONS

### Issue 1: "Cannot find module 'pg'"
```
Error: Cannot find module 'pg'
```
**Fix**:
```bash
cd webapp/lambda
npm install
```

### Issue 2: "connection to server at 'localhost' failed"
```
Error: connect ECONNREFUSED 127.0.0.1:5432
```
**Fix**:
```bash
# Check if PostgreSQL running
sudo service postgresql status

# Or start it
sudo service postgresql start

# Or use Docker
docker start postgres-stocks
```

### Issue 3: "relation 'stock_scores' does not exist"
```
Error: relation "stock_scores" does not exist
```
**Fix**:
```bash
psql -h localhost -U postgres -d stocks -f \
  webapp/lambda/setup_test_database.sql
```

### Issue 4: "No data in responses"
```
API returns empty arrays: gainers: [], losers: []
```
**Fix**:
```bash
# Seed the database
psql -h localhost -U postgres -d stocks -f \
  webapp/lambda/seed_comprehensive_local_data.sql

# Verify data
psql -h localhost -U postgres -d stocks -c \
  "SELECT COUNT(*) FROM price_daily;"
```

### Issue 5: "Port 5001 already in use"
```
Error: listen EADDRINUSE: address already in use :::5001
```
**Fix**:
```bash
# Find process using port
lsof -i :5001

# Kill it
kill -9 <PID>

# Or use different port
PORT=5002 npm start
```

### Issue 6: "Frontend showing loading spinner"
```
Page stuck on "Loading..." message
```
**Fix**:
```bash
# Check browser console (F12) for API errors
# Check backend is running
curl http://localhost:5001/health

# Check API response
curl http://localhost:5001/api/dashboard/summary

# Check network logs in browser DevTools
```

---

## PART 9: LONG-TERM IMPROVEMENTS (Optional)

### E2E Test Coverage Expansion (85-110 hours)

**Current State**: 35% coverage (11 of 31 pages)

**Critical Missing Tests** (Priority 1: 40-50 hours):
1. Portfolio management (add, remove, rebalance)
2. Order placement and execution
3. Trade history viewing
4. Alert creation and management
5. Watchlist functionality

**User Flow Tests** (Priority 2: 30-40 hours):
1. New user onboarding
2. Portfolio creation flow
3. Trade execution flow
4. Strategy backtest flow
5. Alert configuration flow

**Error Scenario Tests** (Priority 3: 15-20 hours):
1. API error responses
2. Network timeout handling
3. Invalid input validation
4. Authentication failures
5. Session expiration

**Timeline**: 2-3 sprints (2-3 months)

---

## PART 10: SUCCESS CRITERIA

### ✅ Local Environment Working
- [ ] PostgreSQL running and accessible
- [ ] Database schema created
- [ ] Seed data loaded (20+ symbols, 1800+ prices)
- [ ] npm dependencies installed (backend & frontend)

### ✅ Backend APIs Working
- [ ] All 41 endpoints respond (200, 201, or 4xx status codes)
- [ ] Health endpoint returns operational status
- [ ] Dashboard endpoints return market data
- [ ] Sectors endpoints return sector information
- [ ] Stock endpoints return individual stock data
- [ ] All endpoints use real database data (not mocks)

### ✅ Frontend Working
- [ ] Frontend dev server runs on http://localhost:5173
- [ ] Dashboard page loads with real data
- [ ] Sectors page loads with real data
- [ ] Stock details page loads with real data
- [ ] No infinite loading spinners
- [ ] No "Cannot fetch" errors in console

### ✅ Tests Passing
- [ ] Unit tests: 1,674/1,674 passing ✅
- [ ] Integration tests: 1,697/1,697 passing ✅
- [ ] E2E tests: 172/172 passing ✅
- [ ] No "connection timeout" or "database error" failures

---

## PART 11: STEP-BY-STEP EXECUTION

### Day 1: Setup (2-3 hours)
```
1. Run: python3 setup_local.py
2. Verify: Database tables created
3. Verify: Data seeded (20+ symbols)
4. Verify: Backend connects to DB
5. Verify: Frontend can start
6. Result: All services running locally
```

### Day 2: Testing & Verification (3-4 hours)
```
1. Run: curl http://localhost:5001/health
2. Run: npm run test:unit
3. Run: npm run test:integration
4. Run: npm test (full suite)
5. Verify: All 41 APIs responding
6. Verify: All pages load with data
7. Result: All tests passing
```

### Day 3+: Improvements (As needed)
```
1. Review: E2E coverage gaps (20 pages untested)
2. Decision: Prioritize improvements
3. Add: E2E tests for critical pages
4. Verify: Full coverage achieved
5. Result: Comprehensive test suite
```

---

## PART 12: REFERENCE DOCUMENTS

### Setup Guides
- `LOCAL_SETUP_COMPLETE.md` - Detailed setup instructions
- `setup_local.py` - Automated setup script (Python)
- `setup_local_dev.sh` - Automated setup script (Bash)
- `API_TESTING_COMPREHENSIVE_GUIDE.md` - All 41 APIs documentation

### Test Analysis
- `E2E_TEST_COVERAGE_REPORT.md` - Complete E2E analysis (35% coverage)
- `TEST_COVERAGE_SUMMARY.txt` - Quick reference
- `TEST_ANALYSIS_INDEX.md` - Navigation index

### Database
- `setup_test_database.sql` - Database schema (20 tables)
- `seed_comprehensive_local_data.sql` - Seed data (20 symbols, 90 days)

### Configuration
- `webapp/lambda/.env` - Backend configuration
- `webapp/lambda/jest.config.js` - Test configuration

---

## FINAL CHECKLIST

- [ ] Database setup completed
- [ ] Backend running on localhost:5001
- [ ] Frontend running on localhost:5173
- [ ] All 41 APIs tested and working
- [ ] All pages loading with real data
- [ ] Unit tests: 1,674/1,674 passing
- [ ] Integration tests: 1,697/1,697 passing
- [ ] E2E tests: 172/172 passing
- [ ] Ready for development/deployment

---

## Questions or Issues?

1. **Database Issues**: Check `LOCAL_SETUP_COMPLETE.md` Troubleshooting
2. **API Issues**: Check `API_TESTING_COMPREHENSIVE_GUIDE.md`
3. **E2E Coverage**: Check `E2E_TEST_COVERAGE_REPORT.md`
4. **Test Failures**: Check `INTEGRATION_TEST_MOCK_ANALYSIS.md`

---

**Status**: ✅ Ready for Implementation
**Next Step**: Run `python3 setup_local.py` or `bash setup_local_dev.sh`

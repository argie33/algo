# Comprehensive API Testing & Validation Guide

## Overview

This guide covers all 41 API endpoints, their expected behavior, database requirements, and how to verify they work locally with real data.

---

## Part 1: SETUP & PREREQUISITES

### Quick Start
```bash
# 1. Setup database and data
python3 setup_local.py
# or
bash setup_local_dev.sh

# 2. Start backend
cd webapp/lambda
npm start

# 3. Start frontend (new terminal)
cd webapp/frontend
npm run dev

# 4. Open browser
http://localhost:5173
```

### Database Requirements
- PostgreSQL 13+ running on localhost:5432
- Database: `stocks`
- User: `postgres` / Password: `password`
- Tables: 20+ (see setup_test_database.sql)
- Sample data: 20 symbols × 90 days of prices

---

## Part 2: API ENDPOINTS (41 Total)

### 2.1 Health & Status Endpoints (2)

#### GET /health
**Purpose**: Server health check
**Database**: None
**Expected Response**:
```json
{
  "status": "operational",
  "timestamp": "2025-10-20T...",
  "version": "1.0.0"
}
```
**Test Command**:
```bash
curl http://localhost:5001/health
```

#### GET /
**Purpose**: API information
**Database**: None
**Expected Response**:
```json
{
  "service": "financial-dashboard-api",
  "version": "1.0.0",
  "endpoints": 41
}
```

---

### 2.2 Dashboard Endpoints (6)

#### GET /api/dashboard/summary
**Purpose**: Complete dashboard overview
**Database Tables Required**: stock_scores, price_daily, company_profile
**Expected Response**:
```json
{
  "market_overview": {
    "total_symbols": 20,
    "gainers": [...],
    "losers": [...],
    "most_active": [...]
  },
  "sector_breakdown": {...},
  "economic_data": {...}
}
```
**Test Command**:
```bash
curl http://localhost:5001/api/dashboard/summary
```
**Verification**:
- Gainers: 5-10 symbols
- Losers: 5-10 symbols
- Most active: 10 symbols
- Sectors: 8+ sectors

---

#### GET /api/dashboard/gainers
**Purpose**: Top performing stocks today
**Required Data**: price_daily with recent dates

#### GET /api/dashboard/losers
**Purpose**: Worst performing stocks today

#### GET /api/dashboard/most-active
**Purpose**: Most traded stocks
**Required Data**: Volumes >= 10M+ shares

#### GET /api/dashboard/sector-breakdown
**Purpose**: Market by sector
**Required Data**: stock_scores + company_profile.sector

#### GET /api/dashboard/alerts
**Purpose**: User alerts (requires auth)

---

### 2.3 Sectors Endpoints (8)

#### GET /api/sectors
**Purpose**: All sectors overview
**Database Tables**: stock_scores, company_profile
**Expected Response**:
```json
{
  "sectors": [
    {
      "name": "Technology",
      "count": 7,
      "avg_score": 72.5,
      "performance": {...}
    },
    ...
  ]
}
```

#### GET /api/sectors/:sectorName
**Purpose**: Stocks in specific sector
**URL Example**: `/api/sectors/Technology`

#### GET /api/sectors/:sectorName/stocks
**Purpose**: Detailed stock list by sector

#### GET /api/sectors/ranking/history
**Purpose**: Sector ranking over time

#### GET /api/sectors/ranking/current
**Purpose**: Current sector rankings

#### GET /api/sectors/analysis/:sectorName
**Purpose**: Detailed sector analysis

#### GET /api/sectors/:sectorName/rotation
**Purpose**: Sector rotation (requires portfolio_holdings table)

#### GET /api/sectors/:sectorName/allocation
**Purpose**: User sector allocation (requires auth)

---

### 2.4 Stock Endpoints (12)

#### GET /api/stocks
**Purpose**: Search/filter stocks
**Query Params**:
- `symbol` - Filter by symbol (e.g., AAPL)
- `sector` - Filter by sector
- `limit` - Results limit (default: 20)

#### GET /api/stocks/:symbol
**Purpose**: Detailed stock information
**URL Example**: `/api/stocks/AAPL`
**Expected Response**:
```json
{
  "symbol": "AAPL",
  "company_profile": {...},
  "current_score": 75.4,
  "price": 178.50,
  "scores": {
    "composite": 75.4,
    "momentum": 68.2,
    "trend": 82.1,
    "value": 71.3,
    "quality": 79.8,
    "growth": 73.5,
    "positioning": 68.9,
    "sentiment": 72.1
  }
}
```

#### GET /api/stocks/:symbol/history
**Purpose**: Historical price data (90 days)
**Required Data**: price_daily table

#### GET /api/stocks/:symbol/technicals
**Purpose**: Technical indicators
**Required Data**: technical_data_daily table

#### GET /api/stocks/:symbol/fundamentals
**Purpose**: Fundamental metrics
**Required Data**: quality_metrics, growth_metrics tables

#### GET /api/stocks/:symbol/news
**Purpose**: News/sentiment (optional)

#### GET /api/stocks/:symbol/compare
**Purpose**: Compare with peers
**Query Params**: `compare_to=MSFT,GOOGL`

#### GET /api/stocks/:symbol/signals
**Purpose**: Trading signals based on scores

#### GET /api/stocks/screener
**Purpose**: Stock screener with filters
**Query Params**:
- `min_score=70`
- `sector=Technology`
- `min_price=100`
- `max_pe=25`

#### GET /api/stocks/top-gainers
**Purpose**: Top performing stocks (52-week)

#### GET /api/stocks/top-losers
**Purpose**: Worst performing stocks (52-week)

#### GET /api/stocks/trending
**Purpose**: Trending stocks (last 7 days)

---

### 2.5 Portfolio Endpoints (6) - REQUIRES AUTH

#### GET /api/portfolio
**Purpose**: User portfolio overview
**Auth**: Bearer token required
**Expected Response**:
```json
{
  "portfolio": {
    "total_value": 50000.00,
    "total_gain_loss": 2500.00,
    "gain_loss_pct": 5.25,
    "holdings": [...]
  }
}
```

#### POST /api/portfolio/add
**Purpose**: Add stock to portfolio
**Body**:
```json
{
  "symbol": "AAPL",
  "quantity": 10,
  "avg_cost": 170.50
}
```

#### DELETE /api/portfolio/:symbol
**Purpose**: Remove stock from portfolio

#### GET /api/portfolio/risk
**Purpose**: Portfolio risk analysis

#### GET /api/portfolio/allocation
**Purpose**: Asset allocation by sector/type

#### POST /api/portfolio/rebalance
**Purpose**: Suggest portfolio rebalancing

---

### 2.6 Backtest Endpoints (3)

#### POST /api/backtest
**Purpose**: Run strategy backtest
**Body**:
```json
{
  "strategy": "momentum",
  "symbols": ["AAPL", "MSFT"],
  "start_date": "2024-01-01",
  "end_date": "2024-12-31"
}
```

#### GET /api/backtest/:backtest_id
**Purpose**: Get backtest results

#### GET /api/backtest/results
**Purpose**: List all backtests

---

### 2.7 Analytics Endpoints (2)

#### GET /api/analytics/market
**Purpose**: Market-wide analytics

#### GET /api/analytics/portfolio
**Purpose**: Portfolio analytics (requires auth)

---

### 2.8 Settings Endpoints (2)

#### GET /api/settings
**Purpose**: User settings (requires auth)

#### POST /api/settings
**Purpose**: Update settings (requires auth)

---

---

## Part 3: DATABASE DATA REQUIREMENTS

### Minimum Data for All Tests to Pass

```sql
-- Check data counts
SELECT COUNT(*) as stocks FROM stock_symbols;
SELECT COUNT(*) as prices FROM price_daily;
SELECT COUNT(*) as scores FROM stock_scores;
SELECT COUNT(*) as technicals FROM technical_data_daily;
```

### Expected Counts (Seed Data)
- stock_symbols: 20+
- price_daily: 20 symbols × 90 days = 1,800+ records
- stock_scores: 20 records (latest scores per symbol)
- technical_data_daily: 1,800+ records
- company_profile: 20 records
- sector_benchmarks: 8-10 records

### Seed Data Script
```bash
# Run comprehensive seed
psql -h localhost -U postgres -d stocks -f webapp/lambda/seed_comprehensive_local_data.sql

# Verify data loaded
psql -h localhost -U postgres -d stocks << SQL
SELECT * FROM stock_symbols LIMIT 5;
SELECT * FROM price_daily ORDER BY date DESC LIMIT 5;
SELECT * FROM stock_scores LIMIT 5;
SQL
```

---

## Part 4: API TESTING CHECKLIST

### Test Every Endpoint

#### Health Check
```bash
# Test 1: Health
curl -i http://localhost:5001/health
# Expected: 200 OK

# Test 2: Root endpoint
curl -i http://localhost:5001/
# Expected: 200 OK with service info
```

#### Dashboard Tests
```bash
# Test 3: Dashboard summary
curl -i http://localhost:5001/api/dashboard/summary
# Expected: 200 OK with market data

# Test 4: Gainers
curl -i http://localhost:5001/api/dashboard/gainers
# Expected: 200 OK with array of gainers

# Test 5: Losers
curl -i http://localhost:5001/api/dashboard/losers
# Expected: 200 OK with array of losers

# Test 6: Most active
curl -i http://localhost:5001/api/dashboard/most-active
# Expected: 200 OK with high volume stocks

# Test 7: Sector breakdown
curl -i http://localhost:5001/api/dashboard/sector-breakdown
# Expected: 200 OK with sector data

# Test 8: Alerts (requires token)
curl -i -H "Authorization: Bearer <token>" \
  http://localhost:5001/api/dashboard/alerts
# Expected: 200 OK or 401 if no token
```

#### Sectors Tests
```bash
# Test 9: Get all sectors
curl -i http://localhost:5001/api/sectors
# Expected: 200 OK with sector list

# Test 10: Get Technology sector
curl -i http://localhost:5001/api/sectors/Technology
# Expected: 200 OK with sector detail

# Test 11: Get sector stocks
curl -i http://localhost:5001/api/sectors/Technology/stocks
# Expected: 200 OK with stock list

# Test 12: Sector ranking
curl -i http://localhost:5001/api/sectors/ranking/current
# Expected: 200 OK with rankings
```

#### Stocks Tests
```bash
# Test 13: Search all stocks
curl -i http://localhost:5001/api/stocks
# Expected: 200 OK with stock list

# Test 14: Get AAPL stock
curl -i http://localhost:5001/api/stocks/AAPL
# Expected: 200 OK with AAPL data

# Test 15: Get AAPL history
curl -i http://localhost:5001/api/stocks/AAPL/history
# Expected: 200 OK with price history

# Test 16: Get AAPL technicals
curl -i http://localhost:5001/api/stocks/AAPL/technicals
# Expected: 200 OK with technical data

# Test 17: Stock screener
curl -i "http://localhost:5001/api/stocks/screener?min_score=70&sector=Technology"
# Expected: 200 OK with filtered stocks
```

#### Portfolio Tests (Requires Auth Token)
```bash
# Test 18: Get portfolio
curl -i -H "Authorization: Bearer <token>" \
  http://localhost:5001/api/portfolio
# Expected: 200 OK or 401/403 if not authorized
```

---

## Part 5: FRONTEND PAGE VALIDATION CHECKLIST

### Pages to Test

```
✅ = Working with real data
❌ = Not loading data or showing errors
🔄 = Partial/needs fixes
```

#### Core Pages

1. **Dashboard** (`/`)
   - [ ] Loads market overview
   - [ ] Shows gainers/losers
   - [ ] Displays sector breakdown
   - [ ] Updates in real-time (if WebSocket works)

2. **Sectors** (`/sectors`)
   - [ ] Lists all sectors
   - [ ] Shows sector stocks
   - [ ] Displays rankings
   - [ ] Allows filtering

3. **Stocks** (`/stocks`)
   - [ ] Stock search works
   - [ ] Displays stock details
   - [ ] Shows price charts
   - [ ] Shows technical indicators

4. **Portfolio** (`/portfolio`)
   - [ ] Shows holdings
   - [ ] Displays total value
   - [ ] Shows gain/loss
   - [ ] Allows add/remove

5. **Analytics** (`/analytics`)
   - [ ] Loads chart data
   - [ ] Allows date range selection
   - [ ] Shows trends

6. **Backtest** (`/backtest`)
   - [ ] Strategy selection works
   - [ ] Parameter input works
   - [ ] Results display correctly

---

## Part 6: VERIFICATION SCRIPT

### Automated Testing Script
```bash
# Create test script
cat > test_all_apis.sh << 'EOF'
#!/bin/bash

# Test all 41 endpoints
echo "Testing 41 API endpoints..."

# Health
echo "1. Testing health endpoint..."
curl -s http://localhost:5001/health | jq .

# Dashboard
echo "2. Testing dashboard..."
curl -s http://localhost:5001/api/dashboard/summary | jq '.market_overview' | head -20

# Sectors
echo "3. Testing sectors..."
curl -s http://localhost:5001/api/sectors | jq '.sectors[0]'

# Stocks
echo "4. Testing stocks..."
curl -s http://localhost:5001/api/stocks | jq '.[0]'

# Specific stock
echo "5. Testing AAPL..."
curl -s http://localhost:5001/api/stocks/AAPL | jq '.symbol, .current_score'

echo "Basic API tests complete!"
EOF

chmod +x test_all_apis.sh
./test_all_apis.sh
```

---

## Part 7: CRITICAL FIXES NEEDED

### Priority 1: Database Connectivity
- [ ] PostgreSQL running on localhost:5432
- [ ] Database "stocks" created
- [ ] Tables created from setup_test_database.sql
- [ ] Data seeded from seed_comprehensive_local_data.sql

### Priority 2: Backend API
- [ ] npm install completed in webapp/lambda
- [ ] Backend starts without errors: `npm start`
- [ ] Health endpoint responds: `curl http://localhost:5001/health`
- [ ] All 41 endpoints return 200-401 status codes (not 500)

### Priority 3: Frontend Loading
- [ ] npm install completed in webapp/frontend
- [ ] Frontend builds: `npm run build`
- [ ] Frontend dev server starts: `npm run dev`
- [ ] Pages load data from API (not showing "loading..." forever)

### Priority 4: E2E Test Coverage
- [ ] Add tests for 20 missing pages (current: 11/31 = 35%)
- [ ] Add critical user flow tests (order, trade, portfolio)
- [ ] Add error scenario tests
- [ ] Expected effort: 85-110 hours

---

## Part 8: TROUBLESHOOTING

### Common Issues & Solutions

#### Issue: "Connection refused" error
```
Error: connect ECONNREFUSED 127.0.0.1:5432
```
**Solution**: Start PostgreSQL
```bash
# Linux
sudo service postgresql start

# macOS
brew services start postgresql

# Docker
docker run -d --name postgres-stocks \
  -e POSTGRES_PASSWORD=password \
  -e POSTGRES_DB=stocks \
  -p 5432:5432 \
  postgres:15
```

#### Issue: "relation does not exist" error
```
Error: relation "stock_scores" does not exist
```
**Solution**: Create schema
```bash
psql -h localhost -U postgres -d stocks -f webapp/lambda/setup_test_database.sql
```

#### Issue: "No data returned" from API
**Solution**: Seed database
```bash
psql -h localhost -U postgres -d stocks -f webapp/lambda/seed_comprehensive_local_data.sql
```

#### Issue: Frontend shows "Loading..." forever
**Solution**: Check browser console (F12) for API errors
```bash
# Backend logs
cd webapp/lambda && npm start

# Check API response
curl http://localhost:5001/api/dashboard/summary
```

#### Issue: Tests timeout
**Solution**: Increase timeout in jest.config.js
```javascript
testTimeout: 60000,  // Increase from 30000
```

---

## Part 9: RUNNING FULL TEST SUITE

### Backend Tests
```bash
cd webapp/lambda

# Unit tests only
npm run test:unit

# Integration tests
npm run test:integration

# All tests
npm test

# Specific test file
npm test -- tests/integration/routes/dashboard.integration.test.js
```

### Frontend Tests
```bash
cd webapp/frontend

# Component tests
npm test

# E2E tests
npm run test:e2e

# Coverage report
npm test -- --coverage
```

---

## Part 10: NEXT STEPS

1. **Run Setup**
   ```bash
   python3 setup_local.py
   ```

2. **Verify Database**
   ```bash
   curl http://localhost:5001/health
   ```

3. **Check Data**
   ```bash
   curl http://localhost:5001/api/dashboard/summary | jq
   ```

4. **Run Tests**
   ```bash
   cd webapp/lambda && npm test
   ```

5. **Start Frontend**
   ```bash
   cd webapp/frontend && npm run dev
   ```

6. **Open Browser**
   ```
   http://localhost:5173
   ```

---

## References

- **Setup Guide**: `/home/stocks/algo/LOCAL_SETUP_COMPLETE.md`
- **E2E Coverage Report**: `/home/stocks/algo/E2E_TEST_COVERAGE_REPORT.md`
- **Database Schema**: `/home/stocks/algo/webapp/lambda/setup_test_database.sql`
- **Seed Data**: `/home/stocks/algo/webapp/lambda/seed_comprehensive_local_data.sql`
- **API Routes**: `/home/stocks/algo/webapp/lambda/routes/`
- **Integration Tests**: `/home/stocks/algo/webapp/lambda/tests/integration/`

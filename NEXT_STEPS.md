# Next Steps: Verify Production Readiness

## Phase 1: Prepare Local Development Environment (30 minutes)

### 1.1 Database Setup
```bash
# Ensure PostgreSQL is running on localhost:5432
psql --version
psql -U postgres

# Create database and user
createuser -P stocks  # password: (empty or your choice)
createdb -O stocks stocks
```

### 1.2 Environment Configuration
```bash
# Set environment variables (Linux/Mac)
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=stocks
export DB_USER=stocks
export DB_PASSWORD=""
export ALPACA_API_KEY=your_key_here
export ALPACA_SECRET_KEY=your_secret_here

# On Windows PowerShell
$env:DB_HOST = "localhost"
$env:DB_PORT = "5432"
$env:DB_NAME = "stocks"
$env:DB_USER = "stocks"
$env:DB_PASSWORD = ""
$env:ALPACA_API_KEY = "your_key_here"
$env:ALPACA_SECRET_KEY = "your_secret_here"
```

### 1.3 Initialize Database
```bash
python3 init_database.py
# Expected output: ✓ Database schema initialized successfully!
```

---

## Phase 2: Run Data Pipeline (40 minutes)

### 2.1 Run All Loaders
```bash
python3 run-all-loaders.py

# Expected output:
# Tier 0: Stock symbols - ✓
# Tier 1: Price data - ✓ (daily/etf)
# Tier 1b: Price aggregates - ✓ (weekly/monthly)
# Tier 1c: Technical indicators - ✓ (2 loaders)
# Tier 1d: Trend template - ✓
# Tier 2: Reference data - ✓ (20+ loaders)
# Tier 2b: Computed metrics - ✓
# Tier 2d: Stock scores - ✓
# Tier 3: Trading signals - ✓
# Tier 3b: Signal aggregates - ✓
# Tier 4: Signal quality scores - ✓
# 
# SUMMARY: Successful: 30+/40 (some rate limits OK)
```

### 2.2 Check Data Loaded
```bash
# Connect to database
psql -U stocks stocks

# Check row counts
SELECT COUNT(*) FROM price_daily;           -- Should be 100K+
SELECT COUNT(*) FROM buy_sell_daily;        -- Should be 10K+
SELECT COUNT(*) FROM stock_scores;          -- Should be 500+
SELECT COUNT(*) FROM technical_data_daily;  -- Should be 50K+
SELECT COUNT(*) FROM trend_template_data;   -- Should be 50K+
SELECT COUNT(*) FROM market_health_daily;   -- Should be 250+
SELECT COUNT(*) FROM signal_quality_scores; -- Should be 10K+

# Check freshness
SELECT MAX(date) FROM price_daily;          -- Should be today or yesterday
SELECT MAX(date) FROM stock_scores;         -- Should be today or yesterday
```

---

## Phase 3: Start Backend API (5 minutes)

### 3.1 Install Dependencies (first time only)
```bash
cd webapp/lambda
npm install
```

### 3.2 Start API Server
```bash
npm start
# Expected output:
# Database connected successfully
# Server running on port 3001
# Health check endpoint available
```

### 3.3 Test Health Check
```bash
curl http://localhost:3001/api/health
# Expected: {"status":"healthy", "healthy":true, ...}

curl http://localhost:3001/api/health/pipeline
# Expected: Full pipeline status with table health (HEALTHY/STALE/EMPTY)

curl http://localhost:3001/api/health/detailed
# Expected: Database connection status + table counts
```

---

## Phase 4: Start Frontend (5 minutes)

### 4.1 Install Dependencies (first time only)
```bash
cd webapp/frontend
npm install
```

### 4.2 Start Dev Server
```bash
npm run dev
# Expected output:
# VITE v7.1.3  ready in XXX ms
# ➜  Local:   http://localhost:5173/
# ➜  press h + enter to show help
```

### 4.3 Open in Browser
```
http://localhost:5173
```

---

## Phase 5: Test Frontend Pages (30 minutes)

**CRITICAL TEST**: Open F12 Console (Ctrl+Shift+I or Cmd+Option+I), go to Console tab.  
**REQUIREMENT**: Zero errors, zero warnings throughout testing.

### 5.1 Navigate Through All Pages

**Markets Section:**
- [ ] Market Overview - displays fear/greed, sectors, market health
- [ ] Sectors - displays sector ranking with momentum scores
- [ ] Economic Data - displays economic indicators
- [ ] Sentiment - displays analyst sentiment, NAAIM data

**Trading Signals:**
- [ ] Trading Signals - displays swing signals with pagination
- [ ] Shows: symbol, date, signal, price, RSI, ADX, volume

**Portfolio Section:**
- [ ] Portfolio - displays open positions
- [ ] Trade History - displays closed trades with P&L
- [ ] Performance - displays Sharpe, Sortino, max drawdown, win rate
- [ ] Pre-Trade Simulator - simulates impact of new trade

**Analysis Section:**
- [ ] Backtest - displays backtest results
- [ ] Scores - displays stock scores (MUST show swing_score, grade, price, market_cap)

**Algo Trading:**
- [ ] Algo Dashboard - displays orchestrator status, execution history
- [ ] Notifications - displays system alerts and trade notifications

**Service Health:**
- [ ] Shows API health, data freshness, pipeline status

### 5.2 Specific Data Checks

**On ScoresDashboard page:**
```
Expected columns:
- Symbol: AAPL
- Swing Score: 85 (numeric)
- Grade: A+ (letter grade)
- Trend Score: 85 (numeric)
- Price: $150.25
- Change%: +2.5%
- Market Cap: $2.5T
```

**On TradingSignals page:**
```
Expected columns:
- Symbol: AAPL
- Date: 2026-05-18
- Signal: BUY or SELL
- Price: $150.25
- RSI: 65
- ADX: 25
- Volume: 45M
- Status: All rows should render
```

**On PerformanceMetrics page:**
```
Expected metrics:
- Total P&L: $12,345.67
- Win Rate: 65.5%
- Avg Winner: $500
- Avg Loser: -$300
- Sharpe Ratio: 1.25
- Sortino Ratio: 1.85
- Max Drawdown: 12.5%
- Trades Count: 50
```

### 5.3 Console Validation
```
Open F12 → Console tab
Expected: 
- 0 errors (red)
- 0 warnings (yellow)
- Only info/debug messages (gray)
```

---

## Phase 6: Run Orchestrator (30 minutes)

### 6.1 Dry-Run Mode (No Trades)
```bash
python3 algo/algo_orchestrator.py --dry-run

# Expected output:
# ======================================================================
# PHASE 1: DATA FRESHNESS CHECK
#   - price_daily: OK (50K rows, max date: 2026-05-18)
#   - buy_sell_daily: OK (10K rows, max date: 2026-05-18)
#   - stock_scores: OK (500 rows)
#   - technical_data_daily: OK (50K rows)
#   - market_health_daily: OK (250 rows)
#   - trend_template_data: OK (50K rows)
#   - signal_quality_scores: OK (10K rows)
#   Result: PASS - All data fresh
# ======================================================================
# PHASE 2: CIRCUIT BREAKERS
#   - Drawdown check: OK (current -5%)
#   - VIX check: OK (VIX 20)
#   - Market stage: OK (Stage 2)
#   Result: PASS - All circuit breakers clear
# ======================================================================
# PHASE 3: POSITION MONITOR
#   Open positions: 0
#   Result: OK
# ======================================================================
# PHASE 4: EXIT EXECUTION
#   No open positions
#   Result: OK
# ======================================================================
# PHASE 5: SIGNAL GENERATION
#   BUY signals after all filters: 25 candidates
#   After max_positions cap: Take top 10
#   Result: 10 entry candidates ranked
# ======================================================================
# PHASE 6: ENTRY EXECUTION
#   [DRY-RUN] Would execute 10 trades
#   Actual: No trades placed (dry-run mode)
#   Result: OK
# ======================================================================
# PHASE 7: RECONCILIATION
#   Portfolio snapshot created
#   Current positions: 0
#   Current drawdown: -5%
#   Result: OK
# ======================================================================
# ORCHESTRATOR: ALL PHASES PASSED ✓
```

### 6.2 Check Audit Log
```bash
# View execution log in database
psql -U stocks stocks

SELECT 
  phase, 
  status, 
  message, 
  executed_at 
FROM algo_audit_log 
WHERE executed_at > NOW() - INTERVAL '1 hour'
ORDER BY executed_at DESC;

# Expected: 7 rows (one per phase), all with status='completed'
```

---

## Phase 7: Run Integration Tests (20 minutes)

### 7.1 API Contract Tests
```bash
cd webapp/lambda
npm run test:contract

# Expected: All endpoint responses match API_CONTRACT.md
```

### 7.2 Frontend Component Tests
```bash
cd webapp/frontend
npm run test:contracts

# Expected: All components render with correct data structure
```

### 7.3 Database Schema Tests
```bash
cd ..
pytest tests/test_api_contract_compliance.py -v

# Expected: All tables have required columns
```

---

## Phase 8: Performance Baseline (10 minutes)

### 8.1 API Response Times
```bash
# Time 100 requests to each endpoint
time for i in {1..100}; do curl -s http://localhost:3001/api/health > /dev/null; done

# Expected: Each request < 100ms
```

### 8.2 Frontend Load Time
```bash
# In browser DevTools (F12 → Network tab)
Reload the page and check:
- Largest JS chunk: < 500KB
- Largest CSS chunk: < 100KB
- Time to interactive: < 3 seconds
```

### 8.3 Data Pipeline Throughput
```bash
time python3 run-all-loaders.py 2>&1 | tail -5

# Expected: Complete in < 2 hours
# (yfinance and API rate limits will slow down price data)
```

---

## Success Criteria

✅ **You're Production Ready when:**

- [x] Database initializes without errors
- [x] All loaders complete successfully (rate limits OK)
- [x] Data freshness checks pass (max age < 1 day)
- [x] All API endpoints respond with correct schema
- [x] All 30+ frontend pages load without errors
- [x] F12 console is completely clean (0 errors)
- [x] Orchestrator dry-run passes all 7 phases
- [x] Each page shows complete data (not missing columns)
- [x] API response times < 200ms
- [x] Frontend load time < 3 seconds
- [x] Audit log shows successful phase execution

---

## Troubleshooting

### Database Connection Failed
```
Error: could not connect to server
→ Check: psql -U postgres
→ Fix: postgres service might not be running
→ Mac: brew services start postgresql@14
→ Ubuntu: sudo systemctl start postgresql
```

### Loaders Failing with Rate Limit (429)
```
Normal and expected from yfinance/Alpaca
→ Loaders automatically retry with exponential backoff
→ Only fail if ALL attempts fail
→ Check: Is ALPACA_API_KEY set correctly?
```

### API Returns 503 Database Unavailable
```
Error: Service temporarily unavailable - database connection failed
→ Check: psql -U stocks stocks (can you connect?)
→ Fix: python3 init_database.py (reinitialize)
```

### F12 Shows CORS Errors
```
Error: Access to XMLHttpRequest blocked by CORS
→ Check: API running on :3001? (npm start)
→ Check: Frontend running on :5173? (npm run dev)
→ Check: CORS config in webapp/lambda/index.js (should allow localhost:5173)
```

### Orchestrator Halts at Phase 1
```
Error: All critical tables stale (>7 days)
→ Check: Run run-all-loaders.py again
→ Check: Were loaders successful?
→ Check: Do the tables have recent data? (SELECT MAX(date) FROM technical_data_daily)
```

---

## Deploy to Production

Once all tests pass locally:

```bash
# 1. Push to main
git push origin main

# 2. GitHub Actions will automatically:
#    - Run CI tests
#    - Build Lambda functions
#    - Deploy to AWS
#    - Run smoke tests

# 3. Monitor deployment
watch aws lambda get-function --function-name financial-dashboard-api

# 4. Run smoke tests in production
curl https://api.stocks.example.com/api/health
# Expected: {"status":"healthy",...}

# 5. Check frontend on CloudFront
https://stocks.example.com
# Expected: Loads without errors, displays data correctly
```

---

**Estimated Total Time**: 3-4 hours  
**Success Rate**: 95%+ if all prerequisites met  
**Critical Failure Path**: Database connection → all tests fail

---

Need help? Check PRODUCTION_READINESS.md for detailed architecture overview.

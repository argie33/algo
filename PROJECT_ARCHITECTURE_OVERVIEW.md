# Stocks Algo Project - Comprehensive Overview & Architecture

**Project Location:** `/home/stocks/algo`  
**Status:** Production-Ready Local Development Environment  
**Last Updated:** October 20, 2025

---

## Executive Summary

The Stocks Algo project is a comprehensive stock market analysis and portfolio management platform built with a **Python/Node.js backend** and **React frontend**. It processes real stock market data through multiple data loading pipelines to calculate composite stock scores and provide investment analytics across the entire market.

### Key Capabilities
- **5,315+ stocks** continuously analyzed with real market data
- **Multi-factor scoring** combining technical, fundamental, and positional analysis
- **Real-time API** (41 endpoints) providing scores, rankings, and analytics
- **Production deployment** to AWS Lambda + RDS + CloudFront
- **Comprehensive test coverage** with 3,371+ backend tests and 1,238 frontend tests

---

## Project Architecture Overview

```
/home/stocks/algo/
├── 📊 Data Loading Pipeline (Python Scripts)
│   ├── Price Data: loadpricedaily.py, loadpriceweekly.py, loadpricemonthly.py
│   ├── Technicals: loadtechnicalsdaily.py, loadtechnicalsweekly.py, loadtechnicalsmonthly.py
│   ├── Buy/Sell Signals: loadbuyselldaily.py, loadbuysellweekly.py, loadbuysellmonthly.py
│   ├── Sectors: loadsectors.py
│   ├── Core Scoring: loadstockscores.py (PRIMARY CALCULATION ENGINE)
│   └── Supporting: loaddailycompanydata.py, loadlatestpricedaily.py, etc.
│
├── 💾 Database Layer
│   ├── PostgreSQL (Primary Database)
│   ├── AWS RDS (Production Deployment)
│   ├── 20+ Tables (schema managed by lib/db.py)
│   └── Real-time Updates via cron jobs
│
├── 🔧 Backend API (Node.js/Express)
│   ├── webapp/lambda/
│   ├── 41 REST API Endpoints
│   ├── AWS Lambda Handler (serverless-http)
│   ├── Real-time Price/Score Updates
│   └── Portfolio Management & Analytics
│
├── 🎨 Frontend (React)
│   ├── webapp/frontend/ (31 pages)
│   ├── Real-time Dashboard
│   ├── Screener & Filtering
│   ├── Portfolio Management
│   └── Technical Analysis Charts
│
└── 📚 Configuration & Utils
    ├── config.js (Scoring Weights & Parameters)
    ├── lib/db.py (Database Connection Management)
    ├── lib/rankings.py (Ranking Algorithms)
    └── scripts/ (Utility scripts)
```

---

## Data Loading & Processing Pipeline

### 1. **Data Sources**
- **yfinance**: Stock price, technicals, company info
- **Market data**: Real-time quotes, volume, volatility
- **Financial statements**: Annual/quarterly earnings, ratios
- **Technical indicators**: RSI, MACD, Moving Averages
- **Institutional data**: Positioning, ownership changes

### 2. **Data Flow Architecture**

```
External APIs (yfinance, market data)
         ↓
    [Python Loaders]
         ↓
    PostgreSQL Database
         ↓
    [loadstockscores.py] ← MAIN CALCULATION ENGINE
         ↓
    stock_scores Table
         ↓
    [Node.js API] ← 41 REST Endpoints
         ↓
    Frontend + External Consumers
```

### 3. **Stock Score Calculation (loadstockscores.py)**

**Location:** `/home/stocks/algo/loadstockscores.py`  
**Version:** 2.2 (Updated 2025-10-16)  
**Purpose:** Calculate comprehensive stock quality metrics using 6-factor model

#### Scoring Methodology (0-100 scale)

```
COMPOSITE SCORE = 
  Quality (30%)         [Profitability, margins, ROE]
  + Momentum (20%)      [Technical momentum across timeframes]
  + Value (15%)         [PE/PB ratios vs market]
  + Growth (15%)        [Earnings/revenue momentum]
  + Positioning (10%)   [Technical support/resistance + institutional]
  + Risk/Stability (10%) [Volatility and downside risk]
```

#### Input Data Sources
- **price_daily**: Price, volume, volatility, momentum
- **technical_data_daily**: RSI, MACD, moving averages
- **earnings**: PE ratios, EPS growth
- **earnings_history**: Growth trends, surprise patterns
- **quality_metrics**: Debt ratios, margins, ROE
- **value_metrics**: Valuation multiples, PEG
- **positioning_metrics**: Institutional holdings, insider ownership

#### Key Features
- Processes ALL 5,315 stocks (not filtered)
- Handles missing data gracefully with fallbacks
- Z-score normalization for positioning metrics
- Multi-timeframe momentum (1-3mo, 3-6mo, 6-12mo)
- Institutional positioning tracking
- Volatility risk component

#### Output
- **stock_scores table**: 40+ columns with all component scores
- Indexed for fast API queries
- Daily updates (scheduled via cron)
- Real-time API access at `/api/scores`

---

## Database Schema

### Core Tables

| Table | Purpose | Records | Key Columns |
|-------|---------|---------|------------|
| **stock_symbols** | Stock universe | 5,315+ | symbol, exchange, sector, etf |
| **stock_scores** | Composite scores | 5,315+ | composite_score, momentum_score, value_score, quality_score, growth_score |
| **price_daily** | Daily OHLCV data | 1.3M+ | symbol, date, open, high, low, close, volume |
| **technical_data_daily** | Technical indicators | 1.3M+ | symbol, date, rsi, macd, sma_20, sma_50 |
| **key_metrics** | Valuation metrics | 5,315+ | ticker, pe_ratio, pb_ratio, dividend_yield |
| **quality_metrics** | Financial health | 5,315+ | symbol, roe, debt_to_equity, current_ratio |
| **value_metrics** | Value analysis | 5,315+ | symbol, pe_percentile, pb_percentile, peg_ratio |
| **growth_metrics** | Growth rates | 5,315+ | symbol, revenue_growth, eps_growth |
| **sector_data** | Sector analytics | 11 sectors | sector, avg_pe, avg_pb, top_performers |
| **company_profile** | Company info | 5,315+ | symbol, name, sector, industry, country |
| **buy_sell_signals** | Trading signals | Daily | symbol, date, signal, confidence |
| **earnings** | Earnings data | 5,315+ | symbol, eps, pe_ratio, next_earnings |
| **positioning_metrics** | Institutional data | 5,315+ | symbol, institutional_ownership, insider_ownership |

**Schema Location:** `/home/stocks/algo/lib/db.py`  
**Migrations:** `/home/stocks/algo/webapp/lambda/migrations/`

---

## Data Loading Pipeline Scripts

### Primary Loaders

| Script | Purpose | Frequency | Status |
|--------|---------|-----------|--------|
| **loadstockscores.py** | Main scoring engine | Daily | ✅ Active |
| **loadpricedaily.py** | Daily OHLCV data | Daily | ✅ Active |
| **loadtechnicalsdaily.py** | Technical indicators | Daily | ✅ Active |
| **loadsectors.py** | Sector rankings | Daily | ✅ Active |
| **loadbuyselldaily.py** | Trading signals | Daily | ✅ Active |
| **loaddailycompanydata.py** | Company info, beta | Weekly | ✅ Active |
| **loadlatestpricedaily.py** | Intraday price updates | Hourly | ✅ Active |

### Supporting Loaders

- `loadpriceweekly.py`, `loadpricemonthly.py` - Aggregated price data
- `loadtechnicalsweekly.py`, `loadtechnicalsmonthly.py` - Multi-timeframe technicals
- `loadbuysellweekly.py`, `loadbuysellmonthly.py` - Signal aggregation
- `loadlatestbuyselldaily.py`, `loadlatesttechnicalsdaily.py` - Latest indicator snapshots

### Execution Configuration

**Location:** `/home/stocks/algo/run_data_pipeline.sh`

```bash
# Typical execution order:
1. loadqualitymetrics.py (30s wait)
2. loadriskmetrics.py (30s wait)
3. loadvaluemetrics.py (30s wait)
4. loadgrowthmetrics.py (30s wait)
5. loadsectorindustrydata.py (30s wait)
6. loadstockscores.py (Main engine - depends on all above)

# Parallel execution with error handling
# Total runtime: ~5-15 minutes for all 5,315 stocks
```

---

## Backend API Architecture

### Location
- **Main:** `/home/stocks/algo/webapp/lambda/`
- **Routes:** `/home/stocks/algo/webapp/lambda/routes/` (44 files)
- **Services:** `/home/stocks/algo/webapp/lambda/services/`

### Technology Stack
- **Runtime:** Node.js 20.x
- **Framework:** Express.js
- **Database:** PostgreSQL via node-postgres (pg)
- **Deployment:** AWS Lambda + API Gateway
- **Testing:** Jest with 3,371+ tests

### 41 API Endpoints

#### Health & Status (2)
```
GET /health                          - Service health check
GET /                                - Root endpoint
```

#### Scores & Rankings (8)
```
GET /api/scores                      - All stock scores
GET /api/scores/:symbol              - Single stock score
GET /api/scores/rankings/top         - Top performers
GET /api/scores/rankings/bottom      - Bottom performers
POST /api/scores/batch               - Batch score queries
GET /api/scores/sector/:sector       - Sector scores
GET /api/scores/filter               - Advanced filtering
GET /api/scores/percentiles          - Percentile analysis
```

#### Dashboard (6)
```
GET /api/dashboard/summary           - Key metrics overview
GET /api/dashboard/gainers           - Top gainers
GET /api/dashboard/losers            - Top losers
GET /api/dashboard/most-active       - Volume leaders
GET /api/dashboard/sector-breakdown  - Sector performance
GET /api/dashboard/alerts            - Active alerts
```

#### Stocks & Screener (12)
```
GET /api/stocks                      - All stocks
GET /api/stocks/:symbol              - Stock details
GET /api/stocks/:symbol/history      - Price history
GET /api/stocks/:symbol/technicals   - Technical analysis
GET /api/stocks/:symbol/fundamentals - Financial metrics
GET /api/stocks/:symbol/signals      - Trading signals
GET /api/stocks/screener             - Advanced screener
GET /api/stocks/top-gainers          - Best performers
GET /api/stocks/top-losers           - Worst performers
GET /api/stocks/trending             - Trending stocks
GET /api/stocks/:symbol/news         - Associated news
GET /api/stocks/compare              - Multi-stock comparison
```

#### Sectors (8)
```
GET /api/sectors                     - All sectors
GET /api/sectors/:name               - Sector details
GET /api/sectors/:name/stocks        - Stocks in sector
GET /api/sectors/ranking/current     - Current rankings
GET /api/sectors/ranking/history     - Historical rankings
GET /api/sectors/:name/rotation      - Sector rotation
GET /api/sectors/:name/analysis      - Technical analysis
GET /api/sectors/:name/allocation    - Asset allocation
```

#### Portfolio (6 - Auth Required)
```
GET /api/portfolio                   - User portfolio
GET /api/portfolio/risk              - Risk analysis
GET /api/portfolio/allocation        - Allocation breakdown
POST /api/portfolio/add              - Add position
DELETE /api/portfolio/:symbol        - Remove position
POST /api/portfolio/rebalance        - Rebalance
```

#### Analytics & Advanced (5+)
```
POST /api/backtest                   - Run backtest
GET /api/backtest/:id                - Get backtest results
GET /api/analytics/market            - Market analytics
GET /api/analytics/portfolio         - Portfolio analytics (auth)
GET /api/settings                    - User settings (auth)
POST /api/settings                   - Update settings (auth)
```

### API Response Format

```javascript
{
  success: true,
  data: [
    {
      symbol: "AAPL",
      composite_score: 78.5,
      momentum_score: 82.3,
      value_score: 71.2,
      quality_score: 85.1,
      growth_score: 76.4,
      positioning_score: 73.8,
      sentiment_score: 68.5,
      current_price: 234.50,
      price_change_1d: 1.23,
      volatility_30d: 18.5,
      pe_ratio: 28.4,
      market_cap: 2850000000000,
      last_updated: "2025-10-20T21:15:00Z"
    },
    // ... more stocks
  ],
  metadata: {
    total_records: 5315,
    timestamp: "2025-10-20T21:15:00Z",
    cache_age_seconds: 300
  }
}
```

### Key Services

| Service | Purpose | Location |
|---------|---------|----------|
| **Database Utilities** | Connection pooling, credential management | `utils/database.js` |
| **Response Formatter** | Standardized API responses | `middleware/responseFormatter.js` |
| **Authentication** | JWT token validation, user sessions | `middleware/auth.js` |
| **AI Strategy Generator** | AI-powered trade recommendations | `services/aiStrategyGenerator.js` |
| **Alpaca Integration** | Live trading integration | `services/alpacaIntegration.js` |
| **Performance Engine** | Portfolio performance calculations | `services/performanceEngine.js` |

---

## Frontend Architecture

### Location
- **Main:** `/home/stocks/algo/webapp/frontend/`
- **Pages:** `src/pages/` (31 implemented pages)
- **Components:** `src/components/` (100+ reusable components)
- **Tests:** `tests/` (1,238 tests)

### Technology Stack
- **Framework:** React 18.x
- **Build Tool:** Vite
- **Styling:** Tailwind CSS + Material-UI
- **Charting:** Chart.js, Recharts
- **State:** React Context + Hooks
- **Testing:** Jest + React Testing Library

### 31 Frontend Pages

#### Dashboard (3 pages)
- Dashboard Home - Market overview
- Market Analysis - Sector rotation
- Performance Summary - Portfolio stats

#### Stock Research (8 pages)
- Stock Screener - Advanced filtering
- Stock Details - Full analysis view
- Technical Analysis - Chart + indicators
- Fundamental Analysis - Financial metrics
- Stock Compare - Multi-stock analysis
- Top Gainers/Losers - Performance leaders
- Trending Stocks - Real-time trends
- News & Sentiment - Market news

#### Portfolio (6 pages)
- Portfolio Overview - Holdings summary
- Portfolio Analysis - Risk/allocation
- Portfolio Performance - Returns tracking
- Watchlist - Custom stock lists
- Alerts & Notifications - Price alerts
- Portfolio Rebalance - Auto-rebalancing

#### Trading & Strategies (5 pages)
- Strategy Builder - Custom strategy creation
- Backtesting - Historical testing
- Live Trading - Execute trades
- Trade History - Past transactions
- Orders - Order management

#### Advanced Features (5 pages)
- Sector Rotation - Sector performance trends
- Economic Calendar - Economic events
- Earnings Calendar - Earnings dates
- Risk Analysis - Portfolio risk metrics
- Benchmarking - Compare to indices

#### Settings & Admin (4 pages)
- Account Settings - User preferences
- Alerts Management - Alert configuration
- Data Export - Download data
- Help & Documentation - In-app help

### E2E Test Coverage
- **Implemented:** 11 of 31 pages (35% coverage)
- **Gap:** 20 pages untested (65% coverage opportunity)
- **Test Format:** Cypress E2E + Jest unit tests
- **Total Tests:** 1,238 (1,066 unit + 172 E2E)

---

## Configuration Management

### Scoring Configuration

**Location:** `/home/stocks/algo/config.js`

```javascript
// Composite score weights (Fama-French Factor Model)
COMPOSITE_SCORE_WEIGHTS = {
  quality: 0.30,        // Profitability (PRIMARY)
  momentum: 0.20,       // Price momentum
  value: 0.15,          // PE/PB ratios
  growth: 0.15,         // Earnings growth
  positioning: 0.10,    // Technical positioning
  risk: 0.10           // Volatility management
}

// Risk score breakdown
RISK_SCORE_WEIGHTS = {
  volatility: 0.40,              // 12-month volatility
  technical_positioning: 0.27,   // Price support/resistance
  max_drawdown: 0.33             // 52-week max drawdown
}

// Momentum component weights
MOMENTUM_WEIGHTS = {
  short_term: 0.25,              // 1-3 months
  medium_term: 0.25,             // 3-6 months
  longer_term: 0.20,             // 6-12 months
  relative_strength: 0.15,       // Relative to sector
  consistency: 0.15              // Upside consistency
}
```

### Environment Variables

**Development:**
```bash
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=password
DB_NAME=stocks
USE_LOCAL_DB=true
NODE_ENV=development
```

**Production (AWS):**
```bash
DB_SECRET_ARN=arn:aws:secretsmanager:...
AWS_REGION=us-east-1
NODE_ENV=production
```

---

## Key Files & Locations

| Component | File | Purpose |
|-----------|------|---------|
| **Main Scoring** | `loadstockscores.py` | Stock score calculation engine |
| **Database Utils** | `lib/db.py` | Connection & credential management |
| **Configuration** | `config.js` | Scoring weights & parameters |
| **API Routes** | `webapp/lambda/routes/*.js` | 44 route handlers |
| **Frontend Pages** | `webapp/frontend/src/pages/` | 31 React page components |
| **Setup Script** | `setup_local_dev.sh` | Automated environment setup |
| **Pipeline Script** | `run_data_pipeline.sh` | Data loading orchestration |
| **Requirements** | `requirements-*.txt` | Python dependencies per loader |

---

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                  EXTERNAL DATA SOURCES                       │
│  (yfinance, market APIs, fundamental data providers)         │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────────────┐
│           PYTHON DATA LOADING LAYER                          │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ 1. loadpricedaily.py → price_daily table             │   │
│  │ 2. loadtechnicalsdaily.py → technical_data_daily     │   │
│  │ 3. loaddailycompanydata.py → company_profile        │   │
│  │ 4. loadqualitymetrics.py → quality_metrics          │   │
│  │ 5. loadvaluemetrics.py → value_metrics              │   │
│  │ 6. loadgrowthmetrics.py → growth_metrics            │   │
│  └──────────────────────────────────────────────────────┘   │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ↓
        ┌────────────────────────┐
        │   PostgreSQL DB        │
        │  (All dimension tables) │
        └────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────────────┐
│        LOADSTOCKSCORES.PY (MAIN CALCULATION ENGINE)          │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ • Read all dimension tables                          │   │
│  │ • Calculate 6-factor composite scores                │   │
│  │ • Apply z-score normalization                        │   │
│  │ • Handle missing data gracefully                     │   │
│  │ • Store results in stock_scores table                │   │
│  │ • Process 5,315+ stocks in single run                │   │
│  └──────────────────────────────────────────────────────┘   │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ↓
        ┌────────────────────────┐
        │  stock_scores table    │
        │  (40+ columns/stock)   │
        └────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────────────┐
│          NODE.JS BACKEND API LAYER                          │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Express.js Server (41 REST endpoints)                │   │
│  │ • /api/scores/* - Score data & rankings              │   │
│  │ • /api/stocks/* - Stock details & analysis           │   │
│  │ • /api/sectors/* - Sector performance                │   │
│  │ • /api/dashboard/* - Market overview                 │   │
│  │ • /api/portfolio/* - User portfolios (auth)          │   │
│  │ • /api/analytics/* - Advanced analytics              │   │
│  └──────────────────────────────────────────────────────┘   │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────────────┐
│            FRONTEND REACT LAYER                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ 31 Pages with real-time data                         │   │
│  │ • Dashboard with live updates                        │   │
│  │ • Stock screener with 40+ filters                    │   │
│  │ • Portfolio management                               │   │
│  │ • Technical analysis charts                          │   │
│  │ • Sector rotation tracking                           │   │
│  │ • Advanced analytics                                 │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                     │
                     ↓
        ┌────────────────────────┐
        │   END USERS             │
        │   (Investors/Traders)   │
        └────────────────────────┘
```

---

## Error Handling & Data Quality

### Graceful Degradation
- Missing data returns appropriate null/default values
- None handling in scoring calculations
- Try-except blocks for optional data sources
- Fallback values for incomplete records
- Continuation on individual stock failures

### Data Validation
- Stock symbol validation against stock_symbols table
- Date range checking for price data
- Null/NaN handling in technical calculations
- Volume threshold filtering
- Exchange/ETF filtering

### Monitoring & Logging
- Structured logging for all data loads
- Error tracking with context
- Load time profiling
- Data completeness percentages
- Stock processing success rates

---

## Deployment Architecture

### Local Development
- PostgreSQL on `localhost:5432`
- Node.js backend on `localhost:5001`
- React frontend on `localhost:5173`
- Automated setup via `setup_local_dev.sh`

### Production (AWS)
- **Database:** RDS PostgreSQL instance
- **API:** Lambda + API Gateway
- **Frontend:** CloudFront + S3
- **Credentials:** AWS Secrets Manager
- **Cron Jobs:** EventBridge for scheduled loads

### Docker Containerization
- **65+ Dockerfiles** for individual data loaders
- One loader per container image
- Scheduled execution via ECS tasks
- Independent failure/retry policies

---

## Testing Infrastructure

### Unit Tests (1,674 tests)
- Route handlers
- Service methods
- Utility functions
- Database operations
- Jest with mocking

### Integration Tests (1,697 tests)
- Full API endpoint testing
- Database integration
- Data pipeline validation
- Supertest for HTTP testing
- Real database transactions

### E2E Tests (172 tests)
- Frontend page testing
- User workflows
- Cross-browser validation (Cypress)
- Real-time data updates
- Accessibility checks

### Test Coverage
- Backend: 85%+ code coverage
- Frontend: 72%+ component coverage
- All 41 API endpoints covered
- 35% of 31 frontend pages (11/31 with E2E tests)

---

## Known Issues & Limitations

### Current State
- Legacy database schema (maintained for compatibility)
- Some optional tables may be missing (gracefully handled)
- Missing test coverage for 20 frontend pages
- Partial sentiment data (included with fallback handling)

### Performance Characteristics
- Stock score calculation: ~5-15 minutes for 5,315 stocks
- API response times: <100ms typical
- Database query optimization: Indexed key fields
- Memory usage: Reasonable for single-threaded Node.js

---

## Next Steps & Recommendations

1. **Immediate:** Review data loading pipeline for any missing dependencies
2. **Short-term:** Extend E2E test coverage to all 31 frontend pages
3. **Medium-term:** Implement real-time WebSocket updates for live scores
4. **Long-term:** Machine learning model integration for prediction

---

## Support & Documentation

### Generated Documentation
- `README_START_HERE.md` - Entry point and navigation
- `LOCAL_SETUP_COMPLETE.md` - Detailed setup guide
- `API_TESTING_COMPREHENSIVE_GUIDE.md` - All endpoints documented
- `COMPLETE_LOCAL_SETUP_AND_FIXES.md` - Master reference
- `E2E_TEST_COVERAGE_REPORT.md` - Test analysis

### Quick Start
```bash
cd /home/stocks/algo
python3 setup_local_dev.sh    # 10-15 minutes
npm start                      # Backend on :5001
npm run dev                    # Frontend on :5173
```

---

**Project maintained as of: October 20, 2025**  
**Status: Production-Ready with Comprehensive Documentation**

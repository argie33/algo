# Stocks Algo Project - API Landscape & Architecture Summary

**Last Updated:** October 21, 2025  
**Project Status:** Production-Ready  
**Repository:** `/home/stocks/algo`

---

## EXECUTIVE SUMMARY

The Stocks Algo project is a **comprehensive stock market analysis and portfolio management platform** with:

- **757+ REST API endpoints** across 45 route files
- **73,603 lines of API route code** (Node.js/Express)
- **5,315+ stocks** continuously analyzed with multi-factor scoring
- **41+ core API resource types** (scores, stocks, sectors, portfolio, technical analysis, etc.)
- **Python data pipeline** with 20+ loaders feeding real data to PostgreSQL
- **Production deployment** to AWS Lambda + RDS + CloudFront
- **3,371+ backend tests** with 85%+ code coverage

---

## PROJECT STRUCTURE

```
/home/stocks/algo/
├── 📊 Data Layer (Python)
│   ├── loadstockscores.py          [PRIMARY: 6-factor stock scoring engine]
│   ├── loadpricedaily.py           [OHLCV data collection]
│   ├── loadtechnicalsdaily.py      [Technical indicators: RSI, MACD, SMA]
│   ├── loadfundamentalmetrics.py   [Financial metrics: PE, ROE, debt ratios]
│   ├── loadgrowthmetrics.py        [Revenue/EPS growth rates]
│   ├── loadvaluemetrics.py         [Valuation multiples: PE, PB, PEG]
│   ├── loadbuyselldaily.py         [Trading signals]
│   ├── loadsectors.py              [Sector rankings and rotation]
│   ├── loaddailycompanydata.py     [Company profiles, beta, exchange]
│   ├── loadeconomicdata.py         [FRED economic indicators]
│   ├── loadsentiment.py            [Market sentiment indicators]
│   ├── loadnews.py                 [News data aggregation]
│   └── 20+ supporting loaders
│
├── 💾 Database Layer (PostgreSQL)
│   ├── stock_symbols              [5,315+ stocks universe]
│   ├── stock_scores               [Composite scoring results - 40+ cols]
│   ├── price_daily                [1.3M+ daily OHLCV records]
│   ├── technical_data_daily       [1.3M+ technical indicator records]
│   ├── key_metrics                [Valuation data]
│   ├── quality_metrics            [Financial health metrics]
│   ├── growth_metrics             [Growth rates]
│   ├── value_metrics              [Value ratios]
│   ├── sector_data                [11 sectors + analysis]
│   ├── company_profile            [Company info + fundamentals]
│   ├── buy_sell_signals           [Daily trading signals]
│   ├── earnings                   [Earnings data]
│   ├── positioning_metrics        [Institutional holdings]
│   ├── economic_data              [FRED indicators]
│   └── 10+ portfolio/user tables
│
├── 🔧 Backend API (Node.js/Express)
│   ├── webapp/lambda/index.js     [Main Express server + Lambda handler]
│   ├── webapp/lambda/routes/      [45 route files with 757+ endpoints]
│   ├── webapp/lambda/middleware/  [Auth, CORS, error handling, response formatting]
│   ├── webapp/lambda/utils/       [Database, route helpers, auth]
│   ├── webapp/lambda/services/    [Business logic: AI, Alpaca integration, performance]
│   └── webapp/lambda/tests/       [3,371+ tests across unit/integration/E2E]
│
├── 🎨 Frontend (React)
│   ├── webapp/frontend/src/       [31 pages, 100+ components]
│   └── webapp/frontend/tests/     [1,238+ tests]
│
└── 📚 Configuration
    ├── config.js                 [Scoring weights, parameters]
    ├── .env.local               [Local dev credentials]
    └── Dockerfile.* (65+ files) [Individual loader containers]
```

---

## TECHNOLOGY STACK

### Backend
| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| **Runtime** | Node.js | 20.x | Lambda/Express runtime |
| **Framework** | Express.js | 4.18.2 | REST API framework |
| **Database** | PostgreSQL | 13+ | Primary data store |
| **ORM/Query** | node-postgres (pg) | 8.11.3 | Direct SQL queries |
| **Authentication** | JWT + AWS Cognito | 9.0.2 | User auth + SSO |
| **Security** | Helmet | 7.1.0 | HTTP security headers |
| **CORS** | cors | 2.8.5 | Cross-origin handling |
| **Logging** | Morgan | 1.10.0 | HTTP request logging |
| **Deployment** | serverless-http | 3.2.0 | Lambda HTTP adapter |
| **WebSocket** | ws | 8.18.3 | Real-time updates |
| **AWS SDK** | @aws-sdk | 3.x | Secrets Manager, SES |
| **Testing** | Jest | 29.7.0 | Unit & integration tests |
| **Code Quality** | ESLint + Prettier | Latest | Linting & formatting |

### Data Processing
| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| **Language** | Python | 3.9+ | Data loading scripts |
| **Data Fetch** | yfinance | Latest | Market data collection |
| **Database** | psycopg2 | 2.9+ | PostgreSQL driver |
| **Data Science** | pandas, numpy | Latest | Data processing & analysis |
| **Scheduling** | AWS EventBridge | - | Cron-like scheduling |
| **Deployment** | Docker | 20.x+ | Container packaging |

### Frontend
| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Framework** | React 18.x | UI framework |
| **Build Tool** | Vite | Build & dev server |
| **Styling** | Tailwind CSS + Material-UI | CSS framework |
| **Charting** | Chart.js, Recharts | Data visualization |
| **State** | React Context + Hooks | State management |
| **Testing** | Jest + React Testing Library | Component testing |

---

## API LANDSCAPE - 757 ENDPOINTS ACROSS 45 RESOURCES

### Core API Organization (app.use() routes in index.js)

```
/api/
├── /alerts (Endpoints: 12+)                    [Price/portfolio alerts]
├── /analytics (Endpoints: 15+)                 [Advanced analytics, reports]
├── /analysts (Endpoints: 8+)                   [Analyst ratings, recommendations]
├── /auth (Endpoints: 10+)                      [Login, logout, OAuth, MFA]
├── /backtest (Endpoints: 8+)                   [Strategy backtesting]
├── /calendar (Endpoints: 6+)                   [Earnings, economic calendar]
├── /commodities (Endpoints: 10+)               [Commodity prices, analysis]
├── /dashboard (Endpoints: 12+)                 [Portfolio dashboard, widgets]
├── /diagnostics (Endpoints: 5+)                [System health, debugging]
├── /dividend (Endpoints: 10+)                  [Dividend data, history, yields]
├── /earnings (Endpoints: 10+)                  [Earnings data, estimates, surprise]
├── /economic (Endpoints: 15+)                  [FRED indicators, economic data]
├── /etf (Endpoints: 12+)                       [ETF data, holdings, performance]
├── /financials (Endpoints: 15+)                [Financial statements, ratios]
├── /health (Endpoints: 5+)                     [Service health, status]
├── /insider (Endpoints: 8+)                    [Insider trading, ownership]
├── /live-data (Endpoints: 8+)                  [Real-time streaming data]
├── /market (Endpoints: 30+)                    [Market overview, breadth, breadth indicators]
├── /metrics (Endpoints: 20+)                   [Company metrics, custom calculations]
├── /news (Endpoints: 10+)                      [News aggregation, sentiment]
├── /orders (Endpoints: 12+)                    [Order management, execution]
├── /performance (Endpoints: 10+)               [Portfolio performance tracking]
├── /portfolio (Endpoints: 20+)                 [Holdings, rebalancing, analysis]
├── /positioning (Endpoints: 8+)                [Institutional positioning]
├── /price (Endpoints: 12+)                     [Price data, history, conversion]
├── /recommendations (Endpoints: 8+)            [Stock recommendations, scoring]
├── /research (Endpoints: 6+)                   [Research tools, data]
├── /risk (Endpoints: 15+)                      [Risk metrics, VaR, volatility]
├── /scores (Endpoints: 15+)                    [Stock scores, rankings, filtering]
├── /screener (Endpoints: 12+)                  [Advanced screening with 40+ filters]
├── /sectors (Endpoints: 15+)                   [Sector data, rotation, analysis]
├── /sentiment (Endpoints: 10+)                 [Market sentiment indicators]
├── /settings (Endpoints: 10+)                  [User settings, preferences]
├── /signals (Endpoints: 12+)                   [Trading signals, buy/sell]
├── /stocks (Endpoints: 40+)                    [Main stock data, details, search]
├── /strategy-builder (Endpoints: 10+)          [Custom strategy creation]
├── /technical (Endpoints: 20+)                 [Technical indicators, patterns]
├── /trades (Endpoints: 15+)                    [Trade history, execution]
├── /trading (Endpoints: 20+)                   [Trading platform features]
├── /user (Endpoints: 10+)                      [User profile, preferences]
├── /watchlist (Endpoints: 12+)                 [Custom watchlists]
├── /websocket (Endpoints: 8+)                  [WebSocket connections]
└── /debug (Endpoints: 8+)                      [Development debugging]
```

### High-Level API Endpoint Categories

#### 1. STOCK & SCORE DATA (80+ endpoints)
```javascript
GET  /api/scores                    // All stock scores (5,315+)
GET  /api/scores/:symbol            // Single stock score
POST /api/scores/batch              // Batch queries
GET  /api/scores/rankings/top       // Top performers
GET  /api/scores/rankings/bottom    // Bottom performers
GET  /api/scores/filter             // Advanced filtering with 40+ criteria
GET  /api/stocks                    // All stocks with full data
GET  /api/stocks/:symbol            // Stock details & company profile
GET  /api/stocks/:symbol/history    // Price history (daily/weekly/monthly)
GET  /api/stocks/:symbol/technicals // Technical analysis & indicators
GET  /api/stocks/:symbol/fundamentals // Financial metrics
GET  /api/stocks/:symbol/signals    // Trading signals
GET  /api/stocks/compare            // Multi-stock comparison
GET  /api/stocks/screener           // Advanced screener (40+ filters)
GET  /api/stocks/top-gainers        // Best daily performers
GET  /api/stocks/top-losers         // Worst daily performers
GET  /api/stocks/trending           // Trending stocks (volume, volatility)
```

#### 2. PORTFOLIO & TRADING (40+ endpoints)
```javascript
GET    /api/portfolio               // User portfolio holdings
GET    /api/portfolio/risk          // Portfolio risk analysis (VaR, Sharpe)
GET    /api/portfolio/allocation    // Asset allocation breakdown
POST   /api/portfolio/add           // Add position
DELETE /api/portfolio/:symbol       // Remove position
POST   /api/portfolio/rebalance     // Auto-rebalance
GET    /api/trades                  // Trade history
POST   /api/trades/execute          // Execute trade
PUT    /api/trades/:id              // Modify order
DELETE /api/trades/:id              // Cancel order
GET    /api/orders                  // Order status
POST   /api/orders                  // Create order
PUT    /api/orders/:id              // Update order
DELETE /api/orders/:id              // Cancel order
```

#### 3. TECHNICAL ANALYSIS (20+ endpoints)
```javascript
GET /api/technical/:symbol          // Technical indicators
GET /api/technical/:symbol/rsi      // RSI analysis
GET /api/technical/:symbol/macd     // MACD analysis
GET /api/technical/:symbol/moving-averages // SMA/EMA
GET /api/technical/:symbol/bollinger        // Bollinger Bands
GET /api/technical/:symbol/patterns         // Chart pattern recognition
GET /api/technical/:symbol/support-resistance // S/R levels
GET /api/technical/:symbol/volume-profile    // Volume analysis
```

#### 4. FUNDAMENTALS & FINANCIALS (20+ endpoints)
```javascript
GET /api/financials/:symbol                 // Financial statements
GET /api/financials/:symbol/income          // Income statement
GET /api/financials/:symbol/balance-sheet   // Balance sheet
GET /api/financials/:symbol/cash-flow       // Cash flow statement
GET /api/financials/:symbol/ratios          // Financial ratios
GET /api/metrics/:symbol                    // Key metrics
GET /api/earnings/:symbol                   // Earnings data
GET /api/earnings/:symbol/history           // Earnings history
GET /api/earnings/:symbol/estimates         // Earnings estimates
```

#### 5. SECTORS & MARKET (30+ endpoints)
```javascript
GET /api/sectors                    // All sectors
GET /api/sectors/:name              // Sector details
GET /api/sectors/:name/stocks       // Stocks in sector
GET /api/sectors/ranking/current    // Sector rankings
GET /api/sectors/:name/rotation     // Sector rotation data
GET /api/market/overview            // Market overview
GET /api/market/breadth             // Market breadth indicators
GET /api/market/sectors/performance // Sector performance
GET /api/market/industries          // Industry performance
GET /api/market/mcclellan-oscillator // Technical breadth
GET /api/market/volatility          // VIX, volatility indicators
```

#### 6. ECONOMIC DATA (15+ endpoints)
```javascript
GET /api/economic/indicators        // FRED economic indicators
GET /api/economic/gdp               // GDP data
GET /api/economic/inflation         // CPI, inflation metrics
GET /api/economic/unemployment      // Unemployment data
GET /api/economic/interest-rates    // Interest rate data
GET /api/economic/credit-spreads    // Credit spread analysis
GET /api/economic/leading-indicators // Leading economic indicators
```

#### 7. ALERTS & NOTIFICATIONS (12+ endpoints)
```javascript
GET  /api/alerts                    // User alerts list
POST /api/alerts                    // Create alert
PUT  /api/alerts/:id                // Update alert
DELETE /api/alerts/:id              // Delete alert
GET  /api/alerts/:symbol            // Price alerts for symbol
GET  /api/alerts/portfolio          // Portfolio alerts
```

#### 8. DASHBOARD & ANALYTICS (20+ endpoints)
```javascript
GET /api/dashboard                  // Dashboard summary
GET /api/dashboard/summary          // Key metrics overview
GET /api/dashboard/gainers          // Top gainers
GET /api/dashboard/losers           // Top losers
GET /api/dashboard/most-active      // Volume leaders
GET /api/dashboard/sector-breakdown // Sector performance
GET /api/analytics/market           // Market analytics
GET /api/analytics/portfolio        // Portfolio analytics
GET /api/analytics/backtest         // Backtest results
```

#### 9. SENTIMENT & NEWS (10+ endpoints)
```javascript
GET /api/sentiment                  // Market sentiment
GET /api/sentiment/history          // Sentiment history
GET /api/news/:symbol               // News for stock
GET /api/news/market                // Market news
GET /api/analysts/:symbol           // Analyst ratings
GET /api/analysts/:symbol/ratings   // Rating distribution
```

#### 10. USER & SETTINGS (10+ endpoints)
```javascript
GET  /api/user/profile              // User profile
PUT  /api/user/profile              // Update profile
GET  /api/settings                  // User settings
POST /api/settings                  // Update settings
GET  /api/user/preferences          // Display preferences
GET  /api/watchlist                 // Watchlists
POST /api/watchlist                 // Create watchlist
PUT  /api/watchlist/:id             // Update watchlist
```

---

## DATABASE SCHEMA

### Core Tables (20+ total)

| Table | Purpose | Records | Key Columns | Last Updated |
|-------|---------|---------|------------|--------------|
| **stock_symbols** | Stock universe | 5,315+ | symbol, exchange, sector, etf | Daily |
| **stock_scores** | Composite scores | 5,315+ | composite_score, momentum_score, value_score, quality_score, growth_score, positioning_score, sentiment_score, stability_score | Daily |
| **price_daily** | Daily OHLCV | 1.3M+ | symbol, date, open, high, low, close, volume, adjusted_close | Daily |
| **technical_data_daily** | Technical indicators | 1.3M+ | symbol, date, rsi, macd, sma_20, sma_50, ema_12, ema_26 | Daily |
| **key_metrics** | Valuation metrics | 5,315+ | ticker, pe_ratio, pb_ratio, ps_ratio, dividend_yield | Weekly |
| **quality_metrics** | Financial health | 5,315+ | symbol, roe, debt_to_equity, current_ratio, gross_margin | Weekly |
| **value_metrics** | Value analysis | 5,315+ | symbol, pe_percentile, pb_percentile, peg_ratio, fcf_yield | Weekly |
| **growth_metrics** | Growth rates | 5,315+ | symbol, revenue_growth, eps_growth, fcf_growth | Weekly |
| **sector_data** | Sector analytics | 11 sectors | sector, avg_pe, avg_pb, top_performers | Daily |
| **company_profile** | Company info | 5,315+ | symbol, name, sector, industry, country, employees | Monthly |
| **buy_sell_signals** | Trading signals | Variable | symbol, date, signal, confidence, strength | Daily |
| **earnings** | Earnings data | 5,315+ | symbol, eps, pe_ratio, next_earnings, fiscal_year | As announced |
| **positioning_metrics** | Institutional data | 5,315+ | symbol, institutional_ownership, insider_ownership, floating_shares | Monthly |
| **portfolio_holdings** | User positions | Variable | user_id, symbol, quantity, average_cost, current_price | Real-time |
| **watchlists** | User watchlists | Variable | user_id, name, created_at | Real-time |
| **watchlist_items** | Watchlist stocks | Variable | watchlist_id, symbol | Real-time |
| **users** | User accounts | Variable | id, email, password_hash, created_at | Real-time |
| **alerts** | Price alerts | Variable | user_id, symbol, target_price, alert_type | Real-time |
| **economic_data** | FRED indicators | 1M+ | indicator_code, date, value, units | Daily |
| **news** | News articles | Variable | id, symbol, title, content, source, timestamp | Real-time |

### Schema Design Notes
- All stock-level data indexed on `symbol` for O(1) lookups
- Time-series data indexed on `symbol, date` for efficient range queries
- User data indexed on `user_id` for session-based queries
- JSONB columns for flexible metadata storage (value_inputs, quality_factors, etc.)
- Constraints enforce data integrity (foreign keys, unique constraints)
- Database location: `/home/stocks/algo/lib/db.py`

---

## API SCORING CALCULATION ENGINE

### Stock Scores Model (loadstockscores.py)

**6-Factor Composite Score Calculation (0-100 scale)**

```
COMPOSITE SCORE = 
  Quality (30%)         [ROE, margins, debt ratios, profitability]
  + Momentum (20%)      [RSI, MACD, price momentum across timeframes]
  + Value (15%)         [PE/PB ratios vs market percentiles]
  + Growth (15%)        [Earnings/revenue growth rates]
  + Positioning (10%)   [Technical support/resistance, institutional holdings]
  + Risk/Stability (10%)  [Volatility, downside risk, price stability]
```

### Component Scores (all 0-100)

| Score | Definition | Data Sources | Weighting |
|-------|-----------|--------------|-----------|
| **Composite** | Overall stock quality | All components | Primary ranking |
| **Momentum** | Price trend strength | RSI, MACD, ROC, price momentum | 20% of composite |
| **Value** | Valuation attractiveness | PE percentile, PB, PEG, FCF yield | 15% of composite |
| **Quality** | Business quality | ROE, margins, debt ratio, current ratio | 30% of composite |
| **Growth** | Growth trajectory | Revenue growth, EPS growth, FCF growth | 15% of composite |
| **Positioning** | Technical position | Support/resistance, institutional holdings | 10% of composite |
| **Sentiment** | Market sentiment | Analyst ratings, news sentiment, insider activity | 5-10% |
| **Stability** | Downside protection | Volatility, beta, max drawdown, Sharpe ratio | 5-10% |

### Input Data Processing

**Data Sources:**
- `price_daily` - OHLCV data, volume, volatility, daily momentum
- `technical_data_daily` - RSI, MACD, moving averages
- `earnings` - PE ratios, EPS, next earnings dates
- `earnings_history` - Historical EPS, earnings surprises
- `quality_metrics` - Debt ratios, margins, ROE
- `value_metrics` - Valuation multiples
- `positioning_metrics` - Institutional/insider ownership
- `sentiment_data` - Analyst ratings, news sentiment

**Handling Missing Data:**
- Z-score normalization for positioning metrics
- Graceful fallbacks for missing optional data
- All 5,315+ stocks processed (not filtered)
- Individual stock failures don't block batch processing

### Multi-Timeframe Momentum Breakdown

```javascript
momentum_score = {
  short_term: 25%        // 1-3 month momentum (ROC_20d)
  medium_term: 25%       // 3-6 month momentum (ROC_60d)
  long_term: 20%         // 6-12 month momentum (ROC_120d)
  relative_strength: 15% // RSI + relative to sector
  consistency: 15%       // Upside consistency indicator
}
```

---

## DATA LOADING PIPELINE

### Loader Scripts (20+ total)

**Primary Loaders (Daily)**
| Script | Purpose | Runtime | Data Source |
|--------|---------|---------|------------|
| loadpricedaily.py | Daily OHLCV | 2-5 min | yfinance |
| loadtechnicalsdaily.py | Technical indicators | 2-5 min | yfinance |
| loadbuyselldaily.py | Trading signals | 2-3 min | Technical analysis |
| loadlatestpricedaily.py | Intraday updates | 1-2 min | yfinance |
| loadstockscores.py | Scoring engine | 5-15 min | All dimension tables |

**Supporting Loaders (Weekly/Monthly)**
| Script | Purpose | Frequency |
|--------|---------|-----------|
| loaddailycompanydata.py | Company info, beta | Weekly |
| loadfundamentalmetrics.py | Financial metrics | Weekly |
| loadqualitymetrics.py | Quality scores | Weekly |
| loadvaluemetrics.py | Value metrics | Weekly |
| loadgrowthmetrics.py | Growth rates | Weekly |
| loadsectors.py | Sector rankings | Daily |
| loadeconomicdata.py | FRED indicators | Daily |
| loadsentiment.py | Market sentiment | Daily |
| loadnews.py | News aggregation | Real-time |

**Execution Flow**
```
1. loadqualitymetrics.py (30s wait)
2. loadriskmetrics.py (30s wait)
3. loadvaluemetrics.py (30s wait)
4. loadgrowthmetrics.py (30s wait)
5. loadsectorindustrydata.py (30s wait)
6. loadstockscores.py (Main engine - depends on all above)

Total Runtime: 5-15 minutes for 5,315+ stocks
```

### Docker Containerization
- 65+ Dockerfiles for individual loaders
- One loader per container image
- Scheduled execution via AWS ECS tasks
- Independent failure/retry policies
- Enables parallel execution

---

## RESPONSE FORMAT

### Standard API Response

```javascript
{
  success: true,
  data: [
    {
      // Stock/score object fields
      symbol: "AAPL",
      composite_score: 78.5,
      momentum_score: 82.3,
      value_score: 71.2,
      quality_score: 85.1,
      growth_score: 76.4,
      positioning_score: 73.8,
      sentiment_score: 68.5,
      stability_score: 75.2,
      
      // Price data
      current_price: 234.50,
      price_change_1d: 1.23,
      price_change_5d: 3.45,
      price_change_30d: -2.10,
      volatility_30d: 18.5,
      
      // Fundamental data
      pe_ratio: 28.4,
      pb_ratio: 42.8,
      dividend_yield: 0.43,
      market_cap: 2850000000000,
      
      // Technical data
      rsi: 65.2,
      macd: 0.85,
      sma_20: 232.10,
      sma_50: 228.50,
      
      // Metadata
      volume_avg_30d: 52150000,
      last_updated: "2025-10-20T21:15:00Z",
      score_date: "2025-10-20"
    }
  ],
  metadata: {
    total_records: 5315,
    timestamp: "2025-10-20T21:15:00Z",
    cache_age_seconds: 300,
    request_id: "req-12345"
  }
}
```

### Error Response

```javascript
{
  success: false,
  error: "Error message here",
  code: "ERROR_CODE",
  message: "User-friendly error message",
  details: {
    // Additional error context
  },
  timestamp: "2025-10-20T21:15:00Z"
}
```

---

## AUTHENTICATION & SECURITY

### Authentication Methods
- **JWT Tokens** - Bearer token in Authorization header
- **AWS Cognito** - OAuth 2.0 / OpenID Connect integration
- **API Keys** - X-Api-Key header for service-to-service
- **Session Cookies** - Browser-based authentication

### Protected Routes
- `/api/portfolio/*` - User portfolio (auth required)
- `/api/user/*` - User profile (auth required)
- `/api/settings/*` - User settings (auth required)
- `/api/alerts/*` - User alerts (auth required)
- `/api/trades/execute` - Trade execution (auth required)

### Security Features
- **CORS** - Specific allowed origins (CloudFront, localhost)
- **HTTPS/TLS** - SSL/TLS in production
- **Rate Limiting** - API Gateway handles throttling
- **Helmet** - HTTP security headers (HSTS, CSP, etc.)
- **Password Hashing** - bcrypt for credential storage
- **CSRF Protection** - SameSite cookie policies

---

## KEY SERVICES & BUSINESS LOGIC

### Service Files

| Service | Purpose | Location |
|---------|---------|----------|
| **AI Strategy Generator** | AI-powered trade recommendations | `services/aiStrategyGenerator.js` |
| **Alpaca Integration** | Live trading via Alpaca API | `services/alpacaIntegration.js` |
| **Performance Engine** | Portfolio performance calculations | `services/performanceEngine.js` |
| **Database Utilities** | Connection pooling, queries | `utils/database.js` |
| **Response Formatter** | Standardized API responses | `middleware/responseFormatter.js` |
| **Authentication** | JWT validation, sessions | `middleware/auth.js` |
| **Error Handler** | Centralized error handling | `middleware/errorHandler.js` |

---

## DEPLOYMENT ARCHITECTURE

### Development Environment
- PostgreSQL on `localhost:5432`
- Node.js backend on `localhost:5001` or `localhost:3000`
- React frontend on `localhost:5173`
- Automated setup via `setup_local_dev.sh` (10-15 minutes)

### Production Environment (AWS)
- **Database**: AWS RDS PostgreSQL
- **API**: AWS Lambda + API Gateway
- **Frontend**: CloudFront + S3
- **Secrets**: AWS Secrets Manager (DB credentials)
- **Scheduling**: AWS EventBridge (cron jobs)
- **Container Registry**: Amazon ECR (Docker images)

### Configuration
- `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` - Database connection
- `DB_SECRET_ARN` - AWS Secrets Manager ARN (production)
- `USE_LOCAL_DB` - Local development flag
- `NODE_ENV` - Environment (development/production/test)
- `FRONTEND_URL` - CORS origin configuration
- `AWS_REGION` - AWS region for Secrets Manager

---

## TESTING & CODE QUALITY

### Test Coverage
- **Backend Tests**: 3,371+ tests
  - Unit tests: 1,674+ (Jest)
  - Integration tests: 1,697+ (real database)
  - E2E tests: 172+ (Cypress/Playwright)
- **Frontend Tests**: 1,238+ tests
  - Unit tests: 1,066+ (Jest + React Testing Library)
  - E2E tests: 172+ (Cypress)
- **Code Coverage**: 85%+ backend, 72%+ frontend

### Test Types
- **Unit Tests** - Individual functions/methods
- **Integration Tests** - Database + API endpoints
- **E2E Tests** - Frontend page flows
- **Security Tests** - Auth, encryption, vulnerabilities
- **Performance Tests** - Load testing, response times
- **Contract Tests** - API contract validation

### Test Commands (npm scripts)
```bash
npm run test                    # Full test suite
npm run test:unit              # Unit tests only
npm run test:integration       # Integration tests
npm run test:e2e               # End-to-end tests
npm run test:security          # Security tests
npm run test:api               # API endpoint tests
npm run test:database          # Database tests
npm run test:financial         # Financial calculations
npm run lint                   # ESLint code quality
npm run lint:fix               # Auto-fix linting issues
npm run format                 # Prettier code formatting
```

---

## CONFIGURATION MANAGEMENT

### Scoring Weights (config.js)

```javascript
COMPOSITE_SCORE_WEIGHTS = {
  quality: 0.30,         // Business quality (PRIMARY)
  momentum: 0.20,        // Price momentum
  value: 0.15,           // Valuation ratios
  growth: 0.15,          // Earnings growth
  positioning: 0.10,     // Technical positioning
  risk: 0.10             // Volatility/risk
}

MOMENTUM_WEIGHTS = {
  short_term: 0.25,      // 1-3 months
  medium_term: 0.25,     // 3-6 months
  long_term: 0.20,       // 6-12 months
  relative_strength: 0.15, // Sector relative
  consistency: 0.15      // Upside consistency
}

RISK_SCORE_WEIGHTS = {
  volatility: 0.40,              // 12-month volatility
  technical_positioning: 0.27,   // Support/resistance
  max_drawdown: 0.33             // 52-week max drawdown
}
```

---

## FILE LOCATIONS & KEY REFERENCE

| Component | File Path | Lines of Code |
|-----------|-----------|---------------|
| **Main API Server** | `/home/stocks/algo/webapp/lambda/index.js` | 700+ |
| **Route Files** | `/home/stocks/algo/webapp/lambda/routes/*.js` | 73,603 total |
| **Stock Scoring** | `/home/stocks/algo/loadstockscores.py` | 500+ |
| **Database Utils** | `/home/stocks/algo/lib/db.py` | 200+ |
| **Configuration** | `/home/stocks/algo/config.js` | 150+ |
| **Middleware** | `/home/stocks/algo/webapp/lambda/middleware/` | 200+ |
| **Services** | `/home/stocks/algo/webapp/lambda/services/` | 300+ |
| **Tests** | `/home/stocks/algo/webapp/lambda/tests/` | 3,371+ |
| **Frontend Pages** | `/home/stocks/algo/webapp/frontend/src/pages/` | 31 pages |
| **Frontend Components** | `/home/stocks/algo/webapp/frontend/src/components/` | 100+ components |

---

## QUICK START COMMANDS

```bash
# Local Development Setup
cd /home/stocks/algo
bash setup_local_dev.sh          # 10-15 minutes

# Start Backend
npm start                        # Runs on :5001 or :3000

# Start Frontend
cd webapp/frontend
npm run dev                      # Runs on :5173

# Run Tests
npm run test                     # All tests
npm run test:api                # API tests only
npm run lint                    # Code quality check

# Run Data Pipeline
bash run_data_pipeline.sh        # Load all data

# Deploy to AWS
npm run predeploy               # Pre-deployment checks
npm run deploy-package          # Package and deploy to Lambda
```

---

## SUMMARY & STATISTICS

| Metric | Value |
|--------|-------|
| **Total API Endpoints** | 757+ |
| **Route Files** | 45 |
| **Route Files LOC** | 73,603 |
| **Python Loaders** | 20+ |
| **Database Tables** | 20+ |
| **Stocks Analyzed** | 5,315+ |
| **Backend Tests** | 3,371+ |
| **Frontend Tests** | 1,238+ |
| **Frontend Pages** | 31 |
| **Frontend Components** | 100+ |
| **Code Coverage** | 85%+ backend, 72%+ frontend |
| **NPM Dependencies** | 10+ core |
| **Python Dependencies** | 5+ core |
| **Docker Containers** | 65+ (loaders) |
| **Production Deployment** | AWS Lambda + RDS + CloudFront |

---

## NEXT STEPS FOR MCP SERVER IMPLEMENTATION

To build an MCP server that exposes these APIs, consider:

1. **Resource Definition**: Create MCP resources for each of the 45 API endpoint groups
2. **Tool Creation**: Generate tools for common operations:
   - Stock scoring & ranking queries
   - Portfolio management operations
   - Technical analysis indicators
   - Screener/filtering operations
   - Historical data retrieval
3. **Sampling Strategy**: Focus first on highest-value endpoints:
   - `/api/scores` - Core scoring system
   - `/api/stocks` - Stock details & search
   - `/api/portfolio` - Portfolio management
   - `/api/technical` - Technical analysis
   - `/api/sectors` - Market structure
4. **Authentication**: Implement JWT token handling in MCP server
5. **Caching**: Implement response caching for frequently accessed data
6. **Rate Limiting**: Respect API Gateway rate limits
7. **Error Handling**: Comprehensive error responses per MCP spec

---

**Document Generated:** 2025-10-21  
**Project Status:** Production-Ready  
**Last API Update:** 2025-10-21 12:10 UTC

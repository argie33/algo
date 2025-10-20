# Project Structure Overview: Institutional-Grade Financial Trading Platform

## Project Type & Architecture
**Monorepo**: Multi-domain financial platform combining web app, mobile app, data pipeline, and serverless backend.

**Core Technology Stack**:
- **Frontend**: React 18.3.1 with Vite (bundler), TypeScript support
- **Backend**: Node.js/Express with AWS Lambda (serverless)
- **Database**: PostgreSQL (pg client, SSL-enabled)
- **Mobile**: React Native 0.72.4 (iOS/Android)
- **Data Pipeline**: Python 3 with 52+ loader scripts
- **Testing**: Jest (backend), Vitest (frontend), Playwright (E2E)
- **Cloud**: AWS (Lambda, Cognito, Secrets Manager, ECS/ECR)
- **Authentication**: JWT + AWS Cognito + 2FA/MFA support

---

## Project Directory Structure

```
/home/stocks/algo/
├── webapp/                           # Main web application (monorepo root)
│   ├── frontend/                     # React SPA with Vite
│   │   ├── src/
│   │   │   ├── pages/               # React components for pages
│   │   │   ├── components/          # Reusable UI components
│   │   │   ├── services/            # API client services
│   │   │   ├── hooks/               # Custom React hooks
│   │   │   ├── contexts/            # React context providers
│   │   │   ├── config/              # Configuration files
│   │   │   ├── utils/               # Utility functions
│   │   │   ├── tests/               # Frontend tests (124 test files)
│   │   │   │   ├── unit/            # Unit tests
│   │   │   │   ├── component/       # Component tests
│   │   │   │   ├── integration/     # Integration tests
│   │   │   │   ├── contracts/       # API contract tests
│   │   │   │   └── screenshots/     # Visual regression tests
│   │   │   └── main.jsx             # Entry point
│   │   ├── public/                  # Static assets
│   │   ├── vite.config.js           # Vite configuration
│   │   ├── vitest.config.js         # Vitest configuration
│   │   ├── playwright.config.js     # E2E testing (multiple configs)
│   │   └── package.json
│   │
│   ├── lambda/                      # AWS Lambda backend
│   │   ├── routes/                  # API route handlers (38 route files)
│   │   │   ├── stocks.js            # Stock data endpoints
│   │   │   ├── portfolio.js         # Portfolio management (206KB)
│   │   │   ├── market.js            # Market data (199KB)
│   │   │   ├── scores.js            # Stock scoring system
│   │   │   ├── sectors.js           # Sector analysis
│   │   │   ├── financials.js        # Financial statements (86KB)
│   │   │   ├── dashboard.js         # Dashboard endpoints (63KB)
│   │   │   ├── news.js              # News/sentiment (63KB)
│   │   │   ├── analytics.js         # Analytics endpoints (63KB)
│   │   │   ├── auth.js              # Authentication endpoints
│   │   │   └── [33 more routes]
│   │   │
│   │   ├── middleware/              # Express middleware
│   │   │   ├── auth.js              # Authentication/authorization
│   │   │   ├── errorHandler.js      # Error handling
│   │   │   ├── responseFormatter.js # Response formatting
│   │   │   └── validation.js        # Request validation
│   │   │
│   │   ├── utils/                   # Utility services (22 files)
│   │   │   ├── database.js          # PostgreSQL connection + pooling
│   │   │   ├── factorScoring.js     # Multi-factor scoring engine
│   │   │   ├── performanceMonitor.js # Performance metrics
│   │   │   ├── alpacaService.js     # Alpaca API integration
│   │   │   ├── apiKeyService.js     # API key management
│   │   │   ├── liveDataManager.js   # Real-time data (60KB)
│   │   │   ├── riskEngine.js        # Risk calculations (60KB)
│   │   │   ├── schemaValidator.js   # Request validation (56KB)
│   │   │   ├── newsAnalyzer.js      # Sentiment/news analysis
│   │   │   ├── alertSystem.js       # Alert management
│   │   │   └── [12 more utilities]
│   │   │
│   │   ├── tests/                   # Backend tests (37 directories)
│   │   │   ├── unit/                # Unit tests
│   │   │   ├── integration/         # Integration tests
│   │   │   │   ├── alpaca/          # Alpaca API tests
│   │   │   │   ├── analytics/       # Analytics endpoints
│   │   │   │   ├── auth/            # Authentication tests
│   │   │   │   ├── database/        # Database tests
│   │   │   │   ├── errors/          # Error handling tests
│   │   │   │   ├── infrastructure/  # Infrastructure tests
│   │   │   │   ├── middleware/      # Middleware tests
│   │   │   │   ├── routes/          # Route tests
│   │   │   │   ├── services/        # Service tests
│   │   │   │   ├── streaming/       # SSE/WebSocket tests
│   │   │   │   ├── utils/           # Utility tests
│   │   │   │   └── websocket/       # WebSocket tests
│   │   │   ├── security/            # Security tests
│   │   │   ├── performance/         # Performance benchmarks
│   │   │   ├── contract/            # Contract tests
│   │   │   ├── ci/                  # CI/CD tests
│   │   │   └── setup/               # Test setup/fixtures
│   │   │
│   │   ├── index.js                 # Lambda handler entry point
│   │   ├── server.js                # Express server configuration
│   │   ├── package.json
│   │   └── jest.unit.config.js      # Jest configuration
│   │
│   ├── dev-server.js                # Local development server
│   ├── package.json                 # Workspace package.json
│   └── .env.template                # Environment template
│
├── mobile-app/                      # React Native mobile application
│   ├── src/
│   ├── ios/                         # iOS native code
│   ├── android/                     # Android native code
│   └── package.json
│
├── lib/                             # Node.js utilities library
├── loaders/                         # Python data loader scripts (private)
├── test-utils/                      # Testing utilities
├── scripts/                         # Build/deployment scripts
│
├── Data Loaders (Python) - 52 scripts:
│   ├── loadstockscores.py           # Stock multi-factor scoring
│   ├── loadbuyselldaily.py          # Buy/sell signals (87KB)
│   ├── loadbuysellmonthly.py        # Monthly signals (69KB)
│   ├── loadbuysellweekly.py         # Weekly signals (69KB)
│   ├── loadgrowthmetrics.py         # Growth calculations (38KB)
│   ├── loadvaluemetrics.py          # Value calculations (32KB)
│   ├── loadmarket.py                # Market data (31KB)
│   ├── loadinfo.py                  # Company info (46KB)
│   ├── loadtechnicalsdaily.py       # Technical indicators (38KB)
│   ├── loadearningsmetrics.py       # Earnings data (32KB)
│   ├── loadfeargreed.py             # Fear/greed index
│   ├── loadnaaim.py                 # NAAIM positioning
│   ├── loadnews.py                  # News/sentiment
│   ├── loadquarterlybalancesheet.py # Q balance sheets
│   ├── loadquarterlycashflow.py     # Q cash flows
│   ├── loadquarterlyincomestatement.py # Q income statements
│   ├── loadannualbalancesheet.py    # Annual balance sheets
│   ├── loadannualcashflow.py        # Annual cash flows
│   ├── loadannualincomestatement.py # Annual income statements
│   ├── loadpricedaily.py            # Daily prices
│   ├── loadpricemonthly.py          # Monthly prices
│   ├── loadpriceweekly.py           # Weekly prices
│   ├── loadlatesttechnicalsdaily.py # Latest technicals
│   ├── loaddailycompanydata.py      # Company data
│   ├── loadanalystupgradedowngrade.py # Analyst ratings
│   ├── loadsectordata.py            # Sector data
│   ├── loadsectorbenchmarks.py      # Sector benchmarks
│   ├── loadstocksymbols.py          # Symbol reference
│   ├── loadcalendar.py              # Calendar events
│   ├── loadaaiidata.py              # AAII sentiment
│   ├── loadmomentummetrics.py       # Momentum metrics
│   ├── loadqualitymetrics.py        # Quality metrics
│   ├── loadriskmetrics.py           # Risk metrics
│   └── [22 more loaders]
│
├── config.js                        # JavaScript scoring config
├── config.py                        # Python scoring config
├── portfolio_management.py          # Portfolio calculations
├── swingtrader.py                   # Swing trading logic
│
├── Docker Configuration:
│   └── Dockerfile.* (60+ files)    # One per data loader + services
│
├── Infrastructure:
│   ├── template-webapp.yml          # CloudFormation template
│   ├── template-webapp-lambda.yml   # Lambda-specific template
│   ├── template-app-stocks.yml      # App cluster template
│   ├── template-app-ecs-tasks.yml   # ECS task definitions
│   ├── deploy-lambda.sh             # Lambda deployment script
│   ├── deploy-serverless.sh         # Serverless Framework deployment
│   └── update-config.sh             # Configuration update script
│
└── Documentation:
    ├── SCORING_CODE_LOCATIONS.md
    ├── STOCK_SCORING_ANALYSIS.md
    ├── TEST_COMPLETION_REPORT.md
    └── [Various test reports]

```

---

## Frontend Architecture (React + Vite)

### Key Features
- **Build Tool**: Vite 7.1.3 (ES module-based bundler)
- **Testing**: Vitest + Playwright for E2E
- **UI Framework**: Material-UI (MUI) 5.18.0
- **State Management**: React Query (@tanstack/react-query) 5.85.5
- **Charts**: Recharts 3.1.2
- **HTTP Client**: Axios 1.11.0
- **Authentication**: AWS Amplify 5.3.27

### Frontend Test Structure
- **124 test files** across unit, component, integration, and contract tests
- **Playwright E2E**: Multi-config setup (CI, critical flows, visual, accessibility, performance, mobile)
- **Vitest**: Unit + component testing with coverage tracking
- **Testing Library**: React Testing Library for component testing

### Main Pages
- Dashboard.jsx (75KB) - Main dashboard
- Portfolio.jsx (122KB) - Portfolio management
- MarketOverview.jsx (76KB) - Market data view
- RealTimeDashboard.jsx (68KB)
- Backtest.jsx (84KB) - Backtesting interface
- FinancialData.jsx - Financial statements
- EarningsCalendar.jsx - Earnings calendar
- EconomicModeling.jsx - Economic forecasts
- And 10+ more pages

---

## Backend Architecture (Express + Lambda)

### Server Architecture
- **Framework**: Express 4.18.2 (Node.js)
- **Deployment**: AWS Lambda via serverless-http
- **HTTP Server**: Native Node.js HTTP module with WebSocket support
- **Security**: Helmet 7.1.0 (security headers), CORS 2.8.5
- **Logging**: Morgan 1.10.0 (HTTP logging)
- **Authentication**: JWT + AWS Cognito with @aws-sdk clients

### API Endpoints (38 Route Files)
**Primary Routes**:
- `/api/stocks/` - Stock data and fundamentals
- `/api/portfolio/` - Portfolio management
- `/api/market/` - Market aggregates
- `/api/scores/` - Stock scores and ratings
- `/api/sectors/` - Sector analysis
- `/api/financials/` - Financial statements
- `/api/analytics/` - Analytics/backtesting
- `/api/dashboard/` - Dashboard data
- `/api/news/` - News and sentiment
- `/api/auth/` - Authentication
- `/api/orders/` - Order management (Alpaca integration)
- `/api/alerts/` - Alert system
- `/api/economic/` - Economic data
- `/api/calendar/` - Economic/earnings calendar
- `/api/price/` - Price data (daily/weekly/monthly)
- `/api/sentiment/` - Sentiment analysis
- `/api/signals/` - Trading signals
- `/api/screening/` - Stock screening
- `/api/websocket/` - WebSocket management
- And 19+ more routes

### Core Services/Utilities
**Data & Analysis**:
- `factorScoring.js` - Multi-factor scoring (momentum, growth, value, quality, risk)
- `riskEngine.js` (60KB) - Risk calculations (VaR, Sharpe ratio, drawdown)
- `schemaValidator.js` (56KB) - Request/response validation
- `alpacaService.js` - Alpaca trading API integration
- `liveDataManager.js` (60KB) - Real-time market data streaming

**System Services**:
- `database.js` - PostgreSQL connection pooling with SSL
- `performanceMonitor.js` - Request/response metrics
- `logger.js` - Structured logging
- `errorTracker.js` - Error tracking
- `newsAnalyzer.js` - News sentiment
- `newsStreamProcessor.js` - WebSocket news streaming
- `alertSystem.js` - Alert management (28KB)
- `apiKeyService.js` (48KB) - API key management
- `sentimentEngine.js` - Market sentiment
- `tradingModeHelper.js` - Trading mode configurations
- `backtestStore.js` - Backtest result storage

**Middleware**:
- `auth.js` - JWT verification + Cognito integration
- `errorHandler.js` - Global error handling
- `responseFormatter.js` - Standard response formatting
- `validation.js` - Request validation

---

## Database Architecture

### Technology
- **Type**: PostgreSQL (pg 8.11.3)
- **Connection**: Pooling with AWS Secrets Manager integration
- **SSL**: Configurable via DB_SSL environment variable
- **Configuration**: Via environment variables or AWS Secrets Manager (ARN-based)

### Key Tables (Inferred from loaders)
- `stock_prices` / `price_daily`, `price_weekly`, `price_monthly` - Price history
- `stock_symbols` - Symbol reference data
- `technical_data_daily` - Technical indicators (RSI, MACD, MA)
- `earnings` - Earnings data with PE ratios
- `earnings_history` - Earnings trends
- `company_info` - Company metadata
- `sector_data` - Sector benchmarks
- `balance_sheets`, `cash_flows`, `income_statements` - Financial statements
- `buy_sell_signals` - Buy/sell signals (daily/weekly/monthly)
- `stock_scores` - Calculated scores (momentum, growth, value, quality, risk, positioning, sentiment)
- `news` - News articles with sentiment
- `alerts` - User alerts
- `portfolios`, `positions` - Portfolio tracking
- `technical_analysis` - Advanced technical indicators
- `calendar_events` - Economic/earnings calendar
- And more...

### Configuration
- **Connection String**: PostgreSQL URI with user/password/SSL
- **Secrets Management**: AWS Secrets Manager (DB_SECRET_ARN environment variable)
- **Query Caching**: In-memory cache with 30-second TTL for frequent queries
- **SSL**: Dynamic SSL configuration (DB_SSL=true/false)

---

## Testing Framework Setup

### Frontend Testing (Vitest + Playwright)
**Test Structure**:
```
src/tests/
├── unit/               # Unit tests (hooks, utilities)
├── component/          # Component tests (React components)
├── integration/        # Integration tests
├── contracts/          # API contract tests
└── screenshots/        # Visual regression tests
```

**Test Scripts**:
- `npm run test` - Unit + component tests
- `npm run test:unit` - Unit tests only
- `npm run test:component` - Component tests
- `npm run test:integration` - Integration tests
- `npm run test:coverage` - Coverage reports
- `npm run test:e2e` - Playwright E2E tests
- `npm run test:e2e:critical` - Critical flow tests
- `npm run test:e2e:visual` - Visual regression
- `npm run test:e2e:a11y` - Accessibility tests
- `npm run test:e2e:perf` - Performance tests
- `npm run test:e2e:mobile` - Mobile device tests

**Configuration**:
- **Vitest**: Testing Library integration with jsdom
- **Playwright**: 7 config files (ci.js, simple.js, cross-browser.js, firefox.js, webkit.js, demo.js, validation.js)
- **Code Coverage**: HTML + LCOV reporters

### Backend Testing (Jest)
**Test Structure**:
```
tests/
├── unit/              # Unit tests (30% of total)
├── integration/       # Integration tests (60% of total)
│   ├── alpaca/        # Alpaca API tests
│   ├── analytics/
│   ├── auth/
│   ├── database/
│   ├── errors/
│   ├── infrastructure/
│   ├── middleware/
│   ├── routes/
│   ├── services/
│   ├── streaming/
│   ├── utils/
│   └── websocket/
├── security/          # Security tests
├── performance/       # Performance benchmarks
├── contract/          # API contract tests
└── ci/               # CI/CD tests
```

**Test Scripts**:
- `npm run test` - Full test suite with coverage
- `npm run test:unit` - Unit tests only
- `npm run test:integration` - Integration tests
- `npm run test:ci` - CI/CD tests
- `npm run test:financial` - Financial calculations
- `npm run test:security` - Security tests
- `npm run test:api` - API endpoint tests
- `npm run test:performance` - Performance tests
- `npm run test:contract` - Contract tests

**Configuration**:
- **Jest**: 29.7.0 with supertest for HTTP testing
- **Mocking**: Jest mocks for database, external APIs
- **Coverage**: Text + HTML + LCOV reporters
- **Timeout**: 15000ms for integration tests

---

## Data Pipeline Architecture

### Python Data Loaders
- **52 total loader scripts** for various data sources
- **Trigger**: Docker containers with scheduled execution
- **Configuration**: Centralized in `config.py` with weights and thresholds
- **Database Output**: PostgreSQL with transactional integrity

### Scoring System
**Multi-Factor Model** (0-100 scale):
1. **Momentum** (20-25%): RSI, MACD, moving averages, price momentum
2. **Trend** (15%): Multi-timeframe trend analysis
3. **Growth** (15-19%): Earnings growth, stability
4. **Value** (15%): PE ratio, PEG-adjusted valuation
5. **Quality** (30%): Profitability, margins, ROE, financial stability (PRIMARY)
6. **Risk** (10%): Volatility, downside risk, drawdown
7. **Positioning** (10%): Institutional holdings, technical levels
8. **Sentiment** (5%): Analyst ratings, market sentiment

### Data Sources
- **Price Data**: Historical OHLCV data (daily/weekly/monthly)
- **Fundamentals**: Financial statements, earnings data, ratios
- **Technicals**: Indicators, oscillators, moving averages
- **Sentiment**: News, analyst ratings, institutional positioning
- **Macro**: Economic data, market indices, commodities
- **Alternative**: Fear/Greed index, NAAIM positioning, AAII sentiment

---

## Environment Configuration

### Environment Variables
```
# Database
DB_HOST=localhost
DB_PORT=5432
DB_NAME=stocks
DB_USER=postgres
DB_PASSWORD=password
DB_SSL=false
DB_SECRET_ARN=arn:aws:secretsmanager:... (for AWS)

# AWS
AWS_REGION=us-east-1
WEBAPP_AWS_REGION=us-east-1

# API
VITE_API_URL=http://localhost:5001 (frontend)
NODE_ENV=development|production

# Authentication
JWT_SECRET=...
COGNITO_CLIENT_ID=...
COGNITO_USER_POOL_ID=...
```

### Environment Files
- `.env` - Default environment
- `.env.local` - Local development (git-ignored)
- `.env.dev`, `.env.development` - Development mode
- `.env.staging` - Staging environment
- `.env.production` - Production environment
- `.env.test` - Testing environment

---

## Deployment Architecture

### Docker Infrastructure
- **60+ Dockerfiles**: One per loader + services
- **Images**: Node.js + Python runtime containers
- **Registries**: Amazon ECR
- **Orchestration**: AWS ECS with task definitions

### CloudFormation Templates
- `template-webapp.yml` - Web application infrastructure
- `template-webapp-lambda.yml` - Lambda-specific configuration
- `template-app-stocks.yml` - App cluster setup
- `template-app-ecs-tasks.yml` - ECS task definitions (128KB)

### Deployment Scripts
- `deploy-lambda.sh` - Lambda function deployment
- `deploy-serverless.sh` - Serverless Framework deployment
- `EMERGENCY_DEPLOY.sh` - Emergency hotfix deployment
- `update-config.sh` - Configuration updates

---

## Key Technologies Summary

### Frontend Stack
- React 18.3.1
- Vite 7.1.3
- TypeScript support
- Material-UI 5.18.0
- Recharts 3.1.2
- Axios 1.11.0
- AWS Amplify 5.3.27
- Vitest 3.2.4
- Playwright 1.55.0

### Backend Stack
- Node.js (>=18.0.0)
- Express 4.18.2 / 5.1.0
- PostgreSQL 8.11.3
- AWS SDK v3 (@aws-sdk/*)
- Jest 29.7.0
- Supertest 6.3.4
- JWT + AWS Cognito auth
- WebSocket (ws 8.18.3)

### Data Pipeline
- Python 3
- PostgreSQL (pg adapter)
- Multiple financial data APIs
- Docker containerization

### Infrastructure
- AWS Lambda (serverless)
- AWS ECS (container orchestration)
- AWS Cognito (authentication)
- AWS Secrets Manager (credential management)
- AWS CloudFormation (IaC)
- Amazon RDS (PostgreSQL)

---

## Project Metrics

- **Frontend Files**: 13 major directories
- **Frontend Tests**: 124 test files
- **Backend Routes**: 38 endpoint files
- **Backend Services**: 22 utility modules
- **Backend Tests**: 37 test directories
- **Data Loaders**: 52 Python scripts
- **Dockerfiles**: 60+ container definitions
- **Package Dependencies**: 
  - Frontend: 34 direct dependencies
  - Backend: 18 direct dependencies
  - Mobile: 16 direct dependencies

---

## Architecture Pattern

**Microservices + Monorepo Hybrid**:
- Monorepo structure for shared code
- Serverless backend (AWS Lambda)
- Separate frontend SPA (React)
- Mobile app (React Native)
- Scheduled batch processors (Docker containers)
- PostgreSQL as central data store

**Design Principles**:
- **Separation of Concerns**: Routes, middleware, services, utilities
- **Factor-Based Analysis**: Multi-factor scoring model
- **Real-Time Processing**: WebSocket support + streaming
- **Scalability**: Lambda auto-scaling + connection pooling
- **Enterprise Security**: JWT + Cognito + 2FA + Helmet CSP
- **Observability**: Structured logging + error tracking
- **Testing**: Comprehensive unit, integration, E2E coverage


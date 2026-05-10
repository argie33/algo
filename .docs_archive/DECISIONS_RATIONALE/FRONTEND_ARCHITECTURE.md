# Frontend Architecture Guide

**Last Updated:** 2026-05-08  
**Status:** Single consolidated frontend, dead code removed

## Overview

We run **ONE real frontend**: `webapp/frontend/` (React + Vite, 40 pages).  
Everything else is removed or archived.

```
webapp/
├── frontend/                    ← THE ONLY FRONTEND (React, Vite)
│   ├── src/
│   │   ├── pages/              ← 40 pages (26 dashboard + 14 marketing)
│   │   ├── components/         ← Reusable UI components
│   │   ├── hooks/              ← API hooks (useDataApi, useApiCall, etc.)
│   │   ├── services/           ← Auth (Cognito), token manager, etc.
│   │   └── tests/              ← Unit, integration, e2e tests
│   ├── vite.config.js          ← Build configuration
│   ├── package.json            ← Dependencies
│   └── .env.example            ← Template (deploy creates actual .env)
├── lambda/                      ← Express backend API
│   ├── routes/                 ← 27 REST endpoints
│   ├── middleware/             ← Auth, logging, error handling
│   ├── utils/                  ← Database, Alpaca, caching
│   └── index.js                ← Express app + route registration
└── [DELETED] spa/              ← Removed: empty stub file
    [DELETED] node_modules/     ← Root-level (moved to frontend/)
```

---

## What Each Directory Does

### `webapp/frontend/src/pages/` (40 pages total)

**Dashboard Pages (26 — Used by authenticated users)**
- Portfolio: PortfolioDashboard, Portfolio, TradeTracker
- Market: MarketOverview, MarketsHealth, EconomicDashboard, SectorAnalysis
- Trading: TradingSignals, SwingCandidates, BacktestResults, ManualTrades
- Analysis: DeepValueStocks, ScoresDashboard, MetricsDashboard, FinancialData
- Admin: ServiceHealth, Settings, HedgeHelper
- Research: ResearchScreener, EarningsCalendar, CompanyDetail, StockDetail

**Marketing Pages (14 — Public site, no auth required)**
- Home, About, Contact, Terms, Privacy
- Firm, OurTeam, MissionValues, ResearchInsights
- InvestmentTools, WealthManagement, ArticleDetail
- ⚠️ FAQs, Markets, Commodities imported but **never routed** → removed (May 8)

**Route Structure:**
- `/` redirects to `/dashboard` (authenticated) or `/home` (public)
- Public pages: `/home`, `/about`, `/terms`, etc.
- Dashboard pages: `/dashboard/*` (auth required via Cognito)
- Wildcard fallback catches unmapped URLs → shows 404 or home

### `webapp/frontend/src/components/`

**UI Components** (`ui/`)
- Button, Input, Card, Badge, Alert, Select, Tabs, Slider, Progress
- Built with TailwindCSS + shadcn/ui patterns

**Feature Components**
- Charts: HistoricalPriceChart, MarketIndicators, Volatility, etc.
- Trading: PortfolioOptimizer, TradeTracker, TradingSignals
- Analysis: EconomicModeling, EarningsCalendar, SectorAnalysisByIndustry
- Marketing: HeroSection, FeatureGrid, PromoBanner, CTASection

**Auth Components** (`auth/`)
- LoginForm, RegisterForm, MFAChallenge, SessionWarningDialog
- ProtectedRoute, AuthModal, ConfirmationForm, ResetPasswordForm

### `webapp/frontend/src/hooks/` (API Integration)

**Core Hooks:**
- `useDataApi.js` — Main hook for all API calls
  - Endpoints: sectors, industries, signals, prices, optimization, sentiment, scores
  - Supports caching, error handling, loading states
- `useApiCall.js` — Generic HTTP wrapper
- `useApiQuery.js` — Tanstack React Query integration
- Others: useDevelopmentMode, useWindowSize, etc.

**Key Design:**
- Hooks use `VITE_API_URL` environment variable (set at deploy time)
- No hardcoded API endpoints
- All URLs dynamically constructed: `/api/sectors`, `/api/signals/list`, etc.
- Uses axios with interceptors for Cognito tokens

### `webapp/lambda/` (Backend API)

**Route Files (27 total, all wired):**
```
algo.js, backtests.js, commodities.js, contact.js, diagnostics.js, earnings.js,
economic.js, financials.js, health.js, industries.js, manual-trades.js, market.js,
meanReversionSignals.js, optimization.js, portfolio.js, prices.js, rangeSignals.js,
scores.js, sectors.js, sentiment.js, signalFilters.js, signals.js, status.js,
stocks.js, strategies.js, trades.js, user.js
```

**Registration in index.js (line 37-60):**
```javascript
const sectorsRoutes = require("./routes/sectors");
...
app.use("/api/sectors", cacheMiddleware(60), sectorsRoutes);
app.use("/api/signals", cacheMiddleware(15), signalsRoutes);
```

**Key Endpoints Used by Frontend:**
1. `GET /api/sectors?limit=20` — Sector list + rankings
2. `GET /api/industries` — Industries dropdown
3. `GET /api/scores/stockscores?limit=10&offset=0` — Stock scores with filtering
4. `GET /api/signals/list?timeframe=daily&limit=100` — Trading signals
5. `GET /api/sectors/trend/sector/{sector}?days=90` — Sector trend chart
6. `GET /api/optimization/analysis` — Portfolio optimization
7. `GET /api/sentiment/history` — Market sentiment
8. `GET /api/price/history/{symbol}?days=365` — Price history

---

## Deployment Flow

### 1. Build Phase (deploy-webapp.yml)
```
npm install → vite build → dist/ (optimized bundles)
```

**Key:** Deploy workflow creates `.env` dynamically from AWS outputs:
```bash
VITE_API_URL=https://{api-gateway-url}/
VITE_COGNITO_USER_POOL_ID={from-aws}
VITE_COGNITO_CLIENT_ID={from-aws}
... (5 more Cognito vars)
```

Frontend `.env.*` files are **templates only** — never used in prod.

### 2. Deploy Phase (CloudFormation)
```
CloudFormation (template-webapp.yml)
  ↓
  ├─ Lambda API (webapp/lambda/index.js)
  ├─ S3 bucket (stocks-webapp-frontend-{env}-{account})
  ├─ CloudFront CDN (d1copuy2oqlazx.cloudfront.net)
  └─ API Gateway (REST API origin)

CloudFront routes requests:
  /api/* → API Gateway → Lambda
  /* → S3 (static frontend)
```

### 3. Frontend Deployment
```bash
aws s3 sync dist/ s3://stocks-webapp-frontend-prod-{account}/ --delete
cloudfront create-invalidation --distribution-id ... --paths "/*"
```

---

## Environment Variables

### Root Level
- `.env.example` — Template (committed to git)
- `.env.local` — Local dev secrets (git ignored, has DB creds + API keys)

### Frontend
- Created at deploy time by workflow (no .env files in repo)
- Local dev: Copy `.env.example` to `.env.local` if needed

### Lambda
- `.env.local` — Local dev (DB_HOST, DB_USER, etc.)
- `.env.example` — Template for reference
- Production: Uses AWS Secrets Manager + environment variables (no .env file)

---

## Known Limitations & Design Decisions

| Issue | Why | Impact |
|-------|-----|--------|
| RDS publicly accessible | Quick dev iteration | Fixed before prod |
| Paper trading only | Safety first | Alpaca sandbox mode |
| Lambda not in VPC | Simpler setup, cost | Using direct internet route |
| No A/B testing framework | Not yet needed | Can add later |

---

## Common Tasks

### Add a New Dashboard Page
1. Create file: `webapp/frontend/src/pages/MyNewPage.jsx`
2. Import in App.jsx: `import MyNewPage from './pages/MyNewPage'`
3. Add route: `<Route path="/my-new-page" element={<MyNewPage />} />`
4. Add to nav menu if needed

### Add a New API Endpoint
1. Create route file: `webapp/lambda/routes/myfeature.js`
2. Export router: `module.exports = router;`
3. Register in index.js: `app.use('/api/myfeature', cacheMiddleware(60), myfeatureRoutes);`
4. Frontend calls: `api.get('/api/myfeature?param=value')`

### Add a New Component
1. Create: `webapp/frontend/src/components/MyComponent.jsx`
2. Import in any page: `import MyComponent from '../components/MyComponent'`
3. Use: `<MyComponent prop="value" />`

### Test Locally
```bash
# Terminal 1: Backend
cd webapp/lambda
node index.js  # or npm start if script exists

# Terminal 2: Frontend
cd webapp/frontend
npm run dev  # http://localhost:5173

# Use .env.local for DB + Cognito config
```

---

## Architecture Principles

✅ **DO:**
- Keep frontend and backend code separate
- Use environment variables for all config (API_URL, Cognito IDs, etc.)
- Register all routes explicitly in index.js
- Use REST patterns: `/api/resource`, `/api/resource/:id`, not `/api/action`
- Cache frequently-accessed data (sectors: 60s, signals: 15s, etc.)

❌ **DON'T:**
- Hardcode API URLs in components
- Create duplicate frontends (spa/, demo/, etc.)
- Leave unused pages/components (remove or route them)
- Mix .env files at different levels without documenting which is used
- Commit secrets or `.env.local` to git

---

## Cleanup Done (May 8, 2026)

| Item | Reason | Status |
|------|--------|--------|
| `webapp/spa/` | Empty stub, not deployed | **Deleted** |
| FAQs.jsx, Markets.jsx, Commodities.jsx | Never routed/used | **Deleted** |
| `webapp/frontend/.env.*` | Deploy creates them | **Deleted** |
| `.env.development`, `.env.production`, `.env.staging`, `.env.test` (root) | Redundant | **Deleted** |
| `webapp/lambda/.env.test` | Not used | **Deleted** |
| `webapp/lambda/.env.example` | Created from `.env.production.example` | **Added** |

---

## Next Steps

1. **Verify endpoints work** — Test `/api/signals/list` and `/api/sectors/trend/sector/Technology`
2. **Monitor frontend** — Check for broken links or console errors after cleanup
3. **Document API response contracts** — Add to API_REFERENCE.md
4. **Consider: Consolidate marketing & dashboard** — Currently two separate UIs; could be one

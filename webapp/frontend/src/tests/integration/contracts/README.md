# Frontend-Backend Contract Tests

Contract tests validate that frontend components can consume real backend API responses correctly.

## Purpose

These tests catch integration bugs like:
- ✅ API key display bug (Settings expected `data.apiKeys` but backend returns `data.data`)
- ✅ Health endpoint inconsistency (missing `success` field)
- ✅ WebSocket parameter validation

## Comprehensive Test Coverage

### Core API Endpoints
- **api-endpoints.contract.test.jsx** - Major API endpoints (health, stocks, market, calendar, sentiment, etc.)
- **additional-endpoints.contract.test.jsx** - Extended coverage (watchlist, analytics, news, risk, screener, backtest)

### Authentication & Security
- **authentication.contract.test.jsx** - Login, registration, validation, password reset, logout

### Market Data & Trading
- **market-data.contract.test.jsx** - Market overview, sectors, quotes, movers, WebSocket streaming
- **trading-orders.contract.test.jsx** - Order management, creation, cancellation
- **realtime-data.contract.test.jsx** - WebSocket streams and real-time price data

### Application Features  
- **portfolio-data.contract.test.jsx** - Portfolio holdings, analytics, value calculations
- **dashboard.contract.test.jsx** - Dashboard summary and aggregated data
- **settings-apikeys.contract.test.jsx** - API key management and configuration
- **core-components.contract.test.jsx** - Watchlist, TechnicalAnalysis, StockExplorer, NewsAnalysis

## Running Contract Tests

```bash
# Run all contract tests
npx vitest run src/tests/integration/contracts/

# Run specific contract test  
npx vitest run src/tests/integration/contracts/api-endpoints.contract.test.jsx

# Run with verbose output
npx vitest run src/tests/integration/contracts/ --reporter=verbose
```

## Zero Duplication Strategy

- **Backend Integration Tests (44 files)**: Test API endpoints work correctly
- **Frontend Contract Tests (4 files)**: Test frontend consumes backend correctly
- **Unit Tests**: Test component/function logic in isolation
- **E2E Tests**: Test complete user workflows

Each layer has a distinct purpose with no overlap.

## Issues Found

1. **Health Endpoint Inconsistency**: `/api/health` missing `success` field
2. **WebSocket Parameter Validation**: Empty symbols properly return 404
3. **API Configuration**: WebSocket needs proper API credentials

## Future Contract Tests

Add contract tests when:
1. Frontend components consume new backend endpoints
2. API response structures change
3. Integration bugs are discovered
4. New critical user flows are added
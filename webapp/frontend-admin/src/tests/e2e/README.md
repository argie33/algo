# E2E Test Organization

This directory contains end-to-end (E2E) tests organized by purpose and functionality, following best practices with clear separation between individual page tests and cross-page workflow tests.

## Directory Structure

```
/tests/e2e/
├── features/           # Individual page tests (matches unit test structure)
├── workflows/          # Cross-page workflow tests (user journeys)
├── infrastructure/     # Technical/infrastructure E2E tests
├── api/               # API validation and integration tests
├── auth.setup.js      # Authentication setup utilities
├── global-setup.js    # Global test configuration
├── global-teardown.js # Global test cleanup
└── visual-regression.visual.spec.js-snapshots/ # Visual test snapshots
```

## Feature Tests (`/features/`) - Individual Pages
Tests specific pages in isolation (matches exact unit test naming pattern and actual app routes):

- `Dashboard.spec.js` - Dashboard page (`/`)
- `MarketOverview.spec.js` - Market overview page (`/market`)
- `Portfolio.spec.js` - Portfolio holdings page (`/portfolio`)
- `ScoresDashboard.spec.js` - Stock scores page (`/scores`)
- `SectorAnalysis.spec.js` - Sector analysis page (`/sectors`)
- `SentimentAnalysis.spec.js` - Sentiment analysis page (`/sentiment`)
- `Settings.spec.js` - Settings page (`/settings`)
- `StockExplorer.spec.js` - Stock analysis page (`/stocks`)
- `TechnicalAnalysis.spec.js` - Technical analysis page (`/technical`)
- `TradingSignals.spec.js` - Trading signals page (`/trading`)
- `Watchlist.spec.js` - Watchlist page (`/watchlist`)

## Workflow Tests (`/workflows/`) - Cross-Page User Journeys
Tests complete user workflows that span multiple pages:

- `authentication-flows.spec.js` - Login/logout across the application
- `portfolio-management.spec.js` - Complete portfolio workflow (view → add holdings → track performance)
- `settings-api-setup.spec.js` - API configuration workflow (setup → validate → use in other pages)
- `stock-research-to-trading.spec.js` - Research workflow (search → analyze → watchlist → trade)

## Infrastructure Tests (`/infrastructure/`)
Tests technical functionality, performance, and cross-cutting concerns:

- `accessibility.spec.js` - WCAG compliance and accessibility testing
- `cross-browser.spec.js` - Cross-browser compatibility (Safari, Chrome, Firefox)
- `edge-case-validation.spec.js` - Edge cases and error boundary testing
- `error-handling.spec.js` - API error handling and network failure scenarios
- `error-monitoring.spec.js` - Console error detection and monitoring
- `load-testing.spec.js` - Performance under load testing
- `mobile-responsive.spec.js` - Mobile and responsive design testing
- `performance.spec.js` - Performance metrics and optimization validation
- `settings-debug.spec.js` - Settings debugging and troubleshooting
- `visual-regression.spec.js` - Visual regression testing

## API Tests (`/api/`)
Tests API integration, validation, and data consistency:

- `api-validation.spec.js` - API endpoint validation and health checks
- `data-integration.spec.js` - Data integration and consistency testing

## Naming Conventions

### Feature Tests
- Named after the primary page or feature being tested
- Use descriptive names that match the application's page structure
- Examples: `portfolio-management.spec.js`, `trading-signals.spec.js`

### Infrastructure Tests
- Named after the technical concern being tested
- Use descriptive names for the type of testing
- Examples: `performance.spec.js`, `accessibility.spec.js`

### API Tests
- Named after the API functionality being tested
- Focus on integration and validation aspects
- Examples: `api-validation.spec.js`, `data-integration.spec.js`

## Test Patterns

All E2E tests follow consistent patterns:

1. **Setup**: Authentication and environment configuration in `beforeEach`
2. **Error Monitoring**: Console error tracking and classification
3. **Navigation**: Consistent page navigation with proper timeouts
4. **Assertions**: Clear, descriptive assertions with helpful error messages
5. **Debugging**: Screenshot capture on failures for debugging
6. **Cleanup**: Proper test cleanup and resource management

## Running Tests

```bash
# Run all E2E tests
npm run test:e2e

# Run specific category
npm run test:e2e -- features/
npm run test:e2e -- infrastructure/
npm run test:e2e -- api/

# Run specific test file
npm run test:e2e -- features/portfolio-management.spec.js
```

## Integration with CI/CD

These tests are organized to support:
- Parallel execution by category
- Selective test execution based on changed features
- Clear failure categorization and debugging
- Consistent reporting and metrics collection
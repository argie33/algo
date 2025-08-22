# Testing Quick Reference Guide

## Overview

This document provides quick commands and instructions for running all tests in the Financial Platform. For comprehensive testing details, see [TEST_PLAN.md](./TEST_PLAN.md).

## Quick Start

### Frontend Tests
```bash
cd webapp/frontend

# Run all tests
npm test

# Run with coverage
npm run test:coverage

# Run E2E tests
npm run test:e2e

# Run E2E tests with browser visible
npm run test:e2e:headed

# Debug E2E tests
npx playwright test --debug
```

### Backend Tests
```bash
cd webapp/lambda

# Run all tests
npm test

# Run unit tests only
npm test tests/unit/

# Run integration tests only
npm test tests/integration/

# Run specific test file
npm test tests/unit/database.unit.test.js

# Run tests with verbose output
npm test -- --verbose
```

## Test Categories

### 1. Unit Tests ✅
**Frontend**: `webapp/frontend/src/tests/unit/` (30+ files)
- Pages, components, services, hooks, utilities
- Vitest + React Testing Library

**Backend**: `webapp/lambda/tests/unit/` (40+ files)  
- Routes, services, middleware, utilities
- Jest + Supertest

### 2. Integration Tests ✅
**Frontend**: `webapp/frontend/src/tests/integration/` (15+ files)
- Complete user workflow testing
- API integration testing

**Backend**: `webapp/lambda/tests/integration/` (25+ files)
- API endpoint testing
- Database integration testing

### 3. End-to-End Tests ✅
**Location**: `webapp/frontend/src/tests/e2e/complete-system.e2e.test.js`
- 539 lines, 29 test scenarios
- Playwright multi-browser testing
- Complete user journey validation

## Test Commands Reference

### Frontend Commands
| Command | Description |
|---------|-------------|
| `npm test` | Run all unit/integration tests |
| `npm run test:coverage` | Run tests with coverage report |
| `npm run test:e2e` | Run E2E tests headless |
| `npm run test:e2e:headed` | Run E2E tests with browser visible |
| `npx playwright test --debug` | Debug E2E tests step-by-step |
| `npx playwright show-report` | View E2E test report |

### Backend Commands
| Command | Description |
|---------|-------------|
| `npm test` | Run all tests |
| `npm test tests/unit/` | Run unit tests only |
| `npm test tests/integration/` | Run integration tests only |
| `npm test -- --verbose` | Run with detailed output |
| `npm test -- --coverage` | Run with coverage report |
| `npm test -- --testNamePattern="API"` | Run tests matching pattern |

## Test Coverage Areas

### ✅ Authentication & Security
- JWT token validation
- API key encryption and management
- Session handling and expiration
- Input validation and sanitization

### ✅ Portfolio Management
- Real-time portfolio data
- Performance calculations
- Asset allocation charts
- Position management

### ✅ Trading Operations
- Order placement (market/limit)
- Order validation and error handling
- Trade history display
- Symbol validation

### ✅ Market Data & Research
- Stock search and details
- Market overview dashboard
- News and sentiment analysis
- Real-time data updates

### ✅ Settings & Configuration
- User preferences management
- API key CRUD operations
- Notification settings
- Trading preferences

### ✅ Mobile & Accessibility
- Responsive design testing
- Mobile navigation
- Keyboard navigation
- WCAG compliance validation

### ✅ Error Handling
- Network failure recovery
- Graceful degradation
- Validation error display
- Session expiration handling

### ✅ Performance
- Page load time validation (<5s)
- Loading state verification
- Memory usage monitoring
- API response times

## Debugging Tests

### Frontend Test Debugging
```bash
# Run single test file
npm test src/tests/unit/pages/Settings.test.jsx

# Run with watch mode
npm test -- --watch

# Debug E2E test in browser
npx playwright test --headed --debug

# Record new E2E test
npx playwright codegen https://d1copuy2oqlazx.cloudfront.net
```

### Backend Test Debugging
```bash
# Run single test with logs
npm test tests/unit/database.unit.test.js -- --verbose

# Debug specific test case
npm test -- --testNamePattern="should handle authentication"

# Run with environment variables
NODE_ENV=test npm test tests/integration/health.api.test.js
```

## Test Environment Setup

### Prerequisites
```bash
# Frontend dependencies
cd webapp/frontend
npm install
npx playwright install

# Backend dependencies  
cd webapp/lambda
npm install
```

### Environment Variables
```bash
# E2E testing
export PLAYWRIGHT_BASE_URL="https://d1copuy2oqlazx.cloudfront.net"
export VITE_API_URL="https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev"

# Local development testing
export PLAYWRIGHT_BASE_URL="http://localhost:5173"
export VITE_API_URL="http://localhost:3001"
```

## Test Data & Configuration

### Test User Credentials
```javascript
const TEST_USER = {
  email: "e2e-test@example.com",
  password: "TestPassword123!",
  firstName: "E2E",
  lastName: "Test",
};
```

### Mock API Keys
```javascript
const TEST_API_KEYS = {
  alpaca: "TEST_ALPACA_KEY",
  polygon: "TEST_POLYGON_KEY",
  finnhub: "TEST_FINNHUB_KEY"
};
```

## Continuous Integration

### GitHub Actions
Tests run automatically on:
- Pull requests to main branch
- Pushes to deployment branches
- Daily scheduled runs

### Test Reports
- HTML reports published to GitHub Pages
- JUnit XML for CI integration
- Coverage reports with quality gates

## Test File Structure

```
webapp/
├── frontend/
│   ├── src/tests/
│   │   ├── unit/           # Component & utility tests
│   │   ├── integration/    # User workflow tests
│   │   └── e2e/           # End-to-end tests
│   ├── vitest.config.js    # Vitest configuration
│   └── playwright.config.js # Playwright configuration
└── lambda/
    ├── tests/
    │   ├── unit/          # Service & route tests
    │   └── integration/   # API endpoint tests
    └── jest.config.js     # Jest configuration
```

## Common Issues & Solutions

### E2E Test Failures
1. **Timeout errors**: Increase timeout in playwright.config.js
2. **Element not found**: Check data-testid attributes exist
3. **Authentication issues**: Verify test user credentials

### Unit Test Failures
1. **Mock issues**: Clear mocks between tests with `vi.clearAllMocks()`
2. **Async issues**: Ensure proper await/waitFor usage
3. **DOM issues**: Check Jest DOM setup in test configuration

### Integration Test Failures
1. **Database issues**: Verify pg-mem setup in test files
2. **API issues**: Check mock service worker configuration
3. **Network issues**: Verify API endpoint URLs in test environment

## Performance Benchmarks

### Test Execution Times
- **Unit Tests**: < 30 seconds (frontend + backend)
- **Integration Tests**: < 60 seconds  
- **E2E Tests**: < 300 seconds (all browsers)

### Coverage Targets
- **Unit Test Coverage**: 90%+
- **Integration Coverage**: 100% of API endpoints
- **E2E Coverage**: 100% of user workflows

---

For comprehensive testing methodology and detailed implementation information, see [TEST_PLAN.md](./TEST_PLAN.md).
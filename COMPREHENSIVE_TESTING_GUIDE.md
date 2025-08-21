# Comprehensive Testing Guide - Finance Application

## Overview

This guide covers the complete testing strategy for our production-ready finance application. We've implemented a 4-tier testing approach: **Unit → Integration → Component → E2E**, with specialized focus on financial calculations, security, and data integrity.

## Current Test Coverage Status

### ✅ **Implemented (Phase 1)**
- **Frontend Unit Tests**: 21 files (components, services, utils)
- **Backend Unit Tests**: 25 files (routes, services, middleware)  
- **Critical Integration Tests**: 3 files (portfolio calculations, API encryption, auth flow)
- **Component Tests**: 1 file (Portfolio component interactions)
- **E2E Tests**: 1 file (complete user workflow)

### 🔧 **Test Infrastructure**
- **Frontend**: Vitest + React Testing Library + Playwright
- **Backend**: Jest + Supertest + Test containers
- **CI/CD**: GitHub Actions integration
- **Coverage**: HTML reports + JUnit XML for CI

## Quick Start - Running Tests

### Frontend Testing
```bash
# Navigate to frontend directory
cd webapp/frontend

# Run all test types
npm run test:comprehensive        # Unit + Integration + Component + E2E
npm run test:ci                   # CI-safe tests (excludes E2E)
npm run test:critical            # Financial + Security tests only

# Run specific test types
npm run test:unit                # Unit tests only
npm run test:integration         # Integration tests only  
npm run test:component           # Component interaction tests
npm run test:e2e                 # End-to-end browser tests
npm run test:e2e:headed          # E2E tests with visible browser

# Run domain-specific tests
npm run test:financial           # Portfolio, calculations, financial logic
npm run test:security            # Auth, encryption, security features

# Get test coverage report
npm run test:coverage            # Coverage report in coverage/ directory
```

### Backend Testing  
```bash
# Navigate to backend directory
cd webapp/lambda

# Run all test types
npm run test:comprehensive        # Unit + Integration + Security + Financial
npm run test:ci                   # CI-safe tests
npm run test:critical            # Financial + Security tests only

# Run specific test types  
npm run test:unit                # Unit tests only
npm run test:integration         # Integration tests only
npm run test:api                 # API endpoint tests
npm run test:database            # Database integration tests

# Run domain-specific tests
npm run test:financial           # Portfolio calculations, financial logic
npm run test:security            # API key encryption, auth security
npm run test:performance         # Performance benchmarks

# Security audits
npm run test:security:audit      # NPM security audit
```

## Test Categories Explained

### 1. Unit Tests - Individual Component Testing
**Purpose**: Test individual functions, components, and services in isolation

**Frontend Unit Tests** (`src/tests/unit/`):
- **Components**: React component rendering, props, state management
- **Services**: API calls, data formatting, utility functions  
- **Hooks**: Custom React hooks, state management
- **Pages**: Page-level component logic

**Backend Unit Tests** (`tests/unit/`):
- **Routes**: Individual route handlers, input validation
- **Services**: Business logic, data processing
- **Middleware**: Authentication, validation, error handling
- **Utilities**: Helper functions, formatters, validators

**Example Unit Test**:
```javascript
// Test individual portfolio calculation function
test('should calculate portfolio gain/loss percentage correctly', () => {
  const result = calculateGainLossPercent(15000, 17550); // cost, value
  expect(result).toBeCloseTo(17.00, 2); // 17% gain
});
```

### 2. Integration Tests - Service Interaction Testing  
**Purpose**: Test how multiple services work together with real data

**Key Integration Tests**:

**Portfolio Calculations** (`tests/integration/database/portfolio-calculations.integration.test.js`):
- Database → Portfolio service → API response
- Real portfolio data calculations
- Sector allocation accuracy
- Risk metrics computation

**API Key Encryption** (`tests/integration/security/api-key-encryption.integration.test.js`):
- Encryption service → Database storage → Decryption retrieval
- AES-256-GCM encryption validation
- User-specific salt generation
- Concurrent operation handling

**Authentication Flow** (`src/tests/integration/auth-flow.integration.test.js`):
- Cognito → JWT validation → API authorization
- Login/logout workflows
- Session management
- Token refresh handling

**Example Integration Test**:
```javascript
// Test complete portfolio data flow
test('should calculate accurate portfolio metrics with real database data', async () => {
  const response = await request(app)
    .get('/api/portfolio/analytics?timeframe=1D')
    .set('Authorization', `Bearer ${token}`);
    
  expect(response.data.totalValue).toBe(26550.00);
  expect(response.data.totalGainLossPercent).toBeCloseTo(4.02, 2);
});
```

### 3. Component Tests - User Interaction Testing
**Purpose**: Test complete component behavior with user interactions

**Portfolio Component Test** (`src/tests/component/Portfolio.component.test.jsx`):
- Full Portfolio page rendering with real data
- User interactions: sorting, filtering, timeframe changes
- Real-time updates, error handling
- Mobile responsiveness

**Key Test Scenarios**:
- Loading and displaying portfolio holdings
- Timeframe selection triggering API calls
- Sorting holdings by gain/loss
- Handling empty portfolio state
- Error recovery and retry mechanisms

**Example Component Test**:
```javascript
// Test user interaction with portfolio timeframe
test('should update data when timeframe is changed', async () => {
  render(<Portfolio />);
  
  const timeframeSelector = screen.getByRole('button', { name: /1D/ });
  await user.click(timeframeSelector);
  
  const oneWeekOption = screen.getByText('1W');
  await user.click(oneWeekOption);
  
  expect(mockApi.get).toHaveBeenCalledWith(
    expect.stringContaining('timeframe=1W')
  );
});
```

### 4. E2E Tests - Complete User Journey Testing
**Purpose**: Test entire user workflows in real browser environment

**Complete User Workflow** (`src/tests/e2e/user-portfolio-workflow.e2e.test.js`):
- User registration → Email verification → Login
- API key setup → Portfolio access → Market data
- Real-time updates → Settings management → Logout

**Browser Coverage**:
- **Desktop**: Chrome, Firefox, Safari, Edge
- **Mobile**: Chrome Mobile, Safari Mobile
- **Viewports**: Desktop (1280x720), Mobile (375x667)

**Performance Testing**:
- Application load time < 5 seconds
- Core Web Vitals compliance (LCP, FID, CLS)
- Large dataset handling < 3 seconds

**Example E2E Test**:
```javascript
// Test complete user onboarding flow
test('Complete user onboarding and portfolio setup', async ({ page }) => {
  // Registration
  await page.click('text=Sign Up');
  await page.fill('[data-testid="email-input"]', 'test@example.com');
  await page.click('[data-testid="register-button"]');
  
  // API Key Setup  
  await page.click('[data-testid="api-setup"]');
  await page.fill('[data-testid="alpaca-key"]', 'test-key');
  
  // Portfolio Access
  await page.click('[data-testid="portfolio-nav"]');
  await expect(page.locator('[data-testid="portfolio-summary"]')).toBeVisible();
});
```

## Financial Application-Specific Testing

### Portfolio Calculation Accuracy
**Critical Requirements**: 100% accuracy for financial calculations

```javascript
// Verify portfolio value calculation
test('should maintain precision for large portfolio values', async () => {
  const portfolio = await getPortfolio(userId);
  const calculatedTotal = portfolio.holdings.reduce((sum, h) => sum + h.value, 0);
  
  expect(Math.abs(portfolio.totalValue - calculatedTotal)).toBeLessThan(0.01);
});
```

### Security Testing
**Critical Requirements**: API key encryption, auth validation, data protection

```javascript
// Verify API key encryption
test('should encrypt API keys before database storage', async () => {
  await apiKeyService.storeApiKey(userId, 'alpaca', keyId, secret);
  
  const dbResult = await query('SELECT encrypted_secret FROM user_api_keys WHERE user_id = ?', [userId]);
  expect(dbResult.encrypted_secret).not.toBe(secret); // Should be encrypted
  expect(dbResult.encrypted_secret).toMatch(/^[0-9a-f]+:[0-9a-f]+$/); // encrypted:iv format
});
```

### Real-time Data Testing  
**Requirements**: Data consistency, WebSocket reliability, price accuracy

```javascript  
// Test real-time price updates
test('should update portfolio values with real-time prices', async () => {
  // Simulate price update
  const priceUpdate = { symbol: 'AAPL', price: 180.50 };
  await simulatePriceUpdate(priceUpdate);
  
  await waitFor(() => {
    expect(screen.getByText('$180.50')).toBeInTheDocument();
  });
});
```

## CI/CD Integration

### GitHub Actions Integration
Tests are automatically run on every push and pull request:

```yaml
# Frontend Tests
- name: Run Frontend Tests
  run: |
    cd webapp/frontend
    npm run test:ci  # Unit + Integration + Component (no E2E in CI)
    npm run test:critical  # Financial + Security tests

# Backend Tests  
- name: Run Backend Tests
  run: |
    cd webapp/lambda  
    npm run test:ci  # Unit + Integration
    npm run test:critical  # Financial + Security tests
```

### Test Coverage Requirements
- **Unit Tests**: 80% line coverage minimum
- **Integration Tests**: 100% critical path coverage  
- **Financial Calculations**: 100% accuracy validation
- **Security Functions**: 100% coverage + penetration testing

## Running Tests in Different Environments

### Local Development
```bash
# Run tests with file watching
npm run test              # Unit tests with watch mode
npm run test:integration  # Integration tests once
npm run test:e2e:headed   # E2E tests with visible browser
```

### CI/CD Pipeline
```bash
# Run CI-safe test suite (no browser dependencies)
npm run test:ci
npm run test:critical
npm run test:security:audit
```

### Production Validation
```bash
# Run comprehensive test suite before deployment
npm run test:comprehensive
npm run test:performance
npm run test:security
```

## Test Data Management

### Mock Data Strategy
- **Unit Tests**: Controlled mock data for predictable testing
- **Integration Tests**: Realistic financial datasets
- **E2E Tests**: Sandbox API keys and test accounts

### Test Database
- **Isolated Environment**: Separate test database for integration tests  
- **Data Fixtures**: Reusable test scenarios (empty portfolio, profitable portfolio, loss portfolio)
- **Cleanup**: Automatic cleanup after each test run

### API Mocking
- **External APIs**: Mock Alpaca, Polygon, Finnhub responses
- **Rate Limiting**: Simulate API rate limits and failures
- **Error Scenarios**: Test network failures, timeouts, invalid data

## Debugging Failed Tests

### Frontend Test Debugging
```bash
# Run specific test with debug info
npm run test src/tests/unit/Portfolio.test.jsx --verbose

# Run test with browser open (E2E)
npm run test:e2e:headed

# Get coverage report to identify untested code
npm run test:coverage
open coverage/index.html
```

### Backend Test Debugging
```bash  
# Run specific test with debug info
npm run test tests/integration/portfolio-calculations.integration.test.js --verbose

# Debug database connections
NODE_ENV=test npm run test:database --verbose

# Check API key encryption
npm run test:security --verbose
```

### Common Issues and Solutions

**Issue**: Tests failing due to async operations
**Solution**: Use `waitFor()` and proper async/await patterns

**Issue**: Database connection timeouts in tests
**Solution**: Increase timeout and ensure test database is running

**Issue**: E2E tests failing due to slow loading
**Solution**: Add proper wait conditions and increase timeouts

**Issue**: Mock API responses not matching real API
**Solution**: Update mocks to match current API response format

## Performance Benchmarks

### Frontend Performance Targets
- **App Load Time**: < 3 seconds on 3G
- **Portfolio Load**: < 2 seconds with 100 holdings
- **Chart Rendering**: < 500ms for real-time updates
- **Memory Usage**: < 100MB on mobile devices

### Backend Performance Targets  
- **API Response**: < 200ms for portfolio analytics
- **Database Queries**: < 100ms for simple queries
- **Concurrent Users**: Support 1000+ simultaneous users
- **Error Rate**: < 0.1% for critical financial calculations

## Security Testing Checklist

### API Security
- [ ] API key encryption/decryption accuracy
- [ ] JWT token validation and expiration  
- [ ] SQL injection prevention
- [ ] Input sanitization and validation
- [ ] Rate limiting and abuse prevention

### Data Protection
- [ ] User data encryption at rest
- [ ] Secure API key storage
- [ ] Password hashing and validation
- [ ] Session management security
- [ ] HTTPS enforcement

### Financial Security
- [ ] Portfolio calculation accuracy (100%)
- [ ] Transaction integrity verification
- [ ] Audit trail for all financial operations
- [ ] Data consistency across services
- [ ] Precision handling for large values

## Maintenance and Updates

### Regular Maintenance Tasks
- **Weekly**: Update test data fixtures with recent market data
- **Monthly**: Review and update mock API responses  
- **Quarterly**: Performance benchmark validation
- **As Needed**: Update tests when adding new features

### Test Coverage Monitoring
- Monitor test coverage trends over time
- Identify and test new critical paths  
- Update E2E tests for new user workflows
- Regular security penetration testing

---

## Next Steps for Full Production Readiness

### Phase 2: Extended Testing (Next 2 Weeks)
1. **Add 15+ more integration tests** covering all API endpoints
2. **Component tests for all major pages** (Dashboard, Trading, Settings)  
3. **Performance testing suite** with load testing
4. **Security penetration testing** with automated scans

### Phase 3: Advanced Testing (Weeks 3-4)
1. **Visual regression testing** for UI consistency
2. **Accessibility testing** (WCAG 2.1 AA compliance)  
3. **Cross-browser compatibility** extended testing
4. **API contract testing** with provider validation

The foundation is solid - we now have comprehensive testing covering the critical financial calculations, security, and user workflows. The test infrastructure supports continuous integration and provides confidence for production deployment.
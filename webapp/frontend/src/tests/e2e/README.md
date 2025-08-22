# E2E Testing Guide

## Overview

Comprehensive end-to-end testing suite for the Financial Platform using Playwright. Tests cover all critical user journeys including authentication, trading, portfolio management, and system reliability.

## Test Coverage

### 🔐 Authentication & Onboarding
- User registration flow
- API key setup and validation
- Login/logout functionality
- Session management

### 💼 Portfolio Management
- Portfolio overview display
- Performance charts and metrics
- Asset allocation visualization
- Real-time updates

### 📈 Trading Functionality
- Order placement (market/limit)
- Order validation and error handling
- Trade history display
- Position management

### 📊 Market Data & Research
- Market overview dashboard
- Stock search and details
- News and sentiment analysis
- Real-time data updates

### ⚙️ Settings & Configuration
- Notification preferences
- API key management
- Trading preferences
- Account settings

### 📱 Mobile Responsiveness
- Mobile navigation
- Responsive layouts
- Touch interactions
- Viewport adaptations

### 🛡️ Error Handling
- Network failure recovery
- Invalid input validation
- Session expiration handling
- Graceful degradation

### ⚡ Performance & Accessibility
- Page load times
- Loading states
- Keyboard navigation
- Heading structure

## Running Tests

### Prerequisites
```bash
# Install dependencies
npm install

# Install Playwright browsers
npx playwright install
```

### Test Execution Commands

```bash
# Run all E2E tests
npm run test:e2e

# Run tests in headed mode (see browser)
npx playwright test --headed

# Run specific test file
npx playwright test complete-system.e2e.test.js

# Run tests with debug mode
npx playwright test --debug

# Run tests for specific browser
npx playwright test --project=chromium

# Run tests with UI mode
npx playwright test --ui
```

### Environment Configuration

Set environment variables for test execution:

```bash
# Frontend URL (defaults to CloudFront)
export PLAYWRIGHT_BASE_URL="https://d1copuy2oqlazx.cloudfront.net"

# API URL (defaults to production API Gateway)
export VITE_API_URL="https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev"

# For local testing
export PLAYWRIGHT_BASE_URL="http://localhost:5173"
export VITE_API_URL="http://localhost:3001"
```

## Test Configuration

### Browser Support
- **Desktop**: Chrome, Firefox, Safari, Edge
- **Mobile**: Chrome (Pixel 5), Safari (iPhone 12)
- **Cross-platform**: All major browsers and devices

### Timeouts & Retries
- **Action timeout**: 10 seconds
- **Navigation timeout**: 30 seconds  
- **Test timeout**: 60 seconds
- **Retries**: 2 on CI, 0 locally

### Artifacts
- **Videos**: Recorded on failure
- **Screenshots**: Captured on failure
- **Traces**: Collected on first retry
- **Reports**: HTML, JSON, and XML formats

## Test Data Management

### Test User Credentials
```javascript
const TEST_USER = {
  email: "e2e-test@example.com",
  password: "TestPassword123!",
  firstName: "E2E",
  lastName: "Test",
};
```

### API Keys for Testing
- Use test API keys for external services
- Validate connection without real trading
- Mock sensitive operations in test environment

## Best Practices

### Test Structure
1. **Setup**: Login and navigate to target page
2. **Action**: Perform user interactions
3. **Assertion**: Verify expected outcomes
4. **Cleanup**: Reset state for next test

### Selector Strategy
- Prefer `data-testid` attributes for stability
- Use semantic selectors when test IDs unavailable
- Avoid CSS selectors tied to styling

### Error Handling
- Test both success and failure scenarios
- Verify error messages are user-friendly
- Ensure graceful degradation

### Performance Testing
- Monitor page load times
- Verify loading states display correctly
- Test with network throttling

## Debugging Tests

### Debug Commands
```bash
# Run with browser dev tools open
npx playwright test --debug

# Run specific test with debug
npx playwright test --debug -g "should login successfully"

# Record new test
npx playwright codegen https://d1copuy2oqlazx.cloudfront.net
```

### Troubleshooting

#### Common Issues
1. **Timeouts**: Increase timeout or wait for specific elements
2. **Flaky tests**: Add proper waits and stable selectors
3. **Authentication**: Verify test user credentials and API keys
4. **Environment**: Check URLs and network connectivity

#### Debug Tips
- Use `page.pause()` to inspect test state
- Check `trace.playwright.dev` for failed test traces
- Review screenshots and videos in test results
- Use `console.log()` for debugging test flow

## CI/CD Integration

### GitHub Actions
Tests run automatically on:
- Pull requests to main branch
- Pushes to deployment branches
- Scheduled daily runs

### Test Results
- HTML reports published to GitHub Pages
- JUnit XML for CI integration
- JSON results for further analysis

## Maintenance

### Regular Updates
- Update test data for API changes
- Add tests for new features
- Review and update selectors
- Optimize test performance

### Test Health Monitoring
- Track test execution times
- Monitor flaky test patterns
- Review failure rates
- Update browser versions

## Contact

For E2E testing questions or issues:
- Review test logs and artifacts
- Check GitHub Actions workflow results
- Update test configuration as needed
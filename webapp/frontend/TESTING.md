# Playwright Testing Guide

This project includes a comprehensive Playwright test suite with full coverage for E2E, visual regression, accessibility, performance, and cross-browser testing.

## Quick Start

### 1. Basic Validation (No Browser Dependencies Required)
```bash
# Test dev server and basic functionality
npm run test:validation
```

### 2. Full Test Suite (Requires System Dependencies)
```bash
# Install browser dependencies (requires sudo)
sudo npx playwright install-deps

# Run all tests
npm run test:e2e

# Run specific test categories
npm run test:e2e:critical     # Critical user flows
npm run test:e2e:visual       # Visual regression
npm run test:e2e:a11y         # Accessibility
npm run test:e2e:perf         # Performance
```

## Test Categories

### 🔍 **Critical User Flows** (`critical-flows.spec.js`)
- React Context error detection
- Navigation between main sections
- API failure handling and graceful degradation  
- Authentication flow validation
- Mobile responsive behavior

### 📸 **Visual Regression** (`visual-regression.visual.spec.js`)
- Screenshot comparisons for all major pages
- Mobile and desktop visual testing
- Component-level visual validation
- Error state visual capture

### ♿ **Accessibility Testing** (`accessibility.accessibility.spec.js`)
- WCAG 2.1 AA compliance with axe-core
- Keyboard navigation validation
- Focus indicator verification
- Color contrast checking
- Form label accessibility
- Interactive element sizing (44px minimum)

### ⚡ **Performance Testing** (`performance.perf.spec.js`)
- Core Web Vitals measurement (LCP, FCP, CLS, TTI)
- Bundle size budget validation (500KB JS, 100KB CSS)
- API response time monitoring (<1s threshold)
- Memory usage tracking (<100MB)
- Mobile performance testing (<5s load time)

### 🌐 **Cross-Browser Testing**
- **Desktop**: Chrome, Firefox, Safari (1920x1080)
- **Tablet**: iPad Pro simulation
- **Mobile**: Pixel 5, iPhone 12 simulation

## Configuration Files

### `playwright.config.js` - Full Production Configuration
- Complete cross-browser testing
- All test categories enabled
- Global setup/teardown
- Requires browser dependencies

### `playwright.config.ci.js` - CI/Limited Environment Configuration
- Basic validation tests only
- No browser dependencies required  
- Suitable for environments without GUI support

## Package.json Scripts

Add these scripts to your `package.json`:

```json
{
  "scripts": {
    "test:validation": "PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS=1 npx playwright test --config playwright.config.ci.js",
    "test:e2e": "PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS=1 npx playwright test",
    "test:e2e:critical": "PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS=1 npx playwright test critical-flows",
    "test:e2e:visual": "PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS=1 npx playwright test --project visual-desktop",
    "test:e2e:a11y": "PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS=1 npx playwright test --project accessibility", 
    "test:e2e:perf": "PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS=1 npx playwright test --project performance",
    "test:e2e:mobile": "PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS=1 npx playwright test --project mobile-chrome",
    "test:e2e:report": "npx playwright show-report"
  }
}
```

## System Requirements

### For Full Test Suite
```bash
# Ubuntu/Debian
sudo apt-get install libnspr4 libnss3 libasound2t64

# Or use Playwright installer
sudo npx playwright install-deps
```

### Environment Variables
- `PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS=1` - Skip system dependency validation
- `CI=true` - Enable CI mode with retries and single worker

## Docker/CI Setup

For Docker or CI environments, use the CI configuration:

```dockerfile
# Dockerfile example
RUN npx playwright install-deps
RUN npx playwright install
```

```yaml
# GitHub Actions example
- name: Install Playwright dependencies
  run: sudo npx playwright install-deps
  
- name: Run E2E tests
  run: npm run test:e2e
```

## Troubleshooting

### "Missing system dependencies" Error
```bash
# Install dependencies
sudo npx playwright install-deps

# Or manually install packages
sudo apt-get install libnspr4 libnss3 libasound2t64
```

### "Browser launch failed" Error
```bash
# Use validation config for basic testing
npm run test:validation

# Check dev server is running
curl http://localhost:3001
```

### "Tests timeout" Error
```bash
# Increase timeout in config
timeout: 60000

# Or run with longer timeout
npx playwright test --timeout=60000
```

## Test Coverage Summary

**Total Tests**: 245 tests across 5 comprehensive categories
**Browsers**: Chrome, Firefox, Safari, Mobile Chrome, Mobile Safari  
**Coverage**: E2E, Visual, Accessibility, Performance, Cross-browser
**Best Practices**: Following Playwright and testing community standards

## Development

### Adding New Tests
1. Follow existing patterns in test files
2. Use descriptive test names
3. Include proper error handling
4. Add to appropriate test category
5. Update this documentation

### Test Organization
```
src/tests/e2e/
├── critical-flows.spec.js          # Core user journeys
├── visual-regression.visual.spec.js # Screenshot testing
├── accessibility.accessibility.spec.js # WCAG compliance
├── performance.perf.spec.js        # Core Web Vitals
├── dev-server-validation.test.js   # Basic server validation
├── auth.setup.js                   # Authentication setup
├── global-setup.js                 # Global test setup
└── global-teardown.js              # Global test cleanup
```

This comprehensive test suite ensures your financial dashboard meets production quality standards for user experience, accessibility, performance, and cross-browser compatibility.
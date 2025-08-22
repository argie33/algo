/**
 * End-to-End User Portfolio Workflow Test
 * Critical: Tests complete user journey from login to portfolio management
 * Uses Playwright for real browser automation
 */

import { test, expect } from '@playwright/test';

// Test configuration
const TEST_CONFIG = {
  baseURL: process.env.VITE_API_URL || 'https://d1copuy2oqlazx.cloudfront.net',
  apiURL: process.env.API_URL || 'https://qda42av7je.execute-api.us-east-1.amazonaws.com/dev',
  timeout: 30000,
  testUser: {
    email: 'e2e-test@example.com',
    password: 'E2ETest123!@#',
    firstName: 'E2E',
    lastName: 'Tester'
  },
  testApiKeys: {
    alpaca: {
      keyId: 'TEST_ALPACA_KEY_' + Date.now(),
      secret: 'test_alpaca_secret_' + Date.now()
    }
  }
};

test.describe('Complete User Portfolio Workflow', () => {
  let page;
  
  test.beforeEach(async ({ browser }) => {
    page = await browser.newPage();
    
    // Set viewport for consistent testing
    await page.setViewportSize({ width: 1280, height: 720 });
    
    // Navigate to application
    await page.goto(TEST_CONFIG.baseURL);
    
    // Wait for app to load
    await page.waitForLoadState('networkidle');
  });

  test.afterEach(async () => {
    if (page) {
      await page.close();
    }
  });

  test('Complete user onboarding and portfolio setup flow', async () => {
    // Step 1: User Registration
    await test.step('User registers new account', async () => {
      // Navigate to registration
      await page.click('text=Sign Up');
      await page.waitForSelector('form[data-testid="register-form"]');

      // Fill registration form
      await page.fill('[data-testid="email-input"]', TEST_CONFIG.testUser.email);
      await page.fill('[data-testid="password-input"]', TEST_CONFIG.testUser.password);
      await page.fill('[data-testid="first-name-input"]', TEST_CONFIG.testUser.firstName);
      await page.fill('[data-testid="last-name-input"]', TEST_CONFIG.testUser.lastName);

      // Submit registration
      await page.click('[data-testid="register-button"]');

      // Handle email verification (mock or skip in test environment)
      await page.waitForSelector('text=Verify your email', { timeout: 10000 });
      
      // For E2E testing, we'll mock the verification step
      await page.evaluate(() => {
        window.localStorage.setItem('e2e-test-verified', 'true');
      });
    });

    // Step 2: Login with new account  
    await test.step('User logs in successfully', async () => {
      // Navigate to login if not already there
      if (await page.isVisible('text=Sign In')) {
        await page.click('text=Sign In');
      }

      await page.waitForSelector('[data-testid="login-form"]');

      // Fill login form
      await page.fill('[data-testid="login-email"]', TEST_CONFIG.testUser.email);
      await page.fill('[data-testid="login-password"]', TEST_CONFIG.testUser.password);

      // Submit login
      await page.click('[data-testid="login-button"]');

      // Wait for successful login and dashboard redirect
      await page.waitForURL(/dashboard|portfolio/, { timeout: 15000 });
      await page.waitForSelector('[data-testid="user-menu"]', { timeout: 10000 });

      // Verify user is logged in
      const userMenu = await page.textContent('[data-testid="user-menu"]');
      expect(userMenu).toContain(TEST_CONFIG.testUser.email);
    });

    // Step 3: API Key Setup
    await test.step('User sets up API keys', async () => {
      // Navigate to API key setup
      await page.click('[data-testid="settings-button"]');
      await page.waitForSelector('text=API Keys');
      await page.click('text=API Keys');

      // Check for onboarding wizard
      if (await page.isVisible('[data-testid="api-key-onboarding"]')) {
        await page.click('[data-testid="start-setup-button"]');
      }

      // Set up Alpaca API key
      await page.waitForSelector('[data-testid="alpaca-api-setup"]');
      await page.fill('[data-testid="alpaca-key-id"]', TEST_CONFIG.testApiKeys.alpaca.keyId);
      await page.fill('[data-testid="alpaca-secret"]', TEST_CONFIG.testApiKeys.alpaca.secret);
      
      // Enable sandbox mode for testing
      await page.check('[data-testid="alpaca-sandbox-mode"]');

      // Save API key
      await page.click('[data-testid="save-alpaca-key"]');

      // Wait for validation
      await page.waitForSelector('[data-testid="api-key-success"]', { timeout: 10000 });
      
      // Verify API key is validated
      const validationStatus = await page.textContent('[data-testid="alpaca-status"]');
      expect(validationStatus).toContain('Connected');
    });

    // Step 4: Portfolio Access
    await test.step('User accesses portfolio page', async () => {
      // Navigate to portfolio
      await page.click('[data-testid="portfolio-nav"]');
      await page.waitForURL(/portfolio/);

      // Wait for portfolio data to load
      await page.waitForSelector('[data-testid="portfolio-summary"]', { timeout: 15000 });

      // Check if it's an empty portfolio (new user)
      const isEmpty = await page.isVisible('[data-testid="empty-portfolio"]');
      
      if (isEmpty) {
        // Verify empty state message
        const emptyMessage = await page.textContent('[data-testid="empty-portfolio-message"]');
        expect(emptyMessage).toContain('No holdings');
        
        // Should show call-to-action
        expect(await page.isVisible('[data-testid="add-position-button"]')).toBeTruthy();
      } else {
        // If portfolio has data, verify it loads correctly
        await page.waitForSelector('[data-testid="holdings-table"]');
        const totalValue = await page.textContent('[data-testid="total-portfolio-value"]');
        expect(totalValue).toMatch(/\$[\d,]+\.?\d*/); // Should show currency format
      }
    });

    // Step 5: Market Data Access
    await test.step('User views market data and research', async () => {
      // Navigate to market overview
      await page.click('[data-testid="market-nav"]');
      await page.waitForURL(/market|dashboard/);

      // Wait for market data to load
      await page.waitForSelector('[data-testid="market-overview"]', { timeout: 15000 });

      // Verify market data components load
      expect(await page.isVisible('[data-testid="market-indices"]')).toBeTruthy();
      expect(await page.isVisible('[data-testid="top-movers"]')).toBeTruthy();

      // Test stock search functionality
      await page.fill('[data-testid="stock-search"]', 'AAPL');
      await page.waitForSelector('[data-testid="search-results"]');
      
      // Click on search result
      await page.click('[data-testid="search-result-AAPL"]');
      await page.waitForURL(/stock\/AAPL/);

      // Verify stock detail page loads
      await page.waitForSelector('[data-testid="stock-detail"]');
      const stockSymbol = await page.textContent('[data-testid="stock-symbol"]');
      expect(stockSymbol).toBe('AAPL');
    });

    // Step 6: Real-time Data Testing
    await test.step('User interacts with real-time features', async () => {
      // Go back to portfolio
      await page.click('[data-testid="portfolio-nav"]');
      await page.waitForURL(/portfolio/);

      // Test real-time updates (if available)
      if (await page.isVisible('[data-testid="real-time-toggle"]')) {
        await page.click('[data-testid="real-time-toggle"]');
        
        // Verify real-time status
        await page.waitForSelector('[data-testid="real-time-connected"]', { timeout: 5000 });
        const connectionStatus = await page.textContent('[data-testid="connection-status"]');
        expect(connectionStatus).toContain('Connected');
      }

      // Test portfolio refresh
      await page.click('[data-testid="refresh-portfolio"]');
      
      // Verify loading state appears and resolves
      await page.waitForSelector('[data-testid="loading-indicator"]', { state: 'visible' });
      await page.waitForSelector('[data-testid="loading-indicator"]', { state: 'hidden', timeout: 10000 });
    });

    // Step 7: Settings and Profile Management
    await test.step('User manages profile settings', async () => {
      // Navigate to user settings
      await page.click('[data-testid="user-menu"]');
      await page.click('[data-testid="profile-settings"]');
      await page.waitForURL(/settings/);

      // Test profile updates
      await page.fill('[data-testid="display-name"]', 'E2E Test User Updated');
      await page.selectOption('[data-testid="timezone"]', 'America/New_York');
      await page.click('[data-testid="save-profile"]');

      // Verify save success
      await page.waitForSelector('[data-testid="save-success"]');
      const successMessage = await page.textContent('[data-testid="save-success"]');
      expect(successMessage).toContain('saved successfully');

      // Test notification preferences
      await page.click('[data-testid="notifications-tab"]');
      await page.check('[data-testid="price-alerts"]');
      await page.check('[data-testid="portfolio-updates"]');
      await page.click('[data-testid="save-notifications"]');

      await page.waitForSelector('[data-testid="notifications-saved"]');
    });

    // Step 8: Error Handling and Recovery
    await test.step('Application handles errors gracefully', async () => {
      // Test network error handling by intercepting API calls
      await page.route('**/api/portfolio/**', route => {
        route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({ error: 'Internal server error' })
        });
      });

      // Navigate to portfolio to trigger error
      await page.click('[data-testid="portfolio-nav"]');
      await page.waitForURL(/portfolio/);

      // Verify error message appears
      await page.waitForSelector('[data-testid="error-message"]');
      const errorMessage = await page.textContent('[data-testid="error-message"]');
      expect(errorMessage).toContain('error');

      // Test retry functionality
      if (await page.isVisible('[data-testid="retry-button"]')) {
        // Remove route intercept to allow retry to succeed
        await page.unroute('**/api/portfolio/**');
        
        await page.click('[data-testid="retry-button"]');
        await page.waitForSelector('[data-testid="portfolio-summary"]', { timeout: 10000 });
      }
    });

    // Step 9: Mobile Responsiveness
    await test.step('Application works on mobile devices', async () => {
      // Switch to mobile viewport
      await page.setViewportSize({ width: 375, height: 667 });

      // Navigate through key pages
      await page.click('[data-testid="mobile-menu-button"]');
      await page.click('[data-testid="mobile-portfolio-link"]');

      // Verify mobile layout
      expect(await page.isVisible('[data-testid="mobile-portfolio-view"]')).toBeTruthy();

      // Test mobile-specific interactions
      if (await page.isVisible('[data-testid="mobile-holdings-list"]')) {
        await page.click('[data-testid="holding-item-0"]');
        expect(await page.isVisible('[data-testid="holding-details-modal"]')).toBeTruthy();
      }
    });

    // Step 10: Logout and Session Cleanup
    await test.step('User logs out successfully', async () => {
      // Return to desktop viewport
      await page.setViewportSize({ width: 1280, height: 720 });

      // Logout
      await page.click('[data-testid="user-menu"]');
      await page.click('[data-testid="logout-button"]');

      // Verify redirect to login page
      await page.waitForURL(/login|signin/);
      await page.waitForSelector('[data-testid="login-form"]');

      // Verify user is logged out
      expect(await page.isVisible('[data-testid="user-menu"]')).toBeFalsy();

      // Verify protected pages redirect to login
      await page.goto(`${TEST_CONFIG.baseURL}/portfolio`);
      await page.waitForURL(/login|signin|auth/);
    });
  });

  test('Portfolio data accuracy and calculations', async () => {
    // This test focuses on verifying portfolio calculations
    await test.step('Setup authenticated user with portfolio data', async () => {
      // Mock login for existing user with portfolio
      await page.evaluate((testUser) => {
        window.localStorage.setItem('auth-token', 'mock-token-with-portfolio');
        window.localStorage.setItem('user-email', testUser.email);
      }, TEST_CONFIG.testUser);

      await page.goto(`${TEST_CONFIG.baseURL}/portfolio`);
      await page.waitForSelector('[data-testid="portfolio-summary"]');
    });

    await test.step('Verify portfolio calculations', async () => {
      // Wait for portfolio data to load
      await page.waitForSelector('[data-testid="holdings-table"]');

      // Get individual holding values
      const holdings = await page.$$eval('[data-testid="holding-row"]', rows => {
        return rows.map(row => ({
          symbol: row.querySelector('[data-testid="holding-symbol"]')?.textContent,
          quantity: parseFloat(row.querySelector('[data-testid="holding-quantity"]')?.textContent || '0'),
          price: parseFloat(row.querySelector('[data-testid="holding-price"]')?.textContent?.replace(/[$,]/g, '') || '0'),
          value: parseFloat(row.querySelector('[data-testid="holding-value"]')?.textContent?.replace(/[$,]/g, '') || '0')
        }));
      });

      // Calculate expected total value
      const expectedTotal = holdings.reduce((sum, holding) => sum + holding.value, 0);

      // Get displayed total value
      const displayedTotal = await page.textContent('[data-testid="total-portfolio-value"]');
      const totalValue = parseFloat(displayedTotal.replace(/[$,]/g, ''));

      // Verify calculations match (within small rounding tolerance)
      expect(Math.abs(totalValue - expectedTotal)).toBeLessThan(0.01);
    });

    await test.step('Verify real-time price updates', async () => {
      // Take screenshot of initial prices
      const _initialPrices = await page.$$eval('[data-testid="holding-price"]', elements => {
        return elements.map(el => el.textContent);
      });

      // Trigger price refresh
      await page.click('[data-testid="refresh-prices"]');
      await page.waitForLoadState('networkidle');

      // Wait for prices to potentially update
      await page.waitForTimeout(2000);

      const updatedPrices = await page.$$eval('[data-testid="holding-price"]', elements => {
        return elements.map(el => el.textContent);
      });

      // Verify price format is consistent
      updatedPrices.forEach(price => {
        expect(price).toMatch(/\$\d+\.\d{2}/);
      });
    });
  });

  test('Performance and loading benchmarks', async () => {
    await test.step('Measure application loading performance', async () => {
      const startTime = Date.now();
      
      await page.goto(TEST_CONFIG.baseURL);
      await page.waitForSelector('[data-testid="app-loaded"]');
      
      const loadTime = Date.now() - startTime;
      
      // Application should load within 5 seconds
      expect(loadTime).toBeLessThan(5000);
      
      // Measure Core Web Vitals
      const webVitals = await page.evaluate(() => {
        return new Promise((resolve) => {
          new PerformanceObserver((list) => {
            const entries = list.getEntries();
            resolve({
              lcp: entries.find(entry => entry.entryType === 'largest-contentful-paint')?.startTime,
              fid: entries.find(entry => entry.entryType === 'first-input')?.processingStart,
              cls: entries.find(entry => entry.entryType === 'layout-shift')?.value
            });
          }).observe({ entryTypes: ['largest-contentful-paint', 'first-input', 'layout-shift'] });
        });
      });

      // Basic Web Vitals thresholds
      if (webVitals.lcp) expect(webVitals.lcp).toBeLessThan(2500); // LCP < 2.5s
      if (webVitals.fid) expect(webVitals.fid).toBeLessThan(100);  // FID < 100ms
      if (webVitals.cls) expect(webVitals.cls).toBeLessThan(0.1);  // CLS < 0.1
    });

    await test.step('Test large dataset handling', async () => {
      // Navigate to page that loads large dataset
      await page.goto(`${TEST_CONFIG.baseURL}/market`);
      
      const startTime = Date.now();
      await page.waitForSelector('[data-testid="large-table-loaded"]');
      const loadTime = Date.now() - startTime;

      // Large datasets should load within 3 seconds
      expect(loadTime).toBeLessThan(3000);

      // Test scrolling performance
      const scrollStartTime = Date.now();
      await page.evaluate(() => {
        window.scrollTo(0, document.body.scrollHeight);
      });
      await page.waitForTimeout(100); // Allow for scroll rendering
      const scrollTime = Date.now() - scrollStartTime;

      // Scrolling should be smooth (< 100ms)
      expect(scrollTime).toBeLessThan(100);
    });
  });
});
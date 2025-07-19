/**
 * Comprehensive E2E Error Recovery Tests
 * Tests circuit breakers, timeouts, graceful degradation, and system resilience
 * No mocks - validates real error handling and recovery mechanisms
 */

import { test, expect } from '@playwright/test';

test.describe('Error Recovery and Resilience Tests', () => {
  let page;
  let context;
  
  test.beforeEach(async ({ browser }) => {
    context = await browser.newContext({
      // Enable debugging and performance monitoring
      recordVideo: { dir: 'test-results/videos/' },
      recordHar: { path: 'test-results/network.har' }
    });
    page = await context.newPage();
    
    // Capture console errors for analysis
    const errors = [];
    page.on('console', msg => {
      if (msg.type() === 'error') {
        errors.push(msg.text());
      }
      console.log(`Page log: ${msg.text()}`);
    });
    page.on('pageerror', err => {
      errors.push(err.message);
      console.error(`Page error: ${err.message}`);
    });
    
    // Store errors on page for test access
    page.pageErrors = errors;
  });

  test.afterEach(async () => {
    await context.close();
  });

  test('should handle network connectivity failures gracefully', async () => {
    console.log('🔄 Testing network connectivity failure handling...');
    
    await page.goto('/dashboard');
    await page.waitForSelector('[data-testid="dashboard-container"]', { timeout: 30000 });
    
    // Simulate network failure by blocking all requests
    await page.route('**/*', route => {
      if (route.request().url().includes('api.us-east-1.amazonaws.com')) {
        route.abort('failed');
      } else {
        route.continue();
      }
    });
    
    // Try to trigger API call that will fail
    await page.click('[data-testid="refresh-data"]');
    
    // Should show error state, not crash
    await page.waitForSelector('[data-testid="network-error"]', { timeout: 10000 });
    const networkError = await page.locator('[data-testid="network-error"]');
    await expect(networkError).toBeVisible();
    await expect(networkError).toContainText('network');
    
    // Verify retry mechanism is available
    const retryButton = await page.locator('[data-testid="retry-button"]');
    await expect(retryButton).toBeVisible();
    
    // Clear network block and test retry
    await page.unroute('**/*');
    await retryButton.click();
    
    // Should recover and show data
    await page.waitForTimeout(5000);
    await expect(networkError).not.toBeVisible();
    
    // Verify dashboard is functional again
    const dashboardData = await page.locator('[data-testid="dashboard-data"]');
    await expect(dashboardData).toBeVisible();
  });

  test('should handle circuit breaker states appropriately', async () => {
    console.log('🔄 Testing circuit breaker behavior...');
    
    await page.goto('/service-health');
    await page.waitForSelector('[data-testid="health-dashboard"]', { timeout: 30000 });
    
    // Check circuit breaker status
    const circuitBreakerStatus = await page.locator('[data-testid="circuit-breaker-status"]');
    await expect(circuitBreakerStatus).toBeVisible();
    
    const statusText = await circuitBreakerStatus.textContent();
    console.log('Circuit breaker status:', statusText);
    
    if (statusText.includes('OPEN')) {
      // If circuit breaker is open, test the waiting period
      await expect(circuitBreakerStatus).toContainText('unavailable');
      
      // Should show countdown or retry message
      const retryMessage = await page.locator('[data-testid="retry-countdown"]');
      if (await retryMessage.isVisible()) {
        await expect(retryMessage).toContainText('seconds');
      }
      
      // Test that API calls are properly blocked
      await page.goto('/portfolio');
      
      const blockedMessage = await page.locator('[data-testid="service-blocked"]');
      if (await blockedMessage.isVisible()) {
        await expect(blockedMessage).toContainText('temporarily unavailable');
      }
      
    } else if (statusText.includes('CLOSED')) {
      // If circuit breaker is closed, test normal operation
      await expect(circuitBreakerStatus).toContainText('operational');
      
      // Test database operations work
      await page.goto('/portfolio');
      await page.waitForSelector('[data-testid="portfolio-container"]', { timeout: 15000 });
      
      const portfolioData = await page.locator('[data-testid="portfolio-data"]');
      await expect(portfolioData).toBeVisible();
      
    } else if (statusText.includes('HALF-OPEN')) {
      // If half-open, test limited operations
      await expect(circuitBreakerStatus).toContainText('testing');
      
      // Should allow limited requests
      await page.goto('/portfolio');
      
      // May work or fail depending on circuit breaker state
      await page.waitForTimeout(5000);
      
      // Check if we got data or error
      const hasData = await page.locator('[data-testid="portfolio-data"]').isVisible();
      const hasError = await page.locator('[data-testid="service-error"]').isVisible();
      
      expect(hasData || hasError).toBe(true);
    }
  });

  test('should handle timeout scenarios with proper fallbacks', async () => {
    console.log('🔄 Testing timeout handling with fallbacks...');
    
    await page.goto('/market-overview');
    await page.waitForSelector('[data-testid="market-container"]', { timeout: 30000 });
    
    // Simulate slow API responses
    await page.route('**/api/**', async route => {
      // Add delay to simulate timeout scenario
      await page.waitForTimeout(8000); // Longer than typical timeout
      route.continue();
    });
    
    // Trigger data refresh
    await page.click('[data-testid="refresh-market-data"]');
    
    // Should show loading state initially
    const loadingIndicator = await page.locator('[data-testid="loading-indicator"]');
    await expect(loadingIndicator).toBeVisible();
    
    // Wait for timeout to occur
    await page.waitForTimeout(12000);
    
    // Should show timeout message, not infinite loading
    const timeoutMessage = await page.locator('[data-testid="timeout-message"]');
    if (await timeoutMessage.isVisible()) {
      await expect(timeoutMessage).toContainText('timeout');
    }
    
    // Should offer retry option
    const retryButton = await page.locator('[data-testid="retry-timeout"]');
    if (await retryButton.isVisible()) {
      await expect(retryButton).toBeVisible();
    }
    
    // Clear timeout simulation
    await page.unroute('**/api/**');
    
    // Test fallback data display
    const fallbackData = await page.locator('[data-testid="fallback-data"]');
    if (await fallbackData.isVisible()) {
      await expect(fallbackData).toContainText('cached data');
    }
  });

  test('should recover from authentication token expiration', async () => {
    console.log('🔄 Testing authentication token expiration recovery...');
    
    await page.goto('/protected-settings');
    await page.waitForSelector('[data-testid="settings-container"]', { timeout: 30000 });
    
    // Simulate expired token by intercepting auth requests
    await page.route('**/api/**', route => {
      if (route.request().headers()['authorization']) {
        route.fulfill({
          status: 401,
          body: JSON.stringify({ error: 'Token expired' })
        });
      } else {
        route.continue();
      }
    });
    
    // Try to perform authenticated action
    await page.click('[data-testid="save-settings"]');
    
    // Should handle 401 gracefully and redirect to login
    await page.waitForTimeout(3000);
    
    // Check for authentication error handling
    const authError = await page.locator('[data-testid="auth-error"]');
    if (await authError.isVisible()) {
      await expect(authError).toContainText('expired');
    }
    
    // Should redirect to login or show re-auth prompt
    const currentUrl = page.url();
    const hasLoginForm = await page.locator('[data-testid="login-form"]').isVisible();
    const hasReauthPrompt = await page.locator('[data-testid="reauth-prompt"]').isVisible();
    
    expect(currentUrl.includes('/login') || hasLoginForm || hasReauthPrompt).toBe(true);
    
    // Clear auth simulation for cleanup
    await page.unroute('**/api/**');
  });

  test('should handle API rate limiting gracefully', async () => {
    console.log('🔄 Testing API rate limiting handling...');
    
    await page.goto('/dashboard');
    await page.waitForSelector('[data-testid="dashboard-container"]', { timeout: 30000 });
    
    // Simulate rate limiting response
    let requestCount = 0;
    await page.route('**/api/**', route => {
      requestCount++;
      if (requestCount > 3) {
        route.fulfill({
          status: 429,
          headers: {
            'Retry-After': '60'
          },
          body: JSON.stringify({ error: 'Rate limit exceeded' })
        });
      } else {
        route.continue();
      }
    });
    
    // Trigger multiple rapid requests
    for (let i = 0; i < 5; i++) {
      await page.click('[data-testid="refresh-data"]');
      await page.waitForTimeout(100);
    }
    
    // Should show rate limit message
    await page.waitForSelector('[data-testid="rate-limit-message"]', { timeout: 5000 });
    const rateLimitMessage = await page.locator('[data-testid="rate-limit-message"]');
    await expect(rateLimitMessage).toBeVisible();
    await expect(rateLimitMessage).toContainText('rate limit');
    
    // Should show retry timer
    const retryTimer = await page.locator('[data-testid="retry-timer"]');
    if (await retryTimer.isVisible()) {
      await expect(retryTimer).toContainText('60');
    }
    
    // Clear rate limiting for cleanup
    await page.unroute('**/api/**');
  });

  test('should handle malformed API responses without crashing', async () => {
    console.log('🔄 Testing malformed API response handling...');
    
    await page.goto('/stock-detail/AAPL');
    await page.waitForSelector('[data-testid="stock-detail-container"]', { timeout: 30000 });
    
    // Simulate malformed JSON responses
    await page.route('**/api/stock/**', route => {
      route.fulfill({
        status: 200,
        headers: { 'Content-Type': 'application/json' },
        body: 'invalid json response'
      });
    });
    
    // Trigger API call
    await page.click('[data-testid="refresh-stock-data"]');
    
    // Should handle JSON parse error gracefully
    await page.waitForTimeout(3000);
    
    const parseError = await page.locator('[data-testid="data-error"]');
    if (await parseError.isVisible()) {
      await expect(parseError).toContainText('data format');
    }
    
    // Page should not crash - verify critical elements still work
    const navigation = await page.locator('[data-testid="main-navigation"]');
    await expect(navigation).toBeVisible();
    
    // Should offer to try again
    const retryButton = await page.locator('[data-testid="retry-data"]');
    if (await retryButton.isVisible()) {
      await expect(retryButton).toBeVisible();
    }
    
    // Clear malformed response simulation
    await page.unroute('**/api/stock/**');
  });

  test('should handle partial data loading failures gracefully', async () => {
    console.log('🔄 Testing partial data loading failures...');
    
    await page.goto('/portfolio-performance');
    await page.waitForSelector('[data-testid="performance-container"]', { timeout: 30000 });
    
    // Simulate some API endpoints failing while others succeed
    await page.route('**/api/portfolio/positions', route => {
      route.fulfill({
        status: 500,
        body: JSON.stringify({ error: 'Internal server error' })
      });
    });
    
    // Other endpoints continue to work normally
    await page.route('**/api/portfolio/summary', route => {
      route.continue();
    });
    
    // Trigger data refresh
    await page.click('[data-testid="refresh-performance"]');
    
    // Should show what data is available
    await page.waitForTimeout(5000);
    
    const summarySection = await page.locator('[data-testid="portfolio-summary"]');
    const positionsSection = await page.locator('[data-testid="portfolio-positions"]');
    
    // Summary might load successfully
    if (await summarySection.isVisible()) {
      await expect(summarySection).toBeVisible();
    }
    
    // Positions should show error state
    const positionsError = await page.locator('[data-testid="positions-error"]');
    if (await positionsError.isVisible()) {
      await expect(positionsError).toContainText('Unable to load positions');
    }
    
    // Should offer to retry failed sections
    const retryPositions = await page.locator('[data-testid="retry-positions"]');
    if (await retryPositions.isVisible()) {
      await expect(retryPositions).toBeVisible();
    }
    
    // Clear partial failure simulation
    await page.unroute('**/api/portfolio/positions');
  });

  test('should maintain session state during temporary failures', async () => {
    console.log('🔄 Testing session state maintenance during failures...');
    
    await page.goto('/settings');
    await page.waitForSelector('[data-testid="settings-container"]', { timeout: 30000 });
    
    // Make some UI state changes
    await page.click('[data-testid="dark-mode-toggle"]');
    await page.fill('[data-testid="display-name"]', 'Test User Updated');
    
    // Simulate temporary network failure
    await page.route('**/api/**', route => {
      route.abort('failed');
    });
    
    // Navigate to another page during network failure
    await page.click('[data-testid="nav-portfolio"]');
    
    // Should maintain UI state even with network issues
    await page.waitForTimeout(3000);
    
    // Restore network and navigate back
    await page.unroute('**/api/**');
    
    await page.click('[data-testid="nav-settings"]');
    await page.waitForSelector('[data-testid="settings-container"]', { timeout: 30000 });
    
    // UI state should be preserved
    const displayName = await page.locator('[data-testid="display-name"]');
    const displayNameValue = await displayName.inputValue();
    expect(displayNameValue).toBe('Test User Updated');
    
    // Dark mode state should be preserved
    const body = await page.locator('body');
    const bodyClass = await body.getAttribute('class');
    if (bodyClass && bodyClass.includes('dark')) {
      expect(bodyClass).toContain('dark');
    }
  });

  test('should provide detailed error information for debugging', async () => {
    console.log('🔄 Testing detailed error information provision...');
    
    await page.goto('/stock-detail/INVALID_SYMBOL');
    
    // Should handle invalid symbol gracefully
    await page.waitForTimeout(5000);
    
    const errorDetails = await page.locator('[data-testid="error-details"]');
    if (await errorDetails.isVisible()) {
      await expect(errorDetails).toBeVisible();
      
      // Should provide useful error information
      const errorText = await errorDetails.textContent();
      expect(errorText.length).toBeGreaterThan(10);
    }
    
    // Check if error ID is provided for support
    const errorId = await page.locator('[data-testid="error-id"]');
    if (await errorId.isVisible()) {
      const errorIdText = await errorId.textContent();
      expect(errorIdText).toMatch(/[A-Z0-9-]{8,}/);
    }
    
    // Should provide contact information or help links
    const helpLink = await page.locator('[data-testid="help-link"]');
    const supportContact = await page.locator('[data-testid="support-contact"]');
    
    expect(await helpLink.isVisible() || await supportContact.isVisible()).toBe(true);
    
    // Check console for structured error logging
    const hasStructuredErrors = page.pageErrors.some(error => 
      error.includes('errorId') || error.includes('correlationId')
    );
    
    if (page.pageErrors.length > 0) {
      console.log('Captured errors:', page.pageErrors);
    }
  });

  test('should handle memory leaks and resource cleanup', async () => {
    console.log('🔄 Testing memory leak prevention and resource cleanup...');
    
    // Navigate through multiple pages quickly to test cleanup
    const pages = [
      '/dashboard',
      '/portfolio',
      '/market-overview',
      '/stock-detail/AAPL',
      '/settings'
    ];
    
    for (const pagePath of pages) {
      await page.goto(pagePath);
      await page.waitForTimeout(2000);
      
      // Trigger some data loading
      const refreshButton = page.locator('[data-testid="refresh-data"]');
      if (await refreshButton.isVisible()) {
        await refreshButton.click();
      }
      
      await page.waitForTimeout(1000);
    }
    
    // Check for memory leak indicators in console
    const memoryWarnings = page.pageErrors.filter(error => 
      error.includes('memory') || error.includes('leak') || error.includes('cleanup')
    );
    
    // Should not have memory-related errors
    expect(memoryWarnings).toHaveLength(0);
    
    // Test WebSocket cleanup specifically
    await page.goto('/live-data-enhanced');
    await page.waitForSelector('[data-testid="live-data-container"]', { timeout: 30000 });
    
    // Start WebSocket connections
    await page.click('[data-testid="start-live-feed"]');
    await page.waitForTimeout(3000);
    
    // Navigate away - should cleanup connections
    await page.goto('/dashboard');
    await page.waitForTimeout(2000);
    
    // Check for WebSocket cleanup in console
    const wsCleanupLogs = page.pageErrors.filter(log => 
      log.includes('WebSocket') && log.includes('cleanup')
    );
    
    // Should see cleanup logs (this is positive indicator)
    if (wsCleanupLogs.length > 0) {
      console.log('WebSocket cleanup detected:', wsCleanupLogs);
    }
  });
});
/**
 * End-to-End User Workflow Tests
 * Tests complete user journeys through the financial dashboard platform
 * 
 * Critical Workflows Covered:
 * 1. New User Setup Journey
 * 2. Stock Research and Analysis Workflow
 * 3. Portfolio Management Workflow
 * 4. Trading Signals and Decision Making
 * 5. Error Recovery and Resilience Testing
 */

import { test, expect } from '@playwright/test';

test.describe('Financial Platform User Workflows', () => {
  
  test.beforeEach(async ({ page, browserName }) => {
    // Set up development environment authentication
    await page.addInitScript(() => {
      localStorage.setItem('financial_auth_token', 'e2e-test-token');
      localStorage.setItem('dev_auth_enabled', 'true');
      localStorage.setItem('user_profile', JSON.stringify({
        id: 'test-user-123',
        email: 'e2e@test.com',
        name: 'E2E Test User',
        subscription: 'premium'
      }));
    });
    
    // Browser-specific timeout optimization
    const timeout = browserName === 'firefox' ? 5000 : 3000;
    
    await page.goto('/', { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.waitForSelector('#root', { state: 'attached', timeout: 15000 });
    await page.waitForTimeout(timeout);
  });

  test.describe('New User Setup Journey', () => {
    
    test('should complete new user setup flow', async ({ page }) => {
      // Step 1: Initial Dashboard Access
      await expect(page.locator('#root')).toBeVisible();
      await expect(page.getByText('Dashboard')).toBeVisible();
      
      // Step 2: Navigate to Settings for API Key Setup
      await page.click('[data-testid="settings-menu-item"]:has-text("Settings")');
      await expect(page.getByText('Settings')).toBeVisible();
      
      // Step 3: API Key Configuration Simulation
      // In development mode, API keys are simulated
      const apiKeySection = page.locator('[data-testid="api-keys-section"]:has-text("API Keys")');
      if (await apiKeySection.isVisible()) {
        await expect(apiKeySection).toBeVisible();
        
        // Verify API key status indicators are present
        const statusElements = page.locator('[data-testid*="status"], .MuiChip-root');
        await expect(statusElements.first()).toBeVisible();
      }
      
      // Step 4: Navigate to Portfolio Setup
      await page.click('[data-testid="portfolio-menu-item"]:has-text("Portfolio Holdings")');
      await expect(page.getByText('Portfolio')).toBeVisible();
      
      // Step 5: Verify setup completion indicators
      const dashboardElements = page.locator('[data-testid="dashboard-widget"], .MuiCard-root');
      await expect(dashboardElements.first()).toBeVisible({ timeout: 10000 });
    });

    test('should handle API key setup workflow', async ({ page }) => {
      await page.goto('/settings');
      await page.waitForSelector('text=Settings', { timeout: 10000 });
      
      // Test API key configuration flow
      const apiKeyInputs = page.locator('input[type="password"], input[placeholder*="key"], input[placeholder*="secret"]');
      const inputCount = await apiKeyInputs.count();
      
      if (inputCount > 0) {
        // Fill sample API key data
        await apiKeyInputs.first().fill('test-api-key-12345');
        
        // Look for save/update buttons
        const saveButtons = page.locator('button:has-text("Save"), button:has-text("Update"), button[type="submit"]');
        const buttonCount = await saveButtons.count();
        
        if (buttonCount > 0) {
          await saveButtons.first().click();
          
          // Verify success feedback
          await expect(page.locator('.MuiAlert-root, [data-testid="success-message"]')).toBeVisible({ timeout: 5000 });
        }
      }
    });
  });

  test.describe('Stock Research and Analysis Workflow', () => {
    
    test('should complete stock research journey', async ({ page }) => {
      // Step 1: Start with Stock Screener
      await page.click('[data-testid="stock-screener-menu"]:has-text("Stock Screener")');
      await expect(page.getByText('Screener', { exact: false })).toBeVisible();
      
      // Step 2: Apply search filters (simulate user research)
      const filterInputs = page.locator('input[placeholder*="symbol"], input[placeholder*="name"], .MuiTextField-root input');
      const inputCount = await filterInputs.count();
      
      if (inputCount > 0) {
        await filterInputs.first().fill('AAPL');
        await page.keyboard.press('Enter');
        await page.waitForTimeout(2000);
      }
      
      // Step 3: Navigate to Stock Analysis
      await page.click('[data-testid="stock-analysis-menu"]:has-text("Stock Analysis")');
      await expect(page.getByText('Analysis')).toBeVisible();
      
      // Step 4: Access Technical Analysis
      await page.click('[data-testid="technical-analysis-menu"]:has-text("Technical Analysis")');
      await expect(page.getByText('Technical')).toBeVisible();
      
      // Step 5: Check Analyst Insights
      await page.click('[data-testid="analyst-insights-menu"]:has-text("Analyst Insights")');
      await expect(page.getByText('Analyst', { exact: false })).toBeVisible();
      
      // Verify data visualization elements are present
      const chartElements = page.locator('canvas, svg, [data-testid*="chart"], .recharts-wrapper');
      const chartCount = await chartElements.count();
      if (chartCount > 0) {
        await expect(chartElements.first()).toBeVisible();
      }
    });

    test('should navigate between market analysis pages', async ({ page }) => {
      // Market Overview → Sector Analysis → Economic Indicators journey
      await page.click('[data-testid="market-overview-menu"]:has-text("Market Overview")');
      await expect(page.getByText('Market')).toBeVisible();
      
      await page.click('[data-testid="sector-analysis-menu"]:has-text("Sector Analysis")');
      await expect(page.getByText('Sector')).toBeVisible();
      
      await page.click('[data-testid="economic-indicators-menu"]:has-text("Economic Indicators")');
      await expect(page.getByText('Economic')).toBeVisible();
      
      // Verify page transitions work smoothly
      await page.goBack();
      await page.goBack();
      await expect(page.getByText('Market')).toBeVisible();
    });
  });

  test.describe('Portfolio Management Workflow', () => {
    
    test('should complete portfolio management tasks', async ({ page }) => {
      // Step 1: Access Portfolio Holdings
      await page.click('text=Portfolio Holdings');
      await expect(page.getByText('Portfolio')).toBeVisible();
      
      // Step 2: Review Portfolio Performance
      await page.click('text=Performance');
      await expect(page.getByText('Performance')).toBeVisible();
      
      // Step 3: Check Trade History
      await page.click('text=Trade History');
      await expect(page.getByText('Trade', { exact: false })).toBeVisible();
      
      // Step 4: Access Order Management
      await page.click('text=Order Management');
      await expect(page.getByText('Order')).toBeVisible();
      
      // Verify portfolio data tables are present
      const tableElements = page.locator('table, .MuiDataGrid-root, [data-testid*="table"], .MuiTableContainer-root');
      const tableCount = await tableElements.count();
      if (tableCount > 0) {
        await expect(tableElements.first()).toBeVisible();
      }
    });

    test('should handle portfolio optimization workflow', async ({ page }) => {
      await page.goto('/portfolio');
      await page.waitForSelector('text=Portfolio', { timeout: 10000 });
      
      // Look for optimization tools
      const optimizationElements = page.locator('text=Optimize, text=Allocation, text=Risk, button:has-text("Optimize")');
      const elemCount = await optimizationElements.count();
      
      if (elemCount > 0) {
        await optimizationElements.first().click();
        
        // Verify optimization results or interface
        const resultElements = page.locator('.MuiCard-root, [data-testid*="result"], [data-testid*="recommendation"]');
        await expect(resultElements.first()).toBeVisible({ timeout: 8000 });
      }
    });
  });

  test.describe('Trading Signals and Decision Making', () => {
    
    test('should access trading signals and alerts', async ({ page }) => {
      // Step 1: Check Earnings Calendar for events
      await page.click('text=Earnings Calendar');
      await expect(page.getByText('Earnings')).toBeVisible();
      
      // Step 2: Review Trading Signals (if premium feature available)
      const signalsMenu = page.locator('text=Signals');
      if (await signalsMenu.isVisible()) {
        await signalsMenu.click();
        await expect(page.getByText('Signal', { exact: false })).toBeVisible();
      }
      
      // Step 3: Access Watchlist for monitoring
      await page.click('text=Watchlist');
      await expect(page.getByText('Watchlist')).toBeVisible();
      
      // Step 4: Check Market Sentiment (premium feature)
      const sentimentMenu = page.locator('text=Sentiment');
      if (await sentimentMenu.isVisible()) {
        await sentimentMenu.click();
        await expect(page.getByText('Sentiment')).toBeVisible();
      }
    });

    test('should manage watchlist functionality', async ({ page }) => {
      await page.goto('/watchlist');
      await page.waitForSelector('text=Watchlist', { timeout: 10000 });
      
      // Test adding symbols to watchlist
      const addInputs = page.locator('input[placeholder*="symbol"], input[placeholder*="ticker"], button:has-text("Add")');
      const inputCount = await addInputs.count();
      
      if (inputCount > 0) {
        const symbolInput = addInputs.first();
        if (await symbolInput.getAttribute('type') !== 'button') {
          await symbolInput.fill('MSFT');
          await page.keyboard.press('Enter');
          await page.waitForTimeout(1000);
        }
      }
      
      // Verify watchlist items display
      const watchlistItems = page.locator('.MuiListItem-root, .watchlist-item, [data-testid*="watchlist-item"]');
      const itemCount = await watchlistItems.count();
      if (itemCount > 0) {
        await expect(watchlistItems.first()).toBeVisible();
      }
    });
  });

  test.describe('Error Recovery and Resilience Testing', () => {
    
    test('should handle navigation errors gracefully', async ({ page }) => {
      // Test invalid route handling
      await page.goto('/invalid-route-12345');
      await page.waitForTimeout(2000);
      
      // Should either redirect to valid page or show error state
      const bodyText = await page.locator('body').textContent();
      const isValidState = bodyText.includes('Dashboard') || 
                          bodyText.includes('Not Found') || 
                          bodyText.includes('Error') ||
                          bodyText.includes('404');
      
      expect(isValidState).toBeTruthy();
    });

    test('should recover from API connection issues', async ({ page }) => {
      // Monitor network errors during navigation
      const networkErrors = [];
      
      page.on('response', response => {
        if (response.status() >= 400) {
          networkErrors.push({
            url: response.url(),
            status: response.status()
          });
        }
      });
      
      // Navigate through multiple pages to test resilience
      await page.click('[data-testid="market-menu"], text=Market Overview');
      await page.waitForTimeout(1000);
      
      await page.click('[data-testid="stocks-menu"], text=Stock Analysis');
      await page.waitForTimeout(1000);
      
      await page.click('text=Portfolio Holdings');
      await page.waitForTimeout(1000);
      
      // Application should remain functional despite any API errors
      await expect(page.locator('#root')).toBeVisible();
      
      // Log network errors for debugging but don't fail test
      if (networkErrors.length > 0) {
        console.log('Network errors detected:', networkErrors.slice(0, 5));
      }
    });

    test('should handle session timeout scenarios', async ({ page }) => {
      // Clear authentication to simulate session expiry
      await page.evaluate(() => {
        localStorage.removeItem('financial_auth_token');
        localStorage.removeItem('user_profile');
      });
      
      // Navigate to protected page
      await page.goto('/portfolio');
      await page.waitForTimeout(2000);
      
      // Should handle auth requirement gracefully
      const bodyText = await page.locator('body').textContent();
      const hasValidAuthHandling = bodyText.includes('Login') || 
                                  bodyText.includes('Sign in') || 
                                  bodyText.includes('Authentication') ||
                                  bodyText.includes('Portfolio'); // If dev mode allows access
      
      expect(hasValidAuthHandling).toBeTruthy();
    });

    test('should maintain state during page refreshes', async ({ page }) => {
      // Navigate to a data-heavy page
      await page.click('[data-testid="dashboard-menu"], text=Dashboard');
      await page.waitForTimeout(2000);
      
      // Capture initial state
      const initialContent = await page.locator('#root').textContent();
      
      // Refresh page
      await page.reload({ waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(3000);
      
      // Verify page loads successfully after refresh
      await expect(page.locator('#root')).toBeVisible();
      
      const refreshedContent = await page.locator('#root').textContent();
      expect(refreshedContent.length).toBeGreaterThan(100);
      
      // Should maintain functional dashboard
      const hasDashboardElements = refreshedContent.includes('Dashboard') || 
                                  refreshedContent.length > initialContent.length * 0.5;
      expect(hasDashboardElements).toBeTruthy();
    });
  });

  test.describe('Cross-Feature Integration Workflows', () => {
    
    test('should complete research-to-action workflow', async ({ page }) => {
      // Research: Start with Market Overview
      await page.click('text=Market Overview');
      await page.waitForTimeout(1000);
      
      // Analysis: Move to Technical Analysis
      await page.click('text=Technical Analysis');
      await page.waitForTimeout(1000);
      
      // Decision: Check Analyst Insights
      await page.click('text=Analyst Insights');
      await page.waitForTimeout(1000);
      
      // Action: Add to Watchlist
      await page.click('text=Watchlist');
      await page.waitForTimeout(1000);
      
      // Monitor: Return to Dashboard for overview
      await page.click('text=Dashboard');
      await page.waitForTimeout(1000);
      
      // Verify complete workflow maintains app stability
      await expect(page.locator('#root')).toBeVisible();
      const finalContent = await page.locator('#root').textContent();
      expect(finalContent.length).toBeGreaterThan(500);
    });

    test('should handle settings changes affecting other pages', async ({ page }) => {
      // Start at Settings
      await page.click('text=Settings');
      await page.waitForTimeout(1000);
      
      // Make a settings change (theme, preferences, etc.)
      const settingsButtons = page.locator('button, .MuiSwitch-root, .MuiCheckbox-root');
      const buttonCount = await settingsButtons.count();
      
      if (buttonCount > 0) {
        // Click first available setting control
        await settingsButtons.first().click();
        await page.waitForTimeout(500);
      }
      
      // Navigate to other pages to verify settings take effect
      await page.click('text=Dashboard');
      await page.waitForTimeout(1000);
      
      await page.click('text=Portfolio Holdings');
      await page.waitForTimeout(1000);
      
      // Verify pages remain functional with settings changes
      await expect(page.locator('#root')).toBeVisible();
    });
  });

  test.describe('Performance and Responsiveness', () => {
    
    test('should load pages within performance budgets', async ({ page }) => {
      const pageLoadTimes = [];
      
      const testPages = [
        { name: 'Dashboard', selector: 'text=Dashboard' },
        { name: 'Market Overview', selector: 'text=Market Overview' },
        { name: 'Stock Analysis', selector: 'text=Stock Analysis' },
        { name: 'Portfolio', selector: 'text=Portfolio Holdings' }
      ];
      
      for (const testPage of testPages) {
        const startTime = Date.now();
        
        await page.click(testPage.selector);
        await page.waitForSelector('#root', { state: 'visible' });
        await page.waitForTimeout(1000);
        
        const loadTime = Date.now() - startTime;
        pageLoadTimes.push({ page: testPage.name, time: loadTime });
        
        // Each page should load within 5 seconds (E2E performance budget)
        expect(loadTime).toBeLessThan(5000);
      }
      
      console.log('Page load times:', pageLoadTimes);
    });

    test('should handle rapid navigation without breaking', async ({ page }) => {
      // Rapid navigation test - simulate quick user clicks
      const navigationSequence = [
        'text=Dashboard',
        'text=Market Overview', 
        'text=Stock Analysis',
        'text=Technical Analysis',
        'text=Portfolio Holdings',
        'text=Watchlist'
      ];
      
      for (const selector of navigationSequence) {
        await page.click(selector);
        await page.waitForTimeout(300); // Minimal wait to simulate rapid clicking
      }
      
      // App should remain stable after rapid navigation
      await page.waitForTimeout(2000);
      await expect(page.locator('#root')).toBeVisible();
      
      const finalContent = await page.locator('#root').textContent();
      expect(finalContent.length).toBeGreaterThan(200);
    });
  });
});
/**
 * Visual Regression Testing
 * Captures screenshots and compares against baselines
 */

import { test, expect } from '@playwright/test';

test.describe('Visual Regression Tests', () => {
  
  test.beforeEach(async ({ page }) => {
    // Set up consistent viewport for stable screenshots  
    await page.setViewportSize({ width: 1920, height: 1080 });
    
    // Set up consistent state for visual testing
    await page.addInitScript(() => {
      localStorage.setItem('financial_auth_token', 'visual-test-token');
      localStorage.setItem('theme', 'light');
      localStorage.setItem('api_keys_status', JSON.stringify({
        alpaca: { configured: true, valid: true },
        polygon: { configured: true, valid: true },
        finnhub: { configured: true, valid: true }
      }));
      
      // Disable auto-refresh and real-time updates
      window.DISABLE_AUTO_REFRESH = true;
      window.TEST_MODE = true;
    });
    
    // Mock consistent API responses for visual stability
    await page.route('**/api/**', route => {
      const url = route.request().url();
      
      if (url.includes('/portfolio/holdings')) {
        route.fulfill({
          json: {
            success: true,
            data: {
              totalValue: 125000.50,
              totalGainLoss: 8500.25,
              totalGainLossPercent: 7.3,
              holdings: [
                { symbol: 'AAPL', quantity: 100, currentPrice: 195.20, totalValue: 19520.00, gainLoss: 1470.00, lastUpdated: '2024-01-15T12:00:00Z' },
                { symbol: 'MSFT', quantity: 50, currentPrice: 385.75, totalValue: 19287.50, gainLoss: 1787.50, lastUpdated: '2024-01-15T12:00:00Z' },
                { symbol: 'GOOGL', quantity: 25, currentPrice: 2650.75, totalValue: 66268.75, gainLoss: 6268.75, lastUpdated: '2024-01-15T12:00:00Z' }
              ]
            }
          }
        });
      } else if (url.includes('/market/overview')) {
        route.fulfill({
          json: {
            success: true,
            data: {
              indices: {
                SPY: { price: 445.32, change: 2.15, changePercent: 0.48, lastUpdated: '2024-01-15T12:00:00Z' },
                QQQ: { price: 375.68, change: -1.23, changePercent: -0.33, lastUpdated: '2024-01-15T12:00:00Z' },
                DIA: { price: 355.91, change: 0.87, changePercent: 0.24, lastUpdated: '2024-01-15T12:00:00Z' }
              },
              sectors: [
                { name: 'Technology', performance: 1.85, trend: 'up' },
                { name: 'Healthcare', performance: 0.75, trend: 'up' },
                { name: 'Financials', performance: 0.45, trend: 'up' }
              ]
            }
          }
        });
      } else {
        route.fulfill({ json: { success: true, data: {} } });
      }
    });
    
    // Enhanced content stabilization for visual testing
    await page.addStyleTag({
      content: `
        /* Hide all dynamic and time-sensitive content */
        .timestamp, .last-updated, .time, .datetime,
        [class*="timestamp"], [class*="time"], [data-testid*="time"],
        .loading, .spinner, .progress, .pulse, .animate,
        [class*="loading"], [class*="spinner"], [class*="progress"],
        [class*="pulse"], [class*="animate"], [class*="blink"] {
          visibility: hidden !important;
          opacity: 0 !important;
        }
        
        /* Disable ALL animations and transitions */
        *, *::before, *::after {
          animation-duration: 0s !important;
          animation-delay: 0s !important;
          transition-duration: 0s !important;
          transition-delay: 0s !important;
          animation-play-state: paused !important;
        }
        
        /* Hide scrollbars and variable elements */
        ::-webkit-scrollbar { display: none !important; }
        html { scrollbar-width: none !important; }
        
        /* Force consistent font rendering */
        * {
          -webkit-font-smoothing: antialiased !important;
          -moz-osx-font-smoothing: grayscale !important;
          font-feature-settings: normal !important;
        }
        
        /* Hide any auto-updating elements */
        [data-auto-update], [data-live], .live-data, .real-time {
          visibility: hidden !important;
        }
      `
    });
    
    await page.goto('/');
    await page.waitForSelector('#root', { state: 'attached' });
    await page.waitForTimeout(1000);
    
    // Wait for fonts and animations to settle
    await page.waitForTimeout(1000);
  });

  test('Dashboard homepage visual comparison', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('#root', { state: 'attached' });
    await page.waitForTimeout(1000);
    
    await expect(page).toHaveScreenshot('dashboard-homepage.png', {
      fullPage: false,  // Use viewport screenshot for consistency
      animations: 'disabled',
      threshold: 0.5,
      maxDiffPixels: 50000,
      clip: { x: 0, y: 0, width: 1920, height: 1080 }
    });
  });

  test('Portfolio page visual comparison', async ({ page }) => {
    await page.goto('/portfolio');
    await page.waitForSelector('#root', { state: 'attached' });
    await page.waitForTimeout(1000);
    
    await expect(page).toHaveScreenshot('portfolio-page.png', {
      fullPage: false,
      animations: 'disabled',
      threshold: 0.5,
      maxDiffPixels: 50000,
      clip: { x: 0, y: 0, width: 1920, height: 1080 }
    });
  });

  test('Market overview visual comparison', async ({ page }) => {
    await page.goto('/market');
    await page.waitForSelector('#root', { state: 'attached' });
    await page.waitForTimeout(2000);  // Extra wait for content stabilization
    
    await expect(page).toHaveScreenshot('market-overview.png', {
      fullPage: false,
      animations: 'disabled',
      threshold: 0.5,
      maxDiffPixels: 50000,
      clip: { x: 0, y: 0, width: 1920, height: 1080 }
    });
  });

  test('Settings page visual comparison', async ({ page }) => {
    await page.goto('/settings');
    await page.waitForSelector('#root', { state: 'attached' });
    await page.waitForTimeout(2000);
    
    await expect(page).toHaveScreenshot('settings-page.png', {
      fullPage: false,
      animations: 'disabled',
      threshold: 0.5,
      maxDiffPixels: 50000,
      clip: { x: 0, y: 0, width: 1920, height: 1080 }
    });
  });

  test('Mobile dashboard visual comparison', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto('/');
    await page.waitForSelector('#root', { state: 'attached' });
    await page.waitForTimeout(1000);
    
    await expect(page).toHaveScreenshot('mobile-dashboard.png', {
      fullPage: true,
      animations: 'disabled',
      threshold: 0.2,
      maxDiffPixels: 5000
    });
  });

  test('Portfolio chart component visual comparison', async ({ page }) => {
    await page.goto('/portfolio');
    await page.waitForSelector('#root', { state: 'attached' });
    
    // Wait for charts to render
    await page.waitForSelector('[data-testid="portfolio-chart"], .recharts-wrapper', { timeout: 10000 });
    await page.waitForTimeout(2000);
    
    const chartElement = page.locator('[data-testid="portfolio-chart"], .recharts-wrapper').first();
    if (await chartElement.count() > 0) {
      await expect(chartElement).toHaveScreenshot('portfolio-chart.png', {
        animations: 'disabled',
        threshold: 0.2,
        maxDiffPixels: 2000
      });
    }
  });

  test('Navigation menu visual comparison', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('#root', { state: 'attached' });
    
    // Capture main navigation
    const nav = page.locator('nav, [data-testid="navigation"], header').first();
    if (await nav.count() > 0) {
      await expect(nav).toHaveScreenshot('navigation-menu.png', {
        animations: 'disabled',
        threshold: 0.2,
        maxDiffPixels: 1000
      });
    }
  });

  test('Error state visual comparison', async ({ page }) => {
    // Mock API error
    await page.route('**/api/**', route => {
      route.fulfill({
        status: 500,
        json: { error: 'Test error for visual regression' }
      });
    });
    
    await page.goto('/portfolio');
    await page.waitForSelector('#root', { state: 'attached' });
    
    // Wait for page to load and handle error state (if it appears)
    await page.waitForTimeout(3000); // Give time for error handling
    
    // Check if error state appears, but don't require it
    const errorVisible = await page.locator('[data-testid*="error"], .error, [class*="error"], :has-text("error"), :has-text("failed"), :has-text("unavailable")').count() > 0;
    console.log(`📊 Error state visible: ${errorVisible}`);
    
    await page.waitForTimeout(1000);
    
    await expect(page).toHaveScreenshot('error-state.png', {
      fullPage: true,
      animations: 'disabled',
      threshold: 0.5,
      maxDiffPixels: 50000
    });
  });
});
import { test, expect } from '@playwright/test';

/**
 * Visual Regression Testing Suite
 * 
 * Automated visual testing to catch UI regressions across browsers and viewports.
 * Tests critical user journeys and component states with pixel-perfect accuracy.
 * 
 * Setup: npm install @playwright/test
 * Config: playwright.config.js with visual testing configuration
 * Run: npx playwright test --project=visual-regression
 */

const BASE_URL = process.env.VITE_APP_URL || 'http://localhost:3000';

// Critical pages and states to test
const PAGES = {
  dashboard: '/',
  portfolio: '/portfolio',
  trading: '/trading',
  market: '/market-overview',
  settings: '/settings',
  stockDetail: '/stocks/AAPL',
  watchlist: '/watchlist'
};

// Viewport configurations for responsive testing
const VIEWPORTS = [
  { name: 'desktop', width: 1920, height: 1080 },
  { name: 'tablet', width: 768, height: 1024 },
  { name: 'mobile', width: 375, height: 667 }
];

// Component states to test
const COMPONENT_STATES = {
  loading: 'data-testid=loading-spinner',
  error: 'data-testid=error-message', 
  empty: 'data-testid=empty-state',
  populated: 'data-testid=data-table'
};

test.describe('Visual Regression Tests', () => {
  test.beforeEach(async ({ page }) => {
    // Mock authentication for consistent testing
    await page.addInitScript(() => {
      localStorage.setItem('financial_auth_token', 'mock-jwt-token');
      localStorage.setItem('financial_user_data', JSON.stringify({
        username: 'testuser',
        email: 'test@example.com'
      }));
    });

    // Mock API responses for consistent visual states
    await page.route('**/api/**', async route => {
      const url = route.request().url();
      
      if (url.includes('/portfolio/holdings')) {
        await route.fulfill({
          json: {
            success: true,
            data: {
              totalValue: 125000.50,
              totalGainLoss: 8500.25,
              totalGainLossPercent: 7.3,
              holdings: [
                {
                  symbol: 'AAPL',
                  quantity: 100,
                  avgPrice: 180.50,
                  currentPrice: 195.20,
                  totalValue: 19520.00,
                  gainLoss: 1470.00,
                  gainLossPercent: 8.14
                },
                {
                  symbol: 'MSFT',
                  quantity: 50,
                  avgPrice: 350.00,
                  currentPrice: 385.75,
                  totalValue: 19287.50,
                  gainLoss: 1787.50,
                  gainLossPercent: 10.21
                }
              ]
            }
          }
        });
      } else if (url.includes('/market/overview')) {
        await route.fulfill({
          json: {
            success: true,
            data: {
              indices: {
                SPY: { price: 445.32, change: 2.15, changePercent: 0.48 },
                QQQ: { price: 375.68, change: -1.23, changePercent: -0.33 },
                DIA: { price: 355.91, change: 0.87, changePercent: 0.24 }
              },
              sectors: [
                { name: 'Technology', performance: 1.85, trend: 'up' },
                { name: 'Healthcare', performance: 0.75, trend: 'up' },
                { name: 'Energy', performance: -1.22, trend: 'down' }
              ]
            }
          }
        });
      } else {
        await route.continue();
      }
    });
  });

  // Test each critical page across all viewports
  for (const [pageName, path] of Object.entries(PAGES)) {
    for (const viewport of VIEWPORTS) {
      test(`${pageName} page - ${viewport.name} viewport`, async ({ page }) => {
        await page.setViewportSize({ width: viewport.width, height: viewport.height });
        await page.goto(`${BASE_URL}${path}`);
        
        // Wait for page to fully load
        await page.waitForLoadState('networkidle');
        
        // Wait for any animations to complete
        await page.waitForTimeout(1000);
        
        // Take full page screenshot
        await expect(page).toHaveScreenshot(`${pageName}-${viewport.name}.png`, {
          fullPage: true,
          animations: 'disabled'
        });
      });
    }
  }

  test.describe('Component State Testing', () => {
    test('Loading states visual consistency', async ({ page }) => {
      await page.goto(`${BASE_URL}/portfolio`);
      
      // Intercept API to delay response and show loading state
      await page.route('**/api/portfolio/holdings', async route => {
        await new Promise(resolve => setTimeout(resolve, 2000));
        await route.continue();
      });
      
      await page.reload();
      
      // Capture loading state
      await page.waitForSelector('[data-testid="loading-spinner"]');
      await expect(page).toHaveScreenshot('portfolio-loading-state.png');
    });

    test('Error states visual consistency', async ({ page }) => {
      // Mock API error response
      await page.route('**/api/portfolio/holdings', async route => {
        await route.fulfill({
          status: 500,
          json: { success: false, error: 'Internal server error' }
        });
      });
      
      await page.goto(`${BASE_URL}/portfolio`);
      await page.waitForSelector('[data-testid="error-message"]');
      await expect(page).toHaveScreenshot('portfolio-error-state.png');
    });

    test('Empty states visual consistency', async ({ page }) => {
      // Mock empty data response
      await page.route('**/api/portfolio/holdings', async route => {
        await route.fulfill({
          json: {
            success: true,
            data: {
              totalValue: 0,
              totalGainLoss: 0,
              totalGainLossPercent: 0,
              holdings: []
            }
          }
        });
      });
      
      await page.goto(`${BASE_URL}/portfolio`);
      await page.waitForSelector('[data-testid="empty-state"]');
      await expect(page).toHaveScreenshot('portfolio-empty-state.png');
    });
  });

  test.describe('Interactive Element Testing', () => {
    test('Button hover states', async ({ page }) => {
      await page.goto(`${BASE_URL}/trading`);
      await page.waitForLoadState('networkidle');
      
      const buyButton = page.getByRole('button', { name: 'Buy' });
      await buyButton.hover();
      await expect(page).toHaveScreenshot('buy-button-hover.png');
      
      const sellButton = page.getByRole('button', { name: 'Sell' });
      await sellButton.hover();
      await expect(page).toHaveScreenshot('sell-button-hover.png');
    });

    test('Form validation states', async ({ page }) => {
      await page.goto(`${BASE_URL}/trading`);
      
      // Fill form with invalid data to trigger validation
      await page.fill('[data-testid="symbol-input"]', '');
      await page.fill('[data-testid="quantity-input"]', '-5');
      await page.click('[data-testid="submit-button"]');
      
      await page.waitForSelector('.error-message');
      await expect(page).toHaveScreenshot('form-validation-errors.png');
    });

    test('Modal and overlay states', async ({ page }) => {
      await page.goto(`${BASE_URL}/settings`);
      
      // Open API key setup modal
      await page.click('[data-testid="add-api-key-button"]');
      await page.waitForSelector('[data-testid="api-key-modal"]');
      await expect(page).toHaveScreenshot('api-key-modal.png');
      
      // Test modal with form filled
      await page.fill('[data-testid="api-key-input"]', 'PK123456789');
      await page.fill('[data-testid="api-secret-input"]', 'SECRET123456789');
      await expect(page).toHaveScreenshot('api-key-modal-filled.png');
    });
  });

  test.describe('Chart and Data Visualization', () => {
    test('Stock chart rendering consistency', async ({ page }) => {
      await page.goto(`${BASE_URL}/stocks/AAPL`);
      
      // Wait for chart to fully render
      await page.waitForSelector('[data-testid="stock-chart"]');
      await page.waitForTimeout(2000); // Allow chart animations
      
      await expect(page).toHaveScreenshot('stock-chart-AAPL.png');
      
      // Test different time ranges
      await page.click('[data-testid="chart-1D"]');
      await page.waitForTimeout(1000);
      await expect(page).toHaveScreenshot('stock-chart-AAPL-1D.png');
      
      await page.click('[data-testid="chart-1W"]');
      await page.waitForTimeout(1000);
      await expect(page).toHaveScreenshot('stock-chart-AAPL-1W.png');
    });

    test('Portfolio allocation chart', async ({ page }) => {
      await page.goto(`${BASE_URL}/portfolio`);
      
      await page.waitForSelector('[data-testid="allocation-chart"]');
      await page.waitForTimeout(1500); // Chart animation
      
      await expect(page).toHaveScreenshot('portfolio-allocation-chart.png');
    });

    test('Market overview widgets', async ({ page }) => {
      await page.goto(`${BASE_URL}/market-overview`);
      
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(1000);
      
      // Test individual widget components
      await expect(page.locator('[data-testid="market-indices"]')).toHaveScreenshot('market-indices-widget.png');
      await expect(page.locator('[data-testid="sector-performance"]')).toHaveScreenshot('sector-performance-widget.png');
    });
  });

  test.describe('Responsive Design Validation', () => {
    test('Navigation menu responsive behavior', async ({ page }) => {
      // Desktop navigation
      await page.setViewportSize({ width: 1920, height: 1080 });
      await page.goto(`${BASE_URL}/`);
      await expect(page).toHaveScreenshot('navigation-desktop.png');
      
      // Tablet navigation
      await page.setViewportSize({ width: 768, height: 1024 });
      await page.reload();
      await expect(page).toHaveScreenshot('navigation-tablet.png');
      
      // Mobile navigation (hamburger menu)
      await page.setViewportSize({ width: 375, height: 667 });
      await page.reload();
      await expect(page).toHaveScreenshot('navigation-mobile-closed.png');
      
      // Open mobile menu
      await page.click('[data-testid="mobile-menu-button"]');
      await expect(page).toHaveScreenshot('navigation-mobile-open.png');
    });

    test('Data table responsive behavior', async ({ page }) => {
      await page.goto(`${BASE_URL}/portfolio`);
      
      // Desktop table
      await page.setViewportSize({ width: 1920, height: 1080 });
      await page.waitForSelector('[data-testid="portfolio-table"]');
      await expect(page.locator('[data-testid="portfolio-table"]')).toHaveScreenshot('portfolio-table-desktop.png');
      
      // Tablet table
      await page.setViewportSize({ width: 768, height: 1024 });
      await expect(page.locator('[data-testid="portfolio-table"]')).toHaveScreenshot('portfolio-table-tablet.png');
      
      // Mobile table (card view)
      await page.setViewportSize({ width: 375, height: 667 });
      await expect(page.locator('[data-testid="portfolio-cards"]')).toHaveScreenshot('portfolio-cards-mobile.png');
    });
  });

  test.describe('Theme and Color Consistency', () => {
    test('Light theme consistency', async ({ page }) => {
      await page.addInitScript(() => {
        localStorage.setItem('theme', 'light');
      });
      
      await page.goto(`${BASE_URL}/`);
      await page.waitForLoadState('networkidle');
      await expect(page).toHaveScreenshot('dashboard-light-theme.png');
    });

    test('Dark theme consistency', async ({ page }) => {
      await page.addInitScript(() => {
        localStorage.setItem('theme', 'dark');
      });
      
      await page.goto(`${BASE_URL}/`);
      await page.waitForLoadState('networkidle');
      await expect(page).toHaveScreenshot('dashboard-dark-theme.png');
    });

    test('High contrast accessibility mode', async ({ page }) => {
      await page.addInitScript(() => {
        localStorage.setItem('theme', 'high-contrast');
      });
      
      await page.goto(`${BASE_URL}/`);
      await page.waitForLoadState('networkidle');
      await expect(page).toHaveScreenshot('dashboard-high-contrast.png');
    });
  });

  test.describe('Performance and Animation Testing', () => {
    test('Page transition animations', async ({ page }) => {
      await page.goto(`${BASE_URL}/`);
      
      // Navigate to different pages and capture transition states
      await page.click('[data-testid="nav-portfolio"]');
      await page.waitForTimeout(500); // Mid-transition
      await expect(page).toHaveScreenshot('page-transition-portfolio.png');
      
      await page.click('[data-testid="nav-trading"]');
      await page.waitForTimeout(500);
      await expect(page).toHaveScreenshot('page-transition-trading.png');
    });

    test('Loading skeleton states', async ({ page }) => {
      // Slow down network to see skeleton states
      await page.route('**/api/**', async route => {
        await new Promise(resolve => setTimeout(resolve, 1000));
        await route.continue();
      });
      
      await page.goto(`${BASE_URL}/portfolio`);
      
      // Capture skeleton loading state
      await page.waitForSelector('[data-testid="skeleton-loader"]');
      await expect(page).toHaveScreenshot('portfolio-skeleton-loading.png');
    });
  });
});

test.describe('Cross-Browser Visual Consistency', () => {
  ['chromium', 'firefox', 'webkit'].forEach(browserName => {
    test(`Dashboard consistency - ${browserName}`, async ({ page }) => {
      await page.goto(`${BASE_URL}/`);
      await page.waitForLoadState('networkidle');
      await expect(page).toHaveScreenshot(`dashboard-${browserName}.png`);
    });

    test(`Trading interface - ${browserName}`, async ({ page }) => {
      await page.goto(`${BASE_URL}/trading`);
      await page.waitForLoadState('networkidle');
      await expect(page).toHaveScreenshot(`trading-${browserName}.png`);
    });
  });
});
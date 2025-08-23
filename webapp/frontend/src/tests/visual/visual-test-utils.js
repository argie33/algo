/**
 * Visual Testing Utilities
 * 
 * Common utilities and helpers for visual regression testing.
 * Provides consistent mocking, data setup, and screenshot comparison.
 */

import { expect } from '@playwright/test';

/**
 * Standard viewport configurations for responsive testing
 */
export const VIEWPORTS = {
  desktop: { width: 1920, height: 1080 },
  desktopLarge: { width: 2560, height: 1440 },
  laptop: { width: 1366, height: 768 },
  tablet: { width: 1024, height: 768 },
  tabletPortrait: { width: 768, height: 1024 },
  mobile: { width: 375, height: 667 },
  mobileLarge: { width:414, height: 896 },
  mobileSmall: { width: 320, height: 568 }
};

/**
 * Standard test data for consistent visual states
 */
export const MOCK_DATA = {
  portfolioHoldings: {
    success: true,
    data: {
      totalValue: 125000.50,
      totalGainLoss: 8500.25,
      totalGainLossPercent: 7.3,
      dayGainLoss: 350.75,
      dayGainLossPercent: 0.28,
      holdings: [
        {
          symbol: 'AAPL',
          quantity: 100,
          avgPrice: 180.50,
          currentPrice: 195.20,
          totalValue: 19520.00,
          gainLoss: 1470.00,
          gainLossPercent: 8.14,
          sector: 'Technology',
          lastUpdated: '2024-01-15T10:30:00Z'
        },
        {
          symbol: 'MSFT',
          quantity: 50,
          avgPrice: 350.00,
          currentPrice: 385.75,
          totalValue: 19287.50,
          gainLoss: 1787.50,
          gainLossPercent: 10.21,
          sector: 'Technology',
          lastUpdated: '2024-01-15T10:30:00Z'
        },
        {
          symbol: 'GOOGL',
          quantity: 25,
          avgPrice: 2400.00,
          currentPrice: 2650.75,
          totalValue: 66268.75,
          gainLoss: 6268.75,
          gainLossPercent: 10.45,
          sector: 'Technology',
          lastUpdated: '2024-01-15T10:30:00Z'
        }
      ]
    }
  },

  marketOverview: {
    success: true,
    data: {
      indices: {
        SPY: { price: 445.32, change: 2.15, changePercent: 0.48, volume: 45000000 },
        QQQ: { price: 375.68, change: -1.23, changePercent: -0.33, volume: 28000000 },
        DIA: { price: 355.91, change: 0.87, changePercent: 0.24, volume: 15000000 }
      },
      sectors: [
        { name: 'Technology', performance: 1.85, trend: 'up', volume: 850000000 },
        { name: 'Healthcare', performance: 0.75, trend: 'up', volume: 620000000 },
        { name: 'Financials', performance: 0.45, trend: 'up', volume: 580000000 },
        { name: 'Consumer Discretionary', performance: -0.25, trend: 'down', volume: 490000000 },
        { name: 'Energy', performance: -1.22, trend: 'down', volume: 320000000 }
      ],
      marketSentiment: 'bullish',
      vixLevel: 18.5,
      lastUpdated: '2024-01-15T10:30:00Z'
    }
  },

  stockPrice: (symbol) => ({
    success: true,
    data: {
      symbol: symbol,
      price: 195.20,
      change: 2.15,
      changePercent: 1.11,
      volume: 25000000,
      high: 197.50,
      low: 192.80,
      open: 193.40,
      previousClose: 193.05,
      marketCap: 3000000000000,
      peRatio: 28.5,
      dividendYield: 0.52,
      lastUpdated: '2024-01-15T10:30:00Z'
    }
  }),

  watchlists: {
    success: true,
    data: {
      watchlists: [
        {
          id: 1,
          name: 'Tech Stocks',
          symbols: ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA'],
          createdAt: '2024-01-01T00:00:00Z',
          updatedAt: '2024-01-15T10:00:00Z'
        },
        {
          id: 2,
          name: 'Dividend Stocks',
          symbols: ['JNJ', 'PG', 'KO', 'PEP'],
          createdAt: '2024-01-02T00:00:00Z',
          updatedAt: '2024-01-10T15:30:00Z'
        }
      ]
    }
  }
};

/**
 * Setup consistent authentication state for visual testing
 */
export async function setupAuthenticatedUser(page) {
  await page.addInitScript(() => {
    localStorage.setItem('financial_auth_token', 'visual-test-token');
    localStorage.setItem('financial_user_data', JSON.stringify({
      username: 'visualtest',
      email: 'visual@test.com',
      name: 'Visual Test User',
      id: 'visual-test-user-id'
    }));
  });
}

/**
 * Setup consistent theme and preferences
 */
export async function setupUserPreferences(page, theme = 'light') {
  await page.addInitScript((theme) => {
    localStorage.setItem('theme', theme);
    localStorage.setItem('user_preferences', JSON.stringify({
      currency: 'USD',
      timezone: 'America/New_York',
      dateFormat: 'MM/DD/YYYY',
      numberFormat: 'en-US',
      theme: theme
    }));
  }, theme);
}

/**
 * Setup API key status for consistent visual state
 */
export async function setupApiKeyStatus(page, status = 'configured') {
  await page.addInitScript((status) => {
    const statusData = status === 'configured' 
      ? {
          alpaca: { configured: true, valid: true },
          polygon: { configured: true, valid: true },
          finnhub: { configured: true, valid: true }
        }
      : {
          alpaca: { configured: false, valid: false },
          polygon: { configured: false, valid: false },
          finnhub: { configured: false, valid: false }
        };
    
    localStorage.setItem('api_keys_status', JSON.stringify(statusData));
  }, status);
}

/**
 * Setup API route mocking for consistent data
 */
export async function setupApiMocks(page) {
  await page.route('**/api/**', async (route) => {
    const url = route.request().url();
    const method = route.request().method();
    
    // Portfolio endpoints
    if (url.includes('/portfolio/holdings')) {
      await route.fulfill({ json: MOCK_DATA.portfolioHoldings });
    } 
    // Market data endpoints
    else if (url.includes('/market/overview')) {
      await route.fulfill({ json: MOCK_DATA.marketOverview });
    }
    // Stock price endpoints
    else if (url.includes('/stocks/') && url.includes('/price')) {
      const symbol = url.match(/\/stocks\/([^/]+)/)?.[1] || 'UNKNOWN';
      await route.fulfill({ json: MOCK_DATA.stockPrice(symbol) });
    }
    // Watchlist endpoints
    else if (url.includes('/watchlist')) {
      await route.fulfill({ json: MOCK_DATA.watchlists });
    }
    // Settings endpoints
    else if (url.includes('/settings/api-keys')) {
      await route.fulfill({
        json: {
          success: true,
          data: {
            configured: ['alpaca', 'polygon', 'finnhub'],
            valid: ['alpaca', 'polygon', 'finnhub']
          }
        }
      });
    }
    // Health check endpoint
    else if (url.includes('/health')) {
      await route.fulfill({
        json: {
          success: true,
          data: {
            status: 'healthy',
            database: 'connected',
            timestamp: '2024-01-15T10:30:00Z'
          }
        }
      });
    }
    // Default fallback
    else {
      await route.continue();
    }
  });
}

/**
 * Wait for page to be fully loaded and stable for screenshots
 */
export async function waitForPageStable(page, timeout = 3000) {
  // Wait for network idle
  await page.waitForLoadState('networkidle');
  
  // Wait for fonts to load
  await page.waitForFunction(() => document.fonts.ready);
  
  // Wait for any animations to complete
  await page.waitForTimeout(1000);
  
  // Wait for charts and dynamic content
  await page.waitForFunction(() => {
    const loadingElements = document.querySelectorAll('[data-testid*="loading"], .loading, .skeleton');
    return loadingElements.length === 0;
  }, { timeout: timeout });
  
  // Additional stability wait
  await page.waitForTimeout(500);
}

/**
 * Take screenshot with consistent settings
 */
export async function takeConsistentScreenshot(page, name, options = {}) {
  const defaultOptions = {
    fullPage: true,
    animations: 'disabled',
    caret: 'hide',
    ...options
  };
  
  await expect(page).toHaveScreenshot(`${name}.png`, defaultOptions);
}

/**
 * Take element screenshot with consistent settings
 */
export async function takeElementScreenshot(page, selector, name, options = {}) {
  const element = page.locator(selector);
  await element.waitFor({ state: 'visible' });
  
  const defaultOptions = {
    animations: 'disabled',
    caret: 'hide',
    ...options
  };
  
  await expect(element).toHaveScreenshot(`${name}.png`, defaultOptions);
}

/**
 * Setup responsive viewport testing
 */
export async function testResponsiveViewports(page, testFn, viewports = ['desktop', 'tablet', 'mobile']) {
  for (const viewportName of viewports) {
    const viewport = VIEWPORTS[viewportName];
    if (!viewport) {
      throw new Error(`Unknown viewport: ${viewportName}`);
    }
    
    await page.setViewportSize(viewport);
    await page.waitForTimeout(500); // Allow layout to settle
    await testFn(viewportName);
  }
}

/**
 * Test component states (loading, error, empty, populated)
 */
export async function testComponentStates(page, baseUrl, testCases) {
  for (const [stateName, setupFn] of Object.entries(testCases)) {
    await setupFn(page);
    await page.goto(baseUrl);
    await waitForPageStable(page);
    await takeConsistentScreenshot(page, `component-${stateName}-state`);
  }
}

/**
 * Test form interactions and validation states
 */
export async function testFormStates(page, formSelector, testCases) {
  for (const [stateName, interaction] of Object.entries(testCases)) {
    await interaction(page);
    await takeElementScreenshot(page, formSelector, `form-${stateName}-state`);
  }
}

/**
 * Test hover and focus states for interactive elements
 */
export async function testInteractiveStates(page, selector, name) {
  const element = page.locator(selector);
  
  // Default state
  await takeElementScreenshot(page, selector, `${name}-default`);
  
  // Hover state
  await element.hover();
  await page.waitForTimeout(200);
  await takeElementScreenshot(page, selector, `${name}-hover`);
  
  // Focus state (if focusable)
  try {
    await element.focus();
    await page.waitForTimeout(200);
    await takeElementScreenshot(page, selector, `${name}-focus`);
  } catch (error) {
    // Element not focusable, skip
  }
  
  // Reset state
  await page.mouse.move(0, 0);
  await page.keyboard.press('Escape');
}

/**
 * Disable animations and transitions for consistent screenshots
 */
export async function disableAnimations(page) {
  await page.addStyleTag({
    content: `
      *, *::before, *::after {
        animation-duration: 0s !important;
        animation-delay: 0s !important;
        transition-duration: 0s !important;
        transition-delay: 0s !important;
        caret-color: transparent !important;
      }
    `
  });
}

/**
 * Force consistent font rendering
 */
export async function setupConsistentFonts(page) {
  await page.addStyleTag({
    content: `
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
      * {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
        -webkit-font-smoothing: antialiased !important;
        -moz-osx-font-smoothing: grayscale !important;
      }
    `
  });
}
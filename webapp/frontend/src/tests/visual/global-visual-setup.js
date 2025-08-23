/**
 * Global Visual Testing Setup
 * 
 * Prepares the testing environment for consistent visual regression testing.
 * Sets up mock data, authentication, and system state.
 */

import { chromium } from '@playwright/test';

export default async function globalSetup() {
  console.log('🎨 Setting up visual regression testing environment...');
  
  // Launch browser for setup operations
  const browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();
  
  try {
    // Wait for development server to be ready
    const baseURL = process.env.VITE_APP_URL || 'http://localhost:3000';
    console.log(`📡 Waiting for application at ${baseURL}...`);
    
    let retries = 30;
    while (retries > 0) {
      try {
        await page.goto(baseURL, { timeout: 5000 });
        break;
      } catch (error) {
        retries--;
        if (retries === 0) {
          throw new Error(`Application not ready at ${baseURL} after 150 seconds`);
        }
        await new Promise(resolve => setTimeout(resolve, 5000));
      }
    }
    
    console.log('✅ Application server is ready');
    
    // Set up consistent test data
    await setupConsistentState(page);
    
    // Ensure fonts are loaded for consistent rendering
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
    
    // Preload critical resources for consistent rendering
    await page.evaluate(() => {
      // Preload common images and assets
      const imagePaths = [
        '/logo.png',
        '/favicon.ico'
      ];
      
      imagePaths.forEach(path => {
        const img = new Image();
        img.src = path;
      });
      
      // Force font loading
      document.fonts.ready.then(() => {
        console.log('Fonts loaded for visual testing');
      });
    });
    
    console.log('🎨 Visual regression setup completed successfully');
    
  } catch (error) {
    console.error('❌ Visual regression setup failed:', error);
    throw error;
  } finally {
    await browser.close();
  }
}

async function setupConsistentState(page) {
  console.log('🔧 Setting up consistent application state...');
  
  // Set consistent authentication state
  await page.addInitScript(() => {
    // Mock authentication
    localStorage.setItem('financial_auth_token', 'visual-test-token');
    localStorage.setItem('financial_user_data', JSON.stringify({
      username: 'visualtest',
      email: 'visual@test.com',
      name: 'Visual Test User',
      id: 'visual-test-user-id'
    }));
    
    // Set consistent theme
    localStorage.setItem('theme', 'light');
    
    // Set consistent user preferences
    localStorage.setItem('user_preferences', JSON.stringify({
      currency: 'USD',
      timezone: 'America/New_York',
      dateFormat: 'MM/DD/YYYY',
      numberFormat: 'en-US'
    }));
    
    // Mock API keys for consistent state
    localStorage.setItem('api_keys_status', JSON.stringify({
      alpaca: { configured: true, valid: true },
      polygon: { configured: true, valid: true },
      finnhub: { configured: true, valid: true }
    }));
  });
  
  // Set up consistent API mocks
  await page.route('**/api/**', async (route) => {
    const url = route.request().url();
    const method = route.request().method();
    
    // Provide consistent mock data for visual testing
    if (url.includes('/portfolio/holdings')) {
      await route.fulfill({
        json: {
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
                sector: 'Technology'
              },
              {
                symbol: 'MSFT',
                quantity: 50,
                avgPrice: 350.00,
                currentPrice: 385.75,
                totalValue: 19287.50,
                gainLoss: 1787.50,
                gainLossPercent: 10.21,
                sector: 'Technology'
              },
              {
                symbol: 'GOOGL',
                quantity: 25,
                avgPrice: 2400.00,
                currentPrice: 2650.75,
                totalValue: 66268.75,
                gainLoss: 6268.75,
                gainLossPercent: 10.45,
                sector: 'Technology'
              },
              {
                symbol: 'TSLA',
                quantity: 75,
                avgPrice: 220.00,
                currentPrice: 245.80,
                totalValue: 18435.00,
                gainLoss: 1935.00,
                gainLossPercent: 11.73,
                sector: 'Consumer Discretionary'
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
            vixLevel: 18.5
          }
        }
      });
    } else if (url.includes('/stocks/') && url.includes('/price')) {
      const symbol = url.match(/\/stocks\/([^/]+)/)?.[1] || 'UNKNOWN';
      await route.fulfill({
        json: {
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
            dividendYield: 0.52
          }
        }
      });
    } else if (url.includes('/watchlist')) {
      await route.fulfill({
        json: {
          success: true,
          data: {
            watchlists: [
              {
                id: 1,
                name: 'Tech Stocks',
                symbols: ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA'],
                createdAt: '2024-01-01T00:00:00Z'
              },
              {
                id: 2,
                name: 'Dividend Stocks',
                symbols: ['JNJ', 'PG', 'KO', 'PEP'],
                createdAt: '2024-01-02T00:00:00Z'
              }
            ]
          }
        }
      });
    } else {
      // Default fallback for other endpoints
      await route.continue();
    }
  });
  
  console.log('✅ Application state setup completed');
}
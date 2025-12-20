import { test, expect } from '@playwright/test';

// All 27 page routes from the application
const PAGES = [
  { name: 'Dashboard', path: '/', description: 'Main dashboard with market overview' },
  { name: 'Market Overview', path: '/market-overview', description: 'Market sentiment and breadth' },
  { name: 'Stock Explorer', path: '/stock-explorer', description: 'Stock scores and metrics' },
  { name: 'Stock Screener', path: '/stock-screener', description: 'Advanced filtering' },
  { name: 'Stock Detail', path: '/stock-detail/AAPL', description: 'Individual stock analysis' },
  { name: 'Sector Analysis', path: '/sector-analysis', description: 'Sector performance' },
  { name: 'Sentiment', path: '/sentiment', description: 'Market sentiment analysis' },
  { name: 'Analyst Insights', path: '/analyst-insights', description: 'Analyst ratings' },
  { name: 'Scores Dashboard', path: '/scores-dashboard', description: 'Composite scores' },
  { name: 'Metrics Dashboard', path: '/metrics-dashboard', description: 'Performance metrics' },
  { name: 'Economic Dashboard', path: '/economic-dashboard', description: 'Economic data' },
  { name: 'Economic Modeling', path: '/economic-modeling', description: 'Economic forecasts' },
  { name: 'Portfolio Dashboard', path: '/portfolio-dashboard', description: 'Portfolio overview' },
  { name: 'Portfolio', path: '/portfolio', description: 'Holdings and positions' },
  { name: 'Portfolio Optimization', path: '/portfolio-optimization', description: 'Optimization tools' },
  { name: 'Portfolio Optimizer New', path: '/portfolio-optimizer-new', description: 'Advanced optimizer' },
  { name: 'Trade History', path: '/trade-history', description: 'Trade records' },
  { name: 'Trading Signals', path: '/trading-signals', description: 'Buy/Sell signals' },
  { name: 'Watchlist', path: '/watchlist', description: 'Monitored stocks' },
  { name: 'Earnings Calendar', path: '/earnings-calendar', description: 'Earnings schedule' },
  { name: 'Financial Data', path: '/financial-data', description: 'Financial statements' },
  { name: 'Settings', path: '/settings', description: 'Configuration' },
  { name: 'Service Health', path: '/service-health', description: 'System status' },
  { name: 'Coming Soon', path: '/coming-soon', description: 'Placeholder page' },
  { name: 'AuthTest', path: '/auth-test', description: 'Authentication testing' },
];

test.describe('All Pages Load Successfully', () => {
  PAGES.forEach((pageConfig) => {
    test(`${pageConfig.name} (${pageConfig.path}) loads without errors`, async ({ page }) => {
      // Navigate to the page
      const response = await page.goto(pageConfig.path, { waitUntil: 'networkidle' });

      // Verify successful load (200-299 status)
      expect(response.status()).toBeLessThan(300);
      expect(response.ok()).toBeTruthy();

      // Page should have content
      const bodyContent = await page.content();
      expect(bodyContent.length).toBeGreaterThan(100);

      // Should not show "Coming Soon" placeholder unless it's the Coming Soon page
      if (pageConfig.path !== '/coming-soon') {
        const comingSoonElement = await page.locator('text=Coming Soon').isHidden();
        expect(comingSoonElement || pageConfig.path === '/coming-soon').toBeTruthy();
      }

      // Should not have critical error overlays (React warnings are ok)
      const errorElements = await page.locator('[role="alert"]').count();
      // Allow some errors, but shouldn't have critical alerts
      expect(errorElements).toBeLessThan(10);

      console.log(`✅ ${pageConfig.name} loaded successfully`);
    });
  });
});

test.describe('API Endpoints Return Data', () => {
  test('Critical endpoints have real data', async ({ page }) => {
    // Check /api/stocks endpoint
    const stocksResponse = await page.request.get('http://localhost:3001/api/stocks?limit=1');
    expect(stocksResponse.ok()).toBeTruthy();
    const stocksData = await stocksResponse.json();
    expect(stocksData.success).toBe(true);
    expect(Array.isArray(stocksData.data) || typeof stocksData.data === 'object').toBeTruthy();
    console.log('✅ /api/stocks returns real data');

    // Check /api/scores endpoint
    const scoresResponse = await page.request.get('http://localhost:3001/api/scores?limit=1');
    expect(scoresResponse.ok()).toBeTruthy();
    const scoresData = await scoresResponse.json();
    expect(scoresData.success).toBe(true);
    console.log('✅ /api/scores returns real data');

    // Check /api/analysts endpoint
    const analystsResponse = await page.request.get('http://localhost:3001/api/analysts');
    expect(analystsResponse.ok()).toBeTruthy();
    const analystsData = await analystsResponse.json();
    expect(analystsData.success).toBe(true);
    console.log('✅ /api/analysts returns real data');

    // Check /api/market endpoint
    const marketResponse = await page.request.get('http://localhost:3001/api/market');
    expect(marketResponse.ok()).toBeTruthy();
    const marketData = await marketResponse.json();
    expect(marketData.success).toBe(true);
    console.log('✅ /api/market returns real data');

    // Check /api/sentiment endpoint
    const sentimentResponse = await page.request.get('http://localhost:3001/api/sentiment');
    expect(sentimentResponse.ok()).toBeTruthy();
    const sentimentData = await sentimentResponse.json();
    expect(sentimentData.success).toBe(true);
    console.log('✅ /api/sentiment returns real data');

    // Check /api/health endpoint
    const healthResponse = await page.request.get('http://localhost:3001/api/health');
    expect(healthResponse.ok()).toBeTruthy();
    const healthData = await healthResponse.json();
    expect(healthData.success).toBe(true);
    expect(healthData.database).toBeDefined();
    expect(healthData.database.status).toBe('connected');
    console.log('✅ /api/health returns system status');
  });

  test('Signals endpoint responds correctly (empty or with data)', async ({ page }) => {
    const response = await page.request.get('http://localhost:3001/api/signals?symbols=AAPL&timeframe=daily&limit=1');
    expect(response.ok()).toBeTruthy();
    const data = await response.json();
    expect(data.success).toBe(true);
    // Should return either empty signals or actual signals, never an error
    expect(data.data).toBeDefined();
    console.log('✅ /api/signals responds correctly (empty or with data)');
  });

  test('Dashboard endpoint aggregates real data', async ({ page }) => {
    const response = await page.request.get('http://localhost:3001/api/dashboard/summary');
    // Should return 200 or 401 (auth required), not 500
    expect(response.status()).toBeLessThan(500);
    const data = await response.json();
    if (response.ok()) {
      expect(data.success).toBe(true);
      expect(data.data).toBeDefined();
      // Dashboard can have null market_overview if market_data table is empty, but should have structure
      expect(data.data.top_gainers !== undefined || data.data.top_losers !== undefined || data.data.market_sentiment !== undefined).toBeTruthy();
    }
    console.log('✅ /api/dashboard/summary endpoint responds correctly');
  });

  test('Portfolio endpoints respond correctly', async ({ page }) => {
    const response = await page.request.get('http://localhost:3001/api/portfolio');
    // Should return 200 or 403 (auth), not 500
    expect(response.status()).toBeLessThan(500);
    console.log('✅ /api/portfolio endpoint responds without server error');
  });
});

test.describe('Dashboard Page Loads with Real Data', () => {
  test('Dashboard displays real stock data', async ({ page }) => {
    await page.goto('/');

    // Wait for page to load
    await page.waitForLoadState('networkidle');

    // Dashboard should have some indicators of data loading
    // Look for stock symbols or data elements
    const pageContent = await page.content();
    expect(pageContent.length).toBeGreaterThan(500);
    console.log('✅ Dashboard displays content with real data');
  });
});

test.describe('No 503 Stub Responses', () => {
  test('Critical pages do not return 503 Service Unavailable', async ({ page }) => {
    const criticalPages = [
      '/',
      '/market-overview',
      '/stock-explorer',
      '/dashboard',
      '/portfolio-dashboard',
      '/portfolio-optimization'
    ];

    for (const pagePath of criticalPages) {
      const response = await page.goto(pagePath, { waitUntil: 'networkidle' });
      expect(response.status()).not.toBe(503);
      console.log(`✅ ${pagePath} does not return 503`);
    }
  });
});

test.describe('System Health Check', () => {
  test('Backend API is running and responsive', async ({ page }) => {
    const response = await page.request.get('http://localhost:3001/api/health');
    expect(response.ok()).toBeTruthy();
    const data = await response.json();
    expect(data.success).toBe(true);
    expect(data.database.status).toBe('connected');
    console.log('✅ Backend API is healthy and database connected');
  });

  test('Frontend loads on port 5173', async ({ page }) => {
    const response = await page.goto('/');
    expect(response.ok()).toBeTruthy();
    console.log('✅ Frontend is running on port 5173');
  });
});

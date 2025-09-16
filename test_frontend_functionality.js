#!/usr/bin/env node

const { chromium } = require('playwright');
const fs = require('fs');

const FRONTEND_URL = 'http://localhost:3002';
const API_URL = 'http://localhost:3001';

// List of all pages to test (based on the pages directory)
const PAGES_TO_TEST = [
  { name: 'Dashboard', path: '/', hasApiCalls: true },
  { name: 'Market Overview', path: '/market', hasApiCalls: true },
  { name: 'Portfolio', path: '/portfolio', hasApiCalls: true },
  { name: 'Stock Screener', path: '/screener', hasApiCalls: true },
  { name: 'Stock Detail', path: '/stocks/AAPL', hasApiCalls: true },
  { name: 'Technical Analysis', path: '/technical', hasApiCalls: true },
  { name: 'Sentiment Analysis', path: '/sentiment', hasApiCalls: true },
  { name: 'Earnings Calendar', path: '/calendar', hasApiCalls: true },
  { name: 'News Analysis', path: '/news', hasApiCalls: true },
  { name: 'Risk Management', path: '/risk', hasApiCalls: true },
  { name: 'Settings', path: '/settings', hasApiCalls: true },
  { name: 'Backtest', path: '/backtest', hasApiCalls: true },
  { name: 'Scores Dashboard', path: '/scores', hasApiCalls: true },
  { name: 'Sector Analysis', path: '/sectors', hasApiCalls: true },
  { name: 'Real-Time Dashboard', path: '/realtime', hasApiCalls: true },
  { name: 'Economic Modeling', path: '/economic', hasApiCalls: true },
  { name: 'Financial Data', path: '/financials', hasApiCalls: true },
  { name: 'Advanced Screener', path: '/advanced-screener', hasApiCalls: true },
  { name: 'Portfolio Analytics', path: '/portfolio-analytics', hasApiCalls: true },
  { name: 'Order Management', path: '/orders', hasApiCalls: true },
  { name: 'Trade History', path: '/trades', hasApiCalls: true },
  { name: 'Trading Signals', path: '/signals', hasApiCalls: true },
  { name: 'Stock Explorer', path: '/explore', hasApiCalls: true },
  { name: 'Watchlist', path: '/watchlist', hasApiCalls: true },
  { name: 'Service Health', path: '/health', hasApiCalls: true },
  { name: 'Pattern Recognition', path: '/patterns', hasApiCalls: true },
  { name: 'Portfolio Optimization', path: '/optimization', hasApiCalls: true },
  { name: 'AI Assistant', path: '/ai', hasApiCalls: false },
  { name: 'Auth Test', path: '/auth-test', hasApiCalls: true },
  { name: 'Metrics Dashboard', path: '/metrics', hasApiCalls: true },
  { name: 'Market Commentary', path: '/commentary', hasApiCalls: true },
  { name: 'Portfolio Holdings', path: '/holdings', hasApiCalls: true },
  { name: 'Technical History', path: '/technical-history', hasApiCalls: true },
  { name: 'Advanced Portfolio Analytics', path: '/advanced-analytics', hasApiCalls: true }
];

async function testPageFunctionality() {
  console.log('🚀 Starting frontend functionality testing...\n');

  let browser;
  const results = [];
  let totalTests = 0;
  let passedTests = 0;
  let failedTests = 0;

  try {
    // Launch browser
    console.log('🌐 Launching browser...');
    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({
      viewport: { width: 1280, height: 720 },
      ignoreHTTPSErrors: true
    });
    const page = await context.newPage();

    // Track API requests
    const apiRequests = [];
    page.on('request', request => {
      if (request.url().includes(API_URL)) {
        apiRequests.push({
          url: request.url(),
          method: request.method(),
          timestamp: Date.now()
        });
      }
    });

    // Track console errors
    const consoleErrors = [];
    page.on('console', msg => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text());
      }
    });

    // Track page errors
    const pageErrors = [];
    page.on('pageerror', error => {
      pageErrors.push(error.message);
    });

    // Test each page
    for (const pageInfo of PAGES_TO_TEST) {
      totalTests++;
      console.log(`Testing ${totalTests}/${PAGES_TO_TEST.length}: ${pageInfo.name} (${pageInfo.path})`);

      try {
        const startTime = Date.now();

        // Clear previous errors and requests
        apiRequests.length = 0;
        consoleErrors.length = 0;
        pageErrors.length = 0;

        // Navigate to page
        await page.goto(`${FRONTEND_URL}${pageInfo.path}`, {
          waitUntil: 'networkidle',
          timeout: 30000
        });

        // Wait for page to load
        await page.waitForTimeout(2000);

        // Check if page loaded successfully
        const title = await page.title();
        const url = page.url();

        // Check for essential elements (assuming there's always a main content area)
        const hasMainContent = await page.locator('main, #root, .app, [role="main"]').count() > 0;

        // Check for React error boundaries or error messages
        const hasErrorBoundary = await page.locator('[data-testid="error-boundary"], .error-boundary').count() > 0;
        const hasErrorMessage = await page.locator('.error, .error-message, [role="alert"]').count() > 0;

        const endTime = Date.now();
        const loadTime = endTime - startTime;

        // Determine if page is working
        const isWorking = !hasErrorBoundary && !hasErrorMessage && hasMainContent &&
                          title && title !== 'Error' && !title.includes('404') &&
                          consoleErrors.length === 0 && pageErrors.length === 0;

        const result = {
          name: pageInfo.name,
          path: pageInfo.path,
          status: isWorking ? 'PASS' : 'FAIL',
          loadTime: `${loadTime}ms`,
          title: title || 'No title',
          url: url,
          hasMainContent,
          apiRequestCount: apiRequests.length,
          consoleErrors: consoleErrors.length,
          pageErrors: pageErrors.length,
          expectedApiCalls: pageInfo.hasApiCalls,
          actualApiCalls: apiRequests.length > 0,
          issues: []
        };

        // Add specific issues
        if (hasErrorBoundary) result.issues.push('Error boundary triggered');
        if (hasErrorMessage) result.issues.push('Error message displayed');
        if (!hasMainContent) result.issues.push('No main content area found');
        if (consoleErrors.length > 0) result.issues.push(`${consoleErrors.length} console errors`);
        if (pageErrors.length > 0) result.issues.push(`${pageErrors.length} page errors`);
        if (pageInfo.hasApiCalls && apiRequests.length === 0) result.issues.push('Expected API calls but none made');

        results.push(result);

        if (isWorking) {
          passedTests++;
          console.log(`✅ PASS - ${loadTime}ms - ${apiRequests.length} API calls`);
        } else {
          failedTests++;
          console.log(`❌ FAIL - ${result.issues.join(', ')}`);
        }

        // Brief delay between pages
        await page.waitForTimeout(500);

      } catch (error) {
        failedTests++;
        const result = {
          name: pageInfo.name,
          path: pageInfo.path,
          status: 'ERROR',
          error: error.message,
          issues: ['Navigation or loading error']
        };
        results.push(result);
        console.log(`❌ ERROR - ${error.message}`);
      }
    }

    await browser.close();

  } catch (error) {
    console.error('❌ Browser setup error:', error.message);
    if (browser) await browser.close();
    return;
  }

  // Generate summary report
  const summary = {
    totalPages: totalTests,
    passed: passedTests,
    failed: failedTests,
    successRate: ((passedTests / totalTests) * 100).toFixed(1) + '%',
    timestamp: new Date().toISOString(),
    results: results
  };

  // Save detailed results to file
  fs.writeFileSync('frontend_test_results.json', JSON.stringify(summary, null, 2));

  console.log('\n📊 FRONTEND TEST SUMMARY:');
  console.log(`Total Pages: ${summary.totalPages}`);
  console.log(`Passed: ${summary.passed}`);
  console.log(`Failed: ${summary.failed}`);
  console.log(`Success Rate: ${summary.successRate}`);

  console.log('\n🔍 DETAILED RESULTS:');
  results.forEach(result => {
    if (result.status === 'PASS') {
      console.log(`✅ ${result.name}: PASS (${result.loadTime}) - ${result.apiRequestCount} API calls`);
    } else {
      console.log(`❌ ${result.name}: ${result.status} - ${result.issues?.join(', ') || result.error}`);
    }
  });

  console.log('\n📄 Full results saved to: frontend_test_results.json');

  return summary;
}

// Check if Playwright is available
try {
  require('playwright');
  testPageFunctionality().catch(console.error);
} catch (error) {
  console.log('⚠️ Playwright not available, skipping browser tests');
  console.log('💡 To install Playwright: npm install playwright');
  console.log('💡 Then run: npx playwright install chromium');
}
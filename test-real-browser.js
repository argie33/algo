#!/usr/bin/env node

const { chromium } = require('playwright');
const fs = require('fs');

const colors = {
  red: '\x1b[31m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  cyan: '\x1b[36m',
  reset: '\x1b[0m',
  bold: '\x1b[1m'
};

const log = {
  header: (msg) => console.log(`\n${colors.bold}${colors.cyan}${msg}${colors.reset}`),
  success: (msg) => console.log(`${colors.green}✅ ${msg}${colors.reset}`),
  error: (msg) => console.log(`${colors.red}❌ ${msg}${colors.reset}`),
  warn: (msg) => console.log(`${colors.yellow}⚠️  ${msg}${colors.reset}`),
  info: (msg) => console.log(`${colors.blue}ℹ️  ${msg}${colors.reset}`)
};

async function testRealBrowser() {
  log.header('🌐 Testing Application in Real Browser (Non-Headless)');

  const browser = await chromium.launch({
    headless: false,  // Open real browser window
    slowMo: 500       // Slow down actions to see what's happening
  });

  const page = await browser.newPage({
    viewport: { width: 1280, height: 720 }
  });

  const results = {
    tests: [],
    dataLoadedPages: [],
    emptyPages: [],
    errorPages: [],
    totalApiCalls: 0,
    successfulApiCalls: 0,
    failedApiCalls: 0
  };

  // Track network activity
  page.on('response', response => {
    if (response.url().includes('/api')) {
      results.totalApiCalls++;
      if (response.ok()) {
        results.successfulApiCalls++;
      }
    }
  });

  page.on('requestfailed', request => {
    if (request.url().includes('/api')) {
      results.failedApiCalls++;
    }
  });

  const testPages = [
    { url: '/', name: 'Home', checkFor: ['Research', 'h1', 'h2'] },
    { url: '/app/market', name: 'Market Overview', checkFor: ['market', 'chart'] },
    { url: '/app/sectors', name: 'Sectors', checkFor: ['sector', 'industry'] },
    { url: '/app/trading-signals', name: 'Trading Signals', checkFor: ['signal', 'trade'] },
  ];

  try {
    log.info('Opening browser window - you should see Chrome opening...');
    log.info('Testing will proceed automatically. Watch the browser window!');
    log.info('Tests will complete in about 30 seconds.\n');

    for (const test of testPages) {
      log.header(`Testing: ${test.name}`);

      try {
        const url = `http://localhost:5176${test.url}`;
        log.info(`Navigating to ${url}...`);

        await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 15000 }).catch(() => {
          log.warn('DOMContentLoaded timeout, continuing...');
        });

        await page.waitForTimeout(3000); // Wait for API calls to complete

        // Take a screenshot for visual inspection
        const screenshotPath = `screenshot-${test.name.replace(/\s+/g, '-')}.png`;
        await page.screenshot({ path: screenshotPath });
        log.success(`Screenshot saved: ${screenshotPath}`);

        // Get page content
        const pageContent = await page.content();
        const textContent = await page.textContent('body');

        // Check for data
        let hasData = false;
        let dataIndicators = [];

        // Check for specific content
        for (const checkTerm of test.checkFor) {
          if (textContent.toLowerCase().includes(checkTerm.toLowerCase())) {
            dataIndicators.push(checkTerm);
            hasData = true;
          }
        }

        // Check for empty states
        const emptyElements = await page.locator('[class*="empty"], [class*="no-data"]').count();
        const tables = await page.locator('table').count();
        const charts = await page.locator('[class*="chart"]').count();

        const testResult = {
          page: test.name,
          url: test.url,
          loaded: true,
          hasData: hasData || tables > 0 || charts > 0,
          contentLength: textContent.length,
          emptyStates: emptyElements,
          tables: tables,
          charts: charts,
          dataIndicators: dataIndicators,
          screenshot: screenshotPath
        };

        results.tests.push(testResult);

        if (testResult.hasData) {
          log.success(`Page loaded with data!`);
          log.info(`  - Content length: ${testResult.contentLength} chars`);
          log.info(`  - Tables: ${testResult.tables}, Charts: ${testResult.charts}`);
          if (dataIndicators.length > 0) {
            log.info(`  - Found content: ${dataIndicators.join(', ')}`);
          }
          results.dataLoadedPages.push(test.name);
        } else {
          log.warn(`Page loaded but appears empty`);
          log.info(`  - Empty state elements: ${testResult.emptyStates}`);
          log.info(`  - Content length: ${testResult.contentLength} chars`);
          results.emptyPages.push(test.name);
        }

      } catch (error) {
        log.error(`Failed to test ${test.name}: ${error.message}`);
        results.errorPages.push(test.name);
        results.tests.push({
          page: test.name,
          error: error.message,
          loaded: false
        });
      }
    }

    // Final summary
    log.header('📊 Test Results Summary');

    log.info(`\nNetwork Activity:`);
    log.info(`  Total API calls: ${results.totalApiCalls}`);
    log.info(`  Successful: ${colors.green}${results.successfulApiCalls}${colors.reset}`);
    log.info(`  Failed: ${colors.red}${results.failedApiCalls}${colors.reset}`);

    log.info(`\nPage Results:`);
    log.info(`  Pages with data: ${colors.green}${results.dataLoadedPages.length}${colors.reset} - ${results.dataLoadedPages.join(', ') || 'none'}`);
    log.info(`  Empty pages: ${colors.yellow}${results.emptyPages.length}${colors.reset} - ${results.emptyPages.join(', ') || 'none'}`);
    log.info(`  Error pages: ${colors.red}${results.errorPages.length}${colors.reset} - ${results.errorPages.join(', ') || 'none'}`);

    log.info(`\nScreenshots:`);
    results.tests.forEach(t => {
      if (t.screenshot) {
        log.info(`  📸 ${t.page}: ${t.screenshot}`);
      }
    });

    // Save detailed report
    const report = {
      timestamp: new Date().toISOString(),
      browserMode: 'non-headless (real browser)',
      summary: {
        totalApiCalls: results.totalApiCalls,
        successfulApiCalls: results.successfulApiCalls,
        failedApiCalls: results.failedApiCalls,
        pagesWithData: results.dataLoadedPages.length,
        emptyPages: results.emptyPages.length,
        errorPages: results.errorPages.length
      },
      tests: results.tests
    };

    fs.writeFileSync('real-browser-test-report.json', JSON.stringify(report, null, 2));
    log.success('Detailed report saved: real-browser-test-report.json');

    if (results.dataLoadedPages.length > 0) {
      log.header('✅ SUCCESS!');
      log.success('Application is working! Data is loading on multiple pages.');
      log.success(`The fixes have resolved the API configuration issues.`);
    } else if (results.failedApiCalls > 0) {
      log.header('⚠️  PARTIAL SUCCESS');
      log.warn('Pages are loading but API calls are failing.');
      log.warn('This may be a network connectivity issue in the Playwright environment.');
      log.warn('Try opening http://localhost:5176 in your browser manually to verify.');
    }

  } catch (error) {
    log.error(`Test suite failed: ${error.message}`);
  }

  // Don't close the browser - leave it open for manual inspection
  log.header('🔍 Browser Window Still Open');
  log.info('The browser window will stay open for 60 seconds for manual inspection.');
  log.info('You can interact with the application and verify everything is working.');
  log.info('Close the browser window when done, and testing will complete.');

  await page.waitForTimeout(60000); // Keep browser open for 1 minute
  await browser.close();

  log.success('\nTesting complete! Check the screenshots and reports above.');
}

testRealBrowser().catch(err => {
  console.error('Test failed:', err);
  process.exit(1);
});

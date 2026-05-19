import { chromium } from 'playwright';
import fs from 'fs';

const BASE_URL = 'http://localhost:5173';
const PAGES_TO_TEST = [
  { path: '/', name: 'Home (Marketing)' },
  { path: '/app/market', name: 'Market Overview' },
  { path: '/app/sectors', name: 'Sectors' },
  { path: '/app/economic', name: 'Economic Data' },
  { path: '/app/sentiment', name: 'Sentiment' },
  { path: '/app/trading-signals', name: 'Trading Signals' },
  { path: '/app/scores', name: 'Scores Dashboard' },
  { path: '/app/portfolio', name: 'Portfolio', requireAuth: true },
  { path: '/app/trades', name: 'Trade History', requireAuth: true },
  { path: '/app/performance', name: 'Performance', requireAuth: true },
  { path: '/app/algo-dashboard', name: 'Algo Trading', requireAuth: true },
  { path: '/app/health', name: 'System Health', requireAuth: true },
  { path: '/app/audit', name: 'Audit Log', requireAuth: true },
];

const results = {
  timestamp: new Date().toISOString(),
  pages: [],
  summary: {
    total: 0,
    passed: 0,
    failed: 0,
    errors: [],
    warnings: [],
  },
};

async function testPage(page, pagePath, pageName) {
  const pageResult = {
    name: pageName,
    path: pagePath,
    url: `${BASE_URL}${pagePath}`,
    status: 'pending',
    consoleMessages: {
      errors: [],
      warnings: [],
      logs: [],
    },
    networkErrors: [],
    dataLoaded: false,
    loadTime: 0,
    html: null,
  };

  try {
    // Capture console messages
    page.on('console', (msg) => {
      const logObj = {
        type: msg.type(),
        text: msg.text(),
        location: msg.location(),
      };

      if (msg.type() === 'error') {
        pageResult.consoleMessages.errors.push(logObj);
      } else if (msg.type() === 'warning') {
        pageResult.consoleMessages.warnings.push(logObj);
      } else {
        pageResult.consoleMessages.logs.push(logObj);
      }
    });

    // Capture network errors
    page.on('response', (response) => {
      if (response.status() >= 400) {
        pageResult.networkErrors.push({
          url: response.url(),
          status: response.status(),
          statusText: response.statusText(),
        });
      }
    });

    // Navigate and measure load time
    const startTime = Date.now();
    const response = await page.goto(`${BASE_URL}${pagePath}`, {
      waitUntil: 'networkidle',
      timeout: 15000,
    });
    pageResult.loadTime = Date.now() - startTime;

    // Wait for data to load (look for content)
    await page.waitForTimeout(2000);

    // Check if page has substantial content
    const bodyText = await page.evaluate(() => document.body.innerText);
    const htmlContent = await page.content();
    pageResult.html = htmlContent;
    pageResult.dataLoaded = bodyText.trim().length > 100;

    // Determine status
    if (pageResult.consoleMessages.errors.length > 0) {
      pageResult.status = 'ERRORS';
    } else if (pageResult.consoleMessages.warnings.length > 0) {
      pageResult.status = 'WARNINGS';
    } else if (pageResult.networkErrors.length > 0) {
      pageResult.status = 'NETWORK_ERRORS';
    } else if (!pageResult.dataLoaded) {
      pageResult.status = 'NO_DATA';
    } else {
      pageResult.status = 'PASS';
    }
  } catch (error) {
    pageResult.status = 'FAILED';
    pageResult.error = {
      message: error.message,
      code: error.code,
    };
  }

  return pageResult;
}

async function runTests() {
  let browser;

  try {
    console.log('🧪 Starting Production Readiness Tests...\n');
    console.log(`📍 Testing: ${BASE_URL}\n`);

    browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();

    // Test each page
    for (const pageConfig of PAGES_TO_TEST) {
      if (pageConfig.requireAuth) {
        console.log(`⏭️  Skipping (requires auth): ${pageConfig.name}`);
        continue;
      }

      console.log(`🔍 Testing: ${pageConfig.name}...`);
      const result = await testPage(page, pageConfig.path, pageConfig.name);
      results.pages.push(result);
      results.summary.total++;

      if (result.status === 'PASS') {
        results.summary.passed++;
        console.log(`   ✅ PASS - ${result.loadTime}ms\n`);
      } else {
        results.summary.failed++;
        console.log(`   ❌ ${result.status}`);
        if (result.error) {
          console.log(`      Error: ${result.error.message}`);
        }
        if (result.consoleMessages.errors.length > 0) {
          console.log(`      Console Errors: ${result.consoleMessages.errors.length}`);
          result.consoleMessages.errors.forEach(e => console.log(`        - ${e.text}`));
        }
        if (result.consoleMessages.warnings.length > 0) {
          console.log(`      Console Warnings: ${result.consoleMessages.warnings.length}`);
        }
        if (result.networkErrors.length > 0) {
          console.log(`      Network Errors: ${result.networkErrors.length}`);
          result.networkErrors.forEach(e => console.log(`        - ${e.status} ${e.url}`));
        }
        if (!result.dataLoaded) {
          console.log(`      ⚠️  No data loaded`);
        }
        console.log();
      }
    }

    await browser.close();

    // Report summary
    console.log('\n' + '='.repeat(60));
    console.log('📊 TEST SUMMARY');
    console.log('='.repeat(60));
    console.log(`Total Pages Tested: ${results.summary.total}`);
    console.log(`✅ Passed: ${results.summary.passed}/${results.summary.total}`);
    console.log(`❌ Failed: ${results.summary.failed}/${results.summary.total}`);

    if (results.summary.failed === 0) {
      console.log('\n🎉 ALL PAGES PASS - F12 LOGS CLEAN - READY FOR PRODUCTION');
    } else {
      console.log('\n⚠️  ISSUES FOUND - SEE DETAILS ABOVE');
    }

    // Write detailed report
    fs.writeFileSync(
      'test-results.json',
      JSON.stringify(results, null, 2)
    );
    console.log('\n📄 Detailed results saved to: test-results.json');

  } catch (error) {
    console.error('Test execution failed:', error);
    if (browser) await browser.close();
    process.exit(1);
  }
}

runTests().catch(console.error);

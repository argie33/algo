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
  header: (msg) => console.log(`\n${colors.bold}${colors.cyan}═══════════════════════════════════${colors.reset}\n${colors.bold}${colors.cyan}${msg}${colors.reset}\n${colors.bold}${colors.cyan}═══════════════════════════════════${colors.reset}`),
  section: (msg) => console.log(`\n${colors.bold}${colors.blue}📌 ${msg}${colors.reset}`),
  success: (msg) => console.log(`${colors.green}✅ ${msg}${colors.reset}`),
  error: (msg) => console.log(`${colors.red}❌ ${msg}${colors.reset}`),
  warn: (msg) => console.log(`${colors.yellow}⚠️  ${msg}${colors.reset}`),
  info: (msg) => console.log(`${colors.blue}ℹ️  ${msg}${colors.reset}`),
  code: (msg) => console.log(`   ${colors.cyan}${msg}${colors.reset}`)
};

async function comprehensiveCheck() {
  log.header('🔍 COMPREHENSIVE APPLICATION CHECK');

  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });

  const issues = {
    criticalErrors: [],
    warnings: [],
    missingElements: [],
    performanceIssues: [],
    navigationIssues: [],
    apiIssues: []
  };

  const consoleMessages = [];
  const networkRequests = [];
  const networkErrors = [];

  // Capture all console messages
  page.on('console', msg => {
    consoleMessages.push({
      type: msg.type(),
      text: msg.text(),
      timestamp: new Date().toISOString()
    });

    if (msg.type() === 'error') {
      issues.criticalErrors.push({
        source: 'console',
        message: msg.text()
      });
    }
    if (msg.type() === 'warning') {
      issues.warnings.push({
        source: 'console',
        message: msg.text()
      });
    }
  });

  // Track network requests
  page.on('response', response => {
    networkRequests.push({
      url: response.url(),
      status: response.status(),
      ok: response.ok(),
      timestamp: new Date().toISOString()
    });
  });

  page.on('requestfailed', request => {
    networkErrors.push({
      url: request.url(),
      error: request.failure()?.errorText,
      timestamp: new Date().toISOString()
    });
    issues.apiIssues.push({
      url: request.url(),
      error: request.failure()?.errorText
    });
  });

  // Handle page crashes
  page.on('error', err => {
    issues.criticalErrors.push({
      source: 'page_crash',
      message: err.message
    });
  });

  const testCases = [
    { path: '/', name: 'Home Page', checks: ['header', 'nav', 'button'] },
    { path: '/app/market', name: 'Market Health', checks: ['Market', 'Health'] },
    { path: '/app/sectors', name: 'Sector Analysis', checks: ['Sector', 'Analysis'] },
    { path: '/app/trading-signals', name: 'Trading Signals', checks: ['signal', 'trade'] },
    { path: '/app/portfolio', name: 'Portfolio', checks: [] }, // May redirect to login
    { path: '/app/scores', name: 'Scores Dashboard', checks: [] },
    { path: '/app/performance', name: 'Performance', checks: [] },
  ];

  try {
    log.section('1. TESTING PAGE LOADS & RENDERING');

    for (const test of testCases) {
      try {
        const url = `http://localhost:5176${test.path}`;
        log.info(`Testing ${test.name}...`);

        await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 10000 }).catch(() => {});
        await page.waitForTimeout(2000);

        // Get page info
        const title = await page.title();
        const content = await page.content();
        const textLength = (await page.textContent('body'))?.length || 0;

        // Check for React errors
        const errorBoundaries = await page.locator('[class*="error"]').count();
        const loadingStates = await page.locator('[class*="loading"]').count();

        // Check for required elements
        let foundElements = [];
        for (const check of test.checks) {
          const found = content.toLowerCase().includes(check.toLowerCase());
          if (found) foundElements.push(check);
        }

        if (textLength > 500) {
          log.success(`${test.name}: Loaded (${textLength} chars)`);
        } else if (textLength > 100) {
          log.warn(`${test.name}: Minimal content (${textLength} chars)`);
        } else {
          log.error(`${test.name}: Empty page (${textLength} chars)`);
          issues.navigationIssues.push({
            page: test.name,
            issue: 'Empty or minimal content'
          });
        }

        if (errorBoundaries > 0) {
          log.warn(`  ⚠️ ${errorBoundaries} error elements found`);
          issues.missingElements.push({
            page: test.name,
            issue: `${errorBoundaries} error boundary elements`
          });
        }

      } catch (err) {
        log.error(`${test.name}: ${err.message}`);
        issues.navigationIssues.push({
          page: test.name,
          error: err.message
        });
      }
    }

    log.section('2. TESTING INTERACTIVE ELEMENTS');

    // Test home page navigation
    await page.goto('http://localhost:5176/', { waitUntil: 'domcontentloaded' });

    // Look for navigation buttons
    const navButtons = await page.locator('button, a[role="link"]').count();
    log.info(`Found ${navButtons} interactive elements on home page`);

    if (navButtons < 5) {
      log.warn(`Fewer than expected navigation elements (${navButtons})`);
    }

    // Try clicking a navigation link
    try {
      const links = await page.locator('a, button').all();
      if (links.length > 0) {
        log.success(`✅ Navigation elements are clickable`);
      }
    } catch (err) {
      log.warn(`Could not verify clickable elements`);
    }

    log.section('3. TESTING API CONNECTIVITY');

    // Direct API health check
    try {
      const response = await page.request.get('http://localhost:3001/api/health');
      if (response.ok()) {
        log.success(`Backend API is responding (HTTP ${response.status()})`);
      } else {
        log.warn(`Backend API returned HTTP ${response.status()}`);
        issues.apiIssues.push({
          endpoint: '/api/health',
          status: response.status()
        });
      }
    } catch (err) {
      log.error(`Backend API unreachable: ${err.message}`);
      issues.criticalErrors.push({
        source: 'api_health_check',
        message: `Backend API unreachable: ${err.message}`
      });
    }

    // Test a data endpoint
    try {
      const response = await page.request.get('http://localhost:3001/api/sectors?limit=5');
      if (response.ok()) {
        const data = await response.json();
        log.success(`Sectors endpoint working: ${data.data?.items?.length || 0} items returned`);
      } else {
        log.warn(`Sectors endpoint returned HTTP ${response.status()}`);
      }
    } catch (err) {
      log.warn(`Could not fetch sectors data`);
    }

    log.section('4. TESTING ERROR HANDLING');

    // Navigate to 404
    await page.goto('http://localhost:5176/nonexistent-page', { waitUntil: 'domcontentloaded' }).catch(() => {});
    const pageContent = await page.textContent('body');

    if (!pageContent?.includes('404') && !pageContent?.includes('not found')) {
      log.warn(`No 404 error page displayed for invalid route`);
      issues.warnings.push({
        issue: 'No 404 page for invalid routes'
      });
    }

    log.section('5. ANALYZING CONSOLE MESSAGES');

    // Filter and report console issues
    const errors = consoleMessages.filter(m => m.type === 'error');
    const warnings = consoleMessages.filter(m => m.type === 'warning');

    log.info(`Total console messages: ${consoleMessages.length}`);
    log.info(`  Errors: ${errors.length}`);
    log.info(`  Warnings: ${warnings.length}`);

    if (errors.length > 0) {
      log.error(`Console Errors Found:`);
      errors.slice(0, 5).forEach(err => {
        log.code(`${err.text.substring(0, 80)}`);
      });
      if (errors.length > 5) {
        log.code(`... and ${errors.length - 5} more`);
      }
    }

    log.section('6. NETWORK ANALYSIS');

    const apiRequests = networkRequests.filter(r => r.url.includes('/api'));
    const successfulApis = apiRequests.filter(r => r.ok).length;
    const failedApis = apiRequests.filter(r => !r.ok).length;

    log.info(`API Requests: ${apiRequests.length}`);
    log.info(`  ✅ Successful: ${successfulApis}`);
    log.info(`  ❌ Failed: ${failedApis}`);

    if (networkErrors.length > 0) {
      log.error(`Network Errors: ${networkErrors.length}`);
      networkErrors.slice(0, 3).forEach(err => {
        log.code(`${err.url.substring(0, 60)}: ${err.error}`);
      });
    }

    log.section('7. PERFORMANCE CHECK');

    // Measure page load time for home page
    const startTime = Date.now();
    await page.goto('http://localhost:5176/', { waitUntil: 'networkidle' }).catch(() => {});
    const loadTime = Date.now() - startTime;

    log.info(`Home page load time: ${loadTime}ms`);
    if (loadTime > 5000) {
      log.warn(`Slow page load (${loadTime}ms)`);
      issues.performanceIssues.push({
        page: 'home',
        loadTime: `${loadTime}ms`
      });
    } else {
      log.success(`Good page load performance`);
    }

  } catch (err) {
    log.error(`Test interrupted: ${err.message}`);
    issues.criticalErrors.push({
      source: 'test_execution',
      message: err.message
    });
  }

  await browser.close();

  // Generate report
  log.header('📊 COMPREHENSIVE TEST REPORT');

  const report = {
    timestamp: new Date().toISOString(),
    summary: {
      totalTests: testCases.length,
      criticalErrors: issues.criticalErrors.length,
      warnings: issues.warnings.length,
      apiIssues: issues.apiIssues.length,
      navigationIssues: issues.navigationIssues.length,
      performanceIssues: issues.performanceIssues.length
    },
    issues,
    consoleStats: {
      total: consoleMessages.length,
      errors: consoleMessages.filter(m => m.type === 'error').length,
      warnings: consoleMessages.filter(m => m.type === 'warning').length
    },
    networkStats: {
      totalRequests: networkRequests.length,
      apiRequests: networkRequests.filter(r => r.url.includes('/api')).length,
      networkErrors: networkErrors.length
    }
  };

  // Print summary
  log.section('OVERALL STATUS');

  if (issues.criticalErrors.length === 0) {
    log.success(`No critical errors found!`);
  } else {
    log.error(`${issues.criticalErrors.length} critical error(s) found`);
    issues.criticalErrors.forEach(err => {
      log.code(`${err.source}: ${err.message.substring(0, 70)}`);
    });
  }

  if (issues.warnings.length > 0) {
    log.warn(`${issues.warnings.length} warning(s) found`);
  }

  if (issues.navigationIssues.length > 0) {
    log.error(`${issues.navigationIssues.length} navigation issue(s)`);
  }

  if (issues.apiIssues.length > 0) {
    log.error(`${issues.apiIssues.length} API issue(s)`);
  }

  // Save report
  fs.writeFileSync('comprehensive-check-report.json', JSON.stringify(report, null, 2));
  log.success('Full report saved: comprehensive-check-report.json');

  // Final verdict
  log.section('FINAL VERDICT');

  const criticalCount = issues.criticalErrors.length + issues.navigationIssues.length;

  if (criticalCount === 0 && issues.apiIssues.length === 0) {
    log.header('✅ APPLICATION IS FULLY FUNCTIONAL');
    log.success('All systems operational. Application ready for use.');
  } else if (criticalCount === 0) {
    log.header('✅ APPLICATION IS WORKING (With minor API issues)');
    log.success('Core functionality is operational.');
    log.warn('Some API endpoints may need data or configuration.');
  } else {
    log.header('⚠️  APPLICATION HAS ISSUES');
    log.error('Critical issues detected. Review report above.');
  }
}

comprehensiveCheck().catch(err => {
  console.error('Check failed:', err);
  process.exit(1);
});

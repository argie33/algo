#!/usr/bin/env node

const fs = require('fs');

const colors = {
  red: '\x1b[31m',
  yellow: '\x1b[33m',
  green: '\x1b[32m',
  blue: '\x1b[34m',
  cyan: '\x1b[36m',
  reset: '\x1b[0m',
  bold: '\x1b[1m'
};

const log = {
  error: (msg) => console.error(`${colors.red}❌ ${msg}${colors.reset}`),
  warn: (msg) => console.warn(`${colors.yellow}⚠️  ${msg}${colors.reset}`),
  success: (msg) => console.log(`${colors.green}✅ ${msg}${colors.reset}`),
  info: (msg) => console.log(`${colors.blue}ℹ️  ${msg}${colors.reset}`),
  header: (msg) => console.log(`\n${colors.bold}${colors.blue}${msg}${colors.reset}\n`),
  section: (msg) => console.log(`${colors.cyan}--- ${msg} ---${colors.reset}`)
};

async function comprehensiveTest() {
  const { chromium } = require('playwright');

  let browser;
  const findings = {
    pages: [],
    issues: [],
    missingElements: [],
    apiErrors: [],
    renderingIssues: []
  };

  try {
    log.header('🚀 Comprehensive App Testing Suite');

    browser = await chromium.launch({ headless: false });
    const page = await browser.newPage();

    // Set viewport to standard desktop size
    await page.setViewportSize({ width: 1280, height: 720 });

    // Track all console messages
    const consoleMessages = [];
    page.on('console', msg => {
      consoleMessages.push({
        type: msg.type(),
        text: msg.text()
      });
    });

    // Track network errors
    page.on('requestfailed', request => {
      if (request.url().includes('api')) {
        findings.apiErrors.push({
          url: request.url(),
          method: request.method()
        });
      }
    });

    // Test pages to check
    const testPages = [
      { path: '/', name: 'Home Page', selectors: ['h1', 'h2', 'button'] },
      { path: '/app/market', name: 'Market Overview', selectors: ['[class*="chart"]', '[class*="market"]'] },
      { path: '/app/sectors', name: 'Sectors', selectors: ['[class*="sector"]', '[class*="industry"]'] },
      { path: '/app/trading-signals', name: 'Trading Signals', selectors: ['[class*="signal"]', '[class*="table"]'] },
      { path: '/app/portfolio', name: 'Portfolio', selectors: ['[class*="portfolio"]', '[class*="holdings"]'] },
    ];

    log.info('Testing application pages...\n');

    for (const testPage of testPages) {
      log.section(`Testing: ${testPage.name}`);

      try {
        const url = `http://localhost:5176${testPage.path}`;
        log.info(`Navigating to ${url}`);

        await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 10000 }).catch(() => {
          log.warn('DOMContentLoaded timeout, continuing...');
        });

        // Wait for content
        await page.waitForTimeout(2000);

        // Check page title and URL
        const title = await page.title();
        const currentUrl = page.url();

        // Get page content
        const bodyText = await page.textContent('body');
        const bodyEmpty = !bodyText || bodyText.trim().length < 100;

        // Check for common error elements
        const errorMessages = await page.locator('[class*="error"], [role="alert"]').count();
        const emptyStates = await page.locator('[class*="empty"], [class*="no-data"]').count();

        // Check for expected elements
        const foundElements = [];
        for (const selector of testPage.selectors) {
          const count = await page.locator(selector).count();
          if (count > 0) {
            foundElements.push({ selector, count });
          }
        }

        const pageInfo = {
          path: testPage.path,
          name: testPage.name,
          title,
          url: currentUrl,
          status: bodyEmpty ? 'EMPTY' : 'OK',
          contentLength: bodyText?.length || 0,
          errorMessages,
          emptyStates,
          foundElements,
          consoleErrors: consoleMessages.filter(m => m.type === 'error').length
        };

        findings.pages.push(pageInfo);

        // Report on this page
        log.info(`Title: ${title}`);
        log.info(`Content length: ${pageInfo.contentLength} chars`);

        if (errorMessages > 0) {
          log.warn(`Found ${errorMessages} error messages on page`);
          findings.issues.push({
            page: testPage.name,
            issue: `Error messages displayed (${errorMessages})`
          });
        }

        if (emptyStates > 0) {
          log.info(`Empty states: ${emptyStates}`);
        }

        if (foundElements.length > 0) {
          log.success(`Found ${foundElements.length} element types`);
        } else {
          log.warn(`No expected elements found`);
          findings.missingElements.push({
            page: testPage.name,
            expectedSelectors: testPage.selectors
          });
        }

        if (bodyEmpty) {
          log.warn(`Page content appears empty!`);
          findings.issues.push({
            page: testPage.name,
            issue: 'Page content is empty or minimal'
          });
        }

      } catch (error) {
        log.error(`Failed to test ${testPage.name}: ${error.message}`);
        findings.issues.push({
          page: testPage.name,
          issue: `Navigation error: ${error.message}`
        });
      }

      console.log();
    }

    // Test API connectivity
    log.section('Testing API Connectivity');
    try {
      const response = await page.request.get('http://localhost:3001/health');
      if (response.ok()) {
        log.success('Backend API is responding');
      } else {
        log.warn(`Backend API returned status ${response.status()}`);
      }
    } catch (error) {
      log.warn(`Backend API not reachable: ${error.message}`);
    }

    // Test authentication flow
    log.section('Testing Authentication Flow');
    await page.goto('http://localhost:5176/app/dashboard', {
      waitUntil: 'domcontentloaded',
      timeout: 5000
    }).catch(() => log.info('Dashboard load timed out'));

    await page.waitForTimeout(1000);

    const hasAuthForm = await page.locator('[class*="login"], [class*="auth"], input[type="password"]').count();
    const isAuthenticated = hasAuthForm === 0;

    log.info(`Authentication required: ${hasAuthForm > 0 ? 'Yes' : 'No'}`);
    findings.pages.push({
      name: 'Authentication Status',
      authFormElements: hasAuthForm,
      requiresAuth: hasAuthForm > 0
    });

    // Generate summary
    log.header('📊 Test Summary Report');

    const reportData = {
      timestamp: new Date().toISOString(),
      totalPagesTested: findings.pages.filter(p => p.path).length,
      pagesWithIssues: findings.issues.filter(i => i.page).length,
      totalErrors: findings.apiErrors.length,
      missingElements: findings.missingElements.length,
      pages: findings.pages,
      issues: findings.issues,
      apiErrors: findings.apiErrors,
      missingElements: findings.missingElements
    };

    log.info(`Pages tested: ${reportData.totalPagesTested}`);
    log.info(`Pages with issues: ${reportData.pagesWithIssues}`);
    log.info(`API errors: ${reportData.totalErrors}`);
    log.info(`Missing elements: ${reportData.missingElements}`);

    if (findings.issues.length > 0) {
      log.header('⚠️  Issues Found:');
      findings.issues.forEach((issue, i) => {
        console.log(`[${i + 1}] ${issue.page}: ${issue.issue}`);
      });
    } else {
      log.success('No major issues found!');
    }

    // Save report
    fs.writeFileSync(
      'comprehensive-test-report.json',
      JSON.stringify(reportData, null, 2)
    );
    log.success('Full report saved to comprehensive-test-report.json');

    await browser.close();
    process.exit(findings.issues.length > 0 ? 1 : 0);

  } catch (error) {
    log.error(`Test suite failed: ${error.message}`);
    if (browser) await browser.close();
    process.exit(1);
  }
}

comprehensiveTest();

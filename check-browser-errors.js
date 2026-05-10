#!/usr/bin/env node

const fs = require('fs');

// Colors for terminal output
const colors = {
  red: '\x1b[31m',
  yellow: '\x1b[33m',
  green: '\x1b[32m',
  blue: '\x1b[34m',
  reset: '\x1b[0m',
  bold: '\x1b[1m'
};

const log = {
  error: (msg) => console.error(`${colors.red}❌ ${msg}${colors.reset}`),
  warn: (msg) => console.warn(`${colors.yellow}⚠️  ${msg}${colors.reset}`),
  success: (msg) => console.log(`${colors.green}✅ ${msg}${colors.reset}`),
  info: (msg) => console.log(`${colors.blue}ℹ️  ${msg}${colors.reset}`),
  header: (msg) => console.log(`\n${colors.bold}${colors.blue}${msg}${colors.reset}\n`)
};

async function checkBrowserErrors() {
  const { chromium } = require('playwright');

  let browser;
  const issues = {
    errors: [],
    warnings: [],
    networkErrors: [],
    consoleMessages: []
  };

  try {
    log.header('🚀 Starting Browser Error Check');

    browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();

    // Capture all console messages
    page.on('console', msg => {
      const entry = {
        type: msg.type(),
        text: msg.text()
      };
      issues.consoleMessages.push(entry);

      if (msg.type() === 'error') {
        issues.errors.push(entry);
      } else if (msg.type() === 'warning') {
        issues.warnings.push(entry);
      }
    });

    // Capture uncaught exceptions
    page.on('pageerror', error => {
      issues.errors.push({
        type: 'uncaughtError',
        message: error.message,
        stack: error.stack
      });
    });

    // Capture failed network requests
    page.on('requestfailed', request => {
      issues.networkErrors.push({
        url: request.url(),
        method: request.method(),
        failure: request.failure()?.errorText
      });
    });

    log.info('Waiting for dev server to be ready...');

    // Wait for dev server with retries
    let retries = 0;
    let pageLoaded = false;
    while (retries < 30 && !pageLoaded) {
      try {
        await page.goto('http://localhost:5176', {
          waitUntil: 'domcontentloaded',
          timeout: 5000
        });
        pageLoaded = true;
        log.success('Dev server is ready!');
      } catch (err) {
        retries++;
        if (retries % 5 === 0) {
          log.info(`Still waiting... (${retries}s)`);
        }
        await page.waitForTimeout(1000);
      }
    }

    if (!pageLoaded) {
      throw new Error('Dev server did not start within 30 seconds');
    }

    // Wait for app to fully load
    log.info('Waiting for app to fully load...');
    try {
      await page.waitForLoadState('networkidle', { timeout: 15000 });
    } catch (e) {
      log.warn('Network did not reach idle state, continuing...');
    }

    // Wait a bit more for React to render
    await page.waitForTimeout(3000);

    // Take screenshot for visual inspection
    const screenshotPath = 'browser-state.png';
    await page.screenshot({ path: screenshotPath });
    log.success(`Screenshot saved to ${screenshotPath}`);

    // Get page content for debugging
    const pageTitle = await page.title();
    const pageUrl = page.url();
    const bodyText = await page.textContent('body');
    const errorElements = await page.locator('[class*="error"], [class*="Error"]').count();

    log.header('📊 Browser State Report');
    log.info(`Page URL: ${pageUrl}`);
    log.info(`Page Title: ${pageTitle}`);
    log.info(`Error elements found: ${errorElements}`);
    log.info(`Body content length: ${bodyText?.length || 0} chars`);

    await browser.close();

    // Report findings
    log.header('📋 Console Messages Captured');

    if (issues.errors.length > 0) {
      log.error(`Found ${issues.errors.length} ERRORS:`);
      issues.errors.forEach((err, i) => {
        console.error(`\n[${i + 1}] ${err.type || 'Error'}`);
        if (err.message) console.error(`   Message: ${err.message}`);
        if (err.text) console.error(`   Text: ${err.text}`);
        if (err.stack) console.error(`   Stack: ${err.stack}`);
      });
    } else {
      log.success('No JavaScript errors found!');
    }

    if (issues.warnings.length > 0) {
      log.warn(`Found ${issues.warnings.length} WARNINGS:`);
      issues.warnings.forEach((warn, i) => {
        console.warn(`\n[${i + 1}] Warning`);
        console.warn(`   Text: ${warn.text}`);
      });
    } else {
      log.success('No warnings found!');
    }

    if (issues.networkErrors.length > 0) {
      log.error(`Found ${issues.networkErrors.length} NETWORK ERRORS:`);
      issues.networkErrors.forEach((err, i) => {
        console.error(`\n[${i + 1}] ${err.method} ${err.url}`);
        console.error(`   Failure: ${err.failure}`);
      });
    } else {
      log.success('No network errors!');
    }

    // Save full report
    const report = {
      timestamp: new Date().toISOString(),
      stats: {
        totalErrors: issues.errors.length,
        totalWarnings: issues.warnings.length,
        totalNetworkErrors: issues.networkErrors.length,
        totalMessages: issues.consoleMessages.length
      },
      issues,
      pageState: {
        url: pageUrl,
        title: pageTitle,
        bodyLength: bodyText?.length || 0,
        errorElements
      }
    };

    fs.writeFileSync(
      'browser-error-report.json',
      JSON.stringify(report, null, 2)
    );
    log.success('Full report saved to browser-error-report.json');

    process.exit(issues.errors.length > 0 ? 1 : 0);

  } catch (error) {
    log.error(`Test failed: ${error.message}`);
    if (browser) await browser.close();
    process.exit(1);
  }
}

checkBrowserErrors();

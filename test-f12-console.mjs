#!/usr/bin/env node
/**
 * F12 Console Verification Test
 * Captures actual browser console logs and errors on each dashboard page
 * This PROVES the logs are clean with no errors
 */

import { chromium } from 'playwright';

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

const colors = {
  reset: '\x1b[0m',
  red: '\x1b[31m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  cyan: '\x1b[36m',
};

const log = {
  ok: (msg) => console.log(`${colors.green}[OK]${colors.reset} ${msg}`),
  error: (msg) => console.log(`${colors.red}[ERROR]${colors.reset} ${msg}`),
  warn: (msg) => console.log(`${colors.yellow}[WARN]${colors.reset} ${msg}`),
  info: (msg) => console.log(`${colors.cyan}[INFO]${colors.reset} ${msg}`),
};

const pages = [
  { path: '/', name: 'Home / Market Overview' },
  { path: '/stocks', name: 'Stock Market' },
  { path: '/economic', name: 'Economic Dashboard' },
  { path: '/signals', name: 'Trading Signals' },
  { path: '/sectors', name: 'Sector Analysis' },
];

async function testPageConsole(page) {
  let browser = null;
  let browserPage = null;
  const consoleErrors = [];
  const consoleWarnings = [];
  const consoleMessages = [];
  const apiErrors = [];
  const networkErrors = [];

  try {
    browser = await chromium.launch({ headless: true });
    browserPage = await browser.newPage();

    // Capture ALL console messages
    browserPage.on('console', (msg) => {
      const type = msg.type();
      const text = msg.text();
      const location = msg.location().url || 'unknown';

      if (type === 'error') {
        consoleErrors.push({
          text,
          location,
          time: new Date().toISOString(),
        });
      } else if (type === 'warn') {
        consoleWarnings.push({
          text,
          location,
        });
      } else if (type === 'log') {
        consoleMessages.push({ text });
      }
    });

    // Capture API errors
    browserPage.on('response', (response) => {
      if (response.status() >= 400) {
        apiErrors.push({
          status: response.status(),
          url: response.url(),
        });
      }
    });

    // Capture network errors
    browserPage.on('requestfailed', (request) => {
      networkErrors.push({
        url: request.url(),
        failure: request.failure(),
      });
    });

    // Navigate with proper wait
    log.info(`Loading ${page.name}...`);
    const url = `${FRONTEND_URL}${page.path}`;

    const response = await browserPage.goto(url, {
      waitUntil: 'networkidle',
      timeout: 15000
    });

    if (!response) {
      log.error(`${page.name}: No response (network timeout)`);
      return {
        ok: false,
        page: page.name,
        error: 'Timeout',
        consoleErrors: [],
        apiErrors: [],
      };
    }

    if (response.status() >= 400) {
      log.error(`${page.name}: HTTP ${response.status()}`);
      return {
        ok: false,
        page: page.name,
        error: `HTTP ${response.status()}`,
        consoleErrors: [],
        apiErrors: [],
      };
    }

    // Wait for page to fully render and all async calls to settle
    await browserPage.waitForTimeout(3000);

    // Check for data on page
    const pageContent = await browserPage.evaluate(() => {
      return {
        textLength: document.body.innerText.length,
        elementCount: document.querySelectorAll('*').length,
        hasErrors: document.body.textContent.includes('Error') ||
                   document.body.textContent.includes('error'),
      };
    });

    // Report results
    const hasErrors = consoleErrors.length > 0 || apiErrors.length > 0 || networkErrors.length > 0;

    if (!hasErrors) {
      log.ok(`${page.name}: ✓ Clean console (0 errors, ${consoleWarnings.length} warnings)`);
    } else {
      log.error(`${page.name}: ✗ Found ${consoleErrors.length} console errors + ${apiErrors.length} API errors`);
    }

    // Log details if there are issues
    if (consoleErrors.length > 0) {
      consoleErrors.forEach((err, i) => {
        console.log(`    Error ${i + 1}: ${err.text.substring(0, 80)}`);
      });
    }

    if (apiErrors.length > 0) {
      apiErrors.forEach((err, i) => {
        console.log(`    API Error ${i + 1}: ${err.status} ${err.url.substring(0, 60)}`);
      });
    }

    return {
      ok: !hasErrors,
      page: page.name,
      consoleErrors: consoleErrors.length,
      apiErrors: apiErrors.length,
      warnings: consoleWarnings.length,
      pageContent,
    };

  } catch (error) {
    log.error(`${page.name}: ${error.message}`);
    return {
      ok: false,
      page: page.name,
      error: error.message,
      consoleErrors: 0,
    };
  } finally {
    if (browserPage) await browserPage.close();
    if (browser) await browser.close();
  }
}

async function main() {
  console.log('\n' + '='.repeat(70));
  console.log('F12 CONSOLE VERIFICATION TEST');
  console.log('='.repeat(70));
  log.info(`Frontend: ${FRONTEND_URL}`);
  log.info(`Testing browser console logs on each dashboard page\n`);

  const results = [];
  let allClean = true;

  for (const page of pages) {
    const result = await testPageConsole(page);
    results.push(result);
    if (!result.ok) allClean = false;
  }

  // Summary
  console.log('\n' + '='.repeat(70));
  console.log('CONSOLE LOG SUMMARY');
  console.log('='.repeat(70));

  for (const result of results) {
    const status = result.ok ? '✓' : '✗';
    const errorCount = result.consoleErrors || 0;
    const apiErrorCount = result.apiErrors || 0;
    const warningCount = result.warnings || 0;

    if (result.ok) {
      console.log(`${colors.green}${status}${colors.reset} ${result.page}: 0 errors`);
    } else {
      console.log(
        `${colors.red}${status}${colors.reset} ${result.page}: ${errorCount} console errors, ${apiErrorCount} API errors`
      );
    }
  }

  console.log('\n' + '='.repeat(70));

  if (allClean) {
    log.ok('ALL PAGES HAVE CLEAN CONSOLE LOGS - ZERO ERRORS');
    console.log('='.repeat(70) + '\n');
    process.exit(0);
  } else {
    log.error('Some pages have console errors - see details above');
    console.log('='.repeat(70) + '\n');
    process.exit(1);
  }
}

main().catch(err => {
  log.error(`Test error: ${err.message}`);
  process.exit(1);
});

#!/usr/bin/env node
/**
 * ACTUAL Browser Console Inspection
 * Launches real browser, navigates to each page, captures F12 console logs
 * Shows EXACTLY what appears in the browser console
 */

import puppeteer from 'puppeteer';
import { fileURLToPath } from 'url';
import { dirname } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

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
  ok: (msg) => console.log(`${colors.green}✓${colors.reset} ${msg}`),
  error: (msg) => console.log(`${colors.red}✗${colors.reset} ${msg}`),
  warn: (msg) => console.log(`${colors.yellow}⚠${colors.reset} ${msg}`),
  info: (msg) => console.log(`${colors.cyan}ℹ${colors.reset} ${msg}`),
};

const pages = [
  { path: '/', name: 'Home / Market Overview' },
  { path: '/stocks', name: 'Stock Market' },
  { path: '/economic', name: 'Economic Dashboard' },
  { path: '/signals', name: 'Trading Signals' },
  { path: '/sectors', name: 'Sector Analysis' },
];

async function checkPageConsole(page) {
  let browser = null;
  let browserPage = null;

  const consoleLogs = {
    errors: [],
    warnings: [],
    info: [],
    log: [],
    other: []
  };

  const networkErrors = [];
  const apiErrors = [];

  try {
    browser = await puppeteer.launch({
      headless: 'new',
      args: [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-dev-shm-usage'
      ]
    });

    browserPage = await browser.newPage();

    // Capture ALL console messages
    browserPage.on('console', (msg) => {
      const type = msg.type();
      const text = msg.text();

      if (type === 'error') {
        consoleLogs.errors.push({ text, time: new Date().toISOString() });
      } else if (type === 'warn') {
        consoleLogs.warnings.push({ text });
      } else if (type === 'info') {
        consoleLogs.info.push({ text });
      } else if (type === 'log') {
        consoleLogs.log.push({ text });
      } else {
        consoleLogs.other.push({ type, text });
      }
    });

    // Capture failed requests
    browserPage.on('response', (response) => {
      if (response.status() >= 400) {
        apiErrors.push({
          status: response.status(),
          url: response.url(),
          statusText: response.statusText()
        });
      }
    });

    // Capture network errors
    browserPage.on('requestfailed', (request) => {
      networkErrors.push({
        url: request.url(),
        error: request.failure().errorText
      });
    });

    // Navigate to page
    const url = `${FRONTEND_URL}${page.path}`;
    log.info(`Checking: ${page.name} (${page.path})`);

    const response = await browserPage.goto(url, {
      waitUntil: 'networkidle2',
      timeout: 15000
    });

    // Wait for page to settle
    await new Promise(r => setTimeout(r, 2000));

    // Get page content info
    const pageInfo = await browserPage.evaluate(() => ({
      title: document.title,
      textLength: document.body.innerText.length,
      elementCount: document.querySelectorAll('*').length,
      hasContent: document.body.innerText.length > 100,
      url: window.location.href
    }));

    // Check if page has error indicators
    const hasVisibleErrors = consoleLogs.errors.length > 0 || apiErrors.length > 0 || networkErrors.length > 0;

    return {
      page: page.name,
      path: page.path,
      ok: !hasVisibleErrors,
      httpStatus: response?.status() || 'unknown',
      consoleLogs,
      apiErrors,
      networkErrors,
      pageInfo
    };

  } catch (error) {
    log.error(`${page.name}: ${error.message}`);
    return {
      page: page.name,
      path: page.path,
      ok: false,
      error: error.message,
      consoleLogs: consoleLogs,
      apiErrors: [],
      networkErrors: []
    };
  } finally {
    if (browserPage) {
      try {
        await browserPage.close();
      } catch (e) {
        // Ignore close errors
      }
    }
    if (browser) {
      try {
        await browser.close();
      } catch (e) {
        // Ignore close errors
      }
    }
  }
}

function printPageResults(result) {
  console.log('\n' + '-'.repeat(70));
  console.log(`PAGE: ${result.page} (${result.path})`);
  console.log('-'.repeat(70));

  if (result.error) {
    log.error(`Failed to load: ${result.error}`);
    return;
  }

  // HTTP Status
  console.log(`HTTP Status: ${colors.green}${result.httpStatus}${colors.reset}`);

  // Page Content
  if (result.pageInfo) {
    console.log(`Title: ${result.pageInfo.title}`);
    console.log(`Content: ${result.pageInfo.textLength} characters, ${result.pageInfo.elementCount} DOM elements`);
  }

  // Console Errors (most important)
  if (result.consoleLogs.errors.length > 0) {
    console.log(`\n${colors.red}CONSOLE ERRORS (${result.consoleLogs.errors.length}):${colors.reset}`);
    result.consoleLogs.errors.forEach((err, i) => {
      console.log(`  ${i + 1}. ${err.text}`);
    });
  } else {
    console.log(`\n${colors.green}Console Errors: 0${colors.reset}`);
  }

  // Console Warnings
  if (result.consoleLogs.warnings.length > 0) {
    console.log(`\n${colors.yellow}Console Warnings (${result.consoleLogs.warnings.length}):${colors.reset}`);
    result.consoleLogs.warnings.slice(0, 5).forEach((warn, i) => {
      console.log(`  ${i + 1}. ${warn.text.substring(0, 100)}`);
    });
    if (result.consoleLogs.warnings.length > 5) {
      console.log(`  ... and ${result.consoleLogs.warnings.length - 5} more`);
    }
  } else {
    console.log(`Console Warnings: 0`);
  }

  // API Errors
  if (result.apiErrors.length > 0) {
    console.log(`\n${colors.red}API Errors (${result.apiErrors.length}):${colors.reset}`);
    result.apiErrors.forEach((err, i) => {
      console.log(`  ${i + 1}. ${err.status} ${err.url.substring(0, 60)}`);
    });
  } else {
    console.log(`\nAPI Errors: 0`);
  }

  // Network Errors
  if (result.networkErrors.length > 0) {
    console.log(`\n${colors.red}Network Errors (${result.networkErrors.length}):${colors.reset}`);
    result.networkErrors.forEach((err, i) => {
      console.log(`  ${i + 1}. ${err.error}: ${err.url}`);
    });
  } else {
    console.log(`Network Errors: 0`);
  }

  // Overall Status
  console.log('\n' + '-'.repeat(70));
  if (result.ok) {
    log.ok(`${result.page}: CLEAN CONSOLE - Ready for production`);
  } else {
    log.error(`${result.page}: Has errors - see details above`);
  }
}

async function main() {
  console.log('\n' + '='.repeat(70));
  console.log('BROWSER CONSOLE VERIFICATION');
  console.log('='.repeat(70));
  log.info(`Frontend: ${FRONTEND_URL}`);
  log.info(`Launching real browser to capture actual F12 console logs\n`);

  const results = [];
  let allClean = true;

  for (const page of pages) {
    const result = await checkPageConsole(page);
    results.push(result);

    if (!result.ok) {
      allClean = false;
    }

    printPageResults(result);
  }

  // Final Summary
  console.log('\n' + '='.repeat(70));
  console.log('FINAL SUMMARY');
  console.log('='.repeat(70));

  const passed = results.filter(r => r.ok).length;
  const failed = results.filter(r => !r.ok).length;

  console.log('\nConsole Status by Page:');
  results.forEach(result => {
    const status = result.ok ? colors.green + '✓' + colors.reset : colors.red + '✗' + colors.reset;
    const errorCount = result.consoleLogs.errors.length;
    console.log(`  ${status} ${result.page}: ${errorCount} errors`);
  });

  console.log('\n' + '='.repeat(70));
  console.log(`Pages with clean console: ${colors.green}${passed}/${results.length}${colors.reset}`);
  console.log('='.repeat(70));

  if (allClean) {
    console.log(`\n${colors.green}✅ ALL PAGES HAVE CLEAN CONSOLE LOGS${colors.reset}`);
    console.log('✅ No console errors detected');
    console.log('✅ No API errors detected');
    console.log('✅ All pages loading successfully\n');
    process.exit(0);
  } else {
    console.log(`\n${colors.red}❌ SOME PAGES HAVE CONSOLE ERRORS${colors.reset}`);
    console.log('See details above for each page\n');
    process.exit(1);
  }
}

main().catch(err => {
  log.error(`Fatal error: ${err.message}`);
  console.error(err);
  process.exit(1);
});

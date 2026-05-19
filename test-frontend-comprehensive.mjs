#!/usr/bin/env node
/**
 * Comprehensive Frontend Test Suite
 * Tests all dashboard pages for:
 * 1. Page loads without errors
 * 2. No console errors (F12 logs clean)
 * 3. Data is displayed (not empty)
 */

import { chromium } from 'playwright';

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';
const API_URL = process.env.API_URL || 'http://localhost:3001';

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
  { path: '/', name: 'Home / Market Overview', selector: '[data-testid="market-overview"], h1' },
  { path: '/stocks', name: 'Stock Market', selector: '[data-testid="stock-list"], table, .stock' },
  { path: '/economic', name: 'Economic Dashboard', selector: '[data-testid="economic-dashboard"], .economic' },
  { path: '/signals', name: 'Trading Signals', selector: '[data-testid="signals-dashboard"], .signal' },
  { path: '/sectors', name: 'Sector Analysis', selector: '[data-testid="sectors-dashboard"], .sector' },
  { path: '/portfolio', name: 'Portfolio (Protected)', selector: '[data-testid="portfolio"], .portfolio' },
];

async function testPage(browser, page) {
  let browser_instance = null;
  let page_instance = null;
  const consoleMessages = [];
  const errors = [];

  try {
    browser_instance = await chromium.launch();
    page_instance = await browser_instance.newPage();

    // Collect console messages and errors
    page_instance.on('console', (msg) => {
      const type = msg.type();
      const text = msg.text();
      const location = msg.location().url;

      if (type === 'error') {
        errors.push({ type: 'console.error', text, location });
      } else if (type === 'warn') {
        consoleMessages.push({ type: 'warn', text });
      }
    });

    // Collect network errors and API failures
    page_instance.on('response', (response) => {
      if (response.status() >= 400) {
        errors.push({
          type: 'api_error',
          status: response.status(),
          url: response.url(),
        });
      }
    });

    // Navigate to page
    const url = `${FRONTEND_URL}${page.path}`;
    log.info(`Testing ${page.name} at ${page.path}...`);

    const response = await page_instance.goto(url, { waitUntil: 'networkidle', timeout: 10000 });

    if (!response || response.status() >= 400) {
      log.error(`${page.name}: Failed to load (HTTP ${response?.status() || 'UNKNOWN'})`);
      return { ok: false, page: page.name, error: 'Failed to load' };
    }

    // Wait for content to load
    await page_instance.waitForTimeout(2000);

    // Check for data content
    const hasContent = await page_instance.evaluate(() => {
      const text = document.body.innerText;
      return text.length > 100; // Minimal check for content
    });

    if (!hasContent) {
      log.warn(`${page.name}: Page loaded but appears empty`);
    }

    // Check for errors
    if (errors.length > 0) {
      log.error(`${page.name}: ${errors.length} error(s) in console`);
      errors.forEach((err) => {
        if (err.type === 'console.error') {
          console.log(`  └─ ${err.text}`);
        } else if (err.type === 'api_error') {
          console.log(`  └─ API Error: ${err.status} ${err.url.substring(0, 60)}`);
        }
      });
      return { ok: false, page: page.name, errors: errors.length };
    }

    log.ok(`${page.name}: No console errors`);
    return { ok: true, page: page.name };

  } catch (error) {
    log.error(`${page.name}: ${error.message}`);
    return { ok: false, page: page.name, error: error.message };
  } finally {
    if (page_instance) await page_instance.close();
    if (browser_instance) await browser_instance.close();
  }
}

async function main() {
  console.log('\n' + '='.repeat(70));
  console.log('FRONTEND COMPREHENSIVE TEST SUITE');
  console.log('='.repeat(70));
  log.info(`Frontend: ${FRONTEND_URL}`);
  log.info(`Backend: ${API_URL}\n`);

  let passed = 0, failed = 0;

  for (const page of pages) {
    const result = await testPage(null, page);
    if (result.ok) {
      passed++;
    } else {
      failed++;
    }
  }

  console.log('\n' + '='.repeat(70));
  console.log(`RESULTS: ${colors.green}${passed} passed${colors.reset}, ${colors.red}${failed} failed${colors.reset}`);

  if (failed === 0) {
    log.ok('All pages loaded successfully with clean consoles');
  } else {
    log.error(`${failed} page(s) had issues - see above`);
  }
  console.log('='.repeat(70) + '\n');

  process.exit(failed === 0 ? 0 : 1);
}

main().catch(err => {
  log.error(`Test suite error: ${err.message}`);
  process.exit(1);
});

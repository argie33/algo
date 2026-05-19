#!/usr/bin/env node

/**
 * F12 DevTools Console Validation - Real Chrome Browser Test
 *
 * Captures actual F12 console output for all pages to prove:
 * (1) No console errors
 * (2) All APIs working
 * (3) All data loading
 */

const puppeteer = require('puppeteer');
const fs = require('fs');

const PAGES = [
  { path: '/', name: 'Dashboard' },
  { path: '/stocks', name: 'Stocks' },
  { path: '/signals', name: 'Signals' },
  { path: '/trades', name: 'Trades' },
  { path: '/analysis', name: 'Analysis' },
  { path: '/portfolio', name: 'Portfolio' },
  { path: '/settings', name: 'Settings' },
  { path: '/backtest', name: 'Backtest' }
];

const BASE_URL = 'http://localhost:5173';

async function validatePage(browser, path, name) {
  const page = await browser.newPage();
  const console_output = {
    errors: [],
    warnings: [],
    logs: [],
    network_errors: []
  };

  let load_time = 0;

  // Capture console messages
  page.on('console', msg => {
    const text = msg.text();
    const type = msg.type();

    if (type === 'error') {
      console_output.errors.push(text);
    } else if (type === 'warning') {
      console_output.warnings.push(text);
    } else if (type === 'log') {
      console_output.logs.push(text);
    }
  });

  // Capture request failures
  page.on('response', response => {
    if (response.status() >= 400 && response.url().includes('/api/')) {
      console_output.network_errors.push(`${response.status()} ${response.url()}`);
    }
  });

  try {
    const start = Date.now();
    await page.goto(`${BASE_URL}${path}`, {
      waitUntil: 'networkidle2',
      timeout: 30000
    });
    load_time = Date.now() - start;

    // Wait for render
    await page.waitForTimeout(1000);

    // Get page info
    const dom_count = await page.evaluate(() => document.querySelectorAll('*').length);
    const has_data = await page.evaluate(() => {
      const text = document.body.innerText.toLowerCase();
      return text.length > 100; // Simple heuristic: real data exists
    });

    await page.close();

    return {
      name,
      path,
      load_time,
      dom_count,
      has_data,
      status: 'loaded',
      ...console_output
    };
  } catch (error) {
    await page.close();
    return {
      name,
      path,
      status: 'failed',
      error: error.message,
      ...console_output
    };
  }
}

async function main() {
  console.log('\n' + '='.repeat(80));
  console.log('F12 BROWSER CONSOLE VALIDATION');
  console.log('='.repeat(80));
  console.log(`Base URL: ${BASE_URL}`);
  console.log(`Testing ${PAGES.length} pages...\n`);

  let browser;
  try {
    browser = await puppeteer.launch({
      headless: 'new',
      args: ['--disable-gpu', '--no-sandbox', '--disable-dev-shm-usage']
    });

    const results = [];

    for (const page_config of PAGES) {
      console.log(`📄 Testing ${page_config.name}...`);
      const result = await validatePage(browser, page_config.path, page_config.name);
      results.push(result);

      // Print result
      if (result.status === 'loaded') {
        console.log(`   ✓ Loaded in ${result.load_time}ms`);
        console.log(`   📊 DOM elements: ${result.dom_count}`);
        console.log(`   💾 Data loaded: ${result.has_data ? 'yes' : 'no'}`);
        console.log(`   🔴 Errors: ${result.errors.length}`);
        if (result.errors.length > 0) {
          result.errors.slice(0, 3).forEach(e => console.log(`      - ${e}`));
        }
        console.log(`   🟡 Warnings: ${result.warnings.length}`);
        if (result.warnings.length > 0) {
          result.warnings.slice(0, 2).forEach(w => console.log(`      - ${w}`));
        }
      } else {
        console.log(`   ✗ FAILED: ${result.error}`);
      }
      console.log('');
    }

    // Summary
    console.log('='.repeat(80));
    console.log('SUMMARY');
    console.log('='.repeat(80));
    const total_errors = results.reduce((sum, r) => sum + (r.errors ? r.errors.length : 0), 0);
    const total_warnings = results.reduce((sum, r) => sum + (r.warnings ? r.warnings.length : 0), 0);
    const pages_with_errors = results.filter(r => r.errors && r.errors.length > 0).length;
    const pages_loaded = results.filter(r => r.status === 'loaded').length;

    console.log(`✓ Pages loaded: ${pages_loaded}/${PAGES.length}`);
    console.log(`🔴 Total console errors: ${total_errors}`);
    console.log(`🟡 Total warnings: ${total_warnings}`);
    console.log(`⚠️  Pages with errors: ${pages_with_errors}/${PAGES.length}`);
    console.log('');

    if (total_errors === 0 && pages_loaded === PAGES.length) {
      console.log('✅ ALL PAGES CLEAN - NO CONSOLE ERRORS!');
    } else {
      console.log('❌ ISSUES FOUND - See details above');
    }

    // Save detailed report
    fs.writeFileSync('f12-validation-report.json', JSON.stringify(results, null, 2));
    console.log('\n📋 Detailed report saved to: f12-validation-report.json');
    console.log('='.repeat(80) + '\n');

  } catch (error) {
    console.error('Fatal error:', error.message);
    process.exit(1);
  } finally {
    if (browser) {
      await browser.close();
    }
  }
}

main().catch(console.error);

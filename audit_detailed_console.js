#!/usr/bin/env node
/**
 * Detailed console error audit - checks F12 for all error types
 */

const { chromium } = require('playwright');

const BASE_URL = 'http://localhost:5173';

const pages = [
  { path: '/', name: 'Home' },
  { path: '/app/markets', name: 'Markets Health' },
  { path: '/app/scores', name: 'Scores Dashboard' },
  { path: '/app/swing', name: 'Swing Candidates' },
  { path: '/app/deep-value', name: 'Deep Value Stocks' },
  { path: '/app/signals', name: 'Trading Signals' },
  { path: '/app/economic', name: 'Economic Dashboard' },
];

async function auditPage(browser, pageConfig) {
  const page = await browser.newPage();
  const allMessages = [];
  const networkErrors = [];
  const jsErrors = [];

  page.on('console', msg => {
    allMessages.push({
      type: msg.type(),
      text: msg.text(),
      args: msg.args().length,
    });
    if (msg.type() === 'error') jsErrors.push(msg.text());
  });

  page.on('response', response => {
    if (response.status() >= 400) {
      networkErrors.push({
        status: response.status(),
        url: response.url(),
        statusText: response.statusText(),
      });
    }
  });

  const url = `${BASE_URL}${pageConfig.path}`;

  try {
    await page.goto(url, { waitUntil: 'networkidle', timeout: 15000 });

    // Wait a bit for any deferred errors
    await page.waitForTimeout(1000);

    const result = {
      page: pageConfig.name,
      path: pageConfig.path,
      status: 'loaded',
      errors: jsErrors,
      warnings: allMessages.filter(m => m.type === 'warning').map(m => m.text).slice(0, 5),
      networkErrors: networkErrors.slice(0, 5),
      totalMessages: allMessages.length,
      errorCount: jsErrors.length,
      warningCount: allMessages.filter(m => m.type === 'warning').length,
    };

    if (jsErrors.length === 0 && networkErrors.length === 0) {
      console.log(`✅ ${pageConfig.name.padEnd(25)} - Clean console`);
    } else if (jsErrors.length > 0) {
      console.log(`❌ ${pageConfig.name.padEnd(25)} - ${jsErrors.length} JS errors`);
      jsErrors.slice(0, 3).forEach(e => console.log(`   └─ ${e.slice(0, 80)}`));
    } else if (networkErrors.length > 0) {
      console.log(`⚠️  ${pageConfig.name.padEnd(25)} - ${networkErrors.length} network errors`);
      networkErrors.forEach(e => console.log(`   └─ ${e.status} ${e.url.slice(0, 60)}`));
    }

    return result;

  } catch (error) {
    console.log(`❌ ${pageConfig.name.padEnd(25)} - Load error: ${error.message.slice(0, 60)}`);
    return {
      page: pageConfig.name,
      status: 'error',
      error: error.message,
    };
  } finally {
    await page.close();
  }
}

async function main() {
  console.log('🔍 DETAILED F12 CONSOLE AUDIT\n');
  const browser = await chromium.launch();
  const results = [];

  for (const pageConfig of pages) {
    const result = await auditPage(browser, pageConfig);
    results.push(result);
  }

  await browser.close();

  // Summary
  const cleanPages = results.filter(r => r.errorCount === 0).length;
  const pagesWithErrors = results.filter(r => r.errorCount > 0);

  console.log(`\n📊 SUMMARY: ${cleanPages}/${results.length} pages with clean F12 console`);

  if (pagesWithErrors.length > 0) {
    console.log('\n⚠️  PAGES WITH ERRORS:');
    pagesWithErrors.forEach(r => {
      console.log(`\n${r.page}:`);
      console.log(`  Total JS Errors: ${r.errors?.length || 0}`);
      if (r.errors && r.errors.length > 0) {
        r.errors.slice(0, 5).forEach(e => {
          console.log(`  - ${e.slice(0, 100)}`);
        });
      }
      if (r.networkErrors && r.networkErrors.length > 0) {
        console.log(`  Network Errors: ${r.networkErrors.length}`);
        r.networkErrors.forEach(e => {
          console.log(`  - ${e.status} ${e.url}`);
        });
      }
    });
  } else {
    console.log('\n✅ All pages have clean F12 console logs!');
  }
}

main().catch(console.error);

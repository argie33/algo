#!/usr/bin/env node
import { chromium } from 'playwright';

const PORT = 5173;
const BASE_URL = `http://localhost:${PORT}`;

const PAGES = [
  '/',
  '/app/markets',
  '/app/sectors',
  '/app/economic',
  '/app/sentiment',
  '/app/signals',
  '/app/deep-value',
  '/app/swing',
  '/app/backtest',
  '/app/scores',
  '/app/portfolio',
  '/app/performance',
  '/app/service-health',
  '/app/settings',
];

async function testPages() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();

  const results = {
    passed: [],
    failed: [],
    errors: [],
  };

  for (const pagePath of PAGES) {
    const page = await context.newPage();
    const pageErrors = [];

    page.on('console', msg => {
      if (msg.type() === 'error') {
        pageErrors.push(msg.text());
      }
    });

    try {
      const url = `${BASE_URL}${pagePath}`;
      console.log(`\n🧪 Testing ${pagePath}...`);

      const response = await page.goto(url, { waitUntil: 'load', timeout: 15000 });
      const status = response?.status();

      await page.waitForTimeout(1000);

      if (pageErrors.length === 0 && status === 200) {
        results.passed.push(pagePath);
        console.log(`  ✅ PASS (HTTP ${status}, ${pageErrors.length} errors)`);
      } else {
        results.failed.push(pagePath);
        console.log(`  ⚠️  FAIL (HTTP ${status}, ${pageErrors.length} errors)`);
        if (pageErrors.length > 0) {
          pageErrors.forEach(err => {
            console.log(`    ❌ ${err.slice(0, 80)}`);
            results.errors.push({ page: pagePath, error: err });
          });
        }
      }
    } catch (error) {
      results.failed.push(pagePath);
      console.log(`  ❌ ERROR: ${error.message.slice(0, 80)}`);
      results.errors.push({ page: pagePath, error: error.message });
    } finally {
      await page.close();
    }
  }

  await browser.close();

  // Summary
  console.log('\n' + '='.repeat(60));
  console.log('📊 TEST SUMMARY');
  console.log('='.repeat(60));
  console.log(`✅ Passed: ${results.passed.length}/${PAGES.length}`);
  console.log(`❌ Failed: ${results.failed.length}/${PAGES.length}`);

  if (results.failed.length > 0) {
    console.log('\n❌ Failed Pages:');
    results.failed.forEach(page => {
      console.log(`  - ${page}`);
    });
  }

  if (results.errors.length > 0) {
    console.log('\n🔴 Errors Found:');
    const uniqueErrors = {};
    results.errors.forEach(({ error }) => {
      if (!uniqueErrors[error]) {
        uniqueErrors[error] = 0;
      }
      uniqueErrors[error]++;
    });
    Object.entries(uniqueErrors).forEach(([error, count]) => {
      console.log(`  (${count}x) ${error.slice(0, 100)}`);
    });
  } else {
    console.log('\n✅ No errors detected across all pages!');
  }

  console.log('\n');
  process.exit(results.failed.length > 0 ? 1 : 0);
}

testPages();

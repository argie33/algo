#!/usr/bin/env node
import puppeteer from 'puppeteer-core';

const BASE_URL = 'http://localhost:5173';
const chromePath = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';

const testPages = [
  // Public marketing pages
  { path: '/', name: 'Home', type: 'marketing' },
  { path: '/about', name: 'About', type: 'marketing' },
  { path: '/firm', name: 'Firm', type: 'marketing' },
  { path: '/contact', name: 'Contact', type: 'marketing' },

  // Dashboard pages (no auth)
  { path: '/app/markets', name: 'Markets', type: 'dashboard', minElements: 50 },
  { path: '/app/economic', name: 'Economic', type: 'dashboard', minElements: 20 },
  { path: '/app/sectors', name: 'Sectors', type: 'dashboard', minElements: 20 },
  { path: '/app/sentiment', name: 'Sentiment', type: 'dashboard', minElements: 10 },
  { path: '/app/deep-value', name: 'Deep Value', type: 'dashboard', minElements: 50 },
  { path: '/app/trading-signals', name: 'Trading Signals', type: 'dashboard', minElements: 100 },
  { path: '/app/swing', name: 'Swing Candidates', type: 'dashboard', minElements: 10 },
  { path: '/app/scores', name: 'Scores', type: 'dashboard', minElements: 50 },
  { path: '/app/backtests', name: 'Backtests', type: 'dashboard', minElements: 10 },
];

async function checkPage(browser, url, pageName, minElements = 0) {
  const page = await browser.newPage();
  const issues = [];
  const metrics = { errors: 0, warnings: 0, dataElements: 0, pageText: 0 };

  page.on('console', msg => {
    const type = msg.type();
    if (type === 'error') metrics.errors++;
    if (type === 'warning') metrics.warnings++;
  });

  page.on('pageerror', err => {
    issues.push(`JS Error: ${err.message.substring(0,80)}`);
  });

  try {
    await page.goto(url, { waitUntil: 'networkidle2', timeout: 15000 });
    await new Promise(r => setTimeout(r, 2000));

    const data = await page.evaluate(() => {
      const tables = document.querySelectorAll('table tbody tr').length;
      const cards = document.querySelectorAll('[class*="Card"], [role="region"]').length;
      const text = document.body.innerText.length;
      const hasNulls = document.body.innerText.match(/—/g)?.length || 0;
      return { tables, cards, text, hasNulls };
    });

    metrics.dataElements = data.tables + data.cards;
    metrics.pageText = data.text;

    if (minElements > 0 && metrics.dataElements < minElements) {
      issues.push(`Low data: ${metrics.dataElements}/${minElements} elements`);
    }
    if (data.hasNulls > 10) {
      issues.push(`Many dashes: ${data.hasNulls} "—" symbols (incomplete data)`);
    }

  } catch (error) {
    issues.push(`Load failed: ${error.message.substring(0,60)}`);
  }

  await page.close();
  return { metrics, issues };
}

async function main() {
  console.log('COMPREHENSIVE PAGE VERIFICATION');
  console.log('=' .repeat(80));

  let browser;
  try {
    browser = await puppeteer.launch({
      executablePath: chromePath,
      headless: true,
      args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu'],
    });

    const results = [];
    let passed = 0, failed = 0;

    for (const p of testPages) {
      const url = `${BASE_URL}${p.path}`;
      process.stdout.write(`Testing ${p.name.padEnd(20)} ... `);

      const result = await checkPage(browser, url, p.name, p.minElements);
      const status = result.issues.length === 0 ? 'PASS' : 'FAIL';
      console.log(status);

      results.push({
        page: p.name,
        path: p.path,
        ...result,
        status,
      });

      if (result.issues.length === 0) passed++; else failed++;

      if (result.issues.length > 0) {
        result.issues.forEach(issue => console.log(`    ⚠️ ${issue}`));
      }
    }

    console.log('\n' + '='.repeat(80));
    console.log(`FINAL RESULTS: ${passed} PASSED, ${failed} FAILED out of ${testPages.length}`);
    console.log('='.repeat(80));

    if (failed > 0) {
      console.log('\nFAILED PAGES:');
      results.filter(r => r.status === 'FAIL').forEach(r => {
        console.log(`  ${r.page} (${r.path})`);
        r.issues.forEach(i => console.log(`    - ${i}`));
      });
    } else {
      console.log('\n✅ ALL PAGES PASSED VERIFICATION');
    }

    process.exit(failed > 0 ? 1 : 0);
  } catch (error) {
    console.error('Error:', error.message);
    process.exit(1);
  } finally {
    if (browser) await browser.disconnect();
  }
}

main();

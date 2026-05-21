/**
 * Comprehensive Page Audit v2
 * Tests all 13 pages for data completeness, console errors, and API integrity
 */

const { chromium } = require('playwright');
const fs = require('fs');

const BASE_URL = 'http://localhost:5173';

const PAGES = [
  { path: '/', name: 'Home (Marketing)', type: 'public' },
  { path: '/app/markets', name: 'Markets Health', type: 'app' },
  { path: '/app/economic', name: 'Economic Dashboard', type: 'app' },
  { path: '/app/sectors', name: 'Sector Analysis', type: 'app' },
  { path: '/app/sentiment', name: 'Sentiment', type: 'app' },
  { path: '/app/trading-signals', name: 'Trading Signals', type: 'app' },
  { path: '/app/deep-value', name: 'Deep Value Stocks', type: 'app' },
  { path: '/app/swing', name: 'Swing Candidates', type: 'app' },
  { path: '/app/scores', name: 'Scores Dashboard', type: 'app' },
  { path: '/app/backtests', name: 'Backtests', type: 'app' },
  { path: '/app/portfolio', name: 'Portfolio', type: 'app' },
  { path: '/app/trades', name: 'Trade Tracker', type: 'app' },
  { path: '/app/performance', name: 'Performance', type: 'app' },
];

async function auditPage(page, pageUrl, pageName) {
  const result = {
    name: pageName,
    url: pageUrl,
    timestamp: new Date().toISOString(),
    consoleErrors: [],
    consoleWarnings: [],
    dataStatus: { emptyTables: 0, nullFields: 0, dataElements: 0, charts: 0 },
    loadTime: 0,
    hasErrors: false,
    allDataLoaded: false,
  };

  // Collect errors & warnings
  page.on('console', msg => {
    if (msg.type() === 'error') result.consoleErrors.push(msg.text());
    if (msg.type() === 'warning') result.consoleWarnings.push(msg.text());
  });

  page.on('pageerror', err => {
    result.consoleErrors.push(err.toString());
  });

  try {
    const startTime = Date.now();
    console.log(`🔍 Auditing ${pageName}...`);

    await page.goto(`${BASE_URL}${pageUrl}`, { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(1500); // Wait for data to load

    result.loadTime = Date.now() - startTime;

    // Check for empty tables
    const emptyRows = await page.locator('table tbody tr').count();
    result.dataStatus.emptyTables = emptyRows;

    // Count null/empty indicators by evaluating page content
    const nullCount = (await page.evaluate(() => {
      return document.body.innerText.match(/null|undefined|—|n\/a/gi)?.length || 0;
    })) || 0;
    result.dataStatus.nullFields = nullCount;

    // Count data elements
    result.dataStatus.dataElements = await page.locator('[class*="card"], [class*="metric"], [class*="value"]').count();
    result.dataStatus.charts = await page.locator('canvas, [class*="chart"], svg').count();

    // Check for "generic message" endpoints
    const pageText = await page.locator('body').innerText();
    const genericMessages = [
      'generic help message',
      'use /leading-indicators',
      'use /summary',
      'not available',
      'no data available',
    ];
    const hasGenericMsg = genericMessages.some(msg => pageText.toLowerCase().includes(msg));

    // Overall status
    result.hasErrors = result.consoleErrors.length > 0;
    result.allDataLoaded = result.dataStatus.dataElements > 0 && nullCount < 10 && emptyRows === 0;

    // Grade
    let grade = '✅';
    if (result.hasErrors) grade = '❌';
    else if (result.dataStatus.nullFields > 20) grade = '⚠️';
    else if (result.dataStatus.dataElements === 0) grade = '⚠️';

    console.log(`   ${grade} Loaded: ${result.loadTime}ms | Data elements: ${result.dataStatus.dataElements} | Nulls: ${nullCount} | Errors: ${result.consoleErrors.length}`);

    return result;
  } catch (error) {
    console.log(`   ❌ LOAD FAILED: ${error.message.substring(0, 60)}`);
    result.hasErrors = true;
    result.consoleErrors.push(`Page load failed: ${error.message}`);
    return result;
  }
}

async function main() {
  console.log('🚀 COMPREHENSIVE PAGE AUDIT v2\n');

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  const results = {
    timestamp: new Date().toISOString(),
    pages: {},
    summary: {
      totalPages: PAGES.length,
      pagesWithErrors: 0,
      pagesWithoutData: 0,
      fullyWorkingPages: 0,
      avgNullFields: 0,
      avgLoadTime: 0,
    },
  };

  for (const p of PAGES) {
    results.pages[p.path] = await auditPage(page, p.path, p.name);
  }

  // Calculate summary
  const pageResults = Object.values(results.pages);
  results.summary.pagesWithErrors = pageResults.filter(r => r.hasErrors).length;
  results.summary.pagesWithoutData = pageResults.filter(r => r.dataStatus.dataElements === 0).length;
  results.summary.fullyWorkingPages = pageResults.filter(r => r.allDataLoaded && !r.hasErrors).length;
  results.summary.avgNullFields = Math.round(pageResults.reduce((sum, r) => sum + r.dataStatus.nullFields, 0) / pageResults.length);
  results.summary.avgLoadTime = Math.round(pageResults.reduce((sum, r) => sum + r.loadTime, 0) / pageResults.length);

  // Print summary
  console.log('\n📊 SUMMARY');
  console.log(`   Pages audited: ${results.summary.totalPages}`);
  console.log(`   ✅ Fully working: ${results.summary.fullyWorkingPages}`);
  console.log(`   ⚠️  With nulls: ${pageResults.filter(r => r.dataStatus.nullFields > 10 && r.dataStatus.nullFields < 50).length}`);
  console.log(`   ❌ With errors: ${results.summary.pagesWithErrors}`);
  console.log(`   ❌ No data: ${results.summary.pagesWithoutData}`);
  console.log(`   Avg load time: ${results.summary.avgLoadTime}ms`);
  console.log(`   Avg null fields: ${results.summary.avgNullFields}`);

  // List problem pages
  const problemPages = pageResults.filter(r => r.consoleErrors.length > 0 || r.dataStatus.dataElements === 0);
  if (problemPages.length > 0) {
    console.log('\n🔴 PROBLEM PAGES:');
    problemPages.forEach(p => {
      console.log(`   ${p.name}:`);
      if (p.consoleErrors.length > 0) console.log(`      ❌ ${p.consoleErrors.length} console errors`);
      if (p.dataStatus.dataElements === 0) console.log(`      ❌ No data elements found`);
      if (p.dataStatus.nullFields > 50) console.log(`      ⚠️ ${p.dataStatus.nullFields} null fields`);
    });
  }

  // Save report
  fs.writeFileSync('audit_v2_report.json', JSON.stringify(results, null, 2));
  console.log('\n✅ Report saved to audit_v2_report.json');

  await browser.close();
  process.exit(results.summary.pagesWithErrors > 0 ? 1 : 0);
}

main();

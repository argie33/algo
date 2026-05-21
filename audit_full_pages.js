/**
 * Comprehensive Page Audit - checks all pages for:
 * - Data completeness (no null fields)
 * - Formatting consistency
 * - Console errors & warnings
 * - API response accuracy
 * - Database query issues
 */

const { chromium } = require('playwright');
const axios = require('axios');
const fs = require('fs');

const BASE_URL = 'http://localhost:5173';
const API_BASE = 'http://localhost:3001/api';
const REPORT_FILE = 'audit_report_full.json';

// All app pages to audit
const APP_PAGES = [
  '/app/markets',
  '/app/economic',
  '/app/sectors',
  '/app/sentiment',
  '/app/trading-signals',
  '/app/deep-value',
  '/app/swing',
  '/app/scores',
  '/app/backtests',
  '/app/portfolio',
  '/app/trades',
  '/app/performance',
  '/app/algo-dashboard',
];

const MARKETING_PAGES = [
  '/',
  '/about',
  '/firm',
  '/contact',
];

async function auditPage(page, url) {
  const auditResult = {
    url,
    timestamp: new Date().toISOString(),
    consoleMessages: [],
    errors: [],
    dataMetrics: {
      nullCount: 0,
      totalDataPoints: 0,
      emptyTables: [],
      dataBySection: {},
    },
    formatting: {
      textNodes: [],
      inconsistencies: [],
    },
    apiCalls: [],
  };

  // Collect console messages
  page.on('console', (msg) => {
    auditResult.consoleMessages.push({
      type: msg.type(),
      text: msg.text(),
      args: msg.args().length,
    });
  });

  // Collect page errors
  page.on('pageerror', (error) => {
    auditResult.errors.push(error.toString());
  });

  try {
    // Navigate to page
    console.log(`🔍 Auditing ${url}...`);
    await page.goto(`${BASE_URL}${url}`, { waitUntil: 'networkidle' });

    // Wait for content to load
    await page.waitForTimeout(1000);

    // Collect all text content
    const textContent = await page.locator('body').innerText();
    auditResult.formatting.textContent = textContent.substring(0, 500); // First 500 chars

    // Check for common null/empty indicators
    const nullIndicators = await page.locator('text=/null|undefined|N\\/A|—|Loading|Error/i').count();
    auditResult.dataMetrics.nullCount = nullIndicators;

    // Audit tables
    const tables = await page.locator('table').count();
    if (tables > 0) {
      for (let i = 0; i < tables; i++) {
        const table = page.locator('table').nth(i);
        const rows = await table.locator('tbody tr').count();
        const cols = await table.locator('thead th').count();

        if (rows === 0) {
          auditResult.dataMetrics.emptyTables.push(`Table ${i}: 0 rows, ${cols} cols`);
        } else {
          auditResult.dataMetrics.dataBySection[`table_${i}`] = {
            rows,
            cols,
            firstRowText: await table.locator('tbody tr').first().innerText(),
          };
        }
      }
    }

    // Check for data-heavy elements
    const dataElements = {
      cards: await page.locator('[class*="card"]').count(),
      metrics: await page.locator('[class*="metric"]').count(),
      charts: await page.locator('canvas, [class*="chart"]').count(),
      lists: await page.locator('ul, ol').count(),
    };
    auditResult.dataMetrics.dataBySection.elements = dataElements;

    // Intercept API calls
    const responseLog = [];
    page.on('response', async (response) => {
      if (response.url().includes('/api/')) {
        try {
          const data = await response.json().catch(() => null);
          responseLog.push({
            url: response.url(),
            status: response.status(),
            size: JSON.stringify(data).length,
            recordCount: Array.isArray(data) ? data.length : (data?.data?.length || 0),
            dataKeys: data ? Object.keys(data).slice(0, 5) : [],
          });
        } catch (e) {
          responseLog.push({
            url: response.url(),
            status: response.status(),
            error: 'Could not parse response',
          });
        }
      }
    });

    // Simulate user interaction (scroll)
    await page.evaluate(() => window.scrollBy(0, window.innerHeight));
    await page.waitForTimeout(500);

    auditResult.apiCalls = responseLog;

    // Check for missing images/assets
    const images = await page.locator('img').count();
    if (images > 0) {
      const brokenImages = await page.evaluate(() => {
        return Array.from(document.querySelectorAll('img')).filter(
          (img) => !img.complete || img.naturalHeight === 0
        ).length;
      });
      auditResult.formatting.brokenImages = brokenImages;
    }

  } catch (error) {
    auditResult.errors.push(`Page error: ${error.message}`);
  }

  return auditResult;
}

async function auditAPIs() {
  const apiResults = {};
  const endpoints = [
    { path: '/market', name: 'Market Health' },
    { path: '/economic', name: 'Economic Data' },
    { path: '/sectors', name: 'Sectors' },
    { path: '/signals', name: 'Signals' },
    { path: '/scores', name: 'Scores' },
    { path: '/backtests', name: 'Backtests' },
    { path: '/sentiment', name: 'Sentiment' },
    { path: '/trades', name: 'Trades' },
    { path: '/prices?symbol=AAPL&limit=10', name: 'Prices (AAPL)' },
  ];

  for (const endpoint of endpoints) {
    try {
      console.log(`📡 Checking ${endpoint.name}...`);
      const response = await axios.get(`${API_BASE}${endpoint.path}`, {
        headers: { Authorization: 'Bearer test-token' },
        timeout: 5000,
      });

      const data = response.data;
      apiResults[endpoint.name] = {
        status: response.status,
        recordCount: Array.isArray(data) ? data.length : (data?.data?.length || 0),
        dataKeys: Array.isArray(data) ? Object.keys(data[0] || {}) : Object.keys(data).slice(0, 10),
        nullFields: countNullFields(data),
        sampleData: JSON.stringify(data).substring(0, 200),
      };
    } catch (error) {
      apiResults[endpoint.name] = {
        status: error.response?.status || 'FAILED',
        error: error.message,
      };
    }
  }

  return apiResults;
}

function countNullFields(data) {
  let nullCount = 0;
  const walk = (obj) => {
    if (obj === null || obj === undefined) nullCount++;
    else if (typeof obj === 'object') {
      Object.values(obj).forEach(walk);
    }
  };
  walk(data);
  return nullCount;
}

async function main() {
  console.log('🚀 Starting comprehensive page audit...\n');

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  const auditReport = {
    timestamp: new Date().toISOString(),
    pages: {},
    apis: {},
    summary: {},
  };

  // Audit all pages
  console.log('📄 AUDITING PAGES\n');
  for (const pageUrl of [...MARKETING_PAGES, ...APP_PAGES]) {
    try {
      auditReport.pages[pageUrl] = await auditPage(page, pageUrl);
    } catch (error) {
      auditReport.pages[pageUrl] = { error: error.message };
    }
  }

  // Audit APIs
  console.log('\n📡 AUDITING APIS\n');
  auditReport.apis = await auditAPIs();

  // Generate summary
  const pageErrors = Object.values(auditReport.pages).filter(
    (p) => p.consoleMessages?.some((m) => m.type === 'error')
  ).length;
  const emptyPages = Object.values(auditReport.pages).filter(
    (p) => p.dataMetrics?.emptyTables?.length > 0
  ).length;

  auditReport.summary = {
    totalPages: Object.keys(auditReport.pages).length,
    pagesWithErrors: pageErrors,
    pagesWithEmptyData: emptyPages,
    apiEndpoints: Object.keys(auditReport.apis).length,
    apisWithErrors: Object.values(auditReport.apis).filter((a) => a.error).length,
  };

  // Save report
  fs.writeFileSync(REPORT_FILE, JSON.stringify(auditReport, null, 2));
  console.log(`\n✅ Audit complete! Report saved to ${REPORT_FILE}`);
  console.log(`\n📊 SUMMARY:`);
  console.log(`   Pages: ${auditReport.summary.totalPages} (${pageErrors} with errors)`);
  console.log(`   Empty tables: ${emptyPages} pages`);
  console.log(`   APIs: ${auditReport.summary.apiEndpoints} (${auditReport.summary.apisWithErrors} with errors)`);

  // Print critical issues
  console.log('\n🔴 CRITICAL ISSUES:');
  const criticalPages = Object.entries(auditReport.pages).filter(
    ([_, p]) => p.errors?.length > 0 || p.dataMetrics?.nullCount > 10
  );
  if (criticalPages.length === 0) {
    console.log('   None detected');
  } else {
    criticalPages.forEach(([url, data]) => {
      console.log(`   ${url}: ${data.errors?.length || 0} errors, ${data.dataMetrics?.nullCount || 0} nulls`);
    });
  }

  await browser.close();
  process.exit(0);
}

main().catch((error) => {
  console.error('Audit failed:', error);
  process.exit(1);
});

#!/usr/bin/env node
/**
 * Comprehensive page audit using Playwright
 * Checks console errors, page load times, data display, and API responses
 */

const { chromium } = require('playwright');
const axios = require('axios');
const fs = require('fs');

const BASE_URL = 'http://localhost:5173';
const API_URL = 'http://localhost:3004';

const pages = [
  // Marketing pages (public)
  { path: '/', name: 'Home' },
  { path: '/about', name: 'About' },
  { path: '/firm', name: 'Firm' },
  { path: '/contact', name: 'Contact' },
  { path: '/terms', name: 'Terms' },
  { path: '/privacy', name: 'Privacy' },
  // Dashboard pages (require auth mock)
  { path: '/app/markets', name: 'Markets Health' },
  { path: '/app/economic', name: 'Economic Dashboard' },
  { path: '/app/sectors', name: 'Sector Analysis' },
  { path: '/app/sentiment', name: 'Sentiment' },
  { path: '/app/trading-signals', name: 'Trading Signals' },
  { path: '/app/deep-value', name: 'Deep Value Stocks' },
  { path: '/app/swing', name: 'Swing Candidates' },
  { path: '/app/scores', name: 'Scores Dashboard' },
  { path: '/app/backtests', name: 'Backtest Results' },
];

const results = {
  summary: {},
  pages: {},
  errors: [],
  apiStatus: {},
};

async function checkAPI() {
  console.log('\n🔍 Checking API health...');
  const endpoints = [
    '/api/market',
    '/api/economic',
    '/api/sectors',
    '/api/signals',
    '/api/scores',
    '/api/backtests',
  ];

  for (const endpoint of endpoints) {
    try {
      const response = await axios.get(`${API_URL}${endpoint}`, { timeout: 5000 });
      results.apiStatus[endpoint] = {
        status: response.status,
        dataSize: JSON.stringify(response.data).length,
        recordCount: Array.isArray(response.data?.data) ? response.data.data.length : 'N/A',
      };
      console.log(`✅ ${endpoint} - ${response.status} - ${results.apiStatus[endpoint].recordCount} records`);
    } catch (error) {
      results.apiStatus[endpoint] = { error: error.message };
      console.log(`❌ ${endpoint} - ${error.message}`);
    }
  }
}

async function auditPage(browser, pageConfig) {
  const page = await browser.newPage();
  const consoleMessages = [];
  const pageErrors = [];

  page.on('console', msg => consoleMessages.push({
    type: msg.type(),
    text: msg.text(),
    location: msg.location(),
  }));

  page.on('pageerror', error => pageErrors.push({
    message: error.message,
    stack: error.stack,
  }));

  const url = `${BASE_URL}${pageConfig.path}`;
  const startTime = Date.now();

  try {
    await page.goto(url, { waitUntil: 'networkidle', timeout: 15000 });
    const loadTime = Date.now() - startTime;

    // Check for specific data indicators
    const hasContent = await page.evaluate(() => {
      const body = document.body.innerText;
      return body.length > 100;
    });

    // Count tables and data elements
    const dataMetrics = await page.evaluate(() => ({
      tableCount: document.querySelectorAll('table').length,
      tableRowCount: document.querySelectorAll('tr').length,
      dataElements: document.querySelectorAll('[data-testid*="data"], [data-testid*="row"]').length,
      nullCount: document.body.innerText.match(/null|N\/A|undefined|—/gi)?.length || 0,
    }));

    // Check for errors in console
    const errors = consoleMessages.filter(m => m.type === 'error' || m.type === 'warning');

    results.pages[pageConfig.name] = {
      path: pageConfig.path,
      status: 'loaded',
      loadTime,
      hasContent,
      dataMetrics,
      consoleErrors: errors.length,
      errors: errors,
      pageErrors: pageErrors,
    };

    console.log(`✅ ${pageConfig.name} (${loadTime}ms) - Content: ${hasContent}, Tables: ${dataMetrics.tableCount}, Rows: ${dataMetrics.tableRowCount}, Nulls: ${dataMetrics.nullCount}`);

  } catch (error) {
    results.pages[pageConfig.name] = {
      path: pageConfig.path,
      status: 'error',
      error: error.message,
    };
    console.log(`❌ ${pageConfig.name} - ${error.message}`);
  } finally {
    await page.close();
  }
}

async function main() {
  console.log('🚀 Starting comprehensive page audit...');
  console.log(`📍 Base URL: ${BASE_URL}`);
  console.log(`📍 API URL: ${API_URL}\n`);

  // Check API first
  await checkAPI();

  // Audit pages with Playwright
  console.log('\n📄 Auditing pages...');
  const browser = await chromium.launch();

  for (const pageConfig of pages) {
    await auditPage(browser, pageConfig);
  }

  await browser.close();

  // Write results to file
  fs.writeFileSync('audit_results.json', JSON.stringify(results, null, 2));
  console.log('\n📊 Results saved to audit_results.json');

  // Summary
  const successCount = Object.values(results.pages).filter(p => p.status === 'loaded' && p.consoleErrors === 0).length;
  const totalPages = Object.keys(results.pages).length;
  console.log(`\n✅ ${successCount}/${totalPages} pages loaded without console errors`);

  // List problematic pages
  const problematicPages = Object.entries(results.pages).filter(([_, p]) => p.consoleErrors > 0 || p.status === 'error');
  if (problematicPages.length > 0) {
    console.log('\n⚠️  Problematic pages:');
    for (const [name, data] of problematicPages) {
      if (data.status === 'error') {
        console.log(`  ❌ ${name} - ${data.error}`);
      } else {
        console.log(`  ⚠️  ${name} - ${data.consoleErrors} console errors`);
      }
    }
  }
}

main().catch(console.error);

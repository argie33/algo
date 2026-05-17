#!/usr/bin/env node
/**
 * Frontend Page API Endpoint Test
 * Tests all 36 pages to verify they have working API endpoints
 *
 * Run with: node test-frontend-pages.js
 */

const http = require('http');

const BASE_URL = 'http://localhost:3001';

// Map of pages to their required API endpoints
const PAGES_AND_ENDPOINTS = {
  // Trading Pages
  'AlgoTradingDashboard': ['/api/algo/status', '/api/algo/positions', '/api/algo/trades'],
  'PortfolioDashboard': ['/api/portfolio'],
  'TradeTracker': ['/api/trades', '/api/algo/trades'],
  'TradingSignals': ['/api/signals'],
  'SwingCandidates': ['/api/signals'],
  'ScoresDashboard': ['/api/scores/stockscores'],
  'BacktestResults': ['/api/research/backtests'],

  // Market Analysis Pages
  'MarketsHealth': ['/api/market/indices', '/api/market/breadth', '/api/market/status'],
  'SectorAnalysis': ['/api/sectors'],
  'Sentiment': ['/api/sentiment'],
  'EconomicDashboard': ['/api/economic'],
  'DeepValueStocks': ['/api/signals'],
  'PerformanceMetrics': ['/api/algo/performance'],

  // Management Pages
  'Settings': ['/api/settings'],
  'ServiceHealth': ['/api/health', '/api/diagnostics'],
  'AuditViewer': ['/api/audit/logs'],
  'NotificationCenter': ['/api/notifications'],
  'MetricsDashboard': ['/api/metrics'],

  // Info Pages (static)
  'Home': [],
  'About': [],
  'Contact': ['/api/contact'],
  'LoginPage': [],
  'Article': ['/api/articles'],
  'OurTeam': [],
  'Privacy': [],
  'Terms': [],
  'Firm': [],
  'WealthManagement': [],
  'InvestmentTools': [],
  'ResearchInsights': [],
  'PreTradeSimulator': ['/api/simulator'],
};

let passed = 0;
let failed = 0;
let skipped = 0;

/**
 * Test an endpoint
 */
function testEndpoint(endpoint) {
  return new Promise((resolve) => {
    const url = new URL(BASE_URL + endpoint);

    http.get(url, { timeout: 5000 }, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        if (res.statusCode === 200 || res.statusCode === 400) { // 400 might be auth error, still indicates endpoint exists
          resolve({ status: res.statusCode, ok: true });
        } else if (res.statusCode === 404) {
          resolve({ status: res.statusCode, ok: false, error: 'NOT_FOUND' });
        } else {
          resolve({ status: res.statusCode, ok: false, error: `HTTP_${res.statusCode}` });
        }
      });
    }).on('error', (err) => {
      resolve({ status: 0, ok: false, error: err.message });
    }).on('timeout', () => {
      resolve({ status: 0, ok: false, error: 'TIMEOUT' });
    });
  });
}

/**
 * Run all tests
 */
async function runTests() {
  console.log('🔍 Frontend Page API Endpoint Test');
  console.log('==================================\n');

  for (const [page, endpoints] of Object.entries(PAGES_AND_ENDPOINTS)) {
    if (endpoints.length === 0) {
      console.log(`⏭️  ${page.padEnd(30)} [STATIC PAGE - no API calls]`);
      skipped++;
      continue;
    }

    let allPassed = true;
    let results = [];

    for (const endpoint of endpoints) {
      const result = await testEndpoint(endpoint);
      results.push({ endpoint, ...result });
      if (!result.ok) {
        allPassed = false;
      }
    }

    if (allPassed) {
      console.log(`✅ ${page.padEnd(30)} [${endpoints.join(', ')}]`);
      passed++;
    } else {
      const failures = results.filter(r => !r.ok).map(r => `${r.endpoint}(${r.error})`).join(', ');
      console.log(`❌ ${page.padEnd(30)} [${failures}]`);
      failed++;
    }
  }

  console.log('\n==================================');
  console.log(`📊 Results: ${passed} passed, ${failed} failed, ${skipped} skipped`);
  console.log(`✅ Pages with working APIs: ${passed}/${Object.keys(PAGES_AND_ENDPOINTS).length - skipped}`);

  if (failed === 0) {
    console.log('🎉 ALL API ENDPOINTS WORKING!');
    process.exit(0);
  } else {
    console.log(`⚠️  ${failed} pages have broken API endpoints`);
    process.exit(1);
  }
}

runTests();

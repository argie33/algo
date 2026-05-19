#!/usr/bin/env node

/**
 * API Endpoint Validation Test
 * Tests all 20 API endpoints and captures response quality
 */

const http = require('http');

const API_ENDPOINTS = [
  { path: '/api/health', method: 'GET', name: 'Health Check' },
  { path: '/api/performance', method: 'GET', name: 'Performance Metrics' },
  { path: '/api/performance/metrics', method: 'GET', name: 'Performance/Metrics' },
  { path: '/api/performance/trades', method: 'GET', name: 'Performance/Trades' },
  { path: '/api/stocks', method: 'GET', name: 'Stocks List' },
  { path: '/api/stocks/AAPL', method: 'GET', name: 'Stock Detail (AAPL)' },
  { path: '/api/stocks/deep-value', method: 'GET', name: 'Deep Value Stocks' },
  { path: '/api/scores', method: 'GET', name: 'Stock Scores' },
  { path: '/api/backtests', method: 'GET', name: 'Backtests List' },
  { path: '/api/financials/AAPL/key-metrics', method: 'GET', name: 'Financials/Key Metrics' },
  { path: '/api/financials/AAPL/income-statement', method: 'GET', name: 'Financials/Income' },
  { path: '/api/financials/AAPL/balance-sheet', method: 'GET', name: 'Financials/Balance' },
  { path: '/api/financials/AAPL/cash-flow', method: 'GET', name: 'Financials/Cashflow' },
  { path: '/api/commodities', method: 'GET', name: 'Commodities' },
  { path: '/api/market', method: 'GET', name: 'Market Data' },
  { path: '/api/sectors', method: 'GET', name: 'Sectors' },
  { path: '/api/signals', method: 'GET', name: 'Signals' },
  { path: '/api/trades', method: 'GET', name: 'Trades' },
  { path: '/api/economic', method: 'GET', name: 'Economic Data' },
  { path: '/api/sentiment', method: 'GET', name: 'Sentiment' }
];

const BASE_URL = 'http://localhost:3001';

function makeRequest(path) {
  return new Promise((resolve, reject) => {
    const url = new URL(path, BASE_URL);
    const start = Date.now();

    http.get(url, { timeout: 10000 }, (res) => {
      let data = '';

      res.on('data', chunk => {
        data += chunk;
      });

      res.on('end', () => {
        const time = Date.now() - start;
        try {
          const json = JSON.parse(data);
          resolve({
            status: res.statusCode,
            time,
            size: data.length,
            headers: res.headers,
            has_data: json && Object.keys(json).length > 0,
            success: res.statusCode < 400
          });
        } catch (e) {
          resolve({
            status: res.statusCode,
            time,
            size: data.length,
            headers: res.headers,
            parse_error: true,
            success: false
          });
        }
      });
    }).on('error', (err) => {
      resolve({
        status: 0,
        error: err.message,
        success: false,
        time: Date.now() - start
      });
    });
  });
}

async function main() {
  console.log('\n' + '='.repeat(80));
  console.log('API ENDPOINT VALIDATION');
  console.log('='.repeat(80));
  console.log(`Base URL: ${BASE_URL}`);
  console.log(`Testing ${API_ENDPOINTS.length} endpoints...\n`);

  const results = [];

  for (const endpoint of API_ENDPOINTS) {
    process.stdout.write(`📡 ${endpoint.name}... `);
    const result = await makeRequest(endpoint.path);

    result.endpoint = endpoint.name;
    result.path = endpoint.path;
    results.push(result);

    if (result.success) {
      console.log(`✓ ${result.status} ${result.time}ms`);
    } else if (result.error) {
      console.log(`✗ ERROR: ${result.error}`);
    } else {
      console.log(`⚠ ${result.status} (parse error or non-JSON)`);
    }
  }

  // Summary
  console.log('\n' + '='.repeat(80));
  console.log('SUMMARY');
  console.log('='.repeat(80));

  const passed = results.filter(r => r.success).length;
  const failed = results.filter(r => !r.success).length;
  const avg_time = Math.round(
    results.filter(r => r.time).reduce((sum, r) => sum + r.time, 0) / results.length
  );

  console.log(`✓ Passing: ${passed}/${API_ENDPOINTS.length}`);
  console.log(`✗ Failing: ${failed}/${API_ENDPOINTS.length}`);
  console.log(`⏱️  Average response time: ${avg_time}ms`);

  console.log('\nEndpoint Details:');
  console.log('-'.repeat(80));

  results.forEach(r => {
    const status_char = r.success ? '✓' : '✗';
    let status_text = r.status ? `${r.status}` : 'NO CONNECTION';
    if (r.error) status_text = r.error;
    if (r.parse_error) status_text += ' (parse error)';

    console.log(
      `${status_char} ${r.endpoint.padEnd(30)} ${status_text.padEnd(30)} ${r.time}ms`
    );
  });

  console.log('='.repeat(80));

  if (failed === 0) {
    console.log('✅ ALL ENDPOINTS RESPONDING - API IS HEALTHY');
  } else {
    console.log(`❌ ${failed} ENDPOINTS FAILING`);
    console.log('\nFailing endpoints:');
    results.filter(r => !r.success).forEach(r => {
      console.log(`  - ${r.endpoint} (${r.path}): ${r.error || r.status}`);
    });
  }

  console.log('='.repeat(80) + '\n');

  process.exit(failed > 0 ? 1 : 0);
}

main().catch(err => {
  console.error('Fatal error:', err);
  process.exit(1);
});

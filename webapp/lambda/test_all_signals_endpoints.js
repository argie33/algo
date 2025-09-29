#!/usr/bin/env node

/**
 * Comprehensive Trading Signals API Endpoint Testing Script
 * Tests all signals endpoints to identify 404s, errors, and missing functionality
 */

const http = require('http');
const https = require('https');

const BASE_URL = 'http://localhost:3001';
const TEST_SYMBOL = 'AAPL';
const TEST_SYMBOLS = ['AAPL', 'TSLA', 'GOOGL', 'META'];

// Helper function to make HTTP requests
function makeRequest(url, method = 'GET', data = null) {
  return new Promise((resolve, reject) => {
    const urlObj = new URL(url);
    const options = {
      hostname: urlObj.hostname,
      port: urlObj.port,
      path: urlObj.pathname + urlObj.search,
      method: method,
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer dev-bypass-token' // For authenticated routes
      }
    };

    if (data) {
      const postData = JSON.stringify(data);
      options.headers['Content-Length'] = Buffer.byteLength(postData);
    }

    const req = http.request(options, (res) => {
      let body = '';
      res.on('data', (chunk) => {
        body += chunk;
      });
      res.on('end', () => {
        try {
          const jsonData = JSON.parse(body);
          resolve({
            status: res.statusCode,
            headers: res.headers,
            data: jsonData
          });
        } catch (e) {
          resolve({
            status: res.statusCode,
            headers: res.headers,
            data: body
          });
        }
      });
    });

    req.on('error', (err) => {
      reject(err);
    });

    if (data) {
      req.write(JSON.stringify(data));
    }
    req.end();
  });
}

// Test endpoints and their expected behavior
const ENDPOINTS_TO_TEST = [
  // Main signals endpoints
  { url: '/api/signals', method: 'GET', description: 'Get all signals', expectedStatus: 200 },
  { url: '/api/signals?timeframe=daily', method: 'GET', description: 'Get daily signals', expectedStatus: 200 },
  { url: '/api/signals?timeframe=weekly', method: 'GET', description: 'Get weekly signals', expectedStatus: 200 },
  { url: '/api/signals?timeframe=monthly', method: 'GET', description: 'Get monthly signals', expectedStatus: 200 },

  // Signal type endpoints
  { url: '/api/signals/buy', method: 'GET', description: 'Get buy signals', expectedStatus: 200 },
  { url: '/api/signals/sell', method: 'GET', description: 'Get sell signals', expectedStatus: 200 },
  { url: '/api/signals/technical', method: 'GET', description: 'Get technical signals', expectedStatus: 200 },
  { url: '/api/signals/momentum', method: 'GET', description: 'Get momentum signals', expectedStatus: 200 },
  { url: '/api/signals/trending', method: 'GET', description: 'Get trending signals', expectedStatus: 200 },

  // Symbol-specific endpoints
  { url: `/api/signals/${TEST_SYMBOL}`, method: 'GET', description: `Get signals for ${TEST_SYMBOL}`, expectedStatus: 200 },
  { url: `/api/signals/${TEST_SYMBOL}?timeframe=daily`, method: 'GET', description: `Get daily signals for ${TEST_SYMBOL}`, expectedStatus: 200 },

  // Performance endpoints
  { url: '/api/signals/performance', method: 'GET', description: 'Get overall performance', expectedStatus: 200 },
  { url: `/api/signals/performance/${TEST_SYMBOL}`, method: 'GET', description: `Get performance for ${TEST_SYMBOL}`, expectedStatus: 200 },
  { url: `/api/signals/performance/${TEST_SYMBOL}?timeframe=7d`, method: 'GET', description: `Get 7d performance for ${TEST_SYMBOL}`, expectedStatus: 200 },

  // Alert endpoints
  { url: '/api/signals/alerts', method: 'GET', description: 'Get signal alerts', expectedStatus: 200 },
  { url: '/api/signals/alerts', method: 'POST', description: 'Create signal alert', expectedStatus: 201,
    data: { symbol: 'AAPL', signal_type: 'BUY', min_strength: 0.8 } },

  // Other endpoints
  { url: '/api/signals/backtest?symbol=AAPL&start_date=2023-01-01', method: 'GET', description: 'Get backtest results', expectedStatus: 200 },
  { url: '/api/signals/options', method: 'GET', description: 'Get options signals', expectedStatus: 200 },
  { url: '/api/signals/sentiment', method: 'GET', description: 'Get sentiment signals', expectedStatus: 200 },
  { url: '/api/signals/earnings', method: 'GET', description: 'Get earnings signals', expectedStatus: 200 },
  { url: '/api/signals/crypto', method: 'GET', description: 'Get crypto signals', expectedStatus: 200 },
  { url: '/api/signals/history', method: 'GET', description: 'Get historical signals', expectedStatus: 200 },
  { url: '/api/signals/sector-rotation', method: 'GET', description: 'Get sector rotation signals', expectedStatus: 200 },
  { url: '/api/signals/list', method: 'GET', description: 'Get signals list', expectedStatus: 200 },

  // Custom endpoint
  { url: '/api/signals/custom', method: 'POST', description: 'Create custom signal', expectedStatus: 201,
    data: { name: 'Test Alert', criteria: { rsi: { min: 30, max: 70 } }, symbols: ['AAPL'] } },

  // Frontend expected endpoints (that might be missing)
  { url: '/api/trading/performance', method: 'GET', description: 'Trading performance (frontend expects this)', expectedStatus: [200, 404] },
];

async function testAllEndpoints() {
  console.log('🧪 Starting comprehensive Trading Signals API testing...\n');

  let passed = 0;
  let failed = 0;
  let errors = [];

  for (const endpoint of ENDPOINTS_TO_TEST) {
    try {
      const response = await makeRequest(BASE_URL + endpoint.url, endpoint.method, endpoint.data);
      const expectedStatuses = Array.isArray(endpoint.expectedStatus) ? endpoint.expectedStatus : [endpoint.expectedStatus];

      if (expectedStatuses.includes(response.status)) {
        console.log(`✅ ${endpoint.method} ${endpoint.url} - ${response.status} - ${endpoint.description}`);
        passed++;
      } else {
        console.log(`❌ ${endpoint.method} ${endpoint.url} - ${response.status} (expected ${endpoint.expectedStatus}) - ${endpoint.description}`);
        if (response.data && response.data.error) {
          console.log(`   Error: ${response.data.error}`);
        }
        failed++;
        errors.push({
          endpoint: endpoint.url,
          method: endpoint.method,
          expected: endpoint.expectedStatus,
          actual: response.status,
          error: response.data
        });
      }
    } catch (err) {
      console.log(`💥 ${endpoint.method} ${endpoint.url} - FAILED - ${endpoint.description}`);
      console.log(`   Error: ${err.message}`);
      failed++;
      errors.push({
        endpoint: endpoint.url,
        method: endpoint.method,
        expected: endpoint.expectedStatus,
        actual: 'ERROR',
        error: err.message
      });
    }
  }

  console.log(`\n📊 Test Results:`);
  console.log(`✅ Passed: ${passed}`);
  console.log(`❌ Failed: ${failed}`);
  console.log(`📈 Success Rate: ${((passed / (passed + failed)) * 100).toFixed(1)}%`);

  if (errors.length > 0) {
    console.log(`\n🚨 Issues Found:`);
    errors.forEach(error => {
      console.log(`- ${error.method} ${error.endpoint}: Expected ${error.expected}, got ${error.actual}`);
      if (error.error && typeof error.error === 'object' && error.error.error) {
        console.log(`  Error: ${error.error.error}`);
      } else if (typeof error.error === 'string') {
        console.log(`  Error: ${error.error}`);
      }
    });
  }

  return { passed, failed, errors };
}

// Run the tests
if (require.main === module) {
  testAllEndpoints()
    .then(results => {
      process.exit(results.failed > 0 ? 1 : 0);
    })
    .catch(err => {
      console.error('Test runner failed:', err);
      process.exit(1);
    });
}

module.exports = { testAllEndpoints, makeRequest };
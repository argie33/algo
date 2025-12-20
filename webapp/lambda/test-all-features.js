/**
 * COMPREHENSIVE FEATURE TEST SUITE
 * Tests all critical endpoints to ensure consolidation doesn't break anything
 * Run before and after any endpoint refactoring
 */

const http = require('http');

const API_BASE = 'http://localhost:3001';

// Test configuration
const tests = [
  // Dashboard
  {
    name: 'Dashboard - Market Overview',
    endpoint: '/api/market/overview',
    expectedFields: ['data'],
    checkData: (data) => data.data && data.data.sentiment_indicators && data.data.market_quality
  },

  // Stock Screener
  {
    name: 'Stock Screener - List Stocks',
    endpoint: '/api/stocks?limit=2',
    expectedFields: ['data'],
    checkData: (data) => data.data && data.data.stocks && data.data.stocks.length > 0
  },

  {
    name: 'Stock Screener - Filter by Sector',
    endpoint: '/api/stocks?sector=Healthcare&limit=2',
    expectedFields: ['data'],
    checkData: (data) => data.data && data.data.stocks && data.data.stocks.length > 0
  },

  // Economic Data
  {
    name: 'Economic Data - Leading Indicators',
    endpoint: '/api/economic/leading-indicators',
    expectedFields: ['data']
  },

  {
    name: 'Economic Data - Calendar',
    endpoint: '/api/economic/calendar',
    expectedFields: ['data']
  },

  // Sentiment
  {
    name: 'Sentiment - Main Endpoint',
    endpoint: '/api/sentiment',
    expectedFields: ['data']
  },

  {
    name: 'Market Sentiment (Alternative)',
    endpoint: '/api/market/sentiment',
    expectedFields: ['data'],
    checkData: (data) => data.data || (data.aaii && data.fear_greed && data.naaim)
  },

  // Earnings
  {
    name: 'Earnings - List',
    endpoint: '/api/earnings',
    checkData: (data) => data.success !== false || data.data
  },

  // Sectors
  {
    name: 'Sectors - Industries with History',
    endpoint: '/api/sectors/industries-with-history',
    checkData: (data) => data.success !== false || (data.data && Array.isArray(data.data))
  },

  {
    name: 'Sectors - Sectors with History',
    endpoint: '/api/sectors/sectors-with-history?limit=20',
    expectedFields: ['data']
  },

  // Scores
  {
    name: 'Scores - Top Stocks',
    endpoint: '/api/scores/top?limit=10',
    expectedFields: ['data']
  },

  {
    name: 'Scores - Stock Scores',
    endpoint: '/api/scores/stockscores?limit=10&offset=0',
    expectedFields: ['data']
  },

  // Signals
  {
    name: 'Signals - List',
    endpoint: '/api/signals',
    expectedFields: ['data']
  },

  // Financials
  {
    name: 'Financials - General',
    endpoint: '/api/financials',
    expectedFields: ['data']
  },

  // Price Data
  {
    name: 'Price - Latest for Symbol',
    endpoint: '/api/price/latest/AAPL',
    checkData: (data) => data.success || data.data
  },

  // Portfolio
  {
    name: 'Portfolio - Summary',
    endpoint: '/api/portfolio/summary',
    checkData: (data) => data.success !== false
  },

  // Risk
  {
    name: 'Risk - Root',
    endpoint: '/api/risk',
    checkData: (data) => data.success !== false
  },

  // Health
  {
    name: 'Health Check',
    endpoint: '/api/health',
    expectedFields: ['data'],
    checkData: (data) => data.data && data.data.status && data.data.healthy !== undefined
  },

  // Auth
  {
    name: 'Auth - Status',
    endpoint: '/api/auth/status',
    checkData: (data) => true // Just needs to not error
  },
];

// Run tests
async function runTests() {
  console.log('\n' + '='.repeat(80));
  console.log('COMPREHENSIVE FEATURE TEST SUITE');
  console.log('='.repeat(80) + '\n');

  let passed = 0;
  let failed = 0;
  const failures = [];

  for (const test of tests) {
    try {
      const result = await testEndpoint(test);

      if (result.success) {
        console.log(`✅ ${test.name}`);
        passed++;
      } else {
        console.log(`❌ ${test.name}`);
        console.log(`   Error: ${result.error}`);
        failed++;
        failures.push({ test: test.name, error: result.error });
      }
    } catch (err) {
      console.log(`❌ ${test.name}`);
      console.log(`   Exception: ${err.message}`);
      failed++;
      failures.push({ test: test.name, error: err.message });
    }
  }

  // Summary
  console.log('\n' + '='.repeat(80));
  console.log('TEST RESULTS');
  console.log('='.repeat(80));
  console.log(`\n✅ Passed: ${passed}`);
  console.log(`❌ Failed: ${failed}`);
  console.log(`📊 Total:  ${passed + failed}`);
  console.log(`📈 Success Rate: ${((passed / (passed + failed)) * 100).toFixed(1)}%\n`);

  if (failures.length > 0) {
    console.log('FAILURES:');
    failures.forEach(f => {
      console.log(`  • ${f.test}: ${f.error}`);
    });
    console.log();
  }

  process.exit(failed > 0 ? 1 : 0);
}

function testEndpoint(test) {
  return new Promise((resolve) => {
    const url = new URL(test.endpoint, API_BASE);

    http.get(url, (res) => {
      let data = '';

      res.on('data', chunk => data += chunk);

      res.on('end', () => {
        try {
          const parsed = JSON.parse(data);

          // Check status code
          if (res.statusCode >= 400) {
            return resolve({
              success: false,
              error: `HTTP ${res.statusCode}: ${parsed.error || 'Unknown error'}`
            });
          }

          // Check expected fields
          if (test.expectedFields) {
            for (const field of test.expectedFields) {
              if (!(field in parsed)) {
                return resolve({
                  success: false,
                  error: `Missing field: ${field}`
                });
              }
            }
          }

          // Custom validation
          if (test.checkData) {
            const isValid = test.checkData(parsed);
            if (!isValid) {
              return resolve({
                success: false,
                error: 'Custom validation failed'
              });
            }
          }

          resolve({ success: true });
        } catch (err) {
          resolve({
            success: false,
            error: `JSON Parse Error: ${err.message}`
          });
        }
      });
    }).on('error', (err) => {
      resolve({
        success: false,
        error: `Connection Error: ${err.message}`
      });
    });
  });
}

// Run tests
runTests();

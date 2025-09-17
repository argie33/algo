
/**
 * Test Trade History with Authentication
 * Tests the trade history endpoints with proper authentication and data structure
 */

const axios = require('axios');

const BASE_URL = 'http://localhost:3001';

async function testTradeHistoryWithAuth() {
  console.log('🧪 Testing Trade History with Authentication\n');

  const tests = [
    {
      name: 'Trade History - With Dev Token',
      method: 'GET',
      url: `${BASE_URL}/api/trades/history?page=1&limit=25`,
      headers: {
        'Authorization': 'Bearer dev-bypass-token',
        'Content-Type': 'application/json'
      },
      expectedStructure: {
        hasSuccess: true,
        hasData: true,
        dataHas: ['trades', 'pagination'],
        tradesIsArray: true,
        firstTradeHas: ['symbol', 'action', 'quantity', 'price', 'pnl', 'execution_time', 'status']
      }
    },
    {
      name: 'Trade History - Without Auth (Should Fail)',
      method: 'GET',
      url: `${BASE_URL}/api/trades/history?page=1&limit=25`,
      expectError: true,
      expectedStatus: 401
    },
    {
      name: 'Trade Analytics - With Dev Token',
      method: 'GET',
      url: `${BASE_URL}/api/trades/analytics/overview`,
      headers: {
        'Authorization': 'Bearer dev-bypass-token',
        'Content-Type': 'application/json'
      },
      expectedStructure: {
        hasSuccess: true,
        hasData: true
      }
    },
    {
      name: 'Trade Insights - With Dev Token',
      method: 'GET',
      url: `${BASE_URL}/api/trades/insights`,
      headers: {
        'Authorization': 'Bearer dev-bypass-token',
        'Content-Type': 'application/json'
      },
      expectedStructure: {
        hasSuccess: true
      }
    },
    {
      name: 'Trade Performance - With Dev Token',
      method: 'GET',
      url: `${BASE_URL}/api/trades/performance`,
      headers: {
        'Authorization': 'Bearer dev-bypass-token',
        'Content-Type': 'application/json'
      },
      expectedStructure: {
        hasSuccess: true
      }
    }
  ];

  let passed = 0;
  let total = tests.length;

  for (const test of tests) {
    try {
      console.log(`Testing: ${test.name}`);
      const start = Date.now();

      let response;
      try {
        response = await axios({
          method: test.method,
          url: test.url,
          headers: test.headers || {}
        });
      } catch (error) {
        if (test.expectError && error.response) {
          response = error.response;
        } else {
          throw error;
        }
      }

      const elapsed = Date.now() - start;

      let isValid = true;
      let issues = [];

      // Check expected error scenarios
      if (test.expectError) {
        if (response.status !== test.expectedStatus) {
          isValid = false;
          issues.push(`Expected status ${test.expectedStatus}, got ${response.status}`);
        } else {
          console.log(`   ✅ ${response.status} - ${elapsed}ms - Expected error response`);
          passed++;
          continue;
        }
      }

      // Check basic response structure
      if (!test.expectError && response.status !== 200) {
        isValid = false;
        issues.push(`Status ${response.status}`);
      }

      if (!test.expectError && !response.data.success) {
        isValid = false;
        issues.push('Missing success=true');
      }

      // Check expected structure
      if (test.expectedStructure && !test.expectError) {
        const data = response.data.data;
        const expected = test.expectedStructure;

        if (expected.hasData && !data) {
          isValid = false;
          issues.push('Missing data property');
        }

        if (expected.dataHas && data) {
          expected.dataHas.forEach(prop => {
            if (!(prop in data)) {
              isValid = false;
              issues.push(`Missing data.${prop}`);
            }
          });
        }

        if (expected.tradesIsArray && data && !Array.isArray(data.trades)) {
          isValid = false;
          issues.push('data.trades should be array');
        }

        if (expected.firstTradeHas && data && data.trades && data.trades.length > 0) {
          const firstTrade = data.trades[0];
          expected.firstTradeHas.forEach(prop => {
            if (!(prop in firstTrade)) {
              isValid = false;
              issues.push(`Missing trade.${prop}`);
            }
          });
        }
      }

      if (isValid) {
        let responseInfo = `${response.status} - ${elapsed}ms`;
        if (response.data.data?.trades?.length) {
          responseInfo += ` - ${response.data.data.trades.length} trades`;
        } else if (response.data.data && typeof response.data.data === 'object') {
          responseInfo += ` - Data object returned`;
        }
        console.log(`   ✅ ${responseInfo}`);
        passed++;
      } else {
        console.log(`   ❌ Failed - ${issues.join(', ')}`);
        console.log(`   🔍 Response: ${JSON.stringify(response.data).substring(0, 200)}...`);
      }
    } catch (error) {
      console.log(`   ❌ Error - ${error.message}`);
    }
    console.log('');
  }

  console.log(`📋 TRADE HISTORY AUTH TEST RESULTS:`);
  console.log(`✅ Passed: ${passed}/${total} (${Math.round(passed/total*100)}%)`);

  if (passed === total) {
    console.log(`🎉 ALL TRADE HISTORY ENDPOINTS WORKING WITH AUTH!`);
  } else {
    console.log(`⚠️  ${total - passed} endpoints have issues`);
  }

  return passed === total;
}

// Run the tests
testTradeHistoryWithAuth().then(success => {
  process.exit(success ? 0 : 1);
});
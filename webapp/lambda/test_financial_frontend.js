
/**
 * Test Financial Frontend Integration
 * Tests the specific endpoints that the frontend FinancialData page calls
 */

const axios = require('axios');

const BASE_URL = 'http://localhost:3001';

async function testFinancialFrontendEndpoints() {
  console.log('🧪 Testing Financial Frontend Integration\n');

  const tests = [
    {
      name: 'Balance Sheet (Frontend)',
      url: `${BASE_URL}/api/financials/AAPL/balance-sheet?period=annual`,
      expectedFields: ['totalAssets', 'currentAssets', 'date']
    },
    {
      name: 'Income Statement (Frontend)',
      url: `${BASE_URL}/api/financials/AAPL/income-statement?period=annual`,
      expectedFields: ['revenue', 'netIncome', 'date']
    },
    {
      name: 'Comprehensive Statements (Backend)',
      url: `${BASE_URL}/api/financials/AAPL/statements?period=annual`,
      expectedFields: ['statements', 'summary']
    }
  ];

  let passed = 0;
  let total = tests.length;

  for (const test of tests) {
    try {
      console.log(`Testing: ${test.name}`);
      const start = Date.now();
      const response = await axios.get(test.url);
      const elapsed = Date.now() - start;

      // Check response structure
      if (response.status === 200 && response.data.success) {
        const data = response.data.data;

        // Check for expected fields in first item
        const firstItem = Array.isArray(data) ? data[0] : data;
        const hasRequiredFields = test.expectedFields.every(field => {
          if (field === 'statements' || field === 'summary') {
            return firstItem && firstItem[field];
          }
          return firstItem && (firstItem[field] !== undefined);
        });

        if (hasRequiredFields) {
          // Check date format (should not be 1969 or a year integer)
          let dateValid = true;
          if (Array.isArray(data) && data.length > 0 && data[0].date) {
            const dateStr = data[0].date;
            const date = new Date(dateStr);
            const year = date.getFullYear();
            dateValid = year > 2000 && year < 2030; // Reasonable date range
          }

          if (dateValid) {
            console.log(`   ✅ ${response.status} - ${elapsed}ms - ${data.length || 1} records`);
            if (response.data.metadata?.dataSource) {
              console.log(`   📊 Data Source: ${response.data.metadata.dataSource}`);
            }
            passed++;
          } else {
            console.log(`   ❌ Invalid date format in response`);
            console.log(`   🔍 Sample date: ${data[0]?.date}`);
          }
        } else {
          console.log(`   ❌ Missing required fields: ${test.expectedFields.join(', ')}`);
          console.log(`   🔍 Available fields: ${Object.keys(firstItem || {}).join(', ')}`);
        }
      } else {
        console.log(`   ❌ ${response.status} - ${response.data.error || 'Unknown error'}`);
      }
    } catch (error) {
      console.log(`   ❌ Error - ${error.message}`);
    }
    console.log('');
  }

  console.log(`\n📋 FINANCIAL FRONTEND TEST RESULTS:`);
  console.log(`✅ Passed: ${passed}/${total} (${Math.round(passed/total*100)}%)`);

  if (passed === total) {
    console.log(`🎉 ALL FRONTEND FINANCIAL ENDPOINTS WORKING!`);
  } else {
    console.log(`⚠️  Some endpoints have issues`);
  }

  return passed === total;
}

// Run the tests
testFinancialFrontendEndpoints().then(success => {
  process.exit(success ? 0 : 1);
});
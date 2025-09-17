
/**
 * Test Financial Routes that Frontend Actually Uses
 * These are the working endpoints that the frontend FinancialData page calls
 */

const axios = require('axios');

const BASE_URL = 'http://localhost:3001';

async function testFrontendFinancialRoutes() {
  console.log('🧪 Testing Frontend Financial Routes\n');

  const tests = [
    {
      name: 'Balance Sheet (/api/financials/AAPL/balance-sheet)',
      url: `${BASE_URL}/api/financials/AAPL/balance-sheet?period=annual`,
      expectedStructure: {
        hasSuccess: true,
        hasData: true,
        dataIsArray: true,
        firstItemHas: ['symbol', 'date', 'totalAssets', 'currentAssets']
      }
    },
    {
      name: 'Income Statement (/api/financials/AAPL/income-statement)',
      url: `${BASE_URL}/api/financials/AAPL/income-statement?period=annual`,
      expectedStructure: {
        hasSuccess: true,
        hasData: true,
        dataIsArray: true,
        firstItemHas: ['symbol', 'date', 'revenue', 'netIncome']
      }
    },
    {
      name: 'Cash Flow (/api/financials/AAPL/cash-flow)',
      url: `${BASE_URL}/api/financials/AAPL/cash-flow?period=annual`,
      expectedStructure: {
        hasSuccess: true,
        hasData: true,
        dataIsArray: true,
        firstItemHas: ['symbol', 'date']
      }
    },
    {
      name: 'Comprehensive Statements (/api/financials/AAPL/statements)',
      url: `${BASE_URL}/api/financials/AAPL/statements?period=annual`,
      expectedStructure: {
        hasSuccess: true,
        hasData: true,
        dataHasStatements: true,
        statementsHas: ['balance_sheet', 'income_statement']
      }
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

      let isValid = true;
      let issues = [];

      // Check basic response structure
      if (response.status !== 200) {
        isValid = false;
        issues.push(`Status ${response.status}`);
      }

      if (!response.data.success) {
        isValid = false;
        issues.push('Missing success=true');
      }

      // Check expected structure
      const data = response.data.data;
      const expected = test.expectedStructure;

      if (expected.hasData && !data) {
        isValid = false;
        issues.push('Missing data property');
      }

      if (expected.dataIsArray && !Array.isArray(data)) {
        isValid = false;
        issues.push('Data should be array');
      }

      if (expected.firstItemHas && Array.isArray(data) && data.length > 0) {
        const firstItem = data[0];
        expected.firstItemHas.forEach(prop => {
          if (!(prop in firstItem)) {
            isValid = false;
            issues.push(`Missing property: ${prop}`);
          }
        });
      }

      if (expected.dataHasStatements && (!data.statements)) {
        isValid = false;
        issues.push('Missing statements property');
      }

      if (expected.statementsHas && data.statements) {
        expected.statementsHas.forEach(stmt => {
          if (!(stmt in data.statements)) {
            isValid = false;
            issues.push(`Missing statement: ${stmt}`);
          }
        });
      }

      if (isValid) {
        const recordCount = Array.isArray(data) ? data.length :
                           data.statements ? Object.values(data.statements).reduce((sum, arr) => sum + (Array.isArray(arr) ? arr.length : 0), 0) : 1;
        console.log(`   ✅ ${response.status} - ${elapsed}ms - ${recordCount} records`);
        if (response.data.metadata?.dataSource) {
          console.log(`   📊 Data Source: ${response.data.metadata.dataSource}`);
        }
        passed++;
      } else {
        console.log(`   ❌ Failed - ${issues.join(', ')}`);
        console.log(`   🔍 Response structure: ${JSON.stringify(Object.keys(response.data), null, 2)}`);
        if (Array.isArray(data) && data.length > 0) {
          console.log(`   🔍 First item keys: ${Object.keys(data[0]).join(', ')}`);
        }
      }
    } catch (error) {
      console.log(`   ❌ Error - ${error.message}`);
    }
    console.log('');
  }

  console.log(`📋 FRONTEND FINANCIAL ROUTES TEST RESULTS:`);
  console.log(`✅ Passed: ${passed}/${total} (${Math.round(passed/total*100)}%)`);

  if (passed === total) {
    console.log(`🎉 ALL FRONTEND FINANCIAL ROUTES WORKING!`);
  } else {
    console.log(`⚠️  ${total - passed} routes have issues`);
  }

  return passed === total;
}

// Run the tests
testFrontendFinancialRoutes().then(success => {
  process.exit(success ? 0 : 1);
});
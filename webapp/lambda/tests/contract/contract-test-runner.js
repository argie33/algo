const axios = require('axios');
const path = require('path');
const fs = require('fs');

// Contract test configuration
const CONFIG = {
  baseURL: process.env.API_BASE_URL || 'http://localhost:3001',
  timeout: 30000,
  environments: {
    test: 'http://localhost:3001',
    staging: process.env.STAGING_URL || 'https://staging.example.com',
    production: process.env.PRODUCTION_URL || 'https://api.example.com'
  }
};

// Test results tracking
let testResults = {
  total: 0,
  passed: 0,
  failed: 0,
  errors: [],
  contracts: {}
};

// API Contract Definitions
const API_CONTRACTS = {
  // Health and diagnostics
  'GET /api/health': {
    expectedStatus: 200,
    requiredFields: ['status', 'timestamp', 'uptime'],
    responseSchema: {
      status: 'string',
      timestamp: 'string',
      uptime: 'number'
    }
  },
  
  // Portfolio endpoints
  'GET /api/portfolio': {
    expectedStatus: 200,
    requiredFields: ['success', 'message', 'timestamp', 'endpoints'],
    responseSchema: {
      success: 'boolean',
      message: 'string',
      timestamp: 'string',
      endpoints: 'array'
    }
  },
  
  'GET /api/portfolio/positions': {
    expectedStatus: 200,
    requiredFields: ['success', 'data'],
    responseSchema: {
      success: 'boolean',
      data: 'object'
    }
  },
  
  'GET /api/portfolio/performance': {
    expectedStatus: 200,
    requiredFields: ['success', 'performance'],
    responseSchema: {
      success: 'boolean',
      performance: 'array'
    }
  },
  
  // Market data endpoints
  'GET /api/market/overview': {
    expectedStatus: 200,
    requiredFields: ['success', 'data', 'timestamp'],
    responseSchema: {
      success: 'boolean',
      data: 'object',
      timestamp: 'string'
    }
  },
  
  // Alert endpoints
  'GET /api/alerts/active': {
    expectedStatus: [200, 401], // May require auth
    conditionalFields: {
      200: ['success', 'data'],
      401: ['error']
    },
    responseSchema: {
      success: 'boolean',
      data: 'object'
    }
  },
  
  // Calendar endpoints
  'GET /api/calendar/earnings': {
    expectedStatus: 200,
    requiredFields: ['success', 'data'],
    responseSchema: {
      success: 'boolean',
      data: 'object'
    }
  },
  
  // Diagnostics endpoints
  'GET /api/diagnostics': {
    expectedStatus: [200, 401],
    conditionalFields: {
      200: ['message', 'timestamp', 'endpoints'],
      401: ['error']
    },
    responseSchema: {
      message: 'string',
      timestamp: 'string',
      endpoints: 'array'
    }
  },
  
  'GET /api/diagnostics/database-connectivity': {
    expectedStatus: [200, 401],
    conditionalFields: {
      200: ['success', 'results'],
      401: ['error']
    },
    responseSchema: {
      success: 'boolean',
      results: 'object'
    }
  },
  
  // Backtest endpoints
  'GET /api/backtest/strategies': {
    expectedStatus: 200,
    responseSchema: {
      strategies: 'array'
    }
  },

  // Additional comprehensive coverage endpoints
  'GET /api/portfolio/holdings': {
    expectedStatus: [200, 401],
    conditionalFields: {
      200: ['success', 'data'],
      401: ['error']
    }
  },

  'GET /api/portfolio/value': {
    expectedStatus: [200, 401],
    conditionalFields: {
      200: ['success', 'data'],
      401: ['error']
    }
  },

  'GET /api/portfolio/analytics': {
    expectedStatus: [200, 401],
    conditionalFields: {
      200: ['success', 'data'],
      401: ['error']
    },
    responseSchema: {
      success: 'boolean',
      data: 'object'
    }
  },

  // Additional key endpoints for comprehensive coverage
  
  // Portfolio additional endpoints  
  'GET /api/portfolio/transactions': {
    expectedStatus: [200, 401],
    conditionalFields: {
      200: ['success', 'data'],
      401: ['error']
    },
    responseSchema: {
      success: 'boolean',
      data: 'object'
    }
  },

  'GET /api/portfolio/summary': {
    expectedStatus: [200, 401],
    conditionalFields: {
      200: ['success', 'data'],
      401: ['error']
    }
  },

  'GET /api/portfolio/metrics': {
    expectedStatus: [200, 401],
    conditionalFields: {
      200: ['success', 'data'],
      401: ['error']
    }
  },

  // Market data endpoints
  'GET /api/market': {
    expectedStatus: 200,
    requiredFields: ['success', 'data'],
    responseSchema: {
      success: 'boolean',
      data: 'object'
    }
  },

  // Stock endpoints
  'GET /api/stocks': {
    expectedStatus: 200,
    requiredFields: ['success', 'data'],
    responseSchema: {
      success: 'boolean',
      data: 'array'
    }
  },

  // Technical analysis endpoints
  'GET /api/technical': {
    expectedStatus: 200,
    requiredFields: ['success', 'data'],
    responseSchema: {
      success: 'boolean',
      data: 'object'
    }
  },

  // Live data endpoints
  'GET /api/live-data': {
    expectedStatus: 200,
    requiredFields: ['success', 'data'],
    responseSchema: {
      success: 'boolean',
      data: 'object'
    }
  },

  'GET /api/live-data/status': {
    expectedStatus: 200,
    requiredFields: ['success', 'status'],
    responseSchema: {
      success: 'boolean',
      status: 'object'
    }
  },

  // Analytics endpoints
  'GET /api/analytics': {
    expectedStatus: [200, 401],
    conditionalFields: {
      200: ['success', 'data'],
      401: ['error']
    }
  },

  // Performance endpoints
  'GET /api/performance': {
    expectedStatus: [200, 401],
    conditionalFields: {
      200: ['success', 'data'],
      401: ['error']
    }
  },

  // Risk management endpoints
  'GET /api/risk': {
    expectedStatus: [200, 401],
    conditionalFields: {
      200: ['success', 'data'],
      401: ['error']
    }
  },

  // News endpoints
  'GET /api/news': {
    expectedStatus: 200,
    requiredFields: ['success', 'data'],
    responseSchema: {
      success: 'boolean',
      data: 'array'
    }
  },

  // Signals endpoints
  'GET /api/signals': {
    expectedStatus: 200,
    requiredFields: ['success', 'signals'],
    responseSchema: {
      success: 'boolean',
      signals: 'array'
    }
  },

  // Trading endpoints
  'GET /api/trading': {
    expectedStatus: [200, 401],
    conditionalFields: {
      200: ['success', 'data'],
      401: ['error']
    }
  },

  // Orders endpoints
  'GET /api/orders': {
    expectedStatus: [200, 401],
    conditionalFields: {
      200: ['success', 'orders'],
      401: ['error']
    }
  },

  // Watchlist endpoints
  'GET /api/watchlist': {
    expectedStatus: [200, 401],
    conditionalFields: {
      200: ['success', 'data'],
      401: ['error']
    }
  },

  // Screener endpoints
  'GET /api/screener': {
    expectedStatus: 200,
    requiredFields: ['success', 'data'],
    responseSchema: {
      success: 'boolean',
      data: 'object'
    }
  },

  // Scores endpoints
  'GET /api/scores': {
    expectedStatus: 200,
    requiredFields: ['success', 'data'],
    responseSchema: {
      success: 'boolean',
      data: 'object'
    }
  },

  // Metrics endpoints
  'GET /api/metrics': {
    expectedStatus: 200,
    requiredFields: ['success', 'metrics'],
    responseSchema: {
      success: 'boolean',
      metrics: 'object'
    }
  },

  // Sectors endpoints
  'GET /api/sectors': {
    expectedStatus: 200,
    requiredFields: ['success', 'data'],
    responseSchema: {
      success: 'boolean',
      data: 'array'
    }
  },

  // Sentiment analysis endpoints
  'GET /api/sentiment': {
    expectedStatus: 200,
    requiredFields: ['success', 'data'],
    responseSchema: {
      success: 'boolean',
      data: 'object'
    }
  },

  // ETF endpoints
  'GET /api/etf': {
    expectedStatus: 200,
    requiredFields: ['success', 'data'],
    responseSchema: {
      success: 'boolean',
      data: 'array'
    }
  }
};

// Contract validation functions
function validateResponseSchema(data, schema) {
  const errors = [];
  
  for (const [field, expectedType] of Object.entries(schema)) {
    if (!(field in data)) {
      errors.push(`Missing required field: ${field}`);
      continue;
    }
    
    const actualType = Array.isArray(data[field]) ? 'array' : typeof data[field];
    if (actualType !== expectedType) {
      errors.push(`Field '${field}' expected ${expectedType}, got ${actualType}`);
    }
  }
  
  return errors;
}

function validateContract(endpoint, response) {
  const contract = API_CONTRACTS[endpoint];
  if (!contract) {
    return [`No contract defined for endpoint: ${endpoint}`];
  }
  
  const errors = [];
  const { status, data } = response;
  
  // Validate status code
  const expectedStatuses = Array.isArray(contract.expectedStatus) 
    ? contract.expectedStatus 
    : [contract.expectedStatus];
    
  if (!expectedStatuses.includes(status)) {
    errors.push(`Expected status ${expectedStatuses.join(' or ')}, got ${status}`);
  }
  
  // Validate required fields based on status
  if (contract.conditionalFields && contract.conditionalFields[status]) {
    const requiredFields = contract.conditionalFields[status];
    for (const field of requiredFields) {
      if (!(field in data)) {
        errors.push(`Missing required field for status ${status}: ${field}`);
      }
    }
  } else if (contract.requiredFields && status === 200) {
    for (const field of contract.requiredFields) {
      if (!(field in data)) {
        errors.push(`Missing required field: ${field}`);
      }
    }
  }
  
  // Validate response schema
  if (contract.responseSchema && status === 200) {
    const schemaErrors = validateResponseSchema(data, contract.responseSchema);
    errors.push(...schemaErrors);
  }
  
  return errors;
}

// Test execution
async function runContractTest(endpoint, baseURL) {
  const [method, path] = endpoint.split(' ');
  const url = `${baseURL}${path}`;
  
  try {
    console.log(`🔍 Testing ${endpoint}...`);
    
    const response = await axios({
      method: method.toLowerCase(),
      url,
      timeout: CONFIG.timeout,
      validateStatus: () => true // Don't throw on non-2xx status codes
    });
    
    const contractErrors = validateContract(endpoint, response);
    
    if (contractErrors.length === 0) {
      console.log(`✅ ${endpoint} - Contract valid`);
      testResults.passed++;
      testResults.contracts[endpoint] = { status: 'PASS', response: response.status };
      return true;
    } else {
      console.log(`❌ ${endpoint} - Contract violations:`);
      contractErrors.forEach(error => console.log(`   • ${error}`));
      testResults.failed++;
      testResults.contracts[endpoint] = { 
        status: 'FAIL', 
        response: response.status,
        errors: contractErrors 
      };
      testResults.errors.push({
        endpoint,
        errors: contractErrors,
        actualResponse: {
          status: response.status,
          data: response.data
        }
      });
      return false;
    }
    
  } catch (error) {
    console.log(`❌ ${endpoint} - Request failed: ${error.message}`);
    testResults.failed++;
    testResults.contracts[endpoint] = { 
      status: 'ERROR', 
      error: error.message 
    };
    testResults.errors.push({
      endpoint,
      error: error.message
    });
    return false;
  }
}

// Site functionality tests
async function runSiteFunctionalityTests(baseURL) {
  console.log('\n🌐 Running site functionality tests...\n');
  
  // Test critical user workflows
  const workflows = [
    {
      name: 'Portfolio Dashboard Load',
      tests: [
        'GET /api/health',
        'GET /api/portfolio',
        'GET /api/portfolio/positions'
      ]
    },
    {
      name: 'Market Data Access',
      tests: [
        'GET /api/market/overview',
        'GET /api/calendar/earnings'
      ]
    },
    {
      name: 'System Diagnostics',
      tests: [
        'GET /api/diagnostics/database-connectivity',
        'GET /api/diagnostics'
      ]
    }
  ];
  
  for (const workflow of workflows) {
    console.log(`\n📋 Testing workflow: ${workflow.name}`);
    let workflowPassed = true;
    
    for (const test of workflow.tests) {
      const result = await runContractTest(test, baseURL);
      if (!result) {
        workflowPassed = false;
      }
      testResults.total++;
    }
    
    if (workflowPassed) {
      console.log(`✅ Workflow '${workflow.name}' completed successfully`);
    } else {
      console.log(`❌ Workflow '${workflow.name}' has failures`);
    }
  }
}

// Small batch tests for verification
async function runSmallBatchTests(baseURL) {
  console.log('\n🔬 Running small batch verification tests...\n');
  
  const criticalEndpoints = [
    'GET /api/health',
    'GET /api/portfolio',
    'GET /api/market/overview',
    'GET /api/diagnostics/database-connectivity'
  ];
  
  console.log('Testing critical endpoints for quick verification:');
  
  for (const endpoint of criticalEndpoints) {
    await runContractTest(endpoint, baseURL);
    testResults.total++;
  }
}

// Full contract test suite
async function runFullContractTests(baseURL) {
  console.log('\n📝 Running full API contract tests...\n');
  
  for (const endpoint of Object.keys(API_CONTRACTS)) {
    await runContractTest(endpoint, baseURL);
    testResults.total++;
  }
}

// Report generation
function generateReport() {
  const report = {
    summary: {
      total: testResults.total,
      passed: testResults.passed,
      failed: testResults.failed,
      successRate: testResults.total > 0 ? ((testResults.passed / testResults.total) * 100).toFixed(2) + '%' : '0%'
    },
    contracts: testResults.contracts,
    errors: testResults.errors,
    timestamp: new Date().toISOString()
  };
  
  console.log('\n📊 CONTRACT TEST REPORT');
  console.log('=' .repeat(50));
  console.log(`Total Tests: ${report.summary.total}`);
  console.log(`Passed: ${report.summary.passed}`);
  console.log(`Failed: ${report.summary.failed}`);
  console.log(`Success Rate: ${report.summary.successRate}`);
  
  if (testResults.errors.length > 0) {
    console.log('\n❌ FAILURES:');
    testResults.errors.forEach((error, index) => {
      console.log(`${index + 1}. ${error.endpoint}`);
      if (error.errors) {
        error.errors.forEach(err => console.log(`   • ${err}`));
      } else if (error.error) {
        console.log(`   • ${error.error}`);
      }
    });
  }
  
  // Save report to file
  const reportPath = path.join(__dirname, 'contract-test-report.json');
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));
  console.log(`\n📄 Detailed report saved to: ${reportPath}`);
  
  return report;
}

// Main execution
async function main() {
  console.log('🚀 Starting Contract Test Runner');
  console.log('=' .repeat(50));
  
  const args = process.argv.slice(2);
  const envFlag = args.find(arg => arg.startsWith('--env'));
  const noReportFlag = args.includes('--no-report');
  const batchFlag = args.includes('--batch');
  
  let environments = ['test'];
  if (envFlag) {
    const envValues = envFlag.split('=')[1];
    environments = envValues ? envValues.split(',') : ['test'];
  }
  
  for (const env of environments) {
    const baseURL = CONFIG.environments[env] || CONFIG.baseURL;
    console.log(`\n🌍 Testing environment: ${env} (${baseURL})`);
    
    // Reset results for each environment
    testResults = {
      total: 0,
      passed: 0,
      failed: 0,
      errors: [],
      contracts: {}
    };
    
    try {
      if (batchFlag) {
        await runSmallBatchTests(baseURL);
      } else {
        // Run site functionality tests (full workflow validation)
        await runSiteFunctionalityTests(baseURL);
        
        // Run remaining contract tests
        const testedEndpoints = new Set();
        // Add tested endpoints from functionality tests to avoid duplicates
        Object.keys(testResults.contracts).forEach(ep => testedEndpoints.add(ep));
        
        console.log('\n📋 Running remaining contract tests...\n');
        for (const endpoint of Object.keys(API_CONTRACTS)) {
          if (!testedEndpoints.has(endpoint)) {
            await runContractTest(endpoint, baseURL);
            testResults.total++;
          }
        }
      }
      
      if (!noReportFlag) {
        const report = generateReport();
        
        // Exit with error code if tests failed
        if (testResults.failed > 0) {
          process.exit(1);
        }
      }
      
    } catch (error) {
      console.error(`❌ Fatal error testing ${env}:`, error.message);
      process.exit(1);
    }
  }
  
  console.log('\n✅ Contract testing completed');
}

// Handle unhandled rejections
process.on('unhandledRejection', (reason, promise) => {
  console.error('Unhandled Rejection at:', promise, 'reason:', reason);
  process.exit(1);
});

// Run if called directly
if (require.main === module) {
  main().catch(error => {
    console.error('Contract test runner failed:', error);
    process.exit(1);
  });
}

module.exports = {
  runContractTest,
  runSiteFunctionalityTests,
  runSmallBatchTests,
  validateContract,
  API_CONTRACTS
};
/**
 * Integration test for stocks endpoints - testing real API calls
 * Purpose: Discover real application issues like null pointer exceptions
 */

const http = require('http');

// Test configuration
const BASE_URL = 'http://localhost:3001';
const TIMEOUT = 10000; // 10 seconds

// Test endpoints to check
const STOCKS_ENDPOINTS = [
  '/api/stocks/ping',
  '/api/stocks/sectors',
  '/api/stocks/public/sample',
  '/api/stocks?limit=10',
  '/api/stocks/AAPL',
  '/api/stocks/MSFT/prices?limit=10',
  '/api/stocks/screen?sector=Technology&limit=5',
  '/api/stocks/filters/sectors',
  '/api/stocks/screen/stats',
];

// JWT token for authenticated endpoints
const TEST_JWT_TOKEN = 'Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0ZXN0LXVzZXItMTIzIiwiZW1haWwiOiJ0ZXN0QGV4YW1wbGUuY29tIiwidXNlcm5hbWUiOiJ0ZXN0LXVzZXIiLCJyb2xlIjoidXNlciIsInNlc3Npb25JZCI6InRlc3Qtc2Vzc2lvbiIsImV4cCI6OTk5OTk5OTk5OSwiaWF0IjoxNjM5NzUyMDAwfQ.test-signature';

// Make HTTP request
function makeRequest(endpoint, requiresAuth = false) {
  return new Promise((resolve, reject) => {
    const url = new URL(BASE_URL + endpoint);
    
    const options = {
      hostname: url.hostname,
      port: url.port || 3001,
      path: url.pathname + url.search,
      method: 'GET',
      timeout: TIMEOUT,
      headers: {
        'Content-Type': 'application/json',
      }
    };

    if (requiresAuth) {
      options.headers['Authorization'] = TEST_JWT_TOKEN;
    }

    const req = http.request(options, (res) => {
      let data = '';
      
      res.on('data', (chunk) => {
        data += chunk;
      });

      res.on('end', () => {
        try {
          const parsed = JSON.parse(data);
          resolve({
            status: res.statusCode,
            headers: res.headers,
            data: parsed,
            raw: data.substring(0, 1000) // First 1000 chars for debugging
          });
        } catch (parseError) {
          resolve({
            status: res.statusCode,
            headers: res.headers,
            data: null,
            raw: data.substring(0, 1000),
            parseError: parseError.message
          });
        }
      });
    });

    req.on('error', (error) => {
      reject({
        endpoint,
        error: error.message,
        code: error.code
      });
    });

    req.on('timeout', () => {
      req.destroy();
      reject({
        endpoint,
        error: 'Request timeout',
        timeout: TIMEOUT
      });
    });

    req.end();
  });
}

// Run integration tests
async function runStocksIntegrationTests() {
  console.log('🧪 Starting Stocks Integration Tests');
  console.log('=====================================');

  const results = {
    passed: 0,
    failed: 0,
    errors: [],
    responses: []
  };

  for (const endpoint of STOCKS_ENDPOINTS) {
    const requiresAuth = endpoint.includes('/screen') || endpoint.includes('?') || endpoint.includes('/AAPL') || endpoint.includes('/MSFT');
    
    try {
      console.log(`\n🔍 Testing: ${endpoint}`);
      
      const response = await makeRequest(endpoint, requiresAuth);
      
      // Analyze response
      if (response.status === 200) {
        console.log(`✅ SUCCESS: ${endpoint} (${response.status})`);
        results.passed++;
        
        // Check for potential issues
        if (response.data && response.data.data && Array.isArray(response.data.data) && response.data.data.length === 0) {
          console.log(`⚠️  WARNING: Empty data array returned`);
        }
        
        if (response.data && response.data.message && response.data.message.includes('unavailable')) {
          console.log(`⚠️  WARNING: Service unavailable message detected`);
        }
        
      } else if (response.status === 500) {
        console.log(`❌ CRITICAL ERROR: ${endpoint} (${response.status})`);
        console.log(`Error details:`, response.data?.error || 'Unknown error');
        results.failed++;
        results.errors.push({
          endpoint,
          status: response.status,
          error: response.data?.error || 'Unknown 500 error',
          details: response.data?.details || response.raw?.substring(0, 200)
        });
        
      } else if (response.status === 404) {
        console.log(`⚠️  NOT FOUND: ${endpoint} (${response.status})`);
        // 404 might be expected for some endpoints
        results.passed++;
        
      } else {
        console.log(`⚠️  UNEXPECTED: ${endpoint} (${response.status})`);
        console.log(`Response:`, response.data?.message || response.raw?.substring(0, 100));
        results.failed++;
      }
      
      results.responses.push({
        endpoint,
        status: response.status,
        success: response.status === 200 || response.status === 404,
        dataAvailable: !!(response.data?.data && response.data.data.length > 0),
        hasErrors: !!(response.data?.error)
      });
      
    } catch (error) {
      console.log(`💥 CONNECTION ERROR: ${endpoint}`);
      console.log(`Error: ${error.error} (${error.code || 'UNKNOWN'})`);
      results.failed++;
      results.errors.push({
        endpoint,
        error: error.error,
        code: error.code,
        type: 'connection_error'
      });
    }
  }

  // Summary
  console.log('\n📊 STOCKS INTEGRATION TEST RESULTS');
  console.log('===================================');
  console.log(`✅ Passed: ${results.passed}`);
  console.log(`❌ Failed: ${results.failed}`);
  console.log(`📈 Success Rate: ${((results.passed / (results.passed + results.failed)) * 100).toFixed(1)}%`);

  if (results.errors.length > 0) {
    console.log('\n🚨 CRITICAL ERRORS FOUND:');
    results.errors.forEach((error, idx) => {
      console.log(`\n${idx + 1}. ${error.endpoint}`);
      console.log(`   Error: ${error.error}`);
      if (error.details) {
        console.log(`   Details: ${error.details}`);
      }
    });
  }

  // Response analysis
  console.log('\n📋 RESPONSE ANALYSIS:');
  results.responses.forEach(resp => {
    const status = resp.success ? '✅' : '❌';
    const data = resp.dataAvailable ? '📊' : '📭';
    console.log(`${status} ${data} ${resp.endpoint} (${resp.status})`);
  });

  return results;
}

// Run tests if called directly
if (require.main === module) {
  runStocksIntegrationTests()
    .then(results => {
      if (results.failed > 0) {
        throw new Error(`Integration tests failed: ${results.failed} failures`);
      }
    })
    .catch(error => {
      console.error('💥 Test runner failed:', error);
      throw error;
    });
}

module.exports = { runStocksIntegrationTests };
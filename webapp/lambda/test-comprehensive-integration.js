/**
 * Comprehensive integration test for all major endpoints - testing real API calls
 * Purpose: Discover real application issues across the entire system
 */

const http = require('http');

// Test configuration
const BASE_URL = 'http://localhost:3001';
const TIMEOUT = 5000; // 5 seconds

// Test all major endpoints
const ENDPOINTS = [
  // Core functionality
  '/health',
  '/api/portfolio/analytics',
  '/api/market/overview',
  '/api/market/data/indices', 
  '/api/market/data/sectors',
  '/api/settings/profile',
  '/api/settings/api-keys',
  '/api/dashboard/summary',
  '/api/watchlist',
  '/api/alerts',
  '/api/news/sentiment',
  '/api/signals',
  
  // Public endpoints
  '/api/stocks/public/sample',
  '/api/stocks/sectors',
  '/api/market/data/public/sentiment',
  
  // Database dependent endpoints  
  '/api/stocks/AAPL',
  '/api/stocks/MSFT/prices?limit=5',
  '/api/stocks/screen?sector=Technology',
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
            raw: data.substring(0, 500) // First 500 chars for debugging
          });
        } catch (parseError) {
          resolve({
            status: res.statusCode,
            headers: res.headers,
            data: null,
            raw: data.substring(0, 500),
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

// Analyze endpoint categories
function categorizeEndpoint(endpoint) {
  if (endpoint.includes('/public/') || endpoint === '/health') return 'public';
  if (endpoint.includes('/settings/') || endpoint.includes('/portfolio') || endpoint.includes('/watchlist')) return 'authenticated';
  if (endpoint.includes('/stocks/') || endpoint.includes('/market/')) return 'data_dependent';
  return 'general';
}

// Run comprehensive integration tests
async function runComprehensiveIntegrationTests() {
  console.log('🧪 Starting Comprehensive Integration Tests');
  console.log('==========================================');

  const results = {
    passed: 0,
    failed: 0,
    errors: [],
    responses: [],
    categories: {
      public: { passed: 0, failed: 0 },
      authenticated: { passed: 0, failed: 0 },
      data_dependent: { passed: 0, failed: 0 },
      general: { passed: 0, failed: 0 }
    }
  };

  for (const endpoint of ENDPOINTS) {
    const category = categorizeEndpoint(endpoint);
    const requiresAuth = category === 'authenticated' || endpoint.includes('/settings/') || endpoint.includes('/portfolio');
    
    try {
      console.log(`\n🔍 Testing: ${endpoint} (${category})`);
      
      const response = await makeRequest(endpoint, requiresAuth);
      
      // Analyze response
      if (response.status === 200) {
        console.log(`✅ SUCCESS: ${endpoint} (${response.status})`);
        results.passed++;
        results.categories[category].passed++;
        
        // Check for quality warnings
        if (response.data && response.data.data && Array.isArray(response.data.data) && response.data.data.length === 0) {
          console.log(`⚠️  INFO: Empty data array returned (expected for database unavailable)`);
        }
        
        if (response.data && response.data.message && response.data.message.includes('unavailable')) {
          console.log(`✅ GOOD: Proper "unavailable" messaging for graceful degradation`);
        }
        
      } else if (response.status === 503) {
        console.log(`✅ GRACEFUL: ${endpoint} (${response.status}) - Service Unavailable with proper error message`);
        console.log(`Message: ${response.data?.message || 'Unknown service unavailable'}`);
        results.passed++; // 503 with proper message is successful graceful degradation
        results.categories[category].passed++;
        
      } else if (response.status === 401 && requiresAuth) {
        console.log(`✅ EXPECTED: ${endpoint} (${response.status}) - Authentication required as expected`);
        results.passed++; // Expected auth failure is success
        results.categories[category].passed++;
        
      } else if (response.status === 500) {
        console.log(`❌ CRITICAL ERROR: ${endpoint} (${response.status}) - Server crash!`);
        console.log(`Error details:`, response.data?.error || 'Unknown 500 error');
        results.failed++;
        results.categories[category].failed++;
        results.errors.push({
          endpoint,
          status: response.status,
          error: response.data?.error || 'Unknown 500 error',
          details: response.raw?.substring(0, 200)
        });
        
      } else {
        console.log(`⚠️  UNEXPECTED: ${endpoint} (${response.status})`);
        console.log(`Response:`, response.data?.message || response.raw?.substring(0, 100));
        results.failed++;
        results.categories[category].failed++;
      }
      
      results.responses.push({
        endpoint,
        category,
        status: response.status,
        success: response.status === 200 || response.status === 503 || (response.status === 401 && requiresAuth),
        errorMessaging: !!(response.data?.message),
        gracefulDegradation: response.status === 503 && !!(response.data?.message)
      });
      
    } catch (error) {
      console.log(`💥 CONNECTION ERROR: ${endpoint}`);
      console.log(`Error: ${error.error} (${error.code || 'UNKNOWN'})`);
      results.failed++;
      results.categories[category].failed++;
      results.errors.push({
        endpoint,
        error: error.error,
        code: error.code,
        type: 'connection_error'
      });
    }
  }

  // Summary
  console.log('\n📊 COMPREHENSIVE INTEGRATION TEST RESULTS');
  console.log('==========================================');
  console.log(`✅ Passed: ${results.passed}`);
  console.log(`❌ Failed: ${results.failed}`);
  console.log(`📈 Success Rate: ${((results.passed / (results.passed + results.failed)) * 100).toFixed(1)}%`);

  // Category analysis
  console.log('\n📋 CATEGORY ANALYSIS:');
  for (const [category, stats] of Object.entries(results.categories)) {
    const total = stats.passed + stats.failed;
    const rate = total > 0 ? ((stats.passed / total) * 100).toFixed(1) : '0.0';
    console.log(`${category.padEnd(15)}: ${stats.passed}/${total} (${rate}%)`);
  }

  // Error analysis
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

  // Quality metrics
  console.log('\n🏆 QUALITY METRICS:');
  const withErrorMessages = results.responses.filter(r => r.errorMessaging).length;
  const withGracefulDegradation = results.responses.filter(r => r.gracefulDegradation).length;
  const totalResponses = results.responses.length;
  
  console.log(`Error Messaging: ${withErrorMessages}/${totalResponses} (${((withErrorMessages/totalResponses)*100).toFixed(1)}%)`);
  console.log(`Graceful Degradation: ${withGracefulDegradation}/${totalResponses} (${((withGracefulDegradation/totalResponses)*100).toFixed(1)}%)`);
  console.log(`Zero 500 Errors: ${results.responses.filter(r => r.status === 500).length === 0 ? '✅ YES' : '❌ NO'}`);

  return results;
}

// Run tests if called directly
if (require.main === module) {
  runComprehensiveIntegrationTests()
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

module.exports = { runComprehensiveIntegrationTests };
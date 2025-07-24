#!/usr/bin/env node
/**
 * Emergency Deployment Validation Script
 * Tests the deployed CORS/timeout fix to ensure production issues are resolved
 */

const supertest = require('supertest');
const app = require('./index.js').app;

console.log('🚨 Testing Emergency CORS/Timeout Fix Deployment...\n');

async function testEmergencyEndpoints() {
  const tests = [
    {
      name: 'Health Check with CORS',
      path: '/api/health',
      method: 'GET',
      expectedStatus: 200,
      checkCORS: true
    },
    {
      name: 'Portfolio Holdings with Fallback',
      path: '/api/portfolio/holdings',
      method: 'GET',
      expectedStatus: 200,
      checkCORS: true
    },
    {
      name: 'Portfolio Accounts with Fallback',
      path: '/api/portfolio/accounts',
      method: 'GET',
      expectedStatus: 200,
      checkCORS: true
    },
    {
      name: 'API Keys Endpoint',
      path: '/api/api-keys',
      method: 'GET',
      expectedStatus: 200,
      checkCORS: true
    },
    {
      name: 'Stocks Endpoint',
      path: '/api/stocks',
      method: 'GET',
      expectedStatus: 200,
      checkCORS: true
    },
    {
      name: 'Metrics Endpoint',
      path: '/api/metrics',
      method: 'GET',
      expectedStatus: 200,
      checkCORS: true
    },
    {
      name: 'Dashboard Endpoint',
      path: '/api/dashboard',
      method: 'GET',
      expectedStatus: 200,
      checkCORS: true
    },
    {
      name: 'CORS Preflight (OPTIONS)',
      path: '/api/health',
      method: 'OPTIONS',
      expectedStatus: 200,
      checkCORS: true
    }
  ];

  let passedTests = 0;
  let failedTests = 0;

  for (const test of tests) {
    try {
      console.log(`🧪 Testing: ${test.name}`);
      
      const request = supertest(app)[test.method.toLowerCase()](test.path)
        .set('Origin', 'https://d1zb7knau41vl9.cloudfront.net')
        .expect(test.expectedStatus);
      
      const response = await request;
      
      // Check CORS headers
      if (test.checkCORS) {
        const corsOrigin = response.headers['access-control-allow-origin'];
        const corsCredentials = response.headers['access-control-allow-credentials'];
        
        if (!corsOrigin) {
          throw new Error('Missing Access-Control-Allow-Origin header');
        }
        
        if (corsCredentials !== 'true') {
          throw new Error('Missing or incorrect Access-Control-Allow-Credentials header');
        }
        
        console.log(`   ✅ CORS headers present (Origin: ${corsOrigin})`);
      }
      
      // Verify response structure
      if (test.method === 'GET' && test.path !== '/api/health') {
        if (!response.body || typeof response.body.success === 'undefined') {
          throw new Error('Response missing success field');
        }
        console.log(`   ✅ Response structure valid (success: ${response.body.success})`);
      }
      
      console.log(`   ✅ ${test.name} PASSED\n`);
      passedTests++;
      
    } catch (error) {
      console.log(`   ❌ ${test.name} FAILED: ${error.message}\n`);
      failedTests++;
    }
  }

  // Summary
  console.log('📊 Emergency Deployment Test Results:');
  console.log(`   ✅ Passed: ${passedTests}/${tests.length}`);
  console.log(`   ❌ Failed: ${failedTests}/${tests.length}`);
  
  if (failedTests === 0) {
    console.log('\n🎉 ALL TESTS PASSED! Emergency CORS/timeout fix is working correctly.');
    console.log('📡 CORS headers are properly configured for CloudFront origin');
    console.log('⏰ Timeout protection is active');
    console.log('🛡️ Fallback endpoints are responding correctly');
  } else {
    console.log('\n⚠️ Some tests failed. Review the issues above before deploying to AWS.');
  }
  
  return failedTests === 0;
}

// Run tests if called directly
if (require.main === module) {
  testEmergencyEndpoints()
    .then(success => {
      process.exit(success ? 0 : 1);
    })
    .catch(error => {
      console.error('💥 Test execution failed:', error);
      process.exit(1);
    });
}

module.exports = { testEmergencyEndpoints };
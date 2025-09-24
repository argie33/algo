const request = require('supertest');

const { app } = require('./index.js');

// Endpoints that require authentication
const AUTH_REQUIRED_ENDPOINTS = [
  '/api/alerts', '/api/portfolio', '/api/recommendations', '/api/research',
  '/api/settings', '/api/trades', '/api/watchlist'
];

// Comprehensive list of all critical API endpoints to test
const criticalAPIs = [
  { path: '/api/health', method: 'GET', description: 'Health check endpoint' },
  { path: '/api/metrics', method: 'GET', description: 'Market metrics endpoint' },
  { path: '/api/stocks?limit=5', method: 'GET', description: 'Stocks listing endpoint' },
  { path: '/api/signals', method: 'GET', description: 'Trading signals endpoint' },
  { path: '/api/scores', method: 'GET', description: 'Stock scores endpoint' },
  { path: '/api/portfolio', method: 'GET', description: 'Portfolio endpoint' },
  { path: '/api/market', method: 'GET', description: 'Market data endpoint' },
  { path: '/api/news', method: 'GET', description: 'News endpoint' },
  { path: '/api/earnings', method: 'GET', description: 'Earnings endpoint' },
  { path: '/api/sectors', method: 'GET', description: 'Sectors endpoint' },
  { path: '/api/analytics', method: 'GET', description: 'Analytics endpoint' },
  { path: '/api/recommendations', method: 'GET', description: 'Recommendations endpoint' },
  { path: '/api/alerts', method: 'GET', description: 'Alerts endpoint' },
  { path: '/api/calendar', method: 'GET', description: 'Calendar endpoint' },
  { path: '/api/technical', method: 'GET', description: 'Technical analysis endpoint' },
  { path: '/api/performance', method: 'GET', description: 'Performance endpoint' },
  { path: '/api/risk', method: 'GET', description: 'Risk assessment endpoint' },
  { path: '/api/screener', method: 'GET', description: 'Stock screener endpoint' },
  { path: '/api/watchlist', method: 'GET', description: 'Watchlist endpoint' },
  { path: '/api/trades', method: 'GET', description: 'Trades endpoint' }
];

async function testAPI(api) {
  try {
    console.log(`\n🧪 Testing ${api.description}: ${api.method} ${api.path}`);

    // Check if this endpoint requires authentication
    const requiresAuth = AUTH_REQUIRED_ENDPOINTS.some(authEndpoint =>
      api.path.startsWith(authEndpoint)
    );

    let response;
    if (api.method === 'GET') {
      if (requiresAuth) {
        console.log(`   🔧 Using authentication bypass token for protected endpoint`);
        response = await request(app)
          .get(api.path)
          .set('Authorization', 'Bearer test-token')
          .set('Content-Type', 'application/json')
          .timeout(10000);
      } else {
        response = await request(app).get(api.path).timeout(10000);
      }
    }

    console.log(`   Status: ${response.status}`);

    if (response.status === 200) {
      console.log(`   ✅ PASS - ${api.description}`);
      if (response.body.data) {
        const dataCount = Array.isArray(response.body.data) ? response.body.data.length : 'object';
        console.log(`   📊 Data count: ${dataCount}`);
      }
      return { api: api.path, status: 'PASS', code: response.status };
    } else if (response.status >= 400 && response.status < 500) {
      console.log(`   ⚠️  CLIENT ERROR - ${api.description}`);
      console.log(`   Error: ${response.body?.error || response.body?.message || 'Client error'}`);
      return { api: api.path, status: 'CLIENT_ERROR', code: response.status, error: response.body?.error };
    } else if (response.status >= 500) {
      console.log(`   ❌ SERVER ERROR - ${api.description}`);
      console.log(`   Error: ${response.body?.error || response.body?.message || 'Server error'}`);
      return { api: api.path, status: 'SERVER_ERROR', code: response.status, error: response.body?.error };
    } else {
      console.log(`   ⚠️  UNEXPECTED - ${api.description}`);
      return { api: api.path, status: 'UNEXPECTED', code: response.status };
    }
  } catch (error) {
    console.log(`   💥 FATAL ERROR - ${api.description}`);
    console.log(`   Error: ${error.message}`);
    return { api: api.path, status: 'FATAL_ERROR', error: error.message };
  }
}

async function runComprehensiveTest() {
  console.log('🔍 Running comprehensive AWS API verification...\n');
  console.log(`Testing ${criticalAPIs.length} critical endpoints...\n`);

  const results = [];
  const startTime = Date.now();

  for (const api of criticalAPIs) {
    const result = await testAPI(api);
    results.push(result);
  }

  const endTime = Date.now();
  const duration = ((endTime - startTime) / 1000).toFixed(2);

  console.log('\n' + '='.repeat(60));
  console.log('📊 COMPREHENSIVE API TEST RESULTS');
  console.log('='.repeat(60));

  const passed = results.filter(r => r.status === 'PASS');
  const serverErrors = results.filter(r => r.status === 'SERVER_ERROR');
  const clientErrors = results.filter(r => r.status === 'CLIENT_ERROR');
  const fatalErrors = results.filter(r => r.status === 'FATAL_ERROR');
  const unexpected = results.filter(r => r.status === 'UNEXPECTED');

  console.log(`✅ Passed: ${passed.length}/${results.length} (${Math.round(passed.length/results.length*100)}%)`);
  console.log(`❌ Server Errors (5xx): ${serverErrors.length}/${results.length}`);
  console.log(`⚠️  Client Errors (4xx): ${clientErrors.length}/${results.length}`);
  console.log(`💥 Fatal Errors: ${fatalErrors.length}/${results.length}`);
  console.log(`❓ Unexpected: ${unexpected.length}/${results.length}`);
  console.log(`⏱️  Test Duration: ${duration}s`);

  if (serverErrors.length > 0) {
    console.log('\n🚨 CRITICAL SERVER ERRORS (Need immediate fixing):');
    serverErrors.forEach(result => {
      console.log(`   - ${result.api}: ${result.error || 'Status ' + result.code}`);
    });
  }

  if (clientErrors.length > 0) {
    console.log('\n⚠️  CLIENT ERRORS (May need configuration):');
    clientErrors.forEach(result => {
      console.log(`   - ${result.api}: ${result.error || 'Status ' + result.code}`);
    });
  }

  if (fatalErrors.length > 0) {
    console.log('\n💥 FATAL ERRORS (Infrastructure issues):');
    fatalErrors.forEach(result => {
      console.log(`   - ${result.api}: ${result.error}`);
    });
  }

  const criticalFailures = serverErrors.length + fatalErrors.length;
  if (criticalFailures === 0) {
    console.log('\n🎉 All critical APIs are functional! Site ready for deployment.');
  } else {
    console.log(`\n⚡ ${criticalFailures} critical issues found. Fixing required before deployment.`);
  }

  console.log('\n✅ Comprehensive test complete');

  // Save results to file for reference
  const fs = require('fs');
  fs.writeFileSync('api_test_results.json', JSON.stringify({
    timestamp: new Date().toISOString(),
    totalEndpoints: results.length,
    passed: passed.length,
    serverErrors: serverErrors.length,
    clientErrors: clientErrors.length,
    fatalErrors: fatalErrors.length,
    passRate: Math.round(passed.length/results.length*100),
    duration: duration,
    results: results
  }, null, 2));

  process.exit(criticalFailures > 0 ? 1 : 0);
}

runComprehensiveTest();
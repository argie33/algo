const request = require('supertest');
const { app } = require('./index.js');

const criticalAPIs = [
  { path: '/api/metrics', method: 'GET', description: 'Market metrics endpoint' },
  { path: '/api/stocks?limit=5', method: 'GET', description: 'Stocks listing endpoint' },
  { path: '/api/signals', method: 'GET', description: 'Trading signals endpoint' },
  { path: '/api/scores', method: 'GET', description: 'Stock scores endpoint' }
];

async function testAPI(api) {
  try {
    console.log(`\n🧪 Testing ${api.description}: ${api.method} ${api.path}`);

    let response;
    if (api.method === 'GET') {
      response = await request(app).get(api.path);
    }

    console.log(`   Status: ${response.status}`);

    if (response.status === 200) {
      console.log(`   ✅ PASS - ${api.description}`);
      if (response.body.data) {
        console.log(`   📊 Data count: ${Array.isArray(response.body.data) ? response.body.data.length : 'object'}`);
      }
      return { api: api.path, status: 'PASS', code: response.status };
    } else {
      console.log(`   ❌ FAIL - ${api.description}`);
      console.log(`   Error: ${response.body?.error || response.body?.message || 'Unknown error'}`);
      return { api: api.path, status: 'FAIL', code: response.status, error: response.body?.error };
    }
  } catch (error) {
    console.log(`   💥 ERROR - ${api.description}`);
    console.log(`   Error: ${error.message}`);
    return { api: api.path, status: 'ERROR', error: error.message };
  }
}

async function runComprehensiveTest() {
  console.log('🔍 Running comprehensive API verification...\n');

  const results = [];

  for (const api of criticalAPIs) {
    const result = await testAPI(api);
    results.push(result);
  }

  console.log('\n📊 FINAL RESULTS:');
  console.log('==================');

  const passed = results.filter(r => r.status === 'PASS');
  const failed = results.filter(r => r.status === 'FAIL' || r.status === 'ERROR');

  console.log(`✅ Passed: ${passed.length}/${results.length} (${Math.round(passed.length/results.length*100)}%)`);
  console.log(`❌ Failed: ${failed.length}/${results.length}`);

  if (failed.length > 0) {
    console.log('\n🚨 Failed APIs:');
    failed.forEach(result => {
      console.log(`   - ${result.api}: ${result.error || 'Status ' + result.code}`);
    });
  } else {
    console.log('\n🎉 All critical APIs are working correctly!');
  }

  console.log('\n✅ Verification complete');
  process.exit(failed.length > 0 ? 1 : 0);
}

runComprehensiveTest();
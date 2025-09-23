
const axios = require('axios');

const BASE_URL = 'https://qda42av7je.execute-api.us-east-1.amazonaws.com/dev';

async function testEndpoint(endpoint, name) {
  try {
    console.log(`\n🧪 Testing ${name}...`);

    const response = await axios.get(`${BASE_URL}${endpoint}`, {
      timeout: 8000,
      validateStatus: () => true
    });

    const statusIcon = response.status === 200 ? '✅' :
                      response.status >= 500 ? '❌' : '⚠️';

    console.log(`${statusIcon} ${name}: ${response.status}`);

    if (response.data) {
      console.log(`   Success: ${response.data.success || 'N/A'}`);
      if (response.data.data) {
        const dataLength = Array.isArray(response.data.data) ?
          response.data.data.length : 'object';
        console.log(`   Data: ${dataLength} items`);
      }
      if (response.data.message) {
        console.log(`   Message: ${response.data.message.substring(0, 60)}...`);
      }
    }

    return {
      endpoint,
      name,
      status: response.status,
      success: response.data?.success,
      hasData: !!response.data?.data
    };

  } catch (error) {
    console.log(`❌ ${name}: ERROR - ${error.message}`);
    return {
      endpoint,
      name,
      status: 'ERROR',
      success: false,
      hasData: false,
      error: error.message
    };
  }
}

async function runQuickTests() {
  console.log('🚀 Quick AWS API Tests for Fixed Endpoints');
  console.log('==========================================');

  const endpoints = [
    ['/api/signals', 'Trading Signals'],
    ['/api/watchlist', 'Watchlist'],
    ['/api/scores', 'Stock Scores'],
    ['/api/orders', 'Orders'],
    ['/api/health', 'Health Check']
  ];

  const results = [];

  for (const [endpoint, name] of endpoints) {
    const result = await testEndpoint(endpoint, name);
    results.push(result);
  }

  console.log('\n📊 Test Summary:');
  console.log('================');

  let passed = 0;
  results.forEach(result => {
    const status = result.success ? '✅ PASS' : '❌ FAIL';
    console.log(`${status} ${result.name} (${result.status})`);
    if (result.success) passed++;
  });

  console.log(`\n🎯 Results: ${passed}/${results.length} endpoints passing`);

  if (passed === results.length) {
    console.log('🎉 ALL TESTS PASSED! 500 errors have been resolved!');
  } else {
    console.log(`⏳ ${results.length - passed} endpoints still need AWS deployment refresh`);
  }

  return passed === results.length;
}

if (require.main === module) {
  runQuickTests().catch(console.error);
}

module.exports = { runQuickTests };
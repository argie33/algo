// Direct API endpoint testing with real database
process.env.NODE_ENV = 'test';
const axios = require('axios').default;

const API_BASE = 'http://localhost:3001';
const timeout = 5000;

async function testEndpoint(name, endpoint, expectedStatus = 200) {
  try {
    const response = await axios.get(`${API_BASE}${endpoint}`, { timeout });
    const success = response.status === expectedStatus;
    
    console.log(`${success ? '✅' : '❌'} ${name}: ${response.status} (${response.statusText})`);
    if (response.data && response.data.error) {
      console.log(`   Error: ${response.data.error}`);
    }
    return success;
  } catch (error) {
    console.log(`❌ ${name}: ${error.message}`);
    return false;
  }
}

async function runApiTests() {
  console.log('🧪 Running API Endpoint Tests with Real Database\n');
  
  const tests = [
    ['Health Check', '/health'],
    ['API Info', '/api'],
    ['Stocks List', '/api/stocks?page=1&limit=5'],
    ['Portfolio Health', '/api/portfolio/health'],
    ['Market Status', '/api/market/status'],
    ['Analytics Info', '/api/analytics'],
    ['Dashboard Summary', '/api/dashboard/summary'],
    ['Settings Health', '/api/settings/health'],
  ];
  
  let passed = 0;
  let total = tests.length;
  
  for (const [name, endpoint] of tests) {
    if (await testEndpoint(name, endpoint)) {
      passed++;
    }
    // Small delay between tests
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  
  console.log(`\n📊 Results: ${passed}/${total} tests passed (${Math.round(passed/total*100)}%)`);
  return passed === total;
}

// Error handling tests with bad data
async function testErrorHandling() {
  console.log('\n🔥 Testing Error Handling\n');
  
  const errorTests = [
    ['Invalid Symbol', '/api/stocks/INVALID@SYMBOL', 400],
    ['Non-existent Route', '/api/nonexistent', 404],
    ['Bad Portfolio ID', '/api/portfolio/invalid-id', 400],
  ];
  
  let passed = 0;
  for (const [name, endpoint, expectedStatus] of errorTests) {
    if (await testEndpoint(name, endpoint, expectedStatus)) {
      passed++;
    }
  }
  
  console.log(`\n🔥 Error Handling: ${passed}/${errorTests.length} tests passed`);
  return passed === errorTests.length;
}

async function main() {
  try {
    console.log('⏰ Waiting for server to be ready...');
    await new Promise(resolve => setTimeout(resolve, 2000));
    
    const apiSuccess = await runApiTests();
    const errorSuccess = await testErrorHandling();
    
    const overallSuccess = apiSuccess && errorSuccess;
    console.log(`\n${overallSuccess ? '🎉' : '💥'} Overall Result: ${overallSuccess ? 'SUCCESS' : 'FAILED'}`);
    
    process.exit(overallSuccess ? 0 : 1);
  } catch (error) {
    console.error('💥 Test suite failed:', error.message);
    process.exit(1);
  }
}

main();
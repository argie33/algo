// Direct API testing using curl (no extra dependencies needed)
const { exec } = require('child_process');
const util = require('util');
const execAsync = util.promisify(exec);

const API_BASE = 'http://localhost:3001';

async function testEndpoint(name, endpoint, expectedStatus = 200) {
  try {
    const { stdout, stderr } = await execAsync(
      `curl -s -w "%{http_code}" "${API_BASE}${endpoint}"`
    );
    
    // Extract HTTP status code from end of response
    const statusCode = parseInt(stdout.slice(-3));
    const responseBody = stdout.slice(0, -3);
    
    const success = statusCode === expectedStatus;
    console.log(`${success ? '✅' : '❌'} ${name}: ${statusCode}`);
    
    if (!success || statusCode >= 400) {
      try {
        const parsed = JSON.parse(responseBody);
        if (parsed.error) {
          console.log(`   Error: ${parsed.error}`);
        }
      } catch (e) {
        console.log(`   Response: ${responseBody.substring(0, 100)}...`);
      }
    }
    
    return success;
  } catch (error) {
    console.log(`❌ ${name}: ${error.message}`);
    return false;
  }
}

async function runApiTests() {
  console.log('🧪 Running API Tests with Real Database\n');
  
  const tests = [
    ['Health Check', '/health'],
    ['API Info', '/api'],
    ['Stocks Ping', '/api/stocks/ping'],
    ['Portfolio Health', '/api/portfolio/health'],
    ['Market Status', '/api/market/status'],
    ['Analytics Ping', '/api/analytics/ping'],
    ['Dashboard Health', '/api/dashboard/health'],
    ['Settings Health', '/api/settings/health'],
    ['Metrics Health', '/api/metrics/health'],
    ['Technical Ping', '/api/technical/ping'],
  ];
  
  let passed = 0;
  for (const [name, endpoint] of tests) {
    if (await testEndpoint(name, endpoint)) {
      passed++;
    }
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  
  console.log(`\n📊 Basic Tests: ${passed}/${tests.length} passed`);
  
  // Test some data endpoints with small limits
  const dataTests = [
    ['Technical Daily Data', '/api/technical/daily?page=1&limit=3'],
    ['Stocks List', '/api/stocks?page=1&limit=3'],
    ['Portfolio List', '/api/portfolio?page=1&limit=3'],
  ];
  
  let dataPassed = 0;
  console.log('\n📊 Data Endpoint Tests:\n');
  
  for (const [name, endpoint] of dataTests) {
    if (await testEndpoint(name, endpoint)) {
      dataPassed++;
    }
    await new Promise(resolve => setTimeout(resolve, 200));
  }
  
  console.log(`\n📊 Data Tests: ${dataPassed}/${dataTests.length} passed`);
  
  const totalPassed = passed + dataPassed;
  const totalTests = tests.length + dataTests.length;
  
  console.log(`\n🎯 Overall: ${totalPassed}/${totalTests} tests passed (${Math.round(totalPassed/totalTests*100)}%)`);
  return totalPassed >= Math.ceil(totalTests * 0.8); // 80% pass rate
}

runApiTests().then(success => {
  console.log(`\n${success ? '🎉 TESTS PASSED' : '💥 TESTS FAILED'}`);
  if (!success) throw new Error('Tests failed');
}).catch(error => {
  console.error('💥 Test runner failed:', error.message);
  throw error;
});
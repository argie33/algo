const http = require('http');

// Extended API test to check additional endpoints
const testEndpoints = [
  // Test specific symbol endpoints
  { path: '/api/signals/AAPL', method: 'GET', description: 'Signals for specific symbol' },
  { path: '/api/stocks/AAPL', method: 'GET', description: 'Stock details for AAPL' },
  { path: '/api/earnings/AAPL', method: 'GET', description: 'Earnings for AAPL' },

  // Test POST endpoints
  {
    path: '/api/signals/alerts',
    method: 'POST',
    data: JSON.stringify({ symbol: 'AAPL', signal_type: 'BUY' }),
    headers: { 'Content-Type': 'application/json' },
    description: 'Create signal alert'
  },

  // Test other endpoints that might fail
  { path: '/api/price/AAPL', method: 'GET', description: 'Price data for AAPL' },
  { path: '/api/technical/AAPL', method: 'GET', description: 'Technical data for AAPL' },
  { path: '/api/dividend/AAPL', method: 'GET', description: 'Dividend data for AAPL' },
  { path: '/api/market/status', method: 'GET', description: 'Market status' },
];

async function testAPI() {
  const results = [];
  console.log('🔍 Running extended API test...\n');

  // Start server on different port to avoid conflicts
  const server = require('./index.js');
  await new Promise(resolve => setTimeout(resolve, 2000)); // Wait for server to start

  for (const endpoint of testEndpoints) {
    try {
      const result = await makeRequest(endpoint);
      results.push(result);

      const status = result.success ? '✅ PASS' : '❌ FAIL';
      console.log(`${status} - ${endpoint.description}: ${endpoint.method} ${endpoint.path}`);
      if (!result.success) {
        console.log(`   Status: ${result.statusCode}, Error: ${result.error}`);
      }
    } catch (error) {
      results.push({
        success: false,
        statusCode: 'ERROR',
        error: error.message,
        endpoint: endpoint.path
      });
      console.log(`❌ ERROR - ${endpoint.description}: ${error.message}`);
    }
  }

  console.log('\n============================================');
  const passed = results.filter(r => r.success).length;
  const total = results.length;
  const serverErrors = results.filter(r => r.statusCode >= 500).length;

  console.log(`📊 EXTENDED TEST RESULTS`);
  console.log(`✅ Passed: ${passed}/${total} (${Math.round(passed/total*100)}%)`);
  console.log(`❌ Server Errors (5xx): ${serverErrors}/${total}`);
  console.log('============================================');

  process.exit(0);
}

function makeRequest(endpoint) {
  return new Promise((resolve) => {
    const options = {
      hostname: 'localhost',
      port: 3001,
      path: endpoint.path,
      method: endpoint.method,
      headers: endpoint.headers || {}
    };

    const req = http.request(options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        resolve({
          success: res.statusCode >= 200 && res.statusCode < 400,
          statusCode: res.statusCode,
          data: data.substring(0, 200),
          endpoint: endpoint.path
        });
      });
    });

    req.on('error', (error) => {
      resolve({
        success: false,
        statusCode: 'ERROR',
        error: error.message,
        endpoint: endpoint.path
      });
    });

    if (endpoint.data) {
      req.write(endpoint.data);
    }

    req.end();
  });
}

testAPI().catch(console.error);
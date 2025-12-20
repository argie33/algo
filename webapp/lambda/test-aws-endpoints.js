// Test AWS endpoints specifically
require('dotenv').config();

const https = require('https');

const AWS_BASE_URL = process.env.AWS_API_URL || 'https://algo-n2k5puvbra-uc.a.run.app';

console.log(`🔍 Testing AWS endpoints at: ${AWS_BASE_URL}`);

const testEndpoints = [
  '/api/health',
  '/api/metrics',
  '/api/stocks?limit=5',
  '/api/signals',
  '/api/scores',
  '/api/market',
  '/api/news',
  '/api/earnings',
  '/api/sectors',
  '/api/analytics',
  '/api/calendar',
  '/api/performance',
  '/api/risk',
  '/api/screener',
  '/api/watchlist',
  '/api/trades'
];

async function testAWSEndpoint(endpoint) {
  return new Promise((resolve) => {
    const url = new URL(endpoint, AWS_BASE_URL);

    const req = https.get(url, {
      timeout: 10000,
      headers: {
        'User-Agent': 'AWS-Test-Client'
      }
    }, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        resolve({
          endpoint,
          status: res.statusCode,
          success: res.statusCode >= 200 && res.statusCode < 300,
          error: res.statusCode >= 500 ? 'Server Error' : (res.statusCode >= 400 ? 'Client Error' : null),
          dataLength: data.length
        });
      });
    });

    req.on('timeout', () => {
      req.destroy();
      resolve({
        endpoint,
        status: 'TIMEOUT',
        success: false,
        error: 'Request timeout',
        dataLength: 0
      });
    });

    req.on('error', (err) => {
      resolve({
        endpoint,
        status: 'ERROR',
        success: false,
        error: err.message,
        dataLength: 0
      });
    });
  });
}

async function runAWSTests() {
  const results = [];

  console.log('\n🧪 Testing AWS endpoints...\n');

  for (const endpoint of testEndpoints) {
    process.stdout.write(`Testing ${endpoint}... `);
    const result = await testAWSEndpoint(endpoint);

    if (result.success) {
      console.log(`✅ ${result.status} (${result.dataLength} bytes)`);
    } else {
      console.log(`❌ ${result.status} - ${result.error}`);
    }

    results.push(result);
  }

  // Summary
  const passed = results.filter(r => r.success).length;
  const serverErrors = results.filter(r => typeof r.status === 'number' && r.status >= 500).length;
  const clientErrors = results.filter(r => typeof r.status === 'number' && r.status >= 400 && r.status < 500).length;
  const networkErrors = results.filter(r => typeof r.status === 'string').length;

  console.log('\n============================================================');
  console.log('📊 AWS API TEST RESULTS');
  console.log('============================================================');
  console.log(`✅ Passed: ${passed}/${testEndpoints.length} (${Math.round(passed/testEndpoints.length*100)}%)`);
  console.log(`❌ Server Errors (5xx): ${serverErrors}/${testEndpoints.length}`);
  console.log(`⚠️  Client Errors (4xx): ${clientErrors}/${testEndpoints.length}`);
  console.log(`🌐 Network Errors: ${networkErrors}/${testEndpoints.length}`);

  if (serverErrors > 0) {
    console.log('\n🚨 Server errors found:');
    results.filter(r => typeof r.status === 'number' && r.status >= 500).forEach(r => {
      console.log(`   - ${r.endpoint}: ${r.status} - ${r.error}`);
    });
  }

  if (networkErrors > 0) {
    console.log('\n🌐 Network errors found:');
    results.filter(r => typeof r.status === 'string').forEach(r => {
      console.log(`   - ${r.endpoint}: ${r.error}`);
    });
  }

  // Write results to file
  require('fs').writeFileSync('aws_test_results.json', JSON.stringify({
    timestamp: new Date().toISOString(),
    baseUrl: AWS_BASE_URL,
    totalEndpoints: testEndpoints.length,
    passed,
    serverErrors,
    clientErrors,
    networkErrors,
    passRate: Math.round(passed/testEndpoints.length*100),
    results
  }, null, 2));

  console.log('\n📄 Results saved to aws_test_results.json');

  return { passed, serverErrors, total: testEndpoints.length };
}

// Run tests
runAWSTests().then(({ passed, serverErrors, total }) => {
  if (serverErrors === 0 && passed >= total * 0.8) {
    console.log('\n🎉 AWS deployment looks healthy!');
    process.exit(0);
  } else {
    console.log('\n⚠️  AWS deployment has issues that need fixing');
    process.exit(1);
  }
}).catch(err => {
  console.error('❌ Test failed:', err);
  process.exit(1);
});
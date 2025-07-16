#!/usr/bin/env node

// Quick endpoint functionality test
const https = require('https');

const BASE_URL = 'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev';

const testEndpoints = [
  { path: '/api/health-full', method: 'GET', name: 'Health Check' },
  { path: '/api/data', method: 'GET', name: 'Data Overview' },
  { path: '/api/market', method: 'GET', name: 'Market Overview' },
  { path: '/api/stocks/screen', method: 'GET', name: 'Stock Screening' },
  { path: '/api/metrics/ping', method: 'GET', name: 'Metrics Ping' },
];

async function testEndpoint(endpoint) {
  return new Promise((resolve) => {
    const options = {
      hostname: 'jh28jhdp01.execute-api.us-east-1.amazonaws.com',
      port: 443,
      path: `/dev${endpoint.path}`,
      method: endpoint.method,
      headers: {
        'Content-Type': 'application/json',
        'User-Agent': 'Lambda-Test/1.0'
      }
    };

    const req = https.request(options, (res) => {
      let data = '';
      res.on('data', (chunk) => data += chunk);
      res.on('end', () => {
        resolve({
          endpoint: endpoint.name,
          status: res.statusCode,
          success: res.statusCode < 400,
          responseSize: data.length,
          hasData: data.length > 0
        });
      });
    });

    req.on('error', (error) => {
      resolve({
        endpoint: endpoint.name,
        status: 'ERROR',
        success: false,
        error: error.message
      });
    });

    req.setTimeout(10000, () => {
      req.destroy();
      resolve({
        endpoint: endpoint.name,
        status: 'TIMEOUT',
        success: false,
        error: 'Request timeout'
      });
    });

    req.end();
  });
}

async function runTests() {
  console.log('🚀 Testing AWS Lambda endpoints...\n');
  
  const results = [];
  
  for (const endpoint of testEndpoints) {
    console.log(`Testing ${endpoint.name}...`);
    const result = await testEndpoint(endpoint);
    results.push(result);
    
    if (result.success) {
      console.log(`✅ ${endpoint.name}: ${result.status} (${result.responseSize} bytes)`);
    } else {
      console.log(`❌ ${endpoint.name}: ${result.status} - ${result.error || 'Failed'}`);
    }
  }
  
  console.log('\n📊 Test Summary:');
  console.log(`✅ Passed: ${results.filter(r => r.success).length}`);
  console.log(`❌ Failed: ${results.filter(r => !r.success).length}`);
  console.log(`📊 Total: ${results.length}`);
  
  return results;
}

if (require.main === module) {
  runTests().then(results => {
    process.exit(results.every(r => r.success) ? 0 : 1);
  });
}

module.exports = { runTests, testEndpoint };
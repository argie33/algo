const https = require('https');

const API_BASE = 'https://qda42av7je.execute-api.us-east-1.amazonaws.com/dev';

async function testEndpoint(path) {
  const start = Date.now();
  return new Promise((resolve) => {
    const url = `${API_BASE}${path}`;
    https.get(url, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        const duration = Date.now() - start;
        try {
          const parsed = JSON.parse(data);
          resolve({ status: res.statusCode, data: parsed, duration, path });
        } catch {
          resolve({ status: res.statusCode, data: data, duration, path });
        }
      });
    }).on('error', (err) => {
      const duration = Date.now() - start;
      resolve({ status: 0, error: err.message, duration, path });
    });
  });
}

async function main() {
  console.log('🔍 Testing concurrent requests individually:');
  
  const endpoints = [
    '/health',
    '/api/market/overview',
    '/api/sectors/sectors-with-history',
    '/api/technical'
  ];
  
  // Test individually first
  console.log('\n📝 Individual Tests:');
  for (const endpoint of endpoints) {
    const result = await testEndpoint(endpoint);
    console.log(`\n${endpoint}:`);
    console.log(`  Status: ${result.status}`);
    console.log(`  Duration: ${result.duration}ms`);
    if (result.status !== 200) {
      console.log(`  Error: ${result.error || result.data?.error || 'Unknown error'}`);
    } else {
      console.log(`  ✅ SUCCESS`);
    }
  }
  
  // Test concurrently
  console.log('\n📝 Concurrent Test:');
  const start = Date.now();
  const promises = endpoints.map(endpoint => testEndpoint(endpoint));
  const results = await Promise.all(promises);
  const totalDuration = Date.now() - start;
  
  console.log(`\nConcurrent execution time: ${totalDuration}ms`);
  results.forEach(result => {
    console.log(`${result.path}: ${result.status === 200 ? '✅' : '❌'} (${result.duration}ms)`);
    if (result.status !== 200) {
      console.log(`  Error: ${result.error || result.data?.error || 'Unknown'}`);
    }
  });
}

main().catch(console.error);
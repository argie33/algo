#!/usr/bin/env node

const http = require('http');

async function testEndpoint(path) {
  return new Promise((resolve, reject) => {
    const options = {
      hostname: 'localhost',
      port: 3001,
      path: path,
      method: 'GET',
      timeout: 5000
    };

    const req = http.request(options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          resolve({
            status: res.statusCode,
            data: JSON.parse(data)
          });
        } catch (e) {
          resolve({
            status: res.statusCode,
            data: data.substring(0, 200)
          });
        }
      });
    });

    req.on('error', reject);
    req.on('timeout', () => {
      req.destroy();
      reject(new Error('Timeout'));
    });

    req.end();
  });
}

async function test() {
  console.log('\n🧪 TESTING BOTH SIGNAL ENDPOINTS\n');

  try {
    console.log('📊 Testing /api/signals/stocks...');
    const stocksResult = await testEndpoint('/api/signals/stocks?timeframe=daily&limit=5');
    console.log(`Status: ${stocksResult.status}`);
    if (stocksResult.status === 200) {
      const items = stocksResult.data.items || [];
      const pagination = stocksResult.data.pagination || {};
      console.log(`✅ Got ${items.length} items, total: ${pagination.total}`);
      if (items.length > 0) {
        console.log(`   First item:`, Object.keys(items[0]).join(', '));
      }
    } else {
      console.log(`❌ Error:`, stocksResult.data);
    }

    console.log('\n📊 Testing /api/signals/etf...');
    const etfResult = await testEndpoint('/api/signals/etf?timeframe=daily&limit=5');
    console.log(`Status: ${etfResult.status}`);
    if (etfResult.status === 200) {
      const items = etfResult.data.items || [];
      const pagination = etfResult.data.pagination || {};
      console.log(`✅ Got ${items.length} items, total: ${pagination.total}`);
      if (items.length > 0) {
        console.log(`   First item:`, Object.keys(items[0]).join(', '));
      }
    } else {
      console.log(`❌ Error:`, etfResult.data);
    }

  } catch (err) {
    console.error('❌ Error:', err.message);
  }

  process.exit(0);
}

// Start server and test
const { spawn } = require('child_process');
const server = spawn('node', ['webapp/lambda/index.js'], {
  stdio: 'pipe',
  detached: true
});

setTimeout(() => {
  test().then(() => {
    try { process.kill(-server.pid); } catch(e) {}
    process.exit(0);
  });
}, 2000);

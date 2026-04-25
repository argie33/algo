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
  console.log('\n🧪 TESTING ALL TIMEFRAMES\n');

  const timeframes = ['daily', 'weekly', 'monthly'];

  try {
    for (const tf of timeframes) {
      console.log(`📊 Testing /api/signals/stocks?timeframe=${tf}...`);
      const result = await testEndpoint(`/api/signals/stocks?timeframe=${tf}&limit=5`);
      console.log(`   Status: ${result.status}`);
      if (result.status === 200) {
        const items = result.data.items || [];
        const pagination = result.data.pagination || {};
        console.log(`   ✅ Got ${items.length} items, total: ${pagination.total}`);
        if (items.length > 0) {
          console.log(`   Fields: ${Object.keys(items[0]).join(', ')}`);
        }
      } else {
        console.log(`   ❌ Error:`, result.data?.error || result.data);
      }
      console.log('');
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

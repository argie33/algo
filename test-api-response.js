#!/usr/bin/env node

const http = require('http');

async function testAPI() {
  console.log('\n🔍 TESTING LIVE API RESPONSE\n');

  return new Promise((resolve) => {
    const options = {
      hostname: 'localhost',
      port: 3001,
      path: '/api/signals/stocks?timeframe=daily&limit=10',
      method: 'GET',
      timeout: 5000
    };

    const req = http.request(options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          const json = JSON.parse(data);

          console.log('✅ STATUS:', res.statusCode);
          console.log('\n📦 RESPONSE STRUCTURE:');
          console.log('  success:', json.success);
          console.log('  items count:', json.items ? json.items.length : 'NO ITEMS');
          console.log('  pagination.total:', json.pagination?.total);
          console.log('  pagination.page:', json.pagination?.page);
          console.log('  pagination.limit:', json.pagination?.limit);

          if (json.items && json.items.length > 0) {
            console.log('\n✅ FIRST SIGNAL:');
            const item = json.items[0];
            console.log(`  id: ${item.id}`);
            console.log(`  symbol: ${item.symbol}`);
            console.log(`  signal: ${item.signal}`);
            console.log(`  date: ${item.date}`);
            console.log(`  strength: ${item.strength}`);
            console.log(`  open: ${item.open}`);
            console.log(`  Fields:`, Object.keys(item).length);
          } else {
            console.log('\n❌ NO ITEMS IN RESPONSE!');
            console.log('Full response:', JSON.stringify(json, null, 2).substring(0, 500));
          }

        } catch (e) {
          console.log('❌ PARSE ERROR:', e.message);
          console.log('Raw:', data.substring(0, 200));
        }
        resolve();
      });
    });

    req.on('error', (err) => {
      console.error('❌ REQUEST ERROR:', err.message);
      resolve();
    });

    req.end();
  });
}

// Start server and test
const { spawn } = require('child_process');
const server = spawn('node', ['webapp/lambda/index.js'], {
  stdio: 'pipe',
  detached: true
});

setTimeout(async () => {
  await testAPI();
  try { process.kill(-server.pid); } catch(e) {}
  process.exit(0);
}, 2000);

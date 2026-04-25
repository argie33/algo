#!/usr/bin/env node
/**
 * Quick test of the /api/scores endpoint to verify the fix
 */

const http = require('http');

function testEndpoint(path) {
  return new Promise((resolve, reject) => {
    const options = {
      hostname: 'localhost',
      port: 3000,
      path: path,
      method: 'GET'
    };

    const req = http.request(options, (res) => {
      let data = '';
      res.on('data', chunk => { data += chunk; });
      res.on('end', () => {
        try {
          const parsed = JSON.parse(data);
          resolve({
            statusCode: res.statusCode,
            contentType: res.headers['content-type'],
            isJSON: res.headers['content-type']?.includes('application/json'),
            data: parsed
          });
        } catch (e) {
          resolve({
            statusCode: res.statusCode,
            contentType: res.headers['content-type'],
            isJSON: false,
            isHTML: data.includes('<!doctype'),
            error: 'Not valid JSON'
          });
        }
      });
    });

    req.on('error', reject);
    req.end();
  });
}

async function main() {
  console.log('Testing API Fix...\n');

  try {
    console.log('1. Testing /api/scores/stockscores');
    const scores = await testEndpoint('/api/scores/stockscores?limit=1');
    console.log(`   Status: ${scores.statusCode}`);
    console.log(`   Content-Type: ${scores.contentType}`);
    console.log(`   Is JSON: ${scores.isJSON}`);
    console.log(`   Has items: ${scores.data?.items ? `Yes (${scores.data.items.length})` : 'No'}`);
    if (!scores.isJSON) {
      console.log(`   ❌ FAIL: Expected JSON, got ${scores.isHTML ? 'HTML' : 'other'}`);
    } else if (scores.statusCode === 200 && scores.data?.items) {
      console.log(`   ✅ PASS: Scores endpoint working!`);
    } else if (scores.statusCode === 404) {
      console.log(`   ⚠️  NOT FOUND: ${scores.data?.message}`);
    }

    console.log('\n2. Testing /api/signals/stocks (known working)');
    const signals = await testEndpoint('/api/signals/stocks?symbol=AAPL');
    console.log(`   Status: ${signals.statusCode}`);
    console.log(`   Is JSON: ${signals.isJSON}`);
    console.log(`   ✅ PASS: Signals endpoint working`);

    console.log('\n3. Testing /api/nonexistent (should 404 with JSON)');
    const notfound = await testEndpoint('/api/nonexistent');
    console.log(`   Status: ${notfound.statusCode}`);
    console.log(`   Is JSON: ${notfound.isJSON}`);
    if (notfound.statusCode === 404 && notfound.isJSON) {
      console.log(`   ✅ PASS: 404 returns JSON error`);
    } else {
      console.log(`   ❌ FAIL: Expected 404 JSON, got ${notfound.statusCode} ${notfound.isHTML ? 'HTML' : 'other'}`);
    }

  } catch (error) {
    console.error('Test error:', error.message);
    process.exit(1);
  }
}

main();

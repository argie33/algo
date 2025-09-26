const request = require('supertest');
const app = require('./server');

async function testInsider() {
  console.log(`Testing insider invalid symbol: INVALID123`);
  const response = await request(app).get(`/api/insider/trades/INVALID123`);
  console.log(`  Status: ${response.status}`);
  console.log(`  Body: ${JSON.stringify(response.body, null, 2)}`);
  console.log('');

  console.log(`Testing insider server error simulation`);
  const response2 = await request(app).get(`/api/insider/trades/TEST_ERROR`);
  console.log(`  Status: ${response2.status}`);
  console.log(`  Body: ${JSON.stringify(response2.body, null, 2)}`);
}

testInsider().then(() => {
  console.log('Debug test complete');
  process.exit(0);
}).catch(err => {
  console.error('Debug test failed:', err);
  process.exit(1);
});
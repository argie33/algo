const request = require('supertest');
const app = require('./server');

async function testSQLInjection() {
  const maliciousSeries = "GDP'; DROP TABLE economic_data; --";
  console.log(`Testing SQL injection: ${maliciousSeries}`);
  const response = await request(app).get(`/api/economic?series=${encodeURIComponent(maliciousSeries)}`);
  console.log(`  Status: ${response.status}`);
  console.log(`  Body: ${JSON.stringify(response.body).slice(0, 300)}...`);
  console.log('');
}

testSQLInjection().then(() => {
  console.log('Debug test complete');
  process.exit(0);
}).catch(err => {
  console.error('Debug test failed:', err);
  process.exit(1);
});
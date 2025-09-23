const request = require('supertest');

const { app } = require('./index.js');

async function testStocksAPI() {
  try {
    console.log('Testing /api/stocks endpoint...');

    const response = await request(app)
      .get('/api/stocks?limit=5')
      .expect('Content-Type', /json/);

    console.log('Status:', response.status);
    console.log('Response:', JSON.stringify(response.body, null, 2));

    if (response.status === 200) {
      console.log('✅ /api/stocks working correctly');
    } else {
      console.log('❌ /api/stocks failed with status:', response.status);
      console.log('Error:', response.body);
    }

  } catch (error) {
    console.error('❌ /api/stocks test failed:');
    console.error('Error details:', error.message);
    if (error.response) {
      console.error('Response status:', error.response.status);
      console.error('Response body:', error.response.body);
    }
  }

  process.exit(0);
}

testStocksAPI();
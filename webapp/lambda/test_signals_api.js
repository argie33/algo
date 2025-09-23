const request = require('supertest');

const { app } = require('./index.js');

async function testSignalsAPI() {
  try {
    console.log('Testing /api/signals endpoint...');

    const response = await request(app)
      .get('/api/signals?limit=5')
      .expect('Content-Type', /json/);

    console.log('Status:', response.status);
    console.log('Response:', JSON.stringify(response.body, null, 2));

    if (response.status === 200) {
      console.log('✅ /api/signals working correctly');
      if (response.body.data) {
        console.log(`📊 Data count: ${response.body.data.length}`);
      }
    } else {
      console.log('❌ /api/signals failed with status:', response.status);
      console.log('Error:', response.body);
    }

  } catch (error) {
    console.error('❌ /api/signals test failed:');
    console.error('Error details:', error.message);
    if (error.response) {
      console.error('Response status:', error.response.status);
      console.error('Response body:', error.response.body);
    }
  }

  process.exit(0);
}

testSignalsAPI();
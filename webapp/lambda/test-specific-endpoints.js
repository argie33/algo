const axios = require('axios');

const BASE_URL = 'https://qda42av7je.execute-api.us-east-1.amazonaws.com/dev';

const endpoints = [
  '/api/financials/screen?limit=5',
  '/api/scoring/top?minScore=70&limit=5',
  '/api/analytics/sectors',
  '/api/stocks',
  '/api/sectors'
];

async function testEndpoints() {
  console.log('🧪 Testing recently fixed endpoints...\n');

  let successCount = 0;
  let totalCount = endpoints.length;

  for (const endpoint of endpoints) {
    try {
      const response = await axios.get(`${BASE_URL}${endpoint}`, {
        timeout: 10000,
        headers: {
          'Accept': 'application/json',
          'User-Agent': 'Debug-Tool/1.0'
        }
      });

      console.log(`✅ ${endpoint}`);
      console.log(`   Status: ${response.status}`);
      console.log(`   Success: ${response.data?.success || 'N/A'}`);
      if (response.data?.error) {
        console.log(`   Error: ${response.data.error}`);
      }
      console.log();

      if (response.status === 200) successCount++;

    } catch (error) {
      console.log(`❌ ${endpoint}`);
      console.log(`   Status: ${error.response?.status || 'No response'}`);
      console.log(`   Error: ${error.response?.data?.error || error.message}`);
      console.log();
    }
  }

  console.log(`📊 Summary: ${successCount}/${totalCount} endpoints working (${Math.round(successCount/totalCount*100)}%)`);
}

testEndpoints().catch(console.error);
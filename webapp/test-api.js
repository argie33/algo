// Test API endpoints
const axios = require('axios');

const API_BASE_URL = process.env.API_BASE_URL || 'http://localhost:3001';

async function testAPI() {
  console.log('Testing API endpoints...\n');

  // Test endpoints
  const endpoints = [
    { name: 'Stock Explorer', url: '/api/stocks?limit=5' },
    { name: 'Technical Analysis (Daily)', url: '/api/technical/daily?limit=5' },
    { name: 'Balance Sheet', url: '/api/financials/AAPL/balance-sheet?period=annual' },
    { name: 'Income Statement', url: '/api/financials/AAPL/income-statement?period=annual' },
    { name: 'Cash Flow', url: '/api/financials/AAPL/cash-flow?period=annual' },
    { name: 'Key Metrics', url: '/api/financials/AAPL/key-metrics' }
  ];

  for (const endpoint of endpoints) {
    try {
      console.log(`Testing ${endpoint.name}...`);
      const response = await axios.get(`${API_BASE_URL}${endpoint.url}`);
      console.log(`✅ ${endpoint.name}: Success`);
      console.log(`   Status: ${response.status}`);
      console.log(`   Data structure:`, Object.keys(response.data));
      if (response.data.data) {
        console.log(`   Data length: ${Array.isArray(response.data.data) ? response.data.data.length : 'Not an array'}`);
        console.log(`   Sample data:`, response.data.data?.[0] || response.data.data);
      }
      console.log('');
    } catch (error) {
      console.log(`❌ ${endpoint.name}: Failed`);
      console.log(`   Error: ${error.message}`);
      if (error.response) {
        console.log(`   Status: ${error.response.status}`);
        console.log(`   Response:`, error.response.data);
      }
      console.log('');
    }
  }
}

testAPI();
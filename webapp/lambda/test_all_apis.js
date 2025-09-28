
const axios = require('axios');

const BASE_URL = 'http://localhost:3001';

const apiEndpoints = [
  { name: 'Health', url: '/health' },
  { name: 'Stocks', url: '/api/stocks?page=1&limit=5' },
  { name: 'Screener', url: '/api/screener' },
  { name: 'Price STOCK7', url: '/api/price/STOCK7' },
  { name: 'News', url: '/api/news?limit=5' },
  { name: 'Earnings', url: '/api/earnings?limit=5' },
  { name: 'Analytics', url: '/api/analytics' },
  { name: 'Market', url: '/api/market' },
  { name: 'Performance', url: '/api/performance' },
  { name: 'Signals', url: '/api/signals' },
  { name: 'Sectors', url: '/api/sectors' },
  { name: 'Financials', url: '/api/financials?limit=5' },
  { name: 'Scores', url: '/api/scores' },
  { name: 'Portfolio (no auth)', url: '/api/portfolio' },
  { name: 'Portfolio (with auth)', url: '/api/portfolio', headers: { 'Authorization': 'Bearer mock-access-token' } },
  { name: 'Portfolio API Keys', url: '/api/portfolio/api-keys', headers: { 'Authorization': 'Bearer mock-access-token' } },
  { name: 'Risk', url: '/api/risk' },
  { name: 'Sentiment', url: '/api/sentiment' },
  { name: 'ETF', url: '/api/etf' },
  { name: 'Watchlist', url: '/api/watchlist' },
  { name: 'Orders', url: '/api/orders' },
  { name: 'Trading', url: '/api/trading' },
  { name: 'Technical', url: '/api/technical' },
  { name: 'Live Data', url: '/api/live-data' },
  { name: 'Metrics', url: '/api/metrics' },
  { name: 'Diagnostics', url: '/api/diagnostics' },
];

async function testAPI(endpoint) {
  try {
    const config = {
      timeout: 5000,
      validateStatus: function (status) {
        return status < 600; // Don't throw for any status code
      }
    };

    if (endpoint.headers) {
      config.headers = endpoint.headers;
    }

    const response = await axios.get(`${BASE_URL}${endpoint.url}`, config);

    return {
      name: endpoint.name,
      status: response.status,
      success: response.status >= 200 && response.status < 300,
      error: null,
      url: endpoint.url
    };
  } catch (error) {
    return {
      name: endpoint.name,
      status: error.response?.status || 'ERROR',
      success: false,
      error: error.message,
      url: endpoint.url
    };
  }
}

async function runAllTests() {
  console.log('🚀 Testing all API endpoints...\n');

  const results = [];
  const failed = [];
  const passed = [];

  for (const endpoint of apiEndpoints) {
    const result = await testAPI(endpoint);
    results.push(result);

    if (result.success) {
      passed.push(result);
      console.log(`✅ ${result.name.padEnd(25)} - ${result.status}`);
    } else {
      failed.push(result);
      console.log(`❌ ${result.name.padEnd(25)} - ${result.status} ${result.error ? `(${result.error})` : ''}`);
    }
  }

  console.log('\n📊 Summary:');
  console.log(`✅ Passed: ${passed.length}/${results.length} (${((passed.length/results.length)*100).toFixed(1)}%)`);
  console.log(`❌ Failed: ${failed.length}/${results.length}`);

  if (failed.length > 0) {
    console.log('\n🔧 Failed endpoints to fix:');
    failed.forEach(result => {
      console.log(`   • ${result.name} (${result.url}) - Status: ${result.status}`);
    });
  }

  console.log('\n📋 Results for investigation:');
  console.log(JSON.stringify(failed, null, 2));
}

runAllTests().catch(console.error);
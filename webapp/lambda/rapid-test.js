
const axios = require('axios');

const BASE_URL = 'https://qda42av7je.execute-api.us-east-1.amazonaws.com/dev';

const endpoints = [
  '/api/health', '/api/signals', '/api/watchlist', '/api/scores', '/api/orders',
  '/api/alerts', '/api/analysts', '/api/analytics', '/api/auth/validate',
  '/api/backtest', '/api/calendar', '/api/commodities', '/api/dashboard',
  '/api/data', '/api/debug', '/api/dividends', '/api/earnings', '/api/economic',
  '/api/etf', '/api/financials', '/api/insider', '/api/liveData', '/api/market',
  '/api/metrics', '/api/news', '/api/performance', '/api/portfolio',
  '/api/positioning', '/api/price', '/api/recommendations', '/api/research',
  '/api/risk', '/api/scoring', '/api/screener', '/api/sectors', '/api/sentiment',
  '/api/settings', '/api/stocks', '/api/strategyBuilder', '/api/technical',
  '/api/trades', '/api/trading', '/api/user'
];

async function rapidTest() {
  console.log('⚡ RAPID AWS API ERROR DETECTION');
  console.log('=================================');

  const results = await Promise.allSettled(
    endpoints.map(async (endpoint) => {
      try {
        const response = await axios.get(`${BASE_URL}${endpoint}`, {
          timeout: 3000,
          validateStatus: () => true
        });
        return {
          endpoint,
          status: response.status,
          is500: response.status >= 500
        };
      } catch (error) {
        return {
          endpoint,
          status: 'TIMEOUT',
          is500: false
        };
      }
    })
  );

  const serverErrors = [];
  const working = [];
  const other = [];

  results.forEach(result => {
    if (result.status === 'fulfilled') {
      const data = result.value;
      if (data.is500) {
        serverErrors.push(data.endpoint);
      } else if (data.status < 400) {
        working.push(data.endpoint);
      } else {
        other.push(data.endpoint);
      }
    }
  });

  console.log(`\n📊 RAPID RESULTS:`);
  console.log(`✅ Working: ${working.length}/${endpoints.length} (${Math.round(working.length/endpoints.length*100)}%)`);
  console.log(`❌ 500 Errors: ${serverErrors.length}`);
  console.log(`⚠️  Other: ${other.length}`);

  if (serverErrors.length > 0) {
    console.log('\n🚨 ENDPOINTS WITH 500 ERRORS:');
    serverErrors.forEach(endpoint => console.log(`❌ ${endpoint}`));

    console.log('\n🔧 PRIORITY FOR FIXING:');
    serverErrors.slice(0, 8).forEach(endpoint => console.log(`   - ${endpoint}`));
  } else {
    console.log('\n🎉 NO 500 ERRORS FOUND!');
  }

  return { working: working.length, total: endpoints.length, serverErrors };
}

if (require.main === module) {
  rapidTest().catch(console.error);
}

module.exports = { rapidTest };
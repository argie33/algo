
const axios = require('axios');

const BASE_URL = 'https://qda42av7je.execute-api.us-east-1.amazonaws.com/dev';

// Critical endpoints that work locally but fail in AWS
const criticalEndpoints = [
  { endpoint: '/api/dashboard', name: 'Dashboard' },
  { endpoint: '/api/data', name: 'Data API' },
  { endpoint: '/api/calendar', name: 'Calendar' },
  { endpoint: '/api/commodities', name: 'Commodities' },
  { endpoint: '/api/earnings', name: 'Earnings' },
  { endpoint: '/api/economic', name: 'Economic' },
  { endpoint: '/api/etf', name: 'ETF' },
  { endpoint: '/api/financials', name: 'Financials' },
  { endpoint: '/api/insider', name: 'Insider' },
  { endpoint: '/api/liveData', name: 'Live Data' },
  { endpoint: '/api/market', name: 'Market' },
  { endpoint: '/api/metrics', name: 'Metrics' },
  { endpoint: '/api/news', name: 'News' },
  { endpoint: '/api/performance', name: 'Performance' },
  { endpoint: '/api/positioning', name: 'Positioning' },
  { endpoint: '/api/price', name: 'Price' },
  { endpoint: '/api/recommendations', name: 'Recommendations' },
  { endpoint: '/api/research', name: 'Research' },
  { endpoint: '/api/risk', name: 'Risk' },
  { endpoint: '/api/scoring', name: 'Scoring' },
  { endpoint: '/api/screener', name: 'Screener' },
  { endpoint: '/api/sectors', name: 'Sectors' },
  { endpoint: '/api/sentiment', name: 'Sentiment' },
  { endpoint: '/api/settings', name: 'Settings' },
  { endpoint: '/api/stocks', name: 'Stocks' },
  { endpoint: '/api/strategyBuilder', name: 'Strategy Builder' },
  { endpoint: '/api/technical', name: 'Technical' },
  { endpoint: '/api/trades', name: 'Trades' },
  { endpoint: '/api/trading', name: 'Trading' },
  { endpoint: '/api/user', name: 'User' }
];

async function testEndpoint(endpoint, name) {
  try {
    const response = await axios.get(`${BASE_URL}${endpoint}`, {
      timeout: 5000,
      validateStatus: () => true
    });

    const isError = response.status >= 500;
    const hasData = response.data?.success !== false && response.status < 400;

    return {
      endpoint,
      name,
      status: response.status,
      isError,
      hasData,
      errorType: isError ? (response.data?.error || response.data?.message || 'Unknown error') : null
    };

  } catch (error) {
    return {
      endpoint,
      name,
      status: 'TIMEOUT',
      isError: true,
      hasData: false,
      errorType: error.message
    };
  }
}

async function awsSchemaTest() {
  console.log('🔍 AWS SCHEMA COMPATIBILITY TEST');
  console.log('=================================');
  console.log(`📍 Testing ${criticalEndpoints.length} critical endpoints...`);

  const results = await Promise.all(
    criticalEndpoints.map(({ endpoint, name }) => testEndpoint(endpoint, name))
  );

  const working = results.filter(r => r.hasData);
  const errors500 = results.filter(r => r.isError && r.status >= 500);
  const errors400 = results.filter(r => r.status >= 400 && r.status < 500);
  const timeouts = results.filter(r => r.status === 'TIMEOUT');

  console.log('\n📊 AWS TEST RESULTS:');
  console.log('====================');
  console.log(`✅ Working: ${working.length}/${criticalEndpoints.length} (${Math.round(working.length/criticalEndpoints.length*100)}%)`);
  console.log(`❌ 500 Errors: ${errors500.length}`);
  console.log(`⚠️  4xx Errors: ${errors400.length}`);
  console.log(`⏰ Timeouts: ${timeouts.length}`);

  if (errors500.length > 0) {
    console.log('\n🚨 CRITICAL 500 ERRORS (Schema Issues):');
    errors500.forEach(error => {
      console.log(`❌ ${error.name} (${error.endpoint})`);
      if (error.errorType && error.errorType.length < 100) {
        console.log(`   └─ ${error.errorType}`);
      }
    });
  }

  if (working.length > 0) {
    console.log('\n✅ WORKING ENDPOINTS:');
    working.slice(0, 10).forEach(success => {
      console.log(`✅ ${success.name}`);
    });
    if (working.length > 10) {
      console.log(`   ... and ${working.length - 10} more`);
    }
  }

  console.log('\n🎯 DIAGNOSIS:');
  if (errors500.length > 15) {
    console.log('🔧 Major schema differences detected between local and AWS');
    console.log('💡 Solution: Add defensive error handling with fallback data');
  } else if (errors500.length > 5) {
    console.log('⚠️  Moderate schema issues detected');
    console.log('💡 Solution: Fix specific table/column mismatches');
  } else {
    console.log('✅ Minor issues only, site is mostly functional');
  }

  return {
    working: working.length,
    total: criticalEndpoints.length,
    errors500: errors500.length,
    successRate: Math.round(working.length/criticalEndpoints.length*100)
  };
}

if (require.main === module) {
  awsSchemaTest().catch(console.error);
}

module.exports = { awsSchemaTest };
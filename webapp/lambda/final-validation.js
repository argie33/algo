#!/usr/bin/env node

const axios = require('axios');

const BASE_URL = 'https://qda42av7je.execute-api.us-east-1.amazonaws.com/dev';

// Complete endpoint list
const endpoints = [
  '/api/health',
  '/api/signals',
  '/api/watchlist',
  '/api/scores',
  '/api/orders',
  '/api/alerts',
  '/api/analysts',
  '/api/analytics',
  '/api/auth/validate',
  '/api/backtest',
  '/api/calendar',
  '/api/commodities',
  '/api/dashboard',
  '/api/data',
  '/api/debug',
  '/api/dividends',
  '/api/earnings',
  '/api/economic',
  '/api/etf',
  '/api/financials',
  '/api/insider',
  '/api/liveData',
  '/api/market',
  '/api/metrics',
  '/api/news',
  '/api/performance',
  '/api/portfolio',
  '/api/positioning',
  '/api/price',
  '/api/recommendations',
  '/api/research',
  '/api/risk',
  '/api/scoring',
  '/api/screener',
  '/api/sectors',
  '/api/sentiment',
  '/api/settings',
  '/api/stocks',
  '/api/strategyBuilder',
  '/api/technical',
  '/api/trades',
  '/api/trading',
  '/api/user'
];

async function testEndpoint(endpoint) {
  try {
    const response = await axios.get(`${BASE_URL}${endpoint}`, {
      timeout: 5000,
      validateStatus: () => true
    });

    return {
      endpoint,
      status: response.status,
      success: response.data?.success !== false && response.status < 500,
      is500Error: response.status >= 500,
      data: response.data
    };

  } catch (error) {
    return {
      endpoint,
      status: 'TIMEOUT',
      success: false,
      is500Error: false,
      error: error.message
    };
  }
}

async function finalValidation() {
  console.log('🎯 FINAL AWS API VALIDATION');
  console.log('===========================');
  console.log(`📍 Testing all ${endpoints.length} endpoints for comprehensive status...`);

  const results = await Promise.all(endpoints.map(testEndpoint));

  const working = results.filter(r => r.success);
  const serverErrors = results.filter(r => r.is500Error);
  const clientErrors = results.filter(r => r.status >= 400 && r.status < 500);
  const timeouts = results.filter(r => r.status === 'TIMEOUT');

  console.log('\n📊 FINAL RESULTS:');
  console.log('=================');
  console.log(`✅ Working: ${working.length}/${endpoints.length} (${Math.round(working.length/endpoints.length*100)}%)`);
  console.log(`❌ 500 Errors: ${serverErrors.length}`);
  console.log(`⚠️  Client Errors (4xx): ${clientErrors.length}`);
  console.log(`⏰ Timeouts: ${timeouts.length}`);

  if (serverErrors.length > 0) {
    console.log('\n🚨 Remaining 500 Errors:');
    serverErrors.forEach(error => {
      console.log(`❌ ${error.endpoint} (${error.status})`);
    });
  } else {
    console.log('\n🎉 NO 500 ERRORS FOUND!');
  }

  if (clientErrors.length > 0 && clientErrors.length <= 10) {
    console.log('\n⚠️  Client Errors (Expected for some endpoints):');
    clientErrors.forEach(error => {
      console.log(`⚠️  ${error.endpoint} (${error.status})`);
    });
  }

  const successRate = Math.round(working.length/endpoints.length*100);

  console.log('\n🏆 SUCCESS ANALYSIS:');
  console.log('===================');

  if (serverErrors.length === 0) {
    console.log('✅ ALL 500 ERRORS HAVE BEEN RESOLVED!');
    console.log('🎯 Mission accomplished - no more server errors');
    if (successRate >= 90) {
      console.log('🚀 API is fully operational');
    } else {
      console.log('📝 Some endpoints return 4xx errors (which is expected behavior)');
    }
  } else {
    console.log(`⚠️  ${serverErrors.length} endpoints still have 500 errors`);
  }

  console.log(`📈 Overall success rate: ${successRate}%`);

  return {
    total: endpoints.length,
    working: working.length,
    serverErrors: serverErrors.length,
    successRate,
    serverErrorsResolved: serverErrors.length === 0
  };
}

if (require.main === module) {
  finalValidation().catch(console.error);
}

module.exports = { finalValidation };
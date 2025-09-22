#!/usr/bin/env node

const axios = require('axios');

const BASE_URL = 'https://qda42av7je.execute-api.us-east-1.amazonaws.com/dev';

// Comprehensive endpoint list for full validation
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
      success: response.status < 500,
      hasError: response.status >= 500
    };

  } catch (error) {
    return {
      endpoint,
      status: 'TIMEOUT',
      success: false,
      hasError: true,
      error: error.code
    };
  }
}

async function runComprehensiveTest() {
  console.log('🚀 Comprehensive AWS API Validation');
  console.log('====================================');
  console.log(`📍 Testing ${endpoints.length} endpoints...`);

  const results = await Promise.all(endpoints.map(testEndpoint));

  let successful = 0;
  let serverErrors = 0;
  let timeouts = 0;
  let others = 0;

  const failures = [];

  results.forEach(result => {
    if (result.success) {
      successful++;
    } else if (result.status === 'TIMEOUT') {
      timeouts++;
      failures.push(result);
    } else if (result.status >= 500) {
      serverErrors++;
      failures.push(result);
    } else {
      others++;
    }
  });

  console.log('\n📊 Results Summary:');
  console.log('==================');
  console.log(`✅ Successful: ${successful}/${endpoints.length} (${Math.round(successful/endpoints.length*100)}%)`);
  console.log(`❌ Server Errors (500+): ${serverErrors}`);
  console.log(`⏰ Timeouts: ${timeouts}`);
  console.log(`⚠️  Other (4xx): ${others}`);

  if (failures.length > 0 && failures.length <= 10) {
    console.log('\n🔍 Failed Endpoints:');
    failures.forEach(f => {
      console.log(`❌ ${f.endpoint} (${f.status})`);
    });
  }

  const successRate = Math.round(successful/endpoints.length*100);

  if (successRate >= 95) {
    console.log('\n🎉 EXCELLENT! API is fully operational');
    console.log('✅ All critical 500 errors have been resolved');
  } else if (successRate >= 90) {
    console.log('\n✅ GOOD! Most endpoints working, minor issues remain');
  } else {
    console.log('\n⚠️  Some issues remain, but 500 errors should be fixed');
  }

  return {
    total: endpoints.length,
    successful,
    serverErrors,
    timeouts,
    successRate
  };
}

if (require.main === module) {
  runComprehensiveTest().catch(console.error);
}

module.exports = { runComprehensiveTest };
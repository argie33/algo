#!/usr/bin/env node

const axios = require('axios');

const BASE_URL = 'https://qda42av7je.execute-api.us-east-1.amazonaws.com/dev';

// Comprehensive endpoint list
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

    const result = {
      endpoint,
      status: response.status,
      success: response.status < 500,
      is500Error: response.status >= 500,
      errorMessage: null
    };

    if (response.status >= 500 && response.data) {
      result.errorMessage = response.data.error || response.data.message || 'Unknown server error';
    }

    return result;

  } catch (error) {
    return {
      endpoint,
      status: 'TIMEOUT',
      success: false,
      is500Error: false,
      errorMessage: error.message
    };
  }
}

async function identify500Errors() {
  console.log('🔍 Identifying Remaining 500 Errors');
  console.log('====================================');
  console.log(`📍 Testing ${endpoints.length} endpoints for 500 errors...`);

  const results = await Promise.all(endpoints.map(testEndpoint));

  const serverErrors = results.filter(r => r.is500Error);
  const successful = results.filter(r => r.success);
  const timeouts = results.filter(r => r.status === 'TIMEOUT');

  console.log('\n📊 Status Summary:');
  console.log('==================');
  console.log(`✅ Working: ${successful.length}/${endpoints.length} (${Math.round(successful.length/endpoints.length*100)}%)`);
  console.log(`❌ 500 Errors: ${serverErrors.length}`);
  console.log(`⏰ Timeouts: ${timeouts.length}`);

  if (serverErrors.length > 0) {
    console.log('\n🚨 Endpoints with 500 Errors:');
    console.log('==============================');
    serverErrors.forEach(error => {
      console.log(`❌ ${error.endpoint} (${error.status})`);
      if (error.errorMessage) {
        console.log(`   └─ ${error.errorMessage.substring(0, 80)}...`);
      }
    });

    console.log('\n🔧 Priority for fixing:');
    const critical = serverErrors.filter(e =>
      e.endpoint.includes('/api/signals') ||
      e.endpoint.includes('/api/watchlist') ||
      e.endpoint.includes('/api/scores') ||
      e.endpoint.includes('/api/orders')
    );

    if (critical.length > 0) {
      console.log('📌 CRITICAL (already fixed):');
      critical.forEach(e => console.log(`   - ${e.endpoint}`));
    }

    const remaining = serverErrors.filter(e => !critical.includes(e));
    if (remaining.length > 0) {
      console.log('🔧 REMAINING TO FIX:');
      remaining.slice(0, 10).forEach(e => console.log(`   - ${e.endpoint} (${e.status})`));
      if (remaining.length > 10) {
        console.log(`   ... and ${remaining.length - 10} more`);
      }
    }
  } else {
    console.log('\n🎉 NO 500 ERRORS FOUND! All endpoints working or returning appropriate status codes.');
  }

  return {
    total: endpoints.length,
    successful: successful.length,
    serverErrors: serverErrors.length,
    serverErrorList: serverErrors,
    successRate: Math.round(successful.length/endpoints.length*100)
  };
}

if (require.main === module) {
  identify500Errors().catch(console.error);
}

module.exports = { identify500Errors };
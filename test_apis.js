#!/usr/bin/env node

const axios = require('axios');

const BASE_URL = 'http://localhost:3001';

// List of all API endpoints from the route definitions
const endpoints = [
  // Core routes
  '/health',
  '/auth/login',
  '/stocks',
  '/screener',
  '/scores',
  '/metrics',
  '/market',
  '/analysts',
  '/analytics',
  '/commodities',
  '/data',
  '/financials',
  '/trading',
  '/technical/daily',
  '/calendar',
  '/dashboard',
  '/signals',
  '/backtest',
  '/portfolio',
  '/performance',
  '/scoring',
  '/price',
  '/risk',
  '/sectors',
  '/sentiment',
  '/settings',
  '/trades',
  '/live-data',
  '/orders',
  '/news',
  '/diagnostics',
  '/watchlist',
  '/etf',
  '/insider',
  '/dividend',
  
  // API prefixed routes
  '/api/health',
  '/api/auth/login',
  '/api/stocks',
  '/api/screener',
  '/api/scores',
  '/api/metrics',
  '/api/market',
  '/api/analysts',
  '/api/analytics',
  '/api/commodities',
  '/api/data',
  '/api/financials',
  '/api/trading',
  '/api/technical/daily',
  '/api/calendar',
  '/api/dashboard',
  '/api/economic',
  '/api/signals',
  '/api/backtest',
  '/api/portfolio',
  '/api/performance',
  '/api/recommendations',
  '/api/research',
  '/api/earnings',
  '/api/scoring',
  '/api/price',
  '/api/risk',
  '/api/sectors',
  '/api/sentiment',
  '/api/settings',
  '/api/trades',
  '/api/live-data',
  '/api/orders',
  '/api/news',
  '/api/diagnostics',
  '/api/watchlist',
  '/api/etf',
  '/api/insider',
  '/api/dividend',
  '/api/positioning',
  '/api/strategyBuilder',
  '/api/liveData',
  '/api/alerts'
];

async function testEndpoint(endpoint) {
  try {
    const response = await axios.get(`${BASE_URL}${endpoint}`, {
      timeout: 5000,
      validateStatus: () => true // Don't throw on non-2xx status codes
    });
    
    return {
      endpoint,
      status: response.status,
      data: response.status === 501 ? response.data : null
    };
  } catch (error) {
    return {
      endpoint,
      status: 'ERROR',
      error: error.message
    };
  }
}

async function main() {
  console.log('🔍 Testing API endpoints for 501 errors...\n');
  
  const results = [];
  const errors501 = [];
  const errors = [];
  const working = [];
  
  for (const endpoint of endpoints) {
    const result = await testEndpoint(endpoint);
    results.push(result);
    
    if (result.status === 501) {
      errors501.push(result);
      console.log(`❌ 501 - ${endpoint}`);
    } else if (result.status === 'ERROR' || result.status >= 400) {
      errors.push(result);
      console.log(`⚠️  ${result.status} - ${endpoint}`);
    } else {
      working.push(result);
      console.log(`✅ ${result.status} - ${endpoint}`);
    }
  }
  
  console.log('\n📊 Summary:');
  console.log(`✅ Working endpoints: ${working.length}`);
  console.log(`❌ 501 endpoints: ${errors501.length}`);
  console.log(`⚠️  Other errors: ${errors.length}`);
  
  if (errors501.length > 0) {
    console.log('\n🚨 Endpoints returning 501 (Not Implemented):');
    errors501.forEach(result => {
      console.log(`  - ${result.endpoint}`);
    });
  }
  
  if (errors.length > 0) {
    console.log('\n⚠️  Endpoints with other errors:');
    errors.forEach(result => {
      console.log(`  - ${result.endpoint}: ${result.status} ${result.error || ''}`);
    });
  }
  
  // Save detailed results to file
  const fs = require('fs');
  fs.writeFileSync('api_test_results.json', JSON.stringify({
    summary: {
      total: results.length,
      working: working.length,
      errors501: errors501.length,
      otherErrors: errors.length
    },
    working,
    errors501,
    errors
  }, null, 2));
  
  console.log('\n💾 Detailed results saved to api_test_results.json');
}

main().catch(console.error);
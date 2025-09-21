#!/usr/bin/env node

const axios = require('axios');

const AWS_BASE_URL = 'https://qda42av7je.execute-api.us-east-1.amazonaws.com/dev';

// Comprehensive list of all API endpoints from server.js
const ENDPOINTS = [
  // Basic health
  { path: '/health', method: 'GET', category: 'health' },
  { path: '/api', method: 'GET', category: 'info' },

  // Core API endpoints
  { path: '/api/alerts', method: 'GET', category: 'alerts' },
  { path: '/api/analytics', method: 'GET', category: 'analytics' },
  { path: '/api/auth/status', method: 'GET', category: 'auth' },
  { path: '/api/stocks', method: 'GET', category: 'stocks' },
  { path: '/api/stocks/AAPL', method: 'GET', category: 'stocks' },
  { path: '/api/strategies', method: 'GET', category: 'strategies' },
  { path: '/api/strategy-builder', method: 'GET', category: 'strategies' },
  { path: '/api/metrics', method: 'GET', category: 'metrics' },
  { path: '/api/health', method: 'GET', category: 'health' },
  { path: '/api/market', method: 'GET', category: 'market' },
  { path: '/api/market/overview', method: 'GET', category: 'market' },
  { path: '/api/analysts', method: 'GET', category: 'analysts' },
  { path: '/api/backtest', method: 'GET', category: 'backtest' },

  // Calendar endpoints (user reported these failing)
  { path: '/api/calendar', method: 'GET', category: 'calendar' },
  { path: '/api/calendar/events', method: 'GET', category: 'calendar' },
  { path: '/api/calendar/events?type=upcoming&page=1&limit=25', method: 'GET', category: 'calendar' },
  { path: '/api/calendar/earnings-estimates', method: 'GET', category: 'calendar' },
  { path: '/api/calendar/earnings-estimates?page=1&limit=25', method: 'GET', category: 'calendar' },

  // Other endpoints
  { path: '/api/commodities', method: 'GET', category: 'commodities' },
  { path: '/api/dashboard', method: 'GET', category: 'dashboard' },
  { path: '/api/data', method: 'GET', category: 'data' },
  { path: '/api/dividend', method: 'GET', category: 'dividend' },
  { path: '/api/earnings', method: 'GET', category: 'earnings' },
  { path: '/api/economic', method: 'GET', category: 'economic' },
  { path: '/api/etf', method: 'GET', category: 'etf' },
  { path: '/api/financials', method: 'GET', category: 'financials' },
  { path: '/api/insider', method: 'GET', category: 'insider' },
  { path: '/api/livedata', method: 'GET', category: 'livedata' },
  { path: '/api/news', method: 'GET', category: 'news' },
  { path: '/api/orders', method: 'GET', category: 'orders' },
  { path: '/api/performance', method: 'GET', category: 'performance' },
  { path: '/api/portfolio', method: 'GET', category: 'portfolio' },
  { path: '/api/positioning', method: 'GET', category: 'positioning' },
  { path: '/api/price', method: 'GET', category: 'price' },
  { path: '/api/price/AAPL', method: 'GET', category: 'price' },
  { path: '/api/recommendations', method: 'GET', category: 'recommendations' },
  { path: '/api/risk', method: 'GET', category: 'risk' },
  { path: '/api/scoring', method: 'GET', category: 'scoring' },
  { path: '/api/scores', method: 'GET', category: 'scores' },
  { path: '/api/screener', method: 'GET', category: 'screener' },
  { path: '/api/sectors', method: 'GET', category: 'sectors' },
  { path: '/api/sentiment', method: 'GET', category: 'sentiment' },
  { path: '/api/settings', method: 'GET', category: 'settings' },
  { path: '/api/signals', method: 'GET', category: 'signals' },
  { path: '/api/technical', method: 'GET', category: 'technical' },
  { path: '/api/trading', method: 'GET', category: 'trading' },
  { path: '/api/trading/signals', method: 'GET', category: 'trading' },
  { path: '/api/trades', method: 'GET', category: 'trades' },
  { path: '/api/user', method: 'GET', category: 'user' },
  { path: '/api/watchlist', method: 'GET', category: 'watchlist' },
  { path: '/api/websocket', method: 'GET', category: 'websocket' }
];

async function testEndpoint(endpoint) {
  const url = `${AWS_BASE_URL}${endpoint.path}`;
  const startTime = Date.now();

  try {
    const response = await axios({
      method: endpoint.method,
      url: url,
      timeout: 10000,
      validateStatus: () => true // Don't throw on 4xx/5xx
    });

    const responseTime = Date.now() - startTime;

    return {
      endpoint: endpoint.path,
      category: endpoint.category,
      method: endpoint.method,
      status: response.status,
      responseTime,
      success: response.status >= 200 && response.status < 400,
      error: response.status >= 400 ? response.statusText : null,
      responseSize: JSON.stringify(response.data).length,
      hasData: response.data && Object.keys(response.data).length > 0
    };
  } catch (error) {
    const responseTime = Date.now() - startTime;

    return {
      endpoint: endpoint.path,
      category: endpoint.category,
      method: endpoint.method,
      status: error.code === 'ECONNABORTED' ? 'TIMEOUT' : 'ERROR',
      responseTime,
      success: false,
      error: error.message,
      responseSize: 0,
      hasData: false
    };
  }
}

async function runHealthCheck() {
  console.log(`🔍 AWS API Health Check Starting...`);
  console.log(`📍 Base URL: ${AWS_BASE_URL}`);
  console.log(`🎯 Testing ${ENDPOINTS.length} endpoints\n`);

  const results = [];
  const batchSize = 5; // Test 5 endpoints concurrently

  for (let i = 0; i < ENDPOINTS.length; i += batchSize) {
    const batch = ENDPOINTS.slice(i, i + batchSize);
    const batchResults = await Promise.all(batch.map(testEndpoint));
    results.push(...batchResults);

    // Show progress
    console.log(`✅ Tested ${Math.min(i + batchSize, ENDPOINTS.length)}/${ENDPOINTS.length} endpoints`);
  }

  // Analyze results
  const successful = results.filter(r => r.success);
  const failed = results.filter(r => !r.success);
  const by404 = failed.filter(r => r.status === 404);
  const by500 = failed.filter(r => r.status >= 500);
  const timeouts = failed.filter(r => r.status === 'TIMEOUT');
  const otherErrors = failed.filter(r => !['TIMEOUT', 404].includes(r.status) && r.status < 500);

  console.log(`\n📊 HEALTH CHECK SUMMARY`);
  console.log(`========================`);
  console.log(`✅ Successful: ${successful.length}/${ENDPOINTS.length} (${Math.round(successful.length/ENDPOINTS.length*100)}%)`);
  console.log(`❌ Failed: ${failed.length}/${ENDPOINTS.length} (${Math.round(failed.length/ENDPOINTS.length*100)}%)`);
  console.log(`🔴 404 Not Found: ${by404.length}`);
  console.log(`🔴 500+ Server Error: ${by500.length}`);
  console.log(`⏰ Timeouts: ${timeouts.length}`);
  console.log(`⚠️  Other Errors: ${otherErrors.length}`);

  if (failed.length > 0) {
    console.log(`\n🚨 FAILING ENDPOINTS`);
    console.log(`==================`);

    // Group by error type
    if (by404.length > 0) {
      console.log(`\n📍 404 NOT FOUND (${by404.length}):`);
      by404.forEach(r => {
        console.log(`   ${r.method} ${r.endpoint} [${r.category}]`);
      });
    }

    if (by500.length > 0) {
      console.log(`\n💥 500+ SERVER ERRORS (${by500.length}):`);
      by500.forEach(r => {
        console.log(`   ${r.status} ${r.method} ${r.endpoint} [${r.category}] - ${r.error}`);
      });
    }

    if (timeouts.length > 0) {
      console.log(`\n⏰ TIMEOUTS (${timeouts.length}):`);
      timeouts.forEach(r => {
        console.log(`   ${r.method} ${r.endpoint} [${r.category}] - ${r.error}`);
      });
    }

    if (otherErrors.length > 0) {
      console.log(`\n⚠️  OTHER ERRORS (${otherErrors.length}):`);
      otherErrors.forEach(r => {
        console.log(`   ${r.status} ${r.method} ${r.endpoint} [${r.category}] - ${r.error}`);
      });
    }
  }

  if (successful.length > 0) {
    console.log(`\n✅ WORKING ENDPOINTS (${successful.length}):`);
    const byCategory = {};
    successful.forEach(r => {
      if (!byCategory[r.category]) byCategory[r.category] = [];
      byCategory[r.category].push(r);
    });

    Object.keys(byCategory).sort().forEach(category => {
      console.log(`   ${category}: ${byCategory[category].length} endpoints`);
    });
  }

  // Performance analysis
  const avgResponseTime = results.reduce((sum, r) => sum + r.responseTime, 0) / results.length;
  const slowEndpoints = results.filter(r => r.success && r.responseTime > 2000);

  console.log(`\n⚡ PERFORMANCE SUMMARY`);
  console.log(`=====================`);
  console.log(`📊 Average Response Time: ${Math.round(avgResponseTime)}ms`);

  if (slowEndpoints.length > 0) {
    console.log(`🐌 Slow Endpoints (>2s): ${slowEndpoints.length}`);
    slowEndpoints.forEach(r => {
      console.log(`   ${r.endpoint}: ${r.responseTime}ms`);
    });
  }

  // Save detailed results to file
  const detailedResults = {
    timestamp: new Date().toISOString(),
    baseUrl: AWS_BASE_URL,
    summary: {
      total: ENDPOINTS.length,
      successful: successful.length,
      failed: failed.length,
      successRate: Math.round(successful.length/ENDPOINTS.length*100),
      avgResponseTime: Math.round(avgResponseTime)
    },
    errorBreakdown: {
      notFound404: by404.length,
      serverError500: by500.length,
      timeouts: timeouts.length,
      otherErrors: otherErrors.length
    },
    failedEndpoints: failed,
    successfulEndpoints: successful
  };

  require('fs').writeFileSync(
    '/home/stocks/algo/webapp/lambda/aws-health-check-results.json',
    JSON.stringify(detailedResults, null, 2)
  );

  console.log(`\n💾 Detailed results saved to: aws-health-check-results.json`);
  console.log(`\n🔧 NEXT STEPS:`);

  if (by404.length > 0) {
    console.log(`1. Check route definitions for 404 endpoints`);
    console.log(`2. Verify API Gateway deployment includes all routes`);
  }

  if (by500.length > 0) {
    console.log(`3. Check server logs for 500 error root causes`);
    console.log(`4. Verify database connections and table schemas`);
  }

  if (timeouts.length > 0) {
    console.log(`5. Investigate timeout causes (database queries, external APIs)`);
  }

  return detailedResults;
}

if (require.main === module) {
  runHealthCheck().catch(error => {
    console.error('❌ Health check failed:', error.message);
    process.exit(1);
  });
}

module.exports = { runHealthCheck, testEndpoint };
const axios = require('axios');

const BASE_URL = 'http://localhost:3001/api';
const TIMEOUT = 10000;

// Comprehensive API endpoint testing
const endpoints = [
  // Health & Core
  { method: 'GET', path: '/health', name: 'Health Check' },
  
  // Authentication (will be 401 without token)
  { method: 'POST', path: '/auth/login', name: 'Auth Login', data: { email: 'test@example.com', password: 'test' } },
  { method: 'POST', path: '/auth/register', name: 'Auth Register', data: { email: 'test@example.com', password: 'test', name: 'Test' } },
  { method: 'POST', path: '/auth/forgot-password', name: 'Forgot Password', data: { email: 'test@example.com' } },
  
  // Market Data
  { method: 'GET', path: '/market/overview', name: 'Market Overview' },
  { method: 'GET', path: '/market/sectors', name: 'Market Sectors' },
  { method: 'GET', path: '/market/indices', name: 'Market Indices' },
  { method: 'GET', path: '/market/movers', name: 'Market Movers' },
  
  // Stock Data  
  { method: 'GET', path: '/stocks/search?q=AAPL', name: 'Stock Search' },
  { method: 'GET', path: '/stocks/AAPL/quote', name: 'Stock Quote' },
  { method: 'GET', path: '/stocks/AAPL/price', name: 'Stock Price' },
  { method: 'GET', path: '/stocks/AAPL/technical', name: 'Stock Technical' },
  { method: 'GET', path: '/stocks/AAPL/fundamentals', name: 'Stock Fundamentals' },
  
  // Technical Analysis
  { method: 'GET', path: '/technical/analysis/AAPL', name: 'Technical Analysis' },
  { method: 'GET', path: '/technical/indicators/AAPL', name: 'Technical Indicators' },
  
  // News & Sentiment
  { method: 'GET', path: '/news/latest', name: 'Latest News' },
  { method: 'GET', path: '/news/AAPL', name: 'Stock News' },
  { method: 'GET', path: '/sentiment/AAPL', name: 'Stock Sentiment' },
  { method: 'GET', path: '/sentiment/market', name: 'Market Sentiment' },
  
  // Calendar & Events
  { method: 'GET', path: '/calendar/earnings', name: 'Earnings Calendar' },
  { method: 'GET', path: '/calendar/events', name: 'Market Events' },
  
  // Screener & Analysis
  { method: 'GET', path: '/screener/stocks', name: 'Stock Screener' },
  { method: 'POST', path: '/screener/custom', name: 'Custom Screener', data: { filters: {} } },
  
  // Portfolio (requires auth)
  { method: 'GET', path: '/portfolio/holdings', name: 'Portfolio Holdings', requiresAuth: true },
  { method: 'GET', path: '/portfolio/performance', name: 'Portfolio Performance', requiresAuth: true },
  
  // Trading Signals
  { method: 'GET', path: '/signals/trending', name: 'Trending Signals' },
  { method: 'GET', path: '/signals/performance', name: 'Signals Performance' },
  { method: 'POST', path: '/signals/backtest', name: 'Signal Backtest', data: { signal_id: 'test' } },
  
  // Watchlist (requires auth)
  { method: 'GET', path: '/watchlist', name: 'Get Watchlist', requiresAuth: true },
  { method: 'POST', path: '/watchlist', name: 'Add to Watchlist', requiresAuth: true, data: { symbol: 'AAPL' } },
  
  // Settings (requires auth)
  { method: 'GET', path: '/settings', name: 'Get Settings', requiresAuth: true },
  { method: 'PUT', path: '/settings', name: 'Update Settings', requiresAuth: true, data: { theme: 'dark' } },
  
  // Backtest
  { method: 'POST', path: '/backtest/run', name: 'Run Backtest', data: { strategy: 'test', symbols: ['AAPL'] } },
  { method: 'GET', path: '/backtest/results/test', name: 'Backtest Results' },
  
  // Strategy Builder
  { method: 'GET', path: '/strategies', name: 'Get Strategies' },
  { method: 'POST', path: '/strategies/ai-generate', name: 'AI Generate Strategy', requiresAuth: true, data: { prompt: 'simple momentum strategy', symbols: ['AAPL'] } },
  
  // Metrics & Performance
  { method: 'GET', path: '/metrics/system', name: 'System Metrics' },
  { method: 'GET', path: '/performance/api', name: 'API Performance' },
  
  // Root endpoints for route verification
  { method: 'GET', path: '/dashboard', name: 'Dashboard Root' },
  { method: 'GET', path: '/data', name: 'Data Root' },
  { method: 'GET', path: '/financials', name: 'Financials Root' },
  { method: 'GET', path: '/scores', name: 'Scores Root' },
  { method: 'GET', path: '/sectors', name: 'Sectors Root' },
  { method: 'GET', path: '/orders', name: 'Orders Root' },
  { method: 'GET', path: '/trades', name: 'Trades Root' },
  { method: 'GET', path: '/risk', name: 'Risk Root' },
  { method: 'GET', path: '/analysts', name: 'Analysts Root' },
];

async function testEndpoint(endpoint) {
  try {
    const config = {
      method: endpoint.method,
      url: `${BASE_URL}${endpoint.path}`,
      timeout: TIMEOUT,
      validateStatus: () => true // Don't throw on any status code
    };

    if (endpoint.data) {
      config.data = endpoint.data;
    }

    if (endpoint.requiresAuth) {
      config.headers = {
        'Authorization': 'Bearer fake-token-for-testing'
      };
    }

    const response = await axios(config);
    
    return {
      name: endpoint.name,
      path: endpoint.path,
      method: endpoint.method,
      status: response.status,
      statusText: response.statusText,
      success: response.status < 400 || (endpoint.requiresAuth && response.status === 401),
      requiresAuth: endpoint.requiresAuth || false,
      responseSize: JSON.stringify(response.data).length,
      error: null
    };
  } catch (error) {
    return {
      name: endpoint.name,
      path: endpoint.path,
      method: endpoint.method,
      status: error.response?.status || 'ERROR',
      statusText: error.response?.statusText || error.message,
      success: false,
      requiresAuth: endpoint.requiresAuth || false,
      error: error.message
    };
  }
}

async function runComprehensiveTest() {
  console.log(`🧪 Running comprehensive API tests on ${endpoints.length} endpoints...\n`);
  
  const results = [];
  const startTime = Date.now();
  
  // Run tests in parallel batches of 10 to avoid overwhelming the server
  const batchSize = 10;
  for (let i = 0; i < endpoints.length; i += batchSize) {
    const batch = endpoints.slice(i, i + batchSize);
    const batchResults = await Promise.all(batch.map(testEndpoint));
    results.push(...batchResults);
    
    // Show progress
    console.log(`📊 Completed ${Math.min(i + batchSize, endpoints.length)}/${endpoints.length} tests`);
  }
  
  const endTime = Date.now();
  
  // Analyze results
  const successful = results.filter(r => r.success);
  const failed = results.filter(r => !r.success);
  const authRequired = results.filter(r => r.requiresAuth && r.status === 401);
  const notFound = results.filter(r => r.status === 404);
  const notImplemented = results.filter(r => r.status === 501);
  const serverErrors = results.filter(r => r.status >= 500 && r.status !== 501);
  
  console.log(`\n📈 COMPREHENSIVE API TEST RESULTS`);
  console.log(`${'='.repeat(50)}`);
  console.log(`⏱️  Total Time: ${endTime - startTime}ms`);
  console.log(`📊 Total Endpoints: ${endpoints.length}`);
  console.log(`✅ Successful: ${successful.length} (${((successful.length/endpoints.length)*100).toFixed(1)}%)`);
  console.log(`❌ Failed: ${failed.length} (${((failed.length/endpoints.length)*100).toFixed(1)}%)`);
  console.log(`🔒 Auth Required (401): ${authRequired.length}`);
  console.log(`🚫 Not Found (404): ${notFound.length}`);
  console.log(`⚠️  Not Implemented (501): ${notImplemented.length}`);
  console.log(`💥 Server Errors (5xx): ${serverErrors.length}\n`);
  
  // Show problematic endpoints
  if (notImplemented.length > 0) {
    console.log(`🔧 NOT IMPLEMENTED (501) - NEED TO BUILD:`);
    notImplemented.forEach(r => console.log(`   ${r.method} ${r.path} - ${r.name}`));
    console.log();
  }
  
  if (notFound.length > 0) {
    console.log(`🚫 NOT FOUND (404) - CHECK ROUTES:`);
    notFound.forEach(r => console.log(`   ${r.method} ${r.path} - ${r.name}`));
    console.log();
  }
  
  if (serverErrors.length > 0) {
    console.log(`💥 SERVER ERRORS (5xx) - NEED TO FIX:`);
    serverErrors.forEach(r => console.log(`   ${r.method} ${r.path} - ${r.name} (${r.status})`));
    console.log();
  }
  
  // Show failed endpoints for debugging
  if (failed.length > 0) {
    console.log(`❌ FAILED ENDPOINTS (${failed.length}):`)
    failed.forEach(r => console.log(`   ${r.method} ${r.path} - ${r.name} (${r.status}) - ${r.error || r.statusText}`));
    console.log()
  }

  // Show successful endpoints for verification
  console.log(`✅ WORKING ENDPOINTS (${successful.length}):`);
  successful.forEach(r => {
    const authNote = r.requiresAuth ? ' (Auth Required)' : '';
    console.log(`   ${r.method} ${r.path} - ${r.name} (${r.status})${authNote}`);
  });
  
  console.log(`\n${'='.repeat(50)}`);
  console.log(`🎯 API Health: ${((successful.length/endpoints.length)*100).toFixed(1)}% functional`);
  
  return results;
}

if (require.main === module) {
  runComprehensiveTest().catch(console.error);
}

module.exports = { runComprehensiveTest, testEndpoint };
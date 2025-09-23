const http = require('http');

// Comprehensive test of ALL API endpoints
const allEndpoints = [
  // Basic endpoints
  { path: '/api/health', method: 'GET', description: 'Health check' },
  { path: '/api/metrics', method: 'GET', description: 'Metrics' },
  { path: '/api/stocks', method: 'GET', description: 'Stocks listing' },
  { path: '/api/signals', method: 'GET', description: 'Trading signals' },
  { path: '/api/scores', method: 'GET', description: 'Stock scores' },
  { path: '/api/market', method: 'GET', description: 'Market data' },
  { path: '/api/news', method: 'GET', description: 'News' },
  { path: '/api/earnings', method: 'GET', description: 'Earnings' },
  { path: '/api/sectors', method: 'GET', description: 'Sectors' },
  { path: '/api/analytics', method: 'GET', description: 'Analytics' },
  { path: '/api/calendar', method: 'GET', description: 'Calendar' },
  { path: '/api/technical', method: 'GET', description: 'Technical analysis' },
  { path: '/api/performance', method: 'GET', description: 'Performance' },
  { path: '/api/risk', method: 'GET', description: 'Risk assessment' },
  { path: '/api/screener', method: 'GET', description: 'Stock screener' },
  { path: '/api/watchlist', method: 'GET', description: 'Watchlist' },
  { path: '/api/trades', method: 'GET', description: 'Trades' },

  // Symbol-specific endpoints
  { path: '/api/stocks/AAPL', method: 'GET', description: 'Stock details AAPL' },
  { path: '/api/stocks/TSLA', method: 'GET', description: 'Stock details TSLA' },
  { path: '/api/stocks/MSFT', method: 'GET', description: 'Stock details MSFT' },
  { path: '/api/signals/AAPL', method: 'GET', description: 'Signals AAPL' },
  { path: '/api/signals/TSLA', method: 'GET', description: 'Signals TSLA' },
  { path: '/api/technical/AAPL', method: 'GET', description: 'Technical AAPL' },
  { path: '/api/technical/TSLA', method: 'GET', description: 'Technical TSLA' },
  { path: '/api/technical/daily/AAPL', method: 'GET', description: 'Technical daily AAPL' },
  { path: '/api/price/AAPL', method: 'GET', description: 'Price AAPL' },
  { path: '/api/price/TSLA', method: 'GET', description: 'Price TSLA' },
  { path: '/api/earnings/AAPL', method: 'GET', description: 'Earnings AAPL' },
  { path: '/api/dividend/AAPL', method: 'GET', description: 'Dividend AAPL' },

  // Time-based endpoints
  { path: '/api/technical/daily', method: 'GET', description: 'Technical daily' },
  { path: '/api/technical/weekly', method: 'GET', description: 'Technical weekly' },
  { path: '/api/technical/monthly', method: 'GET', description: 'Technical monthly' },
  { path: '/api/price/daily', method: 'GET', description: 'Price daily' },

  // Parameterized endpoints
  { path: '/api/stocks?limit=10', method: 'GET', description: 'Stocks with limit' },
  { path: '/api/signals?limit=5', method: 'GET', description: 'Signals with limit' },
  { path: '/api/news?limit=5', method: 'GET', description: 'News with limit' },
  { path: '/api/earnings?symbol=AAPL', method: 'GET', description: 'Earnings filtered' },
  { path: '/api/technical?symbol=AAPL', method: 'GET', description: 'Technical filtered' },

  // Market status endpoints
  { path: '/api/market/status', method: 'GET', description: 'Market status' },
  { path: '/api/market/hours', method: 'GET', description: 'Market hours' },

  // Additional specific endpoints that might exist
  { path: '/api/fundamentals', method: 'GET', description: 'Fundamentals' },
  { path: '/api/insider', method: 'GET', description: 'Insider trading' },
  { path: '/api/etf', method: 'GET', description: 'ETF data' },
  { path: '/api/commodities', method: 'GET', description: 'Commodities' },
  { path: '/api/economic', method: 'GET', description: 'Economic data' },
  { path: '/api/sentiment', method: 'GET', description: 'Sentiment' },

  // Signal endpoints
  { path: '/api/signals/buy', method: 'GET', description: 'Buy signals' },
  { path: '/api/signals/sell', method: 'GET', description: 'Sell signals' },
  { path: '/api/signals/trending', method: 'GET', description: 'Trending signals' },
  { path: '/api/signals/alerts', method: 'GET', description: 'Signal alerts' },

  // Technical analysis sub-endpoints
  { path: '/api/technical/analysis', method: 'GET', description: 'Technical analysis' },
  { path: '/api/technical/indicators/AAPL', method: 'GET', description: 'Technical indicators AAPL' },
  { path: '/api/technical/patterns/AAPL', method: 'GET', description: 'Technical patterns AAPL' },
];

async function testAPI() {
  const results = [];
  const issues = [];
  console.log('🔍 Running EXHAUSTIVE API test...\n');

  let passed = 0;
  let failed = 0;
  let serverErrors = 0;
  let emptyData = 0;

  for (const endpoint of allEndpoints) {
    try {
      const result = await makeRequest(endpoint);
      results.push(result);

      if (result.success) {
        passed++;
        console.log(`✅ ${endpoint.description}: ${endpoint.method} ${endpoint.path}`);

        // Check for empty data issues
        if (result.data && result.data.includes('"data":[]') ||
            result.data.includes('"data":0') ||
            result.data.includes('"total":0') ||
            result.data.includes('No data available') ||
            result.data.includes('not available')) {
          emptyData++;
          console.log(`   ⚠️  EMPTY DATA: ${endpoint.path}`);
          issues.push({ type: 'EMPTY_DATA', endpoint: endpoint.path, description: endpoint.description });
        }
      } else {
        failed++;
        if (result.statusCode >= 500) {
          serverErrors++;
          console.log(`❌ ${endpoint.description}: ${endpoint.method} ${endpoint.path}`);
          console.log(`   Status: ${result.statusCode}, Error: ${result.error}`);
          issues.push({ type: 'SERVER_ERROR', endpoint: endpoint.path, status: result.statusCode, error: result.error });
        } else if (result.statusCode >= 400) {
          console.log(`⚠️  ${endpoint.description}: ${endpoint.method} ${endpoint.path}`);
          console.log(`   Status: ${result.statusCode}, Error: ${result.error}`);
          issues.push({ type: 'CLIENT_ERROR', endpoint: endpoint.path, status: result.statusCode, error: result.error });
        }
      }
    } catch (error) {
      failed++;
      serverErrors++;
      console.log(`💥 ${endpoint.description}: ${error.message}`);
      issues.push({ type: 'FATAL_ERROR', endpoint: endpoint.path, error: error.message });
    }
  }

  console.log('\n============================================');
  console.log(`📊 EXHAUSTIVE TEST RESULTS`);
  console.log(`✅ Passed: ${passed}/${allEndpoints.length} (${Math.round(passed/allEndpoints.length*100)}%)`);
  console.log(`❌ Failed: ${failed}/${allEndpoints.length}`);
  console.log(`🚨 Server Errors (5xx): ${serverErrors}`);
  console.log(`📭 Empty Data Issues: ${emptyData}`);
  console.log('============================================\n');

  if (issues.length > 0) {
    console.log('🔧 ISSUES TO FIX:');
    issues.forEach((issue, i) => {
      console.log(`${i+1}. [${issue.type}] ${issue.endpoint}`);
      if (issue.status) console.log(`   Status: ${issue.status}`);
      if (issue.error) console.log(`   Error: ${issue.error}`);
      if (issue.description) console.log(`   Description: ${issue.description}`);
      console.log('');
    });
  }

  // Save results to file
  const resultSummary = {
    timestamp: new Date().toISOString(),
    totalEndpoints: allEndpoints.length,
    passed,
    failed,
    serverErrors,
    emptyData,
    passRate: Math.round(passed/allEndpoints.length*100),
    issues
  };

  require('fs').writeFileSync('exhaustive_test_results.json', JSON.stringify(resultSummary, null, 2));
  console.log('💾 Results saved to exhaustive_test_results.json');

  process.exit(0);
}

function makeRequest(endpoint) {
  return new Promise((resolve) => {
    const options = {
      hostname: 'localhost',
      port: 3001,
      path: endpoint.path,
      method: endpoint.method,
      headers: endpoint.headers || {}
    };

    const req = http.request(options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        resolve({
          success: res.statusCode >= 200 && res.statusCode < 400,
          statusCode: res.statusCode,
          data: data.substring(0, 500), // First 500 chars for analysis
          endpoint: endpoint.path,
          error: res.statusCode >= 400 ? data : null
        });
      });
    });

    req.on('error', (error) => {
      resolve({
        success: false,
        statusCode: 'ERROR',
        error: error.message,
        endpoint: endpoint.path
      });
    });

    if (endpoint.data) {
      req.write(endpoint.data);
    }

    req.end();
  });
}

testAPI().catch(console.error);
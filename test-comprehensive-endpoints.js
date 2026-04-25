const http = require('http');

const endpoints = [
  // Health and Status
  { method: 'GET', path: '/health', name: 'Health Check' },
  { method: 'GET', path: '/api', name: 'API Index' },

  // Stocks
  { method: 'GET', path: '/api/stocks', name: 'Stocks List' },
  { method: 'GET', path: '/api/stocks/search?q=AAPL', name: 'Stock Search' },
  { method: 'GET', path: '/api/stocks/deep-value', name: 'Deep Value Stocks' },
  { method: 'GET', path: '/api/stocks/AAPL', name: 'Stock Details' },

  // Earnings
  { method: 'GET', path: '/api/earnings/data?symbol=AAPL', name: 'Earnings Data' },
  { method: 'GET', path: '/api/earnings/calendar', name: 'Earnings Calendar' },
  { method: 'GET', path: '/api/earnings/estimate-momentum', name: 'Estimate Momentum' },
  { method: 'GET', path: '/api/earnings/sp500-trend', name: 'S&P 500 Trend' },
  { method: 'GET', path: '/api/earnings/sector-trend', name: 'Sector Earnings Trend' },

  // Sectors
  { method: 'GET', path: '/api/sectors', name: 'All Sectors' },
  { method: 'GET', path: '/api/sectors/performance', name: 'Sector Performance' },
  { method: 'GET', path: '/api/sectors/rotation', name: 'Sector Rotation' },
  { method: 'GET', path: '/api/sectors/leaders', name: 'Sector Leaders' },

  // Market
  { method: 'GET', path: '/api/market/overview', name: 'Market Overview' },
  { method: 'GET', path: '/api/market/indices', name: 'Market Indices' },

  // Portfolio
  { method: 'GET', path: '/api/portfolio', name: 'Portfolio' },
  { method: 'GET', path: '/api/portfolio/performance', name: 'Portfolio Performance' },

  // Scores
  { method: 'GET', path: '/api/scores', name: 'Scores' },

  // Signals
  { method: 'GET', path: '/api/signals/etf', name: 'ETF Signals' },

  // Other
  { method: 'GET', path: '/api/sentiment', name: 'Sentiment' },
  { method: 'GET', path: '/api/economic/data', name: 'Economic Data' },
  { method: 'GET', path: '/api/industries', name: 'Industries' },
];

async function testEndpoint(method, path, name) {
  return new Promise((resolve) => {
    const options = {
      hostname: 'localhost',
      port: 3000,
      path,
      method,
      timeout: 8000
    };

    const req = http.request(options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        const status = res.statusCode;
        const statusEmoji = status === 200 ? '✓' : (status >= 500 ? '✗' : (status === 404 ? '?' : '⚠️'));
        const dataSize = data.length;
        console.log(`${statusEmoji} [${status}] ${name.padEnd(30)} (${dataSize} bytes)`);
        resolve({ status, name, dataSize });
      });
    });

    req.on('error', (err) => {
      console.log(`✗ [ERR] ${name.padEnd(30)} ${err.code || err.message.split('\n')[0]}`);
      resolve({ status: 0, name, error: err.message });
    });

    req.on('timeout', () => {
      req.destroy();
      console.log(`⏱ [TIMEOUT] ${name.padEnd(30)} (>8s)`);
      resolve({ status: 0, name, error: 'timeout' });
    });

    req.end();
  });
}

async function runTests() {
  console.log('🧪 COMPREHENSIVE API ENDPOINT TEST\n');
  console.log(`Starting at ${new Date().toLocaleTimeString()}\n`);

  const results = [];
  for (const endpoint of endpoints) {
    const result = await testEndpoint(endpoint.method, endpoint.path, endpoint.name);
    results.push(result);
    await new Promise(r => setTimeout(r, 150));
  }

  console.log('\n📊 TEST SUMMARY:');
  const working = results.filter(r => r.status === 200).length;
  const notFound = results.filter(r => r.status === 404).length;
  const errors = results.filter(r => r.status >= 500).length;
  const timeouts = results.filter(r => r.status === 0).length;
  const warnings = results.filter(r => r.status > 0 && r.status < 500 && r.status !== 200).length;

  console.log(`  ✓ Working (200): ${working}/${results.length}`);
  console.log(`  ? Not Found (404): ${notFound}`);
  console.log(`  ✗ Errors (5xx): ${errors}`);
  console.log(`  ⚠️  Warnings (other): ${warnings}`);
  console.log(`  ⏱ Timeouts/Connection: ${timeouts}`);

  if (errors > 0) {
    console.log(`\n❌ ${errors} endpoints have server errors - need fixes`);
  }
  if (notFound > 0) {
    console.log(`\n⚠️  ${notFound} endpoints return 404 - may need implementation`);
  }
  if (working === results.length) {
    console.log(`\n✅ ALL ENDPOINTS WORKING!`);
  }
}

runTests();

const http = require('http');

const endpoints = [
  { method: 'GET', path: '/health', name: 'Health Check' },
  { method: 'GET', path: '/api/stocks/deep-value', name: 'Deep Value Stocks' },
  { method: 'GET', path: '/api/earnings/data?symbol=AAPL', name: 'Earnings Data' },
  { method: 'GET', path: '/api/earnings/calendar', name: 'Earnings Calendar' },
  { method: 'GET', path: '/api/sectors/performance', name: 'Sector Performance' },
  { method: 'GET', path: '/api/sectors/ranking-history', name: 'Sector Ranking' },
  { method: 'GET', path: '/api/market/overview', name: 'Market Overview' },
  { method: 'GET', path: '/api/portfolio', name: 'Portfolio' },
  { method: 'GET', path: '/api/scores/overview', name: 'Scores Overview' },
  { method: 'GET', path: '/api/sentiment/overview', name: 'Sentiment' },
  { method: 'GET', path: '/api/economic/data', name: 'Economic Data' },
  { method: 'GET', path: '/api/analysts/summary', name: 'Analysts' },
  { method: 'GET', path: '/api/signals/etf', name: 'ETF Signals' },
  { method: 'GET', path: '/api/price/latest?symbol=AAPL', name: 'Price Latest' },
  { method: 'GET', path: '/api/financials/income?symbol=AAPL', name: 'Financials' },
  { method: 'GET', path: '/api/industries/overview', name: 'Industries' },
];

async function testEndpoint(method, path, name) {
  return new Promise((resolve) => {
    const options = {
      hostname: 'localhost',
      port: 3000,
      path,
      method,
      timeout: 5000
    };

    const req = http.request(options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        const status = res.statusCode;
        const statusEmoji = status === 200 ? '✓' : (status >= 500 ? '✗' : '⚠️');
        const dataSize = data.length;
        const isJson = res.headers['content-type']?.includes('json');
        console.log(`${statusEmoji} [${status}] ${name.padEnd(25)} (${dataSize} bytes)`);
        resolve({ status, name, dataSize });
      });
    });

    req.on('error', (err) => {
      console.log(`✗ [ERR] ${name.padEnd(25)} ${err.message.split('\n')[0]}`);
      resolve({ status: 0, name, error: err.message });
    });

    req.on('timeout', () => {
      req.destroy();
      console.log(`⏱ [TIMEOUT] ${name.padEnd(25)}`);
      resolve({ status: 0, name, error: 'timeout' });
    });

    req.end();
  });
}

async function runTests() {
  console.log('🧪 Testing All API Endpoints\n');
  console.log(`Starting tests at ${new Date().toLocaleTimeString()}\n`);

  const results = [];
  for (const endpoint of endpoints) {
    const result = await testEndpoint(endpoint.method, endpoint.path, endpoint.name);
    results.push(result);
    await new Promise(r => setTimeout(r, 200)); // 200ms delay between requests
  }

  console.log('\n📊 SUMMARY:');
  const working = results.filter(r => r.status === 200).length;
  const errors = results.filter(r => r.status >= 500).length;
  const warnings = results.filter(r => r.status > 0 && r.status < 500 && r.status !== 200).length;

  console.log(`  ✓ Working: ${working}/${results.length}`);
  console.log(`  ✗ Errors (5xx): ${errors}`);
  console.log(`  ⚠️  Warnings (non-200): ${warnings}`);
  console.log(`  ⏱ Timeouts/Failures: ${results.filter(r => r.status === 0).length}`);
}

runTests();

const http = require('http');

const endpoints = [
  '/api/algo/markets',
  '/api/market/sentiment?range=30d',
  '/api/market/top-movers',
  '/api/market/technicals',
  '/api/market/seasonality',
];

async function testEndpoint(path) {
  return new Promise((resolve) => {
    const req = http.request({
      hostname: 'localhost',
      port: 3001,
      path: path,
      method: 'GET'
    }, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        const status = res.statusCode;
        const ok = status < 400;
        resolve({
          endpoint: path,
          status: status,
          ok: ok
        });
      });
    });
    req.on('error', () => resolve({ endpoint: path, status: 'ERROR', ok: false }));
    req.setTimeout(3000, () => req.destroy());
    req.end();
  });
}

(async () => {
  console.log('Testing MarketsHealth Page APIs...\n');
  for (const endpoint of endpoints) {
    const result = await testEndpoint(endpoint);
    const icon = result.ok ? '✓' : '✗';
    console.log(`${icon} ${endpoint.padEnd(40)} - ${result.status}`);
  }
})();

const http = require('http');

const endpoints = [
  '/api/markets',
  '/api/markets/health',
  '/api/health',
  '/api/market/indicators',
  '/api/stocks/leading-indicators',
  '/api/leading-indicators',
  '/api/economic/leading-indicators',
  '/api/calendar',
  '/api/trades',
  '/api/positions',
  '/api/sentiment',
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
          ok: ok,
          hasData: data.length > 10
        });
      });
    });
    req.on('error', () => resolve({ endpoint: path, status: 'ERROR', ok: false }));
    req.setTimeout(3000, () => req.destroy());
    req.end();
  });
}

(async () => {
  console.log('Testing Additional Endpoints...\n');
  for (const endpoint of endpoints) {
    const result = await testEndpoint(endpoint);
    const icon = result.ok ? '✓' : '✗';
    console.log(`${icon} ${endpoint.padEnd(35)} - ${result.status}`);
  }
})();

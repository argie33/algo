const http = require('http');

const endpoints = [
  '/api/market/health',
  '/api/sectors',
  '/api/stocks/deep-value',
  '/api/signals',
  '/api/portfolio',
  '/api/economic',
];

async function testEndpoint(path) {
  return new Promise((resolve) => {
    const options = {
      hostname: 'localhost',
      port: 3001,
      path: path,
      method: 'GET',
      headers: {
        'Content-Type': 'application/json'
      }
    };

    const req = http.request(options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        let response;
        try {
          response = JSON.parse(data);
        } catch {
          response = { error: 'Invalid JSON', raw: data.substring(0, 200) };
        }
        resolve({
          endpoint: path,
          status: res.statusCode,
          contentType: res.headers['content-type'],
          error: res.statusCode >= 400,
          dataKeys: response && typeof response === 'object' ? Object.keys(response) : [],
          response: response
        });
      });
    });

    req.on('error', (e) => {
      resolve({
        endpoint: path,
        error: true,
        status: 0,
        message: e.message
      });
    });

    req.setTimeout(5000, () => {
      req.destroy();
      resolve({
        endpoint: path,
        error: true,
        status: 0,
        message: 'Timeout'
      });
    });

    req.end();
  });
}

(async () => {
  console.log('Testing API Endpoints...\n');
  for (const endpoint of endpoints) {
    const result = await testEndpoint(endpoint);
    console.log(`${result.status === 200 ? '✓' : '✗'} ${result.endpoint}`);
    console.log(`  Status: ${result.status}`);
    if (result.error) {
      console.log(`  ERROR: ${result.message || 'Unknown error'}`);
    } else {
      console.log(`  Keys: ${result.dataKeys.join(', ').substring(0, 60)}`);
      if (result.response.error || result.response.message) {
        console.log(`  Response Error: ${result.response.error || result.response.message}`);
      }
    }
    console.log();
  }
})();

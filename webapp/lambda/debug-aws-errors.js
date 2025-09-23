
// Quick diagnostic to test AWS endpoint errors

const https = require('https');

const BASE_URL = 'https://qda42av7je.execute-api.us-east-1.amazonaws.com/dev';

// Test a few key endpoints to get detailed error messages
const testEndpoints = [
  '/api/sectors',
  '/api/market',
  '/api/user',
  '/api/stocks',
  '/api/technical'
];

async function testEndpoint(endpoint) {
  return new Promise((resolve) => {
    const options = {
      hostname: 'qda42av7je.execute-api.us-east-1.amazonaws.com',
      port: 443,
      path: `/dev${endpoint}`,
      method: 'GET',
      timeout: 10000
    };

    const req = https.request(options, (res) => {
      let data = '';

      res.on('data', (chunk) => {
        data += chunk;
      });

      res.on('end', () => {
        try {
          const parsed = JSON.parse(data);
          resolve({
            endpoint,
            status: res.statusCode,
            success: parsed.success || false,
            error: parsed.error || null,
            details: parsed.details || null,
            message: parsed.message || null
          });
        } catch (e) {
          resolve({
            endpoint,
            status: res.statusCode,
            success: false,
            error: 'Parse error',
            details: data.slice(0, 200)
          });
        }
      });
    });

    req.on('error', (e) => {
      resolve({
        endpoint,
        status: 'ERROR',
        success: false,
        error: e.message,
        details: null
      });
    });

    req.on('timeout', () => {
      resolve({
        endpoint,
        status: 'TIMEOUT',
        success: false,
        error: 'Request timeout',
        details: null
      });
    });

    req.end();
  });
}

async function diagnoseAWSErrors() {
  console.log('🔍 AWS ERROR DIAGNOSTIC');
  console.log('=======================');

  const results = await Promise.all(
    testEndpoints.map(endpoint => testEndpoint(endpoint))
  );

  results.forEach(result => {
    console.log(`\n📍 ${result.endpoint}`);
    console.log(`   Status: ${result.status}`);
    console.log(`   Success: ${result.success}`);

    if (result.error) {
      console.log(`   Error: ${result.error}`);
    }

    if (result.details) {
      console.log(`   Details: ${result.details}`);
    }

    if (result.message) {
      console.log(`   Message: ${result.message}`);
    }
  });

  const errors = results.filter(r => !r.success);
  console.log(`\n📊 Summary: ${errors.length}/${results.length} endpoints have errors`);
}

if (require.main === module) {
  diagnoseAWSErrors().catch(console.error);
}

module.exports = { diagnoseAWSErrors };
// Try to find the correct AWS endpoint
require('dotenv').config();

const https = require('https');

// Possible AWS endpoints to try
const possibleEndpoints = [
  'https://algo-n2k5puvbra-uc.a.run.app',
  'https://api.algo-trading.com',
  'https://lambda.us-east-1.amazonaws.com',
  // Add more possibilities based on common patterns
];

async function testEndpoint(baseUrl) {
  return new Promise((resolve) => {
    const url = new URL('/api/health', baseUrl);

    const req = https.get(url, {
      timeout: 5000,
      headers: {
        'User-Agent': 'AWS-Health-Check'
      }
    }, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        resolve({
          baseUrl,
          status: res.statusCode,
          working: res.statusCode >= 200 && res.statusCode < 400,
          responseSize: data.length
        });
      });
    });

    req.on('timeout', () => {
      req.destroy();
      resolve({ baseUrl, status: 'TIMEOUT', working: false });
    });

    req.on('error', (err) => {
      resolve({ baseUrl, status: `ERROR: ${err.message}`, working: false });
    });
  });
}

async function findWorkingEndpoint() {
  console.log('🔍 Testing possible AWS endpoints...\n');

  for (const endpoint of possibleEndpoints) {
    process.stdout.write(`Testing ${endpoint}... `);
    const result = await testEndpoint(endpoint);

    if (result.working) {
      console.log(`✅ ${result.status} (${result.responseSize} bytes)`);
      return endpoint;
    } else {
      console.log(`❌ ${result.status}`);
    }
  }

  console.log('\n❌ No working AWS endpoint found');
  return null;
}

// Also try to find endpoint from environment or files
function findEndpointFromConfig() {
  const envUrl = process.env.AWS_API_URL || process.env.API_URL || process.env.VITE_API_URL;
  if (envUrl && envUrl.startsWith('http')) {
    console.log(`Found endpoint in environment: ${envUrl}`);
    return envUrl;
  }

  // Check recent test results
  try {
    const testResults = require('./aws_test_results.json');
    if (testResults.baseUrl) {
      console.log(`Found endpoint in test results: ${testResults.baseUrl}`);
      return testResults.baseUrl;
    }
  } catch (e) {
    // File doesn't exist or invalid
  }

  return null;
}

async function main() {
  console.log('🔍 Looking for AWS deployment endpoint...\n');

  // First try to find from config
  const configEndpoint = findEndpointFromConfig();
  if (configEndpoint) {
    console.log(`Testing configured endpoint: ${configEndpoint}`);
    const result = await testEndpoint(configEndpoint);
    if (result.working) {
      console.log(`✅ Configured endpoint is working!`);
      return configEndpoint;
    } else {
      console.log(`❌ Configured endpoint not working: ${result.status}`);
    }
  }

  // Try to find working endpoint
  const workingEndpoint = await findWorkingEndpoint();

  if (workingEndpoint) {
    console.log(`\n✅ Found working AWS endpoint: ${workingEndpoint}`);
    console.log(`Use this endpoint for testing AWS APIs`);
  } else {
    console.log(`\n❌ No working AWS deployment found`);
    console.log(`Possible issues:`);
    console.log(`- AWS deployment is down`);
    console.log(`- AWS endpoint URL has changed`);
    console.log(`- AWS deployment has not been deployed yet`);
    console.log(`- Network connectivity issues`);
  }

  return workingEndpoint;
}

main().catch(console.error);
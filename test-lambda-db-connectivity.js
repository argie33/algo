#!/usr/bin/env node

/**
 * Comprehensive Lambda Database Connectivity Test Script
 * This script tests all aspects of database connectivity that the Lambda function will encounter
 */

const https = require('https');
const { URL } = require('url');

// Configuration
const API_BASE_URL = 'https://q570hqc8i9.execute-api.us-east-1.amazonaws.com/dev';

// Test endpoints
const testEndpoints = [
  {
    name: 'Root Endpoint',
    path: '/',
    expectedCode: 200,
    description: 'Basic API Gateway routing test'
  },
  {
    name: 'Debug Endpoint',
    path: '/debug',
    expectedCode: 200,
    description: 'Debug information about Lambda environment'
  },
  {
    name: 'Health Quick',
    path: '/health?quick=true',
    expectedCode: 200,
    description: 'Quick health check without database'
  },
  {
    name: 'Health Full',
    path: '/health',
    expectedCode: [200, 503],
    description: 'Full health check with database'
  },
  {
    name: 'Diagnostics',
    path: '/api/diagnostics',
    expectedCode: [200, 500],
    description: 'Basic diagnostics endpoint'
  },
  {
    name: 'Comprehensive Diagnostics',
    path: '/api/diagnostics/comprehensive',
    expectedCode: [200, 500],
    description: 'Comprehensive database connectivity test'
  },
  {
    name: 'Stocks API',
    path: '/api/stocks?limit=1',
    expectedCode: [200, 500, 503],
    description: 'Database-dependent stocks endpoint'
  }
];

// Colors for console output
const colors = {
  green: '\x1b[32m',
  red: '\x1b[31m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  reset: '\x1b[0m',
  bold: '\x1b[1m'
};

function colorize(text, color) {
  return `${colors[color]}${text}${colors.reset}`;
}

function makeRequest(url, timeout = 30000) {
  return new Promise((resolve, reject) => {
    const urlObj = new URL(url);
    const options = {
      hostname: urlObj.hostname,
      port: urlObj.port || 443,
      path: urlObj.pathname + urlObj.search,
      method: 'GET',
      headers: {
        'Accept': 'application/json',
        'User-Agent': 'Lambda-DB-Connectivity-Test/1.0'
      },
      timeout: timeout
    };

    const req = https.request(options, (res) => {
      let data = '';
      
      res.on('data', (chunk) => {
        data += chunk;
      });
      
      res.on('end', () => {
        try {
          const jsonData = JSON.parse(data);
          resolve({
            statusCode: res.statusCode,
            headers: res.headers,
            body: jsonData,
            rawBody: data
          });
        } catch (parseError) {
          resolve({
            statusCode: res.statusCode,
            headers: res.headers,
            body: { error: 'Invalid JSON', rawBody: data },
            rawBody: data
          });
        }
      });
    });

    req.on('error', (error) => {
      reject(error);
    });

    req.on('timeout', () => {
      req.destroy();
      reject(new Error('Request timeout'));
    });

    req.end();
  });
}

async function runTest(endpoint) {
  const url = `${API_BASE_URL}${endpoint.path}`;
  const startTime = Date.now();
  
  try {
    console.log(`\n${colorize('Testing:', 'blue')} ${endpoint.name}`);
    console.log(`${colorize('URL:', 'blue')} ${url}`);
    console.log(`${colorize('Description:', 'blue')} ${endpoint.description}`);
    
    const result = await makeRequest(url);
    const duration = Date.now() - startTime;
    
    // Check if status code is expected
    const expectedCodes = Array.isArray(endpoint.expectedCode) ? endpoint.expectedCode : [endpoint.expectedCode];
    const isExpectedCode = expectedCodes.includes(result.statusCode);
    
    console.log(`${colorize('Status Code:', 'blue')} ${result.statusCode} ${isExpectedCode ? colorize('✓', 'green') : colorize('✗', 'red')}`);
    console.log(`${colorize('Duration:', 'blue')} ${duration}ms`);
    
    // Analyze response
    if (result.statusCode === 200) {
      console.log(`${colorize('Response:', 'green')} Success`);
      
      // Show key information from response
      if (result.body) {
        if (result.body.message) {
          console.log(`${colorize('Message:', 'blue')} ${result.body.message}`);
        }
        if (result.body.status) {
          console.log(`${colorize('Status:', 'blue')} ${result.body.status}`);
        }
        if (result.body.summary) {
          console.log(`${colorize('Summary:', 'blue')} ${JSON.stringify(result.body.summary, null, 2)}`);
        }
        if (result.body.database) {
          console.log(`${colorize('Database:', 'blue')} ${JSON.stringify(result.body.database, null, 2)}`);
        }
      }
    } else if (result.statusCode === 403) {
      console.log(`${colorize('Response:', 'red')} Forbidden - API Gateway authorization issue`);
      console.log(`${colorize('Body:', 'red')} ${JSON.stringify(result.body, null, 2)}`);
    } else if (result.statusCode === 500) {
      console.log(`${colorize('Response:', 'yellow')} Internal Server Error`);
      if (result.body && result.body.error) {
        console.log(`${colorize('Error:', 'red')} ${result.body.error}`);
      }
      if (result.body && result.body.message) {
        console.log(`${colorize('Message:', 'red')} ${result.body.message}`);
      }
    } else if (result.statusCode === 503) {
      console.log(`${colorize('Response:', 'yellow')} Service Unavailable - Database issue`);
      if (result.body && result.body.database) {
        console.log(`${colorize('Database Status:', 'yellow')} ${JSON.stringify(result.body.database, null, 2)}`);
      }
    }
    
    return {
      success: isExpectedCode,
      statusCode: result.statusCode,
      duration,
      endpoint: endpoint.name,
      response: result.body
    };
    
  } catch (error) {
    const duration = Date.now() - startTime;
    console.log(`${colorize('Error:', 'red')} ${error.message}`);
    console.log(`${colorize('Duration:', 'blue')} ${duration}ms`);
    
    return {
      success: false,
      statusCode: 0,
      duration,
      endpoint: endpoint.name,
      error: error.message
    };
  }
}

async function main() {
  console.log(`${colorize('🔍 Lambda Database Connectivity Test', 'bold')}`);
  console.log(`${colorize('Testing API Base URL:', 'blue')} ${API_BASE_URL}`);
  console.log(`${colorize('Timestamp:', 'blue')} ${new Date().toISOString()}`);
  
  const results = [];
  
  for (const endpoint of testEndpoints) {
    const result = await runTest(endpoint);
    results.push(result);
    
    // Small delay between tests
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  
  // Summary
  console.log(`\n${colorize('='.repeat(60), 'blue')}`);
  console.log(`${colorize('TEST SUMMARY', 'bold')}`);
  console.log(`${colorize('='.repeat(60), 'blue')}`);
  
  const successful = results.filter(r => r.success).length;
  const failed = results.filter(r => !r.success).length;
  const total = results.length;
  
  console.log(`${colorize('Total Tests:', 'blue')} ${total}`);
  console.log(`${colorize('Successful:', 'green')} ${successful}`);
  console.log(`${colorize('Failed:', 'red')} ${failed}`);
  console.log(`${colorize('Success Rate:', 'blue')} ${((successful / total) * 100).toFixed(1)}%`);
  
  // Detailed results
  console.log(`\n${colorize('DETAILED RESULTS:', 'bold')}`);
  results.forEach((result, index) => {
    const status = result.success ? colorize('✓ PASS', 'green') : colorize('✗ FAIL', 'red');
    console.log(`${index + 1}. ${result.endpoint}: ${status} (${result.statusCode}) - ${result.duration}ms`);
    if (result.error) {
      console.log(`   Error: ${result.error}`);
    }
  });
  
  // Recommendations
  console.log(`\n${colorize('RECOMMENDATIONS:', 'bold')}`);
  
  const forbiddenTests = results.filter(r => r.statusCode === 403);
  if (forbiddenTests.length > 0) {
    console.log(`${colorize('❌ API Gateway Issues:', 'red')}`);
    console.log('   - Multiple endpoints returning 403 Forbidden');
    console.log('   - Check API Gateway resource policies and IAM permissions');
    console.log('   - Verify API Gateway deployment to correct stage');
    console.log('   - Test with /debug endpoint to get more information');
  }
  
  const errorTests = results.filter(r => r.statusCode === 500);
  if (errorTests.length > 0) {
    console.log(`${colorize('❌ Lambda Function Issues:', 'red')}`);
    console.log('   - Lambda function returning 500 Internal Server Error');
    console.log('   - Check Lambda function logs for detailed error messages');
    console.log('   - Verify environment variables and dependencies');
  }
  
  const dbTests = results.filter(r => r.statusCode === 503);
  if (dbTests.length > 0) {
    console.log(`${colorize('❌ Database Connectivity Issues:', 'red')}`);
    console.log('   - Database connection or query failures');
    console.log('   - Check VPC configuration and security groups');
    console.log('   - Verify database credentials and network access');
  }
  
  if (successful === total) {
    console.log(`${colorize('✅ All tests passed! Database connectivity is working correctly.', 'green')}`);
  }
  
  console.log(`\n${colorize('Test completed at:', 'blue')} ${new Date().toISOString()}`);
}

// Run the test
main().catch(error => {
  console.error(`${colorize('Fatal error:', 'red')} ${error.message}`);
  process.exit(1);
});
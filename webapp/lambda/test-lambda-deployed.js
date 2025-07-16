#!/usr/bin/env node
/**
 * Test Deployed Lambda Health
 * Tests the actual deployed Lambda endpoints to verify deployment success
 */

const https = require('https');
const http = require('http');

// Test configuration
const tests = [
  {
    name: 'Lambda Root Health',
    path: '/',
    expectedData: ['success', 'Financial Dashboard API']
  },
  {
    name: 'Development Health',
    path: '/dev-health', 
    expectedData: ['dev_status', 'OPERATIONAL', 'route_loading']
  },
  {
    name: 'API Health Check',
    path: '/api/health',
    expectedData: ['success', 'environment']
  },
  {
    name: 'Full Health Check', 
    path: '/api/health-full',
    expectedData: ['success', 'database']
  }
];

// Get API URL from various sources
function getApiUrl() {
  // Try environment variable first
  if (process.env.LAMBDA_API_URL) {
    return process.env.LAMBDA_API_URL;
  }
  
  // Try to read from frontend config (if available)
  try {
    const configPath = '../frontend/public/config.js';
    const fs = require('fs');
    if (fs.existsSync(configPath)) {
      const configContent = fs.readFileSync(configPath, 'utf8');
      const match = configContent.match(/API_URL:\s*['"]([^'"]+)['"]/);
      if (match) {
        return match[1];
      }
    }
  } catch (e) {
    // Ignore file reading errors
  }
  
  // Default fallback for development
  return 'https://your-api-gateway-url.execute-api.us-east-1.amazonaws.com/dev';
}

// Make HTTP request
function makeRequest(url, path) {
  return new Promise((resolve, reject) => {
    const fullUrl = url + path;
    const isHttps = fullUrl.startsWith('https');
    const client = isHttps ? https : http;
    
    console.log(`🔍 Testing: ${fullUrl}`);
    
    const req = client.get(fullUrl, (res) => {
      let data = '';
      
      res.on('data', (chunk) => {
        data += chunk;
      });
      
      res.on('end', () => {
        try {
          const parsedData = JSON.parse(data);
          resolve({
            statusCode: res.statusCode,
            headers: res.headers,
            data: parsedData
          });
        } catch (e) {
          resolve({
            statusCode: res.statusCode,
            headers: res.headers,
            data: data,
            parseError: e.message
          });
        }
      });
    });
    
    req.on('error', (err) => {
      reject(err);
    });
    
    req.setTimeout(10000, () => {
      req.destroy();
      reject(new Error('Request timeout'));
    });
  });
}

// Run tests
async function runTests() {
  const apiUrl = getApiUrl();
  console.log('🚀 Testing Deployed Lambda Health');
  console.log(`📡 API URL: ${apiUrl}`);
  console.log('='.repeat(50));
  
  const results = [];
  
  for (const test of tests) {
    try {
      console.log(`\n🧪 ${test.name}`);
      
      const result = await makeRequest(apiUrl, test.path);
      
      // Check status code
      const statusOk = result.statusCode >= 200 && result.statusCode < 300;
      console.log(`   Status: ${result.statusCode} ${statusOk ? '✅' : '❌'}`);
      
      // Check expected data presence
      let dataOk = true;
      if (test.expectedData && typeof result.data === 'object') {
        for (const expected of test.expectedData) {
          const hasData = JSON.stringify(result.data).includes(expected);
          console.log(`   Contains "${expected}": ${hasData ? '✅' : '❌'}`);
          if (!hasData) dataOk = false;
        }
      }
      
      // Show key response data
      if (result.data && typeof result.data === 'object') {
        if (result.data.success !== undefined) {
          console.log(`   Success: ${result.data.success ? '✅' : '❌'}`);
        }
        if (result.data.message) {
          console.log(`   Message: ${result.data.message}`);
        }
        if (result.data.dev_status) {
          console.log(`   Dev Status: ${result.data.dev_status}`);
        }
        if (result.data.route_loading) {
          console.log(`   Routes Loaded: ${result.data.route_loading.all_routes_loaded ? '✅' : '❌'}`);
        }
        if (result.data.missing_critical_vars) {
          console.log(`   Missing Vars: ${result.data.missing_critical_vars.length > 0 ? result.data.missing_critical_vars.join(', ') : 'None'}`);
        }
      }
      
      results.push({
        test: test.name,
        success: statusOk && dataOk,
        statusCode: result.statusCode,
        data: result.data
      });
      
    } catch (error) {
      console.log(`   Error: ❌ ${error.message}`);
      results.push({
        test: test.name,
        success: false,
        error: error.message
      });
    }
  }
  
  // Summary
  console.log('\n' + '='.repeat(50));
  console.log('📊 Test Summary');
  console.log('='.repeat(50));
  
  const passed = results.filter(r => r.success).length;
  const total = results.length;
  
  console.log(`✅ Passed: ${passed}/${total}`);
  console.log(`❌ Failed: ${total - passed}/${total}`);
  
  if (passed === total) {
    console.log('\n🎉 All tests passed! Lambda deployment successful.');
  } else {
    console.log('\n⚠️ Some tests failed. Check Lambda deployment and configuration.');
  }
  
  return results;
}

// Export for use as module or run directly
if (require.main === module) {
  runTests().catch(console.error);
}

module.exports = { runTests, getApiUrl };
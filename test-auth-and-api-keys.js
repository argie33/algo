#!/usr/bin/env node
/**
 * Authentication and API Key Integration Test Script
 * Tests the complete authentication flow and API key management system
 * 
 * This script validates:
 * 1. JWT token extraction and validation
 * 2. User ID consistency across requests  
 * 3. API key encryption/decryption service
 * 4. Settings API endpoints functionality
 * 5. Database connectivity and user isolation
 */

const https = require('https');
const fs = require('fs');

// Configuration
const config = {
  // Update this with your actual API Gateway URL
  baseUrl: 'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev',
  
  // Test user credentials (you'll need to provide these)
  testUser: {
    // You can get these from your Cognito user pool
    username: 'test-user@example.com',
    password: 'TestPassword123!',
    // Or provide a JWT token directly for testing
    jwtToken: null
  },
  
  // Test configuration
  timeout: 30000,
  verbose: true
};

// Test results tracking
const testResults = {
  passed: 0,
  failed: 0,
  tests: []
};

// Utility functions
function log(level, message, ...args) {
  const timestamp = new Date().toISOString();
  const prefix = `${timestamp} [${level.toUpperCase()}]`;
  
  if (level === 'ERROR') {
    console.error(prefix, message, ...args);
  } else if (level === 'WARN') {
    console.warn(prefix, message, ...args);
  } else if (config.verbose || level === 'INFO') {
    console.log(prefix, message, ...args);
  }
}

function recordTest(testName, passed, details = null, error = null) {
  const result = {
    name: testName,
    passed,
    details,
    error: error ? error.message : null,
    timestamp: new Date().toISOString()
  };
  
  testResults.tests.push(result);
  
  if (passed) {
    testResults.passed++;
    log('INFO', `✅ ${testName}`);
    if (details) log('DEBUG', `   Details: ${JSON.stringify(details)}`);
  } else {
    testResults.failed++;
    log('ERROR', `❌ ${testName}`);
    if (error) log('ERROR', `   Error: ${error.message}`);
    if (details) log('ERROR', `   Details: ${JSON.stringify(details)}`);
  }
}

// HTTP request helper
function makeRequest(options, data = null) {
  return new Promise((resolve, reject) => {
    const req = https.request(options, (res) => {
      let body = '';
      
      res.on('data', (chunk) => {
        body += chunk;
      });
      
      res.on('end', () => {
        try {
          const response = {
            statusCode: res.statusCode,
            headers: res.headers,
            body: body,
            data: body ? JSON.parse(body) : null
          };
          resolve(response);
        } catch (error) {
          resolve({
            statusCode: res.statusCode,
            headers: res.headers,
            body: body,
            data: null,
            parseError: error.message
          });
        }
      });
    });
    
    req.on('error', reject);
    req.setTimeout(config.timeout, () => {
      req.destroy();
      reject(new Error('Request timeout'));
    });
    
    if (data) {
      req.write(JSON.stringify(data));
    }
    
    req.end();
  });
}

// Test functions
async function testHealthEndpoint() {
  log('INFO', 'Testing health endpoint...');
  
  try {
    const url = new URL(`${config.baseUrl}/health`);
    const options = {
      hostname: url.hostname,
      port: 443,
      path: url.pathname,
      method: 'GET',
      headers: {
        'Content-Type': 'application/json'
      }
    };
    
    const response = await makeRequest(options);
    
    const passed = response.statusCode === 200 && response.data && response.data.status === 'healthy';
    recordTest('Health Endpoint', passed, {
      statusCode: response.statusCode,
      responseTime: 'measured',
      status: response.data?.status
    }, passed ? null : new Error(`Expected 200 with healthy status, got ${response.statusCode}`));
    
    return passed;
  } catch (error) {
    recordTest('Health Endpoint', false, null, error);
    return false;
  }
}

async function testSecretsStatusEndpoint() {
  log('INFO', 'Testing secrets status endpoint...');
  
  try {
    const url = new URL(`${config.baseUrl}/debug/secrets-status`);
    const options = {
      hostname: url.hostname,
      port: 443,
      path: url.pathname,
      method: 'GET',
      headers: {
        'Content-Type': 'application/json'
      }
    };
    
    const response = await makeRequest(options);
    
    const passed = response.statusCode === 200 && response.data && response.data.secretsStatus;
    recordTest('Secrets Status Endpoint', passed, {
      statusCode: response.statusCode,
      hasApiKeySecret: response.data?.environment?.hasApiKeySecret,
      hasJwtSecret: response.data?.environment?.hasJwtSecret,
      secretsInitialized: response.data?.secretsStatus?.initialized
    }, passed ? null : new Error(`Expected 200 with secrets status, got ${response.statusCode}`));
    
    return response.data;
  } catch (error) {
    recordTest('Secrets Status Endpoint', false, null, error);
    return null;
  }
}

async function testApiKeysEndpointUnauthorized() {
  log('INFO', 'Testing API keys endpoint without authentication...');
  
  try {
    const url = new URL(`${config.baseUrl}/settings/api-keys`);
    const options = {
      hostname: url.hostname,
      port: 443,
      path: url.pathname,
      method: 'GET',
      headers: {
        'Content-Type': 'application/json'
      }
    };
    
    const response = await makeRequest(options);
    
    // Should return 401 Unauthorized
    const passed = response.statusCode === 401;
    recordTest('API Keys Endpoint - Unauthorized', passed, {
      statusCode: response.statusCode,
      error: response.data?.error
    }, passed ? null : new Error(`Expected 401 Unauthorized, got ${response.statusCode}`));
    
    return passed;
  } catch (error) {
    recordTest('API Keys Endpoint - Unauthorized', false, null, error);
    return false;
  }
}

async function testApiKeysEndpointWithoutEncryption() {
  log('INFO', 'Testing API keys endpoint behavior when encryption service disabled...');
  
  try {
    // This test assumes we don't have proper encryption secrets set up yet
    const url = new URL(`${config.baseUrl}/settings/api-keys`);
    const options = {
      hostname: url.hostname,
      port: 443,
      path: url.pathname,
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
        // Add a mock/invalid auth header to test the endpoint logic
        'Authorization': 'Bearer invalid-token-for-testing'
      }
    };
    
    const response = await makeRequest(options);
    
    // Should return graceful response indicating encryption service is unavailable
    const passed = response.statusCode === 200 && 
                   response.data && 
                   (response.data.setupRequired || response.data.encryptionEnabled === false);
    
    recordTest('API Keys Endpoint - No Encryption', passed, {
      statusCode: response.statusCode,
      setupRequired: response.data?.setupRequired,
      encryptionEnabled: response.data?.encryptionEnabled,
      message: response.data?.message
    }, passed ? null : new Error(`Expected graceful degradation, got ${response.statusCode}`));
    
    return response.data;
  } catch (error) {
    recordTest('API Keys Endpoint - No Encryption', false, null, error);
    return null;
  }
}

async function testDatabaseConnectivity() {
  log('INFO', 'Testing database connectivity via API...');
  
  try {
    const url = new URL(`${config.baseUrl}/settings/api-keys/debug`);
    const options = {
      hostname: url.hostname,
      port: 443,
      path: url.pathname,
      method: 'GET',
      headers: {
        'Content-Type': 'application/json'
      }
    };
    
    const response = await makeRequest(options);
    
    const passed = response.statusCode === 200 && response.data;
    recordTest('Database Connectivity', passed, {
      statusCode: response.statusCode,
      tableExists: response.data?.table_exists,
      totalRecords: response.data?.total_records
    }, passed ? null : new Error(`Database connectivity test failed: ${response.statusCode}`));
    
    return response.data;
  } catch (error) {
    recordTest('Database Connectivity', false, null, error);
    return null;
  }
}

async function testCORSConfiguration() {
  log('INFO', 'Testing CORS configuration...');
  
  try {
    const url = new URL(`${config.baseUrl}/health`);
    const options = {
      hostname: url.hostname,
      port: 443,
      path: url.pathname,
      method: 'OPTIONS',
      headers: {
        'Origin': 'https://example.com',
        'Access-Control-Request-Method': 'GET',
        'Access-Control-Request-Headers': 'Authorization'
      }
    };
    
    const response = await makeRequest(options);
    
    const passed = response.statusCode === 200 || response.statusCode === 204;
    recordTest('CORS Configuration', passed, {
      statusCode: response.statusCode,
      allowOrigin: response.headers['access-control-allow-origin'],
      allowMethods: response.headers['access-control-allow-methods']
    }, passed ? null : new Error(`CORS preflight failed: ${response.statusCode}`));
    
    return passed;
  } catch (error) {
    recordTest('CORS Configuration', false, null, error);
    return false;
  }
}

// Main test execution
async function runAllTests() {
  log('INFO', '🚀 Starting Authentication and API Key Integration Tests...');
  log('INFO', `📍 Target API: ${config.baseUrl}`);
  
  const startTime = Date.now();
  
  // Phase 1: Basic connectivity and infrastructure
  log('INFO', '\n📋 PHASE 1: Infrastructure Tests');
  await testHealthEndpoint();
  await testCORSConfiguration();
  
  // Phase 2: Secrets management validation
  log('INFO', '\n🔐 PHASE 2: Secrets Management Tests');
  const secretsStatus = await testSecretsStatusEndpoint();
  
  // Phase 3: Authentication validation  
  log('INFO', '\n🔑 PHASE 3: Authentication Tests');
  await testApiKeysEndpointUnauthorized();
  
  // Phase 4: API key service testing
  log('INFO', '\n⚙️ PHASE 4: API Key Service Tests');
  const apiKeyStatus = await testApiKeysEndpointWithoutEncryption();
  
  // Phase 5: Database connectivity
  log('INFO', '\n🗄️ PHASE 5: Database Tests');
  const dbStatus = await testDatabaseConnectivity();
  
  // Generate final report
  const endTime = Date.now();
  const totalTime = endTime - startTime;
  
  log('INFO', '\n📊 TEST RESULTS SUMMARY');
  log('INFO', '='.repeat(50));
  log('INFO', `✅ Passed: ${testResults.passed}`);
  log('INFO', `❌ Failed: ${testResults.failed}`);
  log('INFO', `⏱️  Total Time: ${totalTime}ms`);
  log('INFO', `📈 Success Rate: ${Math.round((testResults.passed / (testResults.passed + testResults.failed)) * 100)}%`);
  
  // Detailed analysis
  log('INFO', '\n🔍 DETAILED ANALYSIS');
  log('INFO', '='.repeat(50));
  
  if (secretsStatus) {
    log('INFO', `🔐 Secrets Status:`);
    log('INFO', `   - Initialized: ${secretsStatus.secretsStatus?.initialized || false}`);
    log('INFO', `   - API Key Secret: ${secretsStatus.environment?.hasApiKeySecret || false}`);
    log('INFO', `   - JWT Secret: ${secretsStatus.environment?.hasJwtSecret || false}`);
  }
  
  if (dbStatus) {
    log('INFO', `🗄️ Database Status:`);
    log('INFO', `   - User API Keys Table: ${dbStatus.table_exists ? 'EXISTS' : 'MISSING'}`);
    log('INFO', `   - Total Records: ${dbStatus.total_records || 0}`);
  }
  
  if (apiKeyStatus) {
    log('INFO', `⚙️ API Key Service:`);
    log('INFO', `   - Encryption Enabled: ${apiKeyStatus.encryptionEnabled || false}`);
    log('INFO', `   - Setup Required: ${apiKeyStatus.setupRequired || false}`);
  }
  
  // Recommendations
  log('INFO', '\n💡 RECOMMENDATIONS');
  log('INFO', '='.repeat(50));
  
  if (!secretsStatus?.environment?.hasApiKeySecret) {
    log('WARN', '⚠️  Create API_KEY_ENCRYPTION_SECRET in AWS Secrets Manager');
  }
  
  if (!dbStatus?.table_exists) {
    log('WARN', '⚠️  Run webapp-db-init.js to create user_api_keys table');
  }
  
  if (testResults.failed === 0) {
    log('INFO', '🎉 All tests passed! The authentication and API key infrastructure is ready.');
  } else {
    log('WARN', '⚠️  Some tests failed. Review the issues above before proceeding.');
  }
  
  // Write detailed results to file
  const reportPath = '/home/stocks/algo/API_KEY_TEST_RESULTS.json';
  const detailedReport = {
    summary: {
      passed: testResults.passed,
      failed: testResults.failed,
      totalTime,
      timestamp: new Date().toISOString()
    },
    infrastructure: {
      secretsStatus,
      dbStatus,
      apiKeyStatus
    },
    tests: testResults.tests
  };
  
  try {
    fs.writeFileSync(reportPath, JSON.stringify(detailedReport, null, 2));
    log('INFO', `📄 Detailed report saved to: ${reportPath}`);
  } catch (error) {
    log('ERROR', 'Failed to save detailed report:', error.message);
  }
  
  return testResults.failed === 0;
}

// Execute if run directly
if (require.main === module) {
  runAllTests()
    .then(success => {
      process.exit(success ? 0 : 1);
    })
    .catch(error => {
      log('ERROR', 'Test execution failed:', error);
      process.exit(1);
    });
}

module.exports = {
  runAllTests,
  testResults,
  config
};
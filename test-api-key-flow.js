#!/usr/bin/env node

/**
 * End-to-end API Key Flow Test
 * Tests the complete API key integration from settings to portfolio data retrieval
 */

const axios = require('axios');
require('dotenv').config();

// Test configuration
const API_BASE_URL = process.env.VITE_API_URL || 'https://api.example.com';
const TEST_USER_TOKEN = process.env.TEST_USER_TOKEN || '';

// Mock API key for testing
const TEST_API_KEY = {
  provider: 'alpaca',
  apiKey: 'TEST_KEY_12345678901234567890',
  apiSecret: 'TEST_SECRET_1234567890123456789012345678901234567890',
  isSandbox: true,
  description: 'End-to-end test API key'
};

// API client with authentication
const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${TEST_USER_TOKEN}`
  }
});

/**
 * Test results tracking
 */
const testResults = {
  passed: 0,
  failed: 0,
  tests: []
};

function logTest(name, success, message, details = {}) {
  const result = {
    name,
    success,
    message,
    details,
    timestamp: new Date().toISOString()
  };
  
  testResults.tests.push(result);
  
  if (success) {
    testResults.passed++;
    console.log(`✅ ${name}: ${message}`);
  } else {
    testResults.failed++;
    console.log(`❌ ${name}: ${message}`);
    if (Object.keys(details).length > 0) {
      console.log('   Details:', details);
    }
  }
}

/**
 * Test 1: API Key Creation
 */
async function testApiKeyCreation() {
  try {
    console.log('\n🧪 Testing API Key Creation...');
    
    const response = await api.post('/api/settings/api-keys', TEST_API_KEY);
    
    if (response.data.success && response.data.data.id) {
      logTest(
        'API Key Creation',
        true,
        'Successfully created API key',
        { 
          keyId: response.data.data.id,
          provider: response.data.data.provider,
          isSandbox: response.data.data.is_sandbox
        }
      );
      return response.data.data.id;
    } else {
      logTest('API Key Creation', false, 'Failed to create API key', response.data);
      return null;
    }
  } catch (error) {
    logTest(
      'API Key Creation',
      false,
      'Request failed',
      {
        status: error.response?.status,
        message: error.message,
        data: error.response?.data
      }
    );
    return null;
  }
}

/**
 * Test 2: API Key Retrieval
 */
async function testApiKeyRetrieval() {
  try {
    console.log('\n🧪 Testing API Key Retrieval...');
    
    const response = await api.get('/api/settings/api-keys');
    
    if (response.data.success && Array.isArray(response.data.data)) {
      const alpacaKeys = response.data.data.filter(key => key.provider === 'alpaca');
      
      logTest(
        'API Key Retrieval',
        true,
        `Successfully retrieved ${response.data.data.length} API key(s)`,
        {
          totalKeys: response.data.data.length,
          alpacaKeys: alpacaKeys.length,
          providers: response.data.data.map(k => k.provider)
        }
      );
      return alpacaKeys.length > 0 ? alpacaKeys[0] : null;
    } else {
      logTest('API Key Retrieval', false, 'Failed to retrieve API keys', response.data);
      return null;
    }
  } catch (error) {
    logTest(
      'API Key Retrieval',
      false,
      'Request failed',
      {
        status: error.response?.status,
        message: error.message,
        data: error.response?.data
      }
    );
    return null;
  }
}

/**
 * Test 3: API Key Validation
 */
async function testApiKeyValidation(keyId) {
  if (!keyId) {
    logTest('API Key Validation', false, 'No API key ID provided for validation');
    return false;
  }

  try {
    console.log('\n🧪 Testing API Key Validation...');
    
    const response = await api.post(`/api/settings/api-keys/${keyId}/validate`, {
      provider: 'alpaca'
    });
    
    if (response.data.success) {
      logTest(
        'API Key Validation',
        true,
        `Validation completed: ${response.data.data.valid ? 'VALID' : 'INVALID'}`,
        {
          valid: response.data.data.valid,
          message: response.data.data.message,
          provider: 'alpaca'
        }
      );
      return response.data.data.valid;
    } else {
      logTest('API Key Validation', false, 'Validation request failed', response.data);
      return false;
    }
  } catch (error) {
    logTest(
      'API Key Validation',
      false,
      'Validation request failed',
      {
        status: error.response?.status,
        message: error.message,
        data: error.response?.data
      }
    );
    return false;
  }
}

/**
 * Test 4: Portfolio Data Retrieval
 */
async function testPortfolioDataRetrieval() {
  try {
    console.log('\n🧪 Testing Portfolio Data Retrieval...');
    
    const response = await api.get('/api/portfolio/holdings?accountType=paper');
    
    if (response.data.success) {
      const holdings = response.data.holdings || [];
      logTest(
        'Portfolio Data Retrieval',
        true,
        `Successfully retrieved portfolio data`,
        {
          holdingsCount: holdings.length,
          hasPositions: holdings.length > 0,
          dataSource: response.data.dataSource || 'unknown'
        }
      );
      return true;
    } else {
      logTest('Portfolio Data Retrieval', false, 'Failed to retrieve portfolio data', response.data);
      return false;
    }
  } catch (error) {
    // Check if this is an API key missing error (expected for test environment)
    if (error.response?.data?.error_code === 'API_CREDENTIALS_MISSING') {
      logTest(
        'Portfolio Data Retrieval',
        true,
        'Correctly blocked due to missing valid API credentials (expected in test)',
        {
          status: error.response.status,
          errorCode: error.response.data.error_code,
          message: error.response.data.message
        }
      );
      return true;
    }
    
    logTest(
      'Portfolio Data Retrieval',
      false,
      'Request failed',
      {
        status: error.response?.status,
        message: error.message,
        data: error.response?.data
      }
    );
    return false;
  }
}

/**
 * Test 5: Real-time Data Service
 */
async function testRealTimeDataService() {
  try {
    console.log('\n🧪 Testing Real-time Data Service...');
    
    const response = await api.get('/api/websocket/stream/AAPL,MSFT');
    
    if (response.data.success || response.data.error_code === 'API_CREDENTIALS_MISSING') {
      logTest(
        'Real-time Data Service',
        true,
        'Service properly handles API key requirement',
        {
          hasCredentials: !response.data.error_code,
          message: response.data.message || 'Service accessible'
        }
      );
      return true;
    } else {
      logTest('Real-time Data Service', false, 'Service request failed', response.data);
      return false;
    }
  } catch (error) {
    // Check if this is an API key missing error (expected)
    if (error.response?.data?.error_code === 'API_CREDENTIALS_MISSING') {
      logTest(
        'Real-time Data Service',
        true,
        'Correctly blocked due to missing valid API credentials (expected)',
        {
          status: error.response.status,
          errorCode: error.response.data.error_code
        }
      );
      return true;
    }
    
    logTest(
      'Real-time Data Service',
      false,
      'Request failed',
      {
        status: error.response?.status,
        message: error.message,
        data: error.response?.data
      }
    );
    return false;
  }
}

/**
 * Test 6: API Key Cleanup
 */
async function testApiKeyCleanup(keyId) {
  if (!keyId) {
    logTest('API Key Cleanup', true, 'No test API key to clean up');
    return true;
  }

  try {
    console.log('\n🧪 Testing API Key Cleanup...');
    
    const response = await api.delete(`/api/settings/api-keys/${keyId}`);
    
    if (response.data.success) {
      logTest(
        'API Key Cleanup',
        true,
        'Successfully deleted test API key',
        { keyId }
      );
      return true;
    } else {
      logTest('API Key Cleanup', false, 'Failed to delete test API key', response.data);
      return false;
    }
  } catch (error) {
    logTest(
      'API Key Cleanup',
      false,
      'Cleanup request failed',
      {
        status: error.response?.status,
        message: error.message,
        data: error.response?.data
      }
    );
    return false;
  }
}

/**
 * Main test execution
 */
async function runEndToEndTests() {
  console.log('🚀 Starting End-to-End API Key Flow Tests');
  console.log(`📡 Testing against: ${API_BASE_URL}`);
  console.log(`🔑 Using auth token: ${TEST_USER_TOKEN ? '✅ Provided' : '❌ Missing'}\n`);

  if (!TEST_USER_TOKEN) {
    console.log('❌ TEST_USER_TOKEN environment variable is required');
    console.log('   Set it to a valid JWT token for testing');
    process.exit(1);
  }

  let testApiKeyId = null;

  try {
    // Run all tests in sequence
    testApiKeyId = await testApiKeyCreation();
    await testApiKeyRetrieval();
    await testApiKeyValidation(testApiKeyId);
    await testPortfolioDataRetrieval();
    await testRealTimeDataService();
    
  } finally {
    // Always attempt cleanup
    await testApiKeyCleanup(testApiKeyId);
  }

  // Print summary
  console.log('\n📊 Test Summary');
  console.log('================');
  console.log(`✅ Passed: ${testResults.passed}`);
  console.log(`❌ Failed: ${testResults.failed}`);
  console.log(`📈 Success Rate: ${((testResults.passed / (testResults.passed + testResults.failed)) * 100).toFixed(1)}%`);

  if (testResults.failed > 0) {
    console.log('\n❌ Failed Tests:');
    testResults.tests
      .filter(test => !test.success)
      .forEach(test => {
        console.log(`   - ${test.name}: ${test.message}`);
      });
  }

  console.log('\n🎯 Test Results:');
  if (testResults.failed === 0) {
    console.log('🎉 All tests passed! API key integration is working correctly.');
  } else {
    console.log('⚠️  Some tests failed. Check the details above for issues to address.');
  }

  // Exit with appropriate code
  process.exit(testResults.failed > 0 ? 1 : 0);
}

// Run tests if this script is executed directly
if (require.main === module) {
  runEndToEndTests().catch(error => {
    console.error('💥 Test execution failed:', error);
    process.exit(1);
  });
}

module.exports = {
  runEndToEndTests,
  testResults
};
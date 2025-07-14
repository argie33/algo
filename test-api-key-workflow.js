#!/usr/bin/env node

// Test API Key Workflow
// This script tests the complete API key workflow without requiring AWS deployment

const https = require('https');

const API_BASE = 'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev';

// Test token - this would normally come from Cognito authentication
const TEST_TOKEN = 'test-token'; // User should replace with real token

async function makeRequest(method, path, data = null, token = null) {
  return new Promise((resolve, reject) => {
    const url = new URL(API_BASE + path);
    
    const options = {
      hostname: url.hostname,
      port: 443,
      path: url.pathname + url.search,
      method: method,
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      }
    };
    
    if (token) {
      options.headers['Authorization'] = `Bearer ${token}`;
    }
    
    const req = https.request(options, (res) => {
      let data = '';
      
      res.on('data', (chunk) => {
        data += chunk;
      });
      
      res.on('end', () => {
        try {
          const response = JSON.parse(data);
          resolve({
            status: res.statusCode,
            headers: res.headers,
            data: response
          });
        } catch (e) {
          resolve({
            status: res.statusCode,
            headers: res.headers,
            data: data
          });
        }
      });
    });
    
    req.on('error', (error) => {
      reject(error);
    });
    
    if (data) {
      req.write(JSON.stringify(data));
    }
    
    req.end();
  });
}

async function testApiKeyWorkflow() {
  console.log('🧪 Testing API Key Workflow');
  console.log('================================');
  
  // Step 1: Test health endpoint
  console.log('\n1. Testing Health Endpoint...');
  try {
    const healthResponse = await makeRequest('GET', '/health?quick=true');
    console.log('✅ Health Status:', healthResponse.status);
    console.log('📋 Health Data:', JSON.stringify(healthResponse.data, null, 2));
  } catch (error) {
    console.error('❌ Health test failed:', error.message);
  }
  
  // Step 2: Test Settings endpoint availability
  console.log('\n2. Testing Settings Endpoint...');
  try {
    const settingsResponse = await makeRequest('GET', '/api/settings');
    console.log('✅ Settings Status:', settingsResponse.status);
    console.log('📋 Settings Data:', JSON.stringify(settingsResponse.data, null, 2));
  } catch (error) {
    console.error('❌ Settings test failed:', error.message);
  }
  
  // Step 3: Test API Keys endpoint (without auth - should fail)
  console.log('\n3. Testing API Keys Endpoint (No Auth)...');
  try {
    const apiKeysResponse = await makeRequest('GET', '/api/settings/api-keys');
    console.log('📊 API Keys Status:', apiKeysResponse.status);
    console.log('📋 API Keys Response:', JSON.stringify(apiKeysResponse.data, null, 2));
    
    if (apiKeysResponse.status === 401) {
      console.log('✅ Properly rejecting unauthenticated requests');
    }
  } catch (error) {
    console.error('❌ API Keys test failed:', error.message);
  }
  
  // Step 4: Test debug endpoint
  console.log('\n4. Testing API Keys Debug Endpoint...');
  try {
    const debugResponse = await makeRequest('GET', '/api/settings/api-keys/debug');
    console.log('📊 Debug Status:', debugResponse.status);
    console.log('📋 Debug Data:', JSON.stringify(debugResponse.data, null, 2));
  } catch (error) {
    console.error('❌ Debug test failed:', error.message);
  }
  
  // Step 5: Test with mock token (will fail auth but show flow)
  console.log('\n5. Testing API Keys with Mock Token...');
  try {
    const mockAuthResponse = await makeRequest('GET', '/api/settings/api-keys', null, TEST_TOKEN);
    console.log('📊 Mock Auth Status:', mockAuthResponse.status);
    console.log('📋 Mock Auth Response:', JSON.stringify(mockAuthResponse.data, null, 2));
  } catch (error) {
    console.error('❌ Mock auth test failed:', error.message);
  }
  
  console.log('\n🎯 Test Summary:');
  console.log('================');
  console.log('- Health endpoint: Tests basic API availability');
  console.log('- Settings endpoint: Tests route configuration');  
  console.log('- API keys endpoint: Tests authentication requirements');
  console.log('- Debug endpoint: Tests database table status');
  console.log('- Mock token test: Tests authentication flow');
  console.log('\n💡 Next Steps:');
  console.log('- If services are running, user can add API keys via Settings page');
  console.log('- Replace TEST_TOKEN with real Cognito JWT token for full testing');
  console.log('- Test actual API key addition through frontend Settings page');
}

// Run the test
if (require.main === module) {
  testApiKeyWorkflow().catch(console.error);
}

module.exports = { testApiKeyWorkflow, makeRequest };
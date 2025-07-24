#!/usr/bin/env node

/**
 * Test API Key Service Connection to AWS Parameter Store
 * Verifies that the service can connect and handle missing keys gracefully
 */

const apiKeyService = require('./utils/simpleApiKeyService');

async function testApiKeyService() {
  console.log('🧪 Testing API Key Service Connection to Parameter Store...');
  
  try {
    // Test 1: Try to get a non-existent API key (should return null gracefully)
    console.log('\n📋 Test 1: Get non-existent API key');
    const testUserId = 'test-user-123';
    const testProvider = 'alpaca';
    
    const apiKey = await apiKeyService.getApiKey(testUserId, testProvider);
    console.log('Result:', apiKey);
    
    if (apiKey === null) {
      console.log('✅ Test 1 PASSED: Service correctly returns null for missing key');
    } else {
      console.log('❌ Test 1 FAILED: Service should return null for missing key');
    }
    
    // Test 2: Try to store and retrieve a test API key
    console.log('\n📋 Test 2: Store and retrieve test API key');
    const testKeyId = 'test-key-123';
    const testSecretKey = 'test-secret-456';
    
    try {
      const storeResult = await apiKeyService.storeApiKey(testUserId, testProvider, testKeyId, testSecretKey);
      console.log('Store result:', storeResult);
      
      if (storeResult) {
        // Now try to retrieve it
        const retrievedKey = await apiKeyService.getApiKey(testUserId, testProvider);
        console.log('Retrieved key:', retrievedKey);
        
        if (retrievedKey && retrievedKey.keyId === testKeyId) {
          console.log('✅ Test 2 PASSED: Store and retrieve works');
          
          // Clean up - delete the test key
          await apiKeyService.deleteApiKey(testUserId, testProvider);
          console.log('🧹 Test key cleaned up');
        } else {
          console.log('❌ Test 2 FAILED: Retrieved key does not match stored key');
        }
      } else {
        console.log('❌ Test 2 FAILED: Could not store test key');
      }
    } catch (storeError) {
      console.log('❌ Test 2 FAILED: Error during store/retrieve test:', storeError.message);
    }
    
    // Test 3: Test AWS permissions
    console.log('\n📋 Test 3: AWS permissions check');
    console.log('AWS Region:', process.env.AWS_REGION || 'us-east-1');
    console.log('Parameter prefix:', apiKeyService.parameterPrefix || '/financial-platform/users');
    
    console.log('\n🎯 API Key Service Test Complete');
    
  } catch (error) {
    console.error('❌ API Key Service Test Failed:', error);
    console.error('Error details:', {
      name: error.name,
      message: error.message,
      code: error.code,
      stack: error.stack?.split('\n')[0]
    });
  }
}

// Run the test
testApiKeyService().catch(console.error);
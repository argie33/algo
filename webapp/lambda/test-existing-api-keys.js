#!/usr/bin/env node

/**
 * Test for existing API keys in Parameter Store
 * Check if there are any real user API keys already stored
 */

const apiKeyService = require('./utils/simpleApiKeyService');

async function testExistingApiKeys() {
  console.log('🔍 Testing for existing API keys in Parameter Store...');
  
  // Test common user IDs and providers
  const testCombinations = [
    { userId: 'demo@example.com', provider: 'alpaca' },
    { userId: 'test@example.com', provider: 'alpaca' },
    { userId: 'user@example.com', provider: 'alpaca' },
    { userId: 'admin', provider: 'alpaca' },
    { userId: 'demo', provider: 'alpaca' },
    { userId: 'development', provider: 'alpaca' }
  ];
  
  let foundKeys = 0;
  
  for (const combo of testCombinations) {
    try {
      console.log(`\n🔍 Checking: ${combo.userId} / ${combo.provider}`);
      const apiKey = await apiKeyService.getApiKey(combo.userId, combo.provider);
      
      if (apiKey) {
        console.log(`✅ Found API key for ${combo.userId}:`, {
          keyId: apiKey.keyId ? `${apiKey.keyId.substring(0, 8)}...` : 'undefined',
          hasSecret: !!apiKey.secretKey,
          version: apiKey.version
        });
        foundKeys++;
      } else {
        console.log(`📭 No API key found for ${combo.userId}/${combo.provider}`);
      }
    } catch (error) {
      console.log(`❌ Error checking ${combo.userId}/${combo.provider}:`, error.message);
    }
  }
  
  console.log(`\n📊 Summary: Found ${foundKeys} API keys out of ${testCombinations.length} combinations tested`);
  
  if (foundKeys === 0) {
    console.log('\n💡 No API keys found. This explains why portfolio endpoints return empty data.');
    console.log('🔧 To fix: Either add API keys via the frontend or manually via AWS Parameter Store');
  }
}

testExistingApiKeys().catch(console.error);
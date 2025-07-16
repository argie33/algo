#!/usr/bin/env node
/**
 * Test API Key Service
 * Tests the encryption/decryption functionality locally
 */

const crypto = require('crypto');

// Mock the API key service encryption logic locally
class ApiKeyServiceTest {
  constructor() {
    this.algorithm = 'aes-256-gcm';
    this.testSecret = 'test-secret-key-for-development-only-32-chars-long';
  }

  async encryptApiKey(apiKey, userSalt) {
    try {
      // Generate encryption key from secret and user salt
      const key = crypto.scryptSync(this.testSecret, userSalt, 32);
      
      // Generate random IV
      const iv = crypto.randomBytes(12);
      
      // Create cipher
      const cipher = crypto.createCipher('aes-256-gcm', key);
      cipher.setAAD(Buffer.from(userSalt));
      
      let encrypted = cipher.update(apiKey, 'utf8', 'hex');
      encrypted += cipher.final('hex');
      
      const authTag = cipher.getAuthTag();
      
      return {
        encrypted: encrypted,
        iv: iv.toString('hex'),
        authTag: authTag.toString('hex')
      };
    } catch (error) {
      console.error('Encryption error:', error);
      throw error;
    }
  }

  async decryptApiKey(encryptedData, userSalt) {
    try {
      // Generate encryption key from secret and user salt
      const key = crypto.scryptSync(this.testSecret, userSalt, 32);
      
      // Create decipher
      const decipher = crypto.createDecipher('aes-256-gcm', key);
      decipher.setAAD(Buffer.from(userSalt));
      decipher.setAuthTag(Buffer.from(encryptedData.authTag, 'hex'));
      
      let decrypted = decipher.update(encryptedData.encrypted, 'hex', 'utf8');
      decrypted += decipher.final('utf8');
      
      return decrypted;
    } catch (error) {
      console.error('Decryption error:', error);
      throw error;
    }
  }

  validateApiKeyFormat(provider, apiKey) {
    switch (provider.toLowerCase()) {
      case 'alpaca':
        return apiKey.length >= 20 && apiKey.length <= 50 && /^[A-Za-z0-9]+$/.test(apiKey);
      case 'tdameritrade':
        return apiKey.length === 32 && /^[A-Za-z0-9]+$/.test(apiKey);
      default:
        return apiKey.length >= 8 && apiKey.length <= 200;
    }
  }
}

// Run tests
async function runTests() {
  console.log('🧪 Testing API Key Service Encryption/Decryption...');
  
  const apiKeyService = new ApiKeyServiceTest();
  
  // Test data
  const testApiKey = 'PKTEST123456789ABCDEF';
  const testSecret = 'SECRETKEY987654321';
  const userSalt = 'user-salt-123';
  const provider = 'alpaca';
  
  try {
    // Test validation
    console.log('\\n1. Testing API key validation...');
    const isValid = apiKeyService.validateApiKeyFormat(provider, testApiKey);
    console.log(`✅ API key validation: ${isValid ? 'PASS' : 'FAIL'}`);
    
    // Test encryption
    console.log('\\n2. Testing encryption...');
    const encrypted = await apiKeyService.encryptApiKey(testApiKey, userSalt);
    console.log('✅ Encryption successful:', {
      encrypted: encrypted.encrypted.substring(0, 20) + '...',
      iv: encrypted.iv.substring(0, 20) + '...',
      authTag: encrypted.authTag.substring(0, 20) + '...'
    });
    
    // Test decryption
    console.log('\\n3. Testing decryption...');
    const decrypted = await apiKeyService.decryptApiKey(encrypted, userSalt);
    console.log('✅ Decryption successful:', decrypted);
    
    // Verify roundtrip
    console.log('\\n4. Testing roundtrip integrity...');
    const matches = decrypted === testApiKey;
    console.log(`${matches ? '✅' : '❌'} Roundtrip integrity: ${matches ? 'PASS' : 'FAIL'}`);
    
    if (matches) {
      console.log('\\n🎉 All API key service tests PASSED!');
    } else {
      console.log('\\n❌ API key service tests FAILED!');
    }
    
  } catch (error) {
    console.error('❌ Test failed:', error);
  }
}

// Run the tests
if (require.main === module) {
  runTests();
}

module.exports = { ApiKeyServiceTest };
#!/usr/bin/env node
/**
 * Test API Key Retrieval
 * Tests retrieving and decrypting API keys from database
 */

const crypto = require('crypto');

// Mock database with sample encrypted API keys
const mockDatabase = {
  apiKeys: [
    {
      id: 1,
      user_id: 'test-user-123',
      provider: 'alpaca',
      encrypted_api_key: 'encrypted-key-data',
      key_iv: '1234567890abcdef1234567890abcdef',
      key_auth_tag: 'abcdef1234567890abcdef1234567890',
      encrypted_api_secret: 'encrypted-secret-data',
      secret_iv: '9876543210fedcba9876543210fedcba',
      secret_auth_tag: 'fedcba0987654321fedcba0987654321',
      user_salt: 'user-salt-123',
      is_sandbox: true,
      is_active: true,
      created_at: new Date(),
      last_used: null
    }
  ],
  
  query: function(sql, params) {
    console.log('📊 Mock DB Query:', sql.substring(0, 50) + '...');
    console.log('📊 Mock DB Params:', params);
    
    if (sql.includes('SELECT') && sql.includes('user_api_keys')) {
      const userId = params[0];
      const provider = params[1];
      
      const results = this.apiKeys.filter(key => 
        key.user_id === userId && 
        key.provider === provider && 
        key.is_active
      );
      
      return Promise.resolve({ rows: results });
    }
    
    return Promise.resolve({ rows: [] });
  }
};

// API Key Service with encryption/decryption
class ApiKeyRetrievalService {
  constructor() {
    this.algorithm = 'aes-256-gcm';
    this.secretKey = 'test-secret-key-32-chars-long-test';
  }
  
  async getDecryptedApiKey(userId, provider) {
    try {
      console.log(`🔍 Retrieving API key for user ${userId}, provider ${provider}`);
      
      // Query database for API key
      const query = `
        SELECT encrypted_api_key, key_iv, key_auth_tag, 
               encrypted_api_secret, secret_iv, secret_auth_tag, 
               user_salt, is_sandbox, last_used
        FROM user_api_keys 
        WHERE user_id = $1 AND provider = $2 AND is_active = true
        ORDER BY created_at DESC 
        LIMIT 1
      `;
      
      const result = await mockDatabase.query(query, [userId, provider]);
      
      if (!result.rows || result.rows.length === 0) {
        console.log('❌ No API key found for user and provider');
        return null;
      }
      
      const keyData = result.rows[0];
      console.log('✅ API key data retrieved from database');
      
      // Decrypt API key
      const decryptedKey = await this.decryptApiKey(
        {
          encrypted: keyData.encrypted_api_key,
          iv: keyData.key_iv,
          authTag: keyData.key_auth_tag
        },
        keyData.user_salt
      );
      
      // Decrypt API secret if available
      let decryptedSecret = null;
      if (keyData.encrypted_api_secret) {
        decryptedSecret = await this.decryptApiKey(
          {
            encrypted: keyData.encrypted_api_secret,
            iv: keyData.secret_iv,
            authTag: keyData.secret_auth_tag
          },
          keyData.user_salt
        );
      }
      
      return {
        apiKey: decryptedKey,
        apiSecret: decryptedSecret,
        isSandbox: keyData.is_sandbox,
        lastUsed: keyData.last_used
      };
      
    } catch (error) {
      console.error('❌ Error retrieving API key:', error);
      throw error;
    }
  }
  
  async decryptApiKey(encryptedData, userSalt) {
    try {
      // Generate encryption key from secret and user salt
      const key = crypto.scryptSync(this.secretKey, userSalt, 32);
      
      // Create decipher
      const decipher = crypto.createDecipher('aes-256-gcm', key);
      decipher.setAAD(Buffer.from(userSalt));
      decipher.setAuthTag(Buffer.from(encryptedData.authTag, 'hex'));
      
      let decrypted = decipher.update(encryptedData.encrypted, 'hex', 'utf8');
      decrypted += decipher.final('utf8');
      
      return decrypted;
    } catch (error) {
      console.error('❌ Decryption error:', error);
      throw error;
    }
  }
  
  async encryptApiKey(apiKey, userSalt) {
    try {
      // Generate encryption key from secret and user salt
      const key = crypto.scryptSync(this.secretKey, userSalt, 32);
      
      // Generate random IV
      const iv = crypto.randomBytes(16);
      
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
      console.error('❌ Encryption error:', error);
      throw error;
    }
  }
}

// Test suite
async function runTests() {
  console.log('🧪 Testing API Key Retrieval...');
  
  const apiKeyService = new ApiKeyRetrievalService();
  
  // First, let's add a real encrypted API key to our mock database
  console.log('\n1. Setting up test data...');
  const testApiKey = 'PKTEST123456789ABCDEF';
  const testSecret = 'SECRET987654321ABCDEF';
  const userSalt = 'user-salt-123';
  
  try {
    // Encrypt test data
    const encryptedKey = await apiKeyService.encryptApiKey(testApiKey, userSalt);
    const encryptedSecret = await apiKeyService.encryptApiKey(testSecret, userSalt);
    
    // Update mock database with properly encrypted data
    mockDatabase.apiKeys[0].encrypted_api_key = encryptedKey.encrypted;
    mockDatabase.apiKeys[0].key_iv = encryptedKey.iv;
    mockDatabase.apiKeys[0].key_auth_tag = encryptedKey.authTag;
    mockDatabase.apiKeys[0].encrypted_api_secret = encryptedSecret.encrypted;
    mockDatabase.apiKeys[0].secret_iv = encryptedSecret.iv;
    mockDatabase.apiKeys[0].secret_auth_tag = encryptedSecret.authTag;
    
    console.log('✅ Test data encrypted and stored');
    
    // Test 2: Retrieve existing API key
    console.log('\n2. Testing API key retrieval...');
    const retrievedKey = await apiKeyService.getDecryptedApiKey('test-user-123', 'alpaca');
    
    if (retrievedKey) {
      console.log('✅ API key retrieved successfully');
      console.log('   API Key:', retrievedKey.apiKey);
      console.log('   API Secret:', retrievedKey.apiSecret);
      console.log('   Is Sandbox:', retrievedKey.isSandbox);
      
      // Verify decryption worked correctly
      const keyMatches = retrievedKey.apiKey === testApiKey;
      const secretMatches = retrievedKey.apiSecret === testSecret;
      
      console.log(`${keyMatches ? '✅' : '❌'} API key decryption: ${keyMatches ? 'PASS' : 'FAIL'}`);
      console.log(`${secretMatches ? '✅' : '❌'} API secret decryption: ${secretMatches ? 'PASS' : 'FAIL'}`);
    } else {
      console.log('❌ No API key retrieved');
    }
    
    // Test 3: Retrieve non-existent API key
    console.log('\n3. Testing non-existent API key...');
    const nonExistentKey = await apiKeyService.getDecryptedApiKey('non-existent-user', 'alpaca');
    
    console.log(`${!nonExistentKey ? '✅' : '❌'} Non-existent key handling: ${!nonExistentKey ? 'PASS' : 'FAIL'}`);
    
    // Test 4: Retrieve different provider
    console.log('\n4. Testing different provider...');
    const differentProvider = await apiKeyService.getDecryptedApiKey('test-user-123', 'tdameritrade');
    
    console.log(`${!differentProvider ? '✅' : '❌'} Different provider handling: ${!differentProvider ? 'PASS' : 'FAIL'}`);
    
    console.log('\n🎉 API Key Retrieval Tests Complete!');
    console.log('Next: Test portfolio import with retrieved API keys...');
    
  } catch (error) {
    console.error('❌ Test failed:', error);
  }
}

// Run tests if called directly
if (require.main === module) {
  runTests().catch(console.error);
}

module.exports = { ApiKeyRetrievalService, runTests };
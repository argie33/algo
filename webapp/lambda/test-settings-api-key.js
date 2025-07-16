#!/usr/bin/env node
/**
 * Test Settings API Key Addition
 * Tests the complete API key addition workflow
 */

const express = require('express');
const crypto = require('crypto');
const request = require('supertest');

// Mock database query function
const mockDatabase = {
  queryResults: [],
  insertResults: { rows: [{ id: 1, created_at: new Date() }] },
  
  query: function(sql, params) {
    console.log('📊 Mock DB Query:', sql.substring(0, 50) + '...');
    console.log('📊 Mock DB Params:', params);
    
    if (sql.includes('INSERT')) {
      return Promise.resolve(this.insertResults);
    } else if (sql.includes('SELECT')) {
      return Promise.resolve({ rows: this.queryResults });
    }
    
    return Promise.resolve({ rows: [] });
  }
};

// Mock the database module
jest.mock('../utils/database', () => ({
  query: mockDatabase.query.bind(mockDatabase)
}));

// Mock the authentication middleware
const mockAuthMiddleware = (req, res, next) => {
  req.user = {
    sub: 'test-user-123',
    userId: 'test-user-123',
    email: 'test@example.com'
  };
  next();
};

// Mock API key service
const mockApiKeyService = {
  isEnabled: true,
  
  encryptApiKey: function(apiKey, userSalt) {
    const key = crypto.scryptSync('test-secret-key', userSalt, 32);
    const iv = crypto.randomBytes(16);
    const cipher = crypto.createCipher('aes-256-gcm', key);
    
    let encrypted = cipher.update(apiKey, 'utf8', 'hex');
    encrypted += cipher.final('hex');
    const authTag = cipher.getAuthTag ? cipher.getAuthTag() : Buffer.alloc(16);
    
    return {
      encrypted: encrypted,
      iv: iv.toString('hex'),
      authTag: authTag.toString('hex')
    };
  }
};

// Create test app
function createTestApp() {
  const app = express();
  app.use(express.json());
  
  // Mock environment variables
  process.env.API_KEY_ENCRYPTION_SECRET = 'test-secret-key-32-chars-long-test';
  process.env.NODE_ENV = 'test';
  
  // Add API key addition endpoint
  app.post('/api/settings/api-keys', mockAuthMiddleware, async (req, res) => {
    try {
      const { provider, apiKey, apiSecret, isSandbox = true, description } = req.body;
      
      // Validation
      if (!provider || !apiKey) {
        return res.status(400).json({
          success: false,
          error: 'Provider and API key are required'
        });
      }
      
      // Validate provider
      const validProviders = ['alpaca', 'tdameritrade', 'interactivebrokers'];
      if (!validProviders.includes(provider.toLowerCase())) {
        return res.status(400).json({
          success: false,
          error: 'Invalid provider'
        });
      }
      
      // Validate API key format
      const validateApiKeyFormat = (provider, apiKey) => {
        switch (provider.toLowerCase()) {
          case 'alpaca':
            return apiKey.length >= 20 && apiKey.length <= 50 && /^[A-Za-z0-9]+$/.test(apiKey);
          case 'tdameritrade':
            return apiKey.length === 32 && /^[A-Za-z0-9]+$/.test(apiKey);
          default:
            return apiKey.length >= 8 && apiKey.length <= 200;
        }
      };
      
      if (!validateApiKeyFormat(provider, apiKey)) {
        return res.status(400).json({
          success: false,
          error: 'Invalid API key format for provider'
        });
      }
      
      // Generate user salt
      const userSalt = crypto.randomBytes(16).toString('hex');
      
      // Encrypt API key
      const encryptedKey = mockApiKeyService.encryptApiKey(apiKey, userSalt);
      let encryptedSecret = null;
      
      if (apiSecret) {
        encryptedSecret = mockApiKeyService.encryptApiKey(apiSecret, userSalt);
      }
      
      // Insert into database
      const insertQuery = `
        INSERT INTO user_api_keys (
          user_id, provider, encrypted_api_key, key_iv, key_auth_tag,
          encrypted_api_secret, secret_iv, secret_auth_tag, user_salt,
          is_sandbox, description, is_active, created_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, NOW())
        RETURNING id, created_at
      `;
      
      const insertParams = [
        req.user.sub,
        provider.toLowerCase(),
        encryptedKey.encrypted,
        encryptedKey.iv,
        encryptedKey.authTag,
        encryptedSecret?.encrypted || null,
        encryptedSecret?.iv || null,
        encryptedSecret?.authTag || null,
        userSalt,
        isSandbox,
        description || null,
        true
      ];
      
      const result = await mockDatabase.query(insertQuery, insertParams);
      
      res.status(201).json({
        success: true,
        message: 'API key added successfully',
        data: {
          id: result.rows[0].id,
          provider,
          isSandbox,
          description,
          created_at: result.rows[0].created_at
        }
      });
      
    } catch (error) {
      console.error('Error adding API key:', error);
      res.status(500).json({
        success: false,
        error: 'Internal server error'
      });
    }
  });
  
  return app;
}

// Test suite
async function runTests() {
  console.log('🧪 Testing Settings API Key Addition...');
  
  const app = createTestApp();
  
  // Test 1: Valid Alpaca API key
  console.log('\n1. Testing valid Alpaca API key...');
  const alpacaResponse = await request(app)
    .post('/api/settings/api-keys')
    .send({
      provider: 'alpaca',
      apiKey: 'PKTEST123456789ABCDEFGHIJ',
      apiSecret: 'SECRET987654321ABCDEFGHIJ',
      isSandbox: true,
      description: 'Test Alpaca API key'
    });
  
  console.log('✅ Alpaca API key test:', alpacaResponse.status === 201 ? 'PASS' : 'FAIL');
  if (alpacaResponse.status !== 201) {
    console.log('   Error:', alpacaResponse.body);
  }
  
  // Test 2: Invalid provider
  console.log('\n2. Testing invalid provider...');
  const invalidProviderResponse = await request(app)
    .post('/api/settings/api-keys')
    .send({
      provider: 'invalid-provider',
      apiKey: 'TESTKEY123456789'
    });
  
  console.log('✅ Invalid provider test:', invalidProviderResponse.status === 400 ? 'PASS' : 'FAIL');
  
  // Test 3: Invalid API key format
  console.log('\n3. Testing invalid API key format...');
  const invalidKeyResponse = await request(app)
    .post('/api/settings/api-keys')
    .send({
      provider: 'alpaca',
      apiKey: 'TOO-SHORT'
    });
  
  console.log('✅ Invalid API key format test:', invalidKeyResponse.status === 400 ? 'PASS' : 'FAIL');
  
  // Test 4: Missing required fields
  console.log('\n4. Testing missing required fields...');
  const missingFieldsResponse = await request(app)
    .post('/api/settings/api-keys')
    .send({
      provider: 'alpaca'
      // Missing apiKey
    });
  
  console.log('✅ Missing fields test:', missingFieldsResponse.status === 400 ? 'PASS' : 'FAIL');
  
  // Test 5: TD Ameritrade API key
  console.log('\n5. Testing TD Ameritrade API key...');
  const tdResponse = await request(app)
    .post('/api/settings/api-keys')
    .send({
      provider: 'tdameritrade',
      apiKey: 'ABCDEFGHIJ1234567890ABCDEFGHIJ12', // 32 chars
      isSandbox: false,
      description: 'Live TD Ameritrade account'
    });
  
  console.log('✅ TD Ameritrade API key test:', tdResponse.status === 201 ? 'PASS' : 'FAIL');
  
  console.log('\n🎉 API Key Addition Tests Complete!');
  console.log('Ready to test API key retrieval and portfolio import...');
}

// Run tests if called directly
if (require.main === module) {
  runTests().catch(console.error);
}

module.exports = { createTestApp, runTests };
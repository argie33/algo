/**
 * API Key Encryption Integration Test  
 * Critical: Validates secure API key storage and retrieval for financial data
 */

// Unmock the apiKeyService for this test to test real encryption
jest.unmock('../../../utils/apiKeyService');

const apiKeyService = require('../../../utils/apiKeyService');
const { query } = require('../../../utils/database');
const _crypto = require('crypto');

describe('API Key Encryption Integration', () => {
  let testUserId;
  const testApiKeys = {
    alpaca: {
      keyId: 'test-alpaca-key-id',
      secret: 'test-alpaca-secret-key-123456789',
      sandbox: true
    },
    polygon: {
      keyId: 'test-polygon-key',
      secret: 'polygon-api-key-abcdef123456789'
    },
    finnhub: {
      keyId: 'test-finnhub-key', 
      secret: 'finnhub-token-xyz789123'
    }
  };

  beforeAll(async () => {
    testUserId = 'test-user-encryption-' + Date.now();
    
    // Set up environment variables for API key encryption testing
    process.env.API_KEY_ENCRYPTION_SECRET = 'test-secret-key-for-integration-testing-32-chars';
    process.env.NODE_ENV = 'test';
    
    // Ensure API key service is initialized
    if (!apiKeyService.isEnabled) {
      await new Promise(resolve => setTimeout(resolve, 1000));
    }
  });

  afterAll(async () => {
    // Cleanup test data
    try {
      await query('DELETE FROM user_api_keys WHERE user_id = $1', [testUserId]);
    } catch (error) {
      console.log('Cleanup warning:', error.message);
    }
  });

  describe('API Key Storage Encryption', () => {
    test('should encrypt API keys before database storage', async () => {
      const result = await apiKeyService.storeApiKey(
        testUserId,
        'alpaca',
        testApiKeys.alpaca
      );

      expect(result.success).toBe(true);

      // Verify data is encrypted in database
      const dbResult = await query(
        'SELECT encrypted_data, user_salt FROM user_api_keys WHERE user_id = $1 AND provider = $2',
        [testUserId, 'alpaca']
      );

      expect(dbResult.rows).toHaveLength(1);
      const { encrypted_data, user_salt } = dbResult.rows[0];

      // Should not contain original values
      expect(encrypted_data).not.toBe(testApiKeys.alpaca.keyId);
      expect(encrypted_data).not.toBe(testApiKeys.alpaca.secret);
      expect(user_salt).not.toBe(testApiKeys.alpaca.keyId);
      expect(user_salt).not.toBe(testApiKeys.alpaca.secret);
      
      // Should be properly encrypted format
      expect(encrypted_data).toContain(':'); // encrypted:iv format
      expect(user_salt).toMatch(/^[0-9a-f]+$/); // hex format
    });

    test('should use unique encryption for each API key', async () => {
      // Store multiple keys
      await apiKeyService.storeApiKey(testUserId, 'polygon', testApiKeys.polygon);
      await apiKeyService.storeApiKey(testUserId, 'finnhub', testApiKeys.finnhub);

      const dbResult = await query(
        'SELECT provider, encrypted_data, user_salt FROM user_api_keys WHERE user_id = $1',
        [testUserId]
      );

      expect(dbResult.rows.length).toBeGreaterThanOrEqual(2);

      // Each encrypted value should be unique
      const encryptedValues = dbResult.rows.map(row => row.encrypted_data + row.user_salt);
      const uniqueValues = [...new Set(encryptedValues)];
      
      expect(uniqueValues.length).toBe(encryptedValues.length);
    });

    test('should generate unique salt per user', async () => {
      const anotherUserId = 'test-user-encryption-salt-' + Date.now();
      const testData = { keyId: 'same-key', secret: 'same-secret' };
      
      // Store same API key for different users
      await apiKeyService.storeApiKey(testUserId, 'test-same', testData);
      await apiKeyService.storeApiKey(anotherUserId, 'test-same', testData);

      const user1Result = await query(
        'SELECT encrypted_data FROM user_api_keys WHERE user_id = $1 AND provider = $2',
        [testUserId, 'test-same']
      );
      
      const user2Result = await query(
        'SELECT encrypted_data FROM user_api_keys WHERE user_id = $1 AND provider = $2',
        [anotherUserId, 'test-same']
      );

      // Same plaintext should produce different ciphertext for different users
      expect(user1Result.rows[0].encrypted_data).not.toBe(user2Result.rows[0].encrypted_data);

      // Cleanup
      await query('DELETE FROM user_api_keys WHERE user_id = $1', [anotherUserId]);
    });
  });

  describe('API Key Retrieval Decryption', () => {
    test('should decrypt API keys correctly on retrieval', async () => {
      // Store then retrieve
      await apiKeyService.storeApiKey(testUserId, 'alpaca', testApiKeys.alpaca);
      
      const retrievedKey = await apiKeyService.getApiKey(testUserId, 'alpaca');

      expect(retrievedKey).toBeDefined();
      expect(retrievedKey.keyId).toBe(testApiKeys.alpaca.keyId);
      expect(retrievedKey.secret).toBe(testApiKeys.alpaca.secret);
    });

    test('should handle multiple provider retrieval', async () => {
      // Store keys for multiple providers
      await apiKeyService.storeApiKey(testUserId, 'polygon', testApiKeys.polygon);
      await apiKeyService.storeApiKey(testUserId, 'finnhub', testApiKeys.finnhub);

      const polygonKey = await apiKeyService.getApiKey(testUserId, 'polygon');
      const finnhubKey = await apiKeyService.getApiKey(testUserId, 'finnhub');

      expect(polygonKey).toBeDefined();
      expect(finnhubKey).toBeDefined();
      expect(polygonKey.keyId).toBe(testApiKeys.polygon.keyId);
      expect(finnhubKey.secret).toBe(testApiKeys.finnhub.secret);
    });

    test('should fail gracefully for non-existent user', async () => {
      const nonExistentUserId = 'non-existent-user-' + Date.now();
      
      const result = await apiKeyService.getApiKey(nonExistentUserId, 'alpaca');
      
      expect(result).toBeNull();
    });

    test('should handle corrupted encryption data', async () => {
      // Insert corrupted data directly
      await query(
        `INSERT INTO user_api_keys 
         (user_id, provider, encrypted_data, user_salt, created_at) 
         VALUES ($1, 'corrupted', 'invalid-format', 'invalid-format', NOW())`,
        [testUserId]
      );

      const result = await apiKeyService.getApiKey(testUserId, 'corrupted');
      
      // Should handle error gracefully and not crash
      expect(result).toBeNull();
    });
  });

  describe('API Key Security Validation', () => {
    test('should validate API key format before storage', async () => {
      const invalidCases = [
        { keyId: '', secret: 'valid-secret' },
        { keyId: 'valid-key', secret: '' },
        { keyId: null, secret: 'valid-secret' },
        { keyId: 'valid-key', secret: null }
      ];

      for (const testCase of invalidCases) {
        const result = await apiKeyService.storeApiKey(
          testUserId,
          'validation-test',
          testCase
        );

        expect(result.success).toBe(false);
        expect(result.error).toBeDefined();
      }
    });

    test('should enforce maximum key length limits', async () => {
      const tooLongKey = 'x'.repeat(1000); // 1000 characters
      const tooLongSecret = 'y'.repeat(2000); // 2000 characters

      const result = await apiKeyService.storeApiKey(
        testUserId,
        'length-test',
        { keyId: tooLongKey, secret: tooLongSecret }
      );

      expect(result.success).toBe(false);
      expect(result.error).toMatch(/length|size|limit/i);
    });

    test('should prevent SQL injection in provider names', async () => {
      const maliciousProvider = "'; DROP TABLE user_api_keys; --";
      
      const result = await apiKeyService.storeApiKey(
        testUserId,
        maliciousProvider,
        { keyId: 'test-key', secret: 'test-secret' }
      );

      // Should either reject the malicious provider or sanitize it
      expect(result.success).toBe(false);
      
      // Verify table still exists (SQL injection should not drop the table)
      const tableCheck = await query(
        "SELECT table_name FROM information_schema.tables WHERE table_name = 'user_api_keys' AND table_schema = 'public'"
      );
      expect(tableCheck.rows.length).toBe(1);
    });
  });

  describe('API Key Update and Deletion', () => {
    test('should update existing API keys', async () => {
      // Store initial key
      await apiKeyService.storeApiKey(testUserId, 'update-test', { keyId: 'old-key', secret: 'old-secret' });
      
      // Update with new values
      const updateResult = await apiKeyService.storeApiKey(testUserId, 'update-test', { keyId: 'new-key', secret: 'new-secret' });
      expect(updateResult.success).toBe(true);

      // Verify update
      const retrievedKey = await apiKeyService.getApiKey(testUserId, 'update-test');
      expect(retrievedKey.keyId).toBe('new-key');
      expect(retrievedKey.secret).toBe('new-secret');
    });

    test('should delete API keys securely', async () => {
      // Store key
      await apiKeyService.storeApiKey(testUserId, 'delete-test', { keyId: 'delete-key', secret: 'delete-secret' });
      
      // Delete key
      const deleteResult = await apiKeyService.deleteApiKey(testUserId, 'delete-test');
      expect(deleteResult.success).toBe(true);

      // Verify deletion
      const retrievedKey = await apiKeyService.getApiKey(testUserId, 'delete-test');
      expect(retrievedKey).toBeNull();

      // Verify no traces in database
      const dbResult = await query(
        'SELECT * FROM user_api_keys WHERE user_id = $1 AND provider = $2',
        [testUserId, 'delete-test']
      );
      expect(dbResult.rows).toHaveLength(0);
    });
  });

  describe('Performance and Scalability', () => {
    test('should handle concurrent API key operations', async () => {
      const concurrentOperations = [];
      
      // Create 10 concurrent store operations
      for (let i = 0; i < 10; i++) {
        concurrentOperations.push(
          apiKeyService.storeApiKey(
            testUserId,
            `concurrent-${i}`,
            { keyId: `key-${i}`, secret: `secret-${i}` }
          )
        );
      }

      const results = await Promise.all(concurrentOperations);
      
      // All operations should succeed
      results.forEach(result => {
        expect(result.success).toBe(true);
      });

      // Verify all keys stored correctly
      for (let i = 0; i < 10; i++) {
        const retrievedKey = await apiKeyService.getApiKey(testUserId, `concurrent-${i}`);
        expect(retrievedKey).toBeDefined();
        expect(retrievedKey.keyId).toBe(`key-${i}`);
      }
    });

    test('should maintain performance with large number of keys', async () => {
      const _startTime = Date.now();
      
      // Store 50 API keys
      const storePromises = [];
      for (let i = 0; i < 50; i++) {
        storePromises.push(
          apiKeyService.storeApiKey(testUserId, `perf-${i}`, { keyId: `key-${i}`, secret: `secret-${i}` })
        );
      }
      await Promise.all(storePromises);

      // Retrieve all keys
      const retrievalStart = Date.now();
      const keyCount = 50;
      let retrievedCount = 0;
      
      for (let i = 0; i < keyCount; i++) {
        const key = await apiKeyService.getApiKey(testUserId, `perf-${i}`);
        if (key) retrievedCount++;
      }
      
      const retrievalEnd = Date.now();

      // Performance assertions
      expect(retrievalEnd - retrievalStart).toBeLessThan(5000); // < 5 seconds for 50 individual calls
      expect(retrievedCount).toBeGreaterThanOrEqual(50);
    });
  });
});
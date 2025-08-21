/**
 * API Key Encryption Integration Test  
 * Critical: Validates secure API key storage and retrieval for financial data
 */

const { apiKeyService } = require('../../../services/apiKeyService');
const { query } = require('../../../services/database');
const crypto = require('crypto');

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
        testApiKeys.alpaca.keyId,
        testApiKeys.alpaca.secret,
        { sandbox: true }
      );

      expect(result.success).toBe(true);

      // Verify data is encrypted in database
      const dbResult = await query(
        'SELECT encrypted_key_id, encrypted_secret FROM user_api_keys WHERE user_id = $1 AND provider = $2',
        [testUserId, 'alpaca']
      );

      expect(dbResult.rows).toHaveLength(1);
      const { encrypted_key_id, encrypted_secret } = dbResult.rows[0];

      // Should not contain original values
      expect(encrypted_key_id).not.toBe(testApiKeys.alpaca.keyId);
      expect(encrypted_secret).not.toBe(testApiKeys.alpaca.secret);
      
      // Should be properly encrypted format
      expect(encrypted_key_id).toMatch(/^[0-9a-f]+:[0-9a-f]+$/); // encrypted:iv format
      expect(encrypted_secret).toMatch(/^[0-9a-f]+:[0-9a-f]+$/);
    });

    test('should use unique encryption for each API key', async () => {
      // Store multiple keys
      await apiKeyService.storeApiKey(testUserId, 'polygon', testApiKeys.polygon.keyId, testApiKeys.polygon.secret);
      await apiKeyService.storeApiKey(testUserId, 'finnhub', testApiKeys.finnhub.keyId, testApiKeys.finnhub.secret);

      const dbResult = await query(
        'SELECT provider, encrypted_key_id, encrypted_secret FROM user_api_keys WHERE user_id = $1',
        [testUserId]
      );

      expect(dbResult.rows.length).toBeGreaterThanOrEqual(2);

      // Each encrypted value should be unique
      const encryptedValues = dbResult.rows.map(row => row.encrypted_key_id + row.encrypted_secret);
      const uniqueValues = [...new Set(encryptedValues)];
      
      expect(uniqueValues.length).toBe(encryptedValues.length);
    });

    test('should generate unique salt per user', async () => {
      const anotherUserId = 'test-user-encryption-salt-' + Date.now();
      
      // Store same API key for different users
      await apiKeyService.storeApiKey(testUserId, 'test-same', 'same-key', 'same-secret');
      await apiKeyService.storeApiKey(anotherUserId, 'test-same', 'same-key', 'same-secret');

      const user1Result = await query(
        'SELECT encrypted_key_id FROM user_api_keys WHERE user_id = $1 AND provider = $2',
        [testUserId, 'test-same']
      );
      
      const user2Result = await query(
        'SELECT encrypted_key_id FROM user_api_keys WHERE user_id = $1 AND provider = $2',
        [anotherUserId, 'test-same']
      );

      // Same plaintext should produce different ciphertext for different users
      expect(user1Result.rows[0].encrypted_key_id).not.toBe(user2Result.rows[0].encrypted_key_id);

      // Cleanup
      await query('DELETE FROM user_api_keys WHERE user_id = $1', [anotherUserId]);
    });
  });

  describe('API Key Retrieval Decryption', () => {
    test('should decrypt API keys correctly on retrieval', async () => {
      // Store then retrieve
      await apiKeyService.storeApiKey(testUserId, 'alpaca', testApiKeys.alpaca.keyId, testApiKeys.alpaca.secret);
      
      const retrievedKeys = await apiKeyService.getUserApiKeys(testUserId);

      expect(retrievedKeys.success).toBe(true);
      expect(retrievedKeys.keys.alpaca).toBeDefined();
      expect(retrievedKeys.keys.alpaca.keyId).toBe(testApiKeys.alpaca.keyId);
      expect(retrievedKeys.keys.alpaca.secret).toBe(testApiKeys.alpaca.secret);
    });

    test('should handle multiple provider retrieval', async () => {
      // Store keys for multiple providers
      await apiKeyService.storeApiKey(testUserId, 'polygon', testApiKeys.polygon.keyId, testApiKeys.polygon.secret);
      await apiKeyService.storeApiKey(testUserId, 'finnhub', testApiKeys.finnhub.keyId, testApiKeys.finnhub.secret);

      const retrievedKeys = await apiKeyService.getUserApiKeys(testUserId);

      expect(retrievedKeys.success).toBe(true);
      expect(Object.keys(retrievedKeys.keys)).toContain('polygon');
      expect(Object.keys(retrievedKeys.keys)).toContain('finnhub');
      expect(retrievedKeys.keys.polygon.keyId).toBe(testApiKeys.polygon.keyId);
      expect(retrievedKeys.keys.finnhub.secret).toBe(testApiKeys.finnhub.secret);
    });

    test('should fail gracefully for non-existent user', async () => {
      const nonExistentUserId = 'non-existent-user-' + Date.now();
      
      const result = await apiKeyService.getUserApiKeys(nonExistentUserId);
      
      expect(result.success).toBe(true);
      expect(result.keys).toEqual({});
    });

    test('should handle corrupted encryption data', async () => {
      // Insert corrupted data directly
      await query(
        `INSERT INTO user_api_keys 
         (user_id, provider, encrypted_key_id, encrypted_secret, metadata, created_at) 
         VALUES ($1, 'corrupted', 'invalid-format', 'invalid-format', '{}', NOW())`,
        [testUserId]
      );

      const result = await apiKeyService.getUserApiKeys(testUserId);
      
      // Should handle error gracefully and not crash
      expect(result.success).toBe(true);
      // Corrupted key should be excluded from results
      expect(result.keys.corrupted).toBeUndefined();
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
          testCase.keyId,
          testCase.secret
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
        tooLongKey,
        tooLongSecret
      );

      expect(result.success).toBe(false);
      expect(result.error).toMatch(/length|size|limit/i);
    });

    test('should prevent SQL injection in provider names', async () => {
      const maliciousProvider = "'; DROP TABLE user_api_keys; --";
      
      const result = await apiKeyService.storeApiKey(
        testUserId,
        maliciousProvider,
        'test-key',
        'test-secret'
      );

      // Should either reject the malicious provider or sanitize it
      expect(result.success).toBe(false);
      
      // Verify table still exists
      const tableCheck = await query(
        "SELECT table_name FROM information_schema.tables WHERE table_name = 'user_api_keys'"
      );
      expect(tableCheck.rows.length).toBe(1);
    });
  });

  describe('API Key Update and Deletion', () => {
    test('should update existing API keys', async () => {
      // Store initial key
      await apiKeyService.storeApiKey(testUserId, 'update-test', 'old-key', 'old-secret');
      
      // Update with new values
      const updateResult = await apiKeyService.storeApiKey(testUserId, 'update-test', 'new-key', 'new-secret');
      expect(updateResult.success).toBe(true);

      // Verify update
      const retrievedKeys = await apiKeyService.getUserApiKeys(testUserId);
      expect(retrievedKeys.keys['update-test'].keyId).toBe('new-key');
      expect(retrievedKeys.keys['update-test'].secret).toBe('new-secret');
    });

    test('should delete API keys securely', async () => {
      // Store key
      await apiKeyService.storeApiKey(testUserId, 'delete-test', 'delete-key', 'delete-secret');
      
      // Delete key
      const deleteResult = await apiKeyService.deleteApiKey(testUserId, 'delete-test');
      expect(deleteResult.success).toBe(true);

      // Verify deletion
      const retrievedKeys = await apiKeyService.getUserApiKeys(testUserId);
      expect(retrievedKeys.keys['delete-test']).toBeUndefined();

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
            `key-${i}`,
            `secret-${i}`
          )
        );
      }

      const results = await Promise.all(concurrentOperations);
      
      // All operations should succeed
      results.forEach(result => {
        expect(result.success).toBe(true);
      });

      // Verify all keys stored correctly
      const retrievedKeys = await apiKeyService.getUserApiKeys(testUserId);
      
      for (let i = 0; i < 10; i++) {
        expect(retrievedKeys.keys[`concurrent-${i}`]).toBeDefined();
        expect(retrievedKeys.keys[`concurrent-${i}`].keyId).toBe(`key-${i}`);
      }
    });

    test('should maintain performance with large number of keys', async () => {
      const startTime = Date.now();
      
      // Store 50 API keys
      const storePromises = [];
      for (let i = 0; i < 50; i++) {
        storePromises.push(
          apiKeyService.storeApiKey(testUserId, `perf-${i}`, `key-${i}`, `secret-${i}`)
        );
      }
      await Promise.all(storePromises);

      // Retrieve all keys
      const retrievalStart = Date.now();
      const retrievedKeys = await apiKeyService.getUserApiKeys(testUserId);
      const retrievalEnd = Date.now();

      // Performance assertions
      expect(retrievalEnd - retrievalStart).toBeLessThan(1000); // < 1 second
      expect(Object.keys(retrievedKeys.keys).length).toBeGreaterThanOrEqual(50);
    });
  });
});
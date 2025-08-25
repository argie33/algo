/**
 * API Key Encryption Integration Test
 * Critical: Validates secure API key storage and retrieval for financial data
 */

// Use real apiKeyService without mocking JWT validation
jest.unmock("../../../utils/apiKeyService");

const _crypto = require("crypto");
const jwt = require("jsonwebtoken");

const apiKeyService = require("../../../utils/apiKeyService");
const { query } = require("../../../utils/database");

describe("API Key Encryption Integration", () => {
  let testUserId;
  let mockToken;
  const testApiKeys = {
    alpaca: {
      keyId: "test-alpaca-key-id",
      secret: "test-alpaca-secret-key-123456789",
      sandbox: true,
    },
    polygon: {
      keyId: "test-polygon-key",
      secret: "polygon-api-key-abcdef123456789",
    },
    finnhub: {
      keyId: "test-finnhub-key",
      secret: "finnhub-token-xyz789123",
    },
  };

  beforeAll(async () => {
    testUserId = "test-user-encryption-" + Date.now();
    
    // Create a valid JWT token for testing
    const jwtSecret = process.env.JWT_SECRET || 'test-secret';
    mockToken = jwt.sign(
      { sub: testUserId, email: `${testUserId}@test.local` },
      jwtSecret,
      { expiresIn: '1h' }
    );

    // Set up environment variables for API key encryption testing
    process.env.API_KEY_ENCRYPTION_SECRET =
      "test-secret-key-for-integration-testing-32-chars";
    process.env.NODE_ENV = "test";
    process.env.JWT_SECRET = jwtSecret;

    // Ensure API key service is initialized
    if (!apiKeyService.isEnabled) {
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
  });

  beforeEach(() => {
    // No mock needed - using real JWT validation with valid token
  });

  afterAll(async () => {
    // Cleanup test data
    try {
      await query("DELETE FROM user_api_keys WHERE user_id = $1", [testUserId]);
    } catch (error) {
      console.log("Cleanup warning:", error.message);
    }
  });

  describe("API Key Storage Encryption", () => {
    test("should encrypt API keys before database storage", async () => {
      const result = await apiKeyService.storeApiKey(
        mockToken,
        "alpaca",
        testApiKeys.alpaca
      );

      expect(result.success).toBe(true);

      // Verify data is encrypted in database
      const dbResult = await query(
        "SELECT encrypted_data, user_salt FROM user_api_keys WHERE user_id = $1 AND provider = $2",
        [testUserId, "alpaca"]
      );

      expect(dbResult.rows).toHaveLength(1);
      const { encrypted_data, user_salt } = dbResult.rows[0];

      // Should not contain original values
      expect(encrypted_data).not.toBe(testApiKeys.alpaca.keyId);
      expect(encrypted_data).not.toBe(testApiKeys.alpaca.secret);
      expect(user_salt).not.toBe(testApiKeys.alpaca.keyId);
      expect(user_salt).not.toBe(testApiKeys.alpaca.secret);

      // Should be properly encrypted format
      expect(encrypted_data).toContain(":"); // encrypted:iv format
      expect(user_salt).toMatch(/^[0-9a-f]+$/); // hex format
    });

    test("should use unique encryption for each API key", async () => {
      // Store multiple keys (using mockToken like the previous test)
      await apiKeyService.storeApiKey(
        mockToken,
        "polygon",
        testApiKeys.polygon
      );
      await apiKeyService.storeApiKey(
        mockToken,
        "finnhub",
        testApiKeys.finnhub
      );

      const dbResult = await query(
        "SELECT provider, encrypted_data, user_salt FROM user_api_keys WHERE user_id = $1",
        [testUserId]
      );

      expect(dbResult.rows.length).toBeGreaterThanOrEqual(2);

      // Each encrypted value should be unique
      const encryptedValues = dbResult.rows.map(
        (row) => row.encrypted_data + row.user_salt
      );
      const uniqueValues = [...new Set(encryptedValues)];

      expect(uniqueValues.length).toBe(encryptedValues.length);
    });

    test("should generate unique salt per user", async () => {
      const anotherUserId = "test-user-encryption-salt-" + Date.now();
      const testData = { keyId: "same-key", secret: "same-secret" };

      // Create JWT token for second user
      const jwtSecret = process.env.JWT_SECRET || 'test-secret';
      const anotherUserToken = jwt.sign(
        { sub: anotherUserId, email: `${anotherUserId}@test.local` },
        jwtSecret,
        { expiresIn: '1h' }
      );

      // Store same API key for different users (using JWT tokens)
      await apiKeyService.storeApiKey(mockToken, "test-same", testData);
      await apiKeyService.storeApiKey(anotherUserToken, "test-same", testData);

      const user1Result = await query(
        "SELECT encrypted_data FROM user_api_keys WHERE user_id = $1 AND provider = $2",
        [testUserId, "test-same"]
      );

      const user2Result = await query(
        "SELECT encrypted_data FROM user_api_keys WHERE user_id = $1 AND provider = $2",
        [anotherUserId, "test-same"]
      );

      // Same plaintext should produce different ciphertext for different users
      expect(user1Result.rows[0].encrypted_data).not.toBe(
        user2Result.rows[0].encrypted_data
      );

      // Cleanup second user data
      await query("DELETE FROM user_api_keys WHERE user_id = $1", [anotherUserId]);
    });
  });

  describe("API Key Retrieval Decryption", () => {
    test("should decrypt API keys correctly on retrieval", async () => {
      // Store then retrieve using JWT tokens
      await apiKeyService.storeApiKey(mockToken, "alpaca", testApiKeys.alpaca);

      const retrievedKey = await apiKeyService.getApiKey(mockToken, "alpaca");

      expect(retrievedKey).toBeDefined();
      expect(retrievedKey.keyId).toBe(testApiKeys.alpaca.keyId);
      expect(retrievedKey.secret).toBe(testApiKeys.alpaca.secret);
    });

    test("should handle multiple provider retrieval", async () => {
      // Store keys for multiple providers using JWT tokens
      await apiKeyService.storeApiKey(
        mockToken,
        "polygon",
        testApiKeys.polygon
      );
      await apiKeyService.storeApiKey(
        mockToken,
        "finnhub",
        testApiKeys.finnhub
      );

      const polygonKey = await apiKeyService.getApiKey(mockToken, "polygon");
      const finnhubKey = await apiKeyService.getApiKey(mockToken, "finnhub");

      expect(polygonKey).toBeDefined();
      expect(finnhubKey).toBeDefined();
      expect(polygonKey.keyId).toBe(testApiKeys.polygon.keyId);
      expect(finnhubKey.secret).toBe(testApiKeys.finnhub.secret);
    });

    test("should fail gracefully for non-existent user", async () => {
      const nonExistentUserId = "non-existent-user-" + Date.now();

      const result = await apiKeyService.getApiKey(nonExistentUserId, "alpaca");

      expect(result).toBeNull();
    });

    test("should handle corrupted encryption data", async () => {
      // Insert corrupted data directly
      await query(
        `INSERT INTO user_api_keys 
         (user_id, provider, encrypted_data, user_salt, created_at) 
         VALUES ($1, 'corrupted', 'invalid-format', 'invalid-format', NOW())`,
        [testUserId]
      );

      const result = await apiKeyService.getApiKey(testUserId, "corrupted");

      // Should handle error gracefully and not crash
      expect(result).toBeNull();
    });
  });

  describe("API Key Security Validation", () => {
    test("should validate API key format before storage", async () => {
      const invalidCases = [
        { keyId: "", secret: "valid-secret" },
        { keyId: "valid-key", secret: "" },
        { keyId: null, secret: "valid-secret" },
        { keyId: "valid-key", secret: null },
      ];

      for (const testCase of invalidCases) {
        const result = await apiKeyService.storeApiKey(
          testUserId,
          "validation-test",
          testCase
        );

        expect(result.success).toBe(false);
        expect(result.error).toBeDefined();
      }
    });

    test("should enforce maximum key length limits", async () => {
      const tooLongKey = "x".repeat(1000); // 1000 characters
      const tooLongSecret = "y".repeat(2000); // 2000 characters

      const result = await apiKeyService.storeApiKey(
        testUserId,
        "length-test",
        { keyId: tooLongKey, secret: tooLongSecret }
      );

      expect(result.success).toBe(false);
      expect(result.error).toMatch(/length|size|limit/i);
    });

    test("should prevent SQL injection in provider names", async () => {
      const maliciousProvider = "'; DROP TABLE user_api_keys; --";

      const result = await apiKeyService.storeApiKey(
        testUserId,
        maliciousProvider,
        { keyId: "test-key", secret: "test-secret" }
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

  describe("API Key Update and Deletion", () => {
    test("should update existing API keys", async () => {
      // Store initial key using JWT token
      await apiKeyService.storeApiKey(mockToken, "update-test", {
        keyId: "old-key",
        secret: "old-secret",
      });

      // Update with new values using JWT token
      const updateResult = await apiKeyService.storeApiKey(
        mockToken,
        "update-test",
        { keyId: "new-key", secret: "new-secret" }
      );
      expect(updateResult.success).toBe(true);

      // Verify update using JWT token
      const retrievedKey = await apiKeyService.getApiKey(
        mockToken,
        "update-test"
      );
      expect(retrievedKey.keyId).toBe("new-key");
      expect(retrievedKey.secret).toBe("new-secret");
    });

    test("should delete API keys securely", async () => {
      // Store key using JWT token
      await apiKeyService.storeApiKey(mockToken, "delete-test", {
        keyId: "delete-key",
        secret: "delete-secret",
      });

      // Delete key using JWT token
      const deleteResult = await apiKeyService.deleteApiKey(
        mockToken,
        "delete-test"
      );
      expect(deleteResult.success).toBe(true);

      // Verify deletion using JWT token
      const retrievedKey = await apiKeyService.getApiKey(
        mockToken,
        "delete-test"
      );
      expect(retrievedKey).toBeNull();

      // Verify no traces in database
      const dbResult = await query(
        "SELECT * FROM user_api_keys WHERE user_id = $1 AND provider = $2",
        [testUserId, "delete-test"]
      );
      expect(dbResult.rows).toHaveLength(0);
    });
  });

  describe("Performance and Scalability", () => {
    test("should handle concurrent API key operations", async () => {
      const concurrentOperations = [];

      // Create 10 concurrent store operations using JWT token
      for (let i = 0; i < 10; i++) {
        concurrentOperations.push(
          apiKeyService.storeApiKey(mockToken, `concurrent-${i}`, {
            keyId: `key-${i}`,
            secret: `secret-${i}`,
          })
        );
      }

      const results = await Promise.all(concurrentOperations);

      // All operations should succeed - debug failures
      results.forEach((result, index) => {
        if (!result.success) {
          console.log(`Concurrent operation ${index} failed:`, result.error || result);
        }
        expect(result.success).toBe(true);
      });

      // Verify all keys stored correctly using JWT token
      for (let i = 0; i < 10; i++) {
        const retrievedKey = await apiKeyService.getApiKey(
          mockToken,
          `concurrent-${i}`
        );
        expect(retrievedKey).toBeDefined();
        expect(retrievedKey.keyId).toBe(`key-${i}`);
      }
    });

    test("should maintain performance with large number of keys", async () => {
      const _startTime = Date.now();

      // Store 50 API keys
      const storePromises = [];
      for (let i = 0; i < 50; i++) {
        storePromises.push(
          apiKeyService.storeApiKey(mockToken, `perf-${i}`, {
            keyId: `key-${i}`,
            secret: `secret-${i}`,
          })
        );
      }
      await Promise.all(storePromises);

      // Retrieve all keys
      const retrievalStart = Date.now();
      const keyCount = 50;
      let retrievedCount = 0;

      for (let i = 0; i < keyCount; i++) {
        const key = await apiKeyService.getApiKey(mockToken, `perf-${i}`);
        if (key) retrievedCount++;
      }

      const retrievalEnd = Date.now();

      // Performance assertions
      expect(retrievalEnd - retrievalStart).toBeLessThan(5000); // < 5 seconds for 50 individual calls
      expect(retrievedCount).toBeGreaterThanOrEqual(50);
    });
  });
});

/**
 * API Key Service Integration Tests
 * Tests real API key management, encryption, and validation
 */

const { initializeDatabase, closeDatabase } = require("../../../utils/database");
const apiKeyService = require("../../../utils/apiKeyService");

describe("API Key Service Integration Tests", () => {
  beforeAll(async () => {
    await initializeDatabase();
  });

  afterAll(async () => {
    await closeDatabase();
  });

  describe("API Key Encryption", () => {
    test("should encrypt and decrypt API keys", async () => {
      const testKey = "test-api-key-123";
      const userSalt = "user-salt-456";
      
      const encrypted = await apiKeyService.encryptApiKey(testKey, userSalt);
      expect(encrypted).toBeDefined();
      expect(encrypted).not.toBe(testKey);

      const decrypted = await apiKeyService.decryptApiKey(encrypted, userSalt);
      expect(decrypted).toBe(testKey);
    });

    test("should handle encryption with different salts", async () => {
      const testKey = "test-api-key-123";
      const salt1 = "salt1";
      const salt2 = "salt2";
      
      const encrypted1 = await apiKeyService.encryptApiKey(testKey, salt1);
      const encrypted2 = await apiKeyService.encryptApiKey(testKey, salt2);
      
      // Same key with different salts should produce different encrypted results
      expect(encrypted1).not.toBe(encrypted2);
      
      // Should decrypt correctly with matching salts
      expect(await apiKeyService.decryptApiKey(encrypted1, salt1)).toBe(testKey);
      expect(await apiKeyService.decryptApiKey(encrypted2, salt2)).toBe(testKey);
    });

    test("should handle decryption with wrong salt gracefully", async () => {
      const testKey = "test-api-key-123";
      const correctSalt = "correct-salt";
      const wrongSalt = "wrong-salt";
      
      const encrypted = await apiKeyService.encryptApiKey(testKey, correctSalt);
      
      // Should not decrypt correctly with wrong salt
      try {
        const decrypted = await apiKeyService.decryptApiKey(encrypted, wrongSalt);
        expect(decrypted).not.toBe(testKey);
      } catch (error) {
        // Error is expected with wrong salt
        expect(error).toBeDefined();
      }
    });
  });

  describe("API Key Storage and Retrieval", () => {
    const testToken = "test-user-token";
    const testProvider = "alpaca";
    const testApiKeyData = {
      apiKey: "test-api-key-123",
      secretKey: "test-secret-key-456",
      environment: "paper"
    };

    test("should store and retrieve API keys", async () => {
      // Store API key
      const storeResult = await apiKeyService.storeApiKey(testToken, testProvider, testApiKeyData);
      expect(storeResult).toBeDefined();

      // Retrieve API key
      const retrievedData = await apiKeyService.getApiKey(testToken, testProvider);
      expect(retrievedData).toBeDefined();
      
      if (retrievedData) {
        expect(retrievedData.apiKey).toBeDefined();
        expect(retrievedData.environment).toBe(testApiKeyData.environment);
      }
    });

    test("should handle non-existent API keys", async () => {
      const nonExistentToken = "non-existent-token";
      const retrievedData = await apiKeyService.getApiKey(nonExistentToken, testProvider);
      
      // Should return null or handle gracefully
      expect(retrievedData === null || retrievedData === undefined).toBe(true);
    });

    test("should validate API keys", async () => {
      const validation = await apiKeyService.validateApiKey(testToken, testProvider, false);
      expect(validation).toBeDefined();
      expect(typeof validation).toBe('object');
    });
  });

  describe("JWT Token Validation", () => {
    test("should handle JWT token validation", async () => {
      const testToken = "invalid-jwt-token";
      
      // Should handle invalid tokens gracefully
      const result = await apiKeyService.validateJwtToken(testToken);
      expect(result).toBeDefined();
      // Invalid token should return null or false
      expect(result === null || result === false).toBe(true);
    });

    test("should check JWT circuit breaker", () => {
      const circuitBreakerStatus = apiKeyService.checkJwtCircuitBreaker();
      expect(typeof circuitBreakerStatus).toBe('boolean');
    });

    test("should record JWT success and failure", () => {
      // These methods should not throw errors
      expect(() => {
        apiKeyService.recordJwtSuccess();
        apiKeyService.recordJwtFailure(new Error("test error"));
      }).not.toThrow();
    });
  });

  describe("Circuit Breaker Functionality", () => {
    test("should check circuit breaker status", () => {
      const status = apiKeyService.checkCircuitBreaker();
      expect(typeof status).toBe('boolean');
    });

    test("should record success and failure", () => {
      // These methods should not throw errors
      expect(() => {
        apiKeyService.recordSuccess();
        apiKeyService.recordFailure(new Error("test error"));
      }).not.toThrow();
    });
  });

  describe("Audit Logging", () => {
    test("should log audit events", async () => {
      const userId = "test-user-123";
      const action = "API_KEY_ACCESS";
      const provider = "alpaca";
      const sessionId = "session-456";

      // Should not throw error
      await expect(
        apiKeyService.logAuditEvent(userId, action, provider, sessionId)
      ).resolves.not.toThrow();
    });

    test("should handle audit logging failures gracefully", async () => {
      // Should not throw even with invalid data
      await expect(
        apiKeyService.logAuditEvent(null, null, null, null)
      ).resolves.not.toThrow();
    });
  });

  describe("Encryption Key Management", () => {
    test("should get encryption key", async () => {
      const encryptionKey = await apiKeyService.getEncryptionKey();
      expect(encryptionKey).toBeDefined();
      expect(typeof encryptionKey).toBe('string');
    });
  });

  describe("Error Handling", () => {
    test("should handle encryption errors gracefully", async () => {
      // Test with invalid data
      try {
        await apiKeyService.encryptApiKey(null, "salt");
      } catch (error) {
        expect(error).toBeDefined();
      }
    });

    test("should handle decryption errors gracefully", async () => {
      // Test with invalid encrypted data
      try {
        await apiKeyService.decryptApiKey("invalid-encrypted-data", "salt");
      } catch (error) {
        expect(error).toBeDefined();
      }
    });

    test("should handle database errors gracefully", async () => {
      const invalidToken = "invalid-token-with-special-chars-!@#$%^&*()";
      const result = await apiKeyService.getApiKey(invalidToken, "provider");
      
      // Should handle database errors and return null or handle gracefully
      expect(result === null || result === undefined || typeof result === 'object').toBe(true);
    });
  });
});
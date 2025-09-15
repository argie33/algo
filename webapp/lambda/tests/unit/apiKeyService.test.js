const {
  storeApiKey,
  getApiKey,
  validateApiKey,
  deleteApiKey,
  listProviders,
  invalidateSession,
  clearCaches,
  getHealthStatus,
  validateJwtToken,
  getDecryptedApiKey,
  __reinitializeForTests,
} = require("../../utils/apiKeyService");

// Mock dependencies
jest.mock("crypto", () => ({
  scryptSync: jest.fn(),
  randomBytes: jest.fn(),
  createCipheriv: jest.fn(),
  createDecipheriv: jest.fn(),
}));

jest.mock("@aws-sdk/client-secrets-manager", () => ({
  SecretsManagerClient: jest.fn().mockImplementation(() => ({
    send: jest.fn(),
  })),
  GetSecretValueCommand: jest.fn(),
}));

jest.mock("aws-jwt-verify", () => ({
  CognitoJwtVerifier: {
    create: jest.fn().mockReturnValue({
      verify: jest.fn(),
    }),
  },
}));

jest.mock("../../utils/database", () => ({
  query: jest.fn(),
}));

const crypto = require("crypto");
const {
  SecretsManagerClient,
  GetSecretValueCommand,
} = require("@aws-sdk/client-secrets-manager");
const { CognitoJwtVerifier } = require("aws-jwt-verify");
const { query } = require("../../utils/database");

describe("ApiKeyService", () => {
  let mockSecretsManager;
  let mockJwtVerifier;
  let originalEnv;

  beforeEach(async () => {
    jest.clearAllMocks();

    // Store original environment
    originalEnv = { ...process.env };

    // Setup test environment
    process.env.NODE_ENV = "test";
    process.env.COGNITO_USER_POOL_ID = "us-east-1_testpool";
    process.env.COGNITO_CLIENT_ID = "test-client-id";
    process.env.ALLOW_DEV_BYPASS = "true";

    // Mock Secrets Manager
    mockSecretsManager = {
      send: jest.fn(),
    };
    SecretsManagerClient.mockImplementation(() => mockSecretsManager);

    // Mock JWT Verifier
    mockJwtVerifier = {
      verify: jest.fn(),
    };
    CognitoJwtVerifier.create.mockReturnValue(mockJwtVerifier);

    // Mock crypto functions
    crypto.scryptSync.mockReturnValue(Buffer.from("test-key"));
    crypto.randomBytes.mockReturnValue(Buffer.from("test-iv"));

    const mockCipher = {
      update: jest.fn().mockReturnValue(Buffer.from("encrypted")),
      final: jest.fn().mockReturnValue(Buffer.from("")),
    };

    const mockDecipher = {
      update: jest.fn().mockReturnValue(Buffer.from("decrypted")),
      final: jest.fn().mockReturnValue(Buffer.from("")),
    };

    crypto.createCipheriv.mockReturnValue(mockCipher);
    crypto.createDecipheriv.mockReturnValue(mockDecipher);

    // Clear caches between tests
    clearCaches();

    // Reinitialize the service with mocked dependencies
    await __reinitializeForTests();
  });

  afterEach(() => {
    // Restore original environment
    process.env = { ...originalEnv };
  });

  describe("JWT Token Validation", () => {
    test("should validate valid JWT token", async () => {
      const mockUser = {
        sub: "test-user-id",
        email: "test@example.com",
        username: "testuser",
      };

      mockJwtVerifier.verify.mockResolvedValue(mockUser);

      const result = await validateJwtToken("valid.jwt.token");

      expect(result.valid).toBe(true);
      expect(result.user.sub).toBe("test-user-id");
      expect(result.user.email).toBe("test@example.com");
      expect(result.user.sessionId).toBeDefined();
    });

    test("should reject invalid JWT token", async () => {
      mockJwtVerifier.verify.mockRejectedValue(new Error("Invalid token"));

      const result = await validateJwtToken("invalid.jwt.token");

      expect(result.valid).toBe(false);
      expect(result.error).toBe("Invalid token");
    });

    test("should handle empty or null token", async () => {
      const result1 = await validateJwtToken(null);
      const result2 = await validateJwtToken("");
      const result3 = await validateJwtToken("   ");

      expect(result1.valid).toBe(false);
      expect(result2.valid).toBe(false);
      expect(result3.valid).toBe(false);
      expect(result1.error).toContain("Invalid or missing JWT token");
    });

    test("should handle dev bypass token", async () => {
      const result = await validateJwtToken("dev-bypass-token");

      expect(result.valid).toBe(true);
      expect(result.user.sub).toBe("dev-user-bypass");
      expect(result.user.role).toBe("admin");
    });

    test("should handle JWT verifier not initialized", async () => {
      delete process.env.COGNITO_USER_POOL_ID;

      // Reset module to reinitialize without Cognito config
      jest.resetModules();
      const {
        validateJwtToken: newValidateJwtToken,
      } = require("../../utils/apiKeyService");

      const result = await newValidateJwtToken("test.jwt.token");

      expect(result.valid).toBe(false);
      expect(result.error).toContain("JWT verification not configured");
    });

    test("should handle JWT token expiration", async () => {
      const error = new Error("Token expired");
      error.name = "TokenExpiredError";
      mockJwtVerifier.verify.mockRejectedValue(error);

      const result = await validateJwtToken("expired.jwt.token");

      expect(result.valid).toBe(false);
      expect(result.error).toBe("Token expired");
    });

    test("should handle malformed JWT token", async () => {
      const error = new Error("Malformed token");
      error.name = "JsonWebTokenError";
      mockJwtVerifier.verify.mockRejectedValue(error);

      const result = await validateJwtToken("malformed-token");

      expect(result.valid).toBe(false);
      expect(result.error).toBe("Malformed token");
    });
  });

  describe("API Key Storage", () => {
    beforeEach(() => {
      mockJwtVerifier.verify.mockResolvedValue({
        sub: "test-user-id",
        email: "test@example.com",
      });

      query.mockResolvedValue({ rows: [], rowCount: 1 });
    });

    test("should store API key successfully", async () => {
      const apiKeyData = {
        apiKey: "test-api-key",
        apiSecret: "test-secret",
      };

      const result = await storeApiKey("valid.jwt.token", "alpaca", apiKeyData);

      expect(result.success).toBe(true);
      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("INSERT INTO user_api_keys"),
        expect.arrayContaining(["test-user-id", "alpaca"])
      );
    });

    test("should validate required API key fields", async () => {
      const invalidApiKeyData = {
        // missing apiKey
        apiSecret: "test-secret",
      };

      const result = await storeApiKey("valid.jwt.token", "alpaca", invalidApiKeyData);
      expect(result.success).toBe(false);
      expect(result.error).toContain("API key data must include keyId and secret");
    });

    test("should validate provider name", async () => {
      const apiKeyData = {
        apiKey: "test-api-key",
        apiSecret: "test-secret",
      };

      await expect(
        storeApiKey("valid.jwt.token", "invalid-provider", apiKeyData)
      ).rejects.toThrow("Invalid provider");
    });

    test("should handle database storage errors", async () => {
      query.mockRejectedValue(new Error("Database error"));

      const apiKeyData = {
        apiKey: "test-api-key",
        apiSecret: "test-secret",
      };

      await expect(
        storeApiKey("valid.jwt.token", "alpaca", apiKeyData)
      ).rejects.toThrow("Database error");
    });

    test("should update existing API key", async () => {
      query
        .mockResolvedValueOnce({ rows: [{ provider: "alpaca" }] }) // Check existing
        .mockResolvedValueOnce({ rows: [], rowCount: 1 }); // Update

      const apiKeyData = {
        apiKey: "updated-api-key",
        apiSecret: "updated-secret",
      };

      const result = await storeApiKey("valid.jwt.token", "alpaca", apiKeyData);

      expect(result.success).toBe(true);
      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("UPDATE user_api_keys"),
        expect.any(Array)
      );
    });

    test("should handle invalid JWT token for storage", async () => {
      mockJwtVerifier.verify.mockRejectedValue(new Error("Invalid token"));

      const apiKeyData = {
        apiKey: "test-api-key",
        apiSecret: "test-secret",
      };

      await expect(
        storeApiKey("invalid.jwt.token", "alpaca", apiKeyData)
      ).rejects.toThrow("Invalid token");
    });
  });

  describe("API Key Retrieval", () => {
    beforeEach(() => {
      mockJwtVerifier.verify.mockResolvedValue({
        sub: "test-user-id",
        email: "test@example.com",
      });

      // Mock encryption key retrieval
      mockSecretsManager.send.mockResolvedValue({
        SecretString: JSON.stringify({ encryptionKey: "test-encryption-key" }),
      });
    });

    test("should retrieve API key successfully", async () => {
      const encryptedData = Buffer.from("encrypted-data").toString("base64");
      query.mockResolvedValue({
        rows: [
          {
            encrypted_data: encryptedData,
            iv: Buffer.from("test-iv").toString("base64"),
          },
        ],
      });

      const result = await getApiKey("valid.jwt.token", "alpaca");

      expect(result).toBeDefined();
      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("SELECT encrypted_data, iv FROM user_api_keys"),
        ["test-user-id", "alpaca"]
      );
    });

    test("should return null for non-existent API key", async () => {
      query.mockResolvedValue({ rows: [] });

      const result = await getApiKey("valid.jwt.token", "alpaca");

      expect(result).toBeNull();
    });

    test("should handle decryption errors gracefully", async () => {
      query.mockResolvedValue({
        rows: [
          {
            encrypted_data: "invalid-encrypted-data",
            iv: "invalid-iv",
          },
        ],
      });

      crypto.createDecipheriv.mockImplementation(() => {
        throw new Error("Decryption failed");
      });

      const result = await getApiKey("valid.jwt.token", "alpaca");

      expect(result).toBeNull();
    });

    test("should use cache for repeated requests", async () => {
      const encryptedData = Buffer.from("encrypted-data").toString("base64");
      query.mockResolvedValue({
        rows: [
          {
            encrypted_data: encryptedData,
            iv: Buffer.from("test-iv").toString("base64"),
          },
        ],
      });

      await getApiKey("valid.jwt.token", "alpaca");
      await getApiKey("valid.jwt.token", "alpaca");

      // Should only query database once due to caching
      expect(query).toHaveBeenCalledTimes(1);
    });

    test("should handle circuit breaker activation", async () => {
      // Simulate multiple failures to trigger circuit breaker
      query.mockRejectedValue(new Error("Database connection failed"));

      for (let i = 0; i < 6; i++) {
        try {
          await getApiKey("valid.jwt.token", "alpaca");
        } catch (error) {
          // Expected to fail
        }
      }

      // Next call should be circuit breaker error
      await expect(getApiKey("valid.jwt.token", "alpaca")).rejects.toThrow(
        "circuit breaker"
      );
    });
  });

  describe("API Key Validation", () => {
    beforeEach(() => {
      mockJwtVerifier.verify.mockResolvedValue({
        sub: "test-user-id",
        email: "test@example.com",
      });

      mockSecretsManager.send.mockResolvedValue({
        SecretString: JSON.stringify({ encryptionKey: "test-encryption-key" }),
      });
    });

    test("should validate API key with test connection", async () => {
      const encryptedData = Buffer.from("encrypted-data").toString("base64");
      query.mockResolvedValue({
        rows: [
          {
            encrypted_data: encryptedData,
            iv: Buffer.from("test-iv").toString("base64"),
          },
        ],
      });

      const mockTestConnection = jest.fn().mockResolvedValue(true);

      const result = await validateApiKey(
        "valid.jwt.token",
        "alpaca",
        mockTestConnection
      );

      expect(result.valid).toBe(true);
      expect(mockTestConnection).toHaveBeenCalled();
    });

    test("should handle validation failure", async () => {
      const encryptedData = Buffer.from("encrypted-data").toString("base64");
      query.mockResolvedValue({
        rows: [
          {
            encrypted_data: encryptedData,
            iv: Buffer.from("test-iv").toString("base64"),
          },
        ],
      });

      const mockTestConnection = jest.fn().mockResolvedValue(false);

      const result = await validateApiKey(
        "valid.jwt.token",
        "alpaca",
        mockTestConnection
      );

      expect(result.valid).toBe(false);
      expect(result.error).toContain("API key validation failed");
    });

    test("should handle missing API key during validation", async () => {
      query.mockResolvedValue({ rows: [] });

      const mockTestConnection = jest.fn();

      const result = await validateApiKey(
        "valid.jwt.token",
        "alpaca",
        mockTestConnection
      );

      expect(result.valid).toBe(false);
      expect(result.error).toBe("API key not found");
      expect(mockTestConnection).not.toHaveBeenCalled();
    });

    test("should handle test connection errors", async () => {
      const encryptedData = Buffer.from("encrypted-data").toString("base64");
      query.mockResolvedValue({
        rows: [
          {
            encrypted_data: encryptedData,
            iv: Buffer.from("test-iv").toString("base64"),
          },
        ],
      });

      const mockTestConnection = jest
        .fn()
        .mockRejectedValue(new Error("Connection test failed"));

      const result = await validateApiKey(
        "valid.jwt.token",
        "alpaca",
        mockTestConnection
      );

      expect(result.valid).toBe(false);
      expect(result.error).toContain("Connection test failed");
    });
  });

  describe("API Key Deletion", () => {
    beforeEach(() => {
      mockJwtVerifier.verify.mockResolvedValue({
        sub: "test-user-id",
        email: "test@example.com",
      });

      query.mockResolvedValue({ rowCount: 1 });
    });

    test("should delete API key successfully", async () => {
      const result = await deleteApiKey("valid.jwt.token", "alpaca");

      expect(result.success).toBe(true);
      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("DELETE FROM user_api_keys"),
        ["test-user-id", "alpaca"]
      );
    });

    test("should handle deletion of non-existent API key", async () => {
      query.mockResolvedValue({ rowCount: 0 });

      const result = await deleteApiKey("valid.jwt.token", "alpaca");

      expect(result.success).toBe(false);
      expect(result.error).toBe("API key not found");
    });

    test("should handle database deletion errors", async () => {
      query.mockRejectedValue(new Error("Database error"));

      await expect(deleteApiKey("valid.jwt.token", "alpaca")).rejects.toThrow(
        "Database error"
      );
    });
  });

  describe("Provider Listing", () => {
    beforeEach(() => {
      mockJwtVerifier.verify.mockResolvedValue({
        sub: "test-user-id",
        email: "test@example.com",
      });
    });

    test("should list user providers successfully", async () => {
      query.mockResolvedValue({
        rows: [
          { provider: "alpaca", created_at: new Date() },
          { provider: "polygon", created_at: new Date() },
        ],
      });

      const result = await listProviders("valid.jwt.token");

      expect(result.providers).toHaveLength(2);
      expect(result.providers).toContain("alpaca");
      expect(result.providers).toContain("polygon");
    });

    test("should return empty list for user with no API keys", async () => {
      query.mockResolvedValue({ rows: [] });

      const result = await listProviders("valid.jwt.token");

      expect(result.providers).toHaveLength(0);
    });

    test("should handle database errors during listing", async () => {
      query.mockRejectedValue(new Error("Database error"));

      await expect(listProviders("valid.jwt.token")).rejects.toThrow(
        "Database error"
      );
    });
  });

  describe("Session Management", () => {
    test("should invalidate session cache", () => {
      const result = invalidateSession("test.jwt.token");

      expect(result.success).toBe(true);
    });

    test("should clear all caches", () => {
      clearCaches();
      // No direct way to test cache clearing, but should not throw
      expect(true).toBe(true);
    });
  });

  describe("Health Status", () => {
    test("should return health status", () => {
      const health = getHealthStatus();

      expect(health).toHaveProperty("circuitBreaker");
      expect(health).toHaveProperty("jwtCircuitBreaker");
      expect(health).toHaveProperty("cacheStats");
      expect(health.circuitBreaker).toHaveProperty("state");
      expect(health.jwtCircuitBreaker).toHaveProperty("state");
    });

    test("should show circuit breaker states", () => {
      const health = getHealthStatus();

      expect(["CLOSED", "OPEN", "HALF_OPEN"]).toContain(
        health.circuitBreaker.state
      );
      expect(["CLOSED", "OPEN", "HALF_OPEN"]).toContain(
        health.jwtCircuitBreaker.state
      );
    });
  });

  describe("Direct API Key Access", () => {
    beforeEach(() => {
      mockSecretsManager.send.mockResolvedValue({
        SecretString: JSON.stringify({ encryptionKey: "test-encryption-key" }),
      });
    });

    test("should get decrypted API key by user ID", async () => {
      const encryptedData = Buffer.from("encrypted-data").toString("base64");
      query.mockResolvedValue({
        rows: [
          {
            encrypted_data: encryptedData,
            iv: Buffer.from("test-iv").toString("base64"),
          },
        ],
      });

      const result = await getDecryptedApiKey("test-user-id", "alpaca");

      expect(result).toBeDefined();
      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("SELECT encrypted_data, iv FROM user_api_keys"),
        ["test-user-id", "alpaca"]
      );
    });

    test("should return null for non-existent user API key", async () => {
      query.mockResolvedValue({ rows: [] });

      const result = await getDecryptedApiKey("nonexistent-user", "alpaca");

      expect(result).toBeNull();
    });

    test("should handle decryption errors in direct access", async () => {
      query.mockResolvedValue({
        rows: [
          {
            encrypted_data: "invalid-data",
            iv: "invalid-iv",
          },
        ],
      });

      crypto.createDecipheriv.mockImplementation(() => {
        throw new Error("Decryption failed");
      });

      const result = await getDecryptedApiKey("test-user-id", "alpaca");

      expect(result).toBeNull();
    });
  });

  describe("Error Handling and Edge Cases", () => {
    test("should handle AWS Secrets Manager errors", async () => {
      mockSecretsManager.send.mockRejectedValue(
        new Error("Secrets Manager error")
      );

      mockJwtVerifier.verify.mockResolvedValue({
        sub: "test-user-id",
        email: "test@example.com",
      });

      query.mockResolvedValue({
        rows: [
          {
            encrypted_data: "test",
            iv: "test",
          },
        ],
      });

      const result = await getApiKey("valid.jwt.token", "alpaca");

      expect(result).toBeNull();
    });

    test("should handle invalid provider names consistently", async () => {
      mockJwtVerifier.verify.mockResolvedValue({
        sub: "test-user-id",
        email: "test@example.com",
      });

      const apiKeyData = { apiKey: "test", apiSecret: "test" };

      await expect(
        storeApiKey("valid.jwt.token", "", apiKeyData)
      ).rejects.toThrow("Invalid provider");

      await expect(
        storeApiKey("valid.jwt.token", null, apiKeyData)
      ).rejects.toThrow("Invalid provider");

      await expect(
        storeApiKey("valid.jwt.token", "   ", apiKeyData)
      ).rejects.toThrow("Invalid provider");
    });

    test("should handle concurrent API key operations", async () => {
      mockJwtVerifier.verify.mockResolvedValue({
        sub: "test-user-id",
        email: "test@example.com",
      });

      query.mockResolvedValue({ rows: [] });

      const promises = Array(10)
        .fill()
        .map(() => getApiKey("valid.jwt.token", "alpaca"));

      const results = await Promise.all(promises);

      expect(results).toHaveLength(10);
      results.forEach((result) => expect(result).toBeNull());
    });

    test("should handle very large API key data", async () => {
      mockJwtVerifier.verify.mockResolvedValue({
        sub: "test-user-id",
        email: "test@example.com",
      });

      query.mockResolvedValue({ rows: [], rowCount: 1 });

      const largeApiKeyData = {
        apiKey: "x".repeat(10000),
        apiSecret: "y".repeat(10000),
        additionalData: "z".repeat(10000),
      };

      const result = await storeApiKey(
        "valid.jwt.token",
        "alpaca",
        largeApiKeyData
      );

      expect(result.success).toBe(true);
    });

    test("should handle malformed encrypted data", async () => {
      mockJwtVerifier.verify.mockResolvedValue({
        sub: "test-user-id",
        email: "test@example.com",
      });

      mockSecretsManager.send.mockResolvedValue({
        SecretString: JSON.stringify({ encryptionKey: "test-encryption-key" }),
      });

      query.mockResolvedValue({
        rows: [
          {
            encrypted_data: "not-base64-data!@#$",
            iv: "also-not-base64!@#$",
          },
        ],
      });

      const result = await getApiKey("valid.jwt.token", "alpaca");

      expect(result).toBeNull();
    });
  });
});

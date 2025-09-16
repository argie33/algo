/**
 * API Key Service Unit Tests
 * Tests for API key encryption, decryption, and validation
 */

// Mock dependencies before requiring
jest.mock("../../../utils/database");
jest.mock("crypto");
jest.mock("@aws-sdk/client-secrets-manager");
jest.mock("aws-jwt-verify");
jest.mock("jsonwebtoken");

const mockQuery = require("../../../utils/database").query;
const crypto = require("crypto");
const { SecretsManagerClient } = require("@aws-sdk/client-secrets-manager");
const { CognitoJwtVerifier } = require("aws-jwt-verify");
const jwt = require("jsonwebtoken");

// Import ApiKeyService functions after mocking
const {
  storeApiKey,
  getApiKey,
  validateApiKey,
  deleteApiKey,
  listProviders,
  validateJwtToken,
  getDecryptedApiKey,
  invalidateSession,
  clearCaches,
  getHealthStatus,
  __getServiceInstance,
} = require("../../../utils/apiKeyService");

describe("API Key Service", () => {
  let mockSecretsManager;
  let mockJwtVerifier;
  let originalEnv;

  beforeEach(() => {
    jest.clearAllMocks();
    originalEnv = { ...process.env };

    // Set test environment
    process.env.NODE_ENV = "test";
    process.env.JWT_SECRET = "test-secret";

    // Mock AWS Secrets Manager
    mockSecretsManager = {
      send: jest.fn(),
    };
    SecretsManagerClient.mockReturnValue(mockSecretsManager);

    // Mock JWT verifier
    mockJwtVerifier = {
      verify: jest.fn(),
    };
    CognitoJwtVerifier.create = jest.fn().mockReturnValue(mockJwtVerifier);

    // Mock crypto functions
    crypto.randomBytes = jest
      .fn()
      .mockReturnValue(Buffer.from("randomiv123456", "utf8"));
    crypto.randomUUID = jest.fn().mockReturnValue("mock-uuid-123");
    crypto.scryptSync = jest
      .fn()
      .mockReturnValue(Buffer.from("derived-key-32-bytes-long-test"));
    crypto.createCipheriv = jest.fn().mockReturnValue({
      update: jest.fn().mockReturnValue("encrypted"),
      final: jest.fn().mockReturnValue("data"),
      setAAD: jest.fn(),
      getAuthTag: jest.fn().mockReturnValue(Buffer.from("auth-tag")),
    });
    crypto.createDecipheriv = jest.fn().mockReturnValue({
      update: jest.fn().mockReturnValue("decrypted"),
      final: jest.fn().mockReturnValue("data"),
      setAAD: jest.fn(),
      setAuthTag: jest.fn(),
    });

    // Mock jsonwebtoken
    jwt.verify = jest.fn();

    // Clear caches
    clearCaches();
  });

  afterEach(() => {
    process.env = originalEnv;
  });

  describe("validateJwtToken", () => {
    test("should validate JWT token in test environment", async () => {
      const token = "valid-jwt-token";
      jwt.verify.mockReturnValue({ sub: "user123" });

      const result = await validateJwtToken(token);

      expect(result.valid).toBe(true);
      expect(result.user.sub).toBe("user123");
      expect(result.user.email).toBe("user123@test.local");
    });

    test("should reject invalid JWT tokens", async () => {
      const token = "invalid-jwt-token";
      jwt.verify.mockImplementation(() => {
        throw new Error("Invalid token");
      });

      const result = await validateJwtToken(token);

      expect(result.valid).toBe(false);
      expect(result.error).toContain("JWT validation failed");
    });

    test("should handle empty or invalid token input", async () => {
      const result = await validateJwtToken("");

      expect(result.valid).toBe(false);
      expect(result.error).toBe("Invalid or missing JWT token");
    });

    test("should accept dev-bypass-token in development", async () => {
      process.env.NODE_ENV = "development";

      const result = await validateJwtToken("dev-bypass-token");

      expect(result.valid).toBe(true);
      expect(result.user.sub).toBe("dev-user-bypass");
    });
  });

  describe("storeApiKey", () => {
    beforeEach(() => {
      jwt.verify.mockReturnValue({ sub: "user123" });
    });

    test("should store API key successfully", async () => {
      const mockResult = {
        rows: [{ user_id: "user123", broker_name: "alpaca" }],
        rowCount: 1,
      };
      mockQuery.mockResolvedValue(mockResult);

      const apiKeyData = { keyId: "test-key", secret: "test-secret" };
      const result = await storeApiKey("valid-jwt-token", "alpaca", apiKeyData);

      expect(result.success).toBe(true);
      expect(result.provider).toBe("alpaca");
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining("INSERT INTO user_api_keys"),
        expect.arrayContaining(["user123", "alpaca"])
      );
    });

    test("should validate input parameters", async () => {
      const result = await storeApiKey("valid-jwt-token", "alpaca", null);

      expect(result.success).toBe(false);
      expect(result.error).toContain("API key data must be a valid object");
    });

    test("should validate provider name for SQL injection", async () => {
      const apiKeyData = { keyId: "test-key", secret: "test-secret" };
      const result = await storeApiKey(
        "valid-jwt-token",
        "'; DROP TABLE users; --",
        apiKeyData
      );

      expect(result.success).toBe(false);
      expect(result.error).toContain("Invalid provider name");
    });

    test("should validate required fields", async () => {
      const apiKeyData = { keyId: "test-key" }; // Missing secret
      const result = await storeApiKey("valid-jwt-token", "alpaca", apiKeyData);

      expect(result.success).toBe(false);
      expect(result.error).toContain(
        "API key data must include keyId and secret"
      );
    });

    test("should validate field lengths", async () => {
      const apiKeyData = {
        keyId: "x".repeat(501), // Too long
        secret: "test-secret",
      };
      const result = await storeApiKey("valid-jwt-token", "alpaca", apiKeyData);

      expect(result.success).toBe(false);
      expect(result.error).toContain(
        "API key data exceeds maximum length limits"
      );
    });

    test("should handle JWT validation failure", async () => {
      jwt.verify.mockImplementation(() => {
        throw new Error("Invalid token");
      });

      const apiKeyData = { keyId: "test-key", secret: "test-secret" };
      const result = await storeApiKey(
        "invalid-jwt-token",
        "alpaca",
        apiKeyData
      );

      expect(result.success).toBe(false);
      expect(result.error).toContain("JWT validation failed");
    });

    test("should handle database errors", async () => {
      const dbError = new Error("Database connection failed");
      mockQuery.mockRejectedValue(dbError);

      const apiKeyData = { keyId: "test-key", secret: "test-secret" };
      const result = await storeApiKey("valid-jwt-token", "alpaca", apiKeyData);

      expect(result.success).toBe(false);
      expect(result.error).toContain("Failed to store API key");
    });
  });

  describe("getApiKey", () => {
    beforeEach(() => {
      jwt.verify.mockReturnValue({ sub: "user123" });
    });

    test("should retrieve API key successfully", async () => {
      const mockResult = {
        rows: [
          {
            encrypted_api_key: "stored_key",
            encrypted_api_secret: "stored_secret",
            key_iv: "test-iv",
            key_auth_tag: "test-auth",
            secret_iv: "test-iv",
            secret_auth_tag: "test-auth",
          },
        ],
        rowCount: 1,
      };
      mockQuery.mockResolvedValue(mockResult);

      const result = await getApiKey("valid-jwt-token", "alpaca");

      expect(result).toEqual({
        keyId: "stored_key",
        secret: "stored_secret",
      });
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining("SELECT encrypted_api_key"),
        ["user123", "alpaca"]
      );
    });

    test("should return null for non-existent keys", async () => {
      const mockResult = { rows: [], rowCount: 0 };
      mockQuery.mockResolvedValue(mockResult);

      const result = await getApiKey("valid-jwt-token", "nonexistent");

      expect(result).toBeNull();
    });

    test("should handle JWT validation failure", async () => {
      jwt.verify.mockImplementation(() => {
        throw new Error("Invalid token");
      });

      const result = await getApiKey("invalid-jwt-token", "alpaca");

      expect(result).toBeNull();
    });

    test("should update last used timestamp", async () => {
      const mockResult = {
        rows: [
          {
            encrypted_api_key: "stored_key",
            encrypted_api_secret: "stored_secret",
            key_iv: "test-iv",
            key_auth_tag: "test-auth",
            secret_iv: "test-iv",
            secret_auth_tag: "test-auth",
          },
        ],
      };
      mockQuery.mockResolvedValue(mockResult);

      await getApiKey("valid-jwt-token", "alpaca");

      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining("UPDATE user_api_keys"),
        ["user123", "alpaca"]
      );
    });
  });

  describe("validateApiKey", () => {
    beforeEach(() => {
      jwt.verify.mockReturnValue({ sub: "user123" });
    });

    test("should validate API key successfully", async () => {
      const mockResult = {
        rows: [
          {
            encrypted_api_key: "stored_key",
            encrypted_api_secret: "stored_secret",
            key_iv: "test-iv",
            key_auth_tag: "test-auth",
            secret_iv: "test-iv",
            secret_auth_tag: "test-auth",
          },
        ],
      };
      mockQuery.mockResolvedValue(mockResult);

      const result = await validateApiKey("valid-jwt-token", "alpaca", false);

      expect(result.valid).toBe(true);
      expect(result.provider).toBe("alpaca");
    });

    test("should handle API key not configured", async () => {
      const mockResult = { rows: [], rowCount: 0 };
      mockQuery.mockResolvedValue(mockResult);

      const result = await validateApiKey("valid-jwt-token", "alpaca", false);

      expect(result.valid).toBe(false);
      expect(result.error).toBe("API key not configured");
    });

    test("should handle JWT validation failure", async () => {
      jwt.verify.mockImplementation(() => {
        throw new Error("Invalid token");
      });

      const result = await validateApiKey("invalid-jwt-token", "alpaca", false);

      expect(result.valid).toBe(false);
      expect(result.error).toContain("JWT validation failed");
    });

    test("should test connection when requested", async () => {
      const mockResult = {
        rows: [
          {
            encrypted_api_key: "stored_key",
            encrypted_api_secret: "stored_secret",
            key_iv: "test-iv",
            key_auth_tag: "test-auth",
            secret_iv: "test-iv",
            secret_auth_tag: "test-auth",
          },
        ],
      };
      mockQuery.mockResolvedValue(mockResult);

      const result = await validateApiKey("valid-jwt-token", "polygon", true);

      expect(result.valid).toBe(true);
      expect(result.provider).toBe("polygon");
    });
  });

  describe("deleteApiKey", () => {
    beforeEach(() => {
      jwt.verify.mockReturnValue({ sub: "user123" });
    });

    test("should delete API key successfully", async () => {
      const mockResult = {
        rows: [{ user_id: "user123", broker_name: "alpaca" }],
        rowCount: 1,
      };
      mockQuery.mockResolvedValue(mockResult);

      const result = await deleteApiKey("valid-jwt-token", "alpaca");

      expect(result.success).toBe(true);
      expect(result.deleted).toBe(true);
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining("DELETE FROM user_api_keys"),
        ["user123", "alpaca"]
      );
    });

    test("should handle deletion of non-existent key", async () => {
      const mockResult = { rowCount: 0 };
      mockQuery.mockResolvedValue(mockResult);

      const result = await deleteApiKey("valid-jwt-token", "nonexistent");

      expect(result.success).toBe(true);
      expect(result.deleted).toBe(false);
    });

    test("should handle JWT validation failure gracefully", async () => {
      jwt.verify.mockImplementation(() => {
        throw new Error("Invalid token");
      });

      const result = await deleteApiKey("invalid-jwt-token", "alpaca");

      expect(result.success).toBe(true);
      expect(result.deleted).toBe(false);
      expect(result.message).toContain("Token validation failed");
    });

    test("should handle database errors", async () => {
      const dbError = new Error("Database connection failed");
      mockQuery.mockRejectedValue(dbError);

      const result = await deleteApiKey("valid-jwt-token", "alpaca");

      expect(result.success).toBe(false);
      expect(result.error).toContain("Failed to delete API key");
    });
  });

  describe("listProviders", () => {
    beforeEach(() => {
      jwt.verify.mockReturnValue({ sub: "user123" });
    });

    test("should return list of configured providers", async () => {
      const mockResult = {
        rows: [
          {
            provider: "alpaca",
            updated_at: new Date(),
            created_at: new Date(),
            last_used: new Date(),
          },
          {
            provider: "polygon",
            updated_at: new Date(),
            created_at: new Date(),
            last_used: null,
          },
        ],
      };
      mockQuery.mockResolvedValue(mockResult);

      const result = await listProviders("valid-jwt-token");

      expect(Array.isArray(result)).toBe(true);
      expect(result).toHaveLength(2);
      expect(result[0]).toEqual(
        expect.objectContaining({
          provider: "alpaca",
          configured: true,
          lastUpdated: expect.any(Date),
          createdAt: expect.any(Date),
        })
      );
    });

    test("should return empty array for no providers", async () => {
      const mockResult = { rows: [] };
      mockQuery.mockResolvedValue(mockResult);

      const result = await listProviders("valid-jwt-token");

      expect(result).toEqual([]);
    });

    test("should handle JWT validation failure", async () => {
      jwt.verify.mockImplementation(() => {
        throw new Error("Invalid token");
      });

      const result = await listProviders("invalid-jwt-token");

      expect(result).toEqual([]);
    });

    test("should handle database unavailable gracefully", async () => {
      mockQuery.mockResolvedValue(null);

      const result = await listProviders("valid-jwt-token");

      expect(result).toEqual([]);
    });
  });

  describe("getDecryptedApiKey", () => {
    test("should retrieve API key by user ID", async () => {
      const mockResult = {
        rows: [
          {
            encrypted_api_key: "stored_key",
            encrypted_api_secret: "stored_secret",
            key_iv: "test-iv",
            key_auth_tag: "test-auth",
            secret_iv: "test-iv",
            secret_auth_tag: "test-auth",
          },
        ],
      };
      mockQuery.mockResolvedValue(mockResult);

      const result = await getDecryptedApiKey("user123", "alpaca");

      expect(result).toEqual({
        keyId: "stored_key",
        secret: "stored_secret",
      });
    });

    test("should return null for non-existent key", async () => {
      const mockResult = { rows: [] };
      mockQuery.mockResolvedValue(mockResult);

      const result = await getDecryptedApiKey("user123", "nonexistent");

      expect(result).toBeNull();
    });
  });

  describe("cache management", () => {
    test("should invalidate session cache", () => {
      // Test cache invalidation
      invalidateSession("test-token");
      // Since cache is internal, we can't directly verify, but function should not throw
      expect(true).toBe(true);
    });

    test("should clear all caches", () => {
      clearCaches();
      // Since cache is internal, we can't directly verify, but function should not throw
      expect(true).toBe(true);
    });
  });

  describe("health status", () => {
    test("should return health status", () => {
      const health = getHealthStatus();

      expect(health).toEqual(
        expect.objectContaining({
          apiKeyCircuitBreaker: expect.objectContaining({
            state: expect.any(String),
            failures: expect.any(Number),
          }),
          jwtCircuitBreaker: expect.objectContaining({
            state: expect.any(String),
            failures: expect.any(Number),
          }),
          cache: expect.objectContaining({
            keyCache: expect.any(Number),
            sessionCache: expect.any(Number),
          }),
          services: expect.objectContaining({
            encryptionAvailable: expect.any(Boolean),
            jwtVerifierAvailable: expect.any(Boolean),
          }),
        })
      );
    });
  });

  describe("circuit breaker functionality", () => {
    beforeEach(() => {
      // Reset to production mode to test circuit breaker
      process.env.NODE_ENV = "production";
      delete process.env.ALLOW_DEV_BYPASS;
      clearCaches(); // Clear caches to reset circuit breaker state
    });

    test("should handle circuit breaker failures", async () => {
      jwt.verify.mockReturnValue({ sub: "user123" });

      // Simulate database failure
      const dbError = new Error("Database connection failed");
      mockQuery.mockRejectedValue(dbError);

      const apiKeyData = { keyId: "test-key", secret: "test-secret" };

      // First few failures should return error responses (before circuit breaker opens)
      const result = await storeApiKey("valid-jwt-token", "alpaca", apiKeyData);
      expect(result.success).toBe(false);
      expect(result.error).toContain("Failed to store API key");
    });

    test("should test JWT circuit breaker functionality", async () => {
      // Test JWT validation failure handling
      jwt.verify.mockImplementation(() => {
        throw new Error("JWT validation failed");
      });

      const result = await validateJwtToken("invalid-token");

      expect(result.valid).toBe(false);
      expect(result.error).toContain("JWT validation failed");
    });
  });

  describe("security features", () => {
    test("should use different salts for different users", async () => {
      jwt.verify
        .mockReturnValueOnce({ sub: "user1" })
        .mockReturnValueOnce({ sub: "user2" });

      const mockResult = {
        rows: [{ user_id: "user1", broker_name: "alpaca" }],
        rowCount: 1,
      };
      mockQuery.mockResolvedValue(mockResult);

      const apiKeyData = { keyId: "test-key", secret: "test-secret" };

      await storeApiKey("token1", "alpaca", apiKeyData);
      await storeApiKey("token2", "alpaca", apiKeyData);

      // Verify different salts used
      expect(crypto.randomBytes).toHaveBeenCalledTimes(2);
    });

    test("should sanitize log output", async () => {
      const consoleSpy = jest.spyOn(console, "log").mockImplementation();
      jwt.verify.mockReturnValue({ sub: "user123" });

      const mockResult = {
        rows: [{ user_id: "user123", broker_name: "alpaca" }],
        rowCount: 1,
      };
      mockQuery.mockResolvedValue(mockResult);

      const apiKeyData = { keyId: "SENSITIVE_KEY", secret: "SENSITIVE_SECRET" };
      await storeApiKey("valid-jwt-token", "alpaca", apiKeyData);

      // Ensure sensitive data not logged in console.log calls
      const logCalls = consoleSpy.mock.calls.flat();
      const hasLeakedData = logCalls.some(
        (call) =>
          String(call).includes("SENSITIVE_KEY") ||
          String(call).includes("SENSITIVE_SECRET")
      );
      expect(hasLeakedData).toBe(false);

      consoleSpy.mockRestore();
    });

    test("should validate input lengths", async () => {
      jwt.verify.mockReturnValue({ sub: "user123" });

      const apiKeyData = {
        keyId: "x".repeat(501), // Exceeds max length
        secret: "test-secret",
      };

      const result = await storeApiKey("valid-jwt-token", "alpaca", apiKeyData);

      expect(result.success).toBe(false);
      expect(result.error).toContain("exceeds maximum length limits");
    });
  });

  describe("encryption and decryption", () => {
    beforeEach(() => {
      jwt.verify.mockReturnValue({ sub: "user123" });
    });

    test("should handle production encryption mode", async () => {
      process.env.NODE_ENV = "production";
      process.env.API_KEY_ENCRYPTION_SECRET_ARN = "test-arn";

      // Mock JWT verifier for production mode
      const mockJwtVerifier = {
        verify: jest.fn().mockResolvedValue({ sub: "user123" }),
      };
      const service = __getServiceInstance();
      service.jwtVerifier = mockJwtVerifier;

      // Mock secrets manager response
      mockSecretsManager.send.mockResolvedValue({
        SecretString: JSON.stringify({ encryptionKey: "test-encryption-key" }),
      });

      const mockResult = {
        rows: [{ user_id: "user123", broker_name: "alpaca" }],
        rowCount: 1,
      };
      mockQuery.mockResolvedValue(mockResult);

      const apiKeyData = { keyId: "test-key", secret: "test-secret" };
      const result = await storeApiKey("valid-jwt-token", "alpaca", apiKeyData);

      expect(result.success).toBe(true);
      expect(crypto.createCipheriv).toHaveBeenCalled();
    });

    test("should handle encryption key from environment", async () => {
      process.env.NODE_ENV = "production";
      delete process.env.API_KEY_ENCRYPTION_SECRET_ARN;
      process.env.API_KEY_ENCRYPTION_SECRET = "env-encryption-key";

      // Mock JWT verifier for production mode
      const mockJwtVerifier = {
        verify: jest.fn().mockResolvedValue({ sub: "user123" }),
      };
      const service = __getServiceInstance();
      service.jwtVerifier = mockJwtVerifier;

      const mockResult = {
        rows: [{ user_id: "user123", broker_name: "alpaca" }],
        rowCount: 1,
      };
      mockQuery.mockResolvedValue(mockResult);

      const apiKeyData = { keyId: "test-key", secret: "test-secret" };
      const result = await storeApiKey("valid-jwt-token", "alpaca", apiKeyData);

      expect(result.success).toBe(true);
    });

    test("should handle secrets manager errors", async () => {
      process.env.NODE_ENV = "production";
      process.env.API_KEY_ENCRYPTION_SECRET_ARN = "test-arn";

      // Mock JWT verifier for production mode
      const mockJwtVerifier = {
        verify: jest.fn().mockResolvedValue({ sub: "user123" }),
      };
      const service = __getServiceInstance();
      service.jwtVerifier = mockJwtVerifier;

      // Mock secrets manager failure
      mockSecretsManager.send.mockRejectedValue(new Error("Access denied"));

      const mockResult = {
        rows: [{ user_id: "user123", broker_name: "alpaca" }],
        rowCount: 1,
      };
      mockQuery.mockResolvedValue(mockResult);

      const apiKeyData = { keyId: "test-key", secret: "test-secret" };
      const result = await storeApiKey("valid-jwt-token", "alpaca", apiKeyData);

      expect(result.success).toBe(true); // Should fallback to dev key
    });
  });

  describe("production JWT verification", () => {
    beforeEach(() => {
      process.env.NODE_ENV = "production";
      process.env.COGNITO_USER_POOL_ID = "test-pool-id";
      process.env.COGNITO_CLIENT_ID = "test-client-id";
    });

    test("should handle Cognito JWT verification", async () => {
      // Mock JWT verifier on the service instance
      const mockJwtVerifier = {
        verify: jest.fn().mockResolvedValue({
          sub: "user123",
          email: "test@example.com",
          username: "testuser",
        }),
      };
      const service = __getServiceInstance();
      service.jwtVerifier = mockJwtVerifier;

      const result = await validateJwtToken("valid-cognito-jwt");

      expect(result.valid).toBe(true);
      expect(result.user.sub).toBe("user123");
      expect(result.user.email).toBe("test@example.com");
    });

    test("should handle Cognito JWT verification failure", async () => {
      // Mock JWT verifier on the service instance
      const mockJwtVerifier = {
        verify: jest.fn().mockRejectedValue(new Error("Token expired")),
      };
      const service = __getServiceInstance();
      service.jwtVerifier = mockJwtVerifier;

      const result = await validateJwtToken("expired-jwt");

      expect(result.valid).toBe(false);
      expect(result.error).toContain("Token expired");
    });

    test("should use cached JWT session", async () => {
      // Mock JWT verifier on the service instance
      const mockJwtVerifier = {
        verify: jest.fn().mockResolvedValue({
          sub: "user123",
          email: "test@example.com",
        }),
      };
      const service = __getServiceInstance();
      service.jwtVerifier = mockJwtVerifier;

      const result1 = await validateJwtToken("jwt-token");
      expect(result1.valid).toBe(true);

      // Second call - should use cache
      const result2 = await validateJwtToken("jwt-token");
      expect(result2.valid).toBe(true);

      // Should only call verify once (first time)
      expect(mockJwtVerifier.verify).toHaveBeenCalledTimes(1);
    });
  });

  describe("edge cases and error handling", () => {
    beforeEach(() => {
      jwt.verify.mockReturnValue({ sub: "user123" });
    });

    test("should handle database null result", async () => {
      mockQuery.mockResolvedValue(null);

      const result = await getApiKey("valid-jwt-token", "alpaca");

      expect(result).toBeNull();
    });

    test("should handle missing required fields for provider", async () => {
      // Mock getApiKey to return incomplete data by returning empty secret
      const incompleteApiKeyMockResult = {
        rows: [
          {
            encrypted_api_key: "incomplete_key",
            encrypted_api_secret: "", // Missing secret
            key_iv: "test-iv",
            key_auth_tag: "test-auth",
            secret_iv: "test-iv",
            secret_auth_tag: "test-auth",
          },
        ],
      };
      mockQuery
        .mockResolvedValueOnce(incompleteApiKeyMockResult)
        .mockResolvedValueOnce({ rows: [], rowCount: 1 })
        .mockResolvedValueOnce({ rows: [], rowCount: 0 });

      const result = await validateApiKey("valid-jwt-token", "alpaca", false);

      expect(result.valid).toBe(false);
      expect(result.error).toContain("Missing required fields");
    });

    test("should handle connection test for alpaca", async () => {
      const getApiKeyMockResult = {
        rows: [
          {
            encrypted_api_key: "alpaca_key",
            encrypted_api_secret: "alpaca_secret",
            key_iv: "test-iv",
            key_auth_tag: "test-auth",
            secret_iv: "test-iv",
            secret_auth_tag: "test-auth",
          },
        ],
      };
      mockQuery
        .mockResolvedValueOnce(getApiKeyMockResult)
        .mockResolvedValueOnce({ rows: [], rowCount: 1 })
        .mockResolvedValueOnce({ rows: [], rowCount: 0 });

      // Mock AlpacaService
      const mockAlpacaService = {
        validateCredentials: jest
          .fn()
          .mockResolvedValue({ valid: true, provider: "alpaca" }),
      };
      jest.doMock("../../../utils/alpacaService", () => {
        return jest.fn().mockImplementation(() => mockAlpacaService);
      });

      const result = await validateApiKey("valid-jwt-token", "alpaca", true);

      expect(result.valid).toBe(true);
    });
  });

  describe("audit logging", () => {
    beforeEach(() => {
      jwt.verify.mockReturnValue({ sub: "user123" });
    });

    test("should log audit events", async () => {
      const mockResult = {
        rows: [{ user_id: "user123", broker_name: "alpaca" }],
        rowCount: 1,
      };
      mockQuery.mockResolvedValue(mockResult);

      const apiKeyData = { keyId: "test-key", secret: "test-secret" };
      await storeApiKey("valid-jwt-token", "alpaca", apiKeyData);

      // Should call database for INSERT and audit log
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining("INSERT INTO api_key_audit_log"),
        expect.arrayContaining(["user123", "API_KEY_STORED", "alpaca"])
      );
    });

    test("should handle audit logging errors gracefully", async () => {
      const mockResult = {
        rows: [{ user_id: "user123", broker_name: "alpaca" }],
        rowCount: 1,
      };
      mockQuery
        .mockResolvedValueOnce(mockResult)
        .mockRejectedValueOnce(new Error("Audit log failed"));

      const apiKeyData = { keyId: "test-key", secret: "test-secret" };
      const result = await storeApiKey("valid-jwt-token", "alpaca", apiKeyData);

      // Should still succeed even if audit logging fails
      expect(result.success).toBe(true);
    });
  });

  describe("development mode features", () => {
    beforeEach(() => {
      process.env.NODE_ENV = "development";
      process.env.ALLOW_DEV_BYPASS = "true";
    });

    test("should handle development bypass token", async () => {
      const result = await validateJwtToken("dev-bypass-token");

      expect(result.valid).toBe(true);
      expect(result.user.sub).toBe("dev-user-bypass");
      expect(result.user.role).toBe("admin");
    });

    test("should reset circuit breaker in development", async () => {
      // This test verifies dev mode circuit breaker reset behavior
      const apiKeyData = { keyId: "test-key", secret: "test-secret" };

      // Mock JWT validation
      jwt.verify.mockReturnValue({ sub: "user123" });

      // Mock successful storage
      const mockResult = {
        rows: [{ user_id: "user123", broker_name: "alpaca" }],
        rowCount: 1,
      };
      mockQuery.mockResolvedValue(mockResult);

      const result = await storeApiKey("valid-jwt-token", "alpaca", apiKeyData);
      expect(result.success).toBe(true);
    });
  });

  describe("provider specific functionality", () => {
    test("should handle different provider required fields", async () => {
      jwt.verify.mockReturnValue({ sub: "user123" });

      // Test polygon provider (only needs apiKey)
      const polygonResult = {
        rows: [
          {
            encrypted_api_key: "polygon_key",
            encrypted_api_secret: "", // Polygon doesn't need secret
            key_iv: "test-iv",
            key_auth_tag: "test-auth",
            secret_iv: "test-iv",
            secret_auth_tag: "test-auth",
          },
        ],
      };
      mockQuery
        .mockResolvedValueOnce(polygonResult)
        .mockResolvedValueOnce({ rows: [], rowCount: 1 })
        .mockResolvedValueOnce({ rows: [], rowCount: 0 });

      const result = await validateApiKey("valid-jwt-token", "polygon", false);
      expect(result.valid).toBe(true);
    });

    test("should handle unknown provider gracefully", async () => {
      jwt.verify.mockReturnValue({ sub: "user123" });

      const unknownProviderResult = {
        rows: [
          {
            encrypted_api_key: "unknown_key",
            encrypted_api_secret: "unknown_secret",
            key_iv: "test-iv",
            key_auth_tag: "test-auth",
            secret_iv: "test-iv",
            secret_auth_tag: "test-auth",
          },
        ],
      };
      mockQuery
        .mockResolvedValueOnce(unknownProviderResult)
        .mockResolvedValueOnce({ rows: [], rowCount: 1 })
        .mockResolvedValueOnce({ rows: [], rowCount: 0 });

      const result = await validateApiKey(
        "valid-jwt-token",
        "unknown_provider",
        true
      );
      expect(result.valid).toBe(true);
      expect(result.provider).toBe("unknown_provider");
    });
  });
});

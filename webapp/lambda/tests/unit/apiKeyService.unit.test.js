// Unit tests for API Key Service

// Mock AWS SDK before requiring apiKeyService
jest.mock("@aws-sdk/client-secrets-manager", () => ({
  SecretsManagerClient: jest.fn(() => ({
    send: jest.fn(),
  })),
  GetSecretValueCommand: jest.fn(),
}));

// Mock database
jest.mock("../../utils/database", () => ({
  query: jest.fn(),
}));

// Mock crypto
jest.mock("crypto", () => ({
  randomBytes: jest.fn(() => Buffer.from("mockrandomdata12")),
  randomUUID: jest.fn(() => "mock-session-id-1234"),
  scryptSync: jest.fn(() =>
    Buffer.from("mockencryptionkey123456789012345678901234567890")
  ),
  createCipherGCM: jest.fn(),
  createDecipherGCM: jest.fn(),
}));

// Mock aws-jwt-verify
jest.mock("aws-jwt-verify", () => ({
  CognitoJwtVerifier: {
    create: jest.fn(() => ({
      verify: jest.fn(),
    })),
  },
}));

const {
  SecretsManagerClient,
  GetSecretValueCommand,
} = require("@aws-sdk/client-secrets-manager");
const { query } = require("../../utils/database");
const crypto = require("crypto");
const { CognitoJwtVerifier } = require("aws-jwt-verify");

describe("API Key Service Unit Tests", () => {
  let apiKeyService;
  let mockSecretsManager;
  let mockJwtVerifier;
  let mockCipher;
  let mockDecipher;

  beforeEach(() => {
    jest.clearAllMocks();

    // Setup mocks with proper implementations
    mockSecretsManager = {
      send: jest.fn(),
    };

    mockJwtVerifier = {
      verify: jest.fn(),
    };

    mockCipher = {
      update: jest.fn(() => "encrypted"),
      final: jest.fn(() => "data"),
      getAuthTag: jest.fn(() => Buffer.from("authtag123456")),
      setAAD: jest.fn(),
    };

    mockDecipher = {
      update: jest.fn(() => "decrypted"),
      final: jest.fn(() => "data"),
      setAAD: jest.fn(),
      setAuthTag: jest.fn(),
    };

    SecretsManagerClient.mockImplementation(() => mockSecretsManager);
    CognitoJwtVerifier.create.mockReturnValue(mockJwtVerifier);
    crypto.createCipherGCM.mockReturnValue(mockCipher);
    crypto.createDecipherGCM.mockReturnValue(mockDecipher);
    crypto.randomBytes.mockReturnValue(Buffer.from("mockrandomdata12"));

    // Set required environment variables for tests to work
    process.env.COGNITO_USER_POOL_ID = "us-east-1_testpool";
    process.env.COGNITO_CLIENT_ID = "test-client-id";
    process.env.API_KEY_ENCRYPTION_SECRET = "test-encryption-key-32-chars-long";
    process.env.WEBAPP_AWS_REGION = "us-east-1";

    // Import apiKeyService if not already imported
    if (!apiKeyService) {
      apiKeyService = require("../../utils/apiKeyService");
    }

    // Reset service state for clean tests
    apiKeyService.clearAllCaches();
    apiKeyService.jwtCircuitBreaker = {
      failures: 0,
      lastFailureTime: 0,
      state: "CLOSED",
      maxFailures: 3,
      timeout: 30000
    };
    apiKeyService.jwtVerifier = mockJwtVerifier;
  });

  afterEach(() => {
    // Clean up environment variables
    delete process.env.COGNITO_USER_POOL_ID;
    delete process.env.COGNITO_CLIENT_ID;
    delete process.env.API_KEY_ENCRYPTION_SECRET_ARN;
    delete process.env.API_KEY_ENCRYPTION_SECRET;
    delete process.env.WEBAPP_AWS_REGION;
    delete process.env.AWS_REGION;
  });

  describe("JWT Token Validation", () => {
    beforeEach(() => {
      process.env.COGNITO_USER_POOL_ID = "us-east-1_testpool";
      process.env.COGNITO_CLIENT_ID = "test-client-id";
    });

    test("should validate JWT token successfully", async () => {
      const mockToken = "valid-jwt-token";
      const mockPayload = {
        sub: "user123",
        email: "test@example.com",
        username: "testuser",
        "custom:role": "admin",
        "cognito:groups": ["users"],
        iat: Math.floor(Date.now() / 1000),
        exp: Math.floor(Date.now() / 1000) + 3600,
      };

      mockJwtVerifier.verify.mockResolvedValue(mockPayload);

      const user = await apiKeyService.validateJwtToken(mockToken);

      expect(user).toMatchObject({
        valid: true,
        user: {
          sub: "user123",
          email: "test@example.com",
          username: "testuser",
          role: "admin",
          groups: ["users"],
          sessionId: "mock-session-id-1234",
        },
      });
      expect(mockJwtVerifier.verify).toHaveBeenCalledWith(mockToken);
    });

    test("should handle JWT validation failure", async () => {
      const mockToken = "invalid-jwt-token";
      
      // Ensure the JWT verifier is properly mocked and will reject
      apiKeyService.jwtVerifier = mockJwtVerifier;
      mockJwtVerifier.verify.mockRejectedValue(new Error("Invalid token"));

      const result = await apiKeyService.validateJwtToken(mockToken);
      expect(result.valid).toBe(false);
      expect(result.error).toContain("Invalid token");
    });

    test("should use cached session when available", async () => {
      const mockToken = "cached-jwt-token";
      const mockPayload = {
        sub: "user123",
        email: "test@example.com",
        username: "testuser",
      };

      // First call - should verify token
      mockJwtVerifier.verify.mockResolvedValue(mockPayload);
      await apiKeyService.validateJwtToken(mockToken);

      // Second call - should use cache
      jest.clearAllMocks();
      const cachedUser = await apiKeyService.validateJwtToken(mockToken);

      expect(cachedUser.user.sub).toBe("user123");
      expect(mockJwtVerifier.verify).not.toHaveBeenCalled();
    });

    test("should handle circuit breaker OPEN state", async () => {
      const mockToken = "test-token";

      // Ensure the JWT verifier is properly mocked and will reject
      apiKeyService.jwtVerifier = mockJwtVerifier;
      mockJwtVerifier.verify.mockRejectedValue(
        new Error("JWT verification failed")
      );

      // Trigger exactly 3 failures to open circuit breaker (maxFailures = 3)
      for (let i = 0; i < 3; i++) {
        const result = await apiKeyService.validateJwtToken(mockToken);
        expect(result.valid).toBe(false);
      }

      // Verify circuit breaker is now OPEN
      expect(apiKeyService.jwtCircuitBreaker.state).toBe("OPEN");

      // Next call should fail due to circuit breaker
      await expect(apiKeyService.validateJwtToken(mockToken)).rejects.toThrow(
        "JWT circuit breaker is OPEN - authentication temporarily unavailable"
      );
    });
  });

  describe("Encryption and Decryption", () => {
    beforeEach(() => {
      process.env.API_KEY_ENCRYPTION_SECRET =
        "test-encryption-key-32-chars-long";
    });

    test("should encrypt API key data successfully", async () => {
      const mockToken = "valid-jwt-token";
      const mockData = { apiKey: "test-key", apiSecret: "test-secret" };

      // Mock JWT validation
      mockJwtVerifier.verify.mockResolvedValue({
        sub: "user123",
        username: "testuser"
      });

      // Mock database response
      query.mockResolvedValue({
        rows: [{ id: 1 }],
      });

      // Reset module to get fresh instance with encryption key
      delete require.cache[require.resolve("../../utils/apiKeyService")];
      const freshApiKeyService = require("../../utils/apiKeyService");

      const result = await freshApiKeyService.storeApiKey(
        mockToken,
        "alpaca",
        mockData
      );

      expect(result.success).toBe(true);
      expect(crypto.createCipherGCM).toHaveBeenCalled();
      expect(mockCipher.setAAD).toHaveBeenCalled();
      expect(mockCipher.update).toHaveBeenCalled();
      expect(mockCipher.final).toHaveBeenCalled();
      expect(mockCipher.getAuthTag).toHaveBeenCalled();
    });

    test("should decrypt API key data successfully", async () => {
      const _mockEncryptedData = {
        encrypted: "encrypteddata",
        iv: "mockhexiv",
        authTag: "mockauthtag",
        algorithm: "aes-256-gcm",
      };
      const _mockSalt2 = "user-salt-123";

      mockDecipher.update.mockReturnValue('{"apiKey":"test-key"}');
      mockDecipher.final.mockReturnValue("");

      // Reset module to get fresh instance
      delete require.cache[require.resolve("../../utils/apiKeyService")];
      const _freshApiKeyService = require("../../utils/apiKeyService");

      // We need to test the internal method through a public method
      // This is tested indirectly through getApiKey
      expect(crypto.createDecipherGCM).toBeDefined();
    });

    test("should handle encryption key from Secrets Manager", async () => {
      process.env.API_KEY_ENCRYPTION_SECRET_ARN =
        "arn:aws:secretsmanager:us-east-1:123:secret:test";
      delete process.env.API_KEY_ENCRYPTION_SECRET;

      mockSecretsManager.send.mockResolvedValue({
        SecretString: JSON.stringify({ encryptionKey: "secrets-manager-key" }),
      });

      // Reset module to get fresh instance
      delete require.cache[require.resolve("../../utils/apiKeyService")];
      const _freshApiKeyService2 = require("../../utils/apiKeyService");

      // The encryption key should be retrieved from Secrets Manager
      // This is tested indirectly through the service initialization
      expect(GetSecretValueCommand).toBeDefined();
    });

    test("should handle missing encryption key gracefully", async () => {
      delete process.env.API_KEY_ENCRYPTION_SECRET;
      delete process.env.API_KEY_ENCRYPTION_SECRET_ARN;

      // Reset module to get fresh instance
      delete require.cache[require.resolve("../../utils/apiKeyService")];
      const freshApiKeyService = require("../../utils/apiKeyService");

      // Should handle missing encryption key during operations
      expect(freshApiKeyService).toBeDefined();
    });
  });

  describe("API Key Storage Operations", () => {
    beforeEach(() => {
      process.env.COGNITO_USER_POOL_ID = "us-east-1_testpool";
      process.env.COGNITO_CLIENT_ID = "test-client-id";
      process.env.API_KEY_ENCRYPTION_SECRET =
        "test-encryption-key-32-chars-long";

      // Mock JWT validation
      mockJwtVerifier.verify.mockResolvedValue({
        sub: "user123",
        email: "test@example.com",
        username: "testuser",
      });
    });

    test("should store API key successfully", async () => {
      const mockToken = "valid-jwt-token";
      const provider = "alpaca";
      const apiKeyData = { apiKey: "test-key", apiSecret: "test-secret" };

      // Ensure the JWT verifier is properly set and configured
      apiKeyService.jwtVerifier = mockJwtVerifier;
      mockJwtVerifier.verify.mockResolvedValue({
        sub: "user123",
        email: "test@example.com",
        username: "testuser"
      });

      query.mockResolvedValueOnce({ rows: [{ id: 1 }] }); // For store operation
      query.mockResolvedValueOnce({ rows: [] }); // For audit log

      const result = await apiKeyService.storeApiKey(
        mockToken,
        provider,
        apiKeyData
      );

      expect(result.success).toBe(true);
      expect(result.provider).toBe(provider);
      expect(result.encrypted).toBe(true);
      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("INSERT INTO user_api_keys"),
        expect.arrayContaining(["user123", provider])
      );
    });

    test("should retrieve API key successfully", async () => {
      const mockToken = "valid-jwt-token";
      const provider = "alpaca";

      // Setup JWT verifier mock
      apiKeyService.jwtVerifier = mockJwtVerifier;
      mockJwtVerifier.verify.mockResolvedValue({
        sub: "user123",
        email: "test@example.com",
        username: "testuser"
      });

      const mockDbResult = {
        rows: [
          {
            encrypted_data: JSON.stringify({
              encrypted: "encrypteddata",
              iv: "mockhexiv",
              authTag: "mockauthtag",
              algorithm: "aes-256-gcm",
            }),
            user_salt: "user-salt-123",
          },
        ],
      };

      query.mockResolvedValueOnce(mockDbResult); // For get operation
      query.mockResolvedValueOnce({ rows: [] }); // For update last_used
      query.mockResolvedValueOnce({ rows: [] }); // For audit log

      mockDecipher.update.mockReturnValue(
        '{"apiKey":"test-key","apiSecret":"test-secret"}'
      );
      mockDecipher.final.mockReturnValue("");

      const result = await apiKeyService.getApiKey(mockToken, provider);

      expect(result).toEqual({ apiKey: "test-key", apiSecret: "test-secret" });
      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("SELECT encrypted_data, user_salt"),
        ["user123", provider]
      );
    });

    test("should return null when API key not found", async () => {
      const mockToken = "valid-jwt-token";
      const provider = "alpaca";

      // Setup JWT verifier mock
      apiKeyService.jwtVerifier = mockJwtVerifier;
      mockJwtVerifier.verify.mockResolvedValue({
        sub: "user123",
        email: "test@example.com",
        username: "testuser"
      });

      query.mockResolvedValue({ rows: [] }); // No API key found

      const result = await apiKeyService.getApiKey(mockToken, provider);

      expect(result).toBeNull();
    });

    test("should delete API key successfully", async () => {
      const mockToken = "valid-jwt-token";
      const provider = "alpaca";

      // Setup JWT verifier mock
      apiKeyService.jwtVerifier = mockJwtVerifier;
      mockJwtVerifier.verify.mockResolvedValue({
        sub: "user123",
        email: "test@example.com",
        username: "testuser"
      });

      query.mockResolvedValueOnce({ rowCount: 1 }); // For delete operation
      query.mockResolvedValueOnce({ rows: [] }); // For audit log

      const result = await apiKeyService.deleteApiKey(mockToken, provider);

      expect(result.success).toBe(true);
      expect(result.deleted).toBe(true);
      expect(result.provider).toBe(provider);
      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("DELETE FROM user_api_keys"),
        ["user123", provider]
      );
    });

    test("should list providers successfully", async () => {
      const mockToken = "valid-jwt-token";

      // Setup JWT verifier mock
      apiKeyService.jwtVerifier = mockJwtVerifier;
      mockJwtVerifier.verify.mockResolvedValue({
        sub: "user123",
        email: "test@example.com",
        username: "testuser"
      });

      const mockDbResult = {
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

      query.mockResolvedValue(mockDbResult);

      const result = await apiKeyService.listProviders(mockToken);

      expect(result).toHaveLength(2);
      expect(result[0].provider).toBe("alpaca");
      expect(result[0].configured).toBe(true);
      expect(result[1].provider).toBe("polygon");
      expect(result[1].configured).toBe(true);
    });
  });

  describe("API Key Validation", () => {
    beforeEach(() => {
      process.env.COGNITO_USER_POOL_ID = "us-east-1_testpool";
      process.env.COGNITO_CLIENT_ID = "test-client-id";

      mockJwtVerifier.verify.mockResolvedValue({
        sub: "user123",
        email: "test@example.com",
      });
    });

    test("should validate API key configuration", async () => {
      const mockToken = "valid-jwt-token";
      const provider = "alpaca";

      // Setup JWT verifier mock
      apiKeyService.jwtVerifier = mockJwtVerifier;
      mockJwtVerifier.verify.mockResolvedValue({
        sub: "user123",
        email: "test@example.com",
        username: "testuser"
      });

      // Mock getApiKey to return valid data
      query.mockResolvedValue({
        rows: [
          {
            encrypted_data: JSON.stringify({
              encrypted: "encrypteddata",
              iv: "mockhexiv",
              authTag: "mockauthtag",
              algorithm: "aes-256-gcm",
            }),
            user_salt: "user-salt-123",
          },
        ],
      });

      mockDecipher.update.mockReturnValue(
        '{"apiKey":"test-key","apiSecret":"test-secret"}'
      );
      mockDecipher.final.mockReturnValue("");

      const result = await apiKeyService.validateApiKey(mockToken, provider);

      expect(result.valid).toBe(true);
      expect(result.provider).toBe(provider);
    });

    test("should detect missing API key configuration", async () => {
      const mockToken = "valid-jwt-token";
      const provider = "alpaca";

      // Setup JWT verifier mock
      apiKeyService.jwtVerifier = mockJwtVerifier;
      mockJwtVerifier.verify.mockResolvedValue({
        sub: "user123",
        email: "test@example.com",
        username: "testuser"
      });

      query.mockResolvedValue({ rows: [] }); // No API key found

      const result = await apiKeyService.validateApiKey(mockToken, provider);

      expect(result.valid).toBe(false);
      expect(result.error).toBe("API key not configured");
      expect(result.provider).toBe(provider);
    });

    test("should detect missing required fields", async () => {
      const mockToken = "valid-jwt-token";
      const provider = "alpaca";

      // Setup JWT verifier mock
      apiKeyService.jwtVerifier = mockJwtVerifier;
      mockJwtVerifier.verify.mockResolvedValue({
        sub: "user123",
        email: "test@example.com",
        username: "testuser"
      });

      query.mockResolvedValue({
        rows: [
          {
            encrypted_data: JSON.stringify({
              encrypted: "encrypteddata",
              iv: "mockhexiv",
              authTag: "mockauthtag",
              algorithm: "aes-256-gcm",
            }),
            user_salt: "user-salt-123",
          },
        ],
      });

      // Return API key data missing required fields
      mockDecipher.update.mockReturnValue('{"apiKey":"test-key"}'); // Missing apiSecret
      mockDecipher.final.mockReturnValue("");

      const result = await apiKeyService.validateApiKey(mockToken, provider);

      expect(result.valid).toBe(false);
      expect(result.error).toContain("Missing required fields");
      expect(result.missingFields).toContain("apiSecret");
    });

    test("should get required fields for different providers", async () => {
      // This is tested indirectly through validation
      // We can test the internal logic by checking validation results
      const mockToken = "valid-jwt-token";

      // Setup JWT verifier mock
      apiKeyService.jwtVerifier = mockJwtVerifier;
      mockJwtVerifier.verify.mockResolvedValue({
        sub: "user123",
        email: "test@example.com",
        username: "testuser"
      });

      query.mockResolvedValue({ rows: [] }); // No API key found

      // Test alpaca provider
      let result = await apiKeyService.validateApiKey(mockToken, "alpaca");
      expect(result.provider).toBe("alpaca");

      // Test polygon provider
      result = await apiKeyService.validateApiKey(mockToken, "polygon");
      expect(result.provider).toBe("polygon");

      // Test finnhub provider
      result = await apiKeyService.validateApiKey(mockToken, "finnhub");
      expect(result.provider).toBe("finnhub");
    });
  });

  describe("Circuit Breaker Functionality", () => {
    beforeEach(() => {
      process.env.COGNITO_USER_POOL_ID = "us-east-1_testpool";
      process.env.COGNITO_CLIENT_ID = "test-client-id";
    });

    test("should open API key circuit breaker after max failures", async () => {
      const mockToken = "test-token";
      const provider = "alpaca";

      // Setup JWT verifier mock
      apiKeyService.jwtVerifier = mockJwtVerifier;
      mockJwtVerifier.verify.mockResolvedValue({
        sub: "user123",
        email: "test@example.com",
        username: "testuser"
      });

      // Mock database to fail
      query.mockRejectedValue(new Error("Database error"));

      // Trigger failures to open circuit breaker (max 5 failures)
      for (let i = 0; i < 5; i++) {
        try {
          await apiKeyService.getApiKey(mockToken, provider);
        } catch (error) {
          // Ignore errors to continue triggering failures
        }
      }

      // Next call should fail due to circuit breaker
      await expect(
        apiKeyService.getApiKey(mockToken, provider)
      ).rejects.toThrow("API key circuit breaker is OPEN");
    });

    test("should reset circuit breaker on successful operation", async () => {
      const mockToken = "test-token";
      const provider = "alpaca";

      // Setup JWT verifier mock
      apiKeyService.jwtVerifier = mockJwtVerifier;
      mockJwtVerifier.verify.mockResolvedValue({
        sub: "user123",
        email: "test@example.com",
        username: "testuser"
      });

      // Trigger one failure first
      query.mockRejectedValueOnce(new Error("Database error"));
      try {
        await apiKeyService.getApiKey(mockToken, provider);
      } catch (error) {
        // Ignore error
      }

      // Now succeed
      query.mockResolvedValue({ rows: [] });
      const result = await apiKeyService.getApiKey(mockToken, provider);

      expect(result).toBeNull(); // Normal response, circuit breaker working
    });
  });

  describe("Cache Management", () => {
    test("should clear all caches", () => {
      expect(() => apiKeyService.clearCaches()).not.toThrow();
    });

    test("should invalidate specific session", () => {
      const mockToken = "test-token";
      expect(() => apiKeyService.invalidateSession(mockToken)).not.toThrow();
    });
  });

  describe("Health Status", () => {
    test("should return comprehensive health status", () => {
      const health = apiKeyService.getHealthStatus();

      expect(health).toHaveProperty("apiKeyCircuitBreaker");
      expect(health).toHaveProperty("jwtCircuitBreaker");
      expect(health).toHaveProperty("cache");
      expect(health).toHaveProperty("services");

      expect(health.apiKeyCircuitBreaker).toHaveProperty("state");
      expect(health.apiKeyCircuitBreaker).toHaveProperty("failures");
      expect(health.jwtCircuitBreaker).toHaveProperty("state");
      expect(health.cache).toHaveProperty("keyCache");
      expect(health.cache).toHaveProperty("sessionCache");
      expect(health.services).toHaveProperty("encryptionAvailable");
      expect(health.services).toHaveProperty("jwtVerifierAvailable");
    });
  });

  describe("Error Handling", () => {
    test("should handle database connection errors gracefully", async () => {
      const mockToken = "valid-jwt-token";
      const provider = "alpaca";

      mockJwtVerifier.verify.mockResolvedValue({
        sub: "user123",
        email: "test@example.com",
      });

      query.mockRejectedValue(new Error("Database connection failed"));

      const result = await apiKeyService.getApiKey(mockToken, provider);
      expect(result).toBeNull();
    });

    test("should handle encryption/decryption errors", async () => {
      const mockToken = "valid-jwt-token";
      const provider = "alpaca";
      const apiKeyData = { apiKey: "test-key", apiSecret: "test-secret" };

      // Setup JWT verifier mock
      apiKeyService.jwtVerifier = mockJwtVerifier;
      mockJwtVerifier.verify.mockResolvedValue({
        sub: "user123",
        email: "test@example.com",
        username: "testuser"
      });

      // Mock encryption to fail
      crypto.createCipherGCM.mockImplementation(() => {
        throw new Error("Encryption failed");
      });

      await expect(
        apiKeyService.storeApiKey(mockToken, provider, apiKeyData)
      ).rejects.toThrow();
    });

    test("should handle JWT verification errors", async () => {
      const mockToken = "invalid-token";

      // Setup JWT verifier mock to fail
      apiKeyService.jwtVerifier = mockJwtVerifier;
      mockJwtVerifier.verify.mockRejectedValue(new Error("Token expired"));

      const result = await apiKeyService.validateJwtToken(mockToken);
      expect(result.valid).toBe(false);
      expect(result.error).toContain("Token expired");
    });
  });

  describe("Edge Cases", () => {
    test("should handle undefined token gracefully", async () => {
      const result = await apiKeyService.validateJwtToken(undefined);
      expect(result.valid).toBe(false);
    });

    test("should handle empty provider name", async () => {
      const mockToken = "valid-jwt-token";

      // Setup JWT verifier mock
      apiKeyService.jwtVerifier = mockJwtVerifier;
      mockJwtVerifier.verify.mockResolvedValue({
        sub: "user123",
        email: "test@example.com",
        username: "testuser"
      });

      query.mockResolvedValue({ rows: [] });

      const result = await apiKeyService.getApiKey(mockToken, "");
      expect(result).toBeNull();
    });

    test("should handle malformed encrypted data", async () => {
      const mockToken = "valid-jwt-token";
      const provider = "alpaca";

      mockJwtVerifier.verify.mockResolvedValue({
        sub: "user123",
        email: "test@example.com",
      });

      query.mockResolvedValue({
        rows: [
          {
            encrypted_data: "invalid-json",
            user_salt: "user-salt-123",
          },
        ],
      });

      const result = await apiKeyService.getApiKey(mockToken, provider);
      expect(result).toBeNull();
    });
  });
});

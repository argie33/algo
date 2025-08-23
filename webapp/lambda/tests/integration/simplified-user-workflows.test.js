const request = require("supertest");
const express = require("express");

// Mock dependencies
jest.mock("../../utils/database", () => ({
  query: jest.fn(),
  healthCheck: jest.fn(),
}));

jest.mock("../../utils/apiKeyService", () => ({
  isEnabled: true,
  storeApiKey: jest.fn(),
  getApiKey: jest.fn(),
  listProviders: jest.fn(),
  validateJwtToken: jest.fn(),
  getHealthStatus: jest.fn(),
}));

// Import after mocking
const {
  query: _mockQuery,
  healthCheck: mockHealthCheck,
} = require("../../utils/database");
const {
  storeApiKey,
  listProviders,
  validateJwtToken,
  getHealthStatus,
} = require("../../utils/apiKeyService");
// Import routes
const settingsRoutes = require("../../routes/settings");
const healthRoutes = require("../../routes/health");

describe("Simplified User Workflows - Core Functionality", () => {
  let app;
  let mockToken;
  let mockUser;

  beforeAll(() => {
    app = express();
    app.use(express.json());

    // Add only core routes
    app.use("/api/settings", settingsRoutes);
    app.use("/api/health", healthRoutes);

    mockUser = {
      sub: "test-user-123",
      email: "test@example.com",
      role: "admin",
    };

    mockToken = "mock-jwt-token";
  });

  beforeEach(() => {
    jest.clearAllMocks();
    validateJwtToken.mockResolvedValue(mockUser);
    mockHealthCheck.mockResolvedValue({ healthy: true, database: "connected" });
    getHealthStatus.mockReturnValue({
      apiKeyCircuitBreaker: { state: "CLOSED" },
    });
  });

  describe("Workflow 1: Settings API Key Management", () => {
    it("should complete basic API key workflow", async () => {
      // Step 1: List API keys (empty initially)
      listProviders.mockResolvedValue([]);

      const listResponse = await request(app)
        .get("/api/settings/api-keys")
        .set("Authorization", `Bearer ${mockToken}`)
        .expect(200);

      expect(listResponse.body.success).toBe(true);
      expect(listResponse.body.apiKeys).toEqual([]);

      // Step 2: Store new API key
      storeApiKey.mockResolvedValue(true);

      const storeResponse = await request(app)
        .post("/api/settings/api-keys")
        .set("Authorization", `Bearer ${mockToken}`)
        .send({
          provider: "alpaca",
          apiKey: "TEST123",
          apiSecret: "SECRET123",
        })
        .expect(200);

      expect(storeResponse.body.success).toBe(true);
      expect(storeApiKey).toHaveBeenCalledWith(
        mockToken,
        "alpaca",
        expect.objectContaining({
          apiKey: "TEST123",
          apiSecret: "SECRET123",
          isSandbox: true,
        })
      );

      // Step 3: List API keys (should show new key)
      listProviders.mockResolvedValue([
        {
          provider: "alpaca",
          hasApiKey: true,
        },
      ]);

      const updatedListResponse = await request(app)
        .get("/api/settings/api-keys")
        .set("Authorization", `Bearer ${mockToken}`)
        .expect(200);

      expect(updatedListResponse.body.success).toBe(true);
      expect(updatedListResponse.body.apiKeys).toHaveLength(1);
    });

    it("should handle authentication failures", async () => {
      validateJwtToken.mockRejectedValue(new Error("Invalid token"));

      await request(app)
        .get("/api/settings/api-keys")
        .set("Authorization", "Bearer invalid-token")
        .expect(401);
    });

    it("should handle API key storage failures", async () => {
      storeApiKey.mockRejectedValue(new Error("Storage failed"));

      const response = await request(app)
        .post("/api/settings/api-keys")
        .set("Authorization", `Bearer ${mockToken}`)
        .send({
          provider: "alpaca",
          apiKey: "TEST123",
          apiSecret: "SECRET123",
        })
        .expect(500);

      expect(response.body.success).toBe(false);
    });
  });

  describe("Workflow 2: System Health Monitoring", () => {
    it("should check basic health status", async () => {
      // Use quick health check to avoid database dependency
      const response = await request(app)
        .get("/api/health?quick=true")
        .expect(200);

      expect(response.body.status).toBe("healthy");
      expect(response.body.healthy).toBe(true);
    });

    it("should handle database health failures", async () => {
      mockHealthCheck.mockRejectedValue(new Error("Database down"));

      await request(app).get("/api/health").expect(503);
    });
  });

  describe("Workflow 3: Input Validation", () => {
    it("should validate required fields", async () => {
      const response = await request(app)
        .post("/api/settings/api-keys")
        .set("Authorization", `Bearer ${mockToken}`)
        .send({}) // Missing required fields
        .expect(400);

      expect(response.body.success).toBe(false);
    });

    it("should reject invalid provider names", async () => {
      const response = await request(app)
        .post("/api/settings/api-keys")
        .set("Authorization", `Bearer ${mockToken}`)
        .send({
          provider: "  alpaca  ", // Has spaces, not supported
          apiKey: "TEST123",
          apiSecret: "SECRET123",
        })
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("Unsupported provider");
      expect(storeApiKey).not.toHaveBeenCalled();
    });

    it("should sanitize API key data when stored", async () => {
      storeApiKey.mockResolvedValue(true);

      await request(app)
        .post("/api/settings/api-keys")
        .set("Authorization", `Bearer ${mockToken}`)
        .send({
          provider: "alpaca", // Valid provider
          apiKey: "  TEST123  ", // Will be trimmed
          apiSecret: "  SECRET123  ", // Will be trimmed
        })
        .expect(200);

      // Verify that the service was called with sanitized data
      expect(storeApiKey).toHaveBeenCalledWith(
        mockToken,
        "alpaca",
        expect.objectContaining({
          apiKey: "TEST123", // Trimmed
          apiSecret: "SECRET123", // Trimmed
          isSandbox: true,
        })
      );
    });
  });

  describe("Workflow 4: Error Handling", () => {
    it("should handle malformed JSON requests", async () => {
      const response = await request(app)
        .post("/api/settings/api-keys")
        .set("Authorization", `Bearer ${mockToken}`)
        .set("Content-Type", "application/json")
        .send("invalid json")
        .expect(400);

      // Express middleware handles JSON parse errors - may not have success field
      expect(response.body).toBeDefined();
    });

    it("should handle service unavailable scenarios", async () => {
      listProviders.mockRejectedValue(new Error("Service unavailable"));

      const response = await request(app)
        .get("/api/settings/api-keys")
        .set("Authorization", `Bearer ${mockToken}`)
        .expect(500);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain("Failed to fetch API keys");
    });
  });

  describe("Workflow 5: Authorization Levels", () => {
    it("should allow authenticated users to access settings", async () => {
      listProviders.mockResolvedValue([]);

      await request(app)
        .get("/api/settings/api-keys")
        .set("Authorization", `Bearer ${mockToken}`)
        .expect(200);
    });

    it("should reject unauthenticated requests", async () => {
      await request(app).get("/api/settings/api-keys").expect(401);
    });
  });

  describe("Workflow 6: Performance and Concurrency", () => {
    it("should handle concurrent requests", async () => {
      listProviders.mockResolvedValue([]);

      const promises = Array.from({ length: 5 }, () =>
        request(app)
          .get("/api/settings/api-keys")
          .set("Authorization", `Bearer ${mockToken}`)
      );

      const responses = await Promise.all(promises);

      responses.forEach((response) => {
        expect(response.status).toBe(200);
        expect(response.body.success).toBe(true);
      });
    });

    it("should respond within reasonable time", async () => {
      listProviders.mockResolvedValue([]);

      const startTime = Date.now();

      await request(app)
        .get("/api/settings/api-keys")
        .set("Authorization", `Bearer ${mockToken}`)
        .expect(200);

      const responseTime = Date.now() - startTime;
      expect(responseTime).toBeLessThan(1000); // Under 1 second
    });
  });

  describe("Workflow 7: Data Integrity", () => {
    it("should maintain data consistency", async () => {
      // Store API key
      storeApiKey.mockResolvedValue(true);

      await request(app)
        .post("/api/settings/api-keys")
        .set("Authorization", `Bearer ${mockToken}`)
        .send({
          provider: "alpaca",
          apiKey: "TEST123",
          apiSecret: "SECRET123",
        })
        .expect(200);

      // Verify storage was called exactly once with correct parameters
      expect(storeApiKey).toHaveBeenCalledTimes(1);
      expect(storeApiKey).toHaveBeenCalledWith(
        mockToken,
        "alpaca",
        expect.objectContaining({
          apiKey: "TEST123",
          apiSecret: "SECRET123",
          isSandbox: true,
        })
      );
    });

    it("should handle duplicate operations gracefully", async () => {
      storeApiKey.mockResolvedValue(true);

      const apiKeyData = {
        provider: "alpaca",
        apiKey: "TEST123",
        apiSecret: "SECRET123",
      };

      // Store same API key twice
      await request(app)
        .post("/api/settings/api-keys")
        .set("Authorization", `Bearer ${mockToken}`)
        .send(apiKeyData)
        .expect(200);

      await request(app)
        .post("/api/settings/api-keys")
        .set("Authorization", `Bearer ${mockToken}`)
        .send(apiKeyData)
        .expect(200);

      // Should have been called twice
      expect(storeApiKey).toHaveBeenCalledTimes(2);
    });
  });
});

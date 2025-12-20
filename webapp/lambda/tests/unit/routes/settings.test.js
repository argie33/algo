/**
 * Settings API Routes Tests
 * Tests for API key management, onboarding, and user preferences
 */
const request = require("supertest");
const express = require("express");
// Mock database before requiring the route
jest.mock("../../../utils/database", () => ({
  query: jest.fn().mockResolvedValue({ rows: [], rowCount: 0 }),
}));

// Mock authentication middleware
jest.mock("../../../middleware/auth", () => ({
  authenticateToken: (req, res, next) => {
    req.user = { sub: "test-user-id" };
    req.token = "test-jwt-token";
    next();
  },
}));

// Mock API Key Service
jest.mock("../../../utils/apiKeyService", () => ({
  listProviders: jest.fn(),
  storeApiKey: jest.fn(),
  getApiKey: jest.fn(),
  validateApiKey: jest.fn(),
  deleteApiKey: jest.fn(),
  getHealthStatus: jest.fn(),
}));

// Import mocked functions
const { query } = require('../../../utils/database');
const {
  listProviders,
  storeApiKey,
  getApiKey,
  deleteApiKey,
} = require("../../../utils/apiKeyService");
const settingsRoutes = require("../../../routes/settings");

describe("Settings API Routes", () => {
  let app;

  beforeAll(() => {
    app = express();
    app.use(express.json());
    app.use("/api/settings", settingsRoutes);
  });

  beforeEach(() => {
    jest.clearAllMocks();
  });
  describe("GET /api/settings/api-keys", () => {
    it("should return API keys for authenticated user", async () => {
      const mockProviders = [
        {
          provider: "alpaca",
          updated_at: "2023-01-01T00:00:00Z",
          created_at: "2023-01-01T00:00:00Z",
          last_used: null,
        },
      ];
      listProviders.mockResolvedValue(mockProviders);
      const response = await request(app)
        .get("/api/settings/api-keys")
        .expect(200);
      expect(response.body).toEqual({
        success: true,
        apiKeys: mockProviders,
        providers: mockProviders,
        timestamp: expect.any(String),
      });
      expect(listProviders).toHaveBeenCalledWith("test-jwt-token");
    });
    it("should handle database errors gracefully", async () => {
      listProviders.mockRejectedValue(new Error("Database connection failed"));
      const response = await request(app)
        .get("/api/settings/api-keys")
        .expect(500);
      expect(response.body).toEqual({
        success: false,
        error: "Failed to fetch API keys",
        message: "Database connection failed",
      });
    });
  });
  describe("POST /api/settings/api-keys", () => {
    it("should add new API key successfully", async () => {
      const mockStoreResult = {
        id: "1",
        provider: "alpaca",
        encrypted: true,
        user: "test-user-id",
      };
      storeApiKey.mockResolvedValue(mockStoreResult);
      const response = await request(app)
        .post("/api/settings/api-keys")
        .send({
          provider: "alpaca",
          apiKey: "test-api-key",
          apiSecret: "test-secret",
          isSandbox: true,
          description: "New API Key",
        })
        .expect(200);
      expect(response.body).toEqual({
        success: true,
        message: "alpaca API key stored successfully",
        result: {
          id: "1",
          provider: "alpaca",
          encrypted: true,
          user: "test-user-id",
        },
      });
      expect(storeApiKey).toHaveBeenCalledWith(
        "test-jwt-token",
        "alpaca",
        expect.objectContaining({
          apiKey: "test-api-key",
          apiSecret: "test-secret",
          isSandbox: true,
          description: "New API Key",
        })
      );
    });
    it("should validate required fields", async () => {
      const response = await request(app)
        .post("/api/settings/api-keys")
        .send({
          provider: "alpaca",
          // Missing apiKey
        })
        .expect(400);
      expect(response.body).toEqual({
        success: false,
        error: "Provider and API key are required",
        requiredFields: ["provider", "apiKey"],
      });
    });
    it("should handle duplicate API key errors", async () => {
      const error = new Error("API key for this provider already exists");
      storeApiKey.mockRejectedValue(error);
      const response = await request(app)
        .post("/api/settings/api-keys")
        .send({
          provider: "alpaca",
          apiKey: "test-api-key",
        })
        .expect(500);
      expect(response.body).toEqual({
        success: false,
        error: "Failed to store API key",
        message: "API key for this provider already exists",
      });
    });
  });
  describe("PUT /api/settings/api-keys/:provider", () => {
    it("should update API key successfully", async () => {
      const mockExistingData = {
        apiKey: "existing-key",
        apiSecret: "existing-secret",
        isSandbox: true,
        description: "Existing API Key",
      };
      const mockUpdateResult = {
        id: "1",
        provider: "alpaca",
        encrypted: true,
      };
      getApiKey.mockResolvedValue(mockExistingData);
      storeApiKey.mockResolvedValue(mockUpdateResult);
      const response = await request(app)
        .put("/api/settings/api-keys/alpaca")
        .send({
          description: "Updated API Key",
          isSandbox: false,
        })
        .expect(200);
      expect(response.body).toEqual({
        success: true,
        message: "alpaca API key updated successfully",
        result: {
          id: "1",
          provider: "alpaca",
          encrypted: true,
        },
      });
      expect(getApiKey).toHaveBeenCalledWith("test-jwt-token", "alpaca");
      expect(storeApiKey).toHaveBeenCalledWith(
        "test-jwt-token",
        "alpaca",
        expect.objectContaining({
          apiKey: "existing-key",
          apiSecret: "existing-secret",
          isSandbox: false,
          description: "Updated API Key",
        })
      );
    });
    it("should handle not found errors", async () => {
      getApiKey.mockResolvedValue(null);
      const response = await request(app)
        .put("/api/settings/api-keys/nonexistent")
        .send({
          description: "Updated API Key",
        })
        .expect(404);
      expect(response.body).toEqual({
        success: false,
        error: "API key configuration not found",
        provider: "nonexistent",
      });
    });
  });
  describe("DELETE /api/settings/api-keys/:provider", () => {
    it("should delete API key successfully", async () => {
      const mockDeleteResult = {
        deleted: true,
        provider: "alpaca",
      };
      deleteApiKey.mockResolvedValue(mockDeleteResult);
      const response = await request(app)
        .delete("/api/settings/api-keys/alpaca")
        .expect(200);
      expect(response.body).toEqual({
        success: true,
        message: "alpaca API key deleted successfully",
        provider: "alpaca",
      });
      expect(deleteApiKey).toHaveBeenCalledWith("test-jwt-token", "alpaca");
    });
  });
  describe("GET /api/settings/onboarding-status", () => {
    it("should return onboarding status", async () => {
      query.mockResolvedValue({
        rows: [{ onboarding_completed: true }],
      });
      listProviders.mockResolvedValue([
        { provider: "alpaca", configured: true },
      ]);
      const response = await request(app)
        .get("/api/settings/onboarding-status")
        .expect(200);
      expect(response.body).toEqual({
        success: true,
        onboarding: {
          completed: true,
          hasApiKeys: true,
          configuredProviders: 1,
          nextStep: "complete",
        },
        timestamp: expect.any(String),
      });
    });
    it("should handle missing user gracefully", async () => {
      query.mockImplementation((sql, params) => {
      // Handle COUNT queries
      if (sql.includes("SELECT COUNT") || sql.includes("COUNT(*)")) {
        return Promise.resolve({ rows: [{ count: "0", total: "0" }], rowCount: 1 });
      }
      // Handle INSERT/UPDATE/DELETE queries
      if (sql.includes("INSERT") || sql.includes("UPDATE") || sql.includes("DELETE")) {
        return Promise.resolve({ rowCount: 0, rows: [] });
      }
      // Default: return empty rows
      return Promise.resolve({ rows: [], rowCount: 0 });
    });
      listProviders.mockResolvedValue([]);
      const response = await request(app)
        .get("/api/settings/onboarding-status")
        .expect(200);
      expect(response.body.success).toBe(true);
      expect(response.body.onboarding.completed).toBe(false);
      expect(response.body.onboarding.hasApiKeys).toBe(false);
      expect(response.body.onboarding.nextStep).toBe("configure-api-keys");
    });
  });
  describe("POST /api/settings/onboarding-complete", () => {
    it("should mark onboarding as complete", async () => {
      query.mockImplementation((sql, params) => {
      // Handle COUNT queries
      if (sql.includes("SELECT COUNT") || sql.includes("COUNT(*)")) {
        return Promise.resolve({ rows: [{ count: "0", total: "0" }], rowCount: 1 });
      }
      // Handle INSERT/UPDATE/DELETE queries
      if (sql.includes("INSERT") || sql.includes("UPDATE") || sql.includes("DELETE")) {
        return Promise.resolve({ rowCount: 0, rows: [] });
      }
      // Default: return empty rows
      return Promise.resolve({ rows: [], rowCount: 0 });
    });
      const response = await request(app)
        .post("/api/settings/onboarding-complete")
        .expect(200);
      expect(response.body).toEqual({
        success: true,
        message: "Onboarding completed successfully",
        timestamp: expect.any(String),
      });
    });
  });
  describe("GET /api/settings/preferences", () => {
    it("should return user preferences", async () => {
      const mockPreferences = {
        riskTolerance: "moderate",
        investmentStyle: "growth",
        notifications: true,
      };
      query.mockResolvedValue({
        rows: [{ preferences: mockPreferences }],
      });
      const response = await request(app)
        .get("/api/settings/preferences")
        .expect(200);
      expect(response.body).toEqual({
        success: true,
        preferences: mockPreferences,
        timestamp: expect.any(String),
      });
    });
    it("should handle missing preferences gracefully", async () => {
      query.mockImplementation((sql, params) => {
      // Handle COUNT queries
      if (sql.includes("SELECT COUNT") || sql.includes("COUNT(*)")) {
        return Promise.resolve({ rows: [{ count: "0", total: "0" }], rowCount: 1 });
      }
      // Handle INSERT/UPDATE/DELETE queries
      if (sql.includes("INSERT") || sql.includes("UPDATE") || sql.includes("DELETE")) {
        return Promise.resolve({ rowCount: 0, rows: [] });
      }
      // Default: return empty rows
      return Promise.resolve({ rows: [], rowCount: 0 });
    });
      const response = await request(app)
        .get("/api/settings/preferences")
        .expect(200);
      expect(response.body.success).toBe(true);
      expect(response.body.preferences).toEqual({
        theme: "light",
        notifications: true,
        defaultView: "dashboard",
      });
    });
  });
  describe("POST /api/settings/preferences", () => {
    it("should save user preferences", async () => {
      query.mockImplementation((sql, params) => {
      // Handle COUNT queries
      if (sql.includes("SELECT COUNT") || sql.includes("COUNT(*)")) {
        return Promise.resolve({ rows: [{ count: "0", total: "0" }], rowCount: 1 });
      }
      // Handle INSERT/UPDATE/DELETE queries
      if (sql.includes("INSERT") || sql.includes("UPDATE") || sql.includes("DELETE")) {
        return Promise.resolve({ rowCount: 0, rows: [] });
      }
      // Default: return empty rows
      return Promise.resolve({ rows: [], rowCount: 0 });
    });
      const preferences = {
        riskTolerance: "aggressive",
        investmentStyle: "value",
        notifications: false,
        autoRefresh: true,
      };
      const response = await request(app)
        .post("/api/settings/preferences")
        .send({ preferences })
        .expect(200);
      expect(response.body.success).toBe(true);
      expect(response.body.preferences).toEqual({
        riskTolerance: "aggressive",
        investmentStyle: "value",
        notifications: false,
        autoRefresh: true,
      });
      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("INSERT INTO user_profiles"),
        ["test-user-id", JSON.stringify(preferences)]
      );
    });
    it("should handle invalid preferences format", async () => {
      query.mockImplementation((sql, params) => {
      // Handle COUNT queries
      if (sql.includes("SELECT COUNT") || sql.includes("COUNT(*)")) {
        return Promise.resolve({ rows: [{ count: "0", total: "0" }], rowCount: 1 });
      }
      // Handle INSERT/UPDATE/DELETE queries
      if (sql.includes("INSERT") || sql.includes("UPDATE") || sql.includes("DELETE")) {
        return Promise.resolve({ rowCount: 0, rows: [] });
      }
      // Default: return empty rows
      return Promise.resolve({ rows: [], rowCount: 0 });
    });
      const response = await request(app)
        .post("/api/settings/preferences")
        .send({
          riskTolerance: "invalid-value",
          maliciousField: '<script>alert("xss")</script>',
        })
        .expect(400);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("Valid preferences object is required");
    });
  });
});

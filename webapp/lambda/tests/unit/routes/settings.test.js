/**
 * Settings API Routes Tests
 * Tests for API key management, onboarding, and user preferences
 */

const request = require("supertest");
const express = require("express");
// Mock database before requiring the route
jest.mock("../../../utils/database", () => ({
  query: jest.fn(),
}));

const { query } = require("../../../utils/database");

// Mock authentication middleware
jest.mock("../../../middleware/auth", () => ({
  authenticateToken: (req, res, next) => {
    req.user = { sub: "test-user-id" };
    next();
  },
}));

const settingsRoutes = require("../../../routes/settings");
const app = express();
app.use(express.json());
app.use("/api/settings", settingsRoutes);

describe("Settings API Routes", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe("GET /api/settings/api-keys", () => {
    it("should return API keys for authenticated user", async () => {
      const mockRows = [
        {
          id: "1",
          provider: "alpaca",
          description: "Test API Key",
          isSandbox: true,
          isActive: true,
          createdAt: "2023-01-01T00:00:00Z",
          lastUsed: null,
        },
      ];

      query.mockResolvedValue({ rows: mockRows });

      const response = await request(app)
        .get("/api/settings/api-keys")
        .expect(200);

      expect(response.body).toEqual({
        success: true,
        apiKeys: [
          {
            id: "1",
            provider: "alpaca",
            description: "Test API Key",
            isSandbox: true,
            isActive: true,
            createdAt: "2023-01-01T00:00:00Z",
            lastUsed: null,
            apiKey: "****",
          },
        ],
      });

      expect(query).toHaveBeenCalledWith(expect.stringContaining("SELECT"), [
        "test-user-id",
      ]);
    });

    it("should handle database errors gracefully", async () => {
      query.mockRejectedValue(new Error("Database connection failed"));

      const response = await request(app)
        .get("/api/settings/api-keys")
        .expect(500);

      expect(response.body).toEqual({
        success: false,
        error: "Failed to fetch API keys",
      });
    });
  });

  describe("POST /api/settings/api-keys", () => {
    it("should add new API key successfully", async () => {
      const mockRow = {
        id: "1",
        provider: "alpaca",
        description: "New API Key",
        isSandbox: true,
        createdAt: "2023-01-01T00:00:00Z",
      };

      query.mockResolvedValue({ rows: [mockRow] });

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
        message: "API key added successfully",
        apiKey: mockRow,
      });

      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("INSERT INTO user_api_keys"),
        expect.arrayContaining(["test-user-id", "alpaca"])
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
      });
    });

    it("should handle duplicate API key errors", async () => {
      const error = new Error("Duplicate key");
      error.code = "23505";
      query.mockRejectedValue(error);

      const response = await request(app)
        .post("/api/settings/api-keys")
        .send({
          provider: "alpaca",
          apiKey: "test-api-key",
        })
        .expect(400);

      expect(response.body).toEqual({
        success: false,
        error: "API key for this provider already exists",
      });
    });
  });

  describe("PUT /api/settings/api-keys/:keyId", () => {
    it("should update API key successfully", async () => {
      const mockRow = {
        id: "1",
        provider: "alpaca",
        description: "Updated API Key",
        isSandbox: false,
      };

      query.mockResolvedValue({ rows: [mockRow] });

      const response = await request(app)
        .put("/api/settings/api-keys/1")
        .send({
          description: "Updated API Key",
          isSandbox: false,
        })
        .expect(200);

      expect(response.body).toEqual({
        success: true,
        message: "API key updated successfully",
        apiKey: mockRow,
      });
    });

    it("should handle not found errors", async () => {
      query.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .put("/api/settings/api-keys/999")
        .send({
          description: "Updated API Key",
        })
        .expect(404);

      expect(response.body).toEqual({
        success: false,
        error: "API key not found",
      });
    });
  });

  describe("DELETE /api/settings/api-keys/:keyId", () => {
    it("should delete API key successfully", async () => {
      query.mockResolvedValue({
        rows: [{ id: "1", provider: "alpaca" }],
      });

      const response = await request(app)
        .delete("/api/settings/api-keys/1")
        .expect(200);

      expect(response.body).toEqual({
        success: true,
        message: "API key deleted successfully",
      });
    });
  });

  describe("GET /api/settings/onboarding-status", () => {
    it("should return onboarding status", async () => {
      query.mockResolvedValue({
        rows: [{ onboarding_complete: true }],
      });

      const response = await request(app)
        .get("/api/settings/onboarding-status")
        .expect(200);

      expect(response.body).toEqual({
        success: true,
        data: {
          isComplete: true,
          userId: "test-user-id",
        },
      });
    });

    it("should handle missing user gracefully", async () => {
      query.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get("/api/settings/onboarding-status")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.onboarding.completed).toBe(false);
    });
  });

  describe("POST /api/settings/onboarding-complete", () => {
    it("should mark onboarding as complete", async () => {
      query.mockResolvedValue({ rows: [] });

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
      query.mockResolvedValue({ rows: [] });

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
      query.mockResolvedValue({ rows: [] });

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
      query.mockResolvedValue({ rows: [] });

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

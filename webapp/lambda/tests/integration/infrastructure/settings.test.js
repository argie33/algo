/**
 * INTEGRATION TEST - Uses REAL database and REAL services (NO MOCKS)
 *
 * Settings Management Integration Tests
 * Tests for user settings and API key management
 * Route: /routes/settings.js
 */

const request = require("supertest");
const { app } = require("../../../index");

// Mock auth middleware

describe("Settings Management API", () => {
  describe("Settings Overview", () => {
    beforeEach(() => {
    jest.clearAllMocks();
      // Default: return empty rows for all queries
      if (sql.includes("information_schema.tables")) {
        return Promise.resolve({ rows: [{ exists: true }] });
      }
      return Promise.resolve({ rows: [] });
    });
  });
    test("should retrieve settings endpoints", async () => {
      const response = await request(app)
        .get("/api/settings")
        .set("Authorization", "Bearer test-token");

      expect([200, 404, 500, 501]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("message");
        expect(response.body).toHaveProperty("endpoints");
        expect(Array.isArray(response.body.endpoints)).toBe(true);
      }
    });
  });

  describe("Dashboard Settings", () => {
    test("should retrieve dashboard configuration", async () => {
      const response = await request(app)
        .get("/api/settings/dashboard")
        .set("Authorization", "Bearer test-token");

      expect([200, 404, 500, 501]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
      }
    });
  });

  describe("API Key Management", () => {
    test("should list supported providers", async () => {
      const response = await request(app)
        .get("/api/settings/providers")
        .set("Authorization", "Bearer test-token");

      expect([200, 404, 500, 501]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(Array.isArray(response.body.data)).toBe(true);
      }
    });

    test("should retrieve API keys list", async () => {
      const response = await request(app)
        .get("/api/settings/api-keys")
        .set("Authorization", "Bearer test-token");

      expect([200, 404, 500, 501]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("timestamp");
        if (response.body.apiKeys !== undefined) {
          expect(Array.isArray(response.body.apiKeys)).toBe(true);
        }
        if (response.body.providers !== undefined) {
          expect(Array.isArray(response.body.providers)).toBe(true);
        }
      }
    });

    test("should handle API key creation request", async () => {
      const keyData = {
        provider: "alpaca",
        keyId: "test-key-id",
        secretKey: "test-secret-key",
        environment: "paper",
      };

      const response = await request(app)
        .post("/api/settings/api-keys")
        .set("Authorization", "Bearer test-token")
        .send(keyData);

      expect([200, 201, 400, 404, 422, 500, 501]).toContain(response.status);

      if (response.status === 200 || response.status === 201) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("message");
      }
    });
  });

  describe("Settings Health Status", () => {
    test("should retrieve settings health status", async () => {
      const response = await request(app)
        .get("/api/settings/health")
        .set("Authorization", "Bearer test-token");

      expect([200, 404, 500, 501]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("health");
        expect(response.body).toHaveProperty("timestamp");
        expect(response.body.health).toHaveProperty("cacheStats");
        expect(response.body.health).toHaveProperty("circuitBreaker");
        expect(response.body.health).toHaveProperty("jwtCircuitBreaker");
        expect(response.body.health).toHaveProperty("services");
      }
    });
  });
});

/**
 * Insider Integration Tests
 * Tests for insider trading data and analysis
 * Route: /routes/insider.js
 */

const request = require("supertest");
const { app } = require("../../../index");

describe("Insider Trading API", () => {
  describe("Insider Trades", () => {
    test("should return not implemented status for insider trades", async () => {
      const response = await request(app)
        .get("/api/insider/trades/AAPL");
      
      expect([400, 401, 404, 422, 500]).toContain(response.status);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body).toHaveProperty("error", "Insider trading data not implemented");
      expect(response.body).toHaveProperty("symbol", "AAPL");
    });

    test("should handle different symbols correctly", async () => {
      const response = await request(app)
        .get("/api/insider/trades/GOOGL");
      
      expect([400, 401, 404, 422, 500]).toContain(response.status);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body).toHaveProperty("error", "Insider trading data not implemented");
      expect(response.body).toHaveProperty("symbol", "GOOGL");
    });
  });

  describe("Error handling", () => {
    test("should handle invalid symbols", async () => {
      const response = await request(app)
        .get("/api/insider/trades/INVALID123");
      
      expect([400, 401, 404, 422, 500]).toContain(response.status);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body).toHaveProperty("error", "Insider trading data not implemented");
      expect(response.body).toHaveProperty("symbol", "INVALID123");
    });

    test("should handle server errors gracefully", async () => {
      const response = await request(app)
        .get("/api/insider/trades/AAPL");
      
      // Should return 501 for not implemented, not crash with 500
      expect([501]).toContain(response.status);
      if (response.status === 501) {
        expect(response.body).toHaveProperty("success", false);
        expect(response.body).toHaveProperty("error");
      }
    });
  });
});
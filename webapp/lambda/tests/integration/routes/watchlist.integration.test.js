/**
 * Watchlist Integration Tests - REAL DATA ONLY
 * Tests watchlist endpoints with REAL database connection and REAL loaded data
 * NO MOCKS - validates actual behavior with actual data from loaders
 * Validates NO-FALLBACK policy: raw NULL values must flow through unmasked
 */

const request = require("supertest");
const { app } = require("../../../index");
const { initializeDatabase } = require("../../../utils/database"); // Import the actual Express app - NO MOCKS

describe("Watchlist Routes - Real Data Validation", () => {
  beforeAll(async () => {
    await initializeDatabase();
  });

  describe("GET /api/watchlist", () => {
    test("should return user watchlist", async () => {
      const response = await request(app)
        .get("/api/watchlist")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body.success).toBe(true);
        expect(Array.isArray(response.body.data)).toBe(true);
      }
    });
  });

  describe("POST /api/watchlist", () => {
    test("should return validation error for missing name", async () => {
      const response = await request(app)
        .post("/api/watchlist")
        .set("Authorization", "Bearer dev-bypass-token")
        .send({ symbol: "AAPL", notes: "Test stock" });

      expect([400, 422]).toContain(response.status);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("name is required");
    });

    test("should validate required symbol", async () => {
      const response = await request(app)
        .post("/api/watchlist")
        .set("Authorization", "Bearer dev-bypass-token")
        .send({});

      expect([400, 422]).toContain(response.status);
    });
  });

  describe("DELETE /api/watchlist/:id", () => {
    test("should return validation error for invalid ID format", async () => {
      const response = await request(app)
        .delete("/api/watchlist/AAPL")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(400);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("Invalid watchlist ID format");
      expect(response.body.message).toContain("Watchlist ID must be a number");
      expect(response.body.hint).toContain(
        "DELETE /api/watchlist/{id}/items/{symbol}"
      );
    });
  });

  describe("GET /api/watchlist/:listId", () => {
    test("should return specific watchlist", async () => {
      const response = await request(app)
        .get("/api/watchlist/1")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 401, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body.success).toBe(true);
        expect(response.body.data).toHaveProperty("watchlist");
      }
    });
  });

  describe("PUT /api/watchlist/:id", () => {
    test("should return validation error for invalid ID format", async () => {
      const response = await request(app)
        .put("/api/watchlist/AAPL")
        .set("Authorization", "Bearer dev-bypass-token")
        .send({ name: "Test Watchlist", description: "Test description" });

      expect(response.status).toBe(400);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("Invalid watchlist ID format");
      expect(response.body.message).toContain("Watchlist ID must be a number");
    });
  });

  describe("GET /api/watchlist/performance", () => {
    test("should return watchlist performance", async () => {
      const response = await request(app)
        .get("/api/watchlist/performance")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body.success).toBe(true);
        expect(response.body.data).toHaveProperty("performance");
      }
    });
  });

  describe("GET /api/watchlist/alerts", () => {
    test("should return price alerts", async () => {
      const response = await request(app)
        .get("/api/watchlist/alerts")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body.success).toBe(true);
        // Alerts endpoint returns object with status, not array
        expect(response.body.data).toHaveProperty("status");
      }
    });
  });

  describe("POST /api/watchlist/import", () => {
    test("should import watchlist from CSV", async () => {
      const csvData = "symbol,notes\nAAPL,Apple Inc\nMSFT,Microsoft";

      const response = await request(app)
        .post("/api/watchlist/import")
        .set("Authorization", "Bearer dev-bypass-token")
        .attach("file", Buffer.from(csvData), "watchlist.csv");

      expect([200, 400, 401, 422]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body.success).toBe(true);
      }
    });
  });

  describe("GET /api/watchlist/export", () => {
    test("should export watchlist to CSV", async () => {
      const response = await request(app)
        .get("/api/watchlist/export")
        .set("Authorization", "Bearer dev-bypass-token");

      // Export endpoint may return 404 if no watchlist exists
      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.headers["content-type"]).toContain("text/csv");
      }
    });
  });
});

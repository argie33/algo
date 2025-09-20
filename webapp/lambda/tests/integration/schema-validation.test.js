const request = require("supertest");
const {
  initializeDatabase,
  closeDatabase,
} = require("../../utils/database");

let app;

describe("Schema Validation Tests", () => {
  beforeAll(async () => {
    await initializeDatabase();
    app = require("../../server");
  });

  afterAll(async () => {
    await closeDatabase();
  });

  describe("Critical Route Schema Validation", () => {
    // Test that screener route works with correct schema
    test("screener route should return 200 not 500", async () => {
      const response = await request(app).get("/api/screener/technical");

      // This should NEVER return 500 - indicates schema mismatch
      expect(response.status).not.toBe(500);

      // Should return valid response
      if (response.status === 200) {
        expect(response.body.success).toBe(true);
        expect(Array.isArray(response.body.data)).toBe(true);
      }
    });

    // Test other critical routes for schema issues
    test("stocks route should not have schema errors", async () => {
      const response = await request(app).get("/api/stocks?limit=5");

      expect(response.status).not.toBe(500);
      if (response.status === 200) {
        expect(response.body.success).toBe(true);
      }
    });

    test("portfolio route should not have schema errors", async () => {
      const response = await request(app).get("/api/portfolio");

      expect(response.status).not.toBe(500);
      if (response.status === 200) {
        expect(response.body.success).toBe(true);
      }
    });

    test("market route should not have schema errors", async () => {
      const response = await request(app).get("/api/market/summary");

      expect(response.status).not.toBe(500);
      if (response.status === 200) {
        expect(response.body.success).toBe(true);
      }
    });

    test("sectors route should not have schema errors", async () => {
      const response = await request(app).get("/api/sectors");

      expect(response.status).not.toBe(500);
      if (response.status === 200) {
        expect(response.body.success).toBe(true);
      }
    });
  });

  describe("Database Schema Consistency", () => {
    test("should use correct company profile schema", async () => {
      // Test that routes use cp.short_name not cp.name
      const response = await request(app).get("/api/screener/screen?market_cap_min=1000000000&limit=1");

      expect(response.status).toBe(200);

      if (response.body.data && response.body.data.length > 0) {
        const stock = response.body.data[0];
        // Should have company_name field populated correctly
        if (stock.company_name) {
          expect(typeof stock.company_name).toBe('string');
          expect(stock.company_name.length).toBeGreaterThan(0);
        }
      }
    });

    test("should handle missing data gracefully", async () => {
      // Test with filters that might return empty results
      const response = await request(app).get("/api/screener/screen?market_cap_min=999999999999");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(Array.isArray(response.body.data)).toBe(true);
    });
  });

  describe("Error Detection", () => {
    test("should never return 500 errors for valid requests", async () => {
      const routes = [
        "/api/screener",
        "/api/screener/technical",
        "/api/screener/growth",
        "/api/screener/value",
        "/api/stocks",
        "/api/portfolio",
        "/api/market/summary",
        "/api/sectors"
      ];

      for (const route of routes) {
        const response = await request(app).get(route);

        // Critical: No 500 errors allowed for schema issues
        expect(response.status).not.toBe(500);

        // If we get other errors, they should be properly formatted
        if (response.status >= 400) {
          expect(response.body).toHaveProperty('error');
        }
      }
    });

    test("should have consistent error response format", async () => {
      // Test an invalid route that should return 404
      const response = await request(app).get("/api/invalid-route-12345");

      expect([404, 405]).toContain(response.status);
      // Should not return 500 due to route handler issues
      expect(response.status).not.toBe(500);
    });
  });
});
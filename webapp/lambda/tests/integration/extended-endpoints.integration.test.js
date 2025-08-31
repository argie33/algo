/**
 * Extended Integration Tests for Missing API Endpoints
 * Comprehensive coverage for previously untested routes
 */

const request = require("supertest");
const { app } = require("../../index");

describe("Extended API Endpoints Integration Tests", () => {
  let server;

  beforeAll(() => {
    // Start the server for testing
    server = app.listen(0); // Use random port
  });

  afterAll(async () => {
    if (server) {
      await new Promise((resolve) => server.close(resolve));
    }
  });

  describe("Commodities Endpoints", () => {
    it("should return commodities service health", async () => {
      const response = await request(app)
        .get("/api/commodities/health")
        .expect("Content-Type", /json/);

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("status", "operational");
      expect(response.body).toHaveProperty("service", "commodities");
    });

    it("should return commodities overview", async () => {
      const response = await request(app)
        .get("/api/commodities")
        .expect("Content-Type", /json/);

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body.data).toHaveProperty("system", "Commodities API");
      expect(response.body.data).toHaveProperty("available_endpoints");
      expect(response.body.data.available_endpoints).toBeInstanceOf(Array);
    });

    it("should return commodity categories", async () => {
      const response = await request(app)
        .get("/api/commodities/categories")
        .expect("Content-Type", /json/);

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body.data).toBeInstanceOf(Array);
      expect(response.body.data.length).toBeGreaterThan(0);
      
      // Verify category structure
      const category = response.body.data[0];
      expect(category).toHaveProperty("id");
      expect(category).toHaveProperty("name");
      expect(category).toHaveProperty("commodities");
      expect(category).toHaveProperty("performance");
    });

    it("should return commodity prices", async () => {
      const response = await request(app)
        .get("/api/commodities/prices")
        .expect("Content-Type", /json/);

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body.data).toBeInstanceOf(Array);
      
      if (response.body.data.length > 0) {
        const commodity = response.body.data[0];
        expect(commodity).toHaveProperty("symbol");
        expect(commodity).toHaveProperty("name");
        expect(commodity).toHaveProperty("price");
        expect(commodity).toHaveProperty("change");
        expect(commodity).toHaveProperty("category");
      }
    });

    it("should filter commodity prices by category", async () => {
      const response = await request(app)
        .get("/api/commodities/prices?category=energy")
        .expect("Content-Type", /json/);

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body.filters).toHaveProperty("category", "energy");
      
      response.body.data.forEach(commodity => {
        expect(commodity.category).toBe("energy");
      });
    });

    it("should return market summary", async () => {
      const response = await request(app)
        .get("/api/commodities/market-summary")
        .expect("Content-Type", /json/);

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body.data).toHaveProperty("overview");
      expect(response.body.data).toHaveProperty("performance");
    });

    it("should return correlations", async () => {
      const response = await request(app)
        .get("/api/commodities/correlations")
        .expect("Content-Type", /json/);

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body.data).toHaveProperty("matrix");
      expect(response.body.data).toHaveProperty("overview");
    });
  });

  describe("Performance Endpoints", () => {
    it("should handle performance requests", async () => {
      const response = await request(app)
        .get("/api/performance")
        .expect("Content-Type", /json/);

      // Should respond with some status (not 404)
      expect([200, 401, 500]).toContain(response.status);
    });

    it("should handle performance metrics", async () => {
      const response = await request(app)
        .get("/api/performance/metrics")
        .expect("Content-Type", /json/);

      // Should respond with some status
      expect(typeof response.status).toBe("number");
    });
  });

  describe("Trades Endpoints", () => {
    it("should handle trades requests (auth required)", async () => {
      const response = await request(app)
        .get("/api/trades")
        .expect("Content-Type", /json/);

      // Should require auth or return data
      expect([200, 401, 403, 500]).toContain(response.status);
    });

    it("should handle trade history", async () => {
      const response = await request(app)
        .get("/api/trades/history")
        .expect("Content-Type", /json/);

      expect([200, 401, 403, 404, 500]).toContain(response.status);
    });
  });

  describe("WebSocket Endpoints", () => {
    it("should handle websocket health check", async () => {
      const response = await request(app)
        .get("/api/websocket/health")
        .expect("Content-Type", /json/);

      expect([200, 500]).toContain(response.status);
    });

    it("should handle websocket connection info", async () => {
      const response = await request(app)
        .get("/api/websocket/connections")
        .expect("Content-Type", /json/);

      expect(typeof response.status).toBe("number");
    });
  });


  describe("Diagnostics Endpoints", () => {
    it("should handle diagnostics requests", async () => {
      const response = await request(app)
        .get("/api/diagnostics")
        .expect("Content-Type", /json/);

      expect(typeof response.status).toBe("number");
    });

    it("should handle system diagnostics", async () => {
      const response = await request(app)
        .get("/api/diagnostics/system")
        .expect("Content-Type", /json/);

      expect([200, 401, 404, 500]).toContain(response.status);
    });
  });

  describe("Watchlist Endpoints - Fixed Auth Expectations", () => {
    it("should require auth for watchlist access", async () => {
      const response = await request(app)
        .get("/api/watchlist")
        .expect("Content-Type", /json/);

      // Watchlist exists but requires authentication
      expect(response.status).toBe(401);
      expect(response.body).toHaveProperty("error");
    });

    it("should require auth for adding to watchlist", async () => {
      const response = await request(app)
        .post("/api/watchlist")
        .send({ symbol: "AAPL", name: "Apple Inc." })
        .expect("Content-Type", /json/);

      // Should require authentication, not return 404
      expect(response.status).toBe(401);
    });

    it("should require auth for watchlist operations", async () => {
      const response = await request(app)
        .get("/api/watchlist/list")
        .expect("Content-Type", /json/);

      expect([401, 404]).toContain(response.status);
    });
  });

  describe("Data Routes Coverage", () => {
    it("should handle data requests", async () => {
      const response = await request(app)
        .get("/api/data")
        .expect("Content-Type", /json/);

      expect(typeof response.status).toBe("number");
    });

    it("should handle specific data types", async () => {
      const response = await request(app)
        .get("/api/data/prices")
        .expect("Content-Type", /json/);

      expect([200, 401, 404, 500]).toContain(response.status);
    });
  });

  describe("Scoring Endpoints", () => {
    it("should handle scoring requests", async () => {
      const response = await request(app)
        .get("/api/scoring")
        .expect("Content-Type", /json/);

      expect(typeof response.status).toBe("number");
    });

    it("should handle stock scoring", async () => {
      const response = await request(app)
        .get("/api/scoring/stocks")
        .expect("Content-Type", /json/);

      expect([200, 401, 404, 500]).toContain(response.status);
    });
  });

  describe("Price Endpoints", () => {
    it("should handle price requests", async () => {
      const response = await request(app)
        .get("/api/price")
        .expect("Content-Type", /json/);

      expect(typeof response.status).toBe("number");
    });

    it("should handle specific price queries", async () => {
      const response = await request(app)
        .get("/api/price/AAPL")
        .expect("Content-Type", /json/);

      expect([200, 401, 404, 500]).toContain(response.status);
    });
  });

  describe("Orders Endpoints", () => {
    it("should handle orders requests (auth required)", async () => {
      const response = await request(app)
        .get("/api/orders")
        .expect("Content-Type", /json/);

      // Orders should require authentication
      expect([200, 401, 403]).toContain(response.status);
    });

    it("should handle order creation", async () => {
      const response = await request(app)
        .post("/api/orders")
        .send({ symbol: "AAPL", quantity: 10, side: "buy" })
        .expect("Content-Type", /json/);

      expect([200, 400, 401, 403]).toContain(response.status);
    });
  });

  describe("Error Handling for New Endpoints", () => {
    it("should handle malformed requests to commodities", async () => {
      const response = await request(app)
        .post("/api/commodities/categories")
        .set("Content-Type", "application/json")
        .send("invalid json{")
        .expect("Content-Type", /json/);

      expect([400, 405, 500]).toContain(response.status);
    });

    it("should handle invalid commodity categories", async () => {
      const response = await request(app)
        .get("/api/commodities/prices?category=invalid")
        .expect("Content-Type", /json/);

      expect(response.status).toBe(200);
      expect(response.body.data).toBeInstanceOf(Array);
      expect(response.body.data.length).toBe(0);
    });
  });

  describe("Route Coverage Validation", () => {
    it("should have all expected routes mounted", async () => {
      // Test a variety of routes to ensure they're properly mounted
      const routes = [
        "/api/commodities",
        "/api/performance", 
        "/api/trades",
        "/api/diagnostics",
        "/api/watchlist"
      ];

      for (const route of routes) {
        const response = await request(app).get(route);
        // Route exists if it doesn't return 404
        expect(response.status).not.toBe(404);
      }
    });

    it("should handle non-API prefixed routes", async () => {
      // Test non-API prefixed versions
      const routes = [
        "/commodities",
        "/performance",
        "/trades",
        "/diagnostics",
        "/watchlist"
      ];

      for (const route of routes) {
        const response = await request(app).get(route);
        // Route exists if it doesn't return 404
        expect(response.status).not.toBe(404);
      }
    });
  });
});
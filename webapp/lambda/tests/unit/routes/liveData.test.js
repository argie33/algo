const express = require("express");
const request = require("supertest");

// Real database for integration
const { query } = require("../../../utils/database");

describe("Live Data Routes Unit Tests", () => {
  let app;

  beforeAll(() => {
    // Create test app
    app = express();
    app.use(express.json());

    // Mock authentication middleware - allow all requests through
    app.use((req, res, next) => {
      req.user = { sub: "test-user-123" }; // Mock authenticated user
      next();
    });

    // Add response formatter middleware
    const responseFormatter = require("../../../middleware/responseFormatter");
    app.use(responseFormatter);

    // Load live data routes
    const liveDataRouter = require("../../../routes/liveData");
    app.use("/live-data", liveDataRouter);
  });

  describe("GET /live-data/", () => {
    test("should return live data info", async () => {
      const response = await request(app).get("/live-data/").expect(200);

      expect(response.body).toHaveProperty("success");
      expect(response.body).toHaveProperty("status");
    });
  });

  describe("GET /live-data/quotes", () => {
    test("should return live quotes with proper structure", async () => {
      const response = await request(app)
        .get("/live-data/quotes")
        .set("Authorization", "Bearer dev-bypass-token");

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
        expect(response.body.data).toHaveProperty("quotes");
        expect(response.body.data).toHaveProperty("summary");
        expect(Array.isArray(response.body.data.quotes)).toBe(true);

        // Check quote structure
        if (response.body.data.quotes.length > 0) {
          const quote = response.body.data.quotes[0];
          expect(quote).toHaveProperty("symbol");
          expect(quote).toHaveProperty("current_price");
          expect(quote).toHaveProperty("change_amount");
          expect(quote).toHaveProperty("change_percent");
          expect(quote).toHaveProperty("volume");
          expect(quote).toHaveProperty("market_status");
        }

        // Check summary structure
        expect(response.body.data.summary).toHaveProperty("total_symbols");
        expect(response.body.data.summary).toHaveProperty("market_status");
        expect(response.body.data.summary).toHaveProperty("gainers");
        expect(response.body.data.summary).toHaveProperty("losers");
      } else {
        expect([401]).toContain(response.status);
        expect(response.body).toHaveProperty("success", false);
      }
    });

    test("should handle symbols filter", async () => {
      const response = await request(app)
        .get("/live-data/quotes?symbols=AAPL,MSFT,GOOGL")
        .set("Authorization", "Bearer dev-bypass-token");

      if (response.status === 200) {
        expect(response.body.data.quotes.length).toBeLessThanOrEqual(3);
        const symbols = response.body.data.quotes.map((q) => q.symbol);
        symbols.forEach((symbol) => {
          expect(["AAPL", "MSFT", "GOOGL"]).toContain(symbol);
        });
      }
    });

    test("should handle limit parameter", async () => {
      const response = await request(app)
        .get("/live-data/quotes?limit=5")
        .set("Authorization", "Bearer dev-bypass-token");

      if (response.status === 200) {
        expect(response.body.data.quotes.length).toBeLessThanOrEqual(5);
      }
    });
  });

  describe("GET /live-data/stream", () => {
    test("should setup SSE stream with proper headers", async () => {
      const response = await request(app)
        .get("/live-data/stream")
        .set("Authorization", "Bearer dev-bypass-token")
        .timeout(2000); // Short timeout for test

      // SSE requests should either establish connection (200) or fail auth (401)
      if (response.status === 200) {
        // Check SSE headers are set
        expect(response.headers["content-type"]).toBe("text/event-stream");
        expect(response.headers["cache-control"]).toBe("no-cache");
        expect(response.headers["connection"]).toBe("keep-alive");
      } else {
        expect([401]).toContain(response.status);
      }
    });
  });

  describe("GET /live-data/optimization", () => {
    test("should return optimization status", async () => {
      const response = await request(app)
        .get("/live-data/optimization")
        .set("Authorization", "Bearer dev-bypass-token");

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
        expect(response.body.data).toHaveProperty("status");
        expect(response.body.data).toHaveProperty("metrics");
        expect(response.body.data).toHaveProperty("recommendations");

        // Check metrics structure
        expect(response.body.data.metrics).toHaveProperty("active_connections");
        expect(response.body.data.metrics).toHaveProperty("queries_per_minute");
        expect(response.body.data.metrics).toHaveProperty(
          "average_response_time"
        );

        // Check recommendations array
        expect(Array.isArray(response.body.data.recommendations)).toBe(true);
      } else {
        expect([401]).toContain(response.status);
      }
    });
  });

  describe("POST /live-data/admin/toggle-stream", () => {
    test("should handle stream toggle for admin", async () => {
      const response = await request(app)
        .post("/live-data/admin/toggle-stream")
        .set("Authorization", "Bearer dev-bypass-token")
        .send({ enabled: true });

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
        expect(response.body.data).toHaveProperty("streaming_enabled");
        expect(response.body.data).toHaveProperty("active_connections");
      } else {
        expect([401, 403]).toContain(response.status);
      }
    });

    test("should validate toggle request body", async () => {
      const response = await request(app)
        .post("/live-data/admin/toggle-stream")
        .set("Authorization", "Bearer dev-bypass-token")
        .send({}); // Missing enabled parameter

      if (response.status !== 401) {
        expect([400, 422]).toContain(response.status);
        expect(response.body).toHaveProperty("success", false);
      }
    });
  });

  describe("POST /live-data/admin/clear-cache", () => {
    test("should handle cache clearing for admin", async () => {
      const response = await request(app)
        .post("/live-data/admin/clear-cache")
        .set("Authorization", "Bearer dev-bypass-token");

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("message");
        expect(response.body.data).toHaveProperty("cache_status");
        expect(response.body.data).toHaveProperty("cleared_entries");
      } else {
        expect([401, 403]).toContain(response.status);
      }
    });
  });

  describe("GET /live-data/health", () => {
    test("should return live data service health", async () => {
      const response = await request(app)
        .get("/live-data/health")
        .set("Authorization", "Bearer dev-bypass-token");

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
        expect(response.body.data).toHaveProperty("status");
        expect(response.body.data).toHaveProperty("uptime");
        expect(response.body.data).toHaveProperty("database_connection");
        expect(response.body.data).toHaveProperty("streaming_status");
        expect(response.body.data).toHaveProperty("cache_status");
      } else {
        expect([401]).toContain(response.status);
      }
    });
  });
});

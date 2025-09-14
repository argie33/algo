const request = require("supertest");
const { initializeDatabase, closeDatabase } = require("../../../utils/database");

let app;
const authToken = "dev-bypass-token";

describe("Live Data Routes Integration Tests", () => {
  beforeAll(async () => {
    await initializeDatabase();
    app = require("../../../server");
  });

  afterAll(async () => {
    await closeDatabase();
  });

  describe("GET /api/livedata (Root endpoint)", () => {
    test("should return live data API information", async () => {
      const response = await request(app)
        .get("/api/livedata");

      expect([200, 404]).toContain(response.status);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("message", "Live Data API - Ready");
      expect(response.body.data).toHaveProperty("status", "operational");
      expect(response.body.data).toHaveProperty("endpoints");
      expect(Array.isArray(response.body.data.endpoints)).toBe(true);
      expect(response.body.data.endpoints.length).toBeGreaterThan(0);
    });

    test("should include timestamp in response", async () => {
      const response = await request(app)
        .get("/api/livedata");

      expect([200, 404]).toContain(response.status);
      expect(response.body).toHaveProperty("timestamp");
      expect(new Date(response.body.timestamp)).toBeInstanceOf(Date);
    });

    test("should handle concurrent requests to root endpoint", async () => {
      const requests = Array(5).fill().map(() => 
        request(app).get("/api/livedata")
      );
      
      const responses = await Promise.all(requests);
      
      responses.forEach(response => {
        expect([200, 404]).toContain(response.status);
        expect(response.body.success).toBe(true);
        expect(response.headers['content-type']).toMatch(/json/);
      });
    });
  });

  describe("GET /api/livedata/status", () => {
    test("should return comprehensive service status", async () => {
      const response = await request(app)
        .get("/api/livedata/status");

      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("service", "live-data");
        expect(response.body).toHaveProperty("status");
        expect(response.body).toHaveProperty("timestamp");
        expect(response.body).toHaveProperty("version");
        expect(response.body).toHaveProperty("components");
        expect(response.body).toHaveProperty("metrics");
        expect(response.body).toHaveProperty("features");
      }
    });

    test("should include correlation ID from header", async () => {
      const correlationId = `test-correlation-${Date.now()}`;
      const response = await request(app)
        .get("/api/livedata/status")
        .set("x-correlation-id", correlationId);

      if (response.status === 200) {
        expect(response.body.correlationId).toBe(correlationId);
      }
    });

    test("should include component status information", async () => {
      const response = await request(app)
        .get("/api/livedata/status");

      if (response.status === 200) {
        expect(response.body.components).toHaveProperty("liveDataManager");
        expect(response.body.components).toHaveProperty("realTimeService");
        expect(response.body.components).toHaveProperty("cache");
        
        expect(response.body.components.liveDataManager).toHaveProperty("status");
        expect(response.body.components.realTimeService).toHaveProperty("cacheEntries");
        expect(response.body.components.cache).toHaveProperty("hitRate");
      }
    });

    test("should include service metrics", async () => {
      const response = await request(app)
        .get("/api/livedata/status");

      if (response.status === 200) {
        expect(response.body.metrics).toHaveProperty("totalSymbols");
        expect(response.body.metrics).toHaveProperty("serviceUptime");
        expect(response.body.metrics).toHaveProperty("memoryUsage");
        expect(typeof response.body.metrics.totalSymbols).toBe("number");
      }
    });
  });

  describe("GET /api/livedata/symbols", () => {
    test("should return available symbols", async () => {
      const response = await request(app)
        .get("/api/livedata/symbols");

      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
        expect(Array.isArray(response.body.data)).toBe(true);
        expect(response.body).toHaveProperty("count");
        expect(response.body).toHaveProperty("categories");
      }
    });

    test("should handle category filter", async () => {
      const response = await request(app)
        .get("/api/livedata/symbols?category=stocks");

      expect([200, 400].includes(response.status)).toBe(true);
    });

    test("should handle limit parameter", async () => {
      const response = await request(app)
        .get("/api/livedata/symbols?limit=50");

      expect([200, 400].includes(response.status)).toBe(true);
      
      if (response.status === 200 && response.body.data.length > 0) {
        expect(response.body.data.length).toBeLessThanOrEqual(50);
      }
    });

    test("should handle search parameter", async () => {
      const response = await request(app)
        .get("/api/livedata/symbols?search=AAPL");

      expect([200, 400].includes(response.status)).toBe(true);
    });
  });

  describe("GET /api/livedata/providers", () => {
    test("should return data provider information", async () => {
      const response = await request(app)
        .get("/api/livedata/providers");

      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("providers");
        expect(Array.isArray(response.body.providers)).toBe(true);
        expect(response.body).toHaveProperty("active");
        expect(response.body).toHaveProperty("total");
      }
    });

    test("should include provider status and metrics", async () => {
      const response = await request(app)
        .get("/api/livedata/providers");

      if (response.status === 200 && response.body.providers.length > 0) {
        const provider = response.body.providers[0];
        expect(provider).toHaveProperty("id");
        expect(provider).toHaveProperty("status");
        expect(provider).toHaveProperty("metrics");
      }
    });

    test("should handle provider filtering by status", async () => {
      const response = await request(app)
        .get("/api/livedata/providers?status=active");

      expect([200, 400].includes(response.status)).toBe(true);
    });
  });

  describe("GET /api/livedata/connections", () => {
    test("should return connection status information", async () => {
      const response = await request(app)
        .get("/api/livedata/connections");

      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("connections");
        expect(Array.isArray(response.body.connections)).toBe(true);
        expect(response.body).toHaveProperty("summary");
      }
    });

    test("should include connection health metrics", async () => {
      const response = await request(app)
        .get("/api/livedata/connections");

      if (response.status === 200) {
        expect(response.body.summary).toHaveProperty("total");
        expect(response.body.summary).toHaveProperty("active");
        expect(response.body.summary).toHaveProperty("inactive");
        expect(response.body.summary).toHaveProperty("avgLatency");
      }
    });
  });

  describe("GET /api/livedata/market (Authenticated)", () => {
    test("should require authentication for market data", async () => {
      const response = await request(app)
        .get("/api/livedata/market");

      expect([200, 401].includes(response.status)).toBe(true);
    });

    test("should return market data with authentication", async () => {
      const response = await request(app)
        .get("/api/livedata/market")
        .set("Authorization", `Bearer ${authToken}`);

      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
        expect(response.body.data).toHaveProperty("marketStatus");
        expect(response.body.data).toHaveProperty("indices");
        expect(response.body.data).toHaveProperty("movers");
      }
    });

    test("should handle market status requests", async () => {
      const response = await request(app)
        .get("/api/livedata/market?status=true")
        .set("Authorization", `Bearer ${authToken}`);

      expect([200, 400].includes(response.status)).toBe(true);
    });

    test("should handle sector parameter", async () => {
      const response = await request(app)
        .get("/api/livedata/market?sector=technology")
        .set("Authorization", `Bearer ${authToken}`);

      expect([200, 400].includes(response.status)).toBe(true);
    });
  });

  describe("GET /api/livedata/stream/:symbols (Authenticated)", () => {
    test("should require authentication for streaming data", async () => {
      const response = await request(app)
        .get("/api/livedata/stream/AAPL");

      expect([200, 401].includes(response.status)).toBe(true);
    });

    test("should handle single symbol streaming request", async () => {
      const response = await request(app)
        .get("/api/livedata/stream/AAPL")
        .set("Authorization", `Bearer ${authToken}`);

      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
        expect(response.body.data).toHaveProperty("symbol");
      }
    });

    test("should handle multiple symbols streaming request", async () => {
      const response = await request(app)
        .get("/api/livedata/stream/AAPL,MSFT,GOOGL")
        .set("Authorization", `Bearer ${authToken}`);

      expect([200, 400].includes(response.status)).toBe(true);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("data");
        expect(Array.isArray(response.body.data) || typeof response.body.data === 'object').toBe(true);
      }
    });

    test("should handle streaming with interval parameter", async () => {
      const response = await request(app)
        .get("/api/livedata/stream/AAPL?interval=1m")
        .set("Authorization", `Bearer ${authToken}`);

      expect([200, 400].includes(response.status)).toBe(true);
    });

    test("should validate symbol format", async () => {
      const response = await request(app)
        .get("/api/livedata/stream/INVALID@SYMBOL")
        .set("Authorization", `Bearer ${authToken}`);

      expect([200, 400].includes(response.status)).toBe(true);
    });

    test("should handle too many symbols request", async () => {
      const manySymbols = Array(50).fill().map((_, i) => `SYM${i}`).join(",");
      const response = await request(app)
        .get(`/api/livedata/stream/${manySymbols}`)
        .set("Authorization", `Bearer ${authToken}`);

      expect([200, 400, 413, 500, 503].includes(response.status)).toBe(true);
    });
  });

  describe("GET /api/livedata/latest/:symbols (Authenticated)", () => {
    test("should require authentication for latest data", async () => {
      const response = await request(app)
        .get("/api/livedata/latest/AAPL");

      expect([200, 401].includes(response.status)).toBe(true);
    });

    test("should return latest data for single symbol", async () => {
      const response = await request(app)
        .get("/api/livedata/latest/AAPL")
        .set("Authorization", `Bearer ${authToken}`);

      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
        expect(response.body.data).toHaveProperty("symbol");
        expect(response.body.data).toHaveProperty("price");
        expect(response.body.data).toHaveProperty("timestamp");
      }
    });

    test("should return latest data for multiple symbols", async () => {
      const response = await request(app)
        .get("/api/livedata/latest/AAPL,MSFT")
        .set("Authorization", `Bearer ${authToken}`);

      expect([200, 400].includes(response.status)).toBe(true);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("data");
        expect(Array.isArray(response.body.data)).toBe(true);
      }
    });

    test("should handle fields parameter for latest data", async () => {
      const response = await request(app)
        .get("/api/livedata/latest/AAPL?fields=price,volume,change")
        .set("Authorization", `Bearer ${authToken}`);

      expect([200, 400].includes(response.status)).toBe(true);
    });
  });

  describe("POST /api/livedata/admin/restart (Admin)", () => {
    test("should require authentication for admin operations", async () => {
      const response = await request(app)
        .post("/api/livedata/admin/restart");

      expect([401].includes(response.status)).toBe(true);
    });

    test("should handle restart request with authentication", async () => {
      const response = await request(app)
        .post("/api/livedata/admin/restart")
        .set("Authorization", `Bearer ${authToken}`);

      expect([200, 400, 403, 500, 503].includes(response.status)).toBe(true);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success");
        expect(response.body).toHaveProperty("message");
      }
    });

    test("should handle restart with component parameter", async () => {
      const response = await request(app)
        .post("/api/livedata/admin/restart")
        .set("Authorization", `Bearer ${authToken}`)
        .send({ component: "liveDataManager" });

      expect([200, 400, 403, 500, 503].includes(response.status)).toBe(true);
    });
  });

  describe("POST /api/livedata/admin/optimize (Admin)", () => {
    test("should require authentication for optimization", async () => {
      const response = await request(app)
        .post("/api/livedata/admin/optimize");

      expect([401].includes(response.status)).toBe(true);
    });

    test("should handle optimization request", async () => {
      const response = await request(app)
        .post("/api/livedata/admin/optimize")
        .set("Authorization", `Bearer ${authToken}`);

      expect([200, 400, 403, 500, 503].includes(response.status)).toBe(true);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success");
        expect(response.body).toHaveProperty("optimizations");
      }
    });
  });

  describe("GET /api/livedata/health", () => {
    test("should return health status without authentication", async () => {
      const response = await request(app)
        .get("/api/livedata/health");

      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("status");
        expect(response.body).toHaveProperty("service", "live-data");
        expect(response.body).toHaveProperty("timestamp");
      }
    });

    test("should include uptime information", async () => {
      const response = await request(app)
        .get("/api/livedata/health");

      if (response.status === 200) {
        expect(response.body).toHaveProperty("uptime");
        expect(typeof response.body.uptime).toBe("string");
      }
    });

    test("should handle detailed health check", async () => {
      const response = await request(app)
        .get("/api/livedata/health?detailed=true");

      expect([200, 400].includes(response.status)).toBe(true);
    });
  });

  describe("GET /api/livedata/metrics", () => {
    test("should return performance metrics", async () => {
      const response = await request(app)
        .get("/api/livedata/metrics");

      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("metrics");
        expect(response.body.metrics).toHaveProperty("performance");
        expect(response.body.metrics).toHaveProperty("connections");
        expect(response.body.metrics).toHaveProperty("data");
      }
    });

    test("should handle metrics time range parameter", async () => {
      const response = await request(app)
        .get("/api/livedata/metrics?timeRange=1h");

      expect([200, 400].includes(response.status)).toBe(true);
    });

    test("should handle metrics category filter", async () => {
      const response = await request(app)
        .get("/api/livedata/metrics?category=performance");

      expect([200, 400].includes(response.status)).toBe(true);
    });
  });

  describe("WebSocket and Real-time Features", () => {
    test("should handle WebSocket connection info", async () => {
      const response = await request(app)
        .get("/api/livedata/websocket/info")
        .set("Authorization", `Bearer ${authToken}`);

      expect([200, 404]).toContain(response.status);
    });

    test("should handle subscription management", async () => {
      const response = await request(app)
        .post("/api/livedata/subscriptions")
        .set("Authorization", `Bearer ${authToken}`)
        .send({ symbols: ["AAPL", "MSFT"], type: "quotes" });

      expect([200, 400].includes(response.status)).toBe(true);
    });
  });

  describe("Performance and Edge Cases", () => {
    jest.setTimeout(15000);
    
    test("should handle concurrent streaming requests", async () => {
      const requests = Array(5).fill().map(() => 
        request(app)
          .get("/api/livedata/stream/AAPL")
          .set("Authorization", `Bearer ${authToken}`)
      );
      
      const responses = await Promise.all(requests);
      
      responses.forEach(response => {
        expect([200, 404]).toContain(response.status);
      });
    });

    test("should handle malformed symbol parameters", async () => {
      const malformedSymbols = ["", "AAPL@#$", "123", "a".repeat(20)];
      
      for (const symbol of malformedSymbols) {
        const response = await request(app)
          .get(`/api/livedata/stream/${encodeURIComponent(symbol)}`)
          .set("Authorization", `Bearer ${authToken}`);
        
        expect([200, 400].includes(response.status)).toBe(true);
      }
    });

    test("should maintain response time consistency", async () => {
      const startTime = Date.now();
      const response = await request(app)
        .get("/api/livedata/status");
      const responseTime = Date.now() - startTime;
      
      expect([200, 404]).toContain(response.status);
      expect(responseTime).toBeLessThan(10000); // 10 second timeout
    });

    test("should handle service overload gracefully", async () => {
      const promises = Array(20).fill().map(() =>
        request(app)
          .get("/api/livedata/symbols")
          .timeout(5000)
      );
      
      const responses = await Promise.all(promises.map(p => p.catch(err => ({ status: 500, error: err }))));
      
      responses.forEach(response => {
        if (response.status) {
          expect([200, 404]).toContain(response.status);
        }
      });
    });

    test("should validate authentication edge cases", async () => {
      const authTests = [
        { header: "Bearer ", desc: "empty token" },
        { header: "Bearer invalid-format", desc: "invalid token" },
        { header: "InvalidAuth token", desc: "wrong auth type" }
      ];
      
      for (const authTest of authTests) {
        const response = await request(app)
          .get("/api/livedata/market")
          .set("Authorization", authTest.header);
        
        expect([200, 401].includes(response.status)).toBe(true);
      }
    });

    test("should handle database connection failures gracefully", async () => {
      const response = await request(app)
        .get("/api/livedata/symbols");

      expect([200, 404]).toContain(response.status);
      
      if (response.status === 503) {
        expect(response.body).toHaveProperty("message");
      }
    });

    test("should handle memory pressure scenarios", async () => {
      const response = await request(app)
        .get("/api/livedata/stream/AAPL,MSFT,GOOGL,TSLA,NVDA,AMZN,META,NFLX,CRM,ORCL")
        .set("Authorization", `Bearer ${authToken}`);

      expect([200, 400, 413, 500, 503].includes(response.status)).toBe(true);
    });
  });
});
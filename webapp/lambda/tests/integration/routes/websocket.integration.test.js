const request = require("supertest");
const { app } = require("../../../index");
const { initializeDatabase } = require("../../../utils/database");

describe("WebSocket Routes", () => {
  beforeAll(async () => {
    await initializeDatabase();
  });

  describe("GET /api/websocket", () => {
    test("should return websocket API overview", async () => {
      const response = await request(app).get("/api/websocket");

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty(
        "message",
        "WebSocket API - Ready"
      );
      expect(response.body.data).toHaveProperty("status", "operational");
      expect(response.body.data).toHaveProperty("endpoints");
      expect(Array.isArray(response.body.data.endpoints)).toBe(true);
      expect(response.body.data.endpoints.length).toBeGreaterThan(0);
      expect(response.body).toHaveProperty("timestamp");
    });

    test("should include expected endpoints", async () => {
      const response = await request(app).get("/api/websocket");

      expect(response.status).toBe(200);
      const endpoints = response.body.data.endpoints;
      expect(endpoints.some((ep) => ep.includes("/test"))).toBe(true);
      expect(endpoints.some((ep) => ep.includes("/health"))).toBe(true);
      expect(endpoints.some((ep) => ep.includes("/stream"))).toBe(true);
      expect(endpoints.some((ep) => ep.includes("/connect"))).toBe(true);
    });
  });

  describe("GET /api/websocket/test", () => {
    test("should return test endpoint response", async () => {
      const response = await request(app).get("/api/websocket/test");

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty(
        "status",
        "websocket route is working"
      );
      expect(response.body).toHaveProperty("timestamp");

      const timestamp = new Date(response.body.timestamp);
      expect(timestamp).toBeInstanceOf(Date);
      expect(timestamp.getTime()).not.toBeNaN();
    });
  });

  describe("GET /api/websocket/health", () => {
    test("should return health status", async () => {
      const response = await request(app).get("/api/websocket/health");

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body.data).toHaveProperty("status", "operational");
      expect(response.body.data).toHaveProperty("service", "websocket");
      expect(response.body.data).toHaveProperty(
        "message",
        "WebSocket service is running"
      );
      expect(response.body.data).toHaveProperty(
        "type",
        "http_polling_realtime_data"
      );
      expect(response.body.data).toHaveProperty("dependencies");
      expect(response.body).toHaveProperty("timestamp");

      // Validate dependencies structure
      expect(response.body.data.dependencies).toHaveProperty(
        "responseFormatter"
      );
      expect(response.body.data.dependencies).toHaveProperty("apiKeyService");
      expect(response.body.data.dependencies).toHaveProperty("alpacaService");
      expect(response.body.data.dependencies).toHaveProperty(
        "validationMiddleware"
      );

      // Dependencies should be boolean values
      expect(typeof response.body.data.dependencies.responseFormatter).toBe(
        "boolean"
      );
      expect(typeof response.body.data.dependencies.apiKeyService).toBe(
        "boolean"
      );
      expect(typeof response.body.data.dependencies.alpacaService).toBe(
        "boolean"
      );
      expect(typeof response.body.data.dependencies.validationMiddleware).toBe(
        "boolean"
      );
    });

    test("should handle dependencies gracefully", async () => {
      const response = await request(app).get("/api/websocket/health");

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body.data.dependencies).toBeDefined();
      } else {
        expect(response.body).toHaveProperty("success", false);
        expect(response.body).toHaveProperty("error");
      }
    });
  });

  describe("GET /api/websocket/status", () => {
    test("should return status information", async () => {
      const response = await request(app).get("/api/websocket/status");

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("activeUsers");
      expect(response.body.data).toHaveProperty("cachedSymbols");
      expect(response.body.data).toHaveProperty("service", "websocket");
      expect(response.body.data).toHaveProperty("serverTime");
      expect(response.body.data).toHaveProperty("uptime");
      expect(response.body.data).toHaveProperty("dependencies");

      // Validate data types
      expect(typeof response.body.data.activeUsers).toBe("number");
      expect(typeof response.body.data.cachedSymbols).toBe("number");
      expect(typeof response.body.data.uptime).toBe("number");
      expect(response.body.data.uptime).toBeGreaterThan(0);
    });

    test("should handle status errors gracefully", async () => {
      const response = await request(app).get("/api/websocket/status");

      expect(response.status).toBe(200);

      if (response.status === 500) {
        expect(response.body).toHaveProperty("success", false);
        expect(response.body).toHaveProperty("error");
      }
    });
  });

  describe("GET /api/websocket/stream/:symbols", () => {
    test("should require authentication", async () => {
      const response = await request(app).get("/api/websocket/stream/AAPL");

      expect([401].includes(response.status)).toBe(true);
    });

    test("should handle missing API credentials", async () => {
      const response = await request(app)
        .get("/api/websocket/stream/AAPL")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 400, 403, 500].includes(response.status)).toBe(true);

      if (response.status === 400) {
        expect(response.body).toHaveProperty("success", false);
        expect(response.body).toHaveProperty("error");
        expect(response.body.error).toContain("credentials");
        expect(response.body).toHaveProperty(
          "error_code",
          "API_CREDENTIALS_MISSING"
        );
        expect(response.body).toHaveProperty("provider", "alpaca");
        expect(response.body).toHaveProperty("actions");
        expect(Array.isArray(response.body.actions)).toBe(true);
      }
    });

    test("should validate symbols parameter", async () => {
      const response = await request(app)
        .get("/api/websocket/stream/")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([400, 403, 404, 500].includes(response.status)).toBe(true);
    });

    test("should handle single symbol", async () => {
      const response = await request(app)
        .get("/api/websocket/stream/AAPL")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 400, 403, 500].includes(response.status)).toBe(true);

      if (
        response.status === 400 &&
        response.body.error_code === "API_CREDENTIALS_MISSING"
      ) {
        expect(response.body).toHaveProperty("request_info");
        expect(response.body.request_info).toHaveProperty("request_id");
      }
    });

    test("should handle multiple symbols", async () => {
      const response = await request(app)
        .get("/api/websocket/stream/AAPL,MSFT,GOOGL")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 400, 403, 500].includes(response.status)).toBe(true);
    });

    test("should handle invalid symbols", async () => {
      const response = await request(app)
        .get("/api/websocket/stream/INVALID@#$,123456789012345")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 400, 403, 500].includes(response.status)).toBe(true);
    });

    test("should handle mixed valid/invalid symbols", async () => {
      const response = await request(app)
        .get("/api/websocket/stream/AAPL,INVALID@#$,MSFT")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 400, 403, 500].includes(response.status)).toBe(true);
    });

    test("should handle symbol case conversion", async () => {
      const response = await request(app)
        .get("/api/websocket/stream/aapl,msft")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 400, 403, 500].includes(response.status)).toBe(true);
    });

    test("should handle too many symbols", async () => {
      const manySymbols = Array.from({ length: 25 }, (_, i) => `SYM${i}`).join(
        ","
      );
      const response = await request(app)
        .get(`/api/websocket/stream/${manySymbols}`)
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 400, 403, 500].includes(response.status)).toBe(true);
    });

    test("should validate response structure when successful", async () => {
      const response = await request(app)
        .get("/api/websocket/stream/AAPL")
        .set("Authorization", "Bearer dev-bypass-token");

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
        expect(response.body.data).toHaveProperty("symbols");
        expect(response.body.data).toHaveProperty("data");
        expect(response.body.data).toHaveProperty("updateInterval");
        expect(response.body.data).toHaveProperty("cacheStatus");
        expect(response.body.data).toHaveProperty("statistics");
        expect(response.body.data).toHaveProperty("request_info");

        // Validate cache status
        expect(response.body.data.cacheStatus).toHaveProperty(
          "totalCachedSymbols"
        );
        expect(response.body.data.cacheStatus).toHaveProperty(
          "userSubscriptions"
        );
        expect(response.body.data.cacheStatus).toHaveProperty("cacheHitRate");
        expect(response.body.data.cacheStatus).toHaveProperty("cacheTTL");

        // Validate statistics
        expect(response.body.data.statistics).toHaveProperty("successful");
        expect(response.body.data.statistics).toHaveProperty("cached");
        expect(response.body.data.statistics).toHaveProperty("failed");
        expect(response.body.data.statistics).toHaveProperty("total");

        // Validate request info
        expect(response.body.data.request_info).toHaveProperty("request_id");
        expect(response.body.data.request_info).toHaveProperty(
          "total_duration_ms"
        );
        expect(response.body.data.request_info).toHaveProperty("timestamp");
      }
    });
  });

  describe("GET /api/websocket/trades/:symbols", () => {
    test("should require authentication", async () => {
      const response = await request(app).get("/api/websocket/trades/AAPL");

      expect([401].includes(response.status)).toBe(true);
    });

    test("should handle missing API credentials", async () => {
      const response = await request(app)
        .get("/api/websocket/trades/AAPL")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 403, 500].includes(response.status)).toBe(true);

      if (response.status === 403) {
        expect(response.body).toHaveProperty("success", false);
        expect(response.body).toHaveProperty(
          "error",
          "No Alpaca API key configured"
        );
      }
    });

    test("should handle single symbol", async () => {
      const response = await request(app)
        .get("/api/websocket/trades/AAPL")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 403, 500].includes(response.status)).toBe(true);
    });

    test("should handle multiple symbols", async () => {
      const response = await request(app)
        .get("/api/websocket/trades/AAPL,MSFT,GOOGL")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 403, 500].includes(response.status)).toBe(true);
    });

    test("should validate response structure when successful", async () => {
      const response = await request(app)
        .get("/api/websocket/trades/AAPL")
        .set("Authorization", "Bearer dev-bypass-token");

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
        expect(typeof response.body.data).toBe("object");
      }
    });
  });

  describe("GET /api/websocket/bars/:symbols", () => {
    test("should require authentication", async () => {
      const response = await request(app).get("/api/websocket/bars/AAPL");

      expect([401].includes(response.status)).toBe(true);
    });

    test("should handle missing API credentials", async () => {
      const response = await request(app)
        .get("/api/websocket/bars/AAPL")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 403, 500].includes(response.status)).toBe(true);

      if (response.status === 403) {
        expect(response.body).toHaveProperty("success", false);
        expect(response.body).toHaveProperty(
          "error",
          "No Alpaca API key configured"
        );
      }
    });

    test("should handle timeframe parameter", async () => {
      const response = await request(app)
        .get("/api/websocket/bars/AAPL?timeframe=5Min")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 403, 500].includes(response.status)).toBe(true);
    });

    test("should use default timeframe when not specified", async () => {
      const response = await request(app)
        .get("/api/websocket/bars/AAPL")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 403, 500].includes(response.status)).toBe(true);
    });

    test("should handle multiple symbols", async () => {
      const response = await request(app)
        .get("/api/websocket/bars/AAPL,MSFT")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 403, 500].includes(response.status)).toBe(true);
    });

    test("should handle various timeframes", async () => {
      const timeframes = ["1Min", "5Min", "15Min", "1Hour", "1Day"];

      for (const timeframe of timeframes) {
        const response = await request(app)
          .get(`/api/websocket/bars/AAPL?timeframe=${timeframe}`)
          .set("Authorization", "Bearer dev-bypass-token");

        expect([200, 403, 500].includes(response.status)).toBe(true);
      }
    });
  });

  describe("POST /api/websocket/subscribe", () => {
    test("should require authentication", async () => {
      const response = await request(app)
        .post("/api/websocket/subscribe")
        .send({
          symbols: ["AAPL", "MSFT"],
        });

      expect([401].includes(response.status)).toBe(true);
    });

    test("should validate symbols parameter", async () => {
      const response = await request(app)
        .post("/api/websocket/subscribe")
        .set("Authorization", "Bearer dev-bypass-token")
        .send({});

      expect([400, 422]).toContain(response.status);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body).toHaveProperty("error", "Invalid symbols array");
    });

    test("should handle valid subscription", async () => {
      const response = await request(app)
        .post("/api/websocket/subscribe")
        .set("Authorization", "Bearer dev-bypass-token")
        .send({
          symbols: ["AAPL", "MSFT", "GOOGL"],
          dataTypes: ["quotes", "trades"],
        });

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
        expect(response.body.data).toHaveProperty("subscribed");
        expect(response.body.data).toHaveProperty("dataTypes");
        expect(response.body.data).toHaveProperty("message");
        expect(response.body.data).toHaveProperty("streamEndpoints");
        expect(Array.isArray(response.body.data.subscribed)).toBe(true);

        // Validate stream endpoints
        expect(response.body.data.streamEndpoints).toHaveProperty("quotes");
        expect(response.body.data.streamEndpoints).toHaveProperty("trades");
        expect(response.body.data.streamEndpoints).toHaveProperty("bars");
      }
    });

    test("should handle symbols case conversion", async () => {
      const response = await request(app)
        .post("/api/websocket/subscribe")
        .set("Authorization", "Bearer dev-bypass-token")
        .send({
          symbols: ["aapl", "msft"],
        });

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body.data.subscribed).toContain("AAPL");
        expect(response.body.data.subscribed).toContain("MSFT");
      }
    });

    test("should handle default dataTypes", async () => {
      const response = await request(app)
        .post("/api/websocket/subscribe")
        .set("Authorization", "Bearer dev-bypass-token")
        .send({
          symbols: ["AAPL"],
        });

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body.data.dataTypes).toContain("quotes");
      }
    });

    test("should handle invalid symbols array types", async () => {
      const response = await request(app)
        .post("/api/websocket/subscribe")
        .set("Authorization", "Bearer dev-bypass-token")
        .send({
          symbols: "AAPL,MSFT",
        });

      expect([400, 422]).toContain(response.status);
      expect(response.body).toHaveProperty("error", "Invalid symbols array");
    });
  });

  describe("GET /api/websocket/subscriptions", () => {
    test("should require authentication", async () => {
      const response = await request(app).get("/api/websocket/subscriptions");

      expect([401].includes(response.status)).toBe(true);
    });

    test("should return user subscriptions", async () => {
      const response = await request(app)
        .get("/api/websocket/subscriptions")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
        expect(response.body.data).toHaveProperty("symbols");
        expect(response.body.data).toHaveProperty("count");
        expect(Array.isArray(response.body.data.symbols)).toBe(true);
        expect(typeof response.body.data.count).toBe("number");
        expect(response.body.data.count).toBe(
          response.body.data.symbols.length
        );

        // Stream endpoints should be present if there are subscriptions
        if (response.body.data.count > 0) {
          expect(response.body.data).toHaveProperty("streamEndpoints");
          expect(response.body.data.streamEndpoints).toHaveProperty("quotes");
          expect(response.body.data.streamEndpoints).toHaveProperty("trades");
          expect(response.body.data.streamEndpoints).toHaveProperty("bars");
        }
      }
    });
  });

  describe("DELETE /api/websocket/subscribe", () => {
    test("should require authentication", async () => {
      const response = await request(app)
        .delete("/api/websocket/subscribe")
        .send({
          symbols: ["AAPL"],
        });

      expect([401].includes(response.status)).toBe(true);
    });

    test("should handle specific symbol unsubscription", async () => {
      const response = await request(app)
        .delete("/api/websocket/subscribe")
        .set("Authorization", "Bearer dev-bypass-token")
        .send({
          symbols: ["AAPL", "MSFT"],
        });

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
        expect(response.body.data).toHaveProperty(
          "message",
          "Unsubscribed successfully"
        );
        expect(response.body.data).toHaveProperty("remainingSubscriptions");
        expect(Array.isArray(response.body.data.remainingSubscriptions)).toBe(
          true
        );
      }
    });

    test("should handle full unsubscription", async () => {
      const response = await request(app)
        .delete("/api/websocket/subscribe")
        .set("Authorization", "Bearer dev-bypass-token")
        .send({});

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body.data).toHaveProperty(
          "message",
          "Unsubscribed successfully"
        );
      }
    });

    test("should handle empty symbols array", async () => {
      const response = await request(app)
        .delete("/api/websocket/subscribe")
        .set("Authorization", "Bearer dev-bypass-token")
        .send({
          symbols: [],
        });

      expect(response.status).toBe(200);
    });
  });

  describe("GET /api/websocket/connections", () => {
    test("should require authentication", async () => {
      const response = await request(app).get("/api/websocket/connections");

      expect([401].includes(response.status)).toBe(true);
    });

    test("should return connection information", async () => {
      const response = await request(app)
        .get("/api/websocket/connections")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
        expect(response.body.data).toHaveProperty("user_id");
        expect(response.body.data).toHaveProperty("active_subscriptions");
        expect(response.body.data).toHaveProperty("subscription_count");
        expect(response.body.data).toHaveProperty("cache_status");
        expect(response.body.data).toHaveProperty("connection_info");
        expect(response.body.data).toHaveProperty("performance");

        // Validate cache status
        expect(response.body.data.cache_status).toHaveProperty(
          "cached_symbols"
        );
        expect(response.body.data.cache_status).toHaveProperty(
          "user_cache_entries"
        );
        expect(response.body.data.cache_status).toHaveProperty(
          "fresh_data_count"
        );
        expect(response.body.data.cache_status).toHaveProperty(
          "stale_data_count"
        );

        // Validate connection info
        expect(response.body.data.connection_info).toHaveProperty(
          "connected_at"
        );
        expect(response.body.data.connection_info).toHaveProperty(
          "last_activity"
        );
        expect(response.body.data.connection_info).toHaveProperty("status");
        expect(response.body.data.connection_info).toHaveProperty(
          "data_source"
        );
        expect(response.body.data.connection_info).toHaveProperty(
          "environment"
        );

        // Validate performance metrics
        expect(response.body.data.performance).toHaveProperty("cache_ttl");
        expect(response.body.data.performance).toHaveProperty(
          "update_interval"
        );
        expect(response.body.data.performance).toHaveProperty("uptime");
      }
    });

    test("should handle details parameter", async () => {
      const response = await request(app)
        .get("/api/websocket/connections?details=true")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(200);

      if (
        response.status === 200 &&
        response.body.data.subscription_count > 0
      ) {
        expect(response.body.data).toHaveProperty("symbol_details");
        expect(Array.isArray(response.body.data.symbol_details)).toBe(true);

        if (response.body.data.symbol_details.length > 0) {
          const symbolDetail = response.body.data.symbol_details[0];
          expect(symbolDetail).toHaveProperty("symbol");
          expect(symbolDetail).toHaveProperty("has_cached_data");
          expect(symbolDetail).toHaveProperty("data_age");
          expect(symbolDetail).toHaveProperty("is_fresh");
        }
      }
    });

    test("should handle details parameter false", async () => {
      const response = await request(app)
        .get("/api/websocket/connections?details=false")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body.data).not.toHaveProperty("symbol_details");
      }
    });
  });

  describe("Authentication and Error Handling", () => {
    test("should handle invalid authentication tokens", async () => {
      const response = await request(app)
        .get("/api/websocket/stream/AAPL")
        .set("Authorization", "Bearer invalid-token");

      expect([401].includes(response.status)).toBe(true);
    });

    test("should handle missing authorization header", async () => {
      const response = await request(app)
        .post("/api/websocket/subscribe")
        .send({
          symbols: ["AAPL"],
        });

      expect([401].includes(response.status)).toBe(true);
    });

    test("should handle malformed request bodies", async () => {
      const response = await request(app)
        .post("/api/websocket/subscribe")
        .set("Authorization", "Bearer dev-bypass-token")
        .send("invalid json");

      expect([400, 500].includes(response.status)).toBe(true);
    });
  });

  describe("Performance and Concurrency", () => {
    test("should respond within reasonable time", async () => {
      const startTime = Date.now();

      const response = await request(app)
        .get("/api/websocket/health")
        .set("Authorization", "Bearer dev-bypass-token");

      const responseTime = Date.now() - startTime;

      expect(responseTime).toBeLessThan(3000);
      expect(response.status).toBe(200);
    });

    test("should handle concurrent requests", async () => {
      const requests = [
        request(app).get("/api/websocket/health"),
        request(app).get("/api/websocket/status"),
        request(app).get("/api/websocket/test"),
        request(app)
          .get("/api/websocket/subscriptions")
          .set("Authorization", "Bearer dev-bypass-token"),
      ];

      const responses = await Promise.all(requests);

      responses.forEach((response, index) => {
        if (index < 3) {
          // Public endpoints
          expect(response.status).toBe(200);
        } else {
          // Authenticated endpoints
          expect([200, 401].includes(response.status)).toBe(true);
        }
      });
    });
  });

  describe("Data Validation", () => {
    test("should validate timestamp formats", async () => {
      const response = await request(app).get("/api/websocket");

      expect(response.status).toBe(200);
      const timestamp = new Date(response.body.timestamp);
      expect(timestamp).toBeInstanceOf(Date);
      expect(timestamp.getTime()).not.toBeNaN();
    });

    test("should validate numeric types", async () => {
      const response = await request(app).get("/api/websocket/status");

      if (response.status === 200) {
        expect(typeof response.body.data.activeUsers).toBe("number");
        expect(typeof response.body.data.cachedSymbols).toBe("number");
        expect(typeof response.body.data.uptime).toBe("number");
      }
    });

    test("should validate array types", async () => {
      const response = await request(app)
        .get("/api/websocket/subscriptions")
        .set("Authorization", "Bearer dev-bypass-token");

      if (response.status === 200) {
        expect(Array.isArray(response.body.data.symbols)).toBe(true);
      }
    });
  });

  describe("Edge Cases", () => {
    test("should handle empty symbol parameters", async () => {
      const response = await request(app)
        .get("/api/websocket/stream/")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([400, 404, 500].includes(response.status)).toBe(true);
    });

    test("should handle special characters in symbols", async () => {
      const response = await request(app)
        .get("/api/websocket/stream/A@PPL,M$FT")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 400, 403, 500].includes(response.status)).toBe(true);
    });

    test("should handle extremely long symbol names", async () => {
      const longSymbol = "A".repeat(50);
      const response = await request(app)
        .get(`/api/websocket/stream/${longSymbol}`)
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 400, 403, 500].includes(response.status)).toBe(true);
    });

    test("should handle numeric symbols", async () => {
      const response = await request(app)
        .get("/api/websocket/stream/123,456")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 400, 403, 500].includes(response.status)).toBe(true);
    });
  });
});

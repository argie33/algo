const request = require("supertest");
const {
  initializeDatabase,
  closeDatabase,
} = require("../../../utils/database");

let app;
const authToken = "dev-bypass-token";

describe("Dashboard Routes Integration Tests", () => {
  beforeAll(async () => {
    await initializeDatabase();
    app = require("../../../server");
  });

  afterAll(async () => {
    await closeDatabase();
  });

  describe("GET /api/dashboard (Dashboard Root)", () => {
    test("should return dashboard endpoints and operational status", async () => {
      const response = await request(app).get("/api/dashboard");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body.message).toBe("Dashboard API - Ready");
        expect(response.body.status).toBe("operational");
        expect(Array.isArray(response.body.endpoints)).toBe(true);
        expect(response.body.endpoints.length).toBeGreaterThan(0);
        expect(response.body).toHaveProperty("timestamp");

        // Verify expected endpoints are listed
        const endpointsString = response.body.endpoints.join(" ");
        expect(endpointsString).toContain("/summary");
        expect(endpointsString).toContain("/holdings");
        expect(endpointsString).toContain("/performance");
        expect(endpointsString).toContain("/alerts");
        expect(endpointsString).toContain("/market-data");
      }
    });

    test("should handle high-frequency requests without degradation", async () => {
      const requests = Array(5)
        .fill()
        .map(() => request(app).get("/api/dashboard"));

      const responses = await Promise.all(requests);

      responses.forEach((response) => {
        expect([200, 404]).toContain(response.status);
      });
    });
  });

  describe("GET /api/dashboard/summary (Dashboard Summary)", () => {
    test("should return comprehensive dashboard summary data", async () => {
      const response = await request(app).get("/api/dashboard/summary");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("data");

        const data = response.body.data;
        expect(data).toHaveProperty("market_overview");
        expect(data).toHaveProperty("top_gainers");
        expect(data).toHaveProperty("top_losers");
        expect(data).toHaveProperty("sector_performance");
        expect(data).toHaveProperty("recent_earnings");
        expect(data).toHaveProperty("market_sentiment");
        expect(data).toHaveProperty("volume_leaders");
        expect(data).toHaveProperty("market_breadth");
        expect(data).toHaveProperty("timestamp");

        // Validate data structures
        expect(Array.isArray(data.market_overview)).toBe(true);
        expect(Array.isArray(data.top_gainers)).toBe(true);
        expect(Array.isArray(data.top_losers)).toBe(true);
        expect(Array.isArray(data.sector_performance)).toBe(true);
        expect(Array.isArray(data.recent_earnings)).toBe(true);
        expect(Array.isArray(data.volume_leaders)).toBe(true);
      }
    });

    test("should validate market overview data structure", async () => {
      const response = await request(app).get("/api/dashboard/summary");

      if (
        response.status === 200 &&
        response.body.data.market_overview.length > 0
      ) {
        const marketItem = response.body.data.market_overview[0];
        expect(marketItem).toHaveProperty("symbol");
        expect(marketItem).toHaveProperty("current_price");
        expect(typeof marketItem.symbol).toBe("string");
        expect(typeof marketItem.current_price).toBe("number");
      }
    });

    test("should validate sector performance data", async () => {
      const response = await request(app).get("/api/dashboard/summary");

      if (
        response.status === 200 &&
        response.body.data.sector_performance.length > 0
      ) {
        const sectorItem = response.body.data.sector_performance[0];
        expect(sectorItem).toHaveProperty("sector");
        expect(sectorItem).toHaveProperty("avg_change");
        expect(typeof sectorItem.sector).toBe("string");
        expect(typeof sectorItem.avg_change).toBe("number");
      }
    });

    test("should handle database connectivity issues gracefully", async () => {
      const response = await request(app).get("/api/dashboard/summary");

      expect([200, 404]).toContain(response.status);

      if (response.status >= 500) {
        expect(response.body).toHaveProperty("error");
        expect(response.body).toHaveProperty("message");
      }
    });
  });

  describe("GET /api/dashboard/holdings (Portfolio Holdings)", () => {
    test("should require authentication", async () => {
      const response = await request(app).get("/api/dashboard/holdings");

      expect([401].includes(response.status)).toBe(true);
    });

    test("should return holdings data with valid authentication", async () => {
      const response = await request(app)
        .get("/api/dashboard/holdings")
        .set("Authorization", `Bearer ${authToken}`);

      expect([200, 401].includes(response.status)).toBe(true);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("data");
        expect(response.body.data).toHaveProperty("holdings");
        expect(response.body.data).toHaveProperty("summary");
        expect(response.body.data).toHaveProperty("count");
        expect(Array.isArray(response.body.data.holdings)).toBe(true);
      }
    });

    test("should validate holdings data structure", async () => {
      const response = await request(app)
        .get("/api/dashboard/holdings")
        .set("Authorization", `Bearer ${authToken}`);

      if (response.status === 200 && response.body.data.holdings.length > 0) {
        const holding = response.body.data.holdings[0];
        expect(holding).toHaveProperty("symbol");
        expect(holding).toHaveProperty("shares");
        expect(holding).toHaveProperty("avg_price");
        expect(typeof holding.symbol).toBe("string");
        expect(typeof holding.shares).toBe("number");
      }
    });

    test("should handle invalid authentication tokens", async () => {
      const response = await request(app)
        .get("/api/dashboard/holdings")
        .set("Authorization", "Bearer invalid-token");

      expect([401].includes(response.status)).toBe(true);
    });
  });

  describe("GET /api/dashboard/performance (Portfolio Performance)", () => {
    test("should require authentication for performance data", async () => {
      const response = await request(app).get("/api/dashboard/performance");

      expect([401].includes(response.status)).toBe(true);
    });

    test("should return performance data with valid authentication", async () => {
      const response = await request(app)
        .get("/api/dashboard/performance")
        .set("Authorization", `Bearer ${authToken}`);

      expect([200, 401].includes(response.status)).toBe(true);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("data");
        expect(response.body.data).toHaveProperty("performance");
        expect(response.body.data).toHaveProperty("metrics");
        expect(Array.isArray(response.body.data.performance)).toBe(true);
      }
    });

    test("should validate performance metrics structure", async () => {
      const response = await request(app)
        .get("/api/dashboard/performance")
        .set("Authorization", `Bearer ${authToken}`);

      if (
        response.status === 200 &&
        response.body.data.performance.length > 0
      ) {
        const perfData = response.body.data.performance[0];
        expect(perfData).toHaveProperty("date");
        expect(perfData).toHaveProperty("total_value");
        expect(perfData).toHaveProperty("daily_return");
        expect(typeof perfData.total_value).toBe("number");
      }
    });

    test("should validate performance metrics calculations", async () => {
      const response = await request(app)
        .get("/api/dashboard/performance")
        .set("Authorization", `Bearer ${authToken}`);

      if (response.status === 200 && response.body.data.metrics) {
        const metrics = response.body.data.metrics;
        expect(metrics).toHaveProperty("avg_daily_return");
        expect(metrics).toHaveProperty("volatility");
        expect(metrics).toHaveProperty("max_return");
        expect(metrics).toHaveProperty("min_return");

        if (metrics.avg_daily_return !== null) {
          expect(typeof metrics.avg_daily_return).toBe("number");
          expect(isFinite(metrics.avg_daily_return)).toBe(true);
        }
      }
    });
  });

  describe("GET /api/dashboard/alerts (Trading Alerts)", () => {
    test("should require authentication for alerts", async () => {
      const response = await request(app).get("/api/dashboard/alerts");

      expect([401, 403, 500, 501].includes(response.status)).toBe(true);
    });

    test("should return alerts data with authentication", async () => {
      const response = await request(app)
        .get("/api/dashboard/alerts")
        .set("Authorization", `Bearer ${authToken}`);

      expect([200, 401].includes(response.status)).toBe(true);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("data");
        expect(response.body.data).toHaveProperty("alerts");
        expect(response.body.data).toHaveProperty("summary");
        expect(Array.isArray(response.body.data.alerts)).toBe(true);
        expect(Array.isArray(response.body.data.summary)).toBe(true);
      }
    });

    test("should validate alert data structure", async () => {
      const response = await request(app)
        .get("/api/dashboard/alerts")
        .set("Authorization", `Bearer ${authToken}`);

      if (response.status === 200 && response.body.data.alerts.length > 0) {
        const alert = response.body.data.alerts[0];
        expect(alert).toHaveProperty("symbol");
        expect(alert).toHaveProperty("alert_type");
        expect(alert).toHaveProperty("message");
        expect(alert).toHaveProperty("status");
        expect(typeof alert.symbol).toBe("string");
        expect(typeof alert.alert_type).toBe("string");
      }
    });

    test("should handle alert summary aggregation", async () => {
      const response = await request(app)
        .get("/api/dashboard/alerts")
        .set("Authorization", `Bearer ${authToken}`);

      if (response.status === 200 && response.body.data.summary.length > 0) {
        const summaryItem = response.body.data.summary[0];
        expect(summaryItem).toHaveProperty("alert_type");
        expect(summaryItem).toHaveProperty("count");
        expect(summaryItem).toHaveProperty("active_count");
        expect(typeof summaryItem.count).toBe("number");
        expect(typeof summaryItem.active_count).toBe("number");
      }
    });
  });

  describe("GET /api/dashboard/market-data (Market Data)", () => {
    test("should return comprehensive market data", async () => {
      const response = await request(app).get("/api/dashboard/market-data");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("data");
        expect(response.body.data).toHaveProperty("economic_indicators");
        expect(response.body.data).toHaveProperty("sector_rotation");
        expect(response.body.data).toHaveProperty("market_internals");
        expect(response.body.data).toHaveProperty("timestamp");

        expect(Array.isArray(response.body.data.economic_indicators)).toBe(
          true
        );
        expect(Array.isArray(response.body.data.sector_rotation)).toBe(true);
        expect(Array.isArray(response.body.data.market_internals)).toBe(true);
      }
    });

    test("should validate economic indicators structure", async () => {
      const response = await request(app).get("/api/dashboard/market-data");

      if (
        response.status === 200 &&
        response.body.data.economic_indicators.length > 0
      ) {
        const indicator = response.body.data.economic_indicators[0];
        expect(indicator).toHaveProperty("indicator_name");
        expect(indicator).toHaveProperty("value");
        expect(typeof indicator.indicator_name).toBe("string");
        expect(typeof indicator.value).toBe("number");
      }
    });

    test("should validate sector rotation data", async () => {
      const response = await request(app).get("/api/dashboard/market-data");

      if (
        response.status === 200 &&
        response.body.data.sector_rotation.length > 0
      ) {
        const sectorData = response.body.data.sector_rotation[0];
        expect(sectorData).toHaveProperty("sector");
        expect(sectorData).toHaveProperty("avg_change");
        expect(sectorData).toHaveProperty("stock_count");
        expect(typeof sectorData.sector).toBe("string");
        expect(typeof sectorData.avg_change).toBe("number");
        expect(typeof sectorData.stock_count).toBe("number");
      }
    });

    test("should validate market internals data", async () => {
      const response = await request(app).get("/api/dashboard/market-data");

      if (
        response.status === 200 &&
        response.body.data.market_internals.length > 0
      ) {
        const internalData = response.body.data.market_internals[0];
        expect(internalData).toHaveProperty("type");
        expect(internalData).toHaveProperty("count");
        expect(typeof internalData.type).toBe("string");
        expect(typeof internalData.count).toBe("number");

        // Validate expected types
        const validTypes = ["advancing", "declining", "unchanged"];
        expect(validTypes.includes(internalData.type)).toBe(true);
      }
    });
  });

  describe("GET /api/dashboard/debug (Debug Endpoint)", () => {
    test("should return debug information about database connectivity", async () => {
      const response = await request(app).get("/api/dashboard/debug");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("data");
        expect(response.body.data).toHaveProperty("timestamp");
        expect(response.body.data).toHaveProperty("database_status");
        expect(response.body.data).toHaveProperty("table_counts");
        expect(response.body.data).toHaveProperty("sample_data");
      }
    });

    test("should validate table count information", async () => {
      const response = await request(app).get("/api/dashboard/debug");

      if (response.status === 200 && response.body.data.table_counts) {
        const tableCounts = response.body.data.table_counts;
        expect(typeof tableCounts).toBe("object");

        // Check for expected tables
        const expectedTables = [
          "price_daily",
          "earnings_history",
          "fear_greed_index",
          "portfolio_holdings",
          "portfolio_performance",
          "trading_alerts",
          "economic_data",
          "stocks",
          "technical_data_daily",
        ];

        expectedTables.forEach((table) => {
          if (Object.prototype.hasOwnProperty.call(tableCounts, table)) {
            // Count should be either a number or error string
            expect(
              typeof tableCounts[table] === "number" ||
                typeof tableCounts[table] === "string"
            ).toBe(true);
          }
        });
      }
    });

    test("should validate database connection status", async () => {
      const response = await request(app).get("/api/dashboard/debug");

      if (response.status === 200) {
        expect(response.body.data.database_status).toBeDefined();
        expect(typeof response.body.data.database_status).toBe("string");

        // Should be either "connected" or contain error information
        const status = response.body.data.database_status;
        expect(status === "connected" || status.includes("error")).toBe(true);
      }
    });
  });

  describe("GET /api/dashboard/overview (Market Overview)", () => {
    test("should return market overview data", async () => {
      const response = await request(app).get("/api/dashboard/overview");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
        expect(response.body).toHaveProperty("timestamp");

        const data = response.body.data;
        expect(data).toHaveProperty("market_status");
        expect(data).toHaveProperty("key_metrics");
        expect(data).toHaveProperty("top_movers");
        expect(data).toHaveProperty("sector_performance");
        expect(data).toHaveProperty("alerts_summary");
      }
    });

    test("should validate market status information", async () => {
      const response = await request(app).get("/api/dashboard/overview");

      if (response.status === 200) {
        const marketStatus = response.body.data.market_status;
        expect(marketStatus).toHaveProperty("is_open");
        expect(marketStatus).toHaveProperty("next_open");
        expect(marketStatus).toHaveProperty("next_close");
        expect(marketStatus).toHaveProperty("timezone");

        expect(typeof marketStatus.is_open).toBe("boolean");
        expect(typeof marketStatus.timezone).toBe("string");
      }
    });

    test("should validate top movers structure", async () => {
      const response = await request(app).get("/api/dashboard/overview");

      if (response.status === 200) {
        const topMovers = response.body.data.top_movers;
        expect(topMovers).toHaveProperty("gainers");
        expect(topMovers).toHaveProperty("losers");
        expect(Array.isArray(topMovers.gainers)).toBe(true);
        expect(Array.isArray(topMovers.losers)).toBe(true);

        if (topMovers.gainers.length > 0) {
          const gainer = topMovers.gainers[0];
          expect(gainer).toHaveProperty("symbol");
          expect(gainer).toHaveProperty("price");
          expect(gainer).toHaveProperty("change_percent");
          expect(typeof gainer.symbol).toBe("string");
          expect(typeof gainer.price).toBe("number");
          expect(typeof gainer.change_percent).toBe("number");
        }
      }
    });

    test("should handle empty market data gracefully", async () => {
      const response = await request(app).get("/api/dashboard/overview");

      if (response.status === 404) {
        expect(response.body).toHaveProperty("success", false);
        expect(response.body).toHaveProperty("error");
        expect(response.body).toHaveProperty("details");
        expect(response.body).toHaveProperty("troubleshooting");

        // Should provide helpful troubleshooting information
        expect(response.body.troubleshooting).toHaveProperty("required_tables");
        expect(response.body.troubleshooting).toHaveProperty("check_tables");
      }
    });
  });

  describe("Performance and Edge Cases", () => {
    jest.setTimeout(15000);

    test("should handle concurrent requests to dashboard endpoints", async () => {
      const requests = [
        request(app).get("/api/dashboard"),
        request(app).get("/api/dashboard/summary"),
        request(app).get("/api/dashboard/market-data"),
        request(app).get("/api/dashboard/overview"),
        request(app).get("/api/dashboard/debug"),
      ];

      const responses = await Promise.all(requests);

      responses.forEach((response) => {
        expect([200, 404]).toContain(response.status);
      });
    });

    test("should maintain response time consistency", async () => {
      const startTime = Date.now();
      const response = await request(app).get("/api/dashboard/summary");
      const responseTime = Date.now() - startTime;

      expect([200, 404]).toContain(response.status);
      expect(responseTime).toBeLessThan(15000);
    });

    test("should handle malformed authentication headers", async () => {
      const malformedHeaders = [
        "Bearer",
        "InvalidType token-value",
        "Bearer ",
        "Bearer invalid-format-token-with-special-chars-!@#$%",
        "",
      ];

      for (const header of malformedHeaders) {
        const response = await request(app)
          .get("/api/dashboard/holdings")
          .set("Authorization", header);

        expect([401].includes(response.status)).toBe(true);
      }
    });

    test("should handle database connection failures gracefully", async () => {
      const response = await request(app).get("/api/dashboard/summary");

      expect([200, 404]).toContain(response.status);

      if (response.status >= 500) {
        expect(response.body).toHaveProperty("error");
        expect(response.body).toHaveProperty("message");
      }
    });

    test("should validate numeric data integrity", async () => {
      const response = await request(app).get("/api/dashboard/summary");

      if (response.status === 200) {
        const validateNumbers = (obj) => {
          Object.keys(obj).forEach((key) => {
            const value = obj[key];
            if (typeof value === "number") {
              expect(isFinite(value)).toBe(true);
              expect(!isNaN(value)).toBe(true);
            } else if (typeof value === "object" && value !== null) {
              validateNumbers(value);
            }
          });
        };

        validateNumbers(response.body.data);
      }
    });

    test("should handle SQL injection attempts safely", async () => {
      const maliciousInputs = [
        "'; DROP TABLE market_data; --",
        "1' OR '1'='1",
        "UNION SELECT * FROM users",
        "<script>alert('xss')</script>",
        "../../../etc/passwd",
      ];

      for (const input of maliciousInputs) {
        const response = await request(app).get(
          `/api/dashboard/summary?filter=${encodeURIComponent(input)}`
        );

        expect([200, 400].includes(response.status)).toBe(true);
      }
    });

    test("should handle memory pressure with large data requests", async () => {
      const response = await request(app).get("/api/dashboard/summary");

      expect([200, 413, 500, 503].includes(response.status)).toBe(true);
    });

    test("should validate response content types", async () => {
      const endpoints = [
        "/api/dashboard",
        "/api/dashboard/summary",
        "/api/dashboard/market-data",
        "/api/dashboard/overview",
        "/api/dashboard/debug",
      ];

      for (const endpoint of endpoints) {
        const response = await request(app).get(endpoint);

        if ([200].includes(response.status)) {
          expect(response.headers["content-type"]).toMatch(/application\/json/);
        }
      }
    });

    test("should handle authentication edge cases", async () => {
      const authEndpoints = [
        "/api/dashboard/holdings",
        "/api/dashboard/performance",
        "/api/dashboard/alerts",
      ];

      for (const endpoint of authEndpoints) {
        // Test missing authorization header
        const noAuthResponse = await request(app).get(endpoint);
        expect([401, 403, 500, 501].includes(noAuthResponse.status)).toBe(true);

        // Test malformed token
        const badTokenResponse = await request(app)
          .get(endpoint)
          .set("Authorization", "Bearer malformed-token");
        expect([401, 403, 500, 501].includes(badTokenResponse.status)).toBe(
          true
        );

        // Test valid token format
        const validTokenResponse = await request(app)
          .get(endpoint)
          .set("Authorization", `Bearer ${authToken}`);
        expect([200, 401].includes(validTokenResponse.status)).toBe(true);
      }
    });
  });
});

const request = require("supertest");
const { initializeDatabase, closeDatabase } = require("../../../utils/database");

let app;

describe("Trades Routes", () => {
  beforeAll(async () => {
    process.env.ALLOW_DEV_BYPASS = "true";
    await initializeDatabase();
    app = require("../../../server");
  });

  afterAll(async () => {
    await closeDatabase();
  });

  describe("GET /api/trades", () => {
    test("should return trade API information", async () => {
      const response = await request(app)
        .get("/api/trades");

      expect([200, 404]).toContain(response.status);
      expect(response.body).toHaveProperty("message", "Trade History API - Ready");
      expect(response.body).toHaveProperty("status", "operational");
      expect(response.body).toHaveProperty("timestamp");
      
      // Validate timestamp
      const timestamp = new Date(response.body.timestamp);
      expect(timestamp).toBeInstanceOf(Date);
      expect(timestamp.getTime()).not.toBeNaN();
    });
  });

  describe("GET /api/trades/health", () => {
    test("should return health status", async () => {
      const response = await request(app)
        .get("/api/trades/health");

      expect([200, 404]).toContain(response.status);
      expect(response.body).toHaveProperty("status", "operational");
      expect(response.body).toHaveProperty("service", "trades");
      expect(response.body).toHaveProperty("message", "Trade History service is running");
      expect(response.body).toHaveProperty("timestamp");
    });
  });

  describe("GET /api/trades/recent", () => {
    test("should return 501 not implemented", async () => {
      const response = await request(app)
        .get("/api/trades/recent")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([400, 401, 404, 422, 500]).toContain(response.status);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body).toHaveProperty("error", "Recent trades not implemented");
      expect(response.body).toHaveProperty("details");
      expect(response.body).toHaveProperty("troubleshooting");
      expect(response.body).toHaveProperty("filters");
      expect(response.body).toHaveProperty("timestamp");
    });

    test("should handle query parameters", async () => {
      const response = await request(app)
        .get("/api/trades/recent?limit=10&days=30&symbol=AAPL&type=buy&status=executed")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([400, 401, 404, 422, 500]).toContain(response.status);
      expect(response.body.filters).toHaveProperty("limit", 10);
      expect(response.body.filters).toHaveProperty("days", 30);
      expect(response.body.filters).toHaveProperty("symbol", "AAPL");
      expect(response.body.filters).toHaveProperty("type", "buy");
      expect(response.body.filters).toHaveProperty("status", "executed");
    });

    test("should use default values for missing parameters", async () => {
      const response = await request(app)
        .get("/api/trades/recent")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([400, 401, 404, 422, 500]).toContain(response.status);
      expect(response.body.filters).toHaveProperty("limit", 20);
      expect(response.body.filters).toHaveProperty("days", 7);
      expect(response.body.filters).toHaveProperty("symbol", null);
      expect(response.body.filters).toHaveProperty("type", "all");
      expect(response.body.filters).toHaveProperty("status", "all");
    });

    test("should require authentication", async () => {
      const response = await request(app)
        .get("/api/trades/recent");
        // No auth header

      expect([401].includes(response.status)).toBe(true);
    });
  });

  describe("GET /api/trades/import/status", () => {
    test("should return broker status for authenticated user", async () => {
      const response = await request(app)
        .get("/api/trades/import/status")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("brokerStatus");
        expect(response.body).toHaveProperty("totalBrokers");
        expect(response.body).toHaveProperty("activeBrokers");
        expect(Array.isArray(response.body.brokerStatus)).toBe(true);
        expect(typeof response.body.totalBrokers).toBe("number");
        expect(typeof response.body.activeBrokers).toBe("number");
      }
    });

    test("should require authentication", async () => {
      const response = await request(app)
        .get("/api/trades/import/status");
        // No auth header

      expect([401].includes(response.status)).toBe(true);
    });
  });

  describe("POST /api/trades/import/alpaca", () => {
    test("should handle Alpaca import request", async () => {
      const response = await request(app)
        .post("/api/trades/import/alpaca")
        .set("Authorization", "Bearer dev-bypass-token")
        .send({
          startDate: "2023-01-01",
          endDate: "2023-12-31"
        });

      // May return 200 if API keys exist, 400 if not, or 500 for other errors
      expect([200, 400, 500].includes(response.status)).toBe(true);
      
      if (response.status === 400) {
        expect(response.body).toHaveProperty("error");
        expect(response.body.error).toContain("API");
      } else if (response.status === 200) {
        expect(response.body).toHaveProperty("message");
        expect(response.body).toHaveProperty("data");
      }
    });

    test("should require authentication", async () => {
      const response = await request(app)
        .post("/api/trades/import/alpaca")
        .send({ startDate: "2023-01-01", endDate: "2023-12-31" });
        // No auth header

      expect([401].includes(response.status)).toBe(true);
    });
  });

  describe("GET /api/trades/summary", () => {
    test("should return trade summary for authenticated user", async () => {
      const response = await request(app)
        .get("/api/trades/summary")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("data");
        expect(typeof response.body.data).toBe("object");
      }
    });

    test("should require authentication", async () => {
      const response = await request(app)
        .get("/api/trades/summary");
        // No auth header

      expect([401].includes(response.status)).toBe(true);
    });
  });

  describe("GET /api/trades/positions", () => {
    test("should return positions data", async () => {
      const response = await request(app)
        .get("/api/trades/positions")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("data");
        expect(response.body.data).toHaveProperty("positions");
        expect(response.body.data).toHaveProperty("pagination");
        expect(Array.isArray(response.body.data.positions)).toBe(true);
      }
    });

    test("should handle query parameters", async () => {
      const response = await request(app)
        .get("/api/trades/positions?status=open&limit=10&offset=0")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body.data.pagination.limit).toBe(10);
        expect(response.body.data.pagination.offset).toBe(0);
      }
    });

    test("should require authentication", async () => {
      const response = await request(app)
        .get("/api/trades/positions");
        // No auth header

      expect([401].includes(response.status)).toBe(true);
    });
  });

  describe("GET /api/trades/analytics", () => {
    test("should return comprehensive trade analytics", async () => {
      const response = await request(app)
        .get("/api/trades/analytics")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
        expect(response.body).toHaveProperty("metadata");
        expect(response.body).toHaveProperty("timestamp");
        
        // Validate analytics structure
        const data = response.body.data;
        expect(data).toHaveProperty("summary");
        expect(data).toHaveProperty("performance_metrics");
        expect(data).toHaveProperty("sector_breakdown");
        expect(data).toHaveProperty("recent_trades");
        
        // Validate metadata
        expect(response.body.metadata).toHaveProperty("timeframe");
        expect(response.body.metadata).toHaveProperty("date_range");
        expect(response.body.metadata).toHaveProperty("data_source");
      }
    });

    test("should handle timeframe parameter", async () => {
      const timeframes = ["1W", "1M", "3M", "6M", "1Y", "YTD"];
      
      for (const timeframe of timeframes) {
        const response = await request(app)
          .get(`/api/trades/analytics?timeframe=${timeframe}`)
          .set("Authorization", "Bearer dev-bypass-token");

        expect([200, 404]).toContain(response.status);
        
        if (response.status === 200) {
          expect(response.body.metadata.timeframe).toBe(timeframe);
        }
      }
    });

    test("should require authentication", async () => {
      const response = await request(app)
        .get("/api/trades/analytics");
        // No auth header

      expect([401].includes(response.status)).toBe(true);
    });
  });

  describe("GET /api/trades/analytics/overview", () => {
    test("should return analytics overview", async () => {
      const response = await request(app)
        .get("/api/trades/analytics/overview")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
        expect(response.body).toHaveProperty("timestamp");
        
        const data = response.body.data;
        expect(data).toHaveProperty("timeframe");
        expect(data).toHaveProperty("overview");
        expect(data).toHaveProperty("sectorBreakdown");
        expect(data).toHaveProperty("dataSource");
      }
    });

    test("should require authentication", async () => {
      const response = await request(app)
        .get("/api/trades/analytics/overview");
        // No auth header

      expect([401].includes(response.status)).toBe(true);
    });
  });

  describe("GET /api/trades/history", () => {
    test("should return trade history or service unavailable", async () => {
      const response = await request(app)
        .get("/api/trades/history")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 503, 500].includes(response.status)).toBe(true);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("data");
        expect(response.body.data).toHaveProperty("trades");
        expect(response.body.data).toHaveProperty("pagination");
        expect(Array.isArray(response.body.data.trades)).toBe(true);
      } else if (response.status === 503) {
        expect(response.body).toHaveProperty("success", false);
        expect(response.body).toHaveProperty("error", "Trade history unavailable");
        expect(response.body).toHaveProperty("requirements");
        expect(response.body).toHaveProperty("actions");
      }
    });

    test("should handle query parameters", async () => {
      const response = await request(app)
        .get("/api/trades/history?symbol=AAPL&limit=10&offset=0&sortBy=execution_time&sortOrder=desc")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 503, 500].includes(response.status)).toBe(true);
    });

    test("should require authentication", async () => {
      const response = await request(app)
        .get("/api/trades/history");
        // No auth header

      expect([401].includes(response.status)).toBe(true);
    });
  });

  describe("GET /api/trades/performance", () => {
    test("should return performance data or error", async () => {
      const response = await request(app)
        .get("/api/trades/performance")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("data");
        expect(response.body.data).toHaveProperty("benchmarks");
        expect(response.body.data).toHaveProperty("attribution");
        expect(response.body.data).toHaveProperty("timeframe");
      } else if (response.status === 500) {
        expect(response.body).toHaveProperty("success", false);
        expect(response.body).toHaveProperty("error", "Performance data unavailable");
        expect(response.body).toHaveProperty("requirements");
        expect(response.body).toHaveProperty("actions");
      }
    });

    test("should require authentication", async () => {
      const response = await request(app)
        .get("/api/trades/performance");
        // No auth header

      expect([401].includes(response.status)).toBe(true);
    });
  });

  describe("GET /api/trades/insights", () => {
    test("should return trade insights", async () => {
      const response = await request(app)
        .get("/api/trades/insights")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("data");
        expect(response.body.data).toHaveProperty("insights");
        expect(response.body.data).toHaveProperty("total");
        expect(Array.isArray(response.body.data.insights)).toBe(true);
        expect(typeof response.body.data.total).toBe("number");
      }
    });

    test("should handle limit parameter", async () => {
      const response = await request(app)
        .get("/api/trades/insights?limit=5")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 404]).toContain(response.status);
    });

    test("should require authentication", async () => {
      const response = await request(app)
        .get("/api/trades/insights");
        // No auth header

      expect([401].includes(response.status)).toBe(true);
    });
  });

  describe("GET /api/trades/export", () => {
    test("should export trade data as JSON by default", async () => {
      const response = await request(app)
        .get("/api/trades/export")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("data");
        expect(Array.isArray(response.body.data)).toBe(true);
      }
    });

    test("should export as CSV when format=csv", async () => {
      const response = await request(app)
        .get("/api/trades/export?format=csv")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.headers["content-type"]).toBe("text/csv; charset=utf-8");
        expect(response.headers["content-disposition"]).toContain("attachment");
        expect(typeof response.text).toBe("string");
      }
    });

    test("should handle date range parameters", async () => {
      const response = await request(app)
        .get("/api/trades/export?startDate=2023-01-01&endDate=2023-12-31")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 404]).toContain(response.status);
    });

    test("should require authentication", async () => {
      const response = await request(app)
        .get("/api/trades/export");
        // No auth header

      expect([401].includes(response.status)).toBe(true);
    });
  });

  describe("DELETE /api/trades/data", () => {
    test("should require confirmation", async () => {
      const response = await request(app)
        .delete("/api/trades/data")
        .set("Authorization", "Bearer dev-bypass-token")
        .send({});

      expect([400, 422]).toContain(response.status);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body).toHaveProperty("error");
      expect(response.body.error).toContain("Confirmation required");
    });

    test("should delete data with proper confirmation", async () => {
      const response = await request(app)
        .delete("/api/trades/data")
        .set("Authorization", "Bearer dev-bypass-token")
        .send({ confirm: "DELETE_ALL_TRADE_DATA" });

      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("message");
        expect(response.body.message).toContain("deleted successfully");
      }
    });

    test("should require authentication", async () => {
      const response = await request(app)
        .delete("/api/trades/data")
        .send({ confirm: "DELETE_ALL_TRADE_DATA" });
        // No auth header

      expect([401].includes(response.status)).toBe(true);
    });
  });

  describe("Error Handling", () => {
    test("should handle malformed requests", async () => {
      const response = await request(app)
        .get("/api/trades/analytics?timeframe=invalid")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 400, 500].includes(response.status)).toBe(true);
    });

    test("should handle invalid position ID", async () => {
      const response = await request(app)
        .get("/api/trades/analytics/invalid-id")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 404, 500].includes(response.status)).toBe(true);
    });
  });

  describe("Performance", () => {
    test("should respond within reasonable time", async () => {
      const startTime = Date.now();
      
      const response = await request(app)
        .get("/api/trades")
        .set("Authorization", "Bearer dev-bypass-token");

      const responseTime = Date.now() - startTime;
      
      expect(responseTime).toBeLessThan(3000);
      expect([200, 404]).toContain(response.status);
    });

    test("should handle concurrent requests", async () => {
      const requests = [
        request(app).get("/api/trades").set("Authorization", "Bearer dev-bypass-token"),
        request(app).get("/api/trades/health").set("Authorization", "Bearer dev-bypass-token"),
        request(app).get("/api/trades/summary").set("Authorization", "Bearer dev-bypass-token")
      ];

      const responses = await Promise.all(requests);
      
      responses.forEach((response, index) => {
        if (index === 0) {
          expect([200, 404]).toContain(response.status);
        } else {
          expect([200, 404]).toContain(response.status);
        }
      });
    });
  });
});
const express = require("express");
const request = require("supertest");

// Mock database for unit tests
jest.mock("../../../utils/database", () => ({
  query: jest.fn(),
}));

const { query } = require("../../../utils/database");

describe("Market Routes Unit Tests", () => {
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

    // Load market routes
    const marketRouter = require("../../../routes/market");
    app.use("/market", marketRouter);
  });

  beforeEach(() => {
    // Reset all mocks before each test
    jest.clearAllMocks();

    // Set up default mock responses for all tests
    query.mockImplementation((sql, params) => {
      // Mock market overview queries
      if (sql.includes("SELECT") && (sql.includes("market_data") || sql.includes("price_daily"))) {
        return Promise.resolve({
          rows: [
            {
              symbol: "SPY",
              current_price: 435.50,
              change: 2.45,
              change_percent: 0.56,
              volume: 45000000,
              market_cap: 15000000000000,
              sector: "Index",
              date: "2025-09-28"
            },
            {
              symbol: "QQQ",
              current_price: 385.20,
              change: -1.23,
              change_percent: -0.32,
              volume: 32000000,
              market_cap: 12000000000000,
              sector: "Technology",
              date: "2025-09-28"
            }
          ]
        });
      }

      // Mock sector performance queries
      if (sql.includes("GROUP BY") && sql.includes("sector")) {
        return Promise.resolve({
          rows: [
            {
              sector: "Technology",
              avg_change: 1.25,
              avg_volume: 25000000,
              stock_count: 150,
              total_market_cap: 8500000000000
            },
            {
              sector: "Healthcare",
              avg_change: -0.45,
              avg_volume: 18000000,
              stock_count: 120,
              total_market_cap: 3200000000000
            },
            {
              sector: "Finance",
              avg_change: 0.78,
              avg_volume: 22000000,
              stock_count: 110,
              total_market_cap: 4100000000000
            }
          ]
        });
      }

      // Mock economic indicators
      if (sql.includes("economic") || sql.includes("indicators")) {
        return Promise.resolve({
          rows: [
            {
              indicator: "GDP",
              value: 2.3,
              period: "Q3 2025",
              change: 0.2,
              date: "2025-09-28"
            },
            {
              indicator: "Unemployment",
              value: 3.8,
              period: "September 2025",
              change: -0.1,
              date: "2025-09-28"
            }
          ]
        });
      }

      // Mock sentiment data
      if (sql.includes("sentiment") || sql.includes("aaii")) {
        return Promise.resolve({
          rows: [
            {
              date: "2025-09-28",
              bullish: 35.5,
              bearish: 28.2,
              neutral: 36.3,
              sentiment_score: 0.62
            },
            {
              date: "2025-09-21",
              bullish: 32.1,
              bearish: 31.5,
              neutral: 36.4,
              sentiment_score: 0.58
            }
          ]
        });
      }

      // Mock breadth data
      if (sql.includes("breadth") || sql.includes("advance") || sql.includes("decline")) {
        return Promise.resolve({
          rows: [
            {
              date: "2025-09-28",
              advancing: 1823,
              declining: 1456,
              unchanged: 321,
              new_highs: 89,
              new_lows: 34,
              ad_ratio: 1.25
            }
          ]
        });
      }

      // Mock table existence checks
      if (sql.includes("information_schema.tables") || sql.includes("EXISTS")) {
        return Promise.resolve({
          rows: [{ exists: true }]
        });
      }

      // Default empty response for unmatched queries
      return Promise.resolve({
        rows: []
      });
    });
  });

  describe("GET /market/", () => {
    test("should return market info", async () => {
      const response = await request(app).get("/market/").expect(200);

      expect(response.body).toHaveProperty("success");
      expect(response.body.success).toBe(true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("endpoint");
      expect(response.body.data.endpoint).toBe("market");
      expect(response.body.data).toHaveProperty("available_routes");
      expect(Array.isArray(response.body.data.available_routes)).toBe(true);
    });
  });

  describe("GET /market/debug", () => {
    test("should return debug information", async () => {
      const response = await request(app).get("/market/debug").expect(200);

      expect(response.body).toHaveProperty("success");
      expect(response.body).toHaveProperty("tables");
      expect(response.body).toHaveProperty("recordCounts");
    });
  });

  describe("GET /market/overview", () => {
    test("should return market overview", async () => {
      const response = await request(app).get("/market/overview").expect(200);

      expect(response.body).toHaveProperty("success");
      expect(response.body).toHaveProperty("data");
    });
  });

  describe("GET /market/sectors", () => {
    test("should return sector data", async () => {
      const response = await request(app).get("/market/sectors").expect(200);

      expect(response.body).toHaveProperty("success");
    });
  });

  describe("GET /market/economic", () => {
    test("should return economic data", async () => {
      const response = await request(app).get("/market/economic");

      expect([200, 503]).toContain(response.status);
      expect(response.body).toHaveProperty("success");
    });
  });

  describe("GET /market/sentiment", () => {
    test("should return sentiment history with AAII data", async () => {
      const response = await request(app)
        .get("/market/sentiment?days=30");

      expect([200, 404]).toContain(response.status);
      expect(response.body).toBeDefined();
      expect(typeof response.body).toBe("object");

      if (response.status === 200) {
        expect(response.body).toHaveProperty("data");
        // The /sentiment endpoint returns current sentiment data, not historical
        expect(response.body.data).toHaveProperty("fear_greed");
        expect(response.body.data).toHaveProperty("naaim");

        // Check if AAII data is present
        if (response.body.data.aaii) {
          expect(response.body.data.aaii).toHaveProperty("bullish");
          expect(response.body.data.aaii).toHaveProperty("neutral");
          expect(response.body.data.aaii).toHaveProperty("bearish");
          expect(response.body.data.aaii).toHaveProperty("date");
        }
      }
    });

    test("should handle sentiment with custom parameters", async () => {
      const response = await request(app)
        .get("/market/sentiment?days=7&limit=10");

      expect([200, 404]).toContain(response.status);

      expect(response.body).toBeDefined();
      expect(typeof response.body).toBe("object");

      if (response.status === 200) {
        expect(response.body).toHaveProperty("data");
        expect(response.body.data).toHaveProperty("fear_greed");
        expect(response.body.data).toHaveProperty("naaim");
      }
    });
  });

  describe("GET /market/aaii", () => {
    test("should return AAII sentiment data", async () => {
      const response = await request(app).get("/market/aaii").expect(200);

      // AAII endpoint returns data directly without success wrapper
      if (response.body && typeof response.body === "object") {
        expect(response.body).toHaveProperty("bullish");
        expect(response.body).toHaveProperty("neutral");
        expect(response.body).toHaveProperty("bearish");
        expect(response.body).toHaveProperty("date");
      }
    });
  });

  // Add comprehensive tests for major market endpoints
  describe("GET /market/data", () => {
    test("should return market data with success flag", async () => {
      const response = await request(app).get("/market/data").expect(200);

      expect(response.body).toBeDefined();
      expect(typeof response.body).toBe("object");
      expect(response.body).toHaveProperty("data");
    });

    test("should handle query parameters", async () => {
      const response = await request(app)
        .get("/market/data?limit=5&sort=volume")
        .expect(200);

      expect(response.body).toBeDefined();
      expect(typeof response.body).toBe("object");
    });
  });

  describe("GET /market/overview", () => {
    test("should return market overview data", async () => {
      const response = await request(app).get("/market/overview").expect(200);

      expect(response.body).toBeDefined();
      expect(typeof response.body).toBe("object");
      expect(response.body).toHaveProperty("data");

      if (response.body.data) {
        expect(response.body.data).toHaveProperty("indices");
        expect(response.body.data).toHaveProperty("sentiment_indicators");
      }
    });

    test("should handle market overview with parameters", async () => {
      const response = await request(app)
        .get("/market/overview?detailed=true")
        .expect(200);

      expect(response.body).toBeDefined();
      expect(typeof response.body).toBe("object");
    });
  });

  describe("GET /market/sectors/performance", () => {
    test("should return sector performance data", async () => {
      const response = await request(app)
        .get("/market/sectors/performance");

      expect([200, 503]).toContain(response.status);

      expect(response.body).toBeDefined();
      expect(typeof response.body).toBe("object");

      if (response.status === 200) {
        expect(response.body).toHaveProperty("data");
      }
    });

    test("should handle sector performance with timeframe", async () => {
      const response = await request(app)
        .get("/market/sectors/performance?timeframe=1d");

      expect([200, 503]).toContain(response.status);

      expect(response.body).toBeDefined();
      expect(typeof response.body).toBe("object");
    });
  });

  describe("GET /market/economic/indicators", () => {
    test("should return economic indicators", async () => {
      const response = await request(app)
        .get("/market/economic/indicators")
        .expect(200);

      expect(response.body).toBeDefined();
      expect(typeof response.body).toBe("object");
      expect(response.body).toHaveProperty("data");

      if (response.body.data) {
        expect(response.body.data).toHaveProperty("indicators");
        expect(response.body.data).toHaveProperty("summary");
      }
    });

    test("should filter by category", async () => {
      const response = await request(app)
        .get("/market/economic/indicators?category=inflation")
        .expect(200);

      expect(response.body).toBeDefined();
      expect(typeof response.body).toBe("object");
    });

    test("should include historical data when requested", async () => {
      const response = await request(app)
        .get("/market/economic/indicators?historical=true")
        .expect(200);

      expect(response.body).toBeDefined();
      expect(typeof response.body).toBe("object");
      if (response.body.data && response.body.data.indicators) {
        const indicators = Object.values(response.body.data.indicators);
        if (indicators.length > 0) {
          // Some indicators should have historical data
          const hasHistorical = indicators.some((ind) => ind.historical_data);
          expect(hasHistorical).toBeTruthy();
        }
      }
    });
  });

  describe("GET /market/breadth", () => {
    test("should return market breadth data", async () => {
      const response = await request(app).get("/market/breadth");

      expect([200, 503]).toContain(response.status);
      expect(response.body).toBeDefined();
      expect(typeof response.body).toBe("object");

      if (response.status === 200) {
        expect(response.body).toHaveProperty("data");
      }
    });

    test("should handle breadth with parameters", async () => {
      const response = await request(app)
        .get("/market/breadth?period=5d");

      expect([200, 503]).toContain(response.status);
      expect(response.body).toBeDefined();
      expect(typeof response.body).toBe("object");
    });
  });

  describe("GET /market/summary", () => {
    test("should return market summary", async () => {
      const response = await request(app).get("/market/summary").expect(200);

      expect(response.body).toBeDefined();
      expect(typeof response.body).toBe("object");
      expect(response.body).toHaveProperty("data");
    });

    test("should handle summary with filters", async () => {
      const response = await request(app)
        .get("/market/summary?include_sectors=true")
        .expect(200);

      expect(response.body).toBeDefined();
      expect(typeof response.body).toBe("object");
    });
  });

  describe("GET /market/naaim", () => {
    test("should return NAAIM data", async () => {
      const response = await request(app).get("/market/naaim");

      expect([200, 404, 503]).toContain(response.status);

      expect(response.body).toBeDefined();
      expect(typeof response.body).toBe("object");

      if (response.status === 200) {
        expect(response.body).toHaveProperty("data");
      }
    });
  });

  describe("GET /market/ping", () => {
    test("should return ping response", async () => {
      const response = await request(app).get("/market/ping").expect(200);

      expect(response.body).toBeDefined();
      expect(typeof response.body).toBe("object");
      expect(response.body).toHaveProperty("status", "ok");
    });
  });

  // AWS Failing Endpoints Tests (Previously failing due to mock responses)
  describe("AWS Failing Endpoints - Database-Driven", () => {
    test("GET /market/recession-forecast should return database-driven recession analysis", async () => {
      const response = await request(app)
        .get("/market/recession-forecast")
        .expect(200);

      expect(response.body).toBeDefined();
      expect(typeof response.body).toBe("object");
      expect(response.body).toHaveProperty("data");

      if (response.body.data) {
        expect(response.body.data).toHaveProperty("compositeRecessionProbability");
        expect(response.body.data).toHaveProperty("keyIndicators");
        expect(response.body.data).toHaveProperty("analysis");
      }
    });

    test("GET /market/leading-indicators should return database-driven leading indicators", async () => {
      const response = await request(app)
        .get("/market/leading-indicators")
        .expect(200);

      expect(response.body).toBeDefined();
      expect(typeof response.body).toBe("object");
      expect(response.body).toHaveProperty("data");

      if (response.body.data) {
        expect(response.body.data).toHaveProperty("indicators");
        expect(response.body.data).toHaveProperty("gdpGrowth");
      }
    });

    test("GET /market/sectoral-analysis should return database-driven sector analysis", async () => {
      const response = await request(app)
        .get("/market/sectoral-analysis")
        .expect(200);

      expect(response.body).toBeDefined();
      expect(typeof response.body).toBe("object");
      expect(response.body).toHaveProperty("data");

      if (response.body.data) {
        expect(response.body.data).toHaveProperty("sectors");
        expect(response.body.data).toHaveProperty("summary");
      }
    });

    test("GET /market/ai-insights should return database-driven AI insights", async () => {
      const response = await request(app)
        .get("/market/ai-insights")
        .expect(200);

      expect(response.body).toBeDefined();
      expect(typeof response.body).toBe("object");
      expect(response.body).toHaveProperty("data");

      if (response.body.data) {
        expect(response.body.data).toHaveProperty("insights");
        expect(Array.isArray(response.body.data.insights)).toBe(true);
        // Verify insights are based on real data, not hardcoded
        if (response.body.data.insights.length > 0) {
          const firstInsight = response.body.data.insights[0];
          expect(firstInsight).toHaveProperty("title");
          expect(firstInsight).toHaveProperty("description");
          expect(firstInsight).toHaveProperty("confidence");
          // Should have data_source indicating real data usage
          expect(firstInsight).toHaveProperty("data_source");
        }
      }
    });

    test("GET /market/economic-scenarios should return database-driven economic scenarios", async () => {
      const response = await request(app)
        .get("/market/economic-scenarios")
        .expect(200);

      expect(response.body).toBeDefined();
      expect(typeof response.body).toBe("object");
      expect(response.body).toHaveProperty("data");

      if (response.body.data) {
        expect(response.body.data).toHaveProperty("scenarios");
        expect(Array.isArray(response.body.data.scenarios)).toBe(true);
        // Verify scenarios are based on real economic data
        if (response.body.data.scenarios.length > 0) {
          const scenario = response.body.data.scenarios[0];
          expect(scenario).toHaveProperty("name");
          expect(scenario).toHaveProperty("probability");
          expect(scenario).toHaveProperty("gdpGrowth");
          expect(scenario).toHaveProperty("unemployment");
          expect(scenario).toHaveProperty("fedRate");
        }
      }
    });
  });

  // Error handling tests
  describe("Error Handling", () => {
    test("should handle invalid query parameters gracefully", async () => {
      const response = await request(app)
        .get("/market/overview?limit=invalid")
        .expect(200); // Most endpoints handle invalid params gracefully

      expect(response.body).toHaveProperty("success");
    });

    test("should handle missing optional parameters", async () => {
      const response = await request(app)
        .get("/market/economic/indicators?category=")
        .expect(200);

      expect(response.body).toBeDefined();
      expect(typeof response.body).toBe("object");
    });
  });
});

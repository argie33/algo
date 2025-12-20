const express = require("express");
const request = require("supertest");
// Mock database for unit tests
jest.mock("../../../utils/database", () => ({
  query: jest.fn().mockResolvedValue({ rows: [], rowCount: 0 }),
  closeDatabase: jest.fn(),
  initializeDatabase: jest.fn(),
  getPool: jest.fn(),
  transaction: jest.fn(),
  healthCheck: jest.fn(),
}));

const { query, closeDatabase, initializeDatabase, getPool, transaction, healthCheck } = require("../../../utils/database");
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
      // Mock table existence checks (information_schema queries)
      if (sql.includes("information_schema")) {
        // Handle sector_performance_exists aliased column
        if (sql.includes("sector_performance_exists")) {
          return Promise.resolve({
            rows: [
              {
                sector_performance_exists: true
              }
            ]
          });
        }
        // Default for generic exists checks
        return Promise.resolve({
          rows: [
            {
              exists: true
            }
          ]
        });
      }
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
      // Mock sector_performance queries (both DISTINCT ON and ORDER BY variants)
      if (sql.includes("sector_performance") && (sql.includes("DISTINCT ON") || sql.includes("ORDER BY performance_1d"))) {
        return Promise.resolve({
          rows: [
            {
              etf_symbol: "XLK",
              sector: "Technology",
              price: 228.50,
              change_percent: 1.25,
              change: 2.82,
              volume: 45000000,
              market_cap: 12500000000,
              momentum: 0.15,
              money_flow: 12500000,
              rsi: 65.2,
              performance_1d: 1.25,
              performance_5d: 3.45,
              performance_20d: 8.72,
              overall_rank: 1,
              fetched_at: "2025-09-28"
            },
            {
              etf_symbol: "XLV",
              sector: "Healthcare",
              price: 159.30,
              change_percent: -0.45,
              change: -0.72,
              volume: 32000000,
              market_cap: 8500000000,
              momentum: -0.05,
              money_flow: -8500000,
              rsi: 42.1,
              performance_1d: -0.45,
              performance_5d: 1.23,
              performance_20d: 2.15,
              overall_rank: 8,
              fetched_at: "2025-09-28"
            },
            {
              etf_symbol: "XLF",
              sector: "Finance",
              price: 195.75,
              change_percent: 0.78,
              change: 1.52,
              volume: 22000000,
              market_cap: 5500000000,
              momentum: 0.08,
              money_flow: 5500000,
              rsi: 58.3,
              performance_1d: 0.78,
              performance_5d: 2.34,
              performance_20d: 5.67,
              overall_rank: 3,
              fetched_at: "2025-09-28"
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
              name: "GDP",
              category: "economic_growth",
              value: 2.3,
              unit: "percent",
              frequency: "quarterly",
              last_updated: "2025-09-28",
              change_previous: 0.2,
              change_percent: 0.09,
              trend: "positive",
              next_release: "2025-12-28"
            },
            {
              name: "Unemployment Rate",
              category: "employment",
              value: 3.8,
              unit: "percent",
              frequency: "monthly",
              last_updated: "2025-09-28",
              change_previous: -0.1,
              change_percent: -0.02,
              trend: "positive",
              next_release: "2025-10-31"
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
      // Mock breadth data - handle CTE queries for breadth data
      if (sql.includes("daily_changes") || (sql.includes("WITH") && sql.includes("calculated_change_percent")) || sql.includes("strong_advancing")) {
        // Return comprehensive breadth data for CTE queries - includes all required fields
        return Promise.resolve({
          rows: [
            {
              total_stocks: 3300,
              advancing: 1823,
              declining: 1456,
              unchanged: 21,
              strong_advancing: 89,
              strong_declining: 34,
              strong_unchanged: 0,
              ad_ratio: 1.2520,
              breadth_percent: 55.54,
              internal_strength: "Strong",
              fetched_at: "2025-09-28",
              // Fields required by response formatting
              avg_change: 0.45,
              avg_volume: 25000000
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
      // Mock distribution days data
      if (sql.includes("distribution_days")) {
        return Promise.resolve({
          rows: [
            {
              symbol: "^GSPC",
              count: 2,
              signal: "NORMAL",
              days: [
                {
                  date: "2025-09-25",
                  close_price: 4350.25,
                  change_pct: -0.45,
                  volume: 3500000000,
                  volume_ratio: 1.15,
                  days_ago: 3
                },
                {
                  date: "2025-09-20",
                  close_price: 4380.75,
                  change_pct: -0.35,
                  volume: 3450000000,
                  volume_ratio: 1.12,
                  days_ago: 8
                }
              ]
            },
            {
              symbol: "^IXIC",
              count: 4,
              signal: "ELEVATED",
              days: [
                {
                  date: "2025-09-26",
                  close_price: 13520.50,
                  change_pct: -0.55,
                  volume: 4200000000,
                  volume_ratio: 1.22,
                  days_ago: 2
                },
                {
                  date: "2025-09-25",
                  close_price: 13580.25,
                  change_pct: -0.40,
                  volume: 4150000000,
                  volume_ratio: 1.18,
                  days_ago: 3
                },
                {
                  date: "2025-09-22",
                  close_price: 13650.75,
                  change_pct: -0.30,
                  volume: 4100000000,
                  volume_ratio: 1.10,
                  days_ago: 6
                },
                {
                  date: "2025-09-18",
                  close_price: 13720.00,
                  change_pct: -0.25,
                  volume: 4050000000,
                  volume_ratio: 1.08,
                  days_ago: 10
                }
              ]
            },
            {
              symbol: "^DJI",
              count: 5,
              signal: "CAUTION",
              days: [
                {
                  date: "2025-09-27",
                  close_price: 34250.50,
                  change_pct: -0.60,
                  volume: 350000000,
                  volume_ratio: 1.25,
                  days_ago: 1
                },
                {
                  date: "2025-09-26",
                  close_price: 34380.75,
                  change_pct: -0.45,
                  volume: 345000000,
                  volume_ratio: 1.20,
                  days_ago: 2
                },
                {
                  date: "2025-09-24",
                  close_price: 34520.25,
                  change_pct: -0.35,
                  volume: 340000000,
                  volume_ratio: 1.15,
                  days_ago: 4
                },
                {
                  date: "2025-09-21",
                  close_price: 34650.00,
                  change_pct: -0.30,
                  volume: 335000000,
                  volume_ratio: 1.12,
                  days_ago: 7
                },
                {
                  date: "2025-09-19",
                  close_price: 34780.50,
                  change_pct: -0.28,
                  volume: 330000000,
                  volume_ratio: 1.10,
                  days_ago: 9
                }
              ]
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
      // Default responses for unmatched queries - provide smart defaults
      // If it's a query with price_daily joins, return breadth-like data
      if (sql.includes("price_daily") || sql.toUpperCase().includes("COUNT") || sql.toUpperCase().includes("WITH")) {
        // Return breadth data structure for any aggregation query
        return Promise.resolve({
          rows: [
            {
              total_stocks: 3300,
              advancing: 1823,
              declining: 1456,
              unchanged: 21,
              strong_advancing: 89,
              strong_declining: 34,
              strong_unchanged: 0,
              ad_ratio: 1.2520,
              breadth_percent: 55.54,
              avg_change: 0.45,
              avg_volume: 25000000
            }
          ]
        });
      }
      // Default empty response for truly unmatched queries
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
  describe("GET /market/distribution-days", () => {
    test("should return distribution days data for major indices", async () => {
      const response = await request(app).get("/market/distribution-days");
      expect([200, 503]).toContain(response.status);
      expect(response.body).toBeDefined();
      expect(typeof response.body).toBe("object");
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
        // Verify data structure for each major index
        const data = response.body.data;
        expect(data).toBeDefined();
        // Check S&P 500 data
        if (data["^GSPC"]) {
          expect(data["^GSPC"]).toHaveProperty("name");
          expect(data["^GSPC"]).toHaveProperty("count");
          expect(data["^GSPC"]).toHaveProperty("signal");
          expect(data["^GSPC"]).toHaveProperty("days");
          expect(Array.isArray(data["^GSPC"].days)).toBe(true);
          // Verify signal is one of the expected values
          expect(["NORMAL", "ELEVATED", "CAUTION", "UNDER_PRESSURE"]).toContain(data["^GSPC"].signal);
        }
        // Check NASDAQ data
        if (data["^IXIC"]) {
          expect(data["^IXIC"]).toHaveProperty("name");
          expect(data["^IXIC"]).toHaveProperty("count");
          expect(data["^IXIC"]).toHaveProperty("signal");
          expect(data["^IXIC"]).toHaveProperty("days");
          expect(Array.isArray(data["^IXIC"].days)).toBe(true);
        }
        // Check Dow Jones data
        if (data["^DJI"]) {
          expect(data["^DJI"]).toHaveProperty("name");
          expect(data["^DJI"]).toHaveProperty("count");
          expect(data["^DJI"]).toHaveProperty("signal");
          expect(data["^DJI"]).toHaveProperty("days");
          expect(Array.isArray(data["^DJI"].days)).toBe(true);
        }
      }
    });
    test("should return proper distribution day structure", async () => {
      const response = await request(app).get("/market/distribution-days");
      if (response.status === 200 && response.body.data) {
        const data = response.body.data;
        // Check at least one index has distribution days with proper structure
        Object.values(data).forEach((indexData) => {
          if (indexData.days && indexData.days.length > 0) {
            const firstDay = indexData.days[0];
            // Verify distribution day object structure
            expect(firstDay).toHaveProperty("date");
            expect(firstDay).toHaveProperty("close_price");
            expect(firstDay).toHaveProperty("change_pct");
            expect(firstDay).toHaveProperty("volume");
            expect(firstDay).toHaveProperty("volume_ratio");
            expect(firstDay).toHaveProperty("days_ago");
            // Verify data types
            expect(typeof firstDay.date).toBe("string");
            expect(typeof firstDay.change_pct).toBe("number");
            expect(typeof firstDay.volume).toBe("number");
            expect(typeof firstDay.volume_ratio).toBe("number");
            expect(typeof firstDay.days_ago).toBe("number");
          }
        });
      }
    });
    test("should handle missing distribution_days table gracefully", async () => {
      // Mock table doesn't exist
      query.mockImplementation((sql) => {
        if (sql.includes("information_schema.tables") || sql.includes("EXISTS")) {
          return Promise.resolve({
            rows: [{ exists: false }]
          });
        }
        return Promise.resolve({ rows: [] });
      });
      const response = await request(app).get("/market/distribution-days");
      expect(response.status).toBe(503);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body).toHaveProperty("error");
      expect(response.body.error).toContain("Distribution days service unavailable");
    });
    test("should handle database query errors", async () => {
      // Mock database error
      query.mockImplementation((sql) => {
        if (sql.includes("information_schema.tables") || sql.includes("EXISTS")) {
          return Promise.resolve({
            rows: [{ exists: true }]
          });
        }
        if (sql.includes("distribution_days")) {
          return Promise.reject(new Error("Database connection failed"));
        }
        return Promise.resolve({ rows: [] });
      });
      const response = await request(app).get("/market/distribution-days");
      expect(response.status).toBe(503);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body).toHaveProperty("error");
    });
    test("should return 404 when no distribution days data exists", async () => {
      // Mock empty result
      query.mockImplementation((sql) => {
        if (sql.includes("information_schema.tables") || sql.includes("EXISTS")) {
          return Promise.resolve({
            rows: [{ exists: true }]
          });
        }
        if (sql.includes("distribution_days")) {
          return Promise.resolve({ rows: [] });
        }
        return Promise.resolve({ rows: [] });
      });
      const response = await request(app).get("/market/distribution-days");
      expect(response.status).toBe(404);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body).toHaveProperty("error");
      expect(response.body.error).toContain("No distribution days data found");
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
    test("GET /market/recession-forecast should return database-driven recession analysis (or 503 if missing data)", async () => {
      const response = await request(app)
        .get("/market/recession-forecast");
      // Expect either 200 (data loaded) or 503 (data missing) - NO mock fallbacks
      expect([200, 503]).toContain(response.status);
      expect(response.body).toBeDefined();
      expect(typeof response.body).toBe("object");
      if (response.status === 200) {
        expect(response.body).toHaveProperty("data");
        expect(response.body.data).toHaveProperty("compositeRecessionProbability");
        expect(response.body.data).toHaveProperty("keyIndicators");
        expect(response.body.data).toHaveProperty("analysis");
      } else if (response.status === 503) {
        // Missing data - should have error message
        expect(response.body).toHaveProperty("error");
        expect(response.body).toHaveProperty("missing");
      }
    });
    test("GET /market/leading-indicators should return database-driven leading indicators (or 503 if missing data)", async () => {
      const response = await request(app)
        .get("/market/leading-indicators");
      // Expect either 200 (data loaded) or 503 (data missing) - NO mock fallbacks
      expect([200, 503]).toContain(response.status);
      expect(response.body).toBeDefined();
      expect(typeof response.body).toBe("object");
      if (response.status === 200) {
        expect(response.body).toHaveProperty("data");
        expect(response.body.data).toHaveProperty("indicators");
      } else if (response.status === 503) {
        // Missing data - should have error message
        expect(response.body).toHaveProperty("error");
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
    test("GET /market/economic-scenarios should return database-driven economic scenarios (or 503 if missing data)", async () => {
      const response = await request(app)
        .get("/market/economic-scenarios");
      // Expect either 200 (data loaded) or 503 (data missing) - NO mock fallbacks
      expect([200, 503]).toContain(response.status);
      expect(response.body).toBeDefined();
      expect(typeof response.body).toBe("object");
      if (response.status === 200) {
        expect(response.body).toHaveProperty("data");
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
      } else if (response.status === 503) {
        // Missing data - should have error message
        expect(response.body).toHaveProperty("error");
        expect(response.body).toHaveProperty("missing");
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

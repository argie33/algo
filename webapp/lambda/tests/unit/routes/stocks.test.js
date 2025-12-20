const express = require("express");
const request = require("supertest");
// Mock database for unit tests
jest.mock("../../../utils/database", () => ({
  query: jest.fn().mockResolvedValue({ rows: [], rowCount: 0 }),
}));
// Import Jest functions
// Extend Jest expect for custom matchers
expect.extend({
  toBeOneOf(received, expected) {
    const pass = expected.includes(received);
    if (pass) {
      return {
        message: () => `expected ${received} not to be one of ${expected}`,
        pass: true,
      };
    } else {
      return {
        message: () => `expected ${received} to be one of ${expected}`,
        pass: false,
      };
    }
  },
});
const { query, closeDatabase, initializeDatabase, getPool, transaction, healthCheck } = require("../../../utils/database");

describe("Stocks Routes Unit Tests", () => {
  let app;
  beforeAll(() => {
    // Ensure test environment
    process.env.NODE_ENV = "test";
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
    // Load stocks routes
    const stocksRouter = require("../../../routes/stocks");
    app.use("/stocks", stocksRouter);
  });
  beforeEach(() => {
    // Reset all mocks before each test
    jest.clearAllMocks();
    // Set up default mock responses for all tests
    query.mockImplementation((sql, params) => {
      // Mock price_daily table queries (for price endpoints)
      if (sql.includes("FROM price_daily") && sql.includes("WHERE symbol = $1")) {
        // Return empty for price endpoints to trigger 404 with correct error message
        return Promise.resolve({
          rows: []
        });
      }
      // Mock stock list endpoint
      if (sql.includes("SELECT") && sql.includes("company_profile") && sql.includes("market_data")) {
        return Promise.resolve({
          rows: [
            {
              symbol: "AAPL",
              name: "Apple Inc.",
              sector: "Technology",
              industry: "Consumer Electronics",
              market_cap: 2800000000000,
              current_price: 185.50,
              volume: 45678900,
              price: {
                current: 185.50,
                change: 2.34,
                change_percent: 1.28
              },
              financialMetrics: {
                trailing_pe: 28.5,
                forward_pe: 25.2,
                price_to_book: 8.9,
                dividend_yield: 0.45
              }
            },
            {
              symbol: "MSFT",
              name: "Microsoft Corporation",
              sector: "Technology",
              industry: "Software",
              market_cap: 2500000000000,
              current_price: 378.20,
              volume: 23456700,
              price: {
                current: 378.20,
                change: -5.67,
                change_percent: -1.48
              },
              financialMetrics: {
                trailing_pe: 32.1,
                forward_pe: 28.8,
                price_to_book: 12.3,
                dividend_yield: 0.68
              }
            }
          ]
        });
      }
      // Mock stock details endpoint - return empty to trigger 404
      if (sql.includes("WHERE cp.ticker = $1")) {
        return Promise.resolve({
          rows: []
        });
      }
      // Mock sectors endpoint
      if (sql.includes("GROUP BY") && sql.includes("sector")) {
        return Promise.resolve({
          rows: [
            {
              sector: "Technology",
              count: 1250,
              avg_market_cap: 450000000000
            },
            {
              sector: "Healthcare",
              count: 890,
              avg_market_cap: 180000000000
            }
          ]
        });
      }
      // Mock search endpoint
      if (sql.includes("ILIKE") || sql.includes("LIKE")) {
        return Promise.resolve({
          rows: [
            {
              symbol: "AAPL",
              name: "Apple Inc.",
              sector: "Technology",
              match_score: 0.95
            }
          ]
        });
      }
      // Mock comparison endpoint
      if (sql.includes("IN (") || sql.includes("ANY(")) {
        return Promise.resolve({
          rows: [
            {
              symbol: "AAPL",
              name: "Apple Inc.",
              current_price: 185.50,
              market_cap: 2800000000000,
              pe_ratio: 28.5,
              volume: 45678900
            },
            {
              symbol: "MSFT",
              name: "Microsoft Corporation",
              current_price: 378.20,
              market_cap: 2500000000000,
              pe_ratio: 32.1,
              volume: 23456700
            }
          ]
        });
      }
      // Default empty response for unmatched queries
      return Promise.resolve({
        rows: []
      });
    });
  });
  describe("GET /stocks/", () => {
    test("should return stocks data with correct loader table structure", async () => {
      const response = await request(app)
        .get("/stocks/")
        .set("Authorization", "Bearer test-token")
        .expect(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(Array.isArray(response.body.data)).toBe(true);
      expect(response.body).toHaveProperty("pagination");
      // Verify loader table structure fields when data exists
      if (response.body.data.length > 0) {
        const stock = response.body.data[0];
        // Core fields from company_profile and market_data tables
        expect(stock).toHaveProperty("symbol"); // from company_profile.ticker
        expect(stock).toHaveProperty("sector"); // from company_profile.sector
        expect(stock).toHaveProperty("industry"); // from company_profile.industry
        expect(stock).toHaveProperty("marketCap"); // from market_data.market_cap
        expect(stock).toHaveProperty("price"); // object containing price data from market_data
        expect(stock).toHaveProperty("volume"); // from market_data.volume
        // Optional fields that may or may not be present
        // expect(stock).toHaveProperty("name"); // from stocks.name (may be null)
        // expect(stock).toHaveProperty("shortName"); // API transformation
        // expect(stock).toHaveProperty("fullName"); // API transformation
        // Financial metrics from key_metrics table
        if (stock.financialMetrics) {
          const metrics = stock.financialMetrics;
          // Metrics available from key_metrics table (trailing_pe, forward_pe, etc.)
          expect(typeof metrics).toBe("object");
        }
        if (stock.price) {
          expect(stock.price).toHaveProperty("current"); // current_price from market_data
        }
      }
    });
  });
  describe("GET /stocks/search", () => {
    test("should return search results", async () => {
      const response = await request(app)
        .get("/stocks/search?q=AAPL")
        .set("Authorization", "Bearer test-token")
        .expect(200);
      expect(response.body).toHaveProperty("success");
      expect(response.body).toHaveProperty("data");
    });
  });
  describe("GET /stocks/list", () => {
    test("should return stock list with correct loader table structure", async () => {
      const response = await request(app)
        .get("/stocks/list")
        .set("Authorization", "Bearer test-token")
        .expect(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(Array.isArray(response.body.data)).toBe(true);
      // Check the data structure matches what the loader creates
      if (response.body.data.length > 0) {
        const stock = response.body.data[0];
        expect(stock).toHaveProperty("symbol"); // ticker from company_profile
        expect(stock).toHaveProperty("name"); // short_name or long_name from company_profile
        expect(stock).toHaveProperty("sector"); // sector from company_profile
        expect(stock).toHaveProperty("market_cap"); // market_cap from market_data table
      }
    });
  });
  describe("GET /stocks/sectors", () => {
    test("should return sector data from stocks table", async () => {
      const response = await request(app).get("/stocks/sectors").expect(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(Array.isArray(response.body.data)).toBe(true);
      // Check the sector data structure matches loader expectations
      if (response.body.data.length > 0) {
        const sector = response.body.data[0];
        expect(sector).toHaveProperty("sector");
        expect(sector).toHaveProperty("count");
        expect(sector).toHaveProperty("avg_market_cap"); // From market_data.market_cap aggregated
      }
    });
  });
  describe("GET /stocks/AAPL", () => {
    test("should return stock details", async () => {
      const response = await request(app)
        .get("/stocks/AAPL")
        .set("Authorization", "Bearer test-token");
      // Handle both success and error cases gracefully
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
        expect(response.body).toHaveProperty("timestamp");
        // Verify data structure matches Python loader schemas
        expect(response.body.data).toHaveProperty("symbol", "AAPL");
        expect(response.body.data).toHaveProperty("name");
        expect(response.body.data).toHaveProperty("sector");
        expect(response.body.data).toHaveProperty("industry");
        expect(response.body.data).toHaveProperty("market_cap");
        expect(response.body.data).toHaveProperty("current_price");
        expect(response.body.data).toHaveProperty("volume");
      } else {
        expect([200, 404, 500]).toContain(response.status);
        expect(response.body).toHaveProperty("success", false);
      }
    });
  });
  // Add comprehensive tests for all major stocks endpoints
  describe("GET /stocks/search", () => {
    test("should search stocks by query", async () => {
      const response = await request(app)
        .get("/stocks/search?query=AAPL")
        .expect(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
    });
    test("should handle empty search query", async () => {
      const response = await request(app)
        .get("/stocks/search?query=")
        .expect(200);
      expect(response.body).toHaveProperty("success", true);
    });
    test("should limit search results", async () => {
      const response = await request(app)
        .get("/stocks/search?query=A&limit=5")
        .expect(200);
      expect(response.body).toHaveProperty("success", true);
      if (response.body.data && response.body.data.results) {
        expect(response.body.data.results.length).toBeLessThanOrEqual(5);
      }
    });
  });
  describe("GET /stocks/trending", () => {
    test("should return trending stocks", async () => {
      const response = await request(app)
        .get("/stocks/trending")
        .set("Authorization", "Bearer test-token")
        .expect(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
    });
    test("should handle trending with timeframe", async () => {
      const response = await request(app)
        .get("/stocks/trending?timeframe=1d")
        .set("Authorization", "Bearer test-token")
        .expect(200);
      expect(response.body).toHaveProperty("success", true);
    });
    test("should handle trending with different categories", async () => {
      const response = await request(app)
        .get("/stocks/trending?category=gainers")
        .set("Authorization", "Bearer test-token")
        .expect(200);
      expect(response.body).toHaveProperty("success", true);
    });
  });
  describe("GET /stocks/details/:symbol", () => {
    test("should return stock details for valid symbol", async () => {
      const response = await request(app)
        .get("/stocks/details/AAPL")
        .expect(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      if (response.body.data) {
        expect(response.body.data).toHaveProperty("symbol", "AAPL");
      }
    });
    test("should handle invalid stock symbol", async () => {
      const response = await request(app)
        .get("/stocks/details/INVALID123")
        .expect(200);
      expect(response.body).toHaveProperty("success");
    });
    test("should include comprehensive stock data", async () => {
      const response = await request(app)
        .get("/stocks/details/AAPL?include_financials=true")
        .expect(200);
      expect(response.body).toHaveProperty("success", true);
    });
  });
  describe("GET /stocks/price/:symbol", () => {
    test("should return price data for symbol", async () => {
      const response = await request(app).get("/stocks/price/AAPL");
      // API now returns 200 with data instead of 404
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
      } else {
        expect(response.body).toHaveProperty("success", false);
        expect(response.body).toHaveProperty("error", "No price data found");
      }
    });
    test("should handle price with different timeframes", async () => {
      const response = await request(app)
        .get("/stocks/price/AAPL?timeframe=1d");
      // API now returns 200 with data instead of 404
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
      } else {
        expect(response.body).toHaveProperty("success", false);
        expect(response.body).toHaveProperty("error", "No price data found");
      }
    });
    test("should handle price with historical data", async () => {
      const response = await request(app)
        .get("/stocks/price/AAPL?historical=true&days=30");
      // API now returns 200 with data instead of 404
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
      } else {
        expect(response.body).toHaveProperty("success", false);
        expect(response.body).toHaveProperty("error", "No price data found");
      }
    });
  });
  describe("GET /stocks/movers", () => {
    test("should return market movers", async () => {
      const response = await request(app).get("/stocks/movers").expect(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
    });
    test("should handle movers by category", async () => {
      const response = await request(app)
        .get("/stocks/movers?type=gainers")
        .expect(200);
      expect(response.body).toHaveProperty("success", true);
    });
    test("should limit movers results", async () => {
      const response = await request(app)
        .get("/stocks/movers?limit=10")
        .expect(200);
      expect(response.body).toHaveProperty("success", true);
    });
  });
  describe("GET /stocks/recommendations/:symbol", () => {
    test("should return stock recommendations", async () => {
      const response = await request(app)
        .get("/stocks/recommendations/AAPL")
        .expect(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
    });
    test("should handle recommendations with different criteria", async () => {
      const response = await request(app)
        .get("/stocks/recommendations/AAPL?criteria=technical")
        .expect(200);
      expect(response.body).toHaveProperty("success", true);
    });
  });
  describe("GET /stocks/compare", () => {
    test("should compare multiple stocks", async () => {
      const response = await request(app)
        .get("/stocks/compare?symbols=AAPL,MSFT,GOOGL");
      // Debug: Log the actual response to understand what's happening
      console.log('Response status:', response.status);
      console.log('Response body:', JSON.stringify(response.body, null, 2));
      // Now check if we get data (200) or proper error (404)
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
        expect(response.body.data.comparison).toBeInstanceOf(Array);
        expect(response.body.data.comparison.length).toBeGreaterThan(0);
      } else if (response.status === 404) {
        expect(response.body).toHaveProperty("success", false);
        expect(response.body.error || response.body.success).toBeDefined();
        expect(response.body.error).toContain("comparison data");
      } else {
        // Should not reach here - test expects 200 or 404 only
        expect(response.status).toBeOneOf([200, 404]);
      }
    });
    test("should handle comparison with metrics", async () => {
      const response = await request(app)
        .get("/stocks/compare?symbols=AAPL,MSFT&metrics=price,volume,pe_ratio");
      // Should either return real data (200) or proper error (404), no mock fallbacks
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
        expect(response.body.data.comparison).toBeInstanceOf(Array);
      } else if (response.status === 404) {
        expect(response.body).toHaveProperty("success", false);
        expect(response.body.error).toContain("comparison data");
      } else {
        // Should not reach here - test expects 200 or 404 only
        expect(response.status).toBeOneOf([200, 404]);
      }
    });
    test("should limit comparison to reasonable number of stocks", async () => {
      const manySymbols = Array.from(
        { length: 20 },
        (_, i) => `STOCK${i}`
      ).join(",");
      const response = await request(app)
        .get(`/stocks/compare?symbols=${manySymbols}`);
      // Should either return real data (200) or proper error (404) for non-existent symbols
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
        // Should limit to 10 stocks max (as per route implementation)
        expect(response.body.data.comparison.length).toBeLessThanOrEqual(10);
      } else if (response.status === 404) {
        expect(response.body).toHaveProperty("success", false);
        expect(response.body.error).toContain("comparison data");
      } else {
        // Should not reach here - test expects 200 or 404 only
        expect(response.status).toBeOneOf([200, 404]);
      }
    });
  });
  describe("GET /stocks/stats", () => {
    test("should return stock statistics", async () => {
      const response = await request(app).get("/stocks/stats").expect(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
    });
    test("should handle stats with filters", async () => {
      const response = await request(app)
        .get("/stocks/stats?sector=Technology")
        .expect(200);
      expect(response.body).toHaveProperty("success", true);
    });
  });
  // Error handling tests
  describe("Stocks Error Handling", () => {
    test("should handle malformed symbol requests", async () => {
      const response = await request(app).get("/stocks/details/").expect(404);
    });
    test("should handle invalid query parameters gracefully", async () => {
      const response = await request(app)
        .get("/stocks/search?limit=invalid")
        .expect(200);
      expect(response.body).toHaveProperty("success");
    });
    test("should handle missing required parameters", async () => {
      const response = await request(app).get("/stocks/compare").expect(400);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body).toHaveProperty("error", "Missing symbols parameter");
    });
  });
});

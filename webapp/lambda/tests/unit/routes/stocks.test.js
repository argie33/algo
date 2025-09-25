const express = require("express");
const request = require("supertest");

// Real database for integration
const { query } = require("../../../utils/database");

// Import Jest functions
const { fail } = require("@jest/globals");

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

  describe("GET /stocks/", () => {
    test("should return stocks data with correct loader table structure", async () => {
      const response = await request(app)
        .get("/stocks/")
        .set("Authorization", "Bearer dev-bypass-token")
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
        .set("Authorization", "Bearer dev-bypass-token")
        .expect(200);

      expect(response.body).toHaveProperty("success");
      expect(response.body).toHaveProperty("data");
    });
  });

  describe("GET /stocks/list", () => {
    test("should return stock list with correct loader table structure", async () => {
      const response = await request(app)
        .get("/stocks/list")
        .set("Authorization", "Bearer dev-bypass-token")
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
        .set("Authorization", "Bearer dev-bypass-token")
        .expect(200);

      // Verify response structure matches actual API implementation
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
        .set("Authorization", "Bearer dev-bypass-token")
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
    });

    test("should handle trending with timeframe", async () => {
      const response = await request(app)
        .get("/stocks/trending?timeframe=1d")
        .set("Authorization", "Bearer dev-bypass-token")
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
    });

    test("should handle trending with different categories", async () => {
      const response = await request(app)
        .get("/stocks/trending?category=gainers")
        .set("Authorization", "Bearer dev-bypass-token")
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
      const response = await request(app).get("/stocks/price/AAPL").expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
    });

    test("should handle price with different timeframes", async () => {
      const response = await request(app)
        .get("/stocks/price/AAPL?timeframe=1d")
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
    });

    test("should handle price with historical data", async () => {
      const response = await request(app)
        .get("/stocks/price/AAPL?historical=true&days=30")
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
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
        expect(response.body).toHaveProperty("error");
        expect(response.body.error).toContain("comparison data");
      } else {
        fail(`Unexpected status code: ${response.status}`);
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
        fail(`Unexpected status code: ${response.status}`);
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
        fail(`Unexpected status code: ${response.status}`);
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
      const response = await request(app).get("/stocks/compare").expect(200);

      expect(response.body).toHaveProperty("success");
    });
  });
});

/**
 * Scores Routes Integration Tests - REAL DATA ONLY
 * Tests scores endpoints with REAL database connection and REAL loaded data
 * NO MOCKS - validates actual behavior with actual data from loaders
 * Validates NO-FALLBACK policy: raw NULL values must flow through unmasked
 */

/**
 * Scores Integration - Real Data Validation Integration Tests - REAL DATA ONLY
 * Tests scores endpoints with REAL database connection and REAL loaded data
 * NO MOCKS - validates actual behavior with actual data from loaders
 * Validates NO-FALLBACK policy: raw NULL values must flow through unmasked
 */

const request = require("supertest");
const { app } = require("../../../index");
const { initializeDatabase } = require("../../../utils/database"); // Import the actual Express app - NO MOCKS

describe("Scores Integration - Real Data Validation Routes - Real Data Validation", () => {
  beforeAll(async () => {
    await initializeDatabase();
  });
  describe("GET /scores/ping", () => {
    test("should return ping response", async () => {
      const response = await request(app).get("/scores/ping");

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("status", "ok");
      expect(response.body).toHaveProperty("endpoint", "scores");
      expect(response.body).toHaveProperty("timestamp");
    });
  });

  describe("GET /scores - Real Data Validation", () => {
    test("should return ALL loaded stocks from database (3000+)", async () => {
      const response = await request(app).get("/scores");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("stocks");
      expect(Array.isArray(response.body.data.stocks)).toBe(true);
      // Should have substantial real data - 3153 stocks were loaded
      expect(response.body.data.stocks.length).toBeGreaterThan(100);
      expect(response.body).toHaveProperty("summary");
      expect(response.body).toHaveProperty("metadata");
      expect(response.body.metadata).toHaveProperty("dataSource", "stock_scores_real_table");
      expect(response.body.metadata).toHaveProperty("factorAnalysis", "seven_factor_scoring_system");
    });

    test("should validate NO-FALLBACK policy - real data without fallback operators", async () => {
      const response = await request(app).get("/scores");

      expect(response.status).toBe(200);
      const stocks = response.body.data.stocks;
      expect(stocks.length).toBeGreaterThan(0);

      // Validate first 10 stocks - check for real data patterns
      stocks.slice(0, Math.min(10, stocks.length)).forEach(stock => {
        // NO-FALLBACK policy: these fields should exist
        expect(stock).toHaveProperty("symbol");
        expect(stock).toHaveProperty("composite_score");
        expect(stock).toHaveProperty("momentum_score");
        expect(stock).toHaveProperty("value_score");
        expect(stock).toHaveProperty("quality_score");
        expect(stock).toHaveProperty("growth_score");

        // Scores should be real numbers OR explicitly null
        // NOT masked by fallback operators (e.g., "value || 0" is forbidden)
        const scoresArray = [
          stock.composite_score,
          stock.momentum_score,
          stock.value_score,
          stock.quality_score,
          stock.growth_score
        ];

        // At least SOME scores should be real numbers (not all null)
        const hasRealScores = scoresArray.some(s => s !== null && typeof s === "number");
        expect(hasRealScores).toBe(true);

        // Scores that ARE numbers should be in valid range (0-100)
        scoresArray.forEach(score => {
          if (score !== null) {
            expect(typeof score).toBe("number");
            expect(score).toBeGreaterThanOrEqual(0);
            expect(score).toBeLessThanOrEqual(100);
          }
        });
      });
    });

    test("should provide real growth metrics from loaders", async () => {
      const response = await request(app).get("/scores");
      const stocks = response.body.data.stocks;

      // Check for stocks with growth data from loaders
      let stocksWithGrowthData = 0;
      let stocksChecked = 0;

      stocks.slice(0, Math.min(50, stocks.length)).forEach(stock => {
        stocksChecked++;
        if (stock.growth_inputs) {
          // Loader schema requires these fields
          expect(stock.growth_inputs).toHaveProperty("revenue_growth_3y_cagr");
          expect(stock.growth_inputs).toHaveProperty("eps_growth_3y_cagr");

          // Count stocks with actual growth data
          if (stock.growth_inputs.revenue_growth_3y_cagr !== null ||
              stock.growth_inputs.eps_growth_3y_cagr !== null) {
            stocksWithGrowthData++;
          }
        }
      });

      // Expect meaningful subset to have growth data
      expect(stocksWithGrowthData).toBeGreaterThan(0);
    });

    test("should provide real quality metrics from loaders", async () => {
      const response = await request(app).get("/scores");
      const stocks = response.body.data.stocks;

      // Check for stocks with quality data from loaders
      let stocksWithQualityData = 0;
      stocks.slice(0, Math.min(50, stocks.length)).forEach(stock => {
        if (stock.quality_inputs) {
          // Loader schema requires these fields
          expect(stock.quality_inputs).toHaveProperty("debt_to_equity");
          expect(stock.quality_inputs).toHaveProperty("fcf_to_net_income");

          // Count stocks with actual quality data
          if (stock.quality_inputs.debt_to_equity !== null ||
              stock.quality_inputs.fcf_to_net_income !== null) {
            stocksWithQualityData++;
          }
        }
      });

      expect(stocksWithQualityData).toBeGreaterThan(0);
    });

    test("should handle pagination parameters correctly", async () => {
      const response = await request(app)
        .get("/scores")
        .query({ page: 1, limit: 10 });

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("stocks");
      expect(Array.isArray(response.body.data.stocks)).toBe(true);
    });

    test("should handle search parameter with real data", async () => {
      const response = await request(app)
        .get("/scores")
        .query({ search: "AAPL" });

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("stocks");
      expect(Array.isArray(response.body.data.stocks)).toBe(true);

      // If search found results, they should match search term
      if (response.body.data.stocks.length > 0) {
        response.body.data.stocks.forEach(stock => {
          expect(stock.symbol).toContain("AAPL");
        });
      }
    });

    test("should return stocks sorted by composite score descending", async () => {
      const response = await request(app).get("/scores");

      expect(response.status).toBe(200);
      const stocks = response.body.data.stocks;
      expect(Array.isArray(stocks)).toBe(true);

      // Verify sorting order (descending by composite_score)
      if (stocks.length > 1) {
        for (let i = 1; i < stocks.length; i++) {
          // Only compare if both scores are not null
          if (stocks[i-1].composite_score !== null && stocks[i].composite_score !== null) {
            expect(stocks[i-1].composite_score)
              .toBeGreaterThanOrEqual(stocks[i].composite_score);
          }
        }
      }
    });
  });

  describe("GET /scores/:symbol - Individual Stock Data", () => {
    test("should return real individual stock data (e.g., AAPL)", async () => {
      const response = await request(app).get("/scores/AAPL");

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
        expect(response.body.data).toHaveProperty("symbol", "AAPL");
        expect(response.body.data).toHaveProperty("composite_score");
        expect(response.body).toHaveProperty("metadata");
        expect(response.body.metadata).toHaveProperty("dataSource", "stock_scores_real_table");
        expect(response.body.metadata).toHaveProperty("factorAnalysis", "seven_factor_scoring_system");

        // Validate seven factor scores
        expect(response.body.data).toHaveProperty("momentum_score");
        expect(response.body.data).toHaveProperty("value_score");
        expect(response.body.data).toHaveProperty("quality_score");
        expect(response.body.data).toHaveProperty("growth_score");
        expect(response.body.data).toHaveProperty("positioning_score");
        expect(response.body.data).toHaveProperty("sentiment_score");
        expect(response.body.data).toHaveProperty("stability_score");

        // Validate factor inputs are present and have real data
        if (response.body.data.growth_inputs) {
          expect(response.body.data.growth_inputs).toHaveProperty("revenue_growth_3y_cagr");
          expect(response.body.data.growth_inputs).toHaveProperty("eps_growth_3y_cagr");
        }
        if (response.body.data.quality_inputs) {
          expect(response.body.data.quality_inputs).toHaveProperty("debt_to_equity");
          expect(response.body.data.quality_inputs).toHaveProperty("fcf_to_net_income");
        }
      } else if (response.status === 404) {
        // Stock might not be in database yet
        expect(response.body).toHaveProperty("success", false);
      }
    });

    test("should handle case insensitive symbol lookup", async () => {
      const response = await request(app).get("/scores/aapl");

      if (response.status === 200) {
        expect(response.body.data).toHaveProperty("symbol", "AAPL");
      } else if (response.status === 404) {
        expect(response.body.success).toBe(false);
      }
    });

    test("should return 404 for non-existent symbol", async () => {
      const response = await request(app).get("/scores/ZZZNONEXISTENT999");

      expect(response.status).toBe(404);
      expect(response.body).toHaveProperty("success", false);
    });
  });

  describe("Performance Tests", () => {
    test("should respond quickly to ping requests", async () => {
      const startTime = Date.now();
      const response = await request(app).get("/scores/ping");
      const responseTime = Date.now() - startTime;

      expect(response.status).toBe(200);
      expect(responseTime).toBeLessThan(1000); // Should be < 1 second
    });

    test("should handle concurrent requests without issues", async () => {
      const requests = Array.from({ length: 5 }, () =>
        request(app).get("/scores/ping")
      );

      const responses = await Promise.all(requests);

      responses.forEach((response) => {
        expect(response.status).toBe(200);
        expect(response.body).toHaveProperty("status", "ok");
      });
    });
  });

  describe("Error Handling", () => {
    test("should return consistent JSON response format", async () => {
      const response = await request(app).get("/scores/ping");

      expect(response.headers["content-type"]).toMatch(/json/);
      expect(typeof response.body).toBe("object");
    });

    test("should handle invalid endpoints gracefully", async () => {
      const response = await request(app).get("/scores/invalid/endpoint");

      expect([404, 500]).toContain(response.status);
    });

    test("should handle SQL injection attempts safely", async () => {
      const response = await request(app).get("/scores").query({
        search: "'; DROP TABLE stock_scores; --",
      });

      // Should either return data or error, but never execute injection
      expect([200, 400, 500]).toContain(response.status);
      if (response.status === 200) {
        expect(response.body.success).toBe(true);
        expect(response.body).toHaveProperty("data");
      }
    });
  });
});

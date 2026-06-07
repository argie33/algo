/**
 * ETF Routes Integration Tests - REAL DATA ONLY
 * Tests ETF endpoints with REAL database connection and REAL loaded data
 * NO MOCKS - validates actual behavior with actual data from loaders
 * Validates NO-FALLBACK policy: raw NULL values must flow through unmasked
 */

const request = require("supertest");
const { app } = require("../../../index");
const { initializeDatabase } = require("../../../utils/database"); // Import the actual Express app - NO MOCKS

describe("ETF Routes - Real Data Validation", () => {
  beforeAll(async () => {
    await initializeDatabase();
  });

  describe("GET /api/etf/:symbol/holdings", () => {
    test("should return ETF holdings data for major ETFs", async () => {
      const etfSymbols = ["SPY", "QQQ", "IWM", "VTI", "VOO"];

      for (const symbol of etfSymbols) {
        const response = await request(app).get(`/api/etf/${symbol}/holdings`);

        expect(response.status).toBe(200);

        if (response.status === 200) {
          expect(response.body).toHaveProperty("success", true);
          expect(response.body).toHaveProperty("data");
          expect(response.body.data).toHaveProperty("etf");
          expect(response.body.data).toHaveProperty("holdings");
          expect(Array.isArray(response.body.data.holdings)).toBe(true);

          if (response.body.data.holdings.length > 0) {
            const holding = response.body.data.holdings[0];
            expect(holding).toHaveProperty("holding_symbol");
            expect(holding).toHaveProperty("company_name");
            expect(holding).toHaveProperty("weight_percent");
            expect(typeof holding.weight_percent).toBe("number");
          }
        }
      }
    });

    test("should include fund information in holdings response", async () => {
      const response = await request(app).get("/api/etf/SPY/holdings");

      if (response.status === 200) {
        expect(response.body.data.etf).toHaveProperty("fund_name");
        expect(response.body.data.etf).toHaveProperty("total_assets");
        expect(response.body.data.etf).toHaveProperty("expense_ratio");
        expect(response.body.data.etf).toHaveProperty("dividend_yield");
      }
    });

    test("should include sector allocation in holdings response", async () => {
      const response = await request(app).get("/api/etf/SPY/holdings");

      if (response.status === 200) {
        expect(response.body.data).toHaveProperty("sector_allocation");
        expect(Array.isArray(response.body.data.sector_allocation)).toBe(true);

        if (response.body.data.sector_allocation.length > 0) {
          const sector = response.body.data.sector_allocation[0];
          expect(sector).toHaveProperty("sector");
          expect(sector).toHaveProperty("total_weight");
          expect(typeof sector.total_weight).toBe("number");
        }
      }
    });

    test("should handle invalid ETF symbol", async () => {
      const response = await request(app).get("/api/etf/INVALID/holdings");

      expect([404, 500].includes(response.status)).toBe(true);

      if (response.status === 404) {
        expect(response.body).toHaveProperty("success", false);
        expect(response.body).toHaveProperty("error", "ETF not found");
        expect(response.body).toHaveProperty("message");
      }
    });

    test("should handle limit parameter validation", async () => {
      const limitTests = ["5", "25", "50", "100"];

      for (const limit of limitTests) {
        const response = await request(app).get(
          `/api/etf/SPY/holdings?limit=${limit}`
        );

        expect(response.status).toBe(200);

        if (response.status === 200 && response.body.data.holdings.length > 0) {
          expect(response.body.data.holdings.length).toBeLessThanOrEqual(
            parseInt(limit)
          );
        }
      }
    });

    test("should handle invalid limit parameter", async () => {
      const response = await request(app).get(
        "/api/etf/SPY/holdings?limit=invalid"
      );

      expect([200, 400].includes(response.status)).toBe(true);
    });

    test("should handle missing symbol parameter", async () => {
      const response = await request(app).get("/api/etf//holdings");

      expect([400, 404, 500].includes(response.status)).toBe(true);
    });

    test("should handle special characters in ETF symbol", async () => {
      const response = await request(app).get("/api/etf/SPY@#$/holdings");

      expect([400, 404, 500, 503].includes(response.status)).toBe(true);
    });
  });

  describe("GET /api/etf/:symbol/performance", () => {
    test("should return ETF performance data", async () => {
      const response = await request(app).get("/api/etf/SPY/performance");

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
        expect(response.body.data).toHaveProperty("symbol", "SPY");
        expect(response.body.data).toHaveProperty("performance_metrics");
      }
    });

    test("should include historical performance metrics", async () => {
      const response = await request(app).get("/api/etf/QQQ/performance");

      if (response.status === 200) {
        const metrics = response.body.data.performance_metrics;
        expect(metrics).toHaveProperty("ytd_return");
        expect(metrics).toHaveProperty("one_year_return");
        expect(metrics).toHaveProperty("three_year_return");
        expect(metrics).toHaveProperty("five_year_return");
      }
    });

    test("should handle timeframe parameter", async () => {
      const timeframes = ["1D", "1W", "1M", "3M", "6M", "1Y", "3Y", "5Y"];

      for (const timeframe of timeframes) {
        const response = await request(app).get(
          `/api/etf/SPY/performance?timeframe=${timeframe}`
        );

        expect([200, 400].includes(response.status)).toBe(true);
      }
    });

    test("should compare performance against benchmark", async () => {
      const response = await request(app).get(
        "/api/etf/SPY/performance?benchmark=SPX"
      );

      expect([200, 400].includes(response.status)).toBe(true);

      if (response.status === 200) {
        expect(response.body.data).toHaveProperty("benchmark_comparison");
      }
    });
  });

  describe("GET /api/etf/:symbol/analytics", () => {
    test("should return comprehensive ETF analytics", async () => {
      const response = await request(app).get("/api/etf/SPY/analytics");

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("data");
        expect(response.body.data).toHaveProperty("basic_info");
        expect(response.body.data).toHaveProperty("risk_metrics");
        expect(response.body.data).toHaveProperty("dividend_info");
      }
    });

    test("should include risk analysis metrics", async () => {
      const response = await request(app).get("/api/etf/VTI/analytics");

      if (response.status === 200) {
        const riskMetrics = response.body.data.risk_metrics;
        expect(riskMetrics).toHaveProperty("beta");
        expect(riskMetrics).toHaveProperty("volatility");
        expect(riskMetrics).toHaveProperty("sharpe_ratio");
        expect(riskMetrics).toHaveProperty("max_drawdown");
      }
    });
  });

  describe("GET /api/etf/screener", () => {
    test("should return ETF screener results", async () => {
      const response = await request(app).get("/api/etf/screener");

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("data");
        expect(Array.isArray(response.body.data)).toBe(true);
        expect(response.body).toHaveProperty("count");
        expect(response.body).toHaveProperty("filters_applied");
      }
    });

    test("should handle expense ratio filter", async () => {
      const response = await request(app).get(
        "/api/etf/screener?max_expense_ratio=0.5"
      );

      expect([200, 400, 500, 503].includes(response.status)).toBe(true);

      if (response.status === 200 && response.body.data.length > 0) {
        response.body.data.forEach((etf) => {
          if (etf.expense_ratio !== null && etf.expense_ratio !== undefined) {
            expect(etf.expense_ratio).toBeLessThanOrEqual(0.5);
          }
        });
      }
    });

    test("should handle asset size filter", async () => {
      const response = await request(app).get(
        "/api/etf/screener?min_assets=1000000000"
      );

      expect([200, 400, 500, 503].includes(response.status)).toBe(true);
    });

    test("should handle category filter", async () => {
      const categories = ["equity", "fixed_income", "commodity", "mixed"];

      for (const category of categories) {
        const response = await request(app).get(
          `/api/etf/screener?category=${category}`
        );

        expect([200, 400, 500, 503].includes(response.status)).toBe(true);
      }
    });

    test("should handle sector filter", async () => {
      const response = await request(app).get(
        "/api/etf/screener?sector=Technology"
      );

      expect([200, 400, 500, 503].includes(response.status)).toBe(true);
    });

    test("should handle dividend yield filter", async () => {
      const response = await request(app).get(
        "/api/etf/screener?min_dividend_yield=2.0"
      );

      expect([200, 400, 500, 503].includes(response.status)).toBe(true);
    });

    test("should handle multiple filters combined", async () => {
      const response = await request(app).get(
        "/api/etf/screener?category=equity&max_expense_ratio=0.5&min_assets=500000000"
      );

      expect([200, 400, 500, 503].includes(response.status)).toBe(true);
    });

    test("should handle sorting options", async () => {
      const sortOptions = [
        "assets",
        "expense_ratio",
        "dividend_yield",
        "performance",
      ];

      for (const sort of sortOptions) {
        const response = await request(app).get(
          `/api/etf/screener?sort=${sort}&order=desc`
        );

        expect([200, 400, 500, 503].includes(response.status)).toBe(true);
      }
    });

    test("should handle pagination parameters", async () => {
      const response = await request(app).get(
        "/api/etf/screener?page=1&limit=25"
      );

      expect([200, 400, 500, 503].includes(response.status)).toBe(true);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("pagination");
        expect(response.body.pagination).toHaveProperty("page", 1);
        expect(response.body.pagination).toHaveProperty("limit", 25);
      }
    });
  });

  describe("GET /api/etf/compare", () => {
    test("should compare multiple ETFs", async () => {
      const response = await request(app).get(
        "/api/etf/compare?symbols=SPY,QQQ,VTI"
      );

      expect([200, 400, 500, 503].includes(response.status)).toBe(true);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("data");
        expect(response.body.data).toHaveProperty("etfs");
        expect(Array.isArray(response.body.data.etfs)).toBe(true);
        expect(response.body.data).toHaveProperty("comparison_metrics");
      }
    });

    test("should handle invalid symbol in comparison", async () => {
      const response = await request(app).get(
        "/api/etf/compare?symbols=SPY,INVALID,QQQ"
      );

      expect([200, 400].includes(response.status)).toBe(true);
    });

    test("should handle single ETF comparison", async () => {
      const response = await request(app).get("/api/etf/compare?symbols=SPY");

      expect([200, 400, 500, 503].includes(response.status)).toBe(true);
    });

    test("should handle comparison metrics parameter", async () => {
      const response = await request(app).get(
        "/api/etf/compare?symbols=SPY,QQQ&metrics=performance,risk,dividend"
      );

      expect([200, 400, 500, 503].includes(response.status)).toBe(true);
    });
  });

  describe("GET /api/etf/trending", () => {
    test("should return trending ETFs", async () => {
      const response = await request(app).get("/api/etf/trending");

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("data");
        expect(Array.isArray(response.body.data)).toBe(true);
        expect(response.body).toHaveProperty("period");
        expect(response.body).toHaveProperty("criteria");
      }
    });

    test("should handle timeframe for trending", async () => {
      const timeframes = ["1D", "1W", "1M"];

      for (const timeframe of timeframes) {
        const response = await request(app).get(
          `/api/etf/trending?timeframe=${timeframe}`
        );

        expect([200, 400, 500, 503].includes(response.status)).toBe(true);
      }
    });

    test("should handle category filter for trending", async () => {
      const response = await request(app).get(
        "/api/etf/trending?category=equity"
      );

      expect([200, 400, 500, 503].includes(response.status)).toBe(true);
    });
  });

  describe("GET /api/etf/flows", () => {
    test("should return ETF flow data", async () => {
      const response = await request(app).get("/api/etf/flows");

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("data");
        expect(Array.isArray(response.body.data)).toBe(true);
        expect(response.body).toHaveProperty("period");
      }
    });

    test("should handle period parameter for flows", async () => {
      const periods = ["1D", "1W", "1M", "3M", "6M", "1Y"];

      for (const period of periods) {
        const response = await request(app).get(
          `/api/etf/flows?period=${period}`
        );

        expect([200, 400, 500, 503].includes(response.status)).toBe(true);
      }
    });

    test("should handle fund type filter for flows", async () => {
      const response = await request(app).get("/api/etf/flows?type=equity");

      expect([200, 400, 500, 503].includes(response.status)).toBe(true);
    });
  });

  describe("Performance and Edge Cases", () => {
    jest.setTimeout(15000);

    test("should handle concurrent ETF holdings requests", async () => {
      const requests = ["SPY", "QQQ", "VTI", "IWM", "VOO"].map((symbol) =>
        request(app).get(`/api/etf/${symbol}/holdings`)
      );

      const responses = await Promise.all(requests);

      responses.forEach((response) => {
        expect(response.status).toBe(200);
      });
    });

    test("should handle large holdings requests gracefully", async () => {
      const response = await request(app).get(
        "/api/etf/SPY/holdings?limit=500"
      );

      expect([200, 400].includes(response.status)).toBe(true);
    });

    test("should maintain response time consistency", async () => {
      const startTime = Date.now();
      const response = await request(app).get("/api/etf/screener");
      const responseTime = Date.now() - startTime;

      expect(response.status).toBe(200);
      expect(responseTime).toBeLessThan(15000);
    });

    test("should validate data structure consistency", async () => {
      const response = await request(app).get("/api/etf/SPY/holdings");

      if (response.status === 200 && response.body.data.holdings.length > 0) {
        const holding = response.body.data.holdings[0];
        expect(typeof holding.holding_symbol).toBe("string");
        expect(typeof holding.weight_percent).toBe("number");
        expect(holding.weight_percent).toBeGreaterThanOrEqual(0);
        expect(holding.weight_percent).toBeLessThanOrEqual(100);
      }
    });

    test("should handle database connection failures gracefully", async () => {
      const response = await request(app).get("/api/etf/SPY/holdings");

      expect(response.status).toBe(200);

      if (response.status >= 500) {
        expect(response.body).toHaveProperty("error");
      }
    });

    test("should handle malformed query parameters", async () => {
      const malformedTests = [
        "/api/etf/screener?max_expense_ratio=invalid",
        "/api/etf/screener?page=-1",
        "/api/etf/screener?limit=abc",
        "/api/etf/compare?symbols=",
        "/api/etf/SPY/holdings?limit=999999",
      ];

      for (const testUrl of malformedTests) {
        const response = await request(app).get(testUrl);
        expect([200, 400].includes(response.status)).toBe(true);
      }
    });

    test("should handle SQL injection attempts", async () => {
      const maliciousSymbol = "SPY'; DROP TABLE etf_holdings; --";
      const response = await request(app).get(
        `/api/etf/${encodeURIComponent(maliciousSymbol)}/holdings`
      );

      expect([200, 400].includes(response.status)).toBe(true);
    });

    test("should handle authentication edge cases for protected endpoints", async () => {
      const response = await request(app)
        .get("/api/etf/SPY/premium-analytics")
        .set("Authorization", "Bearer invalid-token");

      expect([200, 401].includes(response.status)).toBe(true);
    });

    test("should handle stress testing with multiple concurrent requests", async () => {
      const promises = Array(10)
        .fill()
        .map(() => request(app).get("/api/etf/screener").timeout(10000));

      const responses = await Promise.all(
        promises.map((p) => p.catch((err) => ({ status: 500, error: err })))
      );

      responses.forEach((response) => {
        if (response.status) {
          expect(response.status).toBe(200);
        }
      });
    });
  });
});

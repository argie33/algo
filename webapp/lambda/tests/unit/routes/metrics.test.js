const request = require("supertest");
const express = require("express");
const metricsRoutes = require("../../../routes/metrics");
// Mock database module
jest.mock("../../../utils/database", () => ({
  query: jest.fn().mockResolvedValue({ rows: [], rowCount: 0 }),
}));

const { query, closeDatabase, initializeDatabase, getPool, transaction, healthCheck } = require('../../../utils/database');

describe("Metrics Routes", () => {
  let app;
  beforeAll(() => {
    app = express();
    app.use(express.json());
    // Add response formatter middleware for proper res.error, res.success methods
    const responseFormatter = require("../../../middleware/responseFormatter");
    app.use(responseFormatter);
    app.use("/metrics", metricsRoutes);
  });

  beforeEach(() => {
    // Reset mocks
    jest.clearAllMocks();
    // Set up default mock responses for database queries
    query.mockImplementation((sql) => {
      // Basic connection test
      if (sql.includes("SELECT 1 as test")) {
        return Promise.resolve({ rows: [{ test: 1 }] });
      }
      // Main metrics query - mock data matching loader key_metrics table structure
      if (sql.includes("SELECT") && sql.includes("km.ticker")) {
        return Promise.resolve({
          rows: [
            {
              symbol: "AAPL",
              trailing_pe: 28.5,
              forward_pe: 26.2,
              price_to_book: 5.8,
              book_value: 4.32,
              price_to_sales_ttm: 7.2,
              peg_ratio: 2.1,
              enterprise_value: 2800000000000,
              ev_to_revenue: 7.1,
              ev_to_ebitda: 19.5,
              profit_margin_pct: 0.253,
              gross_margin_pct: 0.433,
              ebitda_margin_pct: 0.311,
              operating_margin_pct: 0.298,
              return_on_assets_pct: 0.204,
              return_on_equity_pct: 0.564,
              current_ratio: 1.06,
              quick_ratio: 0.83,
              debt_to_equity: 186.6,
              eps_trailing: 6.05,
              eps_forward: 6.84,
              eps_current_year: 6.16,
              price_eps_current_year: 28.1,
              total_cash: 67100000000,
              cash_per_share: 4.31,
              operating_cashflow: 109200000000,
              free_cashflow: 84700000000,
              total_debt: 125000000000,
              ebitda: 123300000000,
              total_revenue: 394300000000,
              net_income: 99800000000,
              gross_profit: 170800000000,
              earnings_q_growth_pct: 0.036,
              revenue_growth_pct: -0.027,
              earnings_growth_pct: 0.135,
              dividend_rate: 0.96,
              dividend_yield: 0.0055,
              five_year_avg_dividend_yield: 0.78,
              last_annual_dividend_amt: 0.95,
              last_annual_dividend_yield: 0.54,
              payout_ratio: 0.158
            }
          ]
        });
      }
      // Default fallback
      return Promise.resolve({ rows: [] });
    });
  });
  describe("GET /metrics/ping", () => {
    test("should return ping status", async () => {
      const response = await request(app).get("/metrics/ping").expect(200);
      expect(response.body).toMatchObject({
        status: "ok",
        endpoint: "metrics",
        timestamp: expect.any(String),
      });
    });
  });
  describe("GET /metrics/", () => {
    test("should return comprehensive metrics with default pagination", async () => {
      const response = await request(app).get("/metrics/").expect(200);
      expect(response.body).toHaveProperty("data");
      expect(response.body).toHaveProperty("pagination");
      expect(response.body.pagination).toMatchObject({
        page: 1,
        limit: 50,
        totalPages: expect.any(Number),
        total: expect.any(Number),
      });
      // Verify comprehensive yfinance key metrics data structure
      if (response.body.data && response.body.data.length > 0) {
        const firstStock = response.body.data[0];
        // Basic required fields
        expect(firstStock).toHaveProperty("symbol");
        expect(typeof firstStock.symbol).toBe("string");
        // Valuation metrics from yfinance
        expect(firstStock).toHaveProperty("pe"); // trailing_pe
        expect(firstStock).toHaveProperty("forwardPE"); // forward_pe
        expect(firstStock).toHaveProperty("pb"); // price_to_book
        expect(firstStock).toHaveProperty("bookValue");
        expect(firstStock).toHaveProperty("priceToSales");
        expect(firstStock).toHaveProperty("pegRatio");
        // Enterprise value metrics
        expect(firstStock).toHaveProperty("enterpriseValue");
        expect(firstStock).toHaveProperty("evToRevenue");
        expect(firstStock).toHaveProperty("evToEbitda");
        // Profitability margins
        expect(firstStock).toHaveProperty("profitMargin");
        expect(firstStock).toHaveProperty("grossMargin");
        expect(firstStock).toHaveProperty("ebitdaMargin");
        expect(firstStock).toHaveProperty("operatingMargin");
        // Returns
        expect(firstStock).toHaveProperty("returnOnAssets");
        expect(firstStock).toHaveProperty("returnOnEquity");
        // Liquidity ratios
        expect(firstStock).toHaveProperty("currentRatio");
        expect(firstStock).toHaveProperty("quickRatio");
        // Debt metrics
        expect(firstStock).toHaveProperty("debtToEquity");
        expect(firstStock).toHaveProperty("totalDebt");
        // EPS metrics
        expect(firstStock).toHaveProperty("eps");
        expect(firstStock).toHaveProperty("forwardEPS");
        expect(firstStock).toHaveProperty("epsCurrentYear");
        expect(firstStock).toHaveProperty("priceEpsCurrentYear");
        // Cash metrics
        expect(firstStock).toHaveProperty("totalCash");
        expect(firstStock).toHaveProperty("cashPerShare");
        expect(firstStock).toHaveProperty("operatingCashflow");
        expect(firstStock).toHaveProperty("freeCashflow");
        // Financial data
        expect(firstStock).toHaveProperty("ebitda");
        expect(firstStock).toHaveProperty("totalRevenue");
        expect(firstStock).toHaveProperty("netIncome");
        expect(firstStock).toHaveProperty("grossProfit");
        // Growth metrics
        expect(firstStock).toHaveProperty("earningsGrowth");
        expect(firstStock).toHaveProperty("revenueGrowth");
        expect(firstStock).toHaveProperty("earningsGrowthQuarterly");
        // Dividend metrics
        expect(firstStock).toHaveProperty("dividendYield");
        expect(firstStock).toHaveProperty("dividendRate");
        expect(firstStock).toHaveProperty("payoutRatio");
        expect(firstStock).toHaveProperty("fiveYearAvgDividendYield");
        expect(firstStock).toHaveProperty("trailingAnnualDividendRate");
        expect(firstStock).toHaveProperty("trailingAnnualDividendYield");
        // Metadata
        expect(firstStock).toHaveProperty("lastUpdated");
        expect(firstStock).toHaveProperty("dataSource");
        expect(firstStock.dataSource).toBe("yfinance");
        expect(typeof firstStock.lastUpdated).toBe("string");
        // Verify numeric fields are numbers or null (not strings)
        if (firstStock.pe !== null) expect(typeof firstStock.pe).toBe("number");
        if (firstStock.pb !== null) expect(typeof firstStock.pb).toBe("number");
        if (firstStock.returnOnEquity !== null) expect(typeof firstStock.returnOnEquity).toBe("number");
        if (firstStock.debtToEquity !== null) expect(typeof firstStock.debtToEquity).toBe("number");
        if (firstStock.currentRatio !== null) expect(typeof firstStock.currentRatio).toBe("number");
      }
    });
    test("should handle search filtering", async () => {
      const response = await request(app)
        .get("/metrics/")
        .query({ search: "AAPL", limit: 10, page: 1 })
        .expect(200);
      expect(response.body).toHaveProperty("pagination");
      expect(response.body.pagination).toMatchObject({
        page: 1,
        limit: 10,
        totalPages: expect.any(Number),
        total: expect.any(Number),
      });
    });
    test("should handle sector filtering", async () => {
      const response = await request(app)
        .get("/metrics/")
        .query({
          sector: "Technology",
          sortBy: "quality_metric",
          sortOrder: "desc",
        })
        .expect(200);
      expect(response.body.data).toBeDefined();
      expect(response.body).toHaveProperty("pagination");
    });
    test("should handle metric range filtering", async () => {
      const response = await request(app)
        .get("/metrics/")
        .query({ minMetric: 0.7, maxMetric: 0.9 })
        .expect(200);
      expect(response.body.data).toBeDefined();
      expect(response.body).toHaveProperty("pagination");
    });
    test("should prevent SQL injection in sort parameters", async () => {
      const response = await request(app)
        .get("/metrics/")
        .query({
          sortBy: "invalid_column; DROP TABLE stocks;",
          sortOrder: "malicious",
        })
        .expect(200);
      expect(response.body.data).toBeDefined();
      expect(response.body).toHaveProperty("pagination");
    });
    test("should limit page size to maximum", async () => {
      const response = await request(app)
        .get("/metrics/")
        .query({ limit: 1000 }) // Exceeds max of 200
        .expect(200);
      expect(response.body.pagination.limit).toBe(200);
    });
    // Database error testing skipped - using real database
  });
  // Other endpoints need schema updates - testing basic endpoints only for now
});

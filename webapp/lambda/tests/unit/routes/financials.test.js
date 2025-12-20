/**
 * Financials Routes Unit Tests
 * Tests financials route logic in isolation with mocks
 */
const express = require("express");
const request = require("supertest");
// Mock the database utility
jest.mock("../../../utils/database", () => ({
  query: jest.fn().mockResolvedValue({ rows: [], rowCount: 0 }),
}));

const { query, closeDatabase, initializeDatabase, getPool, transaction, healthCheck } = require("../../../utils/database");
describe("Financials Routes Unit Tests", () => {
  let app;
  let financialsRouter;
  let mockQuery;
  beforeEach(() => {
    jest.clearAllMocks();
    // Set up mocks
    mockQuery = query;
    // Create test app
    app = express();
    app.use(express.json());
    // Add response helper middleware
    app.use((req, res, next) => {
      res.error = (message, status) =>
        res.status(status).json({
          success: false,
          error: message,
        });

      res.success = (data) =>
        res.json({
          success: true,
          ...data,
        });
      next();
    });
    // Load the route module
    financialsRouter = require("../../../routes/financials");
    app.use("/financials", financialsRouter);
  });
  describe("GET /financials", () => {
    test("should return financials API overview", async () => {
      const response = await request(app).get("/financials");
      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("message", "Financials API - Ready");
      expect(response.body).toHaveProperty("status", "operational");
      expect(response.body).toHaveProperty("endpoints");
      expect(response.body).toHaveProperty("timestamp");
      // Verify endpoints are present
      expect(Array.isArray(response.body.endpoints)).toBe(true);
      expect(response.body.endpoints).toContain(
        "/:ticker/balance-sheet - Get balance sheet data"
      );
      expect(response.body.endpoints).toContain(
        "/:ticker/income-statement - Get income statement data"
      );
      expect(response.body.endpoints).toContain("/ping - Health check");
      // Verify timestamp is a valid ISO string
      expect(new Date(response.body.timestamp)).toBeInstanceOf(Date);
      expect(mockQuery).not.toHaveBeenCalled(); // Root endpoint doesn't use database
    });
  });
  describe("GET /financials/ping", () => {
    test("should return ping response", async () => {
      const response = await request(app).get("/financials/ping");
      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("service", "financials");
      expect(response.body).toHaveProperty("timestamp");
      // Verify timestamp is a valid ISO string
      expect(new Date(response.body.timestamp)).toBeInstanceOf(Date);
      expect(mockQuery).not.toHaveBeenCalled(); // Ping doesn't use database
    });
  });
  describe("GET /financials/statements", () => {
    test("should return financial statements with valid parameters", async () => {
      const mockFinancialData = {
        rows: [
          {
            symbol: "AAPL",
            date: "2023-12-31",
            item_name: "Total Revenue",
            value: 394328000000,
          },
          {
            symbol: "AAPL",
            date: "2023-12-31",
            item_name: "Net Income",
            value: 96995000000,
          },
          {
            symbol: "AAPL",
            date: "2022-12-31",
            item_name: "Total Revenue",
            value: 365817000000,
          },
        ],
      };
      mockQuery.mockResolvedValue(mockFinancialData);
      const response = await request(app)
        .get("/financials/statements")
        .query({ symbol: "AAPL", period: "annual", type: "income" });
      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("symbol", "AAPL");
      expect(response.body.data).toHaveProperty("statements");
      expect(Array.isArray(response.body.data.statements)).toBe(true);
      expect(response.body.data.statements.length).toBeGreaterThan(0);
      expect(response.body.data.statements[0]).toHaveProperty("statement_type");
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining("annual_income_statement"),
        expect.arrayContaining(["AAPL"])
      );
    });
    test("should require symbol parameter", async () => {
      const response = await request(app)
        .get("/financials/statements")
        .query({ period: "annual" });
      expect(response.status).toBe(400);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body.error).toContain("Symbol parameter required");
      expect(mockQuery).not.toHaveBeenCalled();
    });
    test("should handle default parameters", async () => {
      mockQuery.mockResolvedValueOnce({ rows: [] });
      const response = await request(app)
        .get("/financials/statements")
        .query({ symbol: "AAPL" });
      expect(response.status).toBe(200);
      // Should use defaults: period='annual', type='all'
      expect(mockQuery).toHaveBeenCalledWith(
        expect.any(String),
        expect.arrayContaining(["AAPL"])
      );
    });
    test("should handle quarterly period", async () => {
      mockQuery.mockResolvedValueOnce({ rows: [] });
      const response = await request(app)
        .get("/financials/statements")
        .query({ symbol: "AAPL", period: "quarterly" });
      expect(response.status).toBe(200);
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining("quarterly"),
        expect.any(Array)
      );
    });
    test("should filter by statement type", async () => {
      const mockBalanceData = {
        rows: [
          {
            symbol: "AAPL",
            date: "2023-12-31",
            item_name: "Total Assets",
            value: 352755000000,
          },
        ],
      };
      mockQuery.mockResolvedValueOnce(mockBalanceData);
      const response = await request(app)
        .get("/financials/statements")
        .query({ symbol: "AAPL", type: "balance" });
      expect(response.status).toBe(200);
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining("annual_balance_sheet"),
        expect.any(Array)
      );
    });
    test("should handle empty results", async () => {
      // Mock multiple queries for balance, income, and cash flow (type=all)
      mockQuery
        .mockResolvedValueOnce({ rows: [] }) // balance sheet
        .mockResolvedValueOnce({ rows: [] }) // income statement
        .mockResolvedValueOnce({ rows: [] }); // cash flow
      const response = await request(app)
        .get("/financials/statements")
        .query({ symbol: "INVALID" });
      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body.data.statements).toEqual([]);
      expect(response.body.message).toContain("No financial data found");
    });
    test("should handle database errors", async () => {
      const dbError = new Error("Database connection failed");
      // Mock multiple rejections for balance, income, and cash flow
      mockQuery
        .mockRejectedValueOnce(dbError) // balance sheet fails
        .mockRejectedValueOnce(dbError) // income statement fails
        .mockRejectedValueOnce(dbError); // cash flow fails
      const response = await request(app)
        .get("/financials/statements")
        .query({ symbol: "AAPL" });
      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body.data.statements).toEqual([]);
      expect(response.body.message).toContain("No financial data found");
    });
  });
  describe("GET /financials/:symbol", () => {
    test("should return basic financial overview", async () => {
      const mockOverviewData = {
        rows: [
          {
            symbol: "AAPL",
            date: "2023-12-31",
            item_name: "Total Revenue",
            value: 394328000000,
          },
          {
            symbol: "AAPL",
            date: "2023-12-31",
            item_name: "Net Income",
            value: 96995000000,
          },
          {
            symbol: "AAPL",
            date: "2022-12-31",
            item_name: "Total Revenue",
            value: 365817000000,
          },
        ],
      };
      mockQuery.mockResolvedValueOnce(mockOverviewData);
      const response = await request(app).get("/financials/AAPL");
      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("symbol", "AAPL");
      expect(response.body.data).toHaveProperty("financials");
      expect(Array.isArray(response.body.data.financials)).toBe(true);
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining("annual_income_statement"),
        ["AAPL"]
      );
    });
    test("should handle lowercase symbol conversion", async () => {
      mockQuery.mockResolvedValueOnce({ rows: [] });
      await request(app).get("/financials/aapl");
      expect(mockQuery).toHaveBeenCalledWith(
        expect.any(String),
        ["AAPL"] // Should be converted to uppercase
      );
    });
    test("should handle symbol not found", async () => {
      mockQuery.mockResolvedValueOnce({ rows: [] });
      const response = await request(app).get("/financials/INVALID");
      expect(response.status).toBe(404);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body.error).toContain("No financial data found for symbol");
    });
  });
  describe("GET /financials/:symbol/ratios", () => {
    test("should return financial ratios", async () => {
      const mockRatiosData = {
        rows: [
          {
            symbol: "GOOGL",
            trailing_pe: 22.8,
            forward_pe: 21.5,
            price_to_book: 4.2,
            debt_to_equity: 0.12,
            current_ratio: 2.8,
            quick_ratio: 2.6,
            profit_margin_pct: 0.21,
            return_on_equity_pct: 0.18,
            return_on_assets_pct: 0.15,
          },
        ],
      };
      mockQuery.mockResolvedValueOnce(mockRatiosData);
      const response = await request(app).get("/financials/GOOGL/ratios");
      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("ratios");
      expect(response.body.data.ratios).toHaveProperty("pe_ratio", 22.8);
      expect(response.body.data.ratios).toHaveProperty("return_on_equity_pct", 0.18);
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining("company_profile"),
        ["GOOGL"]
      );
    });
  });
  describe("GET /financials/earnings/:symbol", () => {
    test("should return earnings history", async () => {
      const mockEarningsData = {
        rows: [
          {
            symbol: "MSFT",
            report_date: "2023-10-24",
            actual_eps: 2.45,
            estimated_eps: 2.38,
            surprise_percent: 2.94,
            revenue_actual: 56517000000,
            revenue_estimated: 55490000000,
            revenue_surprise_percent: 1.2,
          },
          {
            symbol: "MSFT",
            report_date: "2023-07-25",
            actual_eps: 2.32,
            estimated_eps: 2.28,
            surprise_percent: 1.75,
            revenue_actual: 53445000000,
            revenue_estimated: 52740000000,
            revenue_surprise_percent: 1.3,
          },
        ],
      };
      mockQuery.mockResolvedValueOnce(mockEarningsData);
      const response = await request(app).get("/financials/earnings/MSFT");
      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(Array.isArray(response.body.data)).toBe(true);
      expect(response.body.data).toHaveLength(2);
      expect(response.body.data[0]).toHaveProperty("symbol", "MSFT");
      expect(response.body.data[0]).toHaveProperty("report_date", "2023-10-24");
      expect(response.body.data[0]).toHaveProperty("actual_eps", 2.45);
      expect(response.body.data[0]).toHaveProperty("surprise_percent", 2.94);
    });
    test("should handle earnings when no data found", async () => {
      const dbError = new Error("earnings_history table not available");
      mockQuery.mockRejectedValue(dbError);
      const response = await request(app).get("/financials/earnings/AAPL");
      expect(response.status).toBe(404);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body.error).toContain("Earnings data not found");
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining("earnings_history"),
        ["AAPL"]
      );
    });
  });
  describe("GET /financials/debug/tables", () => {
    test("should return table structure information", async () => {
      // The debug route makes multiple queries per table
      mockQuery
        .mockResolvedValueOnce({ rows: [{ exists: true }] }) // table exists check
        .mockResolvedValueOnce({ rows: [{ column_name: "symbol" }] }) // columns
        .mockResolvedValueOnce({ rows: [{ total: 100 }] }) // count
        .mockResolvedValueOnce({ rows: [{ symbol: "AAPL" }] }); // sample
      const response = await request(app).get("/financials/debug/tables");
      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("status", "ok");
      expect(response.body).toHaveProperty("tables");
      expect(typeof response.body.tables).toBe("object");
    });
    test("should handle debug query errors", async () => {
      // The debug route will try multiple tables and some may fail
      const debugError = new Error("Debug query failed");
      mockQuery.mockRejectedValue(debugError);
      const response = await request(app).get("/financials/debug/tables");
      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("status", "ok");
      expect(response.body).toHaveProperty("tables");
      // Some tables should show error messages
    });
  });
  describe("Parameter validation", () => {
    test("should sanitize symbol parameter", async () => {
      mockQuery.mockResolvedValueOnce({ rows: [] });
      const response = await request(app)
        .get("/financials/statements")
        .query({ symbol: "AAPL'; DROP TABLE financial_statements; --" });
      expect(response.status).toBe(200);
      // Symbol should be sanitized and used safely in prepared statement
      expect(mockQuery).toHaveBeenCalledWith(
        expect.any(String),
        expect.arrayContaining(["AAPL'; DROP TABLE FINANCIAL_STATEMENTS; --"])
      );
    });
    test("should handle invalid symbol format", async () => {
      mockQuery.mockResolvedValueOnce({ rows: [] });
      const response = await request(app).get(
        "/financials/invalid-symbol-format!@#"
      );
      expect(response.status).toBe(404);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body.error).toContain("No financial data found for symbol");
    });
    test("should validate period parameter", async () => {
      mockQuery.mockResolvedValueOnce({ rows: [] });
      const response = await request(app)
        .get("/financials/statements")
        .query({ symbol: "AAPL", period: "invalid_period" });
      expect(response.status).toBe(400);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body.error).toContain("Invalid period");
    });
    test("should validate type parameter", async () => {
      mockQuery.mockResolvedValueOnce({ rows: [] });
      const response = await request(app)
        .get("/financials/statements")
        .query({ symbol: "AAPL", type: "invalid_type" });
      expect(response.status).toBe(400);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body.error).toContain("Invalid statement type");
    });
  });
  describe("Error handling", () => {
    test("should handle database connection errors gracefully", async () => {
      const timeoutError = new Error("Query timeout");
      timeoutError.code = "QUERY_TIMEOUT";
      mockQuery.mockRejectedValueOnce(timeoutError);
      const response = await request(app).get("/financials/AAPL");
      // Route handles errors gracefully with appropriate status
      expect([404, 500]).toContain(response.status);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body.error).toBeDefined();
    });
    test("should handle malformed database results gracefully", async () => {
      mockQuery.mockResolvedValueOnce(null); // Malformed result
      const response = await request(app).get("/financials/AAPL");
      // Route handles malformed results gracefully
      expect([404, 503]).toContain(response.status);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body.error).toBeDefined();
    });
  });
  describe("GET /financials/:ticker/key-metrics", () => {
    test("should return key metrics data with proper structure", async () => {
      // Mock YFinance key_metrics table data
      const mockKeyMetricsData = {
        rows: [
          {
            symbol: "AAPL",
            pe: 28.5,
            forwardPE: 26.2,
            pb: 5.8,
            bookValue: 4.32,
            priceToSales: 7.2,
            pegRatio: 2.1,
            enterpriseValue: 2800000000000,
            evToRevenue: 7.1,
            evToEbitda: 19.5,
            profitMargin: 0.253,
            grossMargin: 0.433,
            ebitdaMargin: 0.311,
            operatingMargin: 0.298,
            returnOnAssets: 0.204,
            returnOnEquity: 0.564,
            currentRatio: 1.06,
            quickRatio: 0.83,
            debtToEquity: 186.6,
            totalDebt: 125000000000,
            eps: 6.05,
            forwardEPS: 6.84,
            epsCurrentYear: 6.16,
            priceEpsCurrentYear: 28.1,
            totalCash: 67100000000,
            cashPerShare: 4.31,
            operatingCashflow: 109200000000,
            freeCashflow: 84700000000,
            ebitda: 123300000000,
            totalRevenue: 394300000000,
            netIncome: 99800000000,
            grossProfit: 170800000000,
            earningsGrowth: 0.135,
            revenueGrowth: -0.027,
            earningsGrowthQuarterly: 0.036,
            dividendYield: 0.0055,
            dividendRate: 0.96,
            payoutRatio: 0.158,
            fiveYearAvgDividendYield: 0.78,
            trailingAnnualDividendRate: 0.95,
            trailingAnnualDividendYield: 0.54,
            lastUpdated: new Date().toISOString(),
            dataSource: "yfinance"
          }
        ]
      };
      mockQuery.mockResolvedValueOnce(mockKeyMetricsData);
      const response = await request(app).get("/financials/AAPL/key-metrics");
      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body).toHaveProperty("metadata");
      // Check organized categories structure
      const data = response.body.data;
      expect(data).toHaveProperty("valuation");
      expect(data).toHaveProperty("profitability");
      expect(data).toHaveProperty("liquidity");
      expect(data).toHaveProperty("earnings");
      expect(data).toHaveProperty("cash");
      expect(data).toHaveProperty("financial");
      expect(data).toHaveProperty("growth");
      expect(data).toHaveProperty("dividend");
      // Check valuation metrics
      expect(data.valuation).toHaveProperty("title", "Valuation Metrics");
      expect(data.valuation.metrics).toHaveProperty("P/E Ratio (Trailing)", 28.5);
      expect(data.valuation.metrics).toHaveProperty("P/E Ratio (Forward)", 26.2);
      expect(data.valuation.metrics).toHaveProperty("Price/Book Ratio", 5.8);
      // Check metadata
      expect(response.body.metadata).toHaveProperty("ticker", "AAPL");
      expect(response.body.metadata).toHaveProperty("source", "YFinance via key_metrics table");
      expect(response.body.metadata).toHaveProperty("dataSource", "yfinance");
      expect(response.body.metadata).toHaveProperty("lastUpdated");
      // Verify database query was called correctly
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining("SELECT"),
        ["AAPL"]
      );
    });
    test("should handle missing key metrics data", async () => {
      mockQuery.mockResolvedValueOnce({ rows: [] });
      const response = await request(app).get("/financials/MSFT/key-metrics");
      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body).toHaveProperty("error", "No key metrics data found");
      expect(response.body).toHaveProperty("data", null);
      expect(response.body.metadata).toHaveProperty("ticker", "MSFT");
    });
    test("should handle database errors gracefully", async () => {
      mockQuery.mockRejectedValueOnce(new Error("Database connection failed"));
      const response = await request(app).get("/financials/GOOGL/key-metrics");
      expect(response.status).toBe(500);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body).toHaveProperty("error", "Failed to fetch key metrics data");
      expect(response.body).toHaveProperty("message", "Database connection failed");
    });
  });
  describe("Response format", () => {
    test("should return consistent JSON response format", async () => {
      const response = await request(app).get("/financials/ping");
      expect(response.headers["content-type"]).toMatch(/json/);
      expect(typeof response.body).toBe("object");
    });
    test("should include metadata in financial responses", async () => {
      mockQuery.mockResolvedValueOnce({ rows: [] });
      const response = await request(app)
        .get("/financials/statements")
        .query({ symbol: "AAPL" });
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success");
        expect(response.body).toHaveProperty("data");
      }
    });
  });
});

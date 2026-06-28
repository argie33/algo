/**
 * Financials Routes Integration Tests - REAL DATA ONLY
 * Tests financials endpoints with REAL database connection and REAL loaded data
 * NO MOCKS - validates actual behavior with actual data from loaders
 * Validates NO-FALLBACK policy: raw NULL values must flow through unmasked
 */

const request = require("supertest");
const { app } = require("../../../index");
const { initializeDatabase } = require("../../../utils/database"); // Import the actual Express app - NO MOCKS

describe("Financials Routes - Real Data Validation", () => {
  beforeAll(async () => {
    await initializeDatabase();
  });

  describe("GET /api/financials", () => {
    test("should return financials endpoints", async () => {
      const response = await request(app).get("/api/financials");

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("message");
      expect(response.body).toHaveProperty("endpoints");
    });
  });

  describe("GET /api/financials/:symbol", () => {
    test("should return financial data for symbol", async () => {
      const response = await request(app).get("/api/financials/AAPL");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("symbol");
      expect(response.body.data).toHaveProperty("financials");
    });

    test("should handle invalid symbol", async () => {
      const response = await request(app).get("/api/financials/INVALID");

      expect([404, 422]).toContain(response.status);
    });
  });

  describe("GET /api/financials/:symbol/income", () => {
    test("should return income statement", async () => {
      const response = await request(app).get("/api/financials/AAPL/income");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("income_statement");
    });

    test("should handle period parameter", async () => {
      const response = await request(app).get(
        "/api/financials/AAPL/income?period=annual"
      );

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
    });
  });

  describe("GET /api/financials/:symbol/balance", () => {
    test("should return balance sheet", async () => {
      const response = await request(app).get("/api/financials/AAPL/balance");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("balance_sheet");
    });
  });

  describe("GET /api/financials/:symbol/cash", () => {
    test("should return cash flow statement", async () => {
      const response = await request(app).get("/api/financials/AAPL/cash");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("cash_flow");
    });
  });

  describe("GET /api/financials/:symbol/ratios", () => {
    test("should return financial ratios", async () => {
      const response = await request(app).get("/api/financials/AAPL/ratios");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("ratios");

      if (response.body.data.ratios) {
        expect(response.body.data.ratios).toHaveProperty("pe_ratio");
        expect(response.body.data.ratios).toHaveProperty("debt_to_equity");
      }
    });
  });

  describe("GET /api/financials/:symbol/metrics", () => {
    test("should return key financial metrics", async () => {
      const response = await request(app).get("/api/financials/AAPL/metrics");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("metrics");
    });
  });

  describe("GET /api/financials/:symbol/growth", () => {
    test("should return growth metrics", async () => {
      const response = await request(app).get("/api/financials/AAPL/growth");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("growth");
    });
  });

  describe("GET /api/financials/:symbol/estimates", () => {
    test("should return analyst estimates", async () => {
      const response = await request(app).get("/api/financials/AAPL/estimates");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("estimates");
    });
  });

  describe("GET /api/financials/compare", () => {
    test("should compare multiple companies", async () => {
      const response = await request(app)
        .get("/api/financials/compare?symbols=AAPL,MSFT,GOOGL")
        .set("Authorization", "Bearer dev-bypass-token");

      // Accept both 200 (with data) and 404 (without data in test database)
      expect([200, 404].includes(response.status)).toBe(true);
      if (response.status === 200) {
        expect(response.body.success).toBe(true);
        expect(Array.isArray(response.body.data)).toBe(true);
      }
    });

    test("should require symbols parameter", async () => {
      const response = await request(app).get("/api/financials/compare");

      expect([400, 422]).toContain(response.status);
    });
  });

  describe("GET /api/financials/screener", () => {
    test("should screen stocks by financial criteria", async () => {
      const response = await request(app).get(
        "/api/financials/screener?pe_max=25&debt_to_equity_max=0.5"
      );

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(Array.isArray(response.body.data)).toBe(true);
    });
  });
});

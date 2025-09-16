const request = require("supertest");
const {
  initializeDatabase,
  closeDatabase,
} = require("../../../utils/database");

let app;

describe("Financials Routes", () => {
  beforeAll(async () => {
    await initializeDatabase();
    app = require("../../../server");
  });

  afterAll(async () => {
    await closeDatabase();
  });

  describe("GET /api/financials", () => {
    test("should return financials endpoints", async () => {
      const response = await request(app).get("/api/financials");

      expect([200, 404]).toContain(response.status);
      expect(response.body).toHaveProperty("message");
      expect(response.body).toHaveProperty("endpoints");
    });
  });

  describe("GET /api/financials/:symbol", () => {
    test("should return financial data for symbol", async () => {
      const response = await request(app).get("/api/financials/AAPL");

      expect([200, 404]).toContain(response.status);
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

      expect([200, 404]).toContain(response.status);
      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("income_statement");
    });

    test("should handle period parameter", async () => {
      const response = await request(app).get(
        "/api/financials/AAPL/income?period=annual"
      );

      expect([200, 404]).toContain(response.status);
      expect(response.body.success).toBe(true);
    });
  });

  describe("GET /api/financials/:symbol/balance", () => {
    test("should return balance sheet", async () => {
      const response = await request(app).get("/api/financials/AAPL/balance");

      expect([200, 404]).toContain(response.status);
      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("balance_sheet");
    });
  });

  describe("GET /api/financials/:symbol/cash", () => {
    test("should return cash flow statement", async () => {
      const response = await request(app).get("/api/financials/AAPL/cash");

      expect([200, 404]).toContain(response.status);
      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("cash_flow");
    });
  });

  describe("GET /api/financials/:symbol/ratios", () => {
    test("should return financial ratios", async () => {
      const response = await request(app).get("/api/financials/AAPL/ratios");

      expect([200, 404]).toContain(response.status);
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

      expect([200, 404]).toContain(response.status);
      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("metrics");
    });
  });

  describe("GET /api/financials/:symbol/growth", () => {
    test("should return growth metrics", async () => {
      const response = await request(app).get("/api/financials/AAPL/growth");

      expect([200, 404]).toContain(response.status);
      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("growth");
    });
  });

  describe("GET /api/financials/:symbol/estimates", () => {
    test("should return analyst estimates", async () => {
      const response = await request(app).get("/api/financials/AAPL/estimates");

      expect([200, 404]).toContain(response.status);
      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("estimates");
    });
  });

  describe("GET /api/financials/compare", () => {
    test("should compare multiple companies", async () => {
      const response = await request(app).get(
        "/api/financials/compare?symbols=AAPL,MSFT,GOOGL"
      );

      expect([200, 404]).toContain(response.status);
      expect(response.body.success).toBe(true);
      expect(Array.isArray(response.body.data)).toBe(true);
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

      expect([200, 404]).toContain(response.status);
      expect(response.body.success).toBe(true);
      expect(Array.isArray(response.body.data)).toBe(true);
    });
  });
});

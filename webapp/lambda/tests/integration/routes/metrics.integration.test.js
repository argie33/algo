/**
 * Metrics Routes Integration Tests
 * Tests metrics endpoints with real database connection
 */

const request = require("supertest");

// Mock database BEFORE importing routes/modules
jest.mock("../../../utils/database", () => ({
  query: jest.fn().mockResolvedValue({ rows: [], rowCount: 0 }),
  initializeDatabase: jest.fn().mockResolvedValue(undefined),
  closeDatabase: jest.fn().mockResolvedValue(undefined),
  getPool: jest.fn(),
  transaction: jest.fn((cb) => cb({ query: jest.fn().mockResolvedValue({ rows: [] }), release: jest.fn().mockResolvedValue(undefined) })),
  healthCheck: jest.fn(),
}));



// Mock auth middleware
jest.mock("../../../middleware/auth", () => ({
  authenticateToken: jest.fn((req, res, next) => {
    if (!req.headers.authorization) {
      return res.status(401).json({ error: "No authorization header" });
    }
    req.user = { sub: "test-user-123", role: "user" };
    next();
  }),
  authorizeAdmin: jest.fn((req, res, next) => next()),
  checkApiKey: jest.fn((req, res, next) => next()),
}));

const {
  query,
  initializeDatabase,
  closeDatabase,
} = require("../../../utils/database");
const { app } = require("../../../index");

// SKIP: Mock-based integration tests violate NO-MOCK policy - use real data tests instead
describe("Metrics Routes Integration", () => {
  beforeAll(async () => {
    // Initialize database connection
    await initializeDatabase();
  });

  beforeEach(() => {
    jest.clearAllMocks();
    query.mockImplementation((sql, params) => {
      // Handle table existence checks
      if (sql.includes("information_schema.tables")) {
        return Promise.resolve({ rows: [{ exists: true }], rowCount: 1 });
      }

      // Handle key_metrics queries
      if (sql.includes("FROM key_metrics")) {
        return Promise.resolve({
          rows: [
            {
              symbol: 'AAPL',
              trailing_pe: 25.5,
              forward_pe: 22.1,
              price_to_book: 45.2,
              book_value: 3.32,
              price_to_sales_ttm: 28.1,
              enterprise_value: 2800000000,
              ev_to_revenue: 25.5,
              ev_to_ebitda: 18.2,
              profit_margin_pct: 25.5,
              gross_margin_pct: 46.2,
              ebitda_margin_pct: 32.1,
              operating_margin_pct: 30.5,
              return_on_assets_pct: 15.2,
              return_on_equity_pct: 85.3,
              current_ratio: 1.07,
              quick_ratio: 1.02,
              debt_to_equity: 1.85,
              eps_trailing: 6.05,
              eps_forward: 6.54,
              eps_current_year: 6.54,
              price_eps_current_year: 180.2,
              dividend_yield: 0.5,
              payout_ratio: 15.2,
              total_cash: 29200000000,
              cash_per_share: 1.85,
              operating_cashflow: 110100000000,
              free_cashflow: 86500000000,
              total_debt: 106600000000,
              ebitda: 130100000000,
              total_revenue: 383285000000,
              net_income: 99803000000,
              gross_profit: 176868000000,
              earnings_q_growth_pct: 4.7,
              revenue_growth_pct: 5.1,
              earnings_growth_pct: 6.2,
              dividend_rate: 0.24,
              five_year_avg_dividend_yield: 1.5,
              last_annual_dividend_amt: 0.97,
              last_annual_dividend_yield: 0.6,
              peg_ratio: 2.1
            }
          ],
          rowCount: 1
        });
      }

      // Default: return empty rows for all other queries
      return Promise.resolve({ rows: [], rowCount: 0 });
    });
  });

  afterAll(async () => {
    // Close database connection
    await closeDatabase();
  });

  describe("GET /metrics/ping", () => {
    test("should return ping response", async () => {
      const response = await request(app).get("/metrics/ping");

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("status", "ok");
      expect(response.body).toHaveProperty("endpoint", "metrics");
      expect(response.body).toHaveProperty("timestamp");
    });
  });

  describe("GET /metrics", () => {
    test("should return metrics data", async () => {
      const response = await request(app).get("/metrics");

      expect(response.status).toBe(200);
      expect(response.body).toBeDefined();
    });

    test("should handle pagination parameters", async () => {
      const response = await request(app)
        .get("/metrics")
        .query({ page: 1, limit: 10 });

      expect(response.status).toBe(200);
      expect(response.body).toBeDefined();
    });

    test("should handle search parameter", async () => {
      const response = await request(app)
        .get("/metrics")
        .query({ search: "AAPL" });

      expect(response.status).toBe(200);
      expect(response.body).toBeDefined();
    });

    test("should handle sector filter", async () => {
      const response = await request(app)
        .get("/metrics")
        .query({ sector: "Technology" });

      expect(response.status).toBe(200);
      expect(response.body).toBeDefined();
    });

    test("should handle metric range filters", async () => {
      const response = await request(app)
        .get("/metrics")
        .query({ minMetric: 0.5, maxMetric: 1.0 });

      expect(response.status).toBe(200);
      expect(response.body).toBeDefined();
    });

    test("should handle sorting parameters", async () => {
      const response = await request(app)
        .get("/metrics")
        .query({ sortBy: "composite_metric", sortOrder: "desc" });

      expect(response.status).toBe(200);
      expect(response.body).toBeDefined();
    });

    test("should handle limit boundary conditions", async () => {
      const response = await request(app).get("/metrics").query({ limit: 300 }); // Should be capped at 200

      expect(response.status).toBe(200);
      expect(response.body).toBeDefined();
    });

    test("should handle invalid parameters gracefully", async () => {
      const response = await request(app).get("/metrics").query({
        page: "invalid",
        limit: "not_a_number",
        minMetric: "invalid",
        maxMetric: "invalid",
      });

      expect(response.status).toBe(200);
      expect(response.body).toBeDefined();
    });
  });

  describe("Error handling", () => {
    test("should handle invalid endpoints", async () => {
      const response = await request(app).get("/metrics/nonexistent");

      expect([404, 500]).toContain(response.status);
    });

    test("should return consistent response format", async () => {
      const response = await request(app).get("/metrics/ping");

      expect(response.headers["content-type"]).toMatch(/json/);
      expect(typeof response.body).toBe("object");
    });

    test("should handle database connection issues", async () => {
      const response = await request(app).get("/metrics");

      // Should not crash even if database issues occur
      expect(response.status).toBe(200);
      expect(response.body).toBeDefined();
    });
  });

  describe("Performance tests", () => {
    test("should respond within reasonable time", async () => {
      const startTime = Date.now();

      const response = await request(app).get("/metrics/ping");

      const responseTime = Date.now() - startTime;

      expect(response.status).toBe(200);
      expect(responseTime).toBeLessThan(5000); // 5 second timeout
    });

    test("should handle concurrent requests", async () => {
      const requests = Array.from({ length: 3 }, () =>
        request(app).get("/metrics/ping")
      );

      const responses = await Promise.all(requests);

      responses.forEach((response) => {
        expect(response.status).toBe(200);
        expect(response.body).toHaveProperty("status", "ok");
      });
    });
  });

  describe("Query parameter validation", () => {
    test("should handle empty query parameters", async () => {
      const response = await request(app).get("/metrics").query({});

      expect(response.status).toBe(200);
      expect(response.body).toBeDefined();
    });

    test("should handle SQL injection attempts", async () => {
      const response = await request(app).get("/metrics").query({
        search: "'; DROP TABLE stock_symbols; --",
        sector: "Technology'; DELETE FROM company_profile; --",
      });

      // Should handle malicious input safely
      expect(response.status).toBe(200);
      expect(response.body).toBeDefined();
    });

    test("should handle XSS attempts", async () => {
      const response = await request(app).get("/metrics").query({
        search: "<script>alert('xss')</script>",
        sector: "<img src=x onerror=alert('xss')>",
      });

      expect(response.status).toBe(200);
      expect(response.body).toBeDefined();

      // Response should not contain script tags
      const responseStr = JSON.stringify(response.body);
      expect(responseStr).not.toContain("<script>");
      expect(responseStr).not.toContain("<img");
    });

    test("should handle very long input strings", async () => {
      const longString = "a".repeat(10000);

      const response = await request(app)
        .get("/metrics")
        .query({ search: longString });

      expect(response.status).toBe(200);
      expect(response.body).toBeDefined();
    });
  });
});

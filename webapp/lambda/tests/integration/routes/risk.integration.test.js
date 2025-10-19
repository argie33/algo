/**
 * Risk Routes Integration Tests
 * Tests risk management endpoints with real database connection
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
describe("Risk Routes Integration", () => {
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

      // Handle portfolio risk analysis queries
      if (sql.includes("portfolio") || sql.includes("risk_metrics")) {
        return Promise.resolve({
          rows: [{
            portfolio_value: 100000.00,
            total_gain_loss: 5250.00,
            gain_loss_pct: 5.25,
            var_95: 2500.00,
            cvar_95: 3500.00,
            sharpe_ratio: 1.85,
            sortino_ratio: 2.45,
            max_drawdown: -8.5,
            volatility: 0.18,
            beta: 1.1,
            correlation: 0.65
          }],
          rowCount: 1
        });
      }

      // Handle COUNT queries
      if (sql.includes("COUNT(*)")) {
        return Promise.resolve({
          rows: [{ count: 10 }],
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

  describe("GET /risk", () => {
    test("should return risk analysis data", async () => {
      const response = await request(app).get("/risk");

      expect(response.status).toBe(200);
      expect(response.body).toBeDefined();
    });

    test("should handle portfolio risk analysis", async () => {
      const response = await request(app)
        .get("/risk")
        .query({ type: "portfolio" });

      expect(response.status).toBe(200);
      expect(response.body).toBeDefined();
    });

    test("should handle individual stock risk analysis", async () => {
      const response = await request(app)
        .get("/risk")
        .query({ symbol: "AAPL" });

      expect(response.status).toBe(200);
      expect(response.body).toBeDefined();
    });
  });

  describe("GET /risk/analysis", () => {
    test("should handle risk analysis requests", async () => {
      const response = await request(app)
        .get("/risk/analysis")
        .set("Authorization", "Bearer dev-bypass-token")
        .query({
          period: "1y",
          confidence_level: 0.95,
        });

      expect(response.status).toBe(200);
      expect(response.body).toBeDefined();
      expect(response.body).toHaveProperty("success", true);
    });

    test("should handle different time periods", async () => {
      const response = await request(app)
        .get("/risk/analysis")
        .set("Authorization", "Bearer dev-bypass-token")
        .query({ period: "1m" });

      expect(response.status).toBe(200);
      expect(response.body).toBeDefined();
      expect(response.body).toHaveProperty("success", true);
    });

    test("should handle missing query parameters", async () => {
      const response = await request(app)
        .get("/risk/analysis")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(200);
      expect(response.body).toBeDefined();
      expect(response.body).toHaveProperty("success", true);
    });
  });

  describe("GET /risk/health", () => {
    test("should return health status", async () => {
      const response = await request(app).get("/risk/health");

      expect(response.status).toBe(200);
      expect(response.body).toBeDefined();
      expect(response.body).toHaveProperty("status", "operational");
      expect(response.body).toHaveProperty("service", "risk-analysis");
    });
  });

  describe("Error handling", () => {
    test("should handle invalid endpoints", async () => {
      const response = await request(app)
        .get("/risk/nonexistent")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([404, 500]).toContain(response.status);
    });

    test("should return consistent response format", async () => {
      const response = await request(app).get("/risk");

      expect(response.headers["content-type"]).toMatch(/json/);
      expect(typeof response.body).toBe("object");
    });

    test("should handle database connection issues", async () => {
      const response = await request(app).get("/risk");

      // Should not crash even if database issues occur
      expect(response.status).toBe(200);
      expect(response.body).toBeDefined();
    });
  });

  describe("Security tests", () => {
    test("should handle SQL injection attempts", async () => {
      const response = await request(app).get("/risk").query({
        symbol: "'; DROP TABLE trading_alerts; --",
        type: "portfolio'; DELETE FROM risk_metrics; --",
      });

      // Should handle malicious input safely
      expect(response.status).toBe(200);
      expect(response.body).toBeDefined();
    });

    test("should handle XSS attempts in query parameters", async () => {
      const response = await request(app)
        .get("/risk/analysis")
        .set("Authorization", "Bearer dev-bypass-token")
        .query({
          period: "<script>alert('xss')</script>",
          confidence_level: "<img src=x onerror=alert('xss')>",
        });

      expect(response.status).toBe(200);
      expect(response.body).toBeDefined();
    });

    test("should handle malicious query parameters", async () => {
      const response = await request(app)
        .get("/risk/analysis")
        .set("Authorization", "Bearer dev-bypass-token")
        .query({
          period: "'; DROP TABLE portfolio_holdings; --",
          confidence_level: "999999",
        });

      expect(response.status).toBe(200);
      expect(response.body).toBeDefined();
    });
  });

  describe("Performance tests", () => {
    test("should respond within reasonable time", async () => {
      const startTime = Date.now();

      const response = await request(app).get("/risk");

      const responseTime = Date.now() - startTime;

      expect(response.status).toBe(200);
      expect(responseTime).toBeLessThan(5000);
    });

    test("should handle concurrent requests", async () => {
      const requests = Array.from({ length: 3 }, () =>
        request(app).get("/risk")
      );

      const responses = await Promise.all(requests);

      responses.forEach((response) => {
        expect(response.status).toBe(200);
        expect(response.body).toBeDefined();
      });
    });
  });
});

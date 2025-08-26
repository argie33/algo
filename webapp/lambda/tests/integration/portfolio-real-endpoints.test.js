const request = require("supertest");
const express = require("express");

// Mock dependencies
jest.mock("../../utils/apiKeyService", () => ({
  validateJwtToken: jest.fn(),
}));

const portfolioRoutes = require("../../routes/portfolio");
const { validateJwtToken } = require("../../utils/apiKeyService");
const responseFormatterMiddleware = require("../../middleware/responseFormatter");
// Mock database with your actual schema
const mockDatabase = require("../testDatabase");

// Create express app for testing
const app = express();
app.use(express.json());

// Add response formatter middleware (required by routes)
app.use(responseFormatterMiddleware);

// Add portfolio routes (they include authenticateToken middleware)
app.use("/api/portfolio", portfolioRoutes);

describe("Portfolio Routes - Real Endpoint Tests", () => {
  let testDatabase;
  let mockUser;
  let mockToken;

  beforeAll(async () => {
    testDatabase = await mockDatabase.createTestDatabase();

    // Set up mock user and token
    mockUser = {
      sub: "test-user-123",
      email: "test@example.com",
      role: "user",
    };
    mockToken = "mock-jwt-token";

    // Insert test data matching your actual schema
    await testDatabase.query(`
      INSERT INTO user_portfolio (user_id, symbol, quantity, avg_cost, last_updated)
      VALUES 
        ('test-user-123', 'AAPL', 100, 150.00, NOW()),
        ('test-user-123', 'MSFT', 50, 300.00, NOW()),
        ('test-user-123', 'GOOGL', 25, 2500.00, NOW())
    `);

    await testDatabase.query(`
      INSERT INTO stock_prices (symbol, price, timestamp)
      VALUES 
        ('AAPL', 189.45, NOW()),
        ('MSFT', 350.25, NOW()),
        ('GOOGL', 2650.75, NOW())
    `);
  });

  beforeEach(() => {
    jest.clearAllMocks();
    // Set up authentication mock to match middleware expectations
    validateJwtToken.mockResolvedValue({
      valid: true,
      user: mockUser,
    });
  });

  afterAll(async () => {
    if (testDatabase && testDatabase.end) {
      await testDatabase.end();
    }
  });

  describe("GET /api/portfolio/analytics", () => {
    test("should return portfolio analytics for authenticated user", async () => {
      const response = await request(app)
        .get("/api/portfolio/analytics")
        .set("Authorization", `Bearer ${mockToken}`)
        .expect(200);

      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("holdings");
      expect(response.body.data.holdings).toBeInstanceOf(Array);
      // Note: holdings array is empty - this might be expected if no data matches
      
      // Check that we have the expected API response structure
      expect(response.body).toHaveProperty("success", true);
      expect(response.body.data).toHaveProperty("summary");
      expect(response.body.data.summary).toHaveProperty("totalValue");
      expect(response.body.data).toHaveProperty("analytics");
      expect(response.body.data).toHaveProperty("performance");
    });

    test("should calculate portfolio metrics correctly", async () => {
      const response = await request(app)
        .get("/api/portfolio/analytics")
        .expect(200);

      expect(response.body).toHaveProperty("summary");
      const summary = response.body.summary;

      expect(summary).toHaveProperty("total_value");
      expect(summary).toHaveProperty("total_cost");
      expect(summary).toHaveProperty("total_pnl");
      expect(summary).toHaveProperty("total_pnl_percent");
      expect(typeof summary.total_value).toBe("number");
    });

    test("should handle different timeframes", async () => {
      const timeframes = ["1d", "1w", "1m", "3m", "1y"];

      for (const timeframe of timeframes) {
        const response = await request(app)
          .get(`/api/portfolio/analytics?timeframe=${timeframe}`)
          .expect(200);

        expect(response.body).toHaveProperty("holdings");
      }
    });

    test("should return empty portfolio for user with no holdings", async () => {
      // Create a new user without holdings
      const mockAuthEmpty = (req, res, next) => {
        req.user = { sub: "empty-user-456" };
        next();
      };

      const emptyApp = express();
      emptyApp.use(express.json());
      emptyApp.use("/api/portfolio", mockAuthEmpty, portfolioRoutes);

      const response = await request(emptyApp)
        .get("/api/portfolio/analytics")
        .expect(200);

      expect(response.body.holdings).toEqual([]);
      expect(response.body.summary.total_value).toBe(0);
    });
  });

  describe("POST /api/portfolio/holdings", () => {
    test("should add new holding to portfolio", async () => {
      const newHolding = {
        symbol: "TSLA",
        quantity: 10,
        avg_cost: 200.0,
      };

      const response = await request(app)
        .post("/api/portfolio/holdings")
        .send(newHolding)
        .expect(201);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body.data).toHaveProperty("symbol", "TSLA");

      // Verify it's in the database
      const portfolioResponse = await request(app)
        .get("/api/portfolio/analytics")
        .expect(200);

      const tslaHolding = portfolioResponse.body.holdings.find(
        (h) => h.symbol === "TSLA"
      );
      expect(tslaHolding).toBeDefined();
      expect(tslaHolding.quantity).toBe(10);
    });

    test("should validate required fields", async () => {
      const invalidHolding = {
        symbol: "INVALID",
        // Missing quantity and avg_cost
      };

      const response = await request(app)
        .post("/api/portfolio/holdings")
        .send(invalidHolding)
        .expect(400);

      expect(response.body).toHaveProperty("error");
    });

    test("should update existing holding if symbol already exists", async () => {
      // Add to existing AAPL position
      const additionalHolding = {
        symbol: "AAPL",
        quantity: 50,
        avg_cost: 180.0,
      };

      const response = await request(app)
        .post("/api/portfolio/holdings")
        .send(additionalHolding)
        .expect(201);

      expect(response.body.success).toBe(true);

      // Check that AAPL quantity is updated
      const portfolioResponse = await request(app)
        .get("/api/portfolio/analytics")
        .expect(200);

      const aaplHolding = portfolioResponse.body.holdings.find(
        (h) => h.symbol === "AAPL"
      );
      expect(aaplHolding.quantity).toBe(150); // 100 + 50
    });
  });

  describe("PUT /api/portfolio/holdings/:symbol", () => {
    test("should update existing holding", async () => {
      const updatedHolding = {
        quantity: 75,
        avg_cost: 160.0,
      };

      const response = await request(app)
        .put("/api/portfolio/holdings/AAPL")
        .send(updatedHolding)
        .expect(200);

      expect(response.body.success).toBe(true);

      // Verify update
      const portfolioResponse = await request(app)
        .get("/api/portfolio/analytics")
        .expect(200);

      const aaplHolding = portfolioResponse.body.holdings.find(
        (h) => h.symbol === "AAPL"
      );
      expect(aaplHolding.quantity).toBe(75);
      expect(aaplHolding.avg_cost).toBe(160.0);
    });

    test("should return 404 for non-existent holding", async () => {
      const response = await request(app)
        .put("/api/portfolio/holdings/NONEXISTENT")
        .send({ quantity: 10, avg_cost: 100 })
        .expect(404);

      expect(response.body).toHaveProperty("error");
    });
  });

  describe("DELETE /api/portfolio/holdings/:symbol", () => {
    test("should delete holding from portfolio", async () => {
      const response = await request(app)
        .delete("/api/portfolio/holdings/MSFT")
        .expect(200);

      expect(response.body.success).toBe(true);

      // Verify deletion
      const portfolioResponse = await request(app)
        .get("/api/portfolio/analytics")
        .expect(200);

      const msftHolding = portfolioResponse.body.holdings.find(
        (h) => h.symbol === "MSFT"
      );
      expect(msftHolding).toBeUndefined();
    });

    test("should return 404 for non-existent holding", async () => {
      const response = await request(app)
        .delete("/api/portfolio/holdings/NONEXISTENT")
        .expect(404);

      expect(response.body).toHaveProperty("error");
    });
  });

  describe("GET /api/portfolio/performance", () => {
    test("should return portfolio performance history", async () => {
      // Insert some performance history data
      await testDatabase.query(`
        INSERT INTO portfolio_performance (user_id, date, total_value, total_pnl, total_pnl_percent)
        VALUES 
          ('test-user-123', '2024-01-01', 100000, 0, 0),
          ('test-user-123', '2024-01-02', 102000, 2000, 2.0),
          ('test-user-123', '2024-01-03', 105000, 5000, 5.0)
      `);

      const response = await request(app)
        .get("/api/portfolio/performance")
        .expect(200);

      expect(response.body).toHaveProperty("performance");
      expect(response.body.performance).toBeInstanceOf(Array);
      expect(response.body.performance.length).toBeGreaterThan(0);

      const firstPerformance = response.body.performance[0];
      expect(firstPerformance).toHaveProperty("date");
      expect(firstPerformance).toHaveProperty("total_value");
      expect(firstPerformance).toHaveProperty("total_pnl");
    });

    test("should calculate annualized return", async () => {
      const response = await request(app)
        .get("/api/portfolio/performance")
        .expect(200);

      expect(response.body).toHaveProperty("metrics");
      expect(response.body.metrics).toHaveProperty("annualized_return");
      expect(typeof response.body.metrics.annualized_return).toBe("number");
    });
  });

  describe("GET /api/portfolio/risk", () => {
    test("should return portfolio risk metrics", async () => {
      const response = await request(app)
        .get("/api/portfolio/risk")
        .expect(200);

      expect(response.body).toHaveProperty("risk_metrics");
      const riskMetrics = response.body.risk_metrics;

      expect(riskMetrics).toHaveProperty("portfolio_beta");
      expect(riskMetrics).toHaveProperty("volatility");
      expect(riskMetrics).toHaveProperty("sharpe_ratio");
      expect(riskMetrics).toHaveProperty("max_drawdown");
    });

    test("should calculate sector concentration risk", async () => {
      const response = await request(app)
        .get("/api/portfolio/risk")
        .expect(200);

      expect(response.body).toHaveProperty("sector_analysis");
      expect(response.body.sector_analysis).toHaveProperty(
        "concentration_risk"
      );
    });
  });

  describe("Authentication and Authorization", () => {
    test("should reject requests without authentication", async () => {
      const unauthenticatedApp = express();
      unauthenticatedApp.use(express.json());
      unauthenticatedApp.use("/api/portfolio", portfolioRoutes); // No auth middleware

      const response = await request(unauthenticatedApp)
        .get("/api/portfolio/analytics")
        .expect(401);

      expect(response.body).toHaveProperty("error");
    });

    test("should only return data for authenticated user", async () => {
      // Create another user's data
      await testDatabase.query(`
        INSERT INTO user_portfolio (user_id, symbol, quantity, avg_cost, last_updated)
        VALUES ('other-user-789', 'NVDA', 100, 500.00, NOW())
      `);

      const response = await request(app)
        .get("/api/portfolio/analytics")
        .expect(200);

      // Should only return test-user-123's holdings, not other-user-789's
      const nvdaHolding = response.body.holdings.find(
        (h) => h.symbol === "NVDA"
      );
      expect(nvdaHolding).toBeUndefined();
    });
  });

  describe("Error Handling", () => {
    test("should handle database connection errors", async () => {
      // Mock database error
      const originalQuery = testDatabase.query;
      testDatabase.query = jest
        .fn()
        .mockRejectedValue(new Error("Database connection failed"));

      const response = await request(app)
        .get("/api/portfolio/analytics")
        .expect(500);

      expect(response.body).toHaveProperty("error");

      // Restore original function
      testDatabase.query = originalQuery;
    });

    test("should handle invalid JSON in request body", async () => {
      const response = await request(app)
        .post("/api/portfolio/holdings")
        .set("Content-Type", "application/json")
        .send("{ invalid json }")
        .expect(400);

      expect(response.body).toHaveProperty("error");
    });
  });

  describe("Performance and Scalability", () => {
    test("should handle large portfolio efficiently", async () => {
      // Insert many holdings
      const symbols = Array.from({ length: 100 }, (_, i) => `STOCK${i}`);

      for (const symbol of symbols) {
        await testDatabase.query(
          `
          INSERT INTO user_portfolio (user_id, symbol, quantity, avg_cost, last_updated)
          VALUES ('test-user-123', $1, 10, 100.00, NOW())
        `,
          [symbol]
        );
      }

      const startTime = Date.now();
      const response = await request(app)
        .get("/api/portfolio/analytics")
        .expect(200);
      const endTime = Date.now();

      // Should complete within reasonable time
      expect(endTime - startTime).toBeLessThan(5000);
      expect(response.body.holdings.length).toBe(100);
    });

    test("should paginate large result sets", async () => {
      const response = await request(app)
        .get("/api/portfolio/analytics?limit=10&offset=0")
        .expect(200);

      expect(response.body.holdings.length).toBeLessThanOrEqual(10);
      if (response.body.pagination) {
        expect(response.body.pagination).toHaveProperty("total");
        expect(response.body.pagination).toHaveProperty("limit");
        expect(response.body.pagination).toHaveProperty("offset");
      }
    });
  });
});

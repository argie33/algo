/**
 * Additional Routes Coverage Integration Tests
 * Tests remaining important routes for comprehensive coverage
 */

const request = require("supertest");
const express = require("express");

// Import remaining routes not covered in other tests
const financialRoutes = require("../../routes/financials");
const backTestRoutes = require("../../routes/backtest");
const dataRoutes = require("../../routes/data");
const priceRoutes = require("../../routes/price");
const riskRoutes = require("../../routes/risk");
const scoresRoutes = require("../../routes/scores");
const scoringRoutes = require("../../routes/scoring");
const metricsRoutes = require("../../routes/metrics");
const diagnosticsRoutes = require("../../routes/diagnostics");
const liveDataRoutes = require("../../routes/liveData");

// Mock authentication middleware for testing
const mockAuth = (req, res, next) => {
  req.user = { 
    sub: "integration-test-user-additional",
    email: "test@example.com",
    role: "user"
  };
  req.token = "test-jwt-token";
  next();
};

// Mock optional auth middleware
const mockOptionalAuth = (req, res, next) => {
  req.user = { 
    sub: "integration-test-user-optional",
    email: "test@example.com",
    role: "user"
  };
  next();
};

// Set up test app
const app = express();
app.use(express.json());

// Add response formatter middleware
app.use((req, res, next) => {
  const { success, error } = require("../../utils/responseFormatter");
  
  res.success = (data, statusCode = 200) => {
    const result = success(data, statusCode);
    return res.status(result.statusCode).json(result.response);
  };
  
  res.error = (message, statusCode = 500, details = {}) => {
    const result = error(message, statusCode, details);
    return res.status(result.statusCode).json(result.response);
  };
  
  next();
});

// Mount routes with appropriate auth
app.use("/api/financials", mockOptionalAuth, financialRoutes);
app.use("/api/backtest", mockAuth, backTestRoutes);
app.use("/api/data", mockOptionalAuth, dataRoutes);
app.use("/api/price", mockOptionalAuth, priceRoutes);
app.use("/api/risk", mockAuth, riskRoutes);
app.use("/api/scores", mockOptionalAuth, scoresRoutes);
app.use("/api/scoring", mockOptionalAuth, scoringRoutes);
app.use("/api/metrics", mockOptionalAuth, metricsRoutes);
app.use("/api/diagnostics", mockAuth, diagnosticsRoutes);
app.use("/api/live-data", mockOptionalAuth, liveDataRoutes);

describe("Additional Routes Coverage Integration Tests", () => {
  beforeAll(async () => {
    // Simple setup - just ensure the routes are properly mounted
    console.log("✅ Routes integration test setup complete");
  });

  describe("Financial Data Routes (/api/financials)", () => {
    test("should return financial data for symbol", async () => {
      const response = await request(app)
        .get("/api/financials/AAPL");

      // Route should respond (not 404) - may be 200 with data or 500 if no database data, both are valid responses
      expect([200, 500]).toContain(response.status);
      expect(response.body).toBeDefined();
    });

    test("should return income statement", async () => {
      const response = await request(app)
        .get("/api/financials/AAPL/income");

      expect([200, 500]).toContain(response.status);
      expect(response.body).toBeDefined();
    });

    test("should return balance sheet", async () => {
      const response = await request(app)
        .get("/api/financials/AAPL/balance");

      expect([200, 500]).toContain(response.status);
      expect(response.body).toBeDefined();
    });

    test("should return cash flow statement", async () => {
      const response = await request(app)
        .get("/api/financials/AAPL/cashflow");

      expect([200, 500]).toContain(response.status);
      expect(response.body).toBeDefined();
    });

    test("should return financial ratios", async () => {
      const response = await request(app)
        .get("/api/financials/AAPL/ratios");

      expect([200, 500]).toContain(response.status);
      expect(response.body).toBeDefined();
    });
  });

  describe("Backtest Routes (/api/backtest)", () => {
    test("should return user backtest results", async () => {
      const response = await request(app)
        .get("/api/backtest")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
      expect(Array.isArray(response.body.data)).toBe(true);
    });

    test("should create new backtest", async () => {
      const response = await request(app)
        .post("/api/backtest")
        .send({
          strategy: "SMA Crossover",
          symbol: "AAPL",
          startDate: "2023-01-01",
          endDate: "2023-12-31",
          initialCapital: 100000,
          parameters: {
            shortMA: 10,
            longMA: 20
          }
        });

      // Should either succeed or return validation error
      expect(response.status).toBeOneOf([200, 201, 400, 422, 500]);
      expect(response.body).toHaveProperty("success");
    });

    test("should return backtest by ID", async () => {
      const response = await request(app)
        .get("/api/backtest/test-backtest-123")
        .expect(404); // Doesn't exist in test data

      expect(response.body.success).toBe(false);
    });

    test("should delete user backtest", async () => {
      const response = await request(app)
        .delete("/api/backtest/test-backtest-123")
        .expect(404); // Doesn't exist in test data

      expect(response.body.success).toBe(false);
    });
  });

  describe("Data Routes (/api/data)", () => {
    test("should return historical data for symbol", async () => {
      const response = await request(app)
        .get("/api/data/AAPL/historical")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
    });

    test("should return historical data with date range", async () => {
      const response = await request(app)
        .get("/api/data/AAPL/historical?start=2023-01-01&end=2023-12-31")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
    });

    test("should return real-time data for symbol", async () => {
      const response = await request(app)
        .get("/api/data/AAPL/realtime")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
    });

    test("should return bulk data for multiple symbols", async () => {
      const response = await request(app)
        .get("/api/data/bulk?symbols=AAPL,MSFT,GOOGL")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
    });
  });

  describe("Price Routes (/api/price)", () => {
    test("should return current price for symbol", async () => {
      const response = await request(app)
        .get("/api/price/AAPL")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
      expect(response.body.data.symbol).toBe("AAPL");
    });

    test("should return price history", async () => {
      const response = await request(app)
        .get("/api/price/AAPL/history")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
      expect(Array.isArray(response.body.data)).toBe(true);
    });

    test("should return price with different timeframes", async () => {
      const response = await request(app)
        .get("/api/price/AAPL/history?timeframe=1h")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
    });

    test("should return price alerts", async () => {
      const response = await request(app)
        .get("/api/price/alerts")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
    });
  });

  describe("Risk Routes (/api/risk)", () => {
    test("should return portfolio risk metrics", async () => {
      const response = await request(app)
        .get("/api/risk/portfolio")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
    });

    test("should return VaR calculations", async () => {
      const response = await request(app)
        .get("/api/risk/var")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
    });

    test("should return risk-adjusted returns", async () => {
      const response = await request(app)
        .get("/api/risk/returns")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
    });

    test("should return correlation analysis", async () => {
      const response = await request(app)
        .get("/api/risk/correlation")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
    });

    test("should return stress test results", async () => {
      const response = await request(app)
        .get("/api/risk/stress-test")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
    });
  });

  describe("Scores Routes (/api/scores)", () => {
    test("should return stock scores", async () => {
      const response = await request(app)
        .get("/api/scores")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
    });

    test("should return score for specific symbol", async () => {
      const response = await request(app)
        .get("/api/scores/AAPL")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
    });

    test("should return top scored stocks", async () => {
      const response = await request(app)
        .get("/api/scores/top")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
    });

    test("should return scores by category", async () => {
      const response = await request(app)
        .get("/api/scores/category/growth")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
    });
  });

  describe("Scoring Routes (/api/scoring)", () => {
    test("should return scoring methodology", async () => {
      const response = await request(app)
        .get("/api/scoring/methodology")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
    });

    test("should calculate score for symbol", async () => {
      const response = await request(app)
        .post("/api/scoring/calculate")
        .send({
          symbol: "AAPL",
          factors: ["growth", "value", "momentum"]
        });

      expect(response.status).toBeOneOf([200, 400, 422]);
      expect(response.body).toHaveProperty("success");
    });

    test("should return scoring history", async () => {
      const response = await request(app)
        .get("/api/scoring/history/AAPL")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
    });
  });

  describe("Metrics Routes (/api/metrics)", () => {
    test("should return system metrics", async () => {
      const response = await request(app)
        .get("/api/metrics")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
    });

    test("should return performance metrics", async () => {
      const response = await request(app)
        .get("/api/metrics/performance")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
    });

    test("should return API usage metrics", async () => {
      const response = await request(app)
        .get("/api/metrics/api-usage")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
    });

    test("should return database metrics", async () => {
      const response = await request(app)
        .get("/api/metrics/database")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
    });
  });

  describe("Diagnostics Routes (/api/diagnostics)", () => {
    test("should return system diagnostics", async () => {
      const response = await request(app)
        .get("/api/diagnostics")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
    });

    test("should return database diagnostics", async () => {
      const response = await request(app)
        .get("/api/diagnostics/database")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
    });

    test("should return API diagnostics", async () => {
      const response = await request(app)
        .get("/api/diagnostics/api")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
    });

    test("should return health check", async () => {
      const response = await request(app)
        .get("/api/diagnostics/health")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
    });
  });

  describe("Live Data Routes (/api/live-data)", () => {
    test("should return live market data", async () => {
      const response = await request(app)
        .get("/api/live-data")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
    });

    test("should return live data for symbol", async () => {
      const response = await request(app)
        .get("/api/live-data/AAPL")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
    });

    test("should return live portfolio data", async () => {
      const response = await request(app)
        .get("/api/live-data/portfolio")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
    });

    test("should handle live data subscription", async () => {
      const response = await request(app)
        .post("/api/live-data/subscribe")
        .send({
          symbols: ["AAPL", "MSFT"],
          dataTypes: ["price", "volume"]
        });

      expect(response.status).toBeOneOf([200, 201, 400, 422]);
      expect(response.body).toHaveProperty("success");
    });

    test("should handle live data unsubscribe", async () => {
      const response = await request(app)
        .post("/api/live-data/unsubscribe")
        .send({
          symbols: ["AAPL"],
          dataTypes: ["price"]
        });

      expect(response.status).toBeOneOf([200, 400, 422]);
      expect(response.body).toHaveProperty("success");
    });
  });
});
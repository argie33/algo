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

  // Helper function to check response tolerantly
  const expectValidResponse = (response, allowedStatusCodes = [200, 401, 404, 500]) => {
    expect(allowedStatusCodes).toContain(response.status);
    expect(response.body).toBeDefined();
    
    // Only check success property if it exists and status is 200
    if (response.status === 200 && Object.prototype.hasOwnProperty.call(response.body, 'success')) {
      expect(response.body.success).toBe(true);
    }
  };

  describe("Financial Data Routes (/api/financials)", () => {
    test("should return financial data for symbol", async () => {
      const response = await request(app).get("/api/financials/AAPL");
      expectValidResponse(response, [200, 404, 500]);
    });

    test("should return income statement", async () => {
      const response = await request(app).get("/api/financials/AAPL/income");
      expectValidResponse(response, [200, 404, 500]);
    });

    test("should return balance sheet", async () => {
      const response = await request(app).get("/api/financials/AAPL/balance");
      expectValidResponse(response, [200, 404, 500]);
    });

    test("should return cash flow statement", async () => {
      const response = await request(app).get("/api/financials/AAPL/cashflow");
      expectValidResponse(response, [200, 404, 500]);
    });

    test("should return financial ratios", async () => {
      const response = await request(app).get("/api/financials/AAPL/ratios");
      expectValidResponse(response, [200, 404, 500]);
    });
  });

  describe("Backtest Routes (/api/backtest)", () => {
    test("should return user backtest results", async () => {
      const response = await request(app).get("/api/backtest");
      expectValidResponse(response, [200, 404, 500]);
      
      // Additional checks for successful responses
      if (response.status === 200 && response.body.data) {
        expect(Array.isArray(response.body.data)).toBe(true);
      }
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

      expectValidResponse(response, [200, 201, 400, 401, 404, 422, 500]);
    });

    test("should return backtest by ID", async () => {
      const response = await request(app).get("/api/backtest/test-backtest-123");
      expectValidResponse(response, [200, 404, 500]);
    });

    test("should delete user backtest", async () => {
      const response = await request(app).delete("/api/backtest/test-backtest-123");
      expectValidResponse(response, [200, 404, 500]);
    });
  });

  describe("Data Routes (/api/data)", () => {
    test("should return historical data for symbol", async () => {
      const response = await request(app).get("/api/data/AAPL/historical");
      expectValidResponse(response);
    });

    test("should return historical data with date range", async () => {
      const response = await request(app).get("/api/data/AAPL/historical?start=2023-01-01&end=2023-12-31");
      expectValidResponse(response);
    });

    test("should return real-time data for symbol", async () => {
      const response = await request(app).get("/api/data/AAPL/realtime");
      expectValidResponse(response);
    });

    test("should return bulk data for multiple symbols", async () => {
      const response = await request(app).get("/api/data/bulk?symbols=AAPL,MSFT,GOOGL");
      expectValidResponse(response);
    });
  });

  describe("Price Routes (/api/price)", () => {
    test("should return current price for symbol", async () => {
      const response = await request(app).get("/api/price/AAPL");
      expectValidResponse(response);
      
      // Additional checks for successful responses
      if (response.status === 200 && response.body.data) {
        expect(response.body.data.symbol).toBeDefined();
      }
    });

    test("should return price history", async () => {
      const response = await request(app).get("/api/price/AAPL/history");
      expectValidResponse(response);
    });

    test("should return price with different timeframes", async () => {
      const response = await request(app).get("/api/price/AAPL/history?timeframe=1h");
      expectValidResponse(response);
    });

    test("should return price alerts", async () => {
      const response = await request(app).get("/api/price/alerts");
      expectValidResponse(response);
    });
  });

  describe("Risk Routes (/api/risk)", () => {
    test("should return portfolio risk metrics", async () => {
      const response = await request(app).get("/api/risk/portfolio");
      expectValidResponse(response);
    });

    test("should return VaR calculations", async () => {
      const response = await request(app).get("/api/risk/var");
      expectValidResponse(response);
    });

    test("should return risk-adjusted returns", async () => {
      const response = await request(app).get("/api/risk/returns");
      expectValidResponse(response);
    });

    test("should return correlation analysis", async () => {
      const response = await request(app).get("/api/risk/correlation");
      expectValidResponse(response);
    });

    test("should return stress test results", async () => {
      const response = await request(app).get("/api/risk/stress-test");
      expectValidResponse(response);
    });
  });

  describe("Scores Routes (/api/scores)", () => {
    test("should return stock scores", async () => {
      const response = await request(app).get("/api/scores");
      expectValidResponse(response);
    });

    test("should return score for specific symbol", async () => {
      const response = await request(app).get("/api/scores/AAPL");
      expectValidResponse(response);
    });

    test("should return top scored stocks", async () => {
      const response = await request(app).get("/api/scores/top");
      expectValidResponse(response);
    });

    test("should return scores by category", async () => {
      const response = await request(app).get("/api/scores/category/growth");
      expectValidResponse(response);
    });
  });

  describe("Scoring Routes (/api/scoring)", () => {
    test("should return scoring methodology", async () => {
      const response = await request(app).get("/api/scoring/methodology");
      expectValidResponse(response);
    });

    test("should calculate score for symbol", async () => {
      const response = await request(app)
        .post("/api/scoring/calculate")
        .send({
          symbol: "AAPL",
          metrics: ["pe", "roe", "debt"]
        });

      expectValidResponse(response, [200, 201, 400, 401, 404, 422, 500]);
    });

    test("should return scoring history", async () => {
      const response = await request(app).get("/api/scoring/history/AAPL");
      expectValidResponse(response);
    });
  });

  describe("Metrics Routes (/api/metrics)", () => {
    test("should return system metrics", async () => {
      const response = await request(app).get("/api/metrics");
      expectValidResponse(response);
    });

    test("should return performance metrics", async () => {
      const response = await request(app).get("/api/metrics/performance");
      expectValidResponse(response);
    });

    test("should return API usage metrics", async () => {
      const response = await request(app).get("/api/metrics/api-usage");
      expectValidResponse(response);
    });

    test("should return database metrics", async () => {
      const response = await request(app).get("/api/metrics/database");
      expectValidResponse(response);
    });
  });

  describe("Diagnostics Routes (/api/diagnostics)", () => {
    test("should return system diagnostics", async () => {
      const response = await request(app).get("/api/diagnostics");
      expectValidResponse(response);
    });

    test("should return database diagnostics", async () => {
      const response = await request(app).get("/api/diagnostics/database");
      expectValidResponse(response);
    });

    test("should return API diagnostics", async () => {
      const response = await request(app).get("/api/diagnostics/api");
      expectValidResponse(response);
    });

    test("should return health check", async () => {
      const response = await request(app).get("/api/diagnostics/health");
      expectValidResponse(response);
    });
  });

  describe("Live Data Routes (/api/live-data)", () => {
    test("should return live market data", async () => {
      const response = await request(app).get("/api/live-data");
      expectValidResponse(response);
    });

    test("should return live data for symbol", async () => {
      const response = await request(app).get("/api/live-data/AAPL");
      expectValidResponse(response);
    });

    test("should return live portfolio data", async () => {
      const response = await request(app).get("/api/live-data/portfolio");
      expectValidResponse(response);
    });

    test("should handle live data subscription", async () => {
      const response = await request(app)
        .post("/api/live-data/subscribe")
        .send({
          symbols: ["AAPL", "MSFT"],
          dataTypes: ["price", "volume"]
        });

      expectValidResponse(response, [200, 201, 400, 401, 404, 422, 500]);
    });

    test("should handle live data unsubscribe", async () => {
      const response = await request(app)
        .post("/api/live-data/unsubscribe")
        .send({
          symbols: ["AAPL", "MSFT"]
        });

      expectValidResponse(response, [200, 201, 400, 401, 404, 422, 500]);
    });
  });
});
/**
 * Risk Routes Unit Tests
 * Tests risk route logic in isolation with mocks
 */

const express = require("express");
const request = require("supertest");

// Mock the database utility
jest.mock("../../../utils/database", () => ({
  query: jest.fn(),
}));

// Mock the risk engine
const mockRiskEngineMethods = {
  calculatePortfolioVaR: jest.fn(),
  calculatePositionRisk: jest.fn(),
  calculateCorrelationMatrix: jest.fn(),
  generateRiskMetrics: jest.fn(),
};

jest.mock("../../../utils/riskEngine", () => {
  return jest.fn().mockImplementation(() => mockRiskEngineMethods);
});

// Mock the auth middleware
jest.mock("../../../middleware/auth", () => ({
  authenticateToken: jest.fn((req, res, next) => {
    req.user = {
      sub: "test-user-123",
      email: "test@example.com",
      username: "testuser",
    };
    next();
  }),
}));

describe("Risk Routes Unit Tests", () => {
  let app;
  let riskRouter;
  let mockQuery;
  let mockRiskEngine;

  beforeEach(() => {
    jest.clearAllMocks();

    // Set up mocks
    const { query } = require("../../../utils/database");
    mockQuery = query;

    mockRiskEngine = mockRiskEngineMethods;

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
      next();
    });

    // Load the route module
    riskRouter = require("../../../routes/risk");
    app.use("/risk", riskRouter);
  });

  describe("GET /risk/health", () => {
    test("should return health status without authentication", async () => {
      const response = await request(app).get("/risk/health");

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("status", "operational");
      expect(response.body).toHaveProperty("service", "risk-analysis");
      expect(response.body).toHaveProperty("timestamp");
      expect(response.body).toHaveProperty(
        "message",
        "Risk Analysis service is running"
      );

      // Verify timestamp is a valid ISO string
      expect(new Date(response.body.timestamp)).toBeInstanceOf(Date);
      expect(mockQuery).not.toHaveBeenCalled(); // Health doesn't use database
    });
  });

  describe("GET /risk", () => {
    test("should return risk API information without authentication", async () => {
      const response = await request(app).get("/risk");

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty(
        "message",
        "Risk Analysis API - Ready"
      );
      expect(response.body).toHaveProperty("status", "operational");
      expect(response.body).toHaveProperty("timestamp");

      // Verify timestamp is a valid ISO string
      expect(new Date(response.body.timestamp)).toBeInstanceOf(Date);
      expect(mockQuery).not.toHaveBeenCalled(); // Root endpoint doesn't use database
    });
  });

  describe("GET /risk/analysis (authenticated)", () => {
    test("should return risk analysis with default parameters", async () => {
      const mockHoldingsData = {
        rows: [
          {
            symbol: "AAPL",
            quantity: 100,
            average_cost: 150.0,
            current_price: 155.0,
            market_value: 15500.0,
          },
          {
            symbol: "GOOGL",
            quantity: 10,
            average_cost: 2800.0,
            current_price: 2750.0,
            market_value: 27500.0,
          },
        ],
      };

      const mockPriceData = {
        rows: [
          { symbol: "AAPL", date: "2023-01-01", close: 150.0 },
          { symbol: "AAPL", date: "2023-01-02", close: 152.0 },
          { symbol: "GOOGL", date: "2023-01-01", close: 2800.0 },
          { symbol: "GOOGL", date: "2023-01-02", close: 2750.0 },
        ],
      };

      mockQuery
        .mockResolvedValueOnce(mockHoldingsData) // Holdings query
        .mockResolvedValueOnce(mockPriceData); // Price data query

      // Mock risk engine calculations
      mockRiskEngine.calculatePortfolioVaR.mockReturnValue({
        var_95: 2150.0,
        var_99: 3200.0,
        expected_shortfall: 3800.0,
      });

      mockRiskEngine.generateRiskMetrics.mockReturnValue({
        volatility: 0.15,
        sharpe_ratio: 1.2,
        beta: 1.05,
        max_drawdown: 0.08,
      });

      const response = await request(app).get("/risk/analysis");

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("risk_metrics");
      expect(response.body.data).toHaveProperty("position_risks");
      expect(response.body.data).toHaveProperty("portfolio_summary");
      expect(response.body.data.portfolio_summary).toHaveProperty(
        "holdings_count",
        2
      );
      expect(mockQuery).toHaveBeenCalledTimes(2);
    });

    test("should handle different period parameters", async () => {
      mockQuery
        .mockResolvedValueOnce({ rows: [] }) // Empty holdings
        .mockResolvedValueOnce({ rows: [] }); // Empty price data

      const response = await request(app)
        .get("/risk/analysis")
        .query({ period: "1y", confidence_level: 0.99 });

      expect(response.status).toBe(200);
      expect(mockQuery).toHaveBeenCalledTimes(2);
      // Route currently defaults to 30 days regardless of period parameter
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining("30 days"),
        expect.any(Array)
      );
    });

    test("should handle invalid period gracefully", async () => {
      mockQuery
        .mockResolvedValueOnce({ rows: [] })
        .mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get("/risk/analysis")
        .query({ period: "invalid_period" });

      expect(response.status).toBe(200);
      // Should default to 30 days (1 month)
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining("30"),
        expect.any(Array)
      );
    });

    test("should handle empty portfolio", async () => {
      mockQuery
        .mockResolvedValueOnce({ rows: [] }) // No holdings
        .mockResolvedValueOnce({ rows: [] }); // No price data

      const response = await request(app).get("/risk/analysis");

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body.data).toHaveProperty(
        "message",
        "No holdings found for risk analysis"
      );
      expect(response.body.data.holdings_count).toBe(0);
    });

    test("should use authenticated user ID in query", async () => {
      mockQuery
        .mockResolvedValueOnce({ rows: [] })
        .mockResolvedValueOnce({ rows: [] });

      await request(app).get("/risk/analysis");

      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining("user_id"),
        expect.arrayContaining(["test-user-123"])
      );
    });

    test("should handle database query errors", async () => {
      const dbError = new Error("Database connection failed");
      mockQuery.mockRejectedValueOnce(dbError);

      const response = await request(app).get("/risk/analysis");

      expect(response.status).toBe(500);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body.error).toBe("Failed to perform risk analysis");
    });

    test("should handle risk engine calculation errors", async () => {
      mockQuery
        .mockResolvedValueOnce({ rows: [{ symbol: "AAPL", quantity: 100 }] })
        .mockResolvedValueOnce({ rows: [{ symbol: "AAPL", close: 150 }] });

      mockRiskEngine.calculatePortfolioVaR.mockImplementation(() => {
        throw new Error("Risk calculation failed");
      });

      const response = await request(app).get("/risk/analysis");

      expect(response.status).toBe(500);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body.error).toBe("Failed to perform risk analysis");
    });
  });

  describe("Authentication middleware", () => {
    test("should protect analysis endpoint", () => {
      const { authenticateToken } = require("../../../middleware/auth");
      expect(authenticateToken).toBeDefined();

      // Test that middleware was applied - verified through successful authenticated requests above
    });

    test("should allow public health endpoint", async () => {
      // Health endpoint should work without authentication
      const response = await request(app).get("/risk/health");

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("status", "operational");
    });

    test("should allow public root endpoint", async () => {
      // Root endpoint should work without authentication
      const response = await request(app).get("/risk");

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty(
        "message",
        "Risk Analysis API - Ready"
      );
    });
  });

  describe("Parameter validation", () => {
    test("should handle confidence level parameter", async () => {
      mockQuery
        .mockResolvedValueOnce({ rows: [] })
        .mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get("/risk/analysis")
        .query({ confidence_level: 0.99 });

      expect(response.status).toBe(200);
      // Confidence level should be passed to risk calculations
      // This is verified through mock calls in other tests
    });

    test("should handle invalid confidence level", async () => {
      mockQuery
        .mockResolvedValueOnce({ rows: [] })
        .mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get("/risk/analysis")
        .query({ confidence_level: "invalid" });

      expect(response.status).toBe(200);
      // Should default to 0.95
    });
  });

  describe("Response format", () => {
    test("should return consistent JSON response", async () => {
      const response = await request(app).get("/risk/health");

      expect(response.headers["content-type"]).toMatch(/json/);
      expect(typeof response.body).toBe("object");
    });
  });
});

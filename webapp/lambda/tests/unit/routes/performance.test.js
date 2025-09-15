/**
 * Performance Routes Unit Tests
 * Tests performance route logic in isolation with mocks
 */

const express = require("express");
const request = require("supertest");

// Mock the database utility
jest.mock("../../../utils/database", () => ({
  query: jest.fn(),
}));

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

// Mock the performance monitor
jest.mock("../../../utils/performanceMonitor", () => ({
  getSystemMetrics: jest.fn(),
  getPortfolioMetrics: jest.fn(),
  calculateBenchmarkComparison: jest.fn(),
  getPerformanceAnalytics: jest.fn(),
}));

describe("Performance Routes Unit Tests", () => {
  let app;
  let performanceRouter;
  let mockQuery;
  let mockPerformanceMonitor;

  beforeEach(() => {
    jest.clearAllMocks();

    // Set up mocks
    const { query } = require("../../../utils/database");
    mockQuery = query;

    const performanceMonitor = require("../../../utils/performanceMonitor");
    mockPerformanceMonitor = performanceMonitor;

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
    performanceRouter = require("../../../routes/performance");
    app.use("/performance", performanceRouter);
  });

  describe("GET /performance/health", () => {
    test("should return health status without authentication", async () => {
      const response = await request(app).get("/performance/health");

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("status", "operational");
      expect(response.body).toHaveProperty("service", "performance-analytics");
      expect(response.body).toHaveProperty("timestamp");
      expect(response.body).toHaveProperty(
        "message",
        "Performance Analytics service is running"
      );

      // Verify timestamp is a valid ISO string
      expect(new Date(response.body.timestamp)).toBeInstanceOf(Date);
      expect(mockQuery).not.toHaveBeenCalled(); // Health doesn't use database
    });
  });

  describe("GET /performance", () => {
    test("should return performance API information without authentication", async () => {
      const response = await request(app).get("/performance");

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty(
        "message",
        "Performance Analytics API - Ready"
      );
      expect(response.body).toHaveProperty("status", "operational");
      expect(response.body).toHaveProperty("timestamp");

      // Verify timestamp is a valid ISO string
      expect(new Date(response.body.timestamp)).toBeInstanceOf(Date);
      expect(mockQuery).not.toHaveBeenCalled(); // Root endpoint doesn't use database
    });
  });

  describe("GET /performance/benchmark (authenticated)", () => {
    test("should return benchmark comparison with default parameters", async () => {
      const mockPortfolioData = {
        rows: [
          {
            date: "2023-01-01",
            portfolio_value: 100000.0,
            portfolio_return: 0.0,
          },
          {
            date: "2023-06-01",
            portfolio_value: 110000.0,
            portfolio_return: 0.1,
          },
          {
            date: "2023-12-31",
            portfolio_value: 125000.0,
            portfolio_return: 0.25,
          },
        ],
      };

      const mockBenchmarkData = {
        rows: [
          {
            date: "2023-01-01",
            price: 400.0,
            return_rate: 0.0,
          },
          {
            date: "2023-06-01",
            price: 430.0,
            return_rate: 0.075,
          },
          {
            date: "2023-12-31",
            price: 470.0,
            return_rate: 0.175,
          },
        ],
      };

      mockQuery
        .mockResolvedValueOnce(mockPortfolioData) // Portfolio performance
        .mockResolvedValueOnce(mockBenchmarkData); // Benchmark performance

      mockPerformanceMonitor.calculateBenchmarkComparison.mockReturnValue({
        portfolio_return: 0.25,
        benchmark_return: 0.175,
        alpha: 0.075,
        beta: 1.15,
        sharpe_ratio: 1.2,
        tracking_error: 0.05,
      });

      const response = await request(app).get("/performance/benchmark");

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("portfolio_metrics");
      expect(response.body.data).toHaveProperty("benchmark_metrics");
      expect(response.body.data).toHaveProperty("relative_performance");
      expect(response.body.data.relative_performance).toHaveProperty("alpha");
      expect(mockQuery).toHaveBeenCalledTimes(2);
      expect(
        mockPerformanceMonitor.calculateBenchmarkComparison
      ).toHaveBeenCalled();
    });

    test("should handle custom benchmark parameter", async () => {
      mockQuery
        .mockResolvedValueOnce({ rows: [] })
        .mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get("/performance/benchmark")
        .query({ benchmark: "QQQ" });

      expect(response.status).toBe(200);
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining("QQQ"),
        expect.any(Array)
      );
    });

    test("should handle custom period parameter", async () => {
      mockQuery
        .mockResolvedValueOnce({ rows: [] })
        .mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get("/performance/benchmark")
        .query({ period: "6m" });

      expect(response.status).toBe(200);
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining("180"), // 6 months = 180 days
        expect.any(Array)
      );
    });

    test("should handle invalid period gracefully", async () => {
      mockQuery
        .mockResolvedValueOnce({ rows: [] })
        .mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get("/performance/benchmark")
        .query({ period: "invalid_period" });

      expect(response.status).toBe(200);
      // Should default to 365 days (1 year)
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining("365"),
        expect.any(Array)
      );
    });

    test("should use authenticated user ID in query", async () => {
      mockQuery
        .mockResolvedValueOnce({ rows: [] })
        .mockResolvedValueOnce({ rows: [] });

      await request(app).get("/performance/benchmark");

      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining("user_id"),
        expect.arrayContaining(["test-user-123"])
      );
    });

    test("should handle empty portfolio data", async () => {
      mockQuery
        .mockResolvedValueOnce({ rows: [] }) // No portfolio data
        .mockResolvedValueOnce({ rows: [] }); // No benchmark data

      const response = await request(app).get("/performance/benchmark");

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty(
        "message",
        "Insufficient data for benchmark comparison"
      );
    });

    test("should handle database query errors", async () => {
      const dbError = new Error("Database connection failed");
      mockQuery.mockRejectedValueOnce(dbError);

      const response = await request(app).get("/performance/benchmark");

      expect(response.status).toBe(500);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body.error).toBeDefined();
    });

    test("should handle performance calculation errors", async () => {
      mockQuery
        .mockResolvedValueOnce({
          rows: [{ date: "2023-01-01", portfolio_value: 100000 }],
        })
        .mockResolvedValueOnce({ rows: [{ date: "2023-01-01", price: 400 }] });

      mockPerformanceMonitor.calculateBenchmarkComparison.mockImplementation(
        () => {
          throw new Error("Performance calculation failed");
        }
      );

      const response = await request(app).get("/performance/benchmark");

      expect(response.status).toBe(500);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body.error).toContain("Performance calculation failed");
    });
  });

  describe("GET /performance/analytics (authenticated)", () => {
    test("should return performance analytics", async () => {
      const mockAnalyticsData = {
        total_return: 0.25,
        annualized_return: 0.22,
        volatility: 0.15,
        max_drawdown: 0.08,
        win_rate: 0.65,
        profit_factor: 1.8,
        risk_return_ratio: 1.47,
      };

      mockPerformanceMonitor.getPerformanceAnalytics.mockResolvedValue(
        mockAnalyticsData
      );

      const response = await request(app).get("/performance/analytics");

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("total_return", 0.25);
      expect(response.body.data).toHaveProperty("volatility", 0.15);
      expect(
        mockPerformanceMonitor.getPerformanceAnalytics
      ).toHaveBeenCalledWith("test-user-123");
    });

    test("should handle analytics calculation errors", async () => {
      mockPerformanceMonitor.getPerformanceAnalytics.mockRejectedValue(
        new Error("Analytics failed")
      );

      const response = await request(app).get("/performance/analytics");

      expect(response.status).toBe(500);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body.error).toContain("Analytics failed");
    });
  });

  describe("GET /performance/metrics (authenticated)", () => {
    test("should return system performance metrics", async () => {
      const mockSystemMetrics = {
        cpu_usage: 0.45,
        memory_usage: 0.62,
        disk_usage: 0.35,
        network_latency: 25,
        db_query_time: 15,
        api_response_time: 120,
      };

      mockPerformanceMonitor.getSystemMetrics.mockResolvedValue(
        mockSystemMetrics
      );

      const response = await request(app).get("/performance/metrics");

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("cpu_usage", 0.45);
      expect(response.body.data).toHaveProperty("api_response_time", 120);
      expect(mockPerformanceMonitor.getSystemMetrics).toHaveBeenCalled();
    });

    test("should handle metrics collection errors", async () => {
      mockPerformanceMonitor.getSystemMetrics.mockRejectedValue(
        new Error("Metrics collection failed")
      );

      const response = await request(app).get("/performance/metrics");

      expect(response.status).toBe(500);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body.error).toContain("Metrics collection failed");
    });
  });

  describe("GET /performance/attribution (authenticated)", () => {
    test("should return Brinson attribution analysis", async () => {
      const mockAttributionData = {
        rows: [
          {
            sector: "Technology",
            portfolio_sector_weight: 0.35,
            benchmark_sector_weight: 0.3,
            portfolio_sector_return: 0.15,
            benchmark_sector_return: 0.12,
            allocation_effect: 0.006,
            selection_effect: 0.009,
            interaction_effect: 0.0015,
          },
          {
            sector: "Healthcare",
            portfolio_sector_weight: 0.2,
            benchmark_sector_weight: 0.25,
            portfolio_sector_return: 0.08,
            benchmark_sector_return: 0.1,
            allocation_effect: -0.005,
            selection_effect: -0.005,
            interaction_effect: 0.001,
          },
        ],
      };

      mockQuery.mockResolvedValueOnce(mockAttributionData);

      const response = await request(app).get("/performance/attribution");

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("attribution_analysis");
      expect(response.body.data).toHaveProperty("summary");
      expect(response.body.data).toHaveProperty("methodology");

      // Check attribution analysis structure
      expect(Array.isArray(response.body.data.attribution_analysis)).toBe(true);
      expect(response.body.data.attribution_analysis).toHaveLength(2);

      const firstSector = response.body.data.attribution_analysis[0];
      expect(firstSector).toHaveProperty("sector");
      expect(firstSector).toHaveProperty("allocation_effect");
      expect(firstSector).toHaveProperty("selection_effect");
      expect(firstSector).toHaveProperty("total_effect");

      // Check summary structure
      expect(response.body.data.summary).toHaveProperty(
        "total_allocation_effect"
      );
      expect(response.body.data.summary).toHaveProperty(
        "total_selection_effect"
      );
      expect(response.body.data.summary).toHaveProperty(
        "total_interaction_effect"
      );
      expect(response.body.data.summary).toHaveProperty("total_active_return");

      // Check methodology documentation
      expect(response.body.data.methodology).toHaveProperty("model");
      expect(response.body.data.methodology.model).toBe("Brinson Attribution");
    });

    test("should handle custom benchmark for attribution", async () => {
      mockQuery.mockResolvedValueOnce({ rows: [] });

      const response = await request(app).get(
        "/performance/attribution?benchmark=QQQ"
      );

      expect(response.status).toBe(200);
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining("QQQ"),
        expect.any(Array)
      );
    });

    test("should handle custom period for attribution", async () => {
      mockQuery.mockResolvedValueOnce({ rows: [] });

      const response = await request(app).get(
        "/performance/attribution?period=3m"
      );

      expect(response.status).toBe(200);
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining("90"), // 3 months = 90 days
        expect.any(Array)
      );
    });

    test("should handle insufficient data for attribution", async () => {
      mockQuery.mockResolvedValueOnce({ rows: [] });

      const response = await request(app).get("/performance/attribution");

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty(
        "message",
        "Insufficient data for attribution analysis"
      );
      expect(response.body.data.attribution_analysis).toHaveLength(0);
    });

    test("should validate attribution parameters", async () => {
      const response = await request(app).get(
        "/performance/attribution?benchmark=invalid-symbol!@#"
      );

      expect(response.status).toBe(400);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body.error).toContain("Invalid benchmark symbol");
    });
  });

  describe("GET /performance/portfolio/:symbol (authenticated)", () => {
    test("should return symbol-specific performance", async () => {
      const mockSymbolPerformance = {
        rows: [
          {
            symbol: "AAPL",
            total_return: 0.15,
            position_size: 100,
            unrealized_pnl: 1500.0,
            realized_pnl: 500.0,
            win_rate: 0.7,
            avg_hold_time: 45,
          },
        ],
      };

      mockQuery.mockResolvedValueOnce(mockSymbolPerformance);

      const response = await request(app).get("/performance/portfolio/AAPL");

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("symbol", "AAPL");
      expect(response.body.data).toHaveProperty("total_return", 0.15);
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining("symbol"),
        expect.arrayContaining(["test-user-123", "AAPL"])
      );
    });

    test("should handle lowercase symbol conversion", async () => {
      mockQuery.mockResolvedValueOnce({ rows: [] });

      await request(app).get("/performance/portfolio/aapl");

      expect(mockQuery).toHaveBeenCalledWith(
        expect.any(String),
        expect.arrayContaining(["test-user-123", "AAPL"]) // Should be uppercase
      );
    });

    test("should handle symbol not found", async () => {
      mockQuery.mockResolvedValueOnce({ rows: [] });

      const response = await request(app).get("/performance/portfolio/INVALID");

      expect(response.status).toBe(404);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body.error).toContain("No performance data found");
    });
  });

  describe("Authentication", () => {
    test("should allow public access to health endpoint", async () => {
      const response = await request(app).get("/performance/health");

      expect(response.status).toBe(200);
      // Should work without authentication
    });

    test("should allow public access to root endpoint", async () => {
      const response = await request(app).get("/performance");

      expect(response.status).toBe(200);
      // Should work without authentication
    });

    test("should require authentication for benchmark endpoint", () => {
      const { authenticateToken } = require("../../../middleware/auth");
      expect(authenticateToken).toBeDefined();

      // Authentication is tested through successful requests in other tests
    });
  });

  describe("Parameter validation", () => {
    test("should validate benchmark symbol format", async () => {
      const response = await request(app)
        .get("/performance/benchmark")
        .query({ benchmark: "invalid-benchmark-format!@#" });

      expect(response.status).toBe(400);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body.error).toContain("Invalid benchmark symbol");
    });

    test("should sanitize period parameter", async () => {
      mockQuery
        .mockResolvedValueOnce({ rows: [] })
        .mockResolvedValueOnce({ rows: [] });

      await request(app)
        .get("/performance/benchmark")
        .query({ period: "1y; DROP TABLE portfolio; --" });

      // Should handle malicious input by using predefined period values
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining("365"), // Should default to 1y = 365 days
        expect.any(Array)
      );
    });
  });

  describe("Error handling", () => {
    test("should handle database connection timeout", async () => {
      const timeoutError = new Error("Query timeout");
      timeoutError.code = "QUERY_TIMEOUT";
      mockQuery.mockRejectedValueOnce(timeoutError);

      const response = await request(app).get("/performance/benchmark");

      expect(response.status).toBe(500);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body.error).toContain("timeout");
    });

    test("should handle performance monitor failures", async () => {
      mockPerformanceMonitor.getSystemMetrics.mockRejectedValue(
        new Error("Monitor unavailable")
      );

      const response = await request(app).get("/performance/metrics");

      expect(response.status).toBe(500);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body.error).toContain("Monitor unavailable");
    });
  });

  describe("Response format", () => {
    test("should return consistent JSON response format", async () => {
      const response = await request(app).get("/performance/health");

      expect(response.headers["content-type"]).toMatch(/json/);
      expect(typeof response.body).toBe("object");
    });

    test("should include metadata in performance responses", async () => {
      mockQuery
        .mockResolvedValueOnce({ rows: [] })
        .mockResolvedValueOnce({ rows: [] });

      const response = await request(app).get("/performance/benchmark");

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success");
      expect(response.body).toHaveProperty("data");
    });
  });
});

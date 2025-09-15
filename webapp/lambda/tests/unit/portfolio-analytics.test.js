/**
 * Advanced Portfolio Analytics Unit Tests
 * Tests for enhanced financial metrics and risk calculations implemented in portfolio.js
 */

const request = require("supertest");
const express = require("express");

// Import the portfolio router
const portfolioRouter = require("../../routes/portfolio");

// Mock dependencies
jest.mock("../../utils/database", () => ({
  query: jest.fn(),
}));

jest.mock("../../utils/logger", () => ({
  info: jest.fn(),
  warn: jest.fn(),
  error: jest.fn(),
}));

jest.mock("../../middleware/auth", () => ({
  authenticateToken: (req, res, next) => {
    req.user = { sub: "test-user-123", id: "test-user-123" };
    next();
  },
}));

const { query } = require("../../utils/database");

describe("Advanced Portfolio Analytics Tests", () => {
  let app;

  beforeAll(() => {
    app = express();
    app.use(express.json());

    // Add response formatter middleware
    app.use((req, res, next) => {
      res.success = (data, message) =>
        res.json({ success: true, data, message });
      res.error = (error, code = 500) =>
        res.status(code).json({ success: false, error });
      next();
    });

    app.use("/portfolio", portfolioRouter);
  });

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe("Enhanced Annualized Return Calculation", () => {
    it("should calculate CAGR with proper date-based calculation", async () => {
      const mockPerformanceData = {
        rows: [
          {
            total_value: 100000,
            total_pnl_percent: 0,
            date: "2023-01-01",
            created_at: "2023-01-01T00:00:00Z",
          },
          {
            total_value: 120000,
            total_pnl_percent: 20,
            date: "2024-01-01",
            created_at: "2024-01-01T00:00:00Z",
          },
        ],
      };

      query.mockResolvedValue(mockPerformanceData);

      const response = await request(app)
        .get("/portfolio/performance")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.metrics).toHaveProperty("annualized_return");

      // Should calculate proper CAGR: (120000/100000)^(1/1) - 1 = 20%
      const annualizedReturn = response.body.metrics.annualized_return;
      expect(annualizedReturn).toBeCloseTo(20, 0); // Within 1% of 20%
    });

    it("should handle partial year calculations correctly", async () => {
      const mockPerformanceData = {
        rows: [
          {
            total_value: 100000,
            total_pnl_percent: 0,
            date: "2024-01-01",
            created_at: "2024-01-01T00:00:00Z",
          },
          {
            total_value: 110000,
            total_pnl_percent: 10,
            date: "2024-07-01", // 6 months later
            created_at: "2024-07-01T00:00:00Z",
          },
        ],
      };

      query.mockResolvedValue(mockPerformanceData);

      const response = await request(app)
        .get("/portfolio/performance")
        .expect(200);

      const annualizedReturn = response.body.metrics.annualized_return;
      // 10% return over ~0.5 years should annualize to ~21%
      expect(annualizedReturn).toBeGreaterThan(15);
      expect(annualizedReturn).toBeLessThan(25);
    });

    it("should fallback gracefully with insufficient data", async () => {
      const mockSingleDataPoint = {
        rows: [
          {
            total_value: 100000,
            total_pnl_percent: 5,
            date: "2024-01-01",
          },
        ],
      };

      query.mockResolvedValue(mockSingleDataPoint);

      const response = await request(app)
        .get("/portfolio/performance")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.metrics.annualized_return).toBe(5); // Should fallback to percentage
    });
  });

  describe("Advanced Benchmark Metrics", () => {
    it("should calculate correlation, beta, and alpha", async () => {
      const mockPortfolioData = {
        rows: [
          { total_pnl_percent: 5.2, date: "2024-01-01" },
          { total_pnl_percent: 7.8, date: "2024-01-02" },
          { total_pnl_percent: 6.1, date: "2024-01-03" },
          { total_pnl_percent: 8.9, date: "2024-01-04" },
          { total_pnl_percent: 7.3, date: "2024-01-05" },
        ],
      };

      const mockBenchmarkData = {
        rows: [
          { close: 100, date: "2024-01-01" },
          { close: 102, date: "2024-01-02" }, // 2% return
          { close: 101, date: "2024-01-03" }, // -1% return
          { close: 104, date: "2024-01-04" }, // 3% return
          { close: 103, date: "2024-01-05" }, // -1% return
        ],
      };

      query
        .mockResolvedValueOnce(mockPortfolioData)
        .mockResolvedValueOnce(mockBenchmarkData);

      const response = await request(app)
        .get("/portfolio/benchmark?benchmark=SPY")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.benchmark_metrics).toBeDefined();

      const metrics = response.body.data.benchmark_metrics;
      expect(metrics).toHaveProperty("correlation");
      expect(metrics).toHaveProperty("beta");
      expect(metrics).toHaveProperty("alpha");
      expect(metrics).toHaveProperty("tracking_error");
      expect(metrics).toHaveProperty("information_ratio");
      expect(metrics).toHaveProperty("excess_return");

      // Validate ranges
      expect(metrics.correlation).toBeGreaterThanOrEqual(-1);
      expect(metrics.correlation).toBeLessThanOrEqual(1);
      expect(typeof metrics.beta).toBe("number");
      expect(typeof metrics.alpha).toBe("number");
    });

    it("should handle mismatched data lengths", async () => {
      const mockPortfolioData = {
        rows: [
          { total_pnl_percent: 5.2, date: "2024-01-01" },
          { total_pnl_percent: 7.8, date: "2024-01-02" },
        ],
      };

      const mockBenchmarkData = {
        rows: [
          { close: 100, date: "2024-01-01" },
          { close: 102, date: "2024-01-02" },
          { close: 101, date: "2024-01-03" },
          { close: 104, date: "2024-01-04" },
        ],
      };

      query
        .mockResolvedValueOnce(mockPortfolioData)
        .mockResolvedValueOnce(mockBenchmarkData);

      const response = await request(app)
        .get("/portfolio/benchmark?benchmark=SPY")
        .expect(200);

      // Should use minimum length and still calculate metrics
      expect(response.body.success).toBe(true);
      expect(response.body.data.benchmark_metrics).toBeDefined();
    });

    it("should return null metrics for insufficient data", async () => {
      const mockEmptyData = { rows: [] };

      query
        .mockResolvedValueOnce(mockEmptyData)
        .mockResolvedValueOnce(mockEmptyData);

      const response = await request(app)
        .get("/portfolio/benchmark?benchmark=SPY")
        .expect(200);

      const metrics = response.body.data.benchmark_metrics;
      expect(metrics.correlation).toBeNull();
      expect(metrics.beta).toBeNull();
      expect(metrics.alpha).toBeNull();
    });
  });

  describe("Advanced Risk Metrics", () => {
    it("should calculate Value at Risk (VaR)", async () => {
      const mockReturnsData = {
        rows: [
          { daily_return: 0.02 }, // 2%
          { daily_return: -0.015 }, // -1.5%
          { daily_return: 0.008 }, // 0.8%
          { daily_return: -0.012 }, // -1.2%
          { daily_return: 0.025 }, // 2.5%
          { daily_return: -0.03 }, // -3% (worst case)
          { daily_return: 0.01 }, // 1%
          { daily_return: -0.008 }, // -0.8%
          { daily_return: 0.015 }, // 1.5%
          { daily_return: 0.005 }, // 0.5%
        ],
      };

      query.mockResolvedValue(mockReturnsData);

      const response = await request(app)
        .get("/portfolio/risk-metrics")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.risk_metrics).toBeDefined();

      const riskMetrics = response.body.data.risk_metrics;
      expect(riskMetrics).toHaveProperty("value_at_risk");
      expect(riskMetrics).toHaveProperty("expected_shortfall");
      expect(riskMetrics).toHaveProperty("sortino_ratio");
      expect(riskMetrics).toHaveProperty("calmar_ratio");
      expect(riskMetrics).toHaveProperty("concentration_risk");

      // VaR should be positive (representing potential loss)
      expect(riskMetrics.value_at_risk.var_95).toBeGreaterThan(0);
      expect(riskMetrics.value_at_risk.var_99).toBeGreaterThan(0);
      expect(riskMetrics.value_at_risk.var_99).toBeGreaterThan(
        riskMetrics.value_at_risk.var_95
      );
    });

    it("should calculate Sortino ratio (downside risk)", async () => {
      const mockReturnsData = {
        rows: [
          { daily_return: 0.02 }, // Positive
          { daily_return: -0.015 }, // Negative (downside)
          { daily_return: 0.008 }, // Positive
          { daily_return: -0.012 }, // Negative (downside)
          { daily_return: 0.025 }, // Positive
        ],
      };

      query.mockResolvedValue(mockReturnsData);

      const response = await request(app)
        .get("/portfolio/risk-metrics")
        .expect(200);

      const sortinoRatio = response.body.data.risk_metrics.sortino_ratio;
      expect(typeof sortinoRatio).toBe("number");
      expect(sortinoRatio).toBeGreaterThan(0); // Should be positive for positive mean return
    });

    it("should calculate concentration risk (Herfindahl-Hirschman Index)", async () => {
      const mockHoldingsData = {
        rows: [
          { symbol: "AAPL", percentage_allocation: 40 }, // High concentration
          { symbol: "MSFT", percentage_allocation: 30 },
          { symbol: "GOOGL", percentage_allocation: 20 },
          { symbol: "TSLA", percentage_allocation: 10 },
        ],
      };

      query.mockResolvedValue(mockHoldingsData);

      const response = await request(app)
        .get("/portfolio/risk-metrics")
        .expect(200);

      const concentrationRisk =
        response.body.data.risk_metrics.concentration_risk;
      expect(concentrationRisk).toBeDefined();
      expect(concentrationRisk.hhi).toBeGreaterThan(0);
      expect(concentrationRisk.hhi).toBeLessThanOrEqual(1);

      // With the test data (40%, 30%, 20%, 10%), HHI should be high
      expect(concentrationRisk.hhi).toBeGreaterThan(0.25);
      expect(concentrationRisk.risk_level).toMatch(/^(low|medium|high)$/);
    });
  });

  describe("Portfolio Beta Calculation", () => {
    it("should calculate portfolio beta from holdings", async () => {
      const mockHoldingsData = {
        rows: [
          { symbol: "AAPL", percentage_allocation: 50, sector: "Technology" },
          { symbol: "JPM", percentage_allocation: 30, sector: "Financial" },
          { symbol: "JNJ", percentage_allocation: 20, sector: "Healthcare" },
        ],
      };

      query.mockResolvedValue(mockHoldingsData);

      const response = await request(app)
        .get("/portfolio/risk-metrics")
        .expect(200);

      const portfolioBeta = response.body.data.risk_metrics.portfolio_beta;
      expect(typeof portfolioBeta).toBe("number");
      expect(portfolioBeta).toBeGreaterThan(0.5);
      expect(portfolioBeta).toBeLessThan(2.0);
    });

    it("should use sector-based beta estimates", async () => {
      const mockTechHeavyPortfolio = {
        rows: [
          { symbol: "AAPL", percentage_allocation: 40, sector: "Technology" },
          { symbol: "MSFT", percentage_allocation: 30, sector: "Technology" },
          { symbol: "GOOGL", percentage_allocation: 30, sector: "Technology" },
        ],
      };

      query.mockResolvedValue(mockTechHeavyPortfolio);

      const response = await request(app)
        .get("/portfolio/risk-metrics")
        .expect(200);

      const portfolioBeta = response.body.data.risk_metrics.portfolio_beta;
      // Tech-heavy portfolio should have higher beta
      expect(portfolioBeta).toBeGreaterThan(1.0);
    });

    it("should handle unknown sectors gracefully", async () => {
      const mockMixedPortfolio = {
        rows: [
          {
            symbol: "UNKNOWN1",
            percentage_allocation: 50,
            sector: "Unknown Sector",
          },
          { symbol: "UNKNOWN2", percentage_allocation: 50, sector: null },
        ],
      };

      query.mockResolvedValue(mockMixedPortfolio);

      const response = await request(app)
        .get("/portfolio/risk-metrics")
        .expect(200);

      // Should still calculate beta using default values
      expect(response.body.success).toBe(true);
      expect(typeof response.body.data.risk_metrics.portfolio_beta).toBe(
        "number"
      );
    });
  });

  describe("Statistical Helper Functions", () => {
    it("should calculate correlation correctly", async () => {
      // Test with performance data that should have correlation
      const mockPortfolioData = {
        rows: [
          { total_pnl_percent: 2, date: "2024-01-01" },
          { total_pnl_percent: 4, date: "2024-01-02" },
          { total_pnl_percent: 6, date: "2024-01-03" },
          { total_pnl_percent: 8, date: "2024-01-04" },
        ],
      };

      const mockBenchmarkData = {
        rows: [
          { close: 100, date: "2024-01-01" },
          { close: 102, date: "2024-01-02" }, // 2% return
          { close: 104, date: "2024-01-03" }, // ~2% return
          { close: 106, date: "2024-01-04" }, // ~2% return
        ],
      };

      query
        .mockResolvedValueOnce(mockPortfolioData)
        .mockResolvedValueOnce(mockBenchmarkData);

      const response = await request(app)
        .get("/portfolio/benchmark?benchmark=SPY")
        .expect(200);

      const correlation = response.body.data.benchmark_metrics.correlation;
      expect(correlation).not.toBeNull();
      expect(correlation).toBeGreaterThanOrEqual(-1);
      expect(correlation).toBeLessThanOrEqual(1);
    });

    it("should calculate standard deviation", async () => {
      const mockVolatileReturns = {
        rows: [
          { daily_return: 0.05 }, // High volatility data
          { daily_return: -0.08 },
          { daily_return: 0.12 },
          { daily_return: -0.06 },
          { daily_return: 0.09 },
        ],
      };

      query.mockResolvedValue(mockVolatileReturns);

      const response = await request(app)
        .get("/portfolio/risk-metrics")
        .expect(200);

      // Standard deviation should be calculated and included in various metrics
      expect(response.body.data.risk_metrics.volatility).toBeDefined();
      expect(typeof response.body.data.risk_metrics.volatility).toBe("number");
      expect(response.body.data.risk_metrics.volatility).toBeGreaterThan(0);
    });
  });

  describe("Error Handling and Edge Cases", () => {
    it("should handle database errors gracefully", async () => {
      query.mockRejectedValue(new Error("Database connection failed"));

      const response = await request(app)
        .get("/portfolio/risk-metrics")
        .expect(500);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain("error");
    });

    it("should handle empty portfolio data", async () => {
      query.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get("/portfolio/performance")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.metrics.annualized_return).toBe(0);
    });

    it("should handle null/undefined values in data", async () => {
      const mockDataWithNulls = {
        rows: [
          { daily_return: null, date: "2024-01-01" },
          { daily_return: undefined, date: "2024-01-02" },
          { daily_return: 0.02, date: "2024-01-03" },
          { daily_return: -0.01, date: "2024-01-04" },
        ],
      };

      query.mockResolvedValue(mockDataWithNulls);

      const response = await request(app)
        .get("/portfolio/risk-metrics")
        .expect(200);

      // Should filter out null/undefined values and still calculate metrics
      expect(response.body.success).toBe(true);
      expect(response.body.data.risk_metrics).toBeDefined();
    });

    it("should handle extreme values without crashing", async () => {
      const mockExtremeData = {
        rows: [
          { daily_return: 100 }, // 10000% return (extreme outlier)
          { daily_return: -0.5 }, // -50% return
          { daily_return: 0.02 }, // Normal return
          { daily_return: -0.01 }, // Normal return
        ],
      };

      query.mockResolvedValue(mockExtremeData);

      const response = await request(app)
        .get("/portfolio/risk-metrics")
        .expect(200);

      expect(response.body.success).toBe(true);
      // Should handle extreme values without breaking
      expect(response.body.data.risk_metrics).toBeDefined();
    });

    it("should validate input parameters", async () => {
      query.mockResolvedValue({ rows: [] });

      // Test invalid confidence level for VaR
      const response = await request(app)
        .get("/portfolio/risk-metrics?confidence=invalid")
        .expect(200);

      // Should use default confidence level
      expect(response.body.success).toBe(true);
    });
  });

  describe("Performance Metrics Integration", () => {
    it("should include risk-adjusted returns", async () => {
      const mockPerformanceData = {
        rows: [
          { daily_return: 0.01, date: "2024-01-01" },
          { daily_return: 0.02, date: "2024-01-02" },
          { daily_return: -0.01, date: "2024-01-03" },
          { daily_return: 0.015, date: "2024-01-04" },
        ],
      };

      query.mockResolvedValue(mockPerformanceData);

      const response = await request(app)
        .get("/portfolio/performance")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.metrics).toHaveProperty("sharpe_ratio");
      expect(response.body.metrics).toHaveProperty("volatility");
      expect(response.body.metrics).toHaveProperty("max_drawdown");

      // Risk-adjusted metrics should be numbers
      expect(typeof response.body.metrics.sharpe_ratio).toBe("number");
      expect(typeof response.body.metrics.volatility).toBe("number");
      expect(typeof response.body.metrics.max_drawdown).toBe("number");
    });

    it("should calculate maximum drawdown correctly", async () => {
      const mockEquityCurve = {
        rows: [
          { total_value: 100000, date: "2024-01-01" },
          { total_value: 110000, date: "2024-01-02" }, // +10%
          { total_value: 105000, date: "2024-01-03" }, // -4.5% from peak
          { total_value: 95000, date: "2024-01-04" }, // -13.6% from peak (max drawdown)
          { total_value: 108000, date: "2024-01-05" }, // Recovery
        ],
      };

      query.mockResolvedValue(mockEquityCurve);

      const response = await request(app)
        .get("/portfolio/performance")
        .expect(200);

      const maxDrawdown = response.body.metrics.max_drawdown;
      expect(maxDrawdown).toBeGreaterThan(0.1); // Should be around 13.6%
      expect(maxDrawdown).toBeLessThan(0.2);
    });
  });

  describe("Benchmark Integration", () => {
    it("should support multiple benchmark symbols", async () => {
      const mockPortfolioData = {
        rows: [{ total_pnl_percent: 5, date: "2024-01-01" }],
      };
      const mockBenchmarkData = { rows: [{ close: 100, date: "2024-01-01" }] };

      query
        .mockResolvedValueOnce(mockPortfolioData)
        .mockResolvedValueOnce(mockBenchmarkData);

      const benchmarks = ["SPY", "QQQ", "IWM"];

      for (const benchmark of benchmarks) {
        const response = await request(app)
          .get(`/portfolio/benchmark?benchmark=${benchmark}`)
          .expect(200);

        expect(response.body.success).toBe(true);
        expect(response.body.data.benchmark_symbol).toBe(benchmark);
      }
    });

    it("should handle custom benchmark periods", async () => {
      const mockPortfolioData = {
        rows: [{ total_pnl_percent: 5, date: "2024-01-01" }],
      };
      const mockBenchmarkData = { rows: [{ close: 100, date: "2024-01-01" }] };

      query
        .mockResolvedValueOnce(mockPortfolioData)
        .mockResolvedValueOnce(mockBenchmarkData);

      const response = await request(app)
        .get("/portfolio/benchmark?benchmark=SPY&period=1y")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.time_period).toBeDefined();
    });
  });
});

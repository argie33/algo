const request = require("supertest");
const express = require("express");
const riskRouter = require("../../../routes/risk");

// Mock dependencies with explicit implementations
jest.mock("../../../utils/database", () => ({
  query: jest.fn(),
  initializeDatabase: jest.fn(),
  healthCheck: jest.fn(),
}));

jest.mock("../../../middleware/auth", () => ({
  authenticateToken: jest.fn(),
}));

// Mock RiskEngine with factory pattern
jest.mock("../../../utils/riskEngine", () => {
  const mockMethods = {
    calculateVaR: jest.fn(),
    performStressTest: jest.fn(),
    calculateCorrelationMatrix: jest.fn(),
    calculatePortfolioRisk: jest.fn(),
    startRealTimeMonitoring: jest.fn(),
    stopRealTimeMonitoring: jest.fn(),
    getMonitoringStatus: jest.fn(),
  };
  
  return jest.fn().mockImplementation(() => mockMethods);
});

const { query } = require("../../../utils/database");
const RiskEngine = require("../../../utils/riskEngine");
const { authenticateToken } = require("../../../middleware/auth");

describe("Risk Routes", () => {
  let app;
  let mockRiskEngineInstance;

  beforeEach(() => {
    app = express();
    app.use(express.json());
    app.use("/risk", riskRouter);

    // Get mock instance - create new RiskEngine and it returns our mock
    mockRiskEngineInstance = new RiskEngine();

    // Mock authentication middleware
    authenticateToken.mockImplementation((req, res, next) => {
      req.user = { sub: "test-user-123" };
      next();
    });

    jest.clearAllMocks();
  });

  describe("GET /risk/health", () => {
    test("should return operational status", async () => {
      const response = await request(app).get("/risk/health").expect(200);

      expect(response.body).toEqual({
        success: true,
        status: "operational",
        service: "risk-analysis",
        timestamp: expect.any(String),
        message: "Risk Analysis service is running",
      });

      // Validate timestamp format
      expect(new Date(response.body.timestamp)).toBeInstanceOf(Date);
    });

    test("should not require authentication", async () => {
      // Should work without authentication
      await request(app).get("/risk/health").expect(200);
    });
  });

  describe("GET /risk/", () => {
    test("should return API ready message", async () => {
      const response = await request(app).get("/risk/").expect(200);

      expect(response.body).toEqual({
        success: true,
        message: "Risk Analysis API - Ready",
        timestamp: expect.any(String),
        status: "operational",
      });
    });

    test("should be a public endpoint", async () => {
      // Should work without authentication
      await request(app).get("/risk/").expect(200);
    });
  });

  describe("GET /risk/portfolio/:portfolioId", () => {
    const mockPortfolioData = {
      rows: [{ id: "portfolio-123" }],
    };

    const _mockRiskMetrics = {
      var_95: 0.025,
      var_99: 0.045,
      expected_shortfall: 0.055,
      volatility: 0.18,
      beta: 1.2,
      sharpe_ratio: 1.5,
      max_drawdown: -0.12,
      correlation_metrics: {},
    };

    test("should return portfolio risk metrics", async () => {
      const mockRiskMetrics = {
        overallRisk: "moderate",
        riskScore: 0.65,
        concentrationRisk: 0.15,
        volatilityRisk: 0.25,
        correlationRisk: 0.35,
        recommendations: ["Consider diversification"]
      };

      query.mockResolvedValue(mockPortfolioData);
      mockRiskEngineInstance.calculatePortfolioRisk.mockResolvedValue(mockRiskMetrics);

      const response = await request(app)
        .get("/risk/portfolio/portfolio-123")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
      expect(response.body.data.overallRisk).toBeDefined();
      expect(response.body.data.riskScore).toBeDefined();
      expect(response.body.data.concentrationRisk).toBeDefined();
      expect(response.body.data.volatilityRisk).toBeDefined();
    });

    test("should handle custom parameters", async () => {
      const mockRiskMetrics = {
        overallRisk: "high",
        riskScore: 0.85,
        concentrationRisk: 0.25,
        volatilityRisk: 0.35,
        correlationRisk: 0.45,
        recommendations: ["Reduce concentration risk"]
      };

      query.mockResolvedValue(mockPortfolioData);
      mockRiskEngineInstance.calculatePortfolioRisk.mockResolvedValue(mockRiskMetrics);

      const response = await request(app)
        .get("/risk/portfolio/portfolio-123?timeframe=6M&confidence_level=0.99")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
    });

    test("should return 404 for non-existent portfolio", async () => {
      query.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get("/risk/portfolio/non-existent")
        .expect(404);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("Portfolio not found");
    });

    test("should handle database errors", async () => {
      query.mockRejectedValue(new Error("Database connection failed"));

      const response = await request(app)
        .get("/risk/portfolio/portfolio-123")
        .expect(500);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("Failed to calculate portfolio risk");
    });
  });

  describe("GET /risk/var/:portfolioId", () => {
    const mockPortfolioData = {
      rows: [{ id: "portfolio-123" }],
    };

    const mockVarAnalysis = {
      historical_var: 0.025,
      parametric_var: 0.023,
      monte_carlo_var: 0.027,
      expected_shortfall: 0.035,
      confidence_level: 0.95,
      time_horizon: 1,
      lookback_days: 252,
    };

    test("should return VaR analysis", async () => {
      query.mockResolvedValue(mockPortfolioData);
      mockRiskEngineInstance.calculateVaR.mockResolvedValue(mockVarAnalysis);

      const response = await request(app)
        .get("/risk/var/portfolio-123")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toEqual(mockVarAnalysis);
      expect(mockRiskEngineInstance.calculateVaR).toHaveBeenCalledWith(
        "portfolio-123",
        "historical",
        0.95,
        1,
        252
      );
    });

    test("should handle custom VaR parameters", async () => {
      query.mockResolvedValue(mockPortfolioData);
      mockRiskEngineInstance.calculateVaR.mockResolvedValue(mockVarAnalysis);

      await request(app)
        .get(
          "/risk/var/portfolio-123?method=monte_carlo&confidence_level=0.99&time_horizon=5&lookback_days=500"
        )
        .expect(200);

      expect(mockRiskEngineInstance.calculateVaR).toHaveBeenCalledWith(
        "portfolio-123",
        "monte_carlo",
        0.99,
        5,
        500
      );
    });

    test("should return 404 for non-existent portfolio", async () => {
      query.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get("/risk/var/non-existent")
        .expect(404);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("Portfolio not found");
    });
  });

  describe("POST /risk/stress-test/:portfolioId", () => {
    const mockPortfolioData = {
      rows: [{ id: "portfolio-123" }],
    };

    const mockStressTestResults = {
      portfolioId: "portfolio-123",
      shockMagnitude: 0.2,
      correlationAdjustment: true,
      scenarios: [
        {
          scenario: "Market Shock",
          impact: -19540.20143530528,
          duration: "9 days",
          recovery: "83 days",
          probability: 0.08384342245266004,
        },
      ],
      overallImpact: -19540.20143530528,
      timestamp: "2025-08-21T19:09:23.522Z",
    };

    test("should perform stress test", async () => {
      query.mockResolvedValue(mockPortfolioData);
      mockRiskEngineInstance.performStressTest.mockResolvedValue(mockStressTestResults);

      const requestBody = {
        scenarios: ["market_crash", "interest_rate_spike"],
        shock_magnitude: 0.2,
        correlation_adjustment: true,
      };

      const response = await request(app)
        .post("/risk/stress-test/portfolio-123")
        .send(requestBody)
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toEqual(mockStressTestResults);
      expect(mockRiskEngineInstance.performStressTest).toHaveBeenCalledWith(
        "portfolio-123",
        ["market_crash", "interest_rate_spike"],
        0.2,
        true
      );
    });

    test("should handle default parameters", async () => {
      query.mockResolvedValue(mockPortfolioData);
      mockRiskEngineInstance.performStressTest.mockResolvedValue(mockStressTestResults);

      await request(app)
        .post("/risk/stress-test/portfolio-123")
        .send({})
        .expect(200);

      expect(mockRiskEngineInstance.performStressTest).toHaveBeenCalledWith(
        "portfolio-123",
        [],
        0.1,
        false
      );
    });

    test("should return 404 for non-existent portfolio", async () => {
      query.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .post("/risk/stress-test/non-existent")
        .send({})
        .expect(404);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("Portfolio not found");
    });
  });

  describe("GET /risk/alerts", () => {
    const mockAlertsData = {
      rows: [
        {
          id: "alert-1",
          alert_type: "var_breach",
          severity: "high",
          title: "VaR Limit Exceeded",
          description: "Portfolio VaR has exceeded the defined threshold",
          metric_name: "var_95",
          current_value: 0.055,
          threshold_value: 0.05,
          portfolio_id: "portfolio-123",
          symbol: null,
          created_at: "2023-01-01T10:00:00Z",
          updated_at: "2023-01-01T10:00:00Z",
          status: "active",
          acknowledged_at: null,
          portfolio_name: "My Portfolio",
        },
      ],
    };

    const mockCountData = {
      rows: [{ total: 5 }],
    };

    test("should return risk alerts", async () => {
      query
        .mockResolvedValueOnce(mockAlertsData)
        .mockResolvedValueOnce(mockCountData);

      const response = await request(app).get("/risk/alerts").expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.alerts).toEqual(mockAlertsData.rows);
      expect(response.body.data.total).toBe(5);
      expect(response.body.data.limit).toBe(50);
      expect(response.body.data.offset).toBe(0);
    });

    test("should filter alerts by severity", async () => {
      query
        .mockResolvedValueOnce(mockAlertsData)
        .mockResolvedValueOnce(mockCountData);

      const response = await request(app)
        .get("/risk/alerts?severity=high&status=active&limit=10&offset=5")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(query).toHaveBeenCalledWith(
        expect.stringContaining(
          "WHERE ra.user_id = $1 AND ra.severity = $2 AND ra.status = $3"
        ),
        ["test-user-123", "high", "active", 10, 5]
      );
    });

    test("should handle empty alerts", async () => {
      query
        .mockResolvedValueOnce({ rows: [] })
        .mockResolvedValueOnce({ rows: [{ total: 0 }] });

      const response = await request(app).get("/risk/alerts").expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.alerts).toEqual([]);
      expect(response.body.data.total).toBe(0);
    });
  });

  describe("PUT /risk/alerts/:alertId/acknowledge", () => {
    const mockAlertData = {
      rows: [{ id: "alert-1" }],
    };

    test("should acknowledge alert successfully", async () => {
      query.mockResolvedValueOnce(mockAlertData).mockResolvedValueOnce({});

      const response = await request(app)
        .put("/risk/alerts/alert-1/acknowledge")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.message).toBe("Alert acknowledged successfully");
      expect(query).toHaveBeenCalledWith(
        expect.stringContaining(
          "UPDATE risk_alerts SET status = 'acknowledged'"
        ),
        ["alert-1"]
      );
    });

    test("should return 404 for non-existent alert", async () => {
      query.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .put("/risk/alerts/non-existent/acknowledge")
        .expect(404);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("Alert not found");
    });
  });

  describe("GET /risk/correlation/:portfolioId", () => {
    const mockPortfolioData = {
      rows: [{ id: "portfolio-123" }],
    };

    const mockCorrelationMatrix = {
      portfolioId: "portfolio-123",
      lookbackDays: 252,
      correlationMatrix: {
        AAPL: { AAPL: 1.0, MSFT: 0.65, GOOGL: 0.58 },
        MSFT: { AAPL: 0.65, MSFT: 1.0, GOOGL: 0.72 },
        GOOGL: { AAPL: 0.58, MSFT: 0.72, GOOGL: 1.0 },
      },
      assets: ["AAPL", "MSFT", "GOOGL"],
      timestamp: "2025-08-21T19:09:23.522Z",
    };

    test("should return correlation matrix", async () => {
      query.mockResolvedValue(mockPortfolioData);
      mockRiskEngineInstance.calculateCorrelationMatrix.mockResolvedValue(
        mockCorrelationMatrix
      );

      const response = await request(app)
        .get("/risk/correlation/portfolio-123")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toEqual(mockCorrelationMatrix);
      expect(mockRiskEngineInstance.calculateCorrelationMatrix).toHaveBeenCalledWith(
        "portfolio-123",
        252
      );
    });

    test("should handle custom lookback days", async () => {
      query.mockResolvedValue(mockPortfolioData);
      mockRiskEngineInstance.calculateCorrelationMatrix.mockResolvedValue(
        mockCorrelationMatrix
      );

      await request(app)
        .get("/risk/correlation/portfolio-123?lookback_days=500")
        .expect(200);

      expect(mockRiskEngineInstance.calculateCorrelationMatrix).toHaveBeenCalledWith(
        "portfolio-123",
        500
      );
    });

    test("should return 404 for non-existent portfolio", async () => {
      query.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get("/risk/correlation/non-existent")
        .expect(404);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("Portfolio not found");
    });
  });

  describe("GET /risk/attribution/:portfolioId", () => {
    const mockPortfolioData = {
      rows: [{ id: "portfolio-123" }],
    };

    const mockAttribution = {
      factor_attribution: {
        market: 0.65,
        value: 0.15,
        growth: -0.1,
        momentum: 0.08,
        quality: 0.12,
      },
      security_attribution: [
        { symbol: "AAPL", contribution: 0.35 },
        { symbol: "MSFT", contribution: 0.25 },
        { symbol: "GOOGL", contribution: 0.2 },
      ],
      total_attribution: 1.0,
    };

    test("should return risk attribution analysis", async () => {
      query.mockResolvedValue(mockPortfolioData);
      mockRiskEngineInstance.calculateRiskAttribution.mockResolvedValue(
        mockAttribution
      );

      const response = await request(app)
        .get("/risk/attribution/portfolio-123")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toEqual(mockAttribution);
      expect(mockRiskEngineInstance.calculateRiskAttribution).toHaveBeenCalledWith(
        "portfolio-123",
        "factor"
      );
    });

    test("should handle custom attribution type", async () => {
      query.mockResolvedValue(mockPortfolioData);
      mockRiskEngineInstance.calculateRiskAttribution.mockResolvedValue(
        mockAttribution
      );

      await request(app)
        .get("/risk/attribution/portfolio-123?attribution_type=security")
        .expect(200);

      expect(mockRiskEngineInstance.calculateRiskAttribution).toHaveBeenCalledWith(
        "portfolio-123",
        "security"
      );
    });

    test("should return 404 for non-existent portfolio", async () => {
      query.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get("/risk/attribution/non-existent")
        .expect(404);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("Portfolio not found");
    });
  });

  describe("GET /risk/limits/:portfolioId", () => {
    const mockPortfolioData = {
      rows: [{ id: "portfolio-123" }],
    };

    const mockLimitsData = {
      rows: [
        {
          id: "limit-1",
          metric_name: "var_95",
          threshold_value: 0.05,
          warning_threshold: 0.045,
          threshold_type: "absolute",
          is_active: true,
          created_at: "2023-01-01T00:00:00Z",
          updated_at: "2023-01-01T00:00:00Z",
        },
        {
          id: "limit-2",
          metric_name: "max_drawdown",
          threshold_value: -0.15,
          warning_threshold: -0.12,
          threshold_type: "percentage",
          is_active: true,
          created_at: "2023-01-01T00:00:00Z",
          updated_at: "2023-01-01T00:00:00Z",
        },
      ],
    };

    test("should return risk limits", async () => {
      query
        .mockResolvedValueOnce(mockPortfolioData)
        .mockResolvedValueOnce(mockLimitsData);

      const response = await request(app)
        .get("/risk/limits/portfolio-123")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.limits).toEqual(mockLimitsData.rows);
      expect(response.body.data.portfolio_id).toBe("portfolio-123");
    });

    test("should return 404 for non-existent portfolio", async () => {
      query.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get("/risk/limits/non-existent")
        .expect(404);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("Portfolio not found");
    });
  });

  describe("PUT /risk/limits/:portfolioId", () => {
    const mockPortfolioData = {
      rows: [{ id: "portfolio-123" }],
    };

    const limitsUpdateData = {
      limits: [
        {
          metric_name: "var_95",
          threshold_value: 0.055,
          warning_threshold: 0.05,
          threshold_type: "absolute",
          is_active: true,
        },
        {
          metric_name: "max_drawdown",
          threshold_value: -0.2,
          warning_threshold: -0.15,
          threshold_type: "percentage",
          is_active: true,
        },
      ],
    };

    test("should update risk limits successfully", async () => {
      query.mockResolvedValueOnce(mockPortfolioData).mockResolvedValue({});

      const response = await request(app)
        .put("/risk/limits/portfolio-123")
        .send(limitsUpdateData)
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.message).toBe("Risk limits updated successfully");
      expect(query).toHaveBeenCalledTimes(3); // 1 for portfolio check + 2 for limit updates
    });

    test("should return 404 for non-existent portfolio", async () => {
      query.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .put("/risk/limits/non-existent")
        .send(limitsUpdateData)
        .expect(404);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("Portfolio not found");
    });
  });

  describe("GET /risk/dashboard", () => {
    const mockPortfolioRiskData = {
      rows: [
        {
          id: "portfolio-1",
          name: "Growth Portfolio",
          total_value: 100000,
          var_95: 0.045,
          var_99: 0.065,
          expected_shortfall: 0.075,
          volatility: 0.18,
          beta: 1.2,
          sharpe_ratio: 1.5,
          max_drawdown: -0.12,
          calculated_at: "2023-01-01T10:00:00Z",
        },
      ],
    };

    const mockAlertsCountData = {
      rows: [
        { severity: "high", count: 2 },
        { severity: "medium", count: 5 },
        { severity: "low", count: 3 },
      ],
    };

    const mockMarketRiskData = {
      rows: [
        {
          indicator_name: "VIX",
          current_value: 25.5,
          risk_level: "high",
          last_updated: "2023-01-01T15:00:00Z",
        },
        {
          indicator_name: "Credit Spreads",
          current_value: 150,
          risk_level: "medium",
          last_updated: "2023-01-01T15:00:00Z",
        },
      ],
    };

    test("should return risk dashboard data", async () => {
      query
        .mockResolvedValueOnce(mockPortfolioRiskData)
        .mockResolvedValueOnce(mockAlertsCountData)
        .mockResolvedValueOnce(mockMarketRiskData);

      const response = await request(app).get("/risk/dashboard").expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.portfolios).toEqual(mockPortfolioRiskData.rows);
      expect(response.body.data.alert_counts).toEqual({
        high: 2,
        medium: 5,
        low: 3,
      });
      expect(response.body.data.market_indicators).toEqual(
        mockMarketRiskData.rows
      );
      expect(response.body.data.summary.total_portfolios).toBe(1);
      expect(response.body.data.summary.total_alerts).toBe(10);
      expect(response.body.data.summary.high_risk_portfolios).toBe(0); // var_95 0.045 < 0.05
    });

    test("should handle empty dashboard data", async () => {
      query
        .mockResolvedValueOnce({ rows: [] })
        .mockResolvedValueOnce({ rows: [] })
        .mockResolvedValueOnce({ rows: [] });

      const response = await request(app).get("/risk/dashboard").expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.portfolios).toEqual([]);
      expect(response.body.data.alert_counts).toEqual({
        high: 0,
        medium: 0,
        low: 0,
      });
      expect(response.body.data.summary.total_portfolios).toBe(0);
      expect(response.body.data.summary.total_alerts).toBe(0);
    });
  });

  describe("POST /risk/monitoring/start", () => {
    const mockMonitoringResult = {
      status: "started",
      portfolio_count: 2,
      check_interval: 300000,
      started_at: new Date().toISOString(),
    };

    test("should start risk monitoring", async () => {
      const portfolioIds = ["portfolio-1", "portfolio-2"];
      query.mockResolvedValue({ rows: portfolioIds.map((id) => ({ id })) });
      mockRiskEngineInstance.startRealTimeMonitoring.mockResolvedValue(
        mockMonitoringResult
      );

      const response = await request(app)
        .post("/risk/monitoring/start")
        .send({
          portfolio_ids: portfolioIds,
          check_interval: 300000,
        })
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toEqual(mockMonitoringResult);
      expect(mockRiskEngineInstance.startRealTimeMonitoring).toHaveBeenCalledWith(
        "test-user-123",
        portfolioIds,
        300000
      );
    });

    test("should handle default parameters", async () => {
      mockRiskEngineInstance.startRealTimeMonitoring.mockResolvedValue(
        mockMonitoringResult
      );

      await request(app).post("/risk/monitoring/start").send({}).expect(200);

      expect(mockRiskEngineInstance.startRealTimeMonitoring).toHaveBeenCalledWith(
        "test-user-123",
        [],
        300000
      );
    });

    test("should return 400 for invalid portfolio ownership", async () => {
      query.mockResolvedValue({ rows: [{ id: "portfolio-1" }] }); // Only 1 of 2 portfolios found

      const response = await request(app)
        .post("/risk/monitoring/start")
        .send({
          portfolio_ids: ["portfolio-1", "portfolio-2"],
        })
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("One or more portfolios not found");
    });
  });

  describe("POST /risk/monitoring/stop", () => {
    const mockStopResult = {
      status: "stopped",
      stopped_at: new Date().toISOString(),
    };

    test("should stop risk monitoring", async () => {
      mockRiskEngineInstance.stopRealTimeMonitoring.mockResolvedValue(mockStopResult);

      const response = await request(app)
        .post("/risk/monitoring/stop")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toEqual(mockStopResult);
      expect(mockRiskEngineInstance.stopRealTimeMonitoring).toHaveBeenCalledWith(
        "test-user-123"
      );
    });
  });

  describe("GET /risk/monitoring/status", () => {
    const mockStatusResult = {
      is_monitoring: true,
      portfolio_count: 3,
      check_interval: 300000,
      last_check: "2023-01-01T15:30:00Z",
      alerts_generated: 5,
    };

    test("should return monitoring status", async () => {
      mockRiskEngineInstance.getMonitoringStatus.mockResolvedValue(mockStatusResult);

      const response = await request(app)
        .get("/risk/monitoring/status")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toEqual(mockStatusResult);
      expect(mockRiskEngineInstance.getMonitoringStatus).toHaveBeenCalledWith(
        "test-user-123"
      );
    });
  });

  describe("Error handling", () => {
    test("should handle RiskEngine calculation errors", async () => {
      query.mockResolvedValue({ rows: [{ id: "portfolio-123" }] });
      mockRiskEngineInstance.calculatePortfolioRisk.mockRejectedValue(
        new Error("Risk calculation failed")
      );

      const response = await request(app)
        .get("/risk/portfolio/portfolio-123")
        .expect(500);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("Failed to calculate portfolio risk");
      expect(response.body.message).toBe("Risk calculation failed");
    });

    test("should handle monitoring service errors", async () => {
      mockRiskEngineInstance.startRealTimeMonitoring.mockRejectedValue(
        new Error("Monitoring service unavailable")
      );

      const response = await request(app)
        .post("/risk/monitoring/start")
        .send({})
        .expect(500);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("Failed to start risk monitoring");
    });

    test("should handle malformed request bodies", async () => {
      query.mockResolvedValue({ rows: [{ id: "portfolio-123" }] });

      await request(app)
        .put("/risk/limits/portfolio-123")
        .send("invalid json")
        .expect(400);
    });
  });

  describe("Authentication requirements", () => {
    test("should require authentication for protected endpoints", async () => {
      // Remove authentication mock to test auth requirement
      authenticateToken.mockImplementation((req, res, _next) => {
        res.status(401).json({ error: "Authentication required" });
      });

      const response = await request(app)
        .get("/risk/portfolio/portfolio-123")
        .expect(401);

      expect(response.body.error).toBe("Authentication required");
    });
  });

  describe("Parameter validation", () => {
    test("should handle invalid confidence levels", async () => {
      query.mockResolvedValue({ rows: [{ id: "portfolio-123" }] });
      mockRiskEngineInstance.calculateVaR.mockResolvedValue({});

      await request(app)
        .get("/risk/var/portfolio-123?confidence_level=invalid")
        .expect(200);

      // Should use NaN which becomes 0.95 default in calculation
      expect(mockRiskEngineInstance.calculateVaR).toHaveBeenCalledWith(
        "portfolio-123",
        "historical",
        expect.any(Number),
        1,
        252
      );
    });

    test("should handle invalid time horizons", async () => {
      query.mockResolvedValue({ rows: [{ id: "portfolio-123" }] });
      mockRiskEngineInstance.calculateVaR.mockResolvedValue({});

      await request(app)
        .get("/risk/var/portfolio-123?time_horizon=invalid")
        .expect(200);

      expect(mockRiskEngineInstance.calculateVaR).toHaveBeenCalledWith(
        "portfolio-123",
        "historical",
        0.95,
        expect.any(Number), // parseInt('invalid') = NaN
        252
      );
    });
  });
});

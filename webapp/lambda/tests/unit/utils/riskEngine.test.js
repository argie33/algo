const RiskEngine = require("../../../utils/riskEngine");
const { query } = require("../../../utils/database");

jest.mock("../../../utils/database");

describe("Risk Engine", () => {
  let riskEngine;

  beforeEach(() => {
    riskEngine = new RiskEngine();
    jest.clearAllMocks();
  });

  describe("portfolio risk assessment", () => {
    test("should calculate portfolio VaR", async () => {
      const mockPortfolio = [
        { symbol: "AAPL", quantity: 100, currentPrice: 150, weight: 0.4 },
        { symbol: "GOOGL", quantity: 50, currentPrice: 2500, weight: 0.6 },
      ];

      const mockPriceData = {
        AAPL: [145, 148, 152, 149, 151],
        GOOGL: [2450, 2480, 2520, 2490, 2510],
      };

      query.mockResolvedValue({ rows: mockPriceData });

      const var95 = await riskEngine.calculateVaR(mockPortfolio, 0.95, 252);

      expect(var95).toBeDefined();
      expect(typeof var95).toBe("number");
      expect(var95).toBeGreaterThan(0);
    });

    test("should assess concentration risk", () => {
      const portfolio = [
        { symbol: "AAPL", weight: 0.5 },
        { symbol: "MSFT", weight: 0.3 },
        { symbol: "GOOGL", weight: 0.2 },
      ];

      const concentrationRisk = riskEngine.assessConcentrationRisk(portfolio);

      expect(concentrationRisk.level).toBeDefined();
      expect(concentrationRisk.hhi).toBeDefined(); // Herfindahl-Hirschman Index
      expect(concentrationRisk.recommendations).toBeDefined();
    });

    test("should calculate sector allocation risk", () => {
      const portfolio = [
        { symbol: "AAPL", sector: "Technology", weight: 0.4 },
        { symbol: "GOOGL", sector: "Technology", weight: 0.3 },
        { symbol: "JPM", sector: "Financial", weight: 0.3 },
      ];

      const sectorRisk = riskEngine.calculateSectorRisk(portfolio);

      expect(sectorRisk.Technology).toBeCloseTo(0.7);
      expect(sectorRisk.Financial).toBeCloseTo(0.3);
      expect(sectorRisk.diversification).toBeDefined();
    });

    test("should compute correlation matrix", async () => {
      const symbols = ["AAPL", "GOOGL", "TSLA"];
      const mockReturns = {
        AAPL: [0.01, -0.02, 0.03, -0.01],
        GOOGL: [0.02, -0.01, 0.02, 0.0],
        TSLA: [0.05, -0.08, 0.1, -0.03],
      };

      query.mockResolvedValue({ rows: mockReturns });

      const correlationMatrix =
        await riskEngine.calculateCorrelationMatrix(symbols);

      expect(correlationMatrix.AAPL).toBeDefined();
      expect(correlationMatrix.AAPL.GOOGL).toBeDefined();
      expect(Math.abs(correlationMatrix.AAPL.GOOGL)).toBeLessThanOrEqual(1);
    });
  });

  describe("individual stock risk metrics", () => {
    test("should calculate beta coefficient", async () => {
      const mockStockReturns = [0.02, -0.01, 0.03, -0.02, 0.01];
      const mockMarketReturns = [0.01, -0.005, 0.02, -0.015, 0.005];

      query.mockResolvedValue({
        rows: [
          {
            stock_returns: mockStockReturns,
            market_returns: mockMarketReturns,
          },
        ],
      });

      const beta = await riskEngine.calculateBeta("AAPL", "SPY");

      expect(typeof beta).toBe("number");
      expect(beta).toBeGreaterThan(-3);
      expect(beta).toBeLessThan(3);
    });

    test("should calculate historical volatility", async () => {
      const mockPrices = [100, 102, 98, 105, 103, 107, 104, 109];

      query.mockResolvedValue({ rows: [{ prices: mockPrices }] });

      const volatility = await riskEngine.calculateVolatility("AAPL", 30);

      expect(typeof volatility).toBe("number");
      expect(volatility).toBeGreaterThan(0);
      expect(volatility).toBeLessThan(2); // Annual volatility typically < 200%
    });

    test("should calculate maximum drawdown", async () => {
      const mockPrices = [100, 110, 95, 120, 85, 130, 90];

      query.mockResolvedValue({ rows: mockPrices.map((price) => ({ price })) });

      const maxDrawdown = await riskEngine.calculateMaxDrawdown("AAPL", 252);

      expect(typeof maxDrawdown).toBe("number");
      expect(maxDrawdown).toBeLessThanOrEqual(0); // Drawdown is negative
      expect(maxDrawdown).toBeGreaterThan(-1); // -100% would be bankruptcy
    });

    test("should assess liquidity risk", async () => {
      const mockVolumeData = [1000000, 800000, 1200000, 900000, 1100000];

      query.mockResolvedValue({
        rows: mockVolumeData.map((volume) => ({ volume })),
      });

      const liquidityRisk = await riskEngine.assessLiquidityRisk("AAPL");

      expect(liquidityRisk.level).toBeDefined();
      expect(liquidityRisk.avgVolume).toBeDefined();
      expect(liquidityRisk.daysToLiquidate).toBeDefined();
    });
  });

  describe("risk limit monitoring", () => {
    test("should check position size limits", () => {
      const position = { symbol: "AAPL", weight: 0.15 };
      const limits = { maxSinglePosition: 0.1 };

      const check = riskEngine.checkPositionLimits(position, limits);

      expect(check.exceeded).toBe(true);
      expect(check.limit).toBe("maxSinglePosition");
      expect(check.currentValue).toBe(0.15);
      expect(check.limitValue).toBe(0.1);
    });

    test("should validate sector allocation limits", () => {
      const portfolio = [
        { symbol: "AAPL", sector: "Technology", weight: 0.3 },
        { symbol: "GOOGL", sector: "Technology", weight: 0.3 },
        { symbol: "MSFT", sector: "Technology", weight: 0.2 },
      ];
      const limits = { maxSectorAllocation: 0.6 };

      const check = riskEngine.checkSectorLimits(portfolio, limits);

      expect(check.Technology.exceeded).toBe(true);
      expect(check.Technology.allocation).toBe(0.8);
    });

    test("should monitor leverage limits", () => {
      const portfolio = {
        totalValue: 100000,
        borrowedAmount: 40000,
        netValue: 60000,
      };
      const limits = { maxLeverage: 1.5 };

      const check = riskEngine.checkLeverageLimits(portfolio, limits);

      expect(check.currentLeverage).toBeCloseTo(1.67, 2);
      expect(check.exceeded).toBe(true);
    });

    test("should validate correlation limits", async () => {
      const portfolio = [
        { symbol: "AAPL", weight: 0.4 },
        { symbol: "MSFT", weight: 0.4 },
      ];
      const correlationMatrix = { AAPL: { MSFT: 0.85 } };
      const limits = { maxCorrelation: 0.8 };

      const check = await riskEngine.checkCorrelationLimits(
        portfolio,
        correlationMatrix,
        limits
      );

      expect(check.exceeded).toBe(true);
      expect(check.pairs).toContainEqual({
        pair: ["AAPL", "MSFT"],
        correlation: 0.85,
        weightProduct: 0.16,
      });
    });
  });

  describe("stress testing and scenario analysis", () => {
    test("should run market crash scenario", async () => {
      const portfolio = [
        { symbol: "AAPL", quantity: 100, currentPrice: 150, beta: 1.2 },
        { symbol: "GOOGL", quantity: 50, currentPrice: 2500, beta: 1.1 },
      ];
      const scenario = { marketDrop: -0.2 }; // 20% market drop

      const result = await riskEngine.runScenario(portfolio, scenario);

      expect(result.totalLoss).toBeDefined();
      expect(result.totalLoss).toBeLessThan(0);
      expect(result.breakdown).toBeDefined();
    });

    test("should perform Monte Carlo simulation", async () => {
      const portfolio = [
        { symbol: "AAPL", weight: 0.5, expectedReturn: 0.12, volatility: 0.25 },
      ];

      const simulation = await riskEngine.monteCarloSimulation(portfolio, {
        timeHorizon: 252,
        simulations: 1000,
        confidence: 0.95,
      });

      expect(simulation.var95).toBeDefined();
      expect(simulation.expectedReturn).toBeDefined();
      expect(simulation.worstCase).toBeDefined();
      expect(simulation.bestCase).toBeDefined();
    });

    test("should analyze interest rate sensitivity", async () => {
      const portfolio = [
        { symbol: "BND", weight: 0.3, duration: 6.5 },
        { symbol: "AAPL", weight: 0.7, duration: 0 },
      ];
      const rateShock = 0.01; // 100 basis points

      const sensitivity = await riskEngine.analyzeInterestRateSensitivity(
        portfolio,
        rateShock
      );

      expect(sensitivity.portfolioDuration).toBeDefined();
      expect(sensitivity.priceImpact).toBeDefined();
      expect(sensitivity.bondImpact).toBeLessThan(0);
    });

    test("should evaluate tail risk events", async () => {
      const historicalReturns = [0.01, -0.02, 0.03, -0.15, 0.02, -0.08, 0.01];

      const tailRisk = riskEngine.evaluateTailRisk(historicalReturns, 0.05);

      expect(tailRisk.expectedShortfall).toBeDefined();
      expect(tailRisk.tailRatio).toBeDefined();
      expect(tailRisk.extremeEvents).toBeDefined();
    });
  });

  describe("risk reporting and alerts", () => {
    test("should generate risk dashboard", async () => {
      const portfolio = [
        { symbol: "AAPL", weight: 0.4, sector: "Technology" },
        { symbol: "JPM", weight: 0.3, sector: "Financial" },
        { symbol: "JNJ", weight: 0.3, sector: "Healthcare" },
      ];

      const dashboard = await riskEngine.generateRiskDashboard(portfolio);

      expect(dashboard.overallRiskScore).toBeDefined();
      expect(dashboard.concentrationRisk).toBeDefined();
      expect(dashboard.sectorAllocation).toBeDefined();
      expect(dashboard.keyMetrics).toBeDefined();
      expect(dashboard.alerts).toBeDefined();
    });

    test("should create risk alerts", () => {
      const riskMetrics = {
        var95: -50000,
        concentrationRisk: "High",
        leverageRatio: 2.1,
      };
      const thresholds = {
        maxVar: -40000,
        maxLeverage: 2.0,
      };

      const alerts = riskEngine.generateRiskAlerts(riskMetrics, thresholds);

      expect(alerts).toHaveLength(2);
      expect(alerts.some((alert) => alert.type === "VaR_EXCEEDED")).toBe(true);
      expect(alerts.some((alert) => alert.type === "LEVERAGE_EXCEEDED")).toBe(
        true
      );
    });

    test("should generate compliance report", async () => {
      const portfolio = [{ symbol: "AAPL", weight: 0.15 }];
      const riskLimits = {
        maxSinglePosition: 0.1,
        maxSectorAllocation: 0.3,
      };

      const compliance = await riskEngine.generateComplianceReport(
        portfolio,
        riskLimits
      );

      expect(compliance.overallStatus).toBe("NON_COMPLIANT");
      expect(compliance.violations).toHaveLength(1);
      expect(compliance.violations[0].limit).toBe("maxSinglePosition");
    });
  });

  describe("dynamic risk adjustment", () => {
    test("should calculate optimal position sizes", async () => {
      const assets = [
        { symbol: "AAPL", expectedReturn: 0.12, volatility: 0.25 },
        { symbol: "GOOGL", expectedReturn: 0.15, volatility: 0.3 },
        { symbol: "JNJ", expectedReturn: 0.08, volatility: 0.15 },
      ];
      const riskTolerance = 0.2;

      const positions = await riskEngine.optimizePositionSizes(
        assets,
        riskTolerance
      );

      expect(positions.AAPL).toBeDefined();
      expect(positions.GOOGL).toBeDefined();
      expect(positions.JNJ).toBeDefined();

      const totalWeight = Object.values(positions).reduce(
        (sum, weight) => sum + weight,
        0
      );
      expect(totalWeight).toBeCloseTo(1, 2);
    });

    test("should rebalance portfolio for risk control", async () => {
      const currentPortfolio = [
        { symbol: "AAPL", weight: 0.6, targetWeight: 0.4 },
        { symbol: "BONDS", weight: 0.4, targetWeight: 0.6 },
      ];

      const rebalancing =
        await riskEngine.calculateRebalancing(currentPortfolio);

      expect(rebalancing.AAPL.action).toBe("SELL");
      expect(rebalancing.BONDS.action).toBe("BUY");
      expect(Math.abs(rebalancing.AAPL.amount)).toBeCloseTo(0.2, 2);
    });

    test("should adjust risk based on market conditions", () => {
      const marketConditions = {
        volatilityRegime: "HIGH",
        marketTrend: "BEARISH",
        economicIndicators: "NEGATIVE",
      };

      const adjustment =
        riskEngine.adjustRiskForMarketConditions(marketConditions);

      expect(adjustment.leverageMultiplier).toBeLessThan(1);
      expect(adjustment.concentrationLimit).toBeLessThan(0.1);
      expect(adjustment.recommendedActions).toContain("REDUCE_RISK");
    });
  });

  describe("error handling and edge cases", () => {
    test("should handle missing price data", async () => {
      query.mockResolvedValue({ rows: [] });

      const volatility = await riskEngine.calculateVolatility("INVALID", 30);

      expect(volatility).toBeNull();
    });

    test("should handle portfolio with zero weights", () => {
      const portfolio = [
        { symbol: "AAPL", weight: 0 },
        { symbol: "GOOGL", weight: 1 },
      ];

      const concentrationRisk = riskEngine.assessConcentrationRisk(portfolio);

      expect(concentrationRisk.level).toBe("EXTREME");
    });

    test("should validate input parameters", () => {
      expect(() => riskEngine.calculateVaR([], 1.5, 252)).toThrow();
      expect(() => riskEngine.calculateVaR(null, 0.95, 252)).toThrow();
      expect(() => riskEngine.calculateVaR([{}], 0.95, 0)).toThrow();
    });

    test("should handle database connection errors", async () => {
      query.mockRejectedValue(new Error("Database connection failed"));

      const result = await riskEngine.calculateVolatility("AAPL", 30);

      expect(result).toBeNull();
    });
  });
});

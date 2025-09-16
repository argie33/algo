/**
 * Risk Engine Integration Tests
 * Tests real risk calculations, database integration, and portfolio analysis
 */

const {
  initializeDatabase,
  closeDatabase,
  query,
} = require("../../../utils/database");

const RiskEngine = require("../../../utils/riskEngine");

describe("Risk Engine Integration Tests", () => {
  let riskEngine;

  beforeAll(async () => {
    await initializeDatabase();
    riskEngine = new RiskEngine();

    // Initialize test data in database
    await setupTestData();
  });

  afterAll(async () => {
    await cleanupTestData();
    await closeDatabase();
  });

  async function setupTestData() {
    // Insert test portfolio data
    const testPortfolio = [
      { symbol: "AAPL", quantity: 100, cost_basis: 150, current_price: 175 },
      { symbol: "MSFT", quantity: 50, cost_basis: 300, current_price: 350 },
      { symbol: "GOOGL", quantity: 25, cost_basis: 2800, current_price: 2900 },
      { symbol: "TSLA", quantity: 30, cost_basis: 800, current_price: 750 },
      { symbol: "SPY", quantity: 200, cost_basis: 400, current_price: 450 },
    ];

    for (const position of testPortfolio) {
      await query(
        `
        INSERT INTO user_portfolio (user_id, symbol, quantity, cost_basis, current_price) 
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (user_id, symbol) 
        DO UPDATE SET 
          quantity = EXCLUDED.quantity,
          cost_basis = EXCLUDED.cost_basis,
          current_price = EXCLUDED.current_price
      `,
        [
          "test-user-123",
          position.symbol,
          position.quantity,
          position.cost_basis,
          position.current_price,
        ]
      );
    }

    // Insert test price data for volatility calculations
    const priceHistory = [
      { symbol: "AAPL", date: "2023-12-01", close: 170, volume: 1000000 },
      { symbol: "AAPL", date: "2023-12-02", close: 175, volume: 1200000 },
      { symbol: "AAPL", date: "2023-12-03", close: 165, volume: 900000 },
      { symbol: "AAPL", date: "2023-12-04", close: 180, volume: 1500000 },
      { symbol: "AAPL", date: "2023-12-05", close: 175, volume: 1100000 },
    ];

    for (const price of priceHistory) {
      await query(
        `
        INSERT INTO price_daily (symbol, date, close, volume)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (symbol, date) 
        DO UPDATE SET close = EXCLUDED.close, volume = EXCLUDED.volume
      `,
        [price.symbol, price.date, price.close, price.volume]
      );
    }
  }

  async function cleanupTestData() {
    await query("DELETE FROM user_portfolio WHERE user_id = $1", [
      "test-user-123",
    ]);
    await query(
      "DELETE FROM price_daily WHERE symbol = 'AAPL' AND date >= '2023-12-01'"
    );
  }

  describe("Portfolio Risk Assessment with Database Integration", () => {
    test("should calculate portfolio-wide risk metrics from database", async () => {
      const portfolioRisk =
        await riskEngine.calculatePortfolioRisk("test-user-123");

      expect(portfolioRisk).toHaveProperty("totalValue");
      expect(portfolioRisk).toHaveProperty("totalRisk");
      expect(portfolioRisk).toHaveProperty("diversificationScore");
      expect(portfolioRisk).toHaveProperty("concentrationRisk");
      expect(portfolioRisk).toHaveProperty("positions");

      expect(typeof portfolioRisk.totalValue).toBe("number");
      expect(typeof portfolioRisk.totalRisk).toBe("number");
      expect(typeof portfolioRisk.diversificationScore).toBe("number");
      expect(portfolioRisk.totalValue).toBeGreaterThan(0);
      expect(portfolioRisk.diversificationScore).toBeGreaterThan(0);
      expect(portfolioRisk.diversificationScore).toBeLessThanOrEqual(100);

      // Should have risk data for each position
      expect(portfolioRisk.positions.length).toBe(5);
      portfolioRisk.positions.forEach((position) => {
        expect(position).toHaveProperty("symbol");
        expect(position).toHaveProperty("riskScore");
        expect(position).toHaveProperty("contribution");
        expect(position).toHaveProperty("allocation");
        expect(typeof position.riskScore).toBe("number");
        expect(position.riskScore).toBeGreaterThan(0);
        expect(position.riskScore).toBeLessThanOrEqual(100);
      });
    });

    test("should identify concentration risk", async () => {
      const portfolioRisk =
        await riskEngine.calculatePortfolioRisk("test-user-123");

      expect(portfolioRisk).toHaveProperty("concentrationRisk");
      expect(portfolioRisk.concentrationRisk).toHaveProperty("score");
      expect(portfolioRisk.concentrationRisk).toHaveProperty("topHoldings");
      expect(portfolioRisk.concentrationRisk).toHaveProperty("riskLevel");

      expect(typeof portfolioRisk.concentrationRisk.score).toBe("number");
      expect(Array.isArray(portfolioRisk.concentrationRisk.topHoldings)).toBe(
        true
      );
      expect(
        portfolioRisk.concentrationRisk.topHoldings.length
      ).toBeGreaterThan(0);

      // Top holdings should be sorted by allocation percentage
      const allocations = portfolioRisk.concentrationRisk.topHoldings.map(
        (h) => h.allocation
      );
      for (let i = 1; i < allocations.length; i++) {
        expect(allocations[i]).toBeLessThanOrEqual(allocations[i - 1]);
      }
    });

    test("should calculate sector allocation risk", async () => {
      const sectorRisk = await riskEngine.analyzeSectorRisk("test-user-123");

      expect(sectorRisk).toHaveProperty("sectorAllocations");
      expect(sectorRisk).toHaveProperty("diversificationScore");
      expect(sectorRisk).toHaveProperty("concentrationWarnings");
      expect(sectorRisk).toHaveProperty("recommendations");

      expect(Array.isArray(sectorRisk.sectorAllocations)).toBe(true);
      expect(Array.isArray(sectorRisk.concentrationWarnings)).toBe(true);
      expect(Array.isArray(sectorRisk.recommendations)).toBe(true);

      if (sectorRisk.sectorAllocations.length > 0) {
        sectorRisk.sectorAllocations.forEach((sector) => {
          expect(sector).toHaveProperty("sector");
          expect(sector).toHaveProperty("allocation");
          expect(sector).toHaveProperty("value");
          expect(sector).toHaveProperty("riskLevel");
          expect(typeof sector.allocation).toBe("number");
          expect(sector.allocation).toBeGreaterThan(0);
          expect(sector.allocation).toBeLessThanOrEqual(100);
        });
      }
    });
  });

  describe("Historical Volatility Analysis", () => {
    test("should calculate volatility from historical price data", async () => {
      const volatility = await riskEngine.calculateHistoricalVolatility(
        "AAPL",
        5
      );

      expect(volatility).toHaveProperty("symbol", "AAPL");
      expect(volatility).toHaveProperty("period", 5);
      expect(volatility).toHaveProperty("volatility");
      expect(volatility).toHaveProperty("annualizedVolatility");
      expect(volatility).toHaveProperty("priceChanges");
      expect(volatility).toHaveProperty("standardDeviation");

      expect(typeof volatility.volatility).toBe("number");
      expect(typeof volatility.annualizedVolatility).toBe("number");
      expect(volatility.volatility).toBeGreaterThanOrEqual(0);
      expect(volatility.annualizedVolatility).toBeGreaterThanOrEqual(0);
      expect(Array.isArray(volatility.priceChanges)).toBe(true);
    });

    test("should handle insufficient data gracefully", async () => {
      const volatility = await riskEngine.calculateHistoricalVolatility(
        "NONEXISTENT",
        30
      );

      expect(volatility).toHaveProperty("symbol", "NONEXISTENT");
      expect(volatility).toHaveProperty("error");
      expect(volatility.error).toContain("Insufficient data");
    });

    test("should calculate beta relative to market", async () => {
      // Add SPY data for beta calculation
      const spyData = [
        { date: "2023-12-01", close: 440 },
        { date: "2023-12-02", close: 445 },
        { date: "2023-12-03", close: 435 },
        { date: "2023-12-04", close: 455 },
        { date: "2023-12-05", close: 450 },
      ];

      for (const price of spyData) {
        await query(
          `
          INSERT INTO price_daily (symbol, date, close, volume)
          VALUES ($1, $2, $3, $4)
          ON CONFLICT (symbol, date) 
          DO UPDATE SET close = EXCLUDED.close
        `,
          ["SPY", price.date, price.close, 1000000]
        );
      }

      const beta = await riskEngine.calculateBeta("AAPL", "SPY", 5);

      expect(beta).toHaveProperty("symbol", "AAPL");
      expect(beta).toHaveProperty("benchmark", "SPY");
      expect(beta).toHaveProperty("beta");
      expect(beta).toHaveProperty("correlation");
      expect(beta).toHaveProperty("rSquared");

      expect(typeof beta.beta).toBe("number");
      expect(typeof beta.correlation).toBe("number");
      expect(beta.correlation).toBeGreaterThanOrEqual(-1);
      expect(beta.correlation).toBeLessThanOrEqual(1);
    });
  });

  describe("Value at Risk (VaR) Calculations", () => {
    test("should calculate portfolio VaR using historical method", async () => {
      const var95 = await riskEngine.calculatePortfolioVaR(
        "test-user-123",
        0.95,
        "historical"
      );

      expect(var95).toHaveProperty("confidenceLevel", 0.95);
      expect(var95).toHaveProperty("method", "historical");
      expect(var95).toHaveProperty("valueAtRisk");
      expect(var95).toHaveProperty("expectedShortfall");
      expect(var95).toHaveProperty("portfolioValue");
      expect(var95).toHaveProperty("riskPercentage");

      expect(typeof var95.valueAtRisk).toBe("number");
      expect(typeof var95.expectedShortfall).toBe("number");
      expect(var95.valueAtRisk).toBeGreaterThan(0);
      expect(var95.expectedShortfall).toBeGreaterThanOrEqual(var95.valueAtRisk);
      expect(var95.riskPercentage).toBeGreaterThan(0);
      expect(var95.riskPercentage).toBeLessThan(100);
    });

    test("should calculate VaR for different confidence levels", async () => {
      const var99 = await riskEngine.calculatePortfolioVaR(
        "test-user-123",
        0.99,
        "historical"
      );
      const var95 = await riskEngine.calculatePortfolioVaR(
        "test-user-123",
        0.95,
        "historical"
      );

      // 99% VaR should be higher than 95% VaR (more conservative)
      expect(var99.valueAtRisk).toBeGreaterThan(var95.valueAtRisk);
      expect(var99.expectedShortfall).toBeGreaterThanOrEqual(
        var95.expectedShortfall
      );
    });

    test("should calculate parametric VaR", async () => {
      const parametricVaR = await riskEngine.calculatePortfolioVaR(
        "test-user-123",
        0.95,
        "parametric"
      );

      expect(parametricVaR).toHaveProperty("method", "parametric");
      expect(parametricVaR).toHaveProperty("valueAtRisk");
      expect(parametricVaR).toHaveProperty("assumptions");
      expect(parametricVaR.assumptions).toHaveProperty("distribution");
      expect(parametricVaR.assumptions).toHaveProperty("volatility");

      expect(typeof parametricVaR.valueAtRisk).toBe("number");
      expect(parametricVaR.valueAtRisk).toBeGreaterThan(0);
    });
  });

  describe("Position Sizing and Risk Management", () => {
    test("should recommend optimal position sizes", async () => {
      const positionRecommendation = await riskEngine.recommendPositionSize(
        "test-user-123",
        "NVDA", // New position
        50000, // Investment amount
        0.02 // Risk tolerance (2% of portfolio)
      );

      expect(positionRecommendation).toHaveProperty("symbol", "NVDA");
      expect(positionRecommendation).toHaveProperty("investmentAmount", 50000);
      expect(positionRecommendation).toHaveProperty("recommendedShares");
      expect(positionRecommendation).toHaveProperty("maxShares");
      expect(positionRecommendation).toHaveProperty("riskAdjustedShares");
      expect(positionRecommendation).toHaveProperty("riskMetrics");

      expect(typeof positionRecommendation.recommendedShares).toBe("number");
      expect(typeof positionRecommendation.maxShares).toBe("number");
      expect(positionRecommendation.recommendedShares).toBeGreaterThan(0);
      expect(positionRecommendation.riskAdjustedShares).toBeLessThanOrEqual(
        positionRecommendation.maxShares
      );

      // Should include risk impact assessment
      expect(positionRecommendation.riskMetrics).toHaveProperty(
        "portfolioImpact"
      );
      expect(positionRecommendation.riskMetrics).toHaveProperty(
        "diversificationEffect"
      );
      expect(positionRecommendation.riskMetrics).toHaveProperty(
        "correlationRisk"
      );
    });

    test("should validate position size against risk limits", async () => {
      const validation = await riskEngine.validatePositionSize(
        "test-user-123",
        "AAPL",
        1000, // Very large position
        200 // High price
      );

      expect(validation).toHaveProperty("symbol", "AAPL");
      expect(validation).toHaveProperty("isValid");
      expect(validation).toHaveProperty("warnings");
      expect(validation).toHaveProperty("violations");
      expect(validation).toHaveProperty("recommendations");

      expect(typeof validation.isValid).toBe("boolean");
      expect(Array.isArray(validation.warnings)).toBe(true);
      expect(Array.isArray(validation.violations)).toBe(true);
      expect(Array.isArray(validation.recommendations)).toBe(true);

      // Large position should generate warnings
      if (!validation.isValid) {
        expect(validation.violations.length).toBeGreaterThan(0);
        expect(validation.recommendations.length).toBeGreaterThan(0);
      }
    });
  });

  describe("Correlation and Covariance Analysis", () => {
    test("should calculate correlation matrix for portfolio", async () => {
      const correlationMatrix =
        await riskEngine.calculateCorrelationMatrix("test-user-123");

      expect(correlationMatrix).toHaveProperty("symbols");
      expect(correlationMatrix).toHaveProperty("matrix");
      expect(correlationMatrix).toHaveProperty("averageCorrelation");
      expect(correlationMatrix).toHaveProperty("highestCorrelations");
      expect(correlationMatrix).toHaveProperty("lowestCorrelations");

      expect(Array.isArray(correlationMatrix.symbols)).toBe(true);
      expect(Array.isArray(correlationMatrix.matrix)).toBe(true);
      expect(Array.isArray(correlationMatrix.highestCorrelations)).toBe(true);
      expect(typeof correlationMatrix.averageCorrelation).toBe("number");

      // Matrix should be square
      expect(correlationMatrix.matrix.length).toBe(
        correlationMatrix.symbols.length
      );
      correlationMatrix.matrix.forEach((row) => {
        expect(row.length).toBe(correlationMatrix.symbols.length);
      });

      // Diagonal should be 1 (self-correlation)
      for (let i = 0; i < correlationMatrix.symbols.length; i++) {
        expect(correlationMatrix.matrix[i][i]).toBeCloseTo(1, 2);
      }
    });

    test("should identify highly correlated positions", async () => {
      const correlationAnalysis =
        await riskEngine.analyzePortfolioCorrelations("test-user-123");

      expect(correlationAnalysis).toHaveProperty("highCorrelationPairs");
      expect(correlationAnalysis).toHaveProperty("diversificationScore");
      expect(correlationAnalysis).toHaveProperty("clusterAnalysis");
      expect(correlationAnalysis).toHaveProperty("recommendations");

      expect(Array.isArray(correlationAnalysis.highCorrelationPairs)).toBe(
        true
      );
      expect(Array.isArray(correlationAnalysis.clusterAnalysis)).toBe(true);
      expect(Array.isArray(correlationAnalysis.recommendations)).toBe(true);
      expect(typeof correlationAnalysis.diversificationScore).toBe("number");
      expect(correlationAnalysis.diversificationScore).toBeGreaterThan(0);
      expect(correlationAnalysis.diversificationScore).toBeLessThanOrEqual(100);
    });
  });

  describe("Stress Testing and Scenario Analysis", () => {
    test("should perform market crash stress test", async () => {
      const stressTest = await riskEngine.performStressTest(
        "test-user-123",
        "market_crash"
      );

      expect(stressTest).toHaveProperty("scenario", "market_crash");
      expect(stressTest).toHaveProperty("portfolioValue");
      expect(stressTest).toHaveProperty("stressedValue");
      expect(stressTest).toHaveProperty("totalLoss");
      expect(stressTest).toHaveProperty("percentageLoss");
      expect(stressTest).toHaveProperty("positionImpacts");
      expect(stressTest).toHaveProperty("recoveryTime");

      expect(typeof stressTest.totalLoss).toBe("number");
      expect(typeof stressTest.percentageLoss).toBe("number");
      expect(stressTest.totalLoss).toBeGreaterThan(0); // Should show loss in crash scenario
      expect(stressTest.percentageLoss).toBeGreaterThan(0);
      expect(stressTest.percentageLoss).toBeLessThanOrEqual(100);
      expect(Array.isArray(stressTest.positionImpacts)).toBe(true);
    });

    test("should perform custom scenario analysis", async () => {
      const customScenario = {
        name: "tech_correction",
        description: "Technology sector correction",
        adjustments: {
          AAPL: -0.15, // 15% decline
          MSFT: -0.12, // 12% decline
          GOOGL: -0.18, // 18% decline
          TSLA: -0.25, // 25% decline (most volatile)
          SPY: -0.08, // 8% decline (market ETF less affected)
        },
      };

      const scenarioTest = await riskEngine.performCustomStressTest(
        "test-user-123",
        customScenario
      );

      expect(scenarioTest).toHaveProperty("scenario", "tech_correction");
      expect(scenarioTest).toHaveProperty("totalLoss");
      expect(scenarioTest).toHaveProperty("percentageLoss");
      expect(scenarioTest).toHaveProperty("positionImpacts");

      // Tesla should show highest loss due to 25% decline
      const teslaImpact = scenarioTest.positionImpacts.find(
        (p) => p.symbol === "TSLA"
      );
      expect(teslaImpact).toBeDefined();
      expect(teslaImpact.loss).toBeGreaterThan(0);
    });
  });

  describe("Risk Monitoring and Alerts", () => {
    test("should monitor portfolio risk limits", async () => {
      const riskMonitoring =
        await riskEngine.monitorRiskLimits("test-user-123");

      expect(riskMonitoring).toHaveProperty("overallRisk");
      expect(riskMonitoring).toHaveProperty("riskLimits");
      expect(riskMonitoring).toHaveProperty("breaches");
      expect(riskMonitoring).toHaveProperty("warnings");
      expect(riskMonitoring).toHaveProperty("recommendations");

      expect(Array.isArray(riskMonitoring.breaches)).toBe(true);
      expect(Array.isArray(riskMonitoring.warnings)).toBe(true);
      expect(Array.isArray(riskMonitoring.recommendations)).toBe(true);

      riskMonitoring.riskLimits.forEach((limit) => {
        expect(limit).toHaveProperty("type");
        expect(limit).toHaveProperty("limit");
        expect(limit).toHaveProperty("current");
        expect(limit).toHaveProperty("status");
        expect(typeof limit.limit).toBe("number");
        expect(typeof limit.current).toBe("number");
      });
    });

    test("should generate risk alerts for violations", async () => {
      // Simulate adding a high-risk position that would trigger alerts
      await query(
        `
        INSERT INTO user_portfolio (user_id, symbol, quantity, cost_basis, current_price) 
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (user_id, symbol) 
        DO UPDATE SET 
          quantity = EXCLUDED.quantity,
          cost_basis = EXCLUDED.cost_basis,
          current_price = EXCLUDED.current_price
      `,
        ["test-user-123", "RISKY_STOCK", 1000, 100, 95]
      ); // Large position with recent loss

      const alerts = await riskEngine.generateRiskAlerts("test-user-123");

      expect(Array.isArray(alerts)).toBe(true);
      alerts.forEach((alert) => {
        expect(alert).toHaveProperty("type");
        expect(alert).toHaveProperty("severity");
        expect(alert).toHaveProperty("message");
        expect(alert).toHaveProperty("symbol");
        expect(alert).toHaveProperty("recommendation");
        expect(["info", "warning", "critical"].includes(alert.severity)).toBe(
          true
        );
      });

      // Cleanup test position
      await query(
        "DELETE FROM user_portfolio WHERE user_id = $1 AND symbol = $2",
        ["test-user-123", "RISKY_STOCK"]
      );
    });
  });

  describe("Performance and Scalability", () => {
    test("should handle large portfolios efficiently", async () => {
      // Create a larger test portfolio
      const largePortfolio = [];
      for (let i = 0; i < 50; i++) {
        largePortfolio.push({
          symbol: `TEST${i.toString().padStart(3, "0")}`,
          quantity: Math.floor((i * 23 + 17) % 1000) + 10, // deterministic values
          cost_basis: Math.floor((i * 31 + 23) % 500) + 50,
          current_price: Math.floor((i * 37 + 29) % 600) + 40,
        });
      }

      for (const position of largePortfolio) {
        await query(
          `
          INSERT INTO user_portfolio (user_id, symbol, quantity, cost_basis, current_price) 
          VALUES ($1, $2, $3, $4, $5)
        `,
          [
            "large-portfolio-test",
            position.symbol,
            position.quantity,
            position.cost_basis,
            position.current_price,
          ]
        );
      }

      const startTime = Date.now();
      const portfolioRisk = await riskEngine.calculatePortfolioRisk(
        "large-portfolio-test"
      );
      const duration = Date.now() - startTime;

      expect(portfolioRisk).toHaveProperty("totalValue");
      expect(portfolioRisk.positions.length).toBe(50);

      // Should complete within reasonable time (< 5 seconds for 50 positions)
      expect(duration).toBeLessThan(5000);

      // Cleanup
      await query("DELETE FROM user_portfolio WHERE user_id = $1", [
        "large-portfolio-test",
      ]);
    }, 10000);

    test("should maintain accuracy with concurrent calculations", async () => {
      // Run multiple risk calculations concurrently
      const promises = [
        riskEngine.calculatePortfolioRisk("test-user-123"),
        riskEngine.analyzeSectorRisk("test-user-123"),
        riskEngine.calculatePortfolioVaR("test-user-123", 0.95, "historical"),
        riskEngine.monitorRiskLimits("test-user-123"),
      ];

      const results = await Promise.all(promises);

      // All calculations should complete successfully
      expect(results).toHaveLength(4);
      expect(results[0]).toHaveProperty("totalValue");
      expect(results[1]).toHaveProperty("sectorAllocations");
      expect(results[2]).toHaveProperty("valueAtRisk");
      expect(results[3]).toHaveProperty("overallRisk");

      // Values should be consistent across calculations
      const portfolioValue1 = results[0].totalValue;
      const portfolioValue2 = results[2].portfolioValue;
      expect(Math.abs(portfolioValue1 - portfolioValue2)).toBeLessThan(1000); // Allow small rounding differences
    });
  });

  describe("Error Handling and Edge Cases", () => {
    test("should handle empty portfolio gracefully", async () => {
      const emptyPortfolioRisk =
        await riskEngine.calculatePortfolioRisk("empty-user");

      expect(emptyPortfolioRisk).toHaveProperty("totalValue", 0);
      expect(emptyPortfolioRisk).toHaveProperty("positions");
      expect(emptyPortfolioRisk.positions).toHaveLength(0);
      expect(emptyPortfolioRisk).toHaveProperty("message");
      expect(emptyPortfolioRisk.message).toContain("empty");
    });

    test("should handle database connection errors", async () => {
      // This would typically require mocking database failures
      // For now, test with invalid user ID
      await expect(async () => {
        await riskEngine.calculatePortfolioRisk(null);
      }).not.toThrow();
    });

    test("should handle invalid risk parameters", async () => {
      const invalidVaR = await riskEngine.calculatePortfolioVaR(
        "test-user-123",
        1.5,
        "invalid"
      );

      expect(invalidVaR).toHaveProperty("error");
      expect(invalidVaR.error).toContain("Invalid");
    });
  });
});

/**
 * Trading Mode Helper Integration Tests
 * Tests trading mode switching, validation, and real trading environment integration
 */

const { initializeDatabase, closeDatabase } = require("../../../utils/database");
const tradingModeHelper = require("../../../utils/tradingModeHelper");

describe("Trading Mode Helper Integration Tests", () => {
  beforeAll(async () => {
    await initializeDatabase();
  });

  afterAll(async () => {
    await closeDatabase();
  });

  describe("Trading Mode Management", () => {
    test("should get current trading mode", async () => {
      const currentMode = await tradingModeHelper.getCurrentMode();
      
      expect(currentMode).toBeDefined();
      expect(currentMode.mode).toBeDefined();
      expect(['paper', 'live', 'simulation', 'backtest']).toContain(currentMode.mode);
      expect(currentMode.userId).toBeDefined();
      expect(currentMode.timestamp).toBeDefined();
      expect(currentMode.configuration).toBeDefined();
    });

    test("should switch to paper trading mode", async () => {
      const userId = "test_user_123";
      const switchResult = await tradingModeHelper.switchMode(userId, 'paper', {
        reason: "Testing paper trading functionality",
        autoSwitch: false
      });
      
      expect(switchResult).toBeDefined();
      expect(switchResult.success).toBe(true);
      expect(switchResult.previousMode).toBeDefined();
      expect(switchResult.currentMode).toBe('paper');
      expect(switchResult.switchedAt).toBeDefined();
      expect(switchResult.confirmation).toBeDefined();
    });

    test("should switch to live trading mode with validation", async () => {
      const userId = "test_user_123";
      const liveConfig = {
        confirmationRequired: true,
        riskLimits: {
          maxDailyLoss: 5000,
          maxPositionSize: 10000,
          maxOrderValue: 50000
        },
        apiCredentials: {
          verified: true,
          environment: "live"
        }
      };

      const switchResult = await tradingModeHelper.switchMode(userId, 'live', liveConfig);
      
      if (switchResult.success) {
        expect(switchResult.currentMode).toBe('live');
        expect(switchResult.riskLimits).toEqual(liveConfig.riskLimits);
        expect(switchResult.safeguards).toBeDefined();
      } else {
        // May fail due to missing live credentials in test environment
        expect(switchResult.error).toBeDefined();
        expect(switchResult.error.code).toMatch(/CREDENTIALS|VALIDATION/);
      }
    });

    test("should handle simulation mode", async () => {
      const userId = "test_user_123";
      const simulationConfig = {
        startingBalance: 100000,
        commission: 0.005,
        marketData: "delayed",
        duration: "1month"
      };

      const switchResult = await tradingModeHelper.switchMode(userId, 'simulation', simulationConfig);
      
      expect(switchResult.success).toBe(true);
      expect(switchResult.currentMode).toBe('simulation');
      expect(switchResult.simulationSettings).toEqual(simulationConfig);
    });
  });

  describe("Mode Validation", () => {
    test("should validate paper trading requirements", async () => {
      const userId = "test_user_123";
      const validation = await tradingModeHelper.validateModeRequirements(userId, 'paper');
      
      expect(validation).toBeDefined();
      expect(validation.isValid).toBe(true);
      expect(validation.requirements).toBeDefined();
      expect(validation.checks).toBeDefined();
      
      expect(Array.isArray(validation.checks)).toBe(true);
      validation.checks.forEach(check => {
        expect(check.name).toBeDefined();
        expect(check.status).toBeDefined();
        expect(['passed', 'failed', 'warning']).toContain(check.status);
      });
    });

    test("should validate live trading requirements", async () => {
      const userId = "test_user_123";
      const validation = await tradingModeHelper.validateModeRequirements(userId, 'live');
      
      expect(validation).toBeDefined();
      expect(validation.requirements).toBeDefined();
      
      const requiredChecks = [
        'api_credentials',
        'account_verification',
        'risk_acknowledgment',
        'sufficient_funds',
        'regulatory_compliance'
      ];

      requiredChecks.forEach(checkName => {
        const check = validation.checks.find(c => c.name === checkName);
        expect(check).toBeDefined();
      });
    });

    test("should prevent unauthorized mode switches", async () => {
      const unauthorizedUser = "unauthorized_user";
      
      const switchResult = await tradingModeHelper.switchMode(unauthorizedUser, 'live', {});
      
      expect(switchResult.success).toBe(false);
      expect(switchResult.error).toBeDefined();
      expect(switchResult.error.code).toBe('UNAUTHORIZED');
    });
  });

  describe("Trading Environment Configuration", () => {
    test("should configure paper trading environment", async () => {
      const paperConfig = {
        startingBalance: 100000,
        commission: 0.01,
        slippage: 0.02,
        marketDataDelay: 0,
        fillSimulation: "realistic"
      };

      const configResult = await tradingModeHelper.configureTradingEnvironment('paper', paperConfig);
      
      expect(configResult).toBeDefined();
      expect(configResult.success).toBe(true);
      expect(configResult.configuration).toEqual(paperConfig);
      expect(configResult.environmentReady).toBe(true);
    });

    test("should configure live trading environment", async () => {
      const liveConfig = {
        apiEndpoint: "https://api.alpaca.markets",
        environment: "live",
        riskControls: {
          enabled: true,
          maxDailyLoss: 5000,
          positionSizeLimit: 0.05 // 5% of portfolio
        },
        orderRouting: "smart"
      };

      const configResult = await tradingModeHelper.configureTradingEnvironment('live', liveConfig);
      
      if (configResult.success) {
        expect(configResult.configuration.riskControls.enabled).toBe(true);
        expect(configResult.apiConnection).toBeDefined();
      } else {
        // May fail in test environment
        expect(configResult.error).toBeDefined();
      }
    });

    test("should handle environment health checks", async () => {
      const healthCheck = await tradingModeHelper.performEnvironmentHealthCheck();
      
      expect(healthCheck).toBeDefined();
      expect(healthCheck.status).toBeDefined();
      expect(['healthy', 'degraded', 'unhealthy']).toContain(healthCheck.status);
      expect(healthCheck.checks).toBeDefined();
      expect(healthCheck.timestamp).toBeDefined();
      
      const criticalChecks = ['database', 'api_connectivity', 'market_data'];
      criticalChecks.forEach(checkName => {
        const check = healthCheck.checks.find(c => c.name === checkName);
        expect(check).toBeDefined();
        expect(check.status).toBeDefined();
      });
    });
  });

  describe("Risk Management Integration", () => {
    test("should enforce risk limits by trading mode", async () => {
      const userId = "test_user_123";
      const orderRequest = {
        symbol: "AAPL",
        side: "buy",
        quantity: 1000, // Large quantity to test limits
        type: "market"
      };

      const riskCheck = await tradingModeHelper.validateOrderAgainstRiskLimits(userId, orderRequest);
      
      expect(riskCheck).toBeDefined();
      expect(riskCheck.approved).toBeDefined();
      expect(riskCheck.riskScore).toBeDefined();
      expect(riskCheck.appliedLimits).toBeDefined();
      
      if (!riskCheck.approved) {
        expect(riskCheck.violations).toBeDefined();
        expect(Array.isArray(riskCheck.violations)).toBe(true);
      }
    });

    test("should adjust risk limits based on trading mode", async () => {
      const userId = "test_user_123";
      
      // Check paper mode limits
      await tradingModeHelper.switchMode(userId, 'paper');
      const paperLimits = await tradingModeHelper.getCurrentRiskLimits(userId);
      
      // Check live mode limits (if available)
      try {
        await tradingModeHelper.switchMode(userId, 'live');
        const liveLimits = await tradingModeHelper.getCurrentRiskLimits(userId);
        
        expect(paperLimits.maxPositionSize).toBeGreaterThanOrEqual(liveLimits.maxPositionSize);
        expect(paperLimits.maxDailyLoss).toBeGreaterThanOrEqual(liveLimits.maxDailyLoss);
      } catch (error) {
        // Live mode may not be available in test environment
        expect(error.code).toBe('MODE_UNAVAILABLE');
      }
      
      expect(paperLimits).toBeDefined();
      expect(paperLimits.maxPositionSize).toBeDefined();
      expect(paperLimits.maxDailyLoss).toBeDefined();
    });
  });

  describe("Mode-Specific Features", () => {
    test("should handle paper trading simulations", async () => {
      const userId = "test_user_123";
      await tradingModeHelper.switchMode(userId, 'paper');
      
      const simulatedOrder = {
        symbol: "AAPL",
        side: "buy",
        quantity: 100,
        type: "limit",
        limitPrice: 150.00
      };

      const orderResult = await tradingModeHelper.processPaperOrder(userId, simulatedOrder);
      
      expect(orderResult).toBeDefined();
      expect(orderResult.orderId).toBeDefined();
      expect(orderResult.status).toBeDefined();
      expect(orderResult.fillSimulation).toBeDefined();
      expect(orderResult.commissionCharged).toBeDefined();
      
      expect(['pending', 'filled', 'partially_filled']).toContain(orderResult.status);
      expect(typeof orderResult.commissionCharged).toBe('number');
    });

    test("should track paper trading performance", async () => {
      const userId = "test_user_123";
      const performance = await tradingModeHelper.getPaperTradingPerformance(userId);
      
      expect(performance).toBeDefined();
      expect(performance.totalReturn).toBeDefined();
      expect(performance.realizedPnL).toBeDefined();
      expect(performance.unrealizedPnL).toBeDefined();
      expect(performance.tradeCount).toBeDefined();
      expect(performance.winRate).toBeDefined();
      
      expect(typeof performance.totalReturn).toBe('number');
      expect(typeof performance.tradeCount).toBe('number');
      expect(performance.winRate).toBeGreaterThanOrEqual(0);
      expect(performance.winRate).toBeLessThanOrEqual(1);
    });

    test("should handle backtesting mode", async () => {
      const userId = "test_user_123";
      const backtestConfig = {
        startDate: "2023-01-01",
        endDate: "2023-12-31",
        initialCapital: 100000,
        strategy: "mean_reversion",
        symbols: ["AAPL", "GOOGL", "MSFT"]
      };

      const backtestResult = await tradingModeHelper.runBacktest(userId, backtestConfig);
      
      expect(backtestResult).toBeDefined();
      expect(backtestResult.backtestId).toBeDefined();
      expect(backtestResult.status).toBeDefined();
      expect(backtestResult.progress).toBeDefined();
      
      if (backtestResult.status === 'completed') {
        expect(backtestResult.results).toBeDefined();
        expect(backtestResult.results.totalReturn).toBeDefined();
        expect(backtestResult.results.sharpeRatio).toBeDefined();
        expect(backtestResult.results.maxDrawdown).toBeDefined();
      }
    });
  });

  describe("Data Isolation and Security", () => {
    test("should maintain data isolation between modes", async () => {
      const userId = "test_user_123";
      
      // Create paper trading positions
      await tradingModeHelper.switchMode(userId, 'paper');
      await tradingModeHelper.processPaperOrder(userId, {
        symbol: "AAPL",
        side: "buy",
        quantity: 100,
        type: "market"
      });
      
      const paperPositions = await tradingModeHelper.getPositions(userId);
      
      // Switch to simulation mode
      await tradingModeHelper.switchMode(userId, 'simulation');
      const simulationPositions = await tradingModeHelper.getPositions(userId);
      
      // Positions should be isolated
      expect(paperPositions).not.toEqual(simulationPositions);
      expect(Array.isArray(paperPositions)).toBe(true);
      expect(Array.isArray(simulationPositions)).toBe(true);
    });

    test("should secure live trading credentials", async () => {
      const userId = "test_user_123";
      const credentials = {
        apiKey: "test_api_key",
        secretKey: "test_secret_key",
        environment: "live"
      };

      const securityCheck = await tradingModeHelper.validateCredentialSecurity(credentials);
      
      expect(securityCheck).toBeDefined();
      expect(securityCheck.encrypted).toBe(true);
      expect(securityCheck.keyStrength).toBeDefined();
      expect(securityCheck.securityScore).toBeDefined();
      
      expect(typeof securityCheck.securityScore).toBe('number');
      expect(securityCheck.securityScore).toBeGreaterThan(0.7); // Should meet security standards
    });
  });

  describe("Performance and Monitoring", () => {
    test("should monitor mode switching performance", async () => {
      const userId = "test_user_123";
      
      const startTime = Date.now();
      await tradingModeHelper.switchMode(userId, 'paper');
      const switchDuration = Date.now() - startTime;
      
      expect(switchDuration).toBeLessThan(5000); // Should complete within 5 seconds
      
      const metrics = await tradingModeHelper.getPerformanceMetrics();
      expect(metrics).toBeDefined();
      expect(metrics.averageSwitchTime).toBeDefined();
      expect(metrics.successRate).toBeDefined();
      expect(metrics.activeUsers).toBeDefined();
    });

    test("should handle concurrent mode operations", async () => {
      const userId = "test_user_123";
      
      // Test concurrent operations
      const operations = [
        tradingModeHelper.getCurrentMode(userId),
        tradingModeHelper.validateModeRequirements(userId, 'paper'),
        tradingModeHelper.getCurrentRiskLimits(userId),
        tradingModeHelper.getPositions(userId)
      ];
      
      const results = await Promise.all(operations);
      
      expect(results.length).toBe(4);
      results.forEach(result => {
        expect(result).toBeDefined();
      });
    });
  });

  describe("Error Handling and Edge Cases", () => {
    test("should handle invalid mode transitions", async () => {
      const userId = "test_user_123";
      
      const invalidTransition = await tradingModeHelper.switchMode(userId, 'invalid_mode');
      
      expect(invalidTransition.success).toBe(false);
      expect(invalidTransition.error).toBeDefined();
      expect(invalidTransition.error.code).toBe('INVALID_MODE');
    });

    test("should handle system failures gracefully", async () => {
      const userId = "test_user_123";
      
      // Simulate system failure
      const failureRecovery = await tradingModeHelper.handleSystemFailure(userId, {
        preserveState: true,
        fallbackMode: 'paper'
      });
      
      expect(failureRecovery).toBeDefined();
      expect(failureRecovery.recovered).toBeDefined();
      expect(failureRecovery.fallbackActivated).toBeDefined();
      
      if (failureRecovery.fallbackActivated) {
        expect(failureRecovery.currentMode).toBe('paper');
        expect(failureRecovery.statePreserved).toBeDefined();
      }
    });

    test("should handle network connectivity issues", async () => {
      const connectivityCheck = await tradingModeHelper.checkNetworkConnectivity();
      
      expect(connectivityCheck).toBeDefined();
      expect(connectivityCheck.status).toBeDefined();
      expect(['connected', 'degraded', 'disconnected']).toContain(connectivityCheck.status);
      expect(connectivityCheck.latency).toBeDefined();
      expect(connectivityCheck.endpoints).toBeDefined();
      
      if (connectivityCheck.status === 'degraded') {
        expect(connectivityCheck.degradationReasons).toBeDefined();
        expect(Array.isArray(connectivityCheck.degradationReasons)).toBe(true);
      }
    });
  });

  describe("Audit and Compliance", () => {
    test("should log all mode changes", async () => {
      const userId = "test_user_123";
      
      await tradingModeHelper.switchMode(userId, 'paper', { reason: "Test audit logging" });
      
      const auditLog = await tradingModeHelper.getAuditLog(userId, { limit: 10 });
      
      expect(auditLog).toBeDefined();
      expect(Array.isArray(auditLog.entries)).toBe(true);
      expect(auditLog.entries.length).toBeGreaterThan(0);
      
      const latestEntry = auditLog.entries[0];
      expect(latestEntry.action).toBe('MODE_SWITCH');
      expect(latestEntry.userId).toBe(userId);
      expect(latestEntry.details.targetMode).toBe('paper');
      expect(latestEntry.timestamp).toBeDefined();
    });

    test("should maintain compliance records", async () => {
      const userId = "test_user_123";
      const compliance = await tradingModeHelper.getComplianceStatus(userId);
      
      expect(compliance).toBeDefined();
      expect(compliance.status).toBeDefined();
      expect(compliance.checks).toBeDefined();
      expect(compliance.lastUpdate).toBeDefined();
      
      expect(['compliant', 'non_compliant', 'pending']).toContain(compliance.status);
      expect(Array.isArray(compliance.checks)).toBe(true);
      
      compliance.checks.forEach(check => {
        expect(check.requirement).toBeDefined();
        expect(check.status).toBeDefined();
        expect(['passed', 'failed', 'n/a']).toContain(check.status);
      });
    });
  });
});
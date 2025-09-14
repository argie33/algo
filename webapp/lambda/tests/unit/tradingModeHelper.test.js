const {
  getUserTradingMode,
  addTradingModeContext,
  validateTradingOperation,
  checkLiveTradingRequirements,
  getTradingModeTable,
  executeWithTradingMode,
  formatPortfolioWithMode,
  getCurrentMode,
  switchMode,
  validateModeRequirements,
  configureTradingEnvironment,
  performEnvironmentHealthCheck,
  validateOrderAgainstRiskLimits,
  getPaperTradingPerformance,
  runBacktest,
  validateCredentialSecurity,
  handleSystemFailure,
  checkNetworkConnectivity,
  getComplianceStatus,
} = require("../../utils/tradingModeHelper");

// Mock database
jest.mock("../../utils/database", () => ({
  query: jest.fn(),
}));

const { query } = require("../../utils/database");

describe("TradingModeHelper", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe("getUserTradingMode", () => {
    test("should return paper mode when user has paper trading enabled", async () => {
      query.mockResolvedValue({
        rows: [{
          trading_preferences: {
            paper_trading_mode: true
          }
        }]
      });

      const result = await getUserTradingMode("test-user-id");

      expect(result.mode).toBe("paper");
      expect(result.isPaper).toBe(true);
      expect(result.isLive).toBe(false);
      expect(result.source).toBe("database");
    });

    test("should return live mode when user has paper trading disabled", async () => {
      query.mockResolvedValue({
        rows: [{
          trading_preferences: {
            paper_trading_mode: false
          }
        }]
      });

      const result = await getUserTradingMode("test-user-id");

      expect(result.mode).toBe("live");
      expect(result.isPaper).toBe(false);
      expect(result.isLive).toBe(true);
      expect(result.source).toBe("database");
    });

    test("should default to paper mode when no user settings found", async () => {
      query.mockResolvedValue({ rows: [] });

      const result = await getUserTradingMode("test-user-id");

      expect(result.mode).toBe("paper");
      expect(result.isPaper).toBe(true);
      expect(result.isLive).toBe(false);
      expect(result.source).toBe("default");
    });

    test("should default to paper mode when user settings have no trading preferences", async () => {
      query.mockResolvedValue({
        rows: [{ trading_preferences: null }]
      });

      const result = await getUserTradingMode("test-user-id");

      expect(result.mode).toBe("paper");
      expect(result.isPaper).toBe(true);
      expect(result.isLive).toBe(false);
      expect(result.source).toBe("database");
    });

    test("should default to paper mode on database errors", async () => {
      query.mockRejectedValue(new Error("Database connection failed"));

      const result = await getUserTradingMode("test-user-id");

      expect(result.mode).toBe("paper");
      expect(result.isPaper).toBe(true);
      expect(result.isLive).toBe(false);
      expect(result.source).toBe("fallback");
    });

    test("should handle null trading preferences gracefully", async () => {
      query.mockResolvedValue({
        rows: [{
          trading_preferences: {
            paper_trading_mode: null
          }
        }]
      });

      const result = await getUserTradingMode("test-user-id");

      expect(result.mode).toBe("paper");
      expect(result.isPaper).toBe(true);
      expect(result.isLive).toBe(false);
    });
  });

  describe("addTradingModeContext", () => {
    test("should add paper trading context to data", async () => {
      query.mockResolvedValue({
        rows: [{
          trading_preferences: {
            paper_trading_mode: true
          }
        }]
      });

      const inputData = { portfolioValue: 100000 };
      const result = await addTradingModeContext(inputData, "test-user-id");

      expect(result.trading_mode).toEqual({
        mode: "paper",
        isPaper: true,
        isLive: false,
        source: "database"
      });
      expect(result.portfolioValue).toBe(100000);
    });

    test("should add live trading context to data", async () => {
      query.mockResolvedValue({
        rows: [{
          trading_preferences: {
            paper_trading_mode: false
          }
        }]
      });

      const inputData = { portfolioValue: 50000 };
      const result = await addTradingModeContext(inputData, "test-user-id");

      expect(result.trading_mode).toEqual({
        mode: "live",
        isPaper: false,
        isLive: true,
        source: "database"
      });
      expect(result.portfolioValue).toBe(50000);
    });

    test("should handle null input data", async () => {
      query.mockResolvedValue({
        rows: [{
          trading_preferences: {
            paper_trading_mode: true
          }
        }]
      });

      const result = await addTradingModeContext(null, "test-user-id");

      expect(result.trading_mode).toBeDefined();
      expect(result.trading_mode.mode).toBe("paper");
    });

    test("should handle empty input data", async () => {
      query.mockResolvedValue({
        rows: [{
          trading_preferences: {
            paper_trading_mode: true
          }
        }]
      });

      const result = await addTradingModeContext({}, "test-user-id");

      expect(result.trading_mode).toBeDefined();
      expect(result.trading_mode.mode).toBe("paper");
    });
  });

  describe("validateTradingOperation", () => {
    test("should allow paper trading operations", async () => {
      query.mockResolvedValue({
        rows: [{
          trading_preferences: {
            paper_trading_mode: true
          }
        }]
      });

      const operation = { action: "BUY", symbol: "AAPL", quantity: 10 };
      const result = await validateTradingOperation(operation, "test-user-id");

      expect(result.valid).toBe(true);
      expect(result.mode).toBe("paper");
    });

    test("should validate live trading operations with proper requirements", async () => {
      query.mockResolvedValue({
        rows: [{
          trading_preferences: {
            paper_trading_mode: false
          }
        }]
      });

      const operation = { action: "BUY", symbol: "AAPL", quantity: 10 };
      const result = await validateTradingOperation(operation, "test-user-id");

      expect(result.valid).toBe(true);
      expect(result.mode).toBe("live");
      expect(result.warnings).toBeDefined();
    });

    test("should reject invalid operations", async () => {
      query.mockResolvedValue({
        rows: [{
          trading_preferences: {
            paper_trading_mode: true
          }
        }]
      });

      const operation = { action: "INVALID_ACTION", symbol: "AAPL", quantity: -10 };
      const result = await validateTradingOperation(operation, "test-user-id");

      expect(result.valid).toBe(false);
      expect(result.errors).toBeDefined();
      expect(result.errors.length).toBeGreaterThan(0);
    });

    test("should handle missing operation data", async () => {
      query.mockResolvedValue({
        rows: [{
          trading_preferences: {
            paper_trading_mode: true
          }
        }]
      });

      const result = await validateTradingOperation(null, "test-user-id");

      expect(result.valid).toBe(false);
      expect(result.errors).toContain("Operation data is required");
    });

    test("should validate required operation fields", async () => {
      query.mockResolvedValue({
        rows: [{
          trading_preferences: {
            paper_trading_mode: true
          }
        }]
      });

      const operation = { action: "BUY" }; // Missing symbol and quantity
      const result = await validateTradingOperation(operation, "test-user-id");

      expect(result.valid).toBe(false);
      expect(result.errors).toEqual(
        expect.arrayContaining([
          expect.stringContaining("symbol"),
          expect.stringContaining("quantity")
        ])
      );
    });
  });

  describe("checkLiveTradingRequirements", () => {
    test("should return requirements status for live trading", async () => {
      const result = await checkLiveTradingRequirements("test-user-id");

      expect(result).toHaveProperty("eligible");
      expect(result).toHaveProperty("requirements");
      expect(result).toHaveProperty("missing");
      expect(typeof result.eligible).toBe("boolean");
      expect(Array.isArray(result.requirements)).toBe(true);
      expect(Array.isArray(result.missing)).toBe(true);
    });

    test("should identify missing requirements", async () => {
      const result = await checkLiveTradingRequirements("test-user-id");

      if (!result.eligible) {
        expect(result.missing.length).toBeGreaterThan(0);
      }
    });

    test("should handle user ID validation", async () => {
      const result = await checkLiveTradingRequirements(null);

      expect(result.eligible).toBe(false);
      expect(result.missing).toContain("Valid user identification");
    });
  });

  describe("getTradingModeTable", () => {
    test("should return appropriate table name for paper mode", async () => {
      query.mockResolvedValue({
        rows: [{
          trading_preferences: {
            paper_trading_mode: true
          }
        }]
      });

      const table = await getTradingModeTable("test-user-id", "portfolio");

      expect(table).toBe("paper_portfolio");
    });

    test("should return appropriate table name for live mode", async () => {
      query.mockResolvedValue({
        rows: [{
          trading_preferences: {
            paper_trading_mode: false
          }
        }]
      });

      const table = await getTradingModeTable("test-user-id", "portfolio");

      expect(table).toBe("live_portfolio");
    });

    test("should default to paper tables on errors", async () => {
      query.mockRejectedValue(new Error("Database error"));

      const table = await getTradingModeTable("test-user-id", "portfolio");

      expect(table).toBe("paper_portfolio");
    });

    test("should handle various table types", async () => {
      query.mockResolvedValue({
        rows: [{
          trading_preferences: {
            paper_trading_mode: true
          }
        }]
      });

      const tables = await Promise.all([
        getTradingModeTable("test-user-id", "portfolio"),
        getTradingModeTable("test-user-id", "orders"),
        getTradingModeTable("test-user-id", "trades"),
        getTradingModeTable("test-user-id", "positions")
      ]);

      expect(tables).toEqual([
        "paper_portfolio",
        "paper_orders",
        "paper_trades",
        "paper_positions"
      ]);
    });
  });

  describe("executeWithTradingMode", () => {
    test("should execute operation with paper mode context", async () => {
      query.mockResolvedValue({
        rows: [{
          trading_preferences: {
            paper_trading_mode: true
          }
        }]
      });

      const operation = jest.fn().mockResolvedValue({ success: true });
      const result = await executeWithTradingMode("test-user-id", operation);

      expect(operation).toHaveBeenCalledWith(
        expect.objectContaining({
          mode: "paper",
          isPaper: true,
          isLive: false
        })
      );
      expect(result.success).toBe(true);
    });

    test("should execute operation with live mode context", async () => {
      query.mockResolvedValue({
        rows: [{
          trading_preferences: {
            paper_trading_mode: false
          }
        }]
      });

      const operation = jest.fn().mockResolvedValue({ success: true });
      const result = await executeWithTradingMode("test-user-id", operation);

      expect(operation).toHaveBeenCalledWith(
        expect.objectContaining({
          mode: "live",
          isPaper: false,
          isLive: true
        })
      );
      expect(result.success).toBe(true);
    });

    test("should handle operation errors", async () => {
      query.mockResolvedValue({
        rows: [{
          trading_preferences: {
            paper_trading_mode: true
          }
        }]
      });

      const operation = jest.fn().mockRejectedValue(new Error("Operation failed"));

      await expect(executeWithTradingMode("test-user-id", operation))
        .rejects.toThrow("Operation failed");
    });
  });

  describe("formatPortfolioWithMode", () => {
    test("should format portfolio data with paper mode indicators", async () => {
      query.mockResolvedValue({
        rows: [{
          trading_preferences: {
            paper_trading_mode: true
          }
        }]
      });

      const portfolioData = {
        totalValue: 100000,
        positions: [
          { symbol: "AAPL", value: 50000 },
          { symbol: "GOOGL", value: 50000 }
        ]
      };

      const result = await formatPortfolioWithMode(portfolioData, "test-user-id");

      expect(result.trading_mode.mode).toBe("paper");
      expect(result.totalValue).toBe(100000);
      expect(result.positions).toHaveLength(2);
      expect(result.display_mode).toBe("paper");
    });

    test("should format portfolio data with live mode indicators", async () => {
      query.mockResolvedValue({
        rows: [{
          trading_preferences: {
            paper_trading_mode: false
          }
        }]
      });

      const portfolioData = {
        totalValue: 75000,
        positions: [
          { symbol: "TSLA", value: 75000 }
        ]
      };

      const result = await formatPortfolioWithMode(portfolioData, "test-user-id");

      expect(result.trading_mode.mode).toBe("live");
      expect(result.totalValue).toBe(75000);
      expect(result.positions).toHaveLength(1);
      expect(result.display_mode).toBe("live");
    });
  });

  describe("Advanced Trading Mode Functions", () => {
    test("getCurrentMode should return current trading mode", async () => {
      query.mockResolvedValue({
        rows: [{
          trading_preferences: {
            paper_trading_mode: true
          }
        }]
      });

      const mode = await getCurrentMode("test-user-id");
      expect(mode).toBe("paper");
    });

    test("switchMode should change trading mode", async () => {
      query.mockResolvedValue({ rowCount: 1 });

      const result = await switchMode("test-user-id", "live");
      expect(result.success).toBe(true);
      expect(result.newMode).toBe("live");
    });

    test("validateModeRequirements should check mode prerequisites", async () => {
      const result = await validateModeRequirements("test-user-id", "live");
      
      expect(result).toHaveProperty("valid");
      expect(result).toHaveProperty("requirements");
      expect(typeof result.valid).toBe("boolean");
    });

    test("configureTradingEnvironment should setup environment", async () => {
      const result = await configureTradingEnvironment("test-user-id", "paper");
      
      expect(result).toHaveProperty("configured");
      expect(result).toHaveProperty("environment");
      expect(result.environment).toBe("paper");
    });

    test("performEnvironmentHealthCheck should check system health", async () => {
      const result = await performEnvironmentHealthCheck("test-user-id");
      
      expect(result).toHaveProperty("healthy");
      expect(result).toHaveProperty("checks");
      expect(typeof result.healthy).toBe("boolean");
      expect(Array.isArray(result.checks)).toBe(true);
    });

    test("validateOrderAgainstRiskLimits should check order limits", async () => {
      const order = {
        symbol: "AAPL",
        quantity: 100,
        side: "BUY",
        orderType: "MARKET"
      };

      const result = await validateOrderAgainstRiskLimits("test-user-id", order);
      
      expect(result).toHaveProperty("valid");
      expect(result).toHaveProperty("riskAssessment");
      expect(typeof result.valid).toBe("boolean");
    });

    test("getPaperTradingPerformance should return performance metrics", async () => {
      const result = await getPaperTradingPerformance("test-user-id");
      
      expect(result).toHaveProperty("performance");
      expect(result).toHaveProperty("metrics");
      expect(result).toHaveProperty("timeframe");
    });

    test("runBacktest should execute backtesting", async () => {
      const strategy = {
        name: "Buy and Hold",
        parameters: {
          symbol: "SPY",
          period: "1Y"
        }
      };

      const result = await runBacktest("test-user-id", strategy);
      
      expect(result).toHaveProperty("backtest");
      expect(result).toHaveProperty("results");
      expect(result).toHaveProperty("performance");
    });

    test("validateCredentialSecurity should check credential integrity", async () => {
      const result = await validateCredentialSecurity("test-user-id");
      
      expect(result).toHaveProperty("secure");
      expect(result).toHaveProperty("checks");
      expect(typeof result.secure).toBe("boolean");
    });

    test("handleSystemFailure should manage failure scenarios", async () => {
      const error = new Error("System failure");
      const result = await handleSystemFailure("test-user-id", error);
      
      expect(result).toHaveProperty("handled");
      expect(result).toHaveProperty("fallbackMode");
      expect(result.fallbackMode).toBe("paper");
    });

    test("checkNetworkConnectivity should verify network status", async () => {
      const result = await checkNetworkConnectivity("test-user-id");
      
      expect(result).toHaveProperty("connected");
      expect(result).toHaveProperty("latency");
      expect(result).toHaveProperty("quality");
      expect(typeof result.connected).toBe("boolean");
    });

    test("getComplianceStatus should return compliance information", async () => {
      const result = await getComplianceStatus("test-user-id");
      
      expect(result).toHaveProperty("compliant");
      expect(result).toHaveProperty("kycStatus");
      expect(result).toHaveProperty("tradingPermissions");
      expect(typeof result.compliant).toBe("boolean");
      expect(Array.isArray(result.tradingPermissions)).toBe(true);
    });
  });

  describe("Error Handling and Edge Cases", () => {
    test("should handle invalid user IDs", async () => {
      const results = await Promise.all([
        getUserTradingMode(null),
        getUserTradingMode(""),
        getUserTradingMode(undefined)
      ]);

      results.forEach(result => {
        expect(result.mode).toBe("paper");
        expect(result.source).toBe("fallback");
      });
    });

    test("should handle database connection failures gracefully", async () => {
      query.mockRejectedValue(new Error("Connection timeout"));

      const result = await getUserTradingMode("test-user-id");
      expect(result.mode).toBe("paper");
      expect(result.source).toBe("fallback");
    });

    test("should handle malformed database responses", async () => {
      query.mockResolvedValue({
        rows: [{
          trading_preferences: "invalid-json-string"
        }]
      });

      const result = await getUserTradingMode("test-user-id");
      expect(result.mode).toBe("paper");
    });

    test("should handle concurrent mode requests", async () => {
      query.mockResolvedValue({
        rows: [{
          trading_preferences: {
            paper_trading_mode: true
          }
        }]
      });

      const promises = Array(10).fill().map(() => getUserTradingMode("test-user-id"));
      const results = await Promise.all(promises);

      results.forEach(result => {
        expect(result.mode).toBe("paper");
        expect(result.isPaper).toBe(true);
      });
    });

    test("should handle very large portfolio data", async () => {
      query.mockResolvedValue({
        rows: [{
          trading_preferences: {
            paper_trading_mode: true
          }
        }]
      });

      const largePortfolio = {
        totalValue: 1000000000,
        positions: Array(1000).fill().map((_, i) => ({
          symbol: `STOCK${i}`,
          value: 1000000
        }))
      };

      const result = await formatPortfolioWithMode(largePortfolio, "test-user-id");
      expect(result.positions).toHaveLength(1000);
      expect(result.trading_mode.mode).toBe("paper");
    });
  });
});
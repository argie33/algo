/**
 * Trading Mode Helper Unit Tests
 * Tests the core trading mode functionality
 */
const tradingModeHelper = require("../../../utils/tradingModeHelper");
// Mock the database utility
jest.mock("../../../utils/database", () => ({
  query: jest.fn().mockResolvedValue({ rows: [], rowCount: 0 }),
}));

const { query, closeDatabase, initializeDatabase, getPool, transaction, healthCheck } = require('../../../utils/database');

describe("Trading Mode Helper Unit Tests", () => {
  let mockQuery;
  beforeEach(() => {
    jest.clearAllMocks();
    mockQuery = query;
  });

  describe("getUserTradingMode", () => {
    test("should return paper mode by default", async () => {
      mockQuery.mockResolvedValueOnce({ rows: [] });
      const result = await tradingModeHelper.getUserTradingMode("test-user");
      expect(result).toEqual({
        mode: "paper",
        isPaper: true,
        isLive: false,
        source: "default",
      });
    });
    test("should return paper mode when trading_preferences.paper_trading_mode is true", async () => {
      mockQuery.mockResolvedValueOnce({
        rows: [
          {
            trading_preferences: {
              paper_trading_mode: true,
            },
          },
        ],
      });
      const result = await tradingModeHelper.getUserTradingMode("test-user");
      expect(result).toEqual({
        mode: "paper",
        isPaper: true,
        isLive: false,
        source: "database",
      });
    });
    test("should return live mode when trading_preferences.paper_trading_mode is false", async () => {
      mockQuery.mockResolvedValueOnce({
        rows: [
          {
            trading_preferences: {
              paper_trading_mode: false,
            },
          },
        ],
      });
      const result = await tradingModeHelper.getUserTradingMode("test-user");
      expect(result).toEqual({
        mode: "live",
        isPaper: false,
        isLive: true,
        source: "database",
      });
    });
    test("should default to paper mode on database error", async () => {
      mockQuery.mockRejectedValueOnce(new Error("Database connection failed"));
      const result = await tradingModeHelper.getUserTradingMode("test-user");
      expect(result).toEqual({
        mode: "paper",
        isPaper: true,
        isLive: false,
        source: "fallback",
      });
    });
  });
  describe("addTradingModeContext", () => {
    test("should add paper trading context", async () => {
      mockQuery.mockResolvedValueOnce({
        rows: [
          {
            trading_preferences: {
              paper_trading_mode: true,
            },
          },
        ],
      });
      const inputData = { test: "data" };
      const result = await tradingModeHelper.addTradingModeContext(
        inputData,
        "test-user"
      );
      expect(result).toMatchObject({
        test: "data",
        trading_mode: {
          mode: "paper",
          isPaper: true,
          isLive: false,
          source: "database",
        },
        paper_trading: true,
        live_trading: false,
        mode_context: {
          description:
            "Paper trading - Simulated trades, no real money at risk",
          risk_level: "none",
          disclaimer: "📊 Paper trading for learning and strategy testing.",
        },
      });
    });
    test("should add live trading context", async () => {
      mockQuery.mockResolvedValueOnce({
        rows: [
          {
            trading_preferences: {
              paper_trading_mode: false,
            },
          },
        ],
      });
      const inputData = { test: "data" };
      const result = await tradingModeHelper.addTradingModeContext(
        inputData,
        "test-user"
      );
      expect(result).toMatchObject({
        test: "data",
        trading_mode: {
          mode: "live",
          isPaper: false,
          isLive: true,
          source: "database",
        },
        paper_trading: false,
        live_trading: true,
        mode_context: {
          description: "Live trading - Real money trades with actual brokerage",
          risk_level: "high",
          disclaimer: "⚠️ Live trading involves real money. Trade responsibly.",
        },
      });
    });
  });
  describe("validateTradingOperation", () => {
    test("should allow all operations in paper mode", async () => {
      mockQuery.mockResolvedValueOnce({
        rows: [
          {
            trading_preferences: {
              paper_trading_mode: true,
            },
          },
        ],
      });
      const result = await tradingModeHelper.validateTradingOperation(
        "test-user",
        "buy",
        {
          amount: 1000,
          quantity: 10,
        }
      );
      expect(result).toEqual({
        allowed: true,
        mode: "paper",
        message: "Operation allowed in paper trading mode (simulated)",
      });
    });
    test("should require API keys for live trading", async () => {
      mockQuery.mockResolvedValueOnce({
        rows: [
          {
            trading_preferences: {
              paper_trading_mode: false,
            },
          },
        ],
      });
      // Mock no API keys found
      mockQuery.mockResolvedValueOnce({ rows: [] });
      const result = await tradingModeHelper.validateTradingOperation(
        "test-user",
        "buy",
        {
          amount: 1000,
        }
      );
      expect(result).toEqual({
        allowed: false,
        mode: "live",
        message:
          "Live trading requires valid brokerage API keys. Please configure API keys in settings.",
      });
    });
    test("should allow live trading with valid API keys", async () => {
      mockQuery.mockResolvedValueOnce({
        rows: [
          {
            trading_preferences: {
              paper_trading_mode: false,
            },
          },
        ],
      });
      // Mock production API key found
      mockQuery.mockResolvedValueOnce({
        rows: [
          {
            provider: "alpaca",
            is_sandbox: false,
          },
        ],
      });
      const result = await tradingModeHelper.validateTradingOperation(
        "test-user",
        "buy",
        {
          amount: 1000,
        }
      );
      expect(result).toEqual({
        allowed: true,
        mode: "live",
        message: "Operation allowed in live trading mode",
      });
    });
    test("should block high-value trades without confirmation", async () => {
      mockQuery.mockResolvedValueOnce({
        rows: [
          {
            trading_preferences: {
              paper_trading_mode: false,
            },
          },
        ],
      });
      mockQuery.mockResolvedValueOnce({
        rows: [
          {
            provider: "alpaca",
            is_sandbox: false,
          },
        ],
      });
      const result = await tradingModeHelper.validateTradingOperation(
        "test-user",
        "buy",
        {
          amount: 15000, // Over $10,000 limit
        }
      );
      expect(result).toEqual({
        allowed: false,
        mode: "live",
        message:
          "High-value live trades require additional confirmation. Add confirmed_high_value: true parameter.",
      });
    });
    test("should allow high-value trades with confirmation", async () => {
      mockQuery.mockResolvedValueOnce({
        rows: [
          {
            trading_preferences: {
              paper_trading_mode: false,
            },
          },
        ],
      });
      mockQuery.mockResolvedValueOnce({
        rows: [
          {
            provider: "alpaca",
            is_sandbox: false,
          },
        ],
      });
      const result = await tradingModeHelper.validateTradingOperation(
        "test-user",
        "buy",
        {
          amount: 15000,
          confirmed_high_value: true,
        }
      );
      expect(result).toEqual({
        allowed: true,
        mode: "live",
        message: "Operation allowed in live trading mode",
      });
    });
  });
  describe("getTradingModeTable", () => {
    test("should return paper table name for paper mode", async () => {
      mockQuery.mockResolvedValueOnce({
        rows: [
          {
            trading_preferences: {
              paper_trading_mode: true,
            },
          },
        ],
      });
      const result = await tradingModeHelper.getTradingModeTable(
        "test-user",
        "portfolio_holdings"
      );
      expect(result).toEqual({
        table: "portfolio_holdings",
        mode: "paper",
        fallbackTable: "portfolio_holdings",
      });
    });
    test("should return live table name for live mode", async () => {
      mockQuery.mockResolvedValueOnce({
        rows: [
          {
            trading_preferences: {
              paper_trading_mode: false,
            },
          },
        ],
      });
      const result = await tradingModeHelper.getTradingModeTable(
        "test-user",
        "orders"
      );
      expect(result).toEqual({
        table: "orders_live",
        mode: "live",
        fallbackTable: "orders",
      });
    });
  });
  describe("executeWithTradingMode", () => {
    test("should execute query with paper table", async () => {
      mockQuery.mockResolvedValueOnce({
        rows: [
          {
            trading_preferences: {
              paper_trading_mode: true,
            },
          },
        ],
      });
      const mockQueryResult = { rows: [{ symbol: "AAPL" }] };
      mockQuery.mockResolvedValueOnce(mockQueryResult);
      const result = await tradingModeHelper.executeWithTradingMode(
        "test-user",
        "SELECT * FROM {table} WHERE user_id = $1",
        ["test-user"],
        "portfolio_holdings"
      );
      expect(mockQuery).toHaveBeenLastCalledWith(
        "SELECT * FROM portfolio_holdings WHERE user_id = $1",
        ["test-user"]
      );
      expect(result).toMatchObject({
        rows: [{ symbol: "AAPL" }],
        trading_mode: "paper",
        table_used: "portfolio_holdings",
      });
    });
    test("should fallback to base table when mode-specific table fails", async () => {
      mockQuery.mockResolvedValueOnce({
        rows: [
          {
            trading_preferences: {
              paper_trading_mode: true,
            },
          },
        ],
      });
      // First query (mode-specific table) fails
      mockQuery.mockRejectedValueOnce(
        new Error('relation "portfolio_holdings" does not exist')
      );
      // Second query (fallback table) succeeds
      const mockQueryResult = { rows: [{ symbol: "AAPL" }] };
      mockQuery.mockResolvedValueOnce(mockQueryResult);
      const result = await tradingModeHelper.executeWithTradingMode(
        "test-user",
        "SELECT * FROM {table} WHERE user_id = $1",
        ["test-user"],
        "portfolio_holdings"
      );
      expect(mockQuery).toHaveBeenCalledWith(
        "SELECT * FROM portfolio_holdings WHERE user_id = $1",
        ["test-user"]
      );
      expect(result).toMatchObject({
        rows: [{ symbol: "AAPL" }],
        trading_mode: "paper",
        table_used: "portfolio_holdings (fallback)",
        note: "Mode-specific table portfolio_holdings not available, using shared table",
      });
    });
  });
  describe("formatPortfolioWithMode", () => {
    test("should format portfolio data with paper trading context", async () => {
      mockQuery.mockResolvedValueOnce({
        rows: [
          {
            trading_preferences: {
              paper_trading_mode: true,
            },
          },
        ],
      });
      const portfolioData = {
        total_value: 50000,
        total_pnl: 5000,
      };
      const result = await tradingModeHelper.formatPortfolioWithMode(
        portfolioData,
        "test-user"
      );
      expect(result).toMatchObject({
        total_value: 50000,
        total_pnl: 5000,
        trading_mode: "paper",
        paper_trading: true,
        live_trading: false,
        performance_disclaimer:
          "Paper trading performance - results are simulated and may not reflect real trading conditions",
        risk_warning: null,
      });
    });
    test("should format portfolio data with live trading context", async () => {
      mockQuery.mockResolvedValueOnce({
        rows: [
          {
            trading_preferences: {
              paper_trading_mode: false,
            },
          },
        ],
      });
      const portfolioData = {
        total_value: 50000,
        total_pnl: 5000,
      };
      const result = await tradingModeHelper.formatPortfolioWithMode(
        portfolioData,
        "test-user"
      );
      expect(result).toMatchObject({
        total_value: 50000,
        total_pnl: 5000,
        trading_mode: "live",
        paper_trading: false,
        live_trading: true,
        performance_disclaimer:
          "Live trading performance - actual results from real money trades",
        risk_warning: "⚠️ Live trading results reflect real money gains/losses",
      });
    });
  });
  describe("checkLiveTradingRequirements", () => {
    test("should return true when production API keys exist", async () => {
      mockQuery.mockResolvedValueOnce({
        rows: [
          {
            provider: "alpaca",
            is_sandbox: false,
          },
        ],
      });
      const result =
        await tradingModeHelper.checkLiveTradingRequirements("test-user");
      expect(result).toBe(true);
    });
    test("should return false when only sandbox API keys exist", async () => {
      mockQuery.mockResolvedValueOnce({
        rows: [
          {
            provider: "alpaca",
            is_sandbox: true,
          },
        ],
      });
      const result =
        await tradingModeHelper.checkLiveTradingRequirements("test-user");
      expect(result).toBe(false);
    });
    test("should return false when no API keys exist", async () => {
      mockQuery.mockResolvedValueOnce({ rows: [] });
      const result =
        await tradingModeHelper.checkLiveTradingRequirements("test-user");
      expect(result).toBe(false);
    });
    test("should return false on database error", async () => {
      mockQuery.mockRejectedValueOnce(new Error("Database error"));
      const result =
        await tradingModeHelper.checkLiveTradingRequirements("test-user");
      expect(result).toBe(false);
    });
  });
});

/**
 * Alpaca Service Unit Tests
 * Comprehensive test coverage for Alpaca trading service
 */

const AlpacaService = require("../../utils/alpacaService");

// Mock the Alpaca client
const mockAlpacaClient = {
  getAccount: jest.fn(),
  getPositions: jest.fn(),
  getPortfolioHistory: jest.fn(),
  getActivities: jest.fn(),
  getCalendar: jest.fn(),
  getClock: jest.fn(),
  getAsset: jest.fn(),
  getLatestQuote: jest.fn(),
  getLatestTrade: jest.fn(),
  getBars: jest.fn(),
  createOrder: jest.fn(),
};

jest.mock("@alpacahq/alpaca-trade-api", () => {
  return jest.fn().mockImplementation(() => mockAlpacaClient);
});

describe("AlpacaService", () => {
  let service;
  const mockApiKey = "test-api-key";
  const mockApiSecret = "test-api-secret";

  beforeEach(() => {
    jest.clearAllMocks();
    jest.spyOn(console, "log").mockImplementation();
    jest.spyOn(console, "warn").mockImplementation();
    jest.spyOn(console, "error").mockImplementation();
    service = new AlpacaService(mockApiKey, mockApiSecret, true);
    service.requestTimes = [];
  });

  afterEach(() => {
    console.log.mockRestore();
    console.warn.mockRestore();
    console.error.mockRestore();
  });

  describe("Constructor", () => {
    test("should create service with valid credentials", () => {
      expect(service.isPaper).toBe(true);
      expect(service.rateLimitWindow).toBe(60000);
      expect(service.maxRequestsPerWindow).toBe(200);
      expect(service.requestTimes).toEqual([]);
    });

    test("should throw error without API key", () => {
      expect(() => {
        new AlpacaService(null, mockApiSecret);
      }).toThrow("Alpaca API key and secret are required");
    });

    test("should throw error without API secret", () => {
      expect(() => {
        new AlpacaService(mockApiKey, null);
      }).toThrow("Alpaca API key and secret are required");
    });

    test("should create live trading service", () => {
      const liveService = new AlpacaService(mockApiKey, mockApiSecret, false);
      expect(liveService.isPaper).toBe(false);
    });
  });

  describe("Rate Limiting", () => {
    test("should allow requests within rate limit", () => {
      expect(() => {
        service.checkRateLimit();
      }).not.toThrow();
      expect(service.requestTimes).toHaveLength(1);
    });

    test("should throw error when rate limit exceeded", () => {
      service.requestTimes = new Array(200).fill(Date.now());

      expect(() => {
        service.checkRateLimit();
      }).toThrow("Rate limit exceeded. Please try again in a minute.");
    });

    test("should clean up old requests", () => {
      const now = Date.now();
      const oldTime = now - 70000;
      const recentTime = now - 30000;

      service.requestTimes = [oldTime, recentTime];
      service.checkRateLimit();

      expect(service.requestTimes).toHaveLength(2);
      expect(service.requestTimes.includes(oldTime)).toBe(false);
    });
  });

  describe("getAccount", () => {
    const mockAccountData = {
      id: "account-123",
      status: "ACTIVE",
      currency: "USD",
      buying_power: "10000.50",
      cash: "5000.25",
      portfolio_value: "15000.75",
      equity: "15000.75",
      last_equity: "14500.00",
      daytrade_count: "2",
      daytrading_buying_power: "60000.00",
      regt_buying_power: "10000.50",
      initial_margin: "0.00",
      maintenance_margin: "0.00",
      long_market_value: "10000.50",
      short_market_value: "0.00",
      multiplier: "4",
      created_at: "2023-01-01T00:00:00Z",
      trading_blocked: false,
      transfers_blocked: false,
      account_blocked: false,
      pattern_day_trader: false,
    };

    test("should successfully get account information", async () => {
      mockAlpacaClient.getAccount.mockResolvedValue(mockAccountData);

      const result = await service.getAccount();

      expect(mockAlpacaClient.getAccount).toHaveBeenCalledTimes(1);
      expect(result).toEqual({
        accountId: "account-123",
        status: "ACTIVE",
        currency: "USD",
        buyingPower: 10000.5,
        cash: 5000.25,
        portfolioValue: 15000.75,
        equity: 15000.75,
        lastEquity: 14500.0,
        dayTradeCount: 2,
        dayTradingBuyingPower: 60000.0,
        regtBuyingPower: 10000.5,
        initialMargin: 0.0,
        maintenanceMargin: 0.0,
        longMarketValue: 10000.5,
        shortMarketValue: 0.0,
        multiplier: 4,
        createdAt: "2023-01-01T00:00:00Z",
        tradingBlocked: false,
        transfersBlocked: false,
        accountBlocked: false,
        patternDayTrader: false,
        environment: "paper",
      });
    });

    test("should handle API errors", async () => {
      const apiError = new Error("API connection failed");
      mockAlpacaClient.getAccount.mockRejectedValue(apiError);

      await expect(service.getAccount()).rejects.toThrow(
        "Failed to fetch account information: API connection failed"
      );
    });
  });

  describe("getPositions", () => {
    const mockPositionsData = [
      {
        asset_id: "asset-123",
        symbol: "AAPL",
        exchange: "NASDAQ",
        asset_class: "us_equity",
        qty: "10",
        side: "long",
        market_value: "1500.00",
        cost_basis: "1400.00",
        unrealized_pl: "100.00",
        unrealized_plpc: "0.0714",
        unrealized_intraday_pl: "50.00",
        unrealized_intraday_plpc: "0.0357",
        current_price: "150.00",
        lastday_price: "145.00",
        change_today: "0.0345",
        avg_entry_price: "140.00",
        qty_available: "10",
      },
    ];

    test("should successfully get positions", async () => {
      mockAlpacaClient.getPositions.mockResolvedValue(mockPositionsData);

      const result = await service.getPositions();

      expect(result).toHaveLength(1);
      expect(result[0]).toMatchObject({
        symbol: "AAPL",
        assetId: "asset-123",
        exchange: "NASDAQ",
        assetClass: "us_equity",
        quantity: 10,
        side: "long",
        marketValue: 1500.0,
        costBasis: 1400.0,
        unrealizedPL: 100.0,
        unrealizedPLPercent: 0.0714,
        unrealizedIntradayPL: 50.0,
        unrealizedIntradayPLPercent: 0.0357,
        currentPrice: 150.0,
        lastDayPrice: 145.0,
        changeToday: 0.0345,
        averageEntryPrice: 140.0,
        qtyAvailable: 10,
      });
    });

    test("should handle empty positions", async () => {
      mockAlpacaClient.getPositions.mockResolvedValue([]);
      const result = await service.getPositions();
      expect(result).toEqual([]);
    });

    test("should handle API errors", async () => {
      mockAlpacaClient.getPositions.mockRejectedValue(
        new Error("Network error")
      );
      await expect(service.getPositions()).rejects.toThrow(
        "Failed to fetch positions: Network error"
      );
    });
  });

  describe("getPortfolioHistory", () => {
    const mockPortfolioData = {
      timestamp: [1640995200, 1641081600],
      equity: [10000.0, 10100.0],
      profit_loss: [0.0, 100.0],
      profit_loss_pct: [0.0, 0.01],
      base_value: 10000.0,
    };

    test("should successfully get portfolio history", async () => {
      mockAlpacaClient.getPortfolioHistory.mockResolvedValue(mockPortfolioData);

      const result = await service.getPortfolioHistory("1M", "1Day");

      expect(mockAlpacaClient.getPortfolioHistory).toHaveBeenCalledWith({
        period: "1M",
        timeframe: "1Day",
        extended_hours: true,
      });

      expect(result).toHaveLength(2);
      expect(result[0]).toMatchObject({
        date: "2022-01-01",
        equity: 10000.0,
        profitLoss: 0.0,
        profitLossPercent: 0.0,
        baseValue: 10000.0,
      });
    });

    test("should handle empty portfolio history", async () => {
      mockAlpacaClient.getPortfolioHistory.mockResolvedValue({});
      const result = await service.getPortfolioHistory();
      expect(result).toEqual([]);
    });

    test("should handle API errors", async () => {
      mockAlpacaClient.getPortfolioHistory.mockRejectedValue(
        new Error("Network error")
      );
      await expect(service.getPortfolioHistory()).rejects.toThrow(
        "Failed to fetch portfolio history: Network error"
      );
    });
  });

  describe("getActivities", () => {
    const mockActivitiesData = [
      {
        id: "activity-123",
        activity_type: "FILL",
        date: "2023-01-01",
        net_amount: "1500.00",
        symbol: "AAPL",
        qty: "10",
        price: "150.00",
        side: "buy",
        description: "Buy 10 AAPL",
      },
    ];

    test("should successfully get activities", async () => {
      mockAlpacaClient.getActivities.mockResolvedValue(mockActivitiesData);

      const result = await service.getActivities();

      expect(mockAlpacaClient.getActivities).toHaveBeenCalledWith({
        activity_types: "FILL",
        page_size: 50,
      });

      expect(result).toHaveLength(1);
      expect(result[0]).toMatchObject({
        id: "activity-123",
        activityType: "FILL",
        date: "2023-01-01",
        netAmount: 1500.0,
        symbol: "AAPL",
        qty: 10,
        price: 150.0,
        side: "buy",
        description: "Buy 10 AAPL",
      });
    });

    test("should accept custom parameters", async () => {
      mockAlpacaClient.getActivities.mockResolvedValue([]);
      await service.getActivities("ACATS", 25);

      expect(mockAlpacaClient.getActivities).toHaveBeenCalledWith({
        activity_types: "ACATS",
        page_size: 25,
      });
    });
  });

  describe("getMarketCalendar", () => {
    const mockCalendarData = [
      {
        date: "2023-01-03",
        open: "09:30",
        close: "16:00",
        session_open: "04:00",
        session_close: "20:00",
      },
    ];

    test("should successfully get market calendar", async () => {
      mockAlpacaClient.getCalendar.mockResolvedValue(mockCalendarData);

      const result = await service.getMarketCalendar();

      expect(result).toHaveLength(1);
      expect(result[0]).toMatchObject({
        date: "2023-01-03",
        open: "09:30",
        close: "16:00",
        sessionOpen: "04:00",
        sessionClose: "20:00",
      });
    });
  });

  describe("getMarketStatus", () => {
    const mockClockData = {
      timestamp: "2023-01-03T14:30:00Z",
      is_open: true,
      next_open: "2023-01-04T14:30:00Z",
      next_close: "2023-01-03T21:00:00Z",
    };

    test("should successfully get market status", async () => {
      mockAlpacaClient.getClock.mockResolvedValue(mockClockData);

      const result = await service.getMarketStatus();

      expect(result).toMatchObject({
        timestamp: "2023-01-03T14:30:00Z",
        isOpen: true,
        nextOpen: "2023-01-04T14:30:00Z",
        nextClose: "2023-01-03T21:00:00Z",
        timezone: "America/New_York",
      });
    });
  });

  describe("validateCredentials", () => {
    test("should return valid credentials", async () => {
      mockAlpacaClient.getAccount.mockResolvedValue({
        id: "account-123",
        status: "ACTIVE",
      });

      const result = await service.validateCredentials();

      expect(result).toEqual({
        valid: true,
        accountId: "account-123",
        status: "ACTIVE",
        environment: "paper",
      });
    });

    test("should return invalid credentials on error", async () => {
      mockAlpacaClient.getAccount.mockRejectedValue(new Error("Unauthorized"));

      const result = await service.validateCredentials();

      expect(result).toEqual({
        valid: false,
        error: "Unauthorized",
        environment: "paper",
      });
    });
  });

  describe("getAsset", () => {
    const mockAssetData = {
      id: "asset-123",
      class: "us_equity",
      exchange: "NASDAQ",
      symbol: "AAPL",
      name: "Apple Inc.",
      status: "active",
      tradable: true,
      marginable: true,
      shortable: true,
      easy_to_borrow: true,
      fractionable: true,
    };

    test("should successfully get asset information", async () => {
      mockAlpacaClient.getAsset.mockResolvedValue(mockAssetData);

      const result = await service.getAsset("AAPL");

      expect(result).toMatchObject({
        id: "asset-123",
        class: "us_equity",
        exchange: "NASDAQ",
        symbol: "AAPL",
        name: "Apple Inc.",
        status: "active",
        tradable: true,
        marginable: true,
        shortable: true,
        easyToBorrow: true,
        fractionable: true,
      });
    });

    test("should handle asset fetch errors", async () => {
      mockAlpacaClient.getAsset.mockRejectedValue(new Error("Asset not found"));
      await expect(service.getAsset("INVALID")).rejects.toThrow(
        "Failed to fetch asset information: Asset not found"
      );
    });
  });

  describe("getLatestQuote", () => {
    const mockQuoteData = {
      BidPrice: 149.5,
      AskPrice: 150.5,
      BidSize: 100,
      AskSize: 200,
      Timestamp: "2023-01-03T14:30:00Z",
      Conditions: ["N"],
      Exchange: "NASDAQ",
    };

    test("should successfully get latest quote", async () => {
      mockAlpacaClient.getLatestQuote.mockResolvedValue(mockQuoteData);

      const result = await service.getLatestQuote("AAPL");

      expect(result).toMatchObject({
        symbol: "AAPL",
        bidPrice: 149.5,
        askPrice: 150.5,
        bidSize: 100,
        askSize: 200,
        timestamp: "2023-01-03T14:30:00Z",
        conditions: ["N"],
        exchange: "NASDAQ",
      });
    });

    test("should handle quote fetch errors gracefully", async () => {
      mockAlpacaClient.getLatestQuote.mockRejectedValue(
        new Error("Quote not available")
      );
      const result = await service.getLatestQuote("INVALID");
      expect(result).toBeNull();
    });

    test("should handle null quote data", async () => {
      mockAlpacaClient.getLatestQuote.mockResolvedValue(null);
      const result = await service.getLatestQuote("AAPL");
      expect(result).toBeNull();
    });
  });

  describe("getLatestTrade", () => {
    const mockTradeData = {
      Price: 150.0,
      Size: 100,
      Timestamp: "2023-01-03T14:30:00Z",
      Conditions: ["@"],
      Exchange: "NASDAQ",
    };

    test("should successfully get latest trade", async () => {
      mockAlpacaClient.getLatestTrade.mockResolvedValue(mockTradeData);

      const result = await service.getLatestTrade("AAPL");

      expect(result).toMatchObject({
        symbol: "AAPL",
        price: 150.0,
        size: 100,
        timestamp: "2023-01-03T14:30:00Z",
        conditions: ["@"],
        exchange: "NASDAQ",
      });
    });

    test("should handle trade fetch errors gracefully", async () => {
      mockAlpacaClient.getLatestTrade.mockRejectedValue(
        new Error("Trade not available")
      );
      const result = await service.getLatestTrade("INVALID");
      expect(result).toBeNull();
    });
  });

  describe("getBars", () => {
    const mockBarsData = {
      bars: [
        {
          Timestamp: "2023-01-03T14:30:00Z",
          OpenPrice: 149.0,
          HighPrice: 151.0,
          LowPrice: 148.0,
          ClosePrice: 150.0,
          Volume: 1000000,
          TradeCount: 500,
          VWAP: 149.75,
        },
      ],
    };

    test("should successfully get bars data", async () => {
      mockAlpacaClient.getBars.mockResolvedValue(mockBarsData);

      const result = await service.getBars("AAPL");

      expect(result).toHaveLength(1);
      expect(result[0]).toMatchObject({
        symbol: "AAPL",
        timestamp: "2023-01-03T14:30:00Z",
        open: 149.0,
        high: 151.0,
        low: 148.0,
        close: 150.0,
        volume: 1000000,
        tradeCount: 500,
        vwap: 149.75,
      });
    });

    test("should handle empty bars data", async () => {
      mockAlpacaClient.getBars.mockResolvedValue({ bars: [] });
      const result = await service.getBars("INVALID");
      expect(result).toEqual([]);
    });

    test("should handle bars fetch errors gracefully", async () => {
      mockAlpacaClient.getBars.mockRejectedValue(
        new Error("Bars not available")
      );
      const result = await service.getBars("INVALID");
      expect(result).toEqual([]);
    });
  });

  describe("getMarketClock", () => {
    const mockClockData = {
      timestamp: "2023-01-03T14:30:00Z",
      is_open: true,
      next_open: "2023-01-04T14:30:00Z",
      next_close: "2023-01-03T21:00:00Z",
    };

    test("should successfully get market clock", async () => {
      mockAlpacaClient.getClock.mockResolvedValue(mockClockData);

      const result = await service.getMarketClock();

      expect(result).toMatchObject({
        timestamp: "2023-01-03T14:30:00Z",
        isOpen: true,
        nextOpen: "2023-01-04T14:30:00Z",
        nextClose: "2023-01-03T21:00:00Z",
        timezone: "America/New_York",
      });
    });

    test("should handle clock fetch errors gracefully", async () => {
      mockAlpacaClient.getClock.mockRejectedValue(
        new Error("Clock not available")
      );

      const result = await service.getMarketClock();

      expect(result).toMatchObject({
        isOpen: false,
        timezone: "America/New_York",
        error: "Failed to fetch market status",
      });
    });
  });

  describe("createOrder", () => {
    const mockOrderResponse = {
      id: "order-123",
      symbol: "AAPL",
      qty: "10",
      side: "buy",
      order_type: "market",
      time_in_force: "day",
      status: "accepted",
      submitted_at: "2023-01-03T14:30:00Z",
      filled_qty: "0",
      filled_avg_price: null,
    };

    test("should successfully create market order", async () => {
      mockAlpacaClient.createOrder.mockResolvedValue(mockOrderResponse);

      const result = await service.createOrder("AAPL", 10, "buy", "market");

      expect(mockAlpacaClient.createOrder).toHaveBeenCalledWith({
        symbol: "AAPL",
        qty: 10,
        side: "buy",
        type: "market",
        time_in_force: "day",
      });

      expect(result).toMatchObject({
        orderId: "order-123",
        symbol: "AAPL",
        qty: 10,
        side: "buy",
        type: "market",
        time_in_force: "day",
        status: "accepted",
        createdAt: "2023-01-03T14:30:00Z",
        filledQty: 0,
        filledAvgPrice: null,
      });
    });

    test("should successfully create limit order", async () => {
      mockAlpacaClient.createOrder.mockResolvedValue({
        ...mockOrderResponse,
        order_type: "limit",
      });

      await service.createOrder("AAPL", 10, "buy", "limit", 149.5);

      expect(mockAlpacaClient.createOrder).toHaveBeenCalledWith({
        symbol: "AAPL",
        qty: 10,
        side: "buy",
        type: "limit",
        time_in_force: "day",
        limit_price: 149.5,
      });
    });

    test("should validate required parameters", async () => {
      await expect(service.createOrder("", 10, "buy")).rejects.toThrow(
        "Symbol is required"
      );
      await expect(service.createOrder("AAPL", 0, "buy")).rejects.toThrow(
        "Quantity must be a positive number"
      );
      await expect(service.createOrder("AAPL", 10, "invalid")).rejects.toThrow(
        "Side must be buy or sell"
      );
      await expect(
        service.createOrder("AAPL", 10, "buy", "limit")
      ).rejects.toThrow("Limit price is required for limit orders");
    });

    test("should handle order creation errors", async () => {
      mockAlpacaClient.createOrder.mockRejectedValue(
        new Error("Insufficient buying power")
      );
      await expect(service.createOrder("AAPL", 10, "buy")).rejects.toThrow(
        "Failed to create order: Insufficient buying power"
      );
    });
  });

  describe("getPortfolioSummary", () => {
    test("should generate comprehensive portfolio summary", async () => {
      // Mock all required calls
      mockAlpacaClient.getAccount.mockResolvedValue({
        portfolio_value: "15000.75",
        cash: "5000.25",
        buying_power: "10000.50",
      });

      mockAlpacaClient.getPositions.mockResolvedValue([
        {
          symbol: "AAPL",
          market_value: "1500.00",
          unrealized_pl: "100.00",
          unrealized_intraday_pl: "50.00",
          unrealized_intraday_plpc: "0.0357",
        },
      ]);

      mockAlpacaClient.getPortfolioHistory.mockResolvedValue({
        timestamp: [1640995200, 1641081600],
        equity: [14000.0, 15000.0],
        profit_loss: [0.0, 1000.0],
        profit_loss_pct: [0.0, 0.0714],
      });

      const result = await service.getPortfolioSummary();

      expect(result).toHaveProperty("account");
      expect(result).toHaveProperty("summary");
      expect(result).toHaveProperty("positions");
      expect(result).toHaveProperty("sectorAllocation");
      expect(result).toHaveProperty("riskMetrics");
      expect(result.summary).toMatchObject({
        totalValue: 15000.75,
        totalCash: 5000.25,
        positionsCount: 1,
        buyingPower: 10000.5,
      });
    });
  });

  describe("Sector Classification", () => {
    test("should classify technology stocks correctly", () => {
      expect(service.getSectorFromSymbol("AAPL")).toBe("Technology");
      expect(service.getSectorFromSymbol("MSFT")).toBe("Technology");
      expect(service.getSectorFromSymbol("GOOGL")).toBe("Technology");
    });

    test("should classify financial stocks correctly", () => {
      expect(service.getSectorFromSymbol("JPM")).toBe("Financials");
      expect(service.getSectorFromSymbol("BAC")).toBe("Financials");
    });

    test("should classify healthcare stocks correctly", () => {
      expect(service.getSectorFromSymbol("JNJ")).toBe("Healthcare");
      expect(service.getSectorFromSymbol("PFE")).toBe("Healthcare");
    });

    test("should classify unknown stocks as Other", () => {
      expect(service.getSectorFromSymbol("UNKNOWN")).toBe("Other");
    });
  });

  describe("Risk Metrics Calculation", () => {
    test("should calculate risk metrics with sufficient data", () => {
      const positions = [{ marketValue: 1000, unrealizedPL: 100 }];

      const history = [
        { equity: 9000 },
        { equity: 9500 },
        { equity: 10000 },
        { equity: 9800 },
      ];

      const result = service.calculateBasicRiskMetrics(positions, history);

      expect(result).toHaveProperty("volatility");
      expect(result).toHaveProperty("sharpeRatio");
      expect(result).toHaveProperty("maxDrawdown");
      expect(result).toHaveProperty("beta");
      expect(result.beta).toBe(1);
    });

    test("should handle insufficient data", () => {
      const positions = [];
      const history = [{ equity: 10000 }];

      const result = service.calculateBasicRiskMetrics(positions, history);

      expect(result).toEqual({
        volatility: 0,
        sharpeRatio: 0,
        maxDrawdown: 0,
        beta: 1,
      });
    });
  });

  describe("Error Handling", () => {
    test("should handle network timeouts", async () => {
      const timeoutError = new Error("ETIMEDOUT");
      mockAlpacaClient.getAccount.mockRejectedValue(timeoutError);

      await expect(service.getAccount()).rejects.toThrow(
        "Failed to fetch account information: ETIMEDOUT"
      );
    });

    test("should handle rate limit responses from API", async () => {
      const rateLimitError = new Error("Too Many Requests");
      mockAlpacaClient.getPositions.mockRejectedValue(rateLimitError);

      await expect(service.getPositions()).rejects.toThrow(
        "Failed to fetch positions: Too Many Requests"
      );
    });

    test("should check rate limit before all API calls", async () => {
      service.requestTimes = new Array(200).fill(Date.now());

      await expect(service.getAccount()).rejects.toThrow("Rate limit exceeded");
      await expect(service.getPositions()).rejects.toThrow(
        "Rate limit exceeded"
      );
      await expect(service.getPortfolioHistory()).rejects.toThrow(
        "Rate limit exceeded"
      );
    });
  });
});

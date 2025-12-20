// Create mock functions that will be reused
const mockAlpacaMethods = {
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

// Mock the Alpaca SDK - must be at top level before any requires
jest.mock("@alpacahq/alpaca-trade-api", () => {
  const mockConstructor = jest.fn().mockImplementation(() => {
    console.log("Mock Alpaca constructor called");
    return mockAlpacaMethods;
  });
  mockConstructor.mockAlpacaMethods = mockAlpacaMethods; // Expose for debugging
  return mockConstructor;
});

const AlpacaService = require("../../../utils/alpacaService");

describe("AlpacaService", () => {
  let alpacaService;
  let mockClient;

  beforeEach(() => {
    jest.clearAllMocks();
    jest.spyOn(console, "error").mockImplementation();
    jest.spyOn(console, "warn").mockImplementation();
    jest.spyOn(console, "log").mockImplementation();

    alpacaService = new AlpacaService("test-key", "test-secret", true);
    mockClient = mockAlpacaMethods; // Use the shared mock functions
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  describe("constructor", () => {
    it("should create AlpacaService instance with valid credentials", () => {
      expect(alpacaService).toBeInstanceOf(AlpacaService);
      expect(alpacaService.isPaper).toBe(true);
      expect(alpacaService.maxRequestsPerWindow).toBe(200);
      expect(alpacaService.rateLimitWindow).toBe(60000);
    });

    it("should throw error when API key is missing", () => {
      expect(() => new AlpacaService(null, "test-secret")).toThrow(
        "Alpaca API key and secret are required"
      );
    });

    it("should throw error when API secret is missing", () => {
      expect(() => new AlpacaService("test-key", null)).toThrow(
        "Alpaca API key and secret are required"
      );
    });

    it("should default to paper trading", () => {
      const service = new AlpacaService("test-key", "test-secret");
      expect(service.isPaper).toBe(true);
    });

    it("should support live trading mode", () => {
      const service = new AlpacaService("test-key", "test-secret", false);
      expect(service.isPaper).toBe(false);
    });
  });

  describe("checkRateLimit", () => {
    it("should allow requests under rate limit", () => {
      expect(() => alpacaService.checkRateLimit()).not.toThrow();
      expect(alpacaService.requestTimes).toHaveLength(1);
    });

    it("should throw error when rate limit exceeded", () => {
      // Fill request times to exceed limit
      const now = Date.now();
      alpacaService.requestTimes = new Array(200).fill(now);

      expect(() => alpacaService.checkRateLimit()).toThrow(
        "Rate limit exceeded. Please try again in a minute."
      );
    });

    it("should remove old requests outside time window", () => {
      const now = Date.now();
      const oldTime = now - 70000; // 70 seconds ago
      alpacaService.requestTimes = [oldTime, now - 30000, now - 10000];

      alpacaService.checkRateLimit();

      // Should remove the old request and add new one
      expect(alpacaService.requestTimes).toHaveLength(3); // 2 recent + 1 new
      expect(
        alpacaService.requestTimes.every((time) => time > now - 60000)
      ).toBe(true);
    });
  });

  describe("getAccount", () => {
    const mockAccountData = {
      id: "account-123",
      status: "ACTIVE",
      currency: "USD",
      buying_power: "50000.00",
      cash: "25000.00",
      portfolio_value: "75000.00",
      equity: "75000.00",
      last_equity: "74000.00",
      daytrade_count: 0,
      daytrading_buying_power: "100000.00",
      regt_buying_power: "50000.00",
      initial_margin: "0.00",
      maintenance_margin: "0.00",
      long_market_value: "50000.00",
      short_market_value: "0.00",
      multiplier: "2.00",
      created_at: "2020-01-01T00:00:00Z",
      trading_blocked: false,
      transfers_blocked: false,
      account_blocked: false,
      pattern_day_trader: false,
    };

    it("should fetch and format account data successfully", async () => {
      mockClient.getAccount.mockResolvedValue(mockAccountData);

      const result = await alpacaService.getAccount();

      expect(result).toEqual({
        accountId: "account-123",
        status: "ACTIVE",
        currency: "USD",
        buyingPower: 50000,
        cash: 25000,
        portfolioValue: 75000,
        equity: 75000,
        lastEquity: 74000,
        dayTradeCount: 0,
        dayTradingBuyingPower: 100000,
        regtBuyingPower: 50000,
        initialMargin: 0,
        maintenanceMargin: 0,
        longMarketValue: 50000,
        shortMarketValue: 0,
        multiplier: 2,
        createdAt: "2020-01-01T00:00:00Z",
        tradingBlocked: false,
        transfersBlocked: false,
        accountBlocked: false,
        patternDayTrader: false,
        environment: "paper",
      });
    });

    it("should throw error when account fetch fails", async () => {
      mockClient.getAccount.mockRejectedValue(new Error("API error"));

      await expect(alpacaService.getAccount()).rejects.toThrow(
        "Failed to fetch account information: API error"
      );
    });
  });

  describe("getPositions", () => {
    const mockPositionsData = [
      {
        symbol: "AAPL",
        asset_id: "asset-123",
        exchange: "NASDAQ",
        asset_class: "us_equity",
        qty: "100",
        side: "long",
        market_value: "15000.00",
        cost_basis: "14000.00",
        unrealized_pl: "1000.00",
        unrealized_plpc: "0.0714",
        unrealized_intraday_pl: "50.00",
        unrealized_intraday_plpc: "0.0033",
        current_price: "150.00",
        lastday_price: "149.50",
        change_today: "0.50",
        avg_entry_price: "140.00",
        qty_available: "100",
      },
    ];

    it("should fetch and format positions data successfully", async () => {
      mockClient.getPositions.mockResolvedValue(mockPositionsData);

      const result = await alpacaService.getPositions();

      expect(result).toHaveLength(1);
      expect(result[0]).toEqual({
        symbol: "AAPL",
        assetId: "asset-123",
        exchange: "NASDAQ",
        assetClass: "us_equity",
        quantity: 100,
        side: "long",
        marketValue: 15000,
        costBasis: 14000,
        unrealizedPL: 1000,
        unrealizedPLPercent: 0.0714,
        unrealizedIntradayPL: 50,
        unrealizedIntradayPLPercent: 0.0033,
        currentPrice: 150,
        lastDayPrice: 149.5,
        changeToday: 0.5,
        averageEntryPrice: 140,
        qtyAvailable: 100,
        lastUpdated: expect.any(String),
      });
    });

    it("should handle empty positions", async () => {
      mockClient.getPositions.mockResolvedValue([]);

      const result = await alpacaService.getPositions();

      expect(result).toEqual([]);
    });

    it("should throw error when positions fetch fails", async () => {
      mockClient.getPositions.mockRejectedValue(new Error("API error"));

      await expect(alpacaService.getPositions()).rejects.toThrow(
        "Failed to fetch positions: API error"
      );
    });
  });

  describe("getPortfolioHistory", () => {
    const mockHistoryData = {
      timestamp: [1640995200, 1641081600, 1641168000],
      equity: [75000, 75500, 74800],
      profit_loss: [0, 500, -200],
      profit_loss_pct: [0, 0.0067, -0.0027],
      base_value: 75000,
    };

    it("should fetch and format portfolio history successfully", async () => {
      mockClient.getPortfolioHistory.mockResolvedValue(mockHistoryData);

      const result = await alpacaService.getPortfolioHistory("1M", "1Day");

      expect(result).toHaveLength(3);
      expect(result[0]).toEqual({
        date: "2022-01-01",
        equity: 75000,
        profitLoss: 0,
        profitLossPercent: 0,
        baseValue: 75000,
      });
      expect(result[1]).toEqual({
        date: "2022-01-02",
        equity: 75500,
        profitLoss: 500,
        profitLossPercent: 0.0067,
        baseValue: 75000,
      });
    });

    it("should handle empty portfolio history", async () => {
      mockClient.getPortfolioHistory.mockResolvedValue({});

      const result = await alpacaService.getPortfolioHistory();

      expect(result).toEqual([]);
    });

    it("should filter out null equity values", async () => {
      const dataWithNulls = {
        timestamp: [1640995200, 1641081600, 1641168000],
        equity: [75000, null, 74800],
        profit_loss: [0, 500, -200],
        profit_loss_pct: [0, 0.0067, -0.0027],
        base_value: 75000,
      };

      mockClient.getPortfolioHistory.mockResolvedValue(dataWithNulls);

      const result = await alpacaService.getPortfolioHistory();

      expect(result).toHaveLength(2);
      expect(result[0].equity).toBe(75000);
      expect(result[1].equity).toBe(74800);
    });
  });

  describe("getActivities", () => {
    const mockActivitiesData = [
      {
        id: "activity-123",
        activity_type: "FILL",
        date: "2022-01-01",
        net_amount: "-1000.00",
        symbol: "AAPL",
        qty: "10",
        price: "100.00",
        side: "buy",
        description: "Buy order filled",
      },
    ];

    it("should fetch and format activities successfully", async () => {
      mockClient.getActivities.mockResolvedValue(mockActivitiesData);

      const result = await alpacaService.getActivities("FILL", 50);

      expect(result).toHaveLength(1);
      expect(result[0]).toEqual({
        id: "activity-123",
        activityType: "FILL",
        date: "2022-01-01",
        netAmount: -1000,
        symbol: "AAPL",
        qty: 10,
        price: 100,
        side: "buy",
        description: "Buy order filled",
      });
    });

    it("should handle missing optional fields", async () => {
      const activityWithNulls = [
        {
          id: "activity-456",
          activity_type: "DIV",
          date: "2022-01-01",
          net_amount: null,
          symbol: "AAPL",
          qty: null,
          price: null,
          side: null,
          description: null,
        },
      ];

      mockClient.getActivities.mockResolvedValue(activityWithNulls);

      const result = await alpacaService.getActivities();

      expect(result[0]).toEqual({
        id: "activity-456",
        activityType: "DIV",
        date: "2022-01-01",
        netAmount: 0,
        symbol: "AAPL",
        qty: null,
        price: null,
        side: null,
        description: "DIV",
      });
    });
  });

  describe("getMarketCalendar", () => {
    const mockCalendarData = [
      {
        date: "2022-01-03",
        open: "09:30",
        close: "16:00",
        session_open: "04:00",
        session_close: "20:00",
      },
    ];

    it("should fetch and format market calendar successfully", async () => {
      mockClient.getCalendar.mockResolvedValue(mockCalendarData);

      const result = await alpacaService.getMarketCalendar(
        "2022-01-01",
        "2022-01-31"
      );

      expect(result).toHaveLength(1);
      expect(result[0]).toEqual({
        date: "2022-01-03",
        open: "09:30",
        close: "16:00",
        sessionOpen: "04:00",
        sessionClose: "20:00",
      });

      expect(mockClient.getCalendar).toHaveBeenCalledWith({
        start: "2022-01-01",
        end: "2022-01-31",
      });
    });
  });

  describe("getMarketStatus", () => {
    const mockClockData = {
      timestamp: "2022-01-01T10:30:00Z",
      is_open: true,
      next_open: "2022-01-02T09:30:00Z",
      next_close: "2022-01-01T16:00:00Z",
    };

    it("should fetch market status successfully", async () => {
      mockClient.getClock.mockResolvedValue(mockClockData);

      const result = await alpacaService.getMarketStatus();

      expect(result).toEqual({
        timestamp: "2022-01-01T10:30:00Z",
        isOpen: true,
        nextOpen: "2022-01-02T09:30:00Z",
        nextClose: "2022-01-01T16:00:00Z",
        timezone: "America/New_York",
      });
    });

    it("should throw error when market status fetch fails", async () => {
      mockClient.getClock.mockRejectedValue(new Error("API error"));

      await expect(alpacaService.getMarketStatus()).rejects.toThrow(
        "Failed to fetch market status: API error"
      );
    });
  });

  describe("validateCredentials", () => {
    it("should return valid true when credentials are valid", async () => {
      const mockAccount = { id: "account-123", status: "ACTIVE" };
      mockClient.getAccount.mockResolvedValue(mockAccount);

      const result = await alpacaService.validateCredentials();

      expect(result).toEqual({
        valid: true,
        accountId: "account-123",
        status: "ACTIVE",
        environment: "paper",
      });
    });

    it("should return valid false when credentials are invalid", async () => {
      mockClient.getAccount.mockRejectedValue(new Error("Unauthorized"));

      const result = await alpacaService.validateCredentials();

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
      name: "Apple Inc",
      status: "active",
      tradable: true,
      marginable: true,
      shortable: true,
      easy_to_borrow: true,
      fractionable: false,
    };

    it("should fetch and format asset data successfully", async () => {
      mockClient.getAsset.mockResolvedValue(mockAssetData);

      const result = await alpacaService.getAsset("AAPL");

      expect(result).toEqual({
        id: "asset-123",
        class: "us_equity",
        exchange: "NASDAQ",
        symbol: "AAPL",
        name: "Apple Inc",
        status: "active",
        tradable: true,
        marginable: true,
        shortable: true,
        easyToBorrow: true,
        fractionable: false,
      });

      expect(mockClient.getAsset).toHaveBeenCalledWith("AAPL");
    });
  });

  describe("getSectorFromSymbol", () => {
    it("should classify tech stocks correctly", () => {
      expect(alpacaService.getSectorFromSymbol("AAPL")).toBe("Technology");
      expect(alpacaService.getSectorFromSymbol("MSFT")).toBe("Technology");
      expect(alpacaService.getSectorFromSymbol("GOOGL")).toBe("Technology");
    });

    it("should classify financial stocks correctly", () => {
      expect(alpacaService.getSectorFromSymbol("JPM")).toBe("Financials");
      expect(alpacaService.getSectorFromSymbol("BAC")).toBe("Financials");
    });

    it("should classify healthcare stocks correctly", () => {
      expect(alpacaService.getSectorFromSymbol("JNJ")).toBe("Healthcare");
      expect(alpacaService.getSectorFromSymbol("PFE")).toBe("Healthcare");
    });

    it("should return Other for unknown stocks", () => {
      expect(alpacaService.getSectorFromSymbol("UNKNOWN")).toBe("Other");
    });
  });

  describe("calculateBasicSectorAllocation", () => {
    it("should calculate sector allocation correctly", () => {
      const positions = [
        { symbol: "AAPL", marketValue: 10000 },
        { symbol: "MSFT", marketValue: 5000 },
        { symbol: "JPM", marketValue: 3000 },
        { symbol: "UNKNOWN", marketValue: 2000 },
      ];

      const result = alpacaService.calculateBasicSectorAllocation(positions);

      expect(result.Technology).toEqual({
        value: 15000,
        weight: 75,
        positions: 2,
      });
      expect(result.Financials).toEqual({
        value: 3000,
        weight: 15,
        positions: 1,
      });
      expect(result.Other).toEqual({
        value: 2000,
        weight: 10,
        positions: 1,
      });
    });

    it("should handle empty positions", () => {
      const result = alpacaService.calculateBasicSectorAllocation([]);
      expect(result).toEqual({});
    });
  });

  describe("calculateBasicRiskMetrics", () => {
    it("should calculate risk metrics with sufficient history", () => {
      const positions = [];
      const history = [
        { equity: 10000 },
        { equity: 10100 },
        { equity: 9900 },
        { equity: 10200 },
        { equity: 9800 },
      ];

      const result = alpacaService.calculateBasicRiskMetrics(
        positions,
        history
      );

      expect(result.volatility).toBeGreaterThan(0);
      expect(result.sharpeRatio).toBeDefined();
      expect(result.maxDrawdown).toBeGreaterThan(0);
      expect(result.averageDailyReturn).toBeDefined();
      expect(result.annualizedReturn).toBeDefined();
    });

    it("should return default values with insufficient history", () => {
      const positions = [];
      const history = [{ equity: 10000 }];

      const result = alpacaService.calculateBasicRiskMetrics(
        positions,
        history
      );

      expect(result).toEqual({
        volatility: 0,
        sharpeRatio: 0,
        maxDrawdown: 0,
        beta: 1,
      });
    });
  });

  describe("getLatestQuote", () => {
    const mockQuoteData = {
      BidPrice: 149.5,
      AskPrice: 149.6,
      BidSize: 100,
      AskSize: 200,
      Timestamp: "2022-01-01T10:30:00Z",
      Conditions: ["R"],
      Exchange: "NASDAQ",
    };

    it("should fetch and format quote data successfully", async () => {
      mockClient.getLatestQuote.mockResolvedValue(mockQuoteData);

      const result = await alpacaService.getLatestQuote("AAPL");

      expect(result).toEqual({
        symbol: "AAPL",
        bidPrice: 149.5,
        askPrice: 149.6,
        bidSize: 100,
        askSize: 200,
        timestamp: "2022-01-01T10:30:00Z",
        conditions: ["R"],
        exchange: "NASDAQ",
      });
    });

    it("should return null when no quote data available", async () => {
      mockClient.getLatestQuote.mockResolvedValue(null);

      const result = await alpacaService.getLatestQuote("INVALID");

      expect(result).toBeNull();
    });

    it("should return null on API error", async () => {
      mockClient.getLatestQuote.mockRejectedValue(new Error("API error"));

      const result = await alpacaService.getLatestQuote("AAPL");

      expect(result).toBeNull();
    });
  });

  describe("getLatestTrade", () => {
    const mockTradeData = {
      Price: 149.55,
      Size: 100,
      Timestamp: "2022-01-01T10:30:00Z",
      Conditions: ["@"],
      Exchange: "NASDAQ",
    };

    it("should fetch and format trade data successfully", async () => {
      mockClient.getLatestTrade.mockResolvedValue(mockTradeData);

      const result = await alpacaService.getLatestTrade("AAPL");

      expect(result).toEqual({
        symbol: "AAPL",
        price: 149.55,
        size: 100,
        timestamp: "2022-01-01T10:30:00Z",
        conditions: ["@"],
        exchange: "NASDAQ",
      });
    });

    it("should return null when no trade data available", async () => {
      mockClient.getLatestTrade.mockResolvedValue(null);

      const result = await alpacaService.getLatestTrade("INVALID");

      expect(result).toBeNull();
    });

    it("should return null on API error", async () => {
      mockClient.getLatestTrade.mockRejectedValue(new Error("API error"));

      const result = await alpacaService.getLatestTrade("AAPL");

      expect(result).toBeNull();
    });
  });

  describe("getBars", () => {
    const mockBarsData = {
      bars: [
        {
          Timestamp: "2022-01-01T09:30:00Z",
          OpenPrice: 150.0,
          HighPrice: 151.0,
          LowPrice: 149.5,
          ClosePrice: 150.5,
          Volume: 1000,
          TradeCount: 10,
          VWAP: 150.25,
        },
      ],
    };

    it("should fetch and format bars data successfully", async () => {
      mockClient.getBars.mockResolvedValue(mockBarsData);

      const result = await alpacaService.getBars("AAPL", {
        timeframe: "1Min",
        limit: 100,
      });

      expect(result).toHaveLength(1);
      expect(result[0]).toEqual({
        symbol: "AAPL",
        timestamp: "2022-01-01T09:30:00Z",
        open: 150.0,
        high: 151.0,
        low: 149.5,
        close: 150.5,
        volume: 1000,
        tradeCount: 10,
        vwap: 150.25,
      });
    });

    it("should return empty array when no bars data available", async () => {
      mockClient.getBars.mockResolvedValue({ bars: [] });

      const result = await alpacaService.getBars("INVALID");

      expect(result).toEqual([]);
    });

    it("should return empty array on API error", async () => {
      mockClient.getBars.mockRejectedValue(new Error("API error"));

      const result = await alpacaService.getBars("AAPL");

      expect(result).toEqual([]);
    });

    it("should use default options when none provided", async () => {
      mockClient.getBars.mockResolvedValue(mockBarsData);

      await alpacaService.getBars("AAPL");

      expect(mockClient.getBars).toHaveBeenCalledWith("AAPL", {
        timeframe: "1Min",
        start: expect.any(String),
        end: expect.any(String),
        limit: 100,
        asof: null,
        feed: null,
        page_token: null,
      });
    });
  });

  describe("getMarketClock", () => {
    const mockClockData = {
      timestamp: "2022-01-01T10:30:00Z",
      is_open: true,
      next_open: "2022-01-02T09:30:00Z",
      next_close: "2022-01-01T16:00:00Z",
    };

    it("should fetch market clock successfully", async () => {
      mockClient.getClock.mockResolvedValue(mockClockData);

      const result = await alpacaService.getMarketClock();

      expect(result).toEqual({
        timestamp: "2022-01-01T10:30:00Z",
        isOpen: true,
        nextOpen: "2022-01-02T09:30:00Z",
        nextClose: "2022-01-01T16:00:00Z",
        timezone: "America/New_York",
      });
    });

    it("should throw error on API failure", async () => {
      mockClient.getClock.mockRejectedValue(new Error("API error"));

      await expect(alpacaService.getMarketClock()).rejects.toThrow("API error");
    });
  });

  describe("createOrder", () => {
    const mockOrderData = {
      id: "order-123",
      symbol: "AAPL",
      qty: "10",
      side: "buy",
      order_type: "market",
      time_in_force: "day",
      status: "new",
      submitted_at: "2022-01-01T10:30:00Z",
      filled_qty: "0",
      filled_avg_price: null,
    };

    it("should create market order successfully", async () => {
      mockClient.createOrder.mockResolvedValue(mockOrderData);

      const result = await alpacaService.createOrder(
        "AAPL",
        10,
        "buy",
        "market"
      );

      expect(result).toEqual({
        orderId: "order-123",
        symbol: "AAPL",
        qty: 10,
        side: "buy",
        type: "market",
        time_in_force: "day",
        status: "new",
        createdAt: "2022-01-01T10:30:00Z",
        filledQty: 0,
        filledAvgPrice: null,
      });

      expect(mockClient.createOrder).toHaveBeenCalledWith({
        symbol: "AAPL",
        qty: 10,
        side: "buy",
        type: "market",
        time_in_force: "day",
      });
    });

    it("should create limit order successfully", async () => {
      const limitOrderData = { ...mockOrderData, order_type: "limit" };
      mockClient.createOrder.mockResolvedValue(limitOrderData);

      const result = await alpacaService.createOrder(
        "AAPL",
        10,
        "buy",
        "limit",
        150.0
      );

      expect(result.type).toBe("limit");

      expect(mockClient.createOrder).toHaveBeenCalledWith({
        symbol: "AAPL",
        qty: 10,
        side: "buy",
        type: "limit",
        time_in_force: "day",
        limit_price: 150.0,
      });
    });

    it("should validate required parameters", async () => {
      await expect(alpacaService.createOrder("", 10, "buy")).rejects.toThrow(
        "Symbol is required"
      );

      await expect(alpacaService.createOrder("AAPL", 0, "buy")).rejects.toThrow(
        "Quantity must be a positive number"
      );

      await expect(
        alpacaService.createOrder("AAPL", 10, "invalid")
      ).rejects.toThrow("Side must be buy or sell");

      await expect(
        alpacaService.createOrder("AAPL", 10, "buy", "limit")
      ).rejects.toThrow("Limit price is required for limit orders");
    });

    it("should handle order creation failure", async () => {
      mockClient.createOrder.mockRejectedValue(new Error("Insufficient funds"));

      await expect(
        alpacaService.createOrder("AAPL", 10, "buy")
      ).rejects.toThrow("Failed to create order: Insufficient funds");
    });

    it("should handle undefined order_type in response", async () => {
      const orderWithoutType = { ...mockOrderData, order_type: undefined };
      mockClient.createOrder.mockResolvedValue(orderWithoutType);

      const result = await alpacaService.createOrder(
        "AAPL",
        10,
        "buy",
        "market"
      );

      expect(result.type).toBe("market");
    });
  });
});

const Alpaca = require("@alpacahq/alpaca-trade-api");

/**
 * Alpaca Integration Service
 *
 * This service handles all Alpaca API operations for portfolio management.
 * It supports both paper trading (sandbox) and live trading environments.
 *
 * Security Features:
 * - API keys are never logged
 * - Supports both paper and live trading modes
 * - Rate limiting and error handling
 * - Data validation and sanitization
 */

class AlpacaService {
  constructor(apiKey, apiSecret, isPaper = true) {
    if (!apiKey || !apiSecret) {
      throw new Error("Alpaca API key and secret are required");
    }

    this.client = new Alpaca({
      keyId: apiKey,
      secretKey: apiSecret,
      paper: isPaper,
      baseUrl: isPaper ? 'https://paper-api.alpaca.markets' : 'https://api.alpaca.markets',
      dataBaseUrl: 'https://data.alpaca.markets',
      usePolygon: false, // Use Alpaca data instead of Polygon
    });

    this.isPaper = isPaper;
    this.rateLimitWindow = 60000; // 1 minute
    this.maxRequestsPerWindow = 200;
    this.requestTimes = [];
  }

  /**
   * Rate limiting check
   */
  checkRateLimit() {
    const now = Date.now();
    const windowStart = now - this.rateLimitWindow;

    // Remove old requests outside the window
    this.requestTimes = this.requestTimes.filter((time) => time > windowStart);

    if (this.requestTimes.length >= this.maxRequestsPerWindow) {
      throw new Error("Rate limit exceeded. Please try again in a minute.");
    }

    this.requestTimes.push(now);
  }

  /**
   * Get account information
   */
  async getAccount() {
    try {
      this.checkRateLimit();

      const account = await this.client.getAccount();

      return {
        accountId: account.id,
        status: account.status,
        currency: account.currency,
        buyingPower: parseFloat(account.buying_power),
        cash: parseFloat(account.cash),
        portfolioValue: parseFloat(account.portfolio_value),
        equity: parseFloat(account.equity),
        lastEquity: parseFloat(account.last_equity),
        dayTradeCount: parseInt(account.daytrade_count),
        dayTradingBuyingPower: parseFloat(account.daytrading_buying_power),
        regtBuyingPower: parseFloat(account.regt_buying_power),
        initialMargin: parseFloat(account.initial_margin),
        maintenanceMargin: parseFloat(account.maintenance_margin),
        longMarketValue: parseFloat(account.long_market_value),
        shortMarketValue: parseFloat(account.short_market_value),
        multiplier: parseFloat(account.multiplier),
        createdAt: account.created_at,
        tradingBlocked: account.trading_blocked,
        transfersBlocked: account.transfers_blocked,
        accountBlocked: account.account_blocked,
        patternDayTrader: account.pattern_day_trader,
        environment: this.isPaper ? "paper" : "live",
      };
    } catch (error) {
      console.error("Alpaca account fetch error:", error.message);
      // Check if it's a 401 (authentication failure)
      if (error.status === 401 || error.message.includes('401') || error.message.includes('Unauthorized')) {
        console.error("⚠️ CRITICAL: Alpaca API returned 401 Unauthorized - API credentials may be invalid or expired");
        console.error("⚠️ Please verify ALPACA_API_KEY and ALPACA_API_SECRET in environment variables");
      }
      throw new Error(`Failed to fetch account information: ${error.message}`);
    }
  }

  /**
   * Get all positions
   */
  async getPositions() {
    try {
      this.checkRateLimit();

      const positions = await this.client.getPositions();

      return positions.map((position) => ({
        symbol: position.symbol,
        assetId: position.asset_id,
        exchange: position.exchange,
        assetClass: position.asset_class,
        quantity: parseFloat(position.qty),
        side: position.side,
        marketValue: parseFloat(position.market_value),
        costBasis: parseFloat(position.cost_basis),
        unrealizedPL: parseFloat(position.unrealized_pl),
        unrealizedPLPercent: parseFloat(position.unrealized_plpc),
        unrealizedIntradayPL: parseFloat(position.unrealized_intraday_pl),
        unrealizedIntradayPLPercent: parseFloat(
          position.unrealized_intraday_plpc
        ),
        currentPrice: parseFloat(position.current_price),
        lastDayPrice: parseFloat(position.lastday_price),
        changeToday: parseFloat(position.change_today),
        averageEntryPrice: parseFloat(position.avg_entry_price),
        qtyAvailable: parseFloat(position.qty_available),
        lastUpdated: new Date().toISOString(),
      }));
    } catch (error) {
      console.error("Alpaca positions fetch error:", error.message);
      // Check if it's a 401 (authentication failure)
      if (error.status === 401 || error.message.includes('401') || error.message.includes('Unauthorized')) {
        console.error("⚠️ CRITICAL: Alpaca API returned 401 Unauthorized - API credentials may be invalid or expired");
        console.error("⚠️ Please verify ALPACA_API_KEY and ALPACA_API_SECRET in environment variables");
      }
      throw new Error(`Failed to fetch positions: ${error.message}`);
    }
  }

  /**
   * Get portfolio history
   */
  async getPortfolioHistory(period = "1M", timeframe = "1Day") {
    try {
      this.checkRateLimit();

      // Alpaca API: period can be "1M", "3M", "6M", "1A" (not "1Y"), "all"
      // Only pass required parameters to avoid 422 errors
      const portfolio = await this.client.getPortfolioHistory({
        period: period,
        timeframe: timeframe
      });

      if (!portfolio.timestamp || !portfolio.equity) {
        return [];
      }

      // Convert timestamps and equity values to a usable format
      // CRITICAL: Only include real Alpaca data - do not synthesize $0 values
      const history = [];
      for (let i = 0; i < portfolio.timestamp.length; i++) {
        if (portfolio.equity[i] !== null) {
          history.push({
            date: new Date(portfolio.timestamp[i] * 1000)
              .toISOString()
              .split("T")[0],
            equity: parseFloat(portfolio.equity[i]),
            // CRITICAL: Use null for missing data, not fake 0
            profitLoss: portfolio.profit_loss && portfolio.profit_loss[i] !== null
              ? parseFloat(portfolio.profit_loss[i])
              : null,
            profitLossPercent: portfolio.profit_loss_pct && portfolio.profit_loss_pct[i] !== null
              ? parseFloat(portfolio.profit_loss_pct[i])
              : null,
            baseValue: portfolio.base_value !== null && portfolio.base_value !== undefined
              ? parseFloat(portfolio.base_value)
              : null,
          });
        }
      }

      return history.sort((a, b) => new Date(a.date) - new Date(b.date));
    } catch (error) {
      console.error("Alpaca portfolio history fetch error:", error.message);
      throw new Error(`Failed to fetch portfolio history: ${error.message}`);
    }
  }

  /**
   * Get recent activities (orders, fills, etc.)
   */
  async getActivities(activityTypes = null, pageSize = 50) {
    try {
      this.checkRateLimit();

      // Use REST API call for trading account activities
      const queryParams = {
        activity_types: activityTypes || "FILL",
        page_size: pageSize,
      };

      console.log(`📊 Fetching activities from Alpaca: ${JSON.stringify(queryParams)}`);

      const activities = await this.client.sendRequest(
        `/v2/account/activities`,
        queryParams,
        null,
        "GET"
      );

      console.log(`✅ Received ${activities?.length || 0} activities from Alpaca`);

      return (activities || []).map((activity) => ({
        id: activity.id,
        activityType: activity.activity_type,
        date: activity.date,
        // CRITICAL: Only return real net_amount from Alpaca, never synthetic $0
        netAmount: activity.net_amount !== null && activity.net_amount !== undefined
          ? parseFloat(activity.net_amount)
          : null,
        symbol: activity.symbol,
        qty: activity.qty ? parseFloat(activity.qty) : null,
        price: activity.price ? parseFloat(activity.price) : null,
        side: activity.side,
        description: activity.description || activity.activity_type,
      }));
    } catch (error) {
      console.error("Alpaca activities fetch error:", error.message);
      throw new Error(`Failed to fetch activities: ${error.message}`);
    }
  }

  /**
   * Get market calendar
   */
  async getMarketCalendar(start = null, end = null) {
    try {
      this.checkRateLimit();

      const calendar = await this.client.getCalendar({
        start: start,
        end: end,
      });

      return calendar.map((day) => ({
        date: day.date,
        open: day.open,
        close: day.close,
        sessionOpen: day.session_open,
        sessionClose: day.session_close,
      }));
    } catch (error) {
      console.error("Alpaca calendar fetch error:", error.message);
      throw new Error(`Failed to fetch market calendar: ${error.message}`);
    }
  }

  /**
   * Get current market status
   */
  async getMarketStatus() {
    try {
      this.checkRateLimit();

      const clock = await this.client.getClock();

      return {
        timestamp: clock.timestamp,
        isOpen: clock.is_open,
        nextOpen: clock.next_open,
        nextClose: clock.next_close,
        timezone: "America/New_York",
      };
    } catch (error) {
      console.error("Alpaca market status fetch error:", error.message);
      throw new Error(`Failed to fetch market status: ${error.message}`);
    }
  }

  /**
   * Validate API credentials
   */
  async validateCredentials() {
    try {
      this.checkRateLimit();

      // Simple test - try to get account info
      const account = await this.client.getAccount();

      return {
        valid: true,
        accountId: account.id,
        status: account.status,
        environment: this.isPaper ? "paper" : "live",
      };
    } catch (error) {
      console.error("Alpaca credential validation error:", error.message);

      return {
        valid: false,
        error: error.message,
        environment: this.isPaper ? "paper" : "live",
      };
    }
  }

  /**
   * Get asset information for a symbol
   */
  async getAsset(symbol) {
    try {
      this.checkRateLimit();

      const asset = await this.client.getAsset(symbol);

      return {
        id: asset.id,
        class: asset.class,
        exchange: asset.exchange,
        symbol: asset.symbol,
        name: asset.name,
        status: asset.status,
        tradable: asset.tradable,
        marginable: asset.marginable,
        shortable: asset.shortable,
        easyToBorrow: asset.easy_to_borrow,
        fractionable: asset.fractionable,
      };
    } catch (error) {
      console.error("Alpaca asset fetch error:", error.message);
      throw new Error(`Failed to fetch asset information: ${error.message}`);
    }
  }

  /**
   * Get portfolio summary with calculated metrics
   */
  async getPortfolioSummary() {
    try {
      const [account, positions, history] = await Promise.all([
        this.getAccount(),
        this.getPositions(),
        this.getPortfolioHistory("1M", "1Day"),
      ]);

      // Calculate portfolio metrics
      const totalValue = account.portfolioValue;
      const totalPnL = positions.reduce(
        (sum, pos) => sum + pos.unrealizedPL,
        0
      );
      const totalPnLPercent =
        totalValue > 0 ? (totalPnL / (totalValue - totalPnL)) * 100 : 0;

      // Calculate day change
      const dayPnL = positions.reduce(
        (sum, pos) => sum + pos.unrealizedIntradayPL,
        0
      );
      const dayPnLPercent =
        positions.reduce(
          (sum, pos) => sum + pos.unrealizedIntradayPLPercent,
          0
        ) / positions.length;

      // Sector allocation (simplified - would need additional data for real sectors)
      const sectorAllocation = this.calculateBasicSectorAllocation(positions);

      // Risk metrics
      const riskMetrics = this.calculateBasicRiskMetrics(positions, history);

      return {
        account: account,
        summary: {
          totalValue: totalValue,
          totalCash: account.cash,
          totalPnL: totalPnL,
          totalPnLPercent: totalPnLPercent,
          dayPnL: dayPnL,
          dayPnLPercent: dayPnLPercent,
          positionsCount: positions.length,
          buyingPower: account.buyingPower,
        },
        positions: positions,
        sectorAllocation: sectorAllocation,
        riskMetrics: riskMetrics,
        performance: history.slice(-30), // Last 30 days
        lastUpdated: new Date().toISOString(),
      };
    } catch (error) {
      console.error("Alpaca portfolio summary error:", error.message);
      throw new Error(`Failed to generate portfolio summary: ${error.message}`);
    }
  }

  /**
   * Calculate basic sector allocation (simplified)
   */
  calculateBasicSectorAllocation(positions) {
    const sectors = {};
    const totalValue = positions.reduce((sum, pos) => sum + pos.marketValue, 0);

    positions.forEach((position) => {
      // This is a simplified sector mapping - in production you'd use a more comprehensive service
      const sector = this.getSectorFromSymbol(position.symbol);

      if (!sectors[sector]) {
        sectors[sector] = {
          value: 0,
          weight: 0,
          positions: 0,
        };
      }

      sectors[sector].value += position.marketValue;
      sectors[sector].positions += 1;
    });

    // Calculate weights
    Object.keys(sectors).forEach((sector) => {
      sectors[sector].weight =
        totalValue > 0 ? (sectors[sector].value / totalValue) * 100 : 0;
    });

    return sectors;
  }

  /**
   * Simplified sector mapping (in production, use a proper sector classification service)
   */
  getSectorFromSymbol(symbol) {
    const techStocks = [
      "AAPL",
      "MSFT",
      "GOOGL",
      "AMZN",
      "TSLA",
      "META",
      "NVDA",
      "CRM",
      "ORCL",
      "ADBE",
    ];
    const financialStocks = [
      "JPM",
      "BAC",
      "WFC",
      "GS",
      "MS",
      "C",
      "AXP",
      "BLK",
      "SCHW",
    ];
    const healthcareStocks = [
      "JNJ",
      "PFE",
      "UNH",
      "ABBV",
      "MRK",
      "TMO",
      "DHR",
      "BMY",
      "LLY",
    ];

    if (techStocks.includes(symbol)) return "Technology";
    if (financialStocks.includes(symbol)) return "Financials";
    if (healthcareStocks.includes(symbol)) return "Healthcare";

    return "Other";
  }

  /**
   * Get latest quote data for a symbol
   */
  async getLatestQuote(symbol) {
    try {
      this.checkRateLimit();

      console.log(`📊 Fetching latest quote for ${symbol} from Alpaca`);
      const quote = await this.client.getLatestQuote(symbol);

      if (!quote) {
        console.warn(`⚠️ No quote data returned for ${symbol}`);
        return null;
      }

      console.log(
        `✅ Quote fetched for ${symbol}: bid=${quote.BidPrice}, ask=${quote.AskPrice}`
      );

      return {
        symbol: symbol,
        bidPrice: parseFloat(quote.BidPrice),
        askPrice: parseFloat(quote.AskPrice),
        bidSize: parseInt(quote.BidSize),
        askSize: parseInt(quote.AskSize),
        timestamp: quote.Timestamp || new Date().toISOString(),
        conditions: quote.Conditions || [],
        exchange: quote.Exchange || "UNKNOWN",
      };
    } catch (error) {
      console.error(`❌ Alpaca quote fetch error for ${symbol}:`, {
        error: error.message,
        statusCode: error.status,
        errorCode: error.code,
      });

      // Don't throw - return null to let calling code handle gracefully
      return null;
    }
  }

  /**
   * Get latest trade data for a symbol
   */
  async getLatestTrade(symbol) {
    try {
      this.checkRateLimit();

      console.log(`📊 Fetching latest trade for ${symbol} from Alpaca`);
      const trade = await this.client.getLatestTrade(symbol);

      if (!trade) {
        console.warn(`⚠️ No trade data returned for ${symbol}`);
        return null;
      }

      console.log(
        `✅ Trade fetched for ${symbol}: price=${trade.Price}, size=${trade.Size}`
      );

      return {
        symbol: symbol,
        price: parseFloat(trade.Price),
        size: parseInt(trade.Size),
        timestamp: trade.Timestamp || new Date().toISOString(),
        conditions: trade.Conditions || [],
        exchange: trade.Exchange || "UNKNOWN",
      };
    } catch (error) {
      console.error(`❌ Alpaca trade fetch error for ${symbol}:`, {
        error: error.message,
        statusCode: error.status,
        errorCode: error.code,
      });

      // Don't throw - return null to let calling code handle gracefully
      return null;
    }
  }

  /**
   * Get bars/OHLCV data for a symbol
   */
  async getBars(symbol, options = {}) {
    try {
      this.checkRateLimit();

      const {
        timeframe = "1Min",
        start = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString(),
        end = new Date().toISOString(),
        limit = 100,
      } = options;

      console.log(`📊 Fetching bars for ${symbol} from Alpaca`, {
        timeframe,
        start: start.split("T")[0],
        limit,
      });

      const bars = await this.client.getBars(symbol, {
        timeframe: timeframe,
        start: start,
        end: end,
        limit: limit,
        asof: null,
        feed: null,
        page_token: null,
      });

      if (!bars || !bars.bars || bars.bars.length === 0) {
        console.warn(`⚠️ No bars data returned for ${symbol}`);
        return [];
      }

      console.log(`✅ Bars fetched for ${symbol}: ${bars.bars.length} bars`);

      return bars.bars.map((bar) => ({
        symbol: symbol,
        timestamp: bar.Timestamp,
        open: parseFloat(bar.OpenPrice),
        high: parseFloat(bar.HighPrice),
        low: parseFloat(bar.LowPrice),
        close: parseFloat(bar.ClosePrice),
        volume: parseInt(bar.Volume),
        tradeCount: parseInt(bar.TradeCount) || 0,
        vwap: parseFloat(bar.VWAP) || null,
      }));
    } catch (error) {
      console.error(`❌ Alpaca bars fetch error for ${symbol}:`, {
        error: error.message,
        statusCode: error.status,
        errorCode: error.code,
        options,
      });

      // Don't throw - return empty array to let calling code handle gracefully
      return [];
    }
  }

  /**
   * Get market status and trading calendar
   */
  async getMarketClock() {
    try {
      this.checkRateLimit();

      console.log("📊 Fetching market clock from Alpaca");
      const clock = await this.client.getClock();

      console.log(
        `✅ Market clock fetched: ${clock.is_open ? "OPEN" : "CLOSED"}`
      );

      return {
        timestamp: clock.timestamp,
        isOpen: clock.is_open,
        nextOpen: clock.next_open,
        nextClose: clock.next_close,
        timezone: "America/New_York",
      };
    } catch (error) {
      console.error("❌ Alpaca market clock fetch error:", {
        error: error.message,
        statusCode: error.status,
        errorCode: error.code,
      });

      // Throw error instead of returning fallback data
      throw new Error(`Failed to fetch market status: ${error.message}`);
    }
  }

  /**
   * Calculate basic risk metrics
   */
  calculateBasicRiskMetrics(positions, history) {
    if (history.length < 2) {
      return {
        volatility: 0,
        sharpeRatio: 0,
        maxDrawdown: 0,
        beta: 1,
      };
    }

    // Calculate daily returns
    const returns = [];
    for (let i = 1; i < history.length; i++) {
      const dailyReturn =
        (history[i].equity - history[i - 1].equity) / history[i - 1].equity;
      returns.push(dailyReturn);
    }

    // Calculate volatility (standard deviation of returns)
    const avgReturn = returns.reduce((sum, r) => sum + r, 0) / returns.length;
    const variance =
      returns.reduce((sum, r) => sum + Math.pow(r - avgReturn, 2), 0) /
      returns.length;
    const volatility = Math.sqrt(variance) * Math.sqrt(252); // Annualized

    // Calculate max drawdown
    let maxDrawdown = 0;
    let peak = history[0].equity;

    history.forEach((day) => {
      if (day.equity > peak) {
        peak = day.equity;
      }
      const drawdown = (peak - day.equity) / peak;
      if (drawdown > maxDrawdown) {
        maxDrawdown = drawdown;
      }
    });

    // Simplified Sharpe ratio (assuming risk-free rate of 3%)
    const riskFreeRate = 0.03;
    const excessReturn = avgReturn * 252 - riskFreeRate;
    const sharpeRatio = volatility > 0 ? excessReturn / volatility : 0;

    return {
      volatility: volatility,
      sharpeRatio: sharpeRatio,
      maxDrawdown: maxDrawdown,
      beta: 1, // Simplified - would need market data for real beta calculation
      averageDailyReturn: avgReturn,
      annualizedReturn: avgReturn * 252,
    };
  }

  /**
   * Create trading order (market or limit)
   */
  async createOrder(
    symbolOrParams,
    quantity,
    side,
    type = "market",
    limitPrice = null
  ) {
    try {
      // Handle both object and individual parameter calling conventions
      let symbol, qty, orderSide, orderType, orderLimitPrice;

      if (typeof symbolOrParams === 'object') {
        // Object-based parameters
        ({ symbol, qty, side: orderSide, type: orderType, limit_price: orderLimitPrice } = symbolOrParams);
        quantity = qty;
        side = orderSide;
        type = orderType || "market";
        limitPrice = orderLimitPrice;
      } else {
        // Individual parameters
        symbol = symbolOrParams;
      }

      // Validate required parameters
      if (!symbol) {
        throw new Error("Symbol is required");
      }
      if (!quantity || quantity <= 0) {
        throw new Error("Quantity must be a positive number");
      }
      if (!side || !["buy", "sell"].includes(side)) {
        throw new Error("Side must be buy or sell");
      }

      // Validate limit price for limit orders
      if (type === "limit" && !limitPrice) {
        throw new Error("Limit price is required for limit orders");
      }

      this.checkRateLimit();

      const orderParams = {
        symbol: symbol,
        qty: quantity,
        side: side,
        type: type,
        time_in_force: "day",
      };

      if (type === "limit") {
        orderParams.limit_price = limitPrice;
      }

      const order = await this.client.createOrder(orderParams);

      return {
        orderId: order.id,
        symbol: order.symbol,
        qty: parseFloat(order.qty),
        side: order.side,
        type: order.order_type || type, // Use provided type if order_type is undefined
        time_in_force: order.time_in_force,
        status: order.status,
        createdAt: order.submitted_at,
        // CRITICAL: Only return real filled_qty from Alpaca, never synthetic 0
        filledQty: order.filled_qty !== null && order.filled_qty !== undefined
          ? parseFloat(order.filled_qty)
          : null,
        filledAvgPrice: order.filled_avg_price
          ? parseFloat(order.filled_avg_price)
          : null,
      };
    } catch (error) {
      console.error("Alpaca order creation error:", error.message);
      throw new Error(`Failed to create order: ${error.message}`);
    }
  }

  async getOrders(options = {}) {
    try {
      this.checkRateLimit();
      console.log("Fetching orders from Alpaca");

      // Build query parameters
      const queryParams = {};
      if (options.status) queryParams.status = options.status;
      if (options.limit) queryParams.limit = options.limit;
      if (options.nested) queryParams.nested = options.nested;

      console.log(`📊 Fetching orders with params: ${JSON.stringify(queryParams)}`);

      // Try to use the SDK method first if available
      let orders = [];
      try {
        if (this.client.getOrders && typeof this.client.getOrders === 'function') {
          console.log('Using SDK getOrders method...');
          orders = await this.client.getOrders(options);
          console.log(`✅ SDK method returned ${orders?.length || 0} orders`);
        } else {
          throw new Error('getOrders not available on SDK');
        }
      } catch (sdkError) {
        console.log(`SDK method not available: ${sdkError.message}, trying REST API...`);
        // Fallback to REST API call for orders
        orders = await this.client.sendRequest(
          `/v2/orders`,
          queryParams,
          null,
          "GET"
        );
        console.log(`✅ REST API returned ${orders?.length || 0} orders`);
      }

      return (orders || []).map((order) => ({
        id: order.id,
        symbol: order.symbol,
        qty: parseFloat(order.qty),
        side: order.side,
        type: order.order_type,
        status: order.status,
        createdAt: order.submitted_at,
        // CRITICAL: Only return real filled_qty from Alpaca, never synthetic 0
        filledQty: order.filled_qty !== null && order.filled_qty !== undefined
          ? parseFloat(order.filled_qty)
          : null,
        filledAvgPrice: order.filled_avg_price
          ? parseFloat(order.filled_avg_price)
          : null,
        limitPrice: order.limit_price ? parseFloat(order.limit_price) : null,
        stopPrice: order.stop_price ? parseFloat(order.stop_price) : null,
        timeInForce: order.time_in_force,
      }));
    } catch (error) {
      console.error("Alpaca get orders error:", error.message);
      throw new Error(`Failed to get orders: ${error.message}`);
    }
  }

  async cancelOrder(orderId) {
    try {
      this.checkRateLimit();
      console.log(`Canceling order ${orderId} on Alpaca`);
      const result = await this.client.cancelOrder(orderId);
      return {
        orderId: orderId,
        status: "cancelled",
        cancelledAt: new Date().toISOString(),
        success: true,
      };
    } catch (error) {
      console.error("Alpaca cancel order error:", error.message);
      throw new Error(`Failed to cancel order: ${error.message}`);
    }
  }

  /**
   * Generic method for making HTTP requests to Alpaca API
   * Used for testing compatibility
   */
  /**
   * Get a specific position by symbol
   */
  async getPosition(symbol) {
    this.checkRateLimit();

    try {
      const positions = await this.client.getPositions();
      const position = positions.find((pos) => pos.symbol === symbol);

      if (!position) {
        return null;
      }

      return {
        symbol: position.symbol,
        qty: parseFloat(position.qty),
        side: position.side,
        market_value: position.market_value !== null && position.market_value !== undefined ? parseFloat(position.market_value) : null,
        cost_basis: position.cost_basis !== null && position.cost_basis !== undefined ? parseFloat(position.cost_basis) : null,
        unrealized_pl: position.unrealized_pl !== null && position.unrealized_pl !== undefined ? parseFloat(position.unrealized_pl) : null,
        unrealized_plpc: position.unrealized_plpc !== null && position.unrealized_plpc !== undefined ? parseFloat(position.unrealized_plpc) : null,
        current_price: position.current_price !== null && position.current_price !== undefined ? parseFloat(position.current_price) : null,
        lastday_price: position.lastday_price !== null && position.lastday_price !== undefined ? parseFloat(position.lastday_price) : null,
        change_today: position.change_today !== null && position.change_today !== undefined ? parseFloat(position.change_today) : null,
      };
    } catch (error) {
      console.error("Error fetching position:", error.message);
      throw new Error(
        `Failed to fetch position for ${symbol}: ${error.message}`
      );
    }
  }

  /**
   * Get tradable assets
   */
  async getAssets(options = {}) {
    this.checkRateLimit();

    try {
      const assets = await this.client.getAssets(options);

      return assets.map((asset) => ({
        id: asset.id,
        class: asset.class,
        exchange: asset.exchange,
        symbol: asset.symbol,
        name: asset.name,
        status: asset.status,
        tradable: asset.tradable,
        marginable: asset.marginable,
        shortable: asset.shortable,
        easy_to_borrow: asset.easy_to_borrow,
        fractionable: asset.fractionable,
      }));
    } catch (error) {
      console.error("Error fetching assets:", error.message);
      throw new Error(`Failed to fetch assets: ${error.message}`);
    }
  }

  /**
   * Get latest trade data for a symbol
   */
  async getLastTrade(symbol) {
    this.checkRateLimit();

    try {
      const trade = await this.client.getLastTrade(symbol);

      return {
        symbol: symbol,
        price: parseFloat(trade.price),
        size: parseInt(trade.size),
        timestamp: trade.timestamp,
        timeframe: trade.timeframe,
        exchange: trade.exchange,
      };
    } catch (error) {
      console.error("Error fetching last trade:", error.message);
      throw new Error(
        `Failed to fetch last trade for ${symbol}: ${error.message}`
      );
    }
  }

  /**
   * Get all watchlists
   */
  async getWatchlists() {
    this.checkRateLimit();

    try {
      const watchlists = await this.client.getWatchlists();

      return watchlists.map((watchlist) => ({
        id: watchlist.id,
        name: watchlist.name,
        account_id: watchlist.account_id,
        created_at: watchlist.created_at,
        updated_at: watchlist.updated_at,
        assets: watchlist.assets || [],
      }));
    } catch (error) {
      console.error("Error fetching watchlists:", error.message);
      throw new Error(`Failed to fetch watchlists: ${error.message}`);
    }
  }

  /**
   * Create a new watchlist
   */
  async createWatchlist(options) {
    this.checkRateLimit();

    try {
      const { name, symbols = [] } = options;

      if (!name) {
        throw new Error("Watchlist name is required");
      }

      const watchlist = await this.client.createWatchlist({
        name: name,
        symbols: symbols,
      });

      return {
        id: watchlist.id,
        name: watchlist.name,
        account_id: watchlist.account_id,
        created_at: watchlist.created_at,
        updated_at: watchlist.updated_at,
        assets: watchlist.assets || [],
      };
    } catch (error) {
      console.error("Error creating watchlist:", error.message);
      throw new Error(`Failed to create watchlist: ${error.message}`);
    }
  }

  async makeRequest(provider, endpoint) {
    try {
      this.checkRateLimit();

      // ⛔ CRITICAL FIX: NO FAKE MARKET DATA EVER
      // This is a production system handling real money
      // Never return mock prices or fake data
      console.error(`❌ PRODUCTION API CALL TO UNIMPLEMENTED ENDPOINT: ${provider}${endpoint}`);
      console.error(`❌ This should not happen - real API should be used in production`);
      console.error(`❌ Returning error instead of fake data`);

      return {
        success: false,
        error: `API endpoint not properly implemented - real API credentials may be missing: ${provider}${endpoint}`,
        provider: provider,
        endpoint: endpoint,
        rateLimited: false,
        warning: "This request would have returned FAKE DATA - prevented for data integrity"
      };
    } catch (error) {
      console.error(
        `Make request error for ${provider}${endpoint}:`,
        error.message
      );
      return {
        success: false,
        error: error.message,
        provider: provider,
        endpoint: endpoint,
        rateLimited: false,
      };
    }
  }
}

module.exports = AlpacaService;

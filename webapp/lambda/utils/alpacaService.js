const axios = require('axios');

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
      throw new Error('Alpaca API key and secret are required');
    }

    this.apiKey = apiKey;
    this.apiSecret = apiSecret;
    this.isPaper = isPaper;
    this.baseURL = isPaper 
      ? 'https://paper-api.alpaca.markets'
      : 'https://api.alpaca.markets';
    this.dataURL = 'https://data.alpaca.markets';
    this.wsURL = 'wss://stream.data.alpaca.markets';
    
    // Enhanced configuration with timeouts and retries
    const axiosConfig = {
      baseURL: this.baseURL,
      timeout: 30000, // 30 second timeout
      headers: {
        'APCA-API-KEY-ID': this.apiKey,
        'APCA-API-SECRET-KEY': this.apiSecret
      },
      retry: 3,
      retryDelay: 1000,
      validateStatus: function (status) {
        return status >= 200 && status < 300; // Default
      }
    };

    this.api = axios.create(axiosConfig);
    this.dataApi = axios.create({
      ...axiosConfig,
      baseURL: this.dataURL
    });

    // Add retry interceptor for both APIs
    this.setupRetryInterceptors();

    // Circuit breaker configuration
    this.circuitBreaker = {
      failures: 0,
      lastFailureTime: 0,
      isOpen: false,
      threshold: 5, // Open circuit after 5 failures
      timeout: 60000, // 1 minute circuit breaker timeout
      halfOpenMaxCalls: 3
    };

    this.rateLimitWindow = 60000; // 1 minute
    this.maxRequestsPerWindow = 200;
    this.requestTimes = [];
  }

  /**
   * Setup retry interceptors for axios instances
   */
  setupRetryInterceptors() {
    const retryInterceptor = (axiosInstance) => {
      axiosInstance.interceptors.response.use(
        (response) => response,
        async (error) => {
          const config = error.config;
          
          // Don't retry if we've exceeded max retries
          if (!config || !config.retry || config.__retryCount >= config.retry) {
            return Promise.reject(error);
          }
          
          // Don't retry on 4xx errors (client errors)
          if (error.response && error.response.status >= 400 && error.response.status < 500) {
            return Promise.reject(error);
          }
          
          // Increment retry count
          config.__retryCount = config.__retryCount || 0;
          config.__retryCount += 1;
          
          console.log(`🔄 Alpaca API retry ${config.__retryCount}/${config.retry} for ${config.url}`);
          
          // Wait before retrying with exponential backoff
          const delay = config.retryDelay * Math.pow(2, config.__retryCount - 1);
          await new Promise(resolve => setTimeout(resolve, delay));
          
          return axiosInstance(config);
        }
      );
    };
    
    retryInterceptor(this.api);
    retryInterceptor(this.dataApi);
  }

  /**
   * Circuit breaker check
   */
  checkCircuitBreaker() {
    const now = Date.now();
    
    if (this.circuitBreaker.isOpen) {
      if (now - this.circuitBreaker.lastFailureTime > this.circuitBreaker.timeout) {
        // Circuit breaker timeout expired, move to half-open state
        this.circuitBreaker.isOpen = false;
        this.circuitBreaker.failures = 0;
        console.log('🟡 Alpaca circuit breaker moved to HALF-OPEN state');
      } else {
        throw new Error('Alpaca API circuit breaker is OPEN. Service temporarily unavailable.');
      }
    }
  }

  /**
   * Record circuit breaker success
   */
  recordSuccess() {
    if (this.circuitBreaker.failures > 0) {
      console.log('✅ Alpaca API call successful, resetting circuit breaker');
      this.circuitBreaker.failures = 0;
      this.circuitBreaker.isOpen = false;
    }
  }

  /**
   * Record circuit breaker failure
   */
  recordFailure() {
    this.circuitBreaker.failures++;
    this.circuitBreaker.lastFailureTime = Date.now();
    
    if (this.circuitBreaker.failures >= this.circuitBreaker.threshold) {
      this.circuitBreaker.isOpen = true;
      console.error(`🔴 Alpaca circuit breaker OPENED after ${this.circuitBreaker.failures} failures`);
    } else {
      console.warn(`⚠️ Alpaca failure ${this.circuitBreaker.failures}/${this.circuitBreaker.threshold}`);
    }
  }

  /**
   * Enhanced API call wrapper with circuit breaker
   */
  async safeApiCall(apiCall, operationName = 'API call') {
    try {
      this.checkCircuitBreaker();
      this.checkRateLimit();
      
      const result = await apiCall();
      this.recordSuccess();
      return result;
    } catch (error) {
      this.recordFailure();
      
      // Enhanced error logging
      console.error(`❌ Alpaca ${operationName} failed:`, {
        message: error.message,
        status: error.response?.status,
        statusText: error.response?.statusText,
        data: error.response?.data,
        circuitBreakerState: this.circuitBreaker.isOpen ? 'OPEN' : 'CLOSED',
        failures: this.circuitBreaker.failures
      });
      
      throw error;
    }
  }

  /**
   * Rate limiting check
   */
  checkRateLimit() {
    const now = Date.now();
    const windowStart = now - this.rateLimitWindow;
    
    // Remove old requests outside the window
    this.requestTimes = this.requestTimes.filter(time => time > windowStart);
    
    if (this.requestTimes.length >= this.maxRequestsPerWindow) {
      throw new Error('Rate limit exceeded. Please try again in a minute.');
    }
    
    this.requestTimes.push(now);
  }

  /**
   * Get account information with enhanced error handling
   */
  async getAccount() {
    return await this.safeApiCall(async () => {
      const response = await this.api.get('/v2/account');
      const account = response.data;
      
      return {
        id: account.id,
        accountId: account.id,
        status: account.status,
        currency: account.currency,
        buyingPower: parseFloat(account.buying_power || 0),
        cash: parseFloat(account.cash || 0),
        portfolioValue: parseFloat(account.portfolio_value || 0),
        equity: parseFloat(account.equity || 0),
        lastEquity: parseFloat(account.last_equity || 0),
        dayTradeCount: parseInt(account.daytrade_count || 0),
        dayTradingBuyingPower: parseFloat(account.daytrading_buying_power || 0),
        regtBuyingPower: parseFloat(account.regt_buying_power || 0),
        initialMargin: parseFloat(account.initial_margin || 0),
        maintenanceMargin: parseFloat(account.maintenance_margin || 0),
        longMarketValue: parseFloat(account.long_market_value || 0),
        shortMarketValue: parseFloat(account.short_market_value || 0),
        multiplier: parseFloat(account.multiplier || 1),
        createdAt: account.created_at,
        tradingBlocked: account.trading_blocked,
        transfersBlocked: account.transfers_blocked,
        accountBlocked: account.account_blocked,
        patternDayTrader: account.pattern_day_trader,
        environment: this.isPaper ? 'paper' : 'live'
      };
    }, 'account fetch');
  }

  /**
   * Get all positions with enhanced error handling
   */
  async getPositions() {
    return await this.safeApiCall(async () => {
      const response = await this.api.get('/v2/positions');
      const positions = response.data;
      
      return positions.map(position => ({
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
        unrealizedIntradayPLPercent: parseFloat(position.unrealized_intraday_plpc),
        currentPrice: parseFloat(position.current_price),
        lastDayPrice: parseFloat(position.lastday_price),
        changeToday: parseFloat(position.change_today),
        averageEntryPrice: parseFloat(position.avg_entry_price),
        qtyAvailable: parseFloat(position.qty_available),
        lastUpdated: new Date().toISOString()
      }));
    }, 'positions fetch');
  }

  /**
   * Get portfolio history with enhanced error handling
   */
  async getPortfolioHistory(period = '1M', timeframe = '1Day') {
    return await this.safeApiCall(async () => {
      const response = await this.api.get(`/v2/account/portfolio/history?period=${period}&timeframe=${timeframe}&extended_hours=true`);
      const portfolio = response.data;

      if (!portfolio.timestamp || !portfolio.equity) {
        return [];
      }

      // Convert timestamps and equity values to a usable format
      const history = [];
      for (let i = 0; i < portfolio.timestamp.length; i++) {
        if (portfolio.equity[i] !== null) {
          history.push({
            date: new Date(portfolio.timestamp[i] * 1000).toISOString().split('T')[0],
            equity: parseFloat(portfolio.equity[i]),
            profitLoss: portfolio.profit_loss ? parseFloat(portfolio.profit_loss[i]) : 0,
            profitLossPercent: portfolio.profit_loss_pct ? parseFloat(portfolio.profit_loss_pct[i]) : 0,
            baseValue: portfolio.base_value ? parseFloat(portfolio.base_value) : 0
          });
        }
      }

      return history.sort((a, b) => new Date(a.date) - new Date(b.date));
    }, 'portfolio history fetch');
  }

  /**
   * Get real-time quotes for multiple symbols with enhanced error handling
   */
  async getMultiQuotes(symbols) {
    return await this.safeApiCall(async () => {
      const symbolsStr = symbols.join(',');
      const response = await this.dataApi.get(`/v2/stocks/quotes/latest?symbols=${symbolsStr}`);
      const quotes = response.data.quotes;
      
      return Object.keys(quotes).map(symbol => ({
        symbol: symbol,
        price: quotes[symbol].ap || quotes[symbol].bp || 0,
        bid: quotes[symbol].bp || 0,
        ask: quotes[symbol].ap || 0,
        bidSize: quotes[symbol].bs || 0,
        askSize: quotes[symbol].as || 0,
        timestamp: quotes[symbol].t,
        timeframe: 'realtime',
        exchange: quotes[symbol].ax || 'UNKNOWN'
      }));
    }, 'multi quotes fetch');
  }

  /**
   * Get historical bars for a symbol with enhanced error handling
   */
  async getBars(symbol, params = {}) {
    return await this.safeApiCall(async () => {
      const { timeframe = '1Day', start, end, limit = 100 } = params;
      const queryParams = new URLSearchParams({
        symbols: symbol,
        timeframe: timeframe,
        limit: limit.toString()
      });
      
      if (start) queryParams.append('start', start);
      if (end) queryParams.append('end', end);
      
      const response = await this.dataApi.get(`/v2/stocks/bars?${queryParams}`);
      const bars = response.data.bars[symbol] || [];
      
      return bars.map(bar => ({
        timestamp: bar.t,
        open: bar.o,
        high: bar.h,
        low: bar.l,
        close: bar.c,
        volume: bar.v,
        vwap: bar.vw || null
      }));
    }, 'bars fetch');
  }

  /**
   * Get websocket connection info for real-time data
   */
  getWebSocketConfig() {
    return {
      url: this.wsURL,
      apiKey: this.apiKey,
      apiSecret: this.apiSecret,
      feed: 'iex' // IEX feed for basic data, 'sip' for premium
    };
  }

  /**
   * Get recent activities (orders, fills, etc.) with enhanced error handling
   */
  async getActivities(activityTypes = null, pageSize = 50) {
    return await this.safeApiCall(async () => {
      const params = new URLSearchParams({
        activity_types: activityTypes || 'FILL',
        page_size: pageSize
      });
      const response = await this.api.get(`/v2/account/activities?${params}`);
      const activities = response.data;

      return activities.map(activity => ({
        id: activity.id,
        activityType: activity.activity_type,
        date: activity.date,
        netAmount: parseFloat(activity.net_amount || 0),
        symbol: activity.symbol,
        qty: activity.qty ? parseFloat(activity.qty) : null,
        price: activity.price ? parseFloat(activity.price) : null,
        side: activity.side,
        description: activity.description || activity.activity_type
      }));
    }, 'activities fetch');
  }

  /**
   * Get market calendar with enhanced error handling
   */
  async getMarketCalendar(start = null, end = null) {
    return await this.safeApiCall(async () => {
      const params = new URLSearchParams();
      if (start) params.append('start', start);
      if (end) params.append('end', end);
      const response = await this.api.get(`/v2/calendar?${params}`);
      const calendar = response.data;

      return calendar.map(day => ({
        date: day.date,
        open: day.open,
        close: day.close,
        sessionOpen: day.session_open,
        sessionClose: day.session_close
      }));
    }, 'market calendar fetch');
  }

  /**
   * Get current market status with enhanced error handling
   */
  async getMarketStatus() {
    return await this.safeApiCall(async () => {
      const response = await this.api.get('/v2/clock');
      const clock = response.data;
      
      return {
        timestamp: clock.timestamp,
        isOpen: clock.is_open,
        nextOpen: clock.next_open,
        nextClose: clock.next_close,
        timezone: 'America/New_York'
      };
    }, 'market status fetch');
  }

  /**
   * Validate API credentials with enhanced error handling
   */
  async validateCredentials() {
    try {
      return await this.safeApiCall(async () => {
        // Simple test - try to get account info
        const response = await this.api.get('/v2/account');
        const account = response.data;
        
        return {
          valid: true,
          accountId: account.id,
          status: account.status,
          environment: this.isPaper ? 'paper' : 'live'
        };
      }, 'credential validation');
    } catch (error) {
      console.error('Alpaca credential validation error:', error.message);
      
      return {
        valid: false,
        error: error.message,
        environment: this.isPaper ? 'paper' : 'live'
      };
    }
  }

  /**
   * Get asset information for a symbol with enhanced error handling
   */
  async getAsset(symbol) {
    return await this.safeApiCall(async () => {
      const response = await this.api.get(`/v2/assets/${symbol}`);
      const asset = response.data;
      
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
        fractionable: asset.fractionable
      };
    }, 'asset information fetch');
  }

  /**
   * Place an order with enhanced error handling and validation
   */
  async placeOrder(orderData) {
    return await this.safeApiCall(async () => {
      // Validate order data
      const requiredFields = ['symbol', 'qty', 'side', 'type', 'time_in_force'];
      for (const field of requiredFields) {
        if (!orderData[field]) {
          throw new Error(`Missing required order field: ${field}`);
        }
      }

      // Validate order side and type
      const validSides = ['buy', 'sell'];
      const validTypes = ['market', 'limit', 'stop', 'stop_limit'];
      const validTimeInForce = ['day', 'gtc', 'ioc', 'fok'];

      if (!validSides.includes(orderData.side.toLowerCase())) {
        throw new Error(`Invalid order side: ${orderData.side}. Must be one of: ${validSides.join(', ')}`);
      }

      if (!validTypes.includes(orderData.type.toLowerCase())) {
        throw new Error(`Invalid order type: ${orderData.type}. Must be one of: ${validTypes.join(', ')}`);
      }

      if (!validTimeInForce.includes(orderData.time_in_force.toLowerCase())) {
        throw new Error(`Invalid time_in_force: ${orderData.time_in_force}. Must be one of: ${validTimeInForce.join(', ')}`);
      }

      // Prepare order payload
      const orderPayload = {
        symbol: orderData.symbol.toUpperCase(),
        qty: parseFloat(orderData.qty),
        side: orderData.side.toLowerCase(),
        type: orderData.type.toLowerCase(),
        time_in_force: orderData.time_in_force.toLowerCase()
      };

      // Add limit price for limit orders
      if (orderData.type.toLowerCase().includes('limit') && orderData.limit_price) {
        orderPayload.limit_price = parseFloat(orderData.limit_price);
      }

      // Add stop price for stop orders
      if (orderData.type.toLowerCase().includes('stop') && orderData.stop_price) {
        orderPayload.stop_price = parseFloat(orderData.stop_price);
      }

      console.log('📤 Placing Alpaca order:', orderPayload);
      const response = await this.api.post('/v2/orders', orderPayload);
      const order = response.data;

      return {
        id: order.id,
        clientOrderId: order.client_order_id,
        symbol: order.symbol,
        assetId: order.asset_id,
        assetClass: order.asset_class,
        qty: parseFloat(order.qty),
        filledQty: parseFloat(order.filled_qty || 0),
        side: order.side,
        orderType: order.order_type,
        timeInForce: order.time_in_force,
        limitPrice: order.limit_price ? parseFloat(order.limit_price) : null,
        stopPrice: order.stop_price ? parseFloat(order.stop_price) : null,
        status: order.status,
        submittedAt: order.submitted_at,
        filledAt: order.filled_at,
        expiredAt: order.expired_at,
        canceledAt: order.canceled_at,
        failedAt: order.failed_at,
        environment: this.isPaper ? 'paper' : 'live'
      };
    }, 'order placement');
  }

  /**
   * Get orders with enhanced error handling
   */
  async getOrders(status = 'all', limit = 50) {
    return await this.safeApiCall(async () => {
      const params = new URLSearchParams({
        status: status,
        limit: limit.toString(),
        direction: 'desc'
      });
      
      const response = await this.api.get(`/v2/orders?${params}`);
      const orders = response.data;

      return orders.map(order => ({
        id: order.id,
        clientOrderId: order.client_order_id,
        symbol: order.symbol,
        assetId: order.asset_id,
        qty: parseFloat(order.qty),
        filledQty: parseFloat(order.filled_qty || 0),
        side: order.side,
        orderType: order.order_type,
        timeInForce: order.time_in_force,
        limitPrice: order.limit_price ? parseFloat(order.limit_price) : null,
        stopPrice: order.stop_price ? parseFloat(order.stop_price) : null,
        status: order.status,
        submittedAt: order.submitted_at,
        filledAt: order.filled_at,
        expiredAt: order.expired_at,
        canceledAt: order.canceled_at,
        failedAt: order.failed_at,
        environment: this.isPaper ? 'paper' : 'live'
      }));
    }, 'orders fetch');
  }

  /**
   * Cancel an order with enhanced error handling
   */
  async cancelOrder(orderId) {
    return await this.safeApiCall(async () => {
      const response = await this.api.delete(`/v2/orders/${orderId}`);
      return response.data;
    }, 'order cancellation');
  }

  /**
   * Get portfolio summary with calculated metrics
   */
  async getPortfolioSummary() {
    try {
      const [account, positions, history] = await Promise.all([
        this.getAccount(),
        this.getPositions(),
        this.getPortfolioHistory('1M', '1Day')
      ]);

      // Calculate portfolio metrics
      const totalValue = account.portfolioValue;
      const totalPnL = positions.reduce((sum, pos) => sum + pos.unrealizedPL, 0);
      const totalPnLPercent = totalValue > 0 ? (totalPnL / (totalValue - totalPnL)) * 100 : 0;
      
      // Calculate day change
      const dayPnL = positions.reduce((sum, pos) => sum + pos.unrealizedIntradayPL, 0);
      const dayPnLPercent = positions.reduce((sum, pos) => sum + pos.unrealizedIntradayPLPercent, 0) / positions.length;

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
          buyingPower: account.buyingPower
        },
        positions: positions,
        sectorAllocation: sectorAllocation,
        riskMetrics: riskMetrics,
        performance: history.slice(-30), // Last 30 days
        lastUpdated: new Date().toISOString()
      };
    } catch (error) {
      console.error('Alpaca portfolio summary error:', error.message);
      throw new Error(`Failed to generate portfolio summary: ${error.message}`);
    }
  }

  /**
   * Calculate basic sector allocation (simplified)
   */
  calculateBasicSectorAllocation(positions) {
    const sectors = {};
    const totalValue = positions.reduce((sum, pos) => sum + pos.marketValue, 0);

    positions.forEach(position => {
      // This is a simplified sector mapping - in production you'd use a more comprehensive service
      const sector = this.getSectorFromSymbol(position.symbol);
      
      if (!sectors[sector]) {
        sectors[sector] = {
          value: 0,
          weight: 0,
          positions: 0
        };
      }
      
      sectors[sector].value += position.marketValue;
      sectors[sector].positions += 1;
    });

    // Calculate weights
    Object.keys(sectors).forEach(sector => {
      sectors[sector].weight = totalValue > 0 ? (sectors[sector].value / totalValue) * 100 : 0;
    });

    return sectors;
  }

  /**
   * Simplified sector mapping (in production, use a proper sector classification service)
   */
  getSectorFromSymbol(symbol) {
    const techStocks = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'CRM', 'ORCL', 'ADBE'];
    const financialStocks = ['JPM', 'BAC', 'WFC', 'GS', 'MS', 'C', 'AXP', 'BLK', 'SCHW'];
    const healthcareStocks = ['JNJ', 'PFE', 'UNH', 'ABBV', 'MRK', 'TMO', 'DHR', 'BMY', 'LLY'];
    
    if (techStocks.includes(symbol)) return 'Technology';
    if (financialStocks.includes(symbol)) return 'Financials';
    if (healthcareStocks.includes(symbol)) return 'Healthcare';
    
    return 'Other';
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
        beta: 1
      };
    }

    // Calculate daily returns
    const returns = [];
    for (let i = 1; i < history.length; i++) {
      const dailyReturn = (history[i].equity - history[i-1].equity) / history[i-1].equity;
      returns.push(dailyReturn);
    }

    // Calculate volatility (standard deviation of returns)
    const avgReturn = returns.reduce((sum, r) => sum + r, 0) / returns.length;
    const variance = returns.reduce((sum, r) => sum + Math.pow(r - avgReturn, 2), 0) / returns.length;
    const volatility = Math.sqrt(variance) * Math.sqrt(252); // Annualized

    // Calculate max drawdown
    let maxDrawdown = 0;
    let peak = history[0].equity;
    
    history.forEach(day => {
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
    const excessReturn = (avgReturn * 252) - riskFreeRate;
    const sharpeRatio = volatility > 0 ? excessReturn / volatility : 0;

    return {
      volatility: volatility,
      sharpeRatio: sharpeRatio,
      maxDrawdown: maxDrawdown,
      beta: 1, // Simplified - would need market data for real beta calculation
      averageDailyReturn: avgReturn,
      annualizedReturn: avgReturn * 252
    };
  }
}

module.exports = AlpacaService;
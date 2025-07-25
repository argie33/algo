/**
 * HFT Service - Backend High Frequency Trading Service
 * Handles order execution, strategy management, and risk controls
 */

const { createLogger } = require('../utils/structuredLogger');
const { query } = require('../utils/database');

class HFTService {
  constructor() {
    this.logger = createLogger('financial-platform', 'hft-service');
    this.correlationId = this.generateCorrelationId();
    
    // Service state
    this.isRunning = false;
    this.strategies = new Map();
    this.positions = new Map();
    this.orders = new Map();
    this.marketData = new Map();
    
    // Performance metrics
    this.metrics = {
      totalTrades: 0,
      profitableTrades: 0,
      totalPnL: 0,
      dailyPnL: 0,
      avgExecutionTime: 0,
      signalsGenerated: 0,
      ordersExecuted: 0,
      startTime: null,
      lastTradeTime: null,
      executionTimes: []
    };
    
    // Risk management configuration
    this.riskConfig = {
      maxPositionSize: 1000, // USD
      maxDailyLoss: 500, // USD
      maxOpenPositions: 5,
      stopLossPercentage: 2.0, // 2%
      takeProfitPercentage: 1.0, // 1%
      maxDrawdown: 1000 // USD
    };
    
    // Strategy definitions
    this.initializeStrategies();
  }

  generateCorrelationId() {
    return `hft-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }

  /**
   * Initialize available trading strategies
   */
  initializeStrategies() {
    const defaultStrategies = [
      {
        id: 'scalping_btc',
        name: 'Bitcoin Scalping',
        type: 'scalping',
        symbols: ['BTC/USD'],
        enabled: false,
        params: {
          minSpread: 0.001, // 0.1%
          maxSpread: 0.005, // 0.5%
          volumeThreshold: 1000,
          momentumPeriod: 5,
          executionDelay: 100 // ms
        },
        riskParams: {
          positionSize: 0.1, // BTC
          stopLoss: 0.02, // 2%
          takeProfit: 0.01 // 1%
        }
      },
      {
        id: 'momentum_crypto',
        name: 'Crypto Momentum',
        type: 'momentum',
        symbols: ['BTC/USD', 'ETH/USD'],
        enabled: false,
        params: {
          momentumThreshold: 0.002, // 0.2%
          volumeMultiplier: 2.0,
          lookbackPeriod: 10,
          minVolume: 500
        },
        riskParams: {
          positionSize: 0.05, // BTC/ETH
          stopLoss: 0.03, // 3%
          takeProfit: 0.015 // 1.5%
        }
      },
      {
        id: 'arbitrage_spread',
        name: 'Spread Arbitrage',
        type: 'arbitrage',
        symbols: ['BTC/USD'],
        enabled: false,
        params: {
          minProfitMargin: 0.001, // 0.1%
          maxExecutionTime: 500, // ms
          priceUpdateThreshold: 0.0005 // 0.05%
        },
        riskParams: {
          positionSize: 0.1, // BTC
          maxHoldTime: 30000 // 30 seconds
        }
      }
    ];

    defaultStrategies.forEach(strategy => {
      this.strategies.set(strategy.id, {
        ...strategy,
        created: Date.now(),
        lastModified: Date.now(),
        performance: {
          trades: 0,
          winRate: 0,
          totalPnL: 0,
          avgTrade: 0,
          maxDrawdown: 0
        }
      });
    });
  }

  /**
   * Start HFT service
   */
  async start(userId, enabledStrategies = ['scalping_btc']) {
    if (this.isRunning) {
      return {
        success: false,
        error: 'HFT service already running'
      };
    }

    try {
      this.logger.info('Starting HFT service', {
        userId,
        enabledStrategies,
        correlationId: this.correlationId
      });

      // Reset metrics
      this.metrics.startTime = Date.now();
      this.metrics.totalTrades = 0;
      this.metrics.totalPnL = 0;
      this.metrics.dailyPnL = 0;

      // Enable specified strategies
      enabledStrategies.forEach(strategyId => {
        const strategy = this.strategies.get(strategyId);
        if (strategy) {
          strategy.enabled = true;
          this.logger.info('Strategy enabled', { strategyId, correlationId: this.correlationId });
        }
      });

      // Initialize positions table if not exists
      await this.initializeDatabase();

      // Start monitoring and execution
      this.startExecutionLoop();
      this.startRiskMonitoring();

      this.isRunning = true;

      return {
        success: true,
        message: 'HFT service started successfully',
        enabledStrategies: enabledStrategies,
        correlationId: this.correlationId
      };

    } catch (error) {
      this.logger.error('Failed to start HFT service', {
        error: error.message,
        correlationId: this.correlationId
      });

      return {
        success: false,
        error: 'Failed to start HFT service',
        details: error.message
      };
    }
  }

  /**
   * Stop HFT service
   */
  async stop() {
    if (!this.isRunning) {
      return {
        success: false,
        error: 'HFT service not running'
      };
    }

    try {
      this.logger.info('Stopping HFT service', {
        correlationId: this.correlationId
      });

      // Stop execution loops
      this.stopExecutionLoop();
      this.stopRiskMonitoring();

      // Close all open positions
      await this.closeAllPositions('service_stop');

      // Disable all strategies
      this.strategies.forEach(strategy => {
        strategy.enabled = false;
      });

      const finalMetrics = this.getMetrics();
      this.isRunning = false;

      return {
        success: true,
        message: 'HFT service stopped successfully',
        finalMetrics: finalMetrics
      };

    } catch (error) {
      this.logger.error('Failed to stop HFT service', {
        error: error.message,
        correlationId: this.correlationId
      });

      return {
        success: false,
        error: 'Failed to stop HFT service',
        details: error.message
      };
    }
  }

  /**
   * Process market data and generate signals
   */
  async processMarketData(marketDataUpdate) {
    if (!this.isRunning) return;

    const { symbol, data } = marketDataUpdate;
    
    try {
      // Update market data cache
      this.marketData.set(symbol, {
        ...data,
        timestamp: Date.now(),
        receivedAt: Date.now()
      });

      // Analyze with all enabled strategies
      for (const [strategyId, strategy] of this.strategies) {
        if (strategy.enabled && strategy.symbols.includes(symbol)) {
          await this.executeStrategy(strategyId, symbol, data);
        }
      }

    } catch (error) {
      this.logger.error('Error processing market data', {
        symbol,
        error: error.message,
        correlationId: this.correlationId
      });
    }
  }

  /**
   * Execute strategy logic
   */
  async executeStrategy(strategyId, symbol, marketData) {
    const strategy = this.strategies.get(strategyId);
    if (!strategy) return;

    const startTime = Date.now();

    try {
      let signal = null;

      switch (strategy.type) {
        case 'scalping':
          signal = await this.scalpingStrategy(strategy, symbol, marketData);
          break;
        case 'momentum':
          signal = await this.momentumStrategy(strategy, symbol, marketData);
          break;
        case 'arbitrage':
          signal = await this.arbitrageStrategy(strategy, symbol, marketData);
          break;
      }

      if (signal) {
        this.metrics.signalsGenerated++;
        await this.processSignal(strategyId, signal);
      }

      // Track execution time
      const executionTime = Date.now() - startTime;
      this.updateExecutionMetrics(executionTime);

    } catch (error) {
      this.logger.error('Strategy execution error', {
        strategyId,
        symbol,
        error: error.message,
        correlationId: this.correlationId
      });
    }
  }

  /**
   * Scalping strategy implementation
   */
  async scalpingStrategy(strategy, symbol, marketData) {
    const { price, bid, ask, volume } = marketData;
    const params = strategy.params;

    if (!bid || !ask || !volume) return null;

    // Calculate spread
    const spread = (ask - bid) / price;
    
    // Check spread bounds
    if (spread < params.minSpread || spread > params.maxSpread) {
      return null;
    }

    // Check volume threshold
    if (volume < params.volumeThreshold) {
      return null;
    }

    // Get recent price history (mock implementation)
    const recentPrices = await this.getRecentPrices(symbol, params.momentumPeriod);
    
    if (recentPrices.length < params.momentumPeriod) return null;

    // Calculate momentum
    const priceChange = price - recentPrices[0];
    const momentum = priceChange / recentPrices[0];

    // Generate signals based on momentum
    if (momentum > 0.0005) { // 0.05% positive momentum
      return {
        type: 'BUY',
        symbol: symbol,
        price: ask,
        quantity: strategy.riskParams.positionSize,
        strategy: strategy.id,
        confidence: Math.min(0.9, Math.abs(momentum) * 1000),
        stopLoss: ask * (1 - strategy.riskParams.stopLoss),
        takeProfit: ask * (1 + strategy.riskParams.takeProfit),
        timestamp: Date.now()
      };
    } else if (momentum < -0.0005 && this.hasLongPosition(symbol)) {
      return {
        type: 'SELL',
        symbol: symbol,
        price: bid,
        quantity: this.getPositionSize(symbol),
        strategy: strategy.id,
        confidence: Math.min(0.9, Math.abs(momentum) * 1000),
        reason: 'exit_long',
        timestamp: Date.now()
      };
    }

    return null;
  }

  /**
   * Momentum strategy implementation
   */
  async momentumStrategy(strategy, symbol, marketData) {
    const { price, volume } = marketData;
    const params = strategy.params;

    // Get historical data for momentum calculation
    const historicalData = await this.getRecentPrices(symbol, params.lookbackPeriod);
    
    if (historicalData.length < params.lookbackPeriod) return null;

    // Calculate momentum
    const pastPrice = historicalData[0];
    const momentum = (price - pastPrice) / pastPrice;

    // Calculate average volume
    const avgVolume = historicalData.reduce((sum, data) => sum + (data.volume || 0), 0) / historicalData.length;

    // Check momentum threshold and volume spike
    if (momentum > params.momentumThreshold && 
        volume > avgVolume * params.volumeMultiplier &&
        volume > params.minVolume) {
      
      return {
        type: 'BUY',
        symbol: symbol,
        price: price,
        quantity: strategy.riskParams.positionSize,
        strategy: strategy.id,
        confidence: Math.min(0.95, momentum * 100),
        stopLoss: price * (1 - strategy.riskParams.stopLoss),
        takeProfit: price * (1 + strategy.riskParams.takeProfit),
        timestamp: Date.now()
      };
    }

    return null;
  }

  /**
   * Arbitrage strategy implementation
   */
  async arbitrageStrategy(strategy, symbol, marketData) {
    const params = strategy.params;
    
    // In a real implementation, this would compare prices across multiple exchanges
    // For now, we'll simulate spread arbitrage opportunities
    
    const { price, bid, ask } = marketData;
    if (!bid || !ask) return null;

    const spread = ask - bid;
    const spreadPercentage = spread / price;

    // Look for arbitrage opportunities
    if (spreadPercentage > params.minProfitMargin) {
      return {
        type: 'ARBITRAGE',
        symbol: symbol,
        buyPrice: bid,
        sellPrice: ask,
        quantity: strategy.riskParams.positionSize,
        strategy: strategy.id,
        confidence: 0.8,
        expectedProfit: spread * strategy.riskParams.positionSize,
        maxHoldTime: strategy.riskParams.maxHoldTime,
        timestamp: Date.now()
      };
    }

    return null;
  }

  /**
   * Process trading signal
   */
  async processSignal(strategyId, signal) {
    try {
      // Risk management validation
      if (!this.validateRiskLimits(signal)) {
        this.logger.warn('Signal rejected by risk management', {
          strategyId,
          signal: signal.type,
          symbol: signal.symbol,
          correlationId: this.correlationId
        });
        return;
      }

      // Execute order
      const order = await this.executeOrder(signal);
      
      if (order.success) {
        this.metrics.ordersExecuted++;
        this.updateStrategyPerformance(strategyId, order);
        
        this.logger.info('Order executed successfully', {
          strategyId,
          orderId: order.orderId,
          symbol: signal.symbol,
          type: signal.type,
          correlationId: this.correlationId
        });
      }

    } catch (error) {
      this.logger.error('Error processing signal', {
        strategyId,
        error: error.message,
        correlationId: this.correlationId
      });
    }
  }

  /**
   * Execute trading order
   */
  async executeOrder(signal) {
    const orderId = this.generateOrderId();
    const startTime = Date.now();

    try {
      // In production, this would connect to broker API (Alpaca, Interactive Brokers, etc.)
      // For now, simulate order execution
      
      const executionPrice = signal.price * (1 + (Math.random() - 0.5) * 0.0001); // ±0.01% slippage
      const executionTime = Date.now();

      const order = {
        orderId,
        symbol: signal.symbol,
        type: signal.type,
        quantity: signal.quantity,
        requestedPrice: signal.price,
        executedPrice: executionPrice,
        strategy: signal.strategy,
        timestamp: signal.timestamp,
        executedAt: executionTime,
        executionTime: executionTime - startTime,
        status: 'executed',
        slippage: Math.abs(executionPrice - signal.price) / signal.price
      };

      // Store order
      this.orders.set(orderId, order);

      // Update positions
      await this.updatePosition(order);

      // Save to database
      await this.saveOrderToDatabase(order);

      return {
        success: true,
        orderId: orderId,
        order: order
      };

    } catch (error) {
      this.logger.error('Order execution failed', {
        orderId,
        error: error.message,
        correlationId: this.correlationId
      });

      return {
        success: false,
        orderId: orderId,
        error: error.message
      };
    }
  }

  /**
   * Update position tracking
   */
  async updatePosition(order) {
    const positionKey = `${order.symbol}_${order.strategy}`;
    const existingPosition = this.positions.get(positionKey);

    if (order.type === 'BUY') {
      if (existingPosition) {
        // Add to existing position
        const totalQuantity = existingPosition.quantity + order.quantity;
        const avgPrice = ((existingPosition.avgPrice * existingPosition.quantity) + 
                         (order.executedPrice * order.quantity)) / totalQuantity;
        
        existingPosition.quantity = totalQuantity;
        existingPosition.avgPrice = avgPrice;
        existingPosition.lastUpdate = Date.now();
      } else {
        // Create new position
        this.positions.set(positionKey, {
          symbol: order.symbol,
          strategy: order.strategy,
          type: 'LONG',
          quantity: order.quantity,
          avgPrice: order.executedPrice,
          openTime: Date.now(),
          lastUpdate: Date.now(),
          stopLoss: order.stopLoss,
          takeProfit: order.takeProfit
        });
      }
    } else if (order.type === 'SELL' && existingPosition) {
      // Close position
      const pnl = (order.executedPrice - existingPosition.avgPrice) * order.quantity;
      
      // Update metrics
      this.metrics.totalTrades++;
      this.metrics.totalPnL += pnl;
      this.metrics.dailyPnL += pnl;
      this.metrics.lastTradeTime = Date.now();
      
      if (pnl > 0) {
        this.metrics.profitableTrades++;
      }

      // Remove position
      this.positions.delete(positionKey);

      this.logger.info('Position closed', {
        symbol: order.symbol,
        pnl: pnl,
        correlationId: this.correlationId
      });
    }
  }

  /**
   * Validate risk limits
   */
  validateRiskLimits(signal) {
    // Check daily loss limit
    if (this.metrics.dailyPnL <= -this.riskConfig.maxDailyLoss) {
      return false;
    }

    // Check maximum open positions
    if (this.positions.size >= this.riskConfig.maxOpenPositions) {
      return false;
    }

    // Check position size limit
    const positionValue = signal.price * signal.quantity;
    if (positionValue > this.riskConfig.maxPositionSize) {
      return false;
    }

    return true;
  }

  /**
   * Get service metrics
   */
  getMetrics() {
    const now = Date.now();
    const uptime = this.metrics.startTime ? now - this.metrics.startTime : 0;
    const winRate = this.metrics.totalTrades > 0 ? 
      (this.metrics.profitableTrades / this.metrics.totalTrades) * 100 : 0;

    return {
      ...this.metrics,
      uptime,
      winRate,
      openPositions: this.positions.size,
      avgExecutionTime: this.metrics.executionTimes.length > 0 ?
        this.metrics.executionTimes.reduce((a, b) => a + b, 0) / this.metrics.executionTimes.length : 0,
      isRunning: this.isRunning,
      enabledStrategies: Array.from(this.strategies.values())
        .filter(s => s.enabled)
        .map(s => s.id),
      riskUtilization: {
        dailyLoss: Math.abs(this.metrics.dailyPnL) / this.riskConfig.maxDailyLoss * 100,
        openPositions: this.positions.size / this.riskConfig.maxOpenPositions * 100
      }
    };
  }

  /**
   * Get strategy information
   */
  getStrategies() {
    return Array.from(this.strategies.values()).map(strategy => ({
      id: strategy.id,
      name: strategy.name,
      type: strategy.type,
      symbols: strategy.symbols,
      enabled: strategy.enabled,
      params: strategy.params,
      riskParams: strategy.riskParams,
      performance: strategy.performance
    }));
  }

  /**
   * Update strategy configuration
   */
  updateStrategy(strategyId, updates) {
    const strategy = this.strategies.get(strategyId);
    
    if (!strategy) {
      return {
        success: false,
        error: 'Strategy not found'
      };
    }

    // Apply updates
    if (updates.params) {
      Object.assign(strategy.params, updates.params);
    }
    
    if (updates.riskParams) {
      Object.assign(strategy.riskParams, updates.riskParams);
    }
    
    if (typeof updates.enabled === 'boolean') {
      strategy.enabled = updates.enabled;
    }

    strategy.lastModified = Date.now();

    this.logger.info('Strategy updated', {
      strategyId,
      updates,
      correlationId: this.correlationId
    });

    return {
      success: true,
      strategy: strategy
    };
  }

  // Helper methods
  generateOrderId() {
    return `order_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }

  async getRecentPrices(symbol, periods) {
    // In production, this would query a time-series database
    // For now, return mock data
    const currentData = this.marketData.get(symbol);
    if (!currentData) return [];

    return Array.from({ length: periods }, (_, i) => ({
      price: currentData.price * (1 + (Math.random() - 0.5) * 0.001),
      volume: currentData.volume * (0.8 + Math.random() * 0.4),
      timestamp: Date.now() - (i * 1000)
    }));
  }

  hasLongPosition(symbol) {
    for (const [key, position] of this.positions) {
      if (position.symbol === symbol && position.type === 'LONG') {
        return true;
      }
    }
    return false;
  }

  getPositionSize(symbol) {
    for (const [key, position] of this.positions) {
      if (position.symbol === symbol) {
        return position.quantity;
      }
    }
    return 0;
  }

  updateExecutionMetrics(executionTime) {
    this.metrics.executionTimes.push(executionTime);
    
    // Keep only last 100 execution times
    if (this.metrics.executionTimes.length > 100) {
      this.metrics.executionTimes.shift();
    }
  }

  updateStrategyPerformance(strategyId, order) {
    const strategy = this.strategies.get(strategyId);
    if (strategy) {
      strategy.performance.trades++;
      // Additional performance tracking would go here
    }
  }

  async closeAllPositions(reason) {
    const positions = Array.from(this.positions.entries());
    
    for (const [positionKey, position] of positions) {
      try {
        const marketData = this.marketData.get(position.symbol);
        const exitPrice = marketData ? marketData.bid || marketData.price : position.avgPrice;
        
        const order = {
          type: 'SELL',
          symbol: position.symbol,
          price: exitPrice,
          quantity: position.quantity,
          strategy: position.strategy,
          reason: reason,
          timestamp: Date.now()
        };
        
        await this.executeOrder(order);
        
      } catch (error) {
        this.logger.error('Failed to close position', {
          positionKey,
          error: error.message,
          correlationId: this.correlationId
        });
      }
    }
  }

  async initializeDatabase() {
    try {
      // Create orders table if not exists
      await query(`
        CREATE TABLE IF NOT EXISTS hft_orders (
          id SERIAL PRIMARY KEY,
          order_id VARCHAR(255) UNIQUE NOT NULL,
          symbol VARCHAR(50) NOT NULL,
          order_type VARCHAR(10) NOT NULL,
          quantity DECIMAL(18, 8) NOT NULL,
          requested_price DECIMAL(18, 8) NOT NULL,
          executed_price DECIMAL(18, 8),
          strategy VARCHAR(100) NOT NULL,
          status VARCHAR(20) NOT NULL,
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          executed_at TIMESTAMP,
          execution_time INTEGER,
          slippage DECIMAL(10, 6)
        )
      `);

      // Create positions table if not exists
      await query(`
        CREATE TABLE IF NOT EXISTS hft_positions (
          id SERIAL PRIMARY KEY,
          symbol VARCHAR(50) NOT NULL,
          strategy VARCHAR(100) NOT NULL,
          position_type VARCHAR(10) NOT NULL,
          quantity DECIMAL(18, 8) NOT NULL,
          avg_price DECIMAL(18, 8) NOT NULL,
          stop_loss DECIMAL(18, 8),
          take_profit DECIMAL(18, 8),
          opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          closed_at TIMESTAMP,
          pnl DECIMAL(18, 8),
          status VARCHAR(20) DEFAULT 'open'
        )
      `);

    } catch (error) {
      this.logger.error('Failed to initialize database', {
        error: error.message,
        correlationId: this.correlationId
      });
    }
  }

  async saveOrderToDatabase(order) {
    try {
      await query(`
        INSERT INTO hft_orders (
          order_id, symbol, order_type, quantity, requested_price, 
          executed_price, strategy, status, executed_at, execution_time, slippage
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
      `, [
        order.orderId,
        order.symbol,
        order.type,
        order.quantity,
        order.requestedPrice,
        order.executedPrice,
        order.strategy,
        order.status,
        new Date(order.executedAt),
        order.executionTime,
        order.slippage
      ]);
    } catch (error) {
      this.logger.error('Failed to save order to database', {
        orderId: order.orderId,
        error: error.message,
        correlationId: this.correlationId
      });
    }
  }

  startExecutionLoop() {
    // Implementation for continuous execution monitoring
    this.executionInterval = setInterval(() => {
      if (this.isRunning) {
        this.monitorPositions();
      }
    }, 1000);
  }

  stopExecutionLoop() {
    if (this.executionInterval) {
      clearInterval(this.executionInterval);
      this.executionInterval = null;
    }
  }

  startRiskMonitoring() {
    // Implementation for risk monitoring
    this.riskInterval = setInterval(() => {
      if (this.isRunning) {
        this.checkRiskLimits();
      }
    }, 5000);
  }

  stopRiskMonitoring() {
    if (this.riskInterval) {
      clearInterval(this.riskInterval);
      this.riskInterval = null;
    }
  }

  monitorPositions() {
    // Monitor positions for stop loss / take profit
    this.positions.forEach((position, positionKey) => {
      const marketData = this.marketData.get(position.symbol);
      if (!marketData) return;

      const currentPrice = marketData.price;

      // Check stop loss
      if (position.stopLoss && currentPrice <= position.stopLoss) {
        this.closePosition(position, 'stop_loss');
      }

      // Check take profit
      if (position.takeProfit && currentPrice >= position.takeProfit) {
        this.closePosition(position, 'take_profit');
      }
    });
  }

  async closePosition(position, reason) {
    const marketData = this.marketData.get(position.symbol);
    const exitPrice = marketData ? marketData.bid || marketData.price : position.avgPrice;

    const order = {
      type: 'SELL',
      symbol: position.symbol,
      price: exitPrice,
      quantity: position.quantity,
      strategy: position.strategy,
      reason: reason,
      timestamp: Date.now()
    };

    await this.executeOrder(order);
  }

  checkRiskLimits() {
    // Check if daily loss limit is breached
    if (this.metrics.dailyPnL <= -this.riskConfig.maxDailyLoss) {
      this.logger.warn('Daily loss limit breached, stopping engine', {
        dailyPnL: this.metrics.dailyPnL,
        limit: this.riskConfig.maxDailyLoss,
        correlationId: this.correlationId
      });
      
      this.stop();
    }

    // Check maximum drawdown
    if (this.metrics.totalPnL <= -this.riskConfig.maxDrawdown) {
      this.logger.warn('Maximum drawdown reached, stopping engine', {
        totalPnL: this.metrics.totalPnL,
        maxDrawdown: this.riskConfig.maxDrawdown,
        correlationId: this.correlationId
      });
      
      this.stop();
    }
  }

  /**
   * Get current status of HFT service
   */
  getStatus() {
    return {
      isRunning: this.isRunning,
      status: this.isRunning ? 'active' : 'stopped',
      startTime: this.startTime,
      uptime: this.startTime ? Date.now() - this.startTime : 0,
      activeStrategies: Array.from(this.strategies.values()).filter(s => s.enabled).length,
      totalStrategies: this.strategies.size,
      openPositions: this.positions.size,
      timestamp: Date.now()
    };
  }

  /**
   * Get detailed metrics
   */
  getMetrics() {
    return {
      isRunning: this.isRunning,
      totalTrades: this.totalTrades || 0,
      totalPnL: this.metrics.totalPnL || 0,
      dailyPnL: this.metrics.dailyPnL || 0,
      winRate: this.totalTrades > 0 ? (this.metrics.winCount || 0) / this.totalTrades : 0,
      openPositions: this.positions.size,
      enabledStrategies: Array.from(this.strategies.values()).filter(s => s.enabled).length,
      avgExecutionTime: this.metrics.avgExecutionTime || 0,
      lastUpdate: Date.now()
    };
  }

  /**
   * Health check for HFT service
   */
  async healthCheck() {
    try {
      const strategyHealth = Array.from(this.strategies.values()).map(strategy => ({
        id: strategy.id,
        enabled: strategy.enabled,
        performance: strategy.performance || { uptime: 100, errorRate: 0 },
        errors: strategy.errors || 0
      }));

      const unhealthyStrategies = strategyHealth.filter(s => 
        s.errors > 10 || s.performance.uptime < 95
      );

      // Check if within risk limits
      const riskStatus = {
        dailyPnLOk: this.metrics.dailyPnL > -this.riskConfig.maxDailyLoss,
        drawdownOk: this.metrics.totalPnL > -this.riskConfig.maxDrawdown,
        positionCountOk: this.positions.size <= this.riskConfig.maxPositions
      };

      const riskHealthy = Object.values(riskStatus).every(Boolean);

      return {
        status: unhealthyStrategies.length === 0 && riskHealthy ? 'healthy' : 'degraded',
        message: `${strategyHealth.length} strategies checked`,
        isRunning: this.isRunning,
        uptime: this.startTime ? Date.now() - this.startTime : 0,
        strategies: strategyHealth,
        unhealthyStrategies: unhealthyStrategies.length,
        riskStatus,
        currentMetrics: {
          totalPnL: this.metrics.totalPnL,
          dailyPnL: this.metrics.dailyPnL,
          openPositions: this.positions.size
        },
        timestamp: Date.now()
      };

    } catch (error) {
      return {
        status: 'error',
        message: error.message,
        timestamp: Date.now()
      };
    }
  }
}

module.exports = HFTService;
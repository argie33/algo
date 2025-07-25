/**
 * HFT Engine - High Frequency Trading Core System
 * Integrates seamlessly with existing websocket infrastructure
 * Designed for scalping strategies with sub-second execution
 */

import liveDataService from './liveDataService.js';
import { PERFORMANCE_CONFIG } from '../config/environment.js';

class HFTEngine {
  constructor() {
    // Core engine state
    this.isRunning = false;
    this.strategies = new Map();
    this.activePositions = new Map();
    this.orderQueue = [];
    this.marketData = new Map();
    
    // Performance tracking
    this.metrics = {
      totalTrades: 0,
      profitableTrades: 0,
      totalPnL: 0,
      avgExecutionTime: 0,
      signalsGenerated: 0,
      ordersExecuted: 0,
      startTime: null,
      lastTradeTime: null
    };
    
    // Risk management
    this.riskManager = {
      maxPositionSize: 1000, // USD
      maxDailyLoss: 500, // USD
      maxOpenPositions: 5,
      currentDailyPnL: 0,
      stopLossPercentage: 2.0, // 2%
      takeProfitPercentage: 1.0 // 1%
    };
    
    // Strategy configurations
    this.strategyConfigs = {
      scalping: {
        enabled: true,
        symbols: ['BTC/USD'],
        timeframe: '1s',
        params: {
          minSpread: 0.001, // 0.1%
          maxSpread: 0.005, // 0.5%
          volume_threshold: 1000,
          momentum_period: 5,
          execution_delay: 100 // ms
        }
      },
      momentum: {
        enabled: false,
        symbols: ['BTC/USD', 'ETH/USD'],
        timeframe: '5s',
        params: {
          momentum_threshold: 0.002, // 0.2%
          volume_multiplier: 2.0,
          lookback_period: 10
        }
      },
      arbitrage: {
        enabled: false,
        symbols: ['BTC/USD'],
        timeframe: '1s',
        params: {
          min_profit_margin: 0.001, // 0.1%
          max_execution_time: 500 // ms
        }
      }
    };
    
    // Integration with existing live data service
    this.setupWebSocketIntegration();
  }

  /**
   * Seamlessly integrate with existing websocket infrastructure
   */
  setupWebSocketIntegration() {
    // Listen to market data from existing live data service
    liveDataService.on('marketData', (data) => {
      this.handleMarketData(data);
    });
    
    liveDataService.on('connected', () => {
      console.log('🔗 HFT Engine connected to market data stream');
      this.onWebSocketConnected();
    });
    
    liveDataService.on('error', (error) => {
      console.error('❌ HFT Engine websocket error:', error);
      this.handleWebSocketError(error);
    });
  }

  /**
   * Start HFT engine with specified strategies
   */
  async start(enabledStrategies = ['scalping']) {
    if (this.isRunning) {
      return { success: false, error: 'HFT Engine already running' };
    }

    try {
      console.log('🚀 Starting HFT Engine...');
      
      // Start backend HFT service first
      const backendResponse = await this.startBackendService(enabledStrategies);
      if (!backendResponse.success) {
        console.warn('⚠️ Backend HFT service failed to start, continuing in frontend-only mode');
      }
      
      // Initialize metrics
      this.metrics.startTime = Date.now();
      this.metrics.totalTrades = 0;
      this.metrics.totalPnL = 0;
      
      // Enable specified strategies
      enabledStrategies.forEach(strategyName => {
        if (this.strategyConfigs[strategyName]) {
          this.strategyConfigs[strategyName].enabled = true;
          this.initializeStrategy(strategyName);
        }
      });
      
      // Subscribe to required symbols via existing live data service
      await this.subscribeToMarketData();
      
      // Start strategy execution loop
      this.startStrategyLoop();
      
      this.isRunning = true;
      
      console.log('✅ HFT Engine started successfully');
      return {
        success: true,
        message: 'HFT Engine started',
        enabledStrategies: enabledStrategies,
        subscribedSymbols: this.getSubscribedSymbols(),
        backendIntegrated: backendResponse.success
      };
      
    } catch (error) {
      console.error('❌ Failed to start HFT Engine:', error);
      return {
        success: false,
        error: error.message
      };
    }
  }

  /**
   * Stop HFT engine and close all positions
   */
  async stop() {
    if (!this.isRunning) {
      return { success: false, error: 'HFT Engine not running' };
    }

    try {
      console.log('🛑 Stopping HFT Engine...');
      
      // Stop backend HFT service
      const backendResponse = await this.stopBackendService();
      if (!backendResponse.success) {
        console.warn('⚠️ Backend HFT service failed to stop properly');
      }
      
      // Stop strategy execution
      this.stopStrategyLoop();
      
      // Close all open positions
      await this.closeAllPositions();
      
      // Unsubscribe from market data
      await this.unsubscribeFromMarketData();
      
      this.isRunning = false;
      
      const finalMetrics = this.getMetrics();
      console.log('✅ HFT Engine stopped', finalMetrics);
      
      return {
        success: true,
        message: 'HFT Engine stopped',
        finalMetrics: finalMetrics,
        backendStopped: backendResponse.success
      };
      
    } catch (error) {
      console.error('❌ Failed to stop HFT Engine:', error);
      return {
        success: false,
        error: error.message
      };
    }
  }

  /**
   * Handle incoming market data and trigger strategy analysis
   */
  handleMarketData(marketDataEvent) {
    const { symbol, data } = marketDataEvent;
    
    if (!symbol || !data) return;
    
    // Update internal market data cache
    this.marketData.set(symbol, {
      ...data,
      timestamp: Date.now(),
      receivedAt: Date.now()
    });
    
    // Trigger strategy analysis for this symbol
    this.analyzeSymbol(symbol, data);
  }

  /**
   * Analyze symbol data against all enabled strategies
   */
  analyzeSymbol(symbol, data) {
    if (!this.isRunning) return;
    
    // Check each enabled strategy
    Object.entries(this.strategyConfigs).forEach(([strategyName, config]) => {
      if (config.enabled && config.symbols.includes(symbol)) {
        this.executeStrategy(strategyName, symbol, data);
      }
    });
  }

  /**
   * Execute specific strategy logic
   */
  executeStrategy(strategyName, symbol, data) {
    const startTime = Date.now();
    
    try {
      let signal = null;
      
      switch (strategyName) {
        case 'scalping':
          signal = this.scalpingStrategy(symbol, data);
          break;
        case 'momentum':
          signal = this.momentumStrategy(symbol, data);
          break;
        case 'arbitrage':
          signal = this.arbitrageStrategy(symbol, data);
          break;
      }
      
      if (signal) {
        this.processSignal(strategyName, symbol, signal);
      }
      
      // Update execution time metrics
      const executionTime = Date.now() - startTime;
      this.updateExecutionMetrics(executionTime);
      
    } catch (error) {
      console.error(`❌ Strategy execution error (${strategyName}, ${symbol}):`, error);
    }
  }

  /**
   * Simple scalping strategy - buy low, sell high on small spreads
   */
  scalpingStrategy(symbol, data) {
    const config = this.strategyConfigs.scalping;
    const { price, bid, ask, volume } = data;
    
    if (!bid || !ask || !volume) return null;
    
    const spread = (ask - bid) / price;
    const recentData = this.getRecentData(symbol, config.params.momentum_period);
    
    // Check if spread is within acceptable range
    if (spread < config.params.minSpread || spread > config.params.maxSpread) {
      return null;
    }
    
    // Check volume threshold
    if (volume < config.params.volume_threshold) {
      return null;
    }
    
    // Simple momentum check
    if (recentData.length >= config.params.momentum_period) {
      const priceChange = price - recentData[0].price;
      const momentum = priceChange / recentData[0].price;
      
      // Buy signal on positive momentum
      if (momentum > 0.0005) { // 0.05% positive momentum
        return {
          type: 'BUY',
          symbol: symbol,
          price: ask, // Buy at ask
          quantity: this.calculatePositionSize(symbol, ask),
          strategy: 'scalping',
          confidence: Math.min(0.9, Math.abs(momentum) * 1000),
          stopLoss: ask * (1 - this.riskManager.stopLossPercentage / 100),
          takeProfit: ask * (1 + this.riskManager.takeProfitPercentage / 100)
        };
      }
      
      // Sell signal on negative momentum (if we have long position)
      if (momentum < -0.0005 && this.hasLongPosition(symbol)) {
        return {
          type: 'SELL',
          symbol: symbol,
          price: bid, // Sell at bid
          quantity: this.getPositionSize(symbol),
          strategy: 'scalping',
          confidence: Math.min(0.9, Math.abs(momentum) * 1000),
          reason: 'exit_long'
        };
      }
    }
    
    return null;
  }

  /**
   * Momentum strategy - trend following
   */
  momentumStrategy(symbol, data) {
    const config = this.strategyConfigs.momentum;
    const recentData = this.getRecentData(symbol, config.params.lookback_period);
    
    if (recentData.length < config.params.lookback_period) return null;
    
    const currentPrice = data.price;
    const pastPrice = recentData[0].price;
    const momentum = (currentPrice - pastPrice) / pastPrice;
    const avgVolume = recentData.reduce((sum, d) => sum + d.volume, 0) / recentData.length;
    
    // Strong upward momentum with high volume
    if (momentum > config.params.momentum_threshold && 
        data.volume > avgVolume * config.params.volume_multiplier) {
      return {
        type: 'BUY',
        symbol: symbol,
        price: data.ask || data.price,
        quantity: this.calculatePositionSize(symbol, data.price),
        strategy: 'momentum',
        confidence: Math.min(0.95, momentum * 100)
      };
    }
    
    return null;
  }

  /**
   * Process trading signal and execute if risk management allows
   */
  processSignal(strategy, symbol, signal) {
    this.metrics.signalsGenerated++;
    
    // Risk management checks
    if (!this.passesRiskChecks(signal)) {
      console.log(`🛑 Signal rejected by risk management: ${signal.symbol} ${signal.type}`);
      return;
    }
    
    // Add to order queue for execution
    this.orderQueue.push({
      ...signal,
      timestamp: Date.now(),
      strategy: strategy,
      status: 'pending'
    });
    
    console.log(`📊 Trading signal generated: ${signal.symbol} ${signal.type} @ ${signal.price} (${strategy})`);
    
    // Process order queue
    this.processOrderQueue();
  }

  /**
   * Risk management validation
   */
  passesRiskChecks(signal) {
    // Check daily loss limit
    if (this.riskManager.currentDailyPnL <= -this.riskManager.maxDailyLoss) {
      return false;
    }
    
    // Check maximum open positions
    if (this.activePositions.size >= this.riskManager.maxOpenPositions) {
      return false;
    }
    
    // Check position size limit
    const positionValue = signal.price * signal.quantity;
    if (positionValue > this.riskManager.maxPositionSize) {
      return false;
    }
    
    return true;
  }

  /**
   * Calculate appropriate position size based on risk management
   */
  calculatePositionSize(symbol, price) {
    const maxPositionValue = this.riskManager.maxPositionSize;
    const baseQuantity = maxPositionValue / price;
    
    // Scale down based on current risk exposure
    const riskFactor = 1 - (Math.abs(this.riskManager.currentDailyPnL) / this.riskManager.maxDailyLoss);
    
    return Math.floor(baseQuantity * riskFactor * 100) / 100; // Round to 2 decimals
  }

  /**
   * Subscribe to market data through existing live data service
   */
  async subscribeToMarketData() {
    const symbols = this.getSubscribedSymbols();
    
    // Use existing live data service subscription
    symbols.forEach(symbol => {
      liveDataService.subscribe([symbol], ['trades', 'quotes']);
    });
    
    console.log(`📡 HFT Engine subscribed to ${symbols.length} symbols:`, symbols);
  }

  /**
   * Get all symbols required by enabled strategies
   */
  getSubscribedSymbols() {
    const symbols = new Set();
    
    Object.values(this.strategyConfigs).forEach(config => {
      if (config.enabled) {
        config.symbols.forEach(symbol => symbols.add(symbol));
      }
    });
    
    return Array.from(symbols);
  }

  /**
   * Get recent price data for a symbol
   */
  getRecentData(symbol, periods) {
    // In production, this would query a time-series database or maintain a rolling buffer
    // For now, return mock data
    const currentData = this.marketData.get(symbol);
    if (!currentData) return [];
    
    // Simulate recent data points
    const data = [];
    for (let i = periods - 1; i >= 0; i--) {
      data.push({
        price: currentData.price * (1 + (Math.random() - 0.5) * 0.001), // ±0.1% variation
        volume: currentData.volume * (0.8 + Math.random() * 0.4), // ±20% volume variation
        timestamp: Date.now() - (i * 1000) // 1 second intervals
      });
    }
    
    return data;
  }

  /**
   * Check if we have a long position in symbol
   */
  hasLongPosition(symbol) {
    const position = this.activePositions.get(symbol);
    return position && position.type === 'LONG' && position.quantity > 0;
  }

  /**
   * Get current position size for symbol
   */
  getPositionSize(symbol) {
    const position = this.activePositions.get(symbol);
    return position ? position.quantity : 0;
  }

  /**
   * Process order queue (mock execution for now)
   */
  processOrderQueue() {
    while (this.orderQueue.length > 0) {
      const order = this.orderQueue.shift();
      this.executeOrder(order);
    }
  }

  /**
   * Execute order (mock implementation)
   */
  executeOrder(order) {
    try {
      // In production, this would connect to broker API
      console.log(`⚡ Executing order: ${order.type} ${order.quantity} ${order.symbol} @ ${order.price}`);
      
      // Update position tracking
      this.updatePosition(order);
      
      // Update metrics
      this.metrics.ordersExecuted++;
      this.metrics.totalTrades++;
      this.metrics.lastTradeTime = Date.now();
      
      order.status = 'executed';
      order.executedAt = Date.now();
      
    } catch (error) {
      console.error('❌ Order execution failed:', error);
      order.status = 'failed';
      order.error = error.message;
    }
  }

  /**
   * Update position tracking
   */
  updatePosition(order) {
    const existingPosition = this.activePositions.get(order.symbol);
    
    if (order.type === 'BUY') {
      if (existingPosition) {
        // Add to existing position
        existingPosition.quantity += order.quantity;
        existingPosition.avgPrice = ((existingPosition.avgPrice * existingPosition.quantity) + 
                                   (order.price * order.quantity)) / (existingPosition.quantity + order.quantity);
      } else {
        // New long position
        this.activePositions.set(order.symbol, {
          symbol: order.symbol,
          type: 'LONG',
          quantity: order.quantity,
          avgPrice: order.price,
          openTime: Date.now(),
          strategy: order.strategy,
          stopLoss: order.stopLoss,
          takeProfit: order.takeProfit
        });
      }
    } else if (order.type === 'SELL' && existingPosition) {
      // Close position
      const pnl = (order.price - existingPosition.avgPrice) * order.quantity;
      this.riskManager.currentDailyPnL += pnl;
      this.metrics.totalPnL += pnl;
      
      if (pnl > 0) {
        this.metrics.profitableTrades++;
      }
      
      this.activePositions.delete(order.symbol);
      console.log(`💰 Position closed: ${order.symbol} PnL: $${pnl.toFixed(2)}`);
    }
  }

  /**
   * Start strategy execution loop
   */
  startStrategyLoop() {
    this.strategyInterval = setInterval(() => {
      if (!this.isRunning) return;
      
      // Monitor positions for stop loss / take profit
      this.monitorPositions();
      
      // Update metrics
      this.updateMetrics();
      
    }, 1000); // Run every second
  }

  /**
   * Stop strategy execution loop
   */
  stopStrategyLoop() {
    if (this.strategyInterval) {
      clearInterval(this.strategyInterval);
      this.strategyInterval = null;
    }
  }

  /**
   * Monitor open positions for exit conditions
   */
  monitorPositions() {
    this.activePositions.forEach((position, symbol) => {
      const currentData = this.marketData.get(symbol);
      if (!currentData) return;
      
      const currentPrice = currentData.price;
      
      // Check stop loss
      if (position.stopLoss && currentPrice <= position.stopLoss) {
        this.closePosition(symbol, 'stop_loss');
      }
      
      // Check take profit
      if (position.takeProfit && currentPrice >= position.takeProfit) {
        this.closePosition(symbol, 'take_profit');
      }
    });
  }

  /**
   * Close position
   */
  closePosition(symbol, reason) {
    const position = this.activePositions.get(symbol);
    if (!position) return;
    
    const currentData = this.marketData.get(symbol);
    const exitPrice = currentData ? currentData.bid || currentData.price : position.avgPrice;
    
    const order = {
      type: 'SELL',
      symbol: symbol,
      price: exitPrice,
      quantity: position.quantity,
      strategy: position.strategy,
      reason: reason
    };
    
    this.executeOrder(order);
  }

  /**
   * Close all open positions
   */
  async closeAllPositions() {
    const positions = Array.from(this.activePositions.keys());
    
    for (const symbol of positions) {
      this.closePosition(symbol, 'engine_stop');
      await new Promise(resolve => setTimeout(resolve, 100)); // Small delay between orders
    }
  }

  /**
   * Update performance metrics
   */
  updateMetrics() {
    const now = Date.now();
    const uptime = this.metrics.startTime ? now - this.metrics.startTime : 0;
    
    // Calculate win rate
    const winRate = this.metrics.totalTrades > 0 ? 
      (this.metrics.profitableTrades / this.metrics.totalTrades) * 100 : 0;
    
    // Update metrics object
    this.metrics.uptime = uptime;
    this.metrics.winRate = winRate;
    this.metrics.openPositions = this.activePositions.size;
    this.metrics.dailyPnL = this.riskManager.currentDailyPnL;
  }

  /**
   * Get comprehensive metrics
   */
  getMetrics() {
    this.updateMetrics();
    
    return {
      ...this.metrics,
      isRunning: this.isRunning,
      enabledStrategies: Object.entries(this.strategyConfigs)
        .filter(([_, config]) => config.enabled)
        .map(([name, _]) => name),
      activePositions: Array.from(this.activePositions.values()),
      riskMetrics: {
        ...this.riskManager,
        riskUtilization: Math.abs(this.riskManager.currentDailyPnL) / this.riskManager.maxDailyLoss * 100,
        positionUtilization: this.activePositions.size / this.riskManager.maxOpenPositions * 100
      }
    };
  }

  /**
   * Update strategy configuration
   */
  updateStrategy(strategyName, updates) {
    if (!this.strategyConfigs[strategyName]) {
      return { success: false, error: 'Strategy not found' };
    }
    
    // Merge updates
    Object.assign(this.strategyConfigs[strategyName], updates);
    
    return {
      success: true,
      strategy: this.strategyConfigs[strategyName]
    };
  }

  /**
   * Get strategy status
   */
  getStrategies() {
    return Object.entries(this.strategyConfigs).map(([name, config]) => ({
      name,
      enabled: config.enabled,
      symbols: config.symbols,
      timeframe: config.timeframe,
      params: config.params
    }));
  }

  // Event handlers
  onWebSocketConnected() {
    if (this.isRunning) {
      console.log('🔄 Re-subscribing to market data after reconnection');
      this.subscribeToMarketData();
    }
  }

  handleWebSocketError(error) {
    console.error('🚨 HFT Engine websocket error, pausing strategies:', error);
    // In production, implement strategy pause/resume logic
  }

  updateExecutionMetrics(executionTime) {
    if (this.metrics.avgExecutionTime === 0) {
      this.metrics.avgExecutionTime = executionTime;
    } else {
      this.metrics.avgExecutionTime = (this.metrics.avgExecutionTime * 0.9) + (executionTime * 0.1);
    }
  }

  async unsubscribeFromMarketData() {
    const symbols = this.getSubscribedSymbols();
    
    symbols.forEach(symbol => {
      liveDataService.unsubscribe([symbol]);
    });
    
    console.log(`📡 HFT Engine unsubscribed from ${symbols.length} symbols`);
  }

  initializeStrategy(strategyName) {
    console.log(`🎯 Initializing strategy: ${strategyName}`);
    // Additional strategy-specific initialization can go here
  }

  /**
   * Backend API Integration Methods
   */
  
  /**
   * Start backend HFT service
   */
  async startBackendService(strategies) {
    try {
      const response = await fetch('/api/hft/start', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${this.getAuthToken()}`
        },
        body: JSON.stringify({ strategies })
      });

      const data = await response.json();
      
      if (response.ok && data.success) {
        console.log('✅ Backend HFT service started', data);
        return data;
      } else {
        console.warn('⚠️ Backend HFT service start failed', data);
        return { success: false, error: data.error || 'Backend service unavailable' };
      }
    } catch (error) {
      console.warn('⚠️ Backend HFT service unreachable', error);
      return { success: false, error: 'Backend service unreachable' };
    }
  }

  /**
   * Stop backend HFT service
   */
  async stopBackendService() {
    try {
      const response = await fetch('/api/hft/stop', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${this.getAuthToken()}`
        }
      });

      const data = await response.json();
      
      if (response.ok && data.success) {
        console.log('✅ Backend HFT service stopped', data);
        return data;
      } else {
        console.warn('⚠️ Backend HFT service stop failed', data);
        return { success: false, error: data.error || 'Backend service unavailable' };
      }
    } catch (error) {
      console.warn('⚠️ Backend HFT service unreachable during stop', error);
      return { success: false, error: 'Backend service unreachable' };
    }
  }

  /**
   * Get backend HFT metrics
   */
  async getBackendMetrics() {
    try {
      const response = await fetch('/api/hft/status', {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${this.getAuthToken()}`
        }
      });

      const data = await response.json();
      
      if (response.ok && data.success) {
        return data.data;
      } else {
        console.warn('⚠️ Failed to get backend metrics', data);
        return null;
      }
    } catch (error) {
      console.warn('⚠️ Backend metrics unreachable', error);
      return null;
    }
  }

  /**
   * Send market data to backend for processing
   */
  async sendMarketDataToBackend(marketData) {
    try {
      const response = await fetch('/api/hft/market-data', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${this.getAuthToken()}`
        },
        body: JSON.stringify(marketData)
      });

      const data = await response.json();
      
      if (!response.ok || !data.success) {
        console.warn('⚠️ Failed to send market data to backend', data);
      }
    } catch (error) {
      // Silently fail - this is non-critical
      console.debug('Backend market data sync failed', error);
    }
  }

  /**
   * Get authentication token (stub - should integrate with your auth system)
   */
  getAuthToken() {
    // TODO: Integrate with your authentication system
    // For now, return a placeholder token
    return localStorage.getItem('authToken') || 'demo-token';
  }

  /**
   * Enhanced metrics that combine frontend and backend data
   */
  async getEnhancedMetrics() {
    const frontendMetrics = this.getMetrics();
    const backendMetrics = await this.getBackendMetrics();
    
    if (backendMetrics) {
      return {
        ...frontendMetrics,
        backend: backendMetrics,
        integrated: true,
        combinedPnL: (frontendMetrics.totalPnL || 0) + (backendMetrics.totalPnL || 0),
        combinedTrades: (frontendMetrics.totalTrades || 0) + (backendMetrics.totalTrades || 0)
      };
    }
    
    return {
      ...frontendMetrics,
      integrated: false
    };
  }

  /**
   * Enhanced market data handler that syncs with backend
   */
  async handleMarketDataEnhanced(marketDataEvent) {
    // Process on frontend
    this.handleMarketData(marketDataEvent);
    
    // Sync with backend if running
    if (this.isRunning) {
      await this.sendMarketDataToBackend(marketDataEvent);
    }
  }
}

// Create singleton instance
const hftEngine = new HFTEngine();

// Export for use in components
export default hftEngine;
export { HFTEngine };
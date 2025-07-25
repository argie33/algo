/**
 * Real-Time Data Integrator for HFT
 * Provides live market data feeds, signal generation, and data streaming
 */

const { createLogger } = require('../utils/structuredLogger');
const EventEmitter = require('events');

class RealTimeDataIntegrator extends EventEmitter {
  constructor() {
    super();
    this.logger = createLogger('financial-platform', 'realtime-data-integrator');
    this.correlationId = this.generateCorrelationId();
    
    // Data feed connections
    this.dataFeeds = new Map();
    this.subscriptions = new Map();
    this.marketData = new Map();
    this.lastUpdate = new Map();
    
    // Signal generation
    this.signalBuffer = [];
    this.technicalIndicators = new Map();
    this.priceHistory = new Map();
    
    // Configuration
    this.config = {
      updateInterval: 1000, // 1 second updates
      historyLength: 200, // Keep 200 data points
      signalThreshold: 0.001, // 0.1% minimum price movement
      enableSignalGeneration: true,
      maxSubscriptions: 50,
      dataRetentionHours: 24
    };
    
    // Performance tracking
    this.metrics = {
      messagesReceived: 0,
      signalsGenerated: 0,
      latencyMs: 0,
      lastUpdateTime: null,
      connectionStatus: 'disconnected',
      activeSubscriptions: 0
    };
    
    this.isRunning = false;
  }

  generateCorrelationId() {
    return `rtdi-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }

  /**
   * Initialize real-time data feeds
   */
  async initialize(userCredentials) {
    try {
      this.logger.info('Initializing real-time data integrator', {
        correlationId: this.correlationId
      });

      this.userCredentials = userCredentials;
      
      // Initialize Alpaca data feed
      await this.initializeAlpacaFeed();
      
      // Initialize Polygon data feed (if available)
      await this.initializePolygonFeed();
      
      // Start signal generation engine
      this.startSignalGeneration();
      
      // Start cleanup process
      this.startDataCleanup();
      
      this.isRunning = true;
      this.metrics.connectionStatus = 'connected';
      
      this.logger.info('Real-time data integrator initialized successfully', {
        correlationId: this.correlationId
      });
      
      return { success: true };
      
    } catch (error) {
      this.logger.error('Failed to initialize real-time data integrator', {
        error: error.message,
        correlationId: this.correlationId
      });
      
      throw error;
    }
  }

  /**
   * Initialize Alpaca real-time data feed
   */
  async initializeAlpacaFeed() {
    try {
      if (!this.userCredentials) {
        throw new Error('User credentials required for Alpaca feed');
      }

      const Alpaca = require('@alpacahq/alpaca-trade-api');
      
      const alpaca = new Alpaca({
        credentials: {
          key: this.userCredentials.keyId,
          secret: this.userCredentials.secretKey,
          paper: this.userCredentials.isPaper !== false
        }
      });

      // Create WebSocket connection for real-time data
      const websocket = alpaca.data_stream_v2;
      
      websocket.onConnect(function() {
        console.log('Alpaca WebSocket connected');
      });
      
      websocket.onDisconnect(function() {
        console.log('Alpaca WebSocket disconnected');
      });
      
      websocket.onStateChange(function(newState) {
        console.log('Alpaca WebSocket state:', newState);
      });
      
      websocket.onStockTrade((trade) => {
        this.handleAlpacaTrade(trade);
      });
      
      websocket.onStockQuote((quote) => {
        this.handleAlpacaQuote(quote);
      });
      
      websocket.onStockBar((bar) => {
        this.handleAlpacaBar(bar);
      });
      
      this.dataFeeds.set('alpaca', {
        connection: websocket,
        type: 'alpaca',
        status: 'connected',
        lastMessage: Date.now()
      });
      
      this.logger.info('Alpaca data feed initialized', {
        correlationId: this.correlationId
      });
      
    } catch (error) {
      this.logger.error('Failed to initialize Alpaca feed', {
        error: error.message,
        correlationId: this.correlationId
      });
    }
  }

  /**
   * Initialize Polygon data feed (backup/supplementary)
   */
  async initializePolygonFeed() {
    try {
      // Polygon integration would go here
      // For now, we'll use a mock implementation
      
      this.dataFeeds.set('polygon', {
        connection: null,
        type: 'polygon',
        status: 'disabled',
        lastMessage: null
      });
      
      this.logger.info('Polygon feed configuration set (disabled)', {
        correlationId: this.correlationId
      });
      
    } catch (error) {
      this.logger.error('Failed to initialize Polygon feed', {
        error: error.message,
        correlationId: this.correlationId
      });
    }
  }

  /**
   * Subscribe to real-time data for symbols
   */
  async subscribeToSymbols(symbols) {
    try {
      this.logger.info('Subscribing to real-time data', {
        symbols,
        correlationId: this.correlationId
      });

      if (symbols.length > this.config.maxSubscriptions) {
        throw new Error(`Too many subscriptions requested (max: ${this.config.maxSubscriptions})`);
      }

      const alpacaFeed = this.dataFeeds.get('alpaca');
      if (alpacaFeed && alpacaFeed.connection) {
        // Subscribe to trades, quotes, and bars
        alpacaFeed.connection.subscribeForTrades(symbols);
        alpacaFeed.connection.subscribeForQuotes(symbols);
        alpacaFeed.connection.subscribeForBars(symbols);
        
        // Connect WebSocket
        alpacaFeed.connection.connect();
      }

      // Track subscriptions
      symbols.forEach(symbol => {
        this.subscriptions.set(symbol, {
          symbol,
          subscribedAt: Date.now(),
          dataFeeds: ['alpaca'],
          active: true
        });
        
        // Initialize price history
        if (!this.priceHistory.has(symbol)) {
          this.priceHistory.set(symbol, []);
        }
      });

      this.metrics.activeSubscriptions = this.subscriptions.size;
      
      this.logger.info('Successfully subscribed to real-time data', {
        symbolCount: symbols.length,
        totalSubscriptions: this.subscriptions.size,
        correlationId: this.correlationId
      });
      
      return { success: true, subscribedSymbols: symbols };
      
    } catch (error) {
      this.logger.error('Failed to subscribe to symbols', {
        symbols,
        error: error.message,
        correlationId: this.correlationId
      });
      
      throw error;
    }
  }

  /**
   * Handle Alpaca trade data
   */
  handleAlpacaTrade(trade) {
    try {
      const symbol = trade.Symbol;
      const price = trade.Price;
      const volume = trade.Size;
      const timestamp = new Date(trade.Timestamp);

      // Update market data
      this.updateMarketData(symbol, {
        type: 'trade',
        price,
        volume,
        timestamp,
        source: 'alpaca'
      });

      // Update price history
      this.updatePriceHistory(symbol, price, timestamp);

      // Generate signals if enabled
      if (this.config.enableSignalGeneration) {
        this.generateTradingSignals(symbol, price, volume, timestamp);
      }

      this.metrics.messagesReceived++;
      this.metrics.lastUpdateTime = timestamp;
      
      // Emit event for listeners
      this.emit('trade', {
        symbol,
        price,
        volume,
        timestamp,
        source: 'alpaca'
      });
      
    } catch (error) {
      this.logger.error('Error handling Alpaca trade', {
        trade,
        error: error.message,
        correlationId: this.correlationId
      });
    }
  }

  /**
   * Handle Alpaca quote data
   */
  handleAlpacaQuote(quote) {
    try {
      const symbol = quote.Symbol;
      const bid = quote.BidPrice;
      const ask = quote.AskPrice;
      const bidSize = quote.BidSize;
      const askSize = quote.AskSize;
      const timestamp = new Date(quote.Timestamp);

      // Update market data
      this.updateMarketData(symbol, {
        type: 'quote',
        bid,
        ask,
        bidSize,
        askSize,
        spread: ask - bid,
        midPrice: (bid + ask) / 2,
        timestamp,
        source: 'alpaca'
      });

      this.metrics.messagesReceived++;
      
      // Emit event for listeners
      this.emit('quote', {
        symbol,
        bid,
        ask,
        bidSize,
        askSize,
        timestamp,
        source: 'alpaca'
      });
      
    } catch (error) {
      this.logger.error('Error handling Alpaca quote', {
        quote,
        error: error.message,
        correlationId: this.correlationId
      });
    }
  }

  /**
   * Handle Alpaca bar data (OHLCV)
   */
  handleAlpacaBar(bar) {
    try {
      const symbol = bar.Symbol;
      const timestamp = new Date(bar.Timestamp);

      // Update market data
      this.updateMarketData(symbol, {
        type: 'bar',
        open: bar.OpenPrice,
        high: bar.HighPrice,
        low: bar.LowPrice,
        close: bar.ClosePrice,
        volume: bar.Volume,
        vwap: bar.VWAP,
        timestamp,
        source: 'alpaca'
      });

      // Update technical indicators
      this.updateTechnicalIndicators(symbol, {
        open: bar.OpenPrice,
        high: bar.HighPrice,
        low: bar.LowPrice,
        close: bar.ClosePrice,
        volume: bar.Volume,
        timestamp
      });

      this.metrics.messagesReceived++;
      
      // Emit event for listeners
      this.emit('bar', {
        symbol,
        open: bar.OpenPrice,
        high: bar.HighPrice,
        low: bar.LowPrice,
        close: bar.ClosePrice,
        volume: bar.Volume,
        timestamp,
        source: 'alpaca'
      });
      
    } catch (error) {
      this.logger.error('Error handling Alpaca bar', {
        bar,
        error: error.message,
        correlationId: this.correlationId
      });
    }
  }

  /**
   * Update market data storage
   */
  updateMarketData(symbol, data) {
    if (!this.marketData.has(symbol)) {
      this.marketData.set(symbol, {
        latest: null,
        trades: [],
        quotes: [],
        bars: []
      });
    }

    const symbolData = this.marketData.get(symbol);
    symbolData.latest = data;
    
    // Store by type
    if (data.type === 'trade') {
      symbolData.trades.push(data);
      if (symbolData.trades.length > 100) {
        symbolData.trades = symbolData.trades.slice(-100);
      }
    } else if (data.type === 'quote') {
      symbolData.quotes.push(data);
      if (symbolData.quotes.length > 100) {
        symbolData.quotes = symbolData.quotes.slice(-100);
      }
    } else if (data.type === 'bar') {
      symbolData.bars.push(data);
      if (symbolData.bars.length > 100) {
        symbolData.bars = symbolData.bars.slice(-100);
      }
    }

    this.lastUpdate.set(symbol, Date.now());
  }

  /**
   * Update price history for signal generation
   */
  updatePriceHistory(symbol, price, timestamp) {
    let history = this.priceHistory.get(symbol) || [];
    
    history.push({
      price,
      timestamp: timestamp.getTime()
    });
    
    // Keep only recent history
    if (history.length > this.config.historyLength) {
      history = history.slice(-this.config.historyLength);
    }
    
    this.priceHistory.set(symbol, history);
  }

  /**
   * Generate trading signals from real-time data
   */
  generateTradingSignals(symbol, price, volume, timestamp) {
    try {
      const history = this.priceHistory.get(symbol);
      if (!history || history.length < 20) {
        return; // Need more data for signals
      }

      const prices = history.map(h => h.price);
      const currentPrice = price;
      
      // Simple moving averages
      const sma5 = this.calculateSMA(prices.slice(-5));
      const sma20 = this.calculateSMA(prices.slice(-20));
      
      // Price change percentage
      const priceChange = (currentPrice - prices[prices.length - 2]) / prices[prices.length - 2];
      
      // Volume analysis
      const symbolData = this.marketData.get(symbol);
      const recentVolume = symbolData?.trades.slice(-10).reduce((sum, t) => sum + t.volume, 0) || 0;
      const avgVolume = symbolData?.trades.slice(-50).reduce((sum, t) => sum + t.volume, 0) / 50 || 1;
      const volumeRatio = recentVolume / avgVolume;

      // Signal generation logic
      let signal = null;
      
      // Buy signal: Price above SMA5, SMA5 above SMA20, significant price movement, high volume
      if (currentPrice > sma5 && 
          sma5 > sma20 && 
          priceChange > this.config.signalThreshold &&
          volumeRatio > 1.5) {
        
        signal = {
          type: 'buy',
          symbol,
          price: currentPrice,
          confidence: Math.min(0.95, 0.5 + (priceChange * 10) + (volumeRatio - 1) * 0.1),
          indicators: {
            sma5,
            sma20,
            priceChange,
            volumeRatio
          },
          timestamp,
          source: 'realtime-data-integrator'
        };
      }
      
      // Sell signal: Price below SMA5, SMA5 below SMA20, negative price movement, high volume
      else if (currentPrice < sma5 && 
               sma5 < sma20 && 
               priceChange < -this.config.signalThreshold &&
               volumeRatio > 1.5) {
        
        signal = {
          type: 'sell',
          symbol,
          price: currentPrice,
          confidence: Math.min(0.95, 0.5 + (Math.abs(priceChange) * 10) + (volumeRatio - 1) * 0.1),
          indicators: {
            sma5,
            sma20,
            priceChange,
            volumeRatio
          },
          timestamp,
          source: 'realtime-data-integrator'
        };
      }

      if (signal) {
        this.signalBuffer.push(signal);
        this.metrics.signalsGenerated++;
        
        // Emit signal event
        this.emit('signal', signal);
        
        this.logger.info('Trading signal generated', {
          signal,
          correlationId: this.correlationId
        });
      }
      
    } catch (error) {
      this.logger.error('Error generating trading signals', {
        symbol,
        error: error.message,
        correlationId: this.correlationId
      });
    }
  }

  /**
   * Update technical indicators
   */
  updateTechnicalIndicators(symbol, barData) {
    try {
      if (!this.technicalIndicators.has(symbol)) {
        this.technicalIndicators.set(symbol, {
          rsi: [],
          macd: { macd: [], signal: [], histogram: [] },
          bollinger: { upper: [], middle: [], lower: [] },
          volume: []
        });
      }

      const indicators = this.technicalIndicators.get(symbol);
      const history = this.priceHistory.get(symbol) || [];
      
      if (history.length >= 14) {
        // Calculate RSI
        const rsi = this.calculateRSI(history.slice(-14).map(h => h.price));
        indicators.rsi.push({ value: rsi, timestamp: barData.timestamp });
        if (indicators.rsi.length > 100) {
          indicators.rsi = indicators.rsi.slice(-100);
        }
      }

      // Store volume data
      indicators.volume.push({ value: barData.volume, timestamp: barData.timestamp });
      if (indicators.volume.length > 100) {
        indicators.volume = indicators.volume.slice(-100);
      }
      
    } catch (error) {
      this.logger.error('Error updating technical indicators', {
        symbol,
        error: error.message,
        correlationId: this.correlationId
      });
    }
  }

  /**
   * Calculate Simple Moving Average
   */
  calculateSMA(prices) {
    return prices.reduce((sum, price) => sum + price, 0) / prices.length;
  }

  /**
   * Calculate RSI (Relative Strength Index)
   */
  calculateRSI(prices, period = 14) {
    if (prices.length < period + 1) return 50;

    let gains = 0;
    let losses = 0;

    for (let i = 1; i < prices.length; i++) {
      const change = prices[i] - prices[i - 1];
      if (change > 0) {
        gains += change;
      } else {
        losses -= change;
      }
    }

    const avgGain = gains / period;
    const avgLoss = losses / period;
    const rs = avgGain / avgLoss;
    const rsi = 100 - (100 / (1 + rs));

    return rsi;
  }

  /**
   * Start signal generation engine
   */
  startSignalGeneration() {
    if (this.signalGenerationInterval) {
      clearInterval(this.signalGenerationInterval);
    }

    this.signalGenerationInterval = setInterval(() => {
      try {
        this.processSignalBuffer();
      } catch (error) {
        this.logger.error('Error in signal generation loop', {
          error: error.message,
          correlationId: this.correlationId
        });
      }
    }, this.config.updateInterval);
  }

  /**
   * Process accumulated signals
   */
  processSignalBuffer() {
    if (this.signalBuffer.length === 0) return;

    const signals = [...this.signalBuffer];
    this.signalBuffer = [];

    // Group signals by symbol and prioritize by confidence
    const signalsBySymbol = new Map();
    
    signals.forEach(signal => {
      if (!signalsBySymbol.has(signal.symbol)) {
        signalsBySymbol.set(signal.symbol, []);
      }
      signalsBySymbol.get(signal.symbol).push(signal);
    });

    // Emit best signal for each symbol
    signalsBySymbol.forEach((symbolSignals, symbol) => {
      const bestSignal = symbolSignals.reduce((best, current) => 
        current.confidence > best.confidence ? current : best
      );

      this.emit('bestSignal', bestSignal);
    });
  }

  /**
   * Start data cleanup process
   */
  startDataCleanup() {
    if (this.cleanupInterval) {
      clearInterval(this.cleanupInterval);
    }

    this.cleanupInterval = setInterval(() => {
      this.cleanupOldData();
    }, 60000); // Every minute
  }

  /**
   * Cleanup old data to prevent memory issues
   */
  cleanupOldData() {
    const cutoffTime = Date.now() - (this.config.dataRetentionHours * 60 * 60 * 1000);

    // Clean up price history
    this.priceHistory.forEach((history, symbol) => {
      const filtered = history.filter(point => point.timestamp > cutoffTime);
      this.priceHistory.set(symbol, filtered);
    });

    // Clean up market data
    this.marketData.forEach((data, symbol) => {
      data.trades = data.trades.filter(trade => trade.timestamp.getTime() > cutoffTime);
      data.quotes = data.quotes.filter(quote => quote.timestamp.getTime() > cutoffTime);
      data.bars = data.bars.filter(bar => bar.timestamp.getTime() > cutoffTime);
    });
  }

  /**
   * Get current market data for symbol
   */
  getMarketData(symbol) {
    return this.marketData.get(symbol) || null;
  }

  /**
   * Get latest signals
   */
  getLatestSignals(limit = 10) {
    return this.signalBuffer.slice(-limit);
  }

  /**
   * Get performance metrics
   */
  getMetrics() {
    return {
      ...this.metrics,
      activeSubscriptions: this.subscriptions.size,
      totalSymbols: this.marketData.size,
      signalBufferSize: this.signalBuffer.length
    };
  }

  /**
   * Shutdown data integrator
   */
  async shutdown() {
    try {
      this.logger.info('Shutting down real-time data integrator', {
        correlationId: this.correlationId
      });

      this.isRunning = false;

      // Clear intervals
      if (this.signalGenerationInterval) {
        clearInterval(this.signalGenerationInterval);
      }
      if (this.cleanupInterval) {
        clearInterval(this.cleanupInterval);
      }

      // Disconnect data feeds
      this.dataFeeds.forEach((feed, name) => {
        if (feed.connection && feed.connection.disconnect) {
          feed.connection.disconnect();
        }
      });

      this.metrics.connectionStatus = 'disconnected';
      
      this.logger.info('Real-time data integrator shut down successfully', {
        correlationId: this.correlationId
      });
      
    } catch (error) {
      this.logger.error('Error shutting down real-time data integrator', {
        error: error.message,
        correlationId: this.correlationId
      });
    }
  }
}

module.exports = RealTimeDataIntegrator;
/**
 * Enhanced Real-time Market Data Pipeline
 * Provides optimized data streaming with buffering, batch processing, and performance monitoring
 */

const { getTimeout, withTradingTimeout } = require('./timeoutManager');
const { createRequestLogger } = require('./logger');

class RealtimeDataPipeline {
  constructor(options = {}) {
    this.options = {
      bufferSize: options.bufferSize || 1000,
      flushInterval: options.flushInterval || 1000, // ms
      maxRetries: options.maxRetries || 3,
      batchSize: options.batchSize || 100,
      compressionEnabled: options.compressionEnabled || true,
      performanceMonitoring: options.performanceMonitoring || true,
      ...options
    };

    // Data buffers for different data types
    this.dataBuffers = {
      quotes: new Map(), // symbol -> latest quote
      trades: [],
      bars: new Map(), // symbol -> latest bar
      news: [],
      orderbook: new Map() // symbol -> latest orderbook
    };

    // Performance metrics
    this.metrics = {
      messagesReceived: 0,
      messagesProcessed: 0,
      messagesDropped: 0,
      batchesFlushed: 0,
      averageLatency: 0,
      lastFlushTime: Date.now(),
      bufferUtilization: 0,
      throughputPerSecond: 0
    };

    // Subscriptions and connections
    this.subscriptions = new Map(); // userId -> subscription details
    this.connectionPool = new Map(); // connectionId -> connection details
    
    // Buffer management
    this.flushTimer = null;
    this.compressionEnabled = this.options.compressionEnabled;
    
    // Performance monitoring
    this.performanceTimer = null;
    this.startPerformanceMonitoring();

    this.logger = createRequestLogger('realtime-pipeline');
    this.logger.info('🚀 Real-time Data Pipeline initialized', this.options);
  }

  /**
   * Start performance monitoring
   */
  startPerformanceMonitoring() {
    if (!this.options.performanceMonitoring) return;

    this.performanceTimer = setInterval(() => {
      this.calculatePerformanceMetrics();
      this.logPerformanceMetrics();
    }, 5000); // Every 5 seconds

    // Start periodic buffer flush
    this.flushTimer = setInterval(() => {
      this.flushBuffers();
    }, this.options.flushInterval);
  }

  /**
   * Add a user subscription for real-time data
   */
  addSubscription(userId, symbols, dataTypes = ['quotes'], options = {}) {
    const subscriptionId = `${userId}_${Date.now()}`;
    
    const subscription = {
      id: subscriptionId,
      userId,
      symbols: new Set(symbols),
      dataTypes: new Set(dataTypes),
      options: {
        compression: options.compression || 'gzip',
        throttle: options.throttle || 100, // ms between updates
        conflation: options.conflation || true, // combine rapid updates
        ...options
      },
      metrics: {
        messagesDelivered: 0,
        lastDeliveryTime: Date.now(),
        avgDeliveryLatency: 0
      },
      createdAt: Date.now(),
      lastActivityAt: Date.now()
    };

    this.subscriptions.set(subscriptionId, subscription);
    
    this.logger.info('📡 Subscription added', {
      subscriptionId,
      userId: `${userId.substring(0, 8)}...`,
      symbols: Array.from(symbols),
      dataTypes: Array.from(dataTypes)
    });

    return subscriptionId;
  }

  /**
   * Remove a user subscription
   */
  removeSubscription(subscriptionId) {
    const subscription = this.subscriptions.get(subscriptionId);
    if (subscription) {
      this.subscriptions.delete(subscriptionId);
      this.logger.info('📡 Subscription removed', {
        subscriptionId,
        userId: `${subscription.userId.substring(0, 8)}...`
      });
    }
  }

  /**
   * Process incoming market data with intelligent buffering
   */
  processIncomingData(dataType, data) {
    const processStart = Date.now();
    
    try {
      this.metrics.messagesReceived++;

      // Route data to appropriate buffer
      switch (dataType) {
        case 'quote':
        case 'quotes':
          this.bufferQuoteData(data);
          break;
        case 'trade':
        case 'trades':
          this.bufferTradeData(data);
          break;
        case 'bar':
        case 'bars':
          this.bufferBarData(data);
          break;
        case 'news':
          this.bufferNewsData(data);
          break;
        case 'orderbook':
          this.bufferOrderBookData(data);
          break;
        default:
          this.logger.warn('Unknown data type received', { dataType, data });
          this.metrics.messagesDropped++;
          return;
      }

      this.metrics.messagesProcessed++;
      
      // Check if we need to flush buffers
      if (this.shouldFlushBuffers()) {
        this.flushBuffers();
      }

      // Update latency metrics
      const latency = Date.now() - processStart;
      this.updateLatencyMetrics(latency);

    } catch (error) {
      this.metrics.messagesDropped++;
      this.logger.error('Error processing incoming data', { 
        dataType, 
        error: error.message,
        stack: error.stack 
      });
    }
  }

  /**
   * Buffer quote data with conflation
   */
  bufferQuoteData(data) {
    if (Array.isArray(data)) {
      data.forEach(quote => this.bufferSingleQuote(quote));
    } else {
      this.bufferSingleQuote(data);
    }
  }

  bufferSingleQuote(quote) {
    const symbol = quote.symbol || quote.S;
    if (!symbol) return;

    // Store latest quote with timestamp
    this.dataBuffers.quotes.set(symbol, {
      ...quote,
      bufferedAt: Date.now(),
      price: quote.price || quote.ap || quote.bp || 0,
      bid: quote.bid || quote.bp || 0,
      ask: quote.ask || quote.ap || 0,
      bidSize: quote.bidSize || quote.bs || 0,
      askSize: quote.askSize || quote.as || 0,
      timestamp: quote.timestamp || quote.t || Date.now()
    });
  }

  /**
   * Buffer trade data
   */
  bufferTradeData(data) {
    if (Array.isArray(data)) {
      this.dataBuffers.trades.push(...data.map(trade => ({
        ...trade,
        bufferedAt: Date.now()
      })));
    } else {
      this.dataBuffers.trades.push({
        ...data,
        bufferedAt: Date.now()
      });
    }

    // Limit trade buffer size
    if (this.dataBuffers.trades.length > this.options.bufferSize) {
      this.dataBuffers.trades = this.dataBuffers.trades.slice(-this.options.bufferSize);
    }
  }

  /**
   * Buffer bar/candlestick data
   */
  bufferBarData(data) {
    if (Array.isArray(data)) {
      data.forEach(bar => this.bufferSingleBar(bar));
    } else {
      this.bufferSingleBar(data);
    }
  }

  bufferSingleBar(bar) {
    const symbol = bar.symbol || bar.S;
    if (!symbol) return;

    this.dataBuffers.bars.set(symbol, {
      ...bar,
      bufferedAt: Date.now()
    });
  }

  /**
   * Buffer news data
   */
  bufferNewsData(data) {
    if (Array.isArray(data)) {
      this.dataBuffers.news.push(...data.map(news => ({
        ...news,
        bufferedAt: Date.now()
      })));
    } else {
      this.dataBuffers.news.push({
        ...data,
        bufferedAt: Date.now()
      });
    }

    // Limit news buffer size
    if (this.dataBuffers.news.length > this.options.bufferSize) {
      this.dataBuffers.news = this.dataBuffers.news.slice(-this.options.bufferSize);
    }
  }

  /**
   * Buffer order book data
   */
  bufferOrderBookData(data) {
    const symbol = data.symbol || data.S;
    if (!symbol) return;

    this.dataBuffers.orderbook.set(symbol, {
      ...data,
      bufferedAt: Date.now()
    });
  }

  /**
   * Check if buffers should be flushed
   */
  shouldFlushBuffers() {
    const now = Date.now();
    const timeSinceLastFlush = now - this.metrics.lastFlushTime;
    
    // Flush if interval exceeded
    if (timeSinceLastFlush >= this.options.flushInterval) {
      return true;
    }

    // Flush if any buffer is approaching capacity
    const quoteBufferSize = this.dataBuffers.quotes.size;
    const tradeBufferSize = this.dataBuffers.trades.length;
    const newsBufferSize = this.dataBuffers.news.length;
    
    const maxUtilization = Math.max(
      quoteBufferSize / this.options.bufferSize,
      tradeBufferSize / this.options.bufferSize,
      newsBufferSize / this.options.bufferSize
    );

    return maxUtilization > 0.8; // Flush at 80% capacity
  }

  /**
   * Flush all buffers and distribute to subscribers
   */
  async flushBuffers() {
    const flushStart = Date.now();
    
    try {
      // Prepare data for distribution
      const dataPacket = this.prepareDataPacket();
      
      if (this.isDataPacketEmpty(dataPacket)) {
        return; // Nothing to flush
      }

      // Distribute to subscribers
      await this.distributeToSubscribers(dataPacket);

      // Clear processed buffers
      this.clearProcessedBuffers();

      // Update metrics
      this.metrics.batchesFlushed++;
      this.metrics.lastFlushTime = Date.now();
      
      const flushDuration = Date.now() - flushStart;
      this.logger.debug('Buffers flushed', {
        duration: `${flushDuration}ms`,
        dataPacketSize: this.calculateDataPacketSize(dataPacket),
        subscriberCount: this.subscriptions.size
      });

    } catch (error) {
      this.logger.error('Error flushing buffers', {
        error: error.message,
        stack: error.stack
      });
    }
  }

  /**
   * Prepare data packet for distribution
   */
  prepareDataPacket() {
    return {
      quotes: new Map(this.dataBuffers.quotes),
      trades: [...this.dataBuffers.trades],
      bars: new Map(this.dataBuffers.bars),
      news: [...this.dataBuffers.news],
      orderbook: new Map(this.dataBuffers.orderbook),
      timestamp: Date.now(),
      sequenceNumber: this.metrics.batchesFlushed + 1
    };
  }

  /**
   * Check if data packet is empty
   */
  isDataPacketEmpty(dataPacket) {
    return dataPacket.quotes.size === 0 &&
           dataPacket.trades.length === 0 &&
           dataPacket.bars.size === 0 &&
           dataPacket.news.length === 0 &&
           dataPacket.orderbook.size === 0;
  }

  /**
   * Distribute data to all active subscribers
   */
  async distributeToSubscribers(dataPacket) {
    const distributionPromises = [];

    for (const [subscriptionId, subscription] of this.subscriptions) {
      try {
        // Filter data for this subscription
        const filteredData = this.filterDataForSubscription(dataPacket, subscription);
        
        if (this.isDataPacketEmpty(filteredData)) {
          continue; // No relevant data for this subscription
        }

        // Apply subscription options (compression, throttling, etc.)
        const processedData = await this.processDataForSubscription(filteredData, subscription);

        // Queue for delivery
        distributionPromises.push(
          this.deliverToSubscription(subscriptionId, processedData)
        );

      } catch (error) {
        this.logger.error('Error preparing data for subscription', {
          subscriptionId,
          error: error.message
        });
      }
    }

    // Execute all distributions in parallel
    if (distributionPromises.length > 0) {
      try {
        await Promise.allSettled(distributionPromises);
      } catch (error) {
        this.logger.error('Error in parallel distribution', {
          error: error.message
        });
      }
    }
  }

  /**
   * Filter data packet for specific subscription
   */
  filterDataForSubscription(dataPacket, subscription) {
    const filteredData = {
      quotes: new Map(),
      trades: [],
      bars: new Map(),
      news: [],
      orderbook: new Map(),
      timestamp: dataPacket.timestamp,
      sequenceNumber: dataPacket.sequenceNumber
    };

    // Filter by symbols and data types
    if (subscription.dataTypes.has('quotes')) {
      for (const [symbol, quote] of dataPacket.quotes) {
        if (subscription.symbols.has(symbol)) {
          filteredData.quotes.set(symbol, quote);
        }
      }
    }

    if (subscription.dataTypes.has('trades')) {
      filteredData.trades = dataPacket.trades.filter(trade => 
        subscription.symbols.has(trade.symbol || trade.S)
      );
    }

    if (subscription.dataTypes.has('bars')) {
      for (const [symbol, bar] of dataPacket.bars) {
        if (subscription.symbols.has(symbol)) {
          filteredData.bars.set(symbol, bar);
        }
      }
    }

    if (subscription.dataTypes.has('news')) {
      filteredData.news = dataPacket.news; // News is not symbol-specific
    }

    if (subscription.dataTypes.has('orderbook')) {
      for (const [symbol, orderbook] of dataPacket.orderbook) {
        if (subscription.symbols.has(symbol)) {
          filteredData.orderbook.set(symbol, orderbook);
        }
      }
    }

    return filteredData;
  }

  /**
   * Process data for specific subscription (compression, throttling, etc.)
   */
  async processDataForSubscription(dataPacket, subscription) {
    let processedData = { ...dataPacket };

    // Convert Maps to Objects for JSON serialization
    processedData.quotes = Object.fromEntries(dataPacket.quotes);
    processedData.bars = Object.fromEntries(dataPacket.bars);
    processedData.orderbook = Object.fromEntries(dataPacket.orderbook);

    // Apply compression if enabled
    if (subscription.options.compression && this.compressionEnabled) {
      processedData = await this.compressData(processedData, subscription.options.compression);
    }

    return processedData;
  }

  /**
   * Deliver data to specific subscription
   */
  async deliverToSubscription(subscriptionId, data) {
    const subscription = this.subscriptions.get(subscriptionId);
    if (!subscription) return;

    const deliveryStart = Date.now();

    try {
      // Check throttling
      const timeSinceLastDelivery = Date.now() - subscription.metrics.lastDeliveryTime;
      if (timeSinceLastDelivery < subscription.options.throttle) {
        return; // Skip delivery due to throttling
      }

      // This would typically send data via WebSocket or HTTP SSE
      // For now, we'll store it in a delivery queue
      await this.queueForDelivery(subscriptionId, data);

      // Update subscription metrics
      const deliveryLatency = Date.now() - deliveryStart;
      subscription.metrics.messagesDelivered++;
      subscription.metrics.lastDeliveryTime = Date.now();
      subscription.metrics.avgDeliveryLatency = 
        (subscription.metrics.avgDeliveryLatency + deliveryLatency) / 2;
      subscription.lastActivityAt = Date.now();

    } catch (error) {
      this.logger.error('Error delivering to subscription', {
        subscriptionId,
        error: error.message
      });
    }
  }

  /**
   * Queue data for delivery (placeholder for actual delivery mechanism)
   */
  async queueForDelivery(subscriptionId, data) {
    // This would integrate with your WebSocket or SSE delivery mechanism
    // For now, we'll just log the delivery
    this.logger.debug('Data queued for delivery', {
      subscriptionId,
      dataSize: JSON.stringify(data).length,
      timestamp: data.timestamp
    });
  }

  /**
   * Compress data for delivery
   */
  async compressData(data, compressionType = 'gzip') {
    // Placeholder for compression logic
    // In a real implementation, you'd use compression libraries
    return {
      ...data,
      compressed: true,
      compressionType,
      originalSize: JSON.stringify(data).length
    };
  }

  /**
   * Clear processed buffers
   */
  clearProcessedBuffers() {
    this.dataBuffers.quotes.clear();
    this.dataBuffers.trades.length = 0;
    this.dataBuffers.bars.clear();
    this.dataBuffers.news.length = 0;
    this.dataBuffers.orderbook.clear();
  }

  /**
   * Calculate data packet size
   */
  calculateDataPacketSize(dataPacket) {
    return {
      quotes: dataPacket.quotes.size,
      trades: dataPacket.trades.length,
      bars: dataPacket.bars.size,
      news: dataPacket.news.length,
      orderbook: dataPacket.orderbook.size
    };
  }

  /**
   * Calculate performance metrics
   */
  calculatePerformanceMetrics() {
    const now = Date.now();
    const elapsedSeconds = (now - (this.metrics.lastCalculationTime || now)) / 1000;
    
    if (elapsedSeconds > 0) {
      this.metrics.throughputPerSecond = this.metrics.messagesProcessed / elapsedSeconds;
    }

    // Calculate buffer utilization
    const totalBufferCapacity = this.options.bufferSize * 5; // 5 different buffer types
    const currentBufferUsage = 
      this.dataBuffers.quotes.size +
      this.dataBuffers.trades.length +
      this.dataBuffers.bars.size +
      this.dataBuffers.news.length +
      this.dataBuffers.orderbook.size;
    
    this.metrics.bufferUtilization = (currentBufferUsage / totalBufferCapacity) * 100;
    this.metrics.lastCalculationTime = now;
  }

  /**
   * Update latency metrics
   */
  updateLatencyMetrics(latency) {
    if (this.metrics.averageLatency === 0) {
      this.metrics.averageLatency = latency;
    } else {
      this.metrics.averageLatency = (this.metrics.averageLatency + latency) / 2;
    }
  }

  /**
   * Log performance metrics
   */
  logPerformanceMetrics() {
    this.logger.info('📊 Real-time pipeline performance', {
      metrics: {
        messagesReceived: this.metrics.messagesReceived,
        messagesProcessed: this.metrics.messagesProcessed,
        messagesDropped: this.metrics.messagesDropped,
        batchesFlushed: this.metrics.batchesFlushed,
        averageLatency: `${this.metrics.averageLatency.toFixed(2)}ms`,
        bufferUtilization: `${this.metrics.bufferUtilization.toFixed(1)}%`,
        throughputPerSecond: this.metrics.throughputPerSecond.toFixed(2),
        activeSubscriptions: this.subscriptions.size
      }
    });
  }

  /**
   * Get current pipeline status
   */
  getStatus() {
    return {
      status: 'active',
      metrics: this.metrics,
      subscriptions: {
        total: this.subscriptions.size,
        active: Array.from(this.subscriptions.values()).filter(
          sub => Date.now() - sub.lastActivityAt < 60000
        ).length
      },
      buffers: {
        quotes: this.dataBuffers.quotes.size,
        trades: this.dataBuffers.trades.length,
        bars: this.dataBuffers.bars.size,
        news: this.dataBuffers.news.length,
        orderbook: this.dataBuffers.orderbook.size
      },
      options: this.options
    };
  }

  /**
   * Cleanup and shutdown
   */
  shutdown() {
    if (this.flushTimer) {
      clearInterval(this.flushTimer);
    }
    
    if (this.performanceTimer) {
      clearInterval(this.performanceTimer);
    }

    // Final flush
    this.flushBuffers();
    
    this.logger.info('🛑 Real-time Data Pipeline shutdown completed');
  }
}

module.exports = { RealtimeDataPipeline };
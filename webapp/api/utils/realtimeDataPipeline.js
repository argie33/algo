/**
 * High-Performance Real-time Market Data Pipeline
 * Institutional-grade streaming with ultra-low latency optimization and adaptive throughput management
 */

const { getTimeout, withTradingTimeout } = require('./timeoutManager');
const { createRequestLogger } = require('./logger');
const EventEmitter = require('events');

class RealtimeDataPipeline extends EventEmitter {
  constructor(options = {}) {
    super();
    this.options = {
      bufferSize: options.bufferSize || 2000,
      flushInterval: options.flushInterval || 100, // Reduced to 100ms for ultra-low latency
      maxRetries: options.maxRetries || 3,
      batchSize: options.batchSize || 50, // Smaller batches for faster processing
      compressionEnabled: options.compressionEnabled || true,
      performanceMonitoring: options.performanceMonitoring || true,
      // New high-performance options
      maxConcurrentFlushes: options.maxConcurrentFlushes || 5,
      adaptiveBuffering: options.adaptiveBuffering || true,
      priorityQueuing: options.priorityQueuing || true,
      memoryOptimization: options.memoryOptimization || true,
      circuitBreakerEnabled: options.circuitBreakerEnabled || true,
      preallocationEnabled: options.preallocationEnabled || true,
      ...options
    };

    // High-performance data buffers with priority queuing
    this.dataBuffers = {
      quotes: new Map(), // symbol -> latest quote
      trades: [],
      bars: new Map(), // symbol -> latest bar
      news: [],
      orderbook: new Map() // symbol -> latest orderbook
    };

    // Priority queues for different data types
    this.priorityQueues = {
      critical: [], // Time-sensitive data (quotes, trades)
      high: [],     // Important data (bars, orderbook)
      normal: [],   // Regular data (news, alerts)
      low: []       // Background data (sentiment, research)
    };

    // Enhanced performance metrics
    this.metrics = {
      messagesReceived: 0,
      messagesProcessed: 0,
      messagesDropped: 0,
      batchesFlushed: 0,
      averageLatency: 0,
      lastFlushTime: Date.now(),
      bufferUtilization: 0,
      throughputPerSecond: 0,
      // New performance metrics
      peakThroughput: 0,
      latencyP95: 0,
      latencyP99: 0,
      circuitBreakerTrips: 0,
      memoryUtilization: 0,
      concurrentFlushes: 0,
      adaptiveBufferResizes: 0,
      priorityQueueSizes: { critical: 0, high: 0, normal: 0, low: 0 }
    };

    // Subscriptions and connections
    this.subscriptions = new Map(); // userId -> subscription details
    this.connectionPool = new Map(); // connectionId -> connection details
    
    // Advanced buffer management
    this.flushTimer = null;
    this.adaptiveTimer = null;
    this.compressionEnabled = this.options.compressionEnabled;
    this.currentFlushes = 0;
    this.flushQueue = [];
    
    // Circuit breaker for overload protection
    this.circuitBreaker = {
      isOpen: false,
      failures: 0,
      lastFailureTime: 0,
      threshold: 5,
      resetTimeout: 30000 // 30 seconds
    };

    // Memory optimization
    this.memoryPool = {
      buffers: [],
      maxPoolSize: 100,
      currentSize: 0
    };

    // Performance monitoring with adaptive intervals
    this.performanceTimer = null;
    this.latencyHistory = [];
    this.throughputHistory = [];
    this.startPerformanceMonitoring();

    this.logger = createRequestLogger('realtime-pipeline');
    this.logger.info('🚀 Real-time Data Pipeline initialized', this.options);
  }

  /**
   * Start performance monitoring with adaptive intervals
   */
  startPerformanceMonitoring() {
    if (!this.options.performanceMonitoring) return;

    // Adaptive performance monitoring based on load
    this.performanceTimer = setInterval(() => {
      this.calculatePerformanceMetrics();
      this.logPerformanceMetrics();
      this.adaptiveBufferManagement();
    }, 1000); // Every second for responsive monitoring

    // Start high-frequency buffer flush with adaptive intervals
    this.flushTimer = setInterval(() => {
      this.adaptiveFlushBuffers();
    }, this.options.flushInterval);

    // Start adaptive buffer management
    if (this.options.adaptiveBuffering) {
      this.adaptiveTimer = setInterval(() => {
        this.optimizeBufferSizes();
      }, 5000); // Every 5 seconds
    }
  }

  /**
   * Adaptive buffer management based on current load
   */
  adaptiveBufferManagement() {
    if (!this.options.adaptiveBuffering) return;

    const currentLoad = this.metrics.throughputPerSecond;
    const bufferUtilization = this.metrics.bufferUtilization;

    // Adjust flush interval based on load
    if (currentLoad > 1000 && this.options.flushInterval > 50) {
      // High load - increase flush frequency
      this.options.flushInterval = Math.max(50, this.options.flushInterval - 10);
      this.restartFlushTimer();
    } else if (currentLoad < 100 && this.options.flushInterval < 500) {
      // Low load - decrease flush frequency to save resources
      this.options.flushInterval = Math.min(500, this.options.flushInterval + 10);
      this.restartFlushTimer();
    }

    // Adjust buffer size based on utilization
    if (bufferUtilization > 80) {
      // High utilization - increase buffer size
      this.options.bufferSize = Math.min(5000, this.options.bufferSize * 1.2);
      this.metrics.adaptiveBufferResizes++;
    } else if (bufferUtilization < 20 && this.options.bufferSize > 1000) {
      // Low utilization - decrease buffer size to save memory
      this.options.bufferSize = Math.max(1000, this.options.bufferSize * 0.9);
      this.metrics.adaptiveBufferResizes++;
    }
  }

  /**
   * Restart flush timer with new interval
   */
  restartFlushTimer() {
    if (this.flushTimer) {
      clearInterval(this.flushTimer);
    }
    this.flushTimer = setInterval(() => {
      this.adaptiveFlushBuffers();
    }, this.options.flushInterval);
  }

  /**
   * Circuit breaker check for overload protection
   */
  checkCircuitBreaker() {
    if (!this.options.circuitBreakerEnabled) return false;

    const now = Date.now();
    
    // Reset circuit breaker if enough time has passed
    if (this.circuitBreaker.isOpen && 
        now - this.circuitBreaker.lastFailureTime > this.circuitBreaker.resetTimeout) {
      this.circuitBreaker.isOpen = false;
      this.circuitBreaker.failures = 0;
      this.logger.info('🔄 Circuit breaker reset');
    }

    return this.circuitBreaker.isOpen;
  }

  /**
   * Trip circuit breaker on failure
   */
  tripCircuitBreaker(error) {
    if (!this.options.circuitBreakerEnabled) return;

    this.circuitBreaker.failures++;
    this.circuitBreaker.lastFailureTime = Date.now();
    this.metrics.circuitBreakerTrips++;

    if (this.circuitBreaker.failures >= this.circuitBreaker.threshold) {
      this.circuitBreaker.isOpen = true;
      this.logger.error('🔥 Circuit breaker tripped', { 
        failures: this.circuitBreaker.failures,
        error: error.message 
      });
      this.emit('circuitBreakerTripped', { failures: this.circuitBreaker.failures, error });
    }
  }

  /**
   * Get buffer from memory pool or create new one
   */
  getBuffer() {
    if (this.options.memoryOptimization && this.memoryPool.buffers.length > 0) {
      return this.memoryPool.buffers.pop();
    }
    return {};
  }

  /**
   * Return buffer to memory pool
   */
  returnBuffer(buffer) {
    if (this.options.memoryOptimization && this.memoryPool.currentSize < this.memoryPool.maxPoolSize) {
      // Clear buffer contents
      for (const key in buffer) {
        delete buffer[key];
      }
      this.memoryPool.buffers.push(buffer);
      this.memoryPool.currentSize++;
    }
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
   * Process incoming market data with priority-based intelligent buffering
   */
  processIncomingData(dataType, data) {
    const processStart = Date.now();
    
    try {
      // Circuit breaker check
      if (this.checkCircuitBreaker()) {
        this.metrics.messagesDropped++;
        return;
      }

      this.metrics.messagesReceived++;

      // Determine priority based on data type
      const priority = this.getDataPriority(dataType);
      
      // Route data to appropriate buffer with priority
      switch (dataType) {
        case 'quote':
        case 'quotes':
          this.bufferQuoteDataWithPriority(data, priority);
          break;
        case 'trade':
        case 'trades':
          this.bufferTradeDataWithPriority(data, priority);
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
      
      // Check if we need immediate flush for critical data
      if (priority === 'critical' && this.shouldFlushBuffers()) {
        this.triggerImmediateFlush();
      }

      // Update latency metrics
      const latency = Date.now() - processStart;
      this.updateLatencyMetrics(latency);

    } catch (error) {
      this.metrics.messagesDropped++;
      this.tripCircuitBreaker(error);
      this.logger.error('Error processing incoming data', { 
        dataType, 
        error: error.message,
        stack: error.stack 
      });
    }
  }

  /**
   * Determine data priority for processing
   */
  getDataPriority(dataType) {
    switch (dataType) {
      case 'quote':
      case 'quotes':
      case 'trade':
      case 'trades':
        return 'critical';
      case 'bar':
      case 'bars':
      case 'orderbook':
        return 'high';
      case 'news':
      case 'alerts':
        return 'normal';
      default:
        return 'low';
    }
  }

  /**
   * Buffer quote data with priority handling
   */
  bufferQuoteDataWithPriority(data, priority) {
    if (Array.isArray(data)) {
      data.forEach(quote => this.bufferSingleQuoteWithPriority(quote, priority));
    } else {
      this.bufferSingleQuoteWithPriority(data, priority);
    }
  }

  /**
   * Buffer single quote with priority
   */
  bufferSingleQuoteWithPriority(quote, priority) {
    const symbol = quote.symbol || quote.S;
    if (!symbol) return;

    // Store latest quote with timestamp and priority
    const quoteData = {
      ...quote,
      bufferedAt: Date.now(),
      priority: priority,
      price: quote.price || quote.ap || quote.bp || 0,
      bid: quote.bid || quote.bp || 0,
      ask: quote.ask || quote.ap || 0,
      bidSize: quote.bidSize || quote.bs || 0,
      askSize: quote.askSize || quote.as || 0,
      timestamp: quote.timestamp || quote.t || Date.now()
    };

    this.dataBuffers.quotes.set(symbol, quoteData);

    // Add to priority queue if enabled
    if (this.options.priorityQueuing) {
      this.priorityQueues[priority].push(quoteData);
      this.metrics.priorityQueueSizes[priority]++;
    }
  }

  /**
   * Buffer trade data with priority
   */
  bufferTradeDataWithPriority(data, priority) {
    if (Array.isArray(data)) {
      this.dataBuffers.trades.push(...data.map(trade => ({
        ...trade,
        bufferedAt: Date.now(),
        priority: priority
      })));
    } else {
      this.dataBuffers.trades.push({
        ...data,
        bufferedAt: Date.now(),
        priority: priority
      });
    }

    // Limit trade buffer size
    if (this.dataBuffers.trades.length > this.options.bufferSize) {
      this.dataBuffers.trades = this.dataBuffers.trades.slice(-this.options.bufferSize);
    }
  }

  /**
   * Adaptive flush buffers with concurrent processing
   */
  async adaptiveFlushBuffers() {
    // Don't flush if we're at max concurrent flushes
    if (this.currentFlushes >= this.options.maxConcurrentFlushes) {
      return;
    }

    // Check if we should flush based on priority queues
    if (this.shouldFlushBuffers() || this.hasCriticalData()) {
      this.currentFlushes++;
      this.metrics.concurrentFlushes = this.currentFlushes;

      try {
        await this.flushBuffers();
      } finally {
        this.currentFlushes--;
        this.metrics.concurrentFlushes = this.currentFlushes;
      }
    }
  }

  /**
   * Check if we have critical data that needs immediate processing
   */
  hasCriticalData() {
    return this.priorityQueues.critical.length > 0 || 
           this.priorityQueues.high.length > this.options.batchSize / 2;
  }

  /**
   * Trigger immediate flush for critical data
   */
  triggerImmediateFlush() {
    if (this.currentFlushes < this.options.maxConcurrentFlushes) {
      setImmediate(() => this.adaptiveFlushBuffers());
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
   * Calculate enhanced performance metrics with percentiles
   */
  calculatePerformanceMetrics() {
    const now = Date.now();
    const elapsedSeconds = (now - (this.metrics.lastCalculationTime || now)) / 1000;
    
    if (elapsedSeconds > 0) {
      const currentThroughput = this.metrics.messagesProcessed / elapsedSeconds;
      this.metrics.throughputPerSecond = currentThroughput;
      
      // Track peak throughput
      if (currentThroughput > this.metrics.peakThroughput) {
        this.metrics.peakThroughput = currentThroughput;
      }
      
      // Add to throughput history for trend analysis
      this.throughputHistory.push(currentThroughput);
      if (this.throughputHistory.length > 100) {
        this.throughputHistory.shift();
      }
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
    
    // Calculate priority queue sizes
    this.metrics.priorityQueueSizes = {
      critical: this.priorityQueues.critical.length,
      high: this.priorityQueues.high.length,
      normal: this.priorityQueues.normal.length,
      low: this.priorityQueues.low.length
    };
    
    // Calculate latency percentiles
    if (this.latencyHistory.length > 0) {
      const sortedLatencies = [...this.latencyHistory].sort((a, b) => a - b);
      const p95Index = Math.floor(sortedLatencies.length * 0.95);
      const p99Index = Math.floor(sortedLatencies.length * 0.99);
      
      this.metrics.latencyP95 = sortedLatencies[p95Index] || 0;
      this.metrics.latencyP99 = sortedLatencies[p99Index] || 0;
    }
    
    // Calculate memory utilization (approximate)
    const memoryUsage = process.memoryUsage();
    this.metrics.memoryUtilization = (memoryUsage.heapUsed / memoryUsage.heapTotal) * 100;
    
    this.metrics.lastCalculationTime = now;
  }

  /**
   * Optimize buffer sizes based on historical performance
   */
  optimizeBufferSizes() {
    if (this.throughputHistory.length < 10) return;
    
    const avgThroughput = this.throughputHistory.reduce((sum, val) => sum + val, 0) / this.throughputHistory.length;
    const throughputVariance = this.throughputHistory.reduce((sum, val) => sum + Math.pow(val - avgThroughput, 2), 0) / this.throughputHistory.length;
    
    // Adjust buffer size based on throughput variance
    if (throughputVariance > 1000) {
      // High variance - increase buffer size for stability
      this.options.bufferSize = Math.min(5000, this.options.bufferSize * 1.1);
    } else if (throughputVariance < 100) {
      // Low variance - can reduce buffer size
      this.options.bufferSize = Math.max(1000, this.options.bufferSize * 0.95);
    }
  }

  /**
   * Update latency metrics with history tracking
   */
  updateLatencyMetrics(latency) {
    if (this.metrics.averageLatency === 0) {
      this.metrics.averageLatency = latency;
    } else {
      this.metrics.averageLatency = (this.metrics.averageLatency + latency) / 2;
    }
    
    // Add to latency history for percentile calculations
    this.latencyHistory.push(latency);
    if (this.latencyHistory.length > 1000) {
      this.latencyHistory.shift();
    }
  }

  /**
   * Log enhanced performance metrics
   */
  logPerformanceMetrics() {
    this.logger.info('📊 High-Performance Real-time Pipeline Metrics', {
      throughput: {
        current: this.metrics.throughputPerSecond.toFixed(2),
        peak: this.metrics.peakThroughput.toFixed(2),
        messagesReceived: this.metrics.messagesReceived,
        messagesProcessed: this.metrics.messagesProcessed,
        messagesDropped: this.metrics.messagesDropped
      },
      latency: {
        average: `${this.metrics.averageLatency.toFixed(2)}ms`,
        p95: `${this.metrics.latencyP95.toFixed(2)}ms`,
        p99: `${this.metrics.latencyP99.toFixed(2)}ms`
      },
      buffers: {
        utilization: `${this.metrics.bufferUtilization.toFixed(1)}%`,
        adaptiveResizes: this.metrics.adaptiveBufferResizes,
        concurrentFlushes: this.metrics.concurrentFlushes,
        batchesFlushed: this.metrics.batchesFlushed
      },
      priorityQueues: this.metrics.priorityQueueSizes,
      system: {
        memoryUtilization: `${this.metrics.memoryUtilization.toFixed(1)}%`,
        circuitBreakerTrips: this.metrics.circuitBreakerTrips,
        activeSubscriptions: this.subscriptions.size
      }
    });

    // Emit performance event for monitoring
    this.emit('performanceMetrics', this.metrics);
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
   * Cleanup and shutdown with enhanced resource management
   */
  shutdown() {
    if (this.flushTimer) {
      clearInterval(this.flushTimer);
    }
    
    if (this.performanceTimer) {
      clearInterval(this.performanceTimer);
    }

    if (this.adaptiveTimer) {
      clearInterval(this.adaptiveTimer);
    }

    // Clear priority queues
    Object.keys(this.priorityQueues).forEach(priority => {
      this.priorityQueues[priority].length = 0;
    });

    // Clear memory pool
    this.memoryPool.buffers.length = 0;
    this.memoryPool.currentSize = 0;

    // Final flush
    this.flushBuffers();
    
    this.logger.info('🛑 High-Performance Real-time Data Pipeline shutdown completed', {
      finalMetrics: {
        peakThroughput: this.metrics.peakThroughput,
        totalMessages: this.metrics.messagesProcessed,
        circuitBreakerTrips: this.metrics.circuitBreakerTrips,
        adaptiveResizes: this.metrics.adaptiveBufferResizes
      }
    });
  }
}

module.exports = { RealtimeDataPipeline };
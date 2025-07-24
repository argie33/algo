/**
 * HFT Live Data Integration Service
 * Optimized real-time data feeds for high-frequency trading operations
 */

import liveDataService from './liveDataService';
import apiLimitManager from './apiLimitManager';
import hftEngine from './hftEngine';

class HFTLiveDataIntegration {
  constructor() {
    // HFT-specific configuration
    this.config = {
      // Latency requirements (milliseconds)
      maxAcceptableLatency: 50,
      targetLatency: 25,
      latencyWarningThreshold: 30,
      
      // Data freshness requirements
      maxDataAge: 1000, // 1 second max age for HFT decisions
      staleDataThreshold: 500, // 500ms threshold for stale warnings
      
      // Connection optimization
      priorityConnectionReserved: true,
      fallbackConnectionEnabled: true,
      autoFailoverEnabled: true,
      
      // Message prioritization
      enableMessagePrioritization: true,
      criticalMessageTypes: ['trades', 'level1', 'orderbook'],
      
      // Performance monitoring
      enablePerformanceTracking: true,
      performanceMetricsInterval: 1000
    };
    
    // HFT symbol management
    this.hftSymbols = new Map(); // symbol -> HFTSymbolConfig
    this.symbolMetrics = new Map(); // symbol -> performance metrics
    this.activeStrategies = new Map(); // strategyId -> symbol[]
    
    // Performance tracking
    this.latencyHistory = [];
    this.throughputMetrics = {
      messagesPerSecond: 0,
      tradesPerSecond: 0,
      quotesPerSecond: 0
    };
    
    // Connection health
    this.connectionHealth = {
      primary: { healthy: false, latency: 0, lastCheck: 0 },
      fallback: { healthy: false, latency: 0, lastCheck: 0 }
    };
    
    this.initialize();
  }

  /**
   * Initialize HFT integration
   */
  async initialize() {
    try {
      // Set up live data service listeners with HFT optimizations
      this.setupLiveDataListeners();
      
      // Configure API limit manager for HFT priority
      this.configureApiLimitManager();
      
      // Start performance monitoring
      this.startPerformanceMonitoring();
      
      // Load HFT symbol configurations
      await this.loadHftSymbolConfigurations();
      
      console.log('🚀 HFT Live Data Integration initialized');
      
    } catch (error) {
      console.error('Failed to initialize HFT integration:', error);
      throw error;
    }
  }

  /**
   * Set up live data service listeners with HFT optimizations
   */
  setupLiveDataListeners() {
    // High-priority market data handler
    liveDataService.on('marketData', (data) => {
      this.handleHftMarketData(data);
    });
    
    // Connection status monitoring
    liveDataService.on('connected', () => {
      this.updateConnectionHealth('primary', true);
    });
    
    liveDataService.on('disconnected', () => {
      this.updateConnectionHealth('primary', false);
      this.handleConnectionLoss();
    });
    
    // Latency monitoring
    liveDataService.on('pong', (data) => {
      this.trackLatency(data.latency);
    });
    
    // Error handling with HFT implications
    liveDataService.on('error', (error) => {
      this.handleHftCriticalError(error);
    });
  }

  /**
   * Configure API limit manager for HFT priority
   */
  configureApiLimitManager() {
    // Set HFT symbols with high priority
    this.hftSymbols.forEach((config, symbol) => {
      apiLimitManager.setSymbolPriority(symbol, config.priority);
    });
    
    // Listen for quota warnings that might affect HFT
    apiLimitManager.on('quotaWarning', (warning) => {
      this.handleQuotaWarning(warning);
    });
    
    apiLimitManager.on('quotaEmergency', (emergency) => {
      this.handleQuotaEmergency(emergency);
    });
  }

  /**
   * Add symbol to HFT monitoring with specific configuration
   */
  addHftSymbol(symbol, config = {}) {
    const hftConfig = {
      symbol,
      priority: config.priority || 'critical',
      strategies: config.strategies || [],
      channels: config.channels || ['trades', 'quotes', 'level1'],
      latencyRequirement: config.latencyRequirement || this.config.maxAcceptableLatency,
      dataFreshness: config.dataFreshness || this.config.maxDataAge,
      enabled: true,
      addedAt: Date.now(),
      ...config
    };
    
    this.hftSymbols.set(symbol, hftConfig);
    
    // Initialize symbol metrics
    this.symbolMetrics.set(symbol, {
      latencyStats: { min: Infinity, max: 0, avg: 0, count: 0 },
      messageCount: 0,
      lastUpdate: 0,
      dataQuality: 'unknown',
      missedUpdates: 0,
      performanceScore: 100
    });
    
    // Subscribe to high-priority data feed
    this.subscribeToHftSymbol(symbol, hftConfig);
    
    // Update API limit manager
    apiLimitManager.setSymbolPriority(symbol, hftConfig.priority);
    
    console.log(`📈 Added HFT symbol: ${symbol} with priority ${hftConfig.priority}`);
    
    return hftConfig;
  }

  /**
   * Remove symbol from HFT monitoring
   */
  removeHftSymbol(symbol) {
    const config = this.hftSymbols.get(symbol);
    if (!config) return false;
    
    // Unsubscribe from data feeds
    liveDataService.unsubscribe([symbol]);
    
    // Clean up data structures
    this.hftSymbols.delete(symbol);
    this.symbolMetrics.delete(symbol);
    
    // Update API limit manager
    apiLimitManager.setSymbolPriority(symbol, 'standard');
    
    console.log(`📉 Removed HFT symbol: ${symbol}`);
    
    return true;
  }

  /**
   * Subscribe to high-priority data feed for HFT symbol
   */
  subscribeToHftSymbol(symbol, config) {
    // Subscribe with priority channels
    liveDataService.subscribe([symbol], config.channels);
    
    // Set up symbol-specific listener for real-time processing
    const symbolHandler = (data) => {
      this.processHftSymbolData(symbol, data);
    };
    
    liveDataService.on(`marketData:${symbol}`, symbolHandler);
    
    // Store handler reference for cleanup
    config.dataHandler = symbolHandler;
  }

  /**
   * Process HFT-specific market data with latency optimization
   */
  handleHftMarketData(data) {
    const receiveTime = Date.now();
    const { symbol } = data;
    
    // Check if this is an HFT symbol
    if (!this.hftSymbols.has(symbol)) {
      return; // Not an HFT symbol, let normal processing handle it
    }
    
    const config = this.hftSymbols.get(symbol);
    const metrics = this.symbolMetrics.get(symbol);
    
    // Calculate data latency
    const dataLatency = data.timestamp ? receiveTime - (data.timestamp * 1000) : 0;
    
    // Update symbol metrics
    this.updateSymbolMetrics(symbol, dataLatency, receiveTime);
    
    // Check latency requirements
    if (dataLatency > config.latencyRequirement) {
      console.warn(`⚠️ HFT latency warning for ${symbol}: ${dataLatency}ms > ${config.latencyRequirement}ms`);
      this.handleLatencyViolation(symbol, dataLatency, config.latencyRequirement);
    }
    
    // Check data freshness
    const dataAge = receiveTime - metrics.lastUpdate;
    if (metrics.lastUpdate > 0 && dataAge > config.dataFreshness) {
      console.warn(`⚠️ HFT data freshness warning for ${symbol}: ${dataAge}ms gap`);
      metrics.missedUpdates++;
    }
    
    // Forward to HFT engine with priority flag
    this.forwardToHftEngine(symbol, data, {
      receiveTime,
      dataLatency,
      dataAge,
      priority: config.priority
    });
  }

  /**
   * Process symbol-specific data for HFT operations
   */
  processHftSymbolData(symbol, data) {
    const config = this.hftSymbols.get(symbol);
    const metrics = this.symbolMetrics.get(symbol);
    
    if (!config || !config.enabled) return;
    
    // Update metrics
    metrics.messageCount++;
    metrics.lastUpdate = Date.now();
    
    // Calculate data quality score
    this.updateDataQualityScore(symbol, data);
    
    // Trigger strategy-specific processing
    config.strategies.forEach(strategyId => {
      this.triggerStrategyUpdate(strategyId, symbol, data);
    });
  }

  /**
   * Forward data to HFT engine with optimizations
   */
  forwardToHftEngine(symbol, data, metadata) {
    // Prepare HFT-optimized data package
    const hftData = {
      symbol,
      data: data.data,
      metadata: {
        ...metadata,
        processingTime: Date.now(),
        source: 'hft_integration'
      }
    };
    
    // Send to HFT engine with priority
    if (hftEngine && typeof hftEngine.processMarketData === 'function') {
      hftEngine.processMarketData(hftData);
    }
    
    // Update throughput metrics
    this.updateThroughputMetrics(data.data);
  }

  /**
   * Update symbol performance metrics
   */
  updateSymbolMetrics(symbol, latency, timestamp) {
    const metrics = this.symbolMetrics.get(symbol);
    if (!metrics) return;
    
    // Update latency statistics
    metrics.latencyStats.count++;
    metrics.latencyStats.min = Math.min(metrics.latencyStats.min, latency);
    metrics.latencyStats.max = Math.max(metrics.latencyStats.max, latency);
    metrics.latencyStats.avg = (metrics.latencyStats.avg * (metrics.latencyStats.count - 1) + latency) / metrics.latencyStats.count;
    
    // Update performance score based on latency and data quality
    const latencyScore = Math.max(0, 100 - (latency / this.config.maxAcceptableLatency) * 50);
    const freshnessScore = Math.max(0, 100 - (metrics.missedUpdates / 10) * 20);
    metrics.performanceScore = Math.round((latencyScore + freshnessScore) / 2);
    
    // Track overall latency for system health
    this.trackLatency(latency);
  }

  /**
   * Update data quality score for symbol
   */
  updateDataQualityScore(symbol, data) {
    const metrics = this.symbolMetrics.get(symbol);
    if (!metrics || !data.data) return;
    
    let qualityScore = 100;
    
    // Check for required fields
    const requiredFields = ['price', 'timestamp'];
    const missingFields = requiredFields.filter(field => !data.data[field]);
    qualityScore -= missingFields.length * 20;
    
    // Check for suspicious price movements (basic validation)
    if (metrics.lastPrice && data.data.price) {
      const priceChange = Math.abs(data.data.price - metrics.lastPrice) / metrics.lastPrice;
      if (priceChange > 0.1) { // 10% price change threshold
        qualityScore -= 10;
      }
    }
    
    // Update quality classification
    if (qualityScore >= 90) metrics.dataQuality = 'excellent';
    else if (qualityScore >= 70) metrics.dataQuality = 'good';
    else if (qualityScore >= 50) metrics.dataQuality = 'fair';
    else metrics.dataQuality = 'poor';
    
    metrics.lastPrice = data.data.price;
  }

  /**
   * Handle latency violations for HFT requirements
   */
  handleLatencyViolation(symbol, actualLatency, requiredLatency) {
    const violation = {
      symbol,
      actualLatency,
      requiredLatency,
      severity: actualLatency > requiredLatency * 2 ? 'critical' : 'warning',
      timestamp: Date.now()
    };
    
    // Emit latency violation event
    this.emit('latencyViolation', violation);
    
    // Take corrective actions for critical violations
    if (violation.severity === 'critical') {
      this.handleCriticalLatencyViolation(symbol, violation);
    }
  }

  /**
   * Handle critical latency violations
   */
  handleCriticalLatencyViolation(symbol, violation) {
    console.error(`🚨 Critical latency violation for HFT symbol ${symbol}:`, violation);
    
    // Temporarily disable symbol if too many violations
    const config = this.hftSymbols.get(symbol);
    if (config) {
      config.violationCount = (config.violationCount || 0) + 1;
      
      if (config.violationCount >= 5) {
        console.warn(`⚠️ Temporarily disabling HFT symbol ${symbol} due to repeated latency violations`);
        config.enabled = false;
        
        // Re-enable after cooldown period
        setTimeout(() => {
          config.enabled = true;
          config.violationCount = 0;
          console.log(`✅ Re-enabled HFT symbol ${symbol} after cooldown`);
        }, 30000); // 30 second cooldown
      }
    }
  }

  /**
   * Handle quota warnings that might affect HFT operations
   */
  handleQuotaWarning(warning) {
    console.warn(`⚠️ API quota warning might affect HFT operations:`, warning);
    
    // Reduce non-critical symbol subscriptions to preserve quota for HFT
    this.optimizeSubscriptionsForQuota();
  }

  /**
   * Handle quota emergency situations
   */
  handleQuotaEmergency(emergency) {
    console.error(`🚨 API quota emergency affecting HFT operations:`, emergency);
    
    // Emergency mode: keep only critical HFT symbols active
    this.activateEmergencyMode();
  }

  /**
   * Optimize subscriptions to preserve quota for HFT operations
   */
  optimizeSubscriptionsForQuota() {
    const allSubscriptions = liveDataService.getSubscriptions();
    const hftSymbolSet = new Set(this.hftSymbols.keys());
    
    // Identify non-HFT symbols to potentially unsubscribe
    const nonHftSymbols = allSubscriptions.filter(symbol => !hftSymbolSet.has(symbol));
    
    // Unsubscribe from lowest priority non-HFT symbols
    const symbolsToRemove = nonHftSymbols.slice(0, Math.ceil(nonHftSymbols.length * 0.3));
    if (symbolsToRemove.length > 0) {
      liveDataService.unsubscribe(symbolsToRemove);
      console.log(`📉 Temporarily unsubscribed from ${symbolsToRemove.length} non-HFT symbols to preserve quota`);
    }
  }

  /**
   * Activate emergency mode - keep only critical HFT symbols
   */
  activateEmergencyMode() {
    console.log('🚨 Activating HFT emergency mode - keeping only critical symbols');
    
    const allSubscriptions = liveDataService.getSubscriptions();
    const criticalSymbols = new Set();
    
    // Identify critical HFT symbols
    this.hftSymbols.forEach((config, symbol) => {
      if (config.priority === 'critical') {
        criticalSymbols.add(symbol);
      }
    });
    
    // Unsubscribe from all non-critical symbols
    const symbolsToRemove = allSubscriptions.filter(symbol => !criticalSymbols.has(symbol));
    if (symbolsToRemove.length > 0) {
      liveDataService.unsubscribe(symbolsToRemove);
    }
    
    console.log(`🔥 Emergency mode: keeping ${criticalSymbols.size} critical HFT symbols, removed ${symbolsToRemove.length} others`);
  }

  /**
   * Track system latency for health monitoring
   */
  trackLatency(latency) {
    this.latencyHistory.push({
      latency,
      timestamp: Date.now()
    });
    
    // Keep only last 100 measurements
    if (this.latencyHistory.length > 100) {
      this.latencyHistory.shift();
    }
    
    // Update connection health
    if (latency <= this.config.targetLatency) {
      this.connectionHealth.primary.healthy = true;
    } else if (latency > this.config.maxAcceptableLatency) {
      this.connectionHealth.primary.healthy = false;
    }
    
    this.connectionHealth.primary.latency = latency;
    this.connectionHealth.primary.lastCheck = Date.now();
  }

  /**
   * Update throughput metrics
   */
  updateThroughputMetrics(data) {
    if (!this.throughputWindow) {
      this.throughputWindow = {
        trades: 0,
        quotes: 0,
        messages: 0,
        windowStart: Date.now()
      };
    }
    
    this.throughputWindow.messages++;
    
    if (data.price && data.volume) {
      this.throughputWindow.trades++;
    } else if (data.bid || data.ask) {
      this.throughputWindow.quotes++;
    }
    
    // Reset window every second
    const now = Date.now();
    if (now - this.throughputWindow.windowStart >= 1000) {
      this.throughputMetrics = {
        messagesPerSecond: this.throughputWindow.messages,
        tradesPerSecond: this.throughputWindow.trades,
        quotesPerSecond: this.throughputWindow.quotes
      };
      
      this.throughputWindow = {
        trades: 0,
        quotes: 0,
        messages: 0,
        windowStart: now
      };
    }
  }

  /**
   * Start performance monitoring
   */
  startPerformanceMonitoring() {
    if (!this.config.enablePerformanceTracking) return;
    
    this.performanceInterval = setInterval(() => {
      this.collectPerformanceMetrics();
    }, this.config.performanceMetricsInterval);
  }

  /**
   * Collect comprehensive performance metrics
   */
  collectPerformanceMetrics() {
    const metrics = {
      timestamp: Date.now(),
      latency: this.getLatencyStats(),
      throughput: { ...this.throughputMetrics },
      symbols: {
        total: this.hftSymbols.size,
        active: Array.from(this.hftSymbols.values()).filter(c => c.enabled).length,
        byPriority: this.getSymbolsByPriority()
      },
      connectionHealth: { ...this.connectionHealth },
      dataQuality: this.getOverallDataQuality()
    };
    
    // Emit performance update
    this.emit('performanceUpdate', metrics);
    
    return metrics;
  }

  /**
   * Get latency statistics
   */
  getLatencyStats() {
    if (this.latencyHistory.length === 0) {
      return { min: 0, max: 0, avg: 0, p95: 0, p99: 0 };
    }
    
    const latencies = this.latencyHistory.map(h => h.latency).sort((a, b) => a - b);
    const count = latencies.length;
    
    return {
      min: latencies[0],
      max: latencies[count - 1],
      avg: latencies.reduce((sum, l) => sum + l, 0) / count,
      p95: latencies[Math.floor(count * 0.95)],
      p99: latencies[Math.floor(count * 0.99)]
    };
  }

  /**
   * Get symbols grouped by priority
   */
  getSymbolsByPriority() {
    const byPriority = { critical: 0, high: 0, standard: 0, low: 0 };
    
    this.hftSymbols.forEach(config => {
      byPriority[config.priority] = (byPriority[config.priority] || 0) + 1;
    });
    
    return byPriority;
  }

  /**
   * Get overall data quality assessment
   */
  getOverallDataQuality() {
    const qualities = Array.from(this.symbolMetrics.values()).map(m => m.dataQuality);
    const qualityCounts = qualities.reduce((counts, quality) => {
      counts[quality] = (counts[quality] || 0) + 1;
      return counts;
    }, {});
    
    return qualityCounts;
  }

  /**
   * Get HFT performance summary
   */
  getHftPerformanceSummary() {
    return {
      symbols: {
        total: this.hftSymbols.size,
        active: Array.from(this.hftSymbols.values()).filter(c => c.enabled).length,
        byPriority: this.getSymbolsByPriority()
      },
      performance: {
        latency: this.getLatencyStats(),
        throughput: this.throughputMetrics,
        dataQuality: this.getOverallDataQuality()
      },
      health: {
        connection: this.connectionHealth.primary.healthy,
        avgLatency: this.connectionHealth.primary.latency,
        systemScore: this.calculateSystemHealthScore()
      }
    };
  }

  /**
   * Calculate overall system health score
   */
  calculateSystemHealthScore() {
    let score = 100;
    
    // Latency penalty
    const avgLatency = this.getLatencyStats().avg;
    if (avgLatency > this.config.targetLatency) {
      score -= Math.min(50, (avgLatency - this.config.targetLatency) / this.config.targetLatency * 50);
    }
    
    // Connection health penalty
    if (!this.connectionHealth.primary.healthy) {
      score -= 30;
    }
    
    // Data quality penalty
    const qualityStats = this.getOverallDataQuality();
    const poorQualityCount = qualityStats.poor || 0;
    const totalSymbols = this.hftSymbols.size;
    if (totalSymbols > 0) {
      score -= (poorQualityCount / totalSymbols) * 20;
    }
    
    return Math.max(0, Math.round(score));
  }

  /**
   * Load HFT symbol configurations from storage/server
   */
  async loadHftSymbolConfigurations() {
    try {
      // Load from localStorage or server
      const savedConfig = localStorage.getItem('hft_symbol_config');
      if (savedConfig) {
        const config = JSON.parse(savedConfig);
        config.symbols?.forEach(symbolConfig => {
          this.addHftSymbol(symbolConfig.symbol, symbolConfig);
        });
      }
    } catch (error) {
      console.warn('Failed to load HFT symbol configurations:', error);
    }
  }

  /**
   * Save HFT symbol configurations
   */
  saveHftSymbolConfigurations() {
    try {
      const config = {
        symbols: Array.from(this.hftSymbols.entries()).map(([symbol, config]) => ({
          symbol,
          ...config
        })),
        timestamp: Date.now()
      };
      
      localStorage.setItem('hft_symbol_config', JSON.stringify(config));
    } catch (error) {
      console.warn('Failed to save HFT symbol configurations:', error);
    }
  }

  /**
   * Cleanup resources
   */
  cleanup() {
    if (this.performanceInterval) {
      clearInterval(this.performanceInterval);
      this.performanceInterval = null;
    }
    
    // Remove all symbol listeners
    this.hftSymbols.forEach((config, symbol) => {
      if (config.dataHandler) {
        liveDataService.off(`marketData:${symbol}`, config.dataHandler);
      }
    });
    
    // Save configurations before cleanup
    this.saveHftSymbolConfigurations();
  }
}

// Inherit from EventEmitter
Object.setPrototypeOf(HFTLiveDataIntegration.prototype, require('events').EventEmitter.prototype);

// Create singleton instance
const hftLiveDataIntegration = new HFTLiveDataIntegration();

// Cleanup on page unload
if (typeof window !== 'undefined') {
  window.addEventListener('beforeunload', () => {
    hftLiveDataIntegration.cleanup();
  });
}

export default hftLiveDataIntegration;
export { HFTLiveDataIntegration };
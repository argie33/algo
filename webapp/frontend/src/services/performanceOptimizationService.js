/**
 * Frontend Performance Optimization Service
 * Provides advanced performance monitoring and optimization for trading interface
 */

class PerformanceOptimizationService {
  constructor() {
    this.metrics = {
      renderTimes: [],
      apiResponseTimes: [],
      memoryUsage: [],
      networkRequests: [],
      userInteractions: []
    };
    
    this.optimizations = {
      dataBuffering: new Map(),
      requestDeduplication: new Map(),
      componentCaching: new Map(),
      virtualScrolling: new Map()
    };
    
    this.thresholds = {
      slowRender: 100, // ms
      slowApiResponse: 500, // ms
      highMemoryUsage: 100 * 1024 * 1024, // 100MB
      maxBufferSize: 1000,
      maxCacheSize: 50
    };
    
    this.initialize();
  }

  /**
   * Initialize performance monitoring
   */
  initialize() {
    this.startPerformanceMonitoring();
    this.setupDataBuffering();
    this.setupRequestDeduplication();
    this.setupComponentCaching();
    this.setupVirtualScrolling();
  }

  /**
   * Start comprehensive performance monitoring
   */
  startPerformanceMonitoring() {
    // Monitor render performance
    this.setupRenderMonitoring();
    
    // Monitor API performance
    this.setupApiMonitoring();
    
    // Monitor memory usage
    this.setupMemoryMonitoring();
    
    // Monitor user interactions
    this.setupUserInteractionMonitoring();
    
    // Setup periodic reporting
    setInterval(() => this.reportPerformanceMetrics(), 30000); // Every 30 seconds
  }

  /**
   * Setup render performance monitoring
   */
  setupRenderMonitoring() {
    const observer = new PerformanceObserver((list) => {
      list.getEntries().forEach((entry) => {
        if (entry.entryType === 'measure') {
          this.metrics.renderTimes.push({
            name: entry.name,
            duration: entry.duration,
            timestamp: Date.now()
          });
          
          // Alert on slow renders
          if (entry.duration > this.thresholds.slowRender) {
            this.handleSlowRender(entry);
          }
        }
      });
    });
    
    observer.observe({ entryTypes: ['measure'] });
  }

  /**
   * Setup API performance monitoring
   */
  setupApiMonitoring() {
    const originalFetch = window.fetch;
    
    window.fetch = async (url, options) => {
      const startTime = performance.now();
      
      try {
        const response = await originalFetch(url, options);
        const endTime = performance.now();
        const duration = endTime - startTime;
        
        this.metrics.apiResponseTimes.push({
          url,
          duration,
          status: response.status,
          timestamp: Date.now()
        });
        
        // Alert on slow API responses
        if (duration > this.thresholds.slowApiResponse) {
          this.handleSlowApiResponse(url, duration);
        }
        
        return response;
      } catch (error) {
        const endTime = performance.now();
        const duration = endTime - startTime;
        
        this.metrics.apiResponseTimes.push({
          url,
          duration,
          status: 'error',
          error: error.message,
          timestamp: Date.now()
        });
        
        throw error;
      }
    };
  }

  /**
   * Setup memory usage monitoring
   */
  setupMemoryMonitoring() {
    if (performance.memory) {
      setInterval(() => {
        const memoryInfo = {
          usedJSHeapSize: performance.memory.usedJSHeapSize,
          totalJSHeapSize: performance.memory.totalJSHeapSize,
          jsHeapSizeLimit: performance.memory.jsHeapSizeLimit,
          timestamp: Date.now()
        };
        
        this.metrics.memoryUsage.push(memoryInfo);
        
        // Alert on high memory usage
        if (memoryInfo.usedJSHeapSize > this.thresholds.highMemoryUsage) {
          this.handleHighMemoryUsage(memoryInfo);
        }
        
        // Keep only last 100 entries
        if (this.metrics.memoryUsage.length > 100) {
          this.metrics.memoryUsage = this.metrics.memoryUsage.slice(-100);
        }
      }, 5000); // Every 5 seconds
    }
  }

  /**
   * Setup user interaction monitoring
   */
  setupUserInteractionMonitoring() {
    const interactionTypes = ['click', 'scroll', 'resize', 'keydown'];
    
    interactionTypes.forEach(type => {
      let lastTime = 0;
      
      window.addEventListener(type, (event) => {
        const currentTime = Date.now();
        const timeSinceLastInteraction = currentTime - lastTime;
        
        this.metrics.userInteractions.push({
          type,
          timestamp: currentTime,
          timeSinceLastInteraction,
          target: event.target.tagName
        });
        
        lastTime = currentTime;
        
        // Keep only last 1000 interactions
        if (this.metrics.userInteractions.length > 1000) {
          this.metrics.userInteractions = this.metrics.userInteractions.slice(-1000);
        }
      });
    });
  }

  /**
   * Setup intelligent data buffering for real-time updates
   */
  setupDataBuffering() {
    this.dataBuffer = {
      priceUpdates: new Map(),
      portfolioUpdates: new Map(),
      newsUpdates: new Map()
    };
    
    // Flush buffers periodically
    setInterval(() => this.flushDataBuffers(), 1000); // Every second
  }

  /**
   * Setup request deduplication
   */
  setupRequestDeduplication() {
    this.pendingRequests = new Map();
    this.requestCache = new Map();
    
    // Clean up old cache entries
    setInterval(() => this.cleanupRequestCache(), 60000); // Every minute
  }

  /**
   * Setup component caching
   */
  setupComponentCaching() {
    this.componentCache = new Map();
    
    // Clean up old cache entries
    setInterval(() => this.cleanupComponentCache(), 120000); // Every 2 minutes
  }

  /**
   * Setup virtual scrolling optimization
   */
  setupVirtualScrolling() {
    this.virtualScrollConfigs = new Map();
  }

  /**
   * Optimize data updates with intelligent buffering
   */
  bufferDataUpdate(type, key, data) {
    if (!this.dataBuffer[type]) {
      this.dataBuffer[type] = new Map();
    }
    
    this.dataBuffer[type].set(key, {
      data,
      timestamp: Date.now()
    });
    
    // Prevent buffer overflow
    if (this.dataBuffer[type].size > this.thresholds.maxBufferSize) {
      const oldestKey = this.dataBuffer[type].keys().next().value;
      this.dataBuffer[type].delete(oldestKey);
    }
  }

  /**
   * Flush data buffers and trigger updates
   */
  flushDataBuffers() {
    Object.keys(this.dataBuffer).forEach(type => {
      if (this.dataBuffer[type].size > 0) {
        const updates = Array.from(this.dataBuffer[type].entries());
        this.dataBuffer[type].clear();
        
        // Trigger batch update
        this.triggerBatchUpdate(type, updates);
      }
    });
  }

  /**
   * Trigger batch update for optimized rendering
   */
  triggerBatchUpdate(type, updates) {
    // Use requestAnimationFrame for optimal timing
    requestAnimationFrame(() => {
      const event = new CustomEvent('optimizedDataUpdate', {
        detail: {
          type,
          updates,
          timestamp: Date.now()
        }
      });
      
      window.dispatchEvent(event);
    });
  }

  /**
   * Deduplicate API requests
   */
  async deduplicateRequest(url, options = {}) {
    const requestKey = `${url}_${JSON.stringify(options)}`;
    
    // Check if request is already pending
    if (this.pendingRequests.has(requestKey)) {
      return this.pendingRequests.get(requestKey);
    }
    
    // Check cache
    if (this.requestCache.has(requestKey)) {
      const cached = this.requestCache.get(requestKey);
      if (Date.now() - cached.timestamp < 30000) { // 30 second cache
        return cached.data;
      }
    }
    
    // Make request
    const requestPromise = fetch(url, options)
      .then(response => response.json())
      .then(data => {
        this.requestCache.set(requestKey, {
          data,
          timestamp: Date.now()
        });
        
        this.pendingRequests.delete(requestKey);
        return data;
      })
      .catch(error => {
        this.pendingRequests.delete(requestKey);
        throw error;
      });
    
    this.pendingRequests.set(requestKey, requestPromise);
    return requestPromise;
  }

  /**
   * Cache component render results
   */
  cacheComponentRender(componentKey, props, renderFunction) {
    const cacheKey = `${componentKey}_${JSON.stringify(props)}`;
    
    if (this.componentCache.has(cacheKey)) {
      const cached = this.componentCache.get(cacheKey);
      if (Date.now() - cached.timestamp < 60000) { // 1 minute cache
        return cached.result;
      }
    }
    
    const result = renderFunction();
    this.componentCache.set(cacheKey, {
      result,
      timestamp: Date.now()
    });
    
    return result;
  }

  /**
   * Setup virtual scrolling for large datasets
   */
  setupVirtualScrollingForComponent(componentId, config) {
    this.virtualScrollConfigs.set(componentId, {
      itemHeight: config.itemHeight || 50,
      containerHeight: config.containerHeight || 400,
      overscan: config.overscan || 10,
      ...config
    });
  }

  /**
   * Calculate virtual scroll parameters
   */
  calculateVirtualScrollParams(componentId, scrollTop, totalItems) {
    const config = this.virtualScrollConfigs.get(componentId);
    if (!config) return null;
    
    const startIndex = Math.floor(scrollTop / config.itemHeight);
    const endIndex = Math.min(
      startIndex + Math.ceil(config.containerHeight / config.itemHeight) + config.overscan,
      totalItems
    );
    
    return {
      startIndex: Math.max(0, startIndex - config.overscan),
      endIndex,
      offsetY: startIndex * config.itemHeight,
      totalHeight: totalItems * config.itemHeight
    };
  }

  /**
   * Handle slow render performance
   */
  handleSlowRender(entry) {
    console.warn('Slow render detected:', entry.name, entry.duration);
    
    // Log to analytics
    this.logPerformanceIssue('slow_render', {
      component: entry.name,
      duration: entry.duration,
      timestamp: Date.now()
    });
    
    // Suggest optimizations
    this.suggestRenderOptimizations(entry);
  }

  /**
   * Handle slow API response
   */
  handleSlowApiResponse(url, duration) {
    console.warn('Slow API response detected:', url, duration);
    
    // Log to analytics
    this.logPerformanceIssue('slow_api_response', {
      url,
      duration,
      timestamp: Date.now()
    });
    
    // Suggest optimizations
    this.suggestApiOptimizations(url, duration);
  }

  /**
   * Handle high memory usage
   */
  handleHighMemoryUsage(memoryInfo) {
    console.warn('High memory usage detected:', memoryInfo);
    
    // Log to analytics
    this.logPerformanceIssue('high_memory_usage', {
      memoryInfo,
      timestamp: Date.now()
    });
    
    // Trigger cleanup
    this.triggerMemoryCleanup();
  }

  /**
   * Suggest render optimizations
   */
  suggestRenderOptimizations(entry) {
    const optimizations = [];
    
    if (entry.duration > 200) {
      optimizations.push('Consider implementing React.memo() or useMemo()');
      optimizations.push('Check for unnecessary re-renders');
      optimizations.push('Implement virtual scrolling for large lists');
    }
    
    if (entry.duration > 500) {
      optimizations.push('Consider code splitting and lazy loading');
      optimizations.push('Move heavy computations to Web Workers');
    }
    
    return optimizations;
  }

  /**
   * Suggest API optimizations
   */
  suggestApiOptimizations(url, duration) {
    const optimizations = [];
    
    if (duration > 1000) {
      optimizations.push('Consider implementing request caching');
      optimizations.push('Use request deduplication');
      optimizations.push('Implement progressive loading');
    }
    
    if (duration > 2000) {
      optimizations.push('Consider optimizing backend queries');
      optimizations.push('Implement request batching');
      optimizations.push('Use WebSocket for real-time updates');
    }
    
    return optimizations;
  }

  /**
   * Trigger memory cleanup
   */
  triggerMemoryCleanup() {
    // Clear old cache entries
    this.cleanupRequestCache();
    this.cleanupComponentCache();
    
    // Clear old metrics
    this.metrics.renderTimes = this.metrics.renderTimes.slice(-100);
    this.metrics.apiResponseTimes = this.metrics.apiResponseTimes.slice(-100);
    this.metrics.userInteractions = this.metrics.userInteractions.slice(-100);
    
    // Trigger garbage collection if available
    if (window.gc) {
      window.gc();
    }
  }

  /**
   * Clean up request cache
   */
  cleanupRequestCache() {
    const now = Date.now();
    for (const [key, value] of this.requestCache.entries()) {
      if (now - value.timestamp > 300000) { // 5 minutes
        this.requestCache.delete(key);
      }
    }
  }

  /**
   * Clean up component cache
   */
  cleanupComponentCache() {
    const now = Date.now();
    for (const [key, value] of this.componentCache.entries()) {
      if (now - value.timestamp > 300000) { // 5 minutes
        this.componentCache.delete(key);
      }
    }
  }

  /**
   * Log performance issues
   */
  logPerformanceIssue(type, details) {
    // Send to analytics service
    if (window.gtag) {
      window.gtag('event', 'performance_issue', {
        event_category: 'performance',
        event_label: type,
        value: details.duration || details.memoryInfo?.usedJSHeapSize || 0
      });
    }
    
    // Log to console in development
    if (process.env.NODE_ENV === 'development') {
      console.log('Performance Issue:', type, details);
    }
  }

  /**
   * Report performance metrics
   */
  reportPerformanceMetrics() {
    const report = {
      timestamp: Date.now(),
      metrics: {
        averageRenderTime: this.calculateAverageRenderTime(),
        averageApiResponseTime: this.calculateAverageApiResponseTime(),
        memoryUsage: this.getCurrentMemoryUsage(),
        userInteractionFrequency: this.calculateUserInteractionFrequency()
      },
      optimizations: {
        cacheHitRate: this.calculateCacheHitRate(),
        bufferUtilization: this.calculateBufferUtilization(),
        memoryOptimizations: this.getMemoryOptimizations()
      }
    };
    
    // Send to analytics
    this.sendAnalytics('performance_report', report);
    
    return report;
  }

  /**
   * Calculate average render time
   */
  calculateAverageRenderTime() {
    if (this.metrics.renderTimes.length === 0) return 0;
    
    const total = this.metrics.renderTimes.reduce((sum, entry) => sum + entry.duration, 0);
    return total / this.metrics.renderTimes.length;
  }

  /**
   * Calculate average API response time
   */
  calculateAverageApiResponseTime() {
    if (this.metrics.apiResponseTimes.length === 0) return 0;
    
    const total = this.metrics.apiResponseTimes.reduce((sum, entry) => sum + entry.duration, 0);
    return total / this.metrics.apiResponseTimes.length;
  }

  /**
   * Get current memory usage
   */
  getCurrentMemoryUsage() {
    if (performance.memory) {
      return {
        usedJSHeapSize: performance.memory.usedJSHeapSize,
        totalJSHeapSize: performance.memory.totalJSHeapSize,
        jsHeapSizeLimit: performance.memory.jsHeapSizeLimit
      };
    }
    return null;
  }

  /**
   * Calculate user interaction frequency
   */
  calculateUserInteractionFrequency() {
    if (this.metrics.userInteractions.length === 0) return 0;
    
    const recentInteractions = this.metrics.userInteractions.filter(
      interaction => Date.now() - interaction.timestamp < 60000 // Last minute
    );
    
    return recentInteractions.length;
  }

  /**
   * Calculate cache hit rate
   */
  calculateCacheHitRate() {
    const totalRequests = this.metrics.apiResponseTimes.length;
    const cacheHits = this.requestCache.size;
    
    return totalRequests > 0 ? cacheHits / totalRequests : 0;
  }

  /**
   * Calculate buffer utilization
   */
  calculateBufferUtilization() {
    let totalBufferSize = 0;
    let totalMaxSize = 0;
    
    Object.values(this.dataBuffer).forEach(buffer => {
      totalBufferSize += buffer.size;
      totalMaxSize += this.thresholds.maxBufferSize;
    });
    
    return totalMaxSize > 0 ? totalBufferSize / totalMaxSize : 0;
  }

  /**
   * Get memory optimization suggestions
   */
  getMemoryOptimizations() {
    const optimizations = [];
    
    if (this.requestCache.size > 50) {
      optimizations.push('Consider reducing request cache size');
    }
    
    if (this.componentCache.size > 20) {
      optimizations.push('Consider reducing component cache size');
    }
    
    return optimizations;
  }

  /**
   * Send analytics data
   */
  sendAnalytics(event, data) {
    // Send to analytics service
    if (window.gtag) {
      window.gtag('event', event, {
        event_category: 'performance',
        custom_parameters: data
      });
    }
    
    // Send to custom analytics endpoint
    if (window.fetch) {
      fetch('/api/analytics/performance', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          event,
          data,
          timestamp: Date.now()
        })
      }).catch(error => {
        console.warn('Failed to send analytics:', error);
      });
    }
  }

  /**
   * Get performance optimization recommendations
   */
  getOptimizationRecommendations() {
    const recommendations = [];
    
    // Render performance
    const avgRenderTime = this.calculateAverageRenderTime();
    if (avgRenderTime > this.thresholds.slowRender) {
      recommendations.push({
        type: 'render',
        severity: avgRenderTime > 200 ? 'high' : 'medium',
        description: `Average render time is ${avgRenderTime.toFixed(1)}ms`,
        suggestions: this.suggestRenderOptimizations({ duration: avgRenderTime })
      });
    }
    
    // API performance
    const avgApiTime = this.calculateAverageApiResponseTime();
    if (avgApiTime > this.thresholds.slowApiResponse) {
      recommendations.push({
        type: 'api',
        severity: avgApiTime > 1000 ? 'high' : 'medium',
        description: `Average API response time is ${avgApiTime.toFixed(1)}ms`,
        suggestions: this.suggestApiOptimizations('', avgApiTime)
      });
    }
    
    // Memory usage
    const memoryUsage = this.getCurrentMemoryUsage();
    if (memoryUsage && memoryUsage.usedJSHeapSize > this.thresholds.highMemoryUsage) {
      recommendations.push({
        type: 'memory',
        severity: 'high',
        description: `Memory usage is ${(memoryUsage.usedJSHeapSize / 1024 / 1024).toFixed(1)}MB`,
        suggestions: ['Consider implementing memory cleanup', 'Reduce cache sizes', 'Use lazy loading']
      });
    }
    
    return recommendations;
  }
}

// Create singleton instance
const performanceOptimizationService = new PerformanceOptimizationService();

export default performanceOptimizationService;
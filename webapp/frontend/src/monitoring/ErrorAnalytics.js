/**
 * ErrorAnalytics - Comprehensive error monitoring and analytics system
 * Provides real-time error tracking, pattern analysis, and performance monitoring
 */

import ErrorManager from '../error/ErrorManager';

class ErrorAnalytics {
  constructor() {
    this.metrics = {
      errors: new Map(),
      performance: new Map(),
      users: new Map(),
      sessions: new Map(),
      components: new Map(),
      apis: new Map()
    };
    
    this.realTimeData = {
      errorRate: 0,
      responseTime: 0,
      userSatisfaction: 0,
      systemHealth: 100
    };

    this.thresholds = {
      errorRateWarning: 5, // 5%
      errorRateCritical: 10, // 10%
      responseTimeWarning: 2000, // 2s
      responseTimeCritical: 5000, // 5s
      userSatisfactionWarning: 70, // 70%
      userSatisfactionCritical: 50 // 50%
    };

    this.alerts = [];
    this.isMonitoring = false;
    this.monitoringInterval = null;
  }

  /**
   * Initialize analytics monitoring
   */
  initialize() {
    if (this.isMonitoring) return;

    // Subscribe to error manager
    this.unsubscribe = ErrorManager.subscribe((error) => {
      this.processError(error);
    });

    // Start real-time monitoring
    this.startRealTimeMonitoring();

    // Setup performance observers
    this.setupPerformanceObservers();

    // Setup user behavior tracking
    this.setupUserBehaviorTracking();

    this.isMonitoring = true;
    console.log('📊 Error Analytics initialized');
  }

  /**
   * Process incoming errors for analytics
   */
  processError(error) {
    const timestamp = Date.now();
    const hour = new Date().getHours();
    const errorKey = `${error.category}:${error.type}`;

    // Update error metrics
    this.updateErrorMetrics(errorKey, error, timestamp);

    // Update component metrics if applicable
    if (error.context?.componentName) {
      this.updateComponentMetrics(error.context.componentName, error, timestamp);
    }

    // Update API metrics if applicable
    if (error.context?.operation) {
      this.updateApiMetrics(error.context.operation, error, timestamp);
    }

    // Update user metrics
    this.updateUserMetrics(error.context?.userId || 'anonymous', error, timestamp);

    // Update session metrics
    this.updateSessionMetrics(error.context?.sessionId || 'unknown', error, timestamp);

    // Check for alert conditions
    this.checkAlertConditions(error);

    // Update real-time metrics
    this.updateRealTimeMetrics();
  }

  /**
   * Update error metrics
   */
  updateErrorMetrics(errorKey, error, timestamp) {
    if (!this.metrics.errors.has(errorKey)) {
      this.metrics.errors.set(errorKey, {
        count: 0,
        firstSeen: timestamp,
        lastSeen: timestamp,
        severity: error.severity,
        category: error.category,
        type: error.type,
        hourlyCount: new Array(24).fill(0),
        userCount: new Set(),
        affectedComponents: new Set(),
        contexts: []
      });
    }

    const metric = this.metrics.errors.get(errorKey);
    metric.count++;
    metric.lastSeen = timestamp;
    metric.hourlyCount[new Date().getHours()]++;
    
    if (error.context?.userId) {
      metric.userCount.add(error.context.userId);
    }
    
    if (error.context?.componentName) {
      metric.affectedComponents.add(error.context.componentName);
    }

    // Store recent contexts (last 10)
    metric.contexts.push({
      timestamp,
      context: error.context,
      message: error.message
    });
    if (metric.contexts.length > 10) {
      metric.contexts.shift();
    }
  }

  /**
   * Update component metrics
   */
  updateComponentMetrics(componentName, error, timestamp) {
    if (!this.metrics.components.has(componentName)) {
      this.metrics.components.set(componentName, {
        errorCount: 0,
        lastError: null,
        errorTypes: new Map(),
        averageRenderTime: 0,
        mountCount: 0,
        unmountCount: 0,
        renderCount: 0,
        healthScore: 100
      });
    }

    const metric = this.metrics.components.get(componentName);
    metric.errorCount++;
    metric.lastError = timestamp;
    
    const errorType = error.type;
    metric.errorTypes.set(errorType, (metric.errorTypes.get(errorType) || 0) + 1);

    // Calculate health score
    metric.healthScore = Math.max(0, 100 - (metric.errorCount * 5));
  }

  /**
   * Update API metrics
   */
  updateApiMetrics(operation, error, timestamp) {
    if (!this.metrics.apis.has(operation)) {
      this.metrics.apis.set(operation, {
        requestCount: 0,
        errorCount: 0,
        successCount: 0,
        averageResponseTime: 0,
        errorRate: 0,
        lastError: null,
        statusCodes: new Map(),
        errorTypes: new Map()
      });
    }

    const metric = this.metrics.apis.get(operation);
    metric.requestCount++;
    metric.errorCount++;
    metric.lastError = timestamp;
    metric.errorRate = (metric.errorCount / metric.requestCount) * 100;

    if (error.context?.status) {
      const status = error.context.status;
      metric.statusCodes.set(status, (metric.statusCodes.get(status) || 0) + 1);
    }

    const errorType = error.type;
    metric.errorTypes.set(errorType, (metric.errorTypes.get(errorType) || 0) + 1);

    // Update response time if available
    if (error.context?.duration) {
      const currentAvg = metric.averageResponseTime || 0;
      metric.averageResponseTime = (currentAvg + error.context.duration) / 2;
    }
  }

  /**
   * Update user metrics
   */
  updateUserMetrics(userId, error, timestamp) {
    if (!this.metrics.users.has(userId)) {
      this.metrics.users.set(userId, {
        errorCount: 0,
        firstError: timestamp,
        lastError: timestamp,
        errorTypes: new Map(),
        affectedFeatures: new Set(),
        userAgent: error.context?.userAgent || 'unknown',
        satisfactionScore: 100
      });
    }

    const metric = this.metrics.users.get(userId);
    metric.errorCount++;
    metric.lastError = timestamp;
    
    const errorType = error.type;
    metric.errorTypes.set(errorType, (metric.errorTypes.get(errorType) || 0) + 1);

    if (error.context?.operation) {
      metric.affectedFeatures.add(error.context.operation);
    }

    // Calculate satisfaction score
    metric.satisfactionScore = Math.max(0, 100 - (metric.errorCount * 3));
  }

  /**
   * Update session metrics
   */
  updateSessionMetrics(sessionId, error, timestamp) {
    if (!this.metrics.sessions.has(sessionId)) {
      this.metrics.sessions.set(sessionId, {
        startTime: timestamp,
        errorCount: 0,
        lastActivity: timestamp,
        errorTypes: new Map(),
        duration: 0,
        quality: 100
      });
    }

    const metric = this.metrics.sessions.get(sessionId);
    metric.errorCount++;
    metric.lastActivity = timestamp;
    metric.duration = timestamp - metric.startTime;
    
    const errorType = error.type;
    metric.errorTypes.set(errorType, (metric.errorTypes.get(errorType) || 0) + 1);

    // Calculate session quality
    metric.quality = Math.max(0, 100 - (metric.errorCount * 4));
  }

  /**
   * Start real-time monitoring
   */
  startRealTimeMonitoring() {
    this.monitoringInterval = setInterval(() => {
      this.updateRealTimeMetrics();
      this.detectAnomalies();
      this.cleanOldData();
    }, 5000); // Update every 5 seconds
  }

  /**
   * Update real-time metrics
   */
  updateRealTimeMetrics() {
    const now = Date.now();
    const oneHourAgo = now - (60 * 60 * 1000);

    // Calculate error rate
    let totalErrors = 0;
    let totalRequests = 0;
    
    for (const [, apiMetric] of this.metrics.apis) {
      totalErrors += apiMetric.errorCount;
      totalRequests += apiMetric.requestCount;
    }
    
    this.realTimeData.errorRate = totalRequests > 0 ? (totalErrors / totalRequests) * 100 : 0;

    // Calculate average response time
    let totalResponseTime = 0;
    let apiCount = 0;
    
    for (const [, apiMetric] of this.metrics.apis) {
      if (apiMetric.averageResponseTime > 0) {
        totalResponseTime += apiMetric.averageResponseTime;
        apiCount++;
      }
    }
    
    this.realTimeData.responseTime = apiCount > 0 ? totalResponseTime / apiCount : 0;

    // Calculate user satisfaction
    let totalSatisfaction = 0;
    let userCount = 0;
    
    for (const [, userMetric] of this.metrics.users) {
      totalSatisfaction += userMetric.satisfactionScore;
      userCount++;
    }
    
    this.realTimeData.userSatisfaction = userCount > 0 ? totalSatisfaction / userCount : 100;

    // Calculate system health
    const errorRateHealth = Math.max(0, 100 - (this.realTimeData.errorRate * 10));
    const responseTimeHealth = Math.max(0, 100 - (this.realTimeData.responseTime / 50));
    const satisfactionHealth = this.realTimeData.userSatisfaction;
    
    this.realTimeData.systemHealth = (errorRateHealth + responseTimeHealth + satisfactionHealth) / 3;
  }

  /**
   * Check for alert conditions
   */
  checkAlertConditions(error) {
    const now = Date.now();

    // Critical error severity
    if (error.severity === ErrorManager.SEVERITY.CRITICAL) {
      this.createAlert({
        type: 'critical_error',
        severity: 'critical',
        message: `Critical error detected: ${error.message}`,
        timestamp: now,
        context: error.context
      });
    }

    // High error rate
    if (this.realTimeData.errorRate > this.thresholds.errorRateCritical) {
      this.createAlert({
        type: 'high_error_rate',
        severity: 'critical',
        message: `Error rate is critically high: ${this.realTimeData.errorRate.toFixed(2)}%`,
        timestamp: now,
        context: { errorRate: this.realTimeData.errorRate }
      });
    }

    // Slow response time
    if (this.realTimeData.responseTime > this.thresholds.responseTimeCritical) {
      this.createAlert({
        type: 'slow_response',
        severity: 'critical',
        message: `Response time is critically slow: ${this.realTimeData.responseTime.toFixed(0)}ms`,
        timestamp: now,
        context: { responseTime: this.realTimeData.responseTime }
      });
    }

    // Low user satisfaction
    if (this.realTimeData.userSatisfaction < this.thresholds.userSatisfactionCritical) {
      this.createAlert({
        type: 'low_satisfaction',
        severity: 'warning',
        message: `User satisfaction is low: ${this.realTimeData.userSatisfaction.toFixed(1)}%`,
        timestamp: now,
        context: { userSatisfaction: this.realTimeData.userSatisfaction }
      });
    }
  }

  /**
   * Create alert
   */
  createAlert(alert) {
    this.alerts.unshift({
      ...alert,
      id: `alert_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
    });

    // Keep only last 50 alerts
    if (this.alerts.length > 50) {
      this.alerts = this.alerts.slice(0, 50);
    }

    // Log alert
    console.warn('🚨 ALERT:', alert);
  }

  /**
   * Detect anomalies in error patterns
   */
  detectAnomalies() {
    const now = Date.now();
    const oneHourAgo = now - (60 * 60 * 1000);

    // Check for error spikes
    for (const [errorKey, metric] of this.metrics.errors) {
      const recentErrors = metric.contexts.filter(ctx => ctx.timestamp > oneHourAgo);
      
      if (recentErrors.length > 10) {
        this.createAlert({
          type: 'error_spike',
          severity: 'warning',
          message: `Error spike detected for ${errorKey}: ${recentErrors.length} errors in last hour`,
          timestamp: now,
          context: { errorKey, recentCount: recentErrors.length }
        });
      }
    }

    // Check for new error types
    for (const [errorKey, metric] of this.metrics.errors) {
      const timeSinceFirst = now - metric.firstSeen;
      
      if (timeSinceFirst < 5 * 60 * 1000 && metric.count > 1) { // New error in last 5 minutes
        this.createAlert({
          type: 'new_error_type',
          severity: 'info',
          message: `New error type detected: ${errorKey}`,
          timestamp: now,
          context: { errorKey, count: metric.count }
        });
      }
    }
  }

  /**
   * Setup performance observers
   */
  setupPerformanceObservers() {
    if (typeof window !== 'undefined' && 'PerformanceObserver' in window) {
      // Largest Contentful Paint
      try {
        const lcpObserver = new PerformanceObserver((list) => {
          for (const entry of list.getEntries()) {
            if (entry.entryType === 'largest-contentful-paint') {
              this.trackPerformanceMetric('lcp', entry.startTime);
            }
          }
        });
        lcpObserver.observe({ type: 'largest-contentful-paint', buffered: true });
      } catch (e) { /* Observer not supported */ }

      // First Input Delay
      try {
        const fidObserver = new PerformanceObserver((list) => {
          for (const entry of list.getEntries()) {
            if (entry.entryType === 'first-input') {
              this.trackPerformanceMetric('fid', entry.processingStart - entry.startTime);
            }
          }
        });
        fidObserver.observe({ type: 'first-input', buffered: true });
      } catch (e) { /* Observer not supported */ }

      // Cumulative Layout Shift
      try {
        const clsObserver = new PerformanceObserver((list) => {
          for (const entry of list.getEntries()) {
            if (entry.entryType === 'layout-shift' && !entry.hadRecentInput) {
              this.trackPerformanceMetric('cls', entry.value);
            }
          }
        });
        clsObserver.observe({ type: 'layout-shift', buffered: true });
      } catch (e) { /* Observer not supported */ }
    }
  }

  /**
   * Track performance metric
   */
  trackPerformanceMetric(metric, value) {
    if (!this.metrics.performance.has(metric)) {
      this.metrics.performance.set(metric, {
        values: [],
        average: 0,
        min: Infinity,
        max: 0,
        count: 0
      });
    }

    const perfMetric = this.metrics.performance.get(metric);
    perfMetric.values.push({ value, timestamp: Date.now() });
    perfMetric.count++;
    perfMetric.min = Math.min(perfMetric.min, value);
    perfMetric.max = Math.max(perfMetric.max, value);
    perfMetric.average = perfMetric.values.reduce((sum, v) => sum + v.value, 0) / perfMetric.count;

    // Keep only last 100 values
    if (perfMetric.values.length > 100) {
      perfMetric.values.shift();
    }

    // Check for performance issues
    this.checkPerformanceThresholds(metric, value);
  }

  /**
   * Check performance thresholds
   */
  checkPerformanceThresholds(metric, value) {
    const thresholds = {
      lcp: { warning: 2500, critical: 4000 },
      fid: { warning: 100, critical: 300 },
      cls: { warning: 0.1, critical: 0.25 }
    };

    const threshold = thresholds[metric];
    if (!threshold) return;

    if (value > threshold.critical) {
      this.createAlert({
        type: 'performance_critical',
        severity: 'critical',
        message: `Critical performance issue: ${metric.toUpperCase()} is ${value}`,
        timestamp: Date.now(),
        context: { metric, value, threshold: threshold.critical }
      });
    } else if (value > threshold.warning) {
      this.createAlert({
        type: 'performance_warning',
        severity: 'warning',
        message: `Performance warning: ${metric.toUpperCase()} is ${value}`,
        timestamp: Date.now(),
        context: { metric, value, threshold: threshold.warning }
      });
    }
  }

  /**
   * Setup user behavior tracking
   */
  setupUserBehaviorTracking() {
    if (typeof window !== 'undefined') {
      // Track page visibility changes
      document.addEventListener('visibilitychange', () => {
        if (document.hidden) {
          this.trackUserBehavior('page_hidden');
        } else {
          this.trackUserBehavior('page_visible');
        }
      });

      // Track user interactions
      ['click', 'keydown', 'scroll'].forEach(eventType => {
        document.addEventListener(eventType, () => {
          this.trackUserBehavior(eventType);
        }, { passive: true });
      });
    }
  }

  /**
   * Track user behavior
   */
  trackUserBehavior(action) {
    const userId = localStorage.getItem('user_id') || 'anonymous';
    const sessionId = sessionStorage.getItem('session_id') || 'unknown';

    ErrorManager.handleError({
      type: 'user_behavior',
      message: `User action: ${action}`,
      category: ErrorManager.CATEGORIES.UI,
      severity: ErrorManager.SEVERITY.LOW,
      context: {
        action,
        userId,
        sessionId,
        timestamp: Date.now(),
        url: window.location.href
      }
    });
  }

  /**
   * Clean old data
   */
  cleanOldData() {
    const now = Date.now();
    const oneWeekAgo = now - (7 * 24 * 60 * 60 * 1000);

    // Clean old error contexts
    for (const [, metric] of this.metrics.errors) {
      metric.contexts = metric.contexts.filter(ctx => ctx.timestamp > oneWeekAgo);
    }

    // Clean old performance data
    for (const [, metric] of this.metrics.performance) {
      metric.values = metric.values.filter(v => v.timestamp > oneWeekAgo);
    }
  }

  /**
   * Get analytics dashboard data
   */
  getDashboardData() {
    return {
      realTime: this.realTimeData,
      alerts: this.alerts.slice(0, 10),
      topErrors: this.getTopErrors(),
      componentHealth: this.getComponentHealth(),
      apiHealth: this.getApiHealth(),
      userMetrics: this.getUserMetrics(),
      performanceMetrics: this.getPerformanceMetrics()
    };
  }

  /**
   * Get top errors
   */
  getTopErrors() {
    return Array.from(this.metrics.errors.entries())
      .sort((a, b) => b[1].count - a[1].count)
      .slice(0, 10)
      .map(([key, metric]) => ({
        key,
        count: metric.count,
        severity: metric.severity,
        lastSeen: metric.lastSeen,
        affectedUsers: metric.userCount.size,
        affectedComponents: metric.affectedComponents.size
      }));
  }

  /**
   * Get component health
   */
  getComponentHealth() {
    return Array.from(this.metrics.components.entries())
      .map(([name, metric]) => ({
        name,
        errorCount: metric.errorCount,
        healthScore: metric.healthScore,
        lastError: metric.lastError
      }))
      .sort((a, b) => a.healthScore - b.healthScore);
  }

  /**
   * Get API health
   */
  getApiHealth() {
    return Array.from(this.metrics.apis.entries())
      .map(([operation, metric]) => ({
        operation,
        errorRate: metric.errorRate,
        averageResponseTime: metric.averageResponseTime,
        requestCount: metric.requestCount,
        errorCount: metric.errorCount
      }))
      .sort((a, b) => b.errorRate - a.errorRate);
  }

  /**
   * Get user metrics
   */
  getUserMetrics() {
    const totalUsers = this.metrics.users.size;
    const affectedUsers = Array.from(this.metrics.users.values())
      .filter(metric => metric.errorCount > 0).length;
    
    const averageSatisfaction = Array.from(this.metrics.users.values())
      .reduce((sum, metric) => sum + metric.satisfactionScore, 0) / totalUsers;

    return {
      totalUsers,
      affectedUsers,
      affectedPercentage: totalUsers > 0 ? (affectedUsers / totalUsers) * 100 : 0,
      averageSatisfaction
    };
  }

  /**
   * Get performance metrics
   */
  getPerformanceMetrics() {
    const metrics = {};
    
    for (const [name, metric] of this.metrics.performance) {
      metrics[name] = {
        average: metric.average,
        min: metric.min,
        max: metric.max,
        count: metric.count,
        recent: metric.values.slice(-10).map(v => v.value)
      };
    }
    
    return metrics;
  }

  /**
   * Stop monitoring
   */
  stop() {
    if (this.unsubscribe) {
      this.unsubscribe();
    }
    
    if (this.monitoringInterval) {
      clearInterval(this.monitoringInterval);
    }
    
    this.isMonitoring = false;
  }

  /**
   * Reset all analytics data
   */
  reset() {
    this.metrics = {
      errors: new Map(),
      performance: new Map(),
      users: new Map(),
      sessions: new Map(),
      components: new Map(),
      apis: new Map()
    };
    
    this.alerts = [];
    this.realTimeData = {
      errorRate: 0,
      responseTime: 0,
      userSatisfaction: 0,
      systemHealth: 100
    };
  }
}

// Create singleton instance
const errorAnalytics = new ErrorAnalytics();

export default errorAnalytics;
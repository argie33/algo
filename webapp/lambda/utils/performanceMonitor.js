/**
 * Real-Time Performance Monitoring System
 * Tracks system performance metrics, API response times, database operations,
 * and provides real-time alerts for performance degradation
 */

const { createRequestLogger } = require('./logger');
const { query } = require('./database');

class PerformanceMonitor {
  constructor() {
    this.metrics = {
      // API Performance
      apiRequests: new Map(),
      apiErrors: new Map(),
      responseTimeHistogram: new Map(),
      
      // Database Performance
      dbConnections: new Map(),
      dbQueryTimes: new Map(),
      dbErrors: new Map(),
      
      // Memory & CPU
      memoryUsage: [],
      cpuUsage: [],
      
      // External Services
      externalApiCalls: new Map(),
      
      // Real-time counters
      activeRequests: 0,
      totalRequests: 0,
      totalErrors: 0,
      
      // Performance thresholds
      thresholds: {
        apiResponseTime: 2000, // 2 seconds
        dbQueryTime: 1000, // 1 second
        memoryUsage: 512 * 1024 * 1024, // 512MB
        errorRate: 0.05 // 5%
      }
    };
    
    this.logger = createRequestLogger('performance-monitor');
    this.startTime = Date.now();
    this.alertCallbacks = [];
    
    // Track timer references for proper cleanup
    this.timers = {
      systemMetrics: null,
      cleanup: null,
      alerts: null
    };
    this.isActive = false;
    
    // Start background monitoring
    this.startBackgroundMonitoring();
  }

  /**
   * Start background system monitoring
   */
  startBackgroundMonitoring() {
    if (this.isActive) return;
    
    this.isActive = true;
    
    // Memory and CPU monitoring every 30 seconds
    this.timers.systemMetrics = setInterval(() => {
      this.collectSystemMetrics();
    }, 30000);

    // Clean up old metrics every 5 minutes
    this.timers.cleanup = setInterval(() => {
      this.cleanupOldMetrics();
    }, 300000);

    // Performance alerts check every minute
    this.timers.alerts = setInterval(() => {
      this.checkPerformanceAlerts();
    }, 60000);
  }

  /**
   * Stop background monitoring and clean up resources
   */
  stopBackgroundMonitoring() {
    if (!this.isActive) return;
    
    this.isActive = false;
    
    // Clear all timers
    if (this.timers.systemMetrics) {
      clearInterval(this.timers.systemMetrics);
      this.timers.systemMetrics = null;
    }
    
    if (this.timers.cleanup) {
      clearInterval(this.timers.cleanup);
      this.timers.cleanup = null;
    }
    
    if (this.timers.alerts) {
      clearInterval(this.timers.alerts);
      this.timers.alerts = null;
    }
    
    // Clear alert callbacks
    this.alertCallbacks = [];
  }

  /**
   * Clean up all resources
   */
  cleanup() {
    this.stopBackgroundMonitoring();
    
    // Clear all metrics
    this.metrics.apiRequests.clear();
    this.metrics.apiErrors.clear();
    this.metrics.responseTimeHistogram.clear();
    this.metrics.dbConnections.clear();
    this.metrics.dbQueryTimes.clear();
    this.metrics.dbErrors.clear();
    this.metrics.externalApiCalls.clear();
    this.metrics.memoryUsage = [];
    this.metrics.cpuUsage = [];
    
    // Reset counters
    this.metrics.activeRequests = 0;
    this.metrics.totalRequests = 0;
    this.metrics.totalErrors = 0;
  }

  /**
   * Collect system metrics
   */
  collectSystemMetrics() {
    const memUsage = process.memoryUsage();
    const cpuUsage = process.cpuUsage();
    
    const timestamp = Date.now();
    
    // Memory metrics
    this.metrics.memoryUsage.push({
      timestamp,
      rss: memUsage.rss,
      heapUsed: memUsage.heapUsed,
      heapTotal: memUsage.heapTotal,
      external: memUsage.external
    });
    
    // CPU metrics
    this.metrics.cpuUsage.push({
      timestamp,
      user: cpuUsage.user,
      system: cpuUsage.system
    });
    
    // Keep only last 100 measurements
    if (this.metrics.memoryUsage.length > 100) {
      this.metrics.memoryUsage = this.metrics.memoryUsage.slice(-100);
    }
    if (this.metrics.cpuUsage.length > 100) {
      this.metrics.cpuUsage = this.metrics.cpuUsage.slice(-100);
    }
    
    // Log high memory usage
    if (memUsage.heapUsed > this.metrics.thresholds.memoryUsage) {
      this.logger.warn('High memory usage detected', {
        heapUsed: memUsage.heapUsed,
        heapTotal: memUsage.heapTotal,
        threshold: this.metrics.thresholds.memoryUsage
      });
    }
  }

  /**
   * Track API request start
   */
  trackApiRequestStart(method, path, requestId) {
    const key = `${method}:${path}`;
    
    if (!this.metrics.apiRequests.has(key)) {
      this.metrics.apiRequests.set(key, {
        count: 0,
        errors: 0,
        totalResponseTime: 0,
        avgResponseTime: 0,
        minResponseTime: Infinity,
        maxResponseTime: 0,
        recentRequests: []
      });
    }
    
    const requestData = {
      requestId,
      startTime: Date.now(),
      method,
      path
    };
    
    this.metrics.activeRequests++;
    this.metrics.totalRequests++;
    
    return requestData;
  }

  /**
   * Track API request completion
   */
  trackApiRequestComplete(requestData, statusCode, responseSize = 0) {
    const endTime = Date.now();
    const responseTime = endTime - requestData.startTime;
    const key = `${requestData.method}:${requestData.path}`;
    
    const metric = this.metrics.apiRequests.get(key);
    if (metric) {
      metric.count++;
      metric.totalResponseTime += responseTime;
      metric.avgResponseTime = metric.totalResponseTime / metric.count;
      metric.minResponseTime = Math.min(metric.minResponseTime, responseTime);
      metric.maxResponseTime = Math.max(metric.maxResponseTime, responseTime);
      
      // Track recent requests for trend analysis
      metric.recentRequests.push({
        timestamp: endTime,
        responseTime,
        statusCode,
        responseSize
      });
      
      // Keep only last 50 requests
      if (metric.recentRequests.length > 50) {
        metric.recentRequests = metric.recentRequests.slice(-50);
      }
      
      // Track errors
      if (statusCode >= 400) {
        metric.errors++;
        this.metrics.totalErrors++;
      }
    }
    
    this.metrics.activeRequests--;
    
    // Response time histogram
    const bucket = this.getResponseTimeBucket(responseTime);
    if (!this.metrics.responseTimeHistogram.has(bucket)) {
      this.metrics.responseTimeHistogram.set(bucket, 0);
    }
    this.metrics.responseTimeHistogram.set(bucket, 
      this.metrics.responseTimeHistogram.get(bucket) + 1);
    
    // Alert on slow responses
    if (responseTime > this.metrics.thresholds.apiResponseTime) {
      this.logger.warn('Slow API response detected', {
        method: requestData.method,
        path: requestData.path,
        responseTime,
        threshold: this.metrics.thresholds.apiResponseTime,
        requestId: requestData.requestId
      });
    }
  }

  /**
   * Track database operation
   */
  trackDbOperation(operation, table, duration, success = true, requestId = null) {
    const key = `${operation}:${table}`;
    
    if (!this.metrics.dbQueryTimes.has(key)) {
      this.metrics.dbQueryTimes.set(key, {
        count: 0,
        errors: 0,
        totalTime: 0,
        avgTime: 0,
        minTime: Infinity,
        maxTime: 0,
        recentQueries: []
      });
    }
    
    const metric = this.metrics.dbQueryTimes.get(key);
    metric.count++;
    metric.totalTime += duration;
    metric.avgTime = metric.totalTime / metric.count;
    metric.minTime = Math.min(metric.minTime, duration);
    metric.maxTime = Math.max(metric.maxTime, duration);
    
    metric.recentQueries.push({
      timestamp: Date.now(),
      duration,
      success,
      requestId
    });
    
    // Keep only last 50 queries
    if (metric.recentQueries.length > 50) {
      metric.recentQueries = metric.recentQueries.slice(-50);
    }
    
    if (!success) {
      metric.errors++;
    }
    
    // Alert on slow queries
    if (duration > this.metrics.thresholds.dbQueryTime) {
      this.logger.warn('Slow database query detected', {
        operation,
        table,
        duration,
        threshold: this.metrics.thresholds.dbQueryTime,
        requestId
      });
    }
  }

  /**
   * Track external API call
   */
  trackExternalApiCall(service, endpoint, duration, success = true, requestId = null) {
    const key = `${service}:${endpoint}`;
    
    if (!this.metrics.externalApiCalls.has(key)) {
      this.metrics.externalApiCalls.set(key, {
        count: 0,
        errors: 0,
        totalTime: 0,
        avgTime: 0,
        minTime: Infinity,
        maxTime: 0,
        recentCalls: []
      });
    }
    
    const metric = this.metrics.externalApiCalls.get(key);
    metric.count++;
    metric.totalTime += duration;
    metric.avgTime = metric.totalTime / metric.count;
    metric.minTime = Math.min(metric.minTime, duration);
    metric.maxTime = Math.max(metric.maxTime, duration);
    
    metric.recentCalls.push({
      timestamp: Date.now(),
      duration,
      success,
      requestId
    });
    
    // Keep only last 50 calls
    if (metric.recentCalls.length > 50) {
      metric.recentCalls = metric.recentCalls.slice(-50);
    }
    
    if (!success) {
      metric.errors++;
    }
    
    this.logger.info(`External API call: ${service}`, {
      service,
      endpoint,
      duration,
      success,
      requestId
    });
  }

  /**
   * Get response time bucket for histogram
   */
  getResponseTimeBucket(responseTime) {
    if (responseTime < 100) return '<100ms';
    if (responseTime < 500) return '100-500ms';
    if (responseTime < 1000) return '500ms-1s';
    if (responseTime < 2000) return '1-2s';
    if (responseTime < 5000) return '2-5s';
    return '>5s';
  }

  /**
   * Get comprehensive performance metrics
   */
  getMetrics() {
    const now = Date.now();
    const uptime = now - this.startTime;
    
    // Calculate error rate
    const errorRate = this.metrics.totalRequests > 0 ? 
      this.metrics.totalErrors / this.metrics.totalRequests : 0;
    
    // Current memory usage
    const memUsage = process.memoryUsage();
    
    // Recent response times
    const recentResponseTimes = [];
    for (const [key, metric] of this.metrics.apiRequests) {
      recentResponseTimes.push(...metric.recentRequests.map(r => r.responseTime));
    }
    
    const avgResponseTime = recentResponseTimes.length > 0 ? 
      recentResponseTimes.reduce((a, b) => a + b, 0) / recentResponseTimes.length : 0;
    
    return {
      timestamp: now,
      uptime,
      system: {
        memory: {
          rss: memUsage.rss,
          heapUsed: memUsage.heapUsed,
          heapTotal: memUsage.heapTotal,
          external: memUsage.external
        },
        activeRequests: this.metrics.activeRequests,
        totalRequests: this.metrics.totalRequests,
        totalErrors: this.metrics.totalErrors,
        errorRate,
        avgResponseTime
      },
      api: {
        requests: Object.fromEntries(this.metrics.apiRequests),
        responseTimeHistogram: Object.fromEntries(this.metrics.responseTimeHistogram)
      },
      database: {
        queries: Object.fromEntries(this.metrics.dbQueryTimes)
      },
      external: {
        apis: Object.fromEntries(this.metrics.externalApiCalls)
      },
      thresholds: this.metrics.thresholds
    };
  }

  /**
   * Get performance summary
   */
  getPerformanceSummary() {
    const metrics = this.getMetrics();
    const memUsage = process.memoryUsage();
    
    return {
      status: this.getOverallStatus(metrics),
      uptime: metrics.uptime,
      activeRequests: metrics.system.activeRequests,
      totalRequests: metrics.system.totalRequests,
      errorRate: metrics.system.errorRate,
      avgResponseTime: metrics.system.avgResponseTime,
      memoryUsage: {
        used: memUsage.heapUsed,
        total: memUsage.heapTotal,
        utilization: (memUsage.heapUsed / memUsage.heapTotal) * 100
      },
      alerts: this.getActiveAlerts(metrics)
    };
  }

  /**
   * Get overall system status
   */
  getOverallStatus(metrics) {
    const memUtilization = (metrics.system.memory.heapUsed / metrics.system.memory.heapTotal) * 100;
    
    if (metrics.system.errorRate > this.metrics.thresholds.errorRate ||
        metrics.system.avgResponseTime > this.metrics.thresholds.apiResponseTime ||
        memUtilization > 90) {
      return 'critical';
    }
    
    if (metrics.system.errorRate > this.metrics.thresholds.errorRate * 0.5 ||
        metrics.system.avgResponseTime > this.metrics.thresholds.apiResponseTime * 0.7 ||
        memUtilization > 75) {
      return 'warning';
    }
    
    return 'healthy';
  }

  /**
   * Get active alerts
   */
  getActiveAlerts(metrics) {
    const alerts = [];
    
    // High error rate
    if (metrics.system.errorRate > this.metrics.thresholds.errorRate) {
      alerts.push({
        type: 'error_rate',
        severity: 'critical',
        message: `Error rate ${(metrics.system.errorRate * 100).toFixed(2)}% exceeds threshold ${(this.metrics.thresholds.errorRate * 100).toFixed(2)}%`,
        value: metrics.system.errorRate,
        threshold: this.metrics.thresholds.errorRate
      });
    }
    
    // Slow response times
    if (metrics.system.avgResponseTime > this.metrics.thresholds.apiResponseTime) {
      alerts.push({
        type: 'response_time',
        severity: 'warning',
        message: `Average response time ${metrics.system.avgResponseTime}ms exceeds threshold ${this.metrics.thresholds.apiResponseTime}ms`,
        value: metrics.system.avgResponseTime,
        threshold: this.metrics.thresholds.apiResponseTime
      });
    }
    
    // High memory usage
    const memUtilization = (metrics.system.memory.heapUsed / metrics.system.memory.heapTotal) * 100;
    if (memUtilization > 90) {
      alerts.push({
        type: 'memory_usage',
        severity: 'critical',
        message: `Memory utilization ${memUtilization.toFixed(2)}% is critically high`,
        value: memUtilization,
        threshold: 90
      });
    }
    
    return alerts;
  }

  /**
   * Check for performance alerts
   */
  checkPerformanceAlerts() {
    const metrics = this.getMetrics();
    const alerts = this.getActiveAlerts(metrics);
    
    if (alerts.length > 0) {
      this.logger.warn('Performance alerts detected', {
        alertCount: alerts.length,
        alerts: alerts
      });
      
      // Trigger alert callbacks
      this.alertCallbacks.forEach(callback => {
        try {
          callback(alerts, metrics);
        } catch (error) {
          this.logger.error('Error in alert callback', { error });
        }
      });
    }
  }

  /**
   * Add alert callback
   */
  addAlertCallback(callback) {
    this.alertCallbacks.push(callback);
  }

  /**
   * Clean up old metrics
   */
  cleanupOldMetrics() {
    const fiveMinutesAgo = Date.now() - 300000;
    
    // Clean up API request recent data
    for (const [key, metric] of this.metrics.apiRequests) {
      metric.recentRequests = metric.recentRequests.filter(
        req => req.timestamp > fiveMinutesAgo
      );
    }
    
    // Clean up database query recent data
    for (const [key, metric] of this.metrics.dbQueryTimes) {
      metric.recentQueries = metric.recentQueries.filter(
        query => query.timestamp > fiveMinutesAgo
      );
    }
    
    // Clean up external API call recent data
    for (const [key, metric] of this.metrics.externalApiCalls) {
      metric.recentCalls = metric.recentCalls.filter(
        call => call.timestamp > fiveMinutesAgo
      );
    }
  }

  /**
   * Store metrics to database (for historical analysis)
   */
  async storeMetrics() {
    try {
      const metrics = this.getMetrics();
      await query(`
        INSERT INTO performance_metrics (
          timestamp, uptime, active_requests, total_requests, 
          total_errors, error_rate, avg_response_time, 
          memory_used, memory_total, metrics_data
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
      `, [
        new Date(metrics.timestamp),
        metrics.uptime,
        metrics.system.activeRequests,
        metrics.system.totalRequests,
        metrics.system.totalErrors,
        metrics.system.errorRate,
        metrics.system.avgResponseTime,
        metrics.system.memory.heapUsed,
        metrics.system.memory.heapTotal,
        JSON.stringify(metrics)
      ]);
    } catch (error) {
      this.logger.error('Failed to store performance metrics', { error });
    }
  }
}

// Global performance monitor instance
const performanceMonitor = new PerformanceMonitor();

module.exports = {
  performanceMonitor,
  PerformanceMonitor
};
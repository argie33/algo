/**
 * Performance Monitoring Utility
 * Comprehensive performance tracking for pattern recognition and real-time dashboard
 */

const logger = require("./logger");

class PerformanceMonitor {
  constructor() {
    this.metrics = new Map();
    this.activeOperations = new Map();
    this.historySize = 1000;
    this.performanceHistory = [];
    this.thresholds = {
      database: 1000, // Database queries should complete within 1s
      api: 5000, // API calls should complete within 5s
      pattern: 3000, // Pattern recognition within 3s
      dashboard: 2000, // Dashboard updates within 2s
      general: 10000, // General operations within 10s
    };
  }

  /**
   * Start timing an operation
   */
  startOperation(operationId, category, metadata = {}) {
    const operation = {
      id: operationId,
      category,
      startTime: Date.now(),
      startHrTime: process.hrtime(),
      metadata,
      correlationId: metadata.correlationId,
      userId: metadata.userId,
    };

    this.activeOperations.set(operationId, operation);

    logger.debug("Operation Started", {
      operationId,
      category,
      metadata,
    });

    return operation;
  }

  /**
   * End timing an operation and record metrics
   */
  endOperation(operationId, result = {}) {
    const operation = this.activeOperations.get(operationId);
    if (!operation) {
      logger.warn("Operation not found", { operationId });
      return null;
    }

    const endTime = Date.now();
    const endHrTime = process.hrtime(operation.startHrTime);
    const duration = endTime - operation.startTime;
    const preciseDuration = endHrTime[0] * 1000 + endHrTime[1] / 1000000;

    const metric = {
      id: operationId,
      category: operation.category,
      duration,
      preciseDuration,
      timestamp: new Date().toISOString(),
      success: result.success !== false,
      error: result.error,
      metadata: operation.metadata,
      result: result.data,
      correlationId: operation.correlationId,
      userId: operation.userId,
    };

    // Record the metric
    this.recordMetric(metric);

    // Check performance thresholds
    this.checkPerformanceThresholds(metric);

    // Remove from active operations
    this.activeOperations.delete(operationId);

    logger.debug("Operation Completed", {
      operationId,
      category: operation.category,
      duration,
      success: metric.success,
    });

    return metric;
  }

  /**
   * Record a metric in history
   */
  recordMetric(metric) {
    // Add to history
    this.performanceHistory.push(metric);

    // Maintain history size
    if (this.performanceHistory.length > this.historySize) {
      this.performanceHistory.shift();
    }

    // Update aggregated metrics
    this.updateAggregatedMetrics(metric);
  }

  /**
   * Update aggregated metrics for the category
   */
  updateAggregatedMetrics(metric) {
    const category = metric.category;

    if (!this.metrics.has(category)) {
      this.metrics.set(category, {
        count: 0,
        totalDuration: 0,
        minDuration: Infinity,
        maxDuration: 0,
        successCount: 0,
        errorCount: 0,
        averageDuration: 0,
        recentDurations: [],
      });
    }

    const stats = this.metrics.get(category);
    stats.count++;
    stats.totalDuration += metric.duration;
    stats.minDuration = Math.min(stats.minDuration, metric.duration);
    stats.maxDuration = Math.max(stats.maxDuration, metric.duration);
    stats.averageDuration = stats.totalDuration / stats.count;

    if (metric.success) {
      stats.successCount++;
    } else {
      stats.errorCount++;
    }

    // Keep recent durations for percentile calculations
    stats.recentDurations.push(metric.duration);
    if (stats.recentDurations.length > 100) {
      stats.recentDurations.shift();
    }
  }

  /**
   * Check if performance thresholds are exceeded
   */
  checkPerformanceThresholds(metric) {
    const threshold =
      this.thresholds[metric.category] || this.thresholds.general;

    if (metric.duration > threshold) {
      this.triggerPerformanceAlert(metric, threshold);
    }
  }

  /**
   * Trigger performance alert
   */
  triggerPerformanceAlert(metric, threshold) {
    const alertData = {
      timestamp: new Date().toISOString(),
      operationId: metric.id,
      category: metric.category,
      duration: metric.duration,
      threshold,
      severity: metric.duration > threshold * 2 ? "high" : "medium",
      message: `Slow operation detected: ${metric.category} took ${metric.duration}ms (threshold: ${threshold}ms)`,
      correlationId: metric.correlationId,
      userId: metric.userId,
      metadata: metric.metadata,
    };

    logger.warn("Performance Alert", alertData);

    // Send alert to monitoring system
    this.sendPerformanceAlert(alertData);
  }

  /**
   * Send performance alert to external systems
   */
  sendPerformanceAlert(alertData) {
    // Integration with external alerting systems
    console.log("⚠️ PERFORMANCE ALERT:", alertData.message);
  }

  /**
   * Get performance statistics
   */
  getPerformanceStats() {
    const stats = {
      overview: {
        totalOperations: this.performanceHistory.length,
        activeOperations: this.activeOperations.size,
        lastHour: this.performanceHistory.filter(
          (m) => Date.now() - new Date(m.timestamp).getTime() < 3600000
        ).length,
      },
      byCategory: {},
      slowOperations: this.getSlowOperations(),
      systemHealth: this.calculateSystemHealth(),
    };

    // Convert Map to object for JSON serialization
    for (const [category, metrics] of this.metrics) {
      stats.byCategory[category] = {
        ...metrics,
        successRate:
          metrics.count > 0
            ? ((metrics.successCount / metrics.count) * 100).toFixed(2)
            : 0,
        p95: this.calculatePercentile(metrics.recentDurations, 95),
        p99: this.calculatePercentile(metrics.recentDurations, 99),
      };
    }

    return stats;
  }

  /**
   * Calculate percentile for duration array
   */
  calculatePercentile(durations, percentile) {
    if (durations.length === 0) return 0;

    const sorted = durations.slice().sort((a, b) => a - b);
    const index = Math.ceil((percentile / 100) * sorted.length) - 1;
    return sorted[index];
  }

  /**
   * Get slow operations from recent history
   */
  getSlowOperations(limit = 20) {
    return this.performanceHistory
      .filter((m) => {
        const threshold =
          this.thresholds[m.category] || this.thresholds.general;
        return m.duration > threshold;
      })
      .sort((a, b) => b.duration - a.duration)
      .slice(0, limit);
  }

  /**
   * Calculate overall system health score
   */
  calculateSystemHealth() {
    const recentMetrics = this.performanceHistory.filter(
      (m) => Date.now() - new Date(m.timestamp).getTime() < 300000 // Last 5 minutes
    );

    if (recentMetrics.length === 0) {
      return { score: 100, status: "healthy" };
    }

    const successRate =
      recentMetrics.filter((m) => m.success).length / recentMetrics.length;
    const averageDuration =
      recentMetrics.reduce((sum, m) => sum + m.duration, 0) /
      recentMetrics.length;
    const slowOperations = recentMetrics.filter((m) => {
      const threshold = this.thresholds[m.category] || this.thresholds.general;
      return m.duration > threshold;
    }).length;

    // Calculate health score (0-100)
    let score = 100;
    score -= (1 - successRate) * 50; // Success rate impact
    score -= Math.min((slowOperations / recentMetrics.length) * 30, 30); // Slow operations impact
    score -= Math.min((averageDuration / 1000) * 20, 20); // Average duration impact

    score = Math.max(0, Math.min(100, score));

    let status = "healthy";
    if (score < 50) status = "critical";
    else if (score < 70) status = "degraded";
    else if (score < 90) status = "warning";

    return {
      score: Math.round(score),
      status,
      successRate: (successRate * 100).toFixed(2),
      averageDuration: Math.round(averageDuration),
      slowOperations: slowOperations,
      totalOperations: recentMetrics.length,
    };
  }

  /**
   * Express middleware for automatic performance tracking
   */
  middleware() {
    return (req, res, next) => {
      const operationId = `${req.method}:${req.path}:${Date.now()}:${Math.random().toString(36).substr(2, 9)}`;
      const category = this.categorizeRequest(req);

      const _operation = this.startOperation(operationId, category, {
        method: req.method,
        path: req.path,
        correlationId: req.headers["x-correlation-id"] || req.id,
        userId: req.user?.id,
        userAgent: req.get("User-Agent"),
      });

      // Store operation ID in request for later use
      req.performanceOperationId = operationId;

      // Hook into response finish
      const originalEnd = res.end;
      res.end = function (chunk, encoding) {
        const result = {
          success: res.statusCode < 400,
          statusCode: res.statusCode,
          data: {
            statusCode: res.statusCode,
            contentLength: res.get("Content-Length"),
          },
        };

        if (res.statusCode >= 400) {
          result.error = `HTTP ${res.statusCode}`;
        }

        performanceMonitor.endOperation(operationId, result);

        originalEnd.call(this, chunk, encoding);
      };

      next();
    };
  }

  /**
   * Categorize request for performance tracking
   */
  categorizeRequest(req) {
    const path = req.path.toLowerCase();

    if (path.includes("/api/technical/patterns")) return "pattern";
    if (path.includes("/api/live-data") || path.includes("/api/stocks"))
      return "dashboard";
    if (path.includes("/api/database") || path.includes("/api/health"))
      return "database";
    if (path.includes("/api/")) return "api";

    return "general";
  }

  /**
   * Manual timing utility for specific operations
   */
  time(category, operation, metadata = {}) {
    const operationId = `${category}:${Date.now()}:${Math.random().toString(36).substr(2, 9)}`;

    return {
      operationId,
      start: () => this.startOperation(operationId, category, metadata),
      end: (result) => this.endOperation(operationId, result),
      wrap: async (fn) => {
        this.startOperation(operationId, category, metadata);
        try {
          const result = await fn();
          this.endOperation(operationId, { success: true, data: result });
          return result;
        } catch (error) {
          this.endOperation(operationId, {
            success: false,
            error: error.message,
          });
          throw error;
        }
      },
    };
  }

  /**
   * Get active operations for debugging
   */
  getActiveOperations() {
    return Array.from(this.activeOperations.values());
  }

  /**
   * Clear performance history
   */
  clearHistory() {
    this.performanceHistory = [];
    this.metrics.clear();
    this.activeOperations.clear();
  }

  /**
   * Reset the performance monitor to initial state
   */
  reset() {
    this.metrics.clear();
    this.activeOperations.clear();
    this.performanceHistory = [];
  }
}

// Create singleton instance
const performanceMonitor = new PerformanceMonitor();

module.exports = performanceMonitor;

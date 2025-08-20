/**
 * Error Tracking and Monitoring Utility
 * Comprehensive error tracking for production-ready financial platform
 */

const logger = require('./logger');

class ErrorTracker {
  constructor() {
    this.errorCounts = new Map();
    this.errorHistory = [];
    this.maxHistorySize = 1000;
    this.alertThresholds = {
      database: 5,      // Database errors per minute
      api: 10,          // API errors per minute
      auth: 3,          // Authentication errors per minute
      general: 15       // General errors per minute
    };
  }

  /**
   * Track and log an error with comprehensive context
   */
  trackError(error, context = {}) {
    const errorData = {
      timestamp: new Date().toISOString(),
      message: error.message,
      stack: error.stack,
      name: error.name,
      code: error.code,
      statusCode: error.statusCode,
      correlationId: context.correlationId,
      userId: context.userId,
      route: context.route,
      method: context.method,
      userAgent: context.userAgent,
      ip: context.ip,
      category: this.categorizeError(error),
      severity: this.calculateSeverity(error),
      context: context
    };

    // Log the error with structured format
    logger.error('Application Error', errorData);

    // Track error frequency
    this.updateErrorCounts(errorData);

    // Store in history
    this.addToHistory(errorData);

    // Check if alert thresholds are exceeded
    this.checkAlertThresholds(errorData);

    // Return error ID for reference
    return this.generateErrorId(errorData);
  }

  /**
   * Categorize error based on type and context
   */
  categorizeError(error) {
    const message = error.message.toLowerCase();
    const code = error.code || '';
    const stack = error.stack || '';

    // Database errors
    if (message.includes('database') || 
        message.includes('connection') || 
        message.includes('timeout') ||
        code.includes('ECONNREFUSED') ||
        code.includes('ECONNRESET') ||
        stack.includes('pg')) {
      return 'database';
    }

    // Authentication errors
    if (message.includes('unauthorized') ||
        message.includes('forbidden') ||
        message.includes('token') ||
        message.includes('auth') ||
        error.statusCode === 401 ||
        error.statusCode === 403) {
      return 'auth';
    }

    // API integration errors
    if (message.includes('api') ||
        message.includes('request') ||
        message.includes('network') ||
        error.statusCode >= 500) {
      return 'api';
    }

    // Validation errors
    if (message.includes('validation') ||
        message.includes('invalid') ||
        message.includes('required') ||
        error.statusCode === 400) {
      return 'validation';
    }

    // Circuit breaker errors
    if (message.includes('circuit') ||
        message.includes('breaker') ||
        message.includes('open')) {
      return 'circuit_breaker';
    }

    return 'general';
  }

  /**
   * Calculate error severity based on type and impact
   */
  calculateSeverity(error) {
    const statusCode = error.statusCode;
    const message = error.message.toLowerCase();

    // Critical errors
    if (statusCode >= 500 ||
        message.includes('database') ||
        message.includes('connection') ||
        message.includes('timeout') ||
        message.includes('circuit breaker is open')) {
      return 'critical';
    }

    // High severity errors
    if (statusCode === 401 ||
        statusCode === 403 ||
        message.includes('unauthorized') ||
        message.includes('forbidden') ||
        message.includes('api key')) {
      return 'high';
    }

    // Medium severity errors
    if (statusCode === 400 ||
        message.includes('validation') ||
        message.includes('invalid')) {
      return 'medium';
    }

    // Low severity errors
    return 'low';
  }

  /**
   * Update error frequency tracking
   */
  updateErrorCounts(errorData) {
    const now = Date.now();
    const minuteKey = Math.floor(now / 60000); // Group by minute
    const countKey = `${errorData.category}:${minuteKey}`;

    if (!this.errorCounts.has(countKey)) {
      this.errorCounts.set(countKey, 0);
    }
    this.errorCounts.set(countKey, this.errorCounts.get(countKey) + 1);

    // Clean up old counts (keep last 5 minutes)
    const cutoffKey = minuteKey - 5;
    for (const [key] of this.errorCounts) {
      const keyMinute = parseInt(key.split(':')[1]);
      if (keyMinute < cutoffKey) {
        this.errorCounts.delete(key);
      }
    }
  }

  /**
   * Add error to history with size limit
   */
  addToHistory(errorData) {
    this.errorHistory.push(errorData);
    if (this.errorHistory.length > this.maxHistorySize) {
      this.errorHistory.shift();
    }
  }

  /**
   * Check if alert thresholds are exceeded
   */
  checkAlertThresholds(errorData) {
    const now = Date.now();
    const minuteKey = Math.floor(now / 60000);
    const countKey = `${errorData.category}:${minuteKey}`;
    const currentCount = this.errorCounts.get(countKey) || 0;
    const threshold = this.alertThresholds[errorData.category] || this.alertThresholds.general;

    if (currentCount >= threshold) {
      this.triggerAlert(errorData.category, currentCount, threshold);
    }
  }

  /**
   * Trigger alert for high error rate
   */
  triggerAlert(category, currentCount, threshold) {
    const alertData = {
      timestamp: new Date().toISOString(),
      category,
      currentCount,
      threshold,
      severity: 'high',
      message: `High error rate detected: ${currentCount} ${category} errors in the last minute (threshold: ${threshold})`
    };

    logger.warn('Error Rate Alert', alertData);

    // Here you would integrate with your alerting system
    // Examples: SNS, Slack, PagerDuty, etc.
    this.sendAlert(alertData);
  }

  /**
   * Send alert to external systems
   */
  sendAlert(alertData) {
    // Integration with external alerting systems
    // This is a placeholder - implement based on your needs
    console.log('🚨 ALERT:', alertData.message);
  }

  /**
   * Generate unique error ID for tracking
   */
  generateErrorId(errorData) {
    const timestamp = Date.now().toString(36);
    const random = Math.random().toString(36).substr(2, 5);
    const category = errorData.category.substr(0, 3);
    return `${category}-${timestamp}-${random}`;
  }

  /**
   * Get error statistics
   */
  getErrorStats() {
    const now = Date.now();
    const currentMinute = Math.floor(now / 60000);
    
    const stats = {
      total: this.errorHistory.length,
      lastHour: this.errorHistory.filter(e => 
        Date.now() - new Date(e.timestamp).getTime() < 3600000
      ).length,
      byCategory: {},
      bySeverity: {},
      currentMinuteRates: {}
    };

    // Count by category and severity
    this.errorHistory.forEach(error => {
      stats.byCategory[error.category] = (stats.byCategory[error.category] || 0) + 1;
      stats.bySeverity[error.severity] = (stats.bySeverity[error.severity] || 0) + 1;
    });

    // Current minute rates
    for (const [key, count] of this.errorCounts) {
      const [category, minute] = key.split(':');
      if (parseInt(minute) === currentMinute) {
        stats.currentMinuteRates[category] = count;
      }
    }

    return stats;
  }

  /**
   * Get recent errors for debugging
   */
  getRecentErrors(limit = 50) {
    return this.errorHistory
      .slice(-limit)
      .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
  }

  /**
   * Clear error history (for testing or maintenance)
   */
  clearHistory() {
    this.errorHistory = [];
    this.errorCounts.clear();
  }

  /**
   * Express middleware for automatic error tracking
   */
  middleware() {
    return (err, req, res, next) => {
      const context = {
        correlationId: req.headers['x-correlation-id'] || req.id,
        userId: req.user?.id,
        route: req.route?.path,
        method: req.method,
        userAgent: req.get('User-Agent'),
        ip: req.ip,
        body: req.body,
        query: req.query,
        params: req.params
      };

      const errorId = this.trackError(err, context);
      
      // Add error ID to response headers for debugging
      res.setHeader('X-Error-ID', errorId);

      next(err);
    };
  }
}

// Create singleton instance
const errorTracker = new ErrorTracker();

module.exports = errorTracker;
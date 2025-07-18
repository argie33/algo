// Performance Monitoring Middleware
// Automatic metrics collection for response times, throughput, and system health

const PerformanceMonitoringService = require('../services/performanceMonitoringService');

class PerformanceMonitoringMiddleware {
  constructor() {
    this.performanceService = new PerformanceMonitoringService();
    this.activeRequests = new Map();
  }

  // Request performance tracking middleware
  requestTrackingMiddleware() {
    return (req, res, next) => {
      const startTime = Date.now();
      const requestId = `req_${Math.random().toString(36).substr(2, 9)}`;
      
      // Store request start time
      this.activeRequests.set(requestId, {
        startTime,
        method: req.method,
        path: req.path,
        userAgent: req.get('User-Agent'),
        ip: req.ip
      });
      
      // Override res.end to capture response time
      const originalEnd = res.end;
      res.end = (...args) => {
        const endTime = Date.now();
        const responseTime = endTime - startTime;
        
        // Record performance metrics
        this.recordRequestMetrics(req, res, responseTime, requestId);
        
        // Clean up active request tracking
        this.activeRequests.delete(requestId);
        
        // Call original end
        originalEnd.apply(res, args);
      };
      
      // Add request ID to response headers for tracking
      res.setHeader('X-Request-ID', requestId);
      
      next();
    };
  }

  // Record metrics for completed requests
  recordRequestMetrics(req, res, responseTime, requestId) {
    const endpoint = this.normalizeEndpoint(req.path);
    const statusCode = res.statusCode;
    const isError = statusCode >= 400;
    
    // Record response time metric
    this.performanceService.recordMetric(
      `api_response_time_${endpoint}`,
      responseTime,
      'api',
      {
        method: req.method,
        endpoint: req.path,
        statusCode,
        userAgent: req.get('User-Agent'),
        contentLength: res.getHeader('content-length') || 0,
        requestId
      }
    );
    
    // Record throughput metric
    this.performanceService.recordMetric(
      'api_throughput',
      1,
      'api',
      {
        endpoint,
        method: req.method,
        timestamp: Date.now()
      }
    );
    
    // Record error rate if applicable
    if (isError) {
      this.performanceService.recordMetric(
        `api_error_rate_${endpoint}`,
        1,
        'api',
        {
          statusCode,
          method: req.method,
          endpoint: req.path,
          errorType: this.classifyError(statusCode)
        }
      );
    }
  }

  // Normalize endpoint for consistent metrics
  normalizeEndpoint(path) {
    let normalized = path.split('?')[0];
    normalized = normalized.replace(/\/[0-9a-f-]{36}/gi, '/:id');
    normalized = normalized.replace(/\/\d+/g, '/:id');
    normalized = normalized.replace(/^\/|\/$/g, '').replace(/\/+/g, '/');
    return normalized || 'root';
  }

  // Classify error types
  classifyError(statusCode) {
    if (statusCode >= 500) return 'server_error';
    if (statusCode >= 400 && statusCode < 500) return 'client_error';
    return 'unknown_error';
  }

  // System health monitoring middleware
  systemHealthMiddleware() {
    return (req, res, next) => {
      if (Math.random() < 0.05) {
        process.nextTick(() => {
          this.collectSystemHealthMetrics();
        });
      }
      next();
    };
  }

  // Collect system health metrics
  collectSystemHealthMetrics() {
    try {
      const memoryUsage = process.memoryUsage();
      const memoryUtilization = memoryUsage.heapUsed / memoryUsage.heapTotal;
      
      this.performanceService.recordMetric(
        'system_memory_utilization',
        memoryUtilization,
        'memory',
        memoryUsage
      );
      
      this.performanceService.recordMetric(
        'system_active_requests',
        this.activeRequests.size,
        'api',
        { type: 'concurrent_requests' }
      );
      
      this.performanceService.recordMetric(
        'system_uptime',
        process.uptime(),
        'system',
        { type: 'process_uptime' }
      );
    } catch (error) {
      console.error('System health metrics collection failed:', error);
    }
  }

  // Error tracking middleware
  errorTrackingMiddleware() {
    return (error, req, res, next) => {
      this.performanceService.recordMetric(
        'application_error_rate',
        1,
        'api',
        {
          error: error.message,
          endpoint: req.path,
          method: req.method,
          statusCode: res.statusCode || 500
        }
      );
      next(error);
    };
  }

  getPerformanceService() {
    return this.performanceService;
  }

  getActiveRequestsCount() {
    return this.activeRequests.size;
  }
}

module.exports = PerformanceMonitoringMiddleware;
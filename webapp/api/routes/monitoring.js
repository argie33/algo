const express = require('express');
const { success, error } = require('../utils/responseFormatter');

const router = express.Router();

// In-memory performance tracking
const performanceMetrics = {
  requestCounts: {},
  responseTimes: {},
  errorCounts: {},
  lastUpdated: Date.now()
};

// Route performance tracking middleware
const trackPerformance = (routeName) => (req, res, next) => {
  const startTime = Date.now();
  
  // Track request count
  performanceMetrics.requestCounts[routeName] = (performanceMetrics.requestCounts[routeName] || 0) + 1;
  
  // Override res.end to capture response time
  const originalEnd = res.end;
  res.end = function(...args) {
    const duration = Date.now() - startTime;
    
    // Track response time
    if (!performanceMetrics.responseTimes[routeName]) {
      performanceMetrics.responseTimes[routeName] = [];
    }
    performanceMetrics.responseTimes[routeName].push(duration);
    
    // Keep only last 100 response times per route
    if (performanceMetrics.responseTimes[routeName].length > 100) {
      performanceMetrics.responseTimes[routeName] = performanceMetrics.responseTimes[routeName].slice(-100);
    }
    
    // Track errors (4xx, 5xx status codes)
    if (res.statusCode >= 400) {
      performanceMetrics.errorCounts[routeName] = (performanceMetrics.errorCounts[routeName] || 0) + 1;
    }
    
    performanceMetrics.lastUpdated = Date.now();
    
    originalEnd.apply(this, args);
  };
  
  next();
};

// Health endpoint for monitoring service
router.get('/health', (req, res) => {
  res.json(success({
    status: 'operational',
    service: 'api-monitoring',
    timestamp: new Date().toISOString(),
    message: 'API Monitoring service is running',
    uptime: process.uptime(),
    memory: process.memoryUsage()
  }));
});

// Get comprehensive API performance metrics
router.get('/metrics', (req, res) => {
  const metrics = {
    summary: {
      totalRoutes: Object.keys(performanceMetrics.requestCounts).length,
      totalRequests: Object.values(performanceMetrics.requestCounts).reduce((sum, count) => sum + count, 0),
      totalErrors: Object.values(performanceMetrics.errorCounts).reduce((sum, count) => sum + count, 0),
      lastUpdated: new Date(performanceMetrics.lastUpdated).toISOString(),
      uptime: process.uptime()
    },
    routes: {}
  };
  
  // Calculate metrics per route
  Object.keys(performanceMetrics.requestCounts).forEach(routeName => {
    const requestCount = performanceMetrics.requestCounts[routeName] || 0;
    const errorCount = performanceMetrics.errorCounts[routeName] || 0;
    const responseTimes = performanceMetrics.responseTimes[routeName] || [];
    
    let avgResponseTime = 0;
    let minResponseTime = 0;
    let maxResponseTime = 0;
    
    if (responseTimes.length > 0) {
      avgResponseTime = responseTimes.reduce((sum, time) => sum + time, 0) / responseTimes.length;
      minResponseTime = Math.min(...responseTimes);
      maxResponseTime = Math.max(...responseTimes);
    }
    
    metrics.routes[routeName] = {
      requestCount,
      errorCount,
      errorRate: requestCount > 0 ? (errorCount / requestCount * 100).toFixed(2) + '%' : '0%',
      avgResponseTime: Math.round(avgResponseTime) + 'ms',
      minResponseTime: minResponseTime + 'ms',
      maxResponseTime: maxResponseTime + 'ms',
      responseTimes: responseTimes.slice(-10) // Last 10 response times
    };
  });
  
  res.json(success(metrics));
});

// Get route health status
router.get('/routes', (req, res) => {
  const routeHealth = {
    timestamp: new Date().toISOString(),
    routes: {}
  };
  
  // Define expected routes and their health status
  const expectedRoutes = [
    'health', 'diagnostics', 'websocket', 'live-data', 'stocks', 'portfolio',
    'market', 'market-data', 'data', 'settings', 'auth', 'technical',
    'dashboard', 'screener', 'watchlist', 'metrics', 'alerts', 'news',
    'sentiment', 'signals', 'crypto', 'advanced', 'calendar', 'commodities',
    'sectors', 'trading', 'trades', 'risk', 'performance'
  ];
  
  expectedRoutes.forEach(routeName => {
    const requestCount = performanceMetrics.requestCounts[routeName] || 0;
    const errorCount = performanceMetrics.errorCounts[routeName] || 0;
    const responseTimes = performanceMetrics.responseTimes[routeName] || [];
    
    let status = 'unknown';
    if (requestCount > 0) {
      const errorRate = errorCount / requestCount;
      const avgResponseTime = responseTimes.length > 0 
        ? responseTimes.reduce((sum, time) => sum + time, 0) / responseTimes.length
        : 0;
      
      if (errorRate > 0.5) {
        status = 'critical';
      } else if (errorRate > 0.1 || avgResponseTime > 5000) {
        status = 'warning';
      } else {
        status = 'healthy';
      }
    }
    
    routeHealth.routes[routeName] = {
      status,
      requestCount,
      errorCount,
      lastResponseTime: responseTimes.length > 0 ? responseTimes[responseTimes.length - 1] + 'ms' : 'N/A'
    };
  });
  
  res.json(success(routeHealth));
});

// Get system health overview
router.get('/system', (req, res) => {
  const systemHealth = {
    timestamp: new Date().toISOString(),
    system: {
      uptime: Math.floor(process.uptime()),
      memory: {
        used: Math.round(process.memoryUsage().heapUsed / 1024 / 1024) + 'MB',
        total: Math.round(process.memoryUsage().heapTotal / 1024 / 1024) + 'MB',
        external: Math.round(process.memoryUsage().external / 1024 / 1024) + 'MB'
      },
      cpu: {
        platform: process.platform,
        arch: process.arch,
        nodeVersion: process.version
      }
    },
    api: {
      totalRequests: Object.values(performanceMetrics.requestCounts).reduce((sum, count) => sum + count, 0),
      totalErrors: Object.values(performanceMetrics.errorCounts).reduce((sum, count) => sum + count, 0),
      activeRoutes: Object.keys(performanceMetrics.requestCounts).length,
      lastActivity: new Date(performanceMetrics.lastUpdated).toISOString()
    },
    lambda: {
      functionName: process.env.AWS_LAMBDA_FUNCTION_NAME || 'local',
      functionVersion: process.env.AWS_LAMBDA_FUNCTION_VERSION || 'local',
      memorySize: process.env.AWS_LAMBDA_FUNCTION_MEMORY_SIZE || 'unknown',
      region: process.env.AWS_REGION || 'unknown'
    }
  };
  
  res.json(success(systemHealth));
});

// Reset metrics (for testing/debugging)
router.post('/reset', (req, res) => {
  performanceMetrics.requestCounts = {};
  performanceMetrics.responseTimes = {};
  performanceMetrics.errorCounts = {};
  performanceMetrics.lastUpdated = Date.now();
  
  res.json(success({
    message: 'Performance metrics reset successfully',
    timestamp: new Date().toISOString()
  }));
});

// Export the performance tracking middleware for use in other routes
router.trackPerformance = trackPerformance;

module.exports = router;
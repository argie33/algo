/**
 * Performance Monitoring Middleware
 * Integrates with the performance monitor to track all API requests
 */

const { performanceMonitor } = require('../utils/performanceMonitor');

/**
 * Performance monitoring middleware
 */
function performanceMonitoringMiddleware(req, res, next) {
  // Start tracking this request
  const requestData = performanceMonitor.trackApiRequestStart(
    req.method, 
    req.path, 
    req.logger ? req.logger.requestId : null
  );
  
  // Store request data for completion tracking
  req.performanceData = requestData;
  
  // Override res.json to track completion
  const originalJson = res.json;
  res.json = function(body) {
    // Track request completion
    const responseSize = Buffer.byteLength(JSON.stringify(body), 'utf8');
    performanceMonitor.trackApiRequestComplete(
      req.performanceData, 
      res.statusCode, 
      responseSize
    );
    
    return originalJson.call(this, body);
  };
  
  // Override res.send to track completion
  const originalSend = res.send;
  res.send = function(body) {
    // Track request completion
    const responseSize = Buffer.byteLength(body || '', 'utf8');
    performanceMonitor.trackApiRequestComplete(
      req.performanceData, 
      res.statusCode, 
      responseSize
    );
    
    return originalSend.call(this, body);
  };
  
  next();
}

/**
 * Database performance tracking wrapper
 */
function trackDbQuery(operation, table, queryFunction, requestId = null) {
  const startTime = Date.now();
  
  return queryFunction()
    .then(result => {
      const duration = Date.now() - startTime;
      performanceMonitor.trackDbOperation(operation, table, duration, true, requestId);
      return result;
    })
    .catch(error => {
      const duration = Date.now() - startTime;
      performanceMonitor.trackDbOperation(operation, table, duration, false, requestId);
      throw error;
    });
}

/**
 * External API call tracking wrapper
 */
function trackExternalApiCall(service, endpoint, apiFunction, requestId = null) {
  const startTime = Date.now();
  
  return apiFunction()
    .then(result => {
      const duration = Date.now() - startTime;
      performanceMonitor.trackExternalApiCall(service, endpoint, duration, true, requestId);
      return result;
    })
    .catch(error => {
      const duration = Date.now() - startTime;
      performanceMonitor.trackExternalApiCall(service, endpoint, duration, false, requestId);
      throw error;
    });
}

module.exports = {
  performanceMonitoringMiddleware,
  trackDbQuery,
  trackExternalApiCall
};
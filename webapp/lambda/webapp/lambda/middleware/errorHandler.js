const { logError, generateCorrelationId } = require('../utils/logger');

const errorHandler = (err, req, res, next) => {
  // Get or generate correlation ID
  const requestId = req.logger?.requestId || 
                   req.headers['x-request-id'] || 
                   req.headers['x-correlation-id'] || 
                   generateCorrelationId();
  
  // Use enhanced logging if available
  if (req.logger) {
    req.logger.error('Unhandled error occurred', {
      error: err,
      url: req.url,
      method: req.method,
      user_id: req.user?.sub,
      error_type: err.constructor.name
    });
  } else {
    // Fallback to utility function
    logError(err, {
      url: req.url,
      method: req.method,
      user_id: req.user?.sub,
      error_type: err.constructor.name
    }, requestId);
  }

  // CRITICAL: Set CORS headers immediately to prevent CORS errors
  res.header('Access-Control-Allow-Origin', '*');
  res.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS, HEAD, PATCH');
  res.header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With, X-Session-ID, Accept, Origin, Cache-Control, Pragma');
  res.header('Access-Control-Allow-Credentials', 'true');
  res.header('Access-Control-Max-Age', '86400');
  res.header('Access-Control-Expose-Headers', 'Content-Length, Content-Type, X-Request-ID');

  // Default error response
  let status = 500;
  let message = 'Internal Server Error';
  let details = null;

  // Handle specific error types
  if (err.name === 'ValidationError') {
    status = 400;
    message = 'Validation Error';
    details = err.message;
  } else if (err.code === '23505') { // PostgreSQL unique violation
    status = 409;
    message = 'Duplicate entry';
    details = 'A record with this information already exists';
  } else if (err.code === '23503') { // PostgreSQL foreign key violation
    status = 400;
    message = 'Invalid reference';
    details = 'Referenced record does not exist';
  } else if (err.code === '42P01') { // PostgreSQL table does not exist
    status = 500;
    message = 'Database configuration error';
    details = 'Required database table not found';
  } else if (err.message) {
    // If we have a custom error message, use it
    if (err.status) status = err.status;
    message = err.message;
  }

  const response = {
    error: {
      status,
      message,
      timestamp: new Date().toISOString(),
      path: req.url,
      request_id: requestId
    }
  };

  // Add details in development mode
  if (process.env.NODE_ENV === 'development' && details) {
    response.error.details = details;
  }
  
  // Add error code and type for better debugging
  if (err.code) {
    response.error.code = err.code;
  }
  if (err.constructor.name !== 'Error') {
    response.error.type = err.constructor.name;
  }
  
  // Set correlation ID in response header
  res.setHeader('X-Correlation-ID', requestId);

  console.log(`🚨 Error handler sending response with CORS headers: ${status} ${message}`);
  res.status(status).json(response);
};

module.exports = errorHandler;

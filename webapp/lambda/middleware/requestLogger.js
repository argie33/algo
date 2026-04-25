// Request/Response logging middleware for debugging
// Logs all API requests and responses with detailed error context

const requestLogger = (req, res, next) => {
  const start = Date.now();
  const requestId = req.get('X-Request-ID') || req.id || `${Date.now()}-${Math.random()}`;

  // Store on request for use in error handlers
  req.requestId = requestId;

  // Override res.json to log responses
  const originalJson = res.json.bind(res);
  res.json = function(data) {
    const duration = Date.now() - start;
    const statusCode = res.statusCode;

    // Log failed responses with details
    if (statusCode >= 400) {
      const errorContext = {
        requestId,
        timestamp: new Date().toISOString(),
        method: req.method,
        path: req.path,
        url: req.url,
        statusCode,
        duration: `${duration}ms`,
        query: req.query,
        body: req.body?.length ? '[body present]' : '[no body]'
      };

      if (statusCode >= 500) {
        console.error(`🔴 SERVER ERROR [${statusCode}]:`, {
          ...errorContext,
          response: data
        });
      } else if (statusCode >= 400) {
        console.warn(`🟡 CLIENT ERROR [${statusCode}]:`, {
          ...errorContext,
          error: data?.error || data?.message || data
        });
      }
    } else if (duration > 5000) {
      console.warn(`⏱️ SLOW RESPONSE [${statusCode}]:`, {
        requestId,
        method: req.method,
        path: req.path,
        duration: `${duration}ms`
      });
    }

    return originalJson(data);
  };

  // Log the incoming request
  if (process.env.NODE_ENV !== 'test') {
    console.log(`📨 [${requestId}] ${req.method} ${req.path}`);
  }

  next();
};

module.exports = requestLogger;

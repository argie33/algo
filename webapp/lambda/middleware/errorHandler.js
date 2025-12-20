const errorHandler = (err, req, res, _next) => {
  // Enhanced logging for AWS CloudWatch
  const errorDetails = {
    message: err.message,
    stack: process.env.NODE_ENV === 'development' ? err.stack : undefined,
    url: req.url,
    method: req.method,
    timestamp: new Date().toISOString(),
    userAgent: req.get('User-Agent'),
    requestId: req.get('X-Request-ID') || req.id,
    // AWS-specific context
    awsRequestId: req.context?.awsRequestId,
    functionName: process.env.AWS_LAMBDA_FUNCTION_NAME,
    functionVersion: process.env.AWS_LAMBDA_FUNCTION_VERSION,
    environment: process.env.NODE_ENV,
    memoryLimitInMB: process.env.AWS_LAMBDA_FUNCTION_MEMORY_SIZE,
    remainingTimeInMillis: req.context?.getRemainingTimeInMillis?.()
  };

  console.error('AWS Lambda Error:', JSON.stringify(errorDetails, null, 2));

  // Default error response
  let status = 500;
  let message = "Internal Server Error";
  let details = null;
  let code = 'INTERNAL_ERROR';

  // Handle AWS Lambda specific errors first
  if (err.message?.includes('Task timed out')) {
    status = 504;
    message = "Gateway Timeout";
    details = "Request processing timed out";
    code = 'LAMBDA_TIMEOUT';
  } else if (err.message?.includes('Runtime.ImportModuleError')) {
    status = 500;
    message = "Module Import Error";
    details = "Failed to import required modules";
    code = 'MODULE_IMPORT_ERROR';
  } else if (err.message?.includes('Cannot resolve module')) {
    status = 500;
    message = "Dependency Error";
    details = "Missing required dependencies";
    code = 'DEPENDENCY_ERROR';
  } else if (err.code === 'ECONNREFUSED' && err.address) {
    status = 503;
    message = "Database Connection Error";
    details = `Cannot connect to database at ${err.address}:${err.port}`;
    code = 'DB_CONNECTION_ERROR';
  } else if (err.code === 'ENOTFOUND' || err.code === 'ECONNREFUSED') {
    status = 503;
    message = "Service Unavailable";
    details = "External service connection failed";
    code = 'CONNECTION_ERROR';
  } else if (err.code === 'ECONNRESET' || err.code === 'ETIMEDOUT') {
    status = 504;
    message = "Connection Timeout";
    details = "Connection to external service timed out";
    code = 'CONNECTION_TIMEOUT';
  } else if (err.name === 'SecretsManagerServiceException') {
    status = 503;
    message = "Configuration Service Error";
    details = "Failed to retrieve configuration";
    code = 'SECRETS_MANAGER_ERROR';
  } else if (err.code === "23505") {
    // PostgreSQL unique violation - always use PostgreSQL status, ignore custom status
    status = 409;
    message = "Duplicate entry";
    details = "A record with this information already exists";
  } else if (err.code === "23503") {
    // PostgreSQL foreign key violation - always use PostgreSQL status, ignore custom status
    status = 400;
    message = "Invalid reference";
    details = "Referenced record does not exist";
  } else if (err.code === "42P01") {
    // PostgreSQL table does not exist - always use PostgreSQL status, ignore custom status
    status = 500;
    message = "Database configuration error";
    details = "Required database table not found";
  } else if (err.name === "ValidationError") {
    status = 400;
    message = "Validation Error";
    details = err.message;
  } else if (err.message) {
    // If we have a custom error message, use it
    if (err.status) status = err.status;
    message = err.message;
  }

  // Simple error response - matching RULES.md unified pattern
  // {error: "message", success: false}
  const response = {
    error: message,
    success: false
  };

  // Add development details only in dev mode
  if (process.env.NODE_ENV === "development") {
    response.details = {
      code,
      path: req.url,
      requestId: errorDetails.requestId || errorDetails.awsRequestId || req.headers['x-amzn-requestid'],
      timestamp: new Date().toISOString()
    };
    if (details) response.details.message = details;
    if (err.stack) response.details.stack = err.stack;
  }

  res.status(status).json(response);
};

module.exports = errorHandler;

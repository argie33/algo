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
  } else if (err.code === 'ECONNREFUSED' && err.address) {
    status = 503;
    message = "Database Connection Error";
    details = `Cannot connect to database at ${err.address}:${err.port}`;
    code = 'DB_CONNECTION_ERROR';
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

  const response = {
    success: false,
    error: {
      status,
      code,
      message,
      timestamp: new Date().toISOString(),
      path: req.url,
      requestId: errorDetails.requestId || errorDetails.awsRequestId || req.headers['x-amzn-requestid'] || `req-${Date.now()}`
    },
  };

  // Add details in development mode or for server errors
  if ((process.env.NODE_ENV === "development" || status >= 500) && details) {
    response.error.details = details;
  }

  // Add troubleshooting for AWS-specific issues
  if (status >= 500) {
    response.troubleshooting = {
      suggestion: "This appears to be a server-side issue",
      steps: [
        "1. Check AWS CloudWatch logs for detailed error information",
        "2. Verify all environment variables are properly configured",
        "3. Ensure database connectivity and AWS service permissions",
        "4. Check Lambda function timeout and memory settings"
      ]
    };

    // Add AWS-specific troubleshooting
    if (code === 'LAMBDA_TIMEOUT') {
      response.troubleshooting.aws_specific = [
        "1. Increase Lambda timeout in function configuration",
        "2. Optimize database queries and reduce processing time",
        "3. Consider using Lambda provisioned concurrency for better performance"
      ];
    } else if (code === 'SECRETS_MANAGER_ERROR') {
      response.troubleshooting.aws_specific = [
        "1. Verify Lambda execution role has SecretsManager permissions",
        "2. Check that the secret ARN is correct and accessible",
        "3. Ensure the secret is in the same region as the Lambda function"
      ];
    } else if (code === 'DB_CONNECTION_ERROR' || code === 'CONNECTION_ERROR') {
      response.troubleshooting.aws_specific = [
        "1. Verify RDS instance is running and accessible",
        "2. Check VPC configuration and security groups",
        "3. Ensure Lambda is in the same VPC as the database",
        "4. Verify database credentials in AWS Secrets Manager"
      ];
    }
  }

  res.status(status).json(response);
};

module.exports = errorHandler;

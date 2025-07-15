/**
 * Standardized API Response Formatter
 * Ensures consistent response structure across all API endpoints
 */

/**
 * Standard API response structure
 */
const createResponse = (success, data = null, error = null, metadata = {}) => {
  const response = {
    success,
    timestamp: new Date().toISOString(),
    ...metadata
  };

  if (success && data !== null) {
    response.data = data;
  }

  if (!success && error) {
    if (typeof error === 'string') {
      response.error = error;
    } else {
      response.error = error.message || 'An error occurred';
      if (error.details) response.details = error.details;
      if (error.code) response.code = error.code;
    }
  }

  return response;
};

/**
 * Success response formatters
 */
const success = (data, metadata = {}) => {
  return createResponse(true, data, null, metadata);
};

const successWithPagination = (data, pagination, metadata = {}) => {
  return createResponse(true, data, null, {
    pagination,
    ...metadata
  });
};

const successEmpty = (message = 'Operation completed successfully', metadata = {}) => {
  return createResponse(true, { message }, null, metadata);
};

/**
 * Error response formatters
 */
const error = (message, statusCode = 500, details = null, code = null) => {
  const errorObj = { message };
  if (details) errorObj.details = details;
  if (code) errorObj.code = code;
  
  return {
    response: createResponse(false, null, errorObj),
    statusCode
  };
};

const badRequest = (message, details = null) => {
  return error(message, 400, details, 'BAD_REQUEST');
};

const unauthorized = (message = 'Authentication required', details = null) => {
  return error(message, 401, details, 'UNAUTHORIZED');
};

const forbidden = (message = 'Access denied', details = null) => {
  return error(message, 403, details, 'FORBIDDEN');
};

const notFound = (resource = 'Resource', details = null) => {
  return error(`${resource} not found`, 404, details, 'NOT_FOUND');
};

const conflict = (message, details = null) => {
  return error(message, 409, details, 'CONFLICT');
};

const validationError = (errors) => {
  const details = Array.isArray(errors) ? errors : [errors];
  return error('Validation failed', 400, details, 'VALIDATION_ERROR');
};

const serverError = (message = 'Internal server error', details = null) => {
  return error(message, 500, details, 'SERVER_ERROR');
};

const serviceUnavailable = (service = 'Service', details = null) => {
  return error(`${service} temporarily unavailable`, 503, details, 'SERVICE_UNAVAILABLE');
};

const rateLimitExceeded = (retryAfter = null) => {
  const details = retryAfter ? `Retry after ${retryAfter} seconds` : null;
  return error('Rate limit exceeded', 429, details, 'RATE_LIMIT_EXCEEDED');
};

/**
 * Database error handler
 */
const databaseError = (dbError, context = '') => {
  console.error(`Database error ${context}:`, dbError);
  
  // Don't expose internal database errors in production
  if (process.env.NODE_ENV === 'production') {
    return serverError('Database operation failed');
  }
  
  return serverError('Database error', {
    context,
    error: dbError.message,
    code: dbError.code
  });
};

/**
 * External API error handler
 */
const externalApiError = (apiError, service = 'External service', context = '') => {
  console.error(`${service} API error ${context}:`, apiError);
  
  const statusCode = apiError.response?.status || 500;
  const message = apiError.response?.data?.message || apiError.message || `${service} error`;
  
  return error(message, statusCode, {
    service,
    context,
    originalError: process.env.NODE_ENV === 'development' ? apiError.message : undefined
  }, 'EXTERNAL_API_ERROR');
};

/**
 * Validation middleware error handler
 */
const handleValidationError = (validationErrors) => {
  return validationError(validationErrors);
};

/**
 * Authentication error handler
 */
const authenticationError = (authError) => {
  if (authError.name === 'TokenExpiredError') {
    return unauthorized('Token expired', 'Please log in again');
  }
  
  if (authError.name === 'JsonWebTokenError') {
    return unauthorized('Invalid token', 'Authentication failed');
  }
  
  if (authError.name === 'NotBeforeError') {
    return unauthorized('Token not active', 'Token is not yet valid');
  }
  
  return unauthorized(authError.message || 'Authentication failed');
};

/**
 * Financial data specific formatters
 */
const financialSuccess = (data, dataSource = 'database', provider = null, metadata = {}) => {
  return success(data, {
    dataSource,
    provider,
    ...metadata
  });
};

const portfolioSuccess = (data, accountType = null, lastSync = null, metadata = {}) => {
  return success(data, {
    accountType,
    lastSync,
    ...metadata
  });
};

const tradingSuccess = (data, environment = 'paper', broker = null, metadata = {}) => {
  return success(data, {
    environment,
    broker,
    ...metadata
  });
};

/**
 * Express middleware to add response formatters to res object
 */
const responseFormatterMiddleware = (req, res, next) => {
  // Add success formatters
  res.success = (data, metadata) => {
    return res.json(success(data, metadata));
  };
  
  res.successWithPagination = (data, pagination, metadata) => {
    return res.json(successWithPagination(data, pagination, metadata));
  };
  
  res.successEmpty = (message, metadata) => {
    return res.json(successEmpty(message, metadata));
  };
  
  // Add error formatters that automatically set status and send response
  res.error = (message, statusCode, details, code) => {
    const result = error(message, statusCode, details, code);
    return res.status(result.statusCode).json(result.response);
  };
  
  res.badRequest = (message, details) => {
    const result = badRequest(message, details);
    return res.status(result.statusCode).json(result.response);
  };
  
  res.unauthorized = (message, details) => {
    const result = unauthorized(message, details);
    return res.status(result.statusCode).json(result.response);
  };
  
  res.forbidden = (message, details) => {
    const result = forbidden(message, details);
    return res.status(result.statusCode).json(result.response);
  };
  
  res.notFound = (resource, details) => {
    const result = notFound(resource, details);
    return res.status(result.statusCode).json(result.response);
  };
  
  res.validationError = (errors) => {
    const result = validationError(errors);
    return res.status(result.statusCode).json(result.response);
  };
  
  res.serverError = (message, details) => {
    const result = serverError(message, details);
    return res.status(result.statusCode).json(result.response);
  };
  
  res.serviceUnavailable = (service, details) => {
    const result = serviceUnavailable(service, details);
    return res.status(result.statusCode).json(result.response);
  };
  
  res.databaseError = (dbError, context) => {
    const result = databaseError(dbError, context);
    return res.status(result.statusCode).json(result.response);
  };
  
  res.externalApiError = (apiError, service, context) => {
    const result = externalApiError(apiError, service, context);
    return res.status(result.statusCode).json(result.response);
  };
  
  // Financial-specific formatters
  res.financialSuccess = (data, dataSource, provider, metadata) => {
    return res.json(financialSuccess(data, dataSource, provider, metadata));
  };
  
  res.portfolioSuccess = (data, accountType, lastSync, metadata) => {
    return res.json(portfolioSuccess(data, accountType, lastSync, metadata));
  };
  
  res.tradingSuccess = (data, environment, broker, metadata) => {
    return res.json(tradingSuccess(data, environment, broker, metadata));
  };
  
  next();
};

module.exports = {
  // Core formatters
  success,
  successWithPagination,
  successEmpty,
  error,
  
  // HTTP status formatters
  badRequest,
  unauthorized,
  forbidden,
  notFound,
  conflict,
  validationError,
  serverError,
  serviceUnavailable,
  rateLimitExceeded,
  
  // Specialized error handlers
  databaseError,
  externalApiError,
  authenticationError,
  handleValidationError,
  
  // Financial-specific formatters
  financialSuccess,
  portfolioSuccess,
  tradingSuccess,
  
  // Express middleware
  responseFormatterMiddleware
};
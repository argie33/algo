/**
 * Comprehensive Error Handling Middleware
 * Intercepts all errors in the webapp and provides detailed diagnostics
 */

const comprehensiveErrorHandler = require('../utils/comprehensiveErrorHandler');

/**
 * Global error handler middleware
 */
const globalErrorHandler = (error, req, res, next) => {
    // Skip if response already sent
    if (res.headersSent) {
        return next(error);
    }

    // Add request context
    const context = {
        method: req.method,
        url: req.originalUrl,
        userAgent: req.get('User-Agent'),
        ip: req.ip,
        timestamp: new Date().toISOString(),
        headers: req.headers,
        body: req.body,
        params: req.params,
        query: req.query,
        user: req.user ? { id: req.user.id, email: req.user.email } : null
    };

    // Handle the error comprehensively
    const errorResponse = comprehensiveErrorHandler.handleError(error, context);
    
    // Determine appropriate HTTP status
    const statusCode = getHttpStatusCode(errorResponse);
    
    // Send comprehensive error response
    res.status(statusCode).json({
        success: false,
        error: {
            id: errorResponse.errorId,
            message: errorResponse.message,
            category: errorResponse.category,
            severity: errorResponse.severity,
            canRetry: errorResponse.canRecover,
            timestamp: new Date().toISOString(),
            ...(process.env.NODE_ENV === 'development' && {
                stack: error.stack,
                diagnostics: errorResponse.diagnostics
            })
        },
        meta: {
            requestId: req.id || 'unknown',
            method: req.method,
            url: req.originalUrl
        }
    });
};

/**
 * Async error wrapper for route handlers
 */
const asyncErrorHandler = (fn) => {
    return (req, res, next) => {
        Promise.resolve(fn(req, res, next)).catch(next);
    };
};

/**
 * Database error handler
 */
const databaseErrorHandler = (error, operation = 'database operation') => {
    const enhancedError = new Error(`Database ${operation} failed: ${error.message}`);
    enhancedError.originalError = error;
    enhancedError.operation = operation;
    enhancedError.category = 'DATABASE_ERROR';
    enhancedError.code = error.code;
    enhancedError.errno = error.errno;
    enhancedError.sqlState = error.sqlState;
    enhancedError.sqlMessage = error.sqlMessage;
    
    return enhancedError;
};

/**
 * API error handler
 */
const apiErrorHandler = (error, endpoint = 'unknown endpoint') => {
    const enhancedError = new Error(`API call to ${endpoint} failed: ${error.message}`);
    enhancedError.originalError = error;
    enhancedError.endpoint = endpoint;
    enhancedError.category = 'API_ERROR';
    enhancedError.statusCode = error.response?.status;
    enhancedError.responseData = error.response?.data;
    
    return enhancedError;
};

/**
 * Validation error handler
 */
const validationErrorHandler = (validationResult, field = 'input') => {
    const errors = validationResult.array ? validationResult.array() : [validationResult];
    const errorMessages = errors.map(err => `${err.param}: ${err.msg}`).join(', ');
    
    const enhancedError = new Error(`Validation failed for ${field}: ${errorMessages}`);
    enhancedError.category = 'VALIDATION_ERROR';
    enhancedError.validationErrors = errors;
    enhancedError.field = field;
    
    return enhancedError;
};

/**
 * Authentication error handler
 */
const authErrorHandler = (message = 'Authentication failed', code = 'AUTH_FAILED') => {
    const enhancedError = new Error(message);
    enhancedError.category = 'AUTH_ERROR';
    enhancedError.authCode = code;
    
    return enhancedError;
};

/**
 * Network error handler
 */
const networkErrorHandler = (error, service = 'external service') => {
    const enhancedError = new Error(`Network error connecting to ${service}: ${error.message}`);
    enhancedError.originalError = error;
    enhancedError.service = service;
    enhancedError.category = 'NETWORK_ERROR';
    enhancedError.code = error.code;
    enhancedError.errno = error.errno;
    
    return enhancedError;
};

/**
 * File system error handler
 */
const fileSystemErrorHandler = (error, operation = 'file operation') => {
    const enhancedError = new Error(`File system ${operation} failed: ${error.message}`);
    enhancedError.originalError = error;
    enhancedError.operation = operation;
    enhancedError.category = 'FILESYSTEM_ERROR';
    enhancedError.code = error.code;
    enhancedError.path = error.path;
    
    return enhancedError;
};

/**
 * Performance error handler
 */
const performanceErrorHandler = (operation, duration, threshold) => {
    const enhancedError = new Error(`Performance issue: ${operation} took ${duration}ms (threshold: ${threshold}ms)`);
    enhancedError.category = 'PERFORMANCE_ERROR';
    enhancedError.operation = operation;
    enhancedError.duration = duration;
    enhancedError.threshold = threshold;
    
    return enhancedError;
};

/**
 * Configuration error handler
 */
const configErrorHandler = (configKey, message = 'Configuration error') => {
    const enhancedError = new Error(`${message}: ${configKey}`);
    enhancedError.category = 'CONFIG_ERROR';
    enhancedError.configKey = configKey;
    
    return enhancedError;
};

/**
 * Circuit breaker error handler
 */
const circuitBreakerErrorHandler = (service, state) => {
    const enhancedError = new Error(`Circuit breaker ${state} for service: ${service}`);
    enhancedError.category = 'CIRCUIT_BREAKER_ERROR';
    enhancedError.service = service;
    enhancedError.state = state;
    
    return enhancedError;
};

/**
 * Get appropriate HTTP status code for error category
 */
function getHttpStatusCode(errorResponse) {
    const statusMap = {
        'AUTH_ERROR': 401,
        'VALIDATION_ERROR': 400,
        'NETWORK_ERROR': 503,
        'API_ERROR': 502,
        'DATABASE_ERROR': 503,
        'PERFORMANCE_ERROR': 503,
        'CONFIG_ERROR': 500,
        'FILESYSTEM_ERROR': 500,
        'CIRCUIT_BREAKER_ERROR': 503,
        'UNKNOWN_ERROR': 500
    };

    return statusMap[errorResponse.category] || 500;
}

/**
 * Error monitoring middleware
 */
const errorMonitoringMiddleware = (req, res, next) => {
    // Track response time
    const startTime = Date.now();
    
    // Override res.json to capture response details
    const originalJson = res.json;
    res.json = function(body) {
        const duration = Date.now() - startTime;
        
        // Log slow responses
        if (duration > 5000) {
            const performanceError = performanceErrorHandler(
                `${req.method} ${req.originalUrl}`,
                duration,
                5000
            );
            comprehensiveErrorHandler.handleError(performanceError, {
                method: req.method,
                url: req.originalUrl,
                duration,
                statusCode: res.statusCode
            });
        }
        
        // Log error responses
        if (res.statusCode >= 400) {
            comprehensiveErrorHandler.logger.warn('Error Response', {
                method: req.method,
                url: req.originalUrl,
                statusCode: res.statusCode,
                duration,
                body: body
            });
        }
        
        return originalJson.call(this, body);
    };
    
    next();
};

/**
 * Health check error handler
 */
const healthCheckErrorHandler = (checks) => {
    const failedChecks = checks.filter(check => !check.healthy);
    
    if (failedChecks.length > 0) {
        const enhancedError = new Error(`Health check failed: ${failedChecks.map(c => c.name).join(', ')}`);
        enhancedError.category = 'HEALTH_CHECK_ERROR';
        enhancedError.failedChecks = failedChecks;
        
        return enhancedError;
    }
    
    return null;
};

module.exports = {
    globalErrorHandler,
    asyncErrorHandler,
    databaseErrorHandler,
    apiErrorHandler,
    validationErrorHandler,
    authErrorHandler,
    networkErrorHandler,
    fileSystemErrorHandler,
    performanceErrorHandler,
    configErrorHandler,
    circuitBreakerErrorHandler,
    errorMonitoringMiddleware,
    healthCheckErrorHandler
};
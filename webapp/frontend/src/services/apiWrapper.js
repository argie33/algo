/**
 * API Wrapper - Comprehensive logging and error handling for all API calls
 * Provides consistent error handling, logging, and monitoring across all API functions
 */

import ErrorManager from '../error/ErrorManager';

class ApiWrapper {
  constructor() {
    this.requestCount = 0;
    this.performanceMetrics = new Map();
    this.errorPatterns = new Map();
  }

  /**
   * Wrap any API function with comprehensive logging and error handling
   */
  wrap(apiFunction, metadata = {}) {
    const { 
      operation = apiFunction.name || 'unknown_operation',
      category = ErrorManager.CATEGORIES.API,
      validateInput = null,
      transformResponse = null,
      retryable = true,
      cacheable = false
    } = metadata;

    return async (...args) => {
      const requestId = `req_${++this.requestCount}_${Date.now()}`;
      const startTime = performance.now();
      
      try {
        // Input validation
        if (validateInput) {
          const validationResult = validateInput(...args);
          if (!validationResult.valid) {
            throw new Error(`Input validation failed: ${validationResult.message}`);
          }
        }

        // Log request start
        this.logRequestStart(operation, requestId, args, category);

        // Execute the API function
        const result = await apiFunction(...args);
        
        // Calculate performance metrics
        const duration = performance.now() - startTime;
        this.recordPerformanceMetric(operation, duration);

        // Transform response if needed
        const finalResult = transformResponse ? transformResponse(result) : result;

        // Log successful completion
        this.logRequestSuccess(operation, requestId, duration, finalResult, category);

        return finalResult;

      } catch (error) {
        const duration = performance.now() - startTime;
        
        // Enhanced error handling
        const enhancedError = this.handleApiError(error, {
          operation,
          requestId,
          duration,
          args,
          category,
          retryable
        });

        // Record error patterns
        this.recordErrorPattern(operation, error);

        throw enhancedError;
      }
    };
  }

  /**
   * Log request start with context
   */
  logRequestStart(operation, requestId, args, category = null) {
    const sanitizedArgs = this.sanitizeArgs(args);
    
    console.log(`🚀 [API] ${operation} started`, {
      requestId,
      timestamp: new Date().toISOString(),
      args: sanitizedArgs,
      requestCount: this.requestCount
    });

    // Track for monitoring
    ErrorManager.handleError({
      type: 'api_request_started',
      message: `API request ${operation} initiated`,
      category: category || ErrorManager.CATEGORIES.API,
      severity: ErrorManager.SEVERITY.LOW,
      context: {
        operation,
        requestId,
        argCount: args.length,
        requestNumber: this.requestCount
      }
    });
  }

  /**
   * Log successful request completion
   */
  logRequestSuccess(operation, requestId, duration, result, category = null) {
    const responseSize = this.calculateResponseSize(result);
    
    console.log(`✅ [API] ${operation} completed successfully`, {
      requestId,
      duration: `${duration.toFixed(2)}ms`,
      responseSize,
      timestamp: new Date().toISOString()
    });

    // Performance tracking
    if (duration > 5000) { // Slow requests
      ErrorManager.handleError({
        type: 'slow_api_request',
        message: `Slow API request detected: ${operation} took ${duration}ms`,
        category: ErrorManager.CATEGORIES.PERFORMANCE,
        severity: ErrorManager.SEVERITY.MEDIUM,
        context: {
          operation,
          requestId,
          duration,
          responseSize
        }
      });
    }

    // Success tracking
    ErrorManager.handleError({
      type: 'api_request_completed',
      message: `API request ${operation} completed successfully`,
      category: category || ErrorManager.CATEGORIES.API,
      severity: ErrorManager.SEVERITY.LOW,
      context: {
        operation,
        requestId,
        duration,
        responseSize,
        performanceGrade: this.getPerformanceGrade(duration)
      }
    });
  }

  /**
   * Enhanced error handling for API requests
   */
  handleApiError(error, context) {
    const { operation, requestId, duration, args, category, retryable } = context;
    
    console.error(`❌ [API] ${operation} failed`, {
      requestId,
      duration: `${duration.toFixed(2)}ms`,
      error: error.message,
      status: error.response?.status,
      statusText: error.response?.statusText,
      timestamp: new Date().toISOString()
    });

    // Determine error severity based on status code and operation
    let severity = ErrorManager.SEVERITY.MEDIUM;
    if (error.response?.status >= 500) {
      severity = ErrorManager.SEVERITY.HIGH;
    } else if (error.response?.status === 401 || error.response?.status === 403) {
      severity = ErrorManager.SEVERITY.HIGH;
    } else if (error.response?.status === 404) {
      severity = ErrorManager.SEVERITY.LOW;
    }

    // Create enhanced error with comprehensive context
    const enhancedError = ErrorManager.handleError({
      type: 'api_request_failed',
      message: `${operation} failed: ${error.message}`,
      error: error,
      category: category,
      severity: severity,
      context: {
        operation,
        requestId,
        duration,
        status: error.response?.status,
        statusText: error.response?.statusText,
        url: error.config?.url,
        method: error.config?.method,
        responseData: error.response?.data,
        requestData: this.sanitizeArgs(args),
        retryable,
        userAgent: navigator.userAgent,
        networkStatus: navigator.onLine ? 'online' : 'offline'
      }
    });

    // Add user-friendly messages based on error type
    this.addUserFriendlyMessage(enhancedError, error);

    // Add suggested actions
    this.addSuggestedActions(enhancedError, error, operation);

    return enhancedError;
  }

  /**
   * Add user-friendly error messages
   */
  addUserFriendlyMessage(enhancedError, error) {
    const status = error.response?.status;
    const message = error.message?.toLowerCase() || '';

    if (!navigator.onLine) {
      enhancedError.userMessage = 'No internet connection. Please check your network and try again.';
    } else if (status === 400) {
      enhancedError.userMessage = 'Invalid request. Please check your input and try again.';
    } else if (status === 401) {
      enhancedError.userMessage = 'Please sign in to continue.';
    } else if (status === 403) {
      enhancedError.userMessage = 'You don\'t have permission to perform this action.';
    } else if (status === 404) {
      enhancedError.userMessage = 'The requested information was not found.';
    } else if (status === 429) {
      enhancedError.userMessage = 'Too many requests. Please wait a moment and try again.';
    } else if (status >= 500) {
      enhancedError.userMessage = 'Server error. Our team has been notified and is working on a fix.';
    } else if (message.includes('timeout')) {
      enhancedError.userMessage = 'Request timed out. Please check your connection and try again.';
    } else if (message.includes('network')) {
      enhancedError.userMessage = 'Network error. Please check your connection and try again.';
    } else {
      enhancedError.userMessage = 'An unexpected error occurred. Please try again.';
    }
  }

  /**
   * Add suggested actions based on error type
   */
  addSuggestedActions(enhancedError, error, operation) {
    const status = error.response?.status;
    const actions = [];

    if (!navigator.onLine) {
      actions.push('Check your internet connection');
      actions.push('Try again when connection is restored');
    } else if (status === 401) {
      actions.push('Sign in to your account');
      actions.push('Check if your session has expired');
    } else if (status === 403) {
      actions.push('Verify your account permissions');
      actions.push('Contact support if you believe this is an error');
    } else if (status === 404) {
      actions.push('Verify the requested resource exists');
      actions.push('Check your input parameters');
    } else if (status === 429) {
      actions.push('Wait a few moments before trying again');
      actions.push('Reduce the frequency of requests');
    } else if (status >= 500) {
      actions.push('Try again in a few minutes');
      actions.push('Contact support if the problem persists');
    } else {
      actions.push('Try refreshing the page');
      actions.push('Check your internet connection');
      actions.push('Contact support if the problem continues');
    }

    // Operation-specific suggestions
    if (operation.includes('portfolio') || operation.includes('holding')) {
      actions.push('Check your API key configuration');
      actions.push('Verify your brokerage account connection');
    } else if (operation.includes('market') || operation.includes('stock')) {
      actions.push('Verify market data subscription');
      actions.push('Check market hours if applicable');
    }

    enhancedError.suggestedActions = actions;
  }

  /**
   * Record performance metrics for monitoring
   */
  recordPerformanceMetric(operation, duration) {
    if (!this.performanceMetrics.has(operation)) {
      this.performanceMetrics.set(operation, {
        count: 0,
        totalTime: 0,
        minTime: Infinity,
        maxTime: 0,
        avgTime: 0
      });
    }

    const metrics = this.performanceMetrics.get(operation);
    metrics.count++;
    metrics.totalTime += duration;
    metrics.minTime = Math.min(metrics.minTime, duration);
    metrics.maxTime = Math.max(metrics.maxTime, duration);
    metrics.avgTime = metrics.totalTime / metrics.count;
  }

  /**
   * Record error patterns for analysis
   */
  recordErrorPattern(operation, error) {
    const errorKey = `${operation}:${error.response?.status || 'network'}`;
    const count = this.errorPatterns.get(errorKey) || 0;
    this.errorPatterns.set(errorKey, count + 1);

    // Alert on recurring error patterns
    if (count >= 3) {
      ErrorManager.handleError({
        type: 'error_pattern_detected',
        message: `Recurring error pattern detected: ${errorKey} (${count + 1} occurrences)`,
        category: ErrorManager.CATEGORIES.API,
        severity: ErrorManager.SEVERITY.HIGH,
        context: {
          operation,
          errorPattern: errorKey,
          occurrences: count + 1,
          lastError: error.message
        }
      });
    }
  }

  /**
   * Get performance grade based on duration
   */
  getPerformanceGrade(duration) {
    if (duration < 200) return 'excellent';
    if (duration < 500) return 'good';
    if (duration < 1000) return 'fair';
    if (duration < 2000) return 'slow';
    return 'very_slow';
  }

  /**
   * Calculate approximate response size
   */
  calculateResponseSize(response) {
    try {
      return JSON.stringify(response).length;
    } catch {
      return 'unknown';
    }
  }

  /**
   * Sanitize arguments for logging (remove sensitive data)
   */
  sanitizeArgs(args) {
    return args.map(arg => {
      if (typeof arg === 'object' && arg !== null) {
        const sanitized = { ...arg };
        
        // Remove sensitive fields
        const sensitiveFields = ['password', 'token', 'key', 'secret', 'apiKey', 'apiSecret'];
        sensitiveFields.forEach(field => {
          if (sanitized[field]) {
            sanitized[field] = '[REDACTED]';
          }
        });
        
        return sanitized;
      }
      return arg;
    });
  }

  /**
   * Get performance statistics
   */
  getPerformanceStats() {
    const stats = {};
    for (const [operation, metrics] of this.performanceMetrics) {
      stats[operation] = {
        ...metrics,
        avgTime: Math.round(metrics.avgTime),
        minTime: Math.round(metrics.minTime),
        maxTime: Math.round(metrics.maxTime)
      };
    }
    return stats;
  }

  /**
   * Get error pattern statistics
   */
  getErrorPatterns() {
    return Object.fromEntries(this.errorPatterns);
  }

  /**
   * Reset all statistics
   */
  resetStats() {
    this.performanceMetrics.clear();
    this.errorPatterns.clear();
    this.requestCount = 0;
  }
}

// Create singleton instance
const apiWrapper = new ApiWrapper();

export default apiWrapper;
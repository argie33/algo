/**
 * apiErrorHandler - Enhanced API error handling with retries and fallbacks
 * Integrates with ErrorManager for comprehensive error tracking
 */

import errorManager from './ErrorManager';

class ApiErrorHandler {
  constructor() {
    this.retryAttempts = new Map();
    this.maxRetries = 3;
    this.baseDelay = 1000;
    this.maxDelay = 10000;
  }

  /**
   * Enhanced fetch with comprehensive error handling
   */
  async fetch(url, options = {}) {
    const requestId = this.generateRequestId();
    const retryCount = this.retryAttempts.get(url) || 0;
    let timeoutId;

    try {
      // Add request tracking headers
      const enhancedOptions = {
        ...options,
        headers: {
          'Content-Type': 'application/json',
          'X-Request-ID': requestId,
          'X-Retry-Count': retryCount.toString(),
          ...options.headers
        }
      };

      // Add timeout
      const controller = new AbortController();
      timeoutId = setTimeout(() => controller.abort(), options.timeout || 30000);
      enhancedOptions.signal = controller.signal;

      const response = await fetch(url, enhancedOptions);
      clearTimeout(timeoutId);

      // Reset retry count on success
      this.retryAttempts.delete(url);

      // Handle different response status codes
      await this.handleResponse(response, url, requestId);

      return response;
    } catch (error) {
      if (timeoutId) {
        clearTimeout(timeoutId);
      }
      return this.handleError(error, url, requestId, options);
    }
  }

  /**
   * Handle HTTP response status codes
   */
  async handleResponse(response, url, requestId) {
    if (response.ok) {
      return response;
    }

    // Extract error details from response
    let errorDetails = {};
    try {
      const contentType = response.headers.get('content-type');
      if (contentType && contentType.includes('application/json')) {
        errorDetails = await response.json();
      } else {
        errorDetails = { message: await response.text() };
      }
    } catch (e) {
      errorDetails = { message: 'Unknown error' };
    }

    // Create structured error
    const error = new Error(errorDetails.message || `HTTP ${response.status}`);
    error.status = response.status;
    error.statusText = response.statusText;
    error.url = url;
    error.requestId = requestId;
    error.details = errorDetails;

    // Handle specific status codes
    switch (response.status) {
      case 400:
        this.handleBadRequest(error);
        break;
      case 401:
        this.handleUnauthorized(error);
        break;
      case 403:
        this.handleForbidden(error);
        break;
      case 404:
        this.handleNotFound(error);
        break;
      case 429:
        this.handleRateLimit(error);
        break;
      case 500:
      case 502:
      case 503:
      case 504:
        this.handleServerError(error);
        break;
      default:
        this.handleGenericError(error);
    }

    throw error;
  }

  /**
   * Handle errors during request
   */
  async handleError(error, url, requestId, originalOptions) {
    // Enhance error with context
    error.url = url;
    error.requestId = requestId;
    error.timestamp = new Date().toISOString();

    // Determine error category and severity
    let category = errorManager.CATEGORIES.API;
    let severity = errorManager.SEVERITY.MEDIUM;

    if (error.name === 'AbortError') {
      category = errorManager.CATEGORIES.NETWORK;
      error.message = 'Request timed out';
    } else if (error.message.includes('NetworkError') || error.message.includes('fetch')) {
      category = errorManager.CATEGORIES.NETWORK;
      severity = errorManager.SEVERITY.HIGH;
    }

    // Check if should retry
    const shouldRetry = this.shouldRetry(error, url);
    
    if (shouldRetry) {
      return this.retryRequest(url, originalOptions, error);
    }

    // Log error through error manager
    const managedError = errorManager.handleError({
      type: 'api_request',
      message: error.message,
      error: error,
      category,
      severity,
      context: {
        url,
        requestId,
        method: originalOptions.method || 'GET',
        retryCount: this.retryAttempts.get(url) || 0
      }
    });

    throw managedError;
  }

  /**
   * Determine if request should be retried
   */
  shouldRetry(error, url) {
    const retryCount = this.retryAttempts.get(url) || 0;
    
    // Don't retry if max attempts reached
    if (retryCount >= this.maxRetries) {
      return false;
    }

    // Don't retry client errors (4xx except 429)
    if (error.status >= 400 && error.status < 500 && error.status !== 429) {
      return false;
    }

    // Retry network errors and server errors
    if (error.name === 'AbortError' || 
        error.message.includes('NetworkError') || 
        error.message.includes('fetch') ||
        (error.status >= 500 && error.status < 600) ||
        error.status === 429) {
      return true;
    }

    return false;
  }

  /**
   * Retry request with exponential backoff
   */
  async retryRequest(url, options, originalError) {
    const retryCount = this.retryAttempts.get(url) || 0;
    this.retryAttempts.set(url, retryCount + 1);

    // Calculate delay with exponential backoff
    let delay = this.baseDelay * Math.pow(2, retryCount);
    
    // Add jitter to prevent thundering herd
    delay = delay + (Math.random() * 1000);
    
    // Cap the delay
    delay = Math.min(delay, this.maxDelay);

    // Special handling for rate limits
    if (originalError.status === 429) {
      const retryAfter = originalError.headers?.get('Retry-After');
      if (retryAfter) {
        delay = parseInt(retryAfter) * 1000;
      }
    }

    console.warn(`Retrying request to ${url} in ${delay}ms (attempt ${retryCount + 1}/${this.maxRetries})`);

    // Wait before retry
    await new Promise(resolve => setTimeout(resolve, delay));

    // Retry the request
    return this.fetch(url, options);
  }

  /**
   * Error handlers for specific status codes
   */
  handleBadRequest(error) {
    errorManager.handleError({
      type: 'bad_request',
      message: 'Invalid request data',
      error,
      category: errorManager.CATEGORIES.VALIDATION,
      severity: errorManager.SEVERITY.MEDIUM
    });
  }

  handleUnauthorized(error) {
    errorManager.handleError({
      type: 'unauthorized',
      message: 'Authentication required',
      error,
      category: errorManager.CATEGORIES.AUTH,
      severity: errorManager.SEVERITY.HIGH,
      recovery: errorManager.RECOVERY.REDIRECT,
      redirectUrl: '/login'
    });
  }

  handleForbidden(error) {
    errorManager.handleError({
      type: 'forbidden',
      message: 'Access denied',
      error,
      category: errorManager.CATEGORIES.AUTH,
      severity: errorManager.SEVERITY.HIGH
    });
  }

  handleNotFound(error) {
    errorManager.handleError({
      type: 'not_found',
      message: 'Resource not found',
      error,
      category: errorManager.CATEGORIES.API,
      severity: errorManager.SEVERITY.LOW
    });
  }

  handleRateLimit(error) {
    errorManager.handleError({
      type: 'rate_limit',
      message: 'Too many requests - please slow down',
      error,
      category: errorManager.CATEGORIES.API,
      severity: errorManager.SEVERITY.MEDIUM,
      recovery: errorManager.RECOVERY.RETRY
    });
  }

  handleServerError(error) {
    errorManager.handleError({
      type: 'server_error',
      message: 'Server error - please try again later',
      error,
      category: errorManager.CATEGORIES.API,
      severity: errorManager.SEVERITY.HIGH,
      recovery: errorManager.RECOVERY.RETRY
    });
  }

  handleGenericError(error) {
    errorManager.handleError({
      type: 'api_error',
      message: error.message || 'API request failed',
      error,
      category: errorManager.CATEGORIES.API,
      severity: errorManager.SEVERITY.MEDIUM
    });
  }

  /**
   * Utility methods
   */
  generateRequestId() {
    return 'req_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
  }

  /**
   * Get retry statistics
   */
  getRetryStats() {
    return {
      activeRetries: this.retryAttempts.size,
      retryUrls: Array.from(this.retryAttempts.keys())
    };
  }

  /**
   * Clear retry history
   */
  clearRetryHistory() {
    this.retryAttempts.clear();
  }
}

// Create singleton instance
const apiErrorHandler = new ApiErrorHandler();

// Helper functions for common API operations
export const enhancedFetch = (url, options = {}) => {
  return apiErrorHandler.fetch(url, options);
};

export const get = (url, options = {}) => {
  return enhancedFetch(url, { ...options, method: 'GET' });
};

export const post = (url, data, options = {}) => {
  return enhancedFetch(url, {
    ...options,
    method: 'POST',
    body: JSON.stringify(data)
  });
};

export const put = (url, data, options = {}) => {
  return enhancedFetch(url, {
    ...options,
    method: 'PUT',
    body: JSON.stringify(data)
  });
};

export const del = (url, options = {}) => {
  return enhancedFetch(url, { ...options, method: 'DELETE' });
};

export default apiErrorHandler;
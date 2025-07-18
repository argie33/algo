/**
 * Async Error Handler - Comprehensive error handling for promises and async operations
 * Provides circuit breaker patterns, retry logic, and graceful degradation
 */

class AsyncErrorHandler {
  constructor() {
    this.errorCounts = new Map();
    this.circuitBreakers = new Map();
    this.retryQueues = new Map();
    
    // Default configuration
    this.config = {
      maxRetries: 3,
      retryDelay: 1000,
      circuitBreakerThreshold: 5,
      circuitBreakerTimeout: 30000,
      exponentialBackoff: true
    };

    // Global error handlers
    this.setupGlobalErrorHandlers();
  }

  setupGlobalErrorHandlers() {
    // Catch unhandled promise rejections
    window.addEventListener('unhandledrejection', (event) => {
      console.error('🚨 Unhandled promise rejection:', event.reason);
      this.reportError('unhandledRejection', event.reason);
      
      // Prevent the default browser error handling
      event.preventDefault();
    });

    // Catch global errors
    window.addEventListener('error', (event) => {
      console.error('🚨 Global error:', event.error);
      this.reportError('globalError', event.error);
    });
  }

  /**
   * Wrap an async function with comprehensive error handling
   */
  wrapAsync(fn, options = {}) {
    const config = { ...this.config, ...options };
    const fnName = fn.name || 'anonymous';

    return async (...args) => {
      const startTime = Date.now();
      
      try {
        // Check circuit breaker
        if (this.isCircuitOpen(fnName)) {
          throw new Error(`Circuit breaker is open for ${fnName}`);
        }

        const result = await this.executeWithRetry(fn, args, config);
        
        // Reset error count on success
        this.resetErrorCount(fnName);
        
        return result;
      } catch (error) {
        const duration = Date.now() - startTime;
        this.handleError(fnName, error, duration, config);
        throw error;
      }
    };
  }

  /**
   * Execute function with retry logic
   */
  async executeWithRetry(fn, args, config) {
    let lastError;
    
    for (let attempt = 0; attempt <= config.maxRetries; attempt++) {
      try {
        return await fn(...args);
      } catch (error) {
        lastError = error;
        
        if (attempt < config.maxRetries) {
          const delay = this.calculateDelay(attempt, config);
          console.warn(`⏳ Retry attempt ${attempt + 1} after ${delay}ms for ${fn.name}`);
          await this.sleep(delay);
        }
      }
    }
    
    throw lastError;
  }

  /**
   * Calculate retry delay with exponential backoff
   */
  calculateDelay(attempt, config) {
    if (!config.exponentialBackoff) {
      return config.retryDelay;
    }
    
    return Math.min(config.retryDelay * Math.pow(2, attempt), 10000);
  }

  /**
   * Sleep utility
   */
  sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  /**
   * Handle errors and update circuit breaker state
   */
  handleError(fnName, error, duration, config) {
    // Increment error count
    const currentCount = this.errorCounts.get(fnName) || 0;
    this.errorCounts.set(fnName, currentCount + 1);

    // Check if circuit breaker should open
    if (currentCount + 1 >= config.circuitBreakerThreshold) {
      this.openCircuitBreaker(fnName, config.circuitBreakerTimeout);
    }

    // Report error
    this.reportError(fnName, error, {
      duration,
      attempt: currentCount + 1,
      circuitBreakerOpen: this.isCircuitOpen(fnName)
    });
  }

  /**
   * Open circuit breaker
   */
  openCircuitBreaker(fnName, timeout) {
    console.warn(`🔴 Circuit breaker opened for ${fnName}`);
    
    this.circuitBreakers.set(fnName, {
      openedAt: Date.now(),
      timeout
    });

    // Automatically close after timeout
    setTimeout(() => {
      this.closeCircuitBreaker(fnName);
    }, timeout);
  }

  /**
   * Close circuit breaker
   */
  closeCircuitBreaker(fnName) {
    console.info(`🟢 Circuit breaker closed for ${fnName}`);
    this.circuitBreakers.delete(fnName);
    this.resetErrorCount(fnName);
  }

  /**
   * Check if circuit breaker is open
   */
  isCircuitOpen(fnName) {
    const breaker = this.circuitBreakers.get(fnName);
    if (!breaker) return false;

    const elapsed = Date.now() - breaker.openedAt;
    if (elapsed >= breaker.timeout) {
      this.closeCircuitBreaker(fnName);
      return false;
    }

    return true;
  }

  /**
   * Reset error count for a function
   */
  resetErrorCount(fnName) {
    this.errorCounts.set(fnName, 0);
  }

  /**
   * Report error to logging service
   */
  reportError(source, error, metadata = {}) {
    const errorReport = {
      timestamp: new Date().toISOString(),
      source,
      message: error?.message || String(error),
      stack: error?.stack,
      url: window.location.href,
      userAgent: navigator.userAgent,
      metadata
    };

    // Log to console
    console.group(`🚨 Error Report: ${source}`);
    console.error('Error:', error);
    console.log('Metadata:', metadata);
    console.log('Full Report:', errorReport);
    console.groupEnd();

    // Send to error reporting service in production
    if (process.env.NODE_ENV === 'production') {
      this.sendErrorReport(errorReport);
    }
  }

  /**
   * Send error report to backend
   */
  async sendErrorReport(errorReport) {
    try {
      await fetch('/api/errors', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(errorReport)
      });
    } catch (reportingError) {
      console.warn('Failed to send error report:', reportingError);
    }
  }

  /**
   * Get system health status
   */
  getHealthStatus() {
    const openCircuits = Array.from(this.circuitBreakers.keys());
    const errorCounts = Object.fromEntries(this.errorCounts);
    
    return {
      timestamp: new Date().toISOString(),
      openCircuitBreakers: openCircuits,
      errorCounts,
      healthScore: this.calculateHealthScore()
    };
  }

  /**
   * Calculate overall health score (0-100)
   */
  calculateHealthScore() {
    const openCircuits = this.circuitBreakers.size;
    const totalErrors = Array.from(this.errorCounts.values()).reduce((sum, count) => sum + count, 0);
    
    if (openCircuits > 0) return Math.max(0, 50 - (openCircuits * 10));
    if (totalErrors > 10) return Math.max(20, 100 - (totalErrors * 2));
    
    return 100;
  }
}

// Create singleton instance
const asyncErrorHandler = new AsyncErrorHandler();

// Export utilities
export default asyncErrorHandler;

export const withAsyncErrorHandling = (fn, options) => 
  asyncErrorHandler.wrapAsync(fn, options);

export const getSystemHealth = () => 
  asyncErrorHandler.getHealthStatus();

export const reportError = (source, error, metadata) => 
  asyncErrorHandler.reportError(source, error, metadata);
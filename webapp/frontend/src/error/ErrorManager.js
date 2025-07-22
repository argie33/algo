/**
 * ErrorManager - Central error handling and coordination system
 * Manages all error types, recovery strategies, and user feedback
 */

class ErrorManager {
  constructor() {
    this.errorCounts = new Map();
    this.errorHistory = [];
    this.maxHistorySize = 100;
    this.subscribers = new Set();
    this.isInitialized = false;
    
    // Error severity levels
    this.SEVERITY = {
      LOW: 'low',
      MEDIUM: 'medium', 
      HIGH: 'high',
      CRITICAL: 'critical'
    };

    // Error categories
    this.CATEGORIES = {
      NETWORK: 'network',
      API: 'api',
      AUTH: 'auth',
      VALIDATION: 'validation',
      UI: 'ui',
      WEBSOCKET: 'websocket',
      PERFORMANCE: 'performance'
    };

    // Recovery strategies
    this.RECOVERY = {
      RETRY: 'retry',
      FALLBACK: 'fallback',
      REDIRECT: 'redirect',
      RELOAD: 'reload',
      NONE: 'none'
    };
  }

  /**
   * Initialize the error manager
   */
  initialize() {
    if (this.isInitialized) return;

    // Global error handlers
    this.setupGlobalHandlers();
    
    // Performance monitoring
    this.setupPerformanceMonitoring();
    
    // Network monitoring
    this.setupNetworkMonitoring();
    
    this.isInitialized = true;
    console.log('🛡️ ErrorManager initialized');
  }

  /**
   * Setup global error handlers
   */
  setupGlobalHandlers() {
    // Unhandled JavaScript errors
    if (typeof window !== 'undefined') {
      window.addEventListener('error', (event) => {
        this.handleError({
          type: 'javascript',
          message: event.message,
          filename: event.filename,
          lineno: event.lineno,
          colno: event.colno,
          error: event.error,
          category: this.CATEGORIES.UI,
          severity: this.SEVERITY.MEDIUM
        });
      });

      // Unhandled promise rejections
      window.addEventListener('unhandledrejection', (event) => {
        this.handleError({
          type: 'unhandled_promise',
          message: event.reason?.message || 'Unhandled promise rejection',
          error: event.reason,
          category: this.CATEGORIES.API,
          severity: this.SEVERITY.HIGH
        });
      });

      // Resource loading errors
      window.addEventListener('error', (event) => {
        if (event.target !== window) {
          this.handleError({
            type: 'resource',
            message: `Failed to load resource: ${event.target.src || event.target.href}`,
            resource: event.target.tagName,
            category: this.CATEGORIES.NETWORK,
            severity: this.SEVERITY.LOW
          });
        }
      }, true);
    }
  }

  /**
   * Setup performance monitoring
   */
  setupPerformanceMonitoring() {
    if (typeof window !== 'undefined' && 'PerformanceObserver' in window) {
      // Monitor long tasks
      try {
        const longTaskObserver = new PerformanceObserver((list) => {
          for (const entry of list.getEntries()) {
            if (entry.duration > 50) { // Tasks longer than 50ms
              this.handleError({
                type: 'performance',
                message: `Long task detected: ${entry.duration}ms`,
                duration: entry.duration,
                category: this.CATEGORIES.PERFORMANCE,
                severity: this.SEVERITY.LOW
              });
            }
          }
        });
        longTaskObserver.observe({ entryTypes: ['longtask'] });
      } catch (e) {
        // Long task observer not supported
      }

      // Monitor layout shifts
      try {
        const clsObserver = new PerformanceObserver((list) => {
          for (const entry of list.getEntries()) {
            if (entry.value > 0.1) { // CLS threshold
              this.handleError({
                type: 'layout_shift',
                message: `Cumulative Layout Shift detected: ${entry.value}`,
                value: entry.value,
                category: this.CATEGORIES.PERFORMANCE,
                severity: this.SEVERITY.LOW
              });
            }
          }
        });
        clsObserver.observe({ entryTypes: ['layout-shift'] });
      } catch (e) {
        // Layout shift observer not supported
      }
    }
  }

  /**
   * Setup network monitoring
   */
  setupNetworkMonitoring() {
    if (typeof window !== 'undefined') {
      // Online/offline detection
      window.addEventListener('online', () => {
        this.notifySubscribers({
          type: 'network_status',
          online: true,
          message: 'Connection restored'
        });
      });

      window.addEventListener('offline', () => {
        this.handleError({
          type: 'network',
          message: 'Network connection lost',
          category: this.CATEGORIES.NETWORK,
          severity: this.SEVERITY.HIGH,
          recovery: this.RECOVERY.RETRY
        });
      });
    }
  }

  /**
   * Main error handling method
   */
  handleError(errorInfo) {
    // Enhance error with additional context
    const enhancedError = this.enhanceError(errorInfo);
    
    // Add to history
    this.addToHistory(enhancedError);
    
    // Update error counts
    this.updateErrorCounts(enhancedError);
    
    // Determine recovery strategy
    const recoveryStrategy = this.determineRecoveryStrategy(enhancedError);
    enhancedError.recovery = recoveryStrategy;
    
    // Log the error
    this.logError(enhancedError);
    
    // Notify subscribers
    this.notifySubscribers(enhancedError);
    
    // Execute recovery if automatic
    if (recoveryStrategy && enhancedError.autoRecover !== false) {
      this.executeRecovery(enhancedError);
    }
    
    return enhancedError;
  }

  /**
   * Enhance error with additional context
   */
  enhanceError(errorInfo) {
    const timestamp = new Date().toISOString();
    const errorId = this.generateErrorId();
    
    return {
      id: errorId,
      timestamp,
      url: typeof window !== 'undefined' ? window.location.href : 'unknown',
      userAgent: typeof navigator !== 'undefined' ? navigator.userAgent : 'unknown',
      stackTrace: errorInfo.error?.stack || new Error().stack,
      sessionId: this.getSessionId(),
      userId: this.getUserId(),
      buildVersion: import.meta.env.VITE_BUILD_VERSION || 'unknown',
      ...errorInfo
    };
  }

  /**
   * Add error to history
   */
  addToHistory(error) {
    this.errorHistory.unshift(error);
    if (this.errorHistory.length > this.maxHistorySize) {
      this.errorHistory.pop();
    }
  }

  /**
   * Update error counts for pattern detection
   */
  updateErrorCounts(error) {
    const key = `${error.category}:${error.type}`;
    const count = this.errorCounts.get(key) || 0;
    this.errorCounts.set(key, count + 1);
    
    // Check for error patterns
    if (count > 5) {
      this.handleError({
        type: 'pattern_detected',
        message: `Repeated error pattern detected: ${key}`,
        pattern: key,
        count: count,
        category: this.CATEGORIES.UI,
        severity: this.SEVERITY.HIGH
      });
    }
  }

  /**
   * Determine recovery strategy based on error
   */
  determineRecoveryStrategy(error) {
    // Network errors
    if (error.category === this.CATEGORIES.NETWORK) {
      return this.RECOVERY.RETRY;
    }
    
    // API errors
    if (error.category === this.CATEGORIES.API) {
      if (error.status === 401 || error.status === 403) {
        return this.RECOVERY.REDIRECT;
      }
      if (error.status >= 500) {
        return this.RECOVERY.RETRY;
      }
      return this.RECOVERY.FALLBACK;
    }
    
    // Auth errors
    if (error.category === this.CATEGORIES.AUTH) {
      return this.RECOVERY.REDIRECT;
    }
    
    // Critical UI errors
    if (error.category === this.CATEGORIES.UI && error.severity === this.SEVERITY.CRITICAL) {
      return this.RECOVERY.RELOAD;
    }
    
    return this.RECOVERY.NONE;
  }

  /**
   * Execute recovery strategy
   */
  executeRecovery(error) {
    switch (error.recovery) {
      case this.RECOVERY.RETRY:
        this.scheduleRetry(error);
        break;
        
      case this.RECOVERY.FALLBACK:
        this.activateFallback(error);
        break;
        
      case this.RECOVERY.REDIRECT:
        this.handleRedirect(error);
        break;
        
      case this.RECOVERY.RELOAD:
        this.scheduleReload(error);
        break;
    }
  }

  /**
   * Schedule retry with exponential backoff
   */
  scheduleRetry(error, attempt = 1, maxAttempts = 3) {
    if (attempt > maxAttempts) {
      console.warn('Max retry attempts reached for error:', error.id);
      return;
    }
    
    const delay = Math.min(1000 * Math.pow(2, attempt - 1), 10000);
    
    setTimeout(() => {
      if (error.retryCallback) {
        error.retryCallback()
          .catch(() => {
            this.scheduleRetry(error, attempt + 1, maxAttempts);
          });
      }
    }, delay);
  }

  /**
   * Activate fallback mechanisms
   */
  activateFallback(error) {
    if (error.fallbackCallback) {
      error.fallbackCallback();
    }
  }

  /**
   * Handle redirect recovery
   */
  handleRedirect(error) {
    if (typeof window !== 'undefined') {
      const redirectUrl = error.redirectUrl || '/login';
      window.location.href = redirectUrl;
    }
  }

  /**
   * Schedule page reload
   */
  scheduleReload(error) {
    if (typeof window !== 'undefined') {
      setTimeout(() => {
        window.location.reload();
      }, 2000);
    }
  }

  /**
   * Log error appropriately
   */
  logError(error) {
    const logLevel = this.getLogLevel(error.severity);
    const logMessage = `[${(error.category || 'UNKNOWN').toUpperCase()}] ${error.message}`;
    
    switch (logLevel) {
      case 'error':
        console.error(logMessage, error);
        break;
      case 'warn':
        console.warn(logMessage, error);
        break;
      case 'info':
        console.info(logMessage, error);
        break;
      default:
        console.log(logMessage, error);
    }
    
    // Send to external logging service in production
    if (import.meta.env.PROD && error.severity !== this.SEVERITY.LOW) {
      this.sendToExternalLogger(error);
    }
  }

  /**
   * Get appropriate log level
   */
  getLogLevel(severity) {
    switch (severity) {
      case this.SEVERITY.CRITICAL:
      case this.SEVERITY.HIGH:
        return 'error';
      case this.SEVERITY.MEDIUM:
        return 'warn';
      case this.SEVERITY.LOW:
        return 'info';
      default:
        return 'log';
    }
  }

  /**
   * Send to external logging service
   */
  sendToExternalLogger(error) {
    // Implementation depends on your logging service
    // Examples: DataDog, Sentry, LogRocket, etc.
    try {
      fetch('/api/logs/error', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(error)
      }).catch(() => {
        // Ignore logging errors to prevent infinite loops
      });
    } catch (e) {
      // Ignore logging errors
    }
  }

  /**
   * Subscribe to error events
   */
  subscribe(callback) {
    this.subscribers.add(callback);
    return () => this.subscribers.delete(callback);
  }

  /**
   * Notify all subscribers
   */
  notifySubscribers(error) {
    this.subscribers.forEach(callback => {
      try {
        callback(error);
      } catch (e) {
        console.error('Error in error subscriber:', e);
      }
    });
  }

  /**
   * Get error statistics
   */
  getStats() {
    const totalErrors = this.errorHistory.length;
    const errorsByCategory = {};
    const errorsBySeverity = {};
    
    this.errorHistory.forEach(error => {
      errorsByCategory[error.category] = (errorsByCategory[error.category] || 0) + 1;
      errorsBySeverity[error.severity] = (errorsBySeverity[error.severity] || 0) + 1;
    });
    
    return {
      totalErrors,
      errorsByCategory,
      errorsBySeverity,
      patterns: Object.fromEntries(this.errorCounts),
      lastError: this.errorHistory[0] || null
    };
  }

  /**
   * Clear error history
   */
  clearHistory() {
    this.errorHistory = [];
    this.errorCounts.clear();
  }

  /**
   * Utility methods
   */
  generateErrorId() {
    return 'err_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
  }

  getSessionId() {
    if (typeof window !== 'undefined') {
      let sessionId = sessionStorage.getItem('session_id');
      if (!sessionId) {
        sessionId = 'sess_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
        sessionStorage.setItem('session_id', sessionId);
      }
      return sessionId;
    }
    return 'unknown';
  }

  getUserId() {
    // This should be implemented based on your auth system
    if (typeof window !== 'undefined') {
      return localStorage.getItem('user_id') || 'anonymous';
    }
    return 'unknown';
  }
}

// Create singleton instance
const errorManager = new ErrorManager();

export default errorManager;
/**
 * Crypto Error Handler
 * 
 * Comprehensive error handling system for cryptocurrency operations
 * with user-friendly messages, recovery strategies, and fallback options
 */

class CryptoErrorHandler {
  constructor() {
    this.errorMap = {
      // Network and API Errors
      'NETWORK_ERROR': {
        title: 'Connection Problem',
        message: 'Unable to connect to cryptocurrency data providers. Please check your internet connection.',
        userAction: 'Check connection and retry',
        icon: 'wifi_off',
        severity: 'warning',
        category: 'network',
        recoverable: true,
        retryAfter: 5000
      },
      
      'API_ERROR': {
        title: 'Data Service Unavailable',
        message: 'Our cryptocurrency data provider is experiencing issues. We\'re working to restore service.',
        userAction: 'Try again in a few minutes',
        icon: 'cloud_off',
        severity: 'error',
        category: 'api',
        recoverable: true,
        retryAfter: 30000
      },
      
      'TIMEOUT_ERROR': {
        title: 'Request Timeout',
        message: 'The request is taking longer than expected. This might be due to high network traffic.',
        userAction: 'Please try again',
        icon: 'timer',
        severity: 'warning',
        category: 'network',
        recoverable: true,
        retryAfter: 3000
      },
      
      'RATE_LIMIT_EXCEEDED': {
        title: 'Too Many Requests',
        message: 'You\'ve made too many requests in a short time. Please wait a moment before trying again.',
        userAction: 'Wait 30 seconds and retry',
        icon: 'speed',
        severity: 'warning',
        category: 'rate_limit',
        recoverable: true,
        retryAfter: 30000
      },

      // Data Errors
      'INVALID_SYMBOL': {
        title: 'Invalid Cryptocurrency',
        message: 'The cryptocurrency symbol you requested is not recognized or supported.',
        userAction: 'Check symbol and try again',
        icon: 'warning',
        severity: 'error',
        category: 'validation',
        recoverable: false
      },
      
      'NO_DATA_AVAILABLE': {
        title: 'No Data Available',
        message: 'No price data is currently available for this cryptocurrency.',
        userAction: 'Try a different cryptocurrency',
        icon: 'data_off',
        severity: 'warning',
        category: 'data',
        recoverable: false
      },
      
      'STALE_DATA': {
        title: 'Data May Be Outdated',
        message: 'The displayed data may not reflect current market conditions due to connectivity issues.',
        userAction: 'Data will update automatically',
        icon: 'schedule',
        severity: 'info',
        category: 'data',
        recoverable: true
      },

      // Trading Errors
      'PORTFOLIO_SYNC_FAILED': {
        title: 'Portfolio Sync Error',
        message: 'Unable to sync your portfolio with live market data. Your holdings are safe but prices may be outdated.',
        userAction: 'Refresh portfolio manually',
        icon: 'sync_problem',
        severity: 'warning',
        category: 'portfolio',
        recoverable: true,
        retryAfter: 10000
      },
      
      'PRICE_CALCULATION_ERROR': {
        title: 'Price Calculation Error',
        message: 'There was an error calculating portfolio values. Please refresh the page.',
        userAction: 'Refresh page',
        icon: 'calculate',
        severity: 'error',
        category: 'calculation',
        recoverable: true
      },

      // WebSocket Errors
      'WEBSOCKET_CONNECTION_FAILED': {
        title: 'Real-time Updates Unavailable',
        message: 'Unable to establish real-time price updates. You\'ll still see periodic updates.',
        userAction: 'Enable manual refresh',
        icon: 'sync_disabled',
        severity: 'warning',
        category: 'realtime',
        recoverable: true,
        retryAfter: 15000
      },
      
      'WEBSOCKET_DISCONNECTED': {
        title: 'Real-time Connection Lost',
        message: 'Live price updates have been interrupted. Attempting to reconnect automatically.',
        userAction: 'Connection will restore automatically',
        icon: 'signal_disconnected',
        severity: 'info',
        category: 'realtime',
        recoverable: true,
        retryAfter: 5000
      },

      // Server Errors
      'INTERNAL_SERVER_ERROR': {
        title: 'Server Error',
        message: 'Our servers are experiencing technical difficulties. Please try again later.',
        userAction: 'Try again in a few minutes',
        icon: 'error',
        severity: 'error',
        category: 'server',
        recoverable: true,
        retryAfter: 60000
      },
      
      'SERVICE_UNAVAILABLE': {
        title: 'Service Temporarily Unavailable',
        message: 'Our cryptocurrency service is temporarily down for maintenance.',
        userAction: 'Check back in a few minutes',
        icon: 'build',
        severity: 'error',
        category: 'maintenance',
        recoverable: true,
        retryAfter: 120000
      },

      // Exchange-specific Errors
      'EXCHANGE_API_ERROR': {
        title: 'Exchange Data Unavailable',
        message: 'One of our data sources is experiencing issues. We\'re using backup sources.',
        userAction: 'Data quality may be reduced',
        icon: 'swap_horiz',
        severity: 'warning',
        category: 'exchange',
        recoverable: true
      },
      
      'MULTIPLE_EXCHANGE_FAILURE': {
        title: 'Multiple Data Sources Down',
        message: 'Several cryptocurrency exchanges are experiencing issues. Data may be limited.',
        userAction: 'Check back later for full data',
        icon: 'error_outline',
        severity: 'error',
        category: 'exchange',
        recoverable: true,
        retryAfter: 300000
      }
    };

    this.fallbackData = {
      btc: { price: 45000, change: 0 },
      eth: { price: 2800, change: 0 },
      ada: { price: 0.35, change: 0 },
      dot: { price: 6.5, change: 0 }
    };

    this.errorHistory = [];
    this.maxHistorySize = 100;
  }

  /**
   * Get user-friendly error message and recovery options
   */
  handleError(error, context = {}) {
    console.error('🚨 Crypto Error Handler processing:', error);
    
    const errorInfo = this.classifyError(error);
    const errorDetails = this.errorMap[errorInfo.code] || this.getGenericError();
    
    // Record error for analytics
    this.recordError(error, errorInfo, context);
    
    // Enhanced error response
    const response = {
      ...errorDetails,
      code: errorInfo.code,
      timestamp: new Date().toISOString(),
      context: this.sanitizeContext(context),
      recovery: this.getRecoveryOptions(errorInfo.code, context),
      fallback: this.getFallbackData(context),
      debug: process.env.NODE_ENV === 'development' ? {
        originalError: error.message,
        stack: error.stack,
        details: errorInfo.details
      } : undefined
    };

    return response;
  }

  /**
   * Classify error type and extract relevant information
   */
  classifyError(error) {
    const message = (error.message || '').toLowerCase();
    const code = error.code || error.name || '';
    const status = error.response?.status;

    // Network errors
    if (code.includes('ENOTFOUND') || code.includes('ECONNREFUSED') || 
        message.includes('network') || message.includes('connection')) {
      return { code: 'NETWORK_ERROR', details: { originalCode: code } };
    }

    // Timeout errors
    if (code.includes('ETIMEDOUT') || message.includes('timeout')) {
      return { code: 'TIMEOUT_ERROR', details: { originalCode: code } };
    }

    // Rate limiting
    if (status === 429 || message.includes('rate limit') || message.includes('too many requests')) {
      return { code: 'RATE_LIMIT_EXCEEDED', details: { status } };
    }

    // API errors
    if (status >= 400 && status < 500) {
      if (status === 404) {
        return { code: 'INVALID_SYMBOL', details: { status } };
      }
      return { code: 'API_ERROR', details: { status } };
    }

    if (status >= 500) {
      return { code: 'INTERNAL_SERVER_ERROR', details: { status } };
    }

    // Crypto-specific errors
    if (error instanceof Error && error.name === 'CryptoDataError') {
      return { code: error.code, details: error.details };
    }

    // WebSocket errors
    if (message.includes('websocket') || message.includes('ws')) {
      return { code: 'WEBSOCKET_CONNECTION_FAILED', details: { message } };
    }

    // Portfolio errors
    if (message.includes('portfolio') || message.includes('sync')) {
      return { code: 'PORTFOLIO_SYNC_FAILED', details: { message } };
    }

    // Default to generic server error
    return { 
      code: 'INTERNAL_SERVER_ERROR', 
      details: { message: error.message, code: error.code } 
    };
  }

  /**
   * Get recovery options based on error type
   */
  getRecoveryOptions(errorCode, context) {
    const recovery = {
      automatic: false,
      retryable: false,
      fallbackAvailable: false,
      actions: []
    };

    const errorInfo = this.errorMap[errorCode];
    if (!errorInfo) return recovery;

    recovery.retryable = errorInfo.recoverable;
    recovery.fallbackAvailable = this.hasFallbackData(context);

    switch (errorInfo.category) {
      case 'network':
        recovery.automatic = true;
        recovery.actions = [
          { type: 'retry', delay: errorInfo.retryAfter || 5000, label: 'Retry automatically' },
          { type: 'manual_retry', label: 'Retry now' },
          { type: 'use_cached', label: 'Use cached data' }
        ];
        break;

      case 'api':
        recovery.automatic = true;
        recovery.actions = [
          { type: 'fallback_provider', label: 'Try backup data source' },
          { type: 'retry', delay: errorInfo.retryAfter || 30000, label: 'Retry in 30 seconds' },
          { type: 'use_cached', label: 'Show cached data' }
        ];
        break;

      case 'rate_limit':
        recovery.automatic = true;
        recovery.actions = [
          { type: 'wait_retry', delay: errorInfo.retryAfter || 30000, label: 'Wait and retry' },
          { type: 'use_cached', label: 'Show last known data' }
        ];
        break;

      case 'realtime':
        recovery.automatic = true;
        recovery.actions = [
          { type: 'reconnect_websocket', delay: 5000, label: 'Reconnect live data' },
          { type: 'poll_data', label: 'Use periodic updates' },
          { type: 'manual_refresh', label: 'Manual refresh' }
        ];
        break;

      case 'validation':
        recovery.actions = [
          { type: 'suggest_symbols', label: 'Show popular cryptocurrencies' },
          { type: 'search_similar', label: 'Search for similar symbols' }
        ];
        break;

      default:
        recovery.actions = [
          { type: 'manual_retry', label: 'Try again' },
          { type: 'contact_support', label: 'Contact support' }
        ];
    }

    return recovery;
  }

  /**
   * Get fallback data when live data is unavailable
   */
  getFallbackData(context) {
    if (!this.hasFallbackData(context)) return null;

    const { symbols = [], dataType = 'prices' } = context;

    switch (dataType) {
      case 'prices':
        return this.getFallbackPrices(symbols);
      case 'portfolio':
        return this.getFallbackPortfolio(context);
      case 'market_overview':
        return this.getFallbackMarketOverview();
      default:
        return null;
    }
  }

  getFallbackPrices(symbols) {
    const fallbackPrices = [];
    
    symbols.forEach(symbol => {
      const symbolKey = symbol.toLowerCase();
      if (this.fallbackData[symbolKey]) {
        fallbackPrices.push({
          symbol: symbol.toUpperCase(),
          price: this.fallbackData[symbolKey].price,
          change_24h: this.fallbackData[symbolKey].change,
          source: 'fallback',
          timestamp: new Date().toISOString(),
          note: 'Approximate price - live data unavailable'
        });
      }
    });

    return fallbackPrices.length > 0 ? fallbackPrices : null;
  }

  getFallbackPortfolio(context) {
    return {
      total_value: 'Unable to calculate',
      total_change: 'Unable to calculate',
      holdings: [],
      note: 'Portfolio values unavailable - please try refreshing',
      last_update: null
    };
  }

  getFallbackMarketOverview() {
    return {
      total_market_cap: 'Data unavailable',
      total_volume_24h: 'Data unavailable',
      btc_dominance: 'Data unavailable',
      active_cryptocurrencies: 'Data unavailable',
      note: 'Market overview temporarily unavailable',
      limited_data: true
    };
  }

  /**
   * Check if fallback data is available for context
   */
  hasFallbackData(context) {
    const { symbols = [], dataType = 'prices' } = context;
    
    if (dataType === 'prices' && symbols.length > 0) {
      return symbols.some(symbol => 
        this.fallbackData[symbol.toLowerCase()]
      );
    }

    return dataType === 'market_overview' || dataType === 'portfolio';
  }

  /**
   * Generic error for unknown error types
   */
  getGenericError() {
    return {
      title: 'Unexpected Error',
      message: 'An unexpected error occurred while processing your request. Please try again.',
      userAction: 'Try again or contact support',
      icon: 'error',
      severity: 'error',
      category: 'unknown',
      recoverable: true,
      retryAfter: 10000
    };
  }

  /**
   * Record error for analytics and monitoring
   */
  recordError(error, errorInfo, context) {
    const errorRecord = {
      timestamp: new Date().toISOString(),
      code: errorInfo.code,
      message: error.message,
      context: this.sanitizeContext(context),
      details: errorInfo.details,
      userAgent: context.userAgent,
      url: context.url
    };

    this.errorHistory.push(errorRecord);
    
    // Keep history size manageable
    if (this.errorHistory.length > this.maxHistorySize) {
      this.errorHistory.shift();
    }

    // Log for monitoring
    console.error('📊 Crypto Error Recorded:', {
      code: errorInfo.code,
      category: this.errorMap[errorInfo.code]?.category,
      message: error.message
    });
  }

  /**
   * Sanitize context to remove sensitive information
   */
  sanitizeContext(context) {
    const sanitized = { ...context };
    
    // Remove sensitive fields
    delete sanitized.apiKey;
    delete sanitized.secret;
    delete sanitized.password;
    delete sanitized.token;
    
    return sanitized;
  }

  /**
   * Get error statistics for monitoring
   */
  getErrorStats() {
    const now = Date.now();
    const lastHour = now - (60 * 60 * 1000);
    const recentErrors = this.errorHistory.filter(
      error => new Date(error.timestamp).getTime() > lastHour
    );

    const errorCounts = {};
    const categoryCounts = {};

    recentErrors.forEach(error => {
      errorCounts[error.code] = (errorCounts[error.code] || 0) + 1;
      
      const category = this.errorMap[error.code]?.category || 'unknown';
      categoryCounts[category] = (categoryCounts[category] || 0) + 1;
    });

    return {
      totalErrors: this.errorHistory.length,
      recentErrors: recentErrors.length,
      errorCounts,
      categoryCounts,
      topErrors: Object.entries(errorCounts)
        .sort(([,a], [,b]) => b - a)
        .slice(0, 5),
      timestamp: new Date().toISOString()
    };
  }

  /**
   * Clear error history
   */
  clearErrorHistory() {
    this.errorHistory = [];
    console.log('🧹 Crypto error history cleared');
  }

  /**
   * Get health status based on recent errors
   */
  getHealthStatus() {
    const stats = this.getErrorStats();
    const errorRate = stats.recentErrors / 60; // errors per minute
    
    let status = 'healthy';
    if (errorRate > 10) {
      status = 'critical';
    } else if (errorRate > 5) {
      status = 'degraded';
    } else if (errorRate > 1) {
      status = 'warning';
    }

    return {
      status,
      errorRate: errorRate.toFixed(2),
      recentErrors: stats.recentErrors,
      topIssues: stats.topErrors,
      timestamp: new Date().toISOString()
    };
  }
}

module.exports = new CryptoErrorHandler();
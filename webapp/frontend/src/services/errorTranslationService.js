/**
 * Error Translation Service
 * Translates technical errors into user-friendly messages
 * Addresses REQ-010: Error Handling Critical Gaps - User-Friendly Error Messages
 */

import React from 'react';

class ErrorTranslationService {
  constructor() {
    this.translations = new Map();
    this.contextualRules = [];
    this.fallbackMessage = 'An unexpected error occurred. Please try again.';
    this.supportContact = 'support@financialplatform.com';
    
    // Initialize default translations
    this.initializeTranslations();
    
    // Initialize contextual rules
    this.initializeContextualRules();
  }

  /**
   * Initialize default error translations
   */
  initializeTranslations() {
    // Network and connectivity errors
    this.translations.set('NetworkError', {
      message: 'Network connection issue. Please check your internet connection and try again.',
      action: 'Check your internet connection',
      recoverable: true,
      category: 'network'
    });

    this.translations.set('TimeoutError', {
      message: 'The request took too long to complete. Please try again.',
      action: 'Try again',
      recoverable: true,
      category: 'network'
    });

    this.translations.set('AbortError', {
      message: 'The request was cancelled. Please try again.',
      action: 'Try again',
      recoverable: true,
      category: 'network'
    });

    // Authentication errors
    this.translations.set('AuthenticationError', {
      message: 'Your session has expired. Please log in again.',
      action: 'Log in again',
      recoverable: true,
      category: 'auth'
    });

    this.translations.set('AuthorizationError', {
      message: 'You don\'t have permission to perform this action.',
      action: 'Contact support for access',
      recoverable: false,
      category: 'auth'
    });

    // API and server errors
    this.translations.set('ValidationError', {
      message: 'The information provided is invalid. Please check your input and try again.',
      action: 'Check your input',
      recoverable: true,
      category: 'validation'
    });

    this.translations.set('ServerError', {
      message: 'Our servers are experiencing issues. Please try again in a few minutes.',
      action: 'Try again later',
      recoverable: true,
      category: 'server'
    });

    this.translations.set('ServiceUnavailableError', {
      message: 'This service is temporarily unavailable. Please try again later.',
      action: 'Try again later',
      recoverable: true,
      category: 'server'
    });

    // Data and resource errors
    this.translations.set('NotFoundError', {
      message: 'The requested information could not be found.',
      action: 'Try a different search',
      recoverable: true,
      category: 'data'
    });

    this.translations.set('ConflictError', {
      message: 'This action conflicts with existing data. Please refresh and try again.',
      action: 'Refresh and try again',
      recoverable: true,
      category: 'data'
    });

    // Financial/Trading specific errors
    this.translations.set('InsufficientFundsError', {
      message: 'You don\'t have enough funds to complete this transaction.',
      action: 'Check your account balance',
      recoverable: true,
      category: 'trading'
    });

    this.translations.set('MarketClosedError', {
      message: 'The market is currently closed. Trading is not available.',
      action: 'Try during market hours',
      recoverable: true,
      category: 'trading'
    });

    this.translations.set('InvalidSymbolError', {
      message: 'The stock symbol you entered is not valid or not supported.',
      action: 'Check the symbol and try again',
      recoverable: true,
      category: 'trading'
    });

    // Rate limiting errors
    this.translations.set('RateLimitError', {
      message: 'You\'ve made too many requests. Please wait a moment and try again.',
      action: 'Wait and try again',
      recoverable: true,
      category: 'rate_limit'
    });

    // API key errors
    this.translations.set('InvalidApiKeyError', {
      message: 'Your API key is invalid or expired. Please check your settings.',
      action: 'Update your API key',
      recoverable: true,
      category: 'api_key'
    });

    this.translations.set('MissingApiKeyError', {
      message: 'API key is required for this action. Please add your API key in settings.',
      action: 'Add API key in settings',
      recoverable: true,
      category: 'api_key'
    });

    // Application errors
    this.translations.set('ChunkLoadError', {
      message: 'Failed to load application resources. Please refresh the page.',
      action: 'Refresh the page',
      recoverable: true,
      category: 'app'
    });

    this.translations.set('TypeError', {
      message: 'An unexpected error occurred. Please refresh the page.',
      action: 'Refresh the page',
      recoverable: true,
      category: 'app'
    });

    this.translations.set('ReferenceError', {
      message: 'An application error occurred. Please refresh the page.',
      action: 'Refresh the page',
      recoverable: true,
      category: 'app'
    });

    // WebSocket errors
    this.translations.set('WebSocketError', {
      message: 'Real-time data connection lost. Reconnecting...',
      action: 'Connection will be restored automatically',
      recoverable: true,
      category: 'realtime'
    });

    // Payment errors
    this.translations.set('PaymentError', {
      message: 'Payment processing failed. Please check your payment method.',
      action: 'Check payment method',
      recoverable: true,
      category: 'payment'
    });

    this.translations.set('CardDeclinedError', {
      message: 'Your card was declined. Please try a different payment method.',
      action: 'Try different payment method',
      recoverable: true,
      category: 'payment'
    });
  }

  /**
   * Initialize contextual rules for better error translation
   */
  initializeContextualRules() {
    // HTTP status code rules
    this.contextualRules.push({
      condition: (error) => error.status === 400,
      translation: {
        message: 'Invalid request. Please check your input and try again.',
        action: 'Check your input',
        recoverable: true,
        category: 'validation'
      }
    });

    this.contextualRules.push({
      condition: (error) => error.status === 401,
      translation: {
        message: 'Authentication required. Please log in again.',
        action: 'Log in again',
        recoverable: true,
        category: 'auth'
      }
    });

    this.contextualRules.push({
      condition: (error) => error.status === 403,
      translation: {
        message: 'Access denied. You don\'t have permission for this action.',
        action: 'Contact support for access',
        recoverable: false,
        category: 'auth'
      }
    });

    this.contextualRules.push({
      condition: (error) => error.status === 404,
      translation: {
        message: 'The requested resource was not found.',
        action: 'Try a different search',
        recoverable: true,
        category: 'data'
      }
    });

    this.contextualRules.push({
      condition: (error) => error.status === 429,
      translation: {
        message: 'Too many requests. Please wait a moment and try again.',
        action: 'Wait and try again',
        recoverable: true,
        category: 'rate_limit'
      }
    });

    this.contextualRules.push({
      condition: (error) => error.status >= 500,
      translation: {
        message: 'Server error. Our team has been notified and is working on it.',
        action: 'Try again later',
        recoverable: true,
        category: 'server'
      }
    });

    // Message-based rules
    this.contextualRules.push({
      condition: (error) => error.message?.toLowerCase().includes('timeout'),
      translation: {
        message: 'Request timed out. Please try again.',
        action: 'Try again',
        recoverable: true,
        category: 'network'
      }
    });

    this.contextualRules.push({
      condition: (error) => error.message?.toLowerCase().includes('network'),
      translation: {
        message: 'Network error. Please check your connection and try again.',
        action: 'Check your connection',
        recoverable: true,
        category: 'network'
      }
    });

    this.contextualRules.push({
      condition: (error) => error.message?.toLowerCase().includes('api key'),
      translation: {
        message: 'API key issue. Please check your API key settings.',
        action: 'Update API key',
        recoverable: true,
        category: 'api_key'
      }
    });

    this.contextualRules.push({
      condition: (error) => error.message?.toLowerCase().includes('insufficient funds'),
      translation: {
        message: 'Insufficient funds for this transaction.',
        action: 'Check account balance',
        recoverable: true,
        category: 'trading'
      }
    });

    this.contextualRules.push({
      condition: (error) => error.message?.toLowerCase().includes('market closed'),
      translation: {
        message: 'Market is closed. Trading is not available.',
        action: 'Try during market hours',
        recoverable: true,
        category: 'trading'
      }
    });

    // Context-based rules
    this.contextualRules.push({
      condition: (error, context) => context?.component === 'Login',
      translation: {
        message: 'Login failed. Please check your credentials and try again.',
        action: 'Check credentials',
        recoverable: true,
        category: 'auth'
      }
    });

    this.contextualRules.push({
      condition: (error, context) => context?.component === 'Portfolio',
      translation: {
        message: 'Unable to load portfolio data. Please try again.',
        action: 'Try again',
        recoverable: true,
        category: 'data'
      }
    });

    this.contextualRules.push({
      condition: (error, context) => context?.component === 'TradingForm',
      translation: {
        message: 'Unable to place order. Please check your details and try again.',
        action: 'Check order details',
        recoverable: true,
        category: 'trading'
      }
    });
  }

  /**
   * Translate error to user-friendly message
   */
  translateError(error, context = {}) {
    try {
      // Try contextual rules first
      for (const rule of this.contextualRules) {
        if (rule.condition(error, context)) {
          return this.formatTranslation(rule.translation, error, context);
        }
      }

      // Try direct translation by error name
      if (error.name && this.translations.has(error.name)) {
        const translation = this.translations.get(error.name);
        return this.formatTranslation(translation, error, context);
      }

      // Try translation by error type
      const errorType = this.determineErrorType(error);
      if (errorType && this.translations.has(errorType)) {
        const translation = this.translations.get(errorType);
        return this.formatTranslation(translation, error, context);
      }

      // Fallback to default message
      return this.formatTranslation({
        message: this.fallbackMessage,
        action: 'Try again or contact support',
        recoverable: true,
        category: 'unknown'
      }, error, context);

    } catch (translationError) {
      console.error('Error in error translation:', translationError);
      return this.formatTranslation({
        message: this.fallbackMessage,
        action: 'Try again or contact support',
        recoverable: true,
        category: 'unknown'
      }, error, context);
    }
  }

  /**
   * Determine error type from error object
   */
  determineErrorType(error) {
    if (error.name) {
      return error.name;
    }

    if (error.status) {
      if (error.status === 400) return 'ValidationError';
      if (error.status === 401) return 'AuthenticationError';
      if (error.status === 403) return 'AuthorizationError';
      if (error.status === 404) return 'NotFoundError';
      if (error.status === 409) return 'ConflictError';
      if (error.status === 429) return 'RateLimitError';
      if (error.status >= 500) return 'ServerError';
    }

    if (error.message) {
      const message = error.message.toLowerCase();
      if (message.includes('network')) return 'NetworkError';
      if (message.includes('timeout')) return 'TimeoutError';
      if (message.includes('abort')) return 'AbortError';
      if (message.includes('chunk')) return 'ChunkLoadError';
      if (message.includes('websocket')) return 'WebSocketError';
      if (message.includes('api key')) return 'InvalidApiKeyError';
      if (message.includes('insufficient funds')) return 'InsufficientFundsError';
      if (message.includes('market closed')) return 'MarketClosedError';
    }

    return null;
  }

  /**
   * Format translation with additional context
   */
  formatTranslation(translation, error, context) {
    const formatted = {
      ...translation,
      originalError: {
        message: error.message,
        name: error.name,
        code: error.code,
        status: error.status
      },
      context,
      timestamp: new Date().toISOString(),
      supportContact: this.supportContact
    };

    // Add retry information
    if (translation.recoverable) {
      formatted.canRetry = true;
      formatted.retryDelay = this.getRetryDelay(translation.category);
    }

    // Add category-specific actions
    formatted.actions = this.getCategoryActions(translation.category);

    return formatted;
  }

  /**
   * Get retry delay based on error category
   */
  getRetryDelay(category) {
    const delays = {
      network: 3000,
      server: 5000,
      rate_limit: 10000,
      auth: 0,
      validation: 0,
      trading: 1000,
      data: 2000,
      app: 0,
      realtime: 2000,
      payment: 0,
      api_key: 0,
      unknown: 3000
    };

    return delays[category] || 3000;
  }

  /**
   * Get category-specific actions
   */
  getCategoryActions(category) {
    const categoryActions = {
      network: [
        'Check your internet connection',
        'Try again in a few moments',
        'Switch to a different network if available'
      ],
      server: [
        'Try again in a few minutes',
        'Check our status page for updates',
        'Contact support if the problem persists'
      ],
      auth: [
        'Log in again',
        'Check your credentials',
        'Reset your password if needed'
      ],
      validation: [
        'Check your input for errors',
        'Ensure all required fields are filled',
        'Verify data format is correct'
      ],
      trading: [
        'Check your account balance',
        'Verify market hours',
        'Ensure you have the required permissions'
      ],
      data: [
        'Refresh the page',
        'Try a different search',
        'Check if the data exists'
      ],
      app: [
        'Refresh the page',
        'Clear your browser cache',
        'Try using a different browser'
      ],
      realtime: [
        'Connection will be restored automatically',
        'Refresh the page if needed',
        'Check your internet connection'
      ],
      payment: [
        'Check your payment method',
        'Verify card details',
        'Try a different payment method'
      ],
      api_key: [
        'Update your API key in settings',
        'Check if your API key is valid',
        'Contact your API provider'
      ],
      rate_limit: [
        'Wait a moment and try again',
        'Reduce the frequency of requests',
        'Consider upgrading your plan'
      ]
    };

    return categoryActions[category] || [
      'Try again',
      'Refresh the page',
      'Contact support if the problem persists'
    ];
  }

  /**
   * Add custom translation
   */
  addTranslation(errorName, translation) {
    this.translations.set(errorName, translation);
  }

  /**
   * Add contextual rule
   */
  addContextualRule(condition, translation) {
    this.contextualRules.push({ condition, translation });
  }

  /**
   * Get all translations
   */
  getAllTranslations() {
    return Array.from(this.translations.entries());
  }

  /**
   * Get translation statistics
   */
  getStatistics() {
    const categories = {};
    const recoverable = { true: 0, false: 0 };

    for (const [, translation] of this.translations) {
      categories[translation.category] = (categories[translation.category] || 0) + 1;
      recoverable[translation.recoverable] = (recoverable[translation.recoverable] || 0) + 1;
    }

    return {
      totalTranslations: this.translations.size,
      contextualRules: this.contextualRules.length,
      categories,
      recoverable,
      fallbackMessage: this.fallbackMessage
    };
  }
}

// Create singleton instance
const errorTranslationService = new ErrorTranslationService();

// React hook for error translation
export const useErrorTranslation = () => {
  const translateError = React.useCallback((error, context = {}) => {
    return errorTranslationService.translateError(error, context);
  }, []);

  const addTranslation = React.useCallback((errorName, translation) => {
    errorTranslationService.addTranslation(errorName, translation);
  }, []);

  const addContextualRule = React.useCallback((condition, translation) => {
    errorTranslationService.addContextualRule(condition, translation);
  }, []);

  return {
    translateError,
    addTranslation,
    addContextualRule
  };
};

export default errorTranslationService;
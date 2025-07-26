/**
 * AI Error Handler - Comprehensive error handling for AI services
 * 
 * Provides intelligent error classification, fallback strategies, and user-friendly messages
 */

const bedrockAIService = require('./bedrockAIService');

class AIErrorHandler {
  constructor() {
    this.errorStats = {
      totalErrors: 0,
      errorTypes: {},
      lastError: null,
      recoveryAttempts: 0
    };
    
    this.fallbackResponses = {
      BEDROCK_UNAVAILABLE: {
        content: "I'm currently using simplified responses while my advanced AI capabilities are being restored. I can still help you with portfolio analysis, market insights, and investment questions using my backup knowledge base.",
        suggestions: ['Portfolio overview', 'Market summary', 'Stock analysis', 'Investment strategies']
      },
      RATE_LIMIT_EXCEEDED: {
        content: "I'm receiving a high volume of requests right now. Let me provide you with a quick response while I manage the load. Your question is important to me!",
        suggestions: ['Try again in a moment', 'Ask a different question', 'Check portfolio status', 'View market overview']  
      },
      CONTEXT_TOO_LARGE: {
        content: "Your request involves a lot of context. Let me provide a focused response to your main question. Feel free to ask follow-up questions for more details.",
        suggestions: ['Simplify question', 'Ask specific details', 'Break into parts', 'Focus on one topic']
      },
      NETWORK_ERROR: {
        content: "I'm experiencing connectivity issues but can still provide basic assistance. Let me help you with what I can access locally.",
        suggestions: ['Retry request', 'Check connection', 'Ask basic questions', 'Try again later']
      },
      DATABASE_UNAVAILABLE: {
        content: "I can't access your latest portfolio data right now, but I can still provide general market insights and investment guidance.",
        suggestions: ['General market analysis', 'Investment strategies', 'Stock research tips', 'Retry with portfolio']
      },
      INVALID_CONTEXT: {
        content: "I had trouble understanding your request context. Could you please rephrase your question or provide more specific details?",
        suggestions: ['Rephrase question', 'Be more specific', 'Provide examples', 'Ask differently']
      }
    };
  }

  /**
   * Handle AI errors with intelligent classification and recovery
   */
  async handleAIError(error, context = {}) {
    this.errorStats.totalErrors++;
    this.errorStats.lastError = {
      message: error.message,
      type: error.name,
      timestamp: new Date().toISOString()
    };

    console.error('🚨 AI Error Handler processing error:', {
      name: error.name,
      message: error.message,
      code: error.code,
      userId: context.userId
    });

    const errorType = this.classifyError(error);
    this.recordErrorType(errorType);

    try {
      switch (errorType) {
        case 'BEDROCK_UNAVAILABLE':
          return await this.handleBedrockUnavailable(context);
        
        case 'RATE_LIMIT_EXCEEDED':
          return await this.handleRateLimit(context);
        
        case 'CONTEXT_TOO_LARGE':
          return await this.handleContextTooLarge(context);
        
        case 'NETWORK_ERROR':
          return await this.handleNetworkError(context);
        
        case 'DATABASE_UNAVAILABLE':
          return await this.handleDatabaseUnavailable(context);
        
        case 'AUTHENTICATION_ERROR':
          return await this.handleAuthError(context);
        
        default:
          return await this.handleGenericError(error, context);
      }
    } catch (fallbackError) {
      console.error('❌ Fallback error handling failed:', fallbackError);
      return this.getEmergencyResponse();
    }
  }

  /**
   * Classify error types for appropriate handling
   */
  classifyError(error) {
    const errorMessage = (error.message || '').toLowerCase();
    const errorCode = error.code || error.name || '';

    // Bedrock-specific errors
    if (errorCode.includes('AccessDenied') || errorCode.includes('Unauthorized')) {
      return 'BEDROCK_UNAVAILABLE';
    }
    if (errorCode.includes('Throttling') || errorCode.includes('RateLimit')) {
      return 'RATE_LIMIT_EXCEEDED';
    }
    if (errorCode.includes('ValidationException') || errorMessage.includes('too large')) {
      return 'CONTEXT_TOO_LARGE';
    }
    if (errorCode.includes('ServiceUnavailable') || errorCode.includes('TimeoutError')) {
      return 'BEDROCK_UNAVAILABLE';
    }

    // Network and connectivity errors
    if (errorMessage.includes('network') || errorMessage.includes('timeout') || 
        errorMessage.includes('connection') || errorCode.includes('ENOTFOUND')) {
      return 'NETWORK_ERROR';
    }

    // Database errors
    if (errorMessage.includes('database') || errorMessage.includes('query') ||
        errorCode.includes('ECONNREFUSED') || errorMessage.includes('connection pool')) {
      return 'DATABASE_UNAVAILABLE';
    }

    // Authentication errors
    if (errorMessage.includes('auth') || errorMessage.includes('token') ||
        errorCode.includes('Forbidden')) {
      return 'AUTHENTICATION_ERROR';
    }

    // Context/validation errors
    if (errorMessage.includes('context') || errorMessage.includes('invalid') ||
        errorMessage.includes('malformed')) {
      return 'INVALID_CONTEXT';
    }

    return 'GENERIC_ERROR';
  }

  /**
   * Handle Bedrock service unavailable
   */
  async handleBedrockUnavailable(context) {
    this.errorStats.recoveryAttempts++;
    
    // Try rule-based fallback response
    const fallbackResponse = await this.generateRuleBasedResponse(context);
    
    return {
      ...this.fallbackResponses.BEDROCK_UNAVAILABLE,
      ...fallbackResponse,
      metadata: {
        fallbackMode: true,
        errorType: 'BEDROCK_UNAVAILABLE',
        recoveryAttempt: this.errorStats.recoveryAttempts,
        timestamp: new Date().toISOString()
      }
    };
  }

  /**
   * Handle rate limiting
   */
  async handleRateLimit(context) {
    // Implement backoff and queuing logic here
    return {
      ...this.fallbackResponses.RATE_LIMIT_EXCEEDED,
      metadata: {
        fallbackMode: true,
        errorType: 'RATE_LIMIT_EXCEEDED',
        retryAfter: 60, // seconds
        timestamp: new Date().toISOString()
      }
    };
  }

  /**
   * Handle context too large
   */
  async handleContextTooLarge(context) {
    // Try with truncated context
    const truncatedContext = this.truncateContext(context);
    
    try {
      // Retry with smaller context
      const response = await bedrockAIService.generateResponse(
        context.userMessage, 
        truncatedContext
      );
      
      return {
        ...response,
        metadata: {
          contextTruncated: true,
          originalContextSize: JSON.stringify(context).length,
          truncatedContextSize: JSON.stringify(truncatedContext).length
        }
      };
    } catch (retryError) {
      return {
        ...this.fallbackResponses.CONTEXT_TOO_LARGE,
        metadata: {
          fallbackMode: true,
          errorType: 'CONTEXT_TOO_LARGE',
          retryFailed: true
        }
      };
    }
  }

  /**
   * Handle network errors
   */
  async handleNetworkError(context) {
    // Try cached response first
    const cachedResponse = await this.getCachedResponse(context);
    if (cachedResponse) {
      return {
        ...cachedResponse,
        metadata: {
          fromCache: true,
          errorType: 'NETWORK_ERROR'
        }
      };
    }

    return {
      ...this.fallbackResponses.NETWORK_ERROR,
      metadata: {
        fallbackMode: true,
        errorType: 'NETWORK_ERROR',
        cacheAvailable: false
      }
    };
  }

  /**
   * Handle database unavailable
   */
  async handleDatabaseUnavailable(context) {
    // Remove database-dependent context and retry
    const contextWithoutDB = {
      ...context,
      portfolioContext: null,
      recentMessages: []
    };

    try {
      const response = await bedrockAIService.generateResponse(
        context.userMessage || context.message,
        contextWithoutDB
      );
      
      return {
        ...response,
        content: `${response.content}\n\n_Note: Portfolio data temporarily unavailable._`,
        metadata: {
          databaseUnavailable: true,
          portfolioDataMissing: true
        }
      };
    } catch (retryError) {
      return {
        ...this.fallbackResponses.DATABASE_UNAVAILABLE,
        metadata: {
          fallbackMode: true,
          errorType: 'DATABASE_UNAVAILABLE'
        }
      };
    }
  }

  /**
   * Handle authentication errors
   */
  async handleAuthError(context) {
    return {
      content: "I'm experiencing authentication issues with my AI services. Please try refreshing your session, or contact support if the problem persists.",
      suggestions: ['Refresh page', 'Re-login', 'Contact support', 'Try basic features'],
      metadata: {
        fallbackMode: true,
        errorType: 'AUTHENTICATION_ERROR',
        requiresUserAction: true
      }
    };
  }

  /**
   * Handle generic errors
   */
  async handleGenericError(error, context) {
    console.error('🚨 Unhandled AI error:', error);
    
    return {
      content: "I encountered an unexpected issue, but I'm still here to help. Let me try to assist you with a different approach to your question.",
      suggestions: ['Rephrase question', 'Try simpler query', 'Ask about portfolio', 'Get market overview'],
      metadata: {
        fallbackMode: true,
        errorType: 'GENERIC_ERROR',
        originalError: error.message
      }
    };
  }

  /**
   * Generate rule-based fallback response
   */
  async generateRuleBasedResponse(context) {
    const userMessage = (context.userMessage || context.message || '').toLowerCase();
    
    if (userMessage.includes('portfolio') && context.portfolioContext) {
      const portfolio = context.portfolioContext;
      return {
        content: `Based on your portfolio data:
        
• Total Value: $${portfolio.totalValue?.toFixed(2) || 'N/A'}
• Total Gain/Loss: ${portfolio.totalGainLoss >= 0 ? '+' : ''}$${portfolio.totalGainLoss?.toFixed(2) || 'N/A'} (${portfolio.gainLossPercent?.toFixed(2) || 'N/A'}%)
• Holdings: ${portfolio.holdings?.length || 0} positions

${portfolio.gainLossPercent > 0 ? 
  'Your portfolio is performing positively!' : 
  'Consider reviewing your investment strategy.'
}`,
        suggestions: ['View top holdings', 'Analyze performance', 'Risk assessment', 'Rebalancing advice']
      };
    }

    if (userMessage.includes('market')) {
      return {
        content: `Current market overview:

• Market conditions are showing mixed signals
• Technology and healthcare sectors remain active
• Consider diversification across sectors
• Monitor economic indicators for trend changes

I recommend focusing on quality companies with strong fundamentals during uncertain periods.`,
        suggestions: ['Sector analysis', 'Stock screening', 'Risk management', 'Investment strategy']
      };
    }

    return {
      content: "I'm ready to help you with investment questions, portfolio analysis, market insights, and financial planning. What would you like to explore?",
      suggestions: ['Portfolio review', 'Market analysis', 'Stock research', 'Investment planning']
    };
  }

  /**
   * Truncate context to fit within limits
   */
  truncateContext(context) {
    const truncated = { ...context };
    
    // Reduce conversation history
    if (truncated.recentMessages && truncated.recentMessages.length > 3) {
      truncated.recentMessages = truncated.recentMessages.slice(-3);
    }
    
    // Reduce portfolio holdings
    if (truncated.portfolioContext && truncated.portfolioContext.holdings) {
      truncated.portfolioContext.holdings = truncated.portfolioContext.holdings.slice(0, 5);
    }
    
    // Reduce market context
    if (truncated.marketContext) {
      truncated.marketContext.recentNews = truncated.marketContext.recentNews?.slice(0, 2) || [];
    }
    
    return truncated;
  }

  /**
   * Get cached response if available
   */
  async getCachedResponse(context) {
    // Implement caching logic here
    // For now, return null (no cache)
    return null;
  }

  /**
   * Emergency response when all else fails
   */
  getEmergencyResponse() {
    return {
      content: "I'm experiencing technical difficulties but I'm working to resolve them. Please try your request again in a few moments, or ask a simpler question that I can handle with my basic systems.",
      suggestions: ['Try again', 'Simplify question', 'Check system status', 'Contact support'],
      metadata: {
        emergencyMode: true,
        errorType: 'SYSTEM_FAILURE',
        timestamp: new Date().toISOString()
      }
    };
  }

  /**
   * Record error type for analytics
   */
  recordErrorType(errorType) {
    if (!this.errorStats.errorTypes[errorType]) {
      this.errorStats.errorTypes[errorType] = 0;
    }
    this.errorStats.errorTypes[errorType]++;
  }

  /**
   * Get error statistics
   */
  getErrorStats() {
    return {
      ...this.errorStats,
      uptime: process.uptime(),
      errorRate: this.errorStats.totalErrors / (process.uptime() / 60), // errors per minute
      topErrorTypes: Object.entries(this.errorStats.errorTypes)
        .sort(([,a], [,b]) => b - a)
        .slice(0, 5)
    };
  }

  /**
   * Reset error statistics
   */
  resetStats() {
    this.errorStats = {
      totalErrors: 0,
      errorTypes: {},
      lastError: null,
      recoveryAttempts: 0
    };
    console.log('🔄 AI Error Handler statistics reset');
  }
}

// Export singleton instance
module.exports = new AIErrorHandler();
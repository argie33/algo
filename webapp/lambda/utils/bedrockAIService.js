/**
 * AWS Bedrock AI Service - Production-grade LLM integration
 * 
 * Provides intelligent conversation capabilities using AWS Bedrock Claude models
 * with cost optimization, conversation memory, and financial context awareness
 */

const { BedrockRuntimeClient, InvokeModelCommand } = require('@aws-sdk/client-bedrock-runtime');

class BedrockAIService {
  constructor() {
    this.client = new BedrockRuntimeClient({
      region: process.env.AWS_REGION || 'us-east-1'
    });
    
    // Model configuration
    this.modelConfig = {
      modelId: 'anthropic.claude-3-haiku-20240307-v1:0', // Cost-optimized model
      maxTokens: 1000,
      temperature: 0.1, // Low temperature for consistent financial advice
      topP: 0.9
    };
    
    // Cost tracking
    this.costTracking = {
      inputTokens: 0,
      outputTokens: 0,
      requestCount: 0
    };
    
    // Response caching for common queries
    this.responseCache = new Map();
    this.cacheExpiry = 10 * 60 * 1000; // 10 minutes
  }

  /**
   * Generate AI response using AWS Bedrock Claude
   * @param {string} userMessage - User's message
   * @param {Object} context - Conversation and user context
   * @returns {Promise<Object>} AI response with suggestions
   * @throws {Error} Throws detailed error with actionable steps if Bedrock unavailable
   */
  async generateResponse(userMessage, context = {}) {
    console.log('🤖 Generating AI response with Bedrock for message:', userMessage.substring(0, 50) + '...');
    
    // Check cache first
    const cacheKey = this.getCacheKey(userMessage, context);
    const cachedResponse = this.getFromCache(cacheKey);
    if (cachedResponse) {
      console.log('✅ Returning cached response');
      return cachedResponse;
    }

    try {

      // Build conversation context
      const conversationContext = this.buildConversationContext(userMessage, context);
      
      // Prepare the request
      const request = {
        modelId: this.modelConfig.modelId,
        contentType: 'application/json',
        accept: 'application/json',
        body: JSON.stringify({
          anthropic_version: 'bedrock-2023-05-31',
          max_tokens: this.modelConfig.maxTokens,
          temperature: this.modelConfig.temperature,
          top_p: this.modelConfig.topP,
          messages: [
            {
              role: 'user',
              content: conversationContext
            }
          ]
        })
      };

      // Send request to Bedrock
      const command = new InvokeModelCommand(request);
      const response = await this.client.send(command);
      
      // Parse response
      const responseBody = JSON.parse(new TextDecoder().decode(response.body));
      const aiMessage = responseBody.content[0].text;
      
      // Track usage for cost monitoring
      this.trackUsage(responseBody.usage);
      
      // Generate suggestions based on response
      const suggestions = this.generateSuggestions(userMessage, aiMessage);
      
      // Format final response
      const finalResponse = {
        content: aiMessage,
        suggestions: suggestions,
        context: {
          modelUsed: this.modelConfig.modelId,
          tokensUsed: responseBody.usage?.output_tokens || 0,
          hasPortfolioData: !!context.portfolioContext,
          dataSource: 'aws_bedrock'
        }
      };

      // Cache the response
      this.cacheResponse(cacheKey, finalResponse);
      
      console.log('✅ AI response generated successfully');
      return finalResponse;

    } catch (error) {
      console.error('❌ Error generating AI response:', error);
      
      // Provide detailed error information instead of fallback
      throw this.createDetailedError(error, userMessage, context);
    }
  }

  /**
   * Build conversation context with financial expertise
   */
  buildConversationContext(userMessage, context) {
    let conversationPrompt = `You are an expert AI investment advisor with deep knowledge of financial markets, portfolio management, and investment strategies. You provide clear, actionable, and responsible investment guidance.

Key guidelines:
- Always provide balanced, well-reasoned investment advice
- Consider risk management in all recommendations
- Use specific data and metrics when available
- Suggest next steps or follow-up questions
- Avoid giving specific buy/sell recommendations for individual stocks
- Focus on education and strategy rather than predictions
- Keep responses concise but comprehensive

`;

    // Add portfolio context if available
    if (context.portfolioContext) {
      const portfolio = context.portfolioContext;
      conversationPrompt += `
Current Portfolio Context:
- Total Value: $${portfolio.totalValue?.toFixed(2) || 'N/A'}
- Total Gain/Loss: $${portfolio.totalGainLoss?.toFixed(2) || 'N/A'} (${portfolio.gainLossPercent?.toFixed(2) || 'N/A'}%)
- Number of Holdings: ${portfolio.holdings?.length || 0}
- Top Holdings: ${portfolio.holdings?.slice(0, 3).map(h => `${h.symbol}: $${parseFloat(h.market_value).toFixed(2)}`).join(', ') || 'None'}

`;
    }

    // Add market context if available
    if (context.marketContext) {
      conversationPrompt += `
Current Market Context:
- Market sentiment and recent performance data available
- Consider current market conditions in your response

`;
    }

    // Add conversation history context
    if (context.recentMessages && context.recentMessages.length > 0) {
      conversationPrompt += `
Recent conversation context:
${context.recentMessages.slice(-3).map(msg => 
  `${msg.type === 'user' ? 'User' : 'Assistant'}: ${msg.content.substring(0, 100)}...`
).join('\n')}

`;
    }

    conversationPrompt += `
User Question: ${userMessage}

Please provide a helpful, accurate, and actionable response. Include 2-4 relevant follow-up suggestions that would help the user explore this topic further.`;

    return conversationPrompt;
  }

  /**
   * Generate contextual suggestions based on the conversation
   */
  generateSuggestions(userMessage, aiResponse) {
    const lowerMessage = userMessage.toLowerCase();
    const lowerResponse = aiResponse.toLowerCase();

    // Portfolio-related suggestions
    if (lowerMessage.includes('portfolio') || lowerResponse.includes('portfolio')) {
      return [
        'Analyze sector allocation',
        'Review risk metrics', 
        'Suggest rebalancing',
        'Compare to benchmarks'
      ];
    }

    // Market analysis suggestions
    if (lowerMessage.includes('market') || lowerResponse.includes('market')) {
      return [
        'Sector performance trends',
        'Economic indicators impact',
        'Volatility analysis',
        'Market outlook'
      ];
    }

    // Stock research suggestions
    if (lowerMessage.includes('stock') || lowerMessage.includes('company')) {
      return [
        'Technical analysis',
        'Fundamental metrics',
        'Analyst consensus',
        'Risk assessment'
      ];
    }

    // Investment strategy suggestions
    if (lowerMessage.includes('invest') || lowerMessage.includes('strategy')) {
      return [
        'Risk tolerance assessment',
        'Asset allocation strategy',
        'Dollar-cost averaging',
        'Tax optimization'
      ];
    }

    // Default suggestions
    return [
      'Tell me more about this',
      'What are the key risks?',
      'Show me relevant data',
      'What should I do next?'
    ];
  }

  /**
   * Create detailed error with actionable resolution steps
   */
  createDetailedError(error, userMessage, context) {
    const errorCode = error.name || error.code || 'UNKNOWN_ERROR';
    const errorMessage = error.message || 'Unknown error occurred';
    
    let detailedError = {
      name: 'BedrockAIServiceError',
      code: errorCode,
      message: '',
      details: {},
      actionableSteps: []
    };

    // Handle specific error types
    switch (errorCode) {
      case 'AccessDeniedException':
        detailedError.message = 'AWS Bedrock access denied - IAM permissions required';
        detailedError.details = {
          requiredPermissions: ['bedrock:InvokeModel'],
          resourceArn: 'arn:aws:bedrock:*:*:foundation-model/anthropic.claude-3-haiku-20240307-v1:0',
          currentUser: error.message.match(/User: (arn:aws:iam::[^\\s]+)/)?.[1] || 'Unknown',
          region: process.env.AWS_REGION || 'us-east-1'
        };
        detailedError.actionableSteps = [
          '1. Contact your AWS administrator to add bedrock:InvokeModel permission',
          '2. Ensure Claude 3 Haiku model access is enabled in AWS Bedrock console',
          '3. Verify AWS credentials have the correct permissions',
          '4. Check that the model is available in your AWS region'
        ];
        break;
        
      case 'ModelNotFoundError':
      case 'ValidationException':
        detailedError.message = 'AWS Bedrock model configuration error';
        detailedError.details = {
          requestedModel: this.modelConfig.modelId,
          availableRegions: ['us-east-1', 'us-west-2'],
          modelStatus: 'Check AWS Bedrock console for model availability'
        };
        detailedError.actionableSteps = [
          '1. Verify Claude 3 Haiku model is enabled in AWS Bedrock console',
          '2. Check model availability in your AWS region',
          '3. Ensure model access has been requested and approved',
          '4. Try switching to us-east-1 region if using a different region'
        ];
        break;
        
      case 'ThrottlingException':
        detailedError.message = 'AWS Bedrock rate limit exceeded';
        detailedError.details = {
          retryAfter: '60 seconds',
          currentRequests: this.costTracking.requestCount,
          suggestion: 'Implement request queuing or increase rate limits'
        };
        detailedError.actionableSteps = [
          '1. Wait 60 seconds before retrying',
          '2. Contact AWS support to increase Bedrock rate limits',
          '3. Implement request queuing in your application',
          '4. Consider caching responses to reduce API calls'
        ];
        break;
        
      case 'ServiceUnavailableException':
        detailedError.message = 'AWS Bedrock service temporarily unavailable';
        detailedError.details = {
          serviceStatus: 'Check AWS Status page',
          retryAfter: '5 minutes',
          region: process.env.AWS_REGION || 'us-east-1'
        };
        detailedError.actionableSteps = [
          '1. Check AWS Status page for Bedrock service issues',
          '2. Wait 5 minutes and retry',
          '3. Try switching to a different AWS region',
          '4. Monitor AWS service status for updates'
        ];
        break;
        
      default:
        detailedError.message = `AWS Bedrock error: ${errorMessage}`;
        detailedError.details = {
          originalError: errorMessage,
          errorCode: errorCode,
          timestamp: new Date().toISOString()
        };
        detailedError.actionableSteps = [
          '1. Check AWS credentials and permissions',
          '2. Verify network connectivity to AWS',
          '3. Check AWS CloudTrail logs for detailed error information',
          '4. Contact AWS support if the issue persists'
        ];
    }
    
    // Add context information
    detailedError.context = {
      userMessage: userMessage.substring(0, 100),
      hasPortfolioContext: !!context.portfolioContext,
      region: process.env.AWS_REGION || 'us-east-1',
      modelId: this.modelConfig.modelId,
      timestamp: new Date().toISOString()
    };
    
    return detailedError;
  }

  /**
   * Cache management
   */
  getCacheKey(message, context) {
    const contextHash = JSON.stringify({
      hasPortfolio: !!context.portfolioContext,
      portfolioValue: context.portfolioContext?.totalValue,
      messageLength: message.length
    });
    return `${message.substring(0, 50)}_${contextHash}`;
  }

  getFromCache(key) {
    const cached = this.responseCache.get(key);
    if (cached && Date.now() - cached.timestamp < this.cacheExpiry) {
      return cached.response;
    }
    this.responseCache.delete(key);
    return null;
  }

  cacheResponse(key, response) {
    this.responseCache.set(key, {
      response,
      timestamp: Date.now()
    });
    
    // Clean old cache entries
    if (this.responseCache.size > 100) {
      const oldest = Array.from(this.responseCache.entries())
        .sort(([,a], [,b]) => a.timestamp - b.timestamp)[0];
      this.responseCache.delete(oldest[0]);
    }
  }

  /**
   * Track usage for cost monitoring
   */
  trackUsage(usage) {
    if (usage) {
      this.costTracking.inputTokens += usage.input_tokens || 0;
      this.costTracking.outputTokens += usage.output_tokens || 0;
    }
    this.costTracking.requestCount++;
  }

  /**
   * Get usage statistics
   */
  getUsageStats() {
    const inputCost = (this.costTracking.inputTokens / 1000000) * 0.25; // $0.25 per 1M input tokens
    const outputCost = (this.costTracking.outputTokens / 1000000) * 1.25; // $1.25 per 1M output tokens
    
    return {
      totalRequests: this.costTracking.requestCount,
      inputTokens: this.costTracking.inputTokens,
      outputTokens: this.costTracking.outputTokens,
      estimatedCost: inputCost + outputCost,
      averageTokensPerRequest: this.costTracking.requestCount > 0 ? 
        (this.costTracking.inputTokens + this.costTracking.outputTokens) / this.costTracking.requestCount : 0
    };
  }

  /**
   * Health check for the service
   */
  async healthCheck() {
    try {
      const testRequest = {
        modelId: this.modelConfig.modelId,
        contentType: 'application/json',
        accept: 'application/json',
        body: JSON.stringify({
          anthropic_version: 'bedrock-2023-05-31',
          max_tokens: 10,
          messages: [{
            role: 'user',
            content: 'Hello'
          }]
        })
      };

      const command = new InvokeModelCommand(testRequest);
      await this.client.send(command);

      return {
        status: 'healthy',
        service: 'BedrockAIService',
        model: this.modelConfig.modelId,
        cacheSize: this.responseCache.size,
        usage: this.getUsageStats()
      };
    } catch (error) {
      return {
        status: 'unhealthy',
        service: 'BedrockAIService',
        error: error.message,
        fallbackAvailable: true
      };
    }
  }
}

// Export singleton instance
module.exports = new BedrockAIService();
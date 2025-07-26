/**
 * AI Assistant Handler - Production-ready API handlers
 * 
 * Provides comprehensive AI assistant functionality with:
 * - Real-time streaming responses via WebSocket
 * - Enhanced conversation management
 * - Financial context integration
 * - Advanced error handling and recovery
 */

const { query } = require('../utils/database');
const EnhancedBedrockService = require('../services/EnhancedBedrockService');
const aiStreamingService = require('../utils/aiStreamingService');
const aiErrorHandler = require('../utils/aiErrorHandler');
const conversationStore = require('../utils/conversationStore');

class AIAssistantHandler {
  constructor() {
    this.enhancedBedrock = EnhancedBedrockService;
    this.activeStreams = new Map(); // Track active streaming sessions
    this.userPreferences = new Map(); // Cache user preferences
    
    // AI Configuration
    this.config = {
      maxHistoryLength: 50,
      maxResponseLength: 2000,
      defaultModel: 'claude-3-haiku',
      supportedModels: ['claude-3-haiku', 'claude-3-sonnet'],
      features: {
        streamingEnabled: true,
        enhancedContext: true,
        portfolioIntegration: true,
        marketInsights: true,
        financialAnalysis: true,
        conversationMemory: true
      },
      rateLimits: {
        requestsPerMinute: 60,
        requestsPerHour: 1000,
        maxConcurrentStreams: 5
      }
    };
  }

  /**
   * Handle chat request with enhanced AI capabilities
   */
  async handleChatRequest(req, res) {
    const startTime = Date.now();
    const { userId } = req.user;
    
    try {
      // Extract and validate request data
      const {
        message,
        conversationId = 'default',
        model = this.config.defaultModel,
        streaming = true,
        context = {},
        options = {}
      } = req.body;

      // Input validation
      if (!message || typeof message !== 'string' || message.trim().length === 0) {
        return res.status(400).json({
          error: 'Message is required and must be a non-empty string',
          code: 'INVALID_MESSAGE'
        });
      }

      if (message.length > 10000) {
        return res.status(400).json({
          error: 'Message too long. Maximum 10,000 characters allowed.',
          code: 'MESSAGE_TOO_LONG'
        });
      }

      // Rate limiting check
      const rateLimitResult = await this.checkRateLimit(userId);
      if (!rateLimitResult.allowed) {
        return res.status(429).json({
          error: 'Rate limit exceeded. Please wait before sending another message.',
          code: 'RATE_LIMIT_EXCEEDED',
          retryAfter: rateLimitResult.retryAfter
        });
      }

      console.log(`🤖 Processing AI chat request for user ${userId}: ${message.substring(0, 100)}...`);

      // Add user message to conversation history
      const userMessage = {
        id: `msg_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`,
        type: 'user',
        content: message.trim(),
        timestamp: new Date(),
        metadata: {
          model: model,
          conversationId: conversationId,
          requestId: req.headers['x-request-id'] || `req_${Date.now()}`
        }
      };

      await this.addMessageToHistory(userId, conversationId, userMessage);

      // Build enhanced context
      const enhancedContext = await this.buildEnhancedContext(userId, conversationId, context);

      // Handle streaming vs non-streaming responses
      if (streaming && this.config.features.streamingEnabled) {
        return await this.handleStreamingResponse(req, res, {
          userId,
          message: message.trim(),
          conversationId,
          model,
          context: enhancedContext,
          options,
          userMessage
        });
      } else {
        return await this.handleStandardResponse(req, res, {
          userId,
          message: message.trim(),
          conversationId,
          model,
          context: enhancedContext,
          options,
          userMessage
        });
      }

    } catch (error) {
      console.error('❌ Error in handleChatRequest:', error);
      
      const errorResponse = aiErrorHandler.handleChatError(error, {
        userId,
        message: req.body.message,
        timestamp: new Date(),
        responseTime: Date.now() - startTime
      });

      return res.status(errorResponse.status).json(errorResponse.body);
    }
  }

  /**
   * Handle streaming AI response
   */
  async handleStreamingResponse(req, res, params) {
    const { userId, message, conversationId, model, context, userMessage } = params;
    const streamId = `stream_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
    
    try {
      // Check concurrent stream limits
      const userStreams = Array.from(this.activeStreams.values())
        .filter(stream => stream.userId === userId);
      
      if (userStreams.length >= this.config.rateLimits.maxConcurrentStreams) {
        return res.status(429).json({
          error: 'Too many concurrent streams. Please wait for existing streams to complete.',
          code: 'TOO_MANY_STREAMS'
        });
      }

      // Register active stream
      this.activeStreams.set(streamId, {
        userId,
        conversationId,
        startTime: Date.now(),
        status: 'active'
      });

      // Set up streaming response headers
      res.writeHead(200, {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Cache-Control'
      });

      // Send initial stream started event
      this.sendStreamEvent(res, 'stream_started', {
        streamId,
        conversationId,
        timestamp: new Date().toISOString(),
        messageId: userMessage.id
      });

      let fullResponse = '';
      const assistantMessageId = `msg_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
      let chunkCount = 0;
      let totalTokens = 0;

      // Generate streaming response
      const streamGenerator = this.enhancedBedrock.generateStreamingResponse(
        message,
        context,
        { model, streamId }
      );

      for await (const chunk of streamGenerator) {
        if (chunk.type === 'start') {
          this.sendStreamEvent(res, 'stream_chunk', {
            streamId,
            chunkIndex: 0,
            type: 'start',
            timestamp: chunk.timestamp
          });
        } else if (chunk.type === 'chunk') {
          fullResponse += chunk.content;
          chunkCount++;
          
          this.sendStreamEvent(res, 'stream_chunk', {
            streamId,
            chunkIndex: chunkCount,
            content: chunk.content,
            timestamp: chunk.timestamp
          });
        } else if (chunk.type === 'complete') {
          fullResponse = chunk.fullContent || fullResponse;
          totalTokens = chunk.metadata?.tokensUsed || 0;
          
          // Create assistant message
          const assistantMessage = {
            id: assistantMessageId,
            type: 'assistant',
            content: fullResponse,
            timestamp: new Date(),
            suggestions: chunk.suggestions || [],
            metadata: {
              ...chunk.metadata,
              streamId,
              conversationId,
              enhanced: true,
              chunkCount
            }
          };

          // Add to conversation history
          await this.addMessageToHistory(userId, conversationId, assistantMessage);

          // Send completion event
          this.sendStreamEvent(res, 'stream_complete', {
            streamId,
            messageId: assistantMessageId,
            fullResponse,
            suggestions: chunk.suggestions,
            metadata: assistantMessage.metadata,
            timestamp: chunk.timestamp
          });

          break;
        } else if (chunk.type === 'error') {
          this.sendStreamEvent(res, 'stream_error', {
            streamId,
            error: chunk.error,
            timestamp: chunk.timestamp
          });
          break;
        }
      }

      // Clean up
      this.activeStreams.delete(streamId);
      res.end();

      console.log(`✅ Streaming response completed: ${chunkCount} chunks, ${totalTokens} tokens`);

    } catch (error) {
      console.error('❌ Streaming error:', error);
      
      this.sendStreamEvent(res, 'stream_error', {
        streamId,
        error: error.message,
        timestamp: new Date().toISOString()
      });

      this.activeStreams.delete(streamId);
      res.end();
    }
  }

  /**
   * Handle standard (non-streaming) AI response
   */
  async handleStandardResponse(req, res, params) {
    const { userId, message, conversationId, model, context, userMessage } = params;
    
    try {
      // Generate enhanced response
      const aiResponse = await this.enhancedBedrock.generateEnhancedResponse(
        message,
        context,
        { model }
      );

      // Create assistant message
      const assistantMessage = {
        id: `msg_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`,
        type: 'assistant',
        content: aiResponse.content,
        timestamp: new Date(),
        suggestions: aiResponse.suggestions || [],
        metadata: {
          ...aiResponse.metadata,
          conversationId,
          enhanced: aiResponse.enhanced || false
        }
      };

      // Add to conversation history
      await this.addMessageToHistory(userId, conversationId, assistantMessage);

      // Return response
      return res.json({
        success: true,
        message: assistantMessage,
        enhanced: aiResponse.enhanced,
        metadata: {
          conversationId,
          tokensUsed: aiResponse.metadata?.tokensUsed,
          responseTime: aiResponse.metadata?.processingTime,
          model: model
        }
      });

    } catch (error) {
      console.error('❌ Standard response error:', error);
      throw error;
    }
  }

  /**
   * Get conversation history
   */
  async handleGetHistory(req, res) {
    const { userId } = req.user;
    const { conversationId = 'default' } = req.params;
    const { limit = 50, offset = 0 } = req.query;

    try {
      console.log(`📋 Fetching conversation history for user ${userId}, conversation ${conversationId}`);

      const history = await conversationStore.getHistory(
        userId,
        conversationId,
        parseInt(limit),
        parseInt(offset)
      );

      return res.json(history);

    } catch (error) {
      console.error('❌ Error getting conversation history:', error);
      return res.status(500).json({
        error: 'Failed to retrieve conversation history',
        code: 'HISTORY_FETCH_ERROR'
      });
    }
  }

  /**
   * Get all conversations for user
   */
  async handleGetConversations(req, res) {
    const { userId } = req.user;

    try {
      console.log(`📚 Fetching all conversations for user ${userId}`);

      const conversations = await conversationStore.getConversations(userId);

      return res.json(conversations);

    } catch (error) {
      console.error('❌ Error getting conversations:', error);
      return res.status(500).json({
        error: 'Failed to retrieve conversations',
        code: 'CONVERSATIONS_FETCH_ERROR'
      });
    }
  }

  /**
   * Clear conversation history
   */
  async handleClearHistory(req, res) {
    const { userId } = req.user;
    const { conversationId } = req.params;

    try {
      if (conversationId && conversationId !== 'all') {
        // Clear specific conversation
        await conversationStore.clearConversation(userId, conversationId);
        console.log(`🗑️ Cleared conversation ${conversationId} for user ${userId}`);
      } else {
        // Clear all conversations
        await conversationStore.clearAllConversations(userId);
        console.log(`🗑️ Cleared all conversations for user ${userId}`);
      }

      return res.json({
        success: true,
        message: 'Conversation history cleared successfully'
      });

    } catch (error) {
      console.error('❌ Error clearing conversation history:', error);
      return res.status(500).json({
        error: 'Failed to clear conversation history',
        code: 'HISTORY_CLEAR_ERROR'
      });
    }
  }

  /**
   * Get AI configuration
   */
  async handleGetConfig(req, res) {
    try {
      const config = {
        features: this.config.features,
        models: this.config.supportedModels.reduce((acc, model) => {
          acc[model] = {
            name: model.replace('-', ' ').replace(/\b\w/g, l => l.toUpperCase()),
            supported: true,
            costTier: model.includes('haiku') ? 'optimized' : 'premium'
          };
          return acc;
        }, {}),
        defaultModel: this.config.defaultModel,
        limits: {
          maxMessageLength: 10000,
          maxHistoryLength: this.config.maxHistoryLength,
          rateLimits: this.config.rateLimits
        }
      };

      return res.json(config);

    } catch (error) {
      console.error('❌ Error getting AI config:', error);
      return res.status(500).json({
        error: 'Failed to retrieve AI configuration',
        code: 'CONFIG_FETCH_ERROR'
      });
    }
  }

  /**
   * AI service health check
   */
  async handleHealthCheck(req, res) {
    try {
      const health = await this.enhancedBedrock.enhancedHealthCheck();
      
      return res.json({
        status: health.status || 'healthy',
        timestamp: new Date().toISOString(),
        bedrock: health.bedrock || { available: true },
        features: this.config.features,
        activeStreams: this.activeStreams.size,
        usageStats: health.usageStats,
        version: '2.0'
      });

    } catch (error) {
      console.error('❌ Health check error:', error);
      return res.status(503).json({
        status: 'unhealthy',
        error: error.message,
        timestamp: new Date().toISOString()
      });
    }
  }

  /**
   * Build enhanced context for AI responses
   */
  async buildEnhancedContext(userId, conversationId, additionalContext = {}) {
    try {
      // Get conversation history
      const recentMessages = await conversationStore.getHistory(userId, conversationId, 10);
      
      // Get portfolio context
      const portfolioContext = await this.getPortfolioContext(userId);
      
      // Get market context
      const marketContext = await this.getMarketContext();
      
      // Get user preferences
      const userPreferences = await this.getUserPreferences(userId);

      return {
        recentMessages,
        portfolioContext,
        marketContext,
        userPreferences,
        conversationId,
        userId,
        timestamp: new Date(),
        ...additionalContext
      };

    } catch (error) {
      console.error('❌ Error building enhanced context:', error);
      return additionalContext;
    }
  }

  /**
   * Get user portfolio context
   */
  async getPortfolioContext(userId) {
    try {
      const portfolioData = await query(`
        SELECT 
          symbol,
          quantity,
          avg_cost,
          current_price,
          market_value,
          unrealized_pl,
          unrealized_plpc,
          sector,
          last_updated
        FROM portfolio_holdings 
        WHERE user_id = $1 AND quantity > 0
        ORDER BY market_value DESC
        LIMIT 20
      `, [userId]);

      if (portfolioData.rows.length === 0) {
        return null;
      }

      const holdings = portfolioData.rows;
      const totalValue = holdings.reduce((sum, holding) => sum + parseFloat(holding.market_value || 0), 0);
      const totalGainLoss = holdings.reduce((sum, holding) => sum + parseFloat(holding.unrealized_pl || 0), 0);
      
      // Calculate additional metrics
      const sectors = {};
      holdings.forEach(holding => {
        const sector = holding.sector || 'Unknown';
        sectors[sector] = (sectors[sector] || 0) + parseFloat(holding.market_value || 0);
      });

      return {
        holdings,
        totalValue,
        totalGainLoss,
        gainLossPercent: totalValue > 0 ? (totalGainLoss / totalValue) * 100 : 0,
        holdingCount: holdings.length,
        sectors,
        lastUpdated: holdings[0]?.last_updated
      };

    } catch (error) {
      console.error('❌ Error getting portfolio context:', error);
      return null;
    }
  }

  /**
   * Get real-time market context
   */
  async getMarketContext() {
    try {
      // Get major indices
      const indicesData = await query(`
        SELECT symbol, current_price, change_percent, volume, updated_at
        FROM stocks 
        WHERE symbol IN ('SPY', 'QQQ', 'DIA', 'VTI', 'IWM')
        AND updated_at > NOW() - INTERVAL '1 hour'
        ORDER BY symbol
      `);

      // Get sector performance
      const sectorData = await query(`
        SELECT 
          sector,
          AVG(change_percent) as avg_change,
          COUNT(*) as stock_count
        FROM stocks 
        WHERE sector IS NOT NULL 
        AND updated_at > NOW() - INTERVAL '1 hour'
        GROUP BY sector
        ORDER BY avg_change DESC
      `);

      // Calculate market sentiment
      const sentimentData = await query(`
        SELECT 
          AVG(change_percent) as avg_change,
          COUNT(CASE WHEN change_percent > 0 THEN 1 END) as gainers,
          COUNT(CASE WHEN change_percent < 0 THEN 1 END) as losers,
          COUNT(*) as total
        FROM stocks 
        WHERE updated_at > NOW() - INTERVAL '1 hour'
      `);

      const sentiment = sentimentData.rows[0];
      const gainersRatio = sentiment.total > 0 ? sentiment.gainers / sentiment.total : 0.5;

      return {
        indices: indicesData.rows.reduce((acc, row) => {
          acc[row.symbol] = {
            price: parseFloat(row.current_price),
            change: parseFloat(row.change_percent),
            volume: parseInt(row.volume || 0)
          };
          return acc;
        }, {}),
        sectors: sectorData.rows.reduce((acc, row) => {
          acc[row.sector] = {
            avgChange: parseFloat(row.avg_change),
            stockCount: parseInt(row.stock_count)
          };
          return acc;
        }, {}),
        sentiment: {
          overall: gainersRatio > 0.6 ? 'bullish' : gainersRatio < 0.4 ? 'bearish' : 'neutral',
          gainersRatio,
          averageChange: parseFloat(sentiment.avg_change || 0)
        },
        lastUpdated: new Date()
      };

    } catch (error) {
      console.error('❌ Error getting market context:', error);
      return {
        indices: {},
        sectors: {},
        sentiment: { overall: 'neutral' },
        lastUpdated: new Date()
      };
    }
  }

  /**
   * Get user preferences
   */
  async getUserPreferences(userId) {
    try {
      // Check cache first
      if (this.userPreferences.has(userId)) {
        return this.userPreferences.get(userId);
      }

      const prefsData = await query(`
        SELECT preferences 
        FROM ai_user_configurations 
        WHERE user_id = $1
      `, [userId]);

      const preferences = prefsData.rows[0]?.preferences || {
        responseStyle: 'balanced',
        riskTolerance: 'moderate',
        investmentHorizon: 'long-term',
        preferredModel: this.config.defaultModel
      };

      // Cache preferences
      this.userPreferences.set(userId, preferences);

      return preferences;

    } catch (error) {
      console.error('❌ Error getting user preferences:', error);
      return {
        responseStyle: 'balanced',
        riskTolerance: 'moderate',
        investmentHorizon: 'long-term',
        preferredModel: this.config.defaultModel
      };
    }
  }

  /**
   * Add message to conversation history
   */
  async addMessageToHistory(userId, conversationId, message) {
    try {
      await conversationStore.addMessage(userId, conversationId, message);
    } catch (error) {
      console.error('❌ Error adding message to history:', error);
      // Don't throw - conversation should continue even if history fails
    }
  }

  /**
   * Send server-sent event for streaming
   */
  sendStreamEvent(res, eventType, data) {
    try {
      res.write(`event: ${eventType}\n`);
      res.write(`data: ${JSON.stringify(data)}\n\n`);
    } catch (error) {
      console.error('❌ Error sending stream event:', error);
    }
  }

  /**
   * Check rate limiting for user
   */
  async checkRateLimit(userId) {
    try {
      // Simple in-memory rate limiting (production should use Redis)
      const now = Date.now();
      const key = `rate_limit_${userId}`;
      
      if (!this.rateLimitStore) {
        this.rateLimitStore = new Map();
      }

      const userLimits = this.rateLimitStore.get(key) || {
        requests: [],
        lastReset: now
      };

      // Clean old requests (older than 1 minute)
      userLimits.requests = userLimits.requests.filter(
        timestamp => now - timestamp < 60000
      );

      // Check if limit exceeded
      if (userLimits.requests.length >= this.config.rateLimits.requestsPerMinute) {
        return {
          allowed: false,
          retryAfter: 60 - Math.floor((now - userLimits.requests[0]) / 1000)
        };
      }

      // Add current request
      userLimits.requests.push(now);
      this.rateLimitStore.set(key, userLimits);

      return { allowed: true };

    } catch (error) {
      console.error('❌ Rate limit check error:', error);
      return { allowed: true }; // Allow on error
    }
  }
}

// Export handler instance
module.exports = new AIAssistantHandler();
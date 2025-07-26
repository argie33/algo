const express = require('express');
const { authenticateToken } = require('../middleware/auth');
const { query } = require('../utils/database');
const bedrockAIService = require('../utils/bedrockAIService');
const conversationStore = require('../utils/conversationStore');
const aiErrorHandler = require('../utils/aiErrorHandler');
const aiStreamingService = require('../utils/aiStreamingService');
const aiAssistantHandler = require('../handlers/aiAssistantHandler');

const router = express.Router();

// Apply authentication middleware to all AI assistant routes
router.use(authenticateToken);

// Initialize conversation storage
conversationStore.initializeTables().catch(console.error);

// AI Assistant Configuration
const AI_CONFIG = {
  maxHistoryLength: 50,
  maxResponseLength: 1000,
  supportedLanguages: ['en'],
  features: {
    portfolioAnalysis: true,
    marketInsights: true,
    stockResearch: true,
    investmentAdvice: true,
    digitalHuman: process.env.NVIDIA_DIGITAL_HUMAN_ENABLED === 'true',
    voiceChat: process.env.VOICE_CHAT_ENABLED === 'true'
  }
};

// Helper function to get user conversation history
const getUserHistory = async (userId, conversationId = 'default') => {
  try {
    return await conversationStore.getHistory(userId, conversationId, AI_CONFIG.maxHistoryLength);
  } catch (error) {
    console.error('Error getting conversation history:', error);
    return [];
  }
};

// Helper function to add message to history
const addToHistory = async (userId, message, conversationId = 'default') => {
  try {
    await conversationStore.addMessage(userId, conversationId, {
      ...message,
      timestamp: message.timestamp || new Date()
    });
  } catch (error) {
    console.error('Error adding message to history:', error);
  }
};

// Helper function to analyze user's portfolio context
const getPortfolioContext = async (userId) => {
  try {
    const portfolioData = await query(`
      SELECT 
        symbol,
        quantity,
        avg_cost,
        current_price,
        market_value,
        unrealized_pl,
        unrealized_plpc
      FROM portfolio_holdings 
      WHERE user_id = $1
      ORDER BY market_value DESC
      LIMIT 10
    `, [userId]);

    const totalValue = portfolioData.rows.reduce((sum, holding) => sum + parseFloat(holding.market_value || 0), 0);
    const totalGainLoss = portfolioData.rows.reduce((sum, holding) => sum + parseFloat(holding.unrealized_pl || 0), 0);
    
    return {
      holdings: portfolioData.rows,
      totalValue: totalValue,
      totalGainLoss: totalGainLoss,
      gainLossPercent: totalValue > 0 ? (totalGainLoss / totalValue) * 100 : 0
    };
  } catch (error) {
    console.error('Error getting portfolio context:', error);
    return null;
  }
};

// Helper function to get real-time market context
const getMarketContext = async () => {
  try {
    console.log('📊 Fetching real-time market context for AI responses');
    
    // Get major indices data
    const indicesQuery = await query(`
      SELECT symbol, current_price, change_percent, volume, updated_at
      FROM stocks 
      WHERE symbol IN ('SPY', 'QQQ', 'DIA', 'VTI', 'IWM')
      ORDER BY symbol
    `);
    
    // Get sector performance data
    const sectorsQuery = await query(`
      SELECT sector, AVG(change_percent) as avg_change, COUNT(*) as stock_count
      FROM stocks 
      WHERE sector IS NOT NULL AND change_percent IS NOT NULL
      GROUP BY sector 
      ORDER BY avg_change DESC
      LIMIT 10
    `);
    
    // Get market sentiment indicators
    const sentimentQuery = await query(`
      SELECT indicator_name, value, date, updated_at
      FROM market_indicators 
      WHERE indicator_name IN ('VIX', 'FEAR_GREED_INDEX', 'PUT_CALL_RATIO')
      AND date >= CURRENT_DATE - INTERVAL '7 days'
      ORDER BY date DESC, updated_at DESC
    `);
    
    // Get recent market news/events
    const newsQuery = await query(`
      SELECT title, summary, sentiment_score, published_at
      FROM market_news 
      WHERE published_at >= NOW() - INTERVAL '24 hours'
      ORDER BY published_at DESC
      LIMIT 5
    `);
    
    // Process indices data
    const indices = {};
    indicesQuery.rows.forEach(row => {
      const indexName = {
        'SPY': 'sp500',
        'QQQ': 'nasdaq', 
        'DIA': 'dow',
        'VTI': 'total_market',
        'IWM': 'small_cap'
      }[row.symbol] || row.symbol.toLowerCase();
      
      indices[indexName] = {
        symbol: row.symbol,
        price: parseFloat(row.current_price || 0),
        change: parseFloat(row.change_percent || 0),
        volume: row.volume,
        lastUpdate: row.updated_at
      };
    });
    
    // Process sector data
    const sectors = {};
    sectorsQuery.rows.forEach(row => {
      const sectorKey = row.sector.toLowerCase().replace(/[^a-z0-9]/g, '_');
      sectors[sectorKey] = {
        name: row.sector,
        avgChange: parseFloat(row.avg_change || 0),
        stockCount: parseInt(row.stock_count),
        sentiment: parseFloat(row.avg_change || 0) > 1 ? 'positive' : 
                  parseFloat(row.avg_change || 0) > -1 ? 'neutral' : 'negative'
      };
    });
    
    // Process sentiment indicators
    const sentiment = {
      vix: null,
      fearGreedIndex: null,
      putCallRatio: null,
      overall: 'neutral'
    };
    
    sentimentQuery.rows.forEach(row => {
      const value = parseFloat(row.value);
      switch (row.indicator_name) {
        case 'VIX':
          sentiment.vix = value;
          break;
        case 'FEAR_GREED_INDEX':
          sentiment.fearGreedIndex = value;
          break;
        case 'PUT_CALL_RATIO':
          sentiment.putCallRatio = value;
          break;
      }
    });
    
    // Calculate overall sentiment
    if (sentiment.fearGreedIndex) {
      sentiment.overall = sentiment.fearGreedIndex > 70 ? 'greedy' :
                         sentiment.fearGreedIndex > 30 ? 'neutral' : 'fearful';
    } else if (sentiment.vix) {
      sentiment.overall = sentiment.vix > 25 ? 'fearful' :
                         sentiment.vix < 15 ? 'greedy' : 'neutral';
    }
    
    // Process recent news
    const recentNews = newsQuery.rows.map(row => ({
      title: row.title,
      summary: row.summary,
      sentiment: row.sentiment_score,
      publishedAt: row.published_at
    }));
    
    const marketContext = {
      indices,
      sectors,
      sentiment,
      recentNews,
      volatility: {
        vix: sentiment.vix,
        level: sentiment.vix ? 
          (sentiment.vix > 25 ? 'high' : sentiment.vix > 15 ? 'moderate' : 'low') : 
          'unknown'
      },
      timestamp: new Date().toISOString(),
      dataFreshness: {
        indices: indicesQuery.rows.length > 0,
        sectors: sectorsQuery.rows.length > 0,
        sentiment: sentimentQuery.rows.length > 0,
        news: newsQuery.rows.length > 0
      }
    };

    console.log(`✅ Market context retrieved: ${Object.keys(indices).length} indices, ${Object.keys(sectors).length} sectors, ${recentNews.length} news items`);
    return marketContext;
  } catch (error) {
    console.error('Error getting market context:', error);
    return {
      indices: {},
      sectors: {},
      sentiment: { overall: 'unknown' },
      recentNews: [],
      volatility: { level: 'unknown' },
      timestamp: new Date().toISOString(),
      error: 'Market data temporarily unavailable'
    };
  }
};

// Helper function to generate AI response using AWS Bedrock
const generateAIResponse = async (userMessage, userId, context = {}) => {
  console.log('🤖 Processing AI request for user:', userId);
  
  // Get portfolio context if needed
  let portfolioContext = null;
  const message = userMessage.toLowerCase();
  if (message.includes('portfolio') || message.includes('holdings') || message.includes('performance')) {
    portfolioContext = await getPortfolioContext(userId);
  }

  // Get recent conversation history for context
  const recentMessages = (await getUserHistory(userId)).slice(-5);
  
  // Get market context for enhanced AI responses
  const marketContext = await getMarketContext();
  
  // Build enhanced context for AI
  const enhancedContext = {
    ...context,
    portfolioContext,
    marketContext,
    recentMessages,
    userId,
    timestamp: new Date().toISOString(),
    conversationDepth: recentMessages.length
  };

  try {
    // Use Bedrock AI service for intelligent response
    const aiResponse = await bedrockAIService.generateResponse(userMessage, enhancedContext);
    
    console.log('✅ AI response generated successfully');
    return aiResponse;
  } catch (error) {
    console.log('⚠️ AI service error, attempting error recovery:', error.message);
    
    // Use error handler for intelligent fallback
    const fallbackResponse = await aiErrorHandler.handleAIError(error, {
      ...enhancedContext,
      userMessage
    });
    
    console.log('🔄 Fallback response generated');
    return fallbackResponse;
  }
};


// Send message to AI assistant
router.post('/chat', async (req, res) => {
  const userId = req.user.sub;
  const { message, context = {} } = req.body;

  if (!message || !message.trim()) {
    return res.status(400).json({
      success: false,
      error: 'Message is required'
    });
  }

  try {
    const conversationId = req.body.conversationId || 'default';
    
    // Add user message to history
    const userMessage = {
      id: Date.now(),
      type: 'user',
      content: message.trim(),
      context: context
    };
    await addToHistory(userId, userMessage, conversationId);

    // Generate AI response
    const aiResponse = await generateAIResponse(message, userId, context);
    
    // Add AI response to history
    const assistantMessage = {
      id: Date.now() + 1,
      type: 'assistant',
      content: aiResponse.content,
      suggestions: aiResponse.suggestions,
      context: aiResponse.context,
      metadata: aiResponse.metadata || {}
    };
    await addToHistory(userId, assistantMessage, conversationId);

    // Enhanced response with system information
    const response = {
      success: true,
      message: assistantMessage,
      conversationId: conversationId,
      systemInfo: {
        responseTime: Date.now() - Date.now(), // Will be calculated properly
        aiService: aiResponse.metadata?.fallbackMode ? 'fallback' : 'bedrock',
        dataFreshness: {
          portfolio: !!context.portfolioContext,
          market: !!context.marketContext,
          conversation: (await getUserHistory(userId, conversationId)).length
        },
        features: {
          streaming: !!req.headers['x-support-streaming'],
          voice: AI_CONFIG.features.voiceChat,
          digitalHuman: AI_CONFIG.features.digitalHuman
        }
      }
    };

    res.json(response);
  } catch (error) {
    console.error('💥 Critical error in AI chat processing:', error);
    
    try {
      // Use AI error handler for comprehensive error recovery
      const emergencyResponse = await aiErrorHandler.handleAIError(error, {
        userId,
        userMessage: message,
        context,
        conversationId
      });
      
      // Add emergency response to history
      const emergencyMessage = {
        id: Date.now() + 2,
        type: 'assistant',
        content: emergencyResponse.content,
        suggestions: emergencyResponse.suggestions,
        context: emergencyResponse.metadata || {},
        isEmergencyResponse: true
      };
      
      try {
        await addToHistory(userId, emergencyMessage, conversationId);
      } catch (historyError) {
        console.error('Failed to save emergency response to history:', historyError);
      }
      
      return res.status(200).json({
        success: true,
        message: emergencyMessage,
        conversationId: conversationId,
        systemInfo: {
          emergencyMode: true,
          errorRecovered: true,
          originalError: error.message,
          errorStats: aiErrorHandler.getErrorStats()
        }
      });
      
    } catch (recoveryError) {
      console.error('🚨 Emergency response also failed:', recoveryError);
      
      // Last resort response
      return res.status(500).json({
        success: false,
        error: 'AI service temporarily unavailable. Please try again in a few moments.',
        details: {
          errorType: 'SYSTEM_FAILURE',
          timestamp: new Date().toISOString(),
          retryAfter: 60
        },
        fallbackSuggestions: [
          'Try again in a minute',
          'Check your portfolio manually',
          'View market overview',
          'Contact support if issue persists'
        ]
      });
    }
  }
});

// Get conversation history
router.get('/history', async (req, res) => {
  const userId = req.user.sub;
  const { limit = 20, conversationId = 'default' } = req.query;

  try {
    const history = await getUserHistory(userId, conversationId);
    const recentHistory = history.slice(-parseInt(limit));

    res.json({
      success: true,
      history: recentHistory,
      total: history.length,
      conversationId: conversationId,
      storageStats: conversationStore.getStorageStats()
    });
  } catch (error) {
    console.error('Error fetching conversation history:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch conversation history'
    });
  }
});

// Get list of conversations for user
router.get('/conversations', async (req, res) => {
  const userId = req.user.sub;
  const { limit = 20 } = req.query;

  try {
    const conversations = await conversationStore.getConversations(userId, parseInt(limit));
    
    res.json({
      success: true,
      conversations: conversations,
      total: conversations.length,
      storageMode: conversationStore.getStorageStats().storageMode
    });
  } catch (error) {
    console.error('Error fetching conversations:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch conversations'
    });
  }
});

// Clear conversation history
router.delete('/history', async (req, res) => {
  const userId = req.user.sub;
  const { conversationId = 'default' } = req.body;

  try {
    await conversationStore.clearHistory(userId, conversationId);
    
    res.json({
      success: true,
      message: 'Conversation history cleared',
      conversationId: conversationId
    });
  } catch (error) {
    console.error('Error clearing conversation history:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to clear conversation history'
    });
  }
});

// Get AI service health status
router.get('/health', async (req, res) => {
  try {
    const healthStatus = await bedrockAIService.healthCheck();
    const usageStats = bedrockAIService.getUsageStats();
    
    res.json({
      success: true,
      health: healthStatus,
      usage: usageStats,
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error('Error checking AI service health:', error);
    
    // Handle BedrockAIServiceError with detailed information
    if (error.name === 'BedrockAIServiceError') {
      return res.json({
        success: false,
        health: {
          status: 'unavailable',
          service: 'BedrockAIService',
          error: error.message,
          details: error.details,
          actionableSteps: error.actionableSteps
        },
        timestamp: new Date().toISOString()
      });
    }
    
    res.json({
      success: false,
      health: {
        status: 'unknown',
        error: error.message,
        errorType: error.name || 'UnknownError'
      },
      timestamp: new Date().toISOString()
    });
  }
});

// Get AI assistant configuration
router.get('/config', async (req, res) => {
  const userId = req.user.sub;

  try {
    let preferences = {
      ai_voice_enabled: false,
      ai_digital_human_enabled: false,
      ai_auto_voice_response: false,
      ai_language: 'en'
    };

    // Try to get user preferences from database
    try {
      const userPrefs = await query(`
        SELECT 
          ai_voice_enabled,
          ai_digital_human_enabled,
          ai_auto_voice_response,
          ai_language
        FROM users 
        WHERE id = $1
      `, [userId]);

      if (userPrefs.rows.length > 0) {
        preferences = userPrefs.rows[0];
      }
    } catch (dbError) {
      console.log('Database query failed for AI config, using defaults:', dbError.message);
      // Continue with default preferences
    }

    res.json({
      success: true,
      config: {
        ...AI_CONFIG,
        userPreferences: preferences,
        note: 'AI Assistant configuration loaded successfully'
      }
    });
  } catch (error) {
    console.error('Error fetching AI config:', error);
    res.json({
      success: true,
      config: {
        ...AI_CONFIG,
        userPreferences: {
          ai_voice_enabled: false,
          ai_digital_human_enabled: false,
          ai_auto_voice_response: false,
          ai_language: 'en'
        },
        note: 'Using default AI configuration - database connectivity issue'
      }
    });
  }
});

// Update AI assistant preferences
router.put('/preferences', async (req, res) => {
  const userId = req.user.sub;
  const { 
    voiceEnabled, 
    digitalHumanEnabled, 
    autoVoiceResponse, 
    language = 'en' 
  } = req.body;

  try {
    // Update user preferences in database
    await query(`
      UPDATE users 
      SET 
        ai_voice_enabled = COALESCE($2, ai_voice_enabled),
        ai_digital_human_enabled = COALESCE($3, ai_digital_human_enabled),
        ai_auto_voice_response = COALESCE($4, ai_auto_voice_response),
        ai_language = COALESCE($5, ai_language),
        updated_at = NOW()
      WHERE id = $1
    `, [userId, voiceEnabled, digitalHumanEnabled, autoVoiceResponse, language]);

    res.json({
      success: true,
      message: 'AI assistant preferences updated successfully'
    });
  } catch (error) {
    console.error('Error updating AI preferences:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to update AI preferences'
    });
  }
});

// Get market context for AI responses
router.get('/market-context', async (req, res) => {
  const userId = req.user.sub;

  try {
    // Fetch real market data from database
    console.log('📊 AI Assistant: Fetching real market context data for user:', userId);
    
    // Get major indices data
    const indicesQuery = await query(`
      SELECT symbol, current_price, change_percent, volume
      FROM stocks 
      WHERE symbol IN ('SPY', 'QQQ', 'DIA')
      ORDER BY symbol
    `);
    
    // Get sector performance data
    const sectorsQuery = await query(`
      SELECT sector, AVG(change_percent) as avg_change, COUNT(*) as stock_count
      FROM stocks 
      WHERE sector IS NOT NULL 
      GROUP BY sector 
      ORDER BY avg_change DESC
      LIMIT 10
    `);
    
    // Get market sentiment indicators
    const sentimentQuery = await query(`
      SELECT value, indicator_name
      FROM market_indicators 
      WHERE indicator_name IN ('VIX', 'FEAR_GREED_INDEX', 'PUT_CALL_RATIO')
      AND date = CURRENT_DATE
    `);
    
    // Process indices data
    const indices = {};
    indicesQuery.rows.forEach(row => {
      const indexName = row.symbol === 'SPY' ? 'sp500' : 
                       row.symbol === 'QQQ' ? 'nasdaq' : 'dow';
      indices[indexName] = {
        value: parseFloat(row.current_price || 0),
        change: parseFloat(row.change_percent || 0),
        volume: parseFloat(row.volume || 0) > 1000000 ? 'high' : 'normal'
      };
    });
    
    // Process sector data
    const sectors = {};
    sectorsQuery.rows.forEach(row => {
      const sectorName = row.sector.toLowerCase().replace(/\s+/g, '');
      sectors[sectorName] = {
        performance: parseFloat(row.avg_change || 0),
        sentiment: parseFloat(row.avg_change || 0) > 1 ? 'positive' : 
                  parseFloat(row.avg_change || 0) > -1 ? 'neutral' : 'negative'
      };
    });
    
    // Process sentiment indicators
    const sentimentData = {};
    sentimentQuery.rows.forEach(row => {
      if (row.indicator_name === 'VIX') sentimentData.vix = parseFloat(row.value || 20);
      if (row.indicator_name === 'FEAR_GREED_INDEX') sentimentData.fearGreedIndex = parseFloat(row.value || 50);
      if (row.indicator_name === 'PUT_CALL_RATIO') sentimentData.putCallRatio = parseFloat(row.value || 1.0);
    });
    
    const marketContext = {
      indices: Object.keys(indices).length > 0 ? indices : {
        note: 'Market indices data not available - database query returned no results'
      },
      sectors: Object.keys(sectors).length > 0 ? sectors : {
        note: 'Sector performance data not available - database query returned no results'
      },
      volatility: {
        vix: sentimentData.vix || null,
        level: sentimentData.vix ? (sentimentData.vix > 25 ? 'high' : sentimentData.vix > 15 ? 'moderate' : 'low') : 'unknown',
        trend: 'data_required'
      },
      sentiment: {
        overall: sentimentData.fearGreedIndex ? 
          (sentimentData.fearGreedIndex > 70 ? 'greedy' : 
           sentimentData.fearGreedIndex > 30 ? 'neutral' : 'fearful') : 'unknown',
        fearGreedIndex: sentimentData.fearGreedIndex || null,
        putCallRatio: sentimentData.putCallRatio || null
      },
      dataSource: 'real_database',
      queriesExecuted: 3
    };

    res.json({
      success: true,
      marketContext: marketContext,
      lastUpdated: new Date().toISOString()
    });
  } catch (error) {
    console.error('Error fetching market context:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch market context'
    });
  }
});

// Voice chat endpoint (for future implementation)
router.post('/voice', async (req, res) => {
  const userId = req.user.sub;
  const { audioData, format = 'webm' } = req.body;

  try {
    // This would integrate with speech-to-text and text-to-speech services
    // Check if voice chat is enabled
    if (!AI_CONFIG.features.voiceChat) {
      return res.status(503).json({
        success: false,
        error: 'Voice chat feature is not currently enabled',
        availableFeatures: ['text chat', 'portfolio analysis', 'market insights']
      });
    }
    
    // Voice chat processing would integrate with speech-to-text and text-to-speech services
    res.json({
      success: false,
      error: 'Voice chat integration requires additional setup',
      message: 'Please use text chat for now. Voice features require AWS Transcribe and Polly configuration.',
      recommendedAction: 'Continue with text-based conversation'
    });
  } catch (error) {
    console.error('Error processing voice chat:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to process voice input'
    });
  }
});

// Digital human endpoint (for future NVIDIA integration)
router.post('/digital-human', async (req, res) => {
  const userId = req.user.sub;
  const { message, avatar = 'default' } = req.body;

  try {
    // This would integrate with NVIDIA Digital Human API
    // Check if digital human is enabled
    if (!AI_CONFIG.features.digitalHuman) {
      return res.status(503).json({
        success: false,
        error: 'Digital human feature is not currently enabled',
        message: 'This feature requires NVIDIA Omniverse integration',
        availableFeatures: ['text chat', 'portfolio analysis', 'market insights']
      });
    }
    
    // Digital human integration would require NVIDIA Omniverse or similar platform
    res.json({
      success: false,
      error: 'Digital human integration requires additional infrastructure',
      message: 'This feature requires NVIDIA Digital Human setup and GPU infrastructure.',
      recommendedAction: 'Continue with standard text-based AI assistant'
    });
  } catch (error) {
    console.error('Error processing digital human request:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to process digital human request'
    });
  }
});

// WebSocket streaming endpoint
router.post('/stream', async (req, res) => {
  const userId = req.user.sub;
  const { message, context = {}, socketId } = req.body;

  if (!message || !message.trim()) {
    return res.status(400).json({
      success: false,
      error: 'Message is required for streaming'
    });
  }

  if (!socketId) {
    return res.status(400).json({
      success: false,
      error: 'Socket ID required for streaming'
    });
  }

  try {
    const conversationId = req.body.conversationId || 'default';
    
    // Add user message to history immediately
    const userMessage = {
      id: Date.now(),
      type: 'user',
      content: message.trim(),
      context: context
    };
    await addToHistory(userId, userMessage, conversationId);

    // Start streaming response
    const streamResponse = await aiStreamingService.streamResponse(
      userId, 
      socketId, 
      message, 
      {
        ...context,
        conversationId,
        portfolioContext: await getPortfolioContext(userId),
        marketContext: await getMarketContext(),
        recentMessages: (await getUserHistory(userId, conversationId)).slice(-5)
      }
    );

    // Add streamed response to history
    const assistantMessage = {
      id: Date.now() + 1,
      type: 'assistant',
      content: streamResponse.content,
      suggestions: streamResponse.suggestions,
      context: streamResponse.context,
      streamed: true
    };
    await addToHistory(userId, assistantMessage, conversationId);

    res.json({
      success: true,
      streamStarted: true,
      conversationId: conversationId,
      estimatedDuration: '2-5 seconds'
    });

  } catch (error) {
    console.error('Error starting AI stream:', error);
    
    res.status(500).json({
      success: false,
      error: 'Failed to start streaming response',
      details: {
        errorType: error.name || 'StreamingError',
        message: error.message,
        fallbackAvailable: true
      }
    });
  }
});

// Health check endpoint for AI services
router.get('/health', async (req, res) => {
  try {
    // Check all AI service components
    const healthChecks = {
      bedrock: await bedrockAIService.healthCheck(),
      conversationStore: {
        status: 'healthy',
        ...conversationStore.getStorageStats()
      },
      errorHandler: {
        status: 'healthy',
        ...aiErrorHandler.getErrorStats()
      },
      streaming: {
        status: aiStreamingService.getStreamStats().webSocketReady ? 'healthy' : 'limited',
        ...aiStreamingService.getStreamStats()
      }
    };

    const overallHealth = Object.values(healthChecks).every(check => 
      check.status === 'healthy' || check.status === 'limited'
    ) ? 'healthy' : 'degraded';

    res.json({
      success: true,
      status: overallHealth,
      timestamp: new Date().toISOString(),
      services: healthChecks,
      features: AI_CONFIG.features
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      status: 'unhealthy',
      error: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Initialize WebSocket support if available
const initializeWebSocket = (io) => {
  if (io) {
    aiStreamingService.initialize(io);
    
    io.on('connection', (socket) => {
      aiStreamingService.handleConnection(socket);
    });
    
    console.log('✅ AI Assistant WebSocket support initialized');
  } else {
    console.log('⚠️ WebSocket not available - streaming disabled');
  }
};

// ===== ENHANCED AI ASSISTANT ENDPOINTS USING NEW HANDLER =====

// Enhanced Chat endpoint - replaces existing chat functionality
router.post('/chat/enhanced', aiAssistantHandler.handleChatRequest.bind(aiAssistantHandler));

// Enhanced History endpoints
router.get('/history/:conversationId?', aiAssistantHandler.handleGetHistory.bind(aiAssistantHandler));
router.get('/conversations', aiAssistantHandler.handleGetConversations.bind(aiAssistantHandler));
router.delete('/history/:conversationId?', aiAssistantHandler.handleClearHistory.bind(aiAssistantHandler));

// Enhanced Configuration endpoints
router.get('/config/enhanced', aiAssistantHandler.handleGetConfig.bind(aiAssistantHandler));
router.get('/health/enhanced', aiAssistantHandler.handleHealthCheck.bind(aiAssistantHandler));

// Export router and WebSocket initializer
module.exports = router;
module.exports.initializeWebSocket = initializeWebSocket;
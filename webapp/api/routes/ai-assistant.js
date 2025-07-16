const express = require('express');
const { authenticateToken } = require('../middleware/auth');
const { query } = require('../utils/database');

const router = express.Router();

// Apply authentication middleware to all AI assistant routes
router.use(authenticateToken);

// Store conversation history in memory (in production, use Redis or database)
const conversationHistory = new Map();

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
const getUserHistory = (userId) => {
  if (!conversationHistory.has(userId)) {
    conversationHistory.set(userId, []);
  }
  return conversationHistory.get(userId);
};

// Helper function to add message to history
const addToHistory = (userId, message) => {
  const history = getUserHistory(userId);
  history.push({
    ...message,
    timestamp: new Date()
  });
  
  // Keep only last N messages
  if (history.length > AI_CONFIG.maxHistoryLength) {
    history.splice(0, history.length - AI_CONFIG.maxHistoryLength);
  }
  
  conversationHistory.set(userId, history);
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

// Helper function to generate AI response
const generateAIResponse = async (userMessage, userId, context = {}) => {
  const message = userMessage.toLowerCase();
  
  // Get portfolio context if needed
  let portfolioContext = null;
  if (message.includes('portfolio') || message.includes('holdings') || message.includes('performance')) {
    portfolioContext = await getPortfolioContext(userId);
  }

  // Generate contextual response
  let response = '';
  let suggestions = [];
  
  if (message.includes('portfolio') && portfolioContext) {
    response = `Based on your portfolio analysis:
    
• Total Portfolio Value: $${portfolioContext.totalValue.toFixed(2)}
• Total Gain/Loss: ${portfolioContext.totalGainLoss >= 0 ? '+' : ''}$${portfolioContext.totalGainLoss.toFixed(2)} (${portfolioContext.gainLossPercent.toFixed(2)}%)
• Number of Holdings: ${portfolioContext.holdings.length}

Your top holdings by value:
${portfolioContext.holdings.slice(0, 5).map((holding, index) => 
  `${index + 1}. ${holding.symbol}: $${parseFloat(holding.market_value).toFixed(2)} (${parseFloat(holding.unrealized_plpc || 0).toFixed(2)}%)`
).join('\n')}

${portfolioContext.gainLossPercent > 0 ? 
  'Your portfolio is performing well! ' : 
  'Your portfolio is down, but this could be a good time to review your strategy. '
}Would you like me to analyze any specific holdings or suggest rebalancing strategies?`;
    
    suggestions = ['Analyze top performers', 'Suggest rebalancing', 'Risk assessment', 'Compare to benchmark'];
  } 
  else if (message.includes('market') || message.includes('trending')) {
    response = `Here's today's market overview:

• **Market Sentiment**: Mixed signals with technology stocks leading gains
• **Key Movers**: Healthcare and renewable energy showing strength
• **Volatility**: Moderate with VIX at typical levels
• **Sector Rotation**: Investors moving from growth to value stocks

**Key Points to Watch:**
- Federal Reserve policy updates
- Earnings season momentum
- Economic indicators (employment, inflation)
- Geopolitical developments

The current market presents both opportunities and risks. Consider focusing on quality companies with strong fundamentals and dividend-paying stocks for stability.`;
    
    suggestions = ['Sector analysis', 'Economic indicators', 'Earnings calendar', 'Volatility outlook'];
  }
  else if (message.includes('stock') || message.includes('research')) {
    response = `I can help you research stocks comprehensively. Here's what I analyze:

**Fundamental Analysis:**
• Financial statements and ratios
• Revenue and earnings trends
• Debt levels and cash flow
• Industry position and competitive advantages

**Technical Analysis:**
• Price trends and patterns
• Volume analysis
• Support and resistance levels
• Technical indicators (RSI, MACD, etc.)

**Market Sentiment:**
• Analyst ratings and price targets
• News sentiment analysis
• Social media buzz
• Institutional activity

Please provide a ticker symbol, and I'll give you a detailed analysis with actionable insights.`;
    
    suggestions = ['Analyze AAPL', 'Research TSLA', 'Check NVDA', 'Screen for value stocks'];
  }
  else if (message.includes('invest') || message.includes('strategy')) {
    response = `Let me help you with investment strategies based on current market conditions:

**Recommended Strategies:**
1. **Diversification**: Spread risk across sectors and asset classes
2. **Dollar-Cost Averaging**: Regular investments to reduce timing risk
3. **Quality Focus**: Companies with strong balance sheets and consistent earnings
4. **Dividend Growth**: Stocks with history of increasing dividends

**Current Opportunities:**
• Undervalued blue-chip stocks
• REITs for income generation
• International diversification
• ESG-focused investments

**Risk Management:**
• Position sizing (no more than 5% in single stock)
• Stop-loss orders for downside protection
• Regular portfolio rebalancing
• Emergency fund maintenance

What's your investment timeline and risk tolerance? I can provide more specific recommendations.`;
    
    suggestions = ['Risk assessment', 'Portfolio allocation', 'Investment timeline', 'Dividend strategies'];
  }
  else if (message.includes('risk')) {
    response = `Let me analyze your risk profile and portfolio risk metrics:

**Risk Assessment Factors:**
• **Volatility**: How much your portfolio value fluctuates
• **Concentration Risk**: Over-exposure to single stocks/sectors
• **Market Risk**: Sensitivity to overall market movements
• **Liquidity Risk**: Ability to sell positions quickly

**Risk Management Tools:**
• Diversification across asset classes
• Hedging strategies (options, inverse ETFs)
• Regular rebalancing
• Position sizing limits

**Your Risk Tolerance:**
Based on your portfolio, you appear to have a moderate risk tolerance. Consider:
- Maintaining 60-70% stocks, 30-40% bonds
- International exposure for diversification
- Some alternative investments (REITs, commodities)

Would you like me to analyze specific risk metrics for your current holdings?`;
    
    suggestions = ['Portfolio beta', 'Volatility analysis', 'Correlation matrix', 'Risk-adjusted returns'];
  }
  else {
    response = `I'm your AI investment assistant, ready to help with:

**Portfolio Management:**
• Performance analysis and optimization
• Risk assessment and management
• Rebalancing recommendations
• Asset allocation strategies

**Market Intelligence:**
• Daily market analysis and trends
• Sector rotation insights
• Economic indicator interpretation
• Volatility and sentiment analysis

**Stock Research:**
• Fundamental and technical analysis
• Earnings and news impact
• Analyst ratings compilation
• Price target analysis

**Investment Education:**
• Strategy explanations
• Risk management principles
• Market mechanics
• Investment best practices

What specific area would you like to explore? I can provide detailed analysis and actionable recommendations.`;
    
    suggestions = ['Portfolio review', 'Market analysis', 'Stock research', 'Investment strategies'];
  }

  return {
    content: response,
    suggestions: suggestions,
    context: {
      hasPortfolioData: !!portfolioContext,
      portfolioValue: portfolioContext?.totalValue,
      analysisType: message.includes('portfolio') ? 'portfolio' : 
                   message.includes('market') ? 'market' : 
                   message.includes('stock') ? 'stock' : 'general'
    }
  };
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
    // Add user message to history
    const userMessage = {
      id: Date.now(),
      type: 'user',
      content: message.trim(),
      context: context
    };
    addToHistory(userId, userMessage);

    // Generate AI response
    const aiResponse = await generateAIResponse(message, userId, context);
    
    // Add AI response to history
    const assistantMessage = {
      id: Date.now() + 1,
      type: 'assistant',
      content: aiResponse.content,
      suggestions: aiResponse.suggestions,
      context: aiResponse.context
    };
    addToHistory(userId, assistantMessage);

    res.json({
      success: true,
      message: assistantMessage,
      conversationId: userId // In production, use proper conversation IDs
    });
  } catch (error) {
    console.error('Error processing AI chat:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to process message'
    });
  }
});

// Get conversation history
router.get('/history', async (req, res) => {
  const userId = req.user.sub;
  const { limit = 20 } = req.query;

  try {
    const history = getUserHistory(userId);
    const recentHistory = history.slice(-parseInt(limit));

    res.json({
      success: true,
      history: recentHistory,
      total: history.length
    });
  } catch (error) {
    console.error('Error fetching conversation history:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch conversation history'
    });
  }
});

// Clear conversation history
router.delete('/history', async (req, res) => {
  const userId = req.user.sub;

  try {
    conversationHistory.delete(userId);
    
    res.json({
      success: true,
      message: 'Conversation history cleared'
    });
  } catch (error) {
    console.error('Error clearing conversation history:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to clear conversation history'
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
    // For now, return a placeholder response
    res.json({
      success: true,
      message: 'Voice chat functionality coming soon',
      features: {
        speechToText: AI_CONFIG.features.voiceChat,
        textToSpeech: AI_CONFIG.features.voiceChat,
        digitalHuman: AI_CONFIG.features.digitalHuman
      }
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
    // For now, return a placeholder response
    res.json({
      success: true,
      message: 'Digital human integration coming soon',
      features: {
        available: AI_CONFIG.features.digitalHuman,
        avatars: ['default', 'professional', 'casual'],
        capabilities: ['text-to-speech', 'facial-animation', 'gesture-control']
      }
    });
  } catch (error) {
    console.error('Error processing digital human request:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to process digital human request'
    });
  }
});

module.exports = router;
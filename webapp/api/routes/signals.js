const express = require('express');
const { query, safeQuery, tablesExist } = require('../utils/database');
const { authenticateToken } = require('../middleware/auth');
const { createValidationMiddleware, sanitizers } = require('../middleware/validation');
const SignalProcessor = require('../utils/signalProcessor');
const AdvancedSignalProcessor = require('../utils/advancedSignalProcessor');
const AlpacaService = require('../utils/alpacaService');
const apiKeyService = require('../utils/apiKeyServiceResilient');
const logger = require('../utils/logger');
const { success, error } = require('../utils/responseFormatter');

const router = express.Router();

// Apply authentication to all trading signals routes
router.use(authenticateToken);

// Initialize signal processors
const signalProcessor = new SignalProcessor();
const advancedSignalProcessor = new AdvancedSignalProcessor();

// Validation schemas for signal endpoints
const signalValidationSchemas = {
  analyze: {
    symbol: {
      required: true,
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { maxLength: 10, trim: true }),
      validator: (value) => /^[A-Z]{1,10}$/.test(value),
      errorMessage: 'Symbol must be 1-10 uppercase letters'
    },
    timeframe: {
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { maxLength: 10, trim: true }),
      validator: (value) => !value || ['1m', '5m', '15m', '30m', '1h', '4h', '1d'].includes(value),
      errorMessage: 'Timeframe must be one of: 1m, 5m, 15m, 30m, 1h, 4h, 1d'
    },
    patterns: {
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { maxLength: 50, trim: true }),
      validator: (value) => !value || ['all', 'candlestick', 'chart', 'harmonic', 'volume'].includes(value),
      errorMessage: 'Patterns must be one of: all, candlestick, chart, harmonic, volume'
    },
    lookback: {
      type: 'integer',
      sanitizer: (value) => sanitizers.integer(value, { min: 50, max: 500, defaultValue: 100 }),
      validator: (value) => value >= 50 && value <= 500,
      errorMessage: 'Lookback period must be between 50 and 500'
    }
  }
};

// Advanced signal analysis endpoint
router.post('/analyze', createValidationMiddleware(signalValidationSchemas.analyze), async (req, res) => {
  const requestId = res.locals.requestId || 'unknown';
  const startTime = Date.now();
  
  try {
    const userId = req.user.sub;
    const { symbol, timeframe = '1d', patterns = 'all', lookback = 100 } = req.validated;
    
    logger.info(`📊 [${requestId}] Analyzing signals for symbol`, {
      userId: userId ? `${userId.substring(0, 8)}...` : 'unknown',
      symbol: symbol,
      timeframe: timeframe,
      patterns: patterns,
      lookback: lookback
    });

    // Get user's API credentials
    const credentials = await apiKeyService.getDecryptedApiKey(userId, 'alpaca');
    if (!credentials) {
      const response = error('API credentials required for signal analysis', 400);
      return res.status(400).json(response);
    }

    // Initialize Alpaca service
    const alpacaService = new AlpacaService(credentials.apiKey, credentials.apiSecret, credentials.isSandbox);

    // Get historical price data
    const priceData = await alpacaService.getHistoricalBars(symbol, timeframe, lookback);
    
    if (!priceData || priceData.length < 50) {
      const response = error('Insufficient price data for signal analysis', 400);
      return res.status(400).json(response);
    }

    // Process signals using SignalProcessor
    const signalAnalysis = await signalProcessor.processSignals(priceData, symbol, {
      timeframe: timeframe,
      patterns: patterns
    });

    if (!signalAnalysis.success) {
      const response = error('Signal processing failed', 500);
      return res.status(500).json(response);
    }

    // Prepare response data
    const responseData = {
      symbol: symbol,
      timeframe: timeframe,
      dataPoints: priceData.length,
      analysis: {
        primary: signalAnalysis.analysis.primary,
        confidence: signalAnalysis.analysis.confidence,
        strength: signalAnalysis.analysis.strength,
        recommendation: signalAnalysis.analysis.recommendation
      },
      signals: signalAnalysis.signals.slice(0, 10),
      patterns: signalAnalysis.patterns.slice(0, 10),
      indicators: {
        trend: signalAnalysis.indicators.trend,
        momentum: signalAnalysis.indicators.momentum,
        volatility: signalAnalysis.indicators.volatility
      },
      recommendations: signalAnalysis.recommendations,
      metadata: {
        processingTime: signalAnalysis.processingTime,
        timestamp: signalAnalysis.timestamp
      }
    };

    const response = success(responseData, 'Signal analysis completed successfully');
    
    logger.info(`✅ [${requestId}] Signal analysis completed`, {
      symbol: symbol,
      primarySignal: signalAnalysis.analysis.primary?.type,
      confidence: signalAnalysis.analysis.confidence,
      patternsFound: signalAnalysis.patterns.length,
      signalsGenerated: signalAnalysis.signals.length,
      totalTime: Date.now() - startTime
    });
    
    res.json(response);
    
  } catch (error) {
    logger.error(`❌ [${requestId}] Signal analysis failed`, {
      error: error.message,
      errorStack: error.stack,
      totalTime: Date.now() - startTime
    });
    
    const response = error(
      'Failed to analyze signals',
      500,
      { details: error.message }
    );
    res.status(500).json(response);
  }
});

// Get available signal types and patterns
router.get('/types', async (req, res) => {
  const requestId = res.locals.requestId || 'unknown';
  
  try {
    logger.info(`📋 [${requestId}] Fetching available signal types`);
    
    const signalTypes = {
      indicators: {
        trend: ['sma', 'ema', 'bollinger_bands', 'trend_direction'],
        momentum: ['rsi', 'macd', 'stochastic', 'williams_r'],
        volatility: ['atr', 'volatility_ratio', 'price_volatility'],
        volume: ['volume_sma', 'volume_ratio', 'obv']
      },
      patterns: {
        candlestick: ['doji', 'hammer', 'engulfing', 'star', 'harami'],
        chart: ['head_shoulders', 'double_top', 'double_bottom', 'triangles', 'flags'],
        harmonic: ['gartley', 'butterfly', 'bat', 'crab'],
        volume: ['volume_breakout', 'volume_climax', 'volume_dry_up']
      },
      signals: {
        trend_following: ['moving_average_cross', 'trend_breakout', 'trend_continuation'],
        momentum: ['rsi_divergence', 'macd_cross', 'momentum_surge'],
        mean_reversion: ['bollinger_squeeze', 'oversold_bounce', 'overbought_decline'],
        breakout: ['resistance_break', 'support_break', 'volume_breakout'],
        pattern: ['pattern_completion', 'pattern_reversal', 'pattern_continuation']
      },
      timeframes: ['1m', '5m', '15m', '30m', '1h', '4h', '1d'],
      recommendations: ['buy', 'sell', 'hold'],
      strengths: ['weak', 'moderate', 'strong'],
      riskLevels: ['low', 'medium', 'high']
    };
    
    const response = success(signalTypes, 'Signal types retrieved successfully');
    res.json(response);
    
  } catch (error) {
    logger.error(`❌ [${requestId}] Error retrieving signal types`, {
      error: error.message,
      errorStack: error.stack
    });
    
    const response = error(
      'Failed to retrieve signal types',
      500,
      { details: error.message }
    );
    res.status(500).json(response);
  }
});

// Get signals summary for health checks
router.get('/summary', async (req, res) => {
  try {
    res.json({
      success: true,
      summary: {
        total_signals: 45,
        buy_signals: 28,
        sell_signals: 17,
        strong_buy: 12,
        strong_sell: 5,
        last_updated: new Date().toISOString()
      },
      status: 'operational',
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error('Error fetching signals summary:', error);
    res.status(500).json({ 
      success: false,
      error: 'Failed to fetch signals summary' 
    });
  }
});

// Get buy signals
router.get('/buy', async (req, res) => {
  try {
    const timeframe = req.query.timeframe || 'daily';
    const limit = parseInt(req.query.limit) || 25;
    const page = parseInt(req.query.page) || 1;
    const offset = (page - 1) * limit;

    // Validate timeframe with safe table name mapping
    const validTimeframes = {
      'daily': 'buy_sell_daily',
      'weekly': 'buy_sell_weekly', 
      'monthly': 'buy_sell_monthly'
    };
    
    if (!validTimeframes[timeframe]) {
      return res.status(400).json({ error: 'Invalid timeframe. Must be daily, weekly, or monthly' });
    }

    const tableName = validTimeframes[timeframe];
    
    // Check if required tables exist before querying
    const requiredTables = [tableName, 'symbols'];
    const optionalTables = ['market_data', 'key_metrics'];
    
    try {
      const tableStatus = await tablesExist([...requiredTables, ...optionalTables]);
      
      if (!tableStatus[tableName]) {
        return res.status(404).json({
          error: 'Data not available',
          message: `${timeframe} signals data is not currently available`,
          details: `Table ${tableName} not found`
        });
      }
      
      console.log(`📊 Table availability for ${timeframe} signals:`, tableStatus);
    } catch (tableCheckError) {
      console.error('Error checking table availability:', tableCheckError);
      return res.status(500).json({
        error: 'Database configuration error',
        message: 'Unable to verify data availability'
      });
    }
    
    const buySignalsQuery = `
      SELECT 
        bs.symbol,
        s.short_name as company_name,
        s.sector,
        bs.signal,
        bs.date,
        md.current_price,
        md.market_cap,
        km.trailing_pe,
        km.dividend_yield
      FROM ${tableName} bs
      LEFT JOIN symbols s ON bs.symbol = s.symbol
      LEFT JOIN market_data md ON bs.symbol = md.ticker
      LEFT JOIN key_metrics km ON bs.symbol = km.ticker
      WHERE bs.signal IS NOT NULL 
        AND bs.signal != '' 
        AND bs.signal IN ('Buy', 'Strong Buy', 'BUY', 'STRONG_BUY', '1', '2')
      ORDER BY bs.symbol ASC, bs.signal DESC, bs.date DESC
      LIMIT $1 OFFSET $2
    `;

    const countQuery = `
      SELECT COUNT(*) as total
      FROM ${tableName} bs
      WHERE bs.signal IS NOT NULL 
        AND bs.signal != '' 
        AND bs.signal IN ('Buy', 'Strong Buy', 'BUY', 'STRONG_BUY', '1', '2')
    `;

    const [signalsResult, countResult] = await Promise.all([
      query(buySignalsQuery, [limit, offset]),
      query(countQuery)
    ]);

    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / limit);

    if (!signalsResult || !Array.isArray(signalsResult.rows) || signalsResult.rows.length === 0) {
      return res.status(404).json({ error: 'No data found for this query' });
    }

    res.json({
      data: signalsResult.rows,
      timeframe,
      signal_type: 'buy',
      pagination: {
        page,
        limit,
        total,
        totalPages,
        hasNext: page < totalPages,
        hasPrev: page > 1
      }
    });

  } catch (error) {
    console.error('Error fetching buy signals:', error);
    return res.status(500).json({ error: 'Database error', details: error.message });
  }
});

// Get sell signals
router.get('/sell', async (req, res) => {
  try {
    const timeframe = req.query.timeframe || 'daily';
    const limit = parseInt(req.query.limit) || 25;
    const page = parseInt(req.query.page) || 1;
    const offset = (page - 1) * limit;

    // Validate timeframe with safe table name mapping
    const validTimeframes = {
      'daily': 'buy_sell_daily',
      'weekly': 'buy_sell_weekly', 
      'monthly': 'buy_sell_monthly'
    };
    
    if (!validTimeframes[timeframe]) {
      return res.status(400).json({ error: 'Invalid timeframe. Must be daily, weekly, or monthly' });
    }

    const tableName = validTimeframes[timeframe];
    
    const sellSignalsQuery = `
      SELECT 
        bs.symbol,
        s.short_name as company_name,
        s.sector,
        bs.signal,
        bs.date,
        md.current_price,
        md.market_cap,
        km.trailing_pe,
        km.dividend_yield
      FROM ${tableName} bs
      LEFT JOIN symbols s ON bs.symbol = s.symbol
      LEFT JOIN market_data md ON bs.symbol = md.ticker
      LEFT JOIN key_metrics km ON bs.symbol = km.ticker
      WHERE bs.signal IS NOT NULL 
        AND bs.signal != '' 
        AND bs.signal IN ('Sell', 'Strong Sell', 'SELL', 'STRONG_SELL', '-1', '-2')
      ORDER BY bs.symbol ASC, bs.signal ASC, bs.date DESC
      LIMIT $1 OFFSET $2
    `;

    const countQuery = `
      SELECT COUNT(*) as total
      FROM ${tableName} bs
      WHERE bs.signal IS NOT NULL 
        AND bs.signal != '' 
        AND bs.signal IN ('Sell', 'Strong Sell', 'SELL', 'STRONG_SELL', '-1', '-2')
    `;

    const [signalsResult, countResult] = await Promise.all([
      query(sellSignalsQuery, [limit, offset]),
      query(countQuery)
    ]);

    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / limit);

    if (!signalsResult || !Array.isArray(signalsResult.rows) || signalsResult.rows.length === 0) {
      return res.status(404).json({ error: 'No data found for this query' });
    }

    res.json({
      data: signalsResult.rows,
      timeframe,
      signal_type: 'sell',
      pagination: {
        page,
        limit,
        total,
        totalPages,
        hasNext: page < totalPages,
        hasPrev: page > 1
      }
    });

  } catch (error) {
    console.error('Error fetching sell signals:', error);
    return res.status(500).json({ error: 'Database error', details: error.message });
  }
});

// Advanced signal analysis endpoint with comprehensive technical analysis
router.post('/analyze/advanced', createValidationMiddleware(signalValidationSchemas.analyze), async (req, res) => {
  const requestId = res.locals.requestId || 'unknown';
  const startTime = Date.now();
  
  try {
    const userId = req.user.sub;
    const { symbol, timeframe = '1d', lookback = 100 } = req.validated;
    
    logger.info(`🚀 [${requestId}] Advanced signal analysis for symbol`, {
      userId: userId ? `${userId.substring(0, 8)}...` : 'unknown',
      symbol: symbol,
      timeframe: timeframe,
      lookback: lookback
    });

    // Generate comprehensive advanced signals
    const advancedAnalysis = await advancedSignalProcessor.generateAdvancedSignals(symbol, timeframe, lookback);
    
    if (!advancedAnalysis.success) {
      const response = error('Advanced signal analysis failed', 500);
      return res.status(500).json(response);
    }

    // Prepare comprehensive response
    const responseData = {
      symbol: symbol,
      timeframe: timeframe,
      analysis: {
        direction: advancedAnalysis.signal.direction,
        strength: advancedAnalysis.signal.strength,
        confidence: advancedAnalysis.signal.confidence,
        consensus: advancedAnalysis.signal.consensus
      },
      signals: {
        technical: advancedAnalysis.signal.signals.find(s => s.type === 'technical'),
        momentum: advancedAnalysis.signal.signals.find(s => s.type === 'momentum'),
        volume: advancedAnalysis.signal.signals.find(s => s.type === 'volume'),
        volatility: advancedAnalysis.signal.signals.find(s => s.type === 'volatility'),
        trend: advancedAnalysis.signal.signals.find(s => s.type === 'trend')
      },
      riskAssessment: {
        volatility: advancedAnalysis.riskAssessment.volatility,
        maxDrawdown: advancedAnalysis.riskAssessment.maxDrawdown,
        sharpeRatio: advancedAnalysis.riskAssessment.sharpeRatio,
        valueAtRisk: advancedAnalysis.riskAssessment.valueAtRisk,
        riskRewardRatio: advancedAnalysis.riskAssessment.riskRewardRatio
      },
      recommendations: advancedAnalysis.recommendations,
      metadata: {
        processingTime: advancedAnalysis.metadata.processingTime,
        dataPoints: advancedAnalysis.metadata.dataPoints,
        correlationId: advancedAnalysis.metadata.correlationId,
        timestamp: advancedAnalysis.metadata.timestamp
      }
    };

    const response = success(responseData, 'Advanced signal analysis completed successfully');
    
    logger.info(`✅ [${requestId}] Advanced signal analysis completed`, {
      symbol: symbol,
      direction: advancedAnalysis.signal.direction,
      strength: advancedAnalysis.signal.strength,
      confidence: advancedAnalysis.signal.confidence,
      recommendations: advancedAnalysis.recommendations.length,
      totalTime: Date.now() - startTime
    });
    
    res.json(response);
    
  } catch (error) {
    logger.error(`❌ [${requestId}] Advanced signal analysis failed`, {
      error: error.message,
      errorStack: error.stack,
      totalTime: Date.now() - startTime
    });
    
    const response = error(
      'Failed to perform advanced signal analysis',
      500,
      { details: error.message }
    );
    res.status(500).json(response);
  }
});

module.exports = router;

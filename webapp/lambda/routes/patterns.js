const express = require('express');
const { query, safeQuery, tablesExist } = require('../utils/database');
const { authenticateToken } = require('../middleware/auth');
const PatternDetector = require('../utils/patternDetector');
const WatchlistAlerts = require('../utils/watchlistAlerts');
const { 
  createValidationMiddleware, 
  rateLimitConfigs, 
  sqlInjectionPrevention, 
  xssPrevention,
  sanitizers
} = require('../middleware/validation');
const validator = require('validator');

const router = express.Router();

// Pattern recognition validation schemas
const patternValidationSchemas = {
  patternScan: {
    symbol: {
      type: 'string',
      sanitizer: sanitizers.symbol,
      validator: (value) => !value || /^[A-Z]{1,10}$/.test(value),
      errorMessage: 'Symbol must be 1-10 uppercase letters'
    },
    timeframe: {
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { maxLength: 10, alphaNumOnly: false }),
      validator: (value) => !value || ['1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w', '1M'].includes(value),
      errorMessage: 'Timeframe must be one of: 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w, 1M'
    },
    category: {
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { maxLength: 50, alphaNumOnly: false }),
      validator: (value) => !value || ['reversal', 'continuation', 'breakout', 'momentum', 'volume'].includes(value),
      errorMessage: 'Category must be one of: reversal, continuation, breakout, momentum, volume'
    },
    min_confidence: {
      type: 'number',
      sanitizer: (value) => sanitizers.number(value, { min: 0, max: 1, defaultValue: 0.60 }),
      validator: (value) => !value || (value >= 0 && value <= 1),
      errorMessage: 'Minimum confidence must be between 0 and 1'
    },
    limit: {
      type: 'integer',
      sanitizer: (value) => sanitizers.integer(value, { min: 1, max: 200, defaultValue: 50 }),
      validator: (value) => !value || (value >= 1 && value <= 200),
      errorMessage: 'Limit must be between 1 and 200'
    }
  },

  patternAnalysis: {
    symbol: {
      required: true,
      type: 'string',
      sanitizer: sanitizers.symbol,
      validator: (value) => /^[A-Z]{1,10}$/.test(value),
      errorMessage: 'Symbol must be 1-10 uppercase letters'
    },
    pattern_type: {
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { maxLength: 50, alphaNumOnly: false }),
      validator: (value) => !value || ['head_and_shoulders', 'double_top', 'double_bottom', 'triangle', 'flag', 'wedge'].includes(value),
      errorMessage: 'Pattern type must be a valid technical pattern'
    },
    start_date: {
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { maxLength: 10 }),
      validator: (value) => !value || validator.isDate(value, { format: 'YYYY-MM-DD' }),
      errorMessage: 'Start date must be in YYYY-MM-DD format'
    },
    end_date: {
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { maxLength: 10 }),
      validator: (value) => !value || validator.isDate(value, { format: 'YYYY-MM-DD' }),
      errorMessage: 'End date must be in YYYY-MM-DD format'
    }
  },

  performanceAnalysis: {
    pattern_type: {
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { maxLength: 50, alphaNumOnly: false }),
      validator: (value) => !value || ['head_and_shoulders', 'double_top', 'double_bottom', 'triangle', 'flag', 'wedge'].includes(value),
      errorMessage: 'Pattern type must be a valid technical pattern'
    },
    timeframe: {
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { maxLength: 10, alphaNumOnly: false }),
      validator: (value) => !value || ['1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w', '1M'].includes(value),
      errorMessage: 'Timeframe must be valid'
    },
    min_samples: {
      type: 'integer',
      sanitizer: (value) => sanitizers.integer(value, { min: 10, max: 10000, defaultValue: 50 }),
      validator: (value) => !value || (value >= 10 && value <= 10000),
      errorMessage: 'Minimum samples must be between 10 and 10,000'
    }
  }
};

// Apply authentication and security middleware to pattern routes
router.use(authenticateToken);
router.use(sqlInjectionPrevention);
router.use(xssPrevention);
router.use(rateLimitConfigs.api);

// Root patterns endpoint for health checks
router.get('/', (req, res) => {
  res.json({
    success: true,
    data: {
      system: 'Pattern Recognition API',
      version: '1.0.0',
      status: 'operational',
      available_endpoints: [
        'GET /patterns/scan - Scan for patterns in real-time',
        'GET /patterns/types - Get available pattern types',
        'GET /patterns/performance - Get pattern performance analytics',
        'GET /patterns/alerts - Get pattern-based alerts',
        'GET /patterns/dashboard - Get pattern recognition dashboard',
        'GET /patterns/statistics - Get pattern statistics'
      ],
      timestamp: new Date().toISOString()
    }
  });
});

// Apply authentication middleware to all other pattern routes
router.use(authenticateToken);

// Initialize pattern detector and alerts system
const patternDetector = new PatternDetector();
const watchlistAlerts = new WatchlistAlerts();

// Start real-time pattern monitoring
patternDetector.startRealTimeMonitoring();

/**
 * GET /api/patterns/scan
 * Scan for patterns in real-time
 */
router.get('/scan', createValidationMiddleware(patternValidationSchemas.patternScan), async (req, res) => {
  try {
    const { 
      symbol, 
      timeframe, 
      category,
      min_confidence,
      limit 
    } = req.validated;

    console.log(`🔍 Pattern scan request: symbol=${symbol}, timeframe=${timeframe}, confidence>=${min_confidence}`);

    let whereClause = 'WHERE dp.status = $1';
    let params = ['active'];
    let paramIndex = 2;

    // Add validated symbol filter
    if (symbol) {
      whereClause += ` AND dp.symbol = $${paramIndex}`;
      params.push(symbol);
      paramIndex++;
    }

    // Add validated timeframe filter
    if (timeframe) {
      whereClause += ` AND dp.timeframe = $${paramIndex}`;
      params.push(timeframe);
      paramIndex++;
    }

    // Add validated category filter
    if (category) {
      whereClause += ` AND pt.category = $${paramIndex}`;
      params.push(category);
      paramIndex++;
    }

    // Add validated confidence filter
    whereClause += ` AND dp.confidence_score >= $${paramIndex}`;
    params.push(min_confidence);
    paramIndex++;

    // Add limit with validated value
    whereClause += ` ORDER BY dp.detected_at DESC LIMIT $${paramIndex}`;
    params.push(limit);

    const result = await query(`
      SELECT 
        dp.id,
        dp.symbol,
        dp.timeframe,
        dp.detection_date,
        dp.start_date,
        dp.end_date,
        dp.confidence_score,
        dp.ml_confidence,
        dp.traditional_confidence,
        dp.signal_strength,
        dp.direction,
        dp.target_price,
        dp.stop_loss,
        dp.risk_reward_ratio,
        dp.pattern_data,
        dp.key_levels,
        dp.volume_confirmation,
        dp.momentum_confirmation,
        dp.status,
        pt.name as pattern_name,
        pt.category,
        pt.description,
        pt.reliability_score
      FROM detected_patterns dp
      JOIN pattern_types pt ON dp.pattern_type_id = pt.id
      ${whereClause}
      ORDER BY dp.detection_date DESC, dp.confidence_score DESC
      LIMIT $${paramIndex}
    `, [...params, parseInt(limit)]);

    const patterns = result.rows.map(row => ({
      id: row.id,
      symbol: row.symbol,
      patternName: row.pattern_name,
      category: row.category,
      description: row.description,
      timeframe: row.timeframe,
      detectionDate: row.detection_date,
      startDate: row.start_date,
      endDate: row.end_date,
      confidence: parseFloat(row.confidence_score),
      mlConfidence: row.ml_confidence ? parseFloat(row.ml_confidence) : null,
      traditionalConfidence: parseFloat(row.traditional_confidence),
      signalStrength: row.signal_strength,
      direction: row.direction,
      targetPrice: row.target_price ? parseFloat(row.target_price) : null,
      stopLoss: row.stop_loss ? parseFloat(row.stop_loss) : null,
      riskRewardRatio: row.risk_reward_ratio ? parseFloat(row.risk_reward_ratio) : null,
      patternData: row.pattern_data,
      keyLevels: row.key_levels,
      volumeConfirmation: row.volume_confirmation,
      momentumConfirmation: row.momentum_confirmation,
      status: row.status,
      reliabilityScore: parseFloat(row.reliability_score)
    }));

    res.json({
      success: true,
      patterns,
      total: patterns.length,
      filters: {
        symbol,
        timeframe,
        category,
        minConfidence: min_confidence
      }
    });

  } catch (error) {
    console.error('Error scanning patterns:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to scan patterns',
      details: error.message
    });
  }
});

/**
 * POST /api/patterns/analyze
 * Analyze a specific symbol for patterns
 */
router.post('/analyze', async (req, res) => {
  try {
    const { symbol, timeframe = '1d', categories } = req.body;

    if (!symbol) {
      return res.status(400).json({
        success: false,
        error: 'Symbol is required'
      });
    }

    // This would trigger the pattern recognition service
    // For now, we'll return existing patterns and simulate analysis
    
    let whereClause = 'WHERE dp.symbol = $1 AND dp.timeframe = $2';
    let params = [symbol.toUpperCase(), timeframe];
    let paramIndex = 3;

    if (categories && categories.length > 0) {
      const categoryPlaceholders = categories.map(() => `$${paramIndex++}`).join(',');
      whereClause += ` AND pt.category IN (${categoryPlaceholders})`;
      params.push(...categories);
    }

    const result = await query(`
      SELECT 
        dp.*,
        pt.name as pattern_name,
        pt.category,
        pt.description,
        pt.reliability_score
      FROM detected_patterns dp
      JOIN pattern_types pt ON dp.pattern_type_id = pt.id
      ${whereClause}
      ORDER BY dp.detection_date DESC
      LIMIT 20
    `, params);

    const patterns = result.rows.map(row => ({
      id: row.id,
      symbol: row.symbol,
      patternName: row.pattern_name,
      category: row.category,
      description: row.description,
      timeframe: row.timeframe,
      detectionDate: row.detection_date,
      startDate: row.start_date,
      endDate: row.end_date,
      confidence: parseFloat(row.confidence_score),
      mlConfidence: row.ml_confidence ? parseFloat(row.ml_confidence) : null,
      traditionalConfidence: parseFloat(row.traditional_confidence),
      signalStrength: row.signal_strength,
      direction: row.direction,
      targetPrice: row.target_price ? parseFloat(row.target_price) : null,
      stopLoss: row.stop_loss ? parseFloat(row.stop_loss) : null,
      riskRewardRatio: row.risk_reward_ratio ? parseFloat(row.risk_reward_ratio) : null,
      patternData: row.pattern_data,
      keyLevels: row.key_levels,
      volumeConfirmation: row.volume_confirmation,
      momentumConfirmation: row.momentum_confirmation,
      status: row.status,
      reliabilityScore: parseFloat(row.reliability_score)
    }));

    // Get pattern summary statistics
    const summaryResult = await query(`
      SELECT 
        pt.category,
        COUNT(*) as count,
        AVG(dp.confidence_score) as avg_confidence,
        COUNT(CASE WHEN dp.direction = 'bullish' THEN 1 END) as bullish_count,
        COUNT(CASE WHEN dp.direction = 'bearish' THEN 1 END) as bearish_count
      FROM detected_patterns dp
      JOIN pattern_types pt ON dp.pattern_type_id = pt.id
      WHERE dp.symbol = $1 AND dp.timeframe = $2 
        AND dp.detection_date >= NOW() - INTERVAL '30 days'
      GROUP BY pt.category
    `, [symbol.toUpperCase(), timeframe]);

    const summary = {
      totalPatterns: patterns.length,
      categories: summaryResult.rows.map(row => ({
        category: row.category,
        count: parseInt(row.count),
        avgConfidence: parseFloat(row.avg_confidence),
        bullishCount: parseInt(row.bullish_count),
        bearishCount: parseInt(row.bearish_count)
      })),
      overallSentiment: calculateOverallSentiment(patterns),
      highestConfidencePattern: patterns.length > 0 ? patterns[0] : null
    };

    res.json({
      success: true,
      symbol: symbol.toUpperCase(),
      timeframe,
      patterns,
      summary,
      analysisDate: new Date().toISOString()
    });

  } catch (error) {
    console.error('Error analyzing patterns:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to analyze patterns',
      details: error.message
    });
  }
});

/**
 * GET /api/patterns/types
 * Get all available pattern types
 */
router.get('/types', async (req, res) => {
  try {
    const { category, is_active = true } = req.query;

    let whereClause = 'WHERE is_active = $1';
    let params = [is_active === 'true'];
    let paramIndex = 2;

    if (category) {
      whereClause += ` AND category = $${paramIndex}`;
      params.push(category);
      paramIndex++;
    }

    const result = await query(`
      SELECT 
        id,
        name,
        category,
        description,
        min_bars,
        max_bars,
        reliability_score,
        is_active,
        created_at
      FROM pattern_types
      ${whereClause}
      ORDER BY category, reliability_score DESC, name
    `, params);

    const patternTypes = result.rows.map(row => ({
      id: row.id,
      name: row.name,
      category: row.category,
      description: row.description,
      minBars: row.min_bars,
      maxBars: row.max_bars,
      reliabilityScore: parseFloat(row.reliability_score),
      isActive: row.is_active,
      createdAt: row.created_at
    }));

    // Group by category
    const groupedTypes = patternTypes.reduce((acc, pattern) => {
      if (!acc[pattern.category]) {
        acc[pattern.category] = [];
      }
      acc[pattern.category].push(pattern);
      return acc;
    }, {});

    res.json({
      success: true,
      patternTypes,
      groupedTypes,
      total: patternTypes.length,
      categories: Object.keys(groupedTypes)
    });

  } catch (error) {
    console.error('Error fetching pattern types:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch pattern types',
      details: error.message
    });
  }
});

/**
 * GET /api/patterns/performance
 * Get pattern performance analytics
 */
router.get('/performance', async (req, res) => {
  try {
    const { 
      symbol, 
      pattern_type,
      timeframe = '1d',
      days = 30 
    } = req.query;

    let whereClause = 'WHERE pp.evaluation_date >= NOW() - INTERVAL $1 DAY';
    let params = [parseInt(days)];
    let paramIndex = 2;

    if (symbol) {
      whereClause += ` AND dp.symbol = $${paramIndex}`;
      params.push(symbol.toUpperCase());
      paramIndex++;
    }

    if (pattern_type) {
      whereClause += ` AND pt.name = $${paramIndex}`;
      params.push(pattern_type);
      paramIndex++;
    }

    if (timeframe) {
      whereClause += ` AND dp.timeframe = $${paramIndex}`;
      params.push(timeframe);
      paramIndex++;
    }

    const result = await query(`
      SELECT 
        pt.name as pattern_name,
        pt.category,
        COUNT(*) as total_patterns,
        COUNT(CASE WHEN pp.target_hit = true THEN 1 END) as successful_patterns,
        AVG(pp.percentage_change) as avg_return,
        AVG(pp.accuracy_score) as avg_accuracy,
        AVG(pp.time_to_target) as avg_time_to_target,
        AVG(dp.confidence_score) as avg_confidence,
        MAX(pp.percentage_change) as max_return,
        MIN(pp.percentage_change) as min_return
      FROM pattern_performance pp
      JOIN detected_patterns dp ON pp.detected_pattern_id = dp.id
      JOIN pattern_types pt ON dp.pattern_type_id = pt.id
      ${whereClause}
      GROUP BY pt.name, pt.category
      ORDER BY avg_accuracy DESC, avg_return DESC
    `, params);

    const performance = result.rows.map(row => ({
      patternName: row.pattern_name,
      category: row.category,
      totalPatterns: parseInt(row.total_patterns),
      successfulPatterns: parseInt(row.successful_patterns),
      successRate: row.total_patterns > 0 ? 
        (parseInt(row.successful_patterns) / parseInt(row.total_patterns) * 100).toFixed(2) : '0.00',
      avgReturn: parseFloat(row.avg_return || 0).toFixed(2),
      avgAccuracy: parseFloat(row.avg_accuracy || 0).toFixed(4),
      avgTimeToTarget: parseFloat(row.avg_time_to_target || 0).toFixed(1),
      avgConfidence: parseFloat(row.avg_confidence || 0).toFixed(4),
      maxReturn: parseFloat(row.max_return || 0).toFixed(2),
      minReturn: parseFloat(row.min_return || 0).toFixed(2)
    }));

    // Overall statistics
    const overallStats = await query(`
      SELECT 
        COUNT(DISTINCT dp.id) as total_patterns_evaluated,
        COUNT(CASE WHEN pp.target_hit = true THEN 1 END) as total_successful,
        AVG(pp.percentage_change) as overall_avg_return,
        AVG(pp.accuracy_score) as overall_avg_accuracy
      FROM pattern_performance pp
      JOIN detected_patterns dp ON pp.detected_pattern_id = dp.id
      WHERE pp.evaluation_date >= NOW() - INTERVAL $1 DAY
    `, [parseInt(days)]);

    const overallData = overallStats.rows[0];
    const overall = {
      totalPatternsEvaluated: parseInt(overallData.total_patterns_evaluated || 0),
      totalSuccessful: parseInt(overallData.total_successful || 0),
      overallSuccessRate: overallData.total_patterns_evaluated > 0 ? 
        (parseInt(overallData.total_successful) / parseInt(overallData.total_patterns_evaluated) * 100).toFixed(2) : '0.00',
      overallAvgReturn: parseFloat(overallData.overall_avg_return || 0).toFixed(2),
      overallAvgAccuracy: parseFloat(overallData.overall_avg_accuracy || 0).toFixed(4)
    };

    res.json({
      success: true,
      performance,
      overall,
      filters: {
        symbol,
        patternType: pattern_type,
        timeframe,
        days
      },
      generatedAt: new Date().toISOString()
    });

  } catch (error) {
    console.error('Error fetching pattern performance:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch pattern performance',
      details: error.message
    });
  }
});

/**
 * GET /api/patterns/alerts
 * Get pattern-based alerts
 */
router.get('/alerts', async (req, res) => {
  try {
    const userId = req.user.sub;
    const { is_sent = false, priority, limit = 50 } = req.query;

    let whereClause = 'WHERE 1=1';
    let params = [];
    let paramIndex = 1;

    // Filter by sent status
    if (is_sent !== undefined) {
      whereClause += ` AND pa.is_sent = $${paramIndex}`;
      params.push(is_sent === 'true');
      paramIndex++;
    }

    // Filter by priority
    if (priority) {
      whereClause += ` AND pa.priority = $${paramIndex}`;
      params.push(priority);
      paramIndex++;
    }

    const result = await query(`
      SELECT 
        pa.id,
        pa.alert_type,
        pa.message,
        pa.is_sent,
        pa.sent_at,
        pa.priority,
        pa.created_at,
        dp.symbol,
        dp.timeframe,
        dp.confidence_score,
        dp.direction,
        pt.name as pattern_name,
        pt.category
      FROM pattern_alerts pa
      JOIN detected_patterns dp ON pa.detected_pattern_id = dp.id
      JOIN pattern_types pt ON dp.pattern_type_id = pt.id
      ${whereClause}
      ORDER BY pa.created_at DESC
      LIMIT $${paramIndex}
    `, [...params, parseInt(limit)]);

    const alerts = result.rows.map(row => ({
      id: row.id,
      alertType: row.alert_type,
      message: row.message,
      isSent: row.is_sent,
      sentAt: row.sent_at,
      priority: row.priority,
      createdAt: row.created_at,
      symbol: row.symbol,
      timeframe: row.timeframe,
      patternName: row.pattern_name,
      category: row.category,
      confidence: parseFloat(row.confidence_score),
      direction: row.direction
    }));

    res.json({
      success: true,
      alerts,
      total: alerts.length,
      filters: {
        isSent: is_sent,
        priority
      }
    });

  } catch (error) {
    console.error('Error fetching pattern alerts:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch pattern alerts',
      details: error.message
    });
  }
});

/**
 * POST /api/patterns/alerts/:id/mark-sent
 * Mark an alert as sent
 */
router.post('/alerts/:id/mark-sent', async (req, res) => {
  try {
    const alertId = parseInt(req.params.id);

    if (!alertId) {
      return res.status(400).json({
        success: false,
        error: 'Invalid alert ID'
      });
    }

    const result = await query(`
      UPDATE pattern_alerts
      SET is_sent = true, sent_at = NOW()
      WHERE id = $1
      RETURNING *
    `, [alertId]);

    if (result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: 'Alert not found'
      });
    }

    res.json({
      success: true,
      message: 'Alert marked as sent',
      alert: result.rows[0]
    });

  } catch (error) {
    console.error('Error marking alert as sent:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to mark alert as sent',
      details: error.message
    });
  }
});

/**
 * GET /api/patterns/dashboard
 * Get pattern recognition dashboard data
 */
router.get('/dashboard', async (req, res) => {
  try {
    const { timeframe = '1d', days = 7 } = req.query;

    // Recent patterns
    const recentPatterns = await query(`
      SELECT 
        dp.symbol,
        dp.detection_date,
        dp.confidence_score,
        dp.direction,
        dp.signal_strength,
        pt.name as pattern_name,
        pt.category
      FROM detected_patterns dp
      JOIN pattern_types pt ON dp.pattern_type_id = pt.id
      WHERE dp.timeframe = $1 
        AND dp.detection_date >= NOW() - INTERVAL $2 DAY
        AND dp.status = 'active'
      ORDER BY dp.detection_date DESC, dp.confidence_score DESC
      LIMIT 10
    `, [timeframe, parseInt(days)]);

    // Pattern categories distribution
    const categoryStats = await query(`
      SELECT 
        pt.category,
        COUNT(*) as count,
        AVG(dp.confidence_score) as avg_confidence
      FROM detected_patterns dp
      JOIN pattern_types pt ON dp.pattern_type_id = pt.id
      WHERE dp.timeframe = $1 
        AND dp.detection_date >= NOW() - INTERVAL $2 DAY
        AND dp.status = 'active'
      GROUP BY pt.category
      ORDER BY count DESC
    `, [timeframe, parseInt(days)]);

    // Signal strength distribution
    const signalStats = await query(`
      SELECT 
        signal_strength,
        COUNT(*) as count
      FROM detected_patterns
      WHERE timeframe = $1 
        AND detection_date >= NOW() - INTERVAL $2 DAY
        AND status = 'active'
      GROUP BY signal_strength
      ORDER BY 
        CASE signal_strength
          WHEN 'very_strong' THEN 1
          WHEN 'strong' THEN 2
          WHEN 'moderate' THEN 3
          WHEN 'weak' THEN 4
        END
    `, [timeframe, parseInt(days)]);

    // Direction distribution
    const directionStats = await query(`
      SELECT 
        direction,
        COUNT(*) as count,
        AVG(confidence_score) as avg_confidence
      FROM detected_patterns
      WHERE timeframe = $1 
        AND detection_date >= NOW() - INTERVAL $2 DAY
        AND status = 'active'
      GROUP BY direction
    `, [timeframe, parseInt(days)]);

    // Top performing symbols
    const topSymbols = await query(`
      SELECT 
        symbol,
        COUNT(*) as pattern_count,
        AVG(confidence_score) as avg_confidence,
        COUNT(CASE WHEN direction = 'bullish' THEN 1 END) as bullish_count,
        COUNT(CASE WHEN direction = 'bearish' THEN 1 END) as bearish_count
      FROM detected_patterns
      WHERE timeframe = $1 
        AND detection_date >= NOW() - INTERVAL $2 DAY
        AND status = 'active'
      GROUP BY symbol
      HAVING COUNT(*) >= 2
      ORDER BY pattern_count DESC, avg_confidence DESC
      LIMIT 10
    `, [timeframe, parseInt(days)]);

    res.json({
      success: true,
      dashboard: {
        recentPatterns: recentPatterns.rows.map(row => ({
          symbol: row.symbol,
          patternName: row.pattern_name,
          category: row.category,
          detectionDate: row.detection_date,
          confidence: parseFloat(row.confidence_score),
          direction: row.direction,
          signalStrength: row.signal_strength
        })),
        categoryStats: categoryStats.rows.map(row => ({
          category: row.category,
          count: parseInt(row.count),
          avgConfidence: parseFloat(row.avg_confidence)
        })),
        signalStats: signalStats.rows.map(row => ({
          signalStrength: row.signal_strength,
          count: parseInt(row.count)
        })),
        directionStats: directionStats.rows.map(row => ({
          direction: row.direction,
          count: parseInt(row.count),
          avgConfidence: parseFloat(row.avg_confidence)
        })),
        topSymbols: topSymbols.rows.map(row => ({
          symbol: row.symbol,
          patternCount: parseInt(row.pattern_count),
          avgConfidence: parseFloat(row.avg_confidence),
          bullishCount: parseInt(row.bullish_count),
          bearishCount: parseInt(row.bearish_count)
        }))
      },
      filters: {
        timeframe,
        days
      },
      generatedAt: new Date().toISOString()
    });

  } catch (error) {
    console.error('Error fetching pattern dashboard:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch pattern dashboard',
      details: error.message
    });
  }
});

// Helper functions
function calculateOverallSentiment(patterns) {
  if (patterns.length === 0) return 'neutral';
  
  let bullishScore = 0;
  let bearishScore = 0;
  
  patterns.forEach(pattern => {
    const weight = pattern.confidence;
    if (pattern.direction === 'bullish') {
      bullishScore += weight;
    } else if (pattern.direction === 'bearish') {
      bearishScore += weight;
    }
  });
  
  const total = bullishScore + bearishScore;
  if (total === 0) return 'neutral';
  
  const bullishRatio = bullishScore / total;
  if (bullishRatio > 0.6) return 'bullish';
  if (bullishRatio < 0.4) return 'bearish';
  return 'neutral';
}

// Real-time pattern detection endpoint
router.post('/detect-realtime', async (req, res) => {
  try {
    const { symbols, timeframes = ['1d'], patterns } = req.body;
    const userId = req.user.sub;

    if (!symbols || symbols.length === 0) {
      return res.status(400).json({
        success: false,
        error: 'Symbols array is required'
      });
    }

    // Detect patterns for specified symbols
    const detections = [];
    for (const symbol of symbols) {
      for (const timeframe of timeframes) {
        const results = await patternDetector.detectPatterns(symbol, timeframe, patterns);
        detections.push(...results);
      }
    }

    // Store pattern detections
    await storePatternDetections(detections, userId);

    // Create alerts for significant patterns
    const alerts = await createPatternAlerts(detections, userId);

    res.json({
      success: true,
      data: {
        patterns_detected: detections.length,
        alerts_created: alerts.length,
        detections: detections.slice(0, 20), // Return top 20
        alerts: alerts
      }
    });
  } catch (error) {
    console.error('Error in real-time pattern detection:', error);
    res.status(500).json({
      success: false,
      error: 'Pattern detection failed',
      message: error.message
    });
  }
});

// Get pattern statistics
router.get('/statistics', async (req, res) => {
  try {
    const { period = '30d', category } = req.query;
    
    // Get pattern statistics
    const stats = await getPatternStatistics(period, category);
    
    res.json({
      success: true,
      data: stats
    });
  } catch (error) {
    console.error('Error fetching pattern statistics:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch pattern statistics',
      message: error.message
    });
  }
});

// Get pattern performance
router.get('/performance', async (req, res) => {
  try {
    const { pattern_type, timeframe = '1d', days = 30 } = req.query;
    
    const performance = await getPatternPerformance(pattern_type, timeframe, days);
    
    res.json({
      success: true,
      data: performance
    });
  } catch (error) {
    console.error('Error fetching pattern performance:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch pattern performance',
      message: error.message
    });
  }
});

// Create pattern alert
router.post('/alerts', async (req, res) => {
  try {
    const userId = req.user.sub;
    const { symbol, pattern_types, min_confidence = 0.7, notify_email = true } = req.body;
    
    if (!symbol || !pattern_types || pattern_types.length === 0) {
      return res.status(400).json({
        success: false,
        error: 'Symbol and pattern_types are required'
      });
    }
    
    // Create pattern-based alerts
    const alerts = [];
    for (const patternType of pattern_types) {
      const alertConfig = {
        symbol: symbol.toUpperCase(),
        alertType: 'pattern_detected',
        condition: 'equals',
        targetValue: patternType,
        metadata: {
          pattern_type: patternType,
          min_confidence: min_confidence,
          notify_email: notify_email
        },
        message: `Pattern alert: ${patternType} detected for ${symbol}`
      };
      
      const alert = await watchlistAlerts.createAlert(userId, alertConfig);
      alerts.push(alert);
    }
    
    res.json({
      success: true,
      data: alerts,
      message: `Created ${alerts.length} pattern alerts`
    });
  } catch (error) {
    console.error('Error creating pattern alert:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to create pattern alert',
      message: error.message
    });
  }
});

// Get available pattern types
router.get('/types', (req, res) => {
  try {
    const patternTypes = [
      {
        id: 'head_and_shoulders',
        name: 'Head and Shoulders',
        category: 'reversal',
        description: 'Bearish reversal pattern with three peaks',
        reliability: 'high',
        timeframe_suitability: ['1d', '1w']
      },
      {
        id: 'inverse_head_and_shoulders',
        name: 'Inverse Head and Shoulders',
        category: 'reversal',
        description: 'Bullish reversal pattern with three troughs',
        reliability: 'high',
        timeframe_suitability: ['1d', '1w']
      },
      {
        id: 'double_top',
        name: 'Double Top',
        category: 'reversal',
        description: 'Bearish reversal with two peaks at similar levels',
        reliability: 'medium',
        timeframe_suitability: ['1d', '1w']
      },
      {
        id: 'double_bottom',
        name: 'Double Bottom',
        category: 'reversal',
        description: 'Bullish reversal with two troughs at similar levels',
        reliability: 'medium',
        timeframe_suitability: ['1d', '1w']
      },
      {
        id: 'triangle_ascending',
        name: 'Ascending Triangle',
        category: 'continuation',
        description: 'Bullish continuation pattern with horizontal resistance',
        reliability: 'medium',
        timeframe_suitability: ['1d', '1w']
      },
      {
        id: 'triangle_descending',
        name: 'Descending Triangle',
        category: 'continuation',
        description: 'Bearish continuation pattern with horizontal support',
        reliability: 'medium',
        timeframe_suitability: ['1d', '1w']
      },
      {
        id: 'triangle_symmetrical',
        name: 'Symmetrical Triangle',
        category: 'continuation',
        description: 'Neutral pattern with converging support and resistance',
        reliability: 'low',
        timeframe_suitability: ['1d', '1w']
      },
      {
        id: 'flag_bull',
        name: 'Bull Flag',
        category: 'continuation',
        description: 'Bullish continuation after strong upward move',
        reliability: 'high',
        timeframe_suitability: ['1h', '1d']
      },
      {
        id: 'flag_bear',
        name: 'Bear Flag',
        category: 'continuation',
        description: 'Bearish continuation after strong downward move',
        reliability: 'high',
        timeframe_suitability: ['1h', '1d']
      },
      {
        id: 'cup_and_handle',
        name: 'Cup and Handle',
        category: 'continuation',
        description: 'Bullish continuation pattern with rounded bottom',
        reliability: 'high',
        timeframe_suitability: ['1d', '1w']
      },
      {
        id: 'wedge_rising',
        name: 'Rising Wedge',
        category: 'reversal',
        description: 'Bearish pattern with upward sloping support and resistance',
        reliability: 'medium',
        timeframe_suitability: ['1d', '1w']
      },
      {
        id: 'wedge_falling',
        name: 'Falling Wedge',
        category: 'reversal',
        description: 'Bullish pattern with downward sloping support and resistance',
        reliability: 'medium',
        timeframe_suitability: ['1d', '1w']
      }
    ];
    
    res.json({
      success: true,
      data: patternTypes
    });
  } catch (error) {
    console.error('Error fetching pattern types:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch pattern types'
    });
  }
});

// Helper functions
async function storePatternDetections(detections, userId) {
  if (!detections || detections.length === 0) return;
  
  try {
    for (const detection of detections) {
      await query(`
        INSERT INTO pattern_detections (
          user_id, symbol, pattern_type, timeframe, confidence_score,
          detection_data, start_date, end_date, status, detected_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
        ON CONFLICT (symbol, pattern_type, timeframe, start_date)
        DO UPDATE SET
          confidence_score = EXCLUDED.confidence_score,
          detection_data = EXCLUDED.detection_data,
          status = EXCLUDED.status,
          detected_at = EXCLUDED.detected_at
      `, [
        userId,
        detection.symbol,
        detection.pattern_type,
        detection.timeframe,
        detection.confidence,
        JSON.stringify(detection.data),
        detection.start_date,
        detection.end_date,
        'active'
      ]);
    }
  } catch (error) {
    console.error('Error storing pattern detections:', error);
  }
}

async function createPatternAlerts(detections, userId) {
  const alerts = [];
  
  try {
    for (const detection of detections) {
      if (detection.confidence >= 0.75) { // High confidence patterns
        const alertConfig = {
          symbol: detection.symbol,
          alertType: 'pattern_detected',
          condition: 'equals',
          targetValue: detection.pattern_type,
          metadata: {
            pattern_type: detection.pattern_type,
            confidence: detection.confidence,
            timeframe: detection.timeframe
          },
          message: `High confidence ${detection.pattern_type} pattern detected for ${detection.symbol} (${(detection.confidence * 100).toFixed(1)}% confidence)`
        };
        
        const alert = await watchlistAlerts.createAlert(userId, alertConfig);
        alerts.push(alert);
      }
    }
  } catch (error) {
    console.error('Error creating pattern alerts:', error);
  }
  
  return alerts;
}

async function getPatternStatistics(period, category) {
  try {
    const periodClause = {
      '7d': "detected_at >= NOW() - INTERVAL '7 days'",
      '30d': "detected_at >= NOW() - INTERVAL '30 days'",
      '90d': "detected_at >= NOW() - INTERVAL '90 days'",
      '1y': "detected_at >= NOW() - INTERVAL '1 year'"
    }[period] || "detected_at >= NOW() - INTERVAL '30 days'";
    
    let categoryFilter = '';
    if (category) {
      categoryFilter = `AND pt.category = '${category}'`;
    }
    
    const result = await query(`
      SELECT 
        pd.pattern_type,
        pt.category,
        pt.name,
        COUNT(*) as detection_count,
        AVG(pd.confidence_score) as avg_confidence,
        COUNT(DISTINCT pd.symbol) as unique_symbols,
        MAX(pd.detected_at) as latest_detection
      FROM pattern_detections pd
      LEFT JOIN pattern_types pt ON pd.pattern_type = pt.id
      WHERE ${periodClause} ${categoryFilter}
      GROUP BY pd.pattern_type, pt.category, pt.name
      ORDER BY detection_count DESC
    `);
    
    return {
      period,
      category,
      statistics: result.rows,
      total_detections: result.rows.reduce((sum, row) => sum + parseInt(row.detection_count), 0)
    };
  } catch (error) {
    console.error('Error getting pattern statistics:', error);
    return { period, category, statistics: [], total_detections: 0 };
  }
}

async function getPatternPerformance(patternType, timeframe, days) {
  try {
    const result = await query(`
      SELECT 
        pd.symbol,
        pd.pattern_type,
        pd.confidence_score,
        pd.detected_at,
        pd.detection_data,
        -- Calculate performance metrics
        CASE 
          WHEN pd.pattern_type LIKE '%bull%' OR pd.pattern_type LIKE '%ascending%' OR pd.pattern_type = 'cup_and_handle'
          THEN 'bullish'
          WHEN pd.pattern_type LIKE '%bear%' OR pd.pattern_type LIKE '%descending%' OR pd.pattern_type = 'head_and_shoulders'
          THEN 'bearish'
          ELSE 'neutral'
        END as expected_direction
      FROM pattern_detections pd
      WHERE pd.pattern_type = $1
      AND pd.timeframe = $2
      AND pd.detected_at >= NOW() - INTERVAL '$3 days'
      ORDER BY pd.detected_at DESC
    `, [patternType, timeframe, days]);
    
    return {
      pattern_type: patternType,
      timeframe,
      period_days: days,
      total_detections: result.rows.length,
      performance_data: result.rows
    };
  } catch (error) {
    console.error('Error getting pattern performance:', error);
    return {
      pattern_type: patternType,
      timeframe,
      period_days: days,
      total_detections: 0,
      performance_data: []
    };
  }
}

module.exports = router;
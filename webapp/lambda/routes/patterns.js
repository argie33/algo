const express = require('express');
const { query } = require('../utils/database');
const { authenticateToken } = require('../middleware/auth');

const router = express.Router();

// Apply authentication middleware to all pattern routes
router.use(authenticateToken);

/**
 * GET /api/patterns/scan
 * Scan for patterns in real-time
 */
router.get('/scan', async (req, res) => {
  try {
    const { 
      symbol, 
      timeframe = '1d', 
      category,
      min_confidence = 0.60,
      limit = 50 
    } = req.query;

    let whereClause = 'WHERE dp.status = $1';
    let params = ['active'];
    let paramIndex = 2;

    // Add symbol filter
    if (symbol) {
      whereClause += ` AND dp.symbol = $${paramIndex}`;
      params.push(symbol.toUpperCase());
      paramIndex++;
    }

    // Add timeframe filter
    if (timeframe) {
      whereClause += ` AND dp.timeframe = $${paramIndex}`;
      params.push(timeframe);
      paramIndex++;
    }

    // Add category filter
    if (category) {
      whereClause += ` AND pt.category = $${paramIndex}`;
      params.push(category);
      paramIndex++;
    }

    // Add confidence filter
    whereClause += ` AND dp.confidence_score >= $${paramIndex}`;
    params.push(parseFloat(min_confidence));
    paramIndex++;

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

module.exports = router;
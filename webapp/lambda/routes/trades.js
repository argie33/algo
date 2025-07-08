const express = require('express');
const router = express.Router();
const { authenticateUser } = require('../middleware/auth');
const { getDbConnection } = require('../utils/database');
const TradeAnalyticsService = require('../services/tradeAnalyticsService');
const { decrypt } = require('../utils/secrets');

// Initialize trade analytics service
let tradeAnalyticsService;

/**
 * Professional Trade Analysis API Routes
 * Integrates with user API keys from settings for broker data import
 */

/**
 * @route GET /api/trades/import/status
 * @desc Get trade import status for user
 */
router.get('/import/status', authenticateUser, async (req, res) => {
  try {
    const userId = req.user.id;
    const db = await getDbConnection();
    
    // Get broker configurations
    const result = await db.query(`
      SELECT bc.*, uak.provider, uak.is_active as key_active
      FROM broker_api_configs bc
      JOIN user_api_keys uak ON bc.user_id = uak.user_id AND bc.broker = uak.provider
      WHERE bc.user_id = $1
      ORDER BY bc.updated_at DESC
    `, [userId]);

    const brokerStatus = result.rows.map(row => ({
      broker: row.broker,
      provider: row.provider,
      isActive: row.is_active,
      keyActive: row.key_active,
      isPaperTrading: row.is_paper_trading,
      lastSyncStatus: row.last_sync_status,
      lastSyncError: row.last_sync_error,
      lastImportDate: row.last_import_date,
      totalTradesImported: row.total_trades_imported || 0
    }));

    res.json({
      success: true,
      brokerStatus,
      totalBrokers: brokerStatus.length,
      activeBrokers: brokerStatus.filter(b => b.isActive && b.keyActive).length
    });

  } catch (error) {
    console.error('Error fetching import status:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch import status'
    });
  }
});

/**
 * @route POST /api/trades/import/alpaca
 * @desc Import trades from Alpaca using stored API keys
 */
router.post('/import/alpaca', authenticateUser, async (req, res) => {
  try {
    const userId = req.user.id;
    const { startDate, endDate, forceRefresh = false } = req.body;
    
    const db = await getDbConnection();
    
    // Get user's Alpaca API keys
    const apiKeyResult = await db.query(`
      SELECT * FROM user_api_keys 
      WHERE user_id = $1 AND provider = 'alpaca' AND is_active = true
      ORDER BY created_at DESC
      LIMIT 1
    `, [userId]);

    if (apiKeyResult.rows.length === 0) {
      return res.status(400).json({
        success: false,
        error: 'No active Alpaca API keys found. Please add your Alpaca API keys in Settings.'
      });
    }

    const apiKeyRow = apiKeyResult.rows[0];
    
    // Decrypt API credentials
    let apiKey, apiSecret;
    try {
      apiKey = decrypt(apiKeyRow.encrypted_api_key, apiKeyRow.key_iv, apiKeyRow.key_auth_tag, apiKeyRow.user_salt);
      apiSecret = decrypt(apiKeyRow.encrypted_api_secret, apiKeyRow.secret_iv, apiKeyRow.secret_auth_tag, apiKeyRow.user_salt);
    } catch (decryptError) {
      console.error('Error decrypting API keys:', decryptError);
      return res.status(500).json({
        success: false,
        error: 'Failed to decrypt API keys. Please re-enter your API keys in Settings.'
      });
    }

    // Check if import is already in progress
    const configResult = await db.query(`
      SELECT last_sync_status FROM broker_api_configs 
      WHERE user_id = $1 AND broker = 'alpaca'
    `, [userId]);

    if (configResult.rows.length > 0 && configResult.rows[0].last_sync_status === 'in_progress') {
      return res.status(409).json({
        success: false,
        error: 'Trade import already in progress. Please wait for it to complete.'
      });
    }

    // Initialize trade analytics service
    if (!tradeAnalyticsService) {
      tradeAnalyticsService = new TradeAnalyticsService();
    }

    // Start import process
    const importResult = await tradeAnalyticsService.importAlpacaTrades(
      userId, 
      apiKey, 
      apiSecret, 
      apiKeyRow.is_sandbox, 
      startDate, 
      endDate
    );

    res.json({
      success: true,
      message: 'Trade import completed successfully',
      data: importResult
    });

  } catch (error) {
    console.error('Error importing Alpaca trades:', error);
    res.status(500).json({
      success: false,
      error: error.message || 'Failed to import trades from Alpaca'
    });
  }
});

/**
 * @route GET /api/trades/summary
 * @desc Get comprehensive trade analysis summary
 */
router.get('/summary', authenticateUser, async (req, res) => {
  try {
    const userId = req.user.id;
    const db = await getDbConnection();
    
    if (!tradeAnalyticsService) {
      tradeAnalyticsService = new TradeAnalyticsService();
    }

    const summary = await tradeAnalyticsService.getTradeAnalysisSummary(userId);
    
    res.json({
      success: true,
      data: summary
    });

  } catch (error) {
    console.error('Error fetching trade summary:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch trade summary'
    });
  }
});

/**
 * @route GET /api/trades/positions
 * @desc Get position history with analytics
 */
router.get('/positions', authenticateUser, async (req, res) => {
  try {
    const userId = req.user.id;
    const { status = 'all', limit = 50, offset = 0 } = req.query;
    const db = await getDbConnection();
    
    let statusFilter = '';
    let params = [userId, parseInt(limit), parseInt(offset)];
    
    if (status !== 'all') {
      statusFilter = 'AND ph.status = $4';
      params.push(status);
    }

    const result = await db.query(`
      SELECT 
        ph.*,
        ta.entry_signal_quality,
        ta.exit_signal_quality,
        ta.risk_reward_ratio,
        ta.alpha_generated,
        ta.trade_pattern_type,
        ta.pattern_confidence,
        cp.sector,
        cp.industry
      FROM position_history ph
      LEFT JOIN trade_analytics ta ON ph.id = ta.position_id
      LEFT JOIN company_profile cp ON ph.symbol = cp.ticker
      WHERE ph.user_id = $1 ${statusFilter}
      ORDER BY ph.opened_at DESC
      LIMIT $2 OFFSET $3
    `, params);

    // Get total count
    const countResult = await db.query(`
      SELECT COUNT(*) as total 
      FROM position_history 
      WHERE user_id = $1 ${status !== 'all' ? `AND status = '${status}'` : ''}
    `, [userId]);

    res.json({
      success: true,
      data: {
        positions: result.rows,
        pagination: {
          total: parseInt(countResult.rows[0].total),
          limit: parseInt(limit),
          offset: parseInt(offset),
          hasMore: parseInt(offset) + parseInt(limit) < parseInt(countResult.rows[0].total)
        }
      }
    });

  } catch (error) {
    console.error('Error fetching positions:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch positions'
    });
  }
});

/**
 * @route GET /api/trades/analytics/:positionId
 * @desc Get detailed analytics for a specific position
 */
router.get('/analytics/:positionId', authenticateUser, async (req, res) => {
  try {
    const userId = req.user.id;
    const positionId = parseInt(req.params.positionId);
    const db = await getDbConnection();
    
    // Get position with full analytics
    const result = await db.query(`
      SELECT 
        ph.*,
        ta.*,
        cp.sector,
        cp.industry,
        cp.market_cap,
        cp.description as company_description
      FROM position_history ph
      LEFT JOIN trade_analytics ta ON ph.id = ta.position_id
      LEFT JOIN company_profile cp ON ph.symbol = cp.ticker
      WHERE ph.id = $1 AND ph.user_id = $2
    `, [positionId, userId]);

    if (result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: 'Position not found'
      });
    }

    const position = result.rows[0];

    // Get related executions
    const executionsResult = await db.query(`
      SELECT * FROM trade_executions 
      WHERE user_id = $1 AND symbol = $2 
      AND execution_time BETWEEN $3 AND $4
      ORDER BY execution_time
    `, [userId, position.symbol, position.opened_at, position.closed_at || new Date()]);

    res.json({
      success: true,
      data: {
        position,
        executions: executionsResult.rows,
        analytics: {
          riskReward: position.risk_reward_ratio,
          alphaGenerated: position.alpha_generated,
          patternType: position.trade_pattern_type,
          patternConfidence: position.pattern_confidence,
          entryQuality: position.entry_signal_quality,
          exitQuality: position.exit_signal_quality,
          emotionalState: position.emotional_state_score,
          disciplineScore: position.discipline_score
        }
      }
    });

  } catch (error) {
    console.error('Error fetching position analytics:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch position analytics'
    });
  }
});

/**
 * @route GET /api/trades/insights
 * @desc Get AI-generated trade insights and recommendations
 */
router.get('/insights', authenticateUser, async (req, res) => {
  try {
    const userId = req.user.id;
    const { limit = 10 } = req.query;
    const db = await getDbConnection();
    
    if (!tradeAnalyticsService) {
      tradeAnalyticsService = new TradeAnalyticsService();
    }

    const insights = await tradeAnalyticsService.getTradeInsights(userId, parseInt(limit));
    
    res.json({
      success: true,
      data: {
        insights,
        total: insights.length
      }
    });

  } catch (error) {
    console.error('Error fetching trade insights:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch trade insights'
    });
  }
});

/**
 * @route GET /api/trades/performance
 * @desc Get performance metrics and benchmarks
 */
router.get('/performance', authenticateUser, async (req, res) => {
  try {
    const userId = req.user.id;
    const { timeframe = '3M' } = req.query;
    const db = await getDbConnection();
    
    // Get performance benchmarks
    const benchmarkResult = await db.query(`
      SELECT * FROM performance_benchmarks 
      WHERE user_id = $1 
      ORDER BY benchmark_date DESC
      LIMIT 90
    `, [userId]);

    // Get portfolio summary
    const portfolioResult = await db.query(`
      SELECT * FROM portfolio_summary 
      WHERE user_id = $1
    `, [userId]);

    // Get performance attribution
    const attributionResult = await db.query(`
      SELECT * FROM performance_attribution 
      WHERE user_id = $1 
      ORDER BY closed_at DESC
      LIMIT 50
    `, [userId]);

    res.json({
      success: true,
      data: {
        benchmarks: benchmarkResult.rows,
        portfolio: portfolioResult.rows[0] || null,
        attribution: attributionResult.rows,
        timeframe
      }
    });

  } catch (error) {
    console.error('Error fetching performance data:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch performance data'
    });
  }
});

/**
 * @route DELETE /api/trades/data
 * @desc Delete all trade data for user (for testing/reset)
 */
router.delete('/data', authenticateUser, async (req, res) => {
  try {
    const userId = req.user.id;
    const { confirm } = req.body;
    
    if (confirm !== 'DELETE_ALL_TRADE_DATA') {
      return res.status(400).json({
        success: false,
        error: 'Confirmation required. Send { "confirm": "DELETE_ALL_TRADE_DATA" }'
      });
    }

    const db = await getDbConnection();
    
    // Delete all trade-related data for user
    await db.query('BEGIN');
    
    try {
      await db.query('DELETE FROM trade_analytics WHERE user_id = $1', [userId]);
      await db.query('DELETE FROM position_history WHERE user_id = $1', [userId]);
      await db.query('DELETE FROM trade_executions WHERE user_id = $1', [userId]);
      await db.query('DELETE FROM trade_insights WHERE user_id = $1', [userId]);
      await db.query('DELETE FROM performance_benchmarks WHERE user_id = $1', [userId]);
      await db.query('DELETE FROM broker_api_configs WHERE user_id = $1', [userId]);
      
      await db.query('COMMIT');
      
      res.json({
        success: true,
        message: 'All trade data deleted successfully'
      });
      
    } catch (error) {
      await db.query('ROLLBACK');
      throw error;
    }

  } catch (error) {
    console.error('Error deleting trade data:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to delete trade data'
    });
  }
});

module.exports = router;
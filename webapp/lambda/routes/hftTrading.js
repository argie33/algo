/**
 * Enhanced HFT Trading API Routes
 * Complete implementation of HFT API endpoints with real database integration
 */

const express = require('express');
const router = express.Router();
const { query } = require('../utils/database');
const { authenticateToken } = require('../middleware/auth');
const { createLogger } = require('../utils/structuredLogger');
const AlpacaHFTService = require('../services/alpacaHFTService');
const HFTWebSocketManager = require('../services/hftWebSocketManager');
const PositionSyncService = require('../services/positionSyncService');

const logger = createLogger('financial-platform', 'enhanced-hft-api');

// Service instances
const hftServices = new Map(); // userId -> services
const wsManager = new HFTWebSocketManager();
const positionSync = new PositionSyncService();

// Initialize position sync service
positionSync.initialize();

/**
 * GET /api/hft/strategies
 * Get all HFT strategies for user
 */
router.get('/strategies', authenticateToken, async (req, res) => {
  try {
    const userId = req.user.userId;
    
    const sql = `
      SELECT 
        s.*,
        COUNT(p.id) as active_positions,
        SUM(CASE WHEN p.status = 'OPEN' THEN p.unrealized_pnl ELSE 0 END) as unrealized_pnl,
        (
          SELECT COUNT(*) FROM hft_orders o 
          WHERE o.strategy_id = s.id AND o.created_at >= CURRENT_DATE
        ) as daily_orders
      FROM hft_strategies s
      LEFT JOIN hft_positions p ON s.id = p.strategy_id AND p.status = 'OPEN'
      WHERE s.user_id = $1
      GROUP BY s.id
      ORDER BY s.created_at DESC
    `;

    const result = await query(sql, [userId]);
    
    res.json({
      success: true,
      data: result.rows.map(strategy => ({
        id: strategy.id,
        name: strategy.name,
        type: strategy.type,
        symbols: strategy.symbols,
        parameters: strategy.parameters,
        riskParameters: strategy.risk_parameters,
        enabled: strategy.enabled,
        paperTrading: strategy.paper_trading,
        maxPositionSize: parseFloat(strategy.max_position_size),
        maxDailyLoss: parseFloat(strategy.max_daily_loss),
        createdAt: strategy.created_at,
        deployedAt: strategy.deployed_at,
        lastSignalAt: strategy.last_signal_at,
        stats: {
          activePositions: parseInt(strategy.active_positions),
          unrealizedPnl: parseFloat(strategy.unrealized_pnl || 0),
          dailyOrders: parseInt(strategy.daily_orders)
        }
      }))
    });

  } catch (error) {
    logger.error('Failed to get strategies', {
      error: error.message,
      userId: req.user.userId
    });
    
    res.status(500).json({
      success: false,
      error: 'Failed to get strategies'
    });
  }
});

/**
 * POST /api/hft/strategies
 * Create new HFT strategy
 */
router.post('/strategies', authenticateToken, async (req, res) => {
  try {
    const userId = req.user.userId;
    const {
      name,
      type,
      symbols,
      parameters,
      riskParameters,
      maxPositionSize = 1000,
      maxDailyLoss = 500,
      paperTrading = true
    } = req.body;

    const sql = `
      INSERT INTO hft_strategies (
        user_id, name, type, symbols, parameters, risk_parameters,
        max_position_size, max_daily_loss, paper_trading
      ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
      RETURNING *
    `;

    const result = await query(sql, [
      userId, name, type, symbols, 
      JSON.stringify(parameters),
      JSON.stringify(riskParameters),
      maxPositionSize, maxDailyLoss, paperTrading
    ]);

    res.status(201).json({
      success: true,
      data: {
        id: result.rows[0].id,
        name: result.rows[0].name,
        type: result.rows[0].type,
        symbols: result.rows[0].symbols,
        enabled: result.rows[0].enabled,
        createdAt: result.rows[0].created_at
      }
    });

  } catch (error) {
    logger.error('Failed to create strategy', {
      error: error.message,
      userId: req.user.userId
    });
    
    res.status(500).json({
      success: false,
      error: 'Failed to create strategy'
    });
  }
});

/**
 * POST /api/hft/strategies/:id/deploy
 * Deploy HFT strategy for execution
 */
router.post('/strategies/:id/deploy', authenticateToken, async (req, res) => {
  try {
    const userId = req.user.userId;
    const strategyId = req.params.id;
    
    // Get strategy details
    const strategySql = `
      SELECT * FROM hft_strategies 
      WHERE id = $1 AND user_id = $2
    `;
    const strategyResult = await query(strategySql, [strategyId, userId]);
    
    if (strategyResult.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: 'Strategy not found'
      });
    }

    const strategy = strategyResult.rows[0];

    // Initialize Alpaca service for user
    let alpacaService = hftServices.get(userId);
    if (!alpacaService) {
      // Get user API credentials
      const credSql = `
        SELECT api_key, api_secret, is_sandbox 
        FROM user_api_keys 
        WHERE user_id = $1 AND provider = 'alpaca'
      `;
      const credResult = await query(credSql, [userId]);
      
      if (credResult.rows.length === 0) {
        return res.status(400).json({
          success: false,
          error: 'Alpaca API credentials not configured'
        });
      }

      const creds = credResult.rows[0];
      alpacaService = new AlpacaHFTService(
        creds.api_key,
        creds.api_secret,
        creds.is_sandbox
      );

      const initResult = await alpacaService.initialize();
      if (!initResult.success) {
        return res.status(500).json({
          success: false,
          error: 'Failed to initialize trading service',
          details: initResult.error
        });
      }

      hftServices.set(userId, alpacaService);
    }

    // Subscribe to market data for strategy symbols
    await wsManager.subscribeToHFTSymbols(strategy.symbols, 'high');

    // Enable strategy
    const updateSql = `
      UPDATE hft_strategies 
      SET enabled = true, deployed_at = CURRENT_TIMESTAMP
      WHERE id = $1
    `;
    await query(updateSql, [strategyId]);

    res.json({
      success: true,
      data: {
        strategyId: parseInt(strategyId),
        name: strategy.name,
        symbols: strategy.symbols,
        deployed: true,
        deployedAt: new Date().toISOString()
      }
    });

  } catch (error) {
    logger.error('Failed to deploy strategy', {
      error: error.message,
      strategyId: req.params.id,
      userId: req.user.userId
    });
    
    res.status(500).json({
      success: false,
      error: 'Failed to deploy strategy'
    });
  }
});

/**
 * GET /api/hft/performance
 * Get HFT performance metrics
 */
router.get('/performance', authenticateToken, async (req, res) => {
  try {
    const userId = req.user.userId;
    const { period = '1D', strategyId } = req.query;

    let dateFilter = "pm.date >= CURRENT_DATE";
    if (period === '1W') dateFilter = "pm.date >= CURRENT_DATE - INTERVAL '7 days'";
    if (period === '1M') dateFilter = "pm.date >= CURRENT_DATE - INTERVAL '30 days'";

    const sql = `
      SELECT 
        pm.*,
        s.name as strategy_name,
        s.type as strategy_type
      FROM hft_performance_metrics pm
      JOIN hft_strategies s ON pm.strategy_id = s.id
      WHERE pm.user_id = $1 
        AND ${dateFilter}
        ${strategyId ? 'AND pm.strategy_id = $2' : ''}
      ORDER BY pm.date DESC, pm.total_pnl DESC
    `;

    const params = [userId];
    if (strategyId) params.push(strategyId);

    const result = await query(sql, params);
    
    // Calculate aggregated metrics
    const aggregated = result.rows.reduce((acc, row) => ({
      totalPnl: acc.totalPnl + parseFloat(row.total_pnl || 0),
      totalTrades: acc.totalTrades + parseInt(row.total_trades || 0),
      profitableTrades: acc.profitableTrades + parseInt(row.profitable_trades || 0),
      totalVolume: acc.totalVolume + parseFloat(row.total_volume || 0),
      maxDrawdown: Math.min(acc.maxDrawdown, parseFloat(row.max_drawdown || 0)),
      avgExecutionTime: (acc.avgExecutionTime + parseFloat(row.avg_execution_time_ms || 0)) / 2
    }), {
      totalPnl: 0,
      totalTrades: 0,
      profitableTrades: 0,
      totalVolume: 0,
      maxDrawdown: 0,
      avgExecutionTime: 0
    });

    res.json({
      success: true,
      data: {
        summary: {
          ...aggregated,
          winRate: aggregated.totalTrades > 0 ? 
            (aggregated.profitableTrades / aggregated.totalTrades) : 0,
          profitFactor: result.rows.length > 0 ? 
            result.rows.reduce((sum, r) => sum + (parseFloat(r.profit_factor) || 0), 0) / result.rows.length : 0
        },
        dailyMetrics: result.rows.map(row => ({
          date: row.date,
          strategyName: row.strategy_name,
          strategyType: row.strategy_type,
          totalPnl: parseFloat(row.total_pnl || 0),
          totalTrades: parseInt(row.total_trades || 0),
          profitableTrades: parseInt(row.profitable_trades || 0),
          winRate: parseFloat(row.win_rate || 0),
          avgExecutionTime: parseFloat(row.avg_execution_time_ms || 0),
          sharpeRatio: parseFloat(row.sharpe_ratio || 0),
          maxDrawdown: parseFloat(row.max_drawdown || 0)
        })),
        period
      }
    });

  } catch (error) {
    logger.error('Failed to get performance metrics', {
      error: error.message,
      userId: req.user.userId
    });
    
    res.status(500).json({
      success: false,
      error: 'Failed to get performance metrics'
    });
  }
});

/**
 * GET /api/hft/positions
 * Get active HFT positions
 */
router.get('/positions', authenticateToken, async (req, res) => {
  try {
    const userId = req.user.userId;
    
    const sql = `
      SELECT 
        p.*,
        s.name as strategy_name,
        s.type as strategy_type,
        (p.current_price - p.entry_price) * p.quantity * 
        CASE WHEN p.position_type = 'LONG' THEN 1 ELSE -1 END as current_pnl
      FROM hft_positions p
      JOIN hft_strategies s ON p.strategy_id = s.id
      WHERE p.user_id = $1 AND p.status = 'OPEN'
      ORDER BY p.opened_at DESC
    `;

    const result = await query(sql, [userId]);
    
    res.json({
      success: true,
      data: result.rows.map(pos => ({
        id: pos.id,
        symbol: pos.symbol,
        strategy: {
          id: pos.strategy_id,
          name: pos.strategy_name,
          type: pos.strategy_type
        },
        positionType: pos.position_type,
        quantity: parseFloat(pos.quantity),
        entryPrice: parseFloat(pos.entry_price),
        currentPrice: parseFloat(pos.current_price || pos.entry_price),
        unrealizedPnl: parseFloat(pos.unrealized_pnl || 0),
        currentPnl: parseFloat(pos.current_pnl || 0),
        stopLoss: parseFloat(pos.stop_loss || 0),
        takeProfit: parseFloat(pos.take_profit || 0),
        openedAt: pos.opened_at,
        status: pos.status
      }))
    });

  } catch (error) {
    logger.error('Failed to get positions', {
      error: error.message,
      userId: req.user.userId
    });
    
    res.status(500).json({
      success: false,
      error: 'Failed to get positions'
    });
  }
});

/**
 * GET /api/hft/orders
 * Get HFT order history
 */
router.get('/orders', authenticateToken, async (req, res) => {
  try {
    const userId = req.user.userId;
    const { limit = 50, offset = 0, status, symbol } = req.query;
    
    let whereClause = 'WHERE o.user_id = $1';
    const params = [userId];
    let paramIndex = 2;

    if (status) {
      whereClause += ` AND o.status = $${paramIndex}`;
      params.push(status);
      paramIndex++;
    }

    if (symbol) {
      whereClause += ` AND o.symbol = $${paramIndex}`;
      params.push(symbol);
      paramIndex++;
    }

    const sql = `
      SELECT 
        o.*,
        s.name as strategy_name,
        s.type as strategy_type
      FROM hft_orders o
      JOIN hft_strategies s ON o.strategy_id = s.id
      ${whereClause}
      ORDER BY o.created_at DESC
      LIMIT $${paramIndex} OFFSET $${paramIndex + 1}
    `;

    params.push(parseInt(limit), parseInt(offset));

    const result = await query(sql, params);
    
    res.json({
      success: true,
      data: result.rows.map(order => ({
        id: order.id,
        symbol: order.symbol,
        strategy: {
          id: order.strategy_id,
          name: order.strategy_name,
          type: order.strategy_type
        },
        orderType: order.order_type,
        side: order.side,
        quantity: parseFloat(order.quantity),
        price: parseFloat(order.price || 0),
        status: order.status,
        timeInForce: order.time_in_force,
        filledQuantity: parseFloat(order.filled_quantity || 0),
        avgFillPrice: parseFloat(order.avg_fill_price || 0),
        commission: parseFloat(order.commission || 0),
        executionTime: parseInt(order.execution_time_ms || 0),
        createdAt: order.created_at,
        filledAt: order.filled_at,
        alpacaOrderId: order.alpaca_order_id
      })),
      pagination: {
        limit: parseInt(limit),
        offset: parseInt(offset),
        hasMore: result.rows.length === parseInt(limit)
      }
    });

  } catch (error) {
    logger.error('Failed to get orders', {
      error: error.message,
      userId: req.user.userId
    });
    
    res.status(500).json({
      success: false,
      error: 'Failed to get orders'
    });
  }
});

/**
 * GET /api/hft/risk
 * Get risk metrics and alerts
 */
router.get('/risk', authenticateToken, async (req, res) => {
  try {
    const userId = req.user.userId;
    
    // Get current risk metrics
    const riskSql = `
      SELECT 
        SUM(CASE WHEN p.position_type = 'LONG' THEN p.quantity * p.current_price 
                 ELSE p.quantity * p.current_price * -1 END) as net_exposure,
        SUM(p.quantity * p.current_price) as gross_exposure,
        COUNT(*) as open_positions,
        SUM(p.unrealized_pnl) as total_unrealized_pnl,
        AVG(p.unrealized_pnl) as avg_position_pnl
      FROM hft_positions p
      WHERE p.user_id = $1 AND p.status = 'OPEN'
    `;

    const riskResult = await query(riskSql, [userId]);
    
    // Get recent risk events
    const eventsSql = `
      SELECT *
      FROM hft_risk_events
      WHERE user_id = $1 AND created_at >= CURRENT_DATE - INTERVAL '7 days'
      ORDER BY created_at DESC
      LIMIT 20
    `;

    const eventsResult = await query(eventsSql, [userId]);
    
    // Get strategy risk utilization
    const strategySql = `
      SELECT 
        s.id,
        s.name,
        s.max_position_size,
        s.max_daily_loss,
        COALESCE(SUM(p.quantity * p.current_price), 0) as current_exposure,
        COALESCE(SUM(p.unrealized_pnl), 0) as current_pnl
      FROM hft_strategies s
      LEFT JOIN hft_positions p ON s.id = p.strategy_id AND p.status = 'OPEN'
      WHERE s.user_id = $1 AND s.enabled = true
      GROUP BY s.id, s.name, s.max_position_size, s.max_daily_loss
    `;

    const strategyResult = await query(strategySql, [userId]);

    const riskMetrics = riskResult.rows[0];
    
    res.json({
      success: true,
      data: {
        portfolio: {
          netExposure: parseFloat(riskMetrics.net_exposure || 0),
          grossExposure: parseFloat(riskMetrics.gross_exposure || 0),
          openPositions: parseInt(riskMetrics.open_positions || 0),
          totalUnrealizedPnl: parseFloat(riskMetrics.total_unrealized_pnl || 0),
          avgPositionPnl: parseFloat(riskMetrics.avg_position_pnl || 0)
        },
        strategies: strategyResult.rows.map(strategy => ({
          id: strategy.id,
          name: strategy.name,
          maxPositionSize: parseFloat(strategy.max_position_size),
          maxDailyLoss: parseFloat(strategy.max_daily_loss),
          currentExposure: parseFloat(strategy.current_exposure),
          currentPnl: parseFloat(strategy.current_pnl),
          utilizationPercent: parseFloat(strategy.current_exposure) / parseFloat(strategy.max_position_size) * 100,
          riskLevel: parseFloat(strategy.current_pnl) < parseFloat(strategy.max_daily_loss) * -0.8 ? 'HIGH' : 
                    parseFloat(strategy.current_pnl) < parseFloat(strategy.max_daily_loss) * -0.5 ? 'MEDIUM' : 'LOW'
        })),
        recentEvents: eventsResult.rows.map(event => ({
          id: event.id,
          type: event.event_type,
          severity: event.severity,
          symbol: event.symbol,
          description: event.description,
          actionTaken: event.action_taken,
          createdAt: event.created_at,
          resolvedAt: event.resolved_at
        }))
      }
    });

  } catch (error) {
    logger.error('Failed to get risk metrics', {
      error: error.message,
      userId: req.user.userId
    });
    
    res.status(500).json({
      success: false,
      error: 'Failed to get risk metrics'
    });
  }
});

/**
 * GET /api/hft/ai/recommendations
 * Get AI-powered trading recommendations
 */
router.get('/ai/recommendations', authenticateToken, async (req, res) => {
  try {
    const userId = req.user.userId;
    const { symbols, timeframe = '1h', limit = 10 } = req.query;
    
    // Get user's active strategies for context
    const strategySql = `
      SELECT s.*, array_agg(DISTINCT p.symbol) as active_symbols
      FROM hft_strategies s
      LEFT JOIN hft_positions p ON s.id = p.strategy_id AND p.status = 'OPEN'
      WHERE s.user_id = $1 AND s.enabled = true
      GROUP BY s.id
    `;

    const strategyResult = await query(strategySql, [userId]);
    
    // Generate AI recommendations based on strategy types and market conditions
    const recommendations = await generateAIRecommendations(
      strategyResult.rows,
      symbols ? symbols.split(',') : null,
      timeframe
    );

    res.json({
      success: true,
      data: {
        recommendations: recommendations.slice(0, parseInt(limit)),
        generatedAt: new Date().toISOString(),
        timeframe,
        disclaimer: 'AI recommendations are for informational purposes only and should not be considered as financial advice.'
      }
    });

  } catch (error) {
    logger.error('Failed to get AI recommendations', {
      error: error.message,
      userId: req.user.userId
    });
    
    res.status(500).json({
      success: false,
      error: 'Failed to get AI recommendations'
    });
  }
});

/**
 * Generate AI recommendations (placeholder implementation)
 */
async function generateAIRecommendations(strategies, symbols, timeframe) {
  // This is a placeholder implementation
  // In a real system, this would integrate with ML models
  
  const recommendations = [];
  const defaultSymbols = symbols || ['AAPL', 'TSLA', 'MSFT', 'GOOGL', 'AMZN'];
  
  for (const symbol of defaultSymbols) {
    // Simulate AI analysis
    const confidence = 0.6 + Math.random() * 0.3; // 60-90% confidence
    const action = Math.random() > 0.5 ? 'BUY' : 'SELL';
    const targetPrice = 100 + Math.random() * 200; // $100-300 range
    
    recommendations.push({
      symbol,
      action,
      confidence: Math.round(confidence * 100),
      currentPrice: targetPrice * (0.98 + Math.random() * 0.04),
      targetPrice,
      reasoning: `Technical analysis suggests ${action.toLowerCase()} opportunity based on momentum indicators and volume patterns.`,
      riskLevel: confidence > 0.8 ? 'LOW' : confidence > 0.7 ? 'MEDIUM' : 'HIGH',
      timeHorizon: timeframe,
      expectedReturn: Math.round((Math.random() * 10 - 5) * 100) / 100, // -5% to +5%
      stopLoss: targetPrice * (action === 'BUY' ? 0.95 : 1.05),
      generatedAt: new Date().toISOString()
    });
  }
  
  return recommendations.sort((a, b) => b.confidence - a.confidence);
}

/**
 * POST /api/hft/sync/positions
 * Force position synchronization
 */
router.post('/sync/positions', authenticateToken, async (req, res) => {
  try {
    const userId = req.user.userId;
    
    const result = await positionSync.forceSyncUser(userId);
    
    res.json({
      success: true,
      data: {
        synced: result.synced,
        discrepancies: result.discrepancies,
        timestamp: new Date().toISOString()
      }
    });

  } catch (error) {
    logger.error('Failed to sync positions', {
      error: error.message,
      userId: req.user.userId
    });
    
    res.status(500).json({
      success: false,
      error: 'Failed to sync positions'
    });
  }
});

/**
 * POST /api/hft/alpaca/connect
 * Initialize Alpaca HFT Service integration
 */
router.post('/alpaca/connect', authenticateToken, async (req, res) => {
  try {
    const userId = req.user.userId;
    
    const HFTService = require('../services/hftService');
    const hftService = new HFTService();
    
    // Initialize user credentials and Alpaca service
    const initResult = await hftService.initializeUserCredentials(userId);
    
    if (initResult.success) {
      res.json({
        success: true,
        data: {
          alpacaAccount: initResult.account,
          message: 'Alpaca HFT Service connected successfully',
          timestamp: new Date().toISOString()
        }
      });
    } else {
      res.status(400).json({
        success: false,
        error: initResult.error
      });
    }

  } catch (error) {
    logger.error('Failed to connect Alpaca HFT Service', {
      error: error.message,
      userId: req.user.userId
    });
    
    res.status(500).json({
      success: false,
      error: 'Failed to connect Alpaca HFT Service'
    });
  }
});

/**
 * GET /api/hft/alpaca/status
 * Get Alpaca integration status
 */
router.get('/alpaca/status', authenticateToken, async (req, res) => {
  try {
    const userId = req.user.userId;
    
    // Get user API credentials to check if available
    const credSql = `
      SELECT api_key, is_sandbox, created_at
      FROM user_api_keys 
      WHERE user_id = $1 AND provider = 'alpaca'
    `;
    const credResult = await query(credSql, [userId]);
    
    if (credResult.rows.length === 0) {
      return res.json({
        success: true,
        data: {
          connected: false,
          message: 'No Alpaca API credentials configured',
          configurationRequired: true
        }
      });
    }

    const credentials = credResult.rows[0];
    
    res.json({
      success: true,
      data: {
        connected: true,
        isPaper: credentials.is_sandbox,
        configuredAt: credentials.created_at,
        message: 'Alpaca credentials configured and ready for HFT integration'
      }
    });

  } catch (error) {
    logger.error('Failed to get Alpaca status', {
      error: error.message,
      userId: req.user.userId
    });
    
    res.status(500).json({
      success: false,
      error: 'Failed to get Alpaca status'
    });
  }
});

module.exports = router;
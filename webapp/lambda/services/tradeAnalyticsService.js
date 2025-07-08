const AlpacaService = require('../utils/alpacaService');
const { getDbConnection } = require('../utils/database');

/**
 * Professional Trade Analytics Service
 * Imports and analyzes trade data from Alpaca for institutional-grade analytics
 */
class TradeAnalyticsService {
  constructor() {
    // Database connection is handled by the utility
  }

  /**
   * Import trade executions from Alpaca
   */
  async importAlpacaTrades(userId, apiKey, apiSecret, isPaper = true, startDate = null, endDate = null) {
    try {
      const alpaca = new AlpacaService(apiKey, apiSecret, isPaper);
      
      // Validate credentials first
      const validation = await alpaca.validateCredentials();
      if (!validation.valid) {
        throw new Error(`Invalid Alpaca credentials: ${validation.error}`);
      }

      // Get account info
      const account = await alpaca.getAccount();
      
      // Update or create broker API config
      await this.updateBrokerConfig(userId, 'alpaca', isPaper, true);

      // Get activities (trade executions)
      const activities = await alpaca.getActivities(['FILL'], 500);
      
      // Filter by date range if specified
      let filteredActivities = activities;
      if (startDate || endDate) {
        filteredActivities = activities.filter(activity => {
          const activityDate = new Date(activity.date);
          if (startDate && activityDate < new Date(startDate)) return false;
          if (endDate && activityDate > new Date(endDate)) return false;
          return true;
        });
      }

      // Import trade executions
      const importResults = await this.importTradeExecutions(userId, filteredActivities, 'alpaca', isPaper);
      
      // Reconstruct positions from executions
      const positionsResults = await this.reconstructPositions(userId);
      
      // Calculate analytics for new positions
      const analyticsResults = await this.calculateTradeAnalytics(userId);

      return {
        success: true,
        importResults,
        positionsResults,
        analyticsResults,
        account: {
          id: account.accountId,
          status: account.status,
          environment: account.environment
        }
      };

    } catch (error) {
      console.error('Trade import error:', error);
      
      // Update broker config to mark as failed
      await this.updateBrokerConfig(userId, 'alpaca', isPaper, false, error.message);
      
      throw new Error(`Failed to import trades: ${error.message}`);
    }
  }

  /**
   * Import trade executions into database
   */
  async importTradeExecutions(userId, activities, broker, isPaper) {
    const db = await getDbConnection();
    let imported = 0;
    let updated = 0;
    let errors = 0;

    try {
      await db.query('BEGIN');

      // Get API key ID for reference
      const apiKeyResult = await db.query(
        'SELECT id FROM user_api_keys WHERE user_id = $1 AND provider = $2',
        [userId, broker]
      );
      
      const apiKeyId = apiKeyResult.rows[0]?.id;

      for (const activity of activities) {
        try {
          // Parse execution data
          const executionData = {
            user_id: userId,
            api_key_id: apiKeyId,
            broker: broker,
            trade_id: activity.id,
            order_id: activity.order_id || null,
            symbol: activity.symbol,
            asset_class: 'equity', // Alpaca is primarily equity
            security_type: 'stock',
            side: activity.side,
            quantity: Math.abs(activity.qty || 0),
            price: activity.price || 0,
            commission: 0, // Alpaca is commission-free
            fees: 0,
            execution_time: activity.date,
            settlement_date: activity.date,
            venue: 'ALPACA',
            order_type: 'market', // Default - would need order data for specifics
            time_in_force: 'day',
            imported_at: new Date(),
            last_updated: new Date()
          };

          // Insert or update trade execution
          const result = await db.query(`
            INSERT INTO trade_executions (
              user_id, api_key_id, broker, trade_id, order_id, symbol, asset_class, security_type,
              side, quantity, price, commission, fees, execution_time, settlement_date,
              venue, order_type, time_in_force, imported_at, last_updated
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20)
            ON CONFLICT (broker, trade_id) DO UPDATE SET
              quantity = EXCLUDED.quantity,
              price = EXCLUDED.price,
              last_updated = EXCLUDED.last_updated
            RETURNING id, (xmax = 0) AS inserted
          `, [
            executionData.user_id, executionData.api_key_id, executionData.broker,
            executionData.trade_id, executionData.order_id, executionData.symbol,
            executionData.asset_class, executionData.security_type, executionData.side,
            executionData.quantity, executionData.price, executionData.commission,
            executionData.fees, executionData.execution_time, executionData.settlement_date,
            executionData.venue, executionData.order_type, executionData.time_in_force,
            executionData.imported_at, executionData.last_updated
          ]);

          if (result.rows[0].inserted) {
            imported++;
          } else {
            updated++;
          }

        } catch (error) {
          console.error('Error importing execution:', error);
          errors++;
        }
      }

      await db.query('COMMIT');

      return {
        imported,
        updated,
        errors,
        total: activities.length
      };

    } catch (error) {
      await db.query('ROLLBACK');
      throw error;
    }
  }

  /**
   * Reconstruct positions from trade executions
   */
  async reconstructPositions(userId) {
    const db = await getDbConnection();
    
    try {
      await db.query('BEGIN');

      // Get all executions for user, ordered by time
      const executions = await db.query(`
        SELECT * FROM trade_executions 
        WHERE user_id = $1 
        ORDER BY symbol, execution_time
      `, [userId]);

      const positionsBySymbol = {};
      let positionsCreated = 0;
      let positionsUpdated = 0;

      // Process executions to reconstruct positions
      for (const execution of executions.rows) {
        const symbol = execution.symbol;
        
        if (!positionsBySymbol[symbol]) {
          positionsBySymbol[symbol] = {
            symbol: symbol,
            executions: [],
            currentQuantity: 0,
            totalBought: 0,
            totalSold: 0,
            buyQuantity: 0,
            sellQuantity: 0,
            buyValue: 0,
            sellValue: 0,
            positions: []
          };
        }

        const pos = positionsBySymbol[symbol];
        pos.executions.push(execution);

        const qty = parseFloat(execution.quantity);
        const price = parseFloat(execution.price);
        const value = qty * price;

        if (execution.side === 'buy') {
          pos.buyQuantity += qty;
          pos.buyValue += value;
          pos.currentQuantity += qty;
        } else {
          pos.sellQuantity += qty;
          pos.sellValue += value;
          pos.currentQuantity -= qty;
        }

        // Check if position is closed
        if (pos.currentQuantity === 0 && pos.buyQuantity > 0) {
          // Position closed, calculate P&L
          const grossPnl = pos.sellValue - pos.buyValue;
          const netPnl = grossPnl; // No commissions for Alpaca
          const returnPct = pos.buyValue > 0 ? (grossPnl / pos.buyValue) * 100 : 0;
          
          const firstExecution = pos.executions[0];
          const lastExecution = pos.executions[pos.executions.length - 1];
          
          const holdingPeriod = (new Date(lastExecution.execution_time) - new Date(firstExecution.execution_time)) / (1000 * 60 * 60 * 24);
          
          // Insert closed position
          await db.query(`
            INSERT INTO position_history (
              user_id, symbol, asset_class, opened_at, closed_at, side, total_quantity,
              avg_entry_price, avg_exit_price, gross_pnl, net_pnl, total_commissions, total_fees,
              return_percentage, holding_period_days, status
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
            ON CONFLICT (user_id, symbol, opened_at) DO UPDATE SET
              closed_at = EXCLUDED.closed_at,
              avg_exit_price = EXCLUDED.avg_exit_price,
              gross_pnl = EXCLUDED.gross_pnl,
              net_pnl = EXCLUDED.net_pnl,
              return_percentage = EXCLUDED.return_percentage,
              holding_period_days = EXCLUDED.holding_period_days,
              status = EXCLUDED.status
          `, [
            userId, symbol, execution.asset_class, firstExecution.execution_time,
            lastExecution.execution_time, 'long', pos.buyQuantity,
            pos.buyValue / pos.buyQuantity, pos.sellValue / pos.sellQuantity,
            grossPnl, netPnl, 0, 0, returnPct, holdingPeriod, 'closed'
          ]);

          positionsCreated++;
          
          // Reset for next position
          pos.currentQuantity = 0;
          pos.buyQuantity = 0;
          pos.sellQuantity = 0;
          pos.buyValue = 0;
          pos.sellValue = 0;
          pos.executions = [];
        }
      }

      // Handle any remaining open positions
      for (const [symbol, pos] of Object.entries(positionsBySymbol)) {
        if (pos.currentQuantity > 0) {
          const firstExecution = pos.executions[0];
          
          await db.query(`
            INSERT INTO position_history (
              user_id, symbol, asset_class, opened_at, side, total_quantity,
              avg_entry_price, status
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (user_id, symbol, opened_at) DO UPDATE SET
              total_quantity = EXCLUDED.total_quantity,
              avg_entry_price = EXCLUDED.avg_entry_price
          `, [
            userId, symbol, firstExecution.asset_class, firstExecution.execution_time,
            'long', pos.currentQuantity, pos.buyValue / pos.buyQuantity, 'open'
          ]);

          positionsUpdated++;
        }
      }

      await db.query('COMMIT');

      return {
        positionsCreated,
        positionsUpdated,
        symbolsProcessed: Object.keys(positionsBySymbol).length
      };

    } catch (error) {
      await db.query('ROLLBACK');
      throw error;
    }
  }

  /**
   * Calculate trade analytics for positions
   */
  async calculateTradeAnalytics(userId) {
    const db = await getDbConnection();
    
    try {
      // Get closed positions that need analytics
      const positions = await db.query(`
        SELECT p.*, cp.sector, cp.industry, cp.market_cap
        FROM position_history p
        LEFT JOIN company_profile cp ON p.symbol = cp.ticker
        WHERE p.user_id = $1 AND p.status = 'closed'
        AND NOT EXISTS (
          SELECT 1 FROM trade_analytics ta WHERE ta.position_id = p.id
        )
      `, [userId]);

      let analyticsCreated = 0;

      for (const position of positions.rows) {
        // Calculate basic analytics
        const analytics = await this.calculatePositionAnalytics(position);
        
        // Insert analytics
        await db.query(`
          INSERT INTO trade_analytics (
            position_id, user_id, entry_signal_quality, entry_timing_score,
            exit_signal_quality, exit_timing_score, risk_reward_ratio,
            alpha_generated, emotional_state_score, discipline_score,
            trade_pattern_type, pattern_confidence
          ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
        `, [
          position.id, userId, analytics.entry_signal_quality, analytics.entry_timing_score,
          analytics.exit_signal_quality, analytics.exit_timing_score, analytics.risk_reward_ratio,
          analytics.alpha_generated, analytics.emotional_state_score, analytics.discipline_score,
          analytics.trade_pattern_type, analytics.pattern_confidence
        ]);

        analyticsCreated++;
      }

      return {
        analyticsCreated,
        positionsAnalyzed: positions.rows.length
      };

    } catch (error) {
      console.error('Error calculating trade analytics:', error);
      throw error;
    }
  }

  /**
   * Calculate analytics for a single position
   */
  async calculatePositionAnalytics(position) {
    // This is a simplified version - in production you'd use more sophisticated algorithms
    const returnPct = position.return_percentage || 0;
    const holdingPeriod = position.holding_period_days || 0;
    
    // Basic scoring (0-100)
    const entrySignalQuality = Math.min(100, Math.max(0, 50 + (returnPct * 2)));
    const exitSignalQuality = Math.min(100, Math.max(0, 50 + (returnPct * 1.5)));
    const entryTimingScore = Math.min(100, Math.max(0, 70 - (holdingPeriod * 0.5)));
    const exitTimingScore = Math.min(100, Math.max(0, 60 + (returnPct * 1.2)));
    
    // Risk-reward ratio (simplified)
    const riskRewardRatio = Math.abs(returnPct) > 0 ? Math.max(returnPct, 0) / Math.max(Math.abs(returnPct), 1) : 0;
    
    // Alpha vs market (simplified - assumes 10% market return)
    const marketReturn = 10;
    const alphaGenerated = (returnPct - marketReturn) / 100;
    
    // Emotional and discipline scores (simplified)
    const emotionalStateScore = Math.min(100, Math.max(0, 70 - Math.abs(returnPct - 5)));
    const disciplineScore = Math.min(100, Math.max(0, 80 - (Math.abs(holdingPeriod - 30) * 0.5)));
    
    // Pattern recognition (simplified)
    let tradePatternType = 'unknown';
    let patternConfidence = 0.5;
    
    if (holdingPeriod < 1) {
      tradePatternType = 'day_trading';
      patternConfidence = 0.8;
    } else if (holdingPeriod < 7) {
      tradePatternType = 'swing_trading';
      patternConfidence = 0.7;
    } else if (holdingPeriod < 30) {
      tradePatternType = 'short_term';
      patternConfidence = 0.6;
    } else {
      tradePatternType = 'position_trading';
      patternConfidence = 0.7;
    }

    return {
      entry_signal_quality: entrySignalQuality,
      entry_timing_score: entryTimingScore,
      exit_signal_quality: exitSignalQuality,
      exit_timing_score: exitTimingScore,
      risk_reward_ratio: riskRewardRatio,
      alpha_generated: alphaGenerated,
      emotional_state_score: emotionalStateScore,
      discipline_score: disciplineScore,
      trade_pattern_type: tradePatternType,
      pattern_confidence: patternConfidence
    };
  }

  /**
   * Update broker API configuration
   */
  async updateBrokerConfig(userId, broker, isPaper, isActive, error = null) {
    const db = await getDbConnection();
    
    try {
      await db.query(`
        INSERT INTO broker_api_configs (
          user_id, broker, is_paper_trading, is_active, last_sync_status,
          last_sync_error, last_import_date
        ) VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (user_id, broker) DO UPDATE SET
          is_paper_trading = EXCLUDED.is_paper_trading,
          is_active = EXCLUDED.is_active,
          last_sync_status = EXCLUDED.last_sync_status,
          last_sync_error = EXCLUDED.last_sync_error,
          last_import_date = EXCLUDED.last_import_date,
          updated_at = CURRENT_TIMESTAMP
      `, [
        userId, broker, isPaper, isActive,
        error ? 'failed' : 'success', error,
        isActive ? new Date() : null
      ]);
    } catch (error) {
      console.error('Error updating broker config:', error);
      throw error;
    }
  }

  /**
   * Get trade analysis summary for user
   */
  async getTradeAnalysisSummary(userId) {
    const db = await getDbConnection();
    
    try {
      // Get portfolio summary
      const portfolioResult = await db.query(`
        SELECT * FROM portfolio_summary WHERE user_id = $1
      `, [userId]);

      // Get recent trades with analytics
      const recentTrades = await db.query(`
        SELECT * FROM recent_trades 
        WHERE user_id = $1 
        ORDER BY opened_at DESC 
        LIMIT 10
      `, [userId]);

      // Get performance attribution
      const performanceAttribution = await db.query(`
        SELECT * FROM performance_attribution 
        WHERE user_id = $1 
        ORDER BY closed_at DESC 
        LIMIT 20
      `, [userId]);

      return {
        portfolio: portfolioResult.rows[0] || null,
        recentTrades: recentTrades.rows,
        performanceAttribution: performanceAttribution.rows,
        lastUpdated: new Date().toISOString()
      };

    } catch (error) {
      console.error('Error getting trade analysis summary:', error);
      throw error;
    }
  }

  /**
   * Get trade insights for user
   */
  async getTradeInsights(userId, limit = 10) {
    const db = await getDbConnection();
    
    try {
      const result = await db.query(`
        SELECT * FROM trade_insights 
        WHERE user_id = $1 
        ORDER BY created_at DESC 
        LIMIT $2
      `, [userId, limit]);

      return result.rows;
    } catch (error) {
      console.error('Error getting trade insights:', error);
      throw error;
    }
  }
}

module.exports = TradeAnalyticsService;
/**
 * Portfolio Service - Core Database Integration for Portfolio Management
 * Bridges database layer with portfolio optimization and analytics services
 * Provides real database operations for portfolio holdings, metadata, and history
 */

const { query, transaction, healthCheck } = require('../utils/database');
const logger = require('../utils/logger');
const AlpacaService = require('../utils/alpacaService');
const portfolioSyncService = require('../utils/portfolioSyncService');
const crypto = require('crypto');

class PortfolioService {
  constructor() {
    this.alpacaService = new AlpacaService();
  }

  /**
   * Retrieve complete user portfolio from database
   */
  async getUserPortfolio(userId, options = {}) {
    const { includeMetadata = true, includeHistory = false } = options;
    
    try {
      logger.info(`Retrieving portfolio for user ${userId}`);
      
      // Get current portfolio holdings
      const holdingsResult = await query(`
        SELECT 
          symbol,
          quantity,
          avg_cost,
          current_price,
          market_value,
          unrealized_pl,
          sector,
          created_at,
          updated_at
        FROM portfolio_holdings 
        WHERE user_id = $1 AND quantity > 0
        ORDER BY market_value DESC
      `, [userId]);

      const holdings = holdingsResult.rows;

      let metadata = null;
      if (includeMetadata) {
        const metadataResult = await query(`
          SELECT 
            account_id,
            account_type,
            total_equity,
            buying_power,
            cash,
            day_trade_count,
            last_sync_at,
            sync_status,
            created_at,
            updated_at
          FROM portfolio_metadata 
          WHERE user_id = $1
        `, [userId]);
        
        metadata = metadataResult.rows[0] || null;
      }

      // Calculate portfolio totals
      const totalMarketValue = holdings.reduce((sum, holding) => sum + parseFloat(holding.market_value || 0), 0);
      const totalUnrealizedPL = holdings.reduce((sum, holding) => sum + parseFloat(holding.unrealized_pl || 0), 0);

      const portfolio = {
        userId,
        holdings,
        metadata,
        summary: {
          totalPositions: holdings.length,
          totalMarketValue,
          totalUnrealizedPL,
          totalCost: totalMarketValue - totalUnrealizedPL,
          percentageGain: totalMarketValue > 0 ? (totalUnrealizedPL / (totalMarketValue - totalUnrealizedPL)) * 100 : 0
        },
        lastUpdated: new Date().toISOString()
      };

      if (includeHistory) {
        portfolio.history = await this.getPortfolioHistory(userId, { days: 30 });
      }

      logger.info(`Retrieved portfolio for user ${userId}: ${holdings.length} positions, $${totalMarketValue.toFixed(2)} total value`);
      return portfolio;

    } catch (error) {
      logger.error('Error retrieving user portfolio:', {
        userId,
        error: error.message,
        stack: error.stack
      });
      throw new Error(`Failed to retrieve portfolio: ${error.message}`);
    }
  }

  /**
   * Update portfolio holdings in database
   */
  async updatePortfolioHoldings(userId, holdings) {
    try {
      logger.info(`Updating portfolio holdings for user ${userId}: ${holdings.length} positions`);

      await transaction(async (client) => {
        // Update each holding using UPSERT pattern
        for (const holding of holdings) {
          const {
            symbol,
            quantity,
            avgCost,
            currentPrice,
            marketValue,
            unrealizedPL,
            sector
          } = holding;

          await client.query(`
            INSERT INTO portfolio_holdings (
              user_id, symbol, quantity, avg_cost, current_price, 
              market_value, unrealized_pl, sector, updated_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, CURRENT_TIMESTAMP)
            ON CONFLICT (user_id, symbol) 
            DO UPDATE SET
              quantity = EXCLUDED.quantity,
              avg_cost = EXCLUDED.avg_cost,
              current_price = EXCLUDED.current_price,
              market_value = EXCLUDED.market_value,
              unrealized_pl = EXCLUDED.unrealized_pl,
              sector = EXCLUDED.sector,
              updated_at = CURRENT_TIMESTAMP
          `, [userId, symbol, quantity, avgCost, currentPrice, marketValue, unrealizedPL, sector]);
        }

        // Remove positions with zero quantity
        await client.query(`
          DELETE FROM portfolio_holdings 
          WHERE user_id = $1 AND quantity <= 0
        `, [userId]);

        logger.info(`Successfully updated ${holdings.length} portfolio holdings for user ${userId}`);
      });

      return { success: true, updatedPositions: holdings.length };

    } catch (error) {
      logger.error('Error updating portfolio holdings:', {
        userId,
        holdingsCount: holdings.length,
        error: error.message,
        stack: error.stack
      });
      throw new Error(`Failed to update portfolio holdings: ${error.message}`);
    }
  }

  /**
   * Save portfolio metadata (account information)
   */
  async savePortfolioMetadata(userId, metadata) {
    try {
      logger.info(`Saving portfolio metadata for user ${userId}`);

      const {
        accountId,
        accountType,
        totalEquity,
        buyingPower,
        cash,
        dayTradeCount,
        syncStatus = 'updated'
      } = metadata;

      await query(`
        INSERT INTO portfolio_metadata (
          user_id, account_id, account_type, total_equity, buying_power, 
          cash, day_trade_count, sync_status, last_sync_at, updated_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT (user_id) 
        DO UPDATE SET
          account_id = EXCLUDED.account_id,
          account_type = EXCLUDED.account_type,
          total_equity = EXCLUDED.total_equity,
          buying_power = EXCLUDED.buying_power,
          cash = EXCLUDED.cash,
          day_trade_count = EXCLUDED.day_trade_count,
          sync_status = EXCLUDED.sync_status,
          last_sync_at = CURRENT_TIMESTAMP,
          updated_at = CURRENT_TIMESTAMP
      `, [userId, accountId, accountType, totalEquity, buyingPower, cash, dayTradeCount, syncStatus]);

      logger.info(`Successfully saved portfolio metadata for user ${userId}`);
      return { success: true };

    } catch (error) {
      logger.error('Error saving portfolio metadata:', {
        userId,
        error: error.message,
        stack: error.stack
      });
      throw new Error(`Failed to save portfolio metadata: ${error.message}`);
    }
  }

  /**
   * Get portfolio history for performance calculations
   */
  async getPortfolioHistory(userId, options = {}) {
    const { days = 30, interval = 'daily' } = options;
    
    try {
      logger.info(`Retrieving portfolio history for user ${userId}: ${days} days`);

      const result = await query(`
        SELECT 
          date_trunc($1, created_at) as date,
          SUM(market_value) as total_value,
          SUM(unrealized_pl) as total_unrealized_pl,
          COUNT(DISTINCT symbol) as position_count
        FROM portfolio_holdings 
        WHERE user_id = $2 
          AND created_at >= CURRENT_DATE - INTERVAL '${days} days'
        GROUP BY date_trunc($1, created_at)
        ORDER BY date ASC
      `, [interval, userId]);

      const history = result.rows.map(row => ({
        date: row.date,
        totalValue: parseFloat(row.total_value || 0),
        totalUnrealizedPL: parseFloat(row.total_unrealized_pl || 0),
        positionCount: parseInt(row.position_count || 0),
        totalCost: parseFloat(row.total_value || 0) - parseFloat(row.total_unrealized_pl || 0)
      }));

      logger.info(`Retrieved ${history.length} portfolio history records for user ${userId}`);
      return history;

    } catch (error) {
      logger.error('Error retrieving portfolio history:', {
        userId,
        days,
        error: error.message,
        stack: error.stack
      });
      throw new Error(`Failed to retrieve portfolio history: ${error.message}`);
    }
  }

  /**
   * Sync portfolio from broker API (e.g., Alpaca)
   */
  async syncPortfolioFromBroker(userId, brokerApiKeys) {
    try {
      logger.info(`Syncing portfolio from broker for user ${userId}`);

      // Get positions from broker API
      const alpacaPositions = await this.alpacaService.getPositions(brokerApiKeys);
      const alpacaAccount = await this.alpacaService.getAccount(brokerApiKeys);

      // Transform broker data to our format
      const holdings = alpacaPositions.map(position => ({
        symbol: position.symbol,
        quantity: parseFloat(position.qty),
        avgCost: parseFloat(position.avg_entry_price),
        currentPrice: parseFloat(position.current_price || position.market_value / position.qty),
        marketValue: parseFloat(position.market_value),
        unrealizedPL: parseFloat(position.unrealized_pl),
        sector: position.sector || 'Unknown'
      }));

      const metadata = {
        accountId: alpacaAccount.account_number,
        accountType: alpacaAccount.account_type,
        totalEquity: parseFloat(alpacaAccount.equity),
        buyingPower: parseFloat(alpacaAccount.buying_power),
        cash: parseFloat(alpacaAccount.cash),
        dayTradeCount: parseInt(alpacaAccount.daytrade_count),
        syncStatus: 'synced'
      };

      // Save to database
      await this.updatePortfolioHoldings(userId, holdings);
      await this.savePortfolioMetadata(userId, metadata);

      logger.info(`Successfully synced portfolio from broker for user ${userId}: ${holdings.length} positions`);
      
      return {
        success: true,
        syncedAt: new Date().toISOString(),
        positionsCount: holdings.length,
        totalValue: metadata.totalEquity,
        source: 'alpaca'
      };

    } catch (error) {
      logger.error('Error syncing portfolio from broker:', {
        userId,
        error: error.message,
        stack: error.stack
      });

      // Update metadata to reflect sync failure
      try {
        await query(`
          UPDATE portfolio_metadata 
          SET sync_status = 'error', last_sync_at = CURRENT_TIMESTAMP
          WHERE user_id = $1
        `, [userId]);
      } catch (updateError) {
        logger.error('Failed to update sync status:', updateError);
      }

      throw new Error(`Failed to sync portfolio from broker: ${error.message}`);
    }
  }

  /**
   * Get portfolio for optimization service (formatted for algorithms)
   */
  async getPortfolioForOptimization(userId) {
    try {
      const portfolio = await this.getUserPortfolio(userId, { 
        includeMetadata: true, 
        includeHistory: true 
      });

      // Transform to optimization service format
      const positions = portfolio.holdings.map(holding => ({
        symbol: holding.symbol,
        quantity: parseFloat(holding.quantity),
        price: parseFloat(holding.current_price),
        value: parseFloat(holding.market_value),
        weight: parseFloat(holding.market_value) / portfolio.summary.totalMarketValue,
        sector: holding.sector,
        costBasis: parseFloat(holding.avg_cost) * parseFloat(holding.quantity)
      }));

      const constraints = {
        totalValue: portfolio.summary.totalMarketValue,
        cash: portfolio.metadata?.cash || 0,
        buyingPower: portfolio.metadata?.buying_power || 0,
        maxPositionWeight: 0.3, // Default constraint
        minPositionValue: 100 // Default minimum position size
      };

      return {
        userId,
        positions,
        constraints,
        lastUpdated: portfolio.lastUpdated,
        accountType: portfolio.metadata?.account_type || 'margin'
      };

    } catch (error) {
      logger.error('Error getting portfolio for optimization:', {
        userId,
        error: error.message,
        stack: error.stack
      });
      throw new Error(`Failed to get portfolio for optimization: ${error.message}`);
    }
  }

  /**
   * Save optimization results back to database
   */
  async saveOptimizationResults(userId, optimizationResults) {
    try {
      logger.info(`Saving optimization results for user ${userId}`);

      const optimizationId = crypto.randomUUID();
      
      await transaction(async (client) => {
        // Save optimization metadata
        await client.query(`
          INSERT INTO portfolio_optimizations (
            optimization_id, user_id, optimization_type, parameters, 
            created_at, status
          ) VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP, $5)
        `, [
          optimizationId,
          userId,
          optimizationResults.type,
          JSON.stringify(optimizationResults.parameters),
          'completed'
        ]);

        // Save recommended trades
        if (optimizationResults.trades && optimizationResults.trades.length > 0) {
          for (const trade of optimizationResults.trades) {
            await client.query(`
              INSERT INTO recommended_trades (
                optimization_id, symbol, action, quantity, 
                estimated_price, rationale, priority, created_at
              ) VALUES ($1, $2, $3, $4, $5, $6, $7, CURRENT_TIMESTAMP)
            `, [
              optimizationId,
              trade.symbol,
              trade.action,
              trade.quantity,
              trade.estimatedPrice,
              trade.rationale,
              trade.priority || 'medium'
            ]);
          }
        }
      });

      logger.info(`Successfully saved optimization results for user ${userId}: ${optimizationResults.trades?.length || 0} trades`);
      
      return {
        success: true,
        optimizationId,
        tradesCount: optimizationResults.trades?.length || 0
      };

    } catch (error) {
      logger.error('Error saving optimization results:', {
        userId,
        error: error.message,
        stack: error.stack
      });
      throw new Error(`Failed to save optimization results: ${error.message}`);
    }
  }

  /**
   * Get portfolio performance metrics
   */
  async getPortfolioPerformance(userId, period = '1M') {
    try {
      logger.info(`Calculating portfolio performance for user ${userId}: ${period}`);

      const daysMap = {
        '1D': 1,
        '1W': 7,
        '1M': 30,
        '3M': 90,
        '1Y': 365
      };

      const days = daysMap[period] || 30;
      
      const history = await this.getPortfolioHistory(userId, { days });
      
      if (history.length < 2) {
        return {
          period,
          totalReturn: 0,
          totalReturnPercent: 0,
          dailyReturns: [],
          volatility: 0,
          sharpeRatio: 0,
          maxDrawdown: 0
        };
      }

      // Calculate daily returns
      const dailyReturns = [];
      for (let i = 1; i < history.length; i++) {
        const prevValue = history[i - 1].totalValue;
        const currentValue = history[i].totalValue;
        if (prevValue > 0) {
          dailyReturns.push((currentValue - prevValue) / prevValue);
        }
      }

      // Calculate performance metrics
      const totalReturn = history[history.length - 1].totalValue - history[0].totalValue;
      const totalReturnPercent = history[0].totalValue > 0 ? 
        (totalReturn / history[0].totalValue) * 100 : 0;

      const avgReturn = dailyReturns.reduce((sum, ret) => sum + ret, 0) / dailyReturns.length;
      const variance = dailyReturns.reduce((sum, ret) => sum + Math.pow(ret - avgReturn, 2), 0) / dailyReturns.length;
      const volatility = Math.sqrt(variance) * Math.sqrt(252); // Annualized

      const sharpeRatio = volatility > 0 ? (avgReturn * 252) / volatility : 0; // Assuming 0% risk-free rate

      // Calculate max drawdown
      let maxDrawdown = 0;
      let peak = history[0].totalValue;
      for (const point of history) {
        if (point.totalValue > peak) {
          peak = point.totalValue;
        }
        const drawdown = (peak - point.totalValue) / peak;
        maxDrawdown = Math.max(maxDrawdown, drawdown);
      }

      const performance = {
        period,
        totalReturn,
        totalReturnPercent,
        dailyReturns,
        volatility,
        sharpeRatio,
        maxDrawdown,
        dataPoints: history.length,
        calculatedAt: new Date().toISOString()
      };

      logger.info(`Calculated portfolio performance for user ${userId}: ${totalReturnPercent.toFixed(2)}% return`);
      return performance;

    } catch (error) {
      logger.error('Error calculating portfolio performance:', {
        userId,
        period,
        error: error.message,
        stack: error.stack
      });
      throw new Error(`Failed to calculate portfolio performance: ${error.message}`);
    }
  }

  /**
   * Health check for portfolio service
   */
  async healthCheck() {
    try {
      const dbHealth = await healthCheck();
      return {
        status: 'healthy',
        database: dbHealth,
        service: 'portfolio',
        timestamp: new Date().toISOString()
      };
    } catch (error) {
      return {
        status: 'unhealthy',
        error: error.message,
        service: 'portfolio',
        timestamp: new Date().toISOString()
      };
    }
  }
}

// Create and export singleton instance
const portfolioService = new PortfolioService();

module.exports = portfolioService;
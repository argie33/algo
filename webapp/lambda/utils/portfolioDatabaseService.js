/**
 * Portfolio Database Service
 * Handles all database operations for portfolio data storage and retrieval
 */

const { query, transaction } = require('./database');

class PortfolioDatabaseService {
  /**
   * Store portfolio holdings from Alpaca in database
   * @param {string} userId - User identifier
   * @param {Array} holdings - Array of holding objects from Alpaca
   * @param {string} accountType - 'paper' or 'live'
   */
  async storePortfolioHoldings(userId, holdings, accountType) {
    if (!holdings || holdings.length === 0) {
      console.log('📋 No holdings to store for user:', userId);
      return { stored: 0 };
    }

    console.log(`💾 Storing ${holdings.length} holdings for user ${userId}`);

    const queries = holdings.map(holding => ({
      text: `
        INSERT INTO portfolio_holdings 
        (user_id, symbol, quantity, avg_cost, current_price, market_value, 
         unrealized_pl, sector, alpaca_asset_id, last_sync_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, CURRENT_TIMESTAMP)
        ON CONFLICT (user_id, symbol) 
        DO UPDATE SET
          quantity = EXCLUDED.quantity,
          avg_cost = EXCLUDED.avg_cost,
          current_price = EXCLUDED.current_price,
          market_value = EXCLUDED.market_value,
          unrealized_pl = EXCLUDED.unrealized_pl,
          last_sync_at = CURRENT_TIMESTAMP,
          updated_at = CURRENT_TIMESTAMP
      `,
      values: [
        userId,
        holding.symbol,
        parseFloat(holding.qty) || 0,
        parseFloat(holding.avg_entry_price) || 0,
        parseFloat(holding.current_price) || parseFloat(holding.market_value) / parseFloat(holding.qty) || 0,
        parseFloat(holding.market_value) || 0,
        parseFloat(holding.unrealized_pl) || 0,
        holding.sector || 'Unknown',
        holding.asset_id || null
      ]
    }));

    try {
      const results = await transaction(queries);
      console.log(`✅ Successfully stored ${holdings.length} holdings for user ${userId}`);
      return { stored: holdings.length, results };
    } catch (error) {
      console.error('❌ Error storing portfolio holdings:', error);
      throw new Error(`Failed to store portfolio holdings: ${error.message}`);
    }
  }

  /**
   * Get cached portfolio data from database
   * @param {string} userId - User identifier
   * @param {string} accountType - 'paper' or 'live'
   */
  async getCachedPortfolioData(userId, accountType) {
    try {
      console.log(`📋 Getting cached portfolio data for user ${userId}, account: ${accountType}`);

      const result = await query(`
        SELECT 
          h.*,
          m.total_equity,
          m.buying_power,
          m.cash,
          m.last_sync_at,
          m.account_type,
          m.account_id
        FROM portfolio_holdings h
        LEFT JOIN portfolio_metadata m ON h.user_id = m.user_id
        WHERE h.user_id = $1
        ORDER BY h.market_value DESC NULLS LAST
      `, [userId]);

      if (result.rows.length === 0) {
        console.log(`📭 No cached portfolio data found for user ${userId}`);
        return null;
      }

      const formattedData = this.formatPortfolioResponse(result.rows);
      console.log(`✅ Retrieved cached portfolio data for user ${userId}: ${formattedData.holdings.length} holdings`);
      return formattedData;

    } catch (error) {
      console.error('❌ Error getting cached portfolio data:', error);
      throw new Error(`Failed to get cached portfolio data: ${error.message}`);
    }
  }

  /**
   * Update portfolio metadata (account-level information)
   * @param {string} userId - User identifier
   * @param {Object} accountData - Account data from Alpaca
   * @param {string} accountType - 'paper' or 'live'
   */
  async updatePortfolioMetadata(userId, accountData, accountType) {
    try {
      console.log(`📊 Updating portfolio metadata for user ${userId}`);

      const result = await query(`
        INSERT INTO portfolio_metadata 
        (user_id, account_id, account_type, total_equity, buying_power, 
         cash, last_sync_at, sync_status, api_provider)
        VALUES ($1, $2, $3, $4, $5, $6, CURRENT_TIMESTAMP, 'success', 'alpaca')
        ON CONFLICT (user_id) 
        DO UPDATE SET
          account_id = EXCLUDED.account_id,
          account_type = EXCLUDED.account_type,
          total_equity = EXCLUDED.total_equity,
          buying_power = EXCLUDED.buying_power,
          cash = EXCLUDED.cash,
          last_sync_at = CURRENT_TIMESTAMP,
          sync_status = 'success',
          api_provider = 'alpaca',
          updated_at = CURRENT_TIMESTAMP
        RETURNING *
      `, [
        userId,
        accountData.account_number || accountData.id,
        accountType,
        parseFloat(accountData.equity) || 0,
        parseFloat(accountData.buying_power) || 0,
        parseFloat(accountData.cash) || 0
      ]);

      console.log(`✅ Updated portfolio metadata for user ${userId}`);
      return result.rows[0];

    } catch (error) {
      console.error('❌ Error updating portfolio metadata:', error);
      throw new Error(`Failed to update portfolio metadata: ${error.message}`);
    }
  }

  /**
   * Check if cached data is stale
   * @param {Object} data - Cached portfolio data
   * @param {number} maxAgeMs - Maximum age in milliseconds (default: 5 minutes)
   */
  isDataStale(data, maxAgeMs = 5 * 60 * 1000) {
    if (!data || !data.lastSync) {
      return true;
    }

    const age = Date.now() - new Date(data.lastSync).getTime();
    const isStale = age > maxAgeMs;
    
    console.log(`🕐 Data age: ${Math.round(age / 1000)}s, max age: ${Math.round(maxAgeMs / 1000)}s, stale: ${isStale}`);
    return isStale;
  }

  /**
   * Format database response for frontend consumption
   * @param {Array} rows - Database result rows
   */
  formatPortfolioResponse(rows) {
    if (rows.length === 0) {
      return null;
    }

    const metadata = rows[0];
    
    // Filter out rows without symbols (metadata-only rows)
    const holdings = rows
      .filter(row => row.symbol)
      .map(row => ({
        symbol: row.symbol,
        quantity: parseFloat(row.quantity) || 0,
        avgCost: parseFloat(row.avg_cost) || 0,
        currentPrice: parseFloat(row.current_price) || 0,
        marketValue: parseFloat(row.market_value) || 0,
        unrealizedPL: parseFloat(row.unrealized_pl) || 0,
        sector: row.sector || 'Unknown',
        lastUpdated: row.updated_at,
        alpacaAssetId: row.alpaca_asset_id
      }));

    const summary = {
      totalEquity: parseFloat(metadata.total_equity) || 0,
      buyingPower: parseFloat(metadata.buying_power) || 0,
      cash: parseFloat(metadata.cash) || 0,
      accountType: metadata.account_type || 'paper',
      accountId: metadata.account_id,
      totalValue: holdings.reduce((sum, holding) => sum + holding.marketValue, 0),
      totalPL: holdings.reduce((sum, holding) => sum + holding.unrealizedPL, 0),
      positionCount: holdings.length
    };

    return {
      holdings,
      summary,
      lastSync: metadata.last_sync_at,
      dataSource: 'database'
    };
  }

  /**
   * Clean up old portfolio data for a user
   * @param {string} userId - User identifier
   * @param {number} daysToKeep - Number of days of history to keep
   */
  async cleanupOldData(userId, daysToKeep = 30) {
    try {
      console.log(`🧹 Cleaning up portfolio data older than ${daysToKeep} days for user ${userId}`);

      // Clean up old performance history
      const cleanupResult = await query(`
        DELETE FROM portfolio_performance_history 
        WHERE user_id = $1 
        AND date < CURRENT_DATE - INTERVAL '${daysToKeep} days'
      `, [userId]);

      console.log(`✅ Cleaned up ${cleanupResult.rowCount} old performance records for user ${userId}`);
      return cleanupResult.rowCount;

    } catch (error) {
      console.error('❌ Error cleaning up old data:', error);
      throw new Error(`Failed to cleanup old data: ${error.message}`);
    }
  }

  /**
   * Get portfolio performance history
   * @param {string} userId - User identifier
   * @param {number} days - Number of days to retrieve
   */
  async getPerformanceHistory(userId, days = 30) {
    try {
      const result = await query(`
        SELECT * FROM portfolio_performance_history
        WHERE user_id = $1
        AND date >= CURRENT_DATE - INTERVAL '${days} days'
        ORDER BY date ASC
      `, [userId]);

      return result.rows.map(row => ({
        date: row.date,
        totalValue: parseFloat(row.total_value),
        totalCost: parseFloat(row.total_cost),
        unrealizedPL: parseFloat(row.unrealized_pl),
        realizedPL: parseFloat(row.realized_pl),
        cashValue: parseFloat(row.cash_value),
        positionCount: row.position_count
      }));

    } catch (error) {
      console.error('❌ Error getting performance history:', error);
      throw new Error(`Failed to get performance history: ${error.message}`);
    }
  }

  /**
   * Store daily portfolio performance snapshot
   * @param {string} userId - User identifier
   * @param {Object} performanceData - Daily performance data
   */
  async storePerformanceSnapshot(userId, performanceData) {
    try {
      const result = await query(`
        INSERT INTO portfolio_performance_history
        (user_id, date, total_value, total_cost, unrealized_pl, realized_pl, 
         cash_value, position_count)
        VALUES ($1, CURRENT_DATE, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (user_id, date)
        DO UPDATE SET
          total_value = EXCLUDED.total_value,
          total_cost = EXCLUDED.total_cost,
          unrealized_pl = EXCLUDED.unrealized_pl,
          realized_pl = EXCLUDED.realized_pl,
          cash_value = EXCLUDED.cash_value,
          position_count = EXCLUDED.position_count,
          created_at = CURRENT_TIMESTAMP
      `, [
        userId,
        parseFloat(performanceData.totalValue) || 0,
        parseFloat(performanceData.totalCost) || 0,
        parseFloat(performanceData.unrealizedPL) || 0,
        parseFloat(performanceData.realizedPL) || 0,
        parseFloat(performanceData.cashValue) || 0,
        parseInt(performanceData.positionCount) || 0
      ]);

      return result.rowCount;

    } catch (error) {
      console.error('❌ Error storing performance snapshot:', error);
      throw new Error(`Failed to store performance snapshot: ${error.message}`);
    }
  }
}

module.exports = new PortfolioDatabaseService();
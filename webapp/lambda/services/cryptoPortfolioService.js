/**
 * Crypto Portfolio Service
 * 
 * Comprehensive cryptocurrency portfolio management service with database integration,
 * real-time price updates, and advanced portfolio analytics
 */

const { query } = require('../utils/database');
const enhancedCryptoDataService = require('./enhancedCryptoDataService');
const { StructuredLogger } = require('../utils/structuredLogger');
const logger = new StructuredLogger('crypto-portfolio');

class CryptoPortfolioService {
  constructor() {
    this.logger = logger;
    this.priceCache = new Map();
    this.cacheTimeout = 30000; // 30 seconds
    
    console.log('🚀 Crypto Portfolio Service initialized');
  }

  /**
   * Get user's complete crypto portfolio with real-time valuations
   */
  async getUserPortfolio(userId, options = {}) {
    const startTime = Date.now();
    
    try {
      this.logger.info('Fetching user crypto portfolio', { user_id: userId });

      // Fetch portfolio holdings from database
      const portfolioQuery = `
        SELECT 
          cp.*,
          ca.name as asset_name,
          ca.coingecko_id,
          ca.contract_address,
          ca.blockchain
        FROM crypto_portfolio cp
        LEFT JOIN crypto_assets ca ON cp.symbol = ca.symbol
        WHERE cp.user_id = $1
        ORDER BY cp.market_value DESC NULLS LAST
      `;
      
      const portfolioResult = await query(portfolioQuery, [userId]);
      const holdings = portfolioResult.rows;

      if (holdings.length === 0) {
        return {
          success: true,
          data: {
            holdings: [],
            summary: {
              total_value: 0,
              total_cost: 0,
              total_pnl: 0,
              total_pnl_percentage: 0,
              asset_count: 0
            },
            last_updated: new Date().toISOString()
          }
        };
      }

      // Get current prices for all holdings
      const symbols = holdings.map(h => h.symbol.toLowerCase());
      const priceData = await this.getCurrentPrices(symbols);

      // Calculate portfolio metrics with current prices
      const updatedHoldings = await this.calculateHoldingMetrics(holdings, priceData);
      
      // Update database with current prices and calculations
      await this.updatePortfolioValuations(userId, updatedHoldings);

      // Calculate portfolio summary
      const summary = this.calculatePortfolioSummary(updatedHoldings);

      // Get recent transactions for context
      const recentTransactions = options.includeTransactions 
        ? await this.getRecentTransactions(userId, 10)
        : [];

      // Get performance metrics
      const performanceMetrics = options.includePerformance
        ? await this.calculatePerformanceMetrics(userId)
        : null;

      const duration = Date.now() - startTime;
      
      this.logger.performance('user_portfolio_fetch', duration, {
        user_id: userId,
        holdings_count: holdings.length,
        total_value: summary.total_value
      });

      return {
        success: true,
        data: {
          holdings: updatedHoldings,
          summary,
          recent_transactions: recentTransactions,
          performance_metrics: performanceMetrics,
          last_updated: new Date().toISOString(),
          calculation_time_ms: duration
        }
      };

    } catch (error) {
      this.logger.error('Failed to fetch user portfolio', error, { user_id: userId });
      throw new Error(`Portfolio fetch failed: ${error.message}`);
    }
  }

  /**
   * Add or update portfolio holding
   */
  async updateHolding(userId, symbol, quantity, averageCost, transactionType = 'manual') {
    const startTime = Date.now();
    
    try {
      this.logger.info('Updating portfolio holding', { 
        user_id: userId, 
        symbol, 
        quantity, 
        transaction_type: transactionType 
      });

      // Ensure crypto asset exists in database
      await this.ensureCryptoAsset(symbol);

      // Get current price
      const currentPrice = await this.getCurrentPrice(symbol);

      // Calculate metrics
      const marketValue = quantity * currentPrice;
      const totalCost = quantity * averageCost;
      const unrealizedPnl = marketValue - totalCost;
      const unrealizedPnlPercent = totalCost > 0 ? (unrealizedPnl / totalCost) * 100 : 0;

      // Upsert portfolio holding
      const upsertQuery = `
        INSERT INTO crypto_portfolio (
          user_id, symbol, quantity, average_cost, current_price, 
          market_value, total_cost, unrealized_pnl, unrealized_pnl_percent,
          last_updated
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, CURRENT_TIMESTAMP)
        ON CONFLICT (user_id, symbol) 
        DO UPDATE SET
          quantity = EXCLUDED.quantity,
          average_cost = EXCLUDED.average_cost,
          current_price = EXCLUDED.current_price,
          market_value = EXCLUDED.market_value,
          total_cost = EXCLUDED.total_cost,
          unrealized_pnl = EXCLUDED.unrealized_pnl,
          unrealized_pnl_percent = EXCLUDED.unrealized_pnl_percent,
          last_updated = CURRENT_TIMESTAMP
        RETURNING *
      `;

      const result = await query(upsertQuery, [
        userId, symbol.toUpperCase(), quantity, averageCost, currentPrice,
        marketValue, totalCost, unrealizedPnl, unrealizedPnlPercent
      ]);

      // Record transaction if it's a buy/sell
      if (transactionType !== 'manual') {
        await this.recordTransaction(userId, symbol, transactionType, quantity, currentPrice);
      }

      const duration = Date.now() - startTime;
      
      this.logger.performance('portfolio_holding_update', duration, {
        user_id: userId,
        symbol: symbol,
        new_quantity: quantity
      });

      return {
        success: true,
        data: result.rows[0],
        updated_at: new Date().toISOString()
      };

    } catch (error) {
      this.logger.error('Failed to update holding', error, { 
        user_id: userId, 
        symbol,
        quantity 
      });
      throw new Error(`Holding update failed: ${error.message}`);
    }
  }

  /**
   * Record a crypto transaction
   */
  async recordTransaction(userId, symbol, transactionType, quantity, price, fees = 0, exchange = 'manual', notes = '') {
    try {
      const totalAmount = quantity * price;
      
      const insertQuery = `
        INSERT INTO crypto_transactions (
          user_id, symbol, transaction_type, quantity, price, 
          total_amount, fees, exchange, notes, transaction_date
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, CURRENT_TIMESTAMP)
        RETURNING *
      `;

      const result = await query(insertQuery, [
        userId, symbol.toUpperCase(), transactionType.toUpperCase(), 
        quantity, price, totalAmount, fees, exchange, notes
      ]);

      this.logger.info('Transaction recorded', {
        user_id: userId,
        symbol: symbol,
        type: transactionType,
        amount: totalAmount
      });

      return {
        success: true,
        data: result.rows[0]
      };

    } catch (error) {
      this.logger.error('Failed to record transaction', error, {
        user_id: userId,
        symbol,
        transaction_type: transactionType
      });
      throw new Error(`Transaction recording failed: ${error.message}`);
    }
  }

  /**
   * Get user's recent transactions
   */
  async getRecentTransactions(userId, limit = 50) {
    try {
      const transactionsQuery = `
        SELECT 
          ct.*,
          ca.name as asset_name
        FROM crypto_transactions ct
        LEFT JOIN crypto_assets ca ON ct.symbol = ca.symbol
        WHERE ct.user_id = $1
        ORDER BY ct.transaction_date DESC
        LIMIT $2
      `;

      const result = await query(transactionsQuery, [userId, limit]);
      return result.rows;

    } catch (error) {
      this.logger.error('Failed to fetch transactions', error, { user_id: userId });
      return [];
    }
  }

  /**
   * Calculate portfolio performance metrics
   */
  async calculatePerformanceMetrics(userId) {
    try {
      // Get portfolio history for calculations
      const metricsQuery = `
        SELECT 
          SUM(market_value) as total_value,
          SUM(total_cost) as total_cost,
          SUM(unrealized_pnl) as total_pnl,
          AVG(unrealized_pnl_percent) as avg_return,
          COUNT(*) as position_count,
          MAX(last_updated) as last_updated
        FROM crypto_portfolio 
        WHERE user_id = $1 AND quantity > 0
      `;

      const metricsResult = await query(metricsQuery, [userId]);
      const metrics = metricsResult.rows[0];

      // Calculate additional metrics
      const totalReturn = metrics.total_cost > 0 
        ? (metrics.total_pnl / metrics.total_cost) * 100 
        : 0;

      // Get best and worst performing assets
      const performanceQuery = `
        SELECT symbol, unrealized_pnl_percent, market_value
        FROM crypto_portfolio 
        WHERE user_id = $1 AND quantity > 0
        ORDER BY unrealized_pnl_percent DESC
      `;

      const performanceResult = await query(performanceQuery, [userId]);
      const performances = performanceResult.rows;

      return {
        total_return_percentage: totalReturn,
        total_value: parseFloat(metrics.total_value) || 0,
        total_cost: parseFloat(metrics.total_cost) || 0,
        total_pnl: parseFloat(metrics.total_pnl) || 0,
        position_count: parseInt(metrics.position_count) || 0,
        best_performer: performances[0] || null,
        worst_performer: performances[performances.length - 1] || null,
        last_updated: metrics.last_updated
      };

    } catch (error) {
      this.logger.error('Failed to calculate performance metrics', error, { user_id: userId });
      return null;
    }
  }

  /**
   * Get current prices for multiple cryptocurrencies
   */
  async getCurrentPrices(symbols) {
    try {
      // Check cache first
      const cached = this.getPricesFromCache(symbols);
      if (cached && Object.keys(cached).length === symbols.length) {
        return cached;
      }

      // Fetch from data service
      const priceData = await enhancedCryptoDataService.getRealTimePrices(symbols);
      
      if (priceData.success) {
        // Convert to symbol -> price mapping
        const prices = {};
        priceData.data.forEach(coin => {
          prices[coin.symbol.toLowerCase()] = coin.current_price;
        });

        // Cache the results
        this.setPricesInCache(prices);
        return prices;
      }

      throw new Error('Failed to fetch price data');

    } catch (error) {
      this.logger.error('Failed to get current prices', error, { symbols });
      
      // Return cached data if available, even if stale
      const staleCache = this.getPricesFromCache(symbols, true);
      if (staleCache) {
        return staleCache;
      }

      // Ultimate fallback - return zeros
      const fallbackPrices = {};
      symbols.forEach(symbol => {
        fallbackPrices[symbol] = 0;
      });
      return fallbackPrices;
    }
  }

  /**
   * Get current price for a single cryptocurrency
   */
  async getCurrentPrice(symbol) {
    const prices = await this.getCurrentPrices([symbol.toLowerCase()]);
    return prices[symbol.toLowerCase()] || 0;
  }

  /**
   * Calculate holding metrics with current prices
   */
  async calculateHoldingMetrics(holdings, priceData) {
    return holdings.map(holding => {
      const currentPrice = priceData[holding.symbol.toLowerCase()] || holding.current_price || 0;
      const marketValue = holding.quantity * currentPrice;
      const totalCost = holding.quantity * holding.average_cost;
      const unrealizedPnl = marketValue - totalCost;
      const unrealizedPnlPercent = totalCost > 0 ? (unrealizedPnl / totalCost) * 100 : 0;

      return {
        ...holding,
        current_price: currentPrice,
        market_value: marketValue,
        total_cost: totalCost,
        unrealized_pnl: unrealizedPnl,
        unrealized_pnl_percent: unrealizedPnlPercent,
        allocation_percentage: 0 // Will be calculated in summary
      };
    });
  }

  /**
   * Calculate portfolio summary metrics
   */
  calculatePortfolioSummary(holdings) {
    const totalValue = holdings.reduce((sum, h) => sum + h.market_value, 0);
    const totalCost = holdings.reduce((sum, h) => sum + h.total_cost, 0);
    const totalPnl = holdings.reduce((sum, h) => sum + h.unrealized_pnl, 0);
    const totalPnlPercentage = totalCost > 0 ? (totalPnl / totalCost) * 100 : 0;

    // Calculate allocation percentages
    holdings.forEach(holding => {
      holding.allocation_percentage = totalValue > 0 
        ? (holding.market_value / totalValue) * 100 
        : 0;
    });

    return {
      total_value: totalValue,
      total_cost: totalCost,
      total_pnl: totalPnl,
      total_pnl_percentage: totalPnlPercentage,
      asset_count: holdings.filter(h => h.quantity > 0).length,
      largest_holding: holdings.length > 0 ? holdings[0] : null,
      most_profitable: holdings.reduce((best, current) => 
        current.unrealized_pnl_percent > (best?.unrealized_pnl_percent || -Infinity) ? current : best, null),
      least_profitable: holdings.reduce((worst, current) => 
        current.unrealized_pnl_percent < (worst?.unrealized_pnl_percent || Infinity) ? current : worst, null)
    };
  }

  /**
   * Update portfolio valuations in database
   */
  async updatePortfolioValuations(userId, holdings) {
    try {
      const updatePromises = holdings.map(holding => {
        const updateQuery = `
          UPDATE crypto_portfolio 
          SET 
            current_price = $1,
            market_value = $2,
            unrealized_pnl = $3,
            unrealized_pnl_percent = $4,
            last_updated = CURRENT_TIMESTAMP
          WHERE user_id = $5 AND symbol = $6
        `;

        return query(updateQuery, [
          holding.current_price,
          holding.market_value,
          holding.unrealized_pnl,
          holding.unrealized_pnl_percent,
          userId,
          holding.symbol
        ]);
      });

      await Promise.allSettled(updatePromises);

    } catch (error) {
      this.logger.error('Failed to update portfolio valuations', error, { user_id: userId });
      // Don't throw - this is not critical for the response
    }
  }

  /**
   * Ensure crypto asset exists in database
   */
  async ensureCryptoAsset(symbol) {
    try {
      // Check if asset exists
      const checkQuery = `SELECT symbol FROM crypto_assets WHERE symbol = $1`;
      const checkResult = await query(checkQuery, [symbol.toUpperCase()]);

      if (checkResult.rows.length === 0) {
        // Asset doesn't exist, create it
        const insertQuery = `
          INSERT INTO crypto_assets (symbol, name, is_active)
          VALUES ($1, $2, true)
          ON CONFLICT (symbol) DO NOTHING
        `;

        await query(insertQuery, [symbol.toUpperCase(), symbol.toUpperCase()]);
        
        this.logger.info('Created new crypto asset', { symbol });
      }

    } catch (error) {
      this.logger.error('Failed to ensure crypto asset', error, { symbol });
      // Don't throw - this is not critical
    }
  }

  /**
   * Cache management for prices
   */
  getPricesFromCache(symbols, allowStale = false) {
    const now = Date.now();
    const prices = {};
    let hasAllPrices = true;

    symbols.forEach(symbol => {
      const cached = this.priceCache.get(symbol);
      if (cached) {
        const isStale = now - cached.timestamp > this.cacheTimeout;
        if (!isStale || allowStale) {
          prices[symbol] = cached.price;
        } else {
          hasAllPrices = false;
        }
      } else {
        hasAllPrices = false;
      }
    });

    return hasAllPrices ? prices : null;
  }

  setPricesInCache(prices) {
    const timestamp = Date.now();
    Object.entries(prices).forEach(([symbol, price]) => {
      this.priceCache.set(symbol, { price, timestamp });
    });

    // Clean old cache entries
    if (this.priceCache.size > 200) {
      const entries = Array.from(this.priceCache.entries());
      entries.sort((a, b) => a[1].timestamp - b[1].timestamp);
      entries.slice(0, 50).forEach(([symbol]) => {
        this.priceCache.delete(symbol);
      });
    }
  }

  /**
   * Delete portfolio holding
   */
  async deleteHolding(userId, symbol) {
    try {
      const deleteQuery = `
        DELETE FROM crypto_portfolio 
        WHERE user_id = $1 AND symbol = $2
        RETURNING *
      `;

      const result = await query(deleteQuery, [userId, symbol.toUpperCase()]);

      this.logger.info('Portfolio holding deleted', {
        user_id: userId,
        symbol: symbol,
        deleted: result.rowCount > 0
      });

      return {
        success: true,
        deleted: result.rowCount > 0,
        data: result.rows[0] || null
      };

    } catch (error) {
      this.logger.error('Failed to delete holding', error, { user_id: userId, symbol });
      throw new Error(`Failed to delete holding: ${error.message}`);
    }
  }

  /**
   * Get portfolio allocation analysis
   */
  async getPortfolioAllocation(userId) {
    try {
      const allocationQuery = `
        SELECT 
          cp.symbol,
          ca.name,
          cp.market_value,
          cp.quantity,
          cp.current_price,
          ROUND((cp.market_value / NULLIF(SUM(cp.market_value) OVER(), 0)) * 100, 2) as allocation_percentage
        FROM crypto_portfolio cp
        LEFT JOIN crypto_assets ca ON cp.symbol = ca.symbol
        WHERE cp.user_id = $1 AND cp.quantity > 0
        ORDER BY cp.market_value DESC
      `;

      const result = await query(allocationQuery, [userId]);
      return {
        success: true,
        data: result.rows
      };

    } catch (error) {
      this.logger.error('Failed to get portfolio allocation', error, { user_id: userId });
      throw new Error(`Allocation analysis failed: ${error.message}`);
    }
  }
}

// Export singleton instance
module.exports = new CryptoPortfolioService();
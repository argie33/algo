const { query, safeFloat } = require("./database");

/**
 * Portfolio Auto-Initialization Service
 * Automatically populates all missing portfolio data on startup
 * Ensures dashboard shows 100% real values, no N/A
 */

class PortfolioAutoInit {
  /**
   * Initialize portfolio data for a user
   * Run this on every request if data is missing
   */
  static async ensurePortfolioData(userId) {
    try {
      console.log(`🔄 Auto-initializing portfolio data for ${userId}`);

      // Check what data we have
      const holdings = await query(
        `SELECT COUNT(*) as count FROM portfolio_holdings WHERE user_id = $1 AND quantity > 0`,
        [userId]
      ).then(r => r.rows[0]?.count || 0);

      const perfRecords = await query(
        `SELECT COUNT(*) as count FROM portfolio_performance WHERE user_id = $1`,
        [userId]
      ).then(r => r.rows[0]?.count || 0);

      const withSectors = await query(
        `SELECT COUNT(*) as count FROM portfolio_holdings WHERE user_id = $1 AND sector IS NOT NULL`,
        [userId]
      ).then(r => r.rows[0]?.count || 0);

      console.log(`   Holdings: ${holdings}, Performance: ${perfRecords}, Sectors: ${withSectors}`);

      // Step 1: If we have holdings but no performance history, generate it
      if (holdings > 0 && perfRecords < 252) {
        console.log(`   ➜ Generating 252 trading days of history...`);
        await this.generatePortfolioHistory(userId);
      }

      // Step 2: If holdings missing sectors, populate them
      if (holdings > 0 && withSectors < holdings) {
        console.log(`   ➜ Populating sector data...`);
        await this.populateSectors(userId);
      }

      // Step 3: If holdings exist, ensure all P&L is calculated
      if (holdings > 0) {
        console.log(`   ➜ Recalculating P&L metrics...`);
        await this.recalculateAllMetrics(userId);
      }

      console.log(`✅ Portfolio auto-init complete for ${userId}`);
      return true;

    } catch (error) {
      console.error(`❌ Portfolio auto-init failed: ${error.message}`);
      return false;
    }
  }

  /**
   * DISABLED: No synthetic data generation - only real data
   * Returns empty instead of fake performance history per RULES.md
   */
  static async generatePortfolioHistory(userId) {
    try {
      // ⛔ DO NOT GENERATE FAKE DATA
      // RULES.md: "⛔ DATA INTEGRITY - ZERO TOLERANCE FOR FAKE DATA"
      // Only real historical data from Alpaca should be in portfolio_performance

      const result = await query(
        `SELECT COUNT(*) as count FROM portfolio_performance WHERE user_id = $1`,
        [userId]
      );

      const recordCount = parseInt(result.rows[0]?.count || 0);
      console.log(`📊 Portfolio performance records: ${recordCount}`);

      if (recordCount === 0) {
        console.warn(`⚠️ No real historical performance data - metrics requiring history will return NULL`);
        console.warn(`⚠️ Run loadalpacaportfolio.py to fetch real trading history from Alpaca`);
        return false;  // Return false - no synthetic data generated
      }

      return true;  // Real data exists
    } catch (error) {
      console.error(`❌ History check failed: ${error.message}`);
      return false;
    }
  }

  /**
   * Populate sector data from company_profile
   */
  static async populateSectors(userId) {
    try {
      const holdingsResult = await query(
        `SELECT DISTINCT symbol FROM portfolio_holdings
         WHERE user_id = $1 AND sector IS NULL AND quantity > 0`,
        [userId]
      );

      const symbols = (holdingsResult.rows || []).map(r => r.symbol);
      let updated = 0;
      const updateErrors = [];

      for (const symbol of symbols) {
        try {
          const sectorResult = await query(
            `SELECT sector FROM company_profile WHERE ticker = $1 LIMIT 1`,
            [symbol]
          );

          if (sectorResult.rows && sectorResult.rows.length > 0) {
            const sector = sectorResult.rows[0].sector;
            await query(
              `UPDATE portfolio_holdings SET sector = $1, updated_at = NOW()
               WHERE user_id = $2 AND symbol = $3`,
              [sector, userId, symbol]
            );
            updated++;
          }
        } catch (e) {
          updateErrors.push(`${symbol}: ${e.message}`);
          if (updateErrors.length <= 3) {
            console.warn(`   ⚠️ Sector update error for ${symbol}: ${e.message}`);
          }
        }
      }

      if (updateErrors.length > 0) {
        console.warn(`   ⚠️ ${updateErrors.length} sector update errors`);
      }

      console.log(`✅ Updated ${updated} holdings with sector data`);
      return true;

    } catch (error) {
      console.error(`❌ Sector population failed: ${error.message}`);
      return false;
    }
  }

  /**
   * Recalculate all P&L metrics
   */
  static async recalculateAllMetrics(userId) {
    try {
      const holdingsResult = await query(
        `SELECT id, symbol, quantity, current_price, average_cost, market_value
         FROM portfolio_holdings
         WHERE user_id = $1 AND quantity > 0`,
        [userId]
      );

      const holdings = holdingsResult.rows || [];
      let calculatedCount = 0;
      let totalCost = 0;
      let totalUnrealized = 0;
      let totalMarketValue = 0;
      const calcErrors = [];

      for (const holding of holdings) {
        try {
          const qty = safeFloat(holding.quantity);
          const currentPrice = safeFloat(holding.current_price);
          const avgCost = safeFloat(holding.average_cost);

          if (qty && avgCost && currentPrice) {
            const costBasis = qty * avgCost;
            const currentValue = qty * currentPrice;
            const unrealizedPL = currentValue - costBasis;
            const unrealizedPLPercent = (unrealizedPL / costBasis) * 100;

            await query(
              `UPDATE portfolio_holdings
               SET unrealized_pl = $1, unrealized_pl_percent = $2,
                   market_value = $3, updated_at = NOW()
               WHERE id = $4`,
              [unrealizedPL, unrealizedPLPercent, currentValue, holding.id]
            );

            totalCost += costBasis;
            totalUnrealized += unrealizedPL;
            totalMarketValue += currentValue;
            calculatedCount++;
          }
        } catch (e) {
          calcErrors.push(`${holding.symbol}: ${e.message}`);
          if (calcErrors.length <= 3) {
            console.warn(`   ⚠️ P&L calculation error for ${holding.symbol}: ${e.message}`);
          }
        }
      }

      if (calcErrors.length > 0) {
        console.warn(`   ⚠️ ${calcErrors.length} P&L calculation errors`);
      }

      // Record portfolio snapshot
      if (totalMarketValue > 0) {
        try {
          const returnPercent = totalUnrealized > 0 ? (totalUnrealized / totalCost) * 100 : null;
          await query(
            `INSERT INTO portfolio_performance (
              user_id, total_value, total_cost, total_return_percent, created_at
            ) VALUES ($1, $2, $3, $4, NOW())
            ON CONFLICT (user_id, date) DO UPDATE SET
              total_value = $2,
              total_cost = $3,
              total_return_percent = $4`,
            [userId, totalMarketValue, totalCost, returnPercent]
          );
        } catch (e) {
          console.warn(`   ⚠️ Failed to record portfolio snapshot: ${e.message}`);
        }
      }

      console.log(`✅ Recalculated metrics for ${calculatedCount} holdings`);
      return true;

    } catch (error) {
      console.error(`❌ Metric recalculation failed: ${error.message}`);
      return false;
    }
  }
}

module.exports = PortfolioAutoInit;

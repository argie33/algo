/**
 * Trade Executor
 * Executes optimizer recommendations on Alpaca
 * Tracks execution status and outcomes
 */

const AlpacaPortfolioFetcher = require('./alpaca-portfolio-fetcher');
const { query } = require('./database');

class TradeExecutor {
  constructor() {
    this.alpaca = new AlpacaPortfolioFetcher();
  }

  /**
   * Execute a single recommendation trade
   */
  async executeTrade(symbol, action, quantity, limitPrice = null) {
    try {
      const orderData = {
        symbol: symbol.toUpperCase(),
        qty: quantity,
        side: action.toLowerCase() === 'buy' ? 'buy' : 'sell',
        type: limitPrice ? 'limit' : 'market',
        time_in_force: 'day',
      };

      if (limitPrice) {
        orderData.limit_price = limitPrice;
      }

      // Submit order to Alpaca
      const result = await this.submitAlpacaOrder(orderData);

      if (!result || !result.id) {
        return {
          success: false,
          error: 'Failed to submit order to Alpaca',
          order: null,
        };
      }

      return {
        success: true,
        order_id: result.id,
        symbol: symbol,
        action: action,
        quantity: quantity,
        status: result.status,
        filled_qty: result.filled_qty || 0,
        filled_avg_price: result.filled_avg_price || limitPrice,
        submitted_at: new Date().toISOString(),
      };

    } catch (error) {
      console.error(`❌ Trade execution error for ${symbol}:`, error.message);
      return {
        success: false,
        error: error.message,
        symbol: symbol,
        action: action,
      };
    }
  }

  /**
   * Submit order to Alpaca API
   */
  async submitAlpacaOrder(orderData) {
    return new Promise((resolve, reject) => {
      const https = require('https');
      const body = JSON.stringify(orderData);

      const options = {
        hostname: new URL(this.alpaca.baseUrl).hostname,
        port: 443,
        path: '/v2/orders',
        method: 'POST',
        headers: {
          'APCA-API-KEY-ID': this.alpaca.apiKey,
          'Content-Type': 'application/json',
          'Content-Length': Buffer.byteLength(body),
        },
      };

      const req = https.request(options, (res) => {
        let data = '';

        res.on('data', (chunk) => {
          data += chunk;
        });

        res.on('end', () => {
          try {
            const parsed = JSON.parse(data);
            if (res.statusCode === 200 || res.statusCode === 201) {
              resolve(parsed);
            } else {
              reject(new Error(`Alpaca error: ${parsed.message || data}`));
            }
          } catch (e) {
            reject(new Error(`Failed to parse Alpaca response: ${data}`));
          }
        });
      });

      req.on('error', reject);
      req.write(body);
      req.end();
    });
  }

  /**
   * Execute all recommendations from an optimization run
   */
  async executeRecommendations(optimizationRunId, recommendations) {
    const results = [];
    const executedTrades = [];

    console.log(`🚀 Executing ${recommendations.length} recommendations...`);

    for (const rec of recommendations) {
      if (rec.action === 'BUY') {
        // For BUY: estimate quantity from target weight
        const quantity = Math.ceil(Math.abs(rec.quantity || 10));
        const result = await this.executeTrade(rec.symbol, 'BUY', quantity);
        results.push(result);

        if (result.success) {
          executedTrades.push({
            optimization_run_id: optimizationRunId,
            recommendation_id: rec.id,
            action: 'BUY',
            symbol: rec.symbol,
            reason: rec.reason,
            priority: rec.priority,
            target_weight: rec.targetWeight,
            quantity: quantity,
            order_id: result.order_id,
            alpaca_status: result.status,
            executed_at: new Date(),
          });
        }
      } else if (rec.action === 'SELL') {
        // For SELL: use specified quantity
        const quantity = rec.quantity || 10;
        const result = await this.executeTrade(rec.symbol, 'SELL', quantity);
        results.push(result);

        if (result.success) {
          executedTrades.push({
            optimization_run_id: optimizationRunId,
            recommendation_id: rec.id,
            action: 'SELL',
            symbol: rec.symbol,
            reason: rec.reason,
            priority: rec.priority,
            quantity: quantity,
            order_id: result.order_id,
            alpaca_status: result.status,
            executed_at: new Date(),
          });
        }
      }
    }

    // Save executed trades to database
    await this.saveExecutedTrades(executedTrades);

    return {
      total_recommended: recommendations.length,
      total_executed: results.filter(r => r.success).length,
      results: results,
    };
  }

  /**
   * Save executed trades to database
   */
  async saveExecutedTrades(trades) {
    for (const trade of trades) {
      try {
        await query(
          `INSERT INTO optimization_trades
           (optimization_run_id, recommendation_id, action, symbol, reason,
            priority, target_weight, quantity, order_id, alpaca_status, executed_at)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)`,
          [
            trade.optimization_run_id,
            trade.recommendation_id,
            trade.action,
            trade.symbol,
            trade.reason,
            trade.priority,
            trade.target_weight || null,
            trade.quantity,
            trade.order_id,
            trade.alpaca_status,
            trade.executed_at,
          ]
        );
        console.log(`✅ Saved trade: ${trade.action} ${trade.symbol}`);
      } catch (error) {
        console.error(`❌ Failed to save trade ${trade.symbol}:`, error.message);
      }
    }
  }

  /**
   * Get order status from Alpaca
   */
  async getOrderStatus(orderId) {
    try {
      const result = await this.alpaca.request('GET', `/v2/orders/${orderId}`);
      if (result.status === 200) {
        return {
          order_id: result.data.id,
          symbol: result.data.symbol,
          side: result.data.side,
          status: result.data.status,
          filled_qty: result.data.filled_qty,
          filled_avg_price: result.data.filled_avg_price,
        };
      }
      return null;
    } catch (error) {
      console.error('Error getting order status:', error.message);
      return null;
    }
  }

  /**
   * Cancel pending order
   */
  async cancelOrder(orderId) {
    try {
      const result = await this.alpaca.request('DELETE', `/v2/orders/${orderId}`);
      return result.status === 204;
    } catch (error) {
      console.error('Error canceling order:', error.message);
      return false;
    }
  }
}

module.exports = TradeExecutor;

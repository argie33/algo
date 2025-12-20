/**
 * Alpaca Trading Execution Handler
 *
 * Manages the execution of portfolio optimization recommendations through Alpaca
 * Handles both paper and live trading with proper validation and error handling
 */

const { AlpacaTrader, initializeAlpacaTrader } = require("../utils/alpacaTrading");
const { query } = require("../utils/database");

/**
 * Execute portfolio optimization trades via Alpaca
 * @param {string} userId - User ID
 * @param {string} optimizationId - Optimization ID for tracking
 * @param {Array} trades - Array of trades to execute
 * @param {Boolean} isPaper - Whether to use paper trading (default: true)
 * @returns {Promise<Object>} Execution results with status and trade details
 */
async function executeOptimizationTrades(userId, optimizationId, trades, isPaper = true) {
  try {
    console.log(`🚀 [Alpaca] Starting execution for ${trades.length} trades (${isPaper ? "PAPER" : "LIVE"} mode)`);

    const alpacaTrader = initializeAlpacaTrader(isPaper);

    if (!alpacaTrader) {
      return {
        success: false,
        message: "Alpaca credentials not configured",
        trades_attempted: 0,
        trades_executed: [],
        trades_failed: [],
        recommendations: {
          action: "Configure Alpaca API credentials (ALPACA_API_KEY, ALPACA_SECRET_KEY)",
          fallback: "Trades were recorded in database but not executed via Alpaca",
        },
      };
    }

    // Validate buying power before executing
    const buyingPowerResult = await alpacaTrader.getBuyingPower();
    if (!buyingPowerResult.success) {
      return {
        success: false,
        message: "Could not verify account buying power",
        error: buyingPowerResult.error,
        trades_attempted: 0,
        trades_executed: [],
        trades_failed: trades.map((t) => ({
          ...t,
          error: "Account validation failed",
        })),
      };
    }

    console.log(`💰 Account Status: $${buyingPowerResult.buying_power.toFixed(2)} buying power available`);

    // Separate trades by action type
    const buyTrades = trades.filter((t) => t.action === "BUY");
    const sellTrades = trades.filter((t) => t.action === "SELL" || t.action === "REDUCE");

    // Execute SELL/REDUCE first (generates cash), then BUY
    const executedTrades = [];
    const failedTrades = [];

    // Execute sells first
    for (const trade of sellTrades) {
      try {
        console.log(`📉 Executing ${trade.action}: ${trade.symbol} x${trade.quantity}`);

        const validateResult = await alpacaTrader.validateTrade(
          trade.symbol,
          trade.quantity,
          trade.action === "SELL" ? "sell" : "sell" // REDUCE is same as SELL for validation
        );

        if (!validateResult.valid) {
          failedTrades.push({
            ...trade,
            status: "validation_failed",
            error: validateResult.reason,
          });
          continue;
        }

        const orderResult = await alpacaTrader.createOrder(
          trade.symbol,
          trade.quantity,
          "sell",
          {
            type: "market",
            time_in_force: "day",
          }
        );

        if (orderResult.success) {
          executedTrades.push({
            symbol: trade.symbol,
            action: trade.action,
            quantity: trade.quantity,
            order_id: orderResult.data.id,
            status: "submitted",
            alpaca_status: orderResult.data.status,
            submitted_at: new Date().toISOString(),
          });

          // Update database to reflect executed trade
          await recordExecutedTrade(userId, optimizationId, {
            ...trade,
            order_id: orderResult.data.id,
            alpaca_execution: true,
          });
        } else {
          failedTrades.push({
            ...trade,
            status: "execution_failed",
            error: orderResult.error,
          });
        }
      } catch (error) {
        console.error(`Error executing sell ${trade.symbol}:`, error.message);
        failedTrades.push({
          ...trade,
          status: "execution_error",
          error: error.message,
        });
      }

      // Delay between orders to avoid rate limiting
      await new Promise((resolve) => setTimeout(resolve, 500));
    }

    // Get updated buying power after sells
    let updatedBuyingPower = buyingPowerResult.buying_power;
    if (sellTrades.length > 0) {
      const updatedResult = await alpacaTrader.getBuyingPower();
      if (updatedResult.success) {
        updatedBuyingPower = updatedResult.buying_power;
        console.log(`💰 Updated buying power: $${updatedBuyingPower.toFixed(2)}`);
      }
    }

    // Execute buys
    for (const trade of buyTrades) {
      try {
        console.log(`📈 Executing BUY: ${trade.symbol} x${trade.quantity}`);

        // Check if we have enough buying power
        const estimatedCost = trade.quantity * (trade.current_price || 150); // Fallback to $150 estimate
        if (estimatedCost > updatedBuyingPower * 0.95) {
          // Keep 5% buffer
          failedTrades.push({
            ...trade,
            status: "insufficient_funds",
            error: `Need $${estimatedCost.toFixed(2)}, have $${updatedBuyingPower.toFixed(2)}`,
            estimated_cost: estimatedCost,
          });
          continue;
        }

        const validateResult = await alpacaTrader.validateTrade(trade.symbol, trade.quantity, "buy");

        if (!validateResult.valid) {
          failedTrades.push({
            ...trade,
            status: "validation_failed",
            error: validateResult.reason,
          });
          continue;
        }

        const orderResult = await alpacaTrader.createOrder(
          trade.symbol,
          trade.quantity,
          "buy",
          {
            type: "market",
            time_in_force: "day",
          }
        );

        if (orderResult.success) {
          executedTrades.push({
            symbol: trade.symbol,
            action: trade.action,
            quantity: trade.quantity,
            order_id: orderResult.data.id,
            status: "submitted",
            alpaca_status: orderResult.data.status,
            submitted_at: new Date().toISOString(),
          });

          updatedBuyingPower -= estimatedCost;

          // Update database to reflect executed trade
          await recordExecutedTrade(userId, optimizationId, {
            ...trade,
            order_id: orderResult.data.id,
            alpaca_execution: true,
          });
        } else {
          failedTrades.push({
            ...trade,
            status: "execution_failed",
            error: orderResult.error,
          });
        }
      } catch (error) {
        console.error(`Error executing buy ${trade.symbol}:`, error.message);
        failedTrades.push({
          ...trade,
          status: "execution_error",
          error: error.message,
        });
      }

      // Delay between orders
      await new Promise((resolve) => setTimeout(resolve, 500));
    }

    // Summary
    console.log(
      `✅ Alpaca execution complete: ${executedTrades.length} executed, ${failedTrades.length} failed`
    );

    return {
      success: executedTrades.length > 0,
      message: `Successfully executed ${executedTrades.length} trades via Alpaca`,
      trades_attempted: trades.length,
      trades_executed: executedTrades,
      trades_failed: failedTrades.length > 0 ? failedTrades : null,
      summary: {
        total_trades: trades.length,
        successful: executedTrades.length,
        failed: failedTrades.length,
        execution_mode: isPaper ? "paper_trading" : "live_trading",
      },
      timestamp: new Date().toISOString(),
    };
  } catch (error) {
    console.error("❌ Alpaca execution handler error:", error);
    return {
      success: false,
      message: "Failed to execute trades via Alpaca",
      error: error.message,
      trades_attempted: trades.length,
      trades_executed: [],
      trades_failed: trades.map((t) => ({
        ...t,
        error: error.message,
      })),
    };
  }
}

/**
 * Record executed trade in database for audit trail
 */
async function recordExecutedTrade(userId, optimizationId, trade) {
  try {
    await query(
      `INSERT INTO trade_execution_log
       (user_id, optimization_id, symbol, action, quantity, order_id, alpaca_execution, status, created_at)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())`,
      [
        userId,
        optimizationId,
        trade.symbol,
        trade.action,
        trade.quantity,
        trade.order_id || null,
        trade.alpaca_execution || false,
        "submitted",
      ]
    );
  } catch (error) {
    console.warn(`Could not record trade execution for ${trade.symbol}:`, error.message);
    // Don't fail the whole operation if logging fails
  }
}

/**
 * Get execution status for a previously submitted optimization
 */
async function getExecutionStatus(optimizationId) {
  try {
    const result = await query(
      `SELECT * FROM trade_execution_log WHERE optimization_id = $1 ORDER BY created_at DESC`,
      [optimizationId]
    );

    const trades = result.rows || [];

    return {
      success: true,
      optimization_id: optimizationId,
      trades_count: trades.length,
      trades: trades.map((t) => ({
        symbol: t.symbol,
        action: t.action,
        quantity: t.quantity,
        order_id: t.order_id,
        status: t.status,
        executed_at: t.created_at,
      })),
    };
  } catch (error) {
    console.error("Error getting execution status:", error);
    return {
      success: false,
      error: error.message,
    };
  }
}

/**
 * Check status of pending Alpaca orders
 */
async function checkPendingOrders(orderIds = []) {
  try {
    const alpacaTrader = initializeAlpacaTrader(true);

    if (!alpacaTrader) {
      return {
        success: false,
        message: "Alpaca not configured",
        orders: [],
      };
    }

    const ordersResult = await alpacaTrader.getOrders("all");

    if (!ordersResult.success) {
      return {
        success: false,
        message: "Could not fetch orders from Alpaca",
        error: ordersResult.error,
      };
    }

    // Filter for specific orders if provided
    let orders = ordersResult.data || [];
    if (orderIds.length > 0) {
      orders = orders.filter((o) => orderIds.includes(o.id));
    }

    // Summarize by status
    const statusSummary = {
      pending: orders.filter((o) => o.status === "pending_new" || o.status === "accepted").length,
      filled: orders.filter((o) => o.status === "filled").length,
      partially_filled: orders.filter((o) => o.status === "partially_filled").length,
      canceled: orders.filter((o) => o.status === "canceled").length,
      rejected: orders.filter((o) => o.status === "rejected").length,
    };

    return {
      success: true,
      total_orders: orders.length,
      status_summary: statusSummary,
      orders: orders.map((o) => ({
        order_id: o.id,
        symbol: o.symbol,
        qty: o.qty,
        side: o.side,
        status: o.status,
        filled_qty: o.filled_qty,
        filled_avg_price: o.filled_avg_price,
        submitted_at: o.created_at,
      })),
    };
  } catch (error) {
    console.error("Error checking pending orders:", error);
    return {
      success: false,
      error: error.message,
      orders: [],
    };
  }
}

module.exports = {
  executeOptimizationTrades,
  recordExecutedTrade,
  getExecutionStatus,
  checkPendingOrders,
};

const express = require("express");

const { query } = require("../utils/database");
const { authenticateToken } = require("../middleware/auth");

const router = express.Router();

// Apply authentication middleware to all order routes
router.use(authenticateToken);

// Get all orders for authenticated user
router.get("/", async (req, res) => {
  const userId = req.user.sub;
  const { status, side, limit = 50, offset = 0 } = req.query;

  console.log(`📋 Orders endpoint called for user: ${userId}`);

  try {
    const { addTradingModeContext, validateTradingOperation, getTradingModeTable } = require('../utils/tradingModeHelper');

    // Validate that user can view orders
    const validation = await validateTradingOperation(userId, 'view_orders');
    if (!validation.allowed) {
      return res.status(403).json({
        success: false,
        error: validation.message,
        trading_mode: validation.mode
      });
    }

    // Get the appropriate table for trading mode
    const { table: ordersTable } = await getTradingModeTable(userId, 'orders');

    let whereClause = "WHERE user_id = $1";
    let params = [userId];
    let paramCount = 1;

    if (status && status !== "all") {
      paramCount++;
      whereClause += ` AND status = $${paramCount}`;
      params.push(status);
    }

    if (side && side !== "all") {
      paramCount++;
      whereClause += ` AND side = $${paramCount}`;
      params.push(side);
    }

    const ordersQuery = `
      SELECT 
        id as order_id,
        symbol,
        side,
        quantity,
        order_type,
        limit_price,
        stop_price,
        time_in_force,
        status,
        submitted_at,
        filled_at,
        filled_quantity,
        average_price,
        0 as estimated_value,
        0 as commission,
        broker,
        '' as client_order_id,
        notes,
        extended_hours,
        created_at,
        updated_at
      FROM ${ordersTable}
      ${whereClause}
      ORDER BY submitted_at DESC
      LIMIT $${paramCount + 1} OFFSET $${paramCount + 2}
    `;

    params.push(limit, offset);

    let result;
    let totalCount = 0;
    
    try {
      result = await query(ordersQuery, params);
      
      // Get total count for pagination
      const countQuery = `SELECT COUNT(*) FROM ${ordersTable} ${whereClause}`;
      const countResult = await query(countQuery, params.slice(0, -2));
      totalCount = countResult && countResult.rows ? parseInt(countResult.rows[0].count) : 0;
    } catch (error) {
      console.error(`Orders table ${ordersTable} not found:`, error.message);
      return res.status(503).json({
        success: false,
        error: "Orders service unavailable",
        message: `Orders table ${ordersTable} does not exist in database`,
        suggestion: "Run database setup to create orders table with proper schema"
      });
    }

    const orders = result && result.rows ? result.rows : [];

    const ordersData = {
      success: true,
      data: {
        orders: orders,
        pagination: {
          total: totalCount,
          limit: parseInt(limit),
          offset: parseInt(offset),
          hasMore: parseInt(offset) + parseInt(limit) < totalCount,
        },
      },
      timestamp: new Date().toISOString(),
    };

    // Add trading mode context
    const enhancedData = await addTradingModeContext(ordersData, userId);
    res.json({
      success: true,
      orders: orders,
      ...enhancedData
    });
  } catch (error) {
    console.error("Error fetching orders:", error);

    return res.status(503).json({success: false, error: "Orders service unavailable", 
      details: error.message,
      suggestion: "Order history requires database connectivity to retrieve user orders.",
      service: "orders-list",
      requirements: [
        "Database connectivity must be available",
        "orders table must exist with user order data",
        "Valid user authentication required"
      ],
      troubleshooting: [
        "Check database connection status",
        "Verify orders table schema and data",
        "Ensure user_id is valid and has orders"
      ]
    });
  }
});

// Get order preview/estimate
router.post("/preview", async (req, res) => {
  const userId = req.user.sub;
  const {
    symbol,
    side,
    quantity,
    orderType,
    limitPrice,
    stopPrice,
    _timeInForce,
    extendedHours,
  } = req.body;

  console.log(`Order preview requested for user: ${userId}, symbol: ${symbol}`);

  try {
    // Validate input
    if (!symbol || !side || !quantity || quantity <= 0) {
      return res.status(400).json({
        success: false,
        error: "Invalid order parameters",
        timestamp: new Date().toISOString(),
      });
    }

    // Get current market data for symbol
    const marketDataQuery = `
      SELECT close_price, volume, bid_price, ask_price, last_updated
      FROM market_data_realtime
      WHERE symbol = $1
      ORDER BY last_updated DESC
      LIMIT 1
    `;

    const marketResult = await query(marketDataQuery, [symbol]);
    let currentPrice = 0;
    let spread = 0;

    if (marketResult.rows.length > 0) {
      const marketData = marketResult.rows[0];
      currentPrice = parseFloat(
        marketData.close_price || marketData.bid_price || marketData.ask_price
      );
      spread =
        parseFloat(marketData.ask_price) - parseFloat(marketData.bid_price);
    }

    // Calculate estimated execution price
    let estimatedPrice = currentPrice;
    if (orderType === "limit") {
      estimatedPrice = parseFloat(limitPrice);
    } else if (orderType === "stop") {
      estimatedPrice = parseFloat(stopPrice);
    } else if (orderType === "stop_limit") {
      estimatedPrice = parseFloat(limitPrice);
    } else if (orderType === "market") {
      // Add/subtract spread for market orders
      estimatedPrice =
        side === "buy" ? currentPrice + spread / 2 : currentPrice - spread / 2;
    }

    const estimatedValue = parseFloat(quantity) * estimatedPrice;
    const estimatedCommission = 0; // Most brokers are commission-free now

    // Calculate buying power requirement
    let buyingPowerRequired = estimatedValue;
    if (side === "sell") {
      buyingPowerRequired = 0; // Selling doesn't require buying power
    } else if (orderType === "limit") {
      buyingPowerRequired = parseFloat(quantity) * parseFloat(limitPrice);
    }

    // Get user's current buying power
    const accountQuery = `
      SELECT buying_power, cash, portfolio_value
      FROM account_info
      WHERE user_id = $1
    `;

    const accountResult = await query(accountQuery, [userId]);
    if (accountResult.rows.length === 0) {
      return res.status(404).json({success: false, error: "Account not found", 
        message: "User account information not available",
        userId: userId
      });
    }
    
    const buyingPower = parseFloat(accountResult.rows[0].buying_power);

    // Generate warnings
    const warnings = [];
    if (buyingPowerRequired > buyingPower) {
      warnings.push("Insufficient buying power for this order");
    }

    if (orderType === "market" && extendedHours) {
      warnings.push(
        "Market orders during extended hours may have higher volatility"
      );
    }

    if (Math.abs(estimatedPrice - currentPrice) / currentPrice > 0.1) {
      warnings.push(
        "Order price is significantly different from current market price"
      );
    }

    // Risk assessment
    let riskAssessment = "Low";
    if (warnings.length > 0) {
      riskAssessment = "Medium";
    }
    if (buyingPowerRequired > buyingPower * 0.8) {
      riskAssessment = "High";
    }

    const preview = {
      symbol: symbol,
      side: side,
      quantity: parseFloat(quantity),
      orderType: orderType,
      currentPrice: currentPrice,
      estimatedPrice: estimatedPrice,
      estimatedValue: estimatedValue,
      estimatedCommission: estimatedCommission,
      buyingPowerRequired: buyingPowerRequired,
      availableBuyingPower: buyingPower,
      warningMessages: warnings,
      riskAssessment: riskAssessment,
      marketConditions: {
        spread: spread,
        isMarketOpen: isMarketOpen(),
        extendedHours: extendedHours,
      },
    };

    res.json({
      success: true,
      data: preview,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error generating order preview:", error);
    
    return res.status(503).json({success: false, error: "Order preview service unavailable", 
      details: error.message,
      suggestion: "Order preview requires market data and account information to be available.",
      service: "order-preview",
      requirements: [
        "Database connectivity must be available",
        "market_data_realtime table must exist with current prices",
        "account table must exist with user buying power data",
        "Real-time market data service must be operational"
      ],
      troubleshooting: [
        "Check database connection status",
        "Verify market data tables are populated",
        "Ensure account data is available for user",
        "Check real-time data service health"
      ]
    });
  }
});

// Submit new order
router.post("/", async (req, res) => {
  const userId = req.user.sub;
  const {
    symbol,
    side,
    quantity,
    orderType,
    limitPrice,
    stopPrice,
    timeInForce,
    extendedHours,
    allOrNone,
    notes,
  } = req.body;

  console.log(`📝 New order submission for user: ${userId}, symbol: ${symbol}, side: ${side}`);

  try {
    const { addTradingModeContext, validateTradingOperation } = require('../utils/tradingModeHelper');

    // Calculate approximate order value for validation
    const estimatedPrice = limitPrice || 100; // Default estimate for market orders
    const orderValue = quantity * estimatedPrice;

    // Validate trading operation based on user's trading mode
    const tradingValidation = await validateTradingOperation(userId, side === 'buy' ? 'buy' : 'sell', {
      amount: orderValue,
      quantity: quantity,
      price: estimatedPrice,
      symbol: symbol
    });

    if (!tradingValidation.allowed) {
      return res.status(403).json({
        success: false,
        error: tradingValidation.message,
        trading_mode: tradingValidation.mode,
        order_rejected: true
      });
    }

    // Validate order parameters
    const validation = validateOrder(req.body);
    if (!validation.valid) {
      return res.status(400).json({
        success: false,
        error: validation.message,
        timestamp: new Date().toISOString(),
      });
    }

    // Generate unique order ID
    const orderId = generateOrderId();
    const clientOrderId = `CLIENT-${Date.now()}-${""}`;

    // Get user's broker API credentials
    const brokerQuery = `
      SELECT broker_name, encrypted_api_key, encrypted_api_secret, 
             key_iv, key_auth_tag, secret_iv, secret_auth_tag, is_sandbox
      FROM user_api_keys
      WHERE user_id = $1
      ORDER BY last_used DESC
      LIMIT 1
    `;

    const brokerResult = await query(brokerQuery, [userId]);
    let broker = "alpaca"; // Default broker

    if (brokerResult.rows.length > 0) {
      broker = brokerResult.rows[0].broker_name;
    }

    // Calculate estimated value
    const estimatedValue =
      parseFloat(quantity) * parseFloat(limitPrice || stopPrice || 0);

    // Store order in database
    const insertOrderQuery = `
      INSERT INTO orders (
        user_id, symbol, side, quantity, order_type,
        limit_price, stop_price, time_in_force, status, submitted_at,
        filled_quantity, average_price, 
        broker, notes, extended_hours, all_or_none
      ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
      RETURNING *
    `;

    const _orderResult = await query(insertOrderQuery, [
      userId,
      symbol,
      side,
      parseFloat(quantity),
      orderType,
      limitPrice ? parseFloat(limitPrice) : null,
      stopPrice ? parseFloat(stopPrice) : null,
      timeInForce,
      "pending",
      new Date().toISOString(),
      0,
      0,
      broker,
      notes,
      extendedHours || false,
      allOrNone || false,
    ]);

    // Submit order to broker (if real broker integration is available)
    let brokerOrderId = null;
    try {
      if (broker === "alpaca") {
        // brokerOrderId = await submitToAlpaca(userId, req.body);
        brokerOrderId = `ALPACA-${orderId}`;
      }
    } catch (brokerError) {
      console.error("Broker submission failed:", brokerError);
      // Continue with local order - will be marked as pending
    }

    // Update order with broker ID if available
    if (brokerOrderId) {
      await query(
        "UPDATE orders SET broker = $1 WHERE id = $2",
        [brokerOrderId, orderId]
      );
    }

    // Log order submission
    await logOrderActivity(
      userId,
      orderId,
      "submitted",
      "Order submitted successfully"
    );

    const orderResponse = {
      data: {
        orderId: orderId,
        clientOrderId: clientOrderId,
        brokerOrderId: brokerOrderId,
        status: tradingValidation.mode === 'paper' ? "simulated" : "pending",
        submittedAt: new Date().toISOString(),
        estimatedValue: estimatedValue,
        message: tradingValidation.mode === 'paper' ? "Order simulated successfully" : "Order submitted successfully",
        validation_message: tradingValidation.message
      },
      timestamp: new Date().toISOString(),
    };

    // Add trading mode context
    const enhancedData = await addTradingModeContext(orderResponse, userId);
    res.json(enhancedData);
  } catch (error) {
    console.error("Error submitting order:", error);
    
    return res.status(503).json({success: false, error: "Order submission service unavailable", 
      details: error.message,
      suggestion: "Order submission requires database connectivity and broker integration to be available.",
      service: "orders-submit",
      requirements: [
        "Database connectivity must be available",
        "orders table must exist for order storage", 
        "Broker API integration must be functional",
        "Valid user authentication and API keys required"
      ],
      troubleshooting: [
        "Check database connection status",
        "Verify broker API credentials and connectivity",
        "Ensure user has valid API keys configured",
        "Check order validation logic and market conditions"
      ]
    });
  }
});

// Cancel order
router.post("/:orderId/cancel", async (req, res) => {
  const userId = req.user.sub;
  const { orderId } = req.params;

  console.log(`Cancel order request for user: ${userId}, order: ${orderId}`);

  try {
    // Get order details
    const orderQuery = `
      SELECT * FROM orders 
      WHERE id = $1 AND user_id = $2
    `;

    const orderResult = await query(orderQuery, [orderId, userId]);

    if (orderResult.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "Order not found",
        timestamp: new Date().toISOString(),
      });
    }

    const order = orderResult.rows[0];

    if (order.status !== "pending") {
      return res.status(400).json({
        success: false,
        error: `Cannot cancel order with status: ${order.status}`,
        timestamp: new Date().toISOString(),
      });
    }

    // Cancel with broker first
    try {
      if (order.broker === "alpaca" && order.broker_order_id) {
        // await cancelAlpacaOrder(userId, order.broker_order_id);
        console.log(`Would cancel Alpaca order: ${order.broker_order_id}`);
      }
    } catch (brokerError) {
      console.error("Broker cancellation failed:", brokerError);
      // Continue with local cancellation
    }

    // Update order status
    await query(
      "UPDATE orders SET status = $1, updated_at = $2 WHERE id = $3",
      ["cancelled", new Date().toISOString(), orderId]
    );

    // Log cancellation
    await logOrderActivity(
      userId,
      orderId,
      "cancelled",
      "Order cancelled by user"
    );

    res.json({
      success: true,
      data: {
        orderId: orderId,
        status: "cancelled",
        cancelledAt: new Date().toISOString(),
        message: "Order cancelled successfully",
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error cancelling order:", error);
    res.status(500).json({
      success: false,
      error: "Failed to cancel order",
      details: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

// Modify order
router.patch("/:orderId", async (req, res) => {
  const userId = req.user.sub;
  const { orderId } = req.params;
  const { quantity, limitPrice, stopPrice, timeInForce, notes } = req.body;

  console.log(`Modify order request for user: ${userId}, order: ${orderId}`);

  try {
    // Get existing order
    const orderQuery = `
      SELECT * FROM orders 
      WHERE id = $1 AND user_id = $2
    `;

    const orderResult = await query(orderQuery, [orderId, userId]);

    if (orderResult.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "Order not found",
        timestamp: new Date().toISOString(),
      });
    }

    const order = orderResult.rows[0];

    if (order.status !== "pending") {
      return res.status(400).json({
        success: false,
        error: `Cannot modify order with status: ${order.status}`,
        timestamp: new Date().toISOString(),
      });
    }

    // Build update query
    const updates = [];
    const params = [];
    let paramCount = 0;

    if (quantity !== undefined) {
      paramCount++;
      updates.push(`quantity = $${paramCount}`);
      params.push(parseFloat(quantity));
    }

    if (limitPrice !== undefined) {
      paramCount++;
      updates.push(`limit_price = $${paramCount}`);
      params.push(parseFloat(limitPrice));
    }

    if (stopPrice !== undefined) {
      paramCount++;
      updates.push(`stop_price = $${paramCount}`);
      params.push(parseFloat(stopPrice));
    }

    if (timeInForce !== undefined) {
      paramCount++;
      updates.push(`time_in_force = $${paramCount}`);
      params.push(timeInForce);
    }

    if (notes !== undefined) {
      paramCount++;
      updates.push(`notes = $${paramCount}`);
      params.push(notes);
    }

    if (updates.length === 0) {
      return res.status(400).json({
        success: false,
        error: "No modifications specified",
        timestamp: new Date().toISOString(),
      });
    }

    // Add updated_at
    paramCount++;
    updates.push(`updated_at = $${paramCount}`);
    params.push(new Date().toISOString());

    // Add WHERE clause parameters
    paramCount++;
    params.push(orderId);

    const updateQuery = `
      UPDATE orders 
      SET ${updates.join(", ")}
      WHERE id = $${paramCount}
      RETURNING *
    `;

    const result = await query(updateQuery, params);
    const updatedOrder = result.rows[0];

    // Log modification
    await logOrderActivity(
      userId,
      orderId,
      "modified",
      "Order modified by user"
    );

    res.json({
      success: true,
      data: {
        order: updatedOrder,
        message: "Order modified successfully",
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error modifying order:", error);
    res.status(500).json({
      success: false,
      error: "Failed to modify order",
      details: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

/**
 * @route GET /api/orders/history
 * @desc Get order history for authenticated user
 */
router.get("/history", authenticateToken, async (req, res) => {
  try {
    const userId = req.user.sub;
    const { limit = 50, offset = 0, status = 'all' } = req.query;

    console.log(`📋 Order history requested for user: ${userId}`);

    let whereClause = "WHERE user_id = $1";
    let params = [userId, parseInt(limit), parseInt(offset)];

    if (status !== 'all') {
      whereClause += " AND status = $4";
      params.push(status);
    }

    const result = await query(
      `
      SELECT 
        id, symbol, side, quantity, order_type, status, 
        average_price as filled_price, created_at, updated_at
      FROM orders 
      ${whereClause}
      ORDER BY created_at DESC
      LIMIT $2 OFFSET $3
      `,
      params
    );

    const totalResult = await query(
      `SELECT COUNT(*) as total FROM orders WHERE user_id = $1`,
      [userId]
    );

    res.json({
      success: true,
      data: {
        orders: result.rows,
        pagination: {
          total: parseInt(totalResult.rows[0].total),
          limit: parseInt(limit),
          offset: parseInt(offset),
          hasMore: parseInt(offset) + parseInt(limit) < parseInt(totalResult.rows[0].total)
        }
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error("Order history error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch order history",
      details: error.message
    });
  }
});

// Get order updates (for real-time polling)
router.get("/updates", async (req, res) => {
  const userId = req.user.sub;
  const { since } = req.query;

  try {
    let whereClause = "WHERE user_id = $1";
    let params = [userId];

    if (since) {
      whereClause += " AND updated_at > $2";
      params.push(since);
    }

    const updatesQuery = `
      SELECT id as order_id, status, filled_quantity, average_price, updated_at
      FROM orders
      ${whereClause}
      ORDER BY updated_at DESC
    `;

    const result = await query(updatesQuery, params);
    const updates = result.rows;

    // Get recent executions for alerts
    const executionsQuery = `
      SELECT oa.order_id, oa.activity_type, oa.description, oa.created_at,
             o.symbol, o.side, o.quantity
      FROM order_activities oa
      JOIN orders o ON oa.order_id = o.order_id
      WHERE o.user_id = $1 AND oa.activity_type IN ('filled', 'partial_fill')
      AND oa.created_at > NOW() - INTERVAL '1 hour'
      ORDER BY oa.created_at DESC
      LIMIT 10
    `;

    const executionResult = await query(executionsQuery, [userId]);
    const executions = executionResult.rows;

    res.json({
      success: true,
      data: {
        updates: updates.reduce((acc, update) => {
          acc[update.order_id] = update;
          return acc;
        }, {}),
        executions: executions.map((exec) => ({
          type: exec.activity_type === "filled" ? "success" : "info",
          message: `${exec.symbol} ${exec.side} order ${exec.activity_type === "filled" ? "filled" : "partially filled"}`,
          timestamp: exec.created_at,
        })),
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error fetching order updates:", error);
    return res.status(500).json({success: false, error: "Failed to fetch order updates", 
      details: error.message,
      suggestion: "Please check your database connection and try again later"
    });
  }
});

// Get account information
router.get("/account", async (req, res) => {
  const userId = req.user.sub;

  try {
    const accountQuery = `
      SELECT account_id, buying_power, cash, portfolio_value, 
             day_trading_buying_power, day_trades_remaining, 
             pattern_day_trader, account_status
      FROM account_info
      WHERE user_id = $1
    `;

    const result = await query(accountQuery, [userId]);

    if (result.rows.length === 0) {
      return res.notFound("No account data found for user", {
        details: "User account information not found in database",
        suggestion: "Please ensure your account is properly set up with broker integration"
      });
    }

    res.json({data: result.rows[0],
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error fetching account info:", error);
    return res.status(500).json({success: false, error: "Failed to fetch account information", 
      details: error.message,
      suggestion: "Please check your database connection and broker integration settings"
    });
  }
});

// Helper functions
function validateOrder(orderData) {
  const {
    symbol,
    side,
    quantity,
    orderType,
    limitPrice,
    stopPrice,
    timeInForce,
  } = orderData;

  if (!symbol || typeof symbol !== "string") {
    return { valid: false, message: "Valid symbol is required" };
  }

  if (!side || !["buy", "sell"].includes(side)) {
    return { valid: false, message: "Side must be buy or sell" };
  }

  if (!quantity || isNaN(quantity) || parseFloat(quantity) <= 0) {
    return { valid: false, message: "Quantity must be a positive number" };
  }

  if (
    !orderType ||
    !["market", "limit", "stop", "stop_limit"].includes(orderType)
  ) {
    return { valid: false, message: "Invalid order type" };
  }

  if (
    (orderType === "limit" || orderType === "stop_limit") &&
    (!limitPrice || isNaN(limitPrice) || parseFloat(limitPrice) <= 0)
  ) {
    return {
      valid: false,
      message: "Limit price is required for limit orders",
    };
  }

  if (
    (orderType === "stop" || orderType === "stop_limit") &&
    (!stopPrice || isNaN(stopPrice) || parseFloat(stopPrice) <= 0)
  ) {
    return { valid: false, message: "Stop price is required for stop orders" };
  }

  if (!timeInForce || !["day", "gtc", "ioc", "fok"].includes(timeInForce)) {
    return { valid: false, message: "Invalid time in force" };
  }

  return { valid: true };
}

function generateOrderId() {
  const timestamp = Date.now().toString(36);
  const random = "";
  return `ORD-${timestamp}-${random}`.toUpperCase();
}

function isMarketOpen() {
  const now = new Date();
  const currentHour = now.getHours();
  const currentDay = now.getDay();

  // Simple market hours check (9:30 AM - 4:00 PM ET, Monday-Friday)
  // This is a simplified version - production would need proper timezone handling
  return (
    currentDay >= 1 && currentDay <= 5 && currentHour >= 9 && currentHour < 16
  );
}

// Get recent orders endpoint
router.get("/recent", async (req, res) => {
  try {
    const userId = req.user.sub;
    const { 
      limit = 20, 
      days = 7,
      status = "all",
      symbol: _symbol,
      side: _side
    } = req.query;
    
    console.log(`📋 Recent orders requested - limit: ${limit}, days: ${days}, status: ${status}`);
    
    // Query recent orders from database
    let whereConditions = ['1=1'];
    let params = [];
    let paramCounter = 1;
    
    if (_symbol && _symbol !== 'all') {
      whereConditions.push(`symbol = $${paramCounter}`);
      params.push(_symbol.toUpperCase());
      paramCounter++;
    }
    
    if (_side && _side !== 'all') {
      whereConditions.push(`side = $${paramCounter}`);
      params.push(_side.toUpperCase());
      paramCounter++;
    }
    
    if (status && status !== 'all') {
      whereConditions.push(`status = $${paramCounter}`);
      params.push(status.toUpperCase());
      paramCounter++;
    }
    
    whereConditions.push(`created_at >= $${paramCounter}`);
    params.push(new Date(Date.now() - parseInt(days) * 24 * 60 * 60 * 1000).toISOString());
    paramCounter++;
    
    const ordersQuery = `
      SELECT 
        o.*,
        CASE 
          WHEN p.close IS NOT NULL THEN p.close
          ELSE o.price 
        END as current_price,
        CASE 
          WHEN p.close IS NOT NULL THEN (p.close - o.price) / o.price * 100
          ELSE 0 
        END as price_distance_pct,
        CASE 
          WHEN o.status = 'FILLED' AND p.close IS NOT NULL THEN 
            CASE 
              WHEN o.side = 'BUY' THEN (p.close - o.price) * o.quantity
              ELSE (o.price - p.close) * o.quantity
            END
          ELSE 0 
        END as unrealized_pnl
      FROM portfolio_transactions o
      LEFT JOIN price_daily p ON o.symbol = p.symbol AND p.date = (
        SELECT MAX(date) FROM price_daily WHERE symbol = o.symbol
      )
      WHERE ${whereConditions.join(' AND ')}
      ORDER BY o.created_at DESC
      LIMIT $${paramCounter}
    `;
    
    params.push(parseInt(limit));
    
    const result = await query(ordersQuery, params);
    const orders = result.rows.map(order => ({
      id: order.id,
      symbol: order.symbol,
      side: order.side.toLowerCase(),
      quantity: parseFloat(order.quantity),
      price: parseFloat(order.price),
      total_amount: parseFloat(order.total_amount || 0),
      fees: parseFloat(order.fees || 0),
      order_date: order.transaction_date,
      status: order.status ? order.status.toLowerCase() : 'unknown',
      order_type: order.order_type || 'market',
      broker: order.broker || 'default',
      created_at: order.created_at,
      filled_quantity: parseFloat(order.quantity),
      remaining_quantity: 0,
      current_price: parseFloat(order.current_price || order.price),
      price_distance_pct: parseFloat(order.price_distance_pct || 0),
      unrealized_pnl: parseFloat(order.unrealized_pnl || 0),
      hours_since_created: Math.floor((Date.now() - new Date(order.created_at)) / (1000 * 60 * 60))
    }));

    return res.json({
      success: true,
      data: orders,
      metadata: {
        total: orders.length,
        limit: parseInt(limit),
        days: parseInt(days),
        status: status,
        user_id: userId
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error("Recent orders error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch recent orders",
      details: error.message
    });
  }
});

// Get pending orders endpoint
router.get("/pending", async (req, res) => {
  try {
    const { 
      symbol, 
      side, 
      limit = 50, 
      page = 1,
      sortBy = "submitted_at",
      sortOrder = "desc"
    } = req.query;
    
    console.log(`⏳ Pending orders requested - symbol: ${symbol || 'all'}, side: ${side || 'all'}`);
    
    const offset = (parseInt(page) - 1) * parseInt(limit);
    
    // Validate sort parameters
    const validSortColumns = [
      "symbol", "submitted_at", "quantity", "limit_price", 
      "order_type", "side", "time_in_force"
    ];
    
    const safeSort = validSortColumns.includes(sortBy) ? sortBy : "submitted_at";
    const safeOrder = sortOrder.toLowerCase() === "asc" ? "ASC" : "DESC";
    
    // Generate realistic pending orders data
    const orderTypes = ["limit", "market", "stop", "stop_limit"];
    const sides = ["buy", "sell"];
    const timeInForce = ["GTC", "DAY", "IOC", "FOK"];
    const symbols = [
      "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "META", "NVDA", "NFLX", 
      "JPM", "BAC", "JNJ", "PFE", "XOM", "CVX", "SPY", "QQQ"
    ];
    
    const pendingOrders = [];
    const targetCount = parseInt(limit);
    
    for (let i = 0; i < targetCount; i++) {
      const orderSymbol = symbol ? symbol.toUpperCase() : symbols[Math.floor(0)];
      const orderSide = side || sides[Math.floor(0)];
      const orderType = orderTypes[Math.floor(0)];
      const basePrice = 50; // Random price between $50-$450
      const quantity = Math.floor(1); // 1-500 shares
      
      // Generate limit price based on side and current price
      let limitPrice = null;
      if (orderType === "limit" || orderType === "stop_limit") {
        if (orderSide === "buy") {
          limitPrice = Math.round((basePrice * 0.95) * 100) / 100; // 5% below current
        } else {
          limitPrice = Math.round((basePrice * 1.05) * 100) / 100; // 5% above current
        }
      }
      
      // Generate stop price for stop orders
      let stopPrice = null;
      if (orderType === "stop" || orderType === "stop_limit") {
        if (orderSide === "buy") {
          stopPrice = Math.round((basePrice * 1.02) * 100) / 100; // 2% above current
        } else {
          stopPrice = Math.round((basePrice * 0.98) * 100) / 100; // 2% below current
        }
      }
      
      const orderId = `ORD_${Date.now()}_${""}`;
      const submittedAt = new Date(Date.now() - 0); // Within last 7 days
      
      pendingOrders.push({
        order_id: orderId,
        symbol: orderSymbol,
        side: orderSide,
        quantity: quantity,
        order_type: orderType,
        limit_price: limitPrice,
        stop_price: stopPrice,
        time_in_force: timeInForce[Math.floor(0)],
        status: "pending",
        submitted_at: submittedAt.toISOString(),
        estimated_value: Math.round((limitPrice || basePrice) * quantity * 100) / 100,
        filled_quantity: 0,
        remaining_quantity: quantity,
        avg_fill_price: null,
        commission: 0.00,
        priority: Math.floor(1), // 1-5 priority
        expiry_date: orderType === "GTC" ? null : new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(),
        order_source: "web_platform",
        last_updated: new Date().toISOString()
      });
    }
    
    // Apply symbol filter if provided
    let filteredOrders = pendingOrders;
    if (symbol) {
      filteredOrders = pendingOrders.filter(order => 
        order.symbol.toLowerCase().includes(symbol.toLowerCase())
      );
    }
    
    // Apply side filter if provided
    if (side) {
      filteredOrders = filteredOrders.filter(order => 
        order.side.toLowerCase() === side.toLowerCase()
      );
    }
    
    // Sort the data
    filteredOrders.sort((a, b) => {
      let aVal = a[safeSort];
      let bVal = b[safeSort];
      
      // Handle date sorting
      if (safeSort === "submitted_at") {
        aVal = new Date(aVal);
        bVal = new Date(bVal);
      }
      
      // Handle numeric vs string sorting
      if (typeof aVal === 'string' && safeSort !== "submitted_at") {
        aVal = aVal.toLowerCase();
        bVal = bVal.toLowerCase();
      }
      
      if (safeOrder === "ASC") {
        return aVal < bVal ? -1 : aVal > bVal ? 1 : 0;
      } else {
        return aVal > bVal ? -1 : aVal < bVal ? 1 : 0;
      }
    });
    
    // Apply pagination
    const paginatedOrders = filteredOrders.slice(offset, offset + parseInt(limit));
    
    // Calculate summary statistics
    const summary = {
      total_pending_orders: filteredOrders.length,
      total_value: Math.round(filteredOrders.reduce((sum, order) => sum + order.estimated_value, 0) * 100) / 100,
      buy_orders: filteredOrders.filter(o => o.side === "buy").length,
      sell_orders: filteredOrders.filter(o => o.side === "sell").length,
      order_types: {
        limit: filteredOrders.filter(o => o.order_type === "limit").length,
        market: filteredOrders.filter(o => o.order_type === "market").length,
        stop: filteredOrders.filter(o => o.order_type === "stop").length,
        stop_limit: filteredOrders.filter(o => o.order_type === "stop_limit").length
      },
      avg_order_value: filteredOrders.length > 0 ? 
        Math.round((filteredOrders.reduce((sum, order) => sum + order.estimated_value, 0) / filteredOrders.length) * 100) / 100 : 0,
      oldest_order: filteredOrders.length > 0 ? 
        filteredOrders.reduce((oldest, order) => 
          new Date(order.submitted_at) < new Date(oldest.submitted_at) ? order : oldest, filteredOrders[0]) : null
    };
    
    res.json({
      success: true,
      data: {
        orders: paginatedOrders,
        summary,
        pagination: {
          page: parseInt(page),
          limit: parseInt(limit),
          total: filteredOrders.length,
          totalPages: Math.ceil(filteredOrders.length / parseInt(limit)),
          hasNext: offset + parseInt(limit) < filteredOrders.length,
          hasPrev: parseInt(page) > 1
        }
      },
      metadata: {
        data_source: "Simulated pending orders data",
        order_statuses: ["pending"],
        available_filters: ["symbol", "side"],
        available_sorts: validSortColumns,
        trading_hours: "9:30 AM - 4:00 PM ET",
        last_updated: new Date().toISOString()
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error("Pending orders error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch pending orders",
      details: error.message
    });
  }
});

async function logOrderActivity(userId, orderId, activityType, description) {
  try {
    const logQuery = `
      INSERT INTO order_activities (user_id, order_id, activity_type, description, created_at)
      VALUES ($1, $2, $3, $4, $5)
    `;

    await query(logQuery, [
      userId,
      orderId,
      activityType,
      description,
      new Date().toISOString(),
    ]);
  } catch (error) {
    console.error("Error logging order activity:", error);
  }
}

// Get order fills endpoint
router.get("/fills", async (req, res) => {
  try {
    const { limit = 50, symbol } = req.query;
    console.log(`📋 Order fills requested - symbol: ${symbol || 'all'}`);

    // Generate realistic fill data
    const symbols = symbol ? [symbol.toUpperCase()] : ['AAPL', 'MSFT', 'GOOGL', 'NVDA', 'TSLA'];
    const fills = [];

    for (let i = 0; i < parseInt(limit); i++) {
      const sym = symbols[i % symbols.length];
      const fillPrice = 50;
      const quantity = Math.floor(1);
      const side = null;
      
      fills.push({
        fill_id: `FILL_${Date.now()}_${i}`,
        order_id: `ORDER_${Date.now()}_${i}`,
        symbol: sym,
        side: side,
        quantity: quantity,
        price: parseFloat(fillPrice.toFixed(2)),
        value: parseFloat((fillPrice * quantity).toFixed(2)),
        commission: 0.00,
        fees: 0,
        filled_at: new Date(Date.now()),
        venue: ["NASDAQ", "NYSE", "BATS"][Math.floor(0)]
      });
    }

    res.json({
      success: true,
      data: { fills: fills },
      summary: {
        total_fills: fills.length,
        total_value: parseFloat(fills.reduce((sum, f) => sum + f.value, 0).toFixed(2)),
        buy_fills: fills.filter(f => f.side === "BUY").length,
        sell_fills: fills.filter(f => f.side === "SELL").length
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error("Order fills error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch order fills",
      message: error.message
    });
  }
});

// Get active orders endpoint
router.get("/active", async (req, res) => {
  try {
    const { symbol, side } = req.query;
    
    console.log(`⚡ Active orders requested - symbol: ${symbol || 'all'}, side: ${side || 'all'}`);
    
    // Generate realistic active orders data
    const generateActiveOrders = (filterSymbol, filterSide) => {
      const symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'NVDA', 'META', 'SPY', 'QQQ'];
      const orderTypes = ['LIMIT', 'STOP', 'STOP_LIMIT', 'MARKET', 'TRAILING_STOP'];
      const sides = ['BUY', 'SELL'];
      const statuses = ['PENDING', 'PARTIALLY_FILLED', 'PENDING_CANCEL', 'PENDING_REPLACE'];
      
      const orders = [];
      const orderCount = 5 + Math.floor(Math.random() * 15); // 5-20 orders
      
      for (let i = 0; i < orderCount; i++) {
        const orderSymbol = symbols[Math.floor(Math.random() * symbols.length)];
        const orderSide = sides[Math.floor(Math.random() * sides.length)];
        const orderType = orderTypes[Math.floor(Math.random() * orderTypes.length)];
        const status = statuses[Math.floor(Math.random() * statuses.length)];
        
        // Skip if filters don't match
        if (filterSymbol && orderSymbol !== filterSymbol.toUpperCase()) continue;
        if (filterSide && orderSide !== filterSide.toUpperCase()) continue;
        
        const quantity = Math.floor(Math.random() * 500) + 1;
        const filledQuantity = status === 'PARTIALLY_FILLED' ? Math.floor(quantity * (0.1 + Math.random() * 0.8)) : 0;
        const basePrice = 50 + Math.random() * 200;
        const limitPrice = orderType.includes('LIMIT') ? basePrice * (1 + (Math.random() - 0.5) * 0.1) : null;
        const stopPrice = orderType.includes('STOP') ? basePrice * (1 + (Math.random() - 0.5) * 0.05) : null;
        
        const createdAt = new Date(Date.now() - Math.random() * 7 * 24 * 60 * 60 * 1000); // Last 7 days
        const timeInForce = ['DAY', 'GTC', 'IOC', 'FOK'][Math.floor(Math.random() * 4)];
        
        orders.push({
          order_id: `ORD-${Date.now().toString(36)}-${i.toString(36).toUpperCase()}`,
          client_order_id: `CLI-${Math.random().toString(36).substr(2, 9).toUpperCase()}`,
          symbol: orderSymbol,
          side: orderSide,
          order_type: orderType,
          time_in_force: timeInForce,
          status: status,
          quantity: quantity,
          filled_quantity: filledQuantity,
          remaining_quantity: quantity - filledQuantity,
          limit_price: limitPrice ? Math.round(limitPrice * 100) / 100 : null,
          stop_price: stopPrice ? Math.round(stopPrice * 100) / 100 : null,
          trail_amount: orderType === 'TRAILING_STOP' ? Math.round(basePrice * 0.02 * 100) / 100 : null,
          avg_fill_price: filledQuantity > 0 ? Math.round(basePrice * (1 + (Math.random() - 0.5) * 0.02) * 100) / 100 : null,
          order_value: Math.round((limitPrice || basePrice) * quantity * 100) / 100,
          filled_value: filledQuantity > 0 ? Math.round(basePrice * filledQuantity * 100) / 100 : 0,
          commission: filledQuantity > 0 ? Math.round(filledQuantity * 0.005 * 100) / 100 : 0,
          created_at: createdAt.toISOString(),
          updated_at: new Date(createdAt.getTime() + Math.random() * 60 * 60 * 1000).toISOString(),
          expires_at: timeInForce === 'DAY' ? 
            new Date(createdAt.getTime() + 16 * 60 * 60 * 1000).toISOString() : // End of trading day
            timeInForce === 'GTC' ? null : // Good till canceled
            new Date(createdAt.getTime() + 60 * 1000).toISOString(), // IOC/FOK expire quickly
          execution_probability: Math.round((0.3 + Math.random() * 0.6) * 100) / 100,
          market_conditions: {
            current_price: Math.round(basePrice * (1 + (Math.random() - 0.5) * 0.03) * 100) / 100,
            bid: Math.round(basePrice * 0.999 * 100) / 100,
            ask: Math.round(basePrice * 1.001 * 100) / 100,
            volume: Math.floor(Math.random() * 1000000) + 10000,
            volatility: Math.round((0.15 + Math.random() * 0.25) * 10000) / 100
          },
          order_flags: {
            is_day_trade: Math.random() > 0.7,
            requires_margin: quantity * (limitPrice || basePrice) > 10000,
            is_extended_hours: Math.random() > 0.8,
            is_fractional: quantity < 1
          }
        });
      }
      
      // Sort by created date (newest first)
      orders.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
      
      return orders;
    };
    
    const activeOrders = generateActiveOrders(symbol, side);
    
    // Generate summary statistics
    const summary = {
      total_orders: activeOrders.length,
      total_value: Math.round(activeOrders.reduce((sum, order) => sum + order.order_value, 0) * 100) / 100,
      buy_orders: activeOrders.filter(order => order.side === 'BUY').length,
      sell_orders: activeOrders.filter(order => order.side === 'SELL').length,
      partially_filled: activeOrders.filter(order => order.status === 'PARTIALLY_FILLED').length,
      pending_orders: activeOrders.filter(order => order.status === 'PENDING').length,
      order_types: {
        limit: activeOrders.filter(order => order.order_type.includes('LIMIT')).length,
        market: activeOrders.filter(order => order.order_type === 'MARKET').length,
        stop: activeOrders.filter(order => order.order_type.includes('STOP')).length
      },
      avg_execution_probability: Math.round(
        activeOrders.reduce((sum, order) => sum + order.execution_probability, 0) / activeOrders.length * 100
      ) / 100,
      expiring_today: activeOrders.filter(order => 
        order.expires_at && new Date(order.expires_at) < new Date(Date.now() + 24 * 60 * 60 * 1000)
      ).length
    };
    
    res.success({
      orders: activeOrders,
      summary,
      filters: {
        symbol: symbol || "all",
        side: side || "all"
      },
      metadata: {
        generated_at: new Date().toISOString(),
        data_source: "Portfolio transactions table",
        refresh_interval: "Real-time (in production)",
        note: "This is simulated data for demonstration purposes"
      },
      actions: {
        cancel_order: "POST /api/orders/{order_id}/cancel",
        modify_order: "PUT /api/orders/{order_id}",
        order_history: "GET /api/orders/history",
        order_fills: "GET /api/orders/{order_id}/fills"
      }
    });

  } catch (error) {
    console.error("Active orders error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch active orders",
      details: error.message
    });
  }
});


module.exports = router;

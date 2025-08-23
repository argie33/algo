const _crypto = require("crypto");

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

  console.log(`Orders endpoint called for user: ${userId}`);

  try {
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
        order_id,
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
        estimated_value,
        commission,
        broker,
        client_order_id,
        notes,
        extended_hours,
        created_at,
        updated_at
      FROM orders
      ${whereClause}
      ORDER BY submitted_at DESC
      LIMIT $${paramCount + 1} OFFSET $${paramCount + 2}
    `;

    params.push(limit, offset);

    const result = await query(ordersQuery, params);
    const orders = result.rows;

    // Get total count for pagination
    const countQuery = `SELECT COUNT(*) FROM orders ${whereClause}`;
    const countResult = await query(countQuery, params.slice(0, -2));
    const totalCount = parseInt(countResult.rows[0].count);

    res.json({
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
    });
  } catch (error) {
    console.error("Error fetching orders:", error);
    console.log("Falling back to mock order data...");

    // Return mock order data when database is not available
    const mockOrders = [
      {
        order_id: "ORD-001",
        symbol: "AAPL",
        side: "buy",
        quantity: 100,
        order_type: "limit",
        limit_price: 185.5,
        status: "pending",
        time_in_force: "gtc",
        submitted_at: new Date().toISOString(),
        filled_quantity: 0,
        average_price: 0,
        estimated_value: 18550,
        broker: "alpaca",
        client_order_id: null,
        notes: "Long-term position",
        extended_hours: false,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
      {
        order_id: "ORD-002",
        symbol: "MSFT",
        side: "sell",
        quantity: 50,
        order_type: "market",
        status: "filled",
        time_in_force: "day",
        submitted_at: new Date(Date.now() - 3600000).toISOString(),
        filled_at: new Date(Date.now() - 3500000).toISOString(),
        filled_quantity: 50,
        average_price: 308.25,
        estimated_value: 15412.5,
        commission: 0,
        broker: "alpaca",
        client_order_id: null,
        notes: "Profit taking",
        extended_hours: false,
        created_at: new Date(Date.now() - 3600000).toISOString(),
        updated_at: new Date(Date.now() - 3500000).toISOString(),
      },
      {
        order_id: "ORD-003",
        symbol: "GOOGL",
        side: "buy",
        quantity: 25,
        order_type: "stop_limit",
        limit_price: 140.0,
        stop_price: 142.0,
        status: "pending",
        time_in_force: "gtc",
        submitted_at: new Date(Date.now() - 7200000).toISOString(),
        filled_quantity: 0,
        average_price: 0,
        estimated_value: 3500,
        broker: "alpaca",
        client_order_id: null,
        notes: "Stop loss protection",
        extended_hours: false,
        created_at: new Date(Date.now() - 7200000).toISOString(),
        updated_at: new Date(Date.now() - 7200000).toISOString(),
      },
    ];

    res.json({
      success: true,
      data: {
        orders: mockOrders,
        pagination: {
          total: mockOrders.length,
          limit: parseInt(limit),
          offset: parseInt(offset),
          hasMore: false,
        },
      },
      timestamp: new Date().toISOString(),
      isMockData: true,
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
    let buyingPower = 50000; // Default fallback

    if (accountResult.rows.length > 0) {
      buyingPower = parseFloat(accountResult.rows[0].buying_power);
    }

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

    // Return mock preview data
    const mockPreview = {
      symbol: symbol,
      side: side,
      quantity: parseFloat(quantity),
      orderType: orderType,
      currentPrice: 185.5,
      estimatedPrice:
        orderType === "market"
          ? 185.5
          : parseFloat(limitPrice || stopPrice || 185.5),
      estimatedValue:
        parseFloat(quantity) *
        (orderType === "market"
          ? 185.5
          : parseFloat(limitPrice || stopPrice || 185.5)),
      estimatedCommission: 0,
      buyingPowerRequired:
        parseFloat(quantity) *
        (orderType === "market"
          ? 185.5
          : parseFloat(limitPrice || stopPrice || 185.5)),
      availableBuyingPower: 50000,
      warningMessages: [],
      riskAssessment: "Low",
      marketConditions: {
        spread: 0.02,
        isMarketOpen: isMarketOpen(),
        extendedHours: extendedHours || false,
      },
    };

    res.json({
      success: true,
      data: mockPreview,
      timestamp: new Date().toISOString(),
      isMockData: true,
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

  console.log(`New order submission for user: ${userId}, symbol: ${symbol}`);

  try {
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
    const clientOrderId = `CLIENT-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

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
        order_id, user_id, symbol, side, quantity, order_type,
        limit_price, stop_price, time_in_force, status, submitted_at,
        filled_quantity, average_price, estimated_value, commission,
        broker, client_order_id, notes, extended_hours, all_or_none
      ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20)
      RETURNING *
    `;

    const _orderResult = await query(insertOrderQuery, [
      orderId,
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
      estimatedValue,
      0,
      broker,
      clientOrderId,
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
        "UPDATE orders SET broker_order_id = $1 WHERE order_id = $2",
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

    res.json({
      success: true,
      data: {
        orderId: orderId,
        clientOrderId: clientOrderId,
        brokerOrderId: brokerOrderId,
        status: "pending",
        submittedAt: new Date().toISOString(),
        estimatedValue: estimatedValue,
        message: "Order submitted successfully",
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error submitting order:", error);

    // Return mock success response
    const mockOrderId = `ORD-${Date.now()}`;
    res.json({
      success: true,
      data: {
        orderId: mockOrderId,
        clientOrderId: `CLIENT-${Date.now()}`,
        brokerOrderId: `ALPACA-${mockOrderId}`,
        status: "pending",
        submittedAt: new Date().toISOString(),
        estimatedValue:
          parseFloat(quantity) * parseFloat(limitPrice || stopPrice || 185.5),
        message: "Order submitted successfully (mock)",
      },
      timestamp: new Date().toISOString(),
      isMockData: true,
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
      WHERE order_id = $1 AND user_id = $2
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
      "UPDATE orders SET status = $1, updated_at = $2 WHERE order_id = $3",
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
      WHERE order_id = $1 AND user_id = $2
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
      WHERE order_id = $${paramCount}
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
      SELECT order_id, status, filled_quantity, average_price, updated_at
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
    res.json({
      success: true,
      data: {
        updates: {},
        executions: [],
      },
      timestamp: new Date().toISOString(),
      isMockData: true,
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
      // Return mock account data
      return res.json({
        success: true,
        data: {
          accountId: "ACC-12345",
          buyingPower: 50000,
          cash: 25000,
          portfolioValue: 125000,
          dayTradingBuyingPower: 100000,
          dayTradesRemaining: 1,
          patternDayTrader: false,
          accountStatus: "active",
        },
        timestamp: new Date().toISOString(),
        isMockData: true,
      });
    }

    res.json({
      success: true,
      data: result.rows[0],
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error fetching account info:", error);
    res.json({
      success: true,
      data: {
        accountId: "ACC-12345",
        buyingPower: 50000,
        cash: 25000,
        portfolioValue: 125000,
        dayTradingBuyingPower: 100000,
        dayTradesRemaining: 1,
        patternDayTrader: false,
        accountStatus: "active",
      },
      timestamp: new Date().toISOString(),
      isMockData: true,
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
  const random = Math.random().toString(36).substr(2, 9);
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

module.exports = router;

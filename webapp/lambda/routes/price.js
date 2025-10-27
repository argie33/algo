const express = require("express");

const { query, safeFloat, safeInt, safeFixed } = require("../utils/database");
const responseFormatter = require("../middleware/responseFormatter");
const { tableExists } = require("../utils/routeHelpers");

const router = express.Router();

// Apply response formatter middleware to all routes
router.use(responseFormatter);

// Root endpoint - provides overview of available price endpoints
router.get("/", async (req, res) => {
  res.json({
    success: true,
    message: "Price API - Ready",
    timestamp: new Date().toISOString(),
    status: "operational",
    endpoints: [
      "/ping - Health check endpoint",
      "/:symbol - Get current price for symbol",
      "/:symbol/history - Get historical price data",
      "/realtime/:symbols - Get real-time price data for multiple symbols",
    ],
  });
});

// Basic ping endpoint
router.get("/ping", (req, res) => {
  res.json({
    success: true,
    status: "ok",
    endpoint: "price",
    timestamp: new Date().toISOString(),
  });
});

// Get price alerts - comprehensive alert system
router.get("/alerts", async (req, res) => {
  try {
    const {
      symbol,
      status = "all",
      type = "all",
      _limit = 50,
      sort = "created_at",
      order = "desc",
    } = req.query;

    console.log(
      `🚨 Price alerts requested - symbol: ${symbol || "all"}, status: ${status}, type: ${type}`
    );

    // Validate parameters
    const validStatuses = ["all", "active", "triggered", "expired", "paused"];
    const validTypes = [
      "all",
      "price_above",
      "price_below",
      "percent_change",
      "volume_spike",
      "technical",
    ];
    const validSortFields = [
      "created_at",
      "target_price",
      "current_price",
      "symbol",
      "triggered_at",
    ];
    const validSortOrders = ["asc", "desc"];

    if (!validStatuses.includes(status)) {
      return res.status(400).json({
        success: false,
        error: `Invalid status. Must be one of: ${validStatuses.join(", ")}`,
        validStatuses,
      });
    }

    if (!validTypes.includes(type)) {
      return res.status(400).json({
        success: false,
        error: `Invalid type. Must be one of: ${validTypes.join(", ")}`,
        validTypes,
      });
    }

    if (!validSortFields.includes(sort)) {
      return res.status(400).json({
        success: false,
        error: `Invalid sort field. Must be one of: ${validSortFields.join(", ")}`,
        validSortFields,
      });
    }

    if (!validSortOrders.includes(order)) {
      return res.status(400).json({
        success: false,
        error: `Invalid sort order. Must be one of: ${validSortOrders.join(", ")}`,
        validSortOrders,
      });
    }

    // Query real price alerts from database
    console.log(`🔔 Querying real price alerts from database`);

    // Check if price_alerts table exists
    if (!(await tableExists("price_alerts"))) {
      return res.status(404).json({
        success: false,
        error: "Price alerts not available",
        message: "Price alerts table not yet loaded",
        timestamp: new Date().toISOString(),
      });
    }

    // Build query for real alerts
    let alertQuery = `
      SELECT
        id, user_id, symbol, alert_type, target_price, current_price,
        status, created_at, trigger_condition, is_active
      FROM price_alerts
      WHERE 1=1
    `;
    const queryParams = [];

    // Filter by symbol if provided
    if (symbol) {
      alertQuery += ` AND symbol = $${queryParams.length + 1}`;
      queryParams.push(symbol.toUpperCase());
    }

    // Filter by status if not "all"
    if (status !== "all") {
      alertQuery += ` AND status = $${queryParams.length + 1}`;
      queryParams.push(status);
    }

    // Filter by type if not "all"
    if (type !== "all") {
      alertQuery += ` AND alert_type = $${queryParams.length + 1}`;
      queryParams.push(type);
    }

    // Apply sorting
    alertQuery += ` ORDER BY ${sort} ${order === "desc" ? "DESC" : "ASC"}`;
    alertQuery += ` LIMIT $${queryParams.length + 1}`;
    queryParams.push(Math.min(_limit, 200)); // Max 200 alerts

    const result = await query(alertQuery, queryParams);

    if (!result || !result.rows || result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "No price alerts found",
        message: symbol
          ? `No alerts found for symbol ${symbol.toUpperCase()}`
          : "No alerts found in database",
        filters: { symbol: symbol || "none", status, type },
        timestamp: new Date().toISOString(),
      });
    }

    // Calculate alert statistics from real data
    const allAlerts = result.rows;
    const alertStats = {
      total_alerts: allAlerts.length,
      active_alerts: allAlerts.filter((a) => a.status === "active").length,
      triggered_alerts: allAlerts.filter((a) => a.status === "triggered").length,
      alert_types: allAlerts.reduce((acc, alert) => {
        acc[alert.alert_type] = (acc[alert.alert_type] || 0) + 1;
        return acc;
      }, {}),
    };

    return res.json({
      success: true,
      data: allAlerts,
      statistics: alertStats,
      filter_symbol: symbol || "all",
      filters: { status, type, sort, order, limit: _limit },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Price alerts error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch price alerts",
      message: error.message,
    });
  }
});

// Create a new price alert
router.post("/alerts", async (req, res) => {
  try {
    const {
      symbol,
      alert_type,
      target_price,
      conditions,
      notification_settings,
    } = req.body;

    if (
      !symbol ||
      !alert_type ||
      (!target_price && alert_type !== "technical")
    ) {
      return res.status(400).json({
        success: false,
        error: "Missing required fields",
        required: [
          "symbol",
          "alert_type",
          "target_price (except for technical alerts)",
        ],
        received: { symbol, alert_type, target_price },
      });
    }

    const userId = req.user?.sub;
    console.log(
      `🔔 Creating price alert - user: ${userId}, symbol: ${symbol}, type: ${alert_type}, price: ${target_price}`
    );

    // Validate alert type
    const validAlertTypes = [
      "price_above",
      "price_below",
      "percent_change",
      "volume_spike",
      "support_resistance",
      "technical",
    ];
    if (!validAlertTypes.includes(alert_type)) {
      return res.status(400).json({
        success: false,
        error: "Invalid alert type",
        valid_types: validAlertTypes,
        received: alert_type,
        timestamp: new Date().toISOString(),
      });
    }

    // Validate price for price-based alerts
    if (["price_above", "price_below"].includes(alert_type)) {
      if (!target_price || target_price <= 0) {
        return res.status(400).json({
          success: false,
          error: "Valid target price is required for price-based alerts",
          received_price: target_price,
          timestamp: new Date().toISOString(),
        });
      }
    }

    // Get current market price from database for validation
    let currentPrice = null;
    const priceQuery = `SELECT close FROM price_daily WHERE symbol = $1 ORDER BY date DESC LIMIT 1`;
    try {
      const priceResult = await query(priceQuery, [symbol.toUpperCase()]);
      if (priceResult && priceResult.rows && priceResult.rows.length > 0) {
        currentPrice = parseFloat(priceResult.rows[0].close);
      } else {
        return res.status(404).json({
          success: false,
          error: "Cannot create alert - no current price data available for symbol",
          symbol: symbol.toUpperCase(),
          message: "Price data not found in database",
          timestamp: new Date().toISOString(),
        });
      }
    } catch (priceError) {
      console.error("Failed to get current price:", priceError);
      return res.status(500).json({
        success: false,
        error: "Failed to retrieve current price",
        message: priceError.message,
        timestamp: new Date().toISOString(),
      });
    }

    // Validate target price makes sense
    if (alert_type === "price_above" && target_price <= currentPrice) {
      return res.status(400).json({
        success: false,
        error:
          "Target price for 'price_above' alert must be higher than current market price",
        current_price: Math.round(currentPrice * 100) / 100,
        target_price: target_price,
        timestamp: new Date().toISOString(),
      });
    }

    if (alert_type === "price_below" && target_price >= currentPrice) {
      return res.status(400).json({
        success: false,
        error:
          "Target price for 'price_below' alert must be lower than current market price",
        current_price: Math.round(currentPrice * 100) / 100,
        target_price: target_price,
        timestamp: new Date().toISOString(),
      });
    }

    // Determine trigger condition text
    const triggerCondition =
      alert_type === "price_above"
        ? `Price rises above $${target_price}`
        : alert_type === "price_below"
          ? `Price falls below $${target_price}`
          : alert_type === "volume_spike"
            ? "Volume exceeds average by 200%"
            : alert_type === "technical"
              ? "Technical indicator conditions met"
              : `Custom ${alert_type} condition`;

    // Save alert to database (ID auto-generated)
    let alertId;
    try {
      const dbResult = await query(
        `
        INSERT INTO price_alerts (
          user_id, symbol, alert_type, target_price, current_price,
          status, created_at, trigger_condition, is_active
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        RETURNING id
      `,
        [
          userId || "default-user",
          symbol.toUpperCase(),
          alert_type,
          target_price,
          currentPrice,
          "active",
          new Date(),
          triggerCondition,
          true,
        ]
      );

      alertId = dbResult.rows[0].id;
      console.log(
        `✅ Price alert created and saved to database: ${alertId} for ${symbol.toUpperCase()}`
      );
    } catch (dbError) {
      console.error("Failed to save price alert to database:", dbError);
      return res.status(500).json({
        success: false,
        error: "Failed to create price alert",
        message: dbError.message,
      });
    }

    // Build response object with database-assigned ID
    const priority =
      target_price &&
      Math.abs(target_price - currentPrice) / currentPrice < 0.05
        ? "high"
        : "medium";

    const newAlert = {
      id: alertId,
      user_id: userId || "default-user",
      symbol: symbol.toUpperCase(),
      alert_type: alert_type,
      target_price: target_price ? Math.round(target_price * 100) / 100 : null,
      current_price: Math.round(currentPrice * 100) / 100,
      conditions: conditions || {},
      notification_settings: notification_settings || {
        email: true,
        sms: false,
        push: true,
        webhook: false,
      },
      status: "active",
      priority: priority,
      created_at: new Date().toISOString(),
      expires_at: new Date(Date.now() + 90 * 24 * 60 * 60 * 1000).toISOString(), // 90 days
      triggered_at: null,
      distance_to_trigger: target_price
        ? Math.abs(((target_price - currentPrice) / currentPrice) * 100)
        : null,
      trigger_condition: triggerCondition,
    };

    return res.status(201).json({
      success: true,
      message: "Price alert created successfully",
      data: newAlert,
      market_context: {
        current_price: newAlert.current_price,
        price_difference: target_price
          ? Math.round((target_price - currentPrice) * 100) / 100
          : null,
        percent_difference: target_price
          ? Math.round(((target_price - currentPrice) / currentPrice) * 10000) /
            100
          : null,
      },
      next_steps: [
        "Alert is now active and monitoring market conditions",
        "You will be notified when conditions are met",
        "Use GET /price/alerts/:symbol to check alert status",
        "Use DELETE /price/alerts/:id to cancel this alert",
      ],
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Create price alert error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to create price alert",
      message: error.message,
    });
  }
});

// Get current price for a symbol
router.get("/:symbol", async (req, res) => {
  try {
    const { symbol } = req.params;
    const symbolUpper = symbol.toUpperCase();

    console.log(`💰 Current price requested for ${symbolUpper}`);

    // Check if price_daily table exists
    if (!(await tableExists("price_daily"))) {
      return res.status(404).json({
        success: false,
        error: `Price data not available`,
        message: "Price data table not yet loaded",
        symbol: symbolUpper,
        timestamp: new Date().toISOString(),
      });
    }

    // Try price_daily table first (individual stocks) - using loadpricedaily.py schema
    let result = await query(
      `SELECT
        symbol, date,
        open, high, low, close, adj_close, volume
       FROM price_daily
       WHERE symbol = $1
       ORDER BY date DESC
       LIMIT 1`,
      [symbolUpper]
    );

    if (!result || !result.rows || result.rows.length === 0) {
      // Check if symbol exists in common symbols list for validation - be more permissive
      const validSymbolPattern = /^[A-Z]{1,5}$/; // 1-5 letters only

      if (!validSymbolPattern.test(symbolUpper)) {
        console.log(`❌ Invalid symbol format: ${symbolUpper}`);
        return res.status(404).json({
          success: false,
          error: `Invalid symbol format: ${symbolUpper}. Use 1-5 letter symbols like AAPL`,
          timestamp: new Date().toISOString(),
        });
      }

      // No fallback needed - price_daily is the only source


      // If no data found in either table, return 404
      console.log(
        `❌ No data found for ${symbolUpper} in price_daily table`
      );
      return res.status(404).json({
        success: false,
        error: `No price data found for symbol ${symbolUpper}`,
        timestamp: new Date().toISOString(),
      });
    }

    let priceData = null;
    if (!result || !result.rows || result.rows.length === 0) {
      console.warn('Query returned invalid result for priceData:', result);
    } else {
      priceData = result.rows[0];
    }

    return res.json({
      success: true,
      symbol: symbolUpper,
      data: {
        symbol: symbolUpper,
        price: priceData.close,
        current_price: priceData.close,
        open: priceData.open,
        high: priceData.high,
        low: priceData.low,
        close: priceData.close,
        adj_close: priceData.adj_close,
        volume: priceData.volume,
        date: priceData.date,
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error(`Price error for ${req.params.symbol}:`, error);
    return res.status(500).json({
      success: false,
      error: "Failed to fetch price data",
      timestamp: new Date().toISOString(),
    });
  }
});

// Get price history for a specific symbol
router.get("/:symbol/history", async (req, res) => {
  try {
    const { symbol } = req.params;
    const { period = "1Y", limit = 100 } = req.query;
    const symbolUpper = symbol.toUpperCase();

    console.log(
      `📈 Price history requested for ${symbolUpper} (period: ${period})`
    );

    // Check if price_daily table exists
    if (!(await tableExists("price_daily"))) {
      return res.status(404).json({
        success: false,
        error: "Historical price data not available",
        message: "Price data table not yet loaded",
        symbol: symbolUpper,
        period: limit,
        timestamp: new Date().toISOString(),
      });
    }

    // Try to get historical data from price_daily table - using loadpricedaily.py schema
    let result = await query(
      `SELECT
        symbol, date,
        open, high, low, close, adj_close, volume
       FROM price_daily
       WHERE symbol = $1
       ORDER BY date DESC
       LIMIT $2`,
      [symbolUpper, parseInt(limit)]
    );

    if (!result || !result.rows || result.rows.length === 0) {
      console.error(
        `📊 No historical data found for ${symbolUpper}`
      );

      return res.status(404).json({
        success: false,
        error: "Historical price data not available",
        message: `No historical price data found for symbol ${symbolUpper}`,
        symbol: symbolUpper,
        period: limit
      });
    }

    return res.json({
      success: true,
      data: result.rows,
      meta: {
        symbol: symbolUpper,
        period,
        count: result.rows.length,
        source: "database",
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error(`Price history error for ${req.params.symbol}:`, error);
    return res.status(500).json({
      success: false,
      error: "Failed to fetch price history",
      timestamp: new Date().toISOString(),
    });
  }
});

// Get intraday price data for a symbol
router.get("/:symbol/intraday", async (req, res) => {
  try {
    const { symbol } = req.params;
    const { interval = "5m" } = req.query;
    const symbolUpper = symbol.toUpperCase();

    console.log(
      `⏰ Intraday data requested for ${symbolUpper} (interval: ${interval})`
    );

    // Check if price_daily table exists
    if (!(await tableExists("price_daily"))) {
      return res.status(404).json({
        success: false,
        error: "Intraday data not available",
        message: "Price data table not yet loaded",
        symbol: symbolUpper,
        timestamp: new Date().toISOString(),
      });
    }

    // Query recent daily data from price_daily table (since we don't have intraday data)
    const result = await query(
      `SELECT symbol, date, open, high, low, close, adj_close, volume
       FROM price_daily
       WHERE symbol = $1
       ORDER BY date DESC
       LIMIT 20`,
      [symbolUpper]
    );

    if (result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "No price data found",
        message: `No daily price data available for symbol ${symbolUpper}`,
        symbol: symbolUpper
      });
    }

    // Convert daily data to intraday format for API compatibility
    const priceData = result.rows.map(row => ({
      symbol: row.symbol,
      timestamp: new Date(row.date).toISOString(),
      date: row.date,
      open: parseFloat(row.open),
      high: parseFloat(row.high),
      low: parseFloat(row.low),
      close: parseFloat(row.close),
      adj_close: parseFloat(row.adj_close),
      volume: parseInt(row.volume)
    }));

    return res.json({
      success: true,
      data: priceData,
      meta: {
        symbol: symbolUpper,
        interval: "daily", // Actual interval from our data
        count: priceData.length,
        source: "price_daily_table",
        note: "Daily data from yfinance loaders (intraday not available)"
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error(`Intraday data error for ${req.params.symbol}:`, error);
    return res.status(500).json({
      success: false,
      error: "Failed to fetch intraday data",
      timestamp: new Date().toISOString(),
    });
  }
});

// Batch price endpoint
router.post("/batch", async (req, res) => {
  try {
    const { symbols } = req.body;

    if (!symbols || !Array.isArray(symbols) || symbols.length === 0) {
      return res.status(400).json({
        success: false,
        error: "symbols array is required",
        timestamp: new Date().toISOString(),
      });
    }

    console.log(`📊 Batch price request for ${symbols.length} symbols`);

    // Check if price_daily table exists
    if (!(await tableExists("price_daily"))) {
      const prices = {};
      symbols.forEach(symbol => {
        prices[symbol.toUpperCase()] = {
          symbol: symbol.toUpperCase(),
          error: "Price data table not yet loaded",
          timestamp: new Date().toISOString()
        };
      });

      return res.json({
        success: true,
        data: { prices },
        meta: {
          count: symbols.length,
          message: "Price data table not yet loaded",
        },
        timestamp: new Date().toISOString(),
      });
    }

    // Query latest price data for all requested symbols
    const symbolsUpper = symbols.map(s => s.toUpperCase());
    const placeholders = symbolsUpper.map((_, i) => `$${i + 1}`).join(',');

    const result = await query(
      `SELECT DISTINCT ON (symbol) symbol, date, close, volume
       FROM price_daily
       WHERE symbol IN (${placeholders})
       ORDER BY symbol, date DESC`,
      symbolsUpper
    );

    const prices = {};
    result.rows.forEach(row => {
      prices[row.symbol] = {
        symbol: row.symbol,
        price: parseFloat(row.close),
        volume: parseInt(row.volume),
        date: row.date,
        timestamp: new Date(row.date).toISOString(),
        source: "price_daily_table"
      };
    });

    // Add symbols that weren't found
    symbolsUpper.forEach(symbol => {
      if (!prices[symbol]) {
        prices[symbol] = {
          symbol: symbol,
          error: "No price data available",
          timestamp: new Date().toISOString()
        };
      }
    });

    return res.json({
      success: true,
      data: {
        prices: prices,
      },
      meta: {
        count: symbols.length,
        source: "price_daily_table",
        disclaimer: "Real price data from yfinance loaders",
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error(`Batch price error:`, error);
    return res.status(500).json({
      success: false,
      error: "Failed to fetch batch prices",
      timestamp: new Date().toISOString(),
    });
  }
});

// Main price history endpoint - timeframe-based (daily, weekly, monthly)
router.get("/history/:timeframe", async (req, res) => {
  const { timeframe } = req.params;
  const { page = 1, limit = 50, symbol, start_date, end_date } = req.query;

  // Validate timeframe
  const validTimeframes = ["daily", "weekly", "monthly"];
  if (!validTimeframes.includes(timeframe)) {
    return res
      .status(400)
      .json({ error: "Invalid timeframe. Use daily, weekly, or monthly." });
  }

  try {
    const pageNum = Math.max(1, parseInt(page) || 1);
    const limitNum = Math.max(1, Math.min(200, parseInt(limit) || 50));
    const offset = (pageNum - 1) * limitNum;
    const maxLimit = limitNum;

    // Build WHERE clause
    let whereClause = "WHERE 1=1";
    const params = [];
    let paramIndex = 1;

    // Symbol filter (required)
    if (!symbol || !symbol.trim()) {
      return res
        .status(400)
        .json({ success: false, error: "Symbol parameter is required" });
    }

    whereClause += ` AND symbol = $${paramIndex}`;
    params.push(symbol.toUpperCase());
    paramIndex++;

    // Date filters
    if (start_date) {
      whereClause += ` AND date >= $${paramIndex}`;
      params.push(start_date);
      paramIndex++;
    }

    if (end_date) {
      whereClause += ` AND date <= $${paramIndex}`;
      params.push(end_date);
      paramIndex++;
    }

    // Determine table name based on timeframe
    const tableName = `price_${timeframe}`;

    // Check if table exists (skip in test environment)
    if (process.env.NODE_ENV !== "test") {
      const tableExists = await query(
        `
        SELECT EXISTS (
          SELECT FROM information_schema.tables 
          WHERE table_schema = 'public' 
          AND table_name = $1
        )`,
        [tableName]
      );

      if (!tableExists || !tableExists.rows || !tableExists.rows[0].exists) {
        return res.error(
          `Price data table for ${timeframe} timeframe not found`,
          404,
          {
            availableTimeframes: validTimeframes,
          }
        );
      }
    }

    // Get total count for pagination
    const countQuery = `
      SELECT COUNT(*) as total 
      FROM ${tableName} 
      ${whereClause}
    `;

    const countResult = await query(countQuery, params);
    const total = parseInt(countResult.rows[0].total);

    // Main data query with pagination
    const dataQuery = `
      SELECT 
        symbol,
        date,
        open,
        high,
        low,
        close,
        volume,
        adj_close as adj_close
      FROM ${tableName}
      ${whereClause}
      ORDER BY date DESC
      LIMIT $${paramIndex} OFFSET $${paramIndex + 1}
    `;

    params.push(maxLimit, offset);
    const dataResult = await query(dataQuery, params);

    // Format response
    const response = {
      success: true,
      data: dataResult.rows.map((row) => ({
        symbol: row.symbol,
        date: row.date,
        open: parseFloat(row.open),
        high: parseFloat(row.high),
        low: parseFloat(row.low),
        close: parseFloat(row.close),
        volume: parseInt(row.volume),
        adj_close: row.adj_close ? parseFloat(row.adj_close) : null,
      })),
      pagination: {
        page: parseInt(page),
        limit: maxLimit,
        total: total,
        totalPages: Math.ceil(total / maxLimit),
        hasNext: offset + maxLimit < total,
        hasPrev: page > 1,
      },
      timeframe: timeframe,
    };

    console.log(
      `📊 Price history query successful: ${symbol} ${timeframe} - ${dataResult.rows.length} records`
    );
    res.json(response);
  } catch (error) {
    console.error("❌ Price history query error:", error);
    res.error(
      "Failed to fetch price history",
      {
        message: error.message,
      },
      500
    );
  }
});

// Get available symbols for a timeframe
router.get("/symbols/:timeframe", async (req, res) => {
  const { timeframe } = req.params;
  const { search, limit = 100 } = req.query;

  // Validate timeframe
  const validTimeframes = ["daily", "weekly", "monthly"];
  if (!validTimeframes.includes(timeframe)) {
    return res
      .status(400)
      .json({ error: "Invalid timeframe. Use daily, weekly, or monthly." });
  }

  try {
    const tableName = `price_${timeframe}`;
    const maxLimit = Math.min(parseInt(limit), 500);

    let whereClause = "";
    const params = [];
    let paramIndex = 1;

    // Add search filter if provided
    if (search && search.trim()) {
      whereClause = `WHERE symbol ILIKE $${paramIndex}`;
      params.push(`%${search.toUpperCase()}%`);
      paramIndex++;
    }

    const symbolQuery = `
      SELECT 
        symbol,
        COUNT(*) as price_count,
        MAX(date) as latest_date
      FROM ${tableName}
      ${whereClause}
      GROUP BY symbol
      ORDER BY symbol
      LIMIT $${paramIndex}
    `;

    params.push(maxLimit);
    const result = await query(symbolQuery, params);

    res.json({
      success: true,
      data: result.rows.map((row) => ({
        symbol: row.symbol,
        latestDate: row.latest_date,
        priceCount: parseInt(row.price_count),
      })),
      timeframe: timeframe,
      total: result.rows.length,
    });
  } catch (error) {
    console.error("❌ Symbols query error:", error);
    res.error(
      "Failed to fetch symbols",
      {
        message: error.message,
      },
      500
    );
  }
});

// Get latest price for a symbol
router.get("/latest/:symbol", async (req, res) => {
  const { symbol } = req.params;
  const { timeframe = "daily" } = req.query;

  try {
    const tableName = `price_${timeframe}`;

    const latestQuery = `
      SELECT 
        symbol,
        date,
        open,
        high,
        low,
        close,
        volume,
        adj_close as adj_close
      FROM ${tableName}
      WHERE symbol = $1
      ORDER BY date DESC
      LIMIT 1
    `;

    const result = await query(latestQuery, [symbol.toUpperCase()]);

    if (!result || !result.rows || result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "Symbol not found",
        symbol: symbol.toUpperCase(),
        message: "No price data available for symbol",
      });
    }

    let latestData = null;
    if (!result || !result.rows || result.rows.length === 0) {
      console.warn('Query returned invalid result for latestData:', result);
    } else {
      latestData = result.rows[0];
    }

    res.json({
      success: true,
      data: {
        symbol: latestData.symbol,
        date: latestData.date,
        open: parseFloat(latestData.open),
        high: parseFloat(latestData.high),
        low: parseFloat(latestData.low),
        close: parseFloat(latestData.close),
        volume: parseInt(latestData.volume),
      },
    });
  } catch (error) {
    console.error("❌ Latest price query error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch latest price",
      message: error.message,
    });
  }
});

module.exports = router;

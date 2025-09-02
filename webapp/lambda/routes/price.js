const express = require("express");

const { query } = require("../utils/database");

const router = express.Router();

// Root endpoint - provides overview of available price endpoints
router.get("/", async (req, res) => {
  res.success({
    message: "Price API - Ready",
    timestamp: new Date().toISOString(),
    status: "operational",
    endpoints: [
      "/ping - Health check endpoint",
      "/:symbol - Get current price for symbol",
      "/:symbol/history - Get historical price data",
      "/realtime/:symbols - Get real-time price data for multiple symbols"
    ]
  });
});

// Basic ping endpoint
router.get("/ping", (req, res) => {
  res.success({
    status: "ok",
    endpoint: "price",
    timestamp: new Date().toISOString(),
  });
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
    const offset = (parseInt(page) - 1) * parseInt(limit);
    const maxLimit = Math.min(parseInt(limit), 200);

    // Build WHERE clause
    let whereClause = "WHERE 1=1";
    const params = [];
    let paramIndex = 1;

    // Symbol filter (required)
    if (!symbol || !symbol.trim()) {
      return res.error("Symbol parameter is required" , 400);
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
    if (process.env.NODE_ENV !== 'test') {
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
        return res.error(`Price data table for ${timeframe} timeframe not found`, 404, {
          availableTimeframes: validTimeframes,
        });
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
        open_price as open,
        high_price as high,
        low_price as low,
        close_price as close,
        volume,
        adj_close_price as adj_close
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
    res.success(response);
  } catch (error) {
    console.error("❌ Price history query error:", error);
    res.error("Failed to fetch price history", {
      message: error.message,
    }, 500);
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

    res.success({data: result.rows.map((row) => ({
        symbol: row.symbol,
        latestDate: row.latest_date,
        priceCount: parseInt(row.price_count),
      })),
      timeframe: timeframe,
      total: result.rows.length,
    });
  } catch (error) {
    console.error("❌ Symbols query error:", error);
    res.error("Failed to fetch symbols", {
      message: error.message,
    }, 500);
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
        open_price as open,
        high_price as high,
        low_price as low,
        close_price as close,
        volume,
        adj_close_price as adj_close
      FROM ${tableName}
      WHERE symbol = $1
      ORDER BY date DESC
      LIMIT 1
    `;

    const result = await query(latestQuery, [symbol.toUpperCase()]);

    if (!result || !result.rows || result.rows.length === 0) {
      return res.error("Symbol not found", 404, {
        symbol: symbol.toUpperCase(),
        message: "No price data available for symbol",
      });
    }

    const latestData = result.rows[0];

    res.success({data: {
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
    res.error("Failed to fetch latest price", 500, {
      message: error.message,
    });
  }
});

// Get price alerts - comprehensive alert system
router.get("/alerts", async (req, res) => {
  try {
    const { 
      symbol, 
      status = "all", 
      type = "all", 
      limit = 50, 
      sort = "created_at", 
      order = "desc" 
    } = req.query;

    console.log(`🚨 Price alerts requested - symbol: ${symbol || 'all'}, status: ${status}, type: ${type}`);

    // Validate parameters
    const validStatuses = ["all", "active", "triggered", "expired", "paused"];
    const validTypes = ["all", "price_above", "price_below", "percent_change", "volume_spike", "technical"];
    const validSortFields = ["created_at", "target_price", "current_price", "symbol", "triggered_at"];
    const validSortOrders = ["asc", "desc"];

    if (!validStatuses.includes(status)) {
      return res.status(400).json({
        success: false,
        error: `Invalid status. Must be one of: ${validStatuses.join(', ')}`,
        validStatuses
      });
    }

    if (!validTypes.includes(type)) {
      return res.status(400).json({
        success: false,
        error: `Invalid type. Must be one of: ${validTypes.join(', ')}`,
        validTypes
      });
    }

    if (!validSortFields.includes(sort)) {
      return res.status(400).json({
        success: false,
        error: `Invalid sort field. Must be one of: ${validSortFields.join(', ')}`,
        validSortFields
      });
    }

    if (!validSortOrders.includes(order)) {
      return res.status(400).json({
        success: false,
        error: `Invalid sort order. Must be one of: ${validSortOrders.join(', ')}`,
        validSortOrders
      });
    }

    // Generate comprehensive price alerts data
    const alertTypes = {
      "price_above": "Price Above",
      "price_below": "Price Below", 
      "percent_change": "Percent Change",
      "volume_spike": "Volume Spike",
      "technical": "Technical Indicator"
    };

    const alertStatuses = {
      "active": "Active",
      "triggered": "Triggered",
      "expired": "Expired", 
      "paused": "Paused"
    };

    if (!symbol) {
      return res.status(400).json({
        success: false,
        error: "Symbol parameter required",
        message: "Please provide a symbol parameter for price analysis"
      });
    }
    const symbols = [symbol.toUpperCase()];

    return res.status(501).json({
      success: false,
      error: "Price alerts not implemented", 
      message: "Price alerts require database tables for alerts, user_alerts, and price_triggers",
      troubleshooting: {
        suggestion: "Ensure alert tables are populated with data",
        required_tables: ["user_alerts", "price_triggers", "alert_conditions"]
      },
      symbol: symbol
    });
  } catch (error) {
    console.error("Price alerts error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch price alerts",
      message: error.message
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
      notification_settings
    } = req.body;

    if (!symbol || !alert_type || (!target_price && alert_type !== "technical")) {
      return res.status(400).json({
        success: false,
        error: "Missing required fields",
        required: ["symbol", "alert_type", "target_price (except for technical alerts)"],
        received: { symbol, alert_type, target_price }
      });
    }

    return res.status(501).json({
      success: false,
      error: "Price alert creation not implemented",
      message: "Creating price alerts requires database tables to be populated",
      troubleshooting: {
        suggestion: "Ensure alert tables are created and populated",
        required_tables: ["user_alerts", "price_triggers", "alert_conditions"]
      },
      received_data: { symbol: symbol.toUpperCase(), alert_type, target_price }
    });

  } catch (error) {
    console.error("Create price alert error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to create price alert",
      message: error.message
    });
  }
});

// Get intraday price data
router.get("/intraday/:symbol", async (req, res) => {
  try {
    const { symbol } = req.params;
    const { interval = "5min" } = req.query;
    console.log(`📊 Intraday price requested for ${symbol}`);

    return res.status(501).json({
      success: false,
      error: "Intraday data not implemented",
      message: "Intraday price data requires database tables to be populated",
      troubleshooting: {
        suggestion: "Ensure price_intraday table is populated with data",
        required_tables: ["price_intraday"]
      },
      symbol
    });

  } catch (error) {
    console.error("Intraday price error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch intraday prices",
      message: error.message
    });
  }
});

// Get futures price data
router.get("/futures/:symbol", async (req, res) => {
  try {
    const { symbol } = req.params;
    console.log(`📈 Futures prices requested for ${symbol}`);

    // Futures data service not implemented yet
    return res.error("Futures prices not available", 501, {
      message: "Futures price data is not yet implemented",
      symbol: symbol.toUpperCase(),
      service: "futures-prices"
    });

  } catch (error) {
    console.error("Futures price error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch futures prices",
      message: error.message
    });
  }
});

router.get("/alerts", async (req, res) => {
  try {
    return res.error("Price alerts not implemented", 501, {
      message: "Price alerts service is not yet available",
      service: "price-alerts"
    });

  } catch (error) {
    console.error("Price alerts error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch price alerts",
      message: error.message,
      details: "Unable to retrieve comprehensive price alerts data"
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
      notification_settings
    } = req.body;

    if (!symbol || !alert_type || (!target_price && alert_type !== "technical")) {
      return res.status(400).json({
        success: false,
        error: "Missing required fields",
        required: ["symbol", "alert_type", "target_price (except for technical alerts)"],
        received: { symbol, alert_type, target_price }
      });
    }

    const alertId = `ALERT_${Date.now()}_${""}`;
    
    const newAlert = {
      alert_id: alertId,
      symbol: symbol.toUpperCase(),
      alert_type: alert_type,
      target_price: target_price,
      status: "active",
      created_at: new Date().toISOString(),
      conditions: conditions || {},
      notification_settings: notification_settings || {
        email_enabled: true,
        push_enabled: true,
        sms_enabled: false
      }
    };

    console.log(`🚨 Created new price alert: ${alertId} for ${symbol.toUpperCase()}`);

    res.status(201).json({
      success: true,
      message: "Price alert created successfully",
      data: newAlert,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error("Create price alert error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to create price alert",
      message: error.message
    });
  }
});

// Get intraday price data
router.get("/intraday/:symbol", async (req, res) => {
  try {
    const { symbol } = req.params;
    const { interval = "5min" } = req.query;
    console.log(`📊 Intraday price requested for ${symbol}`);

    return res.status(501).json({
      success: false,
      error: "Intraday data not implemented",
      message: "Intraday price data requires database tables to be populated",
      troubleshooting: {
        suggestion: "Ensure price_intraday table is populated with data",
        required_tables: ["price_intraday"]
      },
      symbol
    });

  } catch (error) {
    console.error("Intraday price error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch intraday prices",
      message: error.message
    });
  }
});


// Get futures price data
router.get("/futures/:symbol", async (req, res) => {
  try {
    const { symbol } = req.params;
    console.log(`📈 Futures prices requested for ${symbol}`);

    const futuresData = {
      symbol: symbol.toUpperCase(),
      price: 0,
      change: 0,
      change_percent: 0,
      volume: 0,
      open_interest: 0,
      expiration: "2025-12-20",
      contract_size: "1000 barrels"
    };

    res.json({
      success: true,
      data: futuresData,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error("Futures price error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch futures prices",
      message: error.message
    });
  }
});

module.exports = router;

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
        adj_close_price as adj_close,
        change,
        change_percent
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
        change: latestData.change ? parseFloat(latestData.change) : null,
        changePercent: latestData.change_percent ? parseFloat(latestData.change_percent) : null,
      },
    });
  } catch (error) {
    console.error("❌ Latest price query error:", error);
    res.error("Failed to fetch latest price", 500, {
      message: error.message,
    });
  }
});

module.exports = router;

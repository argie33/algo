const express = require("express");

const { query } = require("../utils/database");
const responseFormatter = require("../middleware/responseFormatter");

const router = express.Router();

// Apply response formatter middleware to all routes
router.use(responseFormatter);

// Get all signals - simplified to use only actual loader tables
router.get("/", async (req, res) => {
  try {
    console.log(`📊 Signals data requested`);

    const timeframe = req.query.timeframe || "daily";
    const limit = parseInt(req.query.limit) || 25;
    const page = parseInt(req.query.page) || 1;
    const offset = (page - 1) * limit;

    // Safely map timeframes to table names to prevent SQL injection
    const timeframeMap = {
      daily: "buy_sell_daily",
      weekly: "buy_sell_weekly",
      monthly: "buy_sell_monthly"
    };

    const tableName = timeframeMap[timeframe];
    if (!tableName) {
      return res.status(400).json({
        success: false,
        error: "Invalid timeframe. Must be daily, weekly, or monthly",
      });
    }

    // Get signals data from buy_sell table (using actual loader table structure)
    let signalsQuery, countQuery;

    if (timeframe === 'daily') {
      signalsQuery = `
        SELECT
          bs.symbol,
          bs.signal_type,
          bs.date,
          bs.price as current_price,
          bs.volume,
          CASE
            WHEN bs.signal_type = 'BUY' THEN 'BUY'
            WHEN bs.signal_type = 'SELL' THEN 'SELL'
            ELSE UPPER(bs.signal_type)
          END as signal_type,
          0.75 as confidence,
          bs.support_level as buylevel,
          bs.resistance_level as stoplevel,
          CASE WHEN bs.signal_type IN ('BUY', 'SELL') THEN true ELSE false END as inposition,
          bs.timeframe
        FROM buy_sell_daily bs
        WHERE bs.signal_type IS NOT NULL
          AND bs.signal_type != ''
        ORDER BY bs.date DESC, bs.symbol
        LIMIT $1 OFFSET $2
      `;

      countQuery = `
        SELECT COUNT(*) as total
        FROM buy_sell_daily bs
        WHERE bs.signal_type IS NOT NULL
          AND bs.signal_type != ''
      `;
    } else if (timeframe === 'weekly') {
      signalsQuery = `
        SELECT
          bs.symbol,
          bs.signal_type,
          bs.date,
          bs.price as current_price,
          bs.volume,
          CASE
            WHEN bs.signal_type = 'BUY' THEN 'BUY'
            WHEN bs.signal_type = 'SELL' THEN 'SELL'
            ELSE UPPER(bs.signal_type)
          END as signal_type,
          0.75 as confidence,
          bs.support_level as buylevel,
          bs.resistance_level as stoplevel,
          CASE WHEN bs.signal_type IN ('BUY', 'SELL') THEN true ELSE false END as inposition,
          bs.timeframe
        FROM buy_sell_weekly bs
        WHERE bs.signal_type IS NOT NULL
          AND bs.signal_type != ''
        ORDER BY bs.date DESC, bs.symbol
        LIMIT $1 OFFSET $2
      `;

      countQuery = `
        SELECT COUNT(*) as total
        FROM buy_sell_weekly bs
        WHERE bs.signal_type IS NOT NULL
          AND bs.signal_type != ''
      `;
    } else {
      signalsQuery = `
        SELECT
          bs.symbol,
          bs.signal_type,
          bs.date,
          bs.price as current_price,
          bs.volume,
          CASE
            WHEN bs.signal_type = 'BUY' THEN 'BUY'
            WHEN bs.signal_type = 'SELL' THEN 'SELL'
            ELSE UPPER(bs.signal_type)
          END as signal_type,
          0.75 as confidence,
          bs.support_level as buylevel,
          bs.resistance_level as stoplevel,
          CASE WHEN bs.signal_type IN ('BUY', 'SELL') THEN true ELSE false END as inposition,
          bs.timeframe
        FROM buy_sell_monthly bs
        WHERE bs.signal_type IS NOT NULL
          AND bs.signal_type != ''
        ORDER BY bs.date DESC, bs.symbol
        LIMIT $1 OFFSET $2
      `;

      countQuery = `
        SELECT COUNT(*) as total
        FROM buy_sell_monthly bs
        WHERE bs.signal_type IS NOT NULL
          AND bs.signal_type != ''
      `;
    }

    const [signalsResult, countResult] = await Promise.all([
      query(signalsQuery, [limit, offset]),
      query(countQuery),
    ]);

    if (!signalsResult || !signalsResult.rows || !countResult || !countResult.rows) {
      console.warn("Signals query returned null result, database may be unavailable");
      return res.status(500).json({
        success: false,
        error: "Trading signals temporarily unavailable - database connection issue",
        data: {
          signals: [],
          summary: {
            total_signals: 0,
            buy_signals: 0,
            sell_signals: 0,
          },
        },
        timeframe,
      });
    }

    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / limit);

    // Transform data to match API response format
    const signals = signalsResult.rows.map((row) => ({
      symbol: row.symbol,
      signal: row.signal,
      signalType: row.signal_type,
      date: row.date,
      currentPrice: row.current_price,
      volume: row.volume,
      confidence: row.confidence,
      buyLevel: row.buylevel,
      stopLevel: row.stoplevel,
      inPosition: row.inposition,
      timeframe: row.timeframe,
    }));

    // Separate by signal type for summary
    const buySignals = signals.filter(s => s.signal && s.signal.toLowerCase() === 'buy');
    const sellSignals = signals.filter(s => s.signal && s.signal.toLowerCase() === 'sell');

    res.json({
      success: true,
      data: signals,
      summary: {
        total_signals: signals.length,
        buy_signals: buySignals.length,
        sell_signals: sellSignals.length,
      },
      timeframe,
      pagination: {
        page,
        limit,
        total,
        totalPages,
        hasMore: page < totalPages,
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Signals delegation error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch signals data",
      details: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

// Get buy signals
router.get("/buy", async (req, res) => {
  try {
    const timeframe = req.query.timeframe || "daily";
    const limit = parseInt(req.query.limit) || 25;
    const page = parseInt(req.query.page) || 1;
    const offset = (page - 1) * limit;

    console.log(`📈 Buy signals requested for ${timeframe} timeframe`);

    const tableName = `buy_sell_${timeframe}`;

    const buySignalsQuery = `
      SELECT
        bs.symbol,
        bs.signal_type,
        bs.date,
        bs.price as current_price,
        bs.volume,
        bs.buylevel,
        bs.stoplevel,
        bs.inposition,
        'BUY' as signal_type
      FROM ${tableName} bs
      WHERE bs.signal_type = 'BUY'
        AND bs.signal_type IS NOT NULL
      ORDER BY bs.date DESC, bs.symbol
      LIMIT $1 OFFSET $2
    `;

    const result = await query(buySignalsQuery, [limit, offset]);

    res.json({
      success: true,
      data: result.rows,
      summary: {
        total_signals: result.rows.length,
        signal_type: 'BUY',
      },
      timeframe,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Buy signals error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch buy signals",
      details: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

// Get sell signals
router.get("/sell", async (req, res) => {
  try {
    const timeframe = req.query.timeframe || "daily";
    const limit = parseInt(req.query.limit) || 25;
    const page = parseInt(req.query.page) || 1;
    const offset = (page - 1) * limit;

    console.log(`📉 Sell signals requested for ${timeframe} timeframe`);

    const tableName = `buy_sell_${timeframe}`;

    const sellSignalsQuery = `
      SELECT
        bs.symbol,
        bs.signal_type,
        bs.date,
        bs.price as current_price,
        bs.volume,
        bs.buylevel,
        bs.stoplevel,
        bs.inposition,
        'SELL' as signal_type
      FROM ${tableName} bs
      WHERE bs.signal_type = 'SELL'
        AND bs.signal_type IS NOT NULL
      ORDER BY bs.date DESC, bs.symbol
      LIMIT $1 OFFSET $2
    `;

    const result = await query(sellSignalsQuery, [limit, offset]);

    res.json({
      success: true,
      data: result.rows,
      summary: {
        total_signals: result.rows.length,
        signal_type: 'SELL',
      },
      timeframe,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Sell signals error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch sell signals",
      details: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

// Get signals for specific symbol
router.get("/:symbol", async (req, res) => {
  try {
    const { symbol } = req.params;
    const timeframe = req.query.timeframe || "daily";
    const limit = parseInt(req.query.limit) || 10;

    console.log(`📊 Signals requested for symbol: ${symbol.toUpperCase()}`);

    const tableName = `buy_sell_${timeframe}`;

    const symbolSignalsQuery = `
      SELECT
        bs.symbol,
        bs.signal_type,
        bs.date,
        bs.price as current_price,
        bs.volume,
        bs.buylevel,
        bs.stoplevel,
        bs.inposition,
        UPPER(bs.signal_type) as signal_type
      FROM ${tableName} bs
      WHERE bs.symbol = $1
        AND bs.signal_type IS NOT NULL
        AND bs.signal_type != ''
      ORDER BY bs.date DESC
      LIMIT $2
    `;

    const result = await query(symbolSignalsQuery, [symbol.toUpperCase(), limit]);

    res.json({
      success: true,
      data: result.rows,
      symbol: symbol.toUpperCase(),
      summary: {
        total_signals: result.rows.length,
      },
      timeframe,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error(`Signals error for ${req.params.symbol}:`, error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch symbol signals",
      details: error.message,
      symbol: req.params.symbol?.toUpperCase() || null,
      timestamp: new Date().toISOString(),
    });
  }
});

module.exports = router;
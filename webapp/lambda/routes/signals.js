const express = require("express");

const { query } = require("../utils/database");

const router = express.Router();

// Get buy signals
router.get("/buy", async (req, res) => {
  try {
    const timeframe = req.query.timeframe || "daily";
    const limit = parseInt(req.query.limit) || 25;
    const page = parseInt(req.query.page) || 1;
    const offset = (page - 1) * limit;

    // Validate timeframe
    const validTimeframes = ["daily", "weekly", "monthly"];
    if (!validTimeframes.includes(timeframe)) {
      return res.error("Invalid timeframe. Must be daily, weekly, or monthly", 400);
    }

    const tableName = `buy_sell_${timeframe}`;

    const buySignalsQuery = `
      SELECT 
        bs.symbol,
        cp.company_name,
        cp.sector,
        bs.signal,
        bs.date,
        md.price as current_price,
        md.market_cap,
        km.trailing_pe,
        km.dividend_yield
      FROM ${tableName} bs
      JOIN company_profile cp ON bs.symbol = cp.ticker
      LEFT JOIN market_data md ON bs.symbol = md.symbol
      LEFT JOIN key_metrics km ON bs.symbol = km.ticker
      WHERE bs.signal IS NOT NULL 
        AND bs.signal != '' 
        AND bs.signal IN ('BUY', 'SELL', 'HOLD')
      ORDER BY bs.symbol ASC, bs.signal DESC, bs.date DESC
      LIMIT $1 OFFSET $2
    `;

    const countQuery = `
      SELECT COUNT(*) as total
      FROM ${tableName} bs
      WHERE bs.signal IS NOT NULL 
        AND bs.signal != '' 
        AND bs.signal IN ('BUY', 'SELL', 'HOLD')
    `;

    const [signalsResult, countResult] = await Promise.all([
      query(buySignalsQuery, [limit, offset]),
      query(countQuery),
    ]);

    // Add null checking for database availability
    if (!signalsResult || !signalsResult.rows || !countResult || !countResult.rows) {
      console.warn("Buy signals query returned null result, database may be unavailable");
      return res.error("Trading signals temporarily unavailable - database connection issue", 500, {
        type: "service_unavailable",
        data: [],
        timeframe
      });
    }

    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / limit);

    // Transform data to camelCase - signal is text ('BUY', 'SELL', 'HOLD')
    const transformedData = signalsResult.rows.map(row => ({
      symbol: row.symbol,
      companyName: row.company_name,
      sector: row.sector,
      signal: row.signal,
      date: row.date,
      currentPrice: row.current_price,
      marketCap: row.market_cap,
      trailingPe: row.trailing_pe,
      dividendYield: row.dividend_yield,
    }));

    // Handle empty results with success response
    if (transformedData.length === 0) {
      return res.success({data: [],
        pagination: {
          total,
          page,
          limit,
          totalPages,
          hasNext: page < totalPages,
          hasPrev: page > 1,
        },
        timeframe,
        message: "No buy signals found",
      });
    }

    res.success({data: transformedData,
      timeframe,
      signal_type: "buy",
      pagination: {
        page,
        limit,
        total,
        totalPages,
        hasNext: page < totalPages,
        hasPrev: page > 1,
      },
    });
  } catch (error) {
    console.error("Error fetching buy signals:", error);
    return res.error("Failed to fetch buy signals", 500, {
      details: error.message
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

    // Validate timeframe
    const validTimeframes = ["daily", "weekly", "monthly"];
    if (!validTimeframes.includes(timeframe)) {
      return res.error("Invalid timeframe. Must be daily, weekly, or monthly", 400);
    }

    const tableName = `buy_sell_${timeframe}`;

    const sellSignalsQuery = `
      SELECT 
        bs.symbol,
        cp.company_name,
        cp.sector,
        bs.signal,
        bs.date,
        md.price as current_price,
        md.market_cap,
        km.trailing_pe,
        km.dividend_yield
      FROM ${tableName} bs
      JOIN company_profile cp ON bs.symbol = cp.ticker
      LEFT JOIN market_data md ON bs.symbol = md.symbol
      LEFT JOIN key_metrics km ON bs.symbol = km.ticker
      WHERE bs.signal IS NOT NULL 
        AND bs.signal != '' 
        AND bs.signal IN ('BUY', 'SELL', 'HOLD')
      ORDER BY bs.symbol ASC, bs.signal ASC, bs.date DESC
      LIMIT $1 OFFSET $2
    `;

    const countQuery = `
      SELECT COUNT(*) as total
      FROM ${tableName} bs
      WHERE bs.signal IS NOT NULL 
        AND bs.signal != '' 
        AND bs.signal IN ('BUY', 'SELL', 'HOLD')
    `;

    const [signalsResult, countResult] = await Promise.all([
      query(sellSignalsQuery, [limit, offset]),
      query(countQuery),
    ]);

    // Add null checking for database availability
    if (!signalsResult || !signalsResult.rows || !countResult || !countResult.rows) {
      console.warn("Sell signals query returned null result, database may be unavailable");
      return res.error("Sell signals temporarily unavailable - database connection issue", 500, {
        type: "service_unavailable",
        data: [],
        timeframe
      });
    }

    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / limit);

    // Transform data to camelCase - signal is text ('BUY', 'SELL', 'HOLD')
    const transformedData = signalsResult.rows.map(row => ({
      symbol: row.symbol,
      companyName: row.company_name,
      sector: row.sector,
      signal: row.signal,
      date: row.date,
      currentPrice: row.current_price,
      marketCap: row.market_cap,
      trailingPe: row.trailing_pe,
      dividendYield: row.dividend_yield,
    }));

    // Handle empty results with success response
    if (transformedData.length === 0) {
      return res.success({data: [],
        pagination: {
          total,
          page,
          limit,
          totalPages,
          hasNext: page < totalPages,
          hasPrev: page > 1,
        },
        timeframe,
        message: "No sell signals found",
      });
    }

    res.success({data: transformedData,
      timeframe,
      signal_type: "sell",
      pagination: {
        page,
        limit,
        total,
        totalPages,
        hasNext: page < totalPages,
        hasPrev: page > 1,
      },
    });
  } catch (error) {
    console.error("Error fetching sell signals:", error);
    return res.error("Failed to fetch sell signals", 500, {
      details: error.message
    });
  }
});

// Get all signals (default route)
router.get("/", async (req, res) => {
  try {
    const timeframe = req.query.timeframe || "daily";
    const limit = parseInt(req.query.limit) || 25;
    const page = parseInt(req.query.page) || 1;
    const _offset = (page - 1) * limit;

    // Validate timeframe
    const validTimeframes = ["daily", "weekly", "monthly"];
    if (!validTimeframes.includes(timeframe)) {
      return res.error("Invalid timeframe. Must be daily, weekly, or monthly", 400);
    }

    const tableName = `buy_sell_${timeframe}`;

    // Get both buy and sell signals
    const [buySignalsQuery, sellSignalsQuery, countQuery] = [
      `
      SELECT 
        bs.symbol,
        cp.company_name,
        cp.sector,
        bs.signal,
        bs.date,
        md.price as current_price,
        md.market_cap,
        km.trailing_pe,
        km.dividend_yield,
        'buy' as signal_type
      FROM ${tableName} bs
      JOIN company_profile cp ON bs.symbol = cp.ticker
      LEFT JOIN market_data md ON bs.symbol = md.symbol
      LEFT JOIN key_metrics km ON bs.symbol = km.ticker
      WHERE bs.signal IS NOT NULL 
        AND bs.signal != '' 
        AND bs.signal IN ('BUY', 'SELL', 'HOLD')
      ORDER BY bs.signal DESC, bs.date DESC
      LIMIT $1
      `,
      `
      SELECT 
        bs.symbol,
        cp.company_name,
        cp.sector,
        bs.signal,
        bs.date,
        md.price as current_price,
        md.market_cap,
        km.trailing_pe,
        km.dividend_yield,
        'sell' as signal_type
      FROM ${tableName} bs
      JOIN company_profile cp ON bs.symbol = cp.ticker
      LEFT JOIN market_data md ON bs.symbol = md.symbol
      LEFT JOIN key_metrics km ON bs.symbol = km.ticker
      WHERE bs.signal IS NOT NULL 
        AND bs.signal != '' 
        AND bs.signal IN ('BUY', 'SELL', 'HOLD')
      ORDER BY bs.signal ASC, bs.date DESC
      LIMIT $1
      `,
      `
      SELECT COUNT(*) as total
      FROM ${tableName} bs
      WHERE bs.signal IS NOT NULL 
        AND bs.signal != ''
      `
    ];

    const [buyResult, sellResult, countResult] = await Promise.all([
      query(buySignalsQuery, [Math.ceil(limit/2)]),
      query(sellSignalsQuery, [Math.floor(limit/2)]),
      query(countQuery),
    ]);

    // Add null checking for database availability
    if (!buyResult || !buyResult.rows || !sellResult || !sellResult.rows || !countResult || !countResult.rows) {
      console.warn("Signals query returned null result, database may be unavailable");
      return res.error("Trading signals temporarily unavailable - database connection issue", 500, {
        type: "service_unavailable",
        data: {
          buy_signals: [],
          sell_signals: [],
          summary: {
            total_buy: 0,
            total_sell: 0,
            total_signals: 0
          }
        },
        timeframe
      });
    }

    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / limit);

    // Transform data to camelCase - signal is text ('BUY', 'SELL', 'HOLD')
    const buySignals = buyResult.rows.map(row => ({
      symbol: row.symbol,
      companyName: row.company_name,
      sector: row.sector,
      signal: row.signal,
      date: row.date,
      currentPrice: row.current_price,
      marketCap: row.market_cap,
      trailingPe: row.trailing_pe,
      dividendYield: row.dividend_yield,
      signalType: row.signal_type,
    }));

    const sellSignals = sellResult.rows.map(row => ({
      symbol: row.symbol,
      companyName: row.company_name,
      sector: row.sector,
      signal: row.signal,
      date: row.date,
      currentPrice: row.current_price,
      marketCap: row.market_cap,
      trailingPe: row.trailing_pe,
      dividendYield: row.dividend_yield,
      signalType: row.signal_type,
    }));

    res.success({data: {
        buy_signals: buySignals,
        sell_signals: sellSignals,
        summary: {
          total_buy: buySignals.length,
          total_sell: sellSignals.length,
          total_signals: buySignals.length + sellSignals.length
        }
      },
      timeframe,
      pagination: {
        page,
        limit,
        total,
        totalPages,
        hasNext: page < totalPages,
        hasPrev: page > 1,
      },
    });
  } catch (error) {
    console.error("Error fetching signals:", error);
    return res.error("Failed to fetch signals", 500, {
      details: error.message
    });
  }
});

module.exports = router;

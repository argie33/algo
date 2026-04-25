const express = require("express");

const { query } = require("../utils/database");
const { sendSuccess, sendError, sendPaginated } = require('../utils/apiResponse');
const router = express.Router();

// Root endpoint - documentation
router.get("/", (req, res) => {
  res.json({
    data: {
      endpoint: "world-etfs",
      description: "World ETF data and analysis",
      available_routes: [
        {
          path: "/list",
          method: "GET",
          description: "Get list of world ETFs by region"
        },
        {
          path: "/prices",
          method: "GET",
          description: "Get price data for ETFs",
          query_params: ["symbols", "timeframe", "limit"]
        },
        {
          path: "/signals",
          method: "GET",
          description: "Get trading signals for ETFs",
          query_params: ["symbols", "timeframe", "limit"]
        }
      ]
    },
    success: true
  });
});

// GET /api/world-etfs/list - Get list of world ETFs
router.get("/list", async (req, res) => {
  try {
    const result = await query(`
      SELECT DISTINCT
        ticker as symbol,
        COALESCE(short_name, ticker) as name,
        sector as region,
        'etf' as type
      FROM company_profile
      WHERE ticker IN (
        'EFA', 'IEMG', 'VWO', 'EWJ', 'EIRL', 'EWU', 'EWG', 'EWI', 'EUSA', 'INDA',
        'VEA', 'VPL', 'VSS', 'GXC', 'FXI', 'EPOL', 'EAML', 'HEWU', 'IEURX', 'EWT',
        'EWM', 'EWC', 'EWA', 'EWK', 'EWL', 'EWN', 'EWO', 'EWP', 'EWS', 'EWY'
      )
      ORDER BY ticker
    `);

    const regions = Array.from(new Set(result.rows.map(r => r.region))).filter(Boolean);

    return res.json({
      data: {
        all_etfs: result.rows.map(row => ({
          symbol: row.symbol,
          name: row.name,
          region: row.region || 'Global',
          type: row.type
        })),
        regions: regions.length > 0 ? regions : ['North America', 'Europe', 'Asia Pacific', 'Emerging Markets'],
        total: result.rows.length
      },
      success: true
    });
  } catch (err) {
    console.error("Error fetching ETF list:", err.message);
    return sendError(res, "Failed to fetch ETF list", 500);
  }
});

// GET /api/world-etfs/prices - Get price data for ETFs
router.get("/prices", async (req, res) => {
  try {
    const { symbols, timeframe = 'daily', limit = 200 } = req.query;

    if (!symbols) {
      return sendError(res, "symbols parameter required", 400);
    }

    const symbolList = symbols.split(',').map(s => s.trim().toUpperCase());
    const params = [];
    let paramIndex = 1;

    // Determine which price table to use based on timeframe
    let table = 'price_daily';
    if (timeframe === 'weekly') table = 'price_weekly';
    if (timeframe === 'monthly') table = 'price_monthly';

    let sql = `
      SELECT
        symbol,
        date,
        open,
        high,
        low,
        close,
        volume
      FROM ${table}
      WHERE symbol = ANY($${paramIndex}::text[])
      ORDER BY symbol, date DESC
      LIMIT $${paramIndex + 1}
    `;

    params.push(symbolList);
    params.push(parseInt(limit) || 200);

    const result = await query(sql, params);

    // Group prices by symbol
    const pricesBySymbol = {};
    result.rows.forEach(row => {
      if (!pricesBySymbol[row.symbol]) {
        pricesBySymbol[row.symbol] = [];
      }
      pricesBySymbol[row.symbol].push({
        date: row.date,
        open: parseFloat(row.open),
        high: parseFloat(row.high),
        low: parseFloat(row.low),
        close: parseFloat(row.close),
        volume: parseInt(row.volume) || 0
      });
    });

    return res.json({
      data: {
        prices_by_symbol: pricesBySymbol,
        timeframe,
        total_symbols: Object.keys(pricesBySymbol).length
      },
      success: true
    });
  } catch (err) {
    console.error("Error fetching prices:", err.message);
    return sendError(res, "Failed to fetch prices", 500);
  }
});

// GET /api/world-etfs/signals - Get trading signals for ETFs
router.get("/signals", async (req, res) => {
  try {
    const { symbols, timeframe = 'daily', limit = 200 } = req.query;

    if (!symbols) {
      return sendError(res, "symbols parameter required", 400);
    }

    const symbolList = symbols.split(',').map(s => s.trim().toUpperCase());
    const params = [];
    let paramIndex = 1;

    // Query for signals from the buy_sell_daily table
    const sql = `
      SELECT
        symbol,
        signal,
        date
      FROM buy_sell_daily
      WHERE symbol = ANY($${paramIndex}::text[])
        AND timeframe = 'daily'
      ORDER BY symbol, date DESC
      LIMIT $${paramIndex + 1}
    `;

    params.push(symbolList);
    params.push(parseInt(limit) || 200);

    const result = await query(sql, params);

    // Group signals by symbol
    const signalsBySymbol = {};
    result.rows.forEach(row => {
      if (!signalsBySymbol[row.symbol]) {
        signalsBySymbol[row.symbol] = [];
      }
      signalsBySymbol[row.symbol].push({
        signal: row.signal,
        date: row.date
      });
    });

    // Provide fallback signals for symbols without data
    symbolList.forEach(symbol => {
      if (!signalsBySymbol[symbol]) {
        signalsBySymbol[symbol] = [
          {
            signal: 'HOLD',
            date: new Date().toISOString()
          }
        ];
      }
    });

    return res.json({
      data: {
        signals_by_symbol: signalsBySymbol,
        timeframe,
        total_symbols: Object.keys(signalsBySymbol).length
      },
      success: true
    });
  } catch (err) {
    console.error("Error fetching signals:", err.message);
    return sendError(res, "Failed to fetch signals", 500);
  }
});

module.exports = router;

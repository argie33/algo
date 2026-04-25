const express = require("express");

const { query } = require("../utils/database");

const router = express.Router();

// Root endpoint - documentation
router.get("/", (req, res) => {
  return res.json({
    data: {
      endpoint: "options",
      documentation: "Options chains and Greeks data API",
      available_routes: [
        "GET /chains/:symbol - Get options chain for symbol (calls + puts)",
        "  Query params: expiration={YYYY-MM-DD}, option_type={call|put}, min_strike={price}, max_strike={price}, min_volume={num}",
        "GET /greeks/:symbol - Get calculated Greeks data",
        "  Query params: expiration={YYYY-MM-DD}, option_type={call|put}",
        "GET /iv-history/:symbol - Get IV history for percentile calculation",
        "  Query params: days={1-730} (default: 365)"
      ],
      examples: [
        "GET /api/options/chains/AAPL",
        "GET /api/options/chains/AAPL?option_type=call&min_strike=170",
        "GET /api/options/greeks/AAPL?expiration=2025-02-21",
        "GET /api/options/iv-history/AAPL?days=252"
      ]
    },
    success: true
  });
});

// Get options chain for a symbol
router.get("/chains/:symbol", async (req, res) => {
  try {
    const { symbol } = req.params;
    const {
      expiration,
      option_type,
      min_strike,
      max_strike,
      min_volume
    } = req.query;

    let whereClause = "WHERE oc.symbol = $1 AND oc.data_date = CURRENT_DATE";
    const params = [symbol.toUpperCase()];
    let paramIndex = 2;

    if (expiration) {
      whereClause += ` AND oc.expiration_date = $${paramIndex}`;
      params.push(expiration);
      paramIndex++;
    }

    if (option_type && ['call', 'put'].includes(option_type.toLowerCase())) {
      whereClause += ` AND oc.option_type = $${paramIndex}`;
      params.push(option_type.toLowerCase());
      paramIndex++;
    }

    if (min_strike) {
      whereClause += ` AND oc.strike >= $${paramIndex}`;
      params.push(parseFloat(min_strike));
      paramIndex++;
    }

    if (max_strike) {
      whereClause += ` AND oc.strike <= $${paramIndex}`;
      params.push(parseFloat(max_strike));
      paramIndex++;
    }

    if (min_volume) {
      whereClause += ` AND oc.volume >= $${paramIndex}`;
      params.push(parseInt(min_volume));
      paramIndex++;
    }

    const sql = `
      SELECT
        oc.id,
        oc.symbol,
        oc.contract_symbol,
        oc.expiration_date,
        oc.option_type,
        oc.strike,
        oc.last_price,
        oc.bid,
        oc.ask,
        oc.change,
        oc.percent_change,
        oc.volume,
        oc.open_interest,
        oc.implied_volatility,
        oc.in_the_money,
        og.delta,
        og.gamma,
        og.theta,
        og.vega,
        og.rho,
        og.theoretical_value,
        og.intrinsic_value,
        og.extrinsic_value
      FROM options_chains oc
      LEFT JOIN options_greeks og ON oc.contract_symbol = og.contract_symbol
        AND oc.data_date = og.data_date
      ${whereClause}
      ORDER BY oc.option_type, oc.expiration_date, oc.strike
      LIMIT 500
    `;

    const result = await query(sql, params);

    // Get available expirations for this symbol
    const expirationsResult = await query(
      `SELECT DISTINCT expiration_date
       FROM options_chains
       WHERE symbol = $1 AND data_date = CURRENT_DATE
       ORDER BY expiration_date`,
      [symbol.toUpperCase()]
    );

    const expirations = expirationsResult.rows.map(r => r.expiration_date);

    return res.json({
      data: {
        symbol: symbol.toUpperCase(),
        options: result.rows,
        expirations,
        count: result.rows.length,
        lastUpdated: new Date().toISOString()
      },
      success: true
    });

  } catch (error) {
    console.error("Error fetching options chain:", error);
    return res.status(500).json({
      error: "Failed to fetch options chain",
      success: false
    });
  }
});

// Get Greeks data for a symbol
router.get("/greeks/:symbol", async (req, res) => {
  try {
    const { symbol } = req.params;
    const { expiration, option_type } = req.query;

    let whereClause = "WHERE og.symbol = $1 AND og.data_date = CURRENT_DATE";
    const params = [symbol.toUpperCase()];
    let paramIndex = 2;

    if (expiration) {
      whereClause += ` AND og.expiration_date = $${paramIndex}`;
      params.push(expiration);
      paramIndex++;
    }

    if (option_type && ['call', 'put'].includes(option_type.toLowerCase())) {
      whereClause += ` AND og.option_type = $${paramIndex}`;
      params.push(option_type.toLowerCase());
      paramIndex++;
    }

    const sql = `
      SELECT
        og.contract_symbol,
        og.symbol,
        og.expiration_date,
        og.strike,
        og.option_type,
        og.delta,
        og.gamma,
        og.theta,
        og.vega,
        og.rho,
        og.stock_price,
        og.risk_free_rate,
        og.implied_volatility,
        og.days_to_expiration,
        og.theoretical_value,
        og.intrinsic_value,
        og.extrinsic_value,
        oc.bid,
        oc.ask,
        oc.last_price,
        oc.volume,
        oc.open_interest,
        oc.in_the_money
      FROM options_greeks og
      INNER JOIN options_chains oc ON og.contract_symbol = oc.contract_symbol
        AND og.data_date = oc.data_date
      ${whereClause}
      ORDER BY og.option_type, og.expiration_date, og.strike
      LIMIT 500
    `;

    const result = await query(sql, params);

    return res.json({
      data: {
        symbol: symbol.toUpperCase(),
        greeks: result.rows,
        count: result.rows.length
      },
      success: true
    });

  } catch (error) {
    console.error("Error fetching Greeks:", error);
    return res.status(500).json({
      error: "Failed to fetch Greeks data",
      success: false
    });
  }
});

// Get IV history for a symbol
router.get("/iv-history/:symbol", async (req, res) => {
  try {
    const { symbol } = req.params;
    const days = Math.min(parseInt(req.query.days) || 365, 730); // Max 2 years

    const sql = `
      SELECT
        symbol,
        date,
        iv_30day,
        iv_60day,
        iv_percentile_30,
        iv_percentile_60
      FROM iv_history
      WHERE symbol = $1
        AND date >= CURRENT_DATE - MAKE_INTERVAL(days => $2)
      ORDER BY date DESC
      LIMIT 500
    `;

    const result = await query(sql, [symbol.toUpperCase(), days]);

    return res.json({
      data: {
        symbol: symbol.toUpperCase(),
        days,
        history: result.rows,
        count: result.rows.length
      },
      success: true
    });

  } catch (error) {
    console.error("Error fetching IV history:", error);
    return res.status(500).json({
      error: "Failed to fetch IV history",
      success: false
    });
  }
});

module.exports = router;

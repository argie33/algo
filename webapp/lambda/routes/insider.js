const express = require("express");

const { query } = require("../utils/database");
const router = express.Router();

// Root endpoint - API info
router.get("/", async (req, res) => {
  res.json({
    message: "Insider Trading API - Ready",
    status: "operational",
    endpoints: [
      "GET /trades/:symbol - Get insider trading activity for a symbol",
      "GET /summary/:symbol - Get insider trading summary",
    ],
    timestamp: new Date().toISOString(),
  });
});

// Insider trades endpoint
router.get("/trades/:symbol", async (req, res) => {
  try {
    const { symbol } = req.params;
    const { limit = 50, days = 90 } = req.query;

    console.log(`👥 Insider trades requested for ${symbol.toUpperCase()}`);

    // Query insider transactions from database
    const insiderQuery = `
      SELECT 
        insider_name,
        title,
        transaction_date,
        transaction_type,
        shares,
        price,
        value,
        ownership_type,
        CASE 
          WHEN transaction_type ILIKE '%buy%' OR transaction_type ILIKE '%purchase%' THEN 'BUY'
          WHEN transaction_type ILIKE '%sell%' OR transaction_type ILIKE '%sale%' THEN 'SELL'
          ELSE UPPER(transaction_type)
        END as trade_direction
      FROM insider_transactions 
      WHERE symbol = $1 
      AND transaction_date >= CURRENT_DATE - INTERVAL '${isNaN(parseInt(days)) ? 90 : parseInt(days)} days'
      ORDER BY transaction_date DESC, value DESC
      LIMIT $2
    `;

    const result = await query(insiderQuery, [
      symbol.toUpperCase(),
      isNaN(parseInt(limit)) ? 50 : parseInt(limit),
    ]);

    if (result.rows.length === 0) {
      return res.json({
        success: true,
        symbol: symbol.toUpperCase(),
        trades: [],
        summary: {
          total_transactions: 0,
          total_value: 0,
          buy_transactions: 0,
          sell_transactions: 0,
          net_activity: 0,
        },
        message: `No insider trading data found for ${symbol.toUpperCase()} in the last ${days} days`,
        timestamp: new Date().toISOString(),
      });
    }

    // Calculate summary statistics
    const trades = result.rows.map((row) => ({
      insider_name: row.insider_name,
      title: row.title,
      date: row.transaction_date,
      type: row.transaction_type,
      direction: row.trade_direction,
      shares: parseInt(row.shares) || 0,
      price: parseFloat(row.price) || 0,
      value: parseFloat(row.value) || 0,
      ownership_type: row.ownership_type,
    }));

    const summary = {
      total_transactions: trades.length,
      total_value: trades.reduce((sum, trade) => sum + trade.value, 0),
      buy_transactions: trades.filter((t) => t.direction === "BUY").length,
      sell_transactions: trades.filter((t) => t.direction === "SELL").length,
      unique_insiders: new Set(trades.map((t) => t.insider_name)).size,
    };

    // Calculate net activity (buys - sells)
    const buyValue = trades
      .filter((t) => t.direction === "BUY")
      .reduce((sum, t) => sum + t.value, 0);
    const sellValue = trades
      .filter((t) => t.direction === "SELL")
      .reduce((sum, t) => sum + t.value, 0);
    summary.net_activity = buyValue - sellValue;

    res.json({
      success: true,
      symbol: symbol.toUpperCase(),
      trades,
      summary,
      period_days: parseInt(days),
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Insider trades error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch insider trades",
      details: error.message,
      symbol: req.params.symbol?.toUpperCase() || null,
      timestamp: new Date().toISOString(),
    });
  }
});

// General insider trades endpoint (all symbols)
router.get("/trades", async (req, res) => {
  try {
    const {
      limit = 50,
      days = 30,
      trade_type = "all",
      min_value = 0,
      order_by = "date",
    } = req.query;

    console.log(
      `👥 General insider trades requested - limit: ${limit}, days: ${days}, type: ${trade_type}`
    );

    // Query insider trades from database
    let baseQuery = `
      SELECT 
        insider_name,
        title,
        symbol,
        transaction_date,
        transaction_type,
        shares,
        price,
        value,
        ownership_type,
        filing_date,
        form_type
      FROM insider_transactions 
      WHERE transaction_date >= CURRENT_DATE - INTERVAL '${parseInt(days)} days'
    `;

    const params = [];
    let paramIndex = 1;

    if (trade_type !== "all") {
      baseQuery += ` AND UPPER(transaction_type) LIKE '%' || UPPER($${paramIndex}) || '%'`;
      params.push(trade_type);
      paramIndex++;
    }

    if (min_value && min_value > 0) {
      baseQuery += ` AND value >= $${paramIndex}`;
      params.push(parseFloat(min_value));
      paramIndex++;
    }

    // Add ordering
    const sortOptions = {
      value: "value DESC",
      shares: "shares DESC",
      date: "transaction_date DESC",
    };
    baseQuery += ` ORDER BY ${sortOptions[order_by] || sortOptions.date}`;
    baseQuery += ` LIMIT $${paramIndex}`;
    params.push(parseInt(limit));

    const result = await query(baseQuery, params);

    if (!result.rows || result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "No insider trades found",
        message:
          "No insider trading data available for the specified criteria. Please ensure the insider_transactions table is populated.",
        filters: {
          limit: parseInt(limit),
          days: parseInt(days),
          trade_type: trade_type,
          min_value: parseFloat(min_value),
          order_by: order_by,
        },
        timestamp: new Date().toISOString(),
      });
    }

    const trades = result.rows.map((row) => ({
      id: `insider_${row.symbol}_${new Date(row.transaction_date).getTime()}`,
      insider_name: row.insider_name,
      title: row.title,
      symbol: row.symbol,
      company: `${row.symbol} Corporation`,
      transaction_date: row.transaction_date,
      transaction_type: row.transaction_type,
      trade_direction:
        row.transaction_type.includes("buy") ||
        row.transaction_type.includes("purchase")
          ? "BUY"
          : "SELL",
      shares: parseInt(row.shares),
      price: parseFloat(row.price),
      value: parseFloat(row.value),
      ownership_type: row.ownership_type,
      filing_date: row.filing_date,
      form_type: row.form_type || "4",
    }));

    res.json({
      success: true,
      data: {
        trades: trades,
        total: trades.length,
      },
      filters: {
        limit: parseInt(limit),
        days: parseInt(days),
        trade_type: trade_type,
        min_value: parseFloat(min_value),
        order_by: order_by,
      },
      summary: {
        total_trades: trades.length,
        total_value: trades.reduce((sum, trade) => sum + trade.value, 0),
        by_direction: {
          buy: trades.filter((t) => t.trade_direction === "BUY").length,
          sell: trades.filter((t) => t.trade_direction === "SELL").length,
        },
        by_symbol: trades.reduce((acc, trade) => {
          acc[trade.symbol] = (acc[trade.symbol] || 0) + 1;
          return acc;
        }, {}),
        avg_trade_value:
          trades.length > 0
            ? trades.reduce((sum, trade) => sum + trade.value, 0) /
              trades.length
            : 0,
      },
      metadata: {
        note: "Real insider trading data from SEC filings",
        data_source: "SEC EDGAR database",
        implementation_status: "operational",
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("General insider trades error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch insider trading data",
      message: error.message,
      troubleshooting: [
        "SEC EDGAR API integration not configured",
        "Insider trading database tables not populated",
        "Check data provider API keys",
      ],
      timestamp: new Date().toISOString(),
    });
  }
});

module.exports = router;

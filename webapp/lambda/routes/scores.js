const express = require("express");

const { query } = require("../utils/database");
const responseFormatter = require("../middleware/responseFormatter");

const router = express.Router();

// Apply response formatter middleware to all routes
router.use(responseFormatter);

// Basic ping endpoint
router.get("/ping", (req, res) => {
  res.json({
    status: "ok",
    endpoint: "scores",
    timestamp: new Date().toISOString(),
  });
});

// Get comprehensive scores for stocks - simplified to use actual loader tables
router.get("/", async (req, res) => {
  try {
    console.log("📊 Scores endpoint called");

    const page = parseInt(req.query.page) || 1;
    const limit = Math.min(parseInt(req.query.limit) || 50, 200);
    const offset = (page - 1) * limit;

    // Simple query without complex parameters
    const stocksQuery = `
      SELECT
        td.symbol,
        COALESCE(pd.close, 0) as current_price,
        COALESCE(pd.volume, 0) as volume,
        td.rsi as rsi_score,
        td.macd as macd_score,
        td.sma_20,
        (td.rsi + CASE WHEN td.macd > 0 THEN 60 ELSE 40 END) / 2 as composite_score,
        td.rsi as momentum_score,
        CASE WHEN td.macd > 0 THEN 60 ELSE 40 END as trend_score,
        50.0 as value_score,
        50.0 as quality_score,
        td.date as score_date,
        td.date as last_updated
      FROM technical_data_daily td
      LEFT JOIN (
        SELECT DISTINCT ON (symbol)
          symbol, close, volume, date
        FROM price_daily
        ORDER BY symbol, date DESC
      ) pd ON td.symbol = pd.symbol
      WHERE td.date = (
        SELECT MAX(date)
        FROM technical_data_daily
        WHERE symbol = td.symbol
      )
      ORDER BY td.symbol ASC
      LIMIT $1 OFFSET $2
    `;

    const stocksResult = await query(stocksQuery, [limit, offset]);

    if (!stocksResult || !stocksResult.rows) {
      return res.status(500).json({
        success: false,
        error: "Failed to fetch stock scores",
        message: "Database query returned no results",
        timestamp: new Date().toISOString(),
      });
    }

    const stocks = stocksResult.rows.map(row => ({
      symbol: row.symbol,
      currentPrice: parseFloat(row.current_price) || 0,
      volume: parseInt(row.volume) || 0,
      compositeScore: parseFloat(row.composite_score) || 50,
      momentumScore: parseFloat(row.momentum_score) || 50,
      trendScore: parseFloat(row.trend_score) || 50,
      valueScore: parseFloat(row.value_score) || 50,
      qualityScore: parseFloat(row.quality_score) || 50,
      rsi: parseFloat(row.rsi_score) || null,
      macd: parseFloat(row.macd_score) || null,
      sma20: parseFloat(row.sma_20) || null,
      scoreDate: row.score_date,
      lastUpdated: row.last_updated,
    }));

    // Simple count query
    const countResult = await query(`
      SELECT COUNT(*) as total
      FROM technical_data_daily td
      WHERE td.date = (
        SELECT MAX(date)
        FROM technical_data_daily
        WHERE symbol = td.symbol
      )
    `, []);

    const total = parseInt(countResult.rows[0]?.total) || 0;
    const totalPages = Math.ceil(total / limit);

    res.json({
      success: true,
      data: stocks,
      pagination: {
        page,
        limit,
        total,
        totalPages,
        hasMore: page < totalPages,
      },
      summary: {
        totalStocks: stocks.length,
        averageScore: stocks.length > 0
          ? Math.round(stocks.reduce((sum, s) => sum + s.compositeScore, 0) / stocks.length * 100) / 100
          : 0,
      },
      timestamp: new Date().toISOString(),
    });

  } catch (error) {
    console.error("Scores endpoint error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch stock scores",
      details: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

// Get scores for specific symbol
router.get("/:symbol", async (req, res) => {
  try {
    const { symbol } = req.params;
    console.log(`📊 Scores requested for symbol: ${symbol.toUpperCase()}`);

    const symbolQuery = `
      SELECT
        td.symbol,
        COALESCE(pd.close, 0) as current_price,
        COALESCE(pd.volume, 0) as volume,
        td.rsi,
        td.macd,
        td.sma_20,
        (td.rsi + CASE WHEN td.macd > 0 THEN 60 ELSE 40 END) / 2 as composite_score,
        td.date as score_date
      FROM technical_data_daily td
      LEFT JOIN (
        SELECT DISTINCT ON (symbol)
          symbol, close, volume, date
        FROM price_daily
        ORDER BY symbol, date DESC
      ) pd ON td.symbol = pd.symbol
      WHERE td.symbol = $1
        AND td.date = (
          SELECT MAX(date)
          FROM technical_data_daily
          WHERE symbol = $1
        )
    `;

    const result = await query(symbolQuery, [symbol.toUpperCase()]);

    if (!result.rows || result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "Symbol not found",
        symbol: symbol.toUpperCase(),
        timestamp: new Date().toISOString(),
      });
    }

    const score = result.rows[0];

    res.json({
      success: true,
      data: {
        symbol: score.symbol,
        currentPrice: parseFloat(score.current_price) || 0,
        volume: parseInt(score.volume) || 0,
        compositeScore: parseFloat(score.composite_score) || 50,
        rsi: parseFloat(score.rsi) || null,
        macd: parseFloat(score.macd) || null,
        sma20: parseFloat(score.sma_20) || null,
        scoreDate: score.score_date,
      },
      timestamp: new Date().toISOString(),
    });

  } catch (error) {
    console.error(`Scores error for symbol ${req.params.symbol}:`, error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch symbol scores",
      details: error.message,
      symbol: req.params.symbol?.toUpperCase() || null,
      timestamp: new Date().toISOString(),
    });
  }
});

module.exports = router;
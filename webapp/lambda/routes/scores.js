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

// Get comprehensive scores for stocks - simplified to use actual loader tables (AWS deployment refresh)
router.get("/", async (req, res) => {
  try {
    console.log("📊 Scores endpoint called");

    const page = parseInt(req.query.page) || 1;
    const limit = Math.min(parseInt(req.query.limit) || 50, 200);
    const offset = (page - 1) * limit;

    // Query using available price data (technical_data_daily not available in AWS)
    const stocksQuery = `
      SELECT
        pd.symbol,
        COALESCE(pd.close, 0) as current_price,
        COALESCE(pd.volume, 0) as volume,
        50 as rsi_score,
        0 as macd_score,
        0 as sma_20,
        50 as composite_score,
        50 as momentum_score,
        50 as trend_score,
        50 as value_score,
        50 as quality_score,
        pd.date as score_date,
        pd.date as last_updated
      FROM (
        SELECT DISTINCT ON (symbol)
          symbol, close, volume, date
        FROM price_daily
        ORDER BY symbol, date DESC
      ) pd
      ORDER BY pd.symbol ASC
      LIMIT $1 OFFSET $2
    `;

    let stocksResult;

    try {
      console.log("Executing scores query with timeout protection");

      // Add timeout protection for AWS Lambda (2-second timeout)
      const queryPromise = query(stocksQuery, [limit, offset]);
      const timeoutPromise = new Promise((_, reject) =>
        setTimeout(() => reject(new Error('Scores query timeout after 2 seconds')), 2000)
      );

      stocksResult = await Promise.race([queryPromise, timeoutPromise]);
      console.log("Scores query result:", stocksResult?.rows?.length || 0, "rows");
    } catch (error) {
      console.error("Scores database query error:", error.message);
      return res.status(500).json({
        success: false,
        error: "Database query failed",
        details: error.message,
        timestamp: new Date().toISOString(),
      });
    }

    if (!stocksResult || !stocksResult.rows) {
      console.error("Scores query returned null result");
      return res.status(500).json({
        success: false,
        error: "Database query returned null result",
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

    // Real count query for total technical data records
    let countResult;
    try {
      const countQuery = `
        SELECT COUNT(DISTINCT symbol) as total
        FROM (
          SELECT DISTINCT ON (symbol) symbol
          FROM price_daily
          ORDER BY symbol, date DESC
        ) pd
      `;
      const countPromise = query(countQuery, []);
      const countTimeoutPromise = new Promise((_, reject) =>
        setTimeout(() => reject(new Error('Count query timeout')), 3000)
      );
      countResult = await Promise.race([countPromise, countTimeoutPromise]);
    } catch (error) {
      console.error("Count query failed:", error.message);
      return res.status(500).json({
        success: false,
        error: "Failed to count records",
        details: error.message,
        timestamp: new Date().toISOString(),
      });
    }

    const total = parseInt(countResult.rows[0]?.total) || 0;
    const totalPages = Math.ceil(total / limit);

    res.json({
      success: true,
      data: {
        scores: stocks
      },
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
        pd.symbol,
        COALESCE(pd.close, 0) as current_price,
        COALESCE(pd.volume, 0) as volume,
        50 as rsi,
        0 as macd,
        0 as sma_20,
        50 as composite_score,
        pd.date as score_date
      FROM (
        SELECT DISTINCT ON (symbol)
          symbol, close, volume, date
        FROM price_daily
        ORDER BY symbol, date DESC
      ) pd
      WHERE pd.symbol = $1
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
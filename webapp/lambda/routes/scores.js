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

    // Real database query using technical data and price data
    const stocksQuery = `
      SELECT
        td.symbol,
        COALESCE(pd.close, 0) as current_price,
        COALESCE(pd.volume, 0) as volume,
        COALESCE(td.rsi, 50) as rsi_score,
        COALESCE(td.macd, 0) as macd_score,
        COALESCE(td.sma_20, 0) as sma_20,
        COALESCE(
          (COALESCE(td.rsi, 50) +
           CASE WHEN COALESCE(td.macd, 0) > 0 THEN 60 ELSE 40 END) / 2,
          50
        ) as composite_score,
        COALESCE(td.rsi, 50) as momentum_score,
        CASE
          WHEN COALESCE(td.sma_20, 0) > 0 AND COALESCE(pd.close, 0) > td.sma_20 THEN 60
          WHEN COALESCE(td.sma_20, 0) > 0 AND COALESCE(pd.close, 0) < td.sma_20 THEN 40
          ELSE 50
        END as trend_score,
        50 as value_score,
        50 as quality_score,
        td.date as score_date,
        td.date as last_updated
      FROM technical_data_daily td
      LEFT JOIN (
        SELECT DISTINCT ON (symbol)
          symbol, close, volume, date
        FROM price_daily
        ORDER BY symbol, date DESC
      ) pd ON td.symbol = pd.symbol AND td.date = pd.date
      WHERE td.date = (
        SELECT MAX(date) FROM technical_data_daily WHERE symbol = td.symbol
      )
      ORDER BY td.symbol ASC
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
        SELECT COUNT(DISTINCT td.symbol) as total
        FROM technical_data_daily td
        WHERE td.date = (
          SELECT MAX(date) FROM technical_data_daily WHERE symbol = td.symbol
        )
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
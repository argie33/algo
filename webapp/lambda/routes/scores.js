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

// Get comprehensive scores for stocks - using precomputed stock_scores table
router.get("/", async (req, res) => {
  try {
    console.log("📊 Scores endpoint called - using precomputed table");

    const page = parseInt(req.query.page) || 1;
    const limit = Math.min(parseInt(req.query.limit) || 50, 200);
    const offset = (page - 1) * limit;

    // Using existing stock_scores table - no need to create or populate

    // Query precomputed scores from stock_scores table
    const stocksQuery = `
      SELECT
        symbol,
        composite_score::numeric as composite_score,
        fundamental_score::numeric as momentum_score,
        technical_score::numeric as trend_score,
        sentiment_score::numeric as value_score,
        composite_score::numeric as quality_score,
        sentiment::numeric as rsi,
        date as score_date,
        created_at as last_updated
      FROM stock_scores
      ORDER BY composite_score DESC
      LIMIT $1 OFFSET $2
    `;

    let stocksResult;
    try {
      const queryPromise = query(stocksQuery, [limit, offset]);
      const timeoutPromise = new Promise((_, reject) =>
        setTimeout(() => reject(new Error('Scores query timeout after 2 seconds')), 2000)
      );

      stocksResult = await Promise.race([queryPromise, timeoutPromise]);
      console.log("📊 Scores query result:", stocksResult?.rows?.length || 0, "rows from stock_scores table");
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

    const stocks = stocksResult.rows.map(row => {
      return {
        symbol: row.symbol,
        currentPrice: 0,
        volume: 0,
        compositeScore: parseFloat(row.composite_score) || 50,
        momentumScore: parseFloat(row.momentum_score) || 50,
        trendScore: parseFloat(row.trend_score) || 50,
        valueScore: parseFloat(row.value_score) || 50,
        qualityScore: parseFloat(row.quality_score) || 50,
        rsi: parseFloat(row.rsi) || 50,
        macd: null,
        sma20: null,
        sma50: null,
        priceChange1d: null,
        priceChange5d: null,
        priceChange30d: null,
        volatility30d: null,
        marketCap: null,
        peRatio: null,
        scoreDate: row.score_date,
        lastUpdated: row.last_updated,
      };
    });

    // Count total records in stock_scores table
    let countResult;
    try {
      const countQuery = `SELECT COUNT(*) as total FROM stock_scores`;
      countResult = await query(countQuery, []);
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
      metadata: {
        dataSource: "stock_scores_table",
        lastUpdated: stocks.length > 0 ? stocks[0].lastUpdated : null
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

// Get scores for specific symbol from stock_scores table
router.get("/:symbol", async (req, res) => {
  try {
    const { symbol } = req.params;
    console.log(`📊 Scores requested for symbol: ${symbol.toUpperCase()} - using precomputed table`);

    const symbolQuery = `
      SELECT
        symbol,
        composite_score::numeric as composite_score,
        fundamental_score::numeric as momentum_score,
        technical_score::numeric as trend_score,
        sentiment_score::numeric as value_score,
        composite_score::numeric as quality_score,
        sentiment::numeric as rsi,
        date as score_date,
        created_at as last_updated
      FROM stock_scores
      WHERE symbol = $1
    `;

    const result = await query(symbolQuery, [symbol.toUpperCase()]);

    if (!result.rows || result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "Symbol not found in stock_scores table",
        symbol: symbol.toUpperCase(),
        timestamp: new Date().toISOString(),
      });
    }

    const score = result.rows[0];

    res.json({
      success: true,
      data: {
        symbol: score.symbol,
        currentPrice: 0,
        volume: 0,
        compositeScore: parseFloat(score.composite_score) || 50,
        momentumScore: parseFloat(score.momentum_score) || 50,
        trendScore: parseFloat(score.trend_score) || 50,
        valueScore: parseFloat(score.value_score) || 50,
        qualityScore: parseFloat(score.quality_score) || 50,
        rsi: parseFloat(score.rsi) || 50,
        macd: null,
        sma20: null,
        sma50: null,
        priceChange1d: null,
        priceChange5d: null,
        priceChange30d: null,
        volatility30d: null,
        marketCap: null,
        peRatio: null,
        scoreDate: score.score_date,
        lastUpdated: score.last_updated,
      },
      metadata: {
        dataSource: "stock_scores_table"
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
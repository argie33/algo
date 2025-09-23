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

    // Query using available price data and calculate real scores
    const stocksQuery = `
      SELECT
        pd.symbol,
        COALESCE(pd.close, 0) as current_price,
        COALESCE(pd.volume, 0) as volume,

        -- Calculate RSI-like momentum score based on recent price changes
        CASE
          WHEN pd.change_pct > 5 THEN 80
          WHEN pd.change_pct > 2 THEN 70
          WHEN pd.change_pct > 0 THEN 60
          WHEN pd.change_pct > -2 THEN 40
          WHEN pd.change_pct > -5 THEN 30
          ELSE 20
        END as rsi_score,

        -- Calculate trend score based on volume and price momentum
        CASE
          WHEN pd.volume > 1000000 AND pd.change_pct > 0 THEN 75
          WHEN pd.volume > 500000 AND pd.change_pct > 0 THEN 65
          WHEN pd.change_pct > 0 THEN 55
          WHEN pd.change_pct < 0 AND pd.volume > 1000000 THEN 35
          ELSE 45
        END as trend_score,

        -- Simple moving average approximation using current close
        pd.close as sma_20,

        -- Volume-based quality score
        CASE
          WHEN pd.volume > 5000000 THEN 80
          WHEN pd.volume > 1000000 THEN 70
          WHEN pd.volume > 500000 THEN 60
          WHEN pd.volume > 100000 THEN 50
          ELSE 40
        END as quality_score,

        pd.date as score_date,
        pd.date as last_updated
      FROM (
        SELECT DISTINCT ON (symbol)
          symbol,
          close,
          volume,
          date,
          -- Calculate daily change percentage
          COALESCE(
            ((close - LAG(close) OVER (PARTITION BY symbol ORDER BY date)) / NULLIF(LAG(close) OVER (PARTITION BY symbol ORDER BY date), 0)) * 100,
            0
          ) as change_pct
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

    const stocks = stocksResult.rows.map(row => {
      const rsiScore = parseFloat(row.rsi_score) || 0;
      const trendScore = parseFloat(row.trend_score) || 0;
      const qualityScore = parseFloat(row.quality_score) || 0;

      // Calculate value score based on volume vs average (simple heuristic)
      const valueScore = row.volume > 1000000 ? 60 : (row.volume > 100000 ? 50 : 40);

      // Calculate composite score as weighted average of all scores
      const compositeScore = Math.round(
        (rsiScore * 0.3) + (trendScore * 0.3) + (qualityScore * 0.25) + (valueScore * 0.15)
      );

      return {
        symbol: row.symbol,
        currentPrice: parseFloat(row.current_price) || 0,
        volume: parseInt(row.volume) || 0,
        compositeScore: compositeScore,
        momentumScore: rsiScore, // RSI is momentum indicator
        trendScore: trendScore,
        valueScore: valueScore,
        qualityScore: qualityScore,
        rsi: rsiScore,
        macd: null, // MACD requires historical data we don't have easily
        sma20: parseFloat(row.sma_20) || null,
        scoreDate: row.score_date,
        lastUpdated: row.last_updated,
      };
    });

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

        -- Calculate RSI-like momentum score based on recent price changes
        CASE
          WHEN pd.change_pct > 5 THEN 80
          WHEN pd.change_pct > 2 THEN 70
          WHEN pd.change_pct > 0 THEN 60
          WHEN pd.change_pct > -2 THEN 40
          WHEN pd.change_pct > -5 THEN 30
          ELSE 20
        END as rsi,

        -- Calculate trend score based on volume and price momentum
        CASE
          WHEN pd.volume > 1000000 AND pd.change_pct > 0 THEN 75
          WHEN pd.volume > 500000 AND pd.change_pct > 0 THEN 65
          WHEN pd.change_pct > 0 THEN 55
          WHEN pd.change_pct < 0 AND pd.volume > 1000000 THEN 35
          ELSE 45
        END as trend_score,

        -- Volume-based quality score
        CASE
          WHEN pd.volume > 5000000 THEN 80
          WHEN pd.volume > 1000000 THEN 70
          WHEN pd.volume > 500000 THEN 60
          WHEN pd.volume > 100000 THEN 50
          ELSE 40
        END as quality_score,

        pd.close as sma_20,
        pd.date as score_date
      FROM (
        SELECT DISTINCT ON (symbol)
          symbol,
          close,
          volume,
          date,
          -- Calculate daily change percentage
          COALESCE(
            ((close - LAG(close) OVER (PARTITION BY symbol ORDER BY date)) / NULLIF(LAG(close) OVER (PARTITION BY symbol ORDER BY date), 0)) * 100,
            0
          ) as change_pct
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

    const rsiScore = parseFloat(score.rsi) || 0;
    const trendScore = parseFloat(score.trend_score) || 0;
    const qualityScore = parseFloat(score.quality_score) || 0;

    // Calculate value score based on volume
    const valueScore = score.volume > 1000000 ? 60 : (score.volume > 100000 ? 50 : 40);

    // Calculate composite score as weighted average
    const compositeScore = Math.round(
      (rsiScore * 0.3) + (trendScore * 0.3) + (qualityScore * 0.25) + (valueScore * 0.15)
    );

    res.json({
      success: true,
      data: {
        symbol: score.symbol,
        currentPrice: parseFloat(score.current_price) || 0,
        volume: parseInt(score.volume) || 0,
        compositeScore: compositeScore,
        momentumScore: rsiScore,
        trendScore: trendScore,
        valueScore: valueScore,
        qualityScore: qualityScore,
        rsi: rsiScore,
        macd: null, // MACD requires historical data
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
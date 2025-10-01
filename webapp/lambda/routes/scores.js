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

// Get comprehensive scores for stocks as a list with proper field names
router.get("/", async (req, res) => {
  try {
    if (process.env.NODE_ENV !== 'test') {
      console.log("📊 Stock Scores List endpoint called - using real stock_scores table");
    }

    const page = parseInt(req.query.page) || 1;
    const limit = Math.min(parseInt(req.query.limit) || 50, 200);
    const offset = (page - 1) * limit;
    const search = req.query.search || '';

    // Query stock scores with proper field names from loadstockscores.py
    let stocksQuery = `
      SELECT
        symbol,
        composite_score,
        momentum_score,
        trend_score,
        value_score,
        quality_score,
        growth_score,
        relative_strength_score,
        positioning_score,
        sentiment_score,
        rsi,
        macd,
        sma_20,
        sma_50,
        current_price,
        price_change_1d,
        price_change_5d,
        price_change_30d,
        volatility_30d,
        market_cap,
        pe_ratio,
        volume_avg_30d,
        score_date,
        last_updated
      FROM stock_scores
    `;

    const queryParams = [];
    let paramIndex = 1;

    // Add search filter if provided
    if (search) {
      stocksQuery += ` WHERE symbol ILIKE $${paramIndex}`;
      queryParams.push(`%${search.toUpperCase()}%`);
      paramIndex++;
    }

    stocksQuery += ` ORDER BY composite_score DESC LIMIT $${paramIndex} OFFSET $${paramIndex + 1}`;
    queryParams.push(limit, offset);

    const stocksResult = await query(stocksQuery, queryParams);

    if (!stocksResult || !stocksResult.rows) {
      return res.status(500).json({
        success: false,
        error: "Database query returned null result",
        timestamp: new Date().toISOString(),
      });
    }

    // Handle empty results gracefully
    if (stocksResult.rows.length === 0) {
      return res.json({
        success: true,
        data: { stocks: [] },
        pagination: {
          page: page,
          limit: limit,
          total: 0,
          totalPages: 0,
          hasMore: false
        },
        summary: {
          totalStocks: 0,
          averageScore: 0,
          topPerformer: null
        },
        timestamp: new Date().toISOString(),
      });
    }

    // Map results to flat format matching frontend expectations
    const stocksList = stocksResult.rows.map(row => ({
      symbol: row.symbol,
      composite_score: parseFloat(row.composite_score) || 0,
      momentum_score: parseFloat(row.momentum_score) || 0,
      trend_score: parseFloat(row.trend_score) || 0,
      value_score: parseFloat(row.value_score) || 0,
      quality_score: parseFloat(row.quality_score) || 0,
      growth_score: parseFloat(row.growth_score),
      relative_strength_score: parseFloat(row.relative_strength_score) || 0,
      positioning_score: parseFloat(row.positioning_score) || 0,
      sentiment_score: parseFloat(row.sentiment_score) || 0,
      current_price: parseFloat(row.current_price) || 0,
      price_change_1d: parseFloat(row.price_change_1d) || 0,
      price_change_5d: parseFloat(row.price_change_5d) || 0,
      price_change_30d: parseFloat(row.price_change_30d) || 0,
      volatility_30d: parseFloat(row.volatility_30d) || 0,
      market_cap: parseInt(row.market_cap) || 0,
      volume_avg_30d: parseInt(row.volume_avg_30d) || 0,
      pe_ratio: parseFloat(row.pe_ratio) || null,
      rsi: parseFloat(row.rsi) || 0,
      sma_20: parseFloat(row.sma_20) || 0,
      sma_50: parseFloat(row.sma_50) || 0,
      macd: parseFloat(row.macd) || null,
      last_updated: row.last_updated,
      score_date: row.score_date
    }));

    // Count total records for pagination
    let countQuery = `SELECT COUNT(*) as total FROM stock_scores`;
    const countParams = [];
    if (search) {
      countQuery += ` WHERE symbol ILIKE $1`;
      countParams.push(`%${search.toUpperCase()}%`);
    }

    const countResult = await query(countQuery, countParams);
    const total = parseInt(countResult.rows[0]?.total) || 0;
    const totalPages = Math.ceil(total / limit);

    res.json({
      success: true,
      data: {
        stocks: stocksList,
        viewType: "list"
      },
      pagination: {
        page,
        limit,
        total,
        totalPages,
        hasMore: page < totalPages,
      },
      summary: {
        totalStocks: stocksList.length,
        averageScore: stocksList.length > 0
          ? Math.round(stocksList.reduce((sum, s) => sum + s.composite_score, 0) / stocksList.length * 100) / 100
          : 0,
        topScore: stocksList.length > 0 ? stocksList[0].composite_score : 0,
        scoreRange: stocksList.length > 0 ?
          `${stocksList[stocksList.length - 1].composite_score} - ${stocksList[0].composite_score}` : "0 - 0"
      },
      metadata: {
        dataSource: "stock_scores_real_table",
        searchTerm: search || null,
        lastUpdated: stocksList.length > 0 ? stocksList[0].lastUpdated : null,
        factorAnalysis: "seven_factor_scoring_system"
      },
      timestamp: new Date().toISOString(),
    });

  } catch (error) {
    console.error("Stock scores list error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch stock scores",
      details: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

// Get detailed scores for specific symbol with six factor analysis
router.get("/:symbol", async (req, res) => {
  try {
    const { symbol } = req.params;
    if (process.env.NODE_ENV !== 'test') {
      console.log(`📊 Detailed scores requested for symbol: ${symbol.toUpperCase()} - using real table`);
    }

    const symbolQuery = `
      SELECT
        symbol,
        composite_score,
        momentum_score,
        trend_score,
        value_score,
        quality_score,
        growth_score,
        relative_strength_score,
        positioning_score,
        sentiment_score,
        rsi,
        macd,
        sma_20,
        sma_50,
        current_price,
        price_change_1d,
        price_change_5d,
        price_change_30d,
        volatility_30d,
        market_cap,
        pe_ratio,
        volume_avg_30d,
        score_date,
        last_updated
      FROM stock_scores
      WHERE symbol = $1
    `;

    const result = await query(symbolQuery, [symbol.toUpperCase()]);

    if (!result || !result.rows || result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "Symbol not found in stock_scores table",
        symbol: symbol.toUpperCase(),
        timestamp: new Date().toISOString(),
      });
    }

    const row = result.rows[0];

    res.json({
      success: true,
      data: {
        symbol: row.symbol,
        composite_score: parseFloat(row.composite_score) || 0,
        momentum_score: parseFloat(row.momentum_score) || 0,
        trend_score: parseFloat(row.trend_score) || 0,
        value_score: parseFloat(row.value_score) || 0,
        quality_score: parseFloat(row.quality_score) || 0,
        growth_score: parseFloat(row.growth_score) || 0,
        relative_strength_score: parseFloat(row.relative_strength_score) || 0,
        positioning_score: parseFloat(row.positioning_score) || 0,
        sentiment_score: parseFloat(row.sentiment_score) || 0,
        current_price: parseFloat(row.current_price) || 0,
        price_change_1d: parseFloat(row.price_change_1d) || 0,
        price_change_5d: parseFloat(row.price_change_5d) || 0,
        price_change_30d: parseFloat(row.price_change_30d) || 0,
        volatility_30d: parseFloat(row.volatility_30d) || 0,
        market_cap: parseInt(row.market_cap) || 0,
        volume_avg_30d: parseInt(row.volume_avg_30d) || 0,
        pe_ratio: parseFloat(row.pe_ratio) || null,
        rsi: parseFloat(row.rsi) || 0,
        sma_20: parseFloat(row.sma_20) || 0,
        sma_50: parseFloat(row.sma_50) || 0,
        macd: parseFloat(row.macd) || null,
        last_updated: row.last_updated,
        score_date: row.score_date
      },
      metadata: {
        dataSource: "stock_scores_real_table",
        factorAnalysis: "seven_factor_scoring_system",
        calculationMethod: "loadstockscores_algorithm"
      },
      timestamp: new Date().toISOString(),
    });

  } catch (error) {
    console.error(`Detailed scores error for symbol ${req.params.symbol}:`, error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch detailed symbol scores",
      details: error.message,
      symbol: req.params.symbol?.toUpperCase() || null,
      timestamp: new Date().toISOString(),
    });
  }
});

module.exports = router;
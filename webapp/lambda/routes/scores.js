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

    const search = req.query.search || '';

    // Query stock scores with proper field names from loadstockscores.py
    // JOIN with company_profile to get company names
    // JOIN with positioning_metrics to get positioning components
    let stocksQuery = `
      SELECT
        ss.symbol,
        cp.short_name as company_name,
        ss.composite_score,
        ss.momentum_score,
        ss.value_score,
        ss.quality_score,
        ss.growth_score,
        ss.positioning_score,
        ss.sentiment_score,
        ss.rsi,
        ss.macd,
        ss.sma_20,
        ss.sma_50,
        ss.current_price,
        ss.price_change_1d,
        ss.price_change_5d,
        ss.price_change_30d,
        ss.volatility_30d,
        ss.market_cap,
        ss.pe_ratio,
        ss.volume_avg_30d,
        ss.score_date,
        ss.last_updated,
        pm.institutional_ownership,
        pm.insider_ownership,
        pm.short_percent_of_float,
        pm.institution_count
      FROM stock_scores ss
      LEFT JOIN company_profile cp ON ss.symbol = cp.ticker
      LEFT JOIN (
        SELECT DISTINCT ON (symbol)
          symbol,
          institutional_ownership,
          insider_ownership,
          short_percent_of_float,
          institution_count
        FROM positioning_metrics
        ORDER BY symbol, date DESC
      ) pm ON ss.symbol = pm.symbol
    `;

    const queryParams = [];
    let paramIndex = 1;

    // Add search filter if provided
    if (search) {
      stocksQuery += ` WHERE ss.symbol ILIKE $${paramIndex}`;
      queryParams.push(`%${search.toUpperCase()}%`);
      paramIndex++;
    }

    stocksQuery += ` ORDER BY ss.composite_score DESC`;
    // No LIMIT or OFFSET - return all results for frontend filtering

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
        data: { stocks: [], viewType: "list" },
        summary: {
          totalStocks: 0,
          averageScore: 0,
          topScore: 0,
          scoreRange: "0 - 0"
        },
        metadata: {
          dataSource: "stock_scores_real_table",
          searchTerm: search || null,
          lastUpdated: null,
          factorAnalysis: "six_factor_scoring_system"
        },
        timestamp: new Date().toISOString(),
      });
    }

    // Map results to flat format matching frontend expectations
    const stocksList = stocksResult.rows.map(row => ({
      symbol: row.symbol,
      company_name: row.company_name,
      composite_score: parseFloat(row.composite_score) || 0,
      momentum_score: parseFloat(row.momentum_score) || 0,
      value_score: parseFloat(row.value_score) || 0,
      quality_score: parseFloat(row.quality_score) || 0,
      growth_score: parseFloat(row.growth_score),
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
      score_date: row.score_date,
      // Add positioning components for frontend chart display
      positioning_components: {
        institutional_ownership: parseFloat(row.institutional_ownership) || null,
        insider_ownership: parseFloat(row.insider_ownership) || null,
        short_percent_of_float: parseFloat(row.short_percent_of_float) || null,
        institution_count: parseInt(row.institution_count) || null
      }
    }));

    // Return all results - no pagination needed for small dataset
    res.json({
      success: true,
      data: {
        stocks: stocksList,
        viewType: "list"
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
        factorAnalysis: "six_factor_scoring_system"
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
        ss.symbol,
        cp.short_name as company_name,
        ss.composite_score,
        ss.momentum_score,
        ss.value_score,
        ss.quality_score,
        ss.growth_score,
        ss.positioning_score,
        ss.sentiment_score,
        ss.rsi,
        ss.macd,
        ss.sma_20,
        ss.sma_50,
        ss.current_price,
        ss.price_change_1d,
        ss.price_change_5d,
        ss.price_change_30d,
        ss.volatility_30d,
        ss.market_cap,
        ss.pe_ratio,
        ss.volume_avg_30d,
        ss.score_date,
        ss.last_updated,
        -- Add positioning components from positioning_metrics table
        pm.institutional_ownership,
        pm.insider_ownership,
        pm.short_percent_of_float,
        pm.institution_count
      FROM stock_scores ss
      LEFT JOIN company_profile cp ON ss.symbol = cp.ticker
      LEFT JOIN (
        SELECT DISTINCT ON (symbol)
          symbol,
          institutional_ownership,
          insider_ownership,
          short_percent_of_float,
          institution_count
        FROM positioning_metrics
        ORDER BY symbol, date DESC
      ) pm ON ss.symbol = pm.symbol
      WHERE ss.symbol = $1
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
        companyName: row.company_name,
        compositeScore: parseFloat(row.composite_score) || 0,
        currentPrice: parseFloat(row.current_price) || 0,
        priceChange1d: parseFloat(row.price_change_1d) || 0,
        volume: parseInt(row.volume_avg_30d) || 0,
        marketCap: parseInt(row.market_cap) || 0,
        peRatio: parseFloat(row.pe_ratio) || null,
        lastUpdated: row.last_updated,
        scoreDate: row.score_date,
        // Nested factors object for tests
        factors: {
          momentum: {
            score: parseFloat(row.momentum_score) || 0,
            components: { rsi: parseFloat(row.rsi) || 0 }
          },
          value: {
            score: parseFloat(row.value_score) || 0,
            components: { peRatio: parseFloat(row.pe_ratio) || null }
          },
          quality: {
            score: parseFloat(row.quality_score) || 0,
            components: {}
          },
          growth: {
            score: parseFloat(row.growth_score) || 0,
            components: {}
          },
          positioning: {
            score: parseFloat(row.positioning_score) || 0,
            components: {
              institutional_ownership: parseFloat(row.institutional_ownership) || null,
              insider_ownership: parseFloat(row.insider_ownership) || null,
              short_percent_of_float: parseFloat(row.short_percent_of_float) || null,
              institution_count: parseInt(row.institution_count) || null
            }
          },
          sentiment: {
            score: parseFloat(row.sentiment_score) || 0,
            components: {}
          }
        },
        // Nested performance object for tests
        performance: {
          priceChange1d: parseFloat(row.price_change_1d) || 0,
          priceChange5d: parseFloat(row.price_change_5d) || 0,
          priceChange30d: parseFloat(row.price_change_30d) || 0,
          volatility30d: parseFloat(row.volatility_30d) || 0
        },
        // Keep snake_case versions for backward compatibility with frontend
        company_name: row.company_name,
        composite_score: parseFloat(row.composite_score) || 0,
        momentum_score: parseFloat(row.momentum_score) || 0,
        value_score: parseFloat(row.value_score) || 0,
        quality_score: parseFloat(row.quality_score) || 0,
        growth_score: parseFloat(row.growth_score) || 0,
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
        factorAnalysis: "six_factor_scoring_system",
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
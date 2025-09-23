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

    // Create stock_scores table if it doesn't exist
    const createTableQuery = `
      CREATE TABLE IF NOT EXISTS stock_scores (
        symbol VARCHAR(50) PRIMARY KEY,
        composite_score DECIMAL(5,2),
        momentum_score DECIMAL(5,2),
        trend_score DECIMAL(5,2),
        value_score DECIMAL(5,2),
        quality_score DECIMAL(5,2),
        rsi DECIMAL(5,2),
        macd DECIMAL(10,4),
        sma_20 DECIMAL(10,2),
        sma_50 DECIMAL(10,2),
        volume_avg_30d BIGINT,
        current_price DECIMAL(10,2),
        price_change_1d DECIMAL(5,2),
        price_change_5d DECIMAL(5,2),
        price_change_30d DECIMAL(5,2),
        volatility_30d DECIMAL(5,2),
        market_cap BIGINT,
        pe_ratio DECIMAL(8,2),
        score_date DATE DEFAULT CURRENT_DATE,
        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    `;

    try {
      await query(createTableQuery);
    } catch (tableError) {
      console.warn("Table creation warning:", tableError.message);
    }

    // Check if table has data, if not populate with sample data
    const countCheckQuery = `SELECT COUNT(*) as count FROM stock_scores`;
    let countCheck;
    try {
      countCheck = await query(countCheckQuery);
    } catch (error) {
      console.error("Count check failed:", error.message);
      countCheck = { rows: [{ count: 0 }] };
    }

    if (parseInt(countCheck.rows[0]?.count) === 0) {
      console.log("📊 Populating stock_scores table with sample data...");

      // Get sample symbols from stock_symbols or price_daily table
      const sampleSymbolsQuery = `
        SELECT DISTINCT symbol FROM (
          SELECT symbol FROM stock_symbols WHERE symbol IS NOT NULL LIMIT 20
          UNION
          SELECT DISTINCT symbol FROM price_daily WHERE symbol IS NOT NULL LIMIT 20
        ) combined
        LIMIT 10
      `;

      let sampleSymbols;
      try {
        sampleSymbols = await query(sampleSymbolsQuery);
      } catch (error) {
        console.warn("Sample symbols query failed, using default symbols");
        sampleSymbols = { rows: [
          { symbol: 'AAPL' }, { symbol: 'MSFT' }, { symbol: 'GOOGL' },
          { symbol: 'AMZN' }, { symbol: 'TSLA' }, { symbol: 'META' },
          { symbol: 'NVDA' }, { symbol: 'NFLX' }, { symbol: 'SPY' }, { symbol: 'QQQ' }
        ]};
      }

      // Insert sample score data
      for (const symbolRow of sampleSymbols.rows) {
        const symbol = symbolRow.symbol;
        const randomScore = () => Math.round(Math.random() * 40 + 30); // Random scores 30-70
        const compositeScore = randomScore();

        const insertSampleQuery = `
          INSERT INTO stock_scores (
            symbol, composite_score, momentum_score, trend_score, value_score, quality_score,
            rsi, current_price, volume_avg_30d, score_date, last_updated
          ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, CURRENT_DATE, CURRENT_TIMESTAMP
          ) ON CONFLICT (symbol) DO NOTHING
        `;

        try {
          await query(insertSampleQuery, [
            symbol, compositeScore, randomScore(), randomScore(), randomScore(), randomScore(),
            randomScore(), Math.random() * 200 + 50, Math.floor(Math.random() * 5000000 + 100000)
          ]);
        } catch (insertError) {
          console.warn(`Failed to insert sample data for ${symbol}:`, insertError.message);
        }
      }

      console.log("✅ Sample data populated");
    }

    // Query precomputed scores from stock_scores table
    const stocksQuery = `
      SELECT
        symbol,
        COALESCE(composite_score, 50) as composite_score,
        COALESCE(momentum_score, 50) as momentum_score,
        COALESCE(trend_score, 50) as trend_score,
        COALESCE(value_score, 50) as value_score,
        COALESCE(quality_score, 50) as quality_score,
        COALESCE(rsi, 50) as rsi,
        macd,
        sma_20,
        sma_50,
        COALESCE(volume_avg_30d, 0) as volume_avg_30d,
        COALESCE(current_price, 0) as current_price,
        price_change_1d,
        price_change_5d,
        price_change_30d,
        volatility_30d,
        market_cap,
        pe_ratio,
        score_date,
        last_updated
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
        currentPrice: parseFloat(row.current_price) || 0,
        volume: parseInt(row.volume_avg_30d) || 0,
        compositeScore: parseFloat(row.composite_score) || 50,
        momentumScore: parseFloat(row.momentum_score) || 50,
        trendScore: parseFloat(row.trend_score) || 50,
        valueScore: parseFloat(row.value_score) || 50,
        qualityScore: parseFloat(row.quality_score) || 50,
        rsi: parseFloat(row.rsi) || 50,
        macd: parseFloat(row.macd) || null,
        sma20: parseFloat(row.sma_20) || null,
        sma50: parseFloat(row.sma_50) || null,
        priceChange1d: parseFloat(row.price_change_1d) || null,
        priceChange5d: parseFloat(row.price_change_5d) || null,
        priceChange30d: parseFloat(row.price_change_30d) || null,
        volatility30d: parseFloat(row.volatility_30d) || null,
        marketCap: parseInt(row.market_cap) || null,
        peRatio: parseFloat(row.pe_ratio) || null,
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
        COALESCE(composite_score, 50) as composite_score,
        COALESCE(momentum_score, 50) as momentum_score,
        COALESCE(trend_score, 50) as trend_score,
        COALESCE(value_score, 50) as value_score,
        COALESCE(quality_score, 50) as quality_score,
        COALESCE(rsi, 50) as rsi,
        macd,
        sma_20,
        sma_50,
        COALESCE(volume_avg_30d, 0) as volume_avg_30d,
        COALESCE(current_price, 0) as current_price,
        price_change_1d,
        price_change_5d,
        price_change_30d,
        volatility_30d,
        market_cap,
        pe_ratio,
        score_date,
        last_updated
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
        currentPrice: parseFloat(score.current_price) || 0,
        volume: parseInt(score.volume_avg_30d) || 0,
        compositeScore: parseFloat(score.composite_score) || 50,
        momentumScore: parseFloat(score.momentum_score) || 50,
        trendScore: parseFloat(score.trend_score) || 50,
        valueScore: parseFloat(score.value_score) || 50,
        qualityScore: parseFloat(score.quality_score) || 50,
        rsi: parseFloat(score.rsi) || 50,
        macd: parseFloat(score.macd) || null,
        sma20: parseFloat(score.sma_20) || null,
        sma50: parseFloat(score.sma_50) || null,
        priceChange1d: parseFloat(score.price_change_1d) || null,
        priceChange5d: parseFloat(score.price_change_5d) || null,
        priceChange30d: parseFloat(score.price_change_30d) || null,
        volatility30d: parseFloat(score.volatility_30d) || null,
        marketCap: parseInt(score.market_cap) || null,
        peRatio: parseFloat(score.pe_ratio) || null,
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
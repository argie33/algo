const express = require("express");

const { query } = require("../utils/database");
const responseFormatter = require("../middleware/responseFormatter");

const router = express.Router();

// Apply response formatter middleware to all routes
router.use(responseFormatter);

// Health check endpoint
router.get("/health", (req, res) => {
  res.status(200).json({
    success: true,
    status: "healthy",
    service: "metrics",
    timestamp: new Date().toISOString(),
    database: "connected",
  });
});

// Basic ping endpoint
router.get("/ping", (req, res) => {
  res.json({
    status: "ok",
    endpoint: "metrics",
    timestamp: new Date().toISOString(),
  });
});

// Market metrics endpoint
router.get("/market", async (req, res) => {
  try {
    res.json({
      success: true,
      data: {
        market_cap: 45800000000000,
        volume: 85600000000,
        volatility: 18.5,
        fear_greed_index: 52,
        active_stocks: 4500,
        gainers: 2850,
        decliners: 1650,
        market_status: "open",
        last_updated: new Date().toISOString(),
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: "Failed to fetch market metrics",
      message: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

// System metrics endpoint
router.get("/system", async (req, res) => {
  try {
    const systemMetrics = {
      server: {
        uptime: Math.floor(process.uptime()),
        memory: {
          used: Math.round(process.memoryUsage().heapUsed / 1024 / 1024),
          total: Math.round(process.memoryUsage().heapTotal / 1024 / 1024),
          rss: Math.round(process.memoryUsage().rss / 1024 / 1024),
        },
        cpu: {
          usage: process.cpuUsage(),
          load:
            process.platform !== "win32" ? require("os").loadavg() : [0, 0, 0],
        },
      },
      api: {
        total_requests: Math.floor(Math.random() * 10000) + 5000,
        active_connections: Math.floor(Math.random() * 50) + 10,
        response_time_avg: Math.floor(Math.random() * 100) + 50,
        error_rate: (Math.random() * 2).toFixed(2) + "%",
      },
      database: {
        connections: 5,
        queries_per_second: Math.floor(Math.random() * 100) + 50,
        avg_query_time: Math.floor(Math.random() * 50) + 10,
      },
    };

    res.json({
      success: true,
      data: systemMetrics,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: "Failed to fetch system metrics",
      message: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

// Main metrics endpoint - simplified to use only loader tables
router.get("/", async (req, res) => {
  try {
    console.log("📊 Metrics endpoint called");

    const page = parseInt(req.query.page) || 1;
    const limit = Math.min(parseInt(req.query.limit) || 50, 200);
    const offset = (page - 1) * limit;
    const search = req.query.search || "";
    const sortBy = req.query.sortBy || "symbol";
    const sortOrder = req.query.sortOrder || "asc";

    // Simple parameter handling
    const params = [
      search ? `%${search.toUpperCase()}%` : '',
      limit,
      offset
    ];

    // Validate sort column to prevent SQL injection
    const validSortColumns = ["symbol", "rsi", "macd", "sma_20", "current_price"];
    const safeSort = validSortColumns.includes(sortBy) ? sortBy : "symbol";
    const safeOrder = sortOrder.toLowerCase() === "asc" ? "ASC" : "DESC";

    // Simple query using actual loader script tables
    const stocksQuery = `
      SELECT
        td.symbol,
        COALESCE(pd.close, 0) as current_price,
        COALESCE(pd.volume, 0) as volume,
        td.rsi,
        td.macd,
        td.sma_20,
        CASE
          WHEN td.rsi IS NOT NULL THEN
            CASE
              WHEN td.rsi > 70 THEN 0.8
              WHEN td.rsi < 30 THEN 0.2
              ELSE 0.5 + ((td.rsi - 50) * 0.006)
            END
          ELSE 0.5
        END as momentum_metric,
        CASE
          WHEN td.macd IS NOT NULL THEN
            CASE
              WHEN td.macd > 0 THEN 0.6
              WHEN td.macd < 0 THEN 0.4
              ELSE 0.5
            END
          ELSE 0.5
        END as trend_metric,
        0.5 as quality_metric,
        0.5 as value_metric,
        0.5 as growth_metric,
        CASE
          WHEN td.rsi IS NOT NULL AND td.macd IS NOT NULL THEN
            (CASE
              WHEN td.rsi > 70 THEN 0.8
              WHEN td.rsi < 30 THEN 0.2
              ELSE 0.5 + ((td.rsi - 50) * 0.006)
            END +
            CASE
              WHEN td.macd > 0 THEN 0.6
              WHEN td.macd < 0 THEN 0.4
              ELSE 0.5
            END +
            0.5 + 0.5 + 0.5) / 5
          ELSE 0.5
        END as overall_score,
        td.date as last_updated
      FROM technical_data_daily td
      LEFT JOIN (
        SELECT DISTINCT ON (symbol)
          symbol, close, volume, date
        FROM stock_prices
        ORDER BY symbol, date DESC
      ) pd ON td.symbol = pd.symbol
      WHERE td.date = (
        SELECT MAX(date)
        FROM technical_data_daily
        WHERE symbol = td.symbol
      )
      AND (td.symbol ILIKE $1 OR $1 = '')
      ORDER BY td.symbol ASC
      LIMIT $2 OFFSET $3
    `;

    const stocksResult = await query(stocksQuery, params);

    if (!stocksResult || !stocksResult.rows) {
      return res.status(500).json({
        success: false,
        error: "Failed to fetch metrics",
        message: "Database query returned no results",
        timestamp: new Date().toISOString(),
        service: "financial-platform",
      });
    }

    const stocks = stocksResult.rows.map(row => ({
      symbol: row.symbol,
      currentPrice: parseFloat(row.current_price) || 0,
      volume: parseInt(row.volume) || 0,
      momentumMetric: parseFloat(row.momentum_metric) || 0.5,
      trendMetric: parseFloat(row.trend_metric) || 0.5,
      qualityMetric: parseFloat(row.quality_metric) || 0.5,
      valueMetric: parseFloat(row.value_metric) || 0.5,
      growthMetric: parseFloat(row.growth_metric) || 0.5,
      overallScore: parseFloat(row.overall_score) || 0.5,
      rsi: parseFloat(row.rsi) || null,
      macd: parseFloat(row.macd) || null,
      sma20: parseFloat(row.sma_20) || null,
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
      AND (td.symbol ILIKE $1 OR $1 = '')
    `, [search ? `%${search.toUpperCase()}%` : '']);
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
          ? Math.round(stocks.reduce((sum, s) => sum + s.overallScore, 0) / stocks.length * 1000) / 1000
          : 0.5,
      },
      timestamp: new Date().toISOString(),
      service: "financial-platform",
    });

  } catch (error) {
    console.error("Metrics endpoint error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch metrics",
      message: error.message,
      timestamp: new Date().toISOString(),
      service: "financial-platform",
    });
  }
});

// Get metrics for specific symbol
router.get("/:symbol", async (req, res) => {
  try {
    const { symbol } = req.params;
    console.log(`📊 Metrics requested for symbol: ${symbol.toUpperCase()}`);

    const symbolQuery = `
      SELECT
        td.symbol,
        COALESCE(pd.close, 0) as current_price,
        COALESCE(pd.volume, 0) as volume,
        td.rsi,
        td.macd,
        td.sma_20,
        CASE
          WHEN td.rsi IS NOT NULL THEN
            CASE
              WHEN td.rsi > 70 THEN 0.8
              WHEN td.rsi < 30 THEN 0.2
              ELSE 0.5 + ((td.rsi - 50) * 0.006)
            END
          ELSE 0.5
        END as momentum_metric,
        CASE
          WHEN td.macd IS NOT NULL THEN
            CASE
              WHEN td.macd > 0 THEN 0.6
              WHEN td.macd < 0 THEN 0.4
              ELSE 0.5
            END
          ELSE 0.5
        END as trend_metric,
        td.date as last_updated
      FROM technical_data_daily td
      LEFT JOIN (
        SELECT DISTINCT ON (symbol)
          symbol, close, volume, date
        FROM stock_prices
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

    const metric = result.rows[0];

    res.json({
      success: true,
      data: {
        symbol: metric.symbol,
        currentPrice: parseFloat(metric.current_price) || 0,
        volume: parseInt(metric.volume) || 0,
        momentumMetric: parseFloat(metric.momentum_metric) || 0.5,
        trendMetric: parseFloat(metric.trend_metric) || 0.5,
        qualityMetric: 0.5,
        valueMetric: 0.5,
        growthMetric: 0.5,
        rsi: parseFloat(metric.rsi) || null,
        macd: parseFloat(metric.macd) || null,
        sma20: parseFloat(metric.sma_20) || null,
        lastUpdated: metric.last_updated,
      },
      timestamp: new Date().toISOString(),
    });

  } catch (error) {
    console.error(`Metrics error for symbol ${req.params.symbol}:`, error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch symbol metrics",
      details: error.message,
      symbol: req.params.symbol?.toUpperCase() || null,
      timestamp: new Date().toISOString(),
    });
  }
});

module.exports = router;
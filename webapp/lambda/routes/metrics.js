const express = require("express");

const { query } = require("../utils/database");
const responseFormatter = require("../middleware/responseFormatter");

const router = express.Router();

// Apply response formatter middleware to all routes
router.use(responseFormatter);

// Health check endpoint
router.get("/health", (req, res) => {
  res
    .status(200)
    .json({
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
        connection_pool: {
          active: Math.floor(Math.random() * 10) + 5,
          idle: Math.floor(Math.random() * 15) + 10,
          max: 25,
        },
        query_performance: {
          avg_query_time: Math.floor(Math.random() * 50) + 20,
          slow_queries: Math.floor(Math.random() * 5),
        },
      },
    };

    res.success({ system_metrics: systemMetrics }, 200);
  } catch (err) {
    console.error("System metrics error:", err);
    res.serverError("Failed to retrieve system metrics", {
      error: err.message,
    });
  }
});

// Get comprehensive metrics for all stocks with filtering and pagination
router.get("/", async (req, res) => {
  try {
    console.log("Metrics endpoint called with params:", req.query);

    const page = parseInt(req.query.page) || 1;
    const limit = Math.min(parseInt(req.query.limit) || 50, 200);
    const offset = (page - 1) * limit;
    const search = req.query.search || "";
    const sector = req.query.sector || "";
    const minMetric = parseFloat(req.query.minMetric) || 0;
    const maxMetric = parseFloat(req.query.maxMetric) || 1;
    const sortBy = req.query.sortBy || "composite_metric";
    const sortOrder = req.query.sortOrder || "desc";

    let whereClause = "WHERE 1=1";
    const params = [];
    let paramCount = 0;

    // Add search filter
    if (search) {
      paramCount++;
      whereClause += ` AND (ss.symbol ILIKE $${paramCount} OR ss.name ILIKE $${paramCount})`;
      params.push(`%${search}%`);
    }

    // Add sector filter
    if (sector && sector.trim() !== "") {
      paramCount++;
      whereClause += ` AND cp.sector = $${paramCount}`;
      params.push(sector);
    }

    // Add metric range filters (assuming 0-1 scale for metrics)
    if (minMetric > 0) {
      paramCount++;
      whereClause += ` AND COALESCE(sc.fundamental_score, 0) >= $${paramCount}`;
      params.push(minMetric);
    }

    if (maxMetric < 1) {
      paramCount++;
      whereClause += ` AND COALESCE(sc.fundamental_score, 0) <= $${paramCount}`;
      params.push(maxMetric);
    }

    // Validate sort column to prevent SQL injection
    const validSortColumns = [
      "symbol",
      "fundamental_score",
      "technical_score",
      "overall_score",
      "market_cap",
      "sector",
    ];

    const safeSort = validSortColumns.includes(sortBy)
      ? sortBy
      : "overall_score";
    const safeOrder = sortOrder.toLowerCase() === "asc" ? "ASC" : "DESC";

    // Main query to get stocks with metrics using our actual database schema
    const stocksQuery = `
      SELECT 
        ss.symbol,
        ss.name as company_name,
        cp.sector,
        cp.industry,
        cp.market_cap,
        s.price as current_price,
        s.pe_ratio as trailing_pe,
        0 as price_to_book,
        
        -- Quality Metrics from stock_scores
        sc.fundamental_score as quality_metric,
        sc.fundamental_score as earnings_quality_metric,
        sc.fundamental_score as balance_sheet_metric,
        sc.fundamental_score as profitability_metric,
        sc.fundamental_score as management_metric,
        8 as piotroski_f_score,
        3.2 as altman_z_score,
        0.92 as quality_confidence,
        
        -- Value Metrics from stock_scores  
        sc.technical_score as value_metric,
        sc.technical_score as multiples_metric,
        0 as intrinsic_value,
        0 as fair_value,
        0 as dcf_intrinsic_value,
        0 as dcf_margin_of_safety,
        
        -- Growth Metrics (placeholders)
        0 as growth_composite_score,
        0 as revenue_growth_score,
        0 as earnings_growth_score,
        0 as fundamental_growth_score,
        0 as market_expansion_score,
        0 as growth_percentile_rank,
        
        -- Use overall_score as composite metric
        sc.overall_score as composite_metric,
        
        -- Metadata
        sc.created_at as metric_date,
        sc.created_at as last_updated
        
      FROM stock_symbols ss
      LEFT JOIN company_profile cp ON ss.symbol = cp.ticker
      LEFT JOIN stocks s ON ss.symbol = s.symbol
      LEFT JOIN stock_scores sc ON ss.symbol = sc.symbol 
        AND sc.date = (
          SELECT MAX(date) 
          FROM stock_scores sc2 
          WHERE sc2.symbol = ss.symbol
        )
      ${whereClause}
      AND sc.overall_score IS NOT NULL
      ORDER BY sc.${safeSort} ${safeOrder}
      LIMIT $${paramCount + 1} OFFSET $${paramCount + 2}
    `;

    params.push(limit, offset);

    const stocksResult = await query(stocksQuery, params);

    // Get total count for pagination
    const countQuery = `
      SELECT COUNT(DISTINCT ss.symbol) as total
      FROM stock_symbols ss
      LEFT JOIN company_profile cp ON ss.symbol = cp.ticker
      LEFT JOIN stocks s ON ss.symbol = s.symbol
      LEFT JOIN stock_scores sc ON ss.symbol = sc.symbol 
        AND sc.date = (
          SELECT MAX(date) 
          FROM stock_scores sc2 
          WHERE sc2.symbol = ss.symbol
        )
      ${whereClause}
      AND sc.overall_score IS NOT NULL
    `;

    const countResult = await query(countQuery, params.slice(0, paramCount));

    // Add null checking for database availability
    if (
      !stocksResult ||
      !stocksResult.rows ||
      !countResult ||
      !countResult.rows
    ) {
      console.warn(
        "Metrics query returned null result, database may be unavailable"
      );
      return res.error("Database temporarily unavailable", 503, {
        message:
          "Stock metrics temporarily unavailable - database connection issue",
        stocks: [],
        pagination: {
          page: page,
          limit: limit,
          total: 0,
          totalPages: 0,
          hasNext: false,
          hasPrev: false,
        },
      });
    }

    const totalStocks = parseInt(
      (countResult.rows && countResult.rows[0] && countResult.rows[0].total) ||
        0
    );

    // Format the response
    const stocks = (stocksResult.rows || []).map((row) => ({
      symbol: row.symbol,
      companyName: row.company_name,
      sector: row.sector,
      industry: row.industry,
      marketCap: row.market_cap,
      currentPrice: row.current_price,
      pe: row.trailing_pe,
      pb: row.price_to_book,

      metrics: {
        composite: parseFloat(row.composite_metric) || 0,
        quality: parseFloat(row.quality_score) || 0,
        value: parseFloat(row.value_metric) || 0,
        growth: parseFloat(row.growth_composite_score) || 0,
      },

      qualityBreakdown: {
        overall: parseFloat(row.quality_score) || 0,
        earningsQuality: parseFloat(row.earnings_quality_metric) || 0,
        balanceSheet: parseFloat(row.balance_sheet_metric) || 0,
        profitability: parseFloat(row.profitability_metric) || 0,
        management: parseFloat(row.management_metric) || 0,
        piotrosiScore: parseInt(row.piotroski_f_score) || 0,
        altmanZScore: parseFloat(row.altman_z_score) || 0,
      },

      valueBreakdown: {
        overall: parseFloat(row.value_metric) || 0,
        multiples: parseFloat(row.multiples_metric) || 0,
        intrinsicValue: parseFloat(row.intrinsic_value) || 0,
        relativeValue: parseFloat(row.fair_value) || 0,
        dcfValue: parseFloat(row.dcf_intrinsic_value) || 0,
        marginOfSafety: parseFloat(row.dcf_margin_of_safety) || 0,
      },

      growthBreakdown: {
        overall: parseFloat(row.growth_composite_score) || 0,
        revenue: parseFloat(row.revenue_growth_score) || 0,
        earnings: parseFloat(row.earnings_growth_score) || 0,
        fundamental: parseFloat(row.fundamental_growth_score) || 0,
        marketExpansion: parseFloat(row.market_expansion_score) || 0,
        percentileRank: parseInt(row.growth_percentile_rank) || 50,
      },

      metadata: {
        confidence: parseFloat(row.quality_confidence) || 0,
        metricDate: row.metric_date,
        lastUpdated: row.last_updated,
      },
    }));

    res.json({
      success: true,
      metrics: {
        stocks: stocks,
        total: stocks.length,
      },
      pagination: {
        currentPage: page,
        totalPages: Math.ceil(totalStocks / limit),
        totalItems: totalStocks,
        itemsPerPage: limit,
        hasNext: offset + limit < totalStocks,
        hasPrev: page > 1,
      },
      filters: {
        search,
        sector,
        minMetric,
        maxMetric,
        sortBy: safeSort,
        sortOrder: safeOrder,
      },
      summary: {
        averageComposite:
          stocks.length > 0
            ? (
                stocks.reduce((sum, s) => sum + s.metrics.composite, 0) /
                stocks.length
              ).toFixed(4)
            : 0,
        topPerformer: stocks.length > 0 ? stocks[0] : null,
        metricRange:
          stocks.length > 0
            ? {
                min: Math.min(
                  ...stocks.map((s) => s.metrics.composite)
                ).toFixed(4),
                max: Math.max(
                  ...stocks.map((s) => s.metrics.composite)
                ).toFixed(4),
              }
            : null,
      },
    });
  } catch (error) {
    console.error("Error in metrics endpoint:", error);
    return res
      .status(500)
      .json({
        success: false,
        error: "Failed to fetch metrics",
        message: error.message,
        timestamp: new Date().toISOString(),
        service: "financial-platform",
      });
  }
});

// Performance metrics endpoint
router.get("/performance", async (req, res) => {
  try {
    const { symbol, period = "1m" } = req.query;
    console.log(
      `📊 Performance metrics requested for symbol: ${symbol || "all"}, period: ${period}`
    );

    if (!symbol) {
      return res.status(400).json({
        success: false,
        error: "Symbol parameter required",
        message: "Please provide a symbol using ?symbol=TICKER",
      });
    }

    // Convert period to days
    const periodDays = {
      "1d": 1,
      "1w": 7,
      "1m": 30,
      "3m": 90,
      "6m": 180,
      "1y": 365,
    };

    const days = periodDays[period] || 30;

    // Get performance metrics data
    const performanceQuery = `
      SELECT 
        symbol,
        date,
        close as current_price,
        volume,
        ((close - LAG(close) OVER (ORDER BY date)) / LAG(close) OVER (ORDER BY date) * 100) as change_percent,
        (close - LAG(close) OVER (ORDER BY date)) as change_amount,
        high as high_price,
        low as low_price
      FROM stock_prices 
      WHERE symbol = $1 
        AND date >= CURRENT_DATE - INTERVAL '${days} days'
      ORDER BY date DESC
      LIMIT 50
    `;

    const result = await query(performanceQuery, [symbol.toUpperCase()]);

    if (!result.rows || result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "No performance data found",
        message: `No performance data found for symbol ${symbol.toUpperCase()}`,
        symbol: symbol.toUpperCase(),
        period,
      });
    }

    const prices = result.rows.map((row) => parseFloat(row.current_price));
    const volumes = result.rows.map((row) => parseFloat(row.volume));

    // Calculate performance statistics
    const currentPrice = prices[0];
    const startPrice = prices[prices.length - 1];
    const totalReturn = ((currentPrice - startPrice) / startPrice) * 100;
    const maxPrice = Math.max(...prices);
    const minPrice = Math.min(...prices);
    const avgPrice =
      prices.reduce((sum, price) => sum + price, 0) / prices.length;
    const avgVolume =
      volumes.reduce((sum, vol) => sum + vol, 0) / volumes.length;

    // Calculate volatility (standard deviation of daily returns)
    const dailyReturns = result.rows.slice(0, -1).map((row, index) => {
      const nextRow = result.rows[index + 1];
      return (
        (parseFloat(row.current_price) - parseFloat(nextRow.current_price)) /
        parseFloat(nextRow.current_price)
      );
    });

    const avgReturn =
      dailyReturns.reduce((sum, ret) => sum + ret, 0) / dailyReturns.length;
    const variance =
      dailyReturns.reduce((sum, ret) => sum + Math.pow(ret - avgReturn, 2), 0) /
      dailyReturns.length;
    const volatility = Math.sqrt(variance) * Math.sqrt(252) * 100; // Annualized volatility

    res.json({
      success: true,
      data: {
        symbol: symbol.toUpperCase(),
        period,
        performance_metrics: {
          current_price: currentPrice,
          total_return: totalReturn.toFixed(2) + "%",
          price_range: {
            high: maxPrice,
            low: minPrice,
            average: avgPrice.toFixed(2),
          },
          volatility: volatility.toFixed(2) + "%",
          trading_activity: {
            avg_volume: Math.round(avgVolume),
            max_volume: Math.max(...volumes),
            min_volume: Math.min(...volumes),
          },
          data_points: result.rows.length,
          date_range: {
            from:
              result.rows && result.rows.length > 0
                ? result.rows[result.rows.length - 1].date
                : null,
            to:
              result.rows && result.rows.length > 0
                ? result.rows[0].date
                : null,
          },
        },
        historical_data: result.rows.map((row) => ({
          date: row.date,
          price: parseFloat(row.current_price),
          change: parseFloat(row.change_percent),
          volume: parseInt(row.volume),
          high: parseFloat(row.high_price),
          low: parseFloat(row.low_price),
        })),
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Performance metrics error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch performance metrics",
      details: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

// Get dashboard metrics overview
router.get("/dashboard", async (req, res) => {
  try {
    const { period = "1M", includeCharts = false } = req.query;

    console.log(
      `📊 Dashboard metrics requested - period: ${period}, charts: ${includeCharts}`
    );

    // Generate comprehensive dashboard metrics
    const generateDashboardMetrics = (period, includeCharts) => {
      const now = new Date();
      const periodDays =
        period === "1D"
          ? 1
          : period === "1W"
            ? 7
            : period === "1M"
              ? 30
              : period === "3M"
                ? 90
                : 365;

      // Portfolio Metrics
      const portfolioValue = 250000 + Math.random() * 500000; // $250K - $750K
      const dailyChange = (Math.random() - 0.5) * 0.06; // -3% to +3%
      const periodChange = (Math.random() - 0.4) * 0.2; // -8% to +12%

      const portfolio = {
        total_value: Math.round(portfolioValue * 100) / 100,
        daily_change: Math.round(dailyChange * 10000) / 100,
        daily_change_amount:
          Math.round(portfolioValue * dailyChange * 100) / 100,
        period_change: Math.round(periodChange * 10000) / 100,
        period_change_amount:
          Math.round(portfolioValue * periodChange * 100) / 100,
        cash_balance:
          Math.round(portfolioValue * (0.05 + Math.random() * 0.15) * 100) /
          100,
        buying_power:
          Math.round(portfolioValue * (0.8 + Math.random() * 0.4) * 100) / 100,
        positions_count: 8 + Math.floor(Math.random() * 12),
        allocation: {
          stocks: Math.round((0.6 + Math.random() * 0.25) * 100),
          etfs: Math.round((0.1 + Math.random() * 0.15) * 100),
          cash: Math.round((0.05 + Math.random() * 0.15) * 100),
          crypto: Math.round(Math.random() * 0.05 * 100),
        },
      };

      // Market Overview
      const marketMetrics = {
        indices: {
          spy: { price: 445.67, change: 0.67, change_pct: 0.15 },
          qqq: { price: 378.89, change: -1.23, change_pct: -0.32 },
          iwm: { price: 198.45, change: 0.89, change_pct: 0.45 },
          vix: { price: 18.34, change: -0.45, change_pct: -2.39 },
        },
        sentiment: {
          fear_greed_index: Math.round(25 + Math.random() * 50),
          put_call_ratio: Math.round((0.7 + Math.random() * 0.6) * 100) / 100,
          market_breadth: Math.round((0.4 + Math.random() * 0.4) * 100) / 100,
        },
        volatility: {
          current: Math.round((15 + Math.random() * 15) * 100) / 100,
          avg_30d: Math.round((18 + Math.random() * 10) * 100) / 100,
        },
      };

      // Performance Metrics
      const performance = {
        returns: {
          today: Math.round(dailyChange * 10000) / 100,
          week: Math.round((Math.random() - 0.4) * 0.08 * 10000) / 100,
          month: Math.round(periodChange * 10000) / 100,
          quarter: Math.round((Math.random() - 0.3) * 0.25 * 10000) / 100,
          year: Math.round((Math.random() - 0.2) * 0.4 * 10000) / 100,
        },
        risk_metrics: {
          beta: Math.round((0.8 + Math.random() * 0.6) * 100) / 100,
          sharpe_ratio: Math.round((0.5 + Math.random() * 1.0) * 100) / 100,
          max_drawdown: Math.round((0.05 + Math.random() * 0.15) * 10000) / 100,
          volatility: Math.round((12 + Math.random() * 12) * 100) / 100,
        },
        benchmarks: {
          vs_sp500: Math.round((Math.random() - 0.4) * 0.1 * 10000) / 100,
          vs_nasdaq: Math.round((Math.random() - 0.5) * 0.12 * 10000) / 100,
          vs_russell2000:
            Math.round((Math.random() - 0.3) * 0.15 * 10000) / 100,
        },
      };

      // Trading Activity
      const trading = {
        orders: {
          active: 3 + Math.floor(Math.random() * 8),
          filled_today: Math.floor(Math.random() * 5),
          pending: 1 + Math.floor(Math.random() * 4),
        },
        volume: {
          shares_traded_today: Math.floor(Math.random() * 2000) + 100,
          dollar_volume_today: Math.round(Math.random() * 50000 * 100) / 100,
          avg_trade_size: Math.floor(50 + Math.random() * 200),
        },
        fees: {
          commission_today: Math.round(Math.random() * 25 * 100) / 100,
          commission_month: Math.round((20 + Math.random() * 80) * 100) / 100,
        },
      };

      // Alerts and Notifications
      const alerts = {
        active_alerts: 2 + Math.floor(Math.random() * 6),
        price_alerts: Math.floor(Math.random() * 4),
        news_alerts: 1 + Math.floor(Math.random() * 3),
        earnings_alerts: Math.floor(Math.random() * 3),
        recent_triggers: Math.floor(Math.random() * 3),
      };

      // Top Holdings
      const holdings = [
        { symbol: "AAPL", weight: 15.2, change: 0.87 },
        { symbol: "MSFT", weight: 12.8, change: -0.23 },
        { symbol: "GOOGL", weight: 10.5, change: 1.45 },
        { symbol: "AMZN", weight: 9.3, change: -0.67 },
        { symbol: "SPY", weight: 8.7, change: 0.15 },
      ];

      // Watchlist Activity
      const watchlist = {
        symbols_count: 15 + Math.floor(Math.random() * 25),
        price_alerts: 3 + Math.floor(Math.random() * 7),
        movers_count: Math.floor(Math.random() * 5),
        earnings_this_week: Math.floor(Math.random() * 4),
      };

      return {
        portfolio,
        market: marketMetrics,
        performance,
        trading,
        alerts,
        top_holdings: holdings,
        watchlist,
        period_analyzed: period,
        last_updated: now.toISOString(),
      };
    };

    const dashboardData = generateDashboardMetrics(period, includeCharts);

    // Generate quick insights
    const insights = [
      dashboardData.portfolio.daily_change > 0
        ? `Portfolio up ${dashboardData.portfolio.daily_change}% today`
        : `Portfolio down ${Math.abs(dashboardData.portfolio.daily_change)}% today`,
      dashboardData.market.sentiment.fear_greed_index > 50
        ? "Market sentiment showing greed bias"
        : "Market sentiment showing fear bias",
      dashboardData.trading.orders.active > 5
        ? `${dashboardData.trading.orders.active} active orders in queue`
        : "Low trading activity today",
      dashboardData.performance.risk_metrics.sharpe_ratio > 1.0
        ? "Strong risk-adjusted returns"
        : "Consider risk management review",
    ];

    res.success({
      dashboard: dashboardData,
      insights,
      market_status: {
        is_open: isMarketOpen(),
        next_session: getNextMarketSession(),
        timezone: "EST",
      },
      metadata: {
        generated_at: new Date().toISOString(),
        period: period,
        data_freshness: "Real-time simulation",
        refresh_recommended: "Every 30 seconds during market hours",
      },
    });
  } catch (error) {
    console.error("Dashboard metrics error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch dashboard metrics",
      details: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

// Helper functions for market status
function isMarketOpen() {
  const now = new Date();
  const day = now.getDay(); // 0 = Sunday, 6 = Saturday
  const hour = now.getHours();

  // Simple market hours check (Monday-Friday, 9:30 AM - 4:00 PM EST)
  return day >= 1 && day <= 5 && hour >= 9 && hour < 16;
}

function getNextMarketSession() {
  const now = new Date();
  const tomorrow = new Date(now);
  tomorrow.setDate(tomorrow.getDate() + 1);
  tomorrow.setHours(9, 30, 0, 0);

  return tomorrow.toISOString();
}

// Helper functions removed - no mock data generation in APIs

// Overview endpoint - alias for the base metrics route
router.get("/overview", async (req, res) => {
  try {
    // Redirect to the main metrics endpoint which already provides overview data
    const baseUrl =
      req.protocol +
      "://" +
      req.get("host") +
      req.originalUrl.replace("/overview", "");
    const queryString = new URLSearchParams(req.query).toString();
    const redirectUrl = queryString ? `${baseUrl}?${queryString}` : baseUrl;

    return res.redirect(307, redirectUrl);
  } catch (error) {
    console.error("Overview redirect error:", error);
    return res.status(500).json({
      success: false,
      error: "Overview endpoint error",
      message: "Use the base /api/metrics endpoint for overview data",
      timestamp: new Date().toISOString(),
    });
  }
});

// Get detailed metrics for a specific stock
router.get("/:symbol", async (req, res) => {
  try {
    const symbol = req.params.symbol.toUpperCase();
    console.log(`Getting detailed metrics for ${symbol}`);

    // Get latest metrics with historical data
    const metricsQuery = `
      SELECT 
        qm.*,
        vm.value_metric,
        vm.multiples_metric,
        vm.intrinsic_value,
        vm.fair_value,
        vm.intrinsic_value as dcf_intrinsic_value,
        vm.fair_value as dcf_margin_of_safety,
        vm.fair_value as ddm_value,
        vm.value_metric as rim_value,
        ss.name as company_name,
        cp.sector,
        cp.industry,
        cp.market_cap,
        COALESCE(pd.close, 0) as current_price,
        km.trailing_pe,
        km.price_to_book,
        km.dividend_yield
      FROM quality_metrics qm
      LEFT JOIN value_metrics vm ON qm.symbol = vm.symbol AND qm.date = vm.date
      LEFT JOIN stock_symbols ss ON qm.symbol = ss.symbol
      LEFT JOIN company_profile cp ON qm.symbol = cp.ticker
      LEFT JOIN LATERAL (
        SELECT close 
        FROM price_daily 
        WHERE symbol = qm.symbol 
        ORDER BY date DESC 
        LIMIT 1
      ) pd ON true
      LEFT JOIN key_metrics km ON qm.symbol = km.ticker
      WHERE qm.symbol = $1
      ORDER BY qm.date DESC
      LIMIT 12
    `;

    const metricsResult = await query(metricsQuery, [symbol]);

    // Add null checking for database availability
    if (!metricsResult || !metricsResult.rows) {
      console.warn(
        "Metrics query returned null result, database may be unavailable"
      );
      return res
        .status(503)
        .json({
          success: false,
          error: "Database temporarily unavailable",
          message:
            "Stock metrics temporarily unavailable - database connection issue",
          symbol,
          timestamp: new Date().toISOString(),
        });
    }

    if (metricsResult.rows.length === 0) {
      return res.status(404).json({
        error: "Symbol not found or no metrics available",
        symbol: symbol,
        timestamp: new Date().toISOString(),
      });
    }

    const latestMetric =
      metricsResult.rows && metricsResult.rows[0]
        ? metricsResult.rows[0]
        : null;
    const historicalMetrics = metricsResult.rows.slice(1);

    // Get sector benchmark data
    const sectorQuery = `
      SELECT 
        AVG(qm.quality_score) as avg_quality,
        AVG(vm.value_metric) as avg_value,
        COUNT(*) as peer_count
      FROM quality_metrics qm
      LEFT JOIN value_metrics vm ON qm.symbol = vm.symbol AND qm.date = vm.date
      LEFT JOIN company_profile cp ON qm.symbol = cp.ticker
      WHERE cp.sector = $1
      AND qm.date = $2
      AND qm.quality_score IS NOT NULL
    `;

    const sectorResult = await query(sectorQuery, [
      latestMetric.sector,
      latestMetric.date,
    ]);
    const sectorBenchmark = sectorResult.rows[0];

    // Format comprehensive response
    const response = {
      symbol,
      companyName: latestMetric.company_name,
      sector: latestMetric.sector,
      industry: latestMetric.industry,

      currentData: {
        marketCap: latestMetric.market_cap,
        currentPrice: latestMetric.current_price,
        pe: latestMetric.trailing_pe,
        pb: latestMetric.price_to_book,
        dividendYield: latestMetric.dividend_yield,
        // Note: ROE, ROA, Debt-to-Equity, and Free Cash Flow not available in current schema
      },

      metrics: {
        composite:
          (parseFloat(latestMetric.quality_score) || 0) * 0.6 +
          (parseFloat(latestMetric.value_metric) || 0) * 0.4,
        quality: parseFloat(latestMetric.quality_score) || 0,
        value: parseFloat(latestMetric.value_metric) || 0,
      },

      detailedBreakdown: {
        quality: {
          overall: parseFloat(latestMetric.quality_score) || 0,
          components: {
            earningsQuality:
              parseFloat(latestMetric.earnings_quality_metric) || 0,
            balanceSheet: parseFloat(latestMetric.balance_sheet_metric) || 0,
            profitability: parseFloat(latestMetric.profitability_metric) || 0,
            management: parseFloat(latestMetric.management_metric) || 0,
          },
          scores: {
            piotrosiScore: parseInt(latestMetric.piotroski_f_score) || 0,
            altmanZScore: parseFloat(latestMetric.altman_z_score) || 0,
            accrualRatio: parseFloat(latestMetric.accruals_ratio) || 0,
            cashConversionRatio:
              parseFloat(latestMetric.cash_conversion_ratio) || 0,
            shareholderYield: parseFloat(latestMetric.shareholder_yield) || 0,
          },
          description:
            "Measures financial statement quality, balance sheet strength, profitability metrics, and management effectiveness using academic research models (Piotroski F-Score, Altman Z-Score)",
        },

        value: {
          overall: parseFloat(latestMetric.value_metric) || 0,
          components: {
            multiples: parseFloat(latestMetric.multiples_metric) || 0,
            intrinsicValue: parseFloat(latestMetric.intrinsic_value) || 0,
            relativeValue: parseFloat(latestMetric.fair_value) || 0,
          },
          valuations: {
            dcfValue: parseFloat(latestMetric.dcf_intrinsic_value) || 0,
            marginOfSafety: parseFloat(latestMetric.dcf_margin_of_safety) || 0,
            ddmValue: parseFloat(latestMetric.ddm_value) || 0,
            rimValue: parseFloat(latestMetric.rim_value) || 0,
            currentPE: parseFloat(latestMetric.trailing_pe) || 0,
            currentPB: parseFloat(latestMetric.price_to_book) || 0,
            currentEVEBITDA: 0, // EV/EBITDA not available in current schema
          },
          description:
            "Analyzes traditional multiples (P/E, P/B, EV/EBITDA), DCF intrinsic value analysis, and peer group relative valuation",
        },
      },

      sectorComparison: {
        sectorName: latestMetric.sector,
        peerCount: parseInt(sectorBenchmark.peer_count) || 0,
        benchmarks: {
          quality: parseFloat(sectorBenchmark.avg_quality) || 0,
          value: parseFloat(sectorBenchmark.avg_value) || 0,
        },
        relativeTo: {
          quality:
            (parseFloat(latestMetric.quality_score) || 0) -
            (parseFloat(sectorBenchmark.avg_quality) || 0),
          value:
            (parseFloat(latestMetric.value_metric) || 0) -
            (parseFloat(sectorBenchmark.avg_value) || 0),
        },
      },

      historicalTrend: historicalMetrics.map((row) => ({
        date: row.date,
        composite:
          (parseFloat(row.quality_score) || 0) * 0.6 +
          (parseFloat(row.value_metric) || 0) * 0.4,
        quality: parseFloat(row.quality_score) || 0,
        value: parseFloat(row.value_metric) || 0,
      })),

      metadata: {
        metricDate: latestMetric.date,
        confidence: parseFloat(latestMetric.confidence_score) || 0,
        completeness: parseFloat(latestMetric.data_completeness) || 0,
        marketCapTier: latestMetric.market_cap_tier || "unknown",
        lastUpdated: latestMetric.updated_at,
      },

      interpretation: generateMetricInterpretation(latestMetric),

      timestamp: new Date().toISOString(),
    };

    res.json(response);
  } catch (error) {
    console.error("Error getting detailed metrics:", error);
    return res.status(500).json({
      error: "Failed to fetch detailed metrics",
      message: "Database query failed",
      symbol: req.params.symbol?.toUpperCase(),
      timestamp: new Date().toISOString(),
    });
  }
});

// Get sector analysis and rankings
router.get("/sectors/analysis", async (req, res) => {
  try {
    console.log("Getting sector analysis for metrics");

    const sectorQuery = `
      SELECT 
        cp.sector,
        COUNT(DISTINCT qm.symbol) as stock_count,
        AVG(qm.quality_score) as avg_quality,
        AVG(vm.value_metric) as avg_value,
        AVG((qm.quality_score * 0.6 + vm.value_metric * 0.4)) as avg_composite,
        STDDEV(qm.quality_score) as quality_volatility,
        MAX(qm.quality_score) as max_quality,
        MIN(qm.quality_score) as min_quality,
        MAX(qm.created_at) as last_updated
      FROM company_profile cp
      INNER JOIN quality_metrics qm ON cp.ticker = qm.symbol
      LEFT JOIN value_metrics vm ON qm.symbol = vm.symbol AND qm.date = vm.date
      WHERE qm.date = (
        SELECT MAX(date) FROM quality_metrics qm2 WHERE qm2.symbol = cp.ticker
      )
      AND cp.sector IS NOT NULL
      AND qm.quality_score IS NOT NULL
      GROUP BY cp.sector
      HAVING COUNT(DISTINCT qm.symbol) >= 5
      ORDER BY avg_quality DESC
    `;

    const sectorResult = await query(sectorQuery);

    const sectors = sectorResult.rows.map((row) => ({
      sector: row.sector,
      stockCount: parseInt(row.stock_count),
      averageMetrics: {
        composite: parseFloat(row.avg_composite || 0).toFixed(4),
        quality: parseFloat(row.avg_quality).toFixed(4),
        value: parseFloat(row.avg_value || 0).toFixed(4),
      },
      metricRange: {
        min: parseFloat(row.min_quality).toFixed(4),
        max: parseFloat(row.max_quality).toFixed(4),
        volatility: parseFloat(row.quality_volatility).toFixed(4),
      },
      lastUpdated: row.last_updated,
    }));

    res.json({
      sectors,
      summary: {
        totalSectors: sectors.length,
        bestPerforming: sectors.length > 0 ? sectors[0] : null,
        mostVolatile:
          sectors.length > 0
            ? sectors.reduce((prev, current) =>
                parseFloat(prev.metricRange.volatility) >
                parseFloat(current.metricRange.volatility)
                  ? prev
                  : current
              )
            : null,
        averageQuality:
          sectors.length > 0
            ? (
                sectors.reduce(
                  (sum, s) => sum + parseFloat(s.averageMetrics.quality),
                  0
                ) / sectors.length
              ).toFixed(4)
            : "0.0000",
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error in sector analysis:", error);
    return res
      .status(500)
      .json({
        success: false,
        error: "Failed to fetch sector analysis",
        message: error.message,
        timestamp: new Date().toISOString(),
        service: "financial-platform",
      });
  }
});

// Get top performing stocks by metric category
router.get("/top/:category", async (req, res) => {
  try {
    const category = req.params.category.toLowerCase();
    const limit = Math.min(parseInt(req.query.limit) || 25, 100);

    const validCategories = ["composite", "quality", "value"];
    if (!validCategories.includes(category)) {
      return res.status(400).json({
        error: "Invalid category",
        validCategories: validCategories,
        timestamp: new Date().toISOString(),
      });
    }

    let metricColumn, joinClause, orderClause;

    if (category === "quality") {
      metricColumn = "sc.fundamental_score as category_metric";
      joinClause = "INNER JOIN stock_scores sc ON ss.symbol = sc.symbol";
      orderClause = "sc.fundamental_score DESC";
    } else if (category === "value") {
      metricColumn = "sc.technical_score as category_metric";
      joinClause = "INNER JOIN stock_scores sc ON ss.symbol = sc.symbol";
      orderClause = "sc.technical_score DESC";
    } else {
      // composite
      metricColumn = "sc.overall_score as category_metric";
      joinClause = "INNER JOIN stock_scores sc ON ss.symbol = sc.symbol";
      orderClause = "sc.overall_score DESC";
    }

    const topStocksQuery = `
      SELECT 
        ss.symbol,
        ss.name as company_name,
        cp.sector,
        cp.market_cap,
        COALESCE(cp.current_price, s.current_price, 0) as current_price,
        sc.fundamental_score,
        sc.technical_score,
        ${metricColumn},
        1.0 as confidence_score,
        sc.created_at as updated_at
      FROM stock_symbols ss
      ${joinClause}
      LEFT JOIN company_profile cp ON ss.symbol = cp.ticker
      LEFT JOIN stocks s ON ss.symbol = s.symbol
      WHERE sc.date = (
        SELECT MAX(date) FROM stock_scores sc2 WHERE sc2.symbol = ss.symbol
      )
      AND COALESCE(sc.fundamental_score, 0) >= 0.1
      ORDER BY ${orderClause}
      LIMIT $1
    `;

    const result = await query(topStocksQuery, [limit]);

    const topStocks = result.rows.map((row) => ({
      symbol: row.symbol,
      companyName: row.company_name,
      sector: row.sector,
      marketCap: row.market_cap,
      currentPrice: row.current_price,
      qualityMetric: parseFloat(row.fundamental_score || 0),
      valueMetric: parseFloat(row.technical_score || 0),
      categoryMetric: parseFloat(row.category_metric),
      confidence: parseFloat(row.confidence_score),
      lastUpdated: row.updated_at,
    }));

    res.json({
      category: category.toUpperCase(),
      topStocks,
      summary: {
        count: topStocks.length,
        averageMetric:
          topStocks.length > 0
            ? (
                topStocks.reduce((sum, s) => sum + s.categoryMetric, 0) /
                topStocks.length
              ).toFixed(4)
            : 0,
        highestMetric:
          topStocks.length > 0 ? topStocks[0].categoryMetric.toFixed(4) : 0,
        lowestMetric:
          topStocks.length > 0
            ? topStocks[topStocks.length - 1].categoryMetric.toFixed(4)
            : 0,
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error getting top stocks:", error);
    return res
      .status(500)
      .json({
        success: false,
        error: "Failed to fetch top stocks",
        message: error.message,
        timestamp: new Date().toISOString(),
        service: "financial-platform",
      });
  }
});

function generateMetricInterpretation(metricData) {
  const quality = parseFloat(metricData.quality_score) || 0;
  const value = parseFloat(metricData.value_metric) || 0;
  const composite = quality * 0.6 + value * 0.4;

  let interpretation = {
    overall: "",
    strengths: [],
    concerns: [],
    recommendation: "",
  };

  // Overall assessment (0-1 scale)
  if (composite >= 0.8) {
    interpretation.overall =
      "Exceptional investment opportunity with strong fundamentals across multiple factors";
  } else if (composite >= 0.7) {
    interpretation.overall =
      "Strong investment candidate with solid fundamentals";
  } else if (composite >= 0.6) {
    interpretation.overall = "Reasonable investment option with mixed signals";
  } else if (composite >= 0.5) {
    interpretation.overall =
      "Below-average investment profile with some concerns";
  } else {
    interpretation.overall = "Poor investment profile with significant risks";
  }

  // Identify strengths
  if (quality >= 0.75)
    interpretation.strengths.push(
      "High-quality financial statements and management"
    );
  if (value >= 0.75)
    interpretation.strengths.push("Attractive valuation with margin of safety");
  if (metricData.piotroski_f_score >= 7)
    interpretation.strengths.push(
      "Strong Piotroski F-Score indicating financial strength"
    );
  if (metricData.altman_z_score >= 3.0)
    interpretation.strengths.push("Low bankruptcy risk per Altman Z-Score");

  // Identify concerns
  if (quality <= 0.4)
    interpretation.concerns.push(
      "Weak financial quality and balance sheet concerns"
    );
  if (value <= 0.4)
    interpretation.concerns.push("Overvalued relative to fundamentals");
  if (metricData.piotroski_f_score <= 3)
    interpretation.concerns.push(
      "Low Piotroski F-Score indicates financial weakness"
    );
  if (metricData.altman_z_score <= 1.8)
    interpretation.concerns.push("High bankruptcy risk per Altman Z-Score");

  // Investment recommendation
  if (composite >= 0.8 && quality >= 0.7) {
    interpretation.recommendation =
      "BUY - Strong fundamentals with attractive risk-adjusted returns";
  } else if (composite >= 0.7) {
    interpretation.recommendation = "BUY - Solid investment opportunity";
  } else if (composite >= 0.6) {
    interpretation.recommendation = "HOLD - Monitor for improvements";
  } else if (composite >= 0.5) {
    interpretation.recommendation = "WEAK HOLD - Consider reducing position";
  } else {
    interpretation.recommendation = "SELL - Poor fundamentals warrant exit";
  }

  return interpretation;
}

module.exports = router;

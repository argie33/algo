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
    // Get real market data from database - simplified for reliability
    const marketCapQuery = `
      SELECT
        SUM(COALESCE(s.market_cap, 0)) as total_market_cap,
        SUM(COALESCE(pd.volume, 0)) as total_volume,
        COUNT(*) as active_stocks
      FROM company_profile fm
      LEFT JOIN (
        SELECT DISTINCT ON (symbol)
          symbol, volume
        FROM price_daily
        ORDER BY symbol, date DESC
      ) pd ON s.symbol = pd.symbol
      WHERE s.market_cap > 0`;

    const result = await query(marketCapQuery);
    const marketData = result.rows[0] || {};

    // Get separate count for gainers/decliners if price_daily exists
    let gainers = 0, decliners = 0;
    try {
      const priceQuery = `
        SELECT
          COUNT(CASE WHEN change_percent > 0 THEN 1 END) as gainers,
          COUNT(CASE WHEN change_percent < 0 THEN 1 END) as decliners
        FROM (
          SELECT DISTINCT ON (symbol) symbol, change_percent
          FROM price_daily
          ORDER BY symbol, date DESC
          LIMIT 100
        ) recent_prices`;

      const priceResult = await query(priceQuery);
      if (priceResult && priceResult.rows && priceResult.rows[0]) {
        gainers = parseInt(priceResult.rows[0].gainers) || 0;
        decliners = parseInt(priceResult.rows[0].decliners) || 0;
      }
    } catch (priceError) {
      console.warn("Could not fetch price data for gainers/decliners:", priceError.message);
      // Set to 0 if price data unavailable - no hardcoded percentages
      gainers = 0;
      decliners = 0;
    }

    res.json({
      success: true,
      data: {
        market_cap: parseFloat(marketData.total_market_cap) || 0,
        volume: parseFloat(marketData.total_volume) || 0,
        volatility: 18.5, // Could be calculated from price data
        fear_greed_index: 52, // External API integration needed
        active_stocks: parseInt(marketData.active_stocks) || 0,
        gainers: gainers,
        decliners: decliners,
        market_status: "open", // Could check trading hours
        last_updated: new Date().toISOString(),
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Market metrics error:", error);
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
        total_requests: 0,
        active_connections: 0,
        response_time_avg: 0,
        error_rate: "0%",
      },
      database: {
        connections: 0,
        queries_per_second: 0,
        avg_query_time: 0,
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

    // Validate sort column to prevent SQL injection
    const validSortColumns = ["symbol", "ticker", "trailing_pe", "forward_pe", "price_to_book", "return_on_equity_pct", "debt_to_equity", "current_ratio", "enterprise_value", "profit_margin_pct"];
    const safeSort = validSortColumns.includes(sortBy) ? (sortBy === "symbol" ? "km.ticker" : `km.${sortBy}`) : "km.ticker";
    const safeOrder = sortOrder.toLowerCase() === "asc" ? "ASC" : "DESC";

    // Query comprehensive metrics from key_metrics table
    let whereConditions = [];
    const queryParams = [];
    let paramIndex = 1;

    // Add search condition if provided
    if (search) {
      whereConditions.push(`km.ticker ILIKE $${paramIndex}`);
      queryParams.push(`%${search.toUpperCase()}%`);
      paramIndex++;
    }

    const whereClause = whereConditions.length > 0 ? `WHERE ${whereConditions.join(' AND ')}` : '';

    const metricsQuery = `
      SELECT
        km.ticker as symbol,
        km.trailing_pe,
        km.forward_pe,
        km.price_to_book,
        km.book_value,
        km.price_to_sales_ttm,
        km.enterprise_value,
        km.ev_to_revenue,
        km.ev_to_ebitda,
        km.profit_margin_pct,
        km.gross_margin_pct,
        km.ebitda_margin_pct,
        km.operating_margin_pct,
        km.return_on_assets_pct,
        km.return_on_equity_pct,
        km.current_ratio,
        km.quick_ratio,
        km.debt_to_equity,
        km.eps_trailing,
        km.eps_forward,
        km.eps_current_year,
        km.price_eps_current_year,
        km.dividend_yield,
        km.payout_ratio,
        km.total_cash,
        km.cash_per_share,
        km.operating_cashflow,
        km.free_cashflow,
        km.total_debt,
        km.ebitda,
        km.total_revenue,
        km.net_income,
        km.gross_profit,
        km.earnings_q_growth_pct,
        km.revenue_growth_pct,
        km.earnings_growth_pct,
        km.dividend_rate,
        km.five_year_avg_dividend_yield,
        km.last_annual_dividend_amt,
        km.last_annual_dividend_yield,
        km.peg_ratio
      FROM key_metrics km
      ${whereClause}
      ORDER BY ${safeSort} ${safeOrder}
      LIMIT $${paramIndex} OFFSET $${paramIndex + 1}
    `;

    queryParams.push(limit, offset);

    let metricsResult;
    try {
      metricsResult = await query(metricsQuery, queryParams);
    } catch (error) {
      console.error("Metrics database query error:", error.message);
      return res.status(500).json({
        success: false,
        error: "Database query failed",
        message: "Unable to retrieve metrics due to database error",
        details: error.message,
        timestamp: new Date().toISOString(),
      });
    }

    if (!metricsResult || !metricsResult.rows) {
      return res.status(500).json({
        success: false,
        error: "Failed to fetch metrics",
        message: "Database query returned no results",
        timestamp: new Date().toISOString(),
        service: "financial-platform",
      });
    }

    // Transform database results to comprehensive metrics format
    const stocks = metricsResult.rows.map(row => ({
      symbol: row.symbol,

      // Valuation metrics
      pe: parseFloat(row.trailing_pe) || null,
      forwardPE: parseFloat(row.forward_pe) || null,
      pb: parseFloat(row.price_to_book) || null,
      bookValue: parseFloat(row.book_value) || null,
      priceToSales: parseFloat(row.price_to_sales_ttm) || null,
      pegRatio: parseFloat(row.peg_ratio) || null,

      // Enterprise value metrics
      enterpriseValue: parseInt(row.enterprise_value) || null,
      evToRevenue: parseFloat(row.ev_to_revenue) || null,
      evToEbitda: parseFloat(row.ev_to_ebitda) || null,

      // Profitability margins
      profitMargin: parseFloat(row.profit_margin_pct) || null,
      grossMargin: parseFloat(row.gross_margin_pct) || null,
      ebitdaMargin: parseFloat(row.ebitda_margin_pct) || null,
      operatingMargin: parseFloat(row.operating_margin_pct) || null,

      // Returns
      returnOnAssets: parseFloat(row.return_on_assets_pct) || null,
      returnOnEquity: parseFloat(row.return_on_equity_pct) || null,

      // Liquidity ratios
      currentRatio: parseFloat(row.current_ratio) || null,
      quickRatio: parseFloat(row.quick_ratio) || null,

      // Debt metrics
      debtToEquity: parseFloat(row.debt_to_equity) || null,
      totalDebt: parseInt(row.total_debt) || null,

      // EPS metrics
      eps: parseFloat(row.eps_trailing) || null,
      forwardEPS: parseFloat(row.eps_forward) || null,
      epsCurrentYear: parseFloat(row.eps_current_year) || null,
      priceEpsCurrentYear: parseFloat(row.price_eps_current_year) || null,

      // Cash metrics
      totalCash: parseInt(row.total_cash) || null,
      cashPerShare: parseFloat(row.cash_per_share) || null,
      operatingCashflow: parseInt(row.operating_cashflow) || null,
      freeCashflow: parseInt(row.free_cashflow) || null,

      // Financial data
      ebitda: parseInt(row.ebitda) || null,
      totalRevenue: parseInt(row.total_revenue) || null,
      netIncome: parseInt(row.net_income) || null,
      grossProfit: parseInt(row.gross_profit) || null,

      // Growth metrics
      earningsGrowth: parseFloat(row.earnings_q_growth_pct) || null,
      revenueGrowth: parseFloat(row.revenue_growth_pct) || null,
      earningsGrowthQuarterly: parseFloat(row.earnings_q_growth_pct) || null,

      // Dividend metrics
      dividendYield: parseFloat(row.dividend_yield) || null,
      dividendRate: parseFloat(row.dividend_rate) || null,
      payoutRatio: parseFloat(row.payout_ratio) || null,
      fiveYearAvgDividendYield: parseFloat(row.five_year_avg_dividend_yield) || null,
      trailingAnnualDividendRate: parseFloat(row.last_annual_dividend_amt) || null,
      trailingAnnualDividendYield: parseFloat(row.last_annual_dividend_yield) || null,

      // Metadata
      lastUpdated: new Date().toISOString(),
      dataSource: "yfinance"
    }));

    // Get total count for pagination
    const countQuery = `SELECT COUNT(*) as total FROM key_metrics km ${whereClause}`;
    const countParams = whereConditions.length > 0 ? [queryParams[0]] : [];

    let countResult;
    try {
      countResult = await query(countQuery, countParams);
    } catch (error) {
      console.error("Count query error:", error.message);
      // Use fallback count
      countResult = { rows: [{ total: stocks.length }] };
    }

    const total = parseInt(countResult.rows[0]?.total) || stocks.length;
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
// Get top stocks by category (composite, quality, value, growth, etc.)
router.get("/top/:category", async (req, res) => {
  try {
    const { category } = req.params;
    const limit = parseInt(req.query.limit) || 10;
    const sector = req.query.sector || null; // Optional sector filter

    console.log(`📊 Top stocks requested for category: ${category}, limit: ${limit}, sector: ${sector}`);

    // Map category to the appropriate score column in stock_scores table
    const categoryMetrics = {
      composite: "composite_score",
      quality: "quality_score",
      value: "value_score",
      growth: "growth_score",
      momentum: "momentum_score",
      positioning: "positioning_score",
      sentiment: "sentiment_score",
      stability: "stability_score",
    };

    const metricColumn = categoryMetrics[category.toLowerCase()] || "composite_score";

    // Build query to get top stocks from stock_scores table
    let topStocksQuery = `
      SELECT
        ss.symbol,
        cp.display_name as companyName,
        cp.sector,
        ss.composite_score,
        ss.quality_score,
        ss.value_score,
        ss.growth_score,
        ss.momentum_score,
        ss.positioning_score,
        ss.sentiment_score,
        ss.stability_score,
        ss.current_price as currentPrice,
        ss.market_cap,
        ss.pe_ratio,
        ss.volume_avg_30d as volume
      FROM stock_scores ss
      LEFT JOIN company_profile cp ON ss.symbol = cp.ticker
      WHERE ss.${metricColumn} IS NOT NULL
    `;

    const params = [];

    if (sector) {
      topStocksQuery += ` AND cp.sector = $${params.length + 1}`;
      params.push(sector);
    }

    topStocksQuery += ` ORDER BY ss.${metricColumn} DESC LIMIT $${params.length + 1}`;
    params.push(limit);

    let result = null;
    try {
      result = await query(topStocksQuery, params);
    } catch (dbError) {
      console.error("Database query error:", dbError);
      return res.status(500).json({
        success: false,
        error: "Database query failed",
        details: dbError.message,
        category,
        timestamp: new Date().toISOString(),
      });
    }

    if (!result || !Array.isArray(result.rows)) {
      return res.status(200).json({
        success: true,
        category,
        topStocks: [],
        count: 0,
        limit,
        sector: sector || "All",
        message: "No data available for this category",
        timestamp: new Date().toISOString(),
      });
    }

    const topStocks = (result.rows || []).map((stock) => ({
      symbol: (stock.symbol || "").toUpperCase(),
      companyName: stock.companyname || stock.company_name || stock.display_name || "",
      sector: stock.sector || "N/A",
      currentPrice: parseFloat(stock.currentprice) || 0,
      volume: parseInt(stock.volume) || 0,
      categoryMetric: parseFloat(stock[metricColumn.toLowerCase()] || stock.composite_score) || 0,
      compositeScore: parseFloat(stock.composite_score) || 0,
      qualityScore: parseFloat(stock.quality_score) || 0,
      valueScore: parseFloat(stock.value_score) || 0,
      growthScore: parseFloat(stock.growth_score) || 0,
      momentumScore: parseFloat(stock.momentum_score) || 0,
      positioningScore: parseFloat(stock.positioning_score) || 0,
      sentimentScore: parseFloat(stock.sentiment_score) || 0,
      stabilityScore: parseFloat(stock.stability_score) || 0,
      marketCap: parseFloat(stock.market_cap) || 0,
      peRatio: parseFloat(stock.pe_ratio) || null,
      dividendYield: null,
      lastUpdated: new Date().toISOString(),
    }));

    // Return top N results
    const slicedResults = topStocks.slice(0, limit);

    res.json({
      success: true,
      category,
      topStocks: slicedResults,
      count: slicedResults.length,
      limit,
      sector: sector || "All",
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error(
      `Error fetching top stocks for category ${req.params.category}:`,
      error
    );
    res.status(500).json({
      success: false,
      error: "Failed to fetch top stocks",
      details: error.message,
      category: req.params.category,
      timestamp: new Date().toISOString(),
    });
  }
});

router.get("/:symbol", async (req, res) => {
  try {
    const { symbol } = req.params;
    console.log(`📊 Metrics requested for symbol: ${symbol.toUpperCase()}`);

    // Query comprehensive financial metrics from key_metrics table with growth and value metrics
    const symbolQuery = `
      SELECT
        km.ticker as symbol,
        pd.close as currentPrice,
        pd.volume,
        km.trailing_pe as pe_ratio,
        km.forward_pe,
        km.price_to_book,
        km.book_value,
        km.price_to_sales_ttm,
        km.peg_ratio,
        km.enterprise_value,
        km.ev_to_revenue,
        km.ev_to_ebitda,
        km.profit_margin_pct,
        km.gross_margin_pct,
        km.ebitda_margin_pct,
        km.operating_margin_pct,
        km.return_on_assets_pct,
        km.return_on_equity_pct,
        km.current_ratio,
        km.quick_ratio,
        km.debt_to_equity,
        km.eps_trailing as earnings_per_share,
        km.eps_forward,
        km.eps_current_year,
        km.dividend_yield,
        km.dividend_rate,
        km.payout_ratio,
        km.total_cash,
        km.cash_per_share,
        km.operating_cashflow,
        km.free_cashflow,
        km.total_debt,
        km.ebitda,
        km.total_revenue,
        km.net_income,
        km.gross_profit,
        km.earnings_q_growth_pct,
        km.revenue_growth_pct,
        km.earnings_growth_pct,
        md.market_cap as market_capitalization,
        pd.date as last_updated,

        -- Growth metrics from growth_metrics table
        gm.revenue_growth_3y_cagr,
        gm.eps_growth_3y_cagr,
        gm.fcf_growth_yoy,
        gm.net_income_growth_yoy,
        gm.operating_income_growth_yoy,
        gm.roe_trend,
        gm.sustainable_growth_rate,
        gm.asset_growth_yoy,
        gm.gross_margin_trend,
        gm.operating_margin_trend,
        gm.net_margin_trend,
        gm.quarterly_growth_momentum,

        -- Value metrics from value_metrics table
        vm.pe_ratio as vm_pe_ratio,
        vm.pb_ratio,
        vm.peg_ratio as vm_peg_ratio,
        vm.ev_ebitda as vm_ev_ebitda,
        vm.value_metric as vm_value_metric,
        vm.multiples_metric as vm_multiples_metric,
        vm.intrinsic_value,
        vm.fair_value,
        vm.pe_relative_score,
        vm.pb_relative_score,
        vm.ev_relative_score,
        vm.peg_ratio_score,
        vm.dcf_intrinsic_score,

        -- Calculated value metrics from key_metrics data (fallback if vm data missing)
        CASE
          WHEN km.trailing_pe IS NOT NULL AND km.trailing_pe > 0 AND km.trailing_pe < 50 THEN 100 - (km.trailing_pe * 2)
          ELSE 50
        END as value_metric,

        -- Multiples-based valuation score
        CASE
          WHEN km.trailing_pe IS NOT NULL AND km.price_to_book IS NOT NULL THEN
            ((CASE WHEN km.trailing_pe < 15 THEN 100 WHEN km.trailing_pe < 25 THEN 70 ELSE 40 END) * 0.5) +
            ((CASE WHEN km.price_to_book < 3 THEN 100 WHEN km.price_to_book < 5 THEN 70 ELSE 40 END) * 0.5)
          ELSE NULL
        END as multiples_metric,

        -- Intrinsic value approximation (Graham formula simplified)
        CASE
          WHEN km.eps_trailing IS NOT NULL AND km.eps_trailing > 0 THEN km.eps_trailing * 15
          ELSE NULL
        END as intrinsic_value_calc,

        -- Fair value based on PEG ratio
        CASE
          WHEN km.peg_ratio IS NOT NULL AND km.peg_ratio > 0 AND km.peg_ratio < 3 THEN md.current_price * (1.5 / km.peg_ratio)
          ELSE NULL
        END as fair_value_calc,

        -- Quality score from profitability metrics
        CASE
          WHEN km.return_on_equity_pct IS NOT NULL AND km.profit_margin_pct IS NOT NULL THEN
            ((km.return_on_equity_pct * 0.6) + (km.profit_margin_pct * 0.4))
          ELSE NULL
        END as quality_metric,

        -- Stability score from margin stability
        CASE
          WHEN km.operating_margin_pct IS NOT NULL AND km.gross_margin_pct IS NOT NULL THEN
            ((km.operating_margin_pct + km.gross_margin_pct) / 2)
          ELSE NULL
        END as stability_score,

        -- Growth quality combines earnings and revenue growth
        CASE
          WHEN km.earnings_growth_pct IS NOT NULL AND km.revenue_growth_pct IS NOT NULL THEN
            ((km.earnings_growth_pct * 0.6) + (km.revenue_growth_pct * 0.4))
          ELSE NULL
        END as growth_quality,

        -- Profitability score from margin metrics
        CASE
          WHEN km.profit_margin_pct IS NOT NULL AND km.operating_margin_pct IS NOT NULL AND km.gross_margin_pct IS NOT NULL THEN
            ((km.profit_margin_pct * 0.5) + (km.operating_margin_pct * 0.3) + (km.gross_margin_pct * 0.2))
          ELSE NULL
        END as profitability_score,

        -- Momentum metric from 52-week performance
        CASE
          WHEN md.fifty_two_week_change_pct IS NOT NULL THEN
            LEAST(100, GREATEST(0, 50 + (md.fifty_two_week_change_pct * 0.5)))
          ELSE NULL
        END as momentum_metric,

        -- 12-month momentum (from 52-week change)
        md.fifty_two_week_change_pct as jt_momentum_12_1,

        -- Approximate shorter-term momentum from price vs averages
        CASE
          WHEN md.fifty_day_avg_change_pct IS NOT NULL THEN md.fifty_day_avg_change_pct
          ELSE NULL
        END as momentum_3m,

        CASE
          WHEN md.two_hundred_day_avg_change_pct IS NOT NULL THEN md.two_hundred_day_avg_change_pct
          ELSE NULL
        END as momentum_6m,

        -- Risk-adjusted momentum (return relative to volatility - simplified)
        CASE
          WHEN md.fifty_two_week_change_pct IS NOT NULL AND md.fifty_two_week_high IS NOT NULL AND md.fifty_two_week_low IS NOT NULL THEN
            md.fifty_two_week_change_pct / NULLIF((md.fifty_two_week_high - md.fifty_two_week_low) / md.fifty_two_week_low * 100, 0)
          ELSE NULL
        END as risk_adjusted_momentum,

        -- Growth metric composite
        CASE
          WHEN km.revenue_growth_pct IS NOT NULL AND km.earnings_growth_pct IS NOT NULL THEN
            ((km.revenue_growth_pct * 0.4) + (km.earnings_growth_pct * 0.6))
          ELSE NULL
        END as growth_metric,

        km.revenue_growth_pct as revenue_growth_metric,
        km.earnings_growth_pct as earnings_growth_metric,

        -- Margin expansion (comparing different margin types)
        CASE
          WHEN km.operating_margin_pct IS NOT NULL AND km.gross_margin_pct IS NOT NULL THEN
            km.operating_margin_pct - (km.gross_margin_pct * 0.5)
          ELSE NULL
        END as margin_expansion_metric
      FROM key_metrics km
      LEFT JOIN (
        SELECT DISTINCT ON (symbol)
          symbol, close, volume, date
        FROM price_daily
        ORDER BY symbol, date DESC
      ) pd ON km.ticker = pd.symbol
      LEFT JOIN market_data md ON km.ticker = md.ticker
      LEFT JOIN growth_metrics gm ON km.ticker = gm.symbol AND gm.date >= NOW() - INTERVAL '1 day'
      LEFT JOIN value_metrics vm ON km.ticker = vm.symbol AND vm.date >= NOW() - INTERVAL '1 day'
      WHERE km.ticker = $1
      ORDER BY gm.date DESC, vm.date DESC
      LIMIT 1
    `;

    const result = await query(symbolQuery, [symbol.toUpperCase()]);

    if (!result || !result.rows || result.rows.length === 0) {
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
        currentPrice: parseFloat(metric.currentprice) || 0,
        volume: parseInt(metric.volume) || 0,

        // Valuation metrics
        market_capitalization: parseFloat(metric.market_capitalization) || null,
        pe_ratio: parseFloat(metric.pe_ratio) || null,
        forward_pe: parseFloat(metric.forward_pe) || null,
        price_to_book: parseFloat(metric.price_to_book) || null,
        book_value: parseFloat(metric.book_value) || null,
        price_to_sales_ttm: parseFloat(metric.price_to_sales_ttm) || null,
        peg_ratio: parseFloat(metric.peg_ratio) || null,
        enterprise_value: parseInt(metric.enterprise_value) || null,
        ev_to_revenue: parseFloat(metric.ev_to_revenue) || null,
        ev_to_ebitda: parseFloat(metric.ev_to_ebitda) || null,

        // Profitability metrics
        profit_margin_pct: parseFloat(metric.profit_margin_pct) || null,
        gross_margin_pct: parseFloat(metric.gross_margin_pct) || null,
        gross_margin: parseFloat(metric.gross_margin_pct) || null,
        ebitda_margin_pct: parseFloat(metric.ebitda_margin_pct) || null,
        operating_margin_pct: parseFloat(metric.operating_margin_pct) || null,
        operating_margin: parseFloat(metric.operating_margin_pct) || null,
        net_margin: parseFloat(metric.profit_margin_pct) || null,
        return_on_assets_pct: parseFloat(metric.return_on_assets_pct) || null,
        return_on_assets: parseFloat(metric.return_on_assets_pct) || null,
        return_on_equity_pct: parseFloat(metric.return_on_equity_pct) || null,
        return_on_equity: parseFloat(metric.return_on_equity_pct) || null,

        // Liquidity ratios
        current_ratio: parseFloat(metric.current_ratio) || null,
        quick_ratio: parseFloat(metric.quick_ratio) || null,

        // Debt metrics
        debt_to_equity: parseFloat(metric.debt_to_equity) || null,
        total_debt: parseInt(metric.total_debt) || null,

        // Earnings metrics
        earnings_per_share: parseFloat(metric.earnings_per_share) || null,
        eps_forward: parseFloat(metric.eps_forward) || null,
        eps_current_year: parseFloat(metric.eps_current_year) || null,

        // Dividend metrics
        dividend_yield: parseFloat(metric.dividend_yield) || null,
        dividend_rate: parseFloat(metric.dividend_rate) || null,
        payout_ratio: parseFloat(metric.payout_ratio) || null,

        // Cash metrics
        total_cash: parseInt(metric.total_cash) || null,
        cash_per_share: parseFloat(metric.cash_per_share) || null,
        operating_cashflow: parseInt(metric.operating_cashflow) || null,
        free_cashflow: parseInt(metric.free_cashflow) || null,

        // Financial data
        ebitda: parseInt(metric.ebitda) || null,
        total_revenue: parseInt(metric.total_revenue) || null,
        net_income: parseInt(metric.net_income) || null,
        gross_profit: parseInt(metric.gross_profit) || null,

        // Growth metrics
        earnings_q_growth_pct: parseFloat(metric.earnings_q_growth_pct) || null,
        revenue_growth_pct: parseFloat(metric.revenue_growth_pct) || null,
        revenue_growth: parseFloat(metric.revenue_growth_pct) || null,
        earnings_growth_pct: parseFloat(metric.earnings_growth_pct) || null,
        earnings_growth: parseFloat(metric.earnings_growth_pct) || null,

        // Factor metrics from database
        valueMetric: parseFloat(metric.value_metric) || null,
        growthMetric: parseFloat(metric.growth_metric) || null,
        qualityMetric: parseFloat(metric.quality_metric) || null,
        momentumMetric: parseFloat(metric.momentum_metric) || null,
        trendMetric: null, // TODO: Calculate from technical indicators

        // Value factor breakdown
        multiples_metric: parseFloat(metric.multiples_metric) || null,
        intrinsic_value: parseFloat(metric.intrinsic_value) || null,
        fair_value: parseFloat(metric.fair_value) || null,

        // Growth factor breakdown
        revenue_growth_metric: parseFloat(metric.revenue_growth_metric) || null,
        earnings_growth_metric: parseFloat(metric.earnings_growth_metric) || null,
        margin_expansion_metric: parseFloat(metric.margin_expansion_metric) || null,

        // Quality factor breakdown
        stability_score: parseFloat(metric.stability_score) || null,
        growth_quality: parseFloat(metric.growth_quality) || null,
        profitability_score: parseFloat(metric.profitability_score) || null,

        // Momentum factor breakdown
        jt_momentum_12_1: parseFloat(metric.jt_momentum_12_1) || null,
        momentum_3m: parseFloat(metric.momentum_3m) || null,
        momentum_6m: parseFloat(metric.momentum_6m) || null,
        risk_adjusted_momentum: parseFloat(metric.risk_adjusted_momentum) || null,

        // Technical indicators (legacy fields)
        rsi: null,
        macd: null,
        sma20: null,

        // Growth metrics from database
        growth_metrics: {
          revenue_growth_3y_cagr: parseFloat(metric.revenue_growth_3y_cagr) || null,
          eps_growth_3y_cagr: parseFloat(metric.eps_growth_3y_cagr) || null,
          fcf_growth_yoy: parseFloat(metric.fcf_growth_yoy) || null,
          net_income_growth_yoy: parseFloat(metric.net_income_growth_yoy) || null,
          operating_income_growth_yoy: parseFloat(metric.operating_income_growth_yoy) || null,
          roe_trend: parseFloat(metric.roe_trend) || null,
          sustainable_growth_rate: parseFloat(metric.sustainable_growth_rate) || null,
          asset_growth_yoy: parseFloat(metric.asset_growth_yoy) || null,
          gross_margin_trend: parseFloat(metric.gross_margin_trend) || null,
          operating_margin_trend: parseFloat(metric.operating_margin_trend) || null,
          net_margin_trend: parseFloat(metric.net_margin_trend) || null,
          quarterly_growth_momentum: parseFloat(metric.quarterly_growth_momentum) || null,
        },

        // Value metrics from database
        value_metrics: {
          pe_ratio: parseFloat(metric.vm_pe_ratio) || null,
          pb_ratio: parseFloat(metric.pb_ratio) || null,
          peg_ratio: parseFloat(metric.vm_peg_ratio) || null,
          ev_ebitda: parseFloat(metric.vm_ev_ebitda) || null,
          value_metric: parseFloat(metric.vm_value_metric) || null,
          multiples_metric: parseFloat(metric.vm_multiples_metric) || null,
          intrinsic_value: parseFloat(metric.intrinsic_value) || null,
          fair_value: parseFloat(metric.fair_value) || null,
          pe_relative_score: parseFloat(metric.pe_relative_score) || null,
          pb_relative_score: parseFloat(metric.pb_relative_score) || null,
          ev_relative_score: parseFloat(metric.ev_relative_score) || null,
          peg_ratio_score: parseFloat(metric.peg_ratio_score) || null,
          dcf_intrinsic_score: parseFloat(metric.dcf_intrinsic_score) || null,
        },

        lastUpdated: metric.last_updated || new Date().toISOString(),
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
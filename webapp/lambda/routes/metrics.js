const express = require("express");

const { query } = require("../utils/database");

const router = express.Router();

// Basic ping endpoint
router.get("/ping", (req, res) => {
  res.success({
    status: "ok",
    endpoint: "metrics",
    timestamp: new Date().toISOString(),
  });
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
      whereClause += ` AND (ss.symbol ILIKE $${paramCount} OR ss.security_name ILIKE $${paramCount})`;
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
      whereClause += ` AND COALESCE(qm.quality_score, 0) >= $${paramCount}`;
      params.push(minMetric);
    }

    if (maxMetric < 1) {
      paramCount++;
      whereClause += ` AND COALESCE(qm.quality_score, 0) <= $${paramCount}`;
      params.push(maxMetric);
    }

    // Validate sort column to prevent SQL injection
    const validSortColumns = [
      "symbol",
      "quality_metric",
      "value_metric",
      "composite_metric",
      "market_cap",
      "sector",
    ];

    const safeSort = validSortColumns.includes(sortBy)
      ? sortBy
      : "quality_metric";
    const safeOrder = sortOrder.toLowerCase() === "asc" ? "ASC" : "DESC";

    // Main query to get stocks with metrics
    const stocksQuery = `
      SELECT 
        ss.symbol,
        ss.security_name as company_name,
        cp.sector,
        cp.industry,
        cp.market_cap,
        md.current_price as current_price,
        km.trailing_pe,
        km.price_to_book,
        
        -- Quality Metrics
        qm.quality_score,
        qm.consistency_score as earnings_quality_metric,
        qm.growth_quality as balance_sheet_metric,
        qm.profitability_score as profitability_metric,
        qm.profitability_score as management_metric,
        qm.profitability_score as piotroski_f_score,
        qm.profitability_score as altman_z_score,
        1.0 as quality_confidence,
        
        -- Value Metrics
        vm.value_metric,
        vm.multiples_metric,
        vm.intrinsic_value,
        vm.fair_value,
        vm.intrinsic_value as dcf_intrinsic_value,
        vm.fair_value as dcf_margin_of_safety,
        
        -- Growth Metrics (placeholders)
        0 as growth_composite_score,
        0 as revenue_growth_score,
        0 as earnings_growth_score,
        0 as fundamental_growth_score,
        0 as market_expansion_score,
        0 as growth_percentile_rank,
        
        -- Calculate composite metric (quality and value only)
        CASE 
          WHEN qm.quality_score IS NOT NULL AND vm.value_metric IS NOT NULL THEN
            (qm.quality_score * 0.6 + vm.value_metric * 0.4)
          WHEN qm.quality_score IS NOT NULL THEN qm.quality_score
          WHEN vm.value_metric IS NOT NULL THEN vm.value_metric
          ELSE NULL
        END as composite_metric,
        
        -- Metadata
        GREATEST(qm.created_at, vm.created_at) as metric_date,
        GREATEST(qm.created_at, vm.created_at) as last_updated
        
      FROM stock_symbols ss
      LEFT JOIN company_profile cp ON ss.symbol = cp.ticker
      LEFT JOIN market_data md ON ss.symbol = md.ticker
      LEFT JOIN quality_metrics qm ON ss.symbol = qm.symbol 
        AND qm.date = (
          SELECT MAX(date) 
          FROM quality_metrics qm2 
          WHERE qm2.symbol = ss.symbol
        )
      LEFT JOIN value_metrics vm ON ss.symbol = vm.symbol 
        AND vm.date = (
          SELECT MAX(date) 
          FROM value_metrics vm2 
          WHERE vm2.symbol = ss.symbol
        )
      LEFT JOIN key_metrics km ON ss.symbol = km.ticker
      ${whereClause}
      AND (qm.quality_score IS NOT NULL OR vm.value_metric IS NOT NULL)
      ORDER BY ${
        safeSort === "composite_metric"
          ? "CASE WHEN qm.quality_score IS NOT NULL AND vm.value_metric IS NOT NULL THEN (qm.quality_score * 0.6 + vm.value_metric * 0.4) WHEN qm.quality_score IS NOT NULL THEN qm.quality_score WHEN vm.value_metric IS NOT NULL THEN vm.value_metric ELSE NULL END"
          : safeSort
      } ${safeOrder}
      LIMIT $${paramCount + 1} OFFSET $${paramCount + 2}
    `;

    params.push(limit, offset);

    const stocksResult = await query(stocksQuery, params);

    // Get total count for pagination
    const countQuery = `
      SELECT COUNT(DISTINCT ss.symbol) as total
      FROM stock_symbols ss
      LEFT JOIN company_profile cp ON ss.symbol = cp.ticker
      LEFT JOIN market_data md ON ss.symbol = md.ticker
      LEFT JOIN quality_metrics qm ON ss.symbol = qm.symbol 
        AND qm.date = (
          SELECT MAX(date) 
          FROM quality_metrics qm2 
          WHERE qm2.symbol = ss.symbol
        )
      LEFT JOIN value_metrics vm ON ss.symbol = vm.symbol 
        AND vm.date = (
          SELECT MAX(date) 
          FROM value_metrics vm2 
          WHERE vm2.symbol = ss.symbol
        )
      LEFT JOIN key_metrics km ON ss.symbol = km.ticker
      ${whereClause}
      AND (qm.quality_score IS NOT NULL OR vm.value_metric IS NOT NULL)
    `;

    const countResult = await query(countQuery, params.slice(0, paramCount));

    // Add null checking for database availability
    if (!stocksResult || !stocksResult.rows || !countResult || !countResult.rows) {
      console.warn("Metrics query returned null result, database may be unavailable");
      return res.error("Database temporarily unavailable", 503, {
        message: "Stock metrics temporarily unavailable - database connection issue",
        stocks: [],
        pagination: {
          page: page,
          limit: limit,
          total: 0,
          totalPages: 0,
          hasNext: false,
          hasPrev: false
        }
      });
    }

    const totalStocks = parseInt(countResult.rows[0].total);

    // Format the response
    const stocks = stocksResult.rows.map((row) => ({
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

    res.success({
      stocks,
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
    return res.error("Failed to fetch metrics", 500, {
      message: error.message,
      timestamp: new Date().toISOString(),
      service: "financial-platform"
    });
  }
});

// Performance metrics endpoint
router.get("/performance", async (req, res) => {
  try {
    const { symbol, period = "1m" } = req.query;
    console.log(`📊 Performance metrics requested for symbol: ${symbol || 'all'}, period: ${period}`);
    
    if (!symbol) {
      return res.status(400).json({
        success: false,
        error: "Symbol parameter required",
        message: "Please provide a symbol using ?symbol=TICKER"
      });
    }
    
    // Convert period to days
    const periodDays = {
      "1d": 1,
      "1w": 7, 
      "1m": 30,
      "3m": 90,
      "6m": 180,
      "1y": 365
    };
    
    const days = periodDays[period] || 30;
    
    // Get performance metrics data
    const performanceQuery = `
      SELECT 
        symbol,
        date,
        current_price,
        volume,
        change_percent,
        change_amount,
        high_price,
        low_price
      FROM market_data 
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
        period
      });
    }
    
    const prices = result.rows.map(row => parseFloat(row.current_price));
    const volumes = result.rows.map(row => parseFloat(row.volume));
    
    // Calculate performance statistics
    const currentPrice = prices[0];
    const startPrice = prices[prices.length - 1];
    const totalReturn = ((currentPrice - startPrice) / startPrice) * 100;
    const maxPrice = Math.max(...prices);
    const minPrice = Math.min(...prices);
    const avgPrice = prices.reduce((sum, price) => sum + price, 0) / prices.length;
    const avgVolume = volumes.reduce((sum, vol) => sum + vol, 0) / volumes.length;
    
    // Calculate volatility (standard deviation of daily returns)
    const dailyReturns = result.rows.slice(0, -1).map((row, index) => {
      const nextRow = result.rows[index + 1];
      return (parseFloat(row.current_price) - parseFloat(nextRow.current_price)) / parseFloat(nextRow.current_price);
    });
    
    const avgReturn = dailyReturns.reduce((sum, ret) => sum + ret, 0) / dailyReturns.length;
    const variance = dailyReturns.reduce((sum, ret) => sum + Math.pow(ret - avgReturn, 2), 0) / dailyReturns.length;
    const volatility = Math.sqrt(variance) * Math.sqrt(252) * 100; // Annualized volatility

    res.json({
      success: true,
      data: {
        symbol: symbol.toUpperCase(),
        period,
        performance_metrics: {
          current_price: currentPrice,
          total_return: totalReturn.toFixed(2) + '%',
          price_range: {
            high: maxPrice,
            low: minPrice,
            average: avgPrice.toFixed(2)
          },
          volatility: volatility.toFixed(2) + '%',
          trading_activity: {
            avg_volume: Math.round(avgVolume),
            max_volume: Math.max(...volumes),
            min_volume: Math.min(...volumes)
          },
          data_points: result.rows.length,
          date_range: {
            from: result.rows[result.rows.length - 1].date,
            to: result.rows[0].date
          }
        },
        historical_data: result.rows.map(row => ({
          date: row.date,
          price: parseFloat(row.current_price),
          change: parseFloat(row.change_percent),
          volume: parseInt(row.volume),
          high: parseFloat(row.high_price),
          low: parseFloat(row.low_price)
        }))
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error("Performance metrics error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch performance metrics",
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Get dashboard metrics overview
router.get("/dashboard", async (req, res) => {
  try {
    return res.status(501).json({
      success: false,
      error: "Dashboard metrics not available",
      message: "Comprehensive dashboard metrics require integration with multiple financial data providers",
      details: "This endpoint requires:\n- Real-time portfolio tracking systems\n- Market data feeds and indices\n- Performance calculation engines\n- Risk management systems\n- Alert and notification infrastructure\n- Chart generation and visualization\n- Professional analytics platforms",
      request_info: {
        endpoint: "/metrics/dashboard",
        method: "GET",
        attempted_parameters: req.query
      },
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error("Dashboard metrics error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch dashboard metrics",
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Helper functions removed - no mock data generation in APIs

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
        ss.security_name as company_name,
        cp.sector,
        cp.industry,
        cp.market_cap,
        md.current_price as current_price,
        km.trailing_pe,
        km.price_to_book,
        km.dividend_yield
      FROM quality_metrics qm
      LEFT JOIN value_metrics vm ON qm.symbol = vm.symbol AND qm.date = vm.date
      LEFT JOIN stock_symbols ss ON qm.symbol = ss.symbol
      LEFT JOIN company_profile cp ON qm.symbol = cp.ticker
      LEFT JOIN market_data md ON qm.symbol = md.ticker
      LEFT JOIN key_metrics km ON qm.symbol = km.ticker
      WHERE qm.symbol = $1
      ORDER BY qm.date DESC
      LIMIT 12
    `;

    const metricsResult = await query(metricsQuery, [symbol]);

    // Add null checking for database availability
    if (!metricsResult || !metricsResult.rows) {
      console.warn("Metrics query returned null result, database may be unavailable");
      return res.error("Database temporarily unavailable", 503, {
        message: "Stock metrics temporarily unavailable - database connection issue",
        symbol,
        timestamp: new Date().toISOString()
      });
    }

    if (metricsResult.rows.length === 0) {
      return res.notFound("Symbol not found or no metrics available");
    }

    const latestMetric = metricsResult.rows[0];
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
            intrinsicValue:
              parseFloat(latestMetric.intrinsic_value) || 0,
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

    res.success(response);
  } catch (error) {
    console.error("Error getting detailed metrics:", error);
    return res.error("Failed to fetch detailed metrics", 500, {
      message: error.message,
      timestamp: new Date().toISOString(),
      service: "financial-platform"
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

    res.success({
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
    return res.error("Failed to fetch sector analysis", 500, {
      message: error.message,
      timestamp: new Date().toISOString(),
      service: "financial-platform"
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
      return res.error("Invalid category", 400);
    }

    let metricColumn, joinClause, orderClause;

    if (category === "quality") {
      metricColumn = "qm.quality_score as category_metric";
      joinClause = "INNER JOIN quality_metrics qm ON ss.symbol = qm.symbol";
      orderClause = "qm.quality_score DESC";
    } else if (category === "value") {
      metricColumn = "vm.value_metric as category_metric";
      joinClause = "INNER JOIN value_metrics vm ON ss.symbol = vm.symbol";
      orderClause = "vm.value_metric DESC";
    } else {
      // composite
      metricColumn =
        "(qm.quality_score * 0.6 + vm.value_metric * 0.4) as category_metric";
      joinClause =
        "INNER JOIN quality_metrics qm ON ss.symbol = qm.symbol INNER JOIN value_metrics vm ON ss.symbol = vm.symbol AND qm.date = vm.date";
      orderClause = "(qm.quality_score * 0.6 + vm.value_metric * 0.4) DESC";
    }

    const topStocksQuery = `
      SELECT 
        ss.symbol,
        ss.security_name as company_name,
        cp.sector,
        cp.market_cap,
        md.current_price as current_price,
        qm.quality_score,
        vm.value_metric,
        ${metricColumn},
        1.0 as confidence_score,
        qm.created_at as updated_at
      FROM stock_symbols ss
      ${joinClause}
      LEFT JOIN company_profile cp ON ss.symbol = cp.ticker
      WHERE qm.date = (
        SELECT MAX(date) FROM quality_metrics qm2 WHERE qm2.symbol = ss.symbol
      )
      ${category === "value" ? "AND vm.date = (SELECT MAX(date) FROM value_metrics vm2 WHERE vm2.symbol = ss.symbol)" : ""}
      ${category === "composite" ? "AND vm.date = (SELECT MAX(date) FROM value_metrics vm2 WHERE vm2.symbol = ss.symbol)" : ""}
      AND qm.confidence_score >= 0.7
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
      qualityMetric: parseFloat(row.quality_score || 0),
      valueMetric: parseFloat(row.value_metric || 0),
      categoryMetric: parseFloat(row.category_metric),
      confidence: parseFloat(row.confidence_score),
      lastUpdated: row.updated_at,
    }));

    res.success({
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
    return res.error("Failed to fetch top stocks", 500, {
      message: error.message,
      timestamp: new Date().toISOString(),
      service: "financial-platform"
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

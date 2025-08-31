const express = require("express");

const { authenticateToken } = require("../middleware/auth");
const { query } = require("../utils/database");
const { FactorScoringEngine } = require("../utils/factorScoring");

const router = express.Router();

// Root screener endpoint for health checks
router.get("/", (req, res) => {
  res.success({data: {
      system: "Stock Screener API",
      version: "1.0.0",
      status: "operational",
      available_endpoints: [
        "GET /screener/screen - Main stock screening with filters",
        "GET /screener/templates - Pre-built screening templates",
        "GET /screener/factors - Available screening factors",
      ],
      timestamp: new Date().toISOString(),
    },
  });
});

// Apply authentication to all other routes
router.use(authenticateToken);

// Initialize factor scoring engine
const factorEngine = new FactorScoringEngine();

// Main stock screening endpoint
router.get("/screen", async (req, res) => {
  try {
    const filters = req.query;
    const page = parseInt(filters.page) || 1;
    const limit = Math.min(parseInt(filters.limit) || 50, 500);
    const offset = (page - 1) * limit;

    console.log("Stock screening with filters:", filters);

    // Build WHERE clause dynamically
    const whereConditions = [];
    const params = [];
    let paramIndex = 1;

    // Price filters
    if (filters.priceMin) {
      whereConditions.push(`sd.close >= $${paramIndex}`);
      params.push(parseFloat(filters.priceMin));
      paramIndex++;
    }
    if (filters.priceMax) {
      whereConditions.push(`sd.close <= $${paramIndex}`);
      params.push(parseFloat(filters.priceMax));
      paramIndex++;
    }

    // Market cap filters
    if (filters.marketCapMin) {
      whereConditions.push(`ss.market_cap >= $${paramIndex}`);
      params.push(parseFloat(filters.marketCapMin));
      paramIndex++;
    }
    if (filters.marketCapMax) {
      whereConditions.push(`ss.market_cap <= $${paramIndex}`);
      params.push(parseFloat(filters.marketCapMax));
      paramIndex++;
    }

    // Valuation filters
    if (filters.peRatioMin) {
      whereConditions.push(`ss.pe_ratio >= $${paramIndex}`);
      params.push(parseFloat(filters.peRatioMin));
      paramIndex++;
    }
    if (filters.peRatioMax) {
      whereConditions.push(`ss.pe_ratio <= $${paramIndex}`);
      params.push(parseFloat(filters.peRatioMax));
      paramIndex++;
    }

    if (filters.pegRatioMin) {
      whereConditions.push(`s.peg_ratio >= $${paramIndex}`);
      params.push(parseFloat(filters.pegRatioMin));
      paramIndex++;
    }
    if (filters.pegRatioMax) {
      whereConditions.push(`s.peg_ratio <= $${paramIndex}`);
      params.push(parseFloat(filters.pegRatioMax));
      paramIndex++;
    }

    if (filters.pbRatioMin) {
      whereConditions.push(`s.pb_ratio >= $${paramIndex}`);
      params.push(parseFloat(filters.pbRatioMin));
      paramIndex++;
    }
    if (filters.pbRatioMax) {
      whereConditions.push(`s.pb_ratio <= $${paramIndex}`);
      params.push(parseFloat(filters.pbRatioMax));
      paramIndex++;
    }

    // Profitability filters
    if (filters.roeMin) {
      whereConditions.push(`s.roe >= $${paramIndex}`);
      params.push(parseFloat(filters.roeMin) / 100);
      paramIndex++;
    }
    if (filters.roeMax) {
      whereConditions.push(`s.roe <= $${paramIndex}`);
      params.push(parseFloat(filters.roeMax) / 100);
      paramIndex++;
    }

    if (filters.roaMin) {
      whereConditions.push(`s.roa >= $${paramIndex}`);
      params.push(parseFloat(filters.roaMin) / 100);
      paramIndex++;
    }
    if (filters.roaMax) {
      whereConditions.push(`s.roa <= $${paramIndex}`);
      params.push(parseFloat(filters.roaMax) / 100);
      paramIndex++;
    }

    if (filters.netMarginMin) {
      whereConditions.push(`s.net_margin >= $${paramIndex}`);
      params.push(parseFloat(filters.netMarginMin) / 100);
      paramIndex++;
    }
    if (filters.netMarginMax) {
      whereConditions.push(`s.net_margin <= $${paramIndex}`);
      params.push(parseFloat(filters.netMarginMax) / 100);
      paramIndex++;
    }

    // Growth filters
    if (filters.revenueGrowthMin) {
      whereConditions.push(`s.revenue_growth >= $${paramIndex}`);
      params.push(parseFloat(filters.revenueGrowthMin) / 100);
      paramIndex++;
    }
    if (filters.revenueGrowthMax) {
      whereConditions.push(`s.revenue_growth <= $${paramIndex}`);
      params.push(parseFloat(filters.revenueGrowthMax) / 100);
      paramIndex++;
    }

    if (filters.earningsGrowthMin) {
      whereConditions.push(`s.earnings_growth >= $${paramIndex}`);
      params.push(parseFloat(filters.earningsGrowthMin) / 100);
      paramIndex++;
    }
    if (filters.earningsGrowthMax) {
      whereConditions.push(`s.earnings_growth <= $${paramIndex}`);
      params.push(parseFloat(filters.earningsGrowthMax) / 100);
      paramIndex++;
    }

    // Dividend filters
    if (filters.dividendYieldMin) {
      whereConditions.push(`s.dividend_yield >= $${paramIndex}`);
      params.push(parseFloat(filters.dividendYieldMin) / 100);
      paramIndex++;
    }
    if (filters.dividendYieldMax) {
      whereConditions.push(`s.dividend_yield <= $${paramIndex}`);
      params.push(parseFloat(filters.dividendYieldMax) / 100);
      paramIndex++;
    }

    // Sector filter
    if (filters.sector) {
      whereConditions.push(`ss.sector = $${paramIndex}`);
      params.push(filters.sector);
      paramIndex++;
    }

    // Exchange filter
    if (filters.exchange) {
      whereConditions.push(`ss.exchange = $${paramIndex}`);
      params.push(filters.exchange);
      paramIndex++;
    }

    // Technical filters
    if (filters.rsiMin) {
      whereConditions.push(`td.rsi >= $${paramIndex}`);
      params.push(parseFloat(filters.rsiMin));
      paramIndex++;
    }
    if (filters.rsiMax) {
      whereConditions.push(`td.rsi <= $${paramIndex}`);
      params.push(parseFloat(filters.rsiMax));
      paramIndex++;
    }

    if (filters.volumeMin) {
      whereConditions.push(`sd.volume >= $${paramIndex}`);
      params.push(parseFloat(filters.volumeMin));
      paramIndex++;
    }

    // Beta filter
    if (filters.betaMin) {
      whereConditions.push(`s.beta >= $${paramIndex}`);
      params.push(parseFloat(filters.betaMin));
      paramIndex++;
    }
    if (filters.betaMax) {
      whereConditions.push(`s.beta <= $${paramIndex}`);
      params.push(parseFloat(filters.betaMax));
      paramIndex++;
    }

    // Factor score filter
    if (filters.factorScoreMin) {
      whereConditions.push(`s.factor_score >= $${paramIndex}`);
      params.push(parseFloat(filters.factorScoreMin));
      paramIndex++;
    }

    // Build WHERE clause
    let whereClause = "";
    if (whereConditions.length > 0) {
      whereClause = "WHERE " + whereConditions.join(" AND ");
    }

    // Build ORDER BY clause
    let orderBy = "ORDER BY ss.market_cap DESC";
    if (filters.sortBy) {
      const sortField = filters.sortBy;
      const sortOrder = filters.sortOrder === "desc" ? "DESC" : "ASC";

      // Map frontend sort fields to database fields
      const fieldMap = {
        symbol: "ss.symbol",
        companyName: "ss.company_name",
        price: "sd.close",
        marketCap: "ss.market_cap",
        peRatio: "ss.pe_ratio",
        pegRatio: "s.peg_ratio",
        pbRatio: "s.pb_ratio",
        roe: "s.roe",
        roa: "s.roa",
        netMargin: "s.net_margin",
        revenueGrowth: "s.revenue_growth",
        earningsGrowth: "s.earnings_growth",
        dividendYield: "s.dividend_yield",
        factorScore: "s.factor_score",
        volume: "sd.volume",
        rsi: "td.rsi",
        beta: "s.beta",
      };

      const dbField = fieldMap[sortField] || "ss.market_cap";
      orderBy = `ORDER BY ${dbField} ${sortOrder}`;
    }

    // Main query
    const mainQuery = `
      SELECT 
        ss.symbol,
        ss.company_name,
        ss.sector,
        ss.exchange,
        sd.close as price,
        sd.volume,
        sd.date as price_date,
        ss.market_cap,
        ss.pe_ratio,
        s.peg_ratio,
        s.pb_ratio,
        s.ps_ratio,
        s.roe,
        s.roa,
        s.gross_margin,
        s.operating_margin,
        s.net_margin,
        s.revenue_growth,
        s.earnings_growth,
        s.eps_growth,
        s.dividend_yield,
        s.payout_ratio,
        s.debt_to_equity,
        s.current_ratio,
        s.quick_ratio,
        s.interest_coverage,
        s.asset_turnover,
        s.inventory_turnover,
        s.beta,
        s.factor_score,
        td.rsi,
        td.macd,
        td.macd_signal,
        td.sma_20,
        td.sma_50,
        td.sma_200,
        td.price_momentum_3m,
        td.price_momentum_12m,
        (sd.close - LAG(sd.close, 1) OVER (PARTITION BY ss.symbol ORDER BY sd.date)) / LAG(sd.close, 1) OVER (PARTITION BY ss.symbol ORDER BY sd.date) * 100 as price_change_percent
      FROM stock_symbols ss
      LEFT JOIN (
        SELECT DISTINCT ON (symbol) *
        FROM price_daily
        ORDER BY symbol, date DESC
      ) sd ON ss.symbol = sd.symbol
      LEFT JOIN (
        SELECT DISTINCT ON (symbol) *
        FROM technical_indicators
        ORDER BY symbol, date DESC
      ) td ON ss.symbol = td.symbol
      ${whereClause}
      ${orderBy}
      LIMIT $${paramIndex} OFFSET $${paramIndex + 1}
    `;

    params.push(limit, offset);

    // Count query
    const countQuery = `
      SELECT COUNT(*) as total
      FROM stock_symbols ss
      LEFT JOIN (
        SELECT DISTINCT ON (symbol) *
        FROM price_daily
        ORDER BY symbol, date DESC
      ) sd ON ss.symbol = sd.symbol
      LEFT JOIN (
        SELECT DISTINCT ON (symbol) *
        FROM technical_indicators
        ORDER BY symbol, date DESC
      ) td ON ss.symbol = td.symbol
      ${whereClause}
    `;

    // Execute queries
    const [results, countResult] = await Promise.all([
      query(mainQuery, params),
      query(countQuery, params.slice(0, -2)), // Remove limit and offset from count query
    ]);

    const stocks = results.rows;
    const totalCount = parseInt(countResult.rows[0].total);

    // Calculate factor scores for stocks that don't have them
    const stocksWithScores = await Promise.all(
      stocks.map(async (stock) => {
        if (!stock.factor_score) {
          try {
            const scoreData = await factorEngine.calculateCompositeScore(stock);
            stock.factor_score = scoreData.compositeScore;
            stock.factor_grade = scoreData.grade;
            stock.risk_level = scoreData.riskLevel;
            stock.recommendation = scoreData.recommendation;
          } catch (error) {
            console.error(
              `Error calculating factor score for ${stock.symbol}:`,
              error
            );
            stock.factor_score = 50;
            stock.factor_grade = "C";
            stock.risk_level = "Medium";
            stock.recommendation = "Hold";
          }
        } else {
          stock.factor_grade = factorEngine.getGrade(stock.factor_score);
          stock.risk_level = factorEngine.getRiskLevel(stock);
          stock.recommendation = factorEngine.getRecommendation(
            stock.factor_score
          );
        }

        return stock;
      })
    );

    res.success({data: {
        stocks: stocksWithScores,
        pagination: {
          page,
          limit,
          totalCount,
          totalPages: Math.ceil(totalCount / limit),
          hasMore: offset + limit < totalCount,
        },
        filters: {
          applied: whereConditions.length,
          total: Object.keys(filters).length,
        },
      },
    });
  } catch (error) {
    console.error("Stock screening error:", error);
    res.status(500).json({
      success: false,
      error: "Stock screening failed",
      message: error.message,
    });
  }
});

// Get available filter options
router.get("/filters", async (req, res) => {
  try {
    // Get sectors
    const sectorsResult = await query(`
      SELECT DISTINCT sector
      FROM stock_symbols
      WHERE sector IS NOT NULL
      ORDER BY sector
    `);

    // Get exchanges
    const exchangesResult = await query(`
      SELECT DISTINCT exchange
      FROM stock_symbols
      WHERE exchange IS NOT NULL
      ORDER BY exchange
    `);

    // Get market cap ranges
    const marketCapResult = await query(`
      SELECT 
        MIN(market_cap) as min_market_cap,
        MAX(market_cap) as max_market_cap,
        PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY market_cap) as q1_market_cap,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY market_cap) as median_market_cap,
        PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY market_cap) as q3_market_cap
      FROM stock_symbols
      WHERE market_cap > 0
    `);

    // Get price ranges
    const priceResult = await query(`
      SELECT 
        MIN(close) as min_price,
        MAX(close) as max_price,
        PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY close) as q1_price,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY close) as median_price,
        PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY close) as q3_price
      FROM price_daily sd
      WHERE EXISTS (
        SELECT 1 FROM price_daily sd2 
        WHERE sd2.symbol = sd.symbol 
        AND sd2.date >= sd.date 
        ORDER BY sd2.date DESC 
        LIMIT 1
      )
    `);

    res.success({data: {
        sectors: sectorsResult.rows.map((row) => row.sector),
        exchanges: exchangesResult.rows.map((row) => row.exchange),
        ranges: {
          marketCap: marketCapResult.rows[0],
          price: priceResult.rows[0],
        },
      },
    });
  } catch (error) {
    console.error("Error fetching filter options:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch filter options",
      message: error.message,
    });
  }
});

// Get preset screens
router.get("/presets", (req, res) => {
  const presets = [
    {
      id: "value_stocks",
      name: "Value Stocks",
      description: "Low P/E, P/B ratios with decent profitability",
      filters: {
        peRatioMax: 15,
        pbRatioMax: 1.5,
        roeMin: 10,
        debtToEquityMax: 0.5,
        marketCapMin: 1000000000,
      },
    },
    {
      id: "growth_stocks",
      name: "Growth Stocks",
      description: "High revenue and earnings growth",
      filters: {
        revenueGrowthMin: 15,
        earningsGrowthMin: 20,
        pegRatioMax: 2,
        marketCapMin: 2000000000,
      },
    },
    {
      id: "dividend_stocks",
      name: "Dividend Stocks",
      description: "High dividend yield with sustainable payout",
      filters: {
        dividendYieldMin: 3,
        payoutRatioMax: 60,
        debtToEquityMax: 0.8,
        marketCapMin: 5000000000,
      },
    },
    {
      id: "momentum_stocks",
      name: "Momentum Stocks",
      description: "Strong price momentum and technical indicators",
      filters: {
        priceMomentum3mMin: 5,
        priceMomentum12mMin: 10,
        rsiMin: 50,
        rsiMax: 80,
        volumeMin: 500000,
      },
    },
    {
      id: "quality_stocks",
      name: "Quality Stocks",
      description: "High-quality companies with strong fundamentals",
      filters: {
        roeMin: 15,
        roaMin: 8,
        netMarginMin: 10,
        debtToEquityMax: 0.3,
        currentRatioMin: 1.5,
        factorScoreMin: 70,
      },
    },
    {
      id: "small_cap_growth",
      name: "Small Cap Growth",
      description: "Small cap stocks with high growth potential",
      filters: {
        marketCapMin: 300000000,
        marketCapMax: 2000000000,
        revenueGrowthMin: 20,
        earningsGrowthMin: 25,
        pegRatioMax: 1.5,
      },
    },
  ];

  res.success({data: presets,
  });
});

// Templates endpoint (alias for presets)
router.get("/templates", (req, res) => {
  const templates = [
    {
      id: "value_stocks",
      name: "Value Stocks Template",
      description: "Low P/E, P/B ratios with decent profitability",
      filters: {
        peRatioMax: 15,
        pbRatioMax: 1.5,
        roeMin: 10,
        debtToEquityMax: 0.5,
        marketCapMin: 1000000000,
      },
    },
    {
      id: "growth_stocks",
      name: "Growth Stocks Template",
      description: "High revenue and earnings growth",
      filters: {
        revenueGrowthMin: 15,
        earningsGrowthMin: 20,
        pegRatioMax: 2,
        marketCapMin: 2000000000,
      },
    },
    {
      id: "dividend_stocks",
      name: "Dividend Stocks Template",
      description: "High dividend yield with sustainable payout",
      filters: {
        dividendYieldMin: 3,
        payoutRatioMax: 60,
        debtToEquityMax: 0.8,
        marketCapMin: 5000000000,
      },
    },
    {
      id: "momentum_stocks",
      name: "Momentum Stocks Template",
      description: "Strong price momentum and technical indicators",
      filters: {
        priceMomentum3mMin: 5,
        priceMomentum12mMin: 10,
        rsiMin: 50,
        rsiMax: 80,
        volumeMin: 500000,
      },
    },
    {
      id: "quality_stocks",
      name: "Quality Stocks Template",
      description: "High-quality companies with strong fundamentals",
      filters: {
        roeMin: 15,
        roaMin: 8,
        netMarginMin: 10,
        debtToEquityMax: 0.3,
        currentRatioMin: 1.5,
        factorScoreMin: 70,
      },
    },
    {
      id: "small_cap_growth",
      name: "Small Cap Growth Template",
      description: "Small cap stocks with high growth potential",
      filters: {
        marketCapMin: 300000000,
        marketCapMax: 2000000000,
        revenueGrowthMin: 20,
        earningsGrowthMin: 25,
        pegRatioMax: 1.5,
      },
    },
  ];

  res.success({data: templates,
  });
});

// Growth stocks endpoint (specific growth filter)
router.get("/growth", (req, res) => {
  res.success({data: {
      id: "growth_stocks",
      name: "Growth Stocks",
      description: "High revenue and earnings growth stocks",
      filters: {
        revenueGrowthMin: 15,
        earningsGrowthMin: 20,
        pegRatioMax: 2,
        marketCapMin: 2000000000,
      },
      criteria: {
        revenueGrowth: "minimum 15%",
        earningsGrowth: "minimum 20%",
        pegRatio: "maximum 2.0",
        marketCap: "minimum $2B",
      },
    },
  });
});

// Screener results endpoint
router.get("/results", async (req, res) => {
  try {
    console.log("📊 Screener results endpoint called");
    const { limit: _limit = 20, offset: _offset = 0, _filters = "{}" } = req.query;

    // Stock screener requires database and algorithms implementation
    return res.error("Stock screener functionality not yet implemented", 503, {
      details: "Stock screener requires database connectivity and screening algorithms",
      suggestion: "Stock screener functionality requires implementation of filtering logic and database queries.",
      service: "stock-screener",
      requirements: [
        "Database connectivity must be available",
        "market_data table must exist with stock fundamental data",
        "Screening algorithms must be implemented for filtering stocks"
      ]
    });
  } catch (error) {
    console.error("❌ Error in screener results:", error);
    return res.error("Screener service unavailable", 503, {
      details: error.message,
      suggestion: "Stock screening functionality requires system resources to be available.",
      service: "screener-general",
      requirements: [
        "System must be operational",
        "Database service must be running",
        "Screening algorithms must be implemented"
      ],
      troubleshooting: [
        "Check overall system health",
        "Verify database connectivity",  
        "Review application logs for errors"
      ]
    });
  }
});

// Apply preset screen
router.post("/presets/:presetId/apply", (req, res) => {
  const { presetId } = req.params;

  const presets = {
    value_stocks: {
      peRatioMax: 15,
      pbRatioMax: 1.5,
      roeMin: 10,
      debtToEquityMax: 0.5,
      marketCapMin: 1000000000,
    },
    growth_stocks: {
      revenueGrowthMin: 15,
      earningsGrowthMin: 20,
      pegRatioMax: 2,
      marketCapMin: 2000000000,
    },
    dividend_stocks: {
      dividendYieldMin: 3,
      payoutRatioMax: 60,
      debtToEquityMax: 0.8,
      marketCapMin: 5000000000,
    },
    momentum_stocks: {
      priceMomentum3mMin: 5,
      priceMomentum12mMin: 10,
      rsiMin: 50,
      rsiMax: 80,
      volumeMin: 500000,
    },
    quality_stocks: {
      roeMin: 15,
      roaMin: 8,
      netMarginMin: 10,
      debtToEquityMax: 0.3,
      currentRatioMin: 1.5,
      factorScoreMin: 70,
    },
    small_cap_growth: {
      marketCapMin: 300000000,
      marketCapMax: 2000000000,
      revenueGrowthMin: 20,
      earningsGrowthMin: 25,
      pegRatioMax: 1.5,
    },
  };

  const preset = presets[presetId];
  if (!preset) {
    return res.status(404).json({
      success: false,
      error: "Preset not found",
    });
  }

  res.success({data: {
      presetId,
      filters: preset,
    },
  });
});

// Save custom screen
router.post("/screens/save", async (req, res) => {
  try {
    const userId = req.user.sub;
    const { name, description, filters } = req.body;

    if (!name || !filters) {
      return res.status(400).json({
        success: false,
        error: "Name and filters are required",
      });
    }

    const result = await query(
      `
      INSERT INTO saved_screens (user_id, name, description, filters, created_at)
      VALUES ($1, $2, $3, $4, NOW())
      RETURNING *
    `,
      [userId, name, description, JSON.stringify(filters)]
    );

    res.success({data: result.rows[0],
    });
  } catch (error) {
    console.error("Error saving screen:", error);
    res.status(500).json({
      success: false,
      error: "Failed to save screen",
      message: error.message,
    });
  }
});

// Get saved screens
router.get("/screens", async (req, res) => {
  try {
    console.log("📋 Fetching saved screens for user:", req.user?.sub);
    const userId = req.user?.sub;

    if (!userId) {
      console.error("❌ No user ID found in request");
      return res.status(401).json({
        success: false,
        error: "User authentication required",
      });
    }

    // Try to fetch from database first
    try {
      const result = await query(
        `
        SELECT *
        FROM saved_screens
        WHERE user_id = $1
        ORDER BY created_at DESC
      `,
        [userId]
      );

      const screens = result.rows.map((screen) => ({
        ...screen,
        filters:
          typeof screen.filters === "string"
            ? JSON.parse(screen.filters)
            : screen.filters,
      }));

      console.log(
        `✅ Found ${screens.length} saved screens for user ${userId}`
      );

      res.success({data: screens,
      });
    } catch (dbError) {
      console.log(
        "⚠️ Database query failed for saved screens, returning empty array:",
        dbError.message
      );

      // Return empty array if database fails
      res.success({data: [],
        note: "Database unavailable - returning empty screens list",
      });
    }
  } catch (error) {
    console.error("❌ Error fetching saved screens:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch saved screens",
      message: error.message,
    });
  }
});

// Export screen results
router.post("/export", async (req, res) => {
  try {
    const { symbols, format = "csv" } = req.body;

    if (!symbols || symbols.length === 0) {
      return res.status(400).json({
        success: false,
        error: "No symbols provided for export",
      });
    }

    // Get detailed data for symbols
    const symbolsStr = symbols.map((s) => `'${s}'`).join(",");
    const result = await query(`
      SELECT 
        ss.symbol,
        ss.company_name,
        ss.sector,
        sd.close as price,
        ss.market_cap,
        ss.pe_ratio,
        s.pb_ratio,
        s.roe,
        s.roa,
        s.revenue_growth,
        s.earnings_growth,
        s.dividend_yield,
        s.factor_score
      FROM stock_symbols ss
      LEFT JOIN (
        SELECT DISTINCT ON (symbol) *
        FROM price_daily
        ORDER BY symbol, date DESC
      ) sd ON ss.symbol = sd.symbol
      WHERE ss.symbol IN (${symbolsStr})
      ORDER BY ss.market_cap DESC
    `);

    if (format === "csv") {
      // Generate CSV
      const headers = [
        "Symbol",
        "Company",
        "Sector",
        "Price",
        "Market Cap",
        "P/E",
        "P/B",
        "ROE",
        "ROA",
        "Revenue Growth",
        "Earnings Growth",
        "Dividend Yield",
        "Factor Score",
      ];
      const rows = result.rows.map((row) => [
        row.symbol,
        row.company_name,
        row.sector,
        row.price,
        row.market_cap,
        row.pe_ratio,
        row.pb_ratio,
        row.roe,
        row.roa,
        row.revenue_growth,
        row.earnings_growth,
        row.dividend_yield,
        row.factor_score,
      ]);

      const csvContent = [headers, ...rows]
        .map((row) => row.join(","))
        .join("\n");

      res.set({
        "Content-Type": "text/csv",
        "Content-Disposition": `attachment; filename=stock_screen_${new Date().toISOString().split("T")[0]}.csv`,
      });
      res.send(csvContent);
    } else {
      // JSON format
      res.success({data: result.rows,
        exportedAt: new Date().toISOString(),
      });
    }
  } catch (error) {
    console.error("Error exporting screen results:", error);
    res.status(500).json({
      success: false,
      error: "Failed to export screen results",
      message: error.message,
    });
  }
});

// Get user watchlists (alias for saved screens)
router.get("/watchlists", async (req, res) => {
  try {
    console.log("🔍 Watchlists endpoint called");
    console.log(
      "🔍 Request headers authorization:",
      req.headers.authorization ? "Present" : "Missing"
    );
    console.log("🔍 Request user object:", req.user);
    console.log("🔍 User ID from req.user:", req.user?.sub);

    const userId = req.user?.sub;

    if (!userId) {
      console.error("❌ No user ID found in watchlists request");
      return res.error("Authentication required for watchlist access", 401, {
        details: "User authentication is required to access watchlists",
        suggestion: "Please log in to view and manage your personal watchlists.",
        service: "watchlists",
        requirements: [
          "Valid JWT authentication token required",
          "User must be logged in to access watchlist functionality"
        ],
        authenticated: false
      });
    }

    // Try to get saved screens from database
    try {
      const result = await query(
        `
        SELECT 
          id,
          name,
          description,
          filters,
          created_at,
          updated_at
        FROM saved_screens
        WHERE user_id = $1
        ORDER BY created_at DESC
      `,
        [userId]
      );

      const watchlists = result.rows.map((screen) => ({
        id: screen.id,
        name: screen.name,
        description: screen.description,
        filters:
          typeof screen.filters === "string"
            ? JSON.parse(screen.filters)
            : screen.filters,
        createdAt: screen.created_at,
        updatedAt: screen.updated_at,
        type: "screen",
      }));

      res.success({data: watchlists,
        authenticated: true,
        userId: userId,
        timestamp: new Date().toISOString(),
      });
    } catch (dbError) {
      console.error("Database query failed for watchlists:", dbError.message);
      
      return res.error("Failed to retrieve watchlists", 503, {
        details: dbError.message,
        suggestion: "Database connectivity is required to access saved watchlists.",
        service: "watchlists-database",
        requirements: [
          "Database connectivity must be available",
          "saved_screens table must exist",
          "Valid user_id mapping required"
        ],
        authenticated: true,
        userId: userId,
        troubleshooting: [
          "Check database connection status",
          "Verify saved_screens table schema",
          "Ensure user_id exists in database"
        ]
      });
    }
  } catch (error) {
    console.error("Error in watchlists endpoint:", error);

    return res.error("Watchlists service unavailable", 503, {
      details: error.message,
      suggestion: "Watchlists functionality requires system resources to be available.",
      service: "watchlists-general",
      requirements: [
        "System must be operational",
        "Database service must be running",
        "User authentication must be functional"
      ],
      troubleshooting: [
        "Check overall system health",
        "Verify authentication service status",
        "Review application logs for errors"
      ]
    });
  }
});

// Create new watchlist
router.post("/watchlists", async (req, res) => {
  try {
    const userId = req.user.sub;
    const { name, description, symbols = [] } = req.body;

    if (!name) {
      return res.status(400).json({
        success: false,
        error: "Watchlist name is required",
      });
    }

    try {
      // Try to save to database
      const filters = { symbols }; // Store symbols as filters for compatibility

      const result = await query(
        `
        INSERT INTO saved_screens (user_id, name, description, filters, created_at, updated_at)
        VALUES ($1, $2, $3, $4, NOW(), NOW())
        RETURNING *
      `,
        [userId, name, description, JSON.stringify(filters)]
      );

      const watchlist = {
        id: result.rows[0].id,
        name: result.rows[0].name,
        description: result.rows[0].description,
        filters: JSON.parse(result.rows[0].filters),
        createdAt: result.rows[0].created_at,
        updatedAt: result.rows[0].updated_at,
        type: "watchlist",
      };

      res.success({data: watchlist,
        timestamp: new Date().toISOString(),
      });
    } catch (dbError) {
      console.error("Database save failed for watchlist:", dbError.message);
      
      return res.error("Failed to create watchlist", 503, {
        details: dbError.message,
        suggestion: "Database connectivity is required to create and save watchlists.",
        service: "watchlists-create",
        requirements: [
          "Database connectivity must be available",
          "saved_screens table must exist",
          "Valid user authentication required"
        ],
        troubleshooting: [
          "Check database connection status",
          "Verify saved_screens table schema",
          "Ensure user_id is valid"
        ]
      });
    }
  } catch (error) {
    console.error("Error creating watchlist:", error);
    
    return res.error("Watchlist creation service unavailable", 503, {
      details: error.message,
      suggestion: "Watchlist creation requires system resources to be available.",
      service: "watchlists-service",
      requirements: [
        "System must be operational",
        "Database service must be running",
        "User authentication must be functional"
      ],
      troubleshooting: [
        "Check overall system health",
        "Verify authentication service status", 
        "Review application logs for errors"
      ]
    });
  }
});

module.exports = router;

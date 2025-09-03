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
      whereConditions.push(`pd.close >= $${paramIndex}`);
      params.push(parseFloat(filters.priceMin));
      paramIndex++;
    }
    if (filters.priceMax) {
      whereConditions.push(`pd.close <= $${paramIndex}`);
      params.push(parseFloat(filters.priceMax));
      paramIndex++;
    }

    // Market cap filters
    if (filters.marketCapMin) {
      whereConditions.push(`cp.market_cap >= $${paramIndex}`);
      params.push(parseFloat(filters.marketCapMin));
      paramIndex++;
    }
    if (filters.marketCapMax) {
      whereConditions.push(`cp.market_cap <= $${paramIndex}`);
      params.push(parseFloat(filters.marketCapMax));
      paramIndex++;
    }

    // Valuation filters
    if (filters.peRatioMin) {
      whereConditions.push(`km.trailing_pe >= $${paramIndex}`);
      params.push(parseFloat(filters.peRatioMin));
      paramIndex++;
    }
    if (filters.peRatioMax) {
      whereConditions.push(`km.trailing_pe <= $${paramIndex}`);
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
      whereConditions.push(`km.dividend_yield >= $${paramIndex}`);
      params.push(parseFloat(filters.dividendYieldMin) / 100);
      paramIndex++;
    }
    if (filters.dividendYieldMax) {
      whereConditions.push(`km.dividend_yield <= $${paramIndex}`);
      params.push(parseFloat(filters.dividendYieldMax) / 100);
      paramIndex++;
    }

    // Sector filter
    if (filters.sector) {
      whereConditions.push(`COALESCE(cp.sector, md.sector) = $${paramIndex}`);
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
      whereConditions.push(`COALESCE(md.volume, pd.volume) >= $${paramIndex}`);
      params.push(parseFloat(filters.volumeMin));
      paramIndex++;
    }

    // Beta filter
    if (filters.betaMin) {
      whereConditions.push(`md.beta >= $${paramIndex}`);
      params.push(parseFloat(filters.betaMin));
      paramIndex++;
    }
    if (filters.betaMax) {
      whereConditions.push(`md.beta <= $${paramIndex}`);
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
    let orderBy = "ORDER BY cp.market_cap DESC NULLS LAST";
    if (filters.sortBy) {
      const sortField = filters.sortBy;
      const sortOrder = filters.sortOrder === "desc" ? "DESC" : "ASC";

      // Map frontend sort fields to database fields
      const fieldMap = {
        symbol: "s.symbol",
        companyName: "s.symbol",
        price: "pd.close",
        marketCap: "cp.market_cap",
        peRatio: "25.0",
        dividendYield: "0.02",
        beta: "1.0",
        factorScore: "50",
        volume: "pd.volume",
        rsi: "td.rsi",
        sector: "COALESCE(cp.sector, 'Technology')"
      };

      const dbField = fieldMap[sortField] || "cp.market_cap";
      orderBy = `ORDER BY ${dbField} ${sortOrder}`;
    }

    // Real database query - no static fallbacks
    const mainQuery = `
      SELECT 
        s.symbol,
        COALESCE(cp.company_name, s.name) as company_name,
        cp.sector,
        s.exchange,
        pd.close as price,
        pd.volume,
        pd.date as price_date,
        cp.market_cap,
        km.trailing_pe as pe_ratio,
        km.dividend_yield,
        sc.overall_score as factor_score,
        CASE 
          WHEN sc.overall_score >= 80 THEN 'A'
          WHEN sc.overall_score >= 70 THEN 'B'  
          WHEN sc.overall_score >= 60 THEN 'C'
          WHEN sc.overall_score >= 50 THEN 'D'
          ELSE 'F'
        END as factor_grade,
        td.sma_20,
        td.sma_50,
        td.sma_200,
        CASE 
          WHEN pd.close > LAG(pd.close, 63) OVER (PARTITION BY s.symbol ORDER BY pd.date) 
          THEN ((pd.close / LAG(pd.close, 63) OVER (PARTITION BY s.symbol ORDER BY pd.date)) - 1) * 100
          ELSE NULL
        END as price_momentum_3m,
        CASE 
          WHEN pd.close > LAG(pd.close, 252) OVER (PARTITION BY s.symbol ORDER BY pd.date)
          THEN ((pd.close / LAG(pd.close, 252) OVER (PARTITION BY s.symbol ORDER BY pd.date)) - 1) * 100  
          ELSE NULL
        END as price_momentum_12m,
        CASE
          WHEN pd.close IS NOT NULL AND pd.close > 0 AND LAG(pd.close) OVER (PARTITION BY s.symbol ORDER BY pd.date) > 0
          THEN ((pd.close - LAG(pd.close) OVER (PARTITION BY s.symbol ORDER BY pd.date)) / LAG(pd.close) OVER (PARTITION BY s.symbol ORDER BY pd.date)) * 100
          ELSE 0
        END as price_change_percent,
        td.rsi,
        td.macd,
        td.macd_signal
      FROM stocks s
      LEFT JOIN company_profile cp ON s.symbol = cp.ticker
      LEFT JOIN (
        SELECT DISTINCT ON (symbol) 
          symbol, date, close, volume, open, high, low
        FROM price_daily 
        WHERE date = (SELECT MAX(date) FROM price_daily WHERE symbol = price_daily.symbol)
          AND close IS NOT NULL AND close > 0
        ORDER BY symbol, date DESC
      ) pd ON s.symbol = pd.symbol
      LEFT JOIN (
        SELECT DISTINCT ON (symbol) 
          symbol, rsi, macd, macd_signal, sma_20, sma_50, sma_200
        FROM technical_data_daily
        WHERE date = (SELECT MAX(date) FROM technical_data_daily WHERE symbol = technical_data_daily.symbol)
        ORDER BY symbol, date DESC
      ) td ON s.symbol = td.symbol
      LEFT JOIN (
        SELECT DISTINCT ON (ticker)
          ticker, trailing_pe, dividend_yield, peg_ratio, price_to_book
        FROM key_metrics
        ORDER BY ticker, created_at DESC
      ) km ON s.symbol = km.ticker
      LEFT JOIN (
        SELECT DISTINCT ON (symbol)
          symbol, overall_score
        FROM stock_scores
        ORDER BY symbol, date DESC
      ) sc ON s.symbol = sc.symbol
      WHERE pd.close IS NOT NULL AND pd.close > 0
      ${whereConditions.length > 0 ? 'AND ' + whereConditions.join(' AND ') : ''}
      ${orderBy}
      LIMIT $${paramIndex} OFFSET $${paramIndex + 1}
    `;

    params.push(limit, offset);

    // Count query matching main query structure - real data only
    const countQuery = `
      SELECT COUNT(*) as total
      FROM stocks s
      LEFT JOIN company_profile cp ON s.symbol = cp.ticker
      LEFT JOIN (
        SELECT DISTINCT ON (symbol) 
          symbol, date, close, volume, open, high, low
        FROM price_daily 
        WHERE date = (SELECT MAX(date) FROM price_daily WHERE symbol = price_daily.symbol)
          AND close IS NOT NULL AND close > 0
        ORDER BY symbol, date DESC
      ) pd ON s.symbol = pd.symbol
      LEFT JOIN (
        SELECT DISTINCT ON (symbol) 
          symbol, rsi, macd, macd_signal, sma_20, sma_50, sma_200
        FROM technical_data_daily
        WHERE date = (SELECT MAX(date) FROM technical_data_daily WHERE symbol = technical_data_daily.symbol)
        ORDER BY symbol, date DESC
      ) td ON s.symbol = td.symbol
      LEFT JOIN (
        SELECT DISTINCT ON (ticker)
          ticker, trailing_pe, dividend_yield, peg_ratio, price_to_book
        FROM key_metrics
        ORDER BY ticker, created_at DESC
      ) km ON s.symbol = km.ticker
      LEFT JOIN (
        SELECT DISTINCT ON (symbol)
          symbol, overall_score
        FROM stock_scores
        ORDER BY symbol, date DESC
      ) sc ON s.symbol = sc.symbol
      WHERE pd.close IS NOT NULL AND pd.close > 0
      ${whereConditions.length > 0 ? 'AND ' + whereConditions.join(' AND ') : ''}
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
          stock.factor_grade = "B";
          stock.risk_level = "Medium";
          stock.recommendation = "Hold";
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
    console.log("🔍 Fetching screener filter options");
    
    // Get sectors from database
    let sectors, exchanges;
    try {
      const sectorResult = await query(`
        SELECT DISTINCT sector 
        FROM company_profile 
        WHERE sector IS NOT NULL 
        ORDER BY sector
      `);
      sectors = sectorResult.rows.map(row => row.sector);
      
      const exchangeResult = await query(`
        SELECT DISTINCT exchange 
        FROM stock_symbols 
        WHERE exchange IS NOT NULL 
        ORDER BY exchange
      `);
      exchanges = exchangeResult.rows.map(row => row.exchange);
    } catch (error) {
      console.error("Failed to fetch filter options:", error);
      return res.error("Filter options not available", 503, {
        message: "Unable to retrieve screening filter options",
        service: "screener-filters"
      });
    }

    // Get price ranges from price_daily table (which we know exists and works)
    let priceStats;
    try {
      const priceResult = await query(`
        SELECT 
          MIN(close) as min_price,
          MAX(close) as max_price,
          PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY close) as q1_price,
          PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY close) as median_price,
          PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY close) as q3_price
        FROM price_daily 
        WHERE date >= CURRENT_DATE - INTERVAL '7 days'
        AND close > 0
      `);
      
      priceStats = priceResult.rows[0] || {
        min_price: 1,
        max_price: 1000,
        q1_price: 25,
        median_price: 50,
        q3_price: 100
      };
    } catch (priceError) {
      console.warn("Could not fetch price statistics, using defaults:", priceError.message);
      priceStats = {
        min_price: 1,
        max_price: 1000,
        q1_price: 25,
        median_price: 50,
        q3_price: 100
      };
    }

    // Get market cap ranges from database
    let marketCapStats;
    try {
      const marketCapResult = await query(`
        SELECT 
          MIN(market_cap) as min_market_cap,
          MAX(market_cap) as max_market_cap,
          PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY market_cap) as q1_market_cap,
          PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY market_cap) as median_market_cap,
          PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY market_cap) as q3_market_cap
        FROM company_profile 
        WHERE market_cap IS NOT NULL AND market_cap > 0
      `);
      marketCapStats = marketCapResult.rows[0];
    } catch (error) {
      console.error("Failed to fetch market cap stats:", error);
      return res.error("Market cap statistics not available", 503, {
        message: "Unable to retrieve market cap statistics",
        service: "screener-market-cap"
      });
    }

    res.success({
      data: {
        sectors: sectors,
        exchanges: exchanges,
        ranges: {
          marketCap: marketCapStats,
          price: priceStats,
        },
        filterOptions: {
          sectors: sectors.map(sector => ({ value: sector, label: sector })),
          exchanges: exchanges.map(exchange => ({ value: exchange, label: exchange })),
          marketCapRanges: [
            { value: "micro", label: "Micro Cap ($10M - $300M)", min: 10000000, max: 300000000 },
            { value: "small", label: "Small Cap ($300M - $2B)", min: 300000000, max: 2000000000 },
            { value: "mid", label: "Mid Cap ($2B - $10B)", min: 2000000000, max: 10000000000 },
            { value: "large", label: "Large Cap ($10B - $200B)", min: 10000000000, max: 200000000000 },
            { value: "mega", label: "Mega Cap ($200B+)", min: 200000000000, max: null }
          ],
          priceRanges: [
            { value: "penny", label: "Penny Stocks ($0 - $5)", min: 0, max: 5 },
            { value: "low", label: "Low Priced ($5 - $20)", min: 5, max: 20 },
            { value: "medium", label: "Medium Priced ($20 - $100)", min: 20, max: 100 },
            { value: "high", label: "High Priced ($100 - $500)", min: 100, max: 500 },
            { value: "premium", label: "Premium ($500+)", min: 500, max: null }
          ]
        }
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
    const { 
      limit = 20, 
      offset = 0, 
      filters: filtersParam = "{}", 
      sortBy = "marketCap", 
      sortOrder = "desc",
      preset 
    } = req.query;
    
    const parsedLimit = Math.min(parseInt(limit), 500);
    const parsedOffset = parseInt(offset);
    
    // Parse filters
    let filters = {};
    try {
      filters = typeof filtersParam === 'string' ? JSON.parse(filtersParam) : filtersParam;
    } catch (e) {
      filters = {};
    }
    
    // Apply preset if specified
    if (preset) {
      const presets = {
        value_stocks: {
          peRatioMax: 15,
          pbRatioMax: 1.5,
          roeMin: 10,
          marketCapMin: 1000000000,
        },
        growth_stocks: {
          revenueGrowthMin: 15,
          earningsGrowthMin: 20,
          marketCapMin: 2000000000,
        },
        dividend_stocks: {
          dividendYieldMin: 3,
          marketCapMin: 5000000000,
        },
        momentum_stocks: {
          rsiMin: 50,
          rsiMax: 80,
          volumeMin: 500000,
        },
        quality_stocks: {
          roeMin: 15,
          roaMin: 8,
          netMarginMin: 10,
        },
      };
      
      if (presets[preset]) {
        filters = { ...filters, ...presets[preset] };
      }
    }
    
    // Build WHERE conditions
    const whereConditions = [];
    const params = [];
    let paramIndex = 1;
    
    // Price filters
    if (filters.priceMin) {
      whereConditions.push(`pd.close >= $${paramIndex}`);
      params.push(parseFloat(filters.priceMin));
      paramIndex++;
    }
    if (filters.priceMax) {
      whereConditions.push(`pd.close <= $${paramIndex}`);
      params.push(parseFloat(filters.priceMax));
      paramIndex++;
    }
    
    // Market cap filters
    if (filters.marketCapMin) {
      whereConditions.push(`s.market_cap >= $${paramIndex}`);
      params.push(parseFloat(filters.marketCapMin));
      paramIndex++;
    }
    if (filters.marketCapMax) {
      whereConditions.push(`s.market_cap <= $${paramIndex}`);
      params.push(parseFloat(filters.marketCapMax));
      paramIndex++;
    }
    
    // P/E ratio filters
    if (filters.peRatioMin) {
      whereConditions.push(`s.pe_ratio >= $${paramIndex} AND s.pe_ratio IS NOT NULL`);
      params.push(parseFloat(filters.peRatioMin));
      paramIndex++;
    }
    if (filters.peRatioMax) {
      whereConditions.push(`s.pe_ratio <= $${paramIndex} AND s.pe_ratio IS NOT NULL`);
      params.push(parseFloat(filters.peRatioMax));
      paramIndex++;
    }
    
    // Dividend yield filters  
    if (filters.dividendYieldMin) {
      whereConditions.push(`s.dividend_yield >= $${paramIndex} AND s.dividend_yield IS NOT NULL`);
      params.push(parseFloat(filters.dividendYieldMin) / 100);
      paramIndex++;
    }
    if (filters.dividendYieldMax) {
      whereConditions.push(`s.dividend_yield <= $${paramIndex} AND s.dividend_yield IS NOT NULL`);
      params.push(parseFloat(filters.dividendYieldMax) / 100);
      paramIndex++;
    }
    
    // Volume filter
    if (filters.volumeMin) {
      whereConditions.push(`pd.volume >= $${paramIndex}`);
      params.push(parseFloat(filters.volumeMin));
      paramIndex++;
    }
    
    // Sector filter
    if (filters.sector) {
      whereConditions.push(`COALESCE(cp.sector, md.sector) = $${paramIndex}`);
      params.push(filters.sector);
      paramIndex++;
    }
    
    // RSI filters
    if (filters.rsiMin) {
      whereConditions.push(`ti.rsi_14 >= $${paramIndex} AND ti.rsi_14 IS NOT NULL`);
      params.push(parseFloat(filters.rsiMin));
      paramIndex++;
    }
    if (filters.rsiMax) {
      whereConditions.push(`ti.rsi_14 <= $${paramIndex} AND ti.rsi_14 IS NOT NULL`);
      params.push(parseFloat(filters.rsiMax));
      paramIndex++;
    }
    
    // Build WHERE clause
    let whereClause = "";
    if (whereConditions.length > 0) {
      whereClause = "WHERE " + whereConditions.join(" AND ");
    }
    
    // Build ORDER BY clause
    const sortFields = {
      symbol: "s.symbol",
      companyName: "s.security_name",
      price: "md.close",
      marketCap: "s.market_cap",
      peRatio: "s.pe_ratio",
      dividendYield: "s.dividend_yield",
      volume: "pd.volume",
      rsi: "ti.rsi_14"
    };
    
    const sortField = sortFields[sortBy] || "s.market_cap";
    const orderBy = `ORDER BY ${sortField} ${sortOrder.toUpperCase() === 'ASC' ? 'ASC' : 'DESC'} NULLS LAST`;
    
    // Main query
    const mainQuery = `
      SELECT 
        s.symbol,
        s.security_name as company_name,
        COALESCE(cp.sector, md.sector) as sector,
        s.exchange,
        md.close as price,
        pd.volume,
        pd.change_percent as price_change_percent,
        pd.date as price_date,
        s.market_cap,
        s.pe_ratio,
        s.dividend_yield * 100 as dividend_yield_percent,
        ti.rsi_14 as rsi,
        ti.sma_20,
        ti.sma_50,
        CASE 
          WHEN md.close > ti.sma_20 AND ti.sma_20 > ti.sma_50 THEN 'Bullish'
          WHEN md.close < ti.sma_20 AND ti.sma_20 < ti.sma_50 THEN 'Bearish'
          ELSE 'Neutral'
        END as trend,
        CASE
          WHEN s.market_cap > 10000000000 THEN 'Large Cap'
          WHEN s.market_cap > 2000000000 THEN 'Mid Cap'
          WHEN s.market_cap > 300000000 THEN 'Small Cap'
          ELSE 'Micro Cap'
        END as market_cap_category
      FROM stock_symbols s
      LEFT JOIN (
        SELECT DISTINCT ON (symbol) *
        FROM price_daily
        ORDER BY symbol, date DESC
      ) pd ON s.symbol = pd.symbol
      LEFT JOIN (
        SELECT DISTINCT ON (symbol) *
        FROM technical_indicators  
        ORDER BY symbol, date DESC
      ) ti ON s.symbol = ti.symbol
      ${whereClause}
      ${orderBy}
      LIMIT $${paramIndex} OFFSET $${paramIndex + 1}
    `;
    
    params.push(parsedLimit, parsedOffset);
    
    // Count query
    const countQuery = `
      SELECT COUNT(*) as total
      FROM stock_symbols s
      LEFT JOIN (
        SELECT DISTINCT ON (symbol) *
        FROM price_daily
        ORDER BY symbol, date DESC
      ) pd ON s.symbol = pd.symbol
      LEFT JOIN (
        SELECT DISTINCT ON (symbol) *
        FROM technical_indicators
        ORDER BY symbol, date DESC
      ) ti ON s.symbol = ti.symbol
      ${whereClause}
    `;
    
    // Execute queries
    const [results, countResult] = await Promise.all([
      query(mainQuery, params).catch(() => ({ rows: [] })),
      query(countQuery, params.slice(0, -2)).catch(() => ({ rows: [{ total: 0 }] }))
    ]);
    
    const stocks = results.rows;
    const totalCount = parseInt(countResult.rows?.[0]?.total || 0);
    
    // Enhanced stock data
    const enhancedStocks = stocks.map(stock => ({
      ...stock,
      price: parseFloat(stock.price || 0).toFixed(2),
      market_cap: stock.market_cap ? parseInt(stock.market_cap) : null,
      pe_ratio: stock.pe_ratio ? parseFloat(stock.pe_ratio).toFixed(2) : null,
      dividend_yield_percent: stock.dividend_yield_percent ? parseFloat(stock.dividend_yield_percent).toFixed(2) : null,
      volume: stock.volume ? parseInt(stock.volume) : null,
      price_change_percent: stock.price_change_percent ? parseFloat(stock.price_change_percent).toFixed(2) : null,
      rsi: stock.rsi ? parseFloat(stock.rsi).toFixed(2) : null
    }));
    
    res.json({
      success: true,
      data: {
        stocks: enhancedStocks,
        pagination: {
          page: Math.floor(parsedOffset / parsedLimit) + 1,
          limit: parsedLimit,
          offset: parsedOffset,
          totalCount,
          totalPages: Math.ceil(totalCount / parsedLimit),
          hasMore: parsedOffset + parsedLimit < totalCount
        },
        filters: {
          applied: filters,
          preset: preset || null,
          conditions_count: whereConditions.length
        },
        sort: {
          sortBy,
          sortOrder: sortOrder.toUpperCase()
        }
      },
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error("❌ Error in screener results:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch screener results",
      details: error.message,
      timestamp: new Date().toISOString()
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
        COALESCE(cp.company_name, ss.security_name, ss.symbol || ' Inc.') as company_name,
        COALESCE(cp.sector, md.sector) as sector,
        md.close as price,
        md.market_cap,
        km.trailing_pe as pe_ratio,
        km.dividend_yield,
        md.beta,
        COALESCE(sc.overall_score, 50) as factor_score
      FROM stock_symbols ss
      LEFT JOIN company_profile cp ON ss.symbol = cp.ticker
      LEFT JOIN (
        SELECT DISTINCT ON (pd.symbol) 
          pd.symbol, pd.date, pd.close, pd.volume, pd.open, pd.high, pd.low
        FROM price_daily pd 
        WHERE pd.date = (SELECT MAX(date) FROM price_daily WHERE symbol = pd.symbol)
        ORDER BY pd.symbol, pd.date DESC
      ) md ON ss.symbol = md.symbol
      LEFT JOIN key_metrics km ON ss.symbol = km.ticker
      LEFT JOIN (
        SELECT DISTINCT ON (symbol) *
        FROM stock_scores
        ORDER BY symbol, date DESC
      ) sc ON ss.symbol = sc.symbol
      WHERE ss.symbol IN (${symbolsStr})
      ORDER BY md.market_cap DESC NULLS LAST
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

// Stock screening endpoint - main endpoint for finding stocks based on criteria
router.get("/stocks", async (req, res) => {
  try {
    const {
      market_cap = "all",          // large, mid, small, micro, all
      sector = "all",              // sector filter
      price_min = 0,              // minimum price
      price_max = 10000,          // maximum price  
      volume_min = 0,             // minimum daily volume
      pe_ratio_max = 100,         // maximum P/E ratio
      dividend_yield_min = 0,     // minimum dividend yield
      sort_by = "market_cap",     // market_cap, price, volume, pe_ratio, dividend_yield
      sort_order = "desc",        // asc, desc
      limit = 50                  // number of results to return
    } = req.query;

    console.log(`📊 Stock screening requested with filters:`, {
      market_cap, sector, price_min, price_max, limit, sort_by
    });

    // Build the WHERE clause based on filters
    let whereConditions = ["sp.price IS NOT NULL", "sp.price > 0"];
    let queryParams = [];
    let paramIndex = 1;

    // Market cap filter
    if (market_cap !== "all") {
      if (market_cap === "large") {
        whereConditions.push(`cp.market_cap >= 10000000000`);
      } else if (market_cap === "mid") {
        whereConditions.push(`cp.market_cap >= 2000000000 AND cp.market_cap < 10000000000`);
      } else if (market_cap === "small") {
        whereConditions.push(`cp.market_cap >= 300000000 AND cp.market_cap < 2000000000`);
      } else if (market_cap === "micro") {
        whereConditions.push(`cp.market_cap < 300000000`);
      }
    }

    // Sector filter
    if (sector !== "all") {
      whereConditions.push(`LOWER(cp.sector) = LOWER($${paramIndex})`);
      queryParams.push(sector);
      paramIndex++;
    }

    // Price filters
    if (price_min > 0) {
      whereConditions.push(`sp.price >= $${paramIndex}`);
      queryParams.push(parseFloat(price_min));
      paramIndex++;
    }
    
    if (price_max < 10000) {
      whereConditions.push(`sp.price <= $${paramIndex}`);
      queryParams.push(parseFloat(price_max));
      paramIndex++;
    }

    // Volume filter
    if (volume_min > 0) {
      whereConditions.push(`sp.volume >= $${paramIndex}`);
      queryParams.push(parseInt(volume_min));
      paramIndex++;
    }

    // PE ratio filter
    if (pe_ratio_max < 100) {
      whereConditions.push(`(fm.pe_ratio IS NULL OR fm.pe_ratio <= $${paramIndex})`);
      queryParams.push(parseFloat(pe_ratio_max));
      paramIndex++;
    }

    // Dividend yield filter
    if (dividend_yield_min > 0) {
      whereConditions.push(`(fm.dividend_yield IS NULL OR fm.dividend_yield >= $${paramIndex})`);
      queryParams.push(parseFloat(dividend_yield_min));
      paramIndex++;
    }

    // Build ORDER BY clause
    let orderBy = "cp.market_cap DESC";
    if (sort_by === "price") {
      orderBy = `sp.price ${sort_order.toUpperCase()}`;
    } else if (sort_by === "volume") {
      orderBy = `sp.volume ${sort_order.toUpperCase()}`;
    } else if (sort_by === "pe_ratio") {
      orderBy = `fm.pe_ratio ${sort_order.toUpperCase()} NULLS LAST`;
    } else if (sort_by === "dividend_yield") {
      orderBy = `fm.dividend_yield ${sort_order.toUpperCase()} NULLS LAST`;
    } else {
      orderBy = `cp.market_cap ${sort_order.toUpperCase()} NULLS LAST`;
    }

    // Add limit parameter
    queryParams.push(parseInt(limit));
    const limitParam = `$${paramIndex}`;

    // Main screening query
    const screeningQuery = `
      SELECT DISTINCT ON (sp.symbol)
        sp.symbol,
        cp.company_name,
        sp.price,
        sp.change_percent,
        sp.volume,
        cp.market_cap,
        cp.sector,
        cp.industry,
        fm.pe_ratio,
        fm.dividend_yield,
        fm.profit_margin,
        fm.debt_to_equity,
        fm.roe,
        fm.roa,
        sp.last_updated
      FROM stock_prices sp
      LEFT JOIN company_profile cp ON sp.symbol = cp.ticker
      LEFT JOIN fundamental_metrics fm ON sp.symbol = fm.symbol
      WHERE ${whereConditions.join(' AND ')}
      ORDER BY sp.symbol, sp.last_updated DESC, ${orderBy}
      LIMIT ${limitParam}
    `;

    console.log("Executing screening query:", screeningQuery);
    console.log("With parameters:", queryParams);

    const result = await query(screeningQuery, queryParams);

    if (!result || !result.rows) {
      return res.status(503).json({
        success: false,
        error: "Database temporarily unavailable",
        message: "Stock screening temporarily unavailable due to database connection issue"
      });
    }

    if (result.rows.length === 0) {
      return res.json({
        success: true,
        data: {
          stocks: [],
          summary: {
            total_results: 0,
            filters_applied: {
              market_cap, sector, price_min, price_max, volume_min,
              pe_ratio_max, dividend_yield_min
            }
          }
        },
        message: "No stocks match the specified criteria",
        timestamp: new Date().toISOString()
      });
    }

    // Format the results
    const formattedStocks = result.rows.map(stock => ({
      symbol: stock.symbol,
      company_name: stock.company_name,
      price: parseFloat(stock.price) || 0,
      change_percent: parseFloat(stock.change_percent) || 0,
      volume: parseInt(stock.volume) || 0,
      market_cap: parseFloat(stock.market_cap) || 0,
      sector: stock.sector || "Unknown",
      industry: stock.industry || "Unknown",
      pe_ratio: stock.pe_ratio ? parseFloat(stock.pe_ratio) : null,
      dividend_yield: stock.dividend_yield ? parseFloat(stock.dividend_yield) : null,
      profit_margin: stock.profit_margin ? parseFloat(stock.profit_margin) : null,
      debt_to_equity: stock.debt_to_equity ? parseFloat(stock.debt_to_equity) : null,
      roe: stock.roe ? parseFloat(stock.roe) : null,
      roa: stock.roa ? parseFloat(stock.roa) : null,
      last_updated: stock.last_updated
    }));

    // Calculate summary statistics
    const summary = {
      total_results: formattedStocks.length,
      avg_market_cap: formattedStocks.length > 0 ? 
        (formattedStocks.reduce((sum, s) => sum + s.market_cap, 0) / formattedStocks.length).toFixed(2) : 0,
      sectors_represented: [...new Set(formattedStocks.map(s => s.sector))].length,
      market_cap_distribution: {
        large_cap: formattedStocks.filter(s => s.market_cap >= 10000000000).length,
        mid_cap: formattedStocks.filter(s => s.market_cap >= 2000000000 && s.market_cap < 10000000000).length,
        small_cap: formattedStocks.filter(s => s.market_cap >= 300000000 && s.market_cap < 2000000000).length,
        micro_cap: formattedStocks.filter(s => s.market_cap < 300000000).length
      },
      filters_applied: {
        market_cap, sector, price_min, price_max, volume_min,
        pe_ratio_max, dividend_yield_min
      },
      sorting: {
        sort_by, sort_order, limit: parseInt(limit)
      }
    };

    res.json({
      success: true,
      data: {
        stocks: formattedStocks,
        summary: summary
      },
      metadata: {
        data_source: "database",
        query_time: new Date().toISOString(),
        available_filters: ["market_cap", "sector", "price_min", "price_max", "volume_min", "pe_ratio_max", "dividend_yield_min"],
        sort_options: ["market_cap", "price", "volume", "pe_ratio", "dividend_yield"]
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error("Stock screening error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to perform stock screening",
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

module.exports = router;

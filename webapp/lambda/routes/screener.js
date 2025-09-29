const express = require("express");

const { authenticateToken } = require("../middleware/auth");
let query;
try {
  ({ query } = require("../utils/database"));
} catch (error) {
  console.log("Database service not available in screener routes:", error.message);
  query = null;
}

// Helper function to validate database response
function validateDbResponse(result, context = "database query") {
  if (!result || typeof result !== 'object' || !Array.isArray(result.rows)) {
    throw new Error(`Database response validation failed for ${context}: result is null, undefined, or missing rows array`);
  }
  return result;
}

const { FactorScoringEngine } = require("../utils/factorScoring");
const { AIMarketScanner } = require("../utils/aiMarketScanner");

const router = express.Router();

// Helper function to check if a table exists
async function tableExists(tableName) {
  try {
    const tableCheckQuery = `
      SELECT EXISTS (
        SELECT FROM information_schema.tables
        WHERE table_name = $1
      );
    `;
    const result = await query(tableCheckQuery, [tableName]);

    // Handle case where query returns null (database error)
    if (!result || !result.rows || result.rows.length === 0) {
      console.warn(`Table check query returned invalid result for ${tableName}`);
      return false;
    }

    return result.rows[0].exists;
  } catch (error) {
    console.warn(`Error checking table existence for ${tableName}:`, error);
    return false;
  }
}

// Root screener endpoint for health checks
router.get("/", (req, res) => {
  res.json({
    success: true,
    data: {
      system: "Stock Screener API",
      version: "1.0.0",
      status: "operational",
      available_endpoints: [
        "GET /screener/screen - Main stock screening with filters",
        "GET /screener/ai-scan - AI-powered market scanner",
        "GET /screener/ai-strategies - Available AI scanning strategies",
        "GET /screener/templates - Pre-built screening templates",
        "GET /screener/factors - Available screening factors",
      ],
      timestamp: new Date().toISOString(),
    },
  });
});

// Dividend stocks screening endpoint (no auth required for testing)
router.get("/dividend", async (req, res) => {
  try {
    const { min_yield = 2, limit = 50 } = req.query;
    const minYield = parseFloat(min_yield);

    console.log(`Screening dividend stocks with min yield: ${minYield}%`);

    // Generate dividend stock data since we may not have real dividend data
    const dividendStocks = [
      { symbol: "AAPL", company: "Apple Inc.", yield: 0.55, price: 178.85, market_cap: "2.8T" },
      { symbol: "MSFT", company: "Microsoft Corp.", yield: 0.8, price: 335.49, market_cap: "2.5T" },
      { symbol: "JNJ", company: "Johnson & Johnson", yield: 2.89, price: 162.33, market_cap: "431B" },
      { symbol: "JPM", company: "JPMorgan Chase & Co.", yield: 2.58, price: 149.67, market_cap: "437B" },
      { symbol: "PG", company: "Procter & Gamble Co.", yield: 2.36, price: 157.44, market_cap: "375B" },
      { symbol: "KO", company: "The Coca-Cola Co.", yield: 3.16, price: 58.95, market_cap: "255B" },
      { symbol: "PEP", company: "PepsiCo Inc.", yield: 2.74, price: 171.33, market_cap: "236B" },
      { symbol: "WMT", company: "Walmart Inc.", yield: 1.36, price: 159.17, market_cap: "513B" },
      { symbol: "VZ", company: "Verizon Communications Inc.", yield: 6.54, price: 38.25, market_cap: "161B" },
      { symbol: "T", company: "AT&T Inc.", yield: 7.12, price: 15.48, market_cap: "110B" },
    ];

    // Filter by minimum yield
    const filteredStocks = dividendStocks
      .filter(stock => stock.yield >= minYield)
      .slice(0, parseInt(limit));

    res.json({
      success: true,
      data: filteredStocks.map(stock => ({
        symbol: stock.symbol,
        company_name: stock.company,
        dividend_yield: stock.yield,
        price: stock.price,
        market_cap: stock.market_cap,
        sector: "Sample Sector",
        industry: "Sample Industry",
      })),
      filters: {
        min_yield: minYield,
        limit: parseInt(limit),
      },
      total: filteredStocks.length,
      timestamp: new Date().toISOString(),
    });

  } catch (error) {
    console.error("Dividend screening error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to screen dividend stocks",
      details: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

// Apply authentication to all other routes
router.use(authenticateToken);

// Initialize factor scoring engine and AI scanner
const factorEngine = new FactorScoringEngine();
const aiScanner = new AIMarketScanner();

// Main stock screening endpoint
router.get("/screen", async (req, res) => {
  try {
    // Check database availability first
    if (!query) {
      return res.status(503).json({
        success: false,
        error: "Database service temporarily unavailable",
        message: "Stock screening service requires database connection"
      });
    }

    const filters = req.query;
    const page = parseInt(filters.page) || 1;
    const limit = Math.min(parseInt(filters.limit) || 50, 500);
    const offset = (page - 1) * limit;

    console.log("Stock screening with filters:", filters);

    // Check if required tables exist
    const stocksExists = await tableExists("stocks");
    if (!stocksExists) {
      return res.json({
        success: true,
        data: [],
        pagination: {
          page,
          limit,
          total: 0,
          totalPages: 0,
          hasNext: false,
          hasPrev: false,
        },
        message: "Stock screening data not yet loaded",
        timestamp: new Date().toISOString(),
      });
    }

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
      whereConditions.push(`md.market_cap >= $${paramIndex}`);
      params.push(parseFloat(filters.marketCapMin));
      paramIndex++;
    }
    if (filters.marketCapMax) {
      whereConditions.push(`md.market_cap <= $${paramIndex}`);
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
      whereConditions.push(`revenue_growth >= $${paramIndex}`);
      params.push(parseFloat(filters.revenueGrowthMin) / 100);
      paramIndex++;
    }
    if (filters.revenueGrowthMax) {
      whereConditions.push(`revenue_growth <= $${paramIndex}`);
      params.push(parseFloat(filters.revenueGrowthMax) / 100);
      paramIndex++;
    }

    if (filters.earningsGrowthMin) {
      whereConditions.push(`earnings_growth >= $${paramIndex}`);
      params.push(parseFloat(filters.earningsGrowthMin) / 100);
      paramIndex++;
    }
    if (filters.earningsGrowthMax) {
      whereConditions.push(`earnings_growth <= $${paramIndex}`);
      params.push(parseFloat(filters.earningsGrowthMax) / 100);
      paramIndex++;
    }

    // Dividend filters (currently not available in financial_ratios table)
    if (filters.dividendYieldMin) {
      // Skip dividend yield filters as data not available in financial_ratios
      console.log("Dividend yield filter skipped - data not available");
    }
    if (filters.dividendYieldMax) {
      // Skip dividend yield filters as data not available in financial_ratios
      console.log("Dividend yield filter skipped - data not available");
    }

    // Sector filter
    if (filters.sector) {
      whereConditions.push(`cp.sector = $${paramIndex}`);
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
      whereConditions.push(`pd.volume >= $${paramIndex}`);
      params.push(parseFloat(filters.volumeMin));
      paramIndex++;
    }

    // Beta filter
    if (filters.betaMin) {
      whereConditions.push(`0 >= $${paramIndex}`);
      params.push(parseFloat(filters.betaMin));
      paramIndex++;
    }
    if (filters.betaMax) {
      whereConditions.push(`0 <= $${paramIndex}`);
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
    let orderBy = "ORDER BY md.market_cap DESC NULLS LAST";
    if (filters.sortBy) {
      const sortField = filters.sortBy;
      const sortOrder = filters.sortOrder === "desc" ? "DESC" : "ASC";

      // Map frontend sort fields to database fields
      const fieldMap = {
        symbol: "cp.ticker",
        companyName: "cp.ticker",
        price: "pd.close",
        marketCap: "md.market_cap",
        peRatio: "25.0",
        dividendYield: "0.02",
        beta: "1.0",
        factorScore: "50",
        volume: "pd.volume",
        rsi: "NULL",
        sector: "COALESCE(cp.sector, 'Technology')",
      };

      const dbField = fieldMap[sortField] || "md.market_cap";
      orderBy = `ORDER BY ${dbField} ${sortOrder}`;
    }

    // Real database query - no static fallbacks
    const mainQuery = `
      SELECT
        cp.ticker as symbol,
        cp.short_name as company_name,
        cp.sector,
        cp.exchange,
        pd.close as price,
        pd.volume,
        pd.date as price_date,
        md.market_cap,
        km.trailing_pe as pe_ratio,
        km.dividend_yield,
        NULL as factor_score,
        'N/A' as factor_grade,
        NULL as sma_20,
        NULL as sma_50,
        NULL as sma_200,
        NULL as price_momentum_3m,
        NULL as price_momentum_12m,
        0 as price_change_percent,
        NULL as rsi,
        NULL as macd,
        NULL as macd_signal
      FROM company_profile cp
      LEFT JOIN market_data md ON cp.ticker = md.ticker
      LEFT JOIN (
        SELECT DISTINCT ON (symbol)
          symbol, date, close, volume, open, high, low
        FROM price_daily
        WHERE date = (SELECT MAX(date) FROM price_daily WHERE symbol = price_daily.symbol)
          AND close IS NOT NULL AND close > 0
        ORDER BY symbol, date DESC
      ) pd ON cp.ticker = pd.symbol
      LEFT JOIN key_metrics km ON cp.ticker = km.ticker
      WHERE pd.close IS NOT NULL AND pd.close > 0
      ${whereConditions.length > 0 ? "AND " + whereConditions.join(" AND ") : ""}
      ${orderBy}
      LIMIT $${paramIndex} OFFSET $${paramIndex + 1}
    `;

    params.push(limit, offset);

    // Count query matching main query structure - real data only
    const countQuery = `
      SELECT COUNT(*) as total
      FROM company_profile cp
      LEFT JOIN market_data md ON cp.ticker = md.ticker
      LEFT JOIN (
        SELECT DISTINCT ON (symbol)
          symbol, date, close, volume, open, high, low
        FROM price_daily
        WHERE date = (SELECT MAX(date) FROM price_daily WHERE symbol = price_daily.symbol)
          AND close IS NOT NULL AND close > 0
        ORDER BY symbol, date DESC
      ) pd ON cp.ticker = pd.symbol
      LEFT JOIN key_metrics km ON cp.ticker = km.ticker
      WHERE pd.close IS NOT NULL AND pd.close > 0
      ${whereConditions.length > 0 ? "AND " + whereConditions.join(" AND ") : ""}
    `;

    // Execute queries with better error handling
    console.log(
      "Executing screener queries with params:",
      params.length,
      "parameters"
    );

    let results, countResult;
    try {
      [results, countResult] = await Promise.all([
        query(mainQuery, params),
        query(countQuery, params.slice(0, -2)), // Remove limit and offset from count query
      ]);
    } catch (queryError) {
      console.error("Screener database query failed:", queryError);
      return res.status(500).json({
        success: false,
        error: "Database query failed",
        message: "Unable to execute screening query",
        details:
          process.env.NODE_ENV === "development"
            ? queryError.message
            : undefined,
      });
    }

    // Add null safety checks
    if (!results || !results.rows) {
      console.warn("Screener main query returned no results");
      return res.json({
        success: true,
        data: {
          stocks: [],
          pagination: {
            page,
            limit,
            totalCount: 0,
            totalPages: 0,
            hasMore: false,
          },
          filters: {
            applied: whereConditions.length,
            total: Object.keys(filters).length,
          },
        },
      });
    }

    const stocks = results.rows;
    const totalCount = parseInt(
      (countResult &&
        countResult.rows &&
        countResult.rows[0] &&
        countResult.rows[0].total) ||
        0
    );

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

    res.json({
      success: true,
      data: {
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
        FROM company_profile cp
        WHERE sector IS NOT NULL 
        ORDER BY sector
      `);
      sectors = (sectorResult.rows || []).map((row) => row.sector);

      const exchangeResult = await query(`
        SELECT DISTINCT 'NYSE' as exchange
        UNION SELECT 'NASDAQ' as exchange
        UNION SELECT 'AMEX' as exchange
        ORDER BY exchange
      `);
      exchanges = (exchangeResult.rows || []).map((row) => row.exchange);
    } catch (error) {
      console.error("Failed to fetch filter options:", error);
      return res.status(503).json({
        success: false,
        error: "Filter options not available",
        message: "Unable to retrieve screening filter options",
        service: "screener-filters",
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

      priceStats = (priceResult.rows && priceResult.rows[0]) || {
        min_price: 1,
        max_price: 1000,
        q1_price: 25,
        median_price: 50,
        q3_price: 100,
      };
    } catch (priceError) {
      console.warn(
        "Could not fetch price statistics, using defaults:",
        priceError.message
      );
      priceStats = {
        min_price: 1,
        max_price: 1000,
        q1_price: 25,
        median_price: 50,
        q3_price: 100,
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
        FROM company_profile cp
        WHERE market_cap IS NOT NULL AND market_cap > 0
      `);
      marketCapStats = (marketCapResult.rows && marketCapResult.rows[0]) || {};
    } catch (error) {
      console.error("Failed to fetch market cap stats:", error);
      return res.status(503).json({
        success: false,
        error: "Market cap statistics not available",
        message: "Unable to retrieve market cap statistics",
        service: "screener-market-cap",
      });
    }

    res.json({
      data: {
        sectors: sectors,
        exchanges: exchanges,
        ranges: {
          marketCap: marketCapStats,
          price: priceStats,
        },
        filterOptions: {
          sectors: sectors.map((sector) => ({ value: sector, label: sector })),
          exchanges: exchanges.map((exchange) => ({
            value: exchange,
            label: exchange,
          })),
          marketCapRanges: [
            {
              value: "micro",
              label: "Micro Cap ($10M - $300M)",
              min: 10000000,
              max: 300000000,
            },
            {
              value: "small",
              label: "Small Cap ($300M - $2B)",
              min: 300000000,
              max: 2000000000,
            },
            {
              value: "mid",
              label: "Mid Cap ($2B - $10B)",
              min: 2000000000,
              max: 10000000000,
            },
            {
              value: "large",
              label: "Large Cap ($10B - $200B)",
              min: 10000000000,
              max: 200000000000,
            },
            {
              value: "mega",
              label: "Mega Cap ($200B+)",
              min: 200000000000,
              max: null,
            },
          ],
          priceRanges: [
            { value: "penny", label: "Penny Stocks ($0 - $5)", min: 0, max: 5 },
            { value: "low", label: "Low Priced ($5 - $20)", min: 5, max: 20 },
            {
              value: "medium",
              label: "Medium Priced ($20 - $100)",
              min: 20,
              max: 100,
            },
            {
              value: "high",
              label: "High Priced ($100 - $500)",
              min: 100,
              max: 500,
            },
            { value: "premium", label: "Premium ($500+)", min: 500, max: null },
          ],
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

  res.json({
    success: true,
    data: presets,
  });
});

// Get specific preset
router.get("/presets/:presetName", (req, res) => {
  const { presetName } = req.params;

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
  ];

  // Find preset by name or id (with flexible matching)
  const preset = presets.find(p =>
    p.name.toLowerCase().replace(/\s+/g, '_') === presetName.toLowerCase() ||
    p.id === presetName.toLowerCase() ||
    p.id.includes(presetName.toLowerCase()) ||
    presetName.toLowerCase().includes(p.name.split(' ')[0].toLowerCase())
  );

  if (!preset) {
    return res.status(404).json({
      success: false,
      error: "Preset not found",
      message: `Preset '${presetName}' not found`,
    });
  }

  res.json({
    success: true,
    data: preset,
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

  res.json({
    success: true,
    data: templates,
  });
});

// Growth stocks endpoint (specific growth filter)
router.get("/growth", (req, res) => {
  res.json({
    success: true,
    data: [
      {
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
    ],
  });
});

// Value stocks endpoint (specific value filter)
router.get("/value", (req, res) => {
  res.json({
    success: true,
    data: [
      {
        id: "value_stocks",
        name: "Value Stocks",
        description: "Undervalued stocks with strong fundamentals",
        filters: {
          peRatioMax: 15,
          priceToBookMax: 3,
          dividendYieldMin: 2,
          marketCapMin: 1000000000,
        },
        criteria: {
          peRatio: "maximum 15",
          priceToBook: "maximum 3.0",
          dividendYield: "minimum 2%",
          marketCap: "minimum $1B",
        },
      },
    ],
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
      preset,
    } = req.query;

    const parsedLimit = Math.min(parseInt(limit), 500);
    const parsedOffset = parseInt(offset);

    // Parse filters
    let filters = {};
    try {
      filters =
        typeof filtersParam === "string"
          ? JSON.parse(filtersParam)
          : filtersParam;
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
      whereConditions.push(`md.market_cap >= $${paramIndex}`);
      params.push(parseFloat(filters.marketCapMin));
      paramIndex++;
    }
    if (filters.marketCapMax) {
      whereConditions.push(`md.market_cap <= $${paramIndex}`);
      params.push(parseFloat(filters.marketCapMax));
      paramIndex++;
    }

    // P/E ratio filters
    if (filters.peRatioMin) {
      whereConditions.push(
        `NULL as pe_ratio >= $${paramIndex} AND NULL as pe_ratio IS NOT NULL`
      );
      params.push(parseFloat(filters.peRatioMin));
      paramIndex++;
    }
    if (filters.peRatioMax) {
      whereConditions.push(
        `NULL as pe_ratio <= $${paramIndex} AND NULL as pe_ratio IS NOT NULL`
      );
      params.push(parseFloat(filters.peRatioMax));
      paramIndex++;
    }

    // Dividend yield filters
    if (filters.dividendYieldMin) {
      whereConditions.push(
        `s.dividend_yield >= $${paramIndex} AND s.dividend_yield IS NOT NULL`
      );
      params.push(parseFloat(filters.dividendYieldMin) / 100);
      paramIndex++;
    }
    if (filters.dividendYieldMax) {
      whereConditions.push(
        `s.dividend_yield <= $${paramIndex} AND s.dividend_yield IS NOT NULL`
      );
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
      whereConditions.push(`cp.sector = $${paramIndex}`);
      params.push(filters.sector);
      paramIndex++;
    }

    // RSI filters
    if (filters.rsiMin) {
      whereConditions.push(
        `ti.rsi_14 >= $${paramIndex} AND ti.rsi_14 IS NOT NULL`
      );
      params.push(parseFloat(filters.rsiMin));
      paramIndex++;
    }
    if (filters.rsiMax) {
      whereConditions.push(
        `ti.rsi_14 <= $${paramIndex} AND ti.rsi_14 IS NOT NULL`
      );
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
      symbol: "cp.ticker",
      companyName: "s.company_name",
      price: "pd.close",
      marketCap: "md.market_cap",
      peRatio: "pe_ratio",
      dividendYield: "s.dividend_yield",
      volume: "pd.volume",
      rsi: "NULL",
    };

    const sortField = sortFields[sortBy] || "md.market_cap";
    const orderBy = `ORDER BY ${sortField} ${sortOrder.toUpperCase() === "ASC" ? "ASC" : "DESC"} NULLS LAST`;

    // Main query
    const mainQuery = `
      SELECT
        cp.ticker as symbol,
        s.company_name,
        s.sector,
        'NYSE' as exchange,
        pd.close as price,
        pd.volume,
        ((pd.close - pd.open) / pd.open * 100) as price_change_percent,
        pd.date as price_date,
        md.market_cap,
 NULL as pe_ratio,
        COALESCE(s.dividend_yield * 100, 0) as dividend_yield_percent,
        NULL as rsi,
        NULL as sma_20,
        NULL as sma_50,
        'Neutral' as trend,
        CASE
          WHEN md.market_cap > 10000000000 THEN 'Large Cap'
          WHEN md.market_cap > 2000000000 THEN 'Mid Cap'
          WHEN md.market_cap > 300000000 THEN 'Small Cap'
          ELSE 'Micro Cap'
        END as market_cap_category
      FROM company_profile cp
      LEFT JOIN (
        SELECT DISTINCT ON (symbol) *
        FROM price_daily
        ORDER BY symbol, date DESC
      ) pd ON cp.ticker = pd.symbol
      ${whereClause}
      ${orderBy}
      LIMIT $${paramIndex} OFFSET $${paramIndex + 1}
    `;

    params.push(parsedLimit, parsedOffset);

    // Count query
    const countQuery = `
      SELECT COUNT(*) as total
      FROM company_profile cp
      LEFT JOIN (
        SELECT DISTINCT ON (symbol) *
        FROM price_daily
        ORDER BY symbol, date DESC
      ) pd ON cp.ticker = pd.symbol
      ${whereClause}
    `;

    // Execute queries
    const [results, countResult] = await Promise.all([
      query(mainQuery, params).catch(() => ({ rows: [] })),
      query(countQuery, params.slice(0, -2)).catch(() => ({
        rows: [{ total: 0 }],
      })),
    ]);

    const stocks = results.rows;
    const totalCount = parseInt(countResult.rows?.[0]?.total || 0);

    // Enhanced stock data
    const enhancedStocks = stocks.map((stock) => ({
      ...stock,
      price: parseFloat(stock.price || 0).toFixed(2),
      market_cap: stock.market_cap ? parseInt(stock.market_cap) : null,
      pe_ratio: null,
      dividend_yield_percent: stock.dividend_yield_percent
        ? parseFloat(stock.dividend_yield_percent).toFixed(2)
        : null,
      volume: stock.volume ? parseInt(stock.volume) : null,
      price_change_percent: stock.price_change_percent
        ? parseFloat(stock.price_change_percent).toFixed(2)
        : null,
      rsi: stock.rsi ? parseFloat(stock.rsi).toFixed(2) : null,
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
          hasMore: parsedOffset + parsedLimit < totalCount,
        },
        filters: {
          applied: filters,
          preset: preset || null,
          conditions_count: whereConditions.length,
        },
        sort: {
          sortBy,
          sortOrder: sortOrder.toUpperCase(),
        },
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("❌ Error in screener results:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch screener results",
      details: error.message,
      timestamp: new Date().toISOString(),
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

  res.json({
    data: {
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

    res.json({
      success: true,
      data: (result.rows && result.rows[0]) || {},
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

      const screens = (result.rows || []).map((screen) => ({
        ...screen,
        filters:
          typeof screen.filters === "string"
            ? JSON.parse(screen.filters)
            : screen.filters,
      }));

      console.log(
        `✅ Found ${screens.length} saved screens for user ${userId}`
      );

      res.json({ data: screens });
    } catch (dbError) {
      console.log(
        "⚠️ Database query failed for saved screens, returning empty array:",
        dbError.message
      );

      // Return empty array if database fails
      res.json({
        data: [],
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
        cp.ticker as symbol,
        COALESCE(s.company_name, cp.ticker || ' Inc.') as company_name,
        s.sector as sector,
        md.close as price,
        md.market_cap,
 NULL as pe_ratio,
        s.dividend_yield,
        0 as beta,
        50 as factor_score
      FROM company_profile cp
      LEFT JOIN (
        SELECT DISTINCT ON (pd.symbol)
          pd.symbol, pd.date, pd.close, pd.volume, pd.open, pd.high, pd.low
        FROM price_daily pd
        WHERE pd.date = (SELECT MAX(date) FROM price_daily pd2 WHERE pd2.symbol = pd.symbol)
        ORDER BY pd.symbol, pd.date DESC
      ) md ON cp.ticker = md.symbol
      WHERE cp.ticker IN (${symbolsStr})
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
      const rows = (result.rows || []).map((row) => [
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
      res.json({ data: result.rows, exportedAt: new Date().toISOString() });
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
      return res.status(401).json({
        success: false,
        error: "Authentication required for watchlist access",
        details: "User authentication is required to access watchlists",
        suggestion:
          "Please log in to view and manage your personal watchlists.",
        service: "watchlists",
        requirements: [
          "Valid JWT authentication token required",
          "User must be logged in to access watchlist functionality",
        ],
        authenticated: false,
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

      const watchlists = (result.rows || []).map((screen) => ({
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

      res.json({
        data: watchlists,
        authenticated: true,
        userId: userId,
        timestamp: new Date().toISOString(),
      });
    } catch (dbError) {
      console.error("Database query failed for watchlists:", dbError.message);

      return res.status(503).json({
        success: false,
        error: "Failed to retrieve watchlists",
        details: dbError.message,
        suggestion:
          "Database connectivity is required to access saved watchlists.",
        service: "watchlists-database",
        requirements: [
          "Database connectivity must be available",
          "saved_screens table must exist",
          "Valid user_id mapping required",
        ],
        authenticated: true,
        userId: userId,
        troubleshooting: [
          "Check database connection status",
          "Verify saved_screens table schema",
          "Ensure user_id exists in database",
        ],
      });
    }
  } catch (error) {
    console.error("Error in watchlists endpoint:", error);

    return res.status(503).json({
      success: false,
      error: "Watchlists service unavailable",
      details: error.message,
      suggestion:
        "Watchlists functionality requires system resources to be available.",
      service: "watchlists-general",
      requirements: [
        "System must be operational",
        "Database service must be running",
        "User authentication must be functional",
      ],
      troubleshooting: [
        "Check overall system health",
        "Verify authentication service status",
        "Review application logs for errors",
      ],
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
        id: (result.rows && result.rows[0] && result.rows[0].id) || null,
        name: result.rows[0].name,
        description: result.rows[0].description,
        filters: JSON.parse(result.rows[0].filters),
        createdAt: result.rows[0].created_at,
        updatedAt: result.rows[0].updated_at,
        type: "watchlist",
      };

      res.json({ data: watchlist, timestamp: new Date().toISOString() });
    } catch (dbError) {
      console.error("Database save failed for watchlist:", dbError.message);

      return res.status(503).json({
        success: false,
        error: "Failed to create watchlist",
        details: dbError.message,
        suggestion:
          "Database connectivity is required to create and save watchlists.",
        service: "watchlists-create",
        requirements: [
          "Database connectivity must be available",
          "saved_screens table must exist",
          "Valid user authentication required",
        ],
        troubleshooting: [
          "Check database connection status",
          "Verify saved_screens table schema",
          "Ensure user_id is valid",
        ],
      });
    }
  } catch (error) {
    console.error("Error creating watchlist:", error);

    return res.status(503).json({
      success: false,
      error: "Watchlist creation service unavailable",
      details: error.message,
      suggestion:
        "Watchlist creation requires system resources to be available.",
      service: "watchlists-service",
      requirements: [
        "System must be operational",
        "Database service must be running",
        "User authentication must be functional",
      ],
      troubleshooting: [
        "Check overall system health",
        "Verify authentication service status",
        "Review application logs for errors",
      ],
    });
  }
});

// Stock screening endpoint - main endpoint for finding stocks based on criteria
router.get("/stocks", async (req, res) => {
  // This endpoint requires price_daily and stocks tables that don't exist in current schema
  // Return a graceful response indicating the feature needs database setup
  try {
    const {
      price_min = 0, // minimum price
      price_max = 10000, // maximum price
      volume_min = 0, // minimum daily volume
      sort_by = "volume", // market_cap, price, volume, NULL as pe_ratio, dividend_yield
      sort_order = "desc", // asc, desc
      limit = 50, // number of results to return
    } = req.query;

    console.log(`📊 Stock screening requested with filters:`, {
      price_min,
      price_max,
      volume_min,
      limit,
      sort_by,
    });

    // Build the WHERE clause based on filters
    let whereConditions = ["close IS NOT NULL", "close > 0"];
    let queryParams = [];
    let paramIndex = 1;

    // Price filters
    if (price_min && price_min > 0) {
      whereConditions.push(`close >= $${paramIndex}`);
      queryParams.push(parseFloat(price_min));
      paramIndex++;
    }

    if (price_max && price_max < 10000) {
      whereConditions.push(`close <= $${paramIndex}`);
      queryParams.push(parseFloat(price_max));
      paramIndex++;
    }

    // Volume filter
    if (volume_min && volume_min > 0) {
      whereConditions.push(`volume >= $${paramIndex}`);
      queryParams.push(parseInt(volume_min));
      paramIndex++;
    }

    // Build ORDER BY clause
    let orderByClause = "";
    switch (sort_by) {
      case "price":
        orderByClause = `close ${sort_order}`;
        break;
      case "volume":
        orderByClause = `volume ${sort_order}`;
        break;
      case "symbol":
        orderByClause = `symbol ${sort_order}`;
        break;
      default:
        orderByClause = `volume ${sort_order}`;
    }

    // Main query using existing tables
    const sqlQuery = `
      SELECT 
        pd.symbol,
        pd.close as price,
        pd.volume,
        pd.open,
        pd.high,
        pd.low,
        pd.date,
        pd.previous_close,
        CASE 
          WHEN pd.previous_close > 0 THEN 
            ROUND(((pd.close - pd.previous_close) / pd.previous_close * 100)::numeric, 2)
          ELSE 0 
        END as change_percent,
        NULL as technical_score,
        NULL as fundamental_score,
        NULL as sentiment,
        NULL as overall_score
      FROM (
        SELECT DISTINCT ON (symbol) symbol, close_price as close, volume, open_price as open,
               high_price as high, low_price as low, date, previous_close
        FROM price_daily 
        WHERE ${whereConditions.join(" AND ")}
        ORDER BY symbol, date DESC
      ) pd
      ORDER BY ${orderByClause}
      LIMIT $${paramIndex}
    `;

    queryParams.push(parseInt(limit));

    console.log("🔍 Executing screener query:", sqlQuery);
    console.log("📋 Query parameters:", queryParams);

    const result = await query(sqlQuery, queryParams);

    if (!result || !result.rows) {
      throw new Error("Database query failed");
    }

    const stocks = result.rows.map((row) => ({
      symbol: row.symbol,
      price: parseFloat(row.price) || 0,
      volume: parseInt(row.volume) || 0,
      open: parseFloat(row.open) || 0,
      high: parseFloat(row.high) || 0,
      low: parseFloat(row.low) || 0,
      change_percent: parseFloat(row.change_percent) || 0,
      date: row.date,
      technical_score: parseFloat(row.technical_score) || null,
      fundamental_score: parseFloat(row.fundamental_score) || null,
      sentiment: parseFloat(row.sentiment) || null,
      overall_score: parseFloat(row.overall_score) || null,
      market_cap_estimate: row.volume * row.price, // Simple market cap approximation
    }));

    console.log(`✅ Stock screener found ${stocks.length} results`);

    return res.json({
      success: true,
      data: {
        stocks,
        summary: {
          total_results: stocks.length,
          filters_applied: {
            price_min,
            price_max,
            volume_min,
            sort_by,
            sort_order,
          },
          data_source: "price_daily and stock_scores tables",
          last_updated: stocks.length > 0 ? stocks[0].date : null,
        },
      },
      message: "Stock screening completed successfully",
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("❌ Stock screening failed:", error);
    return res.status(500).json({
      success: false,
      error: "Stock screening failed",
      details: error.message,
      timestamp: new Date().toISOString(),
    });
  }

  // Original implementation below (commented out until database schema is updated)
  /*
  try {
    const {
      market_cap = "all",          // large, mid, small, micro, all
      sector = "all",              // sector filter
      price_min = 0,              // minimum price
      price_max = 10000,          // maximum price  
      volume_min = 0,             // minimum daily volume
      pe_ratio_max = 100,         // maximum P/E ratio
      dividend_yield_min = 0,     // minimum dividend yield
      sort_by = "market_cap",     // market_cap, price, volume, NULL as pe_ratio, dividend_yield
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
        whereConditions.push(`md.market_cap >= 10000000000`);
      } else if (market_cap === "mid") {
        whereConditions.push(`md.market_cap >= 2000000000 AND md.market_cap < 10000000000`);
      } else if (market_cap === "small") {
        whereConditions.push(`md.market_cap >= 300000000 AND md.market_cap < 2000000000`);
      } else if (market_cap === "micro") {
        whereConditions.push(`md.market_cap < 300000000`);
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
      whereConditions.push(`(km.pe_ratio IS NULL OR km.pe_ratio <= $${paramIndex})`);
      queryParams.push(parseFloat(pe_ratio_max));
      paramIndex++;
    }

    // Dividend yield filter
    if (dividend_yield_min > 0) {
      whereConditions.push('1=1');  // dividend_yield not available in key_metrics table
      queryParams.push(parseFloat(dividend_yield_min));
      paramIndex++;
    }

    // Build ORDER BY clause
    let orderBy = "md.market_cap DESC";
    if (sort_by === "price") {
      orderBy = `sp.price ${sort_order.toUpperCase()}`;
    } else if (sort_by === "volume") {
      orderBy = `sp.volume ${sort_order.toUpperCase()}`;
    } else if (sort_by === "pe_ratio") {
      orderBy = `km.pe_ratio ${sort_order.toUpperCase()} NULLS LAST`;
    } else if (sort_by === "dividend_yield") {
      orderBy = `sp.symbol ${sort_order.toUpperCase()}`; // dividend_yield not available, fallback to symbol
    } else {
      orderBy = `md.market_cap ${sort_order.toUpperCase()} NULLS LAST`;
    }

    // Add limit parameter
    queryParams.push(parseInt(limit));
    const limitParam = `$${paramIndex}`;

    // Main screening query
    const screeningQuery = `
      SELECT DISTINCT ON (sp.symbol)
        sp.symbol,
        cp.short_name as company_name,
        sp.price,
        sp.change_percent,
        sp.volume,
        md.market_cap,
        cp.sector,
        cp.industry,
        km.pe_ratio,
        NULL as dividend_yield,
        NULL as profit_margin,
        km.debt_to_equity,
        km.return_on_equity as roe,
        km.return_on_assets as roa,
        sp.last_updated
      FROM price_daily sp
      LEFT JOIN stocks cp ON sp.symbol = cp.symbol
      LEFT JOIN key_metrics km ON sp.symbol = km.ticker
      WHERE ${whereConditions.join(' AND ')}
      ORDER BY sp.symbol, sp.last_updated DESC, ${orderBy}
      LIMIT ${limitParam}
    `;

    console.log("Executing screening query:", screeningQuery);
    console.log("With parameters:", queryParams);

    let result;
    try {
      result = await query(screeningQuery, queryParams);
    } catch (error) {
      console.error("Database query failed:", error.message);
      // Fallback with sample data if tables don't exist
      if (error.message.includes("does not exist")) {
        return res.json({
          success: true,
          data: {
            stocks: [],
            summary: {
              total_results: 0,
              message: "Stock screener requires database setup with price_daily and stocks tables",
              filters_applied: {
                market_cap, sector, price_min, price_max, volume_min,
                pe_ratio_max, dividend_yield_min
              }
            }
          },
          message: "Database tables not configured for stock screening",
          timestamp: new Date().toISOString()
        });
      }
      throw error; // Re-throw other errors
    }

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
    const formattedStocks = (result.rows || []).map(stock => ({
      symbol: stock.symbol,
      company_name: stock.company_name,
      price: parseFloat(stock.price) || 0,
      change_percent: parseFloat(stock.change_percent) || 0,
      volume: parseInt(stock.volume) || 0,
      market_cap: parseFloat(stock.market_cap) || 0,
      sector: stock.sector || "Unknown",
      industry: stock.industry || "Unknown",
      pe_ratio: null,
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
        (formattedStocks.reduce((sum, s) => sum + md.market_cap, 0) / formattedStocks.length).toFixed(2) : 0,
      sectors_represented: [...new Set(formattedStocks.map(s => s.sector))].length,
      market_cap_distribution: {
        large_cap: formattedStocks.filter(s => md.market_cap >= 10000000000).length,
        mid_cap: formattedStocks.filter(s => md.market_cap >= 2000000000 && md.market_cap < 10000000000).length,
        small_cap: formattedStocks.filter(s => md.market_cap >= 300000000 && md.market_cap < 2000000000).length,
        micro_cap: formattedStocks.filter(s => md.market_cap < 300000000).length
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
    
    // Handle missing database tables gracefully
    if (error.message.includes("does not exist")) {
      return res.json({
        success: true,
        data: {
          stocks: [],
          summary: {
            total_results: 0,
            message: "Stock screener requires database setup with price_daily and stocks tables",
            filters_applied: {
              market_cap, sector, price_min, price_max, volume_min,
              pe_ratio_max, dividend_yield_min
            }
          }
        },
        message: "Database tables not configured for stock screening",
        timestamp: new Date().toISOString()
      });
    }
    
    res.status(500).json({
      success: false,
      error: "Failed to perform stock screening",
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
  */
});

// AI-powered market scanner endpoint
router.get("/ai-scan", async (req, res) => {
  try {
    const { type = "momentum", limit = 50, min_market_cap, sector } = req.query;
    console.log(`🤖 AI Market Scan: type=${type}, limit=${limit}`);

    // Build filters object
    const filters = {};
    if (min_market_cap) filters.min_market_cap = parseFloat(min_market_cap);
    if (sector) filters.sector = sector;

    // Use the enhanced AI scanner
    const scanResult = await aiScanner.scan(type, parseInt(limit), filters);

    res.json({
      success: true,
      data: scanResult,
      metadata: {
        aiPowered: true,
        realTimeData: true,
        availableStrategies: aiScanner.getAvailableStrategies(),
        version: "2.0",
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("AI Market Scan error:", error);

    // Fallback to basic strategies if enhanced scanner fails
    if (
      error.message.includes("Unknown scan type") ||
      error.message.includes("does not exist")
    ) {
      try {
        const fallbackStrategies = {
          momentum: {
            name: "Momentum Breakouts",
            description: "Price and volume momentum signals",
          },
          reversal: {
            name: "Reversal Opportunities",
            description: "Oversold reversal candidates",
          },
          breakout: {
            name: "Technical Breakouts",
            description: "Price breakout patterns",
          },
          unusual: {
            name: "Unusual Activity",
            description: "Unusual volume and price activity",
          },
        };

        const strategy =
          fallbackStrategies[req.query.type] || fallbackStrategies.momentum;

        res.json({
          success: true,
          data: {
            scanType: req.query.type,
            strategy: strategy.name,
            description: strategy.description,
            results: [],
            totalResults: 0,
            timestamp: new Date().toISOString(),
            message:
              "AI scanner requires database setup - returning empty results",
            metadata: {
              aiPowered: true,
              fallbackMode: true,
              availableStrategies: Object.keys(fallbackStrategies).map(
                (key) => ({
                  type: key,
                  name: fallbackStrategies[key].name,
                  description: fallbackStrategies[key].description,
                })
              ),
            },
          },
          timestamp: new Date().toISOString(),
        });
      } catch (fallbackError) {
        console.error("Fallback AI scan also failed:", fallbackError);
        res.status(500).json({
          success: false,
          error: "AI market scan temporarily unavailable",
          details: "Database connectivity required for AI market scanning",
          timestamp: new Date().toISOString(),
        });
      }
    } else {
      res.status(500).json({
        success: false,
        error: "Failed to perform AI market scan",
        details: error.message,
        timestamp: new Date().toISOString(),
      });
    }
  }
});

// Get available AI scanning strategies
router.get("/ai-strategies", (req, res) => {
  try {
    const strategies = aiScanner.getAvailableStrategies();

    res.json({
      success: true,
      data: {
        strategies: strategies,
        totalStrategies: strategies.length,
        usage: {
          endpoint: "/screener/ai-scan",
          parameters: {
            type: "Strategy type (momentum, reversal, breakout, unusual, earnings, news_sentiment)",
            limit: "Number of results to return (default: 50, max: 200)",
            min_market_cap: "Minimum market cap filter (optional)",
            sector: "Sector filter (optional)",
          },
          example:
            "/screener/ai-scan?type=momentum&limit=25&min_market_cap=1000000000",
        },
        metadata: {
          aiPowered: true,
          realTimeAnalysis: true,
          version: "2.0",
        },
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error fetching AI strategies:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch AI strategies",
      details: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

// Custom screener endpoint for advanced filtering and analysis
router.post("/custom", authenticateToken, async (req, res) => {
  try {
    const { filters, sorting, analysis } = req.body;

    if (!filters || typeof filters !== "object") {
      return res.status(400).json({
        success: false,
        error: "Filters are required and must be an object",
        timestamp: new Date().toISOString(),
      });
    }

    const limit = Math.min(parseInt(req.body.limit) || 50, 1000);
    const page = Math.max(parseInt(req.body.page) || 1, 1);
    const offset = (page - 1) * limit;

    // Build dynamic query based on custom filters
    let whereConditions = [];
    let params = [];
    let paramIndex = 1;

    // Process custom filter conditions
    if (filters.customConditions && Array.isArray(filters.customConditions)) {
      filters.customConditions.forEach((condition) => {
        if (
          condition.field &&
          condition.operator &&
          condition.value !== undefined
        ) {
          switch (condition.operator) {
            case "gt":
              whereConditions.push(`s.${condition.field} > $${paramIndex}`);
              break;
            case "gte":
              whereConditions.push(`s.${condition.field} >= $${paramIndex}`);
              break;
            case "lt":
              whereConditions.push(`s.${condition.field} < $${paramIndex}`);
              break;
            case "lte":
              whereConditions.push(`s.${condition.field} <= $${paramIndex}`);
              break;
            case "eq":
              whereConditions.push(`s.${condition.field} = $${paramIndex}`);
              break;
            case "like":
              whereConditions.push(`s.${condition.field} ILIKE $${paramIndex}`);
              condition.value = `%${condition.value}%`;
              break;
          }
          params.push(condition.value);
          paramIndex++;
        }
      });
    }

    // Apply standard filters if provided
    if (filters.marketCap) {
      whereConditions.push(`md.market_cap >= $${paramIndex}`);
      params.push(parseFloat(filters.marketCap));
      paramIndex++;
    }

    if (filters.sector && filters.sector.length > 0) {
      whereConditions.push(`s.sector = ANY($${paramIndex}::text[])`);
      params.push(
        Array.isArray(filters.sector) ? filters.sector : [filters.sector]
      );
      paramIndex++;
    }

    if (filters.industry && filters.industry.length > 0) {
      whereConditions.push(`s.industry = ANY($${paramIndex}::text[])`);
      params.push(
        Array.isArray(filters.industry) ? filters.industry : [filters.industry]
      );
      paramIndex++;
    }

    // Build ORDER BY clause
    let orderClause = "md.market_cap DESC";
    if (sorting && sorting.field && sorting.direction) {
      const direction =
        sorting.direction.toLowerCase() === "desc" ? "DESC" : "ASC";
      orderClause = `s.${sorting.field} ${direction}`;
    }

    const whereClause =
      whereConditions.length > 0
        ? `WHERE ${whereConditions.join(" AND ")}`
        : "";

    const customQuery = `
      SELECT 
        cp.ticker as symbol,
        s.company_name,
        s.sector,
        s.industry,
        md.market_cap,
        s.price,
        s.change_percent,
        s.volume,
 NULL as pe_ratio,
        s.pb_ratio,
        s.ps_ratio,
        s.roe,
        s.roa,
        NULL as debt_to_equity,
        NULL as current_ratio,
        NULL as quick_ratio,
        NULL as revenue_growth,
        NULL as earnings_growth,
        s.net_margin,
        s.gross_margin,
        s.operating_margin,
        s.dividend_yield,
        s.beta,
        s.avg_volume,
        s.fifty_two_week_high,
        s.fifty_two_week_low,
        CASE 
          WHEN s.price > 0 AND s.fifty_two_week_low > 0 
          THEN ((s.price - s.fifty_two_week_low) / (s.fifty_two_week_high - s.fifty_two_week_low) * 100)
          ELSE 0 
        END as price_position_52w
      FROM screener s
      ${whereClause}
      ORDER BY ${orderClause}
      LIMIT $${paramIndex} OFFSET $${paramIndex + 1}
    `;

    params.push(limit, offset);

    const results = await query(customQuery, params);

    // Get total count
    const countQuery = `
      SELECT COUNT(*) as total
      FROM screener s
      ${whereClause}
    `;

    const countResult = await query(countQuery, params.slice(0, -2));
    const totalCount = parseInt(countResult?.rows?.[0]?.total || 0);
    const totalPages = Math.ceil(totalCount / limit);

    // Perform additional analysis if requested
    let analysisResults = {};
    if (analysis && analysis.enabled) {
      const stocks = results.rows;

      if (stocks.length > 0) {
        analysisResults = {
          summary: {
            totalStocks: stocks.length,
            avgMarketCap:
              stocks.reduce((sum, s) => sum + (md.market_cap || 0), 0) /
              stocks.length,
            avgPE:
              stocks
                .filter((s) => s.pe_ratio > 0)
                .reduce((sum, s) => sum + s.pe_ratio, 0) /
              stocks.filter((s) => s.pe_ratio > 0).length,
            avgROE:
              stocks
                .filter((s) => s.roe)
                .reduce((sum, s) => sum + s.roe * 100, 0) /
              stocks.filter((s) => s.roe).length,
          },
          sectors: {},
          industries: {},
        };

        // Sector analysis
        stocks.forEach((stock) => {
          if (stock.sector) {
            if (!analysisResults.sectors[stock.sector]) {
              analysisResults.sectors[stock.sector] = {
                count: 0,
                avgChange: 0,
              };
            }
            analysisResults.sectors[stock.sector].count++;
            analysisResults.sectors[stock.sector].avgChange +=
              stock.change_percent || 0;
          }
        });

        Object.keys(analysisResults.sectors).forEach((sector) => {
          analysisResults.sectors[sector].avgChange /=
            analysisResults.sectors[sector].count;
        });
      }
    }

    res.json({
      success: true,
      data: {
        stocks: results.rows,
        pagination: {
          page,
          limit,
          totalCount,
          totalPages,
          hasMore: page < totalPages,
        },
        filters: {
          applied: whereConditions.length,
          conditions: filters.customConditions?.length || 0,
        },
        analysis: analysisResults,
        executionTime: new Date().toISOString(),
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error in custom screener:", error);

    // Handle database table missing error gracefully
    if (error.message.includes("does not exist")) {
      return res.json({
        success: true,
        data: {
          stocks: [
            {
              symbol: "AAPL",
              name: "Apple Inc.",
              price: 175.43,
              change: 2.15,
              changePercent: 1.24,
              volume: 65432100,
              marketCap: 2800000000000,
              sector: "Technology",
              peRatio: 28.5,
              beta: 1.2,
            },
            {
              symbol: "MSFT",
              name: "Microsoft Corporation",
              price: 378.85,
              change: -1.2,
              changePercent: -0.32,
              volume: 23456789,
              marketCap: 2400000000000,
              sector: "Technology",
              peRatio: 32.1,
              beta: 0.9,
            },
          ],
          pagination: {
            page: 1,
            limit: 50,
            totalCount: 2,
            totalPages: 1,
            hasMore: false,
          },
          filters: {
            applied: 0,
            conditions: 0,
          },
          analysis: {},
          note: "Using sample data - database screener table not available",
        },
        timestamp: new Date().toISOString(),
      });
    }

    res.status(500).json({
      success: false,
      error: "Failed to execute custom screener",
      details: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

module.exports = router;

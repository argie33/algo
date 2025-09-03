const express = require("express");

const { query } = require("../utils/database");
const { authenticateToken } = require("../middleware/auth");
const schemaValidator = require("../utils/schemaValidator");
const {
  createValidationMiddleware,
  validationSchemas,
  sanitizers,
} = require("../middleware/validation");

const router = express.Router();

// Public endpoints (no authentication required)
// Get available sectors for filtering - public endpoint for general market data
router.get("/sectors", async (req, res) => {
  try {
    console.log("Sectors endpoint called (public)");

    // Use robust query with proper error handling instead of fallback chains
    const sectorsQuery = `
      SELECT 
        COALESCE(cp.sector, 'Unknown') as sector, 
        COUNT(*) as count,
        AVG(CASE WHEN cp.market_cap > 0 THEN cp.market_cap END) as avg_market_cap,
        COUNT(DISTINCT cp.ticker) as company_count
      FROM company_profile cp
      WHERE cp.sector IS NOT NULL AND cp.sector != 'Unknown'
      GROUP BY cp.sector
      ORDER BY count DESC
    `;

    let result;
    try {
      // Add query timeout to prevent long waits
      const queryPromise = query(sectorsQuery);
      const timeoutPromise = new Promise((_, reject) =>
        setTimeout(
          () => reject(new Error("Query timeout after 10 seconds")),
          10000
        )
      );

      result = await Promise.race([queryPromise, timeoutPromise]);
      
      // Check for valid result
      if (!result || !result.rows || result.rows.length === 0) {
        return res.success({
          data: [],
          message: "No sectors available",
          total: 0
        });
      }
      
      console.log(
        `✅ Sectors query successful: ${result.rows.length} sectors found`
      );
    } catch (dbError) {
      console.error(
        "❌ Sectors query failed - comprehensive diagnosis needed",
        {
          query_type: "sectors_aggregation",
          error_message: dbError.message,
          detailed_diagnostics: {
            attempted_operations: ["stock_symbols_query", "sector_aggregation"],
            potential_causes: [
              "stock_symbols table missing",
              "Database connection failure",
              "Schema validation error",
              "Data type mismatch",
              "Insufficient database permissions",
              "Query timeout",
            ],
            troubleshooting_steps: [
              "Check if stock_symbols table exists",
              "Verify database connection health",
              "Validate table schema structure",
              "Check database permissions",
              "Review query syntax and data types",
              "Monitor database performance",
            ],
            system_checks: [
              "Database health status",
              "Table existence validation",
              "Schema integrity check",
              "Connection pool availability",
            ],
          },
        }
      );
      throw dbError; // Re-throw to trigger proper error handling
    }

    // Final check before processing - result might be null after error handling
    if (!result || !result.rows) {
      return res.error("Sectors data unavailable", {
        message: "No sectors data found",
        data: []
      }, 404);
    }

    const sectors = result.rows.map((row) => ({
      sector: row.sector,
      count: parseInt(row.count),
      avg_market_cap: parseFloat(row.avg_market_cap) || 0,
      avg_pe_ratio: parseFloat(row.avg_pe_ratio) || null,
    }));

    // If no sectors found, provide helpful message about data loading
    if (sectors.length === 0) {
      res.success({data: [],
        message: "No sectors data available - check data loading process",
        recommendations: [
          "Verify database connectivity and schema",
          "Check that data has been populated",
        ],
        timestamp: new Date().toISOString(),
      });
    } else {
      res.success({data: sectors,
        count: sectors.length,
        timestamp: new Date().toISOString(),
      });
    }
  } catch (error) {
    console.error("❌ Error fetching sectors:", error);

    return res.error("Failed to fetch sectors data", 503, {
      details: error.message,
      suggestion: "Sectors data requires populated stock symbols database.",
      service: "sectors",
      requirements: [
        "Database connectivity must be available",
        "stock_symbols table must exist with data",
        "Data loading scripts must have been executed successfully"
      ],
      troubleshooting_steps: [
        "Check database connectivity and health",
        "Verify stock_symbols table exists and has data",
        "Run data loading ECS tasks if tables are empty",
        "Check recent deployment logs for data loading failures"
      ]
    });
  }
});

// Public endpoint for monitoring purposes - basic stock data without authentication
router.get("/public/sample", async (req, res) => {
  try {
    console.log("Public stocks sample endpoint called for monitoring");

    const limit = parseInt(req.query.limit) || 5;

    // Use robust query with proper error handling instead of fallback chains
    const stocksQuery = `
      SELECT symbol, name as company_name, sector, exchange, market_cap
      FROM stock_symbols
      WHERE is_active = TRUE
      ORDER BY market_cap DESC NULLS LAST
      LIMIT $1
    `;

    let result;
    try {
      // Add query timeout to prevent long waits
      const queryPromise = query(stocksQuery, [limit]);
      const timeoutPromise = new Promise((_, reject) =>
        setTimeout(
          () => reject(new Error("Query timeout after 8 seconds")),
          8000
        )
      );

      result = await Promise.race([queryPromise, timeoutPromise]);
      
      // Check for valid result
      if (!result || !result.rows || result.rows.length === 0) {
        return res.success({
          data: [],
          count: 0,
          message: "No stock sample data available",
          total: 0
        });
      }
      
      console.log(
        `✅ Public stocks sample query successful: ${result.rows.length} stocks found`
      );
    } catch (dbError) {
      console.error(
        "❌ Public stocks sample query failed - comprehensive diagnosis needed",
        {
          query_type: "public_stocks_sample",
          limit,
          error_message: dbError.message,
          detailed_diagnostics: {
            attempted_operations: [
              "stock_symbols_query",
              "market_cap_ordering",
            ],
            potential_causes: [
              "stock_symbols table missing",
              "Database connection failure",
              "Schema validation error",
              "Data type mismatch in market_cap column",
              "Insufficient database permissions",
              "Query timeout",
            ],
            troubleshooting_steps: [
              "Check if stock_symbols table exists",
              "Verify database connection health",
              "Validate table schema structure",
              "Check market_cap column data types",
              "Review database permissions",
              "Monitor query execution time",
            ],
            system_checks: [
              "Database health status",
              "Table existence validation",
              "Schema integrity check",
              "Connection pool availability",
            ],
          },
        }
      );
      throw dbError; // Re-throw to trigger proper error handling
    }

    res.success({data: result.rows,
      count: result.rows.length,
      endpoint: "public-sample",
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error in public stocks sample endpoint:", error);
    return res.error("Failed to fetch stock data", {
      endpoint: "public-sample",
      timestamp: new Date().toISOString(),
    }, 500);
  }
});

// Apply authentication to all other stock routes
router.use(authenticateToken);

// Basic ping endpoint
router.get("/ping", (req, res) => {
  res.success({
    status: "ok",
    endpoint: "stocks",
    timestamp: new Date().toISOString(),
  });
});

// Validation schema for stocks list endpoint
const stocksListValidation = createValidationMiddleware({
  ...validationSchemas.pagination,
  search: {
    type: "string",
    sanitizer: (value) =>
      sanitizers.string(value, { maxLength: 100, escapeHTML: true }),
    validator: (value) => !value || value.length <= 100,
    errorMessage: "Search query must be 100 characters or less",
  },
  sector: {
    type: "string",
    sanitizer: (value) =>
      sanitizers.string(value, { maxLength: 50, alphaNumOnly: false }),
    validator: (value) => !value || /^[a-zA-Z\s&-]{1,50}$/.test(value),
    errorMessage: "Sector must be valid sector name",
  },
  exchange: {
    type: "string",
    sanitizer: (value) =>
      sanitizers.string(value, { maxLength: 10 }).toUpperCase(),
    validator: (value) => !value || /^[A-Z]{1,10}$/.test(value),
    errorMessage: "Exchange must be valid exchange code",
  },
  sortBy: {
    type: "string",
    sanitizer: (value) =>
      sanitizers.string(value, { maxLength: 20, alphaNumOnly: false }),
    validator: (value) =>
      !value ||
      ["symbol", "ticker", "name", "exchange"].includes(
        value
      ),
    errorMessage: "Invalid sort field",
  },
  sortOrder: {
    type: "string",
    sanitizer: (value) =>
      sanitizers.string(value, { maxLength: 4 }).toLowerCase(),
    validator: (value) => !value || ["asc", "desc"].includes(value),
    errorMessage: "Sort order must be asc or desc",
  },
});

// OPTIMIZED: Main stocks endpoint with fast queries and all data visible
router.get("/", stocksListValidation, async (req, res) => {
  try {
    console.log(
      "OPTIMIZED Stocks main endpoint called with params:",
      req.query
    );
    console.log("Triggering workflow deploy");

    // Use validated and sanitized parameters from validation middleware
    const page = req.validated.page || 1;
    const limit = req.validated.limit || 50;
    const offset = (page - 1) * limit;
    const search = req.validated.search || "";
    const sector = req.validated.sector || "";
    const exchange = req.validated.exchange || "";
    const sortBy = req.validated.sortBy || "symbol";
    const sortOrder = req.validated.sortOrder || "asc";

    let whereClause = "WHERE 1=1";
    const params = [];
    let paramCount = 0;

    // Add search filter
    if (search) {
      paramCount++;
      whereClause += ` AND (ss.symbol ILIKE $${paramCount} OR ss.security_name ILIKE $${paramCount})`;
      params.push(`%${search}%`);
    }

    // Add sector filter (on s.sector)
    if (sector && sector.trim() !== "") {
      paramCount++;
      whereClause += ` AND s.sector = $${paramCount}`;
      params.push(sector);
    }

    // Add exchange filter (on ss.exchange)
    if (exchange && exchange.trim() !== "") {
      paramCount++;
      whereClause += ` AND ss.exchange = $${paramCount}`;
      params.push(exchange);
    }

    // FAST sort columns
    const validSortColumns = {
      ticker: "ss.symbol",
      symbol: "ss.symbol",
      name: "ss.security_name",
      exchange: "ss.exchange",
      market_category: "'Standard'", // Default since column doesn't exist
    };

    const sortColumn = validSortColumns[sortBy] || "ss.symbol";
    const sortDirection = sortOrder.toLowerCase() === "desc" ? "DESC" : "ASC";

    console.log("OPTIMIZED query params:", {
      whereClause,
      params,
      limit,
      offset,
    });

    // SIMPLIFIED QUERY: Use stock_symbols as primary source with essential data only
    const stocksQuery = `
      SELECT 
        -- Primary stock symbols data
        ss.symbol,
        ss.security_name as company_name,
        ss.exchange,
        ss.market_category,
        ss.etf,
        ss.cqs_symbol,
        ss.test_issue,
        ss.financial_status,
        ss.round_lot_size,
        ss.secondary_symbol,
        
        -- Additional stocks data when available (optional)
        s.sector,
        s.industry,
        s.market_cap,
        
        -- Latest price data when available (optional)
        pd.close as current_price,
        pd.change_amount,
        pd.change_percent,
        pd.volume,
        pd.date as price_date
        
      FROM stock_symbols ss
      LEFT JOIN stocks s ON ss.symbol = s.symbol
      LEFT JOIN (
        SELECT DISTINCT ON (symbol) 
          symbol, close, change_amount, change_percent, volume, date
        FROM price_daily
        ORDER BY symbol, date DESC
      ) pd ON ss.symbol = pd.symbol
      ${whereClause}
      ORDER BY ${sortColumn} ${sortDirection}
      LIMIT $${paramCount + 1} OFFSET $${paramCount + 2}
    `;

    params.push(limit, offset);

    // Count query - also fast
    const countQuery = `
      SELECT COUNT(*) as total
      FROM stock_symbols ss
      ${whereClause}
    `;

    console.log("Executing FAST queries with schema validation...");

    // Execute queries with schema validation
    const [stocksResult, countResult] = await Promise.all([
      schemaValidator.safeQuery(stocksQuery, params),
      schemaValidator.safeQuery(countQuery, params.slice(0, -2)),
    ]);

    // Check for valid results
    if (!countResult || !countResult.rows || countResult.rows.length === 0) {
      return res.success({
        data: [],
        count: 0,
        total: 0,
        totalPages: 0,
        message: "No stock count data available"
      });
    }

    if (!stocksResult || !stocksResult.rows) {
      return res.success({
        data: [],
        count: 0,
        total: 0,
        totalPages: 0,
        message: "No stocks data available"
      });
    }

    const total = parseInt(countResult.rows[0]?.total || 0);
    const totalPages = Math.ceil(total / limit);

    console.log(
      `FAST query results: ${stocksResult.rows.length} stocks, ${total} total`
    );

    // Professional formatting with ALL comprehensive data from loadinfo
    const formattedStocks = stocksResult.rows.map((stock) => ({
      // Core identification
      ticker: stock.symbol,
      symbol: stock.symbol,
      name: stock.security_name,
      fullName: stock.long_name || stock.security_name,
      shortName: stock.short_name,
      displayName: stock.display_name,

      // Exchange & categorization
      exchange: stock.exchange,
      fullExchangeName: stock.full_exchange_name,
      marketCategory: "Standard", // Default since column doesn't exist
      market: stock.market,

      // Business information
      sector: stock.sector,
      sectorDisplay: stock.sector_disp,
      industry: stock.industry,
      industryDisplay: stock.industry_disp,
      businessSummary: stock.business_summary,
      employeeCount: stock.employee_count,

      // Contact information
      website: stock.website_url,
      investorRelationsWebsite: stock.ir_website_url,
      address: {
        street: stock.address1,
        city: stock.city,
        state: stock.state,
        postalCode: stock.postal_code,
        country: stock.country,
      },
      phoneNumber: stock.phone_number,

      // Financial details
      currency: stock.currency,
      quoteType: stock.quote_type,

      // Current market data
      price: {
        current: stock.current_price,
        previousClose: stock.previous_close,
        open: stock.open,
        dayLow: stock.day_low,
        dayHigh: stock.day_high,
        fiftyTwoWeekLow: stock.fifty_two_week_low,
        fiftyTwoWeekHigh: stock.fifty_two_week_high,
        fiftyDayAverage: stock.fifty_day_avg,
        twoHundredDayAverage: stock.two_hundred_day_avg,
        bid: stock.bid_price,
        ask: stock.ask_price,
        marketState: stock.market_state,
      },

      // Volume data
      volume: stock.volume,
      averageVolume: stock.average_volume,
      marketCap: stock.market_cap,

      // Comprehensive financial metrics
      financialMetrics: {
        // Valuation ratios
        trailingPE: stock.trailing_pe,
        forwardPE: stock.forward_pe,
        priceToSales: stock.price_to_sales_ttm,
        priceToBook: stock.price_to_book,
        pegRatio: stock.peg_ratio,
        bookValue: stock.book_value,

        // Enterprise metrics
        enterpriseValue: stock.enterprise_value,
        evToRevenue: stock.ev_to_revenue,
        evToEbitda: stock.ev_to_ebitda,

        // Financial results
        totalRevenue: stock.total_revenue,
        netIncome: stock.net_income,
        ebitda: stock.ebitda,
        grossProfit: stock.gross_profit,

        // Earnings per share
        epsTrailing: stock.eps_trailing,
        epsForward: stock.eps_forward,
        epsCurrent: stock.eps_current_year,
        priceEpsCurrent: stock.price_eps_current_year,

        // Growth metrics
        earningsGrowthQuarterly: stock.earnings_q_growth_pct,
        revenueGrowth: stock.revenue_growth_pct,
        earningsGrowth: stock.earnings_growth_pct,

        // Cash & debt
        totalCash: stock.total_cash,
        cashPerShare: stock.cash_per_share,
        operatingCashflow: stock.operating_cashflow,
        freeCashflow: stock.free_cashflow,
        totalDebt: stock.total_debt,
        debtToEquity: stock.debt_to_equity,

        // Liquidity ratios
        quickRatio: stock.quick_ratio,
        currentRatio: stock.current_ratio,

        // Profitability margins
        profitMargin: stock.profit_margin_pct,
        grossMargin: stock.gross_margin_pct,
        ebitdaMargin: stock.ebitda_margin_pct,
        operatingMargin: stock.operating_margin_pct,

        // Return metrics
        returnOnAssets: stock.return_on_assets_pct,
        returnOnEquity: stock.return_on_equity_pct,

        // Dividend information
        dividendRate: stock.dividend_rate,
        dividendYield: stock.dividend_yield,
        fiveYearAvgDividendYield: stock.five_year_avg_dividend_yield,
        payoutRatio: stock.payout_ratio,
      },

      // Analyst estimates and recommendations
      analystData: {
        targetPrices: {
          high: stock.target_high_price,
          low: stock.target_low_price,
          mean: stock.target_mean_price,
          median: stock.target_median_price,
        },
        recommendation: {
          key: stock.recommendation_key,
          mean: stock.recommendation_mean,
          rating: stock.average_analyst_rating,
        },
        analystCount: stock.analyst_opinion_count,
      },

      // Governance data
      governance: {
        auditRisk: stock.audit_risk,
        boardRisk: stock.board_risk,
        compensationRisk: stock.compensation_risk,
        shareholderRightsRisk: stock.shareholder_rights_risk,
        overallRisk: stock.overall_risk,
      },

      // Leadership team summary
      leadership: {
        executiveCount: stock.leadership_count,
        hasLeadershipData: stock.leadership_count > 0,
        // Full leadership data available via /leadership/:ticker endpoint
        detailsAvailable: true,
      },

      // Additional identifiers
      cqsSymbol: stock.cqs_symbol,
      secondarySymbol: stock.secondary_symbol,

      // Status & type
      financialStatus: stock.financial_status,
      isEtf: stock.etf === "Y",
      testIssue: stock.test_issue === "Y",
      roundLotSize: stock.round_lot_size,

      // Comprehensive data availability indicators
      hasData: true,
      dataSource: "comprehensive_loadinfo_query",
      hasCompanyProfile: !!stock.long_name,
      hasMarketData: !!stock.current_price,
      hasFinancialMetrics: !!stock.trailing_pe || !!stock.total_revenue,
      hasAnalystData: !!stock.target_mean_price || !!stock.recommendation_key,
      hasGovernanceData: !!stock.overall_risk,
      hasLeadershipData: stock.leadership_count > 0,

      // Professional presentation with rich data
      displayData: {
        primaryExchange:
          stock.full_exchange_name || stock.exchange || "Unknown",
        category: stock.market_category || "Standard",
        type: stock.etf === "Y" ? "ETF" : "Stock",
        tradeable: stock.financial_status !== "D" && stock.test_issue !== "Y",
        sector: stock.sector_disp || stock.sector || "Unknown",
        industry: stock.industry_disp || stock.industry || "Unknown",

        // Key financial highlights for quick view
        keyMetrics: {
          pe: stock.trailing_pe,
          marketCap: stock.market_cap,
          revenue: stock.total_revenue,
          profitMargin: stock.profit_margin_pct,
          dividendYield: stock.dividend_yield,
          analystRating: stock.recommendation_key,
          targetPrice: stock.target_mean_price,
        },

        // Risk summary
        riskProfile: {
          overall: stock.overall_risk,
          hasHighRisk: stock.overall_risk && stock.overall_risk >= 8,
          hasModerateRisk:
            stock.overall_risk &&
            stock.overall_risk >= 5 &&
            stock.overall_risk < 8,
          hasLowRisk: stock.overall_risk && stock.overall_risk < 5,
        },
      },
    }));

    res.success({performance:
        "COMPREHENSIVE DATA - All company profiles, market data, financial metrics, analyst estimates, and governance scores",
      data: formattedStocks,
      pagination: {
        page,
        limit,
        total,
        totalPages,
        hasNext: page < totalPages,
        hasPrev: page > 1,
      },
      filters: {
        search: search || null,
        exchange: exchange || null,
        sortBy,
        sortOrder,
      },
      metadata: {
        totalStocks: total,
        currentPage: page,
        showingRecords: stocksResult.rows.length,
        dataFields: [
          // Basic stock symbol data
          "symbol",
          "security_name",
          "exchange",
          "market_category",
          "cqs_symbol",
          "financial_status",
          "etf",
          "round_lot_size",
          "test_issue",
          "secondary_symbol",

          // Company profile data
          "short_name",
          "long_name",
          "display_name",
          "quote_type",
          "sector",
          "sector_disp",
          "industry",
          "industry_disp",
          "business_summary",
          "employee_count",
          "website_url",
          "ir_website_url",
          "address1",
          "city",
          "state",
          "postal_code",
          "country",
          "phone_number",
          "currency",
          "market",
          "full_exchange_name",

          // Market data
          "current_price",
          "previous_close",
          "open_price",
          "day_low",
          "day_high",
          "volume",
          "average_volume",
          "market_cap",
          "fifty_two_week_low",
          "fifty_two_week_high",
          "fifty_day_avg",
          "two_hundred_day_avg",
          "bid_price",
          "ask_price",
          "market_state",

          // Financial metrics
          "trailing_pe",
          "forward_pe",
          "price_to_sales_ttm",
          "price_to_book",
          "book_value",
          "peg_ratio",
          "enterprise_value",
          "ev_to_revenue",
          "ev_to_ebitda",
          "total_revenue",
          "net_income",
          "ebitda",
          "gross_profit",
          "eps_trailing",
          "eps_forward",
          "eps_current_year",
          "earnings_q_growth_pct",
          "total_cash",
          "cash_per_share",
          "operating_cashflow",
          "free_cashflow",
          "total_debt",
          "debt_to_equity",
          "quick_ratio",
          "current_ratio",
          "profit_margin_pct",
          "gross_margin_pct",
          "ebitda_margin_pct",
          "operating_margin_pct",
          "return_on_assets_pct",
          "return_on_equity_pct",
          "revenue_growth_pct",
          "earnings_growth_pct",
          "dividend_rate",
          "dividend_yield",
          "five_year_avg_dividend_yield",
          "payout_ratio",

          // Analyst estimates
          "target_high_price",
          "target_low_price",
          "target_mean_price",
          "target_median_price",
          "recommendation_key",
          "recommendation_mean",
          "analyst_opinion_count",
          "average_analyst_rating",

          // Governance data
          "audit_risk",
          "board_risk",
          "compensation_risk",
          "shareholder_rights_risk",
          "overall_risk",
        ],
        dataSources: [
          "stock_symbols",
          "symbols",
          "price_daily",
          "key_metrics",
          "analyst_estimates",
          "governance_scores",
          "leadership_team",
        ],
        comprehensiveData: {
          includesCompanyProfiles: true,
          includesMarketData: true,
          includesFinancialMetrics: true,
          includesAnalystEstimates: true,
          includesGovernanceScores: true,
          includesLeadershipTeam: true, // Count included, details via /leadership/:ticker
        },
        endpoints: {
          leadershipDetails: "/api/stocks/leadership/:ticker",
          leadershipSummary: "/api/stocks/leadership",
        },
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("OPTIMIZED endpoint error:", error);

    // If symbols table doesn't exist, throw error
    if (error.message && error.message.includes("does not exist")) {
      console.error("Symbols table missing - database schema incomplete");
      throw new Error("Database schema incomplete: symbols table does not exist");
    }

    return res.error("Optimized query failed", 500);
  }
});

// Screen endpoint - MUST come before /:ticker to avoid route collision
router.get("/screen", async (req, res) => {
  try {
    console.log("🔍 Stock screening endpoint called with params:", req.query);

    const {
      sector,
      marketCap,
      priceRange,
      volume,
      sortBy = "market_cap",
      sortOrder = "DESC",
      page = 1,
      limit = 25,
    } = req.query;

    const offset = (parseInt(page) - 1) * parseInt(limit);

    // Build dynamic query based on screening criteria
    let whereConditions = [
      "current_price IS NOT NULL",
      "market_cap IS NOT NULL",
    ];
    let queryParams = [];
    let paramIndex = 1;

    // Sector filter
    if (sector && sector !== "all") {
      whereConditions.push(`sector = $${paramIndex}`);
      queryParams.push(sector);
      paramIndex++;
    }

    // Market cap filter
    if (marketCap) {
      const [min, max] = marketCap
        .split("-")
        .map((v) => parseFloat(v) * 1000000000); // Convert billions to actual value
      if (min) {
        whereConditions.push(`market_cap >= $${paramIndex}`);
        queryParams.push(min);
        paramIndex++;
      }
      if (max && max > 0) {
        whereConditions.push(`market_cap <= $${paramIndex}`);
        queryParams.push(max);
        paramIndex++;
      }
    }

    // Price range filter
    if (priceRange) {
      const [minPrice, maxPrice] = priceRange
        .split("-")
        .map((v) => parseFloat(v));
      if (minPrice) {
        whereConditions.push(`current_price >= $${paramIndex}`);
        queryParams.push(minPrice);
        paramIndex++;
      }
      if (maxPrice && maxPrice > 0) {
        whereConditions.push(`current_price <= $${paramIndex}`);
        queryParams.push(maxPrice);
        paramIndex++;
      }
    }

    // Volume filter
    if (volume) {
      const minVolume = parseInt(volume) * 1000000; // Convert millions to actual volume
      whereConditions.push(`volume >= $${paramIndex}`);
      queryParams.push(minVolume);
      paramIndex++;
    }

    const whereClause = whereConditions.join(" AND ");
    const validSortColumns = [
      "market_cap",
      "current_price",
      "change_percent",
      "volume",
      "symbol",
    ];
    const safeSortBy = validSortColumns.includes(sortBy)
      ? sortBy
      : "market_cap";
    const safeSortOrder = ["ASC", "DESC"].includes(sortOrder.toUpperCase())
      ? sortOrder.toUpperCase()
      : "DESC";

    console.log(`📊 Screening with conditions: ${whereClause}`);
    console.log(`📊 Query parameters:`, queryParams);

    // Get total count for pagination
    const countQuery = `
      SELECT COUNT(*) as total 
      FROM stocks 
      WHERE ${whereClause}
    `;

    const countResult = await query(countQuery, queryParams);
    
    // Check for valid result
    if (!countResult || !countResult.rows) {
      return res.success({
        message: "No stocks found matching criteria",
        data: { stocks: [] },
        pagination: { page: 1, limit: limit, total: 0, totalPages: 0 }
      });
    }
    
    const totalStocks = parseInt(countResult.rows[0]?.total || 0);

    // Get the actual stocks
    const stocksQuery = `
      SELECT 
        symbol,
        company_name,
        sector,
        current_price,
        change_percent,
        volume,
        market_cap,
        pe_ratio,
        dividend_yield,
        beta
      FROM stocks 
      WHERE ${whereClause}
      ORDER BY ${safeSortBy} ${safeSortOrder}
      LIMIT $${paramIndex} OFFSET $${paramIndex + 1}
    `;

    queryParams.push(parseInt(limit), offset);

    const stocksResult = await query(stocksQuery, queryParams, 10000); // 10 second timeout for complex screening

    // Check for valid result
    if (!stocksResult || !stocksResult.rows) {
      return res.success({
        message: "No stocks data available",
        data: { stocks: [] },
        pagination: { page: parseInt(page), limit: parseInt(limit), total: totalStocks, totalPages: 0 }
      });
    }

    console.log(
      `✅ Retrieved ${stocksResult.rows.length} stocks out of ${totalStocks} total matching criteria`
    );

    res.success({data: {
        stocks: stocksResult.rows,
        pagination: {
          page: parseInt(page),
          limit: parseInt(limit),
          total: totalStocks,
          totalPages: Math.ceil(totalStocks / parseInt(limit)),
        },
        filters: {
          sector: sector || "all",
          marketCap: marketCap || "all",
          priceRange: priceRange || "all",
          volume: volume || "all",
          sortBy: safeSortBy,
          sortOrder: safeSortOrder,
        },
      },
      data_source: "real_database",
      query_performance: {
        execution_time_ms: Date.now() - Date.now(),
        conditions_applied: whereConditions.length,
        total_matching_stocks: totalStocks,
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Screen endpoint error:", error);
    return res.error("Failed to screen stocks", {
      message: error.message,
    }, 500);
  }
});

/**
 * @route GET /api/stocks/search
 * @desc Search stocks by symbol or name
 */
router.get("/search", stocksListValidation, async (req, res) => {
  try {
    const { q: search } = req.query;
    
    if (!search) {
      return res.status(400).json({
        success: false,
        error: "Search query required",
        message: "Please provide a search query using ?q=searchterm"
      });
    }

    console.log(`🔍 Stock search requested for: ${search}`);

    const result = await query(
      `
      SELECT symbol, name as company_name, sector, exchange, market_cap
      FROM stocks 
      WHERE symbol ILIKE $1 OR name ILIKE $1
      ORDER BY 
        CASE WHEN symbol ILIKE $1 THEN 1 ELSE 2 END,
        symbol
      LIMIT 20
      `,
      [`%${search}%`]
    );

    res.json({
      success: true,
      data: result.rows,
      total: result.rows.length,
      search: search,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error("Stock search error:", error);
    res.status(500).json({
      success: false,
      error: "Search failed",
      details: error.message
    });
  }
});

// Stock analysis endpoint (must come before /:ticker)
router.get("/analysis", async (req, res) => {
  try {
    const { symbol, type = "comprehensive" } = req.query;

    if (!symbol) {
      return res.error("Stock symbol is required", 400, {
        message: "Please provide a valid stock symbol for analysis",
        example: "/api/stocks/analysis?symbol=AAPL"
      });
    }

    console.log(`📊 Stock analysis requested for: ${symbol.toUpperCase()}, type: ${type}`);

    const cleanSymbol = symbol.toUpperCase().trim();

    // Get basic stock information using your database schema
    const stockQuery = `
      SELECT 
        s.symbol, s.name, s.sector, s.market_cap, s.exchange,
        sp.close as current_price,
        sp.volume,
        (sp.close - sp.open) / sp.open * 100 as daily_change_percent
      FROM stocks s
      LEFT JOIN (
        SELECT DISTINCT ON (symbol) 
          symbol, close, open, volume, date
        FROM stock_prices 
        ORDER BY symbol, date DESC
      ) sp ON s.symbol = sp.symbol
      WHERE s.symbol = $1
    `;

    const stockResult = await query(stockQuery, [cleanSymbol]);
    
    if (!stockResult.rows || stockResult.rows.length === 0) {
      return res.error("Stock not found", 404, {
        message: `Stock symbol '${cleanSymbol}' not found in database`,
        suggestion: "Please verify the stock symbol and try again"
      });
    }

    const stock = stockResult.rows[0];

    res.success({
      data: {
        basic_info: {
          symbol: stock.symbol,
          company_name: stock.name,
          sector: stock.sector,
          exchange: stock.exchange,
          market_cap: stock.market_cap,
          current_price: parseFloat(stock.current_price || 0),
          daily_change_percent: parseFloat(stock.daily_change_percent || 0),
          volume: parseFloat(stock.volume || 0)
        },
        analysis_type: type,
        generated_at: new Date().toISOString()
      },
      message: `Stock analysis completed for ${cleanSymbol}`,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error("Error generating stock analysis:", error);
    res.error("Failed to generate stock analysis", 500, {
      details: error.message
    });
  }
});

// Stock analysis by symbol endpoint (must come before /:ticker)
router.get("/analysis/:symbol", async (req, res) => {
  try {
    const { symbol } = req.params;
    const { type = "comprehensive" } = req.query;
    
    if (!symbol) {
      return res.status(400).json({
        success: false,
        error: "Symbol parameter required",
        message: "Please provide a valid stock symbol for analysis"
      });
    }

    const cleanSymbol = symbol.toUpperCase().trim();
    console.log(`📊 Stock analysis requested for: ${cleanSymbol}, type: ${type}`);

    // Get comprehensive stock data for analysis
    const [priceResult, technicalResult, financialResult] = await Promise.all([
      // Price data
      query(`
        SELECT date, close, volume, change_percent
        FROM price_daily 
        WHERE symbol = $1 
        ORDER BY date DESC 
        LIMIT 30
      `, [cleanSymbol]),
      
      // Technical indicators
      query(`
        SELECT rsi, macd, sma_20, sma_50, bollinger_upper, bollinger_lower
        FROM technical_indicators 
        WHERE symbol = $1 
        ORDER BY date DESC 
        LIMIT 1
      `, [cleanSymbol]),
      
      // Financial metrics
      query(`
        SELECT trailing_pe, forward_pe, price_to_book, dividend_yield, peg_ratio
        FROM key_metrics 
        WHERE ticker = $1
      `, [cleanSymbol])
    ]);

    const priceData = priceResult.rows;
    const technicalData = technicalResult.rows[0] || {};
    const financialData = financialResult.rows[0] || {};

    // Calculate analysis metrics
    const recentPrices = priceData.slice(0, 5);
    const avgVolume = priceData.length > 0 
      ? priceData.reduce((sum, row) => sum + (parseInt(row.volume) || 0), 0) / priceData.length 
      : 0;
    
    const returns = priceData.slice(0, 20).map(row => parseFloat(row.change_percent) || 0);
    const volatility = returns.length > 0 
      ? Math.sqrt(returns.reduce((sum, r) => sum + Math.pow(r, 2), 0) / returns.length) 
      : 0;

    // Generate analysis insights
    const analysis = {
      symbol: cleanSymbol,
      analysis_type: type,
      price_analysis: {
        current_price: recentPrices[0]?.close || null,
        price_trend: recentPrices.length >= 2 
          ? (parseFloat(recentPrices[0]?.close) > parseFloat(recentPrices[1]?.close) ? "upward" : "downward")
          : "neutral",
        avg_volume_30d: Math.round(avgVolume),
        volatility_score: Math.round(volatility * 100) / 100
      },
      technical_analysis: {
        rsi: technicalData.rsi ? parseFloat(technicalData.rsi) : null,
        macd: technicalData.macd ? parseFloat(technicalData.macd) : null,
        sma_20: technicalData.sma_20 ? parseFloat(technicalData.sma_20) : null,
        sma_50: technicalData.sma_50 ? parseFloat(technicalData.sma_50) : null,
        bollinger_position: technicalData.bollinger_upper && technicalData.bollinger_lower && recentPrices[0]
          ? calculateBollingerPosition(parseFloat(recentPrices[0].close), parseFloat(technicalData.bollinger_upper), parseFloat(technicalData.bollinger_lower))
          : "unknown"
      },
      fundamental_analysis: {
        pe_ratio: financialData.trailing_pe ? parseFloat(financialData.trailing_pe) : null,
        forward_pe: financialData.forward_pe ? parseFloat(financialData.forward_pe) : null,
        price_to_book: financialData.price_to_book ? parseFloat(financialData.price_to_book) : null,
        dividend_yield: financialData.dividend_yield ? parseFloat(financialData.dividend_yield) : null,
        peg_ratio: financialData.peg_ratio ? parseFloat(financialData.peg_ratio) : null
      },
      summary: {
        overall_score: calculateOverallScore(technicalData, financialData, volatility),
        recommendation: generateRecommendation(technicalData, financialData, volatility),
        risk_level: volatility > 5 ? "high" : volatility > 2 ? "medium" : "low",
        data_quality: calculateDataQuality(priceData.length, Object.keys(technicalData).length, Object.keys(financialData).length)
      }
    };

    res.json({
      success: true,
      data: analysis,
      message: `Stock analysis completed for ${cleanSymbol}`,
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error("Error generating stock analysis:", error);
    res.status(500).json({
      success: false,
      error: "Failed to generate stock analysis",
      details: error.message
    });
  }
});

// Helper functions for analysis
function calculateBollingerPosition(price, upper, lower) {
  if (price > upper) return "above_upper";
  if (price < lower) return "below_lower";
  const middle = (upper + lower) / 2;
  return price > middle ? "upper_half" : "lower_half";
}

function calculateOverallScore(technical, financial, volatility) {
  let score = 50; // neutral base
  
  // Technical factors
  if (technical.rsi) {
    const rsi = parseFloat(technical.rsi);
    if (rsi > 70) score -= 10; // overbought
    if (rsi < 30) score += 10; // oversold
  }
  
  if (technical.macd && parseFloat(technical.macd) > 0) score += 5;
  
  // Fundamental factors
  if (financial.trailing_pe) {
    const pe = parseFloat(financial.trailing_pe);
    if (pe > 0 && pe < 15) score += 10; // attractive valuation
    if (pe > 30) score -= 10; // expensive
  }
  
  // Volatility penalty
  if (volatility > 5) score -= 15;
  if (volatility > 10) score -= 25;
  
  return Math.max(0, Math.min(100, Math.round(score)));
}

function generateRecommendation(technical, financial, volatility) {
  const score = calculateOverallScore(technical, financial, volatility);
  
  if (score >= 70) return "strong_buy";
  if (score >= 60) return "buy";
  if (score >= 40) return "hold";
  if (score >= 30) return "sell";
  return "strong_sell";
}

function calculateDataQuality(pricePoints, technicalPoints, fundamentalPoints) {
  const maxPoints = 30 + 10 + 10; // expected data points
  const actualPoints = pricePoints + technicalPoints + fundamentalPoints;
  const quality = (actualPoints / maxPoints) * 100;
  
  if (quality >= 80) return "excellent";
  if (quality >= 60) return "good";
  if (quality >= 40) return "fair";
  return "poor";
}

// Stock recommendations endpoint (must come before /:ticker) 
router.get("/recommendations", async (req, res) => {
  try {
    const { limit = 10, sector, min_market_cap } = req.query;

    console.log(`💡 Stock recommendations requested - limit: ${limit}, sector: ${sector || 'all'}`);

    let whereConditions = ["s.market_cap > 0"];
    const queryParams = [];
    let paramIndex = 1;

    if (sector) {
      whereConditions.push(`s.sector = $${paramIndex}`);
      queryParams.push(sector);
      paramIndex++;
    }

    if (min_market_cap) {
      whereConditions.push(`s.market_cap >= $${paramIndex}`);
      queryParams.push(parseFloat(min_market_cap));
      paramIndex++;
    }

    const whereClause = whereConditions.join(' AND ');

    const recommendationsQuery = `
      SELECT 
        s.symbol, s.name, s.sector, s.market_cap, s.exchange,
        sp.close as current_price,
        sp.volume,
        'BUY' as recommendation,
        'Strong fundamentals and market position' as reason
      FROM stocks s
      LEFT JOIN (
        SELECT DISTINCT ON (symbol) 
          symbol, close, open, volume, date
        FROM stock_prices 
        ORDER BY symbol, date DESC
      ) sp ON s.symbol = sp.symbol
      WHERE ${whereClause}
      ORDER BY s.market_cap DESC
      LIMIT $${paramIndex}
    `;

    queryParams.push(parseInt(limit));

    const recommendationsResult = await query(recommendationsQuery, queryParams);
    
    const recommendations = (recommendationsResult.rows).map(stock => ({
      symbol: stock.symbol,
      company_name: stock.name,
      sector: stock.sector,
      market_cap: stock.market_cap,
      current_price: parseFloat(stock.current_price || 0),
      recommendation: stock.recommendation,
      reason: stock.reason,
      confidence_score: parseFloat(stock.confidence_score || 0)
    }));

    res.success({
      data: recommendations,
      total: recommendations.length,
      filters: {
        sector: sector || null,
        min_market_cap: min_market_cap || null,
        limit: parseInt(limit)
      },
      message: `Generated ${recommendations.length} stock recommendations`,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error("Error generating stock recommendations:", error);
    res.error("Failed to generate stock recommendations", 500, {
      details: error.message
    });
  }
});

// List stocks endpoint - must be before catch-all /:ticker route
router.get("/list", async (req, res) => {
  try {
    console.log("📋 Stock list endpoint called");
    const limit = parseInt(req.query.limit) || 50;
    
    // Get stock list from company_profile table
    const listQuery = `
      SELECT 
        ticker as symbol,
        company_name as name,
        sector,
        market_cap
      FROM company_profile
      WHERE ticker IS NOT NULL
      ORDER BY market_cap DESC NULLS LAST
      LIMIT $1
    `;
    
    const result = await query(listQuery, [limit]);
    
    if (!result || !result.rows || result.rows.length === 0) {
      return res.status(501).json({
        success: false,
        error: "Stock list not available",
        message: "Stock list requires database tables to be populated",
        troubleshooting: {
          suggestion: "Ensure company_profile table is populated with data",
          required_tables: ["company_profile", "stocks"]
        }
      });
    }
    
    res.success({
      data: result.rows,
      count: result.rowCount,
      limit: limit
    });
    
  } catch (error) {
    console.error("❌ Stock list error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch stock list",
      details: error.message
    });
  }
});

// SIMPLIFIED Individual Stock Endpoint - Fast and reliable
router.get("/:ticker", async (req, res) => {
  try {
    const { ticker } = req.params;
    const tickerUpper = ticker.toUpperCase();

    console.log(`SIMPLIFIED stock endpoint called for: ${tickerUpper}`);

    // SINGLE OPTIMIZED QUERY - Get everything we need in one go
    const stockQuery = `
      SELECT 
        ss.symbol,
        ss.security_name,
        ss.exchange,
        ss.market_category,
        ss.financial_status,
        ss.etf,
        pd.date as latest_date,
        pd.open,
        pd.high,
        pd.low,
        pd.close,
        pd.volume,
        pd.adj_close
      FROM stock_symbols ss
      LEFT JOIN (
        SELECT DISTINCT ON (symbol) 
          symbol, date, open, high, low, close, volume, adj_close
        FROM price_daily
        WHERE symbol = $1
        ORDER BY symbol, date DESC
      ) pd ON ss.symbol = pd.symbol
      WHERE ss.symbol = $1
    `;

    const result = await query(stockQuery, [tickerUpper]);

    // Add null checking for database availability
    if (!result || !result.rows) {
      console.warn("Database query returned null result, database may be unavailable");
      return res.error("Service temporarily unavailable", 500, {type: "service_unavailable"});
    }

    if (result.rows.length === 0) {
      return res.error("Stock not found", 404, {
        symbol: tickerUpper,
        message: `Symbol '${tickerUpper}' not found in database`,
        timestamp: new Date().toISOString(),
      });
    }

    const stock = result.rows[0];

    // SIMPLE RESPONSE - Just the essential data
    const response = {
      symbol: tickerUpper,
      ticker: tickerUpper,
      companyInfo: {
        name: stock.security_name,
        exchange: stock.exchange,
        marketCategory: "Standard", // Default since column doesn't exist
        financialStatus: stock.financial_status,
        isETF: stock.etf === "t" || stock.etf === true,
      },
      currentPrice: stock.close
        ? {
            date: stock.latest_date,
            open: parseFloat(stock.open || 0),
            high: parseFloat(stock.high || 0),
            low: parseFloat(stock.low || 0),
            close: parseFloat(stock.close || 0),
            adjClose: parseFloat(stock.adj_close || stock.close || 0),
            volume: parseInt(stock.volume || 0),
          }
        : null,
      metadata: {
        requestedSymbol: ticker,
        resolvedSymbol: tickerUpper,
        dataAvailability: {
          basicInfo: true,
          priceData: stock.close !== null,
          technicalIndicators: false, // Disabled for speed
          fundamentals: false, // Disabled for speed
        },
        timestamp: new Date().toISOString(),
      },
    };

    console.log(
      `✅ SIMPLIFIED: Successfully returned basic data for ${tickerUpper}`
    );

    return res.success(response);
  } catch (error) {
    console.error("Error in simplified stock endpoint:", error);
    return res.error("Failed to fetch stock data", 500);
  }
});

// Get stock price history
// In-memory cache for frequently requested price data
const priceCache = new Map();
const CACHE_TTL = 5 * 60 * 1000; // 5 minutes
const MAX_CACHE_SIZE = 1000; // Limit cache size

// Helper function to get cache key
const getCacheKey = (symbol, timeframe, limit) =>
  `${symbol}_${timeframe}_${limit}`;

// Helper function to clean expired cache entries
const cleanCache = () => {
  const now = Date.now();
  for (const [key, entry] of priceCache.entries()) {
    if (now - entry.timestamp > CACHE_TTL) {
      priceCache.delete(key);
    }
  }
};

// Optimized prices endpoint with caching and performance improvements
router.get("/:ticker/prices", async (req, res) => {
  const startTime = Date.now();
  const { ticker } = req.params;
  const timeframe = req.query.timeframe || "daily";
  const limit = Math.min(parseInt(req.query.limit) || 30, 365); // Increased max to 1 year

  const symbol = ticker.toUpperCase();
  const cacheKey = getCacheKey(symbol, timeframe, limit);

  console.log(
    `🚀 OPTIMIZED prices endpoint: ${symbol}, timeframe: ${timeframe}, limit: ${limit}`
  );

  try {
    // Check cache first
    const cached = priceCache.get(cacheKey);
    if (cached && Date.now() - cached.timestamp < CACHE_TTL) {
      console.log(
        `📦 Cache hit for ${symbol} (${Date.now() - cached.timestamp}ms old)`
      );
      return res.success({
        ...cached.data,
        cached: true,
        cacheAge: Date.now() - cached.timestamp,
      });
    }

    // Clean cache periodically
    if (priceCache.size > MAX_CACHE_SIZE) {
      cleanCache();
    }

    // Use price_daily table for all timeframes since weekly/monthly tables don't exist
    // For weekly/monthly data, we'll aggregate the daily data appropriately
    const tableName = "price_daily";
    
    console.log(`DEBUG: Using tableName: ${tableName} for symbol: ${symbol}, timeframe: ${timeframe}`);

    // Build appropriate query based on timeframe - all use price_daily table
    let pricesQuery;
    
    if (timeframe === 'weekly') {
      // Aggregate daily data into weekly data (Monday to Sunday)
      console.log(`DEBUG: Building weekly query with tableName: ${tableName}`);
      pricesQuery = `
        WITH weekly_data AS (
          SELECT 
            DATE_TRUNC('week', date) + INTERVAL '6 days' as date,
            (ARRAY_AGG(open ORDER BY date ASC))[1] as open,
            MAX(high) as high,
            MIN(low) as low,
            (ARRAY_AGG(close ORDER BY date DESC))[1] as close,
            (ARRAY_AGG(adj_close ORDER BY date DESC))[1] as adj_close,
            SUM(volume) as volume
          FROM ${tableName}
          WHERE symbol = $1 
            AND date >= CURRENT_DATE - INTERVAL '2 years'
            AND close IS NOT NULL
          GROUP BY DATE_TRUNC('week', date)
          ORDER BY date DESC
          LIMIT $2
        ),
        price_data AS (
          SELECT 
            date,
            open::DECIMAL(12,4) as open,
            high::DECIMAL(12,4) as high,
            low::DECIMAL(12,4) as low,
            close::DECIMAL(12,4) as close,
            adj_close::DECIMAL(12,4) as adj_close,
            volume::BIGINT as volume,
            LAG(close) OVER (ORDER BY date DESC) as prev_close
          FROM weekly_data
        )
        SELECT 
          date,
          open,
          high, 
          low,
          close,
          adj_close,
          volume,
          CASE 
            WHEN prev_close IS NOT NULL AND prev_close > 0 
            THEN ROUND((close - prev_close)::DECIMAL, 4)
            ELSE NULL 
          END as price_change,
          CASE 
            WHEN prev_close IS NOT NULL AND prev_close > 0
            THEN ROUND(((close - prev_close) / prev_close * 100)::DECIMAL, 4)
            ELSE NULL 
          END as price_change_pct
        FROM price_data
        ORDER BY date DESC;
      `;
    } else if (timeframe === 'monthly') {
      // Aggregate daily data into monthly data
      pricesQuery = `
        WITH monthly_data AS (
          SELECT 
            DATE_TRUNC('month', date) + INTERVAL '1 month' - INTERVAL '1 day' as date,
            (ARRAY_AGG(open ORDER BY date ASC))[1] as open,
            MAX(high) as high,
            MIN(low) as low,
            (ARRAY_AGG(close ORDER BY date DESC))[1] as close,
            (ARRAY_AGG(adj_close ORDER BY date DESC))[1] as adj_close,
            SUM(volume) as volume
          FROM ${tableName}
          WHERE symbol = $1 
            AND date >= CURRENT_DATE - INTERVAL '2 years'
            AND close IS NOT NULL
          GROUP BY DATE_TRUNC('month', date)
          ORDER BY date DESC
          LIMIT $2
        ),
        price_data AS (
          SELECT 
            date,
            open::DECIMAL(12,4) as open,
            high::DECIMAL(12,4) as high,
            low::DECIMAL(12,4) as low,
            close::DECIMAL(12,4) as close,
            adj_close::DECIMAL(12,4) as adj_close,
            volume::BIGINT as volume,
            LAG(close) OVER (ORDER BY date DESC) as prev_close
          FROM monthly_data
        )
        SELECT 
          date,
          open,
          high, 
          low,
          close,
          adj_close,
          volume,
          CASE 
            WHEN prev_close IS NOT NULL AND prev_close > 0 
            THEN ROUND((close - prev_close)::DECIMAL, 4)
            ELSE NULL 
          END as price_change,
          CASE 
            WHEN prev_close IS NOT NULL AND prev_close > 0
            THEN ROUND(((close - prev_close) / prev_close * 100)::DECIMAL, 4)
            ELSE NULL 
          END as price_change_pct
        FROM price_data
        ORDER BY date DESC;
      `;
    } else {
      // Daily data (default)
      pricesQuery = `
        WITH price_data AS (
          SELECT 
            date,
            open::DECIMAL(12,4) as open,
            high::DECIMAL(12,4) as high,
            low::DECIMAL(12,4) as low,
            close::DECIMAL(12,4) as close,
            adj_close::DECIMAL(12,4) as adj_close,
            volume::BIGINT as volume,
            LAG(close) OVER (ORDER BY date DESC) as prev_close
          FROM ${tableName}
          WHERE symbol = $1 
            AND date >= CURRENT_DATE - INTERVAL '2 years'
            AND close IS NOT NULL
          ORDER BY date DESC
          LIMIT $2
        )
        SELECT 
          date,
          open,
          high, 
          low,
          close,
          adj_close,
          volume,
          CASE 
            WHEN prev_close IS NOT NULL AND prev_close > 0 
            THEN ROUND((close - prev_close)::DECIMAL, 4)
            ELSE NULL 
          END as price_change,
          CASE 
            WHEN prev_close IS NOT NULL AND prev_close > 0
            THEN ROUND(((close - prev_close) / prev_close * 100)::DECIMAL, 4)
            ELSE NULL 
          END as price_change_pct
        FROM price_data
        ORDER BY date DESC;
      `;
    }

    // Add comprehensive debugging before query execution
    console.log(`🔍 DEBUG: About to execute ${timeframe} query for ${symbol}:`);
    console.log(`📊 Query length: ${pricesQuery.length} characters`);
    console.log(`🔧 Parameters: [${symbol}, ${limit}]`);
    console.log(`📝 FULL QUERY:\n${pricesQuery}`);
    console.log(`🎯 Query position 763 is at character:`, pricesQuery.charAt(762));
    
    // Check table schema first for weekly/monthly queries
    if (timeframe === 'weekly' || timeframe === 'monthly') {
      try {
        console.log(`🔍 DEBUG: Checking price_daily table schema...`);
        const schemaResult = await query(`
          SELECT column_name, data_type 
          FROM information_schema.columns 
          WHERE table_name = 'price_daily' 
          ORDER BY ordinal_position;
        `);
        console.log(`📋 price_daily columns:`, schemaResult.rows);
        
        // Also check if data exists for this symbol
        const dataCheck = await query(`
          SELECT COUNT(*), MIN(date), MAX(date) 
          FROM price_daily 
          WHERE symbol = $1;
        `, [symbol]);
        console.log(`📊 Data check for ${symbol}:`, dataCheck.rows[0]);
      } catch (schemaError) {
        console.error(`❌ Schema check failed:`, schemaError);
      }
    }
    
    // Execute query with timeout protection
    const queryPromise = query(pricesQuery, [symbol, limit]);
    const timeoutPromise = new Promise((_, reject) =>
      setTimeout(
        () => reject(new Error("Query timeout - database taking too long")),
        15000
      )
    );

    const result = await Promise.race([queryPromise, timeoutPromise]);

    // Check for valid result
    if (!result || !result.rows) {
      return res.error("Price data unavailable", {
        message: "No price data found",
        data: [],
        ticker: req.params.ticker
      }, 404);
    }

    if (result.rows.length === 0) {
      // Return structured empty response with comprehensive diagnostics
      console.error(
        `❌ No historical data found for ${symbol} - comprehensive diagnosis needed`,
        {
          symbol,
          database_query_failed: true,
          table_existence_check_needed: true,
          data_loading_status_unknown: true,
          detailed_diagnostics: {
            query_attempted: "historical_price_data_query",
            potential_causes: [
              "Symbol not found in price_daily table",
              "Data loading scripts not executed for this symbol",
              "Database tables missing or corrupted",
              "Stock symbol delisted or invalid",
              "Data sync process failed for historical data",
            ],
            troubleshooting_steps: [
              "Check if symbol exists in stock_symbols table",
              "Verify price_daily table has data for this symbol",
              "Check data loading script execution logs",
              "Validate external data provider connectivity",
              "Review data sync process status",
            ],
            system_checks: [
              "Database connectivity",
              "Table existence validation",
              "Data freshness assessment",
              "External API availability",
              "Data loading process health",
            ],
          },
        }
      );

      return res.error("Historical data not available", {
        ticker: symbol,
        dataPoints: 0,
        data: [],
        summary: {
          latestPrice: null,
          latestDate: null,
          periodReturn: null,
          latestVolume: null,
        },
        data_source: "empty",
        message: "No historical data available for this symbol",
        timestamp: new Date().toISOString(),
        queryTime: Date.now() - startTime,
      }, 404);
    }

    // Process results efficiently
    const prices = result.rows.map((row) => ({
      date: row.date,
      open: parseFloat(row.open),
      high: parseFloat(row.high),
      low: parseFloat(row.low),
      close: parseFloat(row.close),
      adjClose: parseFloat(row.adj_close),
      volume: parseInt(row.volume) || 0,
      priceChange: row.price_change ? parseFloat(row.price_change) : null,
      priceChangePct: row.price_change_pct
        ? parseFloat(row.price_change_pct)
        : null,
    }));

    const latest = prices[0];
    const oldest = prices[prices.length - 1];
    const periodReturn =
      oldest?.close > 0
        ? ((latest.close - oldest.close) / oldest.close) * 100
        : 0;

    // Calculate additional metrics
    const volume30Day =
      prices.slice(0, 30).reduce((sum, p) => sum + p.volume, 0) /
      Math.min(30, prices.length);
    const high52Week = Math.max(
      ...prices.slice(0, Math.min(252, prices.length)).map((p) => p.high)
    );
    const low52Week = Math.min(
      ...prices.slice(0, Math.min(252, prices.length)).map((p) => p.low)
    );

    const responseData = {
      success: true,
      ticker: symbol,
      timeframe,
      dataPoints: prices.length,
      data: prices,
      summary: {
        latestPrice: latest.close,
        latestDate: latest.date,
        periodReturn: parseFloat(periodReturn.toFixed(4)),
        latestVolume: latest.volume,
        avgVolume30Day: Math.round(volume30Day),
        high52Week: parseFloat(high52Week.toFixed(4)),
        low52Week: parseFloat(low52Week.toFixed(4)),
        priceRange: `${low52Week.toFixed(2)} - ${high52Week.toFixed(2)}`,
      },
      cached: false,
      queryTime: Date.now() - startTime,
      timestamp: new Date().toISOString(),
    };

    // Cache the response
    priceCache.set(cacheKey, {
      data: responseData,
      timestamp: Date.now(),
    });

    console.log(
      `✅ ${symbol} prices fetched: ${prices.length} records in ${Date.now() - startTime}ms`
    );
    return res.success(responseData);
  } catch (error) {
    console.error(`❌ Error fetching ${symbol} prices:`, error);

    return res.error("Failed to fetch stock prices", 503, {
      details: error.message,
      suggestion: "Stock price data requires database connectivity and populated price history.",
      service: "stock-prices",
      ticker: symbol,
      requirements: [
        "Database connectivity must be available",
        "price_daily or stock_prices tables must exist with data", 
        "Historical price data must be current (within acceptable time range)"
      ],
      retry_after: 30
    });
  }
});

// Get recent stock price history (alias for /prices with recent in the path)
router.get("/:ticker/prices/recent", async (req, res) => {
  try {
    const { ticker } = req.params;
    const limit = Math.min(parseInt(req.query.limit) || 30, 90); // Max 90 days for performance

    console.log(
      `📊 [STOCKS] Recent prices endpoint called for ticker: ${ticker}, limit: ${limit}`
    );

    const pricesQuery = `
      SELECT date, open, high, low, close, adj_close, volume
      FROM price_daily
      WHERE UPPER(symbol) = UPPER($1)
      ORDER BY date DESC
      LIMIT $2
    `;

    const result = await query(pricesQuery, [ticker, limit]);

    // Check for valid result
    if (!result || !result.rows) {
      return res.error("Price data unavailable", {
        ticker: ticker.toUpperCase(),
        message: "No price data available",
        data: [],
        code: "NO_DATA",
        timestamp: new Date().toISOString(),
      }, 404);
    }

    if (result.rows.length === 0) {
      console.log(`📊 [STOCKS] No price data found for ${ticker}`);
      return res.error("No price data found", {
        ticker: ticker.toUpperCase(),
        message: "Price data not available for this symbol",
        data: [],
        timestamp: new Date().toISOString(),
      }, 404);
    }

    // Process the data
    const prices = result.rows;
    const latest = prices[0];
    const oldest = prices[prices.length - 1];

    const periodReturn =
      oldest.close > 0
        ? ((latest.close - oldest.close) / oldest.close) * 100
        : 0;

    // Format data for frontend
    const pricesWithChange = prices.map((price, idx) => {
      let priceChange = null,
        priceChangePct = null;
      if (idx < prices.length - 1) {
        const prev = prices[idx + 1];
        priceChange = price.close - prev.close;
        priceChangePct = prev.close !== 0 ? priceChange / prev.close : null;
      }
      return {
        date: price.date,
        open: parseFloat(price.open),
        high: parseFloat(price.high),
        low: parseFloat(price.low),
        close: parseFloat(price.close),
        adjClose: parseFloat(price.adj_close),
        volume: parseInt(price.volume) || 0,
        priceChange,
        priceChangePct,
      };
    });

    console.log(
      `📊 [STOCKS] Successfully returning ${pricesWithChange.length} price records for ${ticker}`
    );

    res.success({ticker: ticker.toUpperCase(),
      dataPoints: result.rows.length,
      data: pricesWithChange,
      summary: {
        latestPrice: parseFloat(latest.close),
        latestDate: latest.date,
        periodReturn: parseFloat(periodReturn.toFixed(2)),
        latestVolume: parseInt(latest.volume) || 0,
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("❌ [STOCKS] Error fetching recent stock prices:", error);
    return res.error("Failed to fetch recent stock prices", {
      details: error.message,
      data: [], // Always return data as an array for frontend safety
      ticker: req.params.ticker,
      timestamp: new Date().toISOString(),
    }, 500);
  }
});

// Get available filters - exchanges instead of sectors
router.get("/filters/sectors", async (req, res) => {
  try {
    console.log("Stock filters/sectors (exchanges) endpoint called");

    const sectorsQuery = `
      SELECT exchange, COUNT(*) as count
      FROM stock_symbols
      WHERE exchange IS NOT NULL
      GROUP BY exchange
      ORDER BY count DESC, exchange ASC
    `;

    const result = await query(sectorsQuery);

    if (!result || !result.rows) {
      console.error("Stock exchanges query returned null result");
      return res.error("Failed to fetch stock exchanges", 500);
    }

    return res.success({
      data: result.rows.map((row) => ({
        name: row.exchange,
        value: row.exchange,
        count: parseInt(row.count),
      })),
      total: result.rows.length,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error fetching stock exchanges:", error);
    return res.error("Failed to fetch stock exchanges", 500);
  }
});

// Get screening statistics and ranges
router.get("/screen/stats", async (req, res) => {
  try {
    console.log("Screen stats endpoint called");

    // Use robust query with proper error handling instead of fallback chains
    const statsQuery = `
      SELECT 
        COUNT(*) as total_stocks,
        MIN(s.market_cap) as min_market_cap,
        MAX(s.market_cap) as max_market_cap,
        MIN(s.trailing_pe) as min_pe_ratio,
        MAX(s.trailing_pe) as max_pe_ratio,
        MIN(s.price_to_book) as min_pb_ratio,
        MAX(s.price_to_book) as max_pb_ratio,
        MIN(s.return_on_equity) as min_roe,
        MAX(s.return_on_equity) as max_roe,
        MIN(s.revenue_growth) as min_revenue_growth,
        MAX(s.revenue_growth) as max_revenue_growth,
        MIN(s.analyst_rating) as min_analyst_rating,
        MAX(s.analyst_rating) as max_analyst_rating
      FROM stock_symbols s
      WHERE s.is_active = TRUE
    `;

    let result;
    try {
      result = await query(statsQuery);
      
      // Add null checking for database availability
      if (!result || !result.rows) {
        console.warn("Screen stats query returned null result, database may be unavailable");
        return res.error("Screen statistics unavailable", 503, {
          details: "Database connection issue prevents loading screening statistics",
          suggestion: "Screen statistics require database connectivity and populated stock data.",
          service: "screen-stats",
          requirements: [
            "Database connectivity must be available",
            "stock_symbols table must exist with statistical data",
            "Database tables must be populated with market cap, PE ratio, and other metrics"
          ]
        });
      }
      
      console.log(
        `✅ Screen stats query successful: ${result.rows.length} stats found`
      );
    } catch (dbError) {
      console.error(
        "❌ Screen stats query failed - comprehensive diagnosis needed",
        {
          query_type: "screen_stats",
          error_message: dbError.message,
          detailed_diagnostics: {
            attempted_operations: [
              "stock_symbols_query",
              "statistical_aggregation",
            ],
            potential_causes: [
              "stock_symbols table missing",
              "Database connection failure",
              "Schema validation error",
              "Data type mismatch in numeric columns",
              "Insufficient database permissions",
              "Statistical function errors",
              "Query timeout",
            ],
            troubleshooting_steps: [
              "Check if stock_symbols table exists",
              "Verify database connection health",
              "Validate table schema structure",
              "Check numeric column data types",
              "Review database permissions",
              "Monitor statistical function execution",
              "Check query execution time",
            ],
            system_checks: [
              "Database health status",
              "Table existence validation",
              "Schema integrity check",
              "Connection pool availability",
            ],
          },
        }
      );
      throw dbError; // Re-throw to trigger proper error handling
    }

    if (result && result.rows.length > 0) {
      const stats = result.rows[0];

      res.success({data: {
          total_stocks: parseInt(stats.total_stocks) || 0,
          ranges: {
            market_cap: {
              min: parseInt(stats.min_market_cap) || 0,
              max: parseInt(stats.max_market_cap) || 0,
            },
            pe_ratio: {
              min: parseFloat(stats.min_pe_ratio) || 0,
              max: Math.min(parseFloat(stats.max_pe_ratio) || 0, 100),
            },
            price_to_book: {
              min: parseFloat(stats.min_pb_ratio) || 0.1,
              max: Math.min(parseFloat(stats.max_pb_ratio) || 20, 20),
            },
            roe: {
              min: parseFloat(stats.min_roe) || -50,
              max: Math.min(parseFloat(stats.max_roe) || 100, 100),
            },
            revenue_growth: {
              min: parseFloat(stats.min_revenue_growth) || -50,
              max: Math.min(parseFloat(stats.max_revenue_growth) || 200, 200),
            },
            analyst_rating: {
              min: parseFloat(stats.min_analyst_rating) || 1,
              max: parseFloat(stats.max_analyst_rating) || 5,
            },
          },
        },
        timestamp: new Date().toISOString(),
      });
    } else {
      // Return error response with comprehensive diagnostics instead of fallback data
      console.error(
        `❌ Database query failed for screener stats - comprehensive diagnosis needed`,
        {
          error: "No statistical data found",
          detailed_diagnostics: {
            query_attempted: "screener_statistics_query",
            potential_causes: [
              "Database connection failure",
              "Missing required tables for screener functionality",
              "Database schema corruption",
              "Data loading scripts not executed",
              "SQL query syntax errors",
            ],
            troubleshooting_steps: [
              "Check database connectivity",
              "Verify all screener tables exist",
              "Validate database schema integrity",
              "Check data loading script execution",
              "Review SQL query syntax",
            ],
            system_checks: [
              "Database health status",
              "Table existence validation",
              "Schema validation",
              "Data freshness assessment",
            ],
          },
        }
      );

      return res.error("Screener statistics unavailable", {
        message:
          "Unable to retrieve screener statistics due to database issues",
        timestamp: new Date().toISOString(),
        data_source: "error",
      }, 503);
    }
  } catch (error) {
    console.error("Error in screen stats endpoint:", error);
    return res.error("Failed to retrieve screener statistics", {
      details: error.message,
      timestamp: new Date().toISOString(),
    }, 500);
  }
});

module.exports = router;

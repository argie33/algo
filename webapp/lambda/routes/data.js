const express = require("express");

const { query } = require("../utils/database");

const router = express.Router();

// Root endpoint - provides overview of available data endpoints  
router.get("/", async (req, res) => {
  res.success({
    message: "Data API - Ready",
    timestamp: new Date().toISOString(),
    status: "operational",
    endpoints: [
      "/eps-revisions - Get EPS revisions data",
      "/eps-trend - Get EPS trend data",
      "/growth-estimates - Get growth estimates",
      "/economic - Get economic data",
      "/economic/data - Get economic data (DataValidation compatible)",
      "/naaim - Get NAAIM exposure data", 
      "/fear-greed - Get Fear & Greed Index data",
      "/validation-summary - Get data validation summary",
      "/financials/:symbol - Get comprehensive financial data for symbol",
      "/financial-metrics - Get available financial metrics across all tables"
    ]
  });
});

// Get EPS revisions data
router.get("/eps-revisions", async (req, res) => {
  try {
    const page = parseInt(req.query.page) || 1;
    const limit = parseInt(req.query.limit) || 25;
    const offset = (page - 1) * limit;
    const symbol = req.query.symbol;

    let whereClause = "";
    const queryParams = [];
    let paramCount = 0;

    if (symbol) {
      paramCount++;
      whereClause = `WHERE symbol = $${paramCount}`;
      queryParams.push(symbol.toUpperCase());
    }

    const revisionsQuery = `
      SELECT 
        symbol,
        period,
        current_estimate,
        seven_days_ago,
        thirty_days_ago,
        sixty_days_ago,
        ninety_days_ago,
        revision_direction,
        fetched_at
      FROM eps_revisions
      ${whereClause}
      ORDER BY symbol, period DESC
      LIMIT $${paramCount + 1} OFFSET $${paramCount + 2}
    `;

    const countQuery = `
      SELECT COUNT(*) as total FROM eps_revisions ${whereClause}
    `;

    queryParams.push(limit, offset);

    const [revisionsResult, countResult] = await Promise.all([
      query(revisionsQuery, queryParams),
      query(countQuery, queryParams.slice(0, paramCount)),
    ]);

    // Add null safety check BEFORE accessing .rows
    if (!revisionsResult || !revisionsResult.rows || !countResult || !countResult.rows) {
      console.warn("EPS revisions query returned null result, database may be unavailable");
      return res.error("Database temporarily unavailable", 503, {
        message: "EPS revisions data temporarily unavailable - database connection issue",
        data: [],
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

    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / limit);

    if (
      !Array.isArray(revisionsResult.rows) ||
      revisionsResult.rows.length === 0
    ) {
      return res.notFound("No data found for this query" );
    }

    res.json({
      data: revisionsResult.rows,
      pagination: {
        page,
        limit,
        total,
        totalPages,
        hasNext: page < totalPages,
        hasPrev: page > 1,
      },
    });
  } catch (error) {
    console.error("Error fetching EPS revisions:", error);
    return res.error("Database error", 500);
  }
});

// Get EPS trend data
router.get("/eps-trend", async (req, res) => {
  try {
    const page = parseInt(req.query.page) || 1;
    const limit = parseInt(req.query.limit) || 25;
    const offset = (page - 1) * limit;
    const symbol = req.query.symbol;

    let whereClause = "";
    const queryParams = [];
    let paramCount = 0;

    if (symbol) {
      paramCount++;
      whereClause = `WHERE symbol = $${paramCount}`;
      queryParams.push(symbol.toUpperCase());
    }

    const trendQuery = `
      SELECT 
        symbol,
        period,
        current_estimate,
        seven_days_ago,
        thirty_days_ago,
        sixty_days_ago,
        ninety_days_ago,
        number_of_revisions_up,
        number_of_revisions_down,
        fetched_at
      FROM eps_trend
      ${whereClause}
      ORDER BY symbol, period DESC
      LIMIT $${paramCount + 1} OFFSET $${paramCount + 2}
    `;

    const countQuery = `
      SELECT COUNT(*) as total FROM eps_trend ${whereClause}
    `;

    queryParams.push(limit, offset);

    const [trendResult, countResult] = await Promise.all([
      query(trendQuery, queryParams),
      query(countQuery, queryParams.slice(0, paramCount)),
    ]);

    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / limit);

    if (
      !trendResult ||
      !Array.isArray(trendResult.rows) ||
      trendResult.rows.length === 0
    ) {
      return res.notFound("No data found for this query" );
    }

    res.json({
      data: trendResult.rows,
      pagination: {
        page,
        limit,
        total,
        totalPages,
        hasNext: page < totalPages,
        hasPrev: page > 1,
      },
    });
  } catch (error) {
    console.error("Error fetching EPS trend:", error);
    return res.error("Database error", 500);
  }
});

// Get growth estimates data
router.get("/growth-estimates", async (req, res) => {
  try {
    const page = parseInt(req.query.page) || 1;
    const limit = parseInt(req.query.limit) || 25;
    const offset = (page - 1) * limit;
    const symbol = req.query.symbol;

    let whereClause = "";
    const queryParams = [];
    let paramCount = 0;

    if (symbol) {
      paramCount++;
      whereClause = `WHERE symbol = $${paramCount}`;
      queryParams.push(symbol.toUpperCase());
    }

    const growthQuery = `
      SELECT 
        symbol,
        period,
        growth_estimate,
        number_of_analysts,
        low_estimate,
        high_estimate,
        mean_estimate,
        fetched_at
      FROM growth_estimates
      ${whereClause}
      ORDER BY symbol, period DESC
      LIMIT $${paramCount + 1} OFFSET $${paramCount + 2}
    `;

    const countQuery = `
      SELECT COUNT(*) as total FROM growth_estimates ${whereClause}
    `;

    queryParams.push(limit, offset);

    const [growthResult, countResult] = await Promise.all([
      query(growthQuery, queryParams),
      query(countQuery, queryParams.slice(0, paramCount)),
    ]);

    // Add null safety check
    if (!countResult || !countResult.rows || countResult.rows.length === 0) {
      console.warn("Growth estimates count query returned null result, database may be unavailable");
      return res.error("Database temporarily unavailable", 503, {
        message: "Growth estimates data temporarily unavailable - database connection issue",
        data: [],
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
    
    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / limit);

    if (
      !growthResult ||
      !Array.isArray(growthResult.rows) ||
      growthResult.rows.length === 0
    ) {
      return res.notFound("No data found for this query" );
    }

    res.json({
      data: growthResult.rows,
      pagination: {
        page,
        limit,
        total,
        totalPages,
        hasNext: page < totalPages,
        hasPrev: page > 1,
      },
    });
  } catch (error) {
    console.error("Error fetching growth estimates:", error);
    return res.error("Database error", 500);
  }
});

// Get economic data
router.get("/economic", async (req, res) => {
  try {
    const page = parseInt(req.query.page) || 1;
    const limit = parseInt(req.query.limit) || 25;
    const offset = (page - 1) * limit;
    const series = req.query.series;

    let whereClause = "";
    const queryParams = [];
    let paramCount = 0;

    if (series) {
      paramCount++;
      whereClause = `WHERE series_id = $${paramCount}`;
      queryParams.push(series);
    }

    const economicQuery = `
      SELECT 
        series_id,
        date,
        value,
        title,
        units,
        frequency,
        last_updated
      FROM economic_data
      ${whereClause}
      ORDER BY series_id, date DESC
      LIMIT $${paramCount + 1} OFFSET $${paramCount + 2}
    `;

    const countQuery = `
      SELECT COUNT(*) as total FROM economic_data ${whereClause}
    `;

    queryParams.push(limit, offset);

    const [economicResult, countResult] = await Promise.all([
      query(economicQuery, queryParams),
      query(countQuery, queryParams.slice(0, paramCount)),
    ]);

    // Add null safety check
    if (!countResult || !countResult.rows || countResult.rows.length === 0) {
      console.warn("Economic data count query returned null result, database may be unavailable");
      return res.error("Database temporarily unavailable", 503, {
        message: "Economic data temporarily unavailable - database connection issue",
        data: [],
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
    
    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / limit);

    if (
      !economicResult ||
      !Array.isArray(economicResult.rows) ||
      economicResult.rows.length === 0
    ) {
      return res.notFound("No data found for this query" );
    }

    res.json({
      data: economicResult.rows,
      pagination: {
        page,
        limit,
        total,
        totalPages,
        hasNext: page < totalPages,
        hasPrev: page > 1,
      },
    });
  } catch (error) {
    console.error("Error fetching economic data:", error);
    return res.error("Database error", 500);
  }
});

// Get economic data (for DataValidation page - matches frontend expectation)
router.get("/economic/data", async (req, res) => {
  try {
    const limit = Math.min(parseInt(req.query.limit) || 50, 100);
    console.log(`Economic data endpoint called with limit: ${limit}`);

    const economicQuery = `
      SELECT series_id, date, value
      FROM economic_data 
      ORDER BY date DESC, series_id ASC
      LIMIT $1
    `;

    const result = await query(economicQuery, [limit]);

    if (!result || !Array.isArray(result.rows) || result.rows.length === 0) {
      return res.notFound("No data found for this query" );
    }

    res.json({
      data: result.rows,
      count: result.rows.length,
      limit: limit,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error fetching economic data:", error);
    return res.error("Database error", 500);
  }
});

// Get NAAIM exposure data
router.get("/naaim", async (req, res) => {
  try {
    const limit = parseInt(req.query.limit) || 50;
    const naaimQuery = `
      SELECT 
        date,
        naaim_number_mean,
        bearish,
        bullish
      FROM naaim
      ORDER BY date DESC
      LIMIT $1
    `;

    const result = await query(naaimQuery, [limit]);

    if (!result || !Array.isArray(result.rows) || result.rows.length === 0) {
      return res.notFound("No data found for this query" );
    }

    res.json({
      data: result.rows,
      count: result.rows.length,
    });
  } catch (error) {
    console.error("Error fetching NAAIM data:", error);
    return res.error("Database error", 500);
  }
});

// Get Fear & Greed Index data
router.get("/fear-greed", async (req, res) => {
  try {
    const limit = parseInt(req.query.limit) || 50;
    const fearGreedQuery = `
      SELECT 
        date,
        index_value,
        rating,
        fetched_at
      FROM fear_greed_index
      ORDER BY date DESC
      LIMIT $1
    `;

    const result = await query(fearGreedQuery, [limit]);

    if (!result || !Array.isArray(result.rows) || result.rows.length === 0) {
      return res.notFound("No data found for this query" );
    }

    res.json({
      data: result.rows,
      count: result.rows.length,
    });
  } catch (error) {
    console.error("Error fetching Fear & Greed data:", error);
    return res.error("Database error", 500);
  }
});

// Get data validation summary
router.get("/validation-summary", async (req, res) => {
  try {
    const summaryQuery = `
      SELECT 
        'stock_symbols' as table_name,
        COUNT(*) as record_count,
        NULL as last_updated
      FROM stock_symbols
      UNION ALL
      SELECT 
        'earnings_estimates' as table_name,
        COUNT(*) as record_count,
        MAX(fetched_at) as last_updated
      FROM earnings_estimates
      UNION ALL
      SELECT 
        'earnings_history' as table_name,
        COUNT(*) as record_count,
        MAX(fetched_at) as last_updated
      FROM earnings_history
      UNION ALL
      SELECT 
        'revenue_estimates' as table_name,
        COUNT(*) as record_count,
        MAX(fetched_at) as last_updated
      FROM revenue_estimates
      UNION ALL
      SELECT 
        'growth_estimates' as table_name,
        COUNT(*) as record_count,
        MAX(fetched_at) as last_updated
      FROM growth_estimates
      UNION ALL
      SELECT 
        'eps_revisions' as table_name,
        COUNT(*) as record_count,
        MAX(fetched_at) as last_updated
      FROM eps_revisions
      UNION ALL
      SELECT 
        'eps_trend' as table_name,
        COUNT(*) as record_count,
        MAX(fetched_at) as last_updated
      FROM eps_trend
      UNION ALL
      SELECT 
        'technical_data_daily' as table_name,
        COUNT(*) as record_count,
        MAX(fetched_at) as last_updated
      FROM technical_data_daily
      UNION ALL
      SELECT 
        'analyst_recommendations' as table_name,
        COUNT(*) as record_count,
        MAX(fetched_at) as last_updated
      FROM analyst_recommendations
      UNION ALL
      SELECT 
        'aaii_sentiment' as table_name,
        COUNT(*) as record_count,
        MAX(fetched_at) as last_updated
      FROM aaii_sentiment
      ORDER BY table_name
    `;

    const result = await query(summaryQuery);

    if (!result || !Array.isArray(result.rows) || result.rows.length === 0) {
      return res.notFound("No data found for this query" );
    }

    res.json({
      summary: result.rows,
      generated_at: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error fetching validation summary:", error);
    return res.error("Database error", 500);
  }
});

// Get all financial data for a symbol across all statement types
router.get("/financials/:symbol", async (req, res) => {
  try {
    const { symbol } = req.params;
    const limit = parseInt(req.query.limit) || 10;

    // Query all financial statement types
    const queries = [
      { name: "TTM Income Statement", table: "ttm_income_stmt" },
      { name: "TTM Cash Flow", table: "ttm_cashflow" },
      { name: "Annual Income Statement", table: "income_stmt" },
      { name: "Annual Cash Flow", table: "cash_flow" },
      { name: "Balance Sheet", table: "balance_sheet" },
      { name: "Quarterly Income Statement", table: "quarterly_income_stmt" },
      { name: "Quarterly Cash Flow", table: "quarterly_cashflow" },
      { name: "Quarterly Balance Sheet", table: "quarterly_balance_sheet" },
    ];

    const results = {};

    for (const { name, table } of queries) {
      try {
        const financialQuery = `
          SELECT date, item_name, value
          FROM ${table}
          WHERE symbol = $1
          ORDER BY date DESC, item_name
          LIMIT $2
        `;

        const result = await query(financialQuery, [
          symbol.toUpperCase(),
          limit * 50,
        ]); // Get more items per date

        // Transform the data by date
        const transformedData = {};
        result.rows.forEach((row) => {
          const dateKey = row.date;
          if (!transformedData[dateKey]) {
            transformedData[dateKey] = {
              date: row.date,
              items: {},
            };
          }
          transformedData[dateKey].items[row.item_name] = row.value;
        });

        results[name] = Object.values(transformedData)
          .sort((a, b) => new Date(b.date) - new Date(a.date))
          .slice(0, limit);
      } catch (tableError) {
        console.warn(`Table ${table} not accessible:`, tableError.message);
        results[name] = [];
      }
    }

    if (Object.values(results).every((tableData) => tableData.length === 0)) {
      return res.notFound("No data found for this query" );
    }

    res.json({
      symbol: symbol.toUpperCase(),
      data: results,
      limit,
    });
  } catch (error) {
    console.error("Error fetching comprehensive financial data:", error);
    return res.error("Database error", 500);
  }
});

// Get all available financial metrics (item names) across all tables
router.get("/financial-metrics", async (req, res) => {
  try {
    const tables = [
      "ttm_income_stmt",
      "ttm_cashflow",
      "income_stmt",
      "cash_flow",
      "balance_sheet",
      "quarterly_income_stmt",
      "quarterly_cashflow",
      "quarterly_balance_sheet",
    ];

    const metrics = {};

    for (const table of tables) {
      try {
        const metricsQuery = `
          SELECT DISTINCT item_name, COUNT(*) as occurrence_count
          FROM ${table}
          GROUP BY item_name
          ORDER BY item_name
        `;

        const result = await query(metricsQuery);
        metrics[table] = result.rows;
      } catch (tableError) {
        console.warn(`Table ${table} not accessible:`, tableError.message);
        metrics[table] = [];
      }
    }

    if (
      Object.values(metrics).every((tableMetrics) => tableMetrics.length === 0)
    ) {
      return res.notFound("No data found for this query" );
    }

    res.json({
      metrics,
      tables: tables,
      generated_at: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error fetching financial metrics:", error);
    return res.error("Database error", 500);
  }
});

module.exports = router;

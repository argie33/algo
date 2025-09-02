const express = require("express");

const { query } = require("../utils/database");

const router = express.Router();

// Health endpoint (no auth required)
router.get("/health", (req, res) => {
  res.success({status: "operational",
    service: "economic-calendar",
    timestamp: new Date().toISOString(),
    message: "Economic Calendar service is running",
  });
});

// Basic root endpoint (public)
router.get("/", (req, res) => {
  res.success({message: "Economic Calendar API - Ready",
    timestamp: new Date().toISOString(),
    status: "operational",
  });
});

// Earnings calendar endpoint
router.get("/earnings", async (req, res) => {
  try {
    const { 
      symbol, 
      start_date, 
      end_date, 
      days_ahead = 30,
      limit = 50 
    } = req.query;

    console.log(`📅 Earnings calendar requested - symbol: ${symbol || 'all'}, days_ahead: ${days_ahead}`);

    let whereClause = "WHERE 1=1";
    let params = [];
    let paramIndex = 1;

    // Add symbol filter if provided
    if (symbol) {
      whereClause += ` AND symbol = $${paramIndex}`;
      params.push(symbol.toUpperCase());
      paramIndex++;
    }

    // Add date range filter
    if (start_date && end_date) {
      whereClause += ` AND report_date >= $${paramIndex} AND report_date <= $${paramIndex + 1}`;
      params.push(start_date, end_date);
      paramIndex += 2;
    } else {
      // Default to upcoming earnings (next N days)
      whereClause += ` AND report_date >= CURRENT_DATE AND report_date <= CURRENT_DATE + INTERVAL '${parseInt(days_ahead)} days'`;
    }

    whereClause += ` ORDER BY report_date ASC, symbol ASC LIMIT $${paramIndex}`;
    params.push(parseInt(limit));

    // First check what columns actually exist in earnings_reports table
    let availableColumns;
    try {
      const columnCheck = await query(`
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'earnings_reports'
        ORDER BY ordinal_position
      `);
      availableColumns = columnCheck.rows.map(row => row.column_name);
      console.log('Available earnings_reports columns:', availableColumns);
    } catch (error) {
      console.error("Could not check earnings_reports table structure:", error.message);
      throw new Error(`Database table structure check failed: ${error.message}`);
    }

    // Build dynamic query based on available columns
    let selectColumns = ['symbol'];
    const columnMap = {
      'report_date': 'report_date',
      'announcement_date': 'report_date', 
      'date': 'report_date',
      'quarter': 'quarter',
      'qtr': 'quarter',
      'year': 'year',
      'fiscal_year': 'year',
      'estimated_eps': 'estimated_eps',
      'estimate': 'estimated_eps',
      'consensus_eps': 'estimated_eps',
      'actual_eps': 'actual_eps', 
      'reported_eps': 'actual_eps',
      'surprise_percent': 'surprise_percent',
      'surprise': 'surprise_percent'
    };

    // Add available columns to select
    Object.keys(columnMap).forEach(colVariant => {
      if (availableColumns.includes(colVariant)) {
        const alias = columnMap[colVariant];
        if (!selectColumns.includes(`${colVariant} as ${alias}`) && !selectColumns.includes(alias)) {
          selectColumns.push(alias !== colVariant ? `${colVariant} as ${alias}` : colVariant);
        }
      }
    });

    console.log('Using select columns:', selectColumns);

    const result = await query(
      `
      SELECT ${selectColumns.join(', ')}
      FROM earnings_reports
      ${whereClause}
      `,
      params
    );

    if (result.rows.length === 0) {
      return res.json({
        success: true,
        data: {
          earnings: [],
          grouped_by_date: {},
          summary: {
            total_earnings: 0,
            upcoming_reports: 0,
            completed_reports: 0,
            sectors_represented: 0,
            message: "No earnings data found for the specified criteria"
          }
        },
        timestamp: new Date().toISOString()
      });
    }

    // Transform and enrich the data with real database values
    const earnings = result.rows.map(row => ({
      symbol: row.symbol,
      company_name: null, // Will be populated from stocks table if available
      sector: null,
      market_cap: null,
      report_date: row.report_date,
      quarter: parseInt(row.quarter || 1),
      year: parseInt(row.year || new Date().getFullYear()),
      period: `Q${row.quarter || 1} ${row.year || new Date().getFullYear()}`,
      estimated_eps: row.estimated_eps ? parseFloat(row.estimated_eps).toFixed(2) : null,
      actual_eps: row.actual_eps ? parseFloat(row.actual_eps).toFixed(2) : null,
      surprise_percent: row.surprise_percent ? parseFloat(row.surprise_percent).toFixed(2) : null,
      status: row.actual_eps ? 'reported' : 'upcoming',
      days_until: row.report_date ? Math.ceil((new Date(row.report_date) - new Date()) / (1000 * 60 * 60 * 24)) : null
    }));

    // Try to enrich with company data from stocks table if available
    try {
      const symbols = [...new Set(earnings.map(e => e.symbol))];
      if (symbols.length > 0) {
        const companyData = await query(
          `SELECT symbol, name, sector, market_cap FROM stocks WHERE symbol = ANY($1)`,
          [symbols]
        );
        
        const companyMap = {};
        companyData.rows.forEach(row => {
          companyMap[row.symbol] = {
            name: row.name,
            sector: row.sector, 
            market_cap: row.market_cap
          };
        });

        // Enrich earnings data with company info
        earnings.forEach(earning => {
          if (companyMap[earning.symbol]) {
            earning.company_name = companyMap[earning.symbol].name;
            earning.sector = companyMap[earning.symbol].sector;
            earning.market_cap = companyMap[earning.symbol].market_cap;
          }
        });
      }
    } catch (enrichError) {
      console.log("Could not enrich with company data:", enrichError.message);
      // Continue without company enrichment
    }

    // Group by date for easier consumption
    const groupedByDate = earnings.reduce((groups, earning) => {
      const date = earning.report_date;
      if (!groups[date]) {
        groups[date] = [];
      }
      groups[date].push(earning);
      return groups;
    }, {});

    // Calculate summary statistics
    const upcomingCount = earnings.filter(e => e.status === 'upcoming').length;
    const reportedCount = earnings.filter(e => e.status === 'reported').length;
    const sectors = [...new Set(earnings.map(e => e.sector).filter(Boolean))];

    res.json({
      success: true,
      data: {
        earnings: earnings,
        grouped_by_date: groupedByDate,
        summary: {
          total_earnings: earnings.length,
          upcoming_reports: upcomingCount,
          completed_reports: reportedCount,
          sectors_represented: sectors.length,
          date_range: {
            from: earnings[0]?.report_date || null,
            to: earnings[earnings.length - 1]?.report_date || null
          }
        }
      },
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error("Earnings calendar error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch earnings calendar",
      details: error.message
    });
  }
});

// Debug endpoint to check earnings_reports table status (used for calendar functionality)
router.get("/debug", async (req, res) => {
  try {
    console.log("Calendar debug endpoint called");

    // Check if earnings_reports table exists (our calendar data source)
    const tableExistsQuery = `
      SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'earnings_reports'
      );
    `;

    const tableExists = await query(tableExistsQuery);
    console.log("Table exists check:", tableExists.rows[0]);

    if (tableExists.rows[0].exists) {
      // Count total records
      const countQuery = `SELECT COUNT(*) as total FROM earnings_reports`;
      const countResult = await query(countQuery);
      console.log("Total earnings reports:", countResult.rows[0]);

      // Get sample records
      const sampleQuery = `
        SELECT symbol, 'earnings' as event_type, report_date as start_date, 
               CONCAT('Q', quarter, ' ', year, ' Earnings Report') as title, 
               eps_estimate, eps_reported
        FROM earnings_reports 
        ORDER BY report_date DESC 
        LIMIT 5
      `;
      const sampleResult = await query(sampleQuery);
      console.log("Sample records:", sampleResult.rows);

      res.json({
        tableExists: true,
        tableName: "earnings_reports",
        totalRecords: parseInt(countResult.rows[0].total),
        sampleRecords: sampleResult.rows,
        note: "Using earnings_reports table for calendar functionality",
        timestamp: new Date().toISOString(),
      });
    } else {
      res.json({
        tableExists: false,
        message: "earnings_reports table does not exist",
        timestamp: new Date().toISOString(),
      });
    }
  } catch (error) {
    console.error("Error in calendar debug:", error);
    return res.error("Debug check failed", 500);
  }
});

// Simple test endpoint that returns raw data from earnings_reports
router.get("/test", async (req, res) => {
  try {
    console.log("Calendar test endpoint called");

    const testQuery = `
      SELECT 
        symbol,
        'earnings' as event_type,
        report_date as start_date,
        report_date as end_date,
        CONCAT('Q', quarter, ' ', year, ' Earnings Report') as title,
        eps_estimate,
        eps_reported
      FROM earnings_reports
      ORDER BY report_date ASC
      LIMIT 10
    `;

    const result = await query(testQuery);

    if (!result || !Array.isArray(result.rows) || result.rows.length === 0) {
      return res.notFound("No earnings data found for this query" );
    }

    res.success({count: result.rows.length,
      data: result.rows,
      note: "Using earnings_reports table for calendar test data",
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error in calendar test:", error);
    return res.error("Test failed", 500);
  }
});

// Get calendar events (earnings, dividends, splits, etc.)
// Note: Using earnings_reports table since calendar_events doesn't exist
router.get("/events", async (req, res) => {
  try {
    console.log("Calendar events endpoint called with params:", req.query);

    const page = parseInt(req.query.page) || 1;
    const limit = parseInt(req.query.limit) || 25;
    const offset = (page - 1) * limit;
    const timeFilter = req.query.type || "upcoming";

    let whereClause = "WHERE 1=1";
    const _params = []; // Apply time filters using report_date from earnings_reports
    switch (timeFilter) {
      case "this_week":
        whereClause += ` AND er.report_date >= CURRENT_DATE AND er.report_date < (CURRENT_DATE + INTERVAL '7 days')`;
        break;
      case "next_week":
        whereClause += ` AND er.report_date >= (CURRENT_DATE + INTERVAL '7 days') AND er.report_date < (CURRENT_DATE + INTERVAL '14 days')`;
        break;
      case "this_month":
        whereClause += ` AND er.report_date >= CURRENT_DATE AND er.report_date < (CURRENT_DATE + INTERVAL '30 days')`;
        break;
      case "upcoming":
      default:
        whereClause += ` AND er.report_date >= CURRENT_DATE`;
        break;
    }

    console.log("Using whereClause:", whereClause);

    const eventsQuery = `
      SELECT 
        er.symbol,
        'earnings' as event_type,
        er.report_date as start_date,
        er.report_date as end_date,
        CONCAT('Q', er.quarter, ' ', er.year, ' Earnings Report') as title,
        cp.company_name,
        er.eps_estimate,
        er.eps_reported,
        er.revenue
      FROM earnings_reports er
      LEFT JOIN company_profile cp ON er.symbol = cp.ticker
      ${whereClause}
      ORDER BY er.report_date ASC
      LIMIT $1 OFFSET $2
    `;

    const countQuery = `
      SELECT COUNT(*) as total
      FROM earnings_reports er
      ${whereClause}
    `;
    console.log("Executing queries with limit:", limit, "offset:", offset);

    const [eventsResult, countResult] = await Promise.all([
      query(eventsQuery, [limit, offset]),
      query(countQuery, []),
    ]);

    // Add null safety check BEFORE accessing .rows
    if (
      !eventsResult ||
      !eventsResult.rows ||
      !countResult ||
      !countResult.rows
    ) {
      console.warn("Calendar events query returned null result, database may be unavailable");
      return res.error("Database temporarily unavailable", 503, {
        message: "Calendar events temporarily unavailable - database connection issue",
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

    console.log(
      "Query results - events:",
      eventsResult.rows.length,
      "total:",
      countResult.rows[0].total
    );

    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / limit);

    // Return empty results with 200 status, not 404
    if (!Array.isArray(eventsResult.rows) || eventsResult.rows.length === 0) {
      return res.success({
        data: [],
        pagination: {
          page,
          limit,
          total: 0,
          totalPages: 0,
          hasNext: false,
          hasPrev: false,
        },
        summary: {
          upcoming_events: 0,
          this_week: 0,
          filter: timeFilter,
        },
        message: "No calendar events found for the specified criteria"
      });
    }

    res.json({
      data: eventsResult.rows,
      pagination: {
        page,
        limit,
        total,
        totalPages,
        hasNext: page < totalPages,
        hasPrev: page > 1,
      },
      summary: {
        upcoming_events: total,
        this_week: 0, // Would need separate query
        filter: timeFilter,
      },
    });
  } catch (error) {
    console.error("Error fetching calendar events:", error);
    console.error("Error stack:", error.stack);
    return res.error("Failed to fetch calendar events", 500);
  }
});

// Get upcoming calendar events (comprehensive financial calendar)
router.get("/upcoming", async (req, res) => {
  try {
    const { 
      limit = 50, 
      days = 14, 
      type = "all",
      symbol 
    } = req.query;

    console.log(`📅 Upcoming calendar events requested - days: ${days}, type: ${type}, limit: ${limit}`);

    console.log(`📅 Calendar upcoming events - not implemented`);

    return res.status(501).json({
      success: false,
      error: "Calendar upcoming events not implemented",
      details: "This endpoint requires integration with multiple financial data providers for earnings, dividends, splits, IPOs, and economic events.",
      troubleshooting: {
        suggestion: "Calendar events require external data feed integration",
        required_setup: [
          "Yahoo Finance events API integration",
          "SEC filings API for corporate actions",
          "Economic calendar API integration",
          "Calendar events database tables"
        ],
        status: "Not implemented - requires multiple data source integrations"
      },
      symbol: symbol || null,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error("Upcoming calendar error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch upcoming calendar events",
      details: error.message
    });
  }
});

// Get earnings calendar summary
router.get("/summary", async (req, res) => {
  try {
    const summaryQuery = `
      SELECT 
        COUNT(CASE WHEN start_date >= CURRENT_DATE AND start_date < CURRENT_DATE + INTERVAL '7 days' THEN 1 END) as this_week,
        COUNT(CASE WHEN start_date >= CURRENT_DATE + INTERVAL '7 days' AND start_date < CURRENT_DATE + INTERVAL '14 days' THEN 1 END) as next_week,
        COUNT(CASE WHEN start_date >= CURRENT_DATE AND start_date < CURRENT_DATE + INTERVAL '30 days' THEN 1 END) as this_month,
        COUNT(CASE WHEN event_type = 'earnings' AND start_date >= CURRENT_DATE THEN 1 END) as upcoming_earnings,
        COUNT(CASE WHEN event_type = 'dividend' AND start_date >= CURRENT_DATE THEN 1 END) as upcoming_dividends
      FROM calendar_events
    `;

    const result = await query(summaryQuery);

    if (!result || !Array.isArray(result.rows) || result.rows.length === 0) {
      return res.notFound("No data found for this query" );
    }

    res.json({
      summary: result.rows[0],
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error fetching calendar summary:", error);
    return res.error("Failed to fetch calendar summary" , 500);
  }
});

// Get earnings estimates for all companies
router.get("/earnings-estimates", async (req, res) => {
  try {
    const page = parseInt(req.query.page) || 1;
    const limit = parseInt(req.query.limit) || 25;
    const offset = (page - 1) * limit;

    const estimatesQuery = `
      SELECT 
        ee.symbol,
        cp.company_name,
        ee.period,
        ee.avg_estimate,
        ee.low_estimate,
        ee.high_estimate,
        ee.number_of_analysts,
        ee.growth
      FROM earnings_estimates ee
      LEFT JOIN company_profile cp ON ee.symbol = cp.ticker
      ORDER BY ee.symbol ASC, ee.period DESC
      LIMIT $1 OFFSET $2
    `;

    const countQuery = `
      SELECT COUNT(*) as total
      FROM earnings_estimates
    `;

    // Group and summarize by symbol for insights
    const summaryQuery = `
      SELECT 
        symbol,
        COUNT(*) as count,
        AVG(growth) as avg_growth,
        AVG(avg_estimate) as avg_estimate,
        MAX(high_estimate) as max_estimate,
        MIN(low_estimate) as min_estimate
      FROM earnings_estimates
      GROUP BY symbol
      ORDER BY symbol ASC
    `;

    const [estimatesResult, countResult, summaryResult] = await Promise.all([
      query(estimatesQuery, [limit, offset]),
      query(countQuery),
      query(summaryQuery),
    ]);

    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / limit);

    // Group data by symbol
    const grouped = {};
    estimatesResult.rows.forEach((row) => {
      if (!grouped[row.symbol])
        grouped[row.symbol] = { company_name: row.company_name, estimates: [] };
      grouped[row.symbol].estimates.push(row);
    });

    // Attach summary insights
    const insights = {};
    summaryResult.rows.forEach((row) => {
      insights[row.symbol] = {
        count: row.count,
        avg_growth: row.avg_growth,
        avg_estimate: row.avg_estimate,
        max_estimate: row.max_estimate,
        min_estimate: row.min_estimate,
      };
    });

    if (
      !estimatesResult ||
      !Array.isArray(estimatesResult.rows) ||
      estimatesResult.rows.length === 0
    ) {
      return res.notFound("No data found for this query" );
    }

    res.json({
      data: grouped,
      pagination: {
        page,
        limit,
        total,
        totalPages,
        hasNext: page < totalPages,
        hasPrev: page > 1,
      },
      insights,
    });
  } catch (error) {
    console.error("Error fetching earnings estimates:", error);
    return res.error("Failed to fetch earnings estimates" , 500);
  }
});

// Get earnings history for all companies
router.get("/earnings-history", async (req, res) => {
  try {
    const page = parseInt(req.query.page) || 1;
    const limit = parseInt(req.query.limit) || 25;
    const offset = (page - 1) * limit;

    const historyQuery = `
      SELECT 
        eh.symbol,
        cp.company_name,
        eh.quarter,
        eh.eps_actual,
        eh.eps_estimate,
        eh.eps_difference,
        eh.surprise_percent
      FROM earnings_history eh
      LEFT JOIN company_profile cp ON eh.symbol = cp.ticker
      ORDER BY eh.symbol ASC, eh.quarter DESC
      LIMIT $1 OFFSET $2
    `;

    const countQuery = `
      SELECT COUNT(*) as total
      FROM earnings_history
    `;

    // Group and summarize by symbol for insights
    const summaryQuery = `
      SELECT 
        symbol,
        COUNT(*) as count,
        AVG(surprise_percent) as avg_surprise,
        MAX(eps_actual) as max_actual,
        MIN(eps_actual) as min_actual,
        MAX(eps_estimate) as max_estimate,
        MIN(eps_estimate) as min_estimate,
        SUM(CASE WHEN surprise_percent > 0 THEN 1 ELSE 0 END) as positive_surprises,
        SUM(CASE WHEN surprise_percent < 0 THEN 1 ELSE 0 END) as negative_surprises
      FROM earnings_history
      GROUP BY symbol
      ORDER BY symbol ASC
    `;

    const [historyResult, countResult, summaryResult] = await Promise.all([
      query(historyQuery, [limit, offset]),
      query(countQuery),
      query(summaryQuery),
    ]);

    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / limit);

    // Group data by symbol
    const grouped = {};
    historyResult.rows.forEach((row) => {
      if (!grouped[row.symbol])
        grouped[row.symbol] = { company_name: row.company_name, history: [] };
      grouped[row.symbol].history.push(row);
    });

    // Attach summary insights
    const insights = {};
    summaryResult.rows.forEach((row) => {
      insights[row.symbol] = {
        count: row.count,
        avg_surprise: row.avg_surprise,
        max_actual: row.max_actual,
        min_actual: row.min_actual,
        max_estimate: row.max_estimate,
        min_estimate: row.min_estimate,
        positive_surprises: row.positive_surprises,
        negative_surprises: row.negative_surprises,
      };
    });

    if (
      !historyResult ||
      !Array.isArray(historyResult.rows) ||
      historyResult.rows.length === 0
    ) {
      return res.notFound("No data found for this query" );
    }

    res.json({
      data: grouped,
      pagination: {
        page,
        limit,
        total,
        totalPages,
        hasNext: page < totalPages,
        hasPrev: page > 1,
      },
      insights,
    });
  } catch (error) {
    console.error("Error fetching earnings history:", error);
    return res.error("Failed to fetch earnings history" , 500);
  }
});

// Get earnings metrics for all companies
router.get("/earnings-metrics", async (req, res) => {
  try {
    const page = parseInt(req.query.page) || 1;
    const limit = parseInt(req.query.limit) || 25;
    const offset = (page - 1) * limit;

    const metricsQuery = `
      SELECT 
        em.symbol,
        cp.company_name,
        em.report_date,
        em.eps_growth_1q,
        em.eps_growth_2q,
        em.eps_growth_4q,
        em.eps_growth_8q,
        em.eps_acceleration_qtrs,
        em.eps_surprise_last_q,
        em.eps_estimate_revision_1m,
        em.eps_estimate_revision_3m,
        em.eps_estimate_revision_6m,
        em.annual_eps_growth_1y,
        em.annual_eps_growth_3y,
        em.annual_eps_growth_5y,
        em.consecutive_eps_growth_years,
        em.eps_estimated_change_this_year
      FROM earnings_metrics em
      LEFT JOIN company_profile cp ON em.symbol = cp.ticker
      ORDER BY em.symbol ASC, em.report_date DESC
      LIMIT $1 OFFSET $2
    `;

    const countQuery = `
      SELECT COUNT(*) as total
      FROM earnings_metrics
    `;

    // Group and summarize by symbol for insights
    const summaryQuery = `
      SELECT 
        symbol,
        COUNT(*) as count,
        AVG(eps_growth_1q) as avg_growth_1q,
        AVG(eps_growth_2q) as avg_growth_2q,
        AVG(eps_growth_4q) as avg_growth_4q,
        AVG(eps_growth_8q) as avg_growth_8q,
        MAX(annual_eps_growth_1y) as max_annual_growth_1y,
        MAX(annual_eps_growth_3y) as max_annual_growth_3y,
        MAX(annual_eps_growth_5y) as max_annual_growth_5y
      FROM earnings_metrics
      GROUP BY symbol
      ORDER BY symbol ASC
    `;

    const [metricsResult, countResult, summaryResult] = await Promise.all([
      query(metricsQuery, [limit, offset]),
      query(countQuery),
      query(summaryQuery),
    ]);

    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / limit);

    // Group data by symbol
    const grouped = {};
    metricsResult.rows.forEach((row) => {
      if (!grouped[row.symbol])
        grouped[row.symbol] = { company_name: row.company_name, metrics: [] };
      grouped[row.symbol].metrics.push(row);
    });

    // Attach summary insights
    const insights = {};
    summaryResult.rows.forEach((row) => {
      insights[row.symbol] = {
        count: row.count,
        avg_growth_1q: row.avg_growth_1q,
        avg_growth_2q: row.avg_growth_2q,
        avg_growth_4q: row.avg_growth_4q,
        avg_growth_8q: row.avg_growth_8q,
        max_annual_growth_1y: row.max_annual_growth_1y,
        max_annual_growth_3y: row.max_annual_growth_3y,
        max_annual_growth_5y: row.max_annual_growth_5y,
      };
    });

    if (
      !metricsResult ||
      !Array.isArray(metricsResult.rows) ||
      metricsResult.rows.length === 0
    ) {
      return res.notFound("No data found for this query" );
    }

    res.json({
      data: grouped,
      pagination: {
        page,
        limit,
        total,
        totalPages,
        hasNext: page < totalPages,
        hasPrev: page > 1,
      },
      insights,
    });
  } catch (error) {
    console.error("Error fetching earnings metrics:", error);
    res.status(500).json({
      error: "Failed to fetch earnings metrics",
      data: {}, // Always return data as an object for frontend safety
      pagination: {
        page: 1,
        limit: 25,
        total: 0,
        totalPages: 0,
        hasNext: false,
        hasPrev: false,
      },
      insights: {},
    });
  }
});

// Get calendar dividends endpoint
router.get("/dividends", async (req, res) => {
  try {
    const { 
      symbol, 
      start_date: _startDate, 
      end_date: _endDate, 
      days_ahead: _days_ahead = 30,
      limit: _limit = 50 
    } = req.query;

    console.log(`💰 Dividends calendar requested - symbol: ${symbol || 'all'}, days_ahead: ${_days_ahead}`);

    console.log(`💰 Dividend calendar - not implemented`);

    return res.status(501).json({
      success: false,
      error: "Dividend calendar not implemented",
      details: "This endpoint requires integration with dividend data providers for ex-dividend dates, payment dates, and dividend amounts.",
      troubleshooting: {
        suggestion: "Dividend calendar requires external data feed integration",
        required_setup: [
          "Yahoo Finance dividends API integration",
          "Company dividend database tables",
          "Dividend calendar data pipeline"
        ],
        status: "Not implemented - requires dividend data integration"
      },
      symbol: symbol || null,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error("Dividends calendar error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch dividends calendar",
      message: error.message
    });
  }
});

// Get calendar economic events endpoint
router.get("/economic", async (req, res) => {
  try {
    const { 
      country = "US", 
      importance = "all", 
      days_ahead: _days_ahead = 14,
      limit: _limit = 30 
    } = req.query;

    console.log(`📊 Economic calendar requested - country: ${country}, importance: ${importance}`);

    console.log(`📊 Economic calendar - not implemented`);

    return res.status(501).json({
      success: false,
      error: "Economic calendar not implemented",
      details: "This endpoint requires integration with economic data providers for government statistics, central bank announcements, and economic indicators.",
      troubleshooting: {
        suggestion: "Economic calendar requires government data feed integration",
        required_setup: [
          "Federal Reserve API integration",
          "Bureau of Labor Statistics API",
          "Economic indicators database tables",
          "Central bank announcements data pipeline"
        ],
        status: "Not implemented - requires economic data integration"
      },
      country: country,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error("Economic calendar error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch economic calendar",
      message: error.message
    });
  }
});

module.exports = router;

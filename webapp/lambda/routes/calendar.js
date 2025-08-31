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

    if (
      !Array.isArray(eventsResult.rows) ||
      eventsResult.rows.length === 0
    ) {
      return res.error("No earnings events found for this query", 404);
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

module.exports = router;

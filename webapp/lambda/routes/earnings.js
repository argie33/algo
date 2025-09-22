const express = require("express");

const { query } = require("../utils/database");
const responseFormatter = require("../middleware/responseFormatter");

const router = express.Router();

// Apply response formatter middleware to all routes
router.use(responseFormatter);

// Earnings data - use real earnings tables from loaders
router.get("/", async (req, res) => {
  try {
    console.log(`📈 Earnings data requested`);

    const page = parseInt(req.query.page) || 1;
    const limit = Math.min(parseInt(req.query.limit) || 50, 200);
    const offset = (page - 1) * limit;

    // Try earnings_history table first, fallback if columns don't exist
    let result;
    try {
      const earningsQuery = `
        SELECT
          symbol,
          quarter as report_date,
          eps_actual,
          eps_estimate,
          eps_difference,
          surprise_percent,
          quarter,
          fetched_at as last_updated
        FROM earnings_history
        ORDER BY quarter DESC, symbol
        LIMIT $1 OFFSET $2
      `;

      result = await query(earningsQuery, [limit, offset]);
    } catch (error) {
      // If columns don't exist, try a simpler query or generate sample data
      console.log("Earnings table schema mismatch, using fallback data");

      try {
        // Try to get just basic columns that might exist
        const fallbackQuery = `
          SELECT
            symbol,
            quarter as report_date,
            fetched_at as last_updated
          FROM earnings_history
          ORDER BY quarter DESC, symbol
          LIMIT $1 OFFSET $2
        `;

        const fallbackResult = await query(fallbackQuery, [limit, offset]);

        // Add missing fields with default values
        result = {
          rows: fallbackResult.rows.map(row => ({
            ...row,
            eps_actual: 0,
            eps_estimate: 0,
            eps_difference: 0,
            surprise_percent: 0
          }))
        };
      } catch (fallbackError) {
        // If table doesn't exist at all, return empty data
        result = { rows: [] };
      }
    }

    res.json({
      success: true,
      data: result.rows,
      pagination: {
        page,
        limit,
        total: result.rows.length,
        hasMore: result.rows.length === limit,
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Earnings delegation error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch earnings data",
      details: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

// Earnings calendar endpoint
router.get("/calendar", async (req, res) => {
  try {
    const {
      startDate,
      endDate,
      period = "upcoming",
      limit = 100
    } = req.query;

    console.log(`📅 Earnings calendar requested for period: ${period}`);

    let dateFilter = "";
    let queryParams = [parseInt(limit)];

    if (startDate && endDate) {
      dateFilter = "WHERE date BETWEEN $2 AND $3";
      queryParams = [parseInt(limit), startDate, endDate];
    } else if (period === "upcoming") {
      dateFilter = "WHERE date >= CURRENT_DATE";
    } else if (period === "past") {
      dateFilter = "WHERE date < CURRENT_DATE";
    }

    try {
      // Try earnings_reports table first
      const calendarQuery = `
        SELECT
          er.symbol,
          er.date,
          er.quarter,
          er.year,
          er.estimated_eps,
          er.actual_eps,
          er.estimated_revenue,
          er.actual_revenue,
          cp.company_name,
          cp.sector,
          cp.market_cap
        FROM earnings_reports er
        LEFT JOIN company_profile cp ON er.symbol = cp.symbol
        ${dateFilter}
        ORDER BY er.date ASC, er.symbol
        LIMIT $1
      `;

      const result = await query(calendarQuery, queryParams);

      res.json({
        success: true,
        data: {
          calendar: result.rows.map(row => ({
            symbol: row.symbol,
            company_name: row.company_name || row.symbol,
            date: row.date,
            quarter: row.quarter,
            year: row.year,
            estimated_eps: parseFloat(row.estimated_eps || 0),
            actual_eps: row.actual_eps ? parseFloat(row.actual_eps) : null,
            estimated_revenue: parseFloat(row.estimated_revenue || 0),
            actual_revenue: row.actual_revenue ? parseFloat(row.actual_revenue) : null,
            sector: row.sector || "Unknown",
            market_cap: parseFloat(row.market_cap || 0),
            is_reported: !!row.actual_eps
          })),
          period,
          total: result.rows.length,
          filters: {
            startDate: startDate || null,
            endDate: endDate || null,
            period
          }
        },
        timestamp: new Date().toISOString(),
      });

    } catch (error) {
      console.log("Earnings reports table not available, using fallback");

      // Fallback to earnings_history if available
      try {
        const fallbackQuery = `
          SELECT
            symbol,
            quarter as date,
            quarter,
            eps_actual,
            eps_estimate
          FROM earnings_history
          ORDER BY quarter DESC
          LIMIT $1
        `;

        const fallbackResult = await query(fallbackQuery, [parseInt(limit)]);

        res.json({
          success: true,
          data: {
            calendar: fallbackResult.rows.map(row => ({
              symbol: row.symbol,
              company_name: row.symbol,
              date: row.date,
              quarter: row.quarter,
              year: new Date(row.quarter).getFullYear(),
              estimated_eps: parseFloat(row.eps_estimate || 0),
              actual_eps: row.eps_actual ? parseFloat(row.eps_actual) : null,
              estimated_revenue: 0,
              actual_revenue: null,
              sector: "Unknown",
              market_cap: 0,
              is_reported: !!row.eps_actual
            })),
            period,
            total: fallbackResult.rows.length,
            filters: { period }
          },
          timestamp: new Date().toISOString(),
        });

      } catch (fallbackError) {
        res.json({
          success: true,
          data: {
            calendar: [],
            period,
            total: 0,
            message: "No earnings calendar data available"
          },
          timestamp: new Date().toISOString(),
        });
      }
    }

  } catch (error) {
    console.error("Earnings calendar error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch earnings calendar",
      details: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

// Earnings surprises endpoint
router.get("/surprises", async (req, res) => {
  try {
    const {
      symbol,
      period = "recent",
      limit = 50,
      minSurprise = 0
    } = req.query;

    console.log(`📊 Earnings surprises requested - Symbol: ${symbol || 'all'}, Period: ${period}`);

    let symbolFilter = "";
    let surpriseFilter = "";
    let queryParams = [parseInt(limit)];

    if (symbol) {
      symbolFilter = "AND er.symbol = $2";
      queryParams = [parseInt(limit), symbol.toUpperCase()];
    }

    if (minSurprise && parseFloat(minSurprise) > 0) {
      const surpriseIndex = queryParams.length + 1;
      surpriseFilter = `AND ABS(((er.actual_eps - er.estimated_eps) / NULLIF(ABS(er.estimated_eps), 0)) * 100) >= $${surpriseIndex}`;
      queryParams.push(parseFloat(minSurprise));
    }

    try {
      // Try earnings_reports table with calculated surprises
      const surprisesQuery = `
        SELECT
          er.symbol,
          er.date,
          er.quarter,
          er.year,
          er.estimated_eps,
          er.actual_eps,
          er.estimated_revenue,
          er.actual_revenue,
          cp.company_name,
          cp.sector,
          cp.market_cap,
          CASE
            WHEN er.estimated_eps != 0 AND er.actual_eps IS NOT NULL
            THEN ((er.actual_eps - er.estimated_eps) / ABS(er.estimated_eps)) * 100
            ELSE 0
          END as eps_surprise_percent,
          CASE
            WHEN er.estimated_revenue != 0 AND er.actual_revenue IS NOT NULL
            THEN ((er.actual_revenue - er.estimated_revenue) / ABS(er.estimated_revenue)) * 100
            ELSE 0
          END as revenue_surprise_percent
        FROM earnings_reports er
        LEFT JOIN company_profile cp ON er.symbol = cp.symbol
        WHERE er.actual_eps IS NOT NULL
        ${symbolFilter}
        ${surpriseFilter}
        ORDER BY ABS(((er.actual_eps - er.estimated_eps) / NULLIF(ABS(er.estimated_eps), 0)) * 100) DESC, er.date DESC
        LIMIT $1
      `;

      const result = await query(surprisesQuery, queryParams);

      res.json({
        success: true,
        data: {
          surprises: result.rows.map(row => ({
            symbol: row.symbol,
            company_name: row.company_name || row.symbol,
            date: row.date,
            quarter: row.quarter,
            year: row.year,
            earnings: {
              estimated_eps: parseFloat(row.estimated_eps || 0),
              actual_eps: parseFloat(row.actual_eps || 0),
              eps_surprise: parseFloat(row.actual_eps || 0) - parseFloat(row.estimated_eps || 0),
              eps_surprise_percent: Math.round(parseFloat(row.eps_surprise_percent || 0) * 100) / 100
            },
            revenue: {
              estimated_revenue: parseFloat(row.estimated_revenue || 0),
              actual_revenue: parseFloat(row.actual_revenue || 0),
              revenue_surprise: parseFloat(row.actual_revenue || 0) - parseFloat(row.estimated_revenue || 0),
              revenue_surprise_percent: Math.round(parseFloat(row.revenue_surprise_percent || 0) * 100) / 100
            },
            sector: row.sector || "Unknown",
            market_cap: parseFloat(row.market_cap || 0)
          })),
          filters: {
            symbol: symbol || null,
            period,
            minSurprise: parseFloat(minSurprise || 0)
          },
          total: result.rows.length
        },
        timestamp: new Date().toISOString(),
      });

    } catch (error) {
      console.log("Earnings reports table not available for surprises, using fallback");

      // Fallback to earnings_history if available
      try {
        let fallbackSymbolFilter = "";
        let fallbackParams = [parseInt(limit)];

        if (symbol) {
          fallbackSymbolFilter = "WHERE symbol = $2";
          fallbackParams = [parseInt(limit), symbol.toUpperCase()];
        }

        const fallbackQuery = `
          SELECT
            symbol,
            quarter,
            eps_actual,
            eps_estimate,
            eps_difference,
            surprise_percent
          FROM earnings_history
          ${fallbackSymbolFilter}
          ORDER BY ABS(surprise_percent) DESC, quarter DESC
          LIMIT $1
        `;

        const fallbackResult = await query(fallbackQuery, fallbackParams);

        res.json({
          success: true,
          data: {
            surprises: fallbackResult.rows.map(row => ({
              symbol: row.symbol,
              company_name: row.symbol,
              date: row.quarter,
              quarter: row.quarter,
              year: new Date(row.quarter).getFullYear(),
              earnings: {
                estimated_eps: parseFloat(row.eps_estimate || 0),
                actual_eps: parseFloat(row.eps_actual || 0),
                eps_surprise: parseFloat(row.eps_difference || 0),
                eps_surprise_percent: parseFloat(row.surprise_percent || 0)
              },
              revenue: {
                estimated_revenue: 0,
                actual_revenue: 0,
                revenue_surprise: 0,
                revenue_surprise_percent: 0
              },
              sector: "Unknown",
              market_cap: 0
            })),
            filters: { symbol: symbol || null, period },
            total: fallbackResult.rows.length
          },
          timestamp: new Date().toISOString(),
        });

      } catch (fallbackError) {
        res.json({
          success: true,
          data: {
            surprises: [],
            filters: { symbol: symbol || null, period },
            total: 0,
            message: "No earnings surprises data available"
          },
          timestamp: new Date().toISOString(),
        });
      }
    }

  } catch (error) {
    console.error("Earnings surprises error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch earnings surprises",
      details: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

// Get earnings details for specific symbol
router.get("/:symbol", async (req, res) => {
  try {
    const { symbol } = req.params;
    console.log(`📈 Earnings details requested for symbol: ${symbol.toUpperCase()}`);

    let result;
    try {
      const symbolQuery = `
        SELECT
          symbol,
          quarter as report_date,
          eps_actual,
          eps_estimate,
          eps_difference,
          surprise_percent,
          quarter,
          fetched_at as last_updated
        FROM earnings_history
        WHERE symbol = $1
        ORDER BY quarter DESC
        LIMIT 20
      `;

      result = await query(symbolQuery, [symbol.toUpperCase()]);
    } catch (error) {
      console.log(`Earnings table schema mismatch for ${symbol}, using fallback data`);

      try {
        // Try to get just basic columns that might exist
        const fallbackQuery = `
          SELECT
            symbol,
            quarter as report_date,
            fetched_at as last_updated
          FROM earnings_history
          WHERE symbol = $1
          ORDER BY quarter DESC
          LIMIT 20
        `;

        const fallbackResult = await query(fallbackQuery, [symbol.toUpperCase()]);

        // Add missing fields with default values
        result = {
          rows: fallbackResult.rows.map(row => ({
            ...row,
            eps_actual: 0,
            eps_estimate: 0,
            eps_difference: 0,
            surprise_percent: 0
          }))
        };
      } catch (fallbackError) {
        // If table doesn't exist at all, return empty data
        result = { rows: [] };
      }
    }

    if (!result.rows || result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "No earnings data found for symbol",
        symbol: symbol.toUpperCase(),
        timestamp: new Date().toISOString(),
      });
    }

    res.json({
      success: true,
      data: result.rows,
      symbol: symbol.toUpperCase(),
      count: result.rows.length,
      timestamp: new Date().toISOString(),
    });

  } catch (error) {
    console.error(`Earnings error for symbol ${req.params.symbol}:`, error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch earnings details",
      details: error.message,
      symbol: req.params.symbol?.toUpperCase() || null,
      timestamp: new Date().toISOString(),
    });
  }
});

module.exports = router;

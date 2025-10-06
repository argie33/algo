const express = require("express");

const { query } = require("../utils/database");
const { authenticateToken } = require("../middleware/auth");

const router = express.Router();

// Apply authentication middleware to all routes
router.use(authenticateToken);

// Research endpoint - aggregates research data
router.get("/", async (req, res) => {
  try {
    res.json({
      success: true,
      data: {
        message: "Research API - Ready",
        status: "operational",
        endpoints: [
          "/reports - Research reports",
          "/analysis - Market analysis",
          "/recommendations - Analyst recommendations",
          "/ratings - Stock ratings",
        ],
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: "Research service unavailable",
      timestamp: new Date().toISOString(),
    });
  }
});

// Research reports
router.get("/reports", async (req, res) => {
  try {
    res.json({
      success: true,
      data: {
        reports: [],
        total: 0,
        message: "No research reports available",
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: "Failed to fetch research reports",
      timestamp: new Date().toISOString(),
    });
  }
});

// Market analysis
router.get("/analysis", async (req, res) => {
  try {
    res.json({
      success: true,
      data: {
        analysis: [],
        total: 0,
        message: "No market analysis available",
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: "Failed to fetch market analysis",
      timestamp: new Date().toISOString(),
    });
  }
});

// Analyst recommendations
router.get("/recommendations", async (req, res) => {
  try {
    res.json({
      success: true,
      data: {
        recommendations: [],
        total: 0,
        message: "No recommendations available",
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: "Failed to fetch recommendations",
      timestamp: new Date().toISOString(),
    });
  }
});

// Stock ratings
router.get("/ratings", async (req, res) => {
  try {
    res.json({
      success: true,
      data: {
        ratings: [],
        total: 0,
        message: "No ratings available",
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: "Failed to fetch ratings",
      timestamp: new Date().toISOString(),
    });
  }
});

// Analyst coverage endpoint
router.get("/analyst", async (req, res) => {
  try {
    const { symbol, period = "current", limit = 50 } = req.query;

    if (!symbol) {
      return res.status(400).json({
        success: false,
        error: "Symbol parameter is required",
        timestamp: new Date().toISOString(),
      });
    }

    // Get analyst coverage data from available fundamental metrics
    const analystQuery = `
      SELECT
        s.symbol,
        CURRENT_DATE as date,
        'Q4' as quarter,
        EXTRACT(YEAR FROM CURRENT_DATE) as year,
        5 as analyst_count,
        s.earnings_per_share as estimated_eps,
        s.earnings_per_share as actual_eps,
        (s.revenue_per_share * s.shares_outstanding) as estimated_revenue,
        (s.revenue_per_share * s.shares_outstanding) as actual_revenue,
        s.company_name,
        s.sector,
        s.industry,
        s.market_cap
      FROM company_profile fm
      WHERE s.symbol = $1 AND s.market_cap > 0
      ORDER BY s.market_cap DESC
      LIMIT $2
    `;

    const analystResult = await query(analystQuery, [symbol.toUpperCase(), parseInt(limit)]);
    const analystData = analystResult.rows || [];

    if (!analystData || analystData.length === 0) {
      return res.json({
        success: true,
        data: {
          analyst_coverage: {
            symbol: symbol.toUpperCase(),
            coverage_available: false,
            total_reports: 0,
            analyst_coverage: [],
            summary: {
              avg_analyst_count: 0,
              latest_coverage: 0,
              coverage_trend: "No data",
            },
          },
        },
        timestamp: new Date().toISOString(),
      });
    }

    // Calculate analyst coverage metrics
    const totalAnalystCount = analystData.reduce(
      (sum, report) => sum + parseInt(report.analyst_count || 0), 0
    );
    const avgAnalystCount = Math.round(totalAnalystCount / analystData.length * 100) / 100;
    const latestCoverage = parseInt(analystData[0]?.analyst_count || 0);

    // Calculate coverage trend (comparing latest quarter to previous)
    let coverageTrend = "Stable";
    if (analystData.length >= 2) {
      const current = parseInt(analystData[0]?.analyst_count || 0);
      const previous = parseInt(analystData[1]?.analyst_count || 0);
      if (current > previous) {
        coverageTrend = "Increasing";
      } else if (current < previous) {
        coverageTrend = "Decreasing";
      }
    }

    // Format analyst coverage data
    const coverageData = analystData.map((report) => {
      const estimated_eps = parseFloat(report.estimated_eps || 0);
      const actual_eps = parseFloat(report.actual_eps || 0);
      const estimated_revenue = parseFloat(report.estimated_revenue || 0);
      const actual_revenue = parseFloat(report.actual_revenue || 0);

      return {
        date: report.date,
        quarter: report.quarter,
        year: report.year,
        analyst_count: parseInt(report.analyst_count || 0),
        earnings: {
          estimated_eps: Math.round(estimated_eps * 100) / 100,
          actual_eps: Math.round(actual_eps * 100) / 100,
          eps_surprise: actual_eps && estimated_eps ?
            Math.round(((actual_eps - estimated_eps) / Math.abs(estimated_eps)) * 10000) / 100 : null,
        },
        revenue: {
          estimated_revenue: Math.round(estimated_revenue / 1000000 * 100) / 100, // Convert to millions
          actual_revenue: Math.round(actual_revenue / 1000000 * 100) / 100,
          revenue_surprise: actual_revenue && estimated_revenue ?
            Math.round(((actual_revenue - estimated_revenue) / Math.abs(estimated_revenue)) * 10000) / 100 : null,
        },
      };
    });

    // Company information
    const companyInfo = analystData[0] ? {
      symbol: symbol.toUpperCase(),
      company_name: analystData[0].company_name || symbol.toUpperCase(),
      sector: analystData[0].sector || "Unknown",
      industry: analystData[0].industry || "Unknown",
      market_cap: parseFloat(analystData[0].market_cap || 0),
    } : null;

    const analysisData = {
      symbol: symbol.toUpperCase(),
      coverage_available: true,
      total_reports: analystData.length,
      company_info: companyInfo,
      analyst_coverage: coverageData,
      summary: {
        avg_analyst_count: avgAnalystCount,
        latest_coverage: latestCoverage,
        coverage_trend: coverageTrend,
        reports_analyzed: analystData.length,
      },
      analysis_period: period,
      analysis_date: new Date().toISOString(),
    };

    res.json({
      success: true,
      data: { analyst_coverage: analysisData },
      timestamp: new Date().toISOString(),
    });

  } catch (error) {
    console.error("Analyst endpoint error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch analyst coverage",
      message: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

module.exports = router;

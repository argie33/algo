const express = require("express");

const router = express.Router();
const { authenticateToken } = require("../middleware/auth");
const { query } = require("../utils/database");
const RiskEngine = require("../utils/riskEngine");

// Health endpoint (no auth required)
router.get("/health", (req, res) => {
  res.success({status: "operational",
    service: "risk-analysis",
    timestamp: new Date().toISOString(),
    message: "Risk Analysis service is running",
  });
});

// Basic root endpoint (public)
router.get("/", (req, res) => {
  res.success({message: "Risk Analysis API - Ready",
    timestamp: new Date().toISOString(),
    status: "operational",
  });
});

// Apply authentication to all routes
router.use(authenticateToken);

// Initialize risk engine
const riskEngine = new RiskEngine();

// Get portfolio risk metrics
router.get("/portfolio/:portfolioId", async (req, res) => {
  try {
    const { portfolioId } = req.params;
    const { timeframe = "1Y", confidence_level = 0.95 } = req.query;
    const userId = req.user.sub;

    // Verify portfolio ownership
    const portfolioResult = await query(
      `
      SELECT id FROM portfolios 
      WHERE id = $1 AND user_id = $2
    `,
      [portfolioId, userId]
    );

    if (portfolioResult.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "Portfolio not found",
      });
    }

    const riskMetrics = await riskEngine.calculatePortfolioRisk(
      portfolioId,
      timeframe,
      parseFloat(confidence_level)
    );

    res.success({data: riskMetrics,
    });
  } catch (error) {
    console.error("Error calculating portfolio risk:", error);
    res.status(500).json({
      success: false,
      error: "Failed to calculate portfolio risk",
      message: error.message,
    });
  }
});

// Get Value at Risk (VaR) analysis
router.get("/var/:portfolioId", async (req, res) => {
  try {
    const { portfolioId } = req.params;
    const {
      method = "historical",
      confidence_level = 0.95,
      time_horizon = 1,
      lookback_days = 252,
    } = req.query;
    const userId = req.user.sub;

    // Verify portfolio ownership
    const portfolioResult = await query(
      `
      SELECT id FROM portfolios 
      WHERE id = $1 AND user_id = $2
    `,
      [portfolioId, userId]
    );

    if (portfolioResult.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "Portfolio not found",
      });
    }

    const varAnalysis = await riskEngine.calculateVaR(
      portfolioId,
      method,
      parseFloat(confidence_level),
      parseInt(time_horizon),
      parseInt(lookback_days)
    );

    res.success({data: varAnalysis,
    });
  } catch (error) {
    console.error("Error calculating VaR:", error);
    res.status(500).json({
      success: false,
      error: "Failed to calculate VaR",
      message: error.message,
    });
  }
});

// Get stress testing results
router.post("/stress-test/:portfolioId", async (req, res) => {
  try {
    const { portfolioId } = req.params;
    const {
      scenarios = [],
      shock_magnitude = 0.1,
      correlation_adjustment = false,
    } = req.body;
    const userId = req.user.sub;

    // Verify portfolio ownership
    const portfolioResult = await query(
      `
      SELECT id FROM portfolios 
      WHERE id = $1 AND user_id = $2
    `,
      [portfolioId, userId]
    );

    if (portfolioResult.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "Portfolio not found",
      });
    }

    const stressTestResults = await riskEngine.performStressTest(
      portfolioId,
      scenarios,
      shock_magnitude,
      correlation_adjustment
    );

    res.success({data: stressTestResults,
    });
  } catch (error) {
    console.error("Error performing stress test:", error);
    res.status(500).json({
      success: false,
      error: "Failed to perform stress test",
      message: error.message,
    });
  }
});

// Get risk alerts
router.get("/alerts", async (req, res) => {
  try {
    const {
      severity = "all",
      status = "active",
      limit = 50,
      offset = 0,
    } = req.query;
    const userId = req.user.sub;

    let whereClause = "WHERE ra.user_id = $1";
    const params = [userId];
    let paramIndex = 2;

    if (severity !== "all") {
      whereClause += ` AND ra.severity = $${paramIndex}`;
      params.push(severity);
      paramIndex++;
    }

    if (status !== "all") {
      whereClause += ` AND ra.status = $${paramIndex}`;
      params.push(status);
      paramIndex++;
    }

    const result = await query(
      `
      SELECT 
        ra.id,
        ra.alert_type,
        ra.severity,
        ra.title,
        ra.description,
        ra.metric_name,
        ra.current_value,
        ra.threshold_value,
        ra.portfolio_id,
        ra.symbol,
        ra.created_at,
        ra.updated_at,
        ra.status,
        ra.acknowledged_at,
        p.name as portfolio_name
      FROM risk_alerts ra
      LEFT JOIN portfolios p ON ra.portfolio_id = p.id
      ${whereClause}
      ORDER BY ra.created_at DESC
      LIMIT $${paramIndex} OFFSET $${paramIndex + 1}
    `,
      [...params, parseInt(limit), parseInt(offset)]
    );

    // Get total count
    const countResult = await query(
      `
      SELECT COUNT(*) as total
      FROM risk_alerts ra
      ${whereClause}
    `,
      params
    );

    res.success({data: {
        alerts: result.rows,
        total: parseInt(countResult.rows[0].total),
        limit: parseInt(limit),
        offset: parseInt(offset),
      },
    });
  } catch (error) {
    console.error("Error fetching risk alerts:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch risk alerts",
      message: error.message,
    });
  }
});

// Acknowledge risk alert
router.put("/alerts/:alertId/acknowledge", async (req, res) => {
  try {
    const { alertId } = req.params;
    const userId = req.user.sub;

    // Verify alert ownership
    const alertResult = await query(
      `
      SELECT id FROM risk_alerts 
      WHERE id = $1 AND user_id = $2
    `,
      [alertId, userId]
    );

    if (alertResult.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "Alert not found",
      });
    }

    await query(
      `
      UPDATE risk_alerts 
      SET status = 'acknowledged', acknowledged_at = CURRENT_TIMESTAMP
      WHERE id = $1
    `,
      [alertId]
    );

    res.success({message: "Alert acknowledged successfully",
    });
  } catch (error) {
    console.error("Error acknowledging alert:", error);
    res.status(500).json({
      success: false,
      error: "Failed to acknowledge alert",
      message: error.message,
    });
  }
});

// Get correlation matrix
router.get("/correlation/:portfolioId", async (req, res) => {
  try {
    const { portfolioId } = req.params;
    const { lookback_days = 252 } = req.query;
    const userId = req.user.sub;

    // Verify portfolio ownership
    const portfolioResult = await query(
      `
      SELECT id FROM portfolios 
      WHERE id = $1 AND user_id = $2
    `,
      [portfolioId, userId]
    );

    if (portfolioResult.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "Portfolio not found",
      });
    }

    const correlationMatrix = await riskEngine.calculateCorrelationMatrix(
      portfolioId,
      parseInt(lookback_days)
    );

    res.success({data: correlationMatrix,
    });
  } catch (error) {
    console.error("Error calculating correlation matrix:", error);
    res.status(500).json({
      success: false,
      error: "Failed to calculate correlation matrix",
      message: error.message,
    });
  }
});

// Get risk attribution analysis
router.get("/attribution/:portfolioId", async (req, res) => {
  try {
    const { portfolioId } = req.params;
    const { attribution_type = "factor" } = req.query;
    const userId = req.user.sub;

    // Verify portfolio ownership
    const portfolioResult = await query(
      `
      SELECT id FROM portfolios 
      WHERE id = $1 AND user_id = $2
    `,
      [portfolioId, userId]
    );

    if (portfolioResult.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "Portfolio not found",
      });
    }

    const attribution = await riskEngine.calculateRiskAttribution(
      portfolioId,
      attribution_type
    );

    res.success({data: attribution,
    });
  } catch (error) {
    console.error("Error calculating risk attribution:", error);
    res.status(500).json({
      success: false,
      error: "Failed to calculate risk attribution",
      message: error.message,
    });
  }
});

// Get risk limits and thresholds
router.get("/limits/:portfolioId", async (req, res) => {
  try {
    const { portfolioId } = req.params;
    const userId = req.user.sub;

    // Verify portfolio ownership
    const portfolioResult = await query(
      `
      SELECT id FROM portfolios 
      WHERE id = $1 AND user_id = $2
    `,
      [portfolioId, userId]
    );

    if (portfolioResult.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "Portfolio not found",
      });
    }

    const limitsResult = await query(
      `
      SELECT 
        id,
        metric_name,
        threshold_value,
        warning_threshold,
        threshold_type,
        is_active,
        created_at,
        updated_at
      FROM risk_limits
      WHERE portfolio_id = $1
      ORDER BY metric_name
    `,
      [portfolioId]
    );

    res.success({data: {
        limits: limitsResult.rows,
        portfolio_id: portfolioId,
      },
    });
  } catch (error) {
    console.error("Error fetching risk limits:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch risk limits",
      message: error.message,
    });
  }
});

// Update risk limits
router.put("/limits/:portfolioId", async (req, res) => {
  try {
    const { portfolioId } = req.params;
    const { limits } = req.body;
    const userId = req.user.sub;

    // Verify portfolio ownership
    const portfolioResult = await query(
      `
      SELECT id FROM portfolios 
      WHERE id = $1 AND user_id = $2
    `,
      [portfolioId, userId]
    );

    if (portfolioResult.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "Portfolio not found",
      });
    }

    // Update each limit
    for (const limit of limits) {
      await query(
        `
        INSERT INTO risk_limits (
          portfolio_id, metric_name, threshold_value, warning_threshold,
          threshold_type, is_active, updated_at
        ) VALUES ($1, $2, $3, $4, $5, $6, CURRENT_TIMESTAMP)
        ON CONFLICT (portfolio_id, metric_name) DO UPDATE SET
          threshold_value = EXCLUDED.threshold_value,
          warning_threshold = EXCLUDED.warning_threshold,
          threshold_type = EXCLUDED.threshold_type,
          is_active = EXCLUDED.is_active,
          updated_at = CURRENT_TIMESTAMP
      `,
        [
          portfolioId,
          limit.metric_name,
          limit.threshold_value,
          limit.warning_threshold,
          limit.threshold_type,
          limit.is_active,
        ]
      );
    }

    res.success({message: "Risk limits updated successfully",
    });
  } catch (error) {
    console.error("Error updating risk limits:", error);
    res.status(500).json({
      success: false,
      error: "Failed to update risk limits",
      message: error.message,
    });
  }
});

// Get risk dashboard summary
router.get("/dashboard", async (req, res) => {
  try {
    const userId = req.user.sub;

    // Get portfolio risk summary
    const portfolioRiskResult = await query(
      `
      SELECT 
        p.id,
        p.name,
        p.total_value,
        prm.var_95,
        prm.var_99,
        prm.expected_shortfall,
        prm.volatility,
        prm.beta,
        prm.sharpe_ratio,
        prm.max_drawdown,
        prm.calculated_at
      FROM portfolios p
      LEFT JOIN portfolio_risk_metrics prm ON p.id = prm.portfolio_id
      WHERE p.user_id = $1
      ORDER BY p.created_at DESC
    `,
      [userId]
    );

    // Get active risk alerts count
    const alertsResult = await query(
      `
      SELECT 
        severity,
        COUNT(*) as count
      FROM risk_alerts
      WHERE user_id = $1 AND status = 'active'
      GROUP BY severity
    `,
      [userId]
    );

    // Get market risk indicators
    const marketRiskResult = await query(`
      SELECT 
        indicator_name,
        current_value,
        risk_level,
        last_updated
      FROM market_risk_indicators
      WHERE last_updated >= CURRENT_DATE
      ORDER BY risk_level DESC
    `);

    const alertCounts = alertsResult.rows.reduce(
      (acc, row) => {
        acc[row.severity] = parseInt(row.count);
        return acc;
      },
      { high: 0, medium: 0, low: 0 }
    );

    res.success({data: {
        portfolios: portfolioRiskResult.rows,
        alert_counts: alertCounts,
        market_indicators: marketRiskResult.rows,
        summary: {
          total_portfolios: portfolioRiskResult.rows.length,
          total_alerts: alertsResult.rows.reduce(
            (sum, row) => sum + parseInt(row.count),
            0
          ),
          high_risk_portfolios: portfolioRiskResult.rows.filter(
            (p) => p.var_95 > 0.05
          ).length,
        },
      },
    });
  } catch (error) {
    console.error("Error fetching risk dashboard:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch risk dashboard",
      message: error.message,
    });
  }
});

// Start real-time risk monitoring
router.post("/monitoring/start", async (req, res) => {
  try {
    const { portfolio_ids = [], check_interval = 300000 } = req.body; // 5 minutes default
    const userId = req.user.sub;

    // Verify portfolio ownership
    if (portfolio_ids.length > 0) {
      const portfolioResult = await query(
        `
        SELECT id FROM portfolios 
        WHERE id = ANY($1) AND user_id = $2
      `,
        [portfolio_ids, userId]
      );

      if (portfolioResult.rows.length !== portfolio_ids.length) {
        return res.status(400).json({
          success: false,
          error: "One or more portfolios not found",
        });
      }
    }

    // Start monitoring for user's portfolios
    const monitoringResult = await riskEngine.startRealTimeMonitoring(
      userId,
      portfolio_ids,
      check_interval
    );

    res.success({data: monitoringResult,
    });
  } catch (error) {
    console.error("Error starting risk monitoring:", error);
    res.status(500).json({
      success: false,
      error: "Failed to start risk monitoring",
      message: error.message,
    });
  }
});

// Stop real-time risk monitoring
router.post("/monitoring/stop", async (req, res) => {
  try {
    const userId = req.user.sub;

    const result = await riskEngine.stopRealTimeMonitoring(userId);

    res.success({data: result,
    });
  } catch (error) {
    console.error("Error stopping risk monitoring:", error);
    res.status(500).json({
      success: false,
      error: "Failed to stop risk monitoring",
      message: error.message,
    });
  }
});

// Get monitoring status
router.get("/monitoring/status", async (req, res) => {
  try {
    const userId = req.user.sub;

    const status = await riskEngine.getMonitoringStatus(userId);

    res.success({data: status,
    });
  } catch (error) {
    console.error("Error fetching monitoring status:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch monitoring status",
      message: error.message,
    });
  }
});

module.exports = router;

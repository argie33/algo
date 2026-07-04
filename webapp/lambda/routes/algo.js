/**
 * Swing Trading Algo API Routes
 *
 * Endpoints:
 * - GET /api/algo/status - Current algo status
 * - GET /api/algo/evaluate - Run signal evaluation
 * - GET /api/algo/positions - Get active positions
 * - GET /api/algo/trades - Get trade history
 * - GET /api/algo/config - Get current configuration
 * - POST /api/algo/config/:key - Update configuration (admin only)
 */

const express = require("express");

const { getPool, ensureConnection } = require("../utils/database");
const { authenticateToken, requireAdmin } = require("../middleware/auth");
const {
  sendSuccess,
  sendError,
  sendDatabaseError,
} = require("../utils/apiResponse");
const paginationConfig = require("../config/pagination");
const logger = require("../utils/logger");
const {
  validateQueryResult,
  validateAndCoerceRow,
  validateAndCoerceRows,
  extractCount,
} = require("../utils/responseValidation");
const { getActiveTiers, getActiveTier } = require("../utils/tiers");
const { getSwingGrades, getGradeForScore } = require("../utils/grades");
const {
  requireNumericField,
  requirePrice,
  requirePortfolioValue,
  requireSignalQuality,
  requireExposure,
  requirePositionCount,
  requireUnrealizedPnl,
  isDataError
} = require("../utils/strictValidation");
const {
  createErrorResponse,
  createPartialResponse,
  isDataError: isDataErrorEnvelope,
  collectErrors
} = require("../utils/errorEnvelopes");

const router = express.Router();

const requireAuth = authenticateToken;

/**
 * ISSUE #5: Helper function to compute stage_label from Weinstein stage and Minervini score.
 * Centralizes stage labeling logic to eliminate duplication.
 */
function computeStageLabel(stage, score, stageConfig = {}) {
  if (stage === 1) {
    return "Stage 1 (base)";
  } else if (stage === 2) {
    if (score != null) {
      if (stageConfig.stage_2_late_min_score == null) {
        throw new Error('Missing required config: stage_2_late_min_score');
      }
      if (stageConfig.stage_2_mid_min_score == null) {
        throw new Error('Missing required config: stage_2_mid_min_score');
      }
      if (stageConfig.stage_2_early_min_score == null) {
        throw new Error('Missing required config: stage_2_early_min_score');
      }
      if (score >= stageConfig.stage_2_late_min_score)
        return "Late Stage-2";
      if (score >= stageConfig.stage_2_mid_min_score)
        return "Mid Stage-2";
      if (score >= stageConfig.stage_2_early_min_score)
        return "Early Stage-2";
      return "Early Stage-2";
    }
    return "Stage 2";
  } else if (stage === 3) {
    return "Stage 3 (top)";
  } else if (stage === 4) {
    return "Stage 4 (down)";
  }
  return "Unknown";
}

/**
 * GET /api/algo/status
 * Current algo system status
 */
router.get("/status", async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();

    // Parallelize all 4 independent queries
    const [snapshotResult, posResult, healthResult, configResult] =
      await Promise.all([
        pool.query(`
        SELECT
          snapshot_date,
          total_portfolio_value,
          position_count,
          unrealized_pnl_pct,
          daily_return_pct
        FROM algo_portfolio_snapshots
        ORDER BY snapshot_date DESC
        LIMIT 1
      `),
        pool.query(`
        SELECT COUNT(*) as open_count, SUM(position_value) as total_value
        FROM algo_positions
        WHERE status = 'open'
      `),
        pool.query(`
        SELECT market_trend, market_stage, distribution_days_4w, vix_level
        FROM market_health_daily
        ORDER BY date DESC
        LIMIT 1
      `),
        pool.query(`
        SELECT key, value FROM algo_config
        WHERE key IN ('enable_algo', 'execution_mode')
      `),
      ]);

    // Validate result structures
    validateQueryResult(snapshotResult, { requireRows: false });
    validateQueryResult(posResult, { requireRows: false });
    validateQueryResult(healthResult, { requireRows: false });
    validateQueryResult(configResult, { requireRows: false });

    if (!snapshotResult.rows[0]) {
      return sendError(
        res,
        503,
        "CRITICAL: Portfolio snapshot unavailable. " +
          "Cannot display algorithm status without current portfolio metrics. " +
          "Check algo_portfolio_snapshots table for data availability."
      );
    }
    const snapshot = validateAndCoerceRow(snapshotResult.rows[0], {
      position_count: { type: "int", required: true },
      unrealized_pnl_pct: { type: "float", required: true },
      daily_return_pct: { type: "float", required: true },
      total_portfolio_value: { type: "float", required: true },
    });

    if (!posResult.rows[0]) {
      return sendError(
        res,
        503,
        "CRITICAL: Position aggregation unavailable. " +
          "Cannot compute portfolio state without open position data. " +
          "Check algo_positions table for open position records."
      );
    }
    const positions = validateAndCoerceRow(posResult.rows[0], {
      open_count: { type: "int", required: true },
      total_value: { type: "float", required: true },
    });

    if (!healthResult.rows[0]) {
      return sendError(
        res,
        503,
        "CRITICAL: Market health data unavailable. " +
          "Cannot evaluate market regime without current VIX, breadth, and yield curve data. " +
          "Check market_health_daily table for latest market metrics."
      );
    }
    const health = validateAndCoerceRow(healthResult.rows[0], {
      market_trend: { type: "string", required: true },
      market_stage: { type: "int", required: true },
      distribution_days_4w: { type: "int", required: true },
      vix_level: { type: "float", required: true },
    });

    let algo_enabled = true;
    let execution_mode = "paper";

    validateAndCoerceRows(configResult, {
      key: { type: "string", required: true },
      value: { type: "string", required: true },
    }).forEach((row) => {
      if (row.key === "enable_algo") {
        algo_enabled = row.value.toLowerCase() === "true";
      } else if (row.key === "execution_mode") {
        execution_mode = row.value;
      }
    });

    // Validate critical portfolio metrics - cannot use defaults
    const totalValueValidation = requirePortfolioValue(snapshot?.total_portfolio_value);
    const unrealizedPnlValidation = requireUnrealizedPnl(snapshot?.unrealized_pnl_pct);

    if (isDataError(totalValueValidation) || isDataError(unrealizedPnlValidation)) {
      const errors = [totalValueValidation, unrealizedPnlValidation].filter(isDataError);
      return sendSuccess(res, createErrorResponse(errors));
    }

    const totalValue = totalValueValidation;
    const unrealizedPnlPct = unrealizedPnlValidation;
    const unrealizedPnlDollars = (totalValue * unrealizedPnlPct) / 100;

    const positionCountValidation = requirePositionCount(positions?.open_count);
    const positionValueValidation = requireNumericField(positions?.total_value, 'total_position_value');

    const errors = [positionCountValidation, positionValueValidation].filter(isDataError);
    if (errors.length > 0) {
      return sendSuccess(res, createPartialResponse({
        algo_enabled,
        execution_mode,
        status: "operational",
        portfolio: {
          total_value: totalValue,
          position_count: isDataError(positionCountValidation) ? null : positionCountValidation,
          total_position_value: isDataError(positionValueValidation) ? null : positionValueValidation,
          unrealized_pnl_pct: unrealizedPnlPct,
          unrealized_pnl_dollars: Number(unrealizedPnlDollars.toFixed(2)),
        }
      }, errors));
    }

    const positionCount = positionCountValidation;
    const positionValue = positionValueValidation;

    return sendSuccess(res, {
      algo_enabled: algo_enabled,
      execution_mode: execution_mode,
      status: "operational",
      portfolio: {
        total_value: totalValue,
        position_count: positionCount,
        total_position_value: positionValue,
        unrealized_pnl_pct: unrealizedPnlPct,
        unrealized_pnl_dollars: Number(unrealizedPnlDollars.toFixed(2)),
        daily_return_pct: snapshot?.daily_return_pct,
      },
      market: {
        trend: health?.market_trend,
        stage: health?.market_stage,
        distribution_days: health?.distribution_days_4w,
        vix: health?.vix_level,
      },
    });
  } catch (error) {
    logger.error("Error in /algo/status:", {
      error: error.message,
      stack: error.stack,
    });
    return sendDatabaseError(
      res,
      error,
      "An error occurred while fetching algorithm status"
    );
  }
});

/**
 * GET /api/algo/evaluate
 * Run signal evaluation (latest date with buy signals)
 */
router.get("/evaluate", async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();

    // OPTIMIZED: Single batch query instead of N+1 pattern
    // Was: 150 round-trips (1 initial query + 3 queries Ã— 50 signals)
    // Now: 1 query with CTEs joining all scoring data
    const result = await pool.query(`
      WITH latest_signals AS (
        SELECT symbol, date, signal
        FROM buy_sell_daily
        WHERE signal = 'BUY'
        ORDER BY date DESC, symbol
        LIMIT 50
      ),
      latest_trend AS (
        SELECT DISTINCT ON (symbol)
          symbol, minervini_trend_score,
          percent_from_52w_low, percent_from_52w_high
        FROM trend_template_data
        ORDER BY symbol, date DESC
      ),
      latest_completeness AS (
        SELECT symbol, composite_completeness_pct
        FROM data_completeness_scores
      ),
      latest_sqs AS (
        SELECT DISTINCT ON (symbol)
          symbol, composite_sqs
        FROM signal_quality_scores
        ORDER BY symbol, date DESC
      )
      SELECT
        s.symbol, s.date,
        tt.minervini_trend_score::int as trend_score,
        tt.percent_from_52w_low::numeric as pct_from_52w_low,
        dc.composite_completeness_pct::numeric as completeness_pct,
        sq.composite_sqs::int as sqs
      FROM latest_signals s
      INNER JOIN latest_trend tt ON tt.symbol = s.symbol
      INNER JOIN latest_completeness dc ON dc.symbol = s.symbol
      INNER JOIN latest_sqs sq ON sq.symbol = s.symbol
      ORDER BY s.date DESC, s.symbol
    `);

    // Validate result structure
    validateQueryResult(result, { requireRows: false });

    // PHASE 2: Load signal filter configuration from database (migration 003_signal_filter_tiers.sql)
    const filterConfigResult = await pool.query(`
      SELECT
        completeness_pct_min, trend_score_min, sqs_min,
        require_all_tiers, max_qualified_signals,
        sort_by, sort_order
      FROM signal_filter_tiers
      WHERE is_active = TRUE
      ORDER BY version DESC
      LIMIT 1
    `);

    validateQueryResult(filterConfigResult, { requireRows: false });

    // CRITICAL: Signal filter thresholds must come from database. Hardcoded defaults would
    // mask configuration issues and allow trading with unvalidated filter rules.
    if (!filterConfigResult.rows || filterConfigResult.rows.length === 0) {
      return sendError(
        res,
        503,
        "CRITICAL: Signal filter configuration unavailable. " +
          "Cannot evaluate signals without configured completeness/trend/quality thresholds. " +
          "Check signal_filter_tiers table for active configuration."
      );
    }

    const cfg = filterConfigResult.rows[0];
    // Validate all required fields exist with non-null values
    if (
      cfg.completeness_pct_min === null || cfg.completeness_pct_min === undefined ||
      cfg.trend_score_min === null || cfg.trend_score_min === undefined ||
      cfg.sqs_min === null || cfg.sqs_min === undefined ||
      cfg.max_qualified_signals === null || cfg.max_qualified_signals === undefined ||
      cfg.sort_by === null || cfg.sort_by === undefined ||
      cfg.sort_order === null || cfg.sort_order === undefined
    ) {
      return sendError(
        res,
        503,
        "CRITICAL: Signal filter configuration incomplete. " +
          "Missing required threshold fields in signal_filter_tiers. " +
          "All fields (completeness_pct_min, trend_score_min, sqs_min, max_qualified_signals, sort_by, sort_order) must be configured."
      );
    }

    // Parse and validate numeric values
    const completenessVal = parseFloat(cfg.completeness_pct_min);
    const trendVal = parseInt(cfg.trend_score_min, 10);
    const sqsVal = parseInt(cfg.sqs_min, 10);
    const maxSignalsVal = parseInt(cfg.max_qualified_signals, 10);

    if (isNaN(completenessVal) || isNaN(trendVal) || isNaN(sqsVal) || isNaN(maxSignalsVal)) {
      return sendError(
        res,
        503,
        "CRITICAL: Signal filter configuration has invalid data types. " +
          "Completeness, trend, SQS, and max_signals must be numeric values. " +
          "Check signal_filter_tiers for corrupted data."
      );
    }

    const filterConfig = {
      completeness_pct_min: completenessVal,
      trend_score_min: trendVal,
      sqs_min: sqsVal,
      require_all_tiers: cfg.require_all_tiers !== false,
      max_qualified_signals: maxSignalsVal,
      sort_by: String(cfg.sort_by).toLowerCase(),
      sort_order: String(cfg.sort_order).toUpperCase(),
    };

    // Transform into evaluation objects with database-driven thresholds
    // NOTE: Removed defaultValue: 0 for signal quality metrics - missing data must be visible
    const evaluated = validateAndCoerceRows(result, {
      symbol: { type: "string", required: true },
      date: { type: "date", required: true },
      trend_score: { type: "int", required: false },
      pct_from_52w_low: { type: "float", required: false },
      completeness_pct: { type: "float", required: false },
      sqs: { type: "int", required: false },
    }).map((row) => {
      const tier1 = row.completeness_pct !== null && row.completeness_pct !== undefined ? row.completeness_pct >= filterConfig.completeness_pct_min : false;
      const tier3 = row.trend_score !== null && row.trend_score !== undefined ? row.trend_score >= filterConfig.trend_score_min : false;
      const tier4 = row.sqs !== null && row.sqs !== undefined ? row.sqs >= filterConfig.sqs_min : false;

      const all_tiers_pass = filterConfig.require_all_tiers
        ? tier1 && tier3 && tier4
        : tier1 || tier3 || tier4;

      return {
        symbol: row.symbol,
        date: row.date,
        trend_score: row.trend_score,
        pct_from_52w_low: row.pct_from_52w_low,
        completeness_pct: row.completeness_pct,
        sqs: row.sqs,
        tier1_pass: tier1,
        tier3_pass: tier3,
        tier4_pass: tier4,
        all_tiers_pass: all_tiers_pass,
      };
    });

    // Filter to qualified and sort by configured field/direction
    // CRITICAL: Fail-fast on null/undefined sort metrics — defaulting to 0 masks missing data quality issues
    const sortComparator = (a, b) => {
      if (a[filterConfig.sort_by] === null || a[filterConfig.sort_by] === undefined) {
        throw new Error(
          `CRITICAL: Symbol ${a.symbol} missing sort field '${filterConfig.sort_by}'. ` +
          `Cannot rank signals without complete data. ` +
          `Check signal completeness_pct and signal_quality_scores data.`
        );
      }
      if (b[filterConfig.sort_by] === null || b[filterConfig.sort_by] === undefined) {
        throw new Error(
          `CRITICAL: Symbol ${b.symbol} missing sort field '${filterConfig.sort_by}'. ` +
          `Cannot rank signals without complete data. ` +
          `Check signal completeness_pct and signal_quality_scores data.`
        );
      }
      const aVal = parseFloat(a[filterConfig.sort_by]);
      const bVal = parseFloat(b[filterConfig.sort_by]);
      if (isNaN(aVal) || isNaN(bVal)) {
        throw new Error(
          `CRITICAL: Invalid numeric value in sort field '${filterConfig.sort_by}'. ` +
          `Symbol ${isNaN(aVal) ? a.symbol : b.symbol} has non-numeric value. ` +
          `Check data quality in signal_quality_scores table.`
        );
      }
      const diff = bVal - aVal;
      return filterConfig.sort_order === "ASC" ? -diff : diff;
    };

    const qualified = evaluated
      .filter((e) => e.all_tiers_pass)
      .sort(sortComparator)
      .slice(0, filterConfig.max_qualified_signals);

    return sendSuccess(res, {
      total_buy_signals: evaluated.length,
      qualified_for_trading: qualified.length,
      signals: evaluated,
      top_qualified: qualified,
    });
  } catch (error) {
    logger.error("Error in /algo/evaluate:", {
      error: error.message,
      stack: error.stack,
    });
    return sendDatabaseError(
      res,
      error,
      "An error occurred while evaluating signals"
    );
  }
});

/**
 * GET /api/algo/last-run
 * Get the last orchestrator run status and phase information
 */
router.get("/last-run", async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();

    // FIXED: run_id is stored in details JSON, not as direct column
    const result = await pool.query(`
      SELECT DISTINCT
        details->>'run_id' as run_id,
        MAX(action_date)::timestamp as run_at,
        MAX(error_message) as error_message,
        array_agg(DISTINCT action_type ORDER BY action_type) as phase_actions
      FROM algo_audit_log
      WHERE action_type LIKE 'phase_%'
      GROUP BY details->>'run_id'
      ORDER BY MAX(action_date) DESC
      LIMIT 1
    `);

    if (result.rows.length === 0) {
      return sendSuccess(res, {
        run_id: null,
        run_at: null,
        success: null,
        halted: null,
        error_message: null,
        phases: [],
      });
    }

    const run = result.rows[0];
    // Determine success/halted from error_message presence and phase actions
    const halted = run.error_message && run.error_message.toLowerCase().includes('halt');
    const success = !halted && run.phase_actions && run.phase_actions.length > 0;

    return sendSuccess(res, {
      run_id: run.run_id,
      run_at: run.run_at,
      success: success,
      halted: halted,
      error_message: run.error_message,
      phases: run.phase_actions ? run.phase_actions.map(pt => ({ action_type: pt, status: 'complete' })) : [],
    });
  } catch (error) {
    logger.error("Error in /algo/last-run:", {
      error: error.message,
      stack: error.stack,
    });
    return sendSuccess(res, {
      run_id: null,
      run_at: null,
      success: null,
      halted: null,
      error_message: null,
      phases: [],
    });
  }
});

/**
 * GET /api/algo/positions
 * Get active positions enriched with stop/target levels (from latest open trade),
 * sector (from company_profile), and Minervini stage / RS (from trend_template_data).
 */
router.get("/positions", async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();

    // Fetch positions and stage config in parallel
    const [posResult, configResult] = await Promise.all([
      pool.query(`
        SELECT
          position_id, symbol, quantity, avg_entry_price, current_price,
          position_value, unrealized_pnl, unrealized_pnl_pct,
          status, stage_in_exit_plan, days_since_entry,
          stop_loss_price,
          target_1_price, target_2_price, target_3_price,
          target_1_r_multiple, target_2_r_multiple, target_3_r_multiple,
          sector, industry,
          weinstein_stage, minervini_trend_score,
          percent_from_52w_low, percent_from_52w_high,
          r_multiple, initial_risk_per_share, open_risk_dollars,
          distance_to_stop_pct, distance_to_t1_pct, distance_to_t2_pct, distance_to_t3_pct,
          NULL::float as risk_pct, NULL::int as risk_rank,
          NULL::float as ladder_pct_stop, NULL::float as ladder_pct_entry, NULL::float as ladder_pct_current,
          NULL::float as ladder_pct_t1, NULL::float as ladder_pct_t2, NULL::float as ladder_pct_t3,
          NULL::float as ladder_scale_min, NULL::float as ladder_scale_max
        FROM algo_positions_with_risk
        WHERE status IN ('open', 'partially_closed')
        ORDER BY position_value DESC
      `),
      pool.query(`
        SELECT key, value FROM algo_config
        WHERE key IN ('stage_2_early_min_score', 'stage_2_mid_min_score', 'stage_2_late_min_score')
      `),
    ]);

    // Validate result structures
    validateQueryResult(posResult, { requireRows: false });
    validateQueryResult(configResult, { requireRows: false });

    // CRITICAL: Stage thresholds must come from database. Hardcoded defaults would
    // allow trading with incorrect entry rules for different stages.
    const stageConfig = {
      stage_2_early_min_score: null,
      stage_2_mid_min_score: null,
      stage_2_late_min_score: null,
    };
    if (configResult.rows && configResult.rows.length > 0) {
      for (const row of configResult.rows) {
        const val = parseFloat(row.value);
        if (!isNaN(val)) {
          stageConfig[row.key] = val;
        }
      }
    }

    // Validate all required stage thresholds are configured
    if (
      stageConfig.stage_2_early_min_score === null ||
      stageConfig.stage_2_mid_min_score === null ||
      stageConfig.stage_2_late_min_score === null
    ) {
      return sendError(
        res,
        503,
        "CRITICAL: Stage threshold configuration incomplete. " +
          "Cannot compute position stage labels without configured thresholds. " +
          "Check algo_config for stage_2_early_min_score, stage_2_mid_min_score, stage_2_late_min_score."
      );
    }

    const sf = (v) => (v == null ? null : parseFloat(v));

    // Transform positions (pre-computed metrics from view, ISSUE #6, #7, #8)
    const items = validateAndCoerceRows(posResult, {
      position_id: { type: "int", required: true },
      symbol: { type: "string", required: true },
      quantity: { type: "float", required: true },
      avg_entry_price: { type: "float", required: false },
      current_price: { type: "float", required: false },
      position_value: { type: "float", required: false },
      unrealized_pnl: { type: "float", required: false },
      unrealized_pnl_pct: { type: "float", required: false },
      status: { type: "string", required: false },
      stage_in_exit_plan: { type: "string", required: false },
      days_since_entry: { type: "int", required: false },
      stop_loss_price: { type: "float", required: false },
      target_1_price: { type: "float", required: false },
      target_2_price: { type: "float", required: false },
      target_3_price: { type: "float", required: false },
      target_1_r_multiple: { type: "float", required: false },
      target_2_r_multiple: { type: "float", required: false },
      target_3_r_multiple: { type: "float", required: false },
      sector: { type: "string", required: false },
      industry: { type: "string", required: false },
      weinstein_stage: { type: "int", required: false },
      minervini_trend_score: { type: "int", required: false },
      percent_from_52w_low: { type: "float", required: false },
      percent_from_52w_high: { type: "float", required: false },
      r_multiple: { type: "float", required: false },
      initial_risk_per_share: { type: "float", required: false },
      open_risk_dollars: { type: "float", required: false },
      distance_to_stop_pct: { type: "float", required: false },
      distance_to_t1_pct: { type: "float", required: false },
      distance_to_t2_pct: { type: "float", required: false },
      distance_to_t3_pct: { type: "float", required: false },
      risk_pct: { type: "float", required: false },
      risk_rank: { type: "int", required: false },
      ladder_pct_stop: { type: "float", required: false },
      ladder_pct_entry: { type: "float", required: false },
      ladder_pct_current: { type: "float", required: false },
      ladder_pct_t1: { type: "float", required: false },
      ladder_pct_t2: { type: "float", required: false },
      ladder_pct_t3: { type: "float", required: false },
      ladder_scale_min: { type: "float", required: false },
      ladder_scale_max: { type: "float", required: false },
    }).map((row) => ({
      position_id: row.position_id,
      symbol: row.symbol,
      quantity: row.quantity,
      avg_entry_price: sf(row.avg_entry_price),
      current_price: sf(row.current_price),
      position_value: sf(row.position_value),
      unrealized_pnl: sf(row.unrealized_pnl),
      unrealized_pnl_pct: sf(row.unrealized_pnl_pct),
      status: row.status,
      stage_in_exit_plan: row.stage_in_exit_plan,
      days_since_entry: row.days_since_entry,
      stop_loss_price: sf(row.stop_loss_price),
      target_1_price: sf(row.target_1_price),
      target_2_price: sf(row.target_2_price),
      target_3_price: sf(row.target_3_price),
      target_1_r: sf(row.target_1_r_multiple),
      target_2_r: sf(row.target_2_r_multiple),
      target_3_r: sf(row.target_3_r_multiple),
      r_multiple: sf(row.r_multiple),
      initial_risk_per_share: sf(row.initial_risk_per_share),
      open_risk_dollars: sf(row.open_risk_dollars),
      distance_to_stop_pct: sf(row.distance_to_stop_pct),
      distance_to_t1_pct: sf(row.distance_to_t1_pct),
      distance_to_t2_pct: sf(row.distance_to_t2_pct),
      distance_to_t3_pct: sf(row.distance_to_t3_pct),
      sector: row.sector,
      industry: row.industry,
      weinstein_stage: row.weinstein_stage,
      minervini_trend_score: row.minervini_trend_score,
      stage_label: computeStageLabel(
        row.weinstein_stage,
        row.minervini_trend_score,
        stageConfig
      ),
      pct_from_52w_low: sf(row.percent_from_52w_low),
      pct_from_52w_high: sf(row.percent_from_52w_high),
      risk_pct: sf(row.risk_pct),
      risk_rank: row.risk_rank,
      ladder_pct_stop: sf(row.ladder_pct_stop),
      ladder_pct_entry: sf(row.ladder_pct_entry),
      ladder_pct_current: sf(row.ladder_pct_current),
      ladder_pct_t1: sf(row.ladder_pct_t1),
      ladder_pct_t2: sf(row.ladder_pct_t2),
      ladder_pct_t3: sf(row.ladder_pct_t3),
      ladder_scale_min: sf(row.ladder_scale_min),
      ladder_scale_max: sf(row.ladder_scale_max),
    }));

    // Compute sector allocation from positions
    // CRITICAL: All positions must have valid position values. Zero total position value indicates
    // data quality issue (missing price data, position data, or calculation error).
    const sectorMap = {};
    let totalValue = 0;
    for (const p of items) {
      const posValue = p.position_value;
      if (posValue === null || posValue === undefined) {
        return sendError(
          res,
          503,
          "CRITICAL: Position value missing for symbol " + p.symbol + ". " +
          "Cannot compute portfolio allocation without complete position data. " +
          "Check algo_positions table for complete position records and price data availability."
        );
      }
      if (posValue != null) {
        totalValue += posValue;
      }
    }
    if (totalValue <= 0) {
      return sendError(
        res,
        503,
        "CRITICAL: Total position value is zero or negative. " +
        "Cannot compute allocation with zero portfolio value. " +
        "Verify position data and current prices in database."
      );
    }
    for (const p of items) {
      const sec = p.sector || "Unknown";
      if (!sectorMap[sec])
        sectorMap[sec] = { position_count: 0, total_value_dollars: 0 };
      sectorMap[sec].position_count += 1;
      const posValue = p.position_value;
      if (posValue != null) {
        sectorMap[sec].total_value_dollars += posValue;
      }
    }
    const sector_allocation = Object.entries(sectorMap)
      .map(([sector, d]) => ({
        sector,
        position_count: d.position_count,
        total_value_dollars: parseFloat(d.total_value_dollars.toFixed(2)),
        allocation_pct: parseFloat(
          ((d.total_value_dollars / totalValue) * 100).toFixed(2)
        ),
        is_overweight: d.total_value_dollars / totalValue > 0.3,
      }))
      .sort((a, b) => b.total_value_dollars - a.total_value_dollars);

    return sendSuccess(res, {
      items,
      sector_allocation,
      pagination: {
        total: items.length,
        count: items.length,
      },
    });
  } catch (error) {
    logger.error("Error in /algo/positions:", {
      error: error.message,
      stack: error.stack,
    });
    return sendDatabaseError(
      res,
      error,
      "An error occurred while fetching positions"
    );
  }
});

/**
 * GET /api/algo/portfolio
 * Get current portfolio metrics including cumulative return, max drawdown, largest position.
 */
router.get("/portfolio", async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();

    const result = await pool.query(`
      SELECT
        snapshot_date,
        total_portfolio_value,
        total_cash,
        position_count,
        daily_return_pct,
        unrealized_pnl_pct,
        cumulative_return_pct,
        max_drawdown_pct,
        largest_position_pct
      FROM algo_portfolio_snapshots
      ORDER BY snapshot_date DESC
      LIMIT 1
    `);

    validateQueryResult(result, { requireRows: false });

    // CRITICAL: Fail-fast if no portfolio data. Do not return zeros (masks data quality issue).
    if (result.rows.length === 0) {
      return sendSuccess(res, {
        data: null,
        error: "no_data",
        message: "Portfolio snapshot data not yet available. Run data loaders to populate initial snapshot.",
        data_age_seconds: null,
      }, 503);
    }

    const snapshot = validateAndCoerceRow(result.rows[0], {
      snapshot_date: { type: "date", required: false },
      total_portfolio_value: {
        type: "float",
        required: false,
        defaultValue: null,
      },
      total_cash: { type: "float", required: false, defaultValue: null },
      position_count: { type: "int", required: false, defaultValue: null },
      daily_return_pct: {
        type: "float",
        required: false,
        defaultValue: null,
      },
      unrealized_pnl_pct: {
        type: "float",
        required: false,
        defaultValue: null,
      },
      cumulative_return_pct: {
        type: "float",
        required: false,
        defaultValue: null,
      },
      max_drawdown_pct: {
        type: "float",
        required: false,
        defaultValue: null,
      },
      largest_position_pct: {
        type: "float",
        required: false,
        defaultValue: null,
      },
    });

    const data_age_seconds = snapshot.snapshot_date
      ? Math.floor((Date.now() - new Date(snapshot.snapshot_date).getTime()) / 1000)
      : null;

    // CRITICAL: Return data quality flags so dashboard can alert on stale data
    const is_stale = data_age_seconds && data_age_seconds > 86400; // > 1 day
    const data_freshness = data_age_seconds ? {
      age_seconds: data_age_seconds,
      is_stale: is_stale,
      last_update: snapshot.snapshot_date,
    } : null;

    return sendSuccess(res, {
      snapshot_date: snapshot.snapshot_date,
      total_portfolio_value: snapshot.total_portfolio_value,
      total_cash: snapshot.total_cash,
      position_count: snapshot.position_count,
      daily_return_pct: snapshot.daily_return_pct,
      unrealized_pnl_pct: snapshot.unrealized_pnl_pct,
      cumulative_return_pct: snapshot.cumulative_return_pct,
      max_drawdown_pct: snapshot.max_drawdown_pct,
      largest_position_pct: snapshot.largest_position_pct,
      data_age_seconds: data_age_seconds,
      data_freshness: data_freshness,
    });
  } catch (error) {
    logger.error("Error in /algo/portfolio:", {
      error: error.message,
      stack: error.stack,
    });
    return sendDatabaseError(
      res,
      error,
      "An error occurred while fetching portfolio"
    );
  }
});

/**
 * GET /api/algo/portfolio-summary
 * Get aggregated portfolio metrics without individual positions.
 * ISSUE #9a: Replaces frontend aggregation logic.
 */
router.get("/portfolio-summary", authenticateToken, async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();

    // Fetch portfolio snapshot and sector summary in parallel
    const [snapshotResult, sectorResult] = await Promise.all([
      pool.query(`
        SELECT
          snapshot_date,
          total_portfolio_value,
          position_count,
          unrealized_pnl_pct,
          daily_return_pct,
          largest_position_pct,
          average_position_size_pct,
          concentration_risk_pct,
          realized_pnl_today,
          unrealized_pnl_total,
          max_drawdown_pct,
          sharpe_ratio
        FROM algo_portfolio_snapshots
        ORDER BY snapshot_date DESC
        LIMIT 1
      `),
      pool.query(`
        SELECT sector, position_count, total_value_dollars, allocation_pct, is_overweight
        FROM sector_allocation_summary
        WHERE snapshot_date = CURRENT_DATE
        ORDER BY allocation_pct DESC
      `),
    ]);

    validateQueryResult(snapshotResult, { requireRows: false });
    validateQueryResult(sectorResult, { requireRows: false });

    const snapshot = snapshotResult.rows[0]
      ? validateAndCoerceRow(snapshotResult.rows[0], {
          snapshot_date: { type: "date", required: false },
          total_portfolio_value: {
            type: "float",
            required: false,
          },
          position_count: { type: "int", required: false },
          unrealized_pnl_pct: {
            type: "float",
            required: false,
          },
          daily_return_pct: { type: "float", required: false },
          largest_position_pct: {
            type: "float",
            required: false,
          },
          average_position_size_pct: {
            type: "float",
            required: false,
          },
          concentration_risk_pct: {
            type: "float",
            required: false,
          },
          realized_pnl_today: {
            type: "float",
            required: false,
          },
          unrealized_pnl_total: {
            type: "float",
            required: false,
          },
          max_drawdown_pct: { type: "float", required: false },
          sharpe_ratio: { type: "float", required: false },
        })
      : null;

    const sector_allocation = validateAndCoerceRows(sectorResult, {
      sector: { type: "string", required: true },
      position_count: { type: "int", required: false },
      total_value_dollars: { type: "float", required: false },
      allocation_pct: { type: "float", required: false },
      is_overweight: { type: "bool", required: false },
    });

    return sendSuccess(res, {
      portfolio: {
        snapshot_date: snapshot.snapshot_date,
        total_value: snapshot.total_portfolio_value,
        position_count: snapshot.position_count,
        unrealized_pnl_pct: snapshot.unrealized_pnl_pct,
        unrealized_pnl_dollars: snapshot.unrealized_pnl_total,
        daily_return_pct: snapshot.daily_return_pct,
        realized_pnl_today: snapshot.realized_pnl_today,
        largest_position_pct: snapshot.largest_position_pct,
        average_position_size_pct: snapshot.average_position_size_pct,
        concentration_risk_pct: snapshot.concentration_risk_pct,
        max_drawdown_pct: snapshot.max_drawdown_pct,
        sharpe_ratio: snapshot.sharpe_ratio,
      },
      sector_allocation,
    });
  } catch (error) {
    logger.error("Error in /algo/portfolio-summary:", {
      error: error.message,
      stack: error.stack,
    });
    return sendDatabaseError(
      res,
      error,
      "An error occurred while fetching portfolio summary"
    );
  }
});

/**
 * GET /api/algo/trades
 * Get trade history
 */
router.get("/trades", async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();
    const { limit, offset } = paginationConfig.sanitize(
      req.query.limit,
      req.query.offset,
      "trades"
    );

    // Parallelize data fetch and count query
    const [result, countResult] = await Promise.all([
      pool.query(
        `
        SELECT
          trade_id,
          symbol,
          signal_date,
          trade_date,
          entry_price,
          entry_quantity,
          status,
          exit_date,
          exit_price,
          exit_r_multiple,
          profit_loss_pct,
          profit_loss_dollars,
          trade_duration_days
        FROM algo_trades
        ORDER BY trade_date DESC
        LIMIT $1 OFFSET $2
      `,
        [limit, offset]
      ),
      pool.query("SELECT COUNT(*) as total FROM algo_trades"),
    ]);

    // Validate result structures
    validateQueryResult(result, { requireRows: false });
    validateQueryResult(countResult, { minRows: 1, maxRows: 1 });
    const total = extractCount(countResult, "total");

    // Validate and coerce row types
    const validated = validateAndCoerceRows(result, {
      trade_id: { type: "int", required: true },
      symbol: { type: "string", required: true },
      signal_date: { type: "date", required: false },
      trade_date: { type: "date", required: true },
      entry_price: { type: "float", required: false },
      entry_quantity: { type: "float", required: false },
      status: { type: "string", required: false },
      exit_date: { type: "date", required: false },
      exit_price: { type: "float", required: false },
      exit_r_multiple: { type: "float", required: false },
      profit_loss_pct: { type: "float", required: false },
      profit_loss_dollars: { type: "float", required: false },
      trade_duration_days: { type: "int", required: false },
    });

    return sendSuccess(res, {
      items: validated,
      pagination: {
        total,
        limit,
        offset,
        page: Math.floor(offset / limit) + 1,
        totalPages: Math.ceil(total / limit),
      },
    });
  } catch (error) {
    logger.error("Error in /algo/trades:", {
      error: error.message,
      stack: error.stack,
    });
    return sendDatabaseError(
      res,
      error,
      "An error occurred while fetching trade history"
    );
  }
});

/**
 * Configuration category mapping (for frontend grouping)
 */
const CONFIG_CATEGORIES = {
  base_risk_pct: "Risk Management",
  max_position_size_pct: "Risk Management",
  max_positions: "Risk Management",
  max_concentration_pct: "Risk Management",
  max_total_invested_pct: "Risk Management",
  max_consecutive_losses: "Risk Management",
  max_daily_loss_pct: "Risk Management",
  max_weekly_loss_pct: "Risk Management",
  min_win_rate_pct: "Risk Management",
  halt_drawdown_pct: "Drawdown Defense",
  risk_reduction_at_minus_5: "Drawdown Defense",
  risk_reduction_at_minus_10: "Drawdown Defense",
  risk_reduction_at_minus_15: "Drawdown Defense",
  risk_reduction_at_minus_20: "Drawdown Defense",
  sector_drawdown_halt_pct: "Drawdown Defense",
  halt_entries_before_major_release_minutes: "Circuit Breakers",
  re_engage_min_days: "Circuit Breakers",
  re_engage_recovery_pct: "Circuit Breakers",
  position_halt_flag_count: "Circuit Breakers",
  max_distribution_days: "Market Conditions",
  require_stage_2_market: "Market Conditions",
  vix_max_threshold: "Market Conditions",
  vix_caution_threshold: "Market Conditions",
  vix_caution_risk_reduction: "Market Conditions",
  min_completeness_score: "Filter Thresholds",
  min_stock_price: "Filter Thresholds",
  min_signal_quality_score: "Filter Thresholds",
  min_volume_ma_50d: "Filter Thresholds",
  min_avg_daily_dollar_volume: "Filter Thresholds",
  min_market_cap_millions: "Filter Thresholds",
  min_float_millions: "Filter Thresholds",
  min_price_history_days: "Filter Thresholds",
  min_daily_volume_shares: "Filter Thresholds",
  max_spread_pct: "Filter Thresholds",
  max_short_interest_pct: "Filter Thresholds",
  max_data_staleness_days: "Filter Thresholds",
  require_sma50_above_sma200: "Entry Rules (Minervini)",
  min_percent_from_52w_low: "Entry Rules (Minervini)",
  max_percent_from_52w_high: "Entry Rules (Minervini)",
  eight_week_rule_threshold_pct: "Entry Rules (Minervini)",
  eight_week_rule_window_days: "Entry Rules (Minervini)",
  max_signal_age_days: "Entry Quality Gates",
  min_close_quality_pct: "Entry Quality Gates",
  min_breakout_volume_ratio: "Entry Quality Gates",
  require_weekly_stage_2: "Entry Quality Gates",
  min_rs_line_slope_days: "Entry Quality Gates",
  max_rs_pct_from_60d_high: "Entry Quality Gates",
  rs_slope_gate_enabled: "Entry Quality Gates",
  volume_decay_gate_enabled: "Entry Quality Gates",
  require_target_pullback: "Entry Quality Gates",
  exit_on_distribution_day: "Exit Rules",
  exit_on_rs_line_break_50dma: "Exit Rules",
  exit_on_td_sequential: "Exit Rules",
  max_hold_days: "Exit Rules",
  min_hold_days: "Exit Rules",
  chandelier_atr_mult: "Exit Rules",
  use_chandelier_trail: "Exit Rules",
  switch_to_21ema_after_days: "Exit Rules",
  move_be_at_r: "Exit Rules",
  pyramid_enabled: "Pyramid & Re-engagement",
  pyramid_add_1_gain_pct: "Pyramid & Re-engagement",
  pyramid_add_2_gain_pct: "Pyramid & Re-engagement",
  pyramid_split_pct: "Pyramid & Re-engagement",
  require_ftd_to_re_engage: "Pyramid & Re-engagement",
  max_trades_per_day: "Position Monitoring",
  max_reentries_per_name: "Position Monitoring",
  min_days_before_reentry_same_symbol: "Position Monitoring",
  max_positions_per_sector: "Position Monitoring",
  max_positions_per_industry: "Position Monitoring",
  min_swing_score: "Swing Trader Scoring",
  min_swing_grade: "Swing Trader Scoring",
  swing_min_trend_score: "Swing Trader Scoring",
  swing_min_industry_rank: "Swing Trader Scoring",
  swing_days_to_earnings_block: "Swing Trader Scoring",
  swing_score_good_threshold: "Swing Trader Scoring",
  swing_score_excellent_threshold: "Swing Trader Scoring",
  swing_weight_setup: "Swing Trader Scoring",
  swing_weight_trend: "Swing Trader Scoring",
  swing_weight_momentum: "Swing Trader Scoring",
  swing_weight_volume: "Swing Trader Scoring",
  swing_weight_fundamentals: "Swing Trader Scoring",
  swing_weight_sector: "Swing Trader Scoring",
  swing_weight_multi_timeframe: "Swing Trader Scoring",
  block_days_before_earnings: "Economic & Earnings",
  earnings_blackout_days_before: "Economic & Earnings",
  earnings_blackout_days_after: "Economic & Earnings",
  require_stock_stage_2: "Economic & Earnings",
  min_trend_template_score: "Fundamental Filters",
  strong_sector_top_n: "Fundamental Filters",
  enable_advanced_filters: "Advanced Filters",
  max_total_risk_pct: "Risk Metrics",
  t1_target_r_multiple: "Risk Metrics",
  t2_target_r_multiple: "Risk Metrics",
  t3_target_r_multiple: "Risk Metrics",
  execution_mode: "Execution Mode",
  enable_algo: "Execution Mode",
  enable_backtesting: "Execution Mode",
  alpaca_paper_trading: "Execution Mode",
  verbose_logging: "Feature Flags",
  api_request_timeout_seconds: "Network Configuration",
  db_connection_timeout_seconds: "Network Configuration",
  default_portfolio_value: "Failsafe Configuration",
  imported_position_default_stop_loss_pct: "Failsafe Configuration",
  imported_position_default_target_1_pct: "Failsafe Configuration",
  imported_position_default_target_2_pct: "Failsafe Configuration",
  imported_position_default_target_3_pct: "Failsafe Configuration",
  daily_profit_cap_pct: "Failsafe Configuration",
  stale_loader_threshold_minutes: "Failsafe Configuration",
};

/**
 * GET /api/algo/config (admin only)
 * Get current configuration as array with categories
 */
router.get("/config", async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();

    const result = await pool.query(`
      SELECT key, value, value_type, description, updated_at
      FROM algo_config
      ORDER BY key
    `);

    const configArray = result.rows.map((row) => {
      let parsedValue = row.value;
      if (row.value_type === "int") {
        parsedValue = parseInt(row.value, 10);
      } else if (row.value_type === "float") {
        parsedValue = parseFloat(row.value);
      } else if (row.value_type === "bool") {
        parsedValue = ["true", "1", "yes"].includes(
          String(row.value).toLowerCase()
        );
      }
      return {
        key: row.key,
        value: parsedValue,
        value_type: row.value_type,
        description: row.description,
        category: CONFIG_CATEGORIES[row.key] || "Other",
        updated_at: row.updated_at,
        is_custom: false,
      };
    });

    return sendSuccess(res, configArray);
  } catch (error) {
    logger.error("Error in /algo/config:", {
      error: error.message,
      stack: error.stack,
    });
    return sendDatabaseError(
      res,
      error,
      "An error occurred while fetching configuration"
    );
  }
});

/**
 * PUT /api/algo/config/:key (admin only)
 * Update a single configuration value
 */
router.put("/config/:key", requireAuth, requireAdmin, async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();
    const { key } = req.params;
    const { value } = req.body;

    if (!key || !key.match(/^[a-z0-9_]+$/i)) {
      return sendError(res, "Invalid configuration key", 400);
    }

    if (value === undefined || value === null) {
      return sendError(res, "Value is required", 400);
    }

    // Get the current config to know the value_type for proper conversion
    const configResult = await pool.query(
      "SELECT key, value, value_type, description FROM algo_config WHERE key = $1",
      [key]
    );

    if (configResult.rows.length === 0) {
      return sendError(res, `Configuration key not found: ${key}`, 404);
    }

    const config = configResult.rows[0];
    let storedValue = String(value);

    // Validate and convert value based on type
    if (config.value_type === "int") {
      const intVal = parseInt(value, 10);
      if (isNaN(intVal)) {
        return sendError(
          res,
          `Invalid integer value for ${key}: ${value}`,
          400
        );
      }
      storedValue = String(intVal);
    } else if (config.value_type === "float") {
      const floatVal = parseFloat(value);
      if (isNaN(floatVal)) {
        return sendError(res, `Invalid float value for ${key}: ${value}`, 400);
      }
      storedValue = String(floatVal);
    } else if (config.value_type === "bool") {
      const boolVal = ["true", "1", "yes"].includes(
        String(value).toLowerCase()
      );
      storedValue = boolVal ? "true" : "false";
    }

    // Update the configuration
    const updateResult = await pool.query(
      `UPDATE algo_config
       SET value = $1, updated_at = CURRENT_TIMESTAMP
       WHERE key = $2
       RETURNING key, value, value_type, description, updated_at`,
      [storedValue, key]
    );

    if (updateResult.rows.length === 0) {
      return sendError(res, "Failed to update configuration", 500);
    }

    const updatedRow = updateResult.rows[0];

    // Parse the updated value to match frontend expectations
    let parsedValue = updatedRow.value;
    if (updatedRow.value_type === "int") {
      parsedValue = parseInt(updatedRow.value, 10);
    } else if (updatedRow.value_type === "float") {
      parsedValue = parseFloat(updatedRow.value);
    } else if (updatedRow.value_type === "bool") {
      parsedValue = ["true", "1", "yes"].includes(
        updatedRow.value.toLowerCase()
      );
    }

    return sendSuccess(res, {
      key: updatedRow.key,
      value: parsedValue,
      value_type: updatedRow.value_type,
      description: updatedRow.description,
      category: CONFIG_CATEGORIES[updatedRow.key] || "Other",
      updated_at: updatedRow.updated_at,
      is_custom: true,
    });
  } catch (error) {
    logger.error("Error in PUT /algo/config/:key:", {
      error: error.message,
      stack: error.stack,
    });
    return sendDatabaseError(
      res,
      error,
      "An error occurred while updating configuration"
    );
  }
});

// ============================================================
// MARKET EXPOSURE â€” for the Markets page
// ============================================================
router.get("/markets", async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();

    // Parallelize all 6 independent queries
    const [
      latestResult,
      historyResult,
      healthResult,
      spyResult,
      sectorsResult,
      sentimentResult,
    ] = await Promise.all([
      pool.query(`
        SELECT date, exposure_pct, raw_score, regime, distribution_days,
               factors, halt_reasons, created_at
        FROM market_exposure_daily
        ORDER BY date DESC LIMIT 1
      `),
      pool.query(`
        SELECT date, exposure_pct, regime, distribution_days
        FROM market_exposure_daily
        WHERE date >= CURRENT_DATE - INTERVAL '90 days'
        ORDER BY date ASC
      `),
      pool.query(`
        SELECT date, market_trend, market_stage, distribution_days_4w, vix_level,
               advance_decline_ratio, new_highs_count, new_lows_count, put_call_ratio,
               breadth_momentum_10d, yield_curve_slope, fed_rate_environment, up_volume_percent
        FROM market_health_daily ORDER BY date DESC LIMIT 1
      `),
      pool.query(`
        SELECT close, volume FROM price_daily WHERE symbol = 'SPY' ORDER BY date DESC LIMIT 2
      `),
      pool.query(`
        SELECT sector_name, current_rank, momentum_score
        FROM sector_ranking
        WHERE date = (SELECT MAX(date) FROM sector_ranking)
          AND sector_name <> '' AND sector_name IS NOT NULL AND sector_name <> 'Benchmark'
        ORDER BY current_rank ASC
      `),
      pool.query(`
        SELECT date, bullish, bearish, neutral
        FROM aaii_sentiment ORDER BY date DESC LIMIT 8
      `),
    ]);

    // Validate all result structures
    validateQueryResult(latestResult, { requireRows: false });
    validateQueryResult(historyResult, { requireRows: false });
    validateQueryResult(healthResult, { requireRows: false });
    validateQueryResult(spyResult, { requireRows: false });
    validateQueryResult(sectorsResult, { requireRows: false });
    validateQueryResult(sentimentResult, { requireRows: false });

    const latest = latestResult.rows[0]
      ? validateAndCoerceRow(latestResult.rows[0], {
          date: { type: "date", required: false },
          exposure_pct: { type: "float", required: false },
          raw_score: { type: "float", required: false },
          regime: { type: "string", required: false },
          distribution_days: { type: "int", required: false },
          factors: { type: "raw", required: false },
          halt_reasons: { type: "raw", required: false },
          created_at: { type: "date", required: false },
        })
      : null;

    const health = healthResult.rows[0]
      ? validateAndCoerceRow(healthResult.rows[0], {
          date: { type: "date", required: false },
          market_trend: { type: "string", required: false },
          market_stage: { type: "int", required: false },
          distribution_days_4w: { type: "int", required: false },
          vix_level: { type: "float", required: false },
          advance_decline_ratio: { type: "float", required: false },
          new_highs_count: { type: "int", required: false },
          new_lows_count: { type: "int", required: false },
          put_call_ratio: { type: "float", required: false },
          breadth_momentum_10d: { type: "float", required: false },
          yield_curve_slope: { type: "float", required: false },
          fed_rate_environment: { type: "string", required: false },
          up_volume_percent: { type: "float", required: false },
        })
      : null;

    // Get SPY price (latest 2 rows for change calculation)
    const spyPrices = spyResult.rows || [];
    const spyClose = spyPrices.length > 0 ? parseFloat(spyPrices[0].close) : null;
    const spyChangePct = spyPrices.length >= 2
      ? ((parseFloat(spyPrices[0].close) - parseFloat(spyPrices[1].close)) / parseFloat(spyPrices[1].close)) * 100
      : null;

    // Determine active tier policy from database - exposure is critical for tier decisions
    let policy = null;
    let exposureError = null;
    if (latest) {
      const exposureValidation = requireExposure(latest.exposure_pct);
      if (isDataError(exposureValidation)) {
        exposureError = exposureValidation;
      } else {
        const tiers = await getActiveTiers();
        policy = getActiveTier(exposureValidation, tiers);
      }
    }

    // Validate and coerce all rows
    const historyRows = validateAndCoerceRows(historyResult, {
      date: { type: "date", required: false },
      exposure_pct: { type: "float", required: false },
      regime: { type: "string", required: false },
      distribution_days: { type: "int", required: false },
    });

    const sectorsRows = validateAndCoerceRows(sectorsResult, {
      sector_name: { type: "string", required: false },
      current_rank: { type: "int", required: false },
      momentum_score: { type: "float", required: false },
    });

    const sentimentRows = validateAndCoerceRows(sentimentResult, {
      date: { type: "date", required: false },
      bullish: { type: "float", required: false },
      bearish: { type: "float", required: false },
      neutral: { type: "float", required: false },
    });

    // Parse halt_reasons: stored as VARCHAR containing JSON array string (e.g. "[]")
    // FAIL-FAST: Halt reasons are critical for trading decisions - cannot silently default
    let parsedHaltReasons = [];
    if (latest && latest.halt_reasons != null) {
      if (typeof latest.halt_reasons === "string") {
        try {
          parsedHaltReasons = JSON.parse(latest.halt_reasons);
        } catch (e) {
          logger.error("CRITICAL: Halt reasons JSON parse error - data corruption or misconfiguration detected", {
            raw_value: latest.halt_reasons.substring(0, 200),
            error: e.message,
          });
          return sendError(
            res,
            503,
            "CRITICAL: Market halt reasons data is corrupted. Cannot proceed with trading without valid halt information."
          );
        }
      } else if (Array.isArray(latest.halt_reasons)) {
        parsedHaltReasons = latest.halt_reasons;
      }
    }

    // Validate critical fields in current snapshot
    let currentSnapshot = null;
    let currentErrors = [];
    if (latest) {
      const exposureValidation = requireExposure(latest.exposure_pct);
      const scoreValidation = requireSignalQuality(latest.raw_score);

      if (isDataError(exposureValidation) || isDataError(scoreValidation)) {
        currentErrors = [exposureValidation, scoreValidation].filter(isDataError);
        if (exposureError) {
          currentErrors.push(exposureError);
        }
      } else {
        currentSnapshot = {
          date: latest.date,
          exposure_pct: exposureValidation,
          raw_score: scoreValidation,
          regime: latest.regime,
          distribution_days: latest.distribution_days,
          factors: latest.factors !== null && latest.factors !== undefined ? latest.factors : null,
          halt_reasons: parsedHaltReasons,
        };
      }
    }

    // Validate history rows - exposure is critical for risk tracking
    const validatedHistory = historyRows
      .map((r) => {
        const exposureValidation = requireExposure(r.exposure_pct);
        if (isDataError(exposureValidation)) {
          return { error: exposureValidation, original: r };
        }
        return {
          date: r.date,
          exposure_pct: exposureValidation,
          regime: r.regime,
          distribution_days: r.distribution_days,
        };
      });

    const historyErrors = validatedHistory
      .filter(h => h.error)
      .map(h => h.error);

    const validHistory = validatedHistory
      .filter(h => !h.error);

    // Collect all errors from all sections
    const allErrors = [...currentErrors, ...historyErrors];

    // CRITICAL: Fail-fast if essential market health data is completely unavailable
    if (!health || health === null) {
      return sendSuccess(res, {
        current: currentSnapshot,
        active_tier: policy,
        history: validHistory,
        market_health: null,
        data_error: "market_health_unavailable",
        message: "Market health data not yet available. Run data loaders to populate market_health_daily.",
      }, 503);
    }

    // If critical current snapshot failed, return error response with available data
    if (currentErrors.length > 0 && !currentSnapshot) {
      return sendSuccess(res, {
        current: null,
        active_tier: null,
        history: validHistory,
        market_health: {
          date: health.date,
          market_trend: health.market_trend,
          market_stage: health.market_stage,
          distribution_days_4w: health.distribution_days_4w,
          vix_level: health.vix_level,
          advance_decline_ratio: health.advance_decline_ratio,
          new_highs_count: health.new_highs_count,
          new_lows_count: health.new_lows_count,
          put_call_ratio: health.put_call_ratio,
          breadth_momentum_10d: health.breadth_momentum_10d,
          yield_curve_slope: health.yield_curve_slope,
          fed_rate_environment: health.fed_rate_environment,
          up_volume_percent: health.up_volume_percent,
          spy_close: spyClose,
          spy_change_pct: spyChangePct,
        },
        data_errors: allErrors,
        message: "Market exposure data unavailable, but market health data available",
      }, 503);
    }

    return sendSuccess(res, {
      current: currentSnapshot,
      active_tier: policy,
      history: validHistory,
      market_health: {
        date: health.date,
        market_trend: health.market_trend,
        market_stage: health.market_stage,
        distribution_days_4w: health.distribution_days_4w,
        vix_level: health.vix_level,
        advance_decline_ratio: health.advance_decline_ratio,
        new_highs_count: health.new_highs_count,
        new_lows_count: health.new_lows_count,
        put_call_ratio: health.put_call_ratio,
        breadth_momentum_10d: health.breadth_momentum_10d,
        yield_curve_slope: health.yield_curve_slope,
        fed_rate_environment: health.fed_rate_environment,
        up_volume_percent: health.up_volume_percent,
        spy_close: spyClose,
        spy_change_pct: spyChangePct,
      },
      sectors: sectorsRows.map((r) => ({
        name: r.sector_name,
        rank: r.current_rank,
        momentum: r.momentum_score,
      })),
      ...(allErrors.length > 0 && { data_errors: allErrors }),
      sentiment: sentimentRows.map((r) => ({
        date: r.date,
        bullish: r.bullish,
        bearish: r.bearish,
        neutral: r.neutral,
      })),
    });
  } catch (error) {
    logger.error("Error in /algo/markets:", {
      error: error.message,
      stack: error.stack,
    });
    return sendDatabaseError(
      res,
      error,
      "An error occurred while fetching market data"
    );
  }
});

// ============================================================
// SWING TRADER SCORES â€” for ranking display
// ============================================================
router.get("/swing-scores", async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();
    const { limit } = paginationConfig.sanitize(req.query.limit, 0, "signals");
    const minScoreRaw = parseFloat(req.query.min_score);
    const minScore = !isNaN(minScoreRaw) ? minScoreRaw : 0; // Query param default to 0 is acceptable
    const symbol = req.query.symbol ? req.query.symbol.toUpperCase() : null;

    let whereClauses = [
      `s.date = (SELECT MAX(date) FROM swing_trader_scores)`,
      `s.score >= $1`,
    ];
    const params = [minScore];

    if (symbol) {
      params.push(symbol);
      whereClauses.push(`s.symbol = $${params.length}`);
    }

    params.push(limit);
    const limitParamNum = params.length;

    const result = await pool.query(
      `SELECT s.symbol, s.date, s.score, s.components,
              cp.short_name, cp.sector, cp.industry
       FROM swing_trader_scores s
       LEFT JOIN company_profile cp ON cp.ticker = s.symbol
       WHERE ${whereClauses.join(" AND ")}
       ORDER BY s.score DESC
       LIMIT $${limitParamNum}`,
      params
    );

    // Validate result structure
    validateQueryResult(result, { requireRows: false });

    // Fetch grade configuration from database
    const grades = await getSwingGrades();

    const parseComponentsJSON = (components) => {
      if (!components) return null; // Explicitly indicate missing data
      if (typeof components === "object") return components;
      if (typeof components !== "string") {
        logger.warn("swing_trader_scores components field is non-string, non-object type", {
          actualType: typeof components,
          value: String(components).substring(0, 100),
        });
        return null;
      }
      try {
        return JSON.parse(components);
      } catch (e) {
        const parseError = new Error(
          `Cannot parse swing_trader_scores components (data corruption): ${components.substring(0, 100)}`
        );
        parseError.originalError = e;
        logger.error("CRITICAL: swing_trader_scores components JSON parse failed", {
          error: parseError.message,
          originalError: e.message,
          componentsSample: components.substring(0, 200),
        });
        throw parseError;
      }
    };

    return sendSuccess(res, {
      items: validateAndCoerceRows(result, {
        symbol: { type: "string", required: true },
        date: { type: "date", required: true },
        score: { type: "float", required: true },
        components: { type: "string", required: false },
        short_name: { type: "string", required: false },
        sector: { type: "string", required: false },
        industry: { type: "string", required: false },
      }).map((r) => {
        const score = r.score;
        const gradeInfo = getGradeForScore(score, grades);

        return {
          symbol: r.symbol,
          date: r.date,
          swing_score: score,
          score: score, // alias for compatibility
          grade: gradeInfo.letter,
          pass_gates: gradeInfo.pass_gates,
          fail_reason: gradeInfo.fail_reason,
          components: parseComponentsJSON(r.components),
          company_name: r.short_name,
          sector: r.sector,
          industry: r.industry,
        };
      }),
    });
  } catch (error) {
    logger.error("Error in /algo/swing-scores:", {
      error: error.message,
      stack: error.stack,
    });
    return sendDatabaseError(
      res,
      error,
      "An error occurred while fetching swing scores"
    );
  }
});

// ============================================================
// SWING SCORES HISTORY â€” score counts over time
// ============================================================
router.get("/swing-scores-history", async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();
    const parsedDays = parseInt(req.query.days);
    const days = Math.min(!isNaN(parsedDays) ? parsedDays : 30, 180);

    const result = await pool.query(
      `SELECT DATE(date) as eval_date,
              COUNT(*) AS total,
              COUNT(*) FILTER (WHERE score >= 80) AS score_high,
              COUNT(*) FILTER (WHERE score >= 60 AND score < 80) AS score_medium,
              COUNT(*) FILTER (WHERE score < 60) AS score_low,
              ROUND(AVG(score)::numeric, 2) AS avg_score,
              (COUNT(*) FILTER (WHERE score >= 80) + COUNT(*) FILTER (WHERE score >= 60 AND score < 80)) AS pass_count
       FROM swing_trader_scores
       WHERE date >= CURRENT_DATE - MAKE_INTERVAL(days => $1)
       GROUP BY DATE(date)
       ORDER BY eval_date ASC`,
      [days]
    );

    // Validate result structure
    validateQueryResult(result, { requireRows: false });

    return sendSuccess(res, {
      items: validateAndCoerceRows(result, {
        eval_date: { type: "date", required: true },
        total: { type: "int", required: false },
        score_high: { type: "int", required: false },
        score_medium: { type: "int", required: false },
        score_low: { type: "int", required: false },
        avg_score: { type: "float", required: false },
        pass_count: { type: "int", required: false },
      }).map((r) => ({
        eval_date: r.eval_date,
        date: r.eval_date,
        total: r.total !== null && r.total !== undefined ? r.total : null,
        grade_aplus: r.score_high !== null && r.score_high !== undefined ? r.score_high : null,
        grade_a: r.score_medium !== null && r.score_medium !== undefined ? r.score_medium : null,
        pass_count: r.pass_count !== null && r.pass_count !== undefined ? r.pass_count : null,
        low_scores: r.score_low !== null && r.score_low !== undefined ? r.score_low : null,
        high_scores: r.score_high !== null && r.score_high !== undefined ? r.score_high : null,
        medium_scores: r.score_medium !== null && r.score_medium !== undefined ? r.score_medium : null,
        avg_score: r.avg_score !== null && r.avg_score !== undefined ? r.avg_score : null,
      })),
    });
  } catch (error) {
    logger.error("Error in /algo/swing-scores-history:", {
      error: error.message,
      stack: error.stack,
    });
    return sendDatabaseError(
      res,
      error,
      "An error occurred while fetching score history"
    );
  }
});

// ============================================================
// DATA FRESHNESS â€” for monitoring (computed dynamically from source tables)
// ============================================================
router.get("/data-status", async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();

    // Compute data freshness dynamically â€” don't rely on pre-populated audit table
    // which would show false "ready_to_trade: true" when empty.
    const result = await pool.query(`
      SELECT table_name, frequency, role, latest_date,
             CURRENT_DATE - latest_date AS age_days,
             row_count,
             CASE
               WHEN row_count = 0 THEN 'empty'
               WHEN (CURRENT_DATE - latest_date) > stale_days THEN 'stale'
               ELSE 'ok'
             END AS status
      FROM (
        SELECT 'price_daily'          AS table_name, 'daily'   AS frequency, 'CRITICAL'    AS role,
               MAX(date)::date        AS latest_date, COUNT(*)  AS row_count, 3  AS stale_days FROM price_daily
        UNION ALL
        SELECT 'market_health_daily',  'daily',   'CRITICAL',
               MAX(date)::date,        COUNT(*),  3  FROM market_health_daily
        UNION ALL
        SELECT 'trend_template_data',  'daily',   'CRITICAL',
               MAX(date)::date,        COUNT(*),  7  FROM trend_template_data
        UNION ALL
        SELECT 'buy_sell_daily',       'daily',   'SUPPLEMENTAL',
               MAX(date)::date,        COUNT(*),  3  FROM buy_sell_daily
        UNION ALL
        SELECT 'stock_scores',         'daily',   'SUPPLEMENTAL',
               MAX(updated_at::date),  COUNT(*),  3  FROM stock_scores
        UNION ALL
        SELECT 'technical_data_daily', 'daily',   'SUPPLEMENTAL',
               MAX(date)::date,        COUNT(*),  3  FROM technical_data_daily
        UNION ALL
        SELECT 'economic_data',        'weekly',  'SUPPLEMENTAL',
               MAX(date)::date,        COUNT(*),  14 FROM economic_data
        UNION ALL
        SELECT 'sector_ranking',       'weekly',  'SUPPLEMENTAL',
               MAX(date)::date, COUNT(*), 14 FROM sector_ranking
        UNION ALL
        SELECT 'algo_positions',       'live',    'TRADING',
               GREATEST(MAX(updated_at)::date, CURRENT_DATE - 1), COUNT(*), 365 FROM algo_positions WHERE status = 'open'
      ) src
      ORDER BY
        CASE WHEN role = 'CRITICAL' THEN 1 WHEN role = 'IMPORTANT' THEN 2
             WHEN role = 'TRADING' THEN 3 ELSE 4 END,
        table_name
    `);

    // Validate result structure
    validateQueryResult(result, { requireRows: false });

    // Validate and coerce row types
    const validated = validateAndCoerceRows(result, {
      table_name: { type: "string", required: true },
      frequency: { type: "string", required: false },
      role: { type: "string", required: false },
      latest_date: { type: "date", required: false },
      age_days: { type: "int", required: false },
      row_count: { type: "int", required: false, defaultValue: 0 },
      status: { type: "string", required: false },
    });

    const counts = { ok: 0, stale: 0, empty: 0, error: 0 };
    validated.forEach((r) => {
      if (!r.status) {
        throw new Error(`Missing status for table ${r.table_name} - data quality issue`);
      }
      if (!Object.prototype.hasOwnProperty.call(counts, r.status)) {
        throw new Error(`Unknown status "${r.status}" for table ${r.table_name}`);
      }
      counts[r.status]++;
    });

    const criticalStale = validated.filter(
      (r) => r.status !== "ok" && (r.role || "") === "CRITICAL"
    );

    // Only mark ready_to_trade true if we actually have data rows to check
    const ready_to_trade = validated.length > 0 && criticalStale.length === 0;

    const sources_data = validated.map((r) => ({
      name: r.table_name,
      frequency: r.frequency,
      role: r.role,
      latest_date: r.latest_date,
      age_hours: r.age_days ? r.age_days * 24 : null,
      row_count: r.row_count,
      status: r.status,
      last_audit: null,
      error: null,
    }));

    const response_data = {
      items: sources_data,
      total: sources_data.length,
      summary: counts,
      critical_stale: criticalStale.map((r) => r.table_name),
      ready_to_trade,
      sources: sources_data,
      expected_date: new Date().toISOString().split('T')[0],
      as_of: new Date().toISOString(),
      pagination: {
        limit: sources_data.length,
        offset: 0,
        total: sources_data.length,
        page: 1,
        totalPages: 1,
        hasNext: false,
        hasPrev: false,
      },
    };

    return sendSuccess(res, response_data);
  } catch (error) {
    logger.error("Error in /algo/data-status:", {
      error: error.message,
      stack: error.stack,
    });
    return sendDatabaseError(
      res,
      error,
      "An error occurred while checking data status"
    );
  }
});

// ============================================================

// ============================================================
// RUN ORCHESTRATOR â€” trigger the daily algo workflow from UI (admin only)
// ============================================================
router.post("/run", requireAuth, requireAdmin, async (req, res) => {
  const { spawn } = require("child_process");
  const path = require("path");

  try {
    const dryRun = req.body?.dry_run !== false; // default to dry-run for safety
    const date = req.body?.date || null;

    // Validate date format (YYYY-MM-DD) to prevent command injection
    if (date && !/^\d{4}-\d{2}-\d{2}$/.test(date)) {
      return sendError(res, "Invalid date format. Expected YYYY-MM-DD", 400);
    }

    const args = ["algo_orchestrator.py"];
    if (date) args.push("--date", date);
    if (dryRun) args.push("--dry-run");

    const repoRoot = path.resolve(__dirname, "../../..");
    const child = spawn("python3", args, { cwd: repoRoot, env: process.env });

    const runId = `RUN-${new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19)}`;
    const output = [];

    child.stdout.on("data", (chunk) => {
      output.push(chunk.toString());
    });
    child.stderr.on("data", (chunk) => {
      output.push(chunk.toString());
    });

    // Return immediately so the UI can poll, but also stream after completion
    // For simplicity we'll do synchronous version with timeout
    const result = await new Promise((resolve) => {
      const timeout = setTimeout(() => {
        try {
          child.kill("SIGTERM");
        } catch (_e) {
          // Ignore error if process already exited
        }
        resolve({ timeout: true, exitCode: -1, output });
      }, 180000); // 3 minute timeout

      child.on("exit", (code) => {
        clearTimeout(timeout);
        resolve({ timeout: false, exitCode: code, output });
      });
    });

    return sendSuccess(res, {
      run_id: runId,
      dry_run: dryRun,
      date: date || "auto",
      exit_code: result.exitCode,
      timeout: result.timeout || false,
      output: result.output.join(""),
    });
  } catch (error) {
    logger.error("Error in /algo/run:", {
      error: error.message,
      stack: error.stack,
    });
    return sendError(res, "An error occurred while running the algorithm", 500);
  }
});

// ============================================================
// RUN DATA PATROL â€” trigger watchdog from UI (admin only)
// ============================================================
router.post("/patrol", requireAuth, requireAdmin, async (req, res) => {
  const { spawn } = require("child_process");
  const path = require("path");

  try {
    const quick = req.body?.quick === true;
    const validateAlpaca = req.body?.validate_alpaca === true;

    const args = ["algo_data_patrol.py"];
    if (quick) args.push("--quick");
    if (validateAlpaca) args.push("--validate-alpaca");

    const repoRoot = path.resolve(__dirname, "../../..");
    const child = spawn("python3", args, { cwd: repoRoot, env: process.env });
    const output = [];

    const result = await new Promise((resolve) => {
      const timeout = setTimeout(() => {
        try {
          child.kill("SIGTERM");
        } catch (_e) {
          // Ignore error if process already exited
        }
        resolve({ timeout: true, exitCode: -1, output });
      }, 60000);

      child.stdout.on("data", (c) => output.push(c.toString()));
      child.stderr.on("data", (c) => output.push(c.toString()));
      child.on("exit", (code) => {
        clearTimeout(timeout);
        resolve({ timeout: false, exitCode: code, output });
      });
    });

    return sendSuccess(res, {
      ready_to_trade: result.exitCode === 0,
      exit_code: result.exitCode,
      output: result.output.join(""),
    });
  } catch (error) {
    logger.error("Error in /algo/patrol:", {
      error: error.message,
      stack: error.stack,
    });
    return sendError(res, "An error occurred while running data patrol", 500);
  }
});

// ============================================================
// PATROL HISTORY â€” recent patrol log entries (admin only)
// ============================================================
router.get("/patrol-log", requireAuth, requireAdmin, async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();
    const { limit } = paginationConfig.sanitize(
      req.query.limit,
      req.query.offset,
      "logs"
    );
    const minSeverity = req.query.min_severity || "warn";
    const sevOrder = { info: 0, warn: 1, error: 2, critical: 3 };
    const minSev = sevOrder[minSeverity] || 1;
    const allowedSevs = Object.keys(sevOrder).filter(
      (k) => sevOrder[k] >= minSev
    );

    const result = await pool.query(
      `SELECT id, patrol_run_id, check_name, severity, target_table, message,
              details, created_at
       FROM data_patrol_log
       WHERE severity = ANY($1)
       ORDER BY created_at DESC
       LIMIT $2`,
      [allowedSevs, limit]
    );

    // Validate result structure
    validateQueryResult(result, { requireRows: false });

    return sendSuccess(res, {
      items: validateAndCoerceRows(result, {
        id: { type: "int", required: true },
        patrol_run_id: { type: "string", required: false },
        check_name: { type: "string", required: false },
        severity: { type: "string", required: false },
        target_table: { type: "string", required: false },
        message: { type: "string", required: false },
        details: { type: "raw", required: false },
        created_at: { type: "date", required: false },
      }).map((r) => ({
        id: r.id,
        run_id: r.patrol_run_id,
        check_name: r.check_name,
        severity: r.severity,
        target_table: r.target_table,
        message: r.message,
        details: r.details,
        created_at: r.created_at,
      })),
    });
  } catch (error) {
    logger.error("Error in /algo/patrol-log:", {
      error: error.message,
      stack: error.stack,
    });
    return sendDatabaseError(
      res,
      error,
      "An error occurred while fetching patrol logs"
    );
  }
});

// ============================================================
// NOTIFICATIONS â€” surface CRITICAL events to UI as toasts
// ============================================================
router.get("/notifications", authenticateToken, async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();
    const { limit } = paginationConfig.sanitize(
      req.query.limit,
      req.query.offset,
      "logs"
    );
    const kind = req.query.kind || null;
    const severity = req.query.severity || null;
    const unread = req.query.unread === "true";

    let sql = `SELECT id, kind, severity, title, message, symbol, details, seen, created_at
               FROM algo_notifications
               WHERE 1=1`;
    const params = [];

    if (unread) {
      sql += ` AND seen = FALSE`;
    }
    if (kind && kind !== "all") {
      sql += ` AND kind = $${params.length + 1}`;
      params.push(kind);
    }
    if (severity && severity !== "all") {
      sql += ` AND severity = $${params.length + 1}`;
      params.push(severity);
    }

    sql += ` ORDER BY
               CASE severity
                 WHEN 'critical' THEN 1
                 WHEN 'error' THEN 2
                 WHEN 'warning' THEN 3
                 ELSE 4 END,
               created_at DESC
             LIMIT $${params.length + 1}`;
    params.push(limit);

    const result = await pool.query(sql, params);

    // Validate result structure
    validateQueryResult(result, { requireRows: false });

    return sendSuccess(res, {
      items: validateAndCoerceRows(result, {
        id: { type: "int", required: true },
        kind: { type: "string", required: false },
        severity: { type: "string", required: false },
        title: { type: "string", required: false },
        message: { type: "string", required: false },
        symbol: { type: "string", required: false },
        details: { type: "raw", required: false },
        seen: { type: "bool", required: false },
        created_at: { type: "date", required: false },
      }),
    });
  } catch (error) {
    logger.error("Error fetching notifications:", {
      error: error.message,
      stack: error.stack,
    });
    return sendDatabaseError(
      res,
      error,
      "An error occurred while fetching notifications"
    );
  }
});

// Mark single notification as read (PATCH)
router.patch(
  "/notifications/:id/read",
  authenticateToken,
  requireAdmin,
  async (req, res) => {
    try {
      ensureConnection();
      const pool = getPool();
      const { id } = req.params;
      const result = await pool.query(
        `UPDATE algo_notifications SET seen = TRUE, seen_at = CURRENT_TIMESTAMP WHERE id = $1`,
        [id]
      );
      return sendSuccess(res, {
        updated: result.rowCount,
        timestamp: new Date(),
      });
    } catch (error) {
      logger.error("Error marking notification as read:", {
        error: error.message,
        stack: error.stack,
      });
      return sendDatabaseError(
        res,
        error,
        "An error occurred while updating notification"
      );
    }
  }
);

// Delete single notification
router.delete(
  "/notifications/:id",
  authenticateToken,
  requireAdmin,
  async (req, res) => {
    try {
      ensureConnection();
      const pool = getPool();
      const { id } = req.params;
      const result = await pool.query(
        `DELETE FROM algo_notifications WHERE id = $1`,
        [id]
      );
      return sendSuccess(res, {
        deleted: result.rowCount,
        timestamp: new Date(),
      });
    } catch (error) {
      logger.error("Error deleting notification:", {
        error: error.message,
        stack: error.stack,
      });
      return sendDatabaseError(
        res,
        error,
        "An error occurred while deleting notification"
      );
    }
  }
);

// Batch mark as seen (legacy endpoint)
router.post("/notifications/seen", authenticateToken, async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();
    const ids = req.body?.ids || [];
    if (!Array.isArray(ids) || ids.length === 0) {
      return sendSuccess(res, { marked: 0 });
    }
    const result = await pool.query(
      `UPDATE algo_notifications SET seen = TRUE, seen_at = CURRENT_TIMESTAMP WHERE id = ANY($1)`,
      [ids]
    );
    return sendSuccess(res, { marked: result.rowCount, timestamp: new Date() });
  } catch (error) {
    logger.error("Error marking notifications as seen:", {
      error: error.message,
      stack: error.stack,
    });
    return sendDatabaseError(
      res,
      error,
      "An error occurred while updating notifications"
    );
  }
});

// PERFORMANCE METRICS â€” Sharpe, Sortino, Calmar, max DD, profit factor
// ============================================================
router.get("/performance", async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();

    // PHASE 1 FIX: Fetch pre-computed metrics from algo_performance_metrics (O(1) instead of O(N))
    // Instead of fetching all trades and snapshots and recalculating on every request,
    // use the pre-computed daily metrics from the loader.
    const perfResult = await pool.query(`
      SELECT
        total_trades, winning_trades, losing_trades,
        win_rate_pct,
        COALESCE(avg_win_pct, best_trade_pct) as avg_win_pct,
        COALESCE(avg_loss_pct, worst_trade_pct) as avg_loss_pct,
        NULL as avg_win_r, NULL as avg_loss_r,
        NULL as expectancy_r, profit_factor,
        total_pnl_dollars, NULL as gross_win_dollars, NULL as gross_loss_dollars, total_pnl_pct as total_return_pct,
        sharpe_ratio as sharpe_annualized,
        sortino_ratio as sortino_annualized,
        calmar_ratio, max_drawdown_pct,
        NULL as current_win_streak, best_win_streak, worst_loss_streak,
        avg_holding_days as avg_hold_days, NULL as portfolio_snapshots_count
      FROM algo_performance_metrics
      ORDER BY metric_date DESC LIMIT 1
    `);

    // E10 FIX: Include open positions in win rate calculation
    const openPosResult = await pool.query(`
      SELECT
        COUNT(*) as open_count,
        COUNT(*) FILTER (WHERE unrealized_pnl > 0) as open_wins,
        COUNT(*) FILTER (WHERE unrealized_pnl < 0) as open_losses,
        SUM(unrealized_pnl) as total_unrealized_pnl
      FROM algo_positions
      WHERE status IN ('open', 'partially_closed')
    `);

    // Validate result
    validateQueryResult(perfResult, { requireRows: false });

    // Extract open position stats
    const openStats = openPosResult.rows[0] || {
      open_count: 0,
      open_wins: 0,
      open_losses: 0,
      total_unrealized_pnl: 0,
    };

    if (perfResult.rows.length === 0) {
      // Fallback: data not yet computed for today, return empty metrics
      logger.warn(
        "No performance data computed for today; returning default metrics"
      );
      return sendSuccess(res, {
        total_trades: openStats.open_count,
        winning_trades: openStats.open_wins,
        losing_trades: openStats.open_losses,
        win_rate_pct:
          openStats.open_count > 0
            ? ((openStats.open_wins / openStats.open_count) * 100).toFixed(2)
            : 0,
        avg_win_pct: 0,
        avg_loss_pct: 0,
        avg_win_r: 0,
        avg_loss_r: 0,
        expectancy_r: 0,
        profit_factor: null,
        total_pnl_dollars: 0,
        gross_win_dollars: 0,
        gross_loss_dollars: 0,
        total_return_pct: 0,
        sharpe_annualized: null,
        sortino_annualized: null,
        calmar_ratio: null,
        max_drawdown_pct: null,
        current_streak: 0,
        best_win_streak: 0,
        worst_loss_streak: 0,
        avg_hold_days: 0,
        portfolio_snapshots: 0,
        open_positions: openStats.open_count,
        unrealized_pnl: openStats.total_unrealized_pnl !== null && openStats.total_unrealized_pnl !== undefined ? openStats.total_unrealized_pnl : null,
      });
    }

    const perf = validateAndCoerceRow(perfResult.rows[0], {
      total_trades: { type: "int", required: false },
      winning_trades: { type: "int", required: false },
      losing_trades: { type: "int", required: false },
      win_rate_pct: { type: "float", required: false },
      avg_win_pct: { type: "float", required: false },
      avg_loss_pct: { type: "float", required: false },
      avg_win_r: { type: "float", required: false },
      avg_loss_r: { type: "float", required: false },
      expectancy_r: { type: "float", required: false },
      profit_factor: { type: "float", required: false },
      total_pnl_dollars: { type: "float", required: false },
      gross_win_dollars: { type: "float", required: false },
      gross_loss_dollars: { type: "float", required: false },
      total_return_pct: { type: "float", required: false },
      sharpe_annualized: { type: "float", required: false },
      sortino_annualized: { type: "float", required: false },
      calmar_ratio: { type: "float", required: false },
      max_drawdown_pct: { type: "float", required: false },
      current_win_streak: { type: "int", required: false },
      best_win_streak: { type: "int", required: false },
      worst_loss_streak: { type: "int", required: false },
      avg_hold_days: { type: "float", required: false },
      portfolio_snapshots_count: {
        type: "int",
        required: false,
      },
    });

    // E10 FIX: Recalculate win_rate to include open positions
    // FAIL-FAST: Require explicit trade counts; don't default to 0
    const closedWins = perf.winning_trades !== null && perf.winning_trades !== undefined ? perf.winning_trades : null;
    const closedLosses = perf.losing_trades !== null && perf.losing_trades !== undefined ? perf.losing_trades : null;
    const openWins = openStats.open_wins !== null && openStats.open_wins !== undefined ? openStats.open_wins : null;
    const openLosses = openStats.open_losses !== null && openStats.open_losses !== undefined ? openStats.open_losses : null;

    // FAIL-FAST: Require all trade counts to calculate win rate; don't default to 0
    const hasCompleteTradeData = closedWins != null && closedLosses != null && openWins != null && openLosses != null;
    const totalTrades = hasCompleteTradeData ? closedWins + closedLosses + openWins + openLosses : null;
    const totalWins = hasCompleteTradeData ? closedWins + openWins : null;
    const winRateIncludingOpen = hasCompleteTradeData && totalTrades > 0
        ? parseFloat(((totalWins / totalTrades) * 100).toFixed(2))
        : (hasCompleteTradeData ? 0 : null);

    // CRITICAL: Validate essential risk metrics are present
    const criticalPerfMetrics = [
      "max_drawdown_pct",
      "sharpe_annualized",
      "total_pnl_dollars",
    ];
    const missingPerfCritical = criticalPerfMetrics.filter(
      (m) => perf[m] === null || perf[m] === undefined
    );
    if (missingPerfCritical.length > 0) {
      logger.error(`CRITICAL: Performance metrics incomplete. Missing: ${missingPerfCritical.join(", ")}`);
      // Still return response with available data but mark critical fields as null
    }

    return sendSuccess(res, {
      // Trade counts (closed + open)
      total_trades: totalTrades,
      winning_trades: totalWins,
      losing_trades: hasCompleteTradeData ? closedLosses + openLosses : null,
      closed_trades: perf.total_trades !== null && perf.total_trades !== undefined ? perf.total_trades : null,
      open_positions: openStats.open_count !== null && openStats.open_count !== undefined ? openStats.open_count : null,

      // Win/loss profile (including open positions)
      win_rate_pct: winRateIncludingOpen,
      closed_win_rate_pct: perf.win_rate_pct !== null && perf.win_rate_pct !== undefined ? parseFloat(perf.win_rate_pct) : null,
      avg_win_pct: perf.avg_win_pct !== null && perf.avg_win_pct !== undefined ? parseFloat(perf.avg_win_pct) : null,
      avg_loss_pct: perf.avg_loss_pct !== null && perf.avg_loss_pct !== undefined ? parseFloat(perf.avg_loss_pct) : null,
      avg_win_r: perf.avg_win_r !== null && perf.avg_win_r !== undefined ? parseFloat(perf.avg_win_r) : null,
      avg_loss_r: perf.avg_loss_r !== null && perf.avg_loss_r !== undefined ? parseFloat(perf.avg_loss_r) : null,

      // Expectancy
      expectancy_r: perf.expectancy_r !== null && perf.expectancy_r !== undefined ? parseFloat(perf.expectancy_r) : null,
      profit_factor: perf.profit_factor !== null && perf.profit_factor !== undefined ? parseFloat(perf.profit_factor) : null,

      // Total (CRITICAL: total_pnl must not default to 0)
      total_pnl_dollars: perf.total_pnl_dollars !== null && perf.total_pnl_dollars !== undefined ? parseFloat(perf.total_pnl_dollars) : null,
      unrealized_pnl: openStats.total_unrealized_pnl !== null && openStats.total_unrealized_pnl !== undefined ? openStats.total_unrealized_pnl : null,
      gross_win_dollars: perf.gross_win_dollars !== null && perf.gross_win_dollars !== undefined ? parseFloat(perf.gross_win_dollars) : null,
      gross_loss_dollars: perf.gross_loss_dollars !== null && perf.gross_loss_dollars !== undefined ? parseFloat(perf.gross_loss_dollars) : null,
      total_return_pct: perf.total_return_pct !== null && perf.total_return_pct !== undefined ? parseFloat(perf.total_return_pct) : null,

      // Risk-adjusted (CRITICAL: Use raw values to expose missing data)
      sharpe_annualized: perf.sharpe_annualized !== null && perf.sharpe_annualized !== undefined ? parseFloat(perf.sharpe_annualized) : null,
      sortino_annualized: perf.sortino_annualized !== null && perf.sortino_annualized !== undefined ? parseFloat(perf.sortino_annualized) : null,
      calmar_ratio: perf.calmar_ratio !== null && perf.calmar_ratio !== undefined ? parseFloat(perf.calmar_ratio) : null,
      max_drawdown_pct: perf.max_drawdown_pct !== null && perf.max_drawdown_pct !== undefined ? parseFloat(perf.max_drawdown_pct) : null,

      // Streaks + duration
      current_streak: perf.current_win_streak !== null && perf.current_win_streak !== undefined ? perf.current_win_streak : null,
      best_win_streak: perf.best_win_streak !== null && perf.best_win_streak !== undefined ? perf.best_win_streak : null,
      worst_loss_streak: perf.worst_loss_streak !== null && perf.worst_loss_streak !== undefined ? perf.worst_loss_streak : null,
      avg_hold_days: perf.avg_hold_days !== null && perf.avg_hold_days !== undefined ? parseFloat(perf.avg_hold_days) : null,

      // Sample sizes
      portfolio_snapshots: perf.portfolio_snapshots_count !== null && perf.portfolio_snapshots_count !== undefined ? perf.portfolio_snapshots_count : null,
    });
  } catch (error) {
    logger.error("Error in /api/algo/performance:", {
      error: error.message,
      stack: error.stack,
    });
    return sendDatabaseError(
      res,
      error,
      "An error occurred while fetching performance metrics"
    );
  }
});

/**
 * GET /api/algo/equity-curve
 * Time-series of portfolio value from algo_portfolio_snapshots
 * Used by Portfolio Dashboard equity-curve chart.
 */
router.get("/equity-curve", authenticateToken, async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();
    const { limit } = paginationConfig.sanitize(
      req.query.limit,
      req.query.offset,
      "portfolio"
    );
    const result = await pool.query(
      `
      SELECT snapshot_date, total_portfolio_value, daily_return_pct,
             unrealized_pnl_pct, position_count, max_drawdown_pct as drawdown_pct
      FROM algo_portfolio_snapshots
      ORDER BY snapshot_date DESC
      LIMIT $1
    `,
      [limit]
    );

    // Validate result structure
    validateQueryResult(result, { requireRows: false });

    // Validate and coerce row types - drawdown_pct now comes from DB
    const validated = validateAndCoerceRows(result, {
      snapshot_date: { type: "date", required: true },
      total_portfolio_value: {
        type: "float",
        required: false,
      },
      daily_return_pct: { type: "float", required: false },
      unrealized_pnl_pct: { type: "float", required: false },
      position_count: { type: "int", required: false },
      drawdown_pct: { type: "float", required: false },
    });

    // Reverse to chronological order (oldest first)
    const chronological = validated.reverse();

    return sendSuccess(res, {
      items: chronological,
    });
  } catch (error) {
    logger.error("Error in /algo/equity-curve:", {
      error: error.message,
      stack: error.stack,
    });
    return sendDatabaseError(
      res,
      error,
      "An error occurred while fetching equity curve"
    );
  }
});

// ============================================================
// AUDIT LOG â€” every algo decision logged (admin only)
// ============================================================
router.get("/audit-log", authenticateToken, async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();
    const { limit } = paginationConfig.sanitize(
      req.query.limit,
      req.query.offset,
      "audit"
    );
    const actionFilter = req.query.action_type || null;

    let query_str = `
      SELECT id, action_type, symbol, action_date, details, actor, status,
             error_message, created_at
      FROM algo_audit_log
    `;
    const params = [];
    if (actionFilter) {
      query_str += " WHERE action_type LIKE $1";
      params.push(`%${actionFilter}%`);
    }
    query_str += ` ORDER BY created_at DESC LIMIT $${params.length + 1}`;
    params.push(limit);

    const result = await pool.query(query_str, params);

    // Validate result structure
    validateQueryResult(result, { requireRows: false });

    return sendSuccess(res, {
      items: validateAndCoerceRows(result, {
        id: { type: "int", required: true },
        action_type: { type: "string", required: false },
        symbol: { type: "string", required: false },
        action_date: { type: "date", required: false },
        details: { type: "raw", required: false },
        actor: { type: "string", required: false },
        status: { type: "string", required: false },
        error_message: { type: "string", required: false },
        created_at: { type: "date", required: false },
      }).map((r) => ({
        id: r.id,
        action_type: r.action_type,
        symbol: r.symbol,
        action_date: r.action_date,
        details: r.details,
        actor: r.actor,
        status: r.status,
        error: r.error_message,
        created_at: r.created_at,
      })),
    });
  } catch (error) {
    logger.error("Error in /algo/audit-log:", {
      error: error.message,
      stack: error.stack,
    });
    return sendDatabaseError(
      res,
      error,
      "An error occurred while fetching audit logs"
    );
  }
});

// ============================================================
// TRADE DETAIL â€” full reasoning for a single trade
// ============================================================
router.get("/trade/:tradeId", async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();
    const result = await pool.query(
      `SELECT t.*, p.position_id, p.quantity AS current_qty, p.current_price,
              p.unrealized_pnl, p.unrealized_pnl_pct, p.target_levels_hit,
              p.current_stop_price
       FROM algo_trades t
       LEFT JOIN algo_positions p ON t.trade_id = ANY(p.trade_ids_arr)
                                 AND p.status = 'open'
       WHERE t.trade_id = $1`,
      [req.params.tradeId]
    );

    // Validate result structure
    validateQueryResult(result, { requireRows: false });

    if (result.rows.length === 0) {
      return sendError(res, "Trade not found", 404);
    }

    // Validate and coerce the single row
    const trade = validateAndCoerceRow(result.rows[0], {
      trade_id: { type: "int", required: true },
      symbol: { type: "string", required: false },
      entry_price: { type: "float", required: false },
      exit_price: { type: "float", required: false },
      profit_loss_dollars: { type: "float", required: false },
      profit_loss_pct: { type: "float", required: false },
      status: { type: "string", required: false },
      position_id: { type: "int", required: false },
      quantity: { type: "float", required: false },
      current_qty: { type: "float", required: false },
      current_price: { type: "float", required: false },
      unrealized_pnl: { type: "float", required: false },
      unrealized_pnl_pct: { type: "float", required: false },
      target_levels_hit: { type: "string", required: false },
      current_stop_price: { type: "float", required: false },
    });

    return sendSuccess(res, trade);
  } catch (error) {
    logger.error("Error in /algo/trade/:id:", {
      error: error.message,
      stack: error.stack,
    });
    return sendDatabaseError(
      res,
      error,
      "An error occurred while fetching trade details"
    );
  }
});

// ============================================================
// CIRCUIT BREAKERS â€” current state of all 7 kill-switches (admin only)
// ============================================================
router.get("/circuit-breakers", async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();

    // Fetch pre-computed circuit breaker metrics (computed daily at 4:30 PM ET by loaders/compute_circuit_breakers.py)
    const [cbResult, marketResult] = await Promise.all([
      pool.query(`
        SELECT
          portfolio_drawdown_pct, daily_loss_pct, weekly_loss_pct,
          open_risk_pct, consecutive_losses, vix_level, market_stage,
          spy_prior_day_change_pct, win_rate_last_30_pct
        FROM circuit_breaker_status
        WHERE check_date = CURRENT_DATE
        ORDER BY check_date DESC LIMIT 1
      `),
      pool.query(`
        SELECT market_trend FROM market_health_daily
        ORDER BY date DESC LIMIT 1
      `),
    ]);

    // Validate results
    validateQueryResult(cbResult, { requireRows: false });
    validateQueryResult(marketResult, { requireRows: false });

    // Get circuit breaker metrics - must have actual data, not defaults
    // CRITICAL: Do NOT default to 0 for circuit breaker metrics - it masks missing data
    // Zero drawdown looks like "safe portfolio" when data might just be unavailable
    if (cbResult.rows.length === 0) {
      return sendSuccess(res, {
        metrics: null,
        circuit_breakers: null,
        config: null,
        data_error: "circuit_breaker_data_unavailable",
        message: "Circuit breaker metrics not yet available. Run data loaders to compute portfolio metrics.",
      }, 503);
    }

    const cbRow = validateAndCoerceRow(cbResult.rows[0], {
      portfolio_drawdown_pct: {
        type: "float",
        required: false,
      },
      daily_loss_pct: { type: "float", required: false },
      weekly_loss_pct: {
        type: "float",
        required: false,
      },
      open_risk_pct: { type: "float", required: false },
      consecutive_losses: {
        type: "int",
        required: false,
      },
      vix_level: { type: "float", required: false },
      market_stage: { type: "int", required: false },
      spy_prior_day_change_pct: {
        type: "float",
        required: false,
      },
      win_rate_last_30_pct: {
        type: "float",
        required: false,
      },
    });

    const marketTrend =
      marketResult.rows.length > 0
        ? validateAndCoerceRow(marketResult.rows[0], {
            market_trend: { type: "string", required: false },
          }).market_trend || "unknown"
        : "unknown";

    const metrics = {
      current_drawdown_pct: cbRow.portfolio_drawdown_pct,
      daily_loss_pct: cbRow.daily_loss_pct,
      weekly_loss_pct: cbRow.weekly_loss_pct,
      consec_losses: cbRow.consecutive_losses,
      total_risk_pct: cbRow.open_risk_pct,
      vix_level: cbRow.vix_level,
      market_stage: cbRow.market_stage,
      market_trend: marketTrend,
    };

    // Pull config (with sensible defaults if rows missing)
    const cfgResult = await pool.query(
      `SELECT key, value FROM algo_config WHERE key = ANY($1)`,
      [
        [
          "halt_drawdown_pct",
          "max_daily_loss_pct",
          "max_consecutive_losses",
          "max_total_risk_pct",
          "vix_max_threshold",
          "max_weekly_loss_pct",
        ],
      ]
    );

    // Validate config result
    validateQueryResult(cfgResult, { requireRows: false });

    const cfg = {};
    validateAndCoerceRows(cfgResult, {
      key: { type: "string", required: true },
      value: { type: "string", required: true },
    }).forEach((r) => {
      cfg[r.key] = parseFloat(r.value);
    });
    const thresh = {
      drawdown: cfg.halt_drawdown_pct ?? 20,
      daily_loss: cfg.max_daily_loss_pct ?? 2,
      consecutive_losses: cfg.max_consecutive_losses ?? 3,
      total_risk: cfg.max_total_risk_pct ?? 4,
      vix_spike: cfg.vix_max_threshold ?? 35,
      weekly_loss: cfg.max_weekly_loss_pct ?? 5,
    };

    const breakers = [
      {
        id: "drawdown",
        label: "Portfolio Drawdown",
        current: metrics.current_drawdown_pct,
        threshold: thresh.drawdown,
        unit: "%",
        triggered: metrics.current_drawdown_pct >= thresh.drawdown,
        description:
          "Halts entries when total drawdown from peak exceeds threshold",
      },
      {
        id: "daily_loss",
        label: "Daily Loss",
        current: metrics.daily_loss_pct,
        threshold: thresh.daily_loss,
        unit: "%",
        triggered: metrics.daily_loss_pct >= thresh.daily_loss,
        description: "Today's portfolio drop below threshold halts new entries",
      },
      {
        id: "consecutive_losses",
        label: "Consecutive Losses",
        current: metrics.consec_losses,
        threshold: thresh.consecutive_losses,
        unit: "",
        triggered: metrics.consec_losses >= thresh.consecutive_losses,
        description: "Cool-off after streak of losing trades",
      },
      {
        id: "total_risk",
        label: "Total Open Risk",
        current: metrics.total_risk_pct,
        threshold: thresh.total_risk,
        unit: "%",
        triggered: metrics.total_risk_pct >= thresh.total_risk,
        description: "Sum of distance-to-stop across all open positions",
      },
      {
        id: "vix_spike",
        label: "VIX Spike",
        current: metrics.vix_level,
        threshold: thresh.vix_spike,
        unit: "",
        triggered: metrics.vix_level > thresh.vix_spike,
        description: "Volatility expansion above threshold pauses new entries",
      },
      {
        id: "market_stage",
        label: "Market Stage",
        current: metrics.market_stage,
        threshold: 4,
        unit: "",
        triggered: metrics.market_stage === 4,
        description: `Market in stage ${metrics.market_stage} (${metrics.market_trend}) â€” stage 4 = downtrend halts entries`,
      },
      {
        id: "weekly_loss",
        label: "Weekly Loss",
        current: metrics.weekly_loss_pct,
        threshold: thresh.weekly_loss,
        unit: "%",
        triggered: metrics.weekly_loss_pct >= thresh.weekly_loss,
        description:
          "Trailing 5-session loss above threshold halts new entries",
      },
    ];

    return sendSuccess(res, {
      any_triggered: breakers.some((b) => b.triggered),
      triggered_count: breakers.filter((b) => b.triggered).length,
      breakers,
    });
  } catch (error) {
    logger.error("Error in /algo/circuit-breakers:", {
      error: error.message,
      stack: error.stack,
    });
    return sendDatabaseError(
      res,
      error,
      "An error occurred while fetching circuit breaker status"
    );
  }
});

// ============================================================
// SECTOR BREADTH â€” % of stocks above 50d / 200d MA per sector
// ============================================================
router.get("/sector-breadth", async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();
    const result = await pool.query(`
      WITH latest_tt AS (
        SELECT DISTINCT ON (symbol) symbol, price_above_sma50, price_above_sma200
        FROM trend_template_data
        ORDER BY symbol, date DESC
      )
      SELECT
        cp.sector,
        COUNT(*) AS total_stocks,
        SUM(CASE WHEN lt.price_above_sma50 THEN 1 ELSE 0 END) AS above_50d,
        SUM(CASE WHEN lt.price_above_sma200 THEN 1 ELSE 0 END) AS above_200d,
        ROUND(100.0 * SUM(CASE WHEN lt.price_above_sma50 THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 1) AS pct_above_50d,
        ROUND(100.0 * SUM(CASE WHEN lt.price_above_sma200 THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 1) AS pct_above_200d
      FROM company_profile cp
      JOIN latest_tt lt ON lt.symbol = cp.ticker
      WHERE cp.sector IS NOT NULL AND TRIM(cp.sector) <> ''
      GROUP BY cp.sector
      HAVING COUNT(*) > 5
      ORDER BY cp.sector
    `);

    // Validate result structure
    validateQueryResult(result, { requireRows: false });

    return sendSuccess(res, {
      items: validateAndCoerceRows(result, {
        sector: { type: "string", required: true },
        total_stocks: { type: "int", required: false },
        above_50d: { type: "int", required: false },
        above_200d: { type: "int", required: false },
        pct_above_50d: { type: "float", required: false },
        pct_above_200d: { type: "float", required: false },
      }).map((r) => ({
        sector: r.sector,
        total_stocks: r.total_stocks !== null && r.total_stocks !== undefined ? r.total_stocks : null,
        above_50d: r.above_50d !== null && r.above_50d !== undefined ? r.above_50d : null,
        above_200d: r.above_200d !== null && r.above_200d !== undefined ? r.above_200d : null,
        pct_above_50d: r.pct_above_50d !== null && r.pct_above_50d !== undefined ? r.pct_above_50d : null,
        pct_above_200d: r.pct_above_200d !== null && r.pct_above_200d !== undefined ? r.pct_above_200d : null,
      })),
    });
  } catch (error) {
    logger.error("Error in /algo/sector-breadth:", {
      error: error.message,
      stack: error.stack,
    });
    return sendDatabaseError(
      res,
      error,
      "An error occurred while calculating sector breadth"
    );
  }
});

// ============================================================
// SECTOR STAGE-2 LEADERS â€” Stage 2 stocks per sector
// ============================================================
router.get("/sector-stage2", async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();
    const result = await pool.query(`
      WITH latest_tt AS (
        SELECT DISTINCT ON (symbol) symbol, weinstein_stage, minervini_trend_score
        FROM trend_template_data
        ORDER BY symbol, date DESC
      )
      SELECT
        cp.sector,
        COUNT(*) AS total_stocks,
        SUM(CASE WHEN lt.weinstein_stage = 2 THEN 1 ELSE 0 END) AS stage_2,
        SUM(CASE WHEN lt.weinstein_stage = 1 THEN 1 ELSE 0 END) AS stage_1,
        SUM(CASE WHEN lt.weinstein_stage = 3 THEN 1 ELSE 0 END) AS stage_3,
        SUM(CASE WHEN lt.weinstein_stage = 4 THEN 1 ELSE 0 END) AS stage_4,
        AVG(lt.minervini_trend_score) AS avg_trend_score,
        ROUND(100.0 * SUM(CASE WHEN lt.weinstein_stage = 2 THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 1) AS pct_stage_2
      FROM company_profile cp
      JOIN latest_tt lt ON lt.symbol = cp.ticker
      WHERE cp.sector IS NOT NULL AND TRIM(cp.sector) <> ''
      GROUP BY cp.sector
      HAVING COUNT(*) > 5
      ORDER BY stage_2 DESC
    `);

    // Validate result structure
    validateQueryResult(result, { requireRows: false });

    return sendSuccess(res, {
      items: validateAndCoerceRows(result, {
        sector: { type: "string", required: true },
        total_stocks: { type: "int", required: false },
        stage_1: { type: "int", required: false },
        stage_2: { type: "int", required: false },
        stage_3: { type: "int", required: false },
        stage_4: { type: "int", required: false },
        avg_trend_score: { type: "float", required: false },
        pct_stage_2: { type: "float", required: false },
      }).map((r) => ({
        sector: r.sector,
        total: r.total_stocks !== null && r.total_stocks !== undefined ? r.total_stocks : null,
        stage_1: r.stage_1 !== null && r.stage_1 !== undefined ? r.stage_1 : null,
        stage_2: r.stage_2 !== null && r.stage_2 !== undefined ? r.stage_2 : null,
        stage_3: r.stage_3 !== null && r.stage_3 !== undefined ? r.stage_3 : null,
        stage_4: r.stage_4 !== null && r.stage_4 !== undefined ? r.stage_4 : null,
        pct_stage_2: r.pct_stage_2 !== null && r.pct_stage_2 !== undefined ? r.pct_stage_2 : null,
        avg_trend_score: r.avg_trend_score,
      })),
    });
  } catch (error) {
    logger.error("Error in /algo/sector-stage2:", {
      error: error.message,
      stack: error.stack,
    });
    return sendDatabaseError(
      res,
      error,
      "An error occurred while analyzing sector stage 2 leaders"
    );
  }
});

// ============================================================
// SECTOR ROTATION SIGNAL â€” defensive vs cyclical leadership timeline
// ============================================================
router.get("/sector-rotation", async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();
    const { limit } = paginationConfig.sanitize(
      req.query.limit,
      req.query.offset,
      "security"
    );

    const result = await pool.query(
      `SELECT date, sector, signal, strength, rank, details
       FROM sector_rotation_signal
       ORDER BY date DESC, rank ASC NULLS LAST LIMIT $1`,
      [limit]
    );

    // Validate result structure
    validateQueryResult(result, { requireRows: false });

    const parseDetailsJSON = (details) => {
      if (!details) return null;
      if (typeof details === "object") return details;
      if (typeof details !== "string") {
        throw new Error(`Invalid details type: expected string or object, got ${typeof details}`);
      }
      try {
        return JSON.parse(details);
      } catch (e) {
        throw new Error(
          `Failed to parse sector_rotation_signal details: ${details.substring(0, 100)}. ${e.message}`
        );
      }
    };

    return sendSuccess(res, {
      items: validateAndCoerceRows(result, {
        date: { type: "date", required: false },
        sector: { type: "string", required: false },
        signal: { type: "string", required: false },
        strength: { type: "float", required: false },
        rank: { type: "int", required: false },
        details: { type: "raw", required: false },
      }).map((r) => ({
        date: r.date,
        sector: r.sector,
        signal: r.signal,
        strength: r.strength !== null && r.strength !== undefined ? r.strength : null,
        rank: r.rank,
        ...parseDetailsJSON(r.details),
      })),
    });
  } catch (error) {
    logger.error("Error in /algo/sector-rotation:", {
      error: error.message,
      stack: error.stack,
    });
    return sendDatabaseError(
      res,
      error,
      "An error occurred while analyzing sector rotation"
    );
  }
});

/**
 * GET /api/algo/sector-position-warnings
 * Get sector position concentration warnings (sector allocation alerts)
 */
router.get("/sector-position-warnings", async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();

    // Fetch sector position counts for open positions
    const sectorResult = await pool.query(`
      SELECT cp.sector, COUNT(DISTINCT ap.symbol) as position_count
      FROM algo_positions ap
      LEFT JOIN company_profile cp ON ap.symbol = cp.ticker
      WHERE ap.status = 'open' AND ap.quantity > 0
      GROUP BY cp.sector
      ORDER BY position_count DESC
    `);

    validateQueryResult(sectorResult, { requireRows: false });

    // Get configuration for max positions per sector
    const configResult = await pool.query(`
      SELECT value FROM algo_config WHERE key = 'max_positions_per_sector' LIMIT 1
    `);

    let max_per_sector = 3; // default
    if (
      configResult.rows &&
      configResult.rows.length > 0 &&
      configResult.rows[0].value
    ) {
      max_per_sector = parseInt(configResult.rows[0].value, 10);
    }

    const sector_counts = sectorResult.rows || [];
    const warnings = [];
    const at_cap = [];

    for (const row of sector_counts) {
      const sector = row.sector || "Unknown";
      const count = row.position_count !== null && row.position_count !== undefined ? row.position_count : 0;

      if (count >= max_per_sector) {
        at_cap.push({
          sector: sector,
          position_count: count,
          max: max_per_sector,
          status: "AT_CAP",
        });
      } else if (count >= max_per_sector - 1) {
        warnings.push({
          sector: sector,
          position_count: count,
          max: max_per_sector,
          status: "NEAR_CAP",
        });
      }
    }

    return sendSuccess(res, {
      warnings: warnings,
      at_cap: at_cap,
    });
  } catch (error) {
    logger.error("Error in /algo/sector-position-warnings:", {
      error: error.message,
      stack: error.stack,
    });
    return sendDatabaseError(
      res,
      error,
      "An error occurred while fetching sector position warnings"
    );
  }
});

// ============================================================
// PHASE 1-4 INTEGRATION: Data Quality, Signal Performance, Rejections, Orders
// ============================================================

/**
 * GET /api/algo/data-quality
 * Loader SLA status - check data freshness
 */
router.get("/data-quality", async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();
    const result = await pool.query(`
      SELECT
        loader_name,
        table_name,
        latest_data_date,
        ROUND((EXTRACT(EPOCH FROM (NOW() - TO_TIMESTAMP(latest_data_date, 'YYYY-MM-DD'))) / 3600)::numeric, 1) as age_hours,
        max_age_hours,
        row_count_today,
        status,
        error_message
      FROM loader_sla_status
      ORDER BY status ASC, last_check_at DESC
    `);

    // Validate result structure
    validateQueryResult(result, { requireRows: false });

    const checks = validateAndCoerceRows(result, {
      loader_name: { type: "string", required: true },
      table_name: { type: "string", required: true },
      latest_data_date: { type: "string", required: false },
      age_hours: { type: "float", required: false },
      max_age_hours: { type: "int", required: false },
      row_count_today: { type: "int", required: false },
      status: { type: "string", required: false },
      error_message: { type: "string", required: false },
    }).map((r) => ({
      loader: r.loader_name,
      table: r.table_name,
      latest_date: r.latest_data_date,
      age_hours: r.age_hours !== null && r.age_hours !== undefined ? r.age_hours : null,
      max_age_hours: r.max_age_hours,
      row_count: r.row_count_today,
      status: r.status,
      error_message: r.error_message,
    }));

    const overall_status = checks.some((c) => c.status === "CRITICAL")
      ? "critical"
      : checks.some((c) => c.status === "WARNING")
        ? "warning"
        : "ok";

    return sendSuccess(res, { status: overall_status, checks });
  } catch (error) {
    logger.error("Error in /algo/data-quality:", {
      error: error.message,
      stack: error.stack,
    });
    return sendDatabaseError(
      res,
      error,
      "An error occurred while checking data quality"
    );
  }
});

/**
 * GET /api/algo/rejection-funnel?date=2026-05-06
 * Signal rejection funnel analysis
 */
router.get("/rejection-funnel", async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();
    let eval_date = req.query.date;
    if (!eval_date) {
      eval_date = new Date().toISOString().split("T")[0];
    } else if (!/^\d{4}-\d{2}-\d{2}$/.test(eval_date)) {
      return sendError(res, "Invalid date format. Expected YYYY-MM-DD", 400);
    }

    const result = await pool.query(
      `
      WITH tier_counts AS (
        SELECT
          COUNT(*) as total,
          SUM(CASE WHEN tier_1_pass THEN 1 ELSE 0 END) as t1_pass,
          SUM(CASE WHEN tier_2_pass THEN 1 ELSE 0 END) as t2_pass,
          SUM(CASE WHEN tier_3_pass THEN 1 ELSE 0 END) as t3_pass,
          SUM(CASE WHEN tier_4_pass THEN 1 ELSE 0 END) as t4_pass,
          SUM(CASE WHEN tier_5_pass THEN 1 ELSE 0 END) as t5_pass
        FROM filter_rejection_log
        WHERE eval_date = $1::DATE
      )
      SELECT
        total,
        t1_pass,
        t2_pass,
        t3_pass,
        t4_pass,
        t5_pass,
        (total - t1_pass) as t1_reject,
        (t1_pass - t2_pass) as t2_reject,
        (t2_pass - t3_pass) as t3_reject,
        (t3_pass - t4_pass) as t4_reject,
        (t4_pass - t5_pass) as t5_reject
      FROM tier_counts
    `,
      [eval_date]
    );

    // Validate result structure
    validateQueryResult(result, { requireRows: false });

    const row = result.rows[0]
      ? validateAndCoerceRow(result.rows[0], {
          total: { type: "int", required: false, defaultValue: 0 },
          t1_pass: { type: "int", required: false, defaultValue: 0 },
          t2_pass: { type: "int", required: false, defaultValue: 0 },
          t3_pass: { type: "int", required: false, defaultValue: 0 },
          t4_pass: { type: "int", required: false, defaultValue: 0 },
          t5_pass: { type: "int", required: false, defaultValue: 0 },
          t1_reject: { type: "int", required: false, defaultValue: 0 },
          t2_reject: { type: "int", required: false, defaultValue: 0 },
          t3_reject: { type: "int", required: false, defaultValue: 0 },
          t4_reject: { type: "int", required: false, defaultValue: 0 },
          t5_reject: { type: "int", required: false, defaultValue: 0 },
        })
      : {
          total: 0,
          t1_pass: 0,
          t2_pass: 0,
          t3_pass: 0,
          t4_pass: 0,
          t5_pass: 0,
          t1_reject: 0,
          t2_reject: 0,
          t3_reject: 0,
          t4_reject: 0,
          t5_reject: 0,
        };

    return sendSuccess(res, {
      date: eval_date,
      total_signals: row.total !== null && row.total !== undefined ? row.total : null,
      tiers: [
        {
          tier: 1,
          name: "Data Quality",
          pass: row.t1_pass !== null && row.t1_pass !== undefined ? row.t1_pass : null,
          reject: row.t1_reject !== null && row.t1_reject !== undefined ? row.t1_reject : null,
        },
        {
          tier: 2,
          name: "Market Health",
          pass: row.t2_pass !== null && row.t2_pass !== undefined ? row.t2_pass : null,
          reject: row.t2_reject !== null && row.t2_reject !== undefined ? row.t2_reject : null,
        },
        {
          tier: 3,
          name: "Trend Confirmation",
          pass: row.t3_pass !== null && row.t3_pass !== undefined ? row.t3_pass : null,
          reject: row.t3_reject !== null && row.t3_reject !== undefined ? row.t3_reject : null,
        },
        {
          tier: 4,
          name: "Signal Quality",
          pass: row.t4_pass !== null && row.t4_pass !== undefined ? row.t4_pass : null,
          reject: row.t4_reject !== null && row.t4_reject !== undefined ? row.t4_reject : null,
        },
        {
          tier: 5,
          name: "Portfolio Health",
          pass: row.t5_pass !== null && row.t5_pass !== undefined ? row.t5_pass : null,
          reject: row.t5_reject !== null && row.t5_reject !== undefined ? row.t5_reject : null,
        },
      ],
    });
  } catch (error) {
    logger.error("Error in /algo/rejection-funnel:", {
      error: error.message,
      stack: error.stack,
    });
    return sendDatabaseError(
      res,
      error,
      "An error occurred while analyzing rejection funnel"
    );
  }
});

/**
 * GET /api/algo/orders/pending
 * Pre-execution order review
 */
router.get("/orders/pending", authenticateToken, async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();
    const [ordersResult, totalsResult] = await Promise.all([
      pool.query(`
        SELECT
          id, trade_id, symbol, order_type, side, requested_shares, requested_price,
          order_timestamp
        FROM order_execution_log
        WHERE order_status IN ('pending', 'submitted')
        ORDER BY order_timestamp DESC
        LIMIT 20
      `),
      pool.query(`
        SELECT
          COUNT(*) as order_count,
          ROUND(SUM(CASE WHEN side = 'BUY' THEN requested_shares * requested_price ELSE 0 END), 2) as total_buy_value
        FROM order_execution_log
        WHERE order_status IN ('pending', 'submitted')
      `),
    ]);

    // Validate result structures
    validateQueryResult(ordersResult, { requireRows: false });
    validateQueryResult(totalsResult, { minRows: 1, maxRows: 1 });

    const pending_orders = validateAndCoerceRows(ordersResult, {
      id: { type: "int", required: true },
      trade_id: { type: "int", required: false },
      symbol: { type: "string", required: true },
      order_type: { type: "string", required: false },
      side: { type: "string", required: false },
      requested_shares: { type: "float", required: false },
      requested_price: { type: "float", required: false },
      order_timestamp: { type: "date", required: false },
    }).map((r) => ({
      order_id: r.id,
      trade_id: r.trade_id,
      symbol: r.symbol,
      order_type: r.order_type,
      side: r.side,
      requested_shares: r.requested_shares,
      requested_price: r.requested_price !== null && r.requested_price !== undefined ? r.requested_price : null,
      order_timestamp: r.order_timestamp,
    }));

    const totals = validateAndCoerceRow(totalsResult.rows[0], {
      order_count: { type: "int", required: false },
      total_buy_value: { type: "float", required: false },
    });

    return sendSuccess(res, {
      pending_orders,
      total_pending_value: totals.total_buy_value !== null && totals.total_buy_value !== undefined ? totals.total_buy_value : null,
      approval_required: totals.order_count > 0,
    });
  } catch (error) {
    logger.error("Error in /algo/orders/pending:", {
      error: error.message,
      stack: error.stack,
    });
    return sendDatabaseError(
      res,
      error,
      "An error occurred while fetching pending orders"
    );
  }
});

/**
 * GET /api/algo/execution-quality?days=30
 * Execution metrics: fill rate, slippage, etc.
 */
router.get("/execution-quality", authenticateToken, async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();
    const parsedDays = parseInt(req.query.days);
    const days = Math.min(Math.max(!isNaN(parsedDays) ? parsedDays : 30, 1), 365); // Clamp to [1, 365]

    const result = await pool.query(
      `
      SELECT
        COUNT(*) as total_orders,
        SUM(CASE WHEN order_status = 'filled' THEN 1 ELSE 0 END) as filled,
        SUM(CASE WHEN order_status = 'rejected' THEN 1 ELSE 0 END) as rejected,
        SUM(CASE WHEN order_status = 'partial' THEN 1 ELSE 0 END) as partial,
        ROUND(AVG(fill_rate_pct)::numeric, 2) as avg_fill_rate,
        ROUND(AVG(ABS(slippage_bps))::numeric, 2) as avg_slippage_bps,
        ROUND(MAX(ABS(slippage_bps))::numeric, 2) as max_slippage_bps,
        ROUND(AVG(ABS(slippage_bps))::numeric, 2) > 100 as slippage_alert
      FROM order_execution_log
      WHERE order_timestamp >= NOW() - MAKE_INTERVAL(days => $1)
    `,
      [days]
    );

    // Validate result structure
    validateQueryResult(result, { minRows: 1, maxRows: 1 });

    const row = validateAndCoerceRow(result.rows[0], {
      total_orders: { type: "int", required: false },
      filled: { type: "int", required: false },
      rejected: { type: "int", required: false },
      partial: { type: "int", required: false },
      avg_fill_rate: { type: "float", required: false },
      avg_slippage_bps: { type: "float", required: false },
      max_slippage_bps: { type: "float", required: false },
      slippage_alert: { type: "bool", required: false },
    });

    const metrics = {
      period: `last ${days} days`,
      total_orders: row.total_orders !== null && row.total_orders !== undefined ? row.total_orders : null,
      filled: row.filled !== null && row.filled !== undefined ? row.filled : null,
      rejected: row.rejected !== null && row.rejected !== undefined ? row.rejected : null,
      partial: row.partial !== null && row.partial !== undefined ? row.partial : null,
      fill_rate_pct: row.avg_fill_rate !== null && row.avg_fill_rate !== undefined ? row.avg_fill_rate : null,
      avg_slippage_bps: row.avg_slippage_bps !== null && row.avg_slippage_bps !== undefined ? row.avg_slippage_bps : null,
      max_slippage_bps: row.max_slippage_bps !== null && row.max_slippage_bps !== undefined ? row.max_slippage_bps : null,
      slippage_alert: row.slippage_alert !== null && row.slippage_alert !== undefined ? row.slippage_alert : false,
    };

    return sendSuccess(res, { metrics });
  } catch (error) {
    logger.error("Error in /algo/execution-quality:", {
      error: error.message,
      stack: error.stack,
    });
    return sendDatabaseError(
      res,
      error,
      "An error occurred while analyzing execution quality"
    );
  }
});

/**
 * GET /api/algo/signal-performance-by-pattern
 * Analyze trade performance grouped by signal pattern/type
 */
router.get("/signal-performance-by-pattern", async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();
    const result = await pool.query(`
      SELECT
        COALESCE(base_type, 'Unknown') as pattern,
        COUNT(*) as total_trades,
        SUM(CASE WHEN status = 'closed' AND profit_loss_dollars > 0 THEN 1 ELSE 0 END) as winning_trades,
        SUM(CASE WHEN status = 'closed' AND profit_loss_dollars < 0 THEN 1 ELSE 0 END) as losing_trades,
        COUNT(*) FILTER (WHERE status = 'closed') as closed_trades,
        ROUND(AVG(CASE WHEN status = 'closed' THEN profit_loss_pct ELSE NULL END)::numeric, 2) as avg_return_pct,
        ROUND(SUM(profit_loss_dollars)::numeric, 2) as total_pnl,
        ROUND((SUM(CASE WHEN status = 'closed' AND profit_loss_dollars > 0 THEN 1 ELSE 0 END)::float /
               NULLIF(COUNT(*) FILTER (WHERE status = 'closed'), 0) * 100)::numeric, 1) as win_rate_pct
      FROM algo_trades
      WHERE trade_date >= CURRENT_DATE - INTERVAL '90 days'
      GROUP BY base_type
      ORDER BY total_trades DESC
    `);

    // Validate result structure
    validateQueryResult(result, { requireRows: false });

    const patterns = validateAndCoerceRows(result, {
      pattern: { type: "string", required: false, defaultValue: "Unknown" },
      total_trades: { type: "int", required: false },
      winning_trades: { type: "int", required: false },
      losing_trades: { type: "int", required: false },
      closed_trades: { type: "int", required: false },
      avg_return_pct: { type: "float", required: false },
      total_pnl: { type: "float", required: false },
      win_rate_pct: { type: "float", required: false },
    }).map((r) => ({
      pattern: r.pattern,
      total_trades: r.total_trades !== null && r.total_trades !== undefined ? r.total_trades : null,
      winning_trades: r.winning_trades !== null && r.winning_trades !== undefined ? r.winning_trades : null,
      losing_trades: r.losing_trades !== null && r.losing_trades !== undefined ? r.losing_trades : null,
      closed_trades: r.closed_trades !== null && r.closed_trades !== undefined ? r.closed_trades : null,
      avg_return_pct: r.avg_return_pct !== null && r.avg_return_pct !== undefined ? r.avg_return_pct : null,
      total_pnl: r.total_pnl !== null && r.total_pnl !== undefined ? r.total_pnl : null,
      win_rate_pct: r.win_rate_pct !== null && r.win_rate_pct !== undefined ? r.win_rate_pct : null,
    }));

    return sendSuccess(res, { patterns, timestamp: new Date() }, 200);
  } catch (error) {
    logger.error("Error in /algo/signal-performance-by-pattern:", {
      error: error.message,
      stack: error.stack,
    });
    return sendDatabaseError(
      res,
      error,
      "An error occurred while analyzing signal performance"
    );
  }
});

/**
 * GET /api/algo/daily-return-histogram
 * Computes daily return histogram on-the-fly from algo_portfolio_snapshots.
 */
router.get("/daily-return-histogram", authenticateToken, async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();
    const result = await pool.query(`
      SELECT daily_return_pct
      FROM algo_portfolio_snapshots
      WHERE daily_return_pct IS NOT NULL
      ORDER BY snapshot_date DESC
      LIMIT 250
    `);

    const returns = result.rows
      .map((r) => parseFloat(r.daily_return_pct))
      .filter((v) => !isNaN(v));
    // FAIL-FAST: No valid return data means we can't compute performance histogram
    if (returns.length === 0) {
      return sendError(res, "[RETURN_DATA_UNAVAILABLE] No valid daily return data available to compute histogram", 503);
    }

    const BW = 0.5;
    const minB = Math.floor(Math.min(...returns) / BW) * BW;
    const maxB = Math.ceil(Math.max(...returns) / BW) * BW;
    const bucketsMap = {};
    for (
      let mid = minB;
      mid <= maxB + 0.001;
      mid = Math.round((mid + BW) * 1000) / 1000
    ) {
      bucketsMap[mid] = 0;
    }
    for (const r of returns) {
      const mid = Math.round(r / BW) * BW;
      if (mid in bucketsMap) bucketsMap[mid]++;
    }
    const buckets = Object.entries(bucketsMap).map(([mid, count]) => ({
      mid: parseFloat(mid),
      count,
    }));
    const mean = returns.reduce((s, v) => s + v, 0) / returns.length;
    const std = Math.sqrt(
      returns.reduce((s, v) => s + (v - mean) ** 2, 0) / returns.length
    );
    return sendSuccess(res, {
      buckets,
      stats: {
        count: returns.length,
        mean: parseFloat(mean.toFixed(2)),
        std: parseFloat(std.toFixed(2)),
      },
    });
  } catch (error) {
    logger.error("Error in /api/algo/daily-return-histogram:", {
      error: error.message,
    });
    // FAIL-FAST: Return error response, not success with error marker
    return sendError(res, `[HISTOGRAM_COMPUTATION_FAILED] ${error.message}`, 500);
  }
});

/**
 * GET /api/algo/trade-distribution
 * Computes trade R-multiple distribution on-the-fly from algo_trades.
 */
router.get("/trade-distribution", authenticateToken, async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();
    const result = await pool.query(`
      SELECT exit_r_multiple
      FROM algo_trades
      WHERE exit_r_multiple IS NOT NULL AND status = 'closed'
      ORDER BY exit_date DESC LIMIT 500
    `);

    const rValues = result.rows
      .map((r) => parseFloat(r.exit_r_multiple))
      .filter((v) => !isNaN(v));
    // FAIL-FAST: No trade data means we can't compute R-multiple histogram
    if (rValues.length === 0) {
      return sendError(res, "[TRADE_DATA_UNAVAILABLE] No valid trade R-multiple data available", 503);
    }

    const buckets = [
      { range: "<-2R", count: 0 },
      { range: "-2R to -1R", count: 0 },
      { range: "-1R to 0R", count: 0 },
      { range: "0R to 1R", count: 0 },
      { range: "1R to 2R", count: 0 },
      { range: "2R to 3R", count: 0 },
      { range: ">3R", count: 0 },
    ];
    for (const r of rValues) {
      if (r < -2) buckets[0].count++;
      else if (r < -1) buckets[1].count++;
      else if (r < 0) buckets[2].count++;
      else if (r < 1) buckets[3].count++;
      else if (r < 2) buckets[4].count++;
      else if (r < 3) buckets[5].count++;
      else buckets[6].count++;
    }
    return sendSuccess(res, {
      buckets: buckets.filter((b) => b.count > 0),
      total_trades: rValues.length,
    });
  } catch (error) {
    logger.error("Error in /api/algo/trade-distribution:", {
      error: error.message,
      stack: error.stack,
    });
    return sendDatabaseError(
      res,
      error,
      "An error occurred while computing trade distribution"
    );
  }
});

/**
 * GET /api/algo/holding-period-distribution
 * Computes holding period distribution on-the-fly from algo_trades.
 */
router.get(
  "/holding-period-distribution",
  authenticateToken,
  async (req, res) => {
    try {
      ensureConnection();
      const pool = getPool();
      const result = await pool.query(`
      SELECT trade_duration_days
      FROM algo_trades
      WHERE trade_duration_days IS NOT NULL AND status = 'closed' AND exit_date IS NOT NULL
      ORDER BY exit_date DESC LIMIT 500
    `);

      const durations = result.rows
        .map((r) => parseInt(r.trade_duration_days))
        .filter((v) => !isNaN(v));
      // FAIL-FAST: No trade duration data means we can't compute histogram
      if (durations.length === 0) {
        return sendError(res, "[TRADE_DURATION_UNAVAILABLE] No valid trade duration data available", 503);
      }

      const buckets = [
        { range: "1-3 days", count: 0 },
        { range: "4-7 days", count: 0 },
        { range: "8-14 days", count: 0 },
        { range: "15-30 days", count: 0 },
        { range: "31-60 days", count: 0 },
        { range: "61-90 days", count: 0 },
        { range: "91-180 days", count: 0 },
        { range: ">180 days", count: 0 },
      ];
      for (const d of durations) {
        if (d <= 3) buckets[0].count++;
        else if (d <= 7) buckets[1].count++;
        else if (d <= 14) buckets[2].count++;
        else if (d <= 30) buckets[3].count++;
        else if (d <= 60) buckets[4].count++;
        else if (d <= 90) buckets[5].count++;
        else if (d <= 180) buckets[6].count++;
        else buckets[7].count++;
      }
      return sendSuccess(res, {
        buckets: buckets.filter((b) => b.count > 0),
        total_trades: durations.length,
      });
    } catch (error) {
      logger.error("Error in /api/algo/holding-period-distribution:", {
        error: error.message,
        stack: error.stack,
      });
      return sendDatabaseError(
        res,
        error,
        "An error occurred while computing holding period distribution"
      );
    }
  }
);

/**
 * GET /api/algo/stage-distribution
 * Stage phase distribution across open positions
 */
router.get("/stage-distribution", authenticateToken, async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();
    const configResult = await pool.query(`
      SELECT key, value FROM algo_config
      WHERE key IN ('stage_2_early_min_score', 'stage_2_mid_min_score', 'stage_2_late_min_score')
    `);
    const posResult = await pool.query(`
      SELECT weinstein_stage, minervini_trend_score
      FROM algo_positions_with_risk
      WHERE status = 'open'
    `);

    validateQueryResult(configResult, { requireRows: false });
    validateQueryResult(posResult, { requireRows: false });

    // CRITICAL: Stage thresholds must come from database. Hardcoded defaults would
    // allow incorrect stage distribution reporting across positions.
    const stageConfig = {
      stage_2_early_min_score: null,
      stage_2_mid_min_score: null,
      stage_2_late_min_score: null,
    };
    if (configResult.rows && configResult.rows.length > 0) {
      for (const row of configResult.rows) {
        const val = parseFloat(row.value);
        if (!isNaN(val)) {
          stageConfig[row.key] = val;
        }
      }
    }

    // Validate all required stage thresholds are configured
    if (
      stageConfig.stage_2_early_min_score === null ||
      stageConfig.stage_2_mid_min_score === null ||
      stageConfig.stage_2_late_min_score === null
    ) {
      return sendError(
        res,
        503,
        "CRITICAL: Stage threshold configuration incomplete. " +
          "Cannot compute position stage distribution without configured thresholds. " +
          "Check algo_config for stage_2_early_min_score, stage_2_mid_min_score, stage_2_late_min_score."
      );
    }

    const order = [
      "Early Stage-2",
      "Mid Stage-2",
      "Late Stage-2",
      "Stage 1 (base)",
      "Stage 3 (top)",
      "Stage 4 (down)",
      "Unknown",
    ];

    // Initialize counts with explicit 0 values to avoid || 0 antipattern
    const counts = Object.fromEntries(order.map(label => [label, 0]));

    for (const row of posResult.rows) {
      const stage = row.weinstein_stage;
      const score = row.minervini_trend_score;
      let label = "Unknown";
      if (stage === 1) {
        label = "Stage 1 (base)";
      } else if (stage === 2) {
        if (score != null) {
          if (score >= stageConfig.stage_2_late_min_score)
            label = "Late Stage-2";
          else if (score >= stageConfig.stage_2_mid_min_score)
            label = "Mid Stage-2";
          else if (score >= stageConfig.stage_2_early_min_score)
            label = "Early Stage-2";
          else label = "Early Stage-2";
        } else {
          label = "Stage 2";
        }
      } else if (stage === 3) {
        label = "Stage 3 (top)";
      } else if (stage === 4) {
        label = "Stage 4 (down)";
      }

      // Explicit increment without || antipattern
      counts[label] = counts[label] !== undefined ? counts[label] + 1 : 1;
    }

    const distribution = order
      .filter((k) => counts[k])
      .map((k) => ({ phase: k, count: counts[k] }));

    return sendSuccess(res, {
      distribution,
      total_positions: posResult.rows.length,
    });
  } catch (error) {
    logger.error("Error in /api/algo/stage-distribution:", {
      error: error.message,
      stack: error.stack,
    });
    return sendDatabaseError(
      res,
      error,
      "An error occurred while computing stage distribution"
    );
  }
});

// ============================================================
// MISSING ENDPOINTS - Return empty data to prevent 404 errors
// ============================================================

router.get("/metrics", async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();

    const [circuitResult, perfResult] = await Promise.all([
      pool.query(
        `SELECT * FROM circuit_breaker_status ORDER BY date DESC LIMIT 1`
      ),
      pool.query(
        `SELECT * FROM algo_performance_metrics ORDER BY metric_date DESC LIMIT 1`
      ),
    ]);

    return sendSuccess(res, {
      circuit_breakers: circuitResult.rows[0] !== null && circuitResult.rows[0] !== undefined ? circuitResult.rows[0] : null,
      performance: perfResult.rows[0] !== null && perfResult.rows[0] !== undefined ? perfResult.rows[0] : null,
    });
  } catch (error) {
    logger.error("Error in /algo/metrics:", { error: error.message });
    return sendDatabaseError(
      res,
      error,
      "An error occurred while fetching metrics"
    );
  }
});

router.get("/risk-metrics", authenticateToken, async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();

    const result = await pool.query(`
      SELECT report_date, var_pct_95, cvar_pct_95, stressed_var_pct,
             portfolio_beta, top_5_concentration
      FROM algo_risk_daily
      ORDER BY report_date DESC LIMIT 1
    `);

    const row = result.rows[0];
    if (!row) {
      return sendSuccess(res, {
        report_date: null,
        var_pct_95: null,
        cvar_pct_95: null,
        stressed_var_pct: null,
        portfolio_beta: null,
        top_5_concentration: null,
      });
    }

    const sf = (v) => (v == null ? null : parseFloat(v));
    return sendSuccess(res, {
      report_date: row.report_date,
      var95: sf(row.var_pct_95),
      cvar95: sf(row.cvar_pct_95),
      svar: sf(row.stressed_var_pct),
      beta: sf(row.portfolio_beta),
      concentration5: sf(row.top_5_concentration),
    });
  } catch (error) {
    logger.error("Error in /algo/risk-metrics:", { error: error.message });
    return sendDatabaseError(
      res,
      error,
      "An error occurred while fetching risk metrics"
    );
  }
});

router.get("/performance-analytics", authenticateToken, async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();

    const perfResult = await pool.query(`
      SELECT
        win_rate_pct,
        COALESCE(avg_win_pct, best_trade_pct) as avg_win_pct,
        COALESCE(avg_loss_pct, worst_trade_pct) as avg_loss_pct,
        profit_factor,
        total_return_pct,
        sharpe_ratio as sharpe252,
        sortino_ratio as sortino,
        calmar_ratio, max_drawdown_pct,
        best_win_streak, worst_loss_streak,
        avg_holding_days
      FROM algo_performance_metrics
      ORDER BY metric_date DESC LIMIT 1
    `);

    validateQueryResult(perfResult, { requireRows: false });

    if (perfResult.rows.length === 0) {
      return sendSuccess(res, {
        wr50: null,
        avg_w_r: null,
        avg_l_r: null,
        expectancy: null,
        sharpe252: null,
        sortino: null,
        calmar: null,
        maxdd: null,
      });
    }

    const perf = validateAndCoerceRow(perfResult.rows[0], {
      win_rate_pct: { type: "float", required: false },
      avg_win_pct: { type: "float", required: false },
      avg_loss_pct: { type: "float", required: false },
      profit_factor: { type: "float", required: false },
      total_return_pct: { type: "float", required: false },
      sharpe252: { type: "float", required: false },
      sortino: { type: "float", required: false },
      calmar: { type: "float", required: false },
      max_drawdown_pct: { type: "float", required: false },
      best_win_streak: { type: "int", required: false },
      worst_loss_streak: { type: "int", required: false },
      avg_holding_days: { type: "float", required: false },
    });

    const expectancy = perf.profit_factor
      ? ((perf.avg_win_pct + perf.avg_loss_pct) * perf.profit_factor) / 100
      : null;

    return sendSuccess(res, {
      wr50: perf.win_rate_pct,
      avg_w_r: perf.avg_win_pct,
      avg_l_r: perf.avg_loss_pct,
      expectancy: expectancy,
      sharpe252: perf.sharpe252,
      sortino: perf.sortino,
      calmar: perf.calmar,
      maxdd: perf.max_drawdown_pct,
    });
  } catch (error) {
    logger.error("Error in /algo/performance-analytics:", {
      error: error.message,
    });
    return sendDatabaseError(
      res,
      error,
      "An error occurred while fetching performance analytics"
    );
  }
});

router.get("/sentiment", async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();

    const fgiResult = await pool.query(
      `SELECT date, fear_greed_value, fear_greed_label FROM fear_greed_index ORDER BY date DESC LIMIT 1`
    );

    return sendSuccess(res, {
      fear_greed_index: fgiResult.rows[0] || null,
      current_sentiment: fgiResult.rows[0]?.fear_greed_value || null,
    });
  } catch (error) {
    logger.error("Error in /algo/sentiment:", { error: error.message });
    return sendDatabaseError(
      res,
      error,
      "An error occurred while fetching sentiment"
    );
  }
});

router.get("/economic-calendar", async (req, res) => {
  try {
    return sendSuccess(res, {
      upcoming_events: [],
      impact_level: null,
    });
  } catch (error) {
    logger.error("Error in /algo/economic-calendar:", { error: error.message });
    return sendDatabaseError(
      res,
      error,
      "An error occurred while fetching economic calendar"
    );
  }
});

router.get("/execution/recent", authenticateToken, async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();
    const parsedDays = parseInt(req.query.days);
    const days = Math.min(!isNaN(parsedDays) ? parsedDays : 7, 90);
    const parsedLimit = parseInt(req.query.limit);
    const limit = Math.min(!isNaN(parsedLimit) ? parsedLimit : 50, 1000);

    const result = await pool.query(
      `SELECT run_id, run_date, started_at, completed_at, overall_status, summary,
              phases_completed, phases_halted, phases_errored
       FROM orchestrator_execution_log
       WHERE run_date >= CURRENT_DATE - $1
       ORDER BY started_at DESC
       LIMIT $2`,
      [days, limit]
    );

    return sendSuccess(res, {
      items: result.rows !== null && result.rows !== undefined ? result.rows : [],
      total: result.rows !== null && result.rows !== undefined ? result.rows.length : 0,
    });
  } catch (error) {
    logger.error("Error in /algo/execution/recent:", { error: error.message });
    return sendDatabaseError(
      res,
      error,
      "An error occurred while fetching recent executions"
    );
  }
});

router.get("/execution/stats", async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();
    const parsedDays = parseInt(req.query.days);
    const days = Math.min(!isNaN(parsedDays) ? parsedDays : 7, 90);

    const result = await pool.query(
      `SELECT overall_status, COUNT(*) as count
       FROM orchestrator_execution_log
       WHERE run_date >= CURRENT_DATE - $1
       GROUP BY overall_status`,
      [days]
    );

    const byStatus = {};
    let total = 0;
    for (const row of result.rows) {
      byStatus[row.overall_status] = parseInt(row.count);
      total += parseInt(row.count);
    }
    const successCount = byStatus.success !== undefined ? byStatus.success : 0;
    const haltCount = byStatus.halted !== undefined ? byStatus.halted : 0;
    const errorCount = byStatus.error !== undefined ? byStatus.error : 0;

    return sendSuccess(res, {
      total_runs: total,
      by_status: byStatus,
      success_rate:
        total > 0 ? `${((successCount / total) * 100).toFixed(1)}%` : "N/A",
      halt_rate:
        total > 0 ? `${((haltCount / total) * 100).toFixed(1)}%` : "N/A",
      error_rate:
        total > 0 ? `${((errorCount / total) * 100).toFixed(1)}%` : "N/A",
      period_days: days,
    });
  } catch (error) {
    logger.error("Error in /algo/execution/stats:", { error: error.message });
    return sendDatabaseError(
      res,
      error,
      "An error occurred while fetching execution stats"
    );
  }
});

// Signals endpoint - required by dashboard
router.get("/signals/stocks", async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();

    const result = await pool.query(`
      SELECT symbol, final_signal_quality_score, final_risk_score, raw_signal, signal_date
      FROM algo_signals_evaluated
      ORDER BY signal_date DESC, final_signal_quality_score DESC LIMIT 20
    `);

    const signals = (result.rows || []).map((row) => ({
      symbol: row.symbol,
      score: row.final_signal_quality_score,
      risk: row.final_risk_score,
      signal: row.raw_signal,
    }));

    return sendSuccess(res, {
      signals: signals,
      total: signals.length,
      grades: {},
      trend: [],
    });
  } catch (error) {
    logger.error("Error in /algo/signals/stocks:", { error: error.message });
    return sendDatabaseError(
      res,
      error,
      "An error occurred while fetching signals"
    );
  }
});

module.exports = router;

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

const express = require('express');
const { getPool, ensureConnection } = require('../utils/database');
const { authenticateToken, requireAdmin } = require('../middleware/auth');
const { sendSuccess, sendError, sendDatabaseError } = require('../utils/apiResponse');
const paginationConfig = require('../config/pagination');
const logger = require('../utils/logger');
const { validateQueryResult, validateAndCoerceRow, validateAndCoerceRows, extractCount } = require('../utils/responseValidation');
const { getActiveTiers, getActiveTier } = require('../utils/tiers');
const { getSwingGrades, getGradeForScore } = require('../utils/grades');

const router = express.Router();

const requireAuth = authenticateToken;

/**
 * ISSUE #5: Helper function to compute stage_label from Weinstein stage and Minervini score.
 * Centralizes stage labeling logic to eliminate duplication.
 */
function computeStageLabel(stage, score, stageConfig = {}) {
  if (stage === 1) {
    return 'Stage 1 (base)';
  } else if (stage === 2) {
    if (score != null) {
      if (score >= (stageConfig.stage_2_late_min_score ?? 8)) return 'Late Stage-2';
      if (score >= (stageConfig.stage_2_mid_min_score ?? 6)) return 'Mid Stage-2';
      if (score >= (stageConfig.stage_2_early_min_score ?? 0)) return 'Early Stage-2';
      return 'Early Stage-2';
    }
    return 'Stage 2';
  } else if (stage === 3) {
    return 'Stage 3 (top)';
  } else if (stage === 4) {
    return 'Stage 4 (down)';
  }
  return 'Unknown';
}

/**
 * GET /api/algo/status
 * Current algo system status
 */
router.get('/status', async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();

    // Parallelize all 4 independent queries
    const [snapshotResult, posResult, healthResult, configResult] = await Promise.all([
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
      `)
    ]);

    // Validate result structures
    validateQueryResult(snapshotResult, { requireRows: false });
    validateQueryResult(posResult, { requireRows: false });
    validateQueryResult(healthResult, { requireRows: false });
    validateQueryResult(configResult, { requireRows: false });

    const snapshot = snapshotResult.rows[0]
      ? validateAndCoerceRow(snapshotResult.rows[0], {
          position_count: { type: 'int', required: false, defaultValue: 0 },
          unrealized_pnl_pct: { type: 'float', required: false, defaultValue: 0 },
          daily_return_pct: { type: 'float', required: false, defaultValue: 0 },
          total_portfolio_value: { type: 'float', required: false, defaultValue: 0 }
        })
      : { position_count: 0, unrealized_pnl_pct: 0, daily_return_pct: 0, total_portfolio_value: 0 };

    const positions = posResult.rows[0]
      ? validateAndCoerceRow(posResult.rows[0], {
          open_count: { type: 'int', required: false, defaultValue: 0 },
          total_value: { type: 'float', required: false, defaultValue: 0 }
        })
      : { open_count: 0, total_value: 0 };

    const health = healthResult.rows[0]
      ? validateAndCoerceRow(healthResult.rows[0], {
          market_trend: { type: 'string', required: false, defaultValue: 'unknown' },
          market_stage: { type: 'int', required: false, defaultValue: 1 },
          distribution_days_4w: { type: 'int', required: false, defaultValue: 0 },
          vix_level: { type: 'float', required: false, defaultValue: 0 }
        })
      : { market_trend: 'unknown', market_stage: 1, distribution_days_4w: 0, vix_level: 0 };

    let algo_enabled = true;
    let execution_mode = 'paper';

    validateAndCoerceRows(configResult, {
      key: { type: 'string', required: true },
      value: { type: 'string', required: true }
    }).forEach(row => {
      if (row.key === 'enable_algo') {
        algo_enabled = row.value.toLowerCase() === 'true';
      } else if (row.key === 'execution_mode') {
        execution_mode = row.value;
      }
    });

    const totalValue = snapshot.total_portfolio_value || 0;
    const unrealizedPnlPct = snapshot.unrealized_pnl_pct || 0;
    const unrealizedPnlDollars = totalValue > 0 ? (totalValue * unrealizedPnlPct / 100) : 0;

    return sendSuccess(res, {
      algo_enabled: algo_enabled,
      execution_mode: execution_mode,
      status: 'operational',
      portfolio: {
        total_value: totalValue,
        position_count: positions.open_count,
        total_position_value: positions.total_value || 0,
        unrealized_pnl_pct: unrealizedPnlPct,
        unrealized_pnl_dollars: Number(unrealizedPnlDollars.toFixed(2)),
        daily_return_pct: snapshot.daily_return_pct || 0
      },
      market: {
        trend: health.market_trend,
        stage: health.market_stage,
        distribution_days: health.distribution_days_4w || 0,
        vix: health.vix_level || 0
      }
    });
  } catch (error) {
    logger.error('Error in /algo/status:', { error: error.message, stack: error.stack });
    return sendDatabaseError(res, error, 'An error occurred while fetching algorithm status');
  }
});

/**
 * GET /api/algo/evaluate
 * Run signal evaluation (latest date with buy signals)
 */
router.get('/evaluate', async (req, res) => {
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
        COALESCE(tt.minervini_trend_score, 0)::int as trend_score,
        COALESCE(tt.percent_from_52w_low, 0)::numeric as pct_from_52w_low,
        COALESCE(dc.composite_completeness_pct, 0)::numeric as completeness_pct,
        COALESCE(sq.composite_sqs, 0)::int as sqs
      FROM latest_signals s
      LEFT JOIN latest_trend tt ON tt.symbol = s.symbol
      LEFT JOIN latest_completeness dc ON dc.symbol = s.symbol
      LEFT JOIN latest_sqs sq ON sq.symbol = s.symbol
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

    let filterConfig = {
      completeness_pct_min: 45,      // Fallback defaults (same as hardcoded values)
      trend_score_min: 8,
      sqs_min: 40,
      require_all_tiers: true,
      max_qualified_signals: 12,
      sort_by: 'sqs',
      sort_order: 'DESC'
    };

    if (filterConfigResult.rows && filterConfigResult.rows.length > 0) {
      const cfg = filterConfigResult.rows[0];
      filterConfig = {
        completeness_pct_min: parseFloat(cfg.completeness_pct_min) || 45,
        trend_score_min: parseInt(cfg.trend_score_min) || 8,
        sqs_min: parseInt(cfg.sqs_min) || 40,
        require_all_tiers: cfg.require_all_tiers !== false,
        max_qualified_signals: parseInt(cfg.max_qualified_signals) || 12,
        sort_by: cfg.sort_by || 'sqs',
        sort_order: (cfg.sort_order || 'DESC').toUpperCase()
      };
    }

    // Transform into evaluation objects with database-driven thresholds
    const evaluated = validateAndCoerceRows(result, {
      symbol: { type: 'string', required: true },
      date: { type: 'date', required: true },
      trend_score: { type: 'int', required: false, defaultValue: 0 },
      pct_from_52w_low: { type: 'float', required: false, defaultValue: 0 },
      completeness_pct: { type: 'float', required: false, defaultValue: 0 },
      sqs: { type: 'int', required: false, defaultValue: 0 }
    }).map(row => {
      const tier1 = row.completeness_pct >= filterConfig.completeness_pct_min;
      const tier3 = row.trend_score >= filterConfig.trend_score_min;
      const tier4 = row.sqs >= filterConfig.sqs_min;

      const all_tiers_pass = filterConfig.require_all_tiers
        ? (tier1 && tier3 && tier4)
        : (tier1 || tier3 || tier4);

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
        all_tiers_pass: all_tiers_pass
      };
    });

    // Filter to qualified and sort by configured field/direction
    const sortComparator = (a, b) => {
      const aVal = a[filterConfig.sort_by] || 0;
      const bVal = b[filterConfig.sort_by] || 0;
      const diff = parseFloat(bVal) - parseFloat(aVal);
      return filterConfig.sort_order === 'ASC' ? -diff : diff;
    };

    const qualified = evaluated
      .filter(e => e.all_tiers_pass)
      .sort(sortComparator)
      .slice(0, filterConfig.max_qualified_signals);

    return sendSuccess(res, {
      total_buy_signals: evaluated.length,
      qualified_for_trading: qualified.length,
      signals: evaluated,
      top_qualified: qualified
    });
  } catch (error) {
    logger.error('Error in /algo/evaluate:', { error: error.message, stack: error.stack });
    return sendDatabaseError(res, error, 'An error occurred while evaluating signals');
  }
});

/**
 * GET /api/algo/last-run
 * Get the last orchestrator run status and phase information
 */
router.get('/last-run', requireAuth, async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();

    const result = await pool.query(`
      SELECT
        run_id, run_at, success, halted, error_message,
        COALESCE(
          json_agg(
            json_build_object(
              'action_type', phase_name,
              'status', status
            ) ORDER BY created_at
          ) FILTER (WHERE phase_name IS NOT NULL),
          '[]'::json
        ) as phases
      FROM algo_audit_log
      WHERE action_type LIKE 'phase_%'
      GROUP BY run_id, run_at, success, halted, error_message
      ORDER BY run_at DESC
      LIMIT 1
    `);

    if (result.rows.length === 0) {
      return sendSuccess(res, {
        run_id: null,
        run_at: null,
        success: null,
        halted: null,
        error_message: null,
        phases: []
      });
    }

    const run = result.rows[0];
    return sendSuccess(res, {
      run_id: run.run_id,
      run_at: run.run_at,
      success: run.success,
      halted: run.halted,
      error_message: run.error_message,
      phases: run.phases || []
    });
  } catch (error) {
    logger.error('Error in /algo/last-run:', { error: error.message, stack: error.stack });
    return sendSuccess(res, {
      run_id: null,
      run_at: null,
      success: null,
      halted: null,
      error_message: null,
      phases: []
    });
  }
});

/**
 * GET /api/algo/positions
 * Get active positions enriched with stop/target levels (from latest open trade),
 * sector (from company_profile), and Minervini stage / RS (from trend_template_data).
 */
router.get('/positions', authenticateToken, async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();

    // Fetch positions and stage config in parallel
    const [posResult, configResult, sectorResult] = await Promise.all([
      pool.query(`
        SELECT
          position_id, symbol, quantity, avg_entry_price, current_price,
          position_value, unrealized_pnl, unrealized_pnl_pct,
          status, stage_in_exit_plan, days_since_entry,
          stop_loss_price, target_1_price, target_2_price, target_3_price,
          target_1_r_multiple, target_2_r_multiple, target_3_r_multiple,
          sector, industry,
          weinstein_stage, minervini_trend_score,
          percent_from_52w_low, percent_from_52w_high,
          r_multiple, initial_risk_per_share, open_risk_dollars,
          distance_to_stop_pct, distance_to_t1_pct, distance_to_t2_pct, distance_to_t3_pct,
          risk_pct, risk_rank,
          ladder_pct_stop, ladder_pct_entry, ladder_pct_current,
          ladder_pct_t1, ladder_pct_t2, ladder_pct_t3,
          ladder_scale_min, ladder_scale_max
        FROM algo_positions_with_risk
        ORDER BY position_value DESC
      `),
      pool.query(`
        SELECT key, value FROM algo_config
        WHERE key IN ('stage_2_early_min_score', 'stage_2_mid_min_score', 'stage_2_late_min_score')
      `),
      pool.query(`
        SELECT sector, position_count, total_value_dollars, allocation_pct, is_overweight
        FROM sector_allocation_summary
        WHERE snapshot_date = CURRENT_DATE
        ORDER BY allocation_pct DESC
      `)
    ]);

    // Validate result structures
    validateQueryResult(posResult, { requireRows: false });
    validateQueryResult(configResult, { requireRows: false });
    validateQueryResult(sectorResult, { requireRows: false });

    // Parse stage threshold config (with sensible defaults)
    const stageConfig = {
      stage_2_early_min_score: 0,
      stage_2_mid_min_score: 6,
      stage_2_late_min_score: 8,
    };
    for (const row of configResult.rows) {
      const val = parseFloat(row.value);
      if (!isNaN(val)) {
        stageConfig[row.key] = val;
      }
    }

    const sf = (v) => v == null ? null : parseFloat(v);

    // Transform positions (pre-computed metrics from view, ISSUE #6, #7, #8)
    const items = validateAndCoerceRows(posResult, {
      position_id: { type: 'int', required: true },
      symbol: { type: 'string', required: true },
      quantity: { type: 'float', required: true },
      avg_entry_price: { type: 'float', required: false },
      current_price: { type: 'float', required: false },
      position_value: { type: 'float', required: false },
      unrealized_pnl: { type: 'float', required: false },
      unrealized_pnl_pct: { type: 'float', required: false },
      status: { type: 'string', required: false },
      stage_in_exit_plan: { type: 'string', required: false },
      days_since_entry: { type: 'int', required: false },
      stop_loss_price: { type: 'float', required: false },
      target_1_price: { type: 'float', required: false },
      target_2_price: { type: 'float', required: false },
      target_3_price: { type: 'float', required: false },
      target_1_r_multiple: { type: 'float', required: false },
      target_2_r_multiple: { type: 'float', required: false },
      target_3_r_multiple: { type: 'float', required: false },
      sector: { type: 'string', required: false },
      industry: { type: 'string', required: false },
      weinstein_stage: { type: 'int', required: false },
      minervini_trend_score: { type: 'int', required: false },
      percent_from_52w_low: { type: 'float', required: false },
      percent_from_52w_high: { type: 'float', required: false },
      r_multiple: { type: 'float', required: false },
      initial_risk_per_share: { type: 'float', required: false },
      open_risk_dollars: { type: 'float', required: false },
      distance_to_stop_pct: { type: 'float', required: false },
      distance_to_t1_pct: { type: 'float', required: false },
      distance_to_t2_pct: { type: 'float', required: false },
      distance_to_t3_pct: { type: 'float', required: false },
      risk_pct: { type: 'float', required: false },
      risk_rank: { type: 'int', required: false },
      ladder_pct_stop: { type: 'float', required: false },
      ladder_pct_entry: { type: 'float', required: false },
      ladder_pct_current: { type: 'float', required: false },
      ladder_pct_t1: { type: 'float', required: false },
      ladder_pct_t2: { type: 'float', required: false },
      ladder_pct_t3: { type: 'float', required: false },
      ladder_scale_min: { type: 'float', required: false },
      ladder_scale_max: { type: 'float', required: false }
    }).map(row => ({
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
      stage_label: computeStageLabel(row.weinstein_stage, row.minervini_trend_score, stageConfig),
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
      ladder_scale_max: sf(row.ladder_scale_max)
    }));

    // Fetch pre-computed sector allocation from database (ISSUE #6)
    const sector_allocation = validateAndCoerceRows(sectorResult, {
      sector: { type: 'string', required: true },
      position_count: { type: 'int', required: false, defaultValue: 0 },
      total_value_dollars: { type: 'float', required: false, defaultValue: 0 },
      allocation_pct: { type: 'float', required: false, defaultValue: 0 },
      is_overweight: { type: 'bool', required: false, defaultValue: false }
    });

    return sendSuccess(res, {
      items,
      sector_allocation,
      pagination: {
        total: items.length,
        count: items.length
      }
    });
  } catch (error) {
    logger.error('Error in /algo/positions:', { error: error.message, stack: error.stack });
    return sendDatabaseError(res, error, 'An error occurred while fetching positions');
  }
});

/**
 * GET /api/algo/portfolio-summary
 * Get aggregated portfolio metrics without individual positions.
 * ISSUE #9a: Replaces frontend aggregation logic.
 */
router.get('/portfolio-summary', authenticateToken, async (req, res) => {
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
      `)
    ]);

    validateQueryResult(snapshotResult, { requireRows: false });
    validateQueryResult(sectorResult, { requireRows: false });

    const snapshot = snapshotResult.rows[0]
      ? validateAndCoerceRow(snapshotResult.rows[0], {
          snapshot_date: { type: 'date', required: false },
          total_portfolio_value: { type: 'float', required: false, defaultValue: 0 },
          position_count: { type: 'int', required: false, defaultValue: 0 },
          unrealized_pnl_pct: { type: 'float', required: false, defaultValue: 0 },
          daily_return_pct: { type: 'float', required: false, defaultValue: 0 },
          largest_position_pct: { type: 'float', required: false, defaultValue: 0 },
          average_position_size_pct: { type: 'float', required: false, defaultValue: 0 },
          concentration_risk_pct: { type: 'float', required: false, defaultValue: 0 },
          realized_pnl_today: { type: 'float', required: false, defaultValue: 0 },
          unrealized_pnl_total: { type: 'float', required: false, defaultValue: 0 },
          max_drawdown_pct: { type: 'float', required: false, defaultValue: 0 },
          sharpe_ratio: { type: 'float', required: false, defaultValue: 0 }
        })
      : {
          snapshot_date: null,
          total_portfolio_value: 0,
          position_count: 0,
          unrealized_pnl_pct: 0,
          daily_return_pct: 0,
          largest_position_pct: 0,
          average_position_size_pct: 0,
          concentration_risk_pct: 0,
          realized_pnl_today: 0,
          unrealized_pnl_total: 0,
          max_drawdown_pct: 0,
          sharpe_ratio: 0
        };

    const sector_allocation = validateAndCoerceRows(sectorResult, {
      sector: { type: 'string', required: true },
      position_count: { type: 'int', required: false, defaultValue: 0 },
      total_value_dollars: { type: 'float', required: false, defaultValue: 0 },
      allocation_pct: { type: 'float', required: false, defaultValue: 0 },
      is_overweight: { type: 'bool', required: false, defaultValue: false }
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
        sharpe_ratio: snapshot.sharpe_ratio
      },
      sector_allocation
    });
  } catch (error) {
    logger.error('Error in /algo/portfolio-summary:', { error: error.message, stack: error.stack });
    return sendDatabaseError(res, error, 'An error occurred while fetching portfolio summary');
  }
});

/**
 * GET /api/algo/trades
 * Get trade history
 */
router.get('/trades', authenticateToken, async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();
    const { limit, offset } = paginationConfig.sanitize(req.query.limit, req.query.offset, 'trades');

    // Parallelize data fetch and count query
    const [result, countResult] = await Promise.all([
      pool.query(`
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
      `, [limit, offset]),
      pool.query('SELECT COUNT(*) as total FROM algo_trades')
    ]);

    // Validate result structures
    validateQueryResult(result, { requireRows: false });
    validateQueryResult(countResult, { minRows: 1, maxRows: 1 });
    const total = extractCount(countResult, 'total');

    // Validate and coerce row types
    const validated = validateAndCoerceRows(result, {
      trade_id: { type: 'int', required: true },
      symbol: { type: 'string', required: true },
      signal_date: { type: 'date', required: false },
      trade_date: { type: 'date', required: true },
      entry_price: { type: 'float', required: false },
      entry_quantity: { type: 'float', required: false },
      status: { type: 'string', required: false },
      exit_date: { type: 'date', required: false },
      exit_price: { type: 'float', required: false },
      exit_r_multiple: { type: 'float', required: false },
      profit_loss_pct: { type: 'float', required: false, defaultValue: 0 },
      profit_loss_dollars: { type: 'float', required: false, defaultValue: 0 },
      trade_duration_days: { type: 'int', required: false }
    });

    return sendSuccess(res, {
      items: validated,
      pagination: {
        total,
        limit,
        offset,
        page: Math.floor(offset / limit) + 1,
        totalPages: Math.ceil(total / limit)
      }
    });
  } catch (error) {
    logger.error('Error in /algo/trades:', { error: error.message, stack: error.stack });
    return sendDatabaseError(res, error, 'An error occurred while fetching trade history');
  }
});

/**
 * Configuration category mapping (for frontend grouping)
 */
const CONFIG_CATEGORIES = {
  'base_risk_pct': 'Risk Management',
  'max_position_size_pct': 'Risk Management',
  'max_positions': 'Risk Management',
  'max_concentration_pct': 'Risk Management',
  'max_total_invested_pct': 'Risk Management',
  'max_consecutive_losses': 'Risk Management',
  'max_daily_loss_pct': 'Risk Management',
  'max_weekly_loss_pct': 'Risk Management',
  'min_win_rate_pct': 'Risk Management',
  'halt_drawdown_pct': 'Drawdown Defense',
  'risk_reduction_at_minus_5': 'Drawdown Defense',
  'risk_reduction_at_minus_10': 'Drawdown Defense',
  'risk_reduction_at_minus_15': 'Drawdown Defense',
  'risk_reduction_at_minus_20': 'Drawdown Defense',
  'sector_drawdown_halt_pct': 'Drawdown Defense',
  'halt_entries_before_major_release_minutes': 'Circuit Breakers',
  're_engage_min_days': 'Circuit Breakers',
  're_engage_recovery_pct': 'Circuit Breakers',
  'position_halt_flag_count': 'Circuit Breakers',
  'max_distribution_days': 'Market Conditions',
  'require_stage_2_market': 'Market Conditions',
  'vix_max_threshold': 'Market Conditions',
  'vix_caution_threshold': 'Market Conditions',
  'vix_caution_risk_reduction': 'Market Conditions',
  'min_completeness_score': 'Filter Thresholds',
  'min_stock_price': 'Filter Thresholds',
  'min_signal_quality_score': 'Filter Thresholds',
  'min_volume_ma_50d': 'Filter Thresholds',
  'min_avg_daily_dollar_volume': 'Filter Thresholds',
  'min_market_cap_millions': 'Filter Thresholds',
  'min_float_millions': 'Filter Thresholds',
  'min_price_history_days': 'Filter Thresholds',
  'min_daily_volume_shares': 'Filter Thresholds',
  'max_spread_pct': 'Filter Thresholds',
  'max_short_interest_pct': 'Filter Thresholds',
  'max_data_staleness_days': 'Filter Thresholds',
  'require_sma50_above_sma200': 'Entry Rules (Minervini)',
  'min_percent_from_52w_low': 'Entry Rules (Minervini)',
  'max_percent_from_52w_high': 'Entry Rules (Minervini)',
  'eight_week_rule_threshold_pct': 'Entry Rules (Minervini)',
  'eight_week_rule_window_days': 'Entry Rules (Minervini)',
  'max_signal_age_days': 'Entry Quality Gates',
  'min_close_quality_pct': 'Entry Quality Gates',
  'min_breakout_volume_ratio': 'Entry Quality Gates',
  'require_weekly_stage_2': 'Entry Quality Gates',
  'min_rs_line_slope_days': 'Entry Quality Gates',
  'max_rs_pct_from_60d_high': 'Entry Quality Gates',
  'rs_slope_gate_enabled': 'Entry Quality Gates',
  'volume_decay_gate_enabled': 'Entry Quality Gates',
  'require_target_pullback': 'Entry Quality Gates',
  'exit_on_distribution_day': 'Exit Rules',
  'exit_on_rs_line_break_50dma': 'Exit Rules',
  'exit_on_td_sequential': 'Exit Rules',
  'max_hold_days': 'Exit Rules',
  'min_hold_days': 'Exit Rules',
  'chandelier_atr_mult': 'Exit Rules',
  'use_chandelier_trail': 'Exit Rules',
  'switch_to_21ema_after_days': 'Exit Rules',
  'move_be_at_r': 'Exit Rules',
  'pyramid_enabled': 'Pyramid & Re-engagement',
  'pyramid_add_1_gain_pct': 'Pyramid & Re-engagement',
  'pyramid_add_2_gain_pct': 'Pyramid & Re-engagement',
  'pyramid_split_pct': 'Pyramid & Re-engagement',
  'require_ftd_to_re_engage': 'Pyramid & Re-engagement',
  'max_trades_per_day': 'Position Monitoring',
  'max_reentries_per_name': 'Position Monitoring',
  'min_days_before_reentry_same_symbol': 'Position Monitoring',
  'max_positions_per_sector': 'Position Monitoring',
  'max_positions_per_industry': 'Position Monitoring',
  'min_swing_score': 'Swing Trader Scoring',
  'min_swing_grade': 'Swing Trader Scoring',
  'swing_min_trend_score': 'Swing Trader Scoring',
  'swing_min_industry_rank': 'Swing Trader Scoring',
  'swing_days_to_earnings_block': 'Swing Trader Scoring',
  'swing_score_good_threshold': 'Swing Trader Scoring',
  'swing_score_excellent_threshold': 'Swing Trader Scoring',
  'swing_weight_setup': 'Swing Trader Scoring',
  'swing_weight_trend': 'Swing Trader Scoring',
  'swing_weight_momentum': 'Swing Trader Scoring',
  'swing_weight_volume': 'Swing Trader Scoring',
  'swing_weight_fundamentals': 'Swing Trader Scoring',
  'swing_weight_sector': 'Swing Trader Scoring',
  'swing_weight_multi_timeframe': 'Swing Trader Scoring',
  'block_days_before_earnings': 'Economic & Earnings',
  'earnings_blackout_days_before': 'Economic & Earnings',
  'earnings_blackout_days_after': 'Economic & Earnings',
  'require_stock_stage_2': 'Economic & Earnings',
  'min_trend_template_score': 'Fundamental Filters',
  'strong_sector_top_n': 'Fundamental Filters',
  'enable_advanced_filters': 'Advanced Filters',
  'max_total_risk_pct': 'Risk Metrics',
  't1_target_r_multiple': 'Risk Metrics',
  't2_target_r_multiple': 'Risk Metrics',
  't3_target_r_multiple': 'Risk Metrics',
  'execution_mode': 'Execution Mode',
  'enable_algo': 'Execution Mode',
  'enable_backtesting': 'Execution Mode',
  'alpaca_paper_trading': 'Execution Mode',
  'verbose_logging': 'Feature Flags',
  'api_request_timeout_seconds': 'Network Configuration',
  'db_connection_timeout_seconds': 'Network Configuration',
  'default_portfolio_value': 'Failsafe Configuration',
  'imported_position_default_stop_loss_pct': 'Failsafe Configuration',
  'imported_position_default_target_1_pct': 'Failsafe Configuration',
  'imported_position_default_target_2_pct': 'Failsafe Configuration',
  'imported_position_default_target_3_pct': 'Failsafe Configuration',
  'daily_profit_cap_pct': 'Failsafe Configuration',
  'stale_loader_threshold_minutes': 'Failsafe Configuration',
};

/**
 * GET /api/algo/config (admin only)
 * Get current configuration as array with categories
 */
router.get('/config', requireAuth, requireAdmin, async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();

    const result = await pool.query(`
      SELECT key, value, value_type, description, updated_at
      FROM algo_config
      ORDER BY key
    `);

    const configArray = result.rows.map(row => {
      let parsedValue = row.value;
      if (row.value_type === 'int') {
        parsedValue = parseInt(row.value, 10);
      } else if (row.value_type === 'float') {
        parsedValue = parseFloat(row.value);
      } else if (row.value_type === 'bool') {
        parsedValue = ['true', '1', 'yes'].includes(String(row.value).toLowerCase());
      }
      return {
        key: row.key,
        value: parsedValue,
        value_type: row.value_type,
        description: row.description,
        category: CONFIG_CATEGORIES[row.key] || 'Other',
        updated_at: row.updated_at,
        is_custom: false
      };
    });

    return sendSuccess(res, configArray);
  } catch (error) {
    logger.error('Error in /algo/config:', { error: error.message, stack: error.stack });
    return sendDatabaseError(res, error, 'An error occurred while fetching configuration');
  }
});

/**
 * PUT /api/algo/config/:key (admin only)
 * Update a single configuration value
 */
router.put('/config/:key', requireAuth, requireAdmin, async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();
    const { key } = req.params;
    const { value } = req.body;

    if (!key || !key.match(/^[a-z0-9_]+$/i)) {
      return sendError(res, 'Invalid configuration key', 400);
    }

    if (value === undefined || value === null) {
      return sendError(res, 'Value is required', 400);
    }

    // Get the current config to know the value_type for proper conversion
    const configResult = await pool.query(
      'SELECT key, value, value_type, description FROM algo_config WHERE key = $1',
      [key]
    );

    if (configResult.rows.length === 0) {
      return sendError(res, `Configuration key not found: ${key}`, 404);
    }

    const config = configResult.rows[0];
    let storedValue = String(value);

    // Validate and convert value based on type
    if (config.value_type === 'int') {
      const intVal = parseInt(value, 10);
      if (isNaN(intVal)) {
        return sendError(res, `Invalid integer value for ${key}: ${value}`, 400);
      }
      storedValue = String(intVal);
    } else if (config.value_type === 'float') {
      const floatVal = parseFloat(value);
      if (isNaN(floatVal)) {
        return sendError(res, `Invalid float value for ${key}: ${value}`, 400);
      }
      storedValue = String(floatVal);
    } else if (config.value_type === 'bool') {
      const boolVal = ['true', '1', 'yes'].includes(String(value).toLowerCase());
      storedValue = boolVal ? 'true' : 'false';
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
      return sendError(res, 'Failed to update configuration', 500);
    }

    const updatedRow = updateResult.rows[0];

    // Parse the updated value to match frontend expectations
    let parsedValue = updatedRow.value;
    if (updatedRow.value_type === 'int') {
      parsedValue = parseInt(updatedRow.value, 10);
    } else if (updatedRow.value_type === 'float') {
      parsedValue = parseFloat(updatedRow.value);
    } else if (updatedRow.value_type === 'bool') {
      parsedValue = ['true', '1', 'yes'].includes(updatedRow.value.toLowerCase());
    }

    return sendSuccess(res, {
      key: updatedRow.key,
      value: parsedValue,
      value_type: updatedRow.value_type,
      description: updatedRow.description,
      category: CONFIG_CATEGORIES[updatedRow.key] || 'Other',
      updated_at: updatedRow.updated_at,
      is_custom: true
    });

  } catch (error) {
    logger.error('Error in PUT /algo/config/:key:', { error: error.message, stack: error.stack });
    return sendDatabaseError(res, error, 'An error occurred while updating configuration');
  }
});

// ============================================================
// MARKET EXPOSURE â€” for the Markets page
// ============================================================
router.get('/markets', async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();

    // Parallelize all 5 independent queries
    const [latestResult, historyResult, healthResult, sectorsResult, sentimentResult] = await Promise.all([
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
        SELECT date, market_trend, market_stage, distribution_days_4w, vix_level
        FROM market_health_daily ORDER BY date DESC LIMIT 1
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
      `)
    ]);

    // Validate all result structures
    validateQueryResult(latestResult, { requireRows: false });
    validateQueryResult(historyResult, { requireRows: false });
    validateQueryResult(healthResult, { requireRows: false });
    validateQueryResult(sectorsResult, { requireRows: false });
    validateQueryResult(sentimentResult, { requireRows: false });

    const latest = latestResult.rows[0]
      ? validateAndCoerceRow(latestResult.rows[0], {
          date: { type: 'date', required: false },
          exposure_pct: { type: 'float', required: false },
          raw_score: { type: 'float', required: false },
          regime: { type: 'string', required: false },
          distribution_days: { type: 'int', required: false },
          factors: { type: 'string', required: false },
          halt_reasons: { type: 'string', required: false },
          created_at: { type: 'date', required: false }
        })
      : null;

    const health = healthResult.rows[0]
      ? validateAndCoerceRow(healthResult.rows[0], {
          date: { type: 'date', required: false },
          market_trend: { type: 'string', required: false },
          market_stage: { type: 'int', required: false },
          distribution_days_4w: { type: 'int', required: false },
          vix_level: { type: 'float', required: false }
        })
      : null;

    // Determine active tier policy from database
    let policy = null;
    if (latest) {
      const exposurePct = latest.exposure_pct || 0;
      const tiers = await getActiveTiers();
      policy = getActiveTier(exposurePct, tiers);
    }

    // Validate and coerce all rows
    const historyRows = validateAndCoerceRows(historyResult, {
      date: { type: 'date', required: false },
      exposure_pct: { type: 'float', required: false },
      regime: { type: 'string', required: false },
      distribution_days: { type: 'int', required: false }
    });

    const sectorsRows = validateAndCoerceRows(sectorsResult, {
      sector_name: { type: 'string', required: false },
      current_rank: { type: 'int', required: false },
      momentum_score: { type: 'float', required: false, defaultValue: 0 }
    });

    const sentimentRows = validateAndCoerceRows(sentimentResult, {
      date: { type: 'date', required: false },
      bullish: { type: 'float', required: false, defaultValue: 0 },
      bearish: { type: 'float', required: false, defaultValue: 0 },
      neutral: { type: 'float', required: false, defaultValue: 0 }
    });

    return sendSuccess(res, {
      current: latest ? {
        date: latest.date,
        exposure_pct: latest.exposure_pct || 0,
        raw_score: latest.raw_score || 0,
        regime: latest.regime,
        distribution_days: latest.distribution_days,
        factors: latest.factors,
        halt_reasons: latest.halt_reasons,
      } : null,
      active_tier: policy,
      history: historyRows.map(r => ({
        date: r.date,
        exposure_pct: r.exposure_pct || 0,
        regime: r.regime,
        distribution_days: r.distribution_days,
      })),
      market_health: health ? {
        date: health.date,
        trend: health.market_trend,
        stage: health.market_stage,
        distribution_days_4w: health.distribution_days_4w,
        vix_level: health.vix_level || 0,
      } : null,
      sectors: sectorsRows.map(r => ({
        name: r.sector_name,
        rank: r.current_rank,
        momentum: r.momentum_score || 0,
      })),
      sentiment: sentimentRows.map(r => ({
        date: r.date,
        bullish: r.bullish || 0,
        bearish: r.bearish || 0,
        neutral: r.neutral || 0,
      })),
    });
  } catch (error) {
    logger.error('Error in /algo/markets:', { error: error.message, stack: error.stack });
    return sendDatabaseError(res, error, 'An error occurred while fetching market data');
  }
});

// ============================================================
// SWING TRADER SCORES â€” for ranking display
// ============================================================
router.get('/swing-scores', async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();
    const { limit } = paginationConfig.sanitize(req.query.limit, 0, 'signals');
    const minScore = parseFloat(req.query.min_score) || 0;
    const symbol = req.query.symbol ? req.query.symbol.toUpperCase() : null;

    let whereClauses = [
      `s.date = (SELECT MAX(date) FROM swing_trader_scores)`,
      `s.score >= $1`
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
       WHERE ${whereClauses.join(' AND ')}
       ORDER BY s.score DESC
       LIMIT $${limitParamNum}`,
      params
    );

    // Validate result structure
    validateQueryResult(result, { requireRows: false });

    // Fetch grade configuration from database
    const grades = await getSwingGrades();

    const parseComponentsJSON = (components) => {
      if (!components) return {};
      if (typeof components === 'object') return components;
      if (typeof components !== 'string') return {};
      try {
        return JSON.parse(components);
      } catch (e) {
        logger.warn(`Failed to parse swing_trader_scores components: ${components.substring(0, 100)}`, { error: e.message });
        return {};
      }
    };

    return sendSuccess(res, {
      items: validateAndCoerceRows(result, {
        symbol: { type: 'string', required: true },
        date: { type: 'date', required: true },
        score: { type: 'float', required: true },
        components: { type: 'string', required: false },
        short_name: { type: 'string', required: false },
        sector: { type: 'string', required: false },
        industry: { type: 'string', required: false }
      }).map(r => {
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
      })
    });
  } catch (error) {
    logger.error('Error in /algo/swing-scores:', { error: error.message, stack: error.stack });
    return sendDatabaseError(res, error, 'An error occurred while fetching swing scores');
  }
});

// ============================================================
// SWING SCORES HISTORY â€” score counts over time
// ============================================================
router.get('/swing-scores-history', async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();
    const days = Math.min(parseInt(req.query.days) || 30, 180);

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
        eval_date: { type: 'date', required: true },
        total: { type: 'int', required: false, defaultValue: 0 },
        score_high: { type: 'int', required: false, defaultValue: 0 },
        score_medium: { type: 'int', required: false, defaultValue: 0 },
        score_low: { type: 'int', required: false, defaultValue: 0 },
        avg_score: { type: 'float', required: false, defaultValue: 0 },
        pass_count: { type: 'int', required: false, defaultValue: 0 }
      }).map(r => ({
        eval_date: r.eval_date,
        date: r.eval_date,
        total: r.total || 0,
        grade_aplus: r.score_high || 0, // scores >= 80
        grade_a: r.score_medium || 0, // scores 60-79
        pass_count: r.pass_count || 0,
        low_scores: r.score_low || 0,
        high_scores: r.score_high || 0,
        medium_scores: r.score_medium || 0,
        avg_score: r.avg_score || 0,
      }))
    });
  } catch (error) {
    logger.error('Error in /algo/swing-scores-history:', { error: error.message, stack: error.stack });
    return sendDatabaseError(res, error, 'An error occurred while fetching score history');
  }
});

// ============================================================
// DATA FRESHNESS â€” for monitoring (computed dynamically from source tables)
// ============================================================
router.get('/data-status', async (req, res) => {
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
      table_name: { type: 'string', required: true },
      frequency: { type: 'string', required: false },
      role: { type: 'string', required: false },
      latest_date: { type: 'date', required: false },
      age_days: { type: 'int', required: false },
      row_count: { type: 'int', required: false, defaultValue: 0 },
      status: { type: 'string', required: false }
    });

    const counts = { ok: 0, stale: 0, empty: 0, error: 0 };
    validated.forEach(r => { counts[r.status] = (counts[r.status] || 0) + 1; });

    const criticalStale = validated.filter(
      r => r.status !== 'ok' && (r.role || '') === 'CRITICAL'
    );

    // Only mark ready_to_trade true if we actually have data rows to check
    const ready_to_trade = validated.length > 0 && criticalStale.length === 0;

    return sendSuccess(res, {
      summary: counts,
      critical_stale: criticalStale.map(r => r.table_name),
      ready_to_trade,
      sources: validated.map(r => ({
        table: r.table_name,
        frequency: r.frequency,
        role: r.role,
        latest: r.latest_date,
        age_days: r.age_days,
        rows: r.row_count,
        status: r.status,
        last_audit: null,
        error: null,
      })),
    });
  } catch (error) {
    logger.error('Error in /algo/data-status:', { error: error.message, stack: error.stack });
    return sendDatabaseError(res, error, 'An error occurred while checking data status');
  }
});

// ============================================================
// EXPOSURE POLICY â€” current tier rules
// ============================================================
router.get('/exposure-policy', async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();
    const tiers = await getActiveTiers();

    // Find active tier from latest exposure
    const latest = await pool.query(`SELECT exposure_pct FROM market_exposure_daily ORDER BY date DESC LIMIT 1`);
    const exp = latest.rows[0] ? parseFloat(latest.rows[0].exposure_pct) : null;
    const active = exp !== null
      ? getActiveTier(exp, tiers)
      : null;

    return sendSuccess(res, {
      current_exposure_pct: exp,
      active_tier: active,
      all_tiers: tiers,
    });
  } catch (error) {
    logger.error('Error in /algo/exposure-policy:', { error: error.message, stack: error.stack });
    return sendDatabaseError(res, error, 'An error occurred while fetching exposure policy');
  }
});

// ============================================================
// RUN ORCHESTRATOR â€” trigger the daily algo workflow from UI (admin only)
// ============================================================
router.post('/run', requireAuth, requireAdmin, async (req, res) => {
  const { spawn } = require('child_process');
  const path = require('path');

  try {
    const dryRun = req.body?.dry_run !== false;  // default to dry-run for safety
    const date = req.body?.date || null;

    // Validate date format (YYYY-MM-DD) to prevent command injection
    if (date && !/^\d{4}-\d{2}-\d{2}$/.test(date)) {
      return sendError(res, 'Invalid date format. Expected YYYY-MM-DD', 400);
    }

    const args = ['algo_orchestrator.py'];
    if (date) args.push('--date', date);
    if (dryRun) args.push('--dry-run');

    const repoRoot = path.resolve(__dirname, '../../..');
    const child = spawn('python3', args, { cwd: repoRoot, env: process.env });

    const runId = `RUN-${new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)}`;
    const output = [];
    let exitCode = null;

    child.stdout.on('data', (chunk) => {
      output.push(chunk.toString());
    });
    child.stderr.on('data', (chunk) => {
      output.push(chunk.toString());
    });

    // Return immediately so the UI can poll, but also stream after completion
    // For simplicity we'll do synchronous version with timeout
    const result = await new Promise((resolve) => {
      const timeout = setTimeout(() => {
        try { child.kill('SIGTERM'); } catch (_e) {
          // Ignore error if process already exited
        }
        resolve({ timeout: true, exitCode: -1, output });
      }, 180000);  // 3 minute timeout

      child.on('exit', (code) => {
        clearTimeout(timeout);
        exitCode = code;
        resolve({ timeout: false, exitCode: code, output });
      });
    });

    return sendSuccess(res, {
      run_id: runId,
      dry_run: dryRun,
      date: date || 'auto',
      exit_code: result.exitCode,
      timeout: result.timeout || false,
      output: result.output.join('')
    });
  } catch (error) {
    logger.error('Error in /algo/run:', { error: error.message, stack: error.stack });
    return sendError(res, 'An error occurred while running the algorithm', 500);
  }
});

// ============================================================
// RUN DATA PATROL â€” trigger watchdog from UI (admin only)
// ============================================================
router.post('/patrol', requireAuth, requireAdmin, async (req, res) => {
  const { spawn } = require('child_process');
  const path = require('path');

  try {
    const quick = req.body?.quick === true;
    const validateAlpaca = req.body?.validate_alpaca === true;

    const args = ['algo_data_patrol.py'];
    if (quick) args.push('--quick');
    if (validateAlpaca) args.push('--validate-alpaca');

    const repoRoot = path.resolve(__dirname, '../../..');
    const child = spawn('python3', args, { cwd: repoRoot, env: process.env });
    const output = [];

    const result = await new Promise((resolve) => {
      const timeout = setTimeout(() => {
        try { child.kill('SIGTERM'); } catch (_e) {
          // Ignore error if process already exited
        }
        resolve({ timeout: true, exitCode: -1, output });
      }, 60000);

      child.stdout.on('data', (c) => output.push(c.toString()));
      child.stderr.on('data', (c) => output.push(c.toString()));
      child.on('exit', (code) => {
        clearTimeout(timeout);
        resolve({ timeout: false, exitCode: code, output });
      });
    });

    return sendSuccess(res, {
      ready_to_trade: result.exitCode === 0,
      exit_code: result.exitCode,
      output: result.output.join('')
    });
  } catch (error) {
    logger.error('Error in /algo/patrol:', { error: error.message, stack: error.stack });
    return sendError(res, 'An error occurred while running data patrol', 500);
  }
});

// ============================================================
// PATROL HISTORY â€” recent patrol log entries (admin only)
// ============================================================
router.get('/patrol-log', requireAuth, requireAdmin, async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();
    const { limit } = paginationConfig.sanitize(req.query.limit, req.query.offset, 'logs');
    const minSeverity = req.query.min_severity || 'warn';
    const sevOrder = { info: 0, warn: 1, error: 2, critical: 3 };
    const minSev = sevOrder[minSeverity] || 1;
    const allowedSevs = Object.keys(sevOrder).filter(k => sevOrder[k] >= minSev);

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
        id: { type: 'int', required: true },
        patrol_run_id: { type: 'string', required: false },
        check_name: { type: 'string', required: false },
        severity: { type: 'string', required: false },
        target_table: { type: 'string', required: false },
        message: { type: 'string', required: false },
        details: { type: 'raw', required: false },
        created_at: { type: 'date', required: false }
      }).map(r => ({
        id: r.id,
        run_id: r.patrol_run_id,
        check_name: r.check_name,
        severity: r.severity,
        target_table: r.target_table,
        message: r.message,
        details: r.details,
        created_at: r.created_at,
      }))
    });
  } catch (error) {
    logger.error('Error in /algo/patrol-log:', { error: error.message, stack: error.stack });
    return sendDatabaseError(res, error, 'An error occurred while fetching patrol logs');
  }
});

// ============================================================
// NOTIFICATIONS â€” surface CRITICAL events to UI as toasts
// ============================================================
router.get('/notifications', authenticateToken, async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();
    const { limit } = paginationConfig.sanitize(req.query.limit, req.query.offset, 'logs');
    const kind = req.query.kind || null;
    const severity = req.query.severity || null;
    const unread = req.query.unread === 'true';

    let sql = `SELECT id, kind, severity, title, message, symbol, details, seen, created_at
               FROM algo_notifications
               WHERE 1=1`;
    const params = [];

    if (unread) {
      sql += ` AND seen = FALSE`;
    }
    if (kind && kind !== 'all') {
      sql += ` AND kind = $${params.length + 1}`;
      params.push(kind);
    }
    if (severity && severity !== 'all') {
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
        id: { type: 'int', required: true },
        kind: { type: 'string', required: false },
        severity: { type: 'string', required: false },
        title: { type: 'string', required: false },
        message: { type: 'string', required: false },
        symbol: { type: 'string', required: false },
        details: { type: 'raw', required: false },
        seen: { type: 'bool', required: false },
        created_at: { type: 'date', required: false }
      })
    });
  } catch (error) {
    logger.error('Error fetching notifications:', { error: error.message, stack: error.stack });
    return sendDatabaseError(res, error, 'An error occurred while fetching notifications');
  }
});

// Mark single notification as read (PATCH)
router.patch('/notifications/:id/read', authenticateToken, requireAdmin, async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();
    const { id } = req.params;
    const result = await pool.query(
      `UPDATE algo_notifications SET seen = TRUE, seen_at = CURRENT_TIMESTAMP WHERE id = $1`,
      [id]
    );
    return sendSuccess(res, { updated: result.rowCount, timestamp: new Date() });
  } catch (error) {
    logger.error('Error marking notification as read:', { error: error.message, stack: error.stack });
    return sendDatabaseError(res, error, 'An error occurred while updating notification');
  }
});

// Delete single notification
router.delete('/notifications/:id', authenticateToken, requireAdmin, async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();
    const { id } = req.params;
    const result = await pool.query(`DELETE FROM algo_notifications WHERE id = $1`, [id]);
    return sendSuccess(res, { deleted: result.rowCount, timestamp: new Date() });
  } catch (error) {
    logger.error('Error deleting notification:', { error: error.message, stack: error.stack });
    return sendDatabaseError(res, error, 'An error occurred while deleting notification');
  }
});

// Batch mark as seen (legacy endpoint)
router.post('/notifications/seen', authenticateToken, async (req, res) => {
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
    logger.error('Error marking notifications as seen:', { error: error.message, stack: error.stack });
    return sendDatabaseError(res, error, 'An error occurred while updating notifications');
  }
});

// ============================================================
// PRE-TRADE SIMULATION â€” what would the algo do? (admin only)
// ============================================================
router.post('/simulate', requireAuth, requireAdmin, async (req, res) => {
  const { spawn } = require('child_process');
  const path = require('path');
  try {
    const date = req.body?.date || null;

    // Validate date format (YYYY-MM-DD) to prevent command injection
    if (date && !/^\d{4}-\d{2}-\d{2}$/.test(date)) {
      return sendError(res, 'Invalid date format. Expected YYYY-MM-DD', 400);
    }

    const args = ['algo_orchestrator.py', '--dry-run'];
    if (date) args.push('--date', date);

    const repoRoot = path.resolve(__dirname, '../../..');
    const child = spawn('python3', args, { cwd: repoRoot, env: process.env });
    const output = [];
    const result = await new Promise((resolve) => {
      const timeout = setTimeout(() => {
        try { child.kill('SIGTERM'); } catch (_e) {
          // Ignore error if process already exited
        }
        resolve({ timeout: true, exitCode: -1, output });
      }, 120000);
      child.stdout.on('data', (c) => output.push(c.toString()));
      child.stderr.on('data', (c) => output.push(c.toString()));
      child.on('exit', (code) => {
        clearTimeout(timeout);
        resolve({ timeout: false, exitCode: code, output });
      });
    });

    return sendSuccess(res, {
      exit_code: result.exitCode,
      output: result.output.join('')
    });
  } catch (error) {
    logger.error('Error in /algo/simulate-execution:', { error: error.message, stack: error.stack });
    return sendError(res, 'An error occurred while simulating trade execution', 500);
  }
});

// ============================================================
// ============================================================
// PRE-TRADE SIMULATION â€” Impact analysis before execution
// ============================================================
router.post('/pre-trade-impact', requireAuth, requireAdmin, async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();
    const { symbol, entry_price, position_dollars, position_pct } = req.body;

    if (!symbol || (!position_dollars && !position_pct)) {
      return sendError(res, 'symbol and (position_dollars or position_pct) required', 400);
    }

    // Call stored procedure to compute all impact metrics in database
    const result = await pool.query(`
      SELECT
        position_size_dollars, position_size_percent, new_total_positions,
        new_sector_percent, new_sector_invested, drawdown_impact_pct,
        sector_name, sector_count,
        meets_position_limit, meets_size_limit, meets_sector_limit,
        meets_cash_requirement, meets_risk_limit
      FROM calculate_pretrade_impact($1, $2, $3, $4)
    `, [symbol.toUpperCase(), entry_price || null, position_dollars || null, position_pct || null]);

    if (!result.rows.length) {
      return sendError(res, `Unable to calculate impact for ${symbol}`, 500);
    }

    const impact = validateAndCoerceRow(result.rows[0], {
      position_size_dollars: { type: 'float', required: false },
      position_size_percent: { type: 'float', required: false },
      new_total_positions: { type: 'int', required: false },
      new_sector_percent: { type: 'float', required: false },
      new_sector_invested: { type: 'float', required: false },
      drawdown_impact_pct: { type: 'float', required: false },
      sector_name: { type: 'string', required: false },
      sector_count: { type: 'int', required: false },
      meets_position_limit: { type: 'bool', required: false },
      meets_size_limit: { type: 'bool', required: false },
      meets_sector_limit: { type: 'bool', required: false },
      meets_cash_requirement: { type: 'bool', required: false },
      meets_risk_limit: { type: 'bool', required: false }
    });

    const allOk = impact.meets_position_limit && impact.meets_size_limit &&
                  impact.meets_sector_limit && impact.meets_cash_requirement &&
                  impact.meets_risk_limit;

    return sendSuccess(res, {
      symbol: symbol.toUpperCase(),
      entry_price: parseFloat(entry_price || 0),
      position_size_dollars: parseFloat(impact.position_size_dollars || 0),
      position_size_percent: parseFloat(impact.position_size_percent || 0),
      sector: impact.sector_name,

      portfolio_impact: {
        new_total_positions: impact.new_total_positions,
        position_limit: 6,
        position_limit_ok: impact.meets_position_limit,

        new_position_percent: parseFloat(impact.position_size_percent || 0),
        max_position_percent: 15,
        position_size_ok: impact.meets_size_limit,

        new_sector_percent: parseFloat(impact.new_sector_percent || 0),
        max_sector_percent: 30,
        sector_limit_ok: impact.meets_sector_limit,

        worst_case_drawdown_impact: parseFloat(impact.drawdown_impact_pct || 0),
        max_acceptable_impact: 0.05,
        drawdown_risk_ok: impact.meets_risk_limit,

        cash_required: parseFloat(impact.position_size_dollars || 0),
        cash_available: 0,
        cash_ok: impact.meets_cash_requirement
      },

      all_constraints_met: allOk,
      recommendation: allOk ? 'READY TO TRADE' : 'CONSTRAINTS VIOLATED'
    });
  } catch (error) {
    logger.error('Pre-trade impact error:', { error: error.message, stack: error.stack });
    return sendDatabaseError(res, error, 'An error occurred while analyzing trade impact');
  }
});

// PERFORMANCE METRICS â€” Sharpe, Sortino, Calmar, max DD, profit factor
// ============================================================
router.get('/performance', authenticateToken, async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();

    // PHASE 1 FIX: Fetch pre-computed metrics from algo_performance_daily (O(1) instead of O(N))
    // Instead of fetching all trades and snapshots and recalculating on every request,
    // use the pre-computed daily metrics from the loader.
    const perfResult = await pool.query(`
      SELECT
        total_trades, num_wins as winning_trades, num_losses as losing_trades,
        win_rate_all as win_rate_pct,
        avg_win_pct, avg_loss_pct, avg_r as avg_win_r, avg_loss_r,
        expectancy as expectancy_r, profit_factor,
        total_pnl_dollars, gross_win_dollars, gross_loss_dollars, total_return_pct,
        rolling_sharpe_252d as sharpe_annualized,
        rolling_sortino_252d as sortino_annualized,
        calmar_ratio, max_drawdown_pct,
        current_win_streak, best_win_streak, worst_loss_streak,
        avg_hold_days, portfolio_snapshots_count
      FROM algo_performance_daily
      WHERE report_date = CURRENT_DATE
      ORDER BY report_date DESC LIMIT 1
    `);

    // Validate result
    validateQueryResult(perfResult, { requireRows: false });

    if (perfResult.rows.length === 0) {
      // Fallback: data not yet computed for today, return empty metrics
      logger.warn('No performance data computed for today; returning default metrics');
      return sendSuccess(res, {
        total_trades: 0,
        winning_trades: 0,
        losing_trades: 0,
        win_rate_pct: 0,
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
        sharpe_annualized: 0,
        sortino_annualized: 0,
        calmar_ratio: 0,
        max_drawdown_pct: 0,
        current_streak: 0,
        best_win_streak: 0,
        worst_loss_streak: 0,
        avg_hold_days: 0,
        portfolio_snapshots: 0,
      });
    }

    const perf = validateAndCoerceRow(perfResult.rows[0], {
      total_trades: { type: 'int', required: false, defaultValue: 0 },
      winning_trades: { type: 'int', required: false, defaultValue: 0 },
      losing_trades: { type: 'int', required: false, defaultValue: 0 },
      win_rate_pct: { type: 'float', required: false, defaultValue: 0 },
      avg_win_pct: { type: 'float', required: false, defaultValue: 0 },
      avg_loss_pct: { type: 'float', required: false, defaultValue: 0 },
      avg_win_r: { type: 'float', required: false, defaultValue: 0 },
      avg_loss_r: { type: 'float', required: false, defaultValue: 0 },
      expectancy_r: { type: 'float', required: false, defaultValue: 0 },
      profit_factor: { type: 'float', required: false, defaultValue: null },
      total_pnl_dollars: { type: 'float', required: false, defaultValue: 0 },
      gross_win_dollars: { type: 'float', required: false, defaultValue: 0 },
      gross_loss_dollars: { type: 'float', required: false, defaultValue: 0 },
      total_return_pct: { type: 'float', required: false, defaultValue: 0 },
      sharpe_annualized: { type: 'float', required: false, defaultValue: 0 },
      sortino_annualized: { type: 'float', required: false, defaultValue: 0 },
      calmar_ratio: { type: 'float', required: false, defaultValue: 0 },
      max_drawdown_pct: { type: 'float', required: false, defaultValue: 0 },
      current_win_streak: { type: 'int', required: false, defaultValue: 0 },
      best_win_streak: { type: 'int', required: false, defaultValue: 0 },
      worst_loss_streak: { type: 'int', required: false, defaultValue: 0 },
      avg_hold_days: { type: 'float', required: false, defaultValue: 0 },
      portfolio_snapshots_count: { type: 'int', required: false, defaultValue: 0 }
    });

    return sendSuccess(res, {
      // Trade counts
      total_trades: perf.total_trades || 0,
      winning_trades: perf.winning_trades || 0,
      losing_trades: perf.losing_trades || 0,

      // Win/loss profile
      win_rate_pct: parseFloat(perf.win_rate_pct) || 0,
      avg_win_pct: parseFloat(perf.avg_win_pct) || 0,
      avg_loss_pct: parseFloat(perf.avg_loss_pct) || 0,
      avg_win_r: parseFloat(perf.avg_win_r) || 0,
      avg_loss_r: parseFloat(perf.avg_loss_r) || 0,

      // Expectancy
      expectancy_r: parseFloat(perf.expectancy_r) || 0,
      profit_factor: perf.profit_factor ? parseFloat(perf.profit_factor) : null,

      // Total
      total_pnl_dollars: parseFloat(perf.total_pnl_dollars) || 0,
      gross_win_dollars: parseFloat(perf.gross_win_dollars) || 0,
      gross_loss_dollars: parseFloat(perf.gross_loss_dollars) || 0,
      total_return_pct: parseFloat(perf.total_return_pct) || 0,

      // Risk-adjusted
      sharpe_annualized: parseFloat(perf.sharpe_annualized) || 0,
      sortino_annualized: parseFloat(perf.sortino_annualized) || 0,
      calmar_ratio: parseFloat(perf.calmar_ratio) || 0,
      max_drawdown_pct: parseFloat(perf.max_drawdown_pct) || 0,

      // Streaks + duration
      current_streak: perf.current_win_streak || 0,
      best_win_streak: perf.best_win_streak || 0,
      worst_loss_streak: perf.worst_loss_streak || 0,
      avg_hold_days: parseFloat(perf.avg_hold_days) || 0,

      // Sample sizes
      portfolio_snapshots: perf.portfolio_snapshots_count || 0,
    });
  } catch (error) {
    logger.error('Error in /api/algo/performance:', { error: error.message, stack: error.stack });
    return sendDatabaseError(res, error, 'An error occurred while fetching performance metrics');
  }
});

/**
 * GET /api/algo/equity-curve
 * Time-series of portfolio value from algo_portfolio_snapshots
 * Used by Portfolio Dashboard equity-curve chart.
 */
router.get('/equity-curve', authenticateToken, async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();
    const { limit } = paginationConfig.sanitize(req.query.limit, req.query.offset, 'portfolio');
    const result = await pool.query(`
      SELECT snapshot_date, total_portfolio_value, daily_return_pct,
             unrealized_pnl_pct, position_count, drawdown_pct
      FROM algo_portfolio_snapshots
      ORDER BY snapshot_date DESC
      LIMIT $1
    `, [limit]);

    // Validate result structure
    validateQueryResult(result, { requireRows: false });

    // Validate and coerce row types - drawdown_pct now comes from DB
    const validated = validateAndCoerceRows(result, {
      snapshot_date: { type: 'date', required: true },
      total_portfolio_value: { type: 'float', required: false, defaultValue: 0 },
      daily_return_pct: { type: 'float', required: false, defaultValue: 0 },
      unrealized_pnl_pct: { type: 'float', required: false, defaultValue: 0 },
      position_count: { type: 'int', required: false, defaultValue: 0 },
      drawdown_pct: { type: 'float', required: false, defaultValue: 0 }
    });

    // Reverse to chronological order (oldest first)
    const chronological = validated.reverse();

    return sendSuccess(res, {
      items: chronological
    });
  } catch (error) {
    logger.error('Error in /algo/equity-curve:', { error: error.message, stack: error.stack });
    return sendDatabaseError(res, error, 'An error occurred while fetching equity curve');
  }
});

// ============================================================
// AUDIT LOG â€” every algo decision logged (admin only)
// ============================================================
router.get('/audit-log', requireAuth, requireAdmin, async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();
    const { limit } = paginationConfig.sanitize(req.query.limit, req.query.offset, 'audit');
    const actionFilter = req.query.action_type || null;

    let query_str = `
      SELECT id, action_type, symbol, action_date, details, actor, status,
             error_message, created_at
      FROM algo_audit_log
    `;
    const params = [];
    if (actionFilter) {
      query_str += ' WHERE action_type LIKE $1';
      params.push(`%${actionFilter}%`);
    }
    query_str += ` ORDER BY created_at DESC LIMIT $${params.length + 1}`;
    params.push(limit);

    const result = await pool.query(query_str, params);

    // Validate result structure
    validateQueryResult(result, { requireRows: false });

    return sendSuccess(res, {
      items: validateAndCoerceRows(result, {
        id: { type: 'int', required: true },
        action_type: { type: 'string', required: false },
        symbol: { type: 'string', required: false },
        action_date: { type: 'date', required: false },
        details: { type: 'raw', required: false },
        actor: { type: 'string', required: false },
        status: { type: 'string', required: false },
        error_message: { type: 'string', required: false },
        created_at: { type: 'date', required: false }
      }).map(r => ({
        id: r.id,
        action_type: r.action_type,
        symbol: r.symbol,
        action_date: r.action_date,
        details: r.details,
        actor: r.actor,
        status: r.status,
        error: r.error_message,
        created_at: r.created_at,
      }))
    });
  } catch (error) {
    logger.error('Error in /algo/audit-log:', { error: error.message, stack: error.stack });
    return sendDatabaseError(res, error, 'An error occurred while fetching audit logs');
  }
});

// ============================================================
// TRADE DETAIL â€” full reasoning for a single trade
// ============================================================
router.get('/trade/:tradeId', async (req, res) => {
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
      return sendError(res, 'Trade not found', 404);
    }

    // Validate and coerce the single row
    const trade = validateAndCoerceRow(result.rows[0], {
      trade_id: { type: 'int', required: true },
      symbol: { type: 'string', required: false },
      entry_price: { type: 'float', required: false },
      exit_price: { type: 'float', required: false },
      profit_loss_dollars: { type: 'float', required: false },
      profit_loss_pct: { type: 'float', required: false },
      status: { type: 'string', required: false },
      position_id: { type: 'int', required: false },
      quantity: { type: 'float', required: false },
      current_qty: { type: 'float', required: false },
      current_price: { type: 'float', required: false },
      unrealized_pnl: { type: 'float', required: false },
      unrealized_pnl_pct: { type: 'float', required: false },
      target_levels_hit: { type: 'string', required: false },
      current_stop_price: { type: 'float', required: false }
    });

    return sendSuccess(res, trade);
  } catch (error) {
    logger.error('Error in /algo/trade/:id:', { error: error.message, stack: error.stack });
    return sendDatabaseError(res, error, 'An error occurred while fetching trade details');
  }
});


// ============================================================
// CIRCUIT BREAKERS â€” current state of all 7 kill-switches (admin only)
// ============================================================
router.get('/circuit-breakers', requireAuth, requireAdmin, async (req, res) => {
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
      `)
    ]);

    // Validate results
    validateQueryResult(cbResult, { requireRows: false });
    validateQueryResult(marketResult, { requireRows: false });

    // Get circuit breaker metrics (or defaults if not yet computed for today)
    const cbRow = cbResult.rows.length > 0
      ? validateAndCoerceRow(cbResult.rows[0], {
          portfolio_drawdown_pct: { type: 'float', required: false, defaultValue: 0 },
          daily_loss_pct: { type: 'float', required: false, defaultValue: 0 },
          weekly_loss_pct: { type: 'float', required: false, defaultValue: 0 },
          open_risk_pct: { type: 'float', required: false, defaultValue: 0 },
          consecutive_losses: { type: 'int', required: false, defaultValue: 0 },
          vix_level: { type: 'float', required: false, defaultValue: 0 },
          market_stage: { type: 'int', required: false, defaultValue: 1 },
          spy_prior_day_change_pct: { type: 'float', required: false, defaultValue: 0 },
          win_rate_last_30_pct: { type: 'float', required: false, defaultValue: 0 }
        })
      : { portfolio_drawdown_pct: 0, daily_loss_pct: 0, weekly_loss_pct: 0, open_risk_pct: 0,
          consecutive_losses: 0, vix_level: 0, market_stage: 1, spy_prior_day_change_pct: 0, win_rate_last_30_pct: 0 };

    const marketTrend = marketResult.rows.length > 0
      ? validateAndCoerceRow(marketResult.rows[0], { market_trend: { type: 'string', required: false } }).market_trend || 'unknown'
      : 'unknown';

    const metrics = {
      current_drawdown_pct: cbRow.portfolio_drawdown_pct,
      daily_loss_pct: cbRow.daily_loss_pct,
      weekly_loss_pct: cbRow.weekly_loss_pct,
      consec_losses: cbRow.consecutive_losses,
      total_risk_pct: cbRow.open_risk_pct,
      vix_level: cbRow.vix_level,
      market_stage: cbRow.market_stage,
      market_trend: marketTrend
    };

    // Pull config (with sensible defaults if rows missing)
    const cfgResult = await pool.query(
      `SELECT key, value FROM algo_config WHERE key = ANY($1)`,
      [[
        'halt_drawdown_pct', 'max_daily_loss_pct', 'max_consecutive_losses',
        'max_total_risk_pct', 'vix_max_threshold', 'max_weekly_loss_pct',
      ]]
    );

    // Validate config result
    validateQueryResult(cfgResult, { requireRows: false });

    const cfg = {};
    validateAndCoerceRows(cfgResult, {
      key: { type: 'string', required: true },
      value: { type: 'string', required: true }
    }).forEach(r => { cfg[r.key] = parseFloat(r.value); });
    const thresh = {
      drawdown:           cfg.halt_drawdown_pct ?? 20,
      daily_loss:         cfg.max_daily_loss_pct ?? 2,
      consecutive_losses: cfg.max_consecutive_losses ?? 3,
      total_risk:         cfg.max_total_risk_pct ?? 4,
      vix_spike:          cfg.vix_max_threshold ?? 35,
      weekly_loss:        cfg.max_weekly_loss_pct ?? 5,
    };

    const breakers = [
      { id: 'drawdown', label: 'Portfolio Drawdown',
        current: metrics.current_drawdown_pct, threshold: thresh.drawdown,
        unit: '%', triggered: metrics.current_drawdown_pct >= thresh.drawdown,
        description: 'Halts entries when total drawdown from peak exceeds threshold' },
      { id: 'daily_loss', label: 'Daily Loss',
        current: metrics.daily_loss_pct, threshold: thresh.daily_loss,
        unit: '%', triggered: metrics.daily_loss_pct >= thresh.daily_loss,
        description: 'Today\'s portfolio drop below threshold halts new entries' },
      { id: 'consecutive_losses', label: 'Consecutive Losses',
        current: metrics.consec_losses, threshold: thresh.consecutive_losses,
        unit: '', triggered: metrics.consec_losses >= thresh.consecutive_losses,
        description: 'Cool-off after streak of losing trades' },
      { id: 'total_risk', label: 'Total Open Risk',
        current: metrics.total_risk_pct, threshold: thresh.total_risk,
        unit: '%', triggered: metrics.total_risk_pct >= thresh.total_risk,
        description: 'Sum of distance-to-stop across all open positions' },
      { id: 'vix_spike', label: 'VIX Spike',
        current: metrics.vix_level, threshold: thresh.vix_spike,
        unit: '', triggered: metrics.vix_level > thresh.vix_spike,
        description: 'Volatility expansion above threshold pauses new entries' },
      { id: 'market_stage', label: 'Market Stage',
        current: metrics.market_stage, threshold: 4,
        unit: '', triggered: metrics.market_stage === 4,
        description: `Market in stage ${metrics.market_stage} (${metrics.market_trend}) â€” stage 4 = downtrend halts entries` },
      { id: 'weekly_loss', label: 'Weekly Loss',
        current: metrics.weekly_loss_pct, threshold: thresh.weekly_loss,
        unit: '%', triggered: metrics.weekly_loss_pct >= thresh.weekly_loss,
        description: 'Trailing 5-session loss above threshold halts new entries' },
    ];

    return sendSuccess(res, {
      any_triggered: breakers.some(b => b.triggered),
      triggered_count: breakers.filter(b => b.triggered).length,
      breakers,
    });
  } catch (error) {
    logger.error('Error in /algo/circuit-breakers:', { error: error.message, stack: error.stack });
    return sendDatabaseError(res, error, 'An error occurred while fetching circuit breaker status');
  }
});

// ============================================================
// SECTOR BREADTH â€” % of stocks above 50d / 200d MA per sector
// ============================================================
router.get('/sector-breadth', async (req, res) => {
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
        sector: { type: 'string', required: true },
        total_stocks: { type: 'int', required: false, defaultValue: 0 },
        above_50d: { type: 'int', required: false, defaultValue: 0 },
        above_200d: { type: 'int', required: false, defaultValue: 0 },
        pct_above_50d: { type: 'float', required: false, defaultValue: 0 },
        pct_above_200d: { type: 'float', required: false, defaultValue: 0 }
      }).map(r => ({
        sector: r.sector,
        total_stocks: r.total_stocks || 0,
        above_50d: r.above_50d || 0,
        above_200d: r.above_200d || 0,
        pct_above_50d: r.pct_above_50d || 0,
        pct_above_200d: r.pct_above_200d || 0,
      }))
    });
  } catch (error) {
    logger.error('Error in /algo/sector-breadth:', { error: error.message, stack: error.stack });
    return sendDatabaseError(res, error, 'An error occurred while calculating sector breadth');
  }
});

// ============================================================
// SECTOR STAGE-2 LEADERS â€” Stage 2 stocks per sector
// ============================================================
router.get('/sector-stage2', async (req, res) => {
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
        sector: { type: 'string', required: true },
        total_stocks: { type: 'int', required: false, defaultValue: 0 },
        stage_1: { type: 'int', required: false, defaultValue: 0 },
        stage_2: { type: 'int', required: false, defaultValue: 0 },
        stage_3: { type: 'int', required: false, defaultValue: 0 },
        stage_4: { type: 'int', required: false, defaultValue: 0 },
        avg_trend_score: { type: 'float', required: false },
        pct_stage_2: { type: 'float', required: false, defaultValue: 0 }
      }).map(r => ({
        sector: r.sector,
        total: r.total_stocks || 0,
        stage_1: r.stage_1 || 0,
        stage_2: r.stage_2 || 0,
        stage_3: r.stage_3 || 0,
        stage_4: r.stage_4 || 0,
        pct_stage_2: r.pct_stage_2 || 0,
        avg_trend_score: r.avg_trend_score,
      }))
    });
  } catch (error) {
    logger.error('Error in /algo/sector-stage2:', { error: error.message, stack: error.stack });
    return sendDatabaseError(res, error, 'An error occurred while analyzing sector stage 2 leaders');
  }
});

// ============================================================
// SECTOR ROTATION SIGNAL â€” defensive vs cyclical leadership timeline
// ============================================================
router.get('/sector-rotation', async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();
    const { limit } = paginationConfig.sanitize(req.query.limit, req.query.offset, 'security');

    const result = await pool.query(
      `SELECT date, sector, signal, strength, rank, details
       FROM sector_rotation_signal
       ORDER BY date DESC, rank ASC NULLS LAST LIMIT $1`,
      [limit]
    );

    // Validate result structure
    validateQueryResult(result, { requireRows: false });

    const parseDetailsJSON = (details) => {
      if (!details) return {};
      if (typeof details === 'object') return details;
      if (typeof details !== 'string') return {};
      try {
        return JSON.parse(details);
      } catch (e) {
        logger.warn(`Failed to parse sector_rotation_signal details: ${details.substring(0, 100)}`, { error: e.message });
        return {};
      }
    };

    return sendSuccess(res, {
      items: validateAndCoerceRows(result, {
        date: { type: 'date', required: false },
        sector: { type: 'string', required: false },
        signal: { type: 'string', required: false },
        strength: { type: 'float', required: false, defaultValue: 0 },
        rank: { type: 'int', required: false },
        details: { type: 'raw', required: false }
      }).map(r => ({
        date: r.date,
        sector: r.sector,
        signal: r.signal,
        strength: r.strength || 0,
        rank: r.rank,
        ...parseDetailsJSON(r.details),
      }))
    });
  } catch (error) {
    logger.error('Error in /algo/sector-rotation:', { error: error.message, stack: error.stack });
    return sendDatabaseError(res, error, 'An error occurred while analyzing sector rotation');
  }
});

/**
 * GET /api/algo/sector-position-warnings
 * Get sector position concentration warnings (sector allocation alerts)
 */
router.get('/sector-position-warnings', async (req, res) => {
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
    if (configResult.rows && configResult.rows.length > 0 && configResult.rows[0].value) {
      max_per_sector = parseInt(configResult.rows[0].value, 10);
    }

    const sector_counts = sectorResult.rows || [];
    const warnings = [];
    const at_cap = [];

    for (const row of sector_counts) {
      const sector = row.sector || 'Unknown';
      const count = row.position_count || 0;

      if (count >= max_per_sector) {
        at_cap.push({
          sector: sector,
          position_count: count,
          max: max_per_sector,
          status: 'AT_CAP'
        });
      } else if (count >= max_per_sector - 1) {
        warnings.push({
          sector: sector,
          position_count: count,
          max: max_per_sector,
          status: 'NEAR_CAP'
        });
      }
    }

    return sendSuccess(res, {
      warnings: warnings,
      at_cap: at_cap,
      data: {
        warnings: warnings,
        at_cap: at_cap
      }
    });
  } catch (error) {
    logger.error('Error in /algo/sector-position-warnings:', { error: error.message, stack: error.stack });
    return sendDatabaseError(res, error, 'An error occurred while fetching sector position warnings');
  }
});

// ============================================================
// PHASE 1-4 INTEGRATION: Data Quality, Signal Performance, Rejections, Orders
// ============================================================

/**
 * GET /api/algo/data-quality
 * Loader SLA status - check data freshness
 */
router.get('/data-quality', async (req, res) => {
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
      loader_name: { type: 'string', required: true },
      table_name: { type: 'string', required: true },
      latest_data_date: { type: 'string', required: false },
      age_hours: { type: 'float', required: false, defaultValue: 0 },
      max_age_hours: { type: 'int', required: false },
      row_count_today: { type: 'int', required: false },
      status: { type: 'string', required: false },
      error_message: { type: 'string', required: false }
    }).map(r => ({
      loader: r.loader_name,
      table: r.table_name,
      latest_date: r.latest_data_date,
      age_hours: r.age_hours || 0,
      max_age_hours: r.max_age_hours,
      row_count: r.row_count_today,
      status: r.status,
      error_message: r.error_message,
    }));

    const overall_status = checks.some(c => c.status === 'CRITICAL') ? 'critical'
                        : checks.some(c => c.status === 'WARNING') ? 'warning'
                        : 'ok';

    return sendSuccess(res, { status: overall_status, checks });
  } catch (error) {
    logger.error('Error in /algo/data-quality:', { error: error.message, stack: error.stack });
    return sendDatabaseError(res, error, 'An error occurred while checking data quality');
  }
});

/**
 * GET /api/algo/rejection-funnel?date=2026-05-06
 * Signal rejection funnel analysis
 */
router.get('/rejection-funnel', async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();
    const eval_date = req.query.date || new Date().toISOString().split('T')[0];

    const result = await pool.query(`
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
    `, [eval_date]);

    // Validate result structure
    validateQueryResult(result, { requireRows: false });

    const row = result.rows[0]
      ? validateAndCoerceRow(result.rows[0], {
          total: { type: 'int', required: false, defaultValue: 0 },
          t1_pass: { type: 'int', required: false, defaultValue: 0 },
          t2_pass: { type: 'int', required: false, defaultValue: 0 },
          t3_pass: { type: 'int', required: false, defaultValue: 0 },
          t4_pass: { type: 'int', required: false, defaultValue: 0 },
          t5_pass: { type: 'int', required: false, defaultValue: 0 },
          t1_reject: { type: 'int', required: false, defaultValue: 0 },
          t2_reject: { type: 'int', required: false, defaultValue: 0 },
          t3_reject: { type: 'int', required: false, defaultValue: 0 },
          t4_reject: { type: 'int', required: false, defaultValue: 0 },
          t5_reject: { type: 'int', required: false, defaultValue: 0 }
        })
      : { total: 0, t1_pass: 0, t2_pass: 0, t3_pass: 0, t4_pass: 0, t5_pass: 0,
          t1_reject: 0, t2_reject: 0, t3_reject: 0, t4_reject: 0, t5_reject: 0 };

    return sendSuccess(res, {
      date: eval_date,
      total_signals: row.total || 0,
      tiers: [
        { tier: 1, name: 'Data Quality', pass: row.t1_pass || 0, reject: row.t1_reject || 0 },
        { tier: 2, name: 'Market Health', pass: row.t2_pass || 0, reject: row.t2_reject || 0 },
        { tier: 3, name: 'Trend Confirmation', pass: row.t3_pass || 0, reject: row.t3_reject || 0 },
        { tier: 4, name: 'Signal Quality', pass: row.t4_pass || 0, reject: row.t4_reject || 0 },
        { tier: 5, name: 'Portfolio Health', pass: row.t5_pass || 0, reject: row.t5_reject || 0 },
      ],
    });
  } catch (error) {
    logger.error('Error in /algo/rejection-funnel:', { error: error.message, stack: error.stack });
    return sendDatabaseError(res, error, 'An error occurred while analyzing rejection funnel');
  }
});


/**
 * GET /api/algo/orders/pending
 * Pre-execution order review
 */
router.get('/orders/pending', authenticateToken, async (req, res) => {
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
      `)
    ]);

    // Validate result structures
    validateQueryResult(ordersResult, { requireRows: false });
    validateQueryResult(totalsResult, { minRows: 1, maxRows: 1 });

    const pending_orders = validateAndCoerceRows(ordersResult, {
      id: { type: 'int', required: true },
      trade_id: { type: 'int', required: false },
      symbol: { type: 'string', required: true },
      order_type: { type: 'string', required: false },
      side: { type: 'string', required: false },
      requested_shares: { type: 'float', required: false },
      requested_price: { type: 'float', required: false, defaultValue: 0 },
      order_timestamp: { type: 'date', required: false }
    }).map(r => ({
      order_id: r.id,
      trade_id: r.trade_id,
      symbol: r.symbol,
      order_type: r.order_type,
      side: r.side,
      requested_shares: r.requested_shares,
      requested_price: r.requested_price || 0,
      order_timestamp: r.order_timestamp,
    }));

    const totals = validateAndCoerceRow(totalsResult.rows[0], {
      order_count: { type: 'int', required: false, defaultValue: 0 },
      total_buy_value: { type: 'float', required: false, defaultValue: 0 }
    });

    return sendSuccess(res, {
      pending_orders,
      total_pending_value: totals.total_buy_value || 0,
      approval_required: totals.order_count > 0
    });
  } catch (error) {
    logger.error('Error in /algo/orders/pending:', { error: error.message, stack: error.stack });
    return sendDatabaseError(res, error, 'An error occurred while fetching pending orders');
  }
});

/**
 * GET /api/algo/execution-quality?days=30
 * Execution metrics: fill rate, slippage, etc.
 */
router.get('/execution-quality', authenticateToken, async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();
    const days = Math.min(Math.max(parseInt(req.query.days) || 30, 1), 365);  // Clamp to [1, 365]

    const result = await pool.query(`
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
    `, [days]);

    // Validate result structure
    validateQueryResult(result, { minRows: 1, maxRows: 1 });

    const row = validateAndCoerceRow(result.rows[0], {
      total_orders: { type: 'int', required: false, defaultValue: 0 },
      filled: { type: 'int', required: false, defaultValue: 0 },
      rejected: { type: 'int', required: false, defaultValue: 0 },
      partial: { type: 'int', required: false, defaultValue: 0 },
      avg_fill_rate: { type: 'float', required: false, defaultValue: 0 },
      avg_slippage_bps: { type: 'float', required: false, defaultValue: 0 },
      max_slippage_bps: { type: 'float', required: false, defaultValue: 0 },
      slippage_alert: { type: 'bool', required: false, defaultValue: false }
    });

    const metrics = {
      period: `last ${days} days`,
      total_orders: row.total_orders || 0,
      filled: row.filled || 0,
      rejected: row.rejected || 0,
      partial: row.partial || 0,
      fill_rate_pct: row.avg_fill_rate || 0,
      avg_slippage_bps: row.avg_slippage_bps || 0,
      max_slippage_bps: row.max_slippage_bps || 0,
      slippage_alert: row.slippage_alert || false,
    };

    return sendSuccess(res, { metrics });
  } catch (error) {
    logger.error('Error in /algo/execution-quality:', { error: error.message, stack: error.stack });
    return sendDatabaseError(res, error, 'An error occurred while analyzing execution quality');
  }
});


/**
 * GET /api/algo/signal-performance-by-pattern
 * Analyze trade performance grouped by signal pattern/type
 */
router.get('/signal-performance-by-pattern', async (req, res) => {
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
      pattern: { type: 'string', required: false, defaultValue: 'Unknown' },
      total_trades: { type: 'int', required: false, defaultValue: 0 },
      winning_trades: { type: 'int', required: false, defaultValue: 0 },
      losing_trades: { type: 'int', required: false, defaultValue: 0 },
      closed_trades: { type: 'int', required: false, defaultValue: 0 },
      avg_return_pct: { type: 'float', required: false, defaultValue: 0 },
      total_pnl: { type: 'float', required: false, defaultValue: 0 },
      win_rate_pct: { type: 'float', required: false, defaultValue: 0 }
    }).map(r => ({
      pattern: r.pattern,
      total_trades: r.total_trades || 0,
      winning_trades: r.winning_trades || 0,
      losing_trades: r.losing_trades || 0,
      closed_trades: r.closed_trades || 0,
      avg_return_pct: r.avg_return_pct || 0,
      total_pnl: r.total_pnl || 0,
      win_rate_pct: r.win_rate_pct || 0
    }));

    return sendSuccess(res, { patterns, timestamp: new Date() }, 200);
  } catch (error) {
    logger.error("Error in /algo/signal-performance-by-pattern:", { error: error.message, stack: error.stack });
    return sendDatabaseError(res, error, 'An error occurred while analyzing signal performance');
  }
});

/**
 * GET /api/algo/daily-return-histogram
 * Issue #2: Returns pre-computed daily return histogram with statistics
 * Reads from algo_daily_return_histogram table (computed daily by orchestrator)
 */
router.get('/daily-return-histogram', authenticateToken, async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();
    const result = await pool.query(`
      SELECT buckets, stats
      FROM algo_daily_return_histogram
      ORDER BY snapshot_date DESC
      LIMIT 1
    `);

    validateQueryResult(result, { requireRows: false });

    if (result.rows.length === 0) {
      return sendSuccess(res, {
        buckets: [],
        stats: null,
        count: 0,
        _error: 'Daily return histogram not available - algo still building trading history',
        _is_placeholder: true,
      });
    }

    const row = result.rows[0];
    const buckets = row.buckets || [];
    const stats = row.stats || { n: 0, mean: 0, std: 0 };

    return sendSuccess(res, {
      buckets,
      stats,
    });
  } catch (error) {
    logger.error('Error in /api/algo/daily-return-histogram:', { error: error.message, stack: error.stack });
    return sendSuccess(res, {
      buckets: [],
      stats: null,
      _error: error.message,
      _is_placeholder: true,
    });
  }
});

/**
 * GET /api/algo/trade-distribution
 * Issue #3: Returns pre-computed trade outcome distribution by R-multiple
 * Reads from algo_trade_r_distribution table (computed daily by orchestrator)
 */
router.get('/trade-distribution', authenticateToken, async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();
    const result = await pool.query(`
      SELECT buckets, total_trades
      FROM algo_trade_r_distribution
      ORDER BY snapshot_date DESC
      LIMIT 1
    `);

    validateQueryResult(result, { requireRows: false });

    if (result.rows.length === 0) {
      return sendSuccess(res, {
        buckets: [],
        total_trades: 0,
        _error: 'Trade distribution not available - no closed trades yet',
        _is_placeholder: true,
      });
    }

    const row = result.rows[0];
    const buckets = row.buckets || [];
    const totalTrades = row.total_trades || 0;

    return sendSuccess(res, {
      buckets,
      total_trades: totalTrades,
    });
  } catch (error) {
    logger.error('Error in /api/algo/trade-distribution:', { error: error.message, stack: error.stack });
    return sendSuccess(res, {
      buckets: [],
      total_trades: 0,
      _error: error.message,
      _is_placeholder: true,
    });
  }
});

/**
 * GET /api/algo/holding-period-distribution
 * Issue #4: Returns pre-computed holding period distribution by days held
 * Reads from algo_holding_period_histogram table (computed daily by orchestrator)
 */
router.get('/holding-period-distribution', authenticateToken, async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();
    const result = await pool.query(`
      SELECT buckets, total_trades
      FROM algo_holding_period_histogram
      ORDER BY snapshot_date DESC
      LIMIT 1
    `);

    validateQueryResult(result, { requireRows: false });

    if (result.rows.length === 0) {
      return sendSuccess(res, {
        buckets: [],
        total_trades: 0,
        _error: 'Holding period distribution not available - no closed trades yet',
        _is_placeholder: true,
      });
    }

    const row = result.rows[0];
    const buckets = row.buckets || [];
    const totalTrades = row.total_trades || 0;

    return sendSuccess(res, {
      buckets,
      total_trades: totalTrades,
    });
  } catch (error) {
    logger.error('Error in /api/algo/holding-period-distribution:', { error: error.message, stack: error.stack });
    return sendSuccess(res, {
      buckets: [],
      total_trades: 0,
      _error: error.message,
      _is_placeholder: true,
    });
  }
});

/**
 * GET /api/algo/stage-distribution
 * Stage phase distribution across open positions
 */
router.get('/stage-distribution', authenticateToken, async (req, res) => {
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

    const stageConfig = {
      stage_2_early_min_score: 0,
      stage_2_mid_min_score: 6,
      stage_2_late_min_score: 8,
    };
    for (const row of configResult.rows) {
      const val = parseFloat(row.value);
      if (!isNaN(val)) {
        stageConfig[row.key] = val;
      }
    }

    const counts = {};
    const order = ['Early Stage-2', 'Mid Stage-2', 'Late Stage-2',
                   'Stage 1 (base)', 'Stage 3 (top)', 'Stage 4 (down)', 'Unknown'];

    for (const row of posResult.rows) {
      const stage = row.weinstein_stage;
      const score = row.minervini_trend_score;
      let label = 'Unknown';
      if (stage === 1) {
        label = 'Stage 1 (base)';
      } else if (stage === 2) {
        if (score != null) {
          if (score >= stageConfig.stage_2_late_min_score) label = 'Late Stage-2';
          else if (score >= stageConfig.stage_2_mid_min_score) label = 'Mid Stage-2';
          else if (score >= stageConfig.stage_2_early_min_score) label = 'Early Stage-2';
          else label = 'Early Stage-2';
        } else {
          label = 'Stage 2';
        }
      } else if (stage === 3) {
        label = 'Stage 3 (top)';
      } else if (stage === 4) {
        label = 'Stage 4 (down)';
      }

      counts[label] = (counts[label] || 0) + 1;
    }

    const distribution = order
      .filter(k => counts[k])
      .map(k => ({ phase: k, count: counts[k] }));

    return sendSuccess(res, {
      distribution,
      total_positions: posResult.rows.length,
    });
  } catch (error) {
    logger.error('Error in /api/algo/stage-distribution:', { error: error.message, stack: error.stack });
    return sendDatabaseError(res, error, 'An error occurred while computing stage distribution');
  }
});

module.exports = router;


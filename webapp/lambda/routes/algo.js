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

const router = express.Router();

const requireAuth = authenticateToken;

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

    return sendSuccess(res, {
      algo_enabled: algo_enabled,
      execution_mode: execution_mode,
      status: 'operational',
      portfolio: {
        total_value: snapshot.total_portfolio_value || 0,
        position_count: positions.open_count,
        total_position_value: positions.total_value || 0,
        unrealized_pnl_pct: snapshot.unrealized_pnl_pct || 0,
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
    logger.error('Error in /algo/status:', { error: error.message });
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

    // Transform into evaluation objects
    // Thresholds match algo_filter_pipeline.py: tier1=45 (session 31), tier4=40 (session 30)
    const evaluated = validateAndCoerceRows(result, {
      symbol: { type: 'string', required: true },
      date: { type: 'date', required: true },
      trend_score: { type: 'int', required: false, defaultValue: 0 },
      pct_from_52w_low: { type: 'float', required: false, defaultValue: 0 },
      completeness_pct: { type: 'float', required: false, defaultValue: 0 },
      sqs: { type: 'int', required: false, defaultValue: 0 }
    }).map(row => {
      const tier1 = row.completeness_pct >= 45;
      const tier3 = row.trend_score >= 8;
      const tier4 = row.sqs >= 40;

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
        all_tiers_pass: tier1 && tier3 && tier4
      };
    });

    // Filter to qualified (pass all tiers) and sort by SQS, take top 12
    const qualified = evaluated.filter(e => e.all_tiers_pass).sort((a, b) => b.sqs - a.sqs).slice(0, 12);

    return sendSuccess(res, {
      total_buy_signals: evaluated.length,
      qualified_for_trading: qualified.length,
      signals: evaluated,
      top_qualified: qualified
    });
  } catch (error) {
    logger.error('Error in /algo/evaluate:', { error: error.message });
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
    logger.error('Error in /algo/last-run:', { error: error.message });
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

    const result = await pool.query(`
      WITH latest_trade AS (
        SELECT DISTINCT ON (symbol)
          symbol, stop_loss_price, target_1_price, target_2_price, target_3_price,
          target_1_r_multiple, target_2_r_multiple, target_3_r_multiple, signal_date
        FROM algo_trades
        WHERE status = 'open'
        ORDER BY symbol, trade_date DESC
      ),
      latest_trend AS (
        SELECT DISTINCT ON (symbol)
          symbol, weinstein_stage, minervini_trend_score,
          percent_from_52w_low, percent_from_52w_high
        FROM trend_template_data
        ORDER BY symbol, date DESC
      )
      SELECT
        p.position_id, p.symbol, p.quantity, p.avg_entry_price, p.current_price,
        p.position_value, p.unrealized_pnl, p.unrealized_pnl_pct,
        p.status, p.stage_in_exit_plan, p.days_since_entry,
        lt.stop_loss_price, lt.target_1_price, lt.target_2_price, lt.target_3_price,
        lt.target_1_r_multiple, lt.target_2_r_multiple, lt.target_3_r_multiple,
        cp.sector, cp.industry,
        ltt.weinstein_stage, ltt.minervini_trend_score,
        ltt.percent_from_52w_low, ltt.percent_from_52w_high
      FROM algo_positions p
      LEFT JOIN latest_trade lt ON lt.symbol = p.symbol
      LEFT JOIN company_profile cp ON cp.ticker = p.symbol
      LEFT JOIN latest_trend ltt ON ltt.symbol = p.symbol
      WHERE p.status = 'open'
      ORDER BY p.position_value DESC
    `);

    // Validate result structure
    validateQueryResult(result, { requireRows: false });

    const sf = (v) => v == null ? null : parseFloat(v);

    return sendSuccess(res, {
      items: validateAndCoerceRows(result, {
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
        percent_from_52w_high: { type: 'float', required: false }
      }).map(row => {
        const entry = sf(row.avg_entry_price);
        const current = sf(row.current_price);
        const stop = sf(row.stop_loss_price);
        const t1 = sf(row.target_1_price);
        const t2 = sf(row.target_2_price);
        const t3 = sf(row.target_3_price);

        // R-multiple = (current - entry) / (entry - stop)
        let r_multiple = null;
        let initial_risk_per_share = null;
        if (entry && stop && entry > stop) {
          initial_risk_per_share = entry - stop;
          if (initial_risk_per_share > 0 && current != null) {
            r_multiple = (current - entry) / initial_risk_per_share;
          }
        }

        // Open risk: distance to stop * quantity (the dollars at risk if stop hits NOW)
        const open_risk_dollars = (current && stop && row.quantity)
          ? Math.max(0, (current - stop)) * Number(row.quantity) : null;

        const distance_to_stop_pct = (current && stop) ? ((current - stop) / current) * 100 : null;
        const distance_to_t1_pct = (current && t1) ? ((t1 - current) / current) * 100 : null;
        const distance_to_t2_pct = (current && t2) ? ((t2 - current) / current) * 100 : null;
        const distance_to_t3_pct = (current && t3) ? ((t3 - current) / current) * 100 : null;

        return {
          position_id: row.position_id,
          symbol: row.symbol,
          quantity: row.quantity,
          avg_entry_price: entry,
          current_price: current,
          position_value: sf(row.position_value),
          unrealized_pnl: sf(row.unrealized_pnl),
          unrealized_pnl_pct: sf(row.unrealized_pnl_pct),
          status: row.status,
          stage_in_exit_plan: row.stage_in_exit_plan,
          days_since_entry: row.days_since_entry,

          // Stops & targets
          stop_loss_price: stop,
          target_1_price: t1,
          target_2_price: t2,
          target_3_price: t3,
          target_1_r: sf(row.target_1_r_multiple),
          target_2_r: sf(row.target_2_r_multiple),
          target_3_r: sf(row.target_3_r_multiple),

          // Derived
          r_multiple: r_multiple == null ? null : Math.round(r_multiple * 100) / 100,
          initial_risk_per_share,
          open_risk_dollars: open_risk_dollars == null ? null : Math.round(open_risk_dollars * 100) / 100,
          distance_to_stop_pct: distance_to_stop_pct == null ? null : Math.round(distance_to_stop_pct * 100) / 100,
          distance_to_t1_pct: distance_to_t1_pct == null ? null : Math.round(distance_to_t1_pct * 100) / 100,
          distance_to_t2_pct: distance_to_t2_pct == null ? null : Math.round(distance_to_t2_pct * 100) / 100,
          distance_to_t3_pct: distance_to_t3_pct == null ? null : Math.round(distance_to_t3_pct * 100) / 100,

          // Context
          sector: row.sector,
          industry: row.industry,
          weinstein_stage: row.weinstein_stage,
          minervini_trend_score: row.minervini_trend_score,
          pct_from_52w_low: sf(row.percent_from_52w_low),
          pct_from_52w_high: sf(row.percent_from_52w_high),
        };
      }),
      pagination: {
        total: result.rows.length,
        count: result.rows.length
      }
    });
  } catch (error) {
    logger.error('Error in /algo/positions:', { error: error.message });
    return sendDatabaseError(res, error, 'An error occurred while fetching positions');
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
    logger.error('Error in /algo/trades:', { error: error.message });
    return sendDatabaseError(res, error, 'An error occurred while fetching trade history');
  }
});

/**
 * GET /api/algo/config (admin only)
 * Get current configuration
 */
router.get('/config', requireAuth, requireAdmin, async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();

    const result = await pool.query(`
      SELECT key, value, value_type, description
      FROM algo_config
      ORDER BY key
    `);

    const config = {};
    result.rows.forEach(row => {
      let parsedValue = row.value;
      if (row.value_type === 'int') {
        parsedValue = parseInt(row.value);
      } else if (row.value_type === 'float') {
        parsedValue = parseFloat(row.value);
      } else if (row.value_type === 'bool') {
        parsedValue = ['true', '1', 'yes'].includes(row.value.toLowerCase());
      }
      config[row.key] = {
        value: parsedValue,
        type: row.value_type,
        description: row.description
      };
    });

    return sendSuccess(res, config);
  } catch (error) {
    logger.error('Error in /algo/config:', { error: error.message });
    return sendDatabaseError(res, error, 'An error occurred while fetching configuration');
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

    const latest = latestResult.rows[0] || null;
    const health = healthResult.rows[0] || null;

    // Determine active tier policy
    let policy = null;
    if (latest) {
      const exposurePct = parseFloat(latest.exposure_pct);
      const tiers = [
        { name: 'confirmed_uptrend', min: 80, max: 100, risk_mult: 1.0, max_new: 5,
          min_grade: 'B', halt: false, color: 'green',
          description: 'Healthy bull market â€” full deployment' },
        { name: 'healthy_uptrend', min: 60, max: 80, risk_mult: 0.85, max_new: 4,
          min_grade: 'B', halt: false, color: 'lightgreen',
          description: 'Bull market with caution â€” slightly reduced risk' },
        { name: 'pressure', min: 40, max: 60, risk_mult: 0.5, max_new: 2,
          min_grade: 'A', halt: false, color: 'yellow',
          description: 'Uptrend under pressure â€” defensive posture' },
        { name: 'caution', min: 20, max: 40, risk_mult: 0.25, max_new: 1,
          min_grade: 'A', halt: true, color: 'orange',
          description: 'Major caution â€” entries halted unless exceptional' },
        { name: 'correction', min: 0, max: 20, risk_mult: 0.0, max_new: 0,
          min_grade: 'A+', halt: true, color: 'red',
          description: 'Market correction â€” preserve capital' },
      ];
      policy = tiers.find(t => exposurePct >= t.min && exposurePct <= t.max) || tiers[0];
    }

    return sendSuccess(res, {
      current: latest ? {
        date: latest.date,
        exposure_pct: parseFloat(latest.exposure_pct),
        raw_score: parseFloat(latest.raw_score),
        regime: latest.regime,
        distribution_days: latest.distribution_days,
        factors: latest.factors,
        halt_reasons: latest.halt_reasons,
      } : null,
      active_tier: policy,
      history: historyResult.rows.map(r => ({
        date: r.date,
        exposure_pct: parseFloat(r.exposure_pct),
        regime: r.regime,
        distribution_days: r.distribution_days,
      })),
      market_health: health,
      sectors: sectorsResult.rows.map(r => ({
        name: r.sector_name,
        rank: r.current_rank,
        momentum: parseFloat(r.momentum_score || 0),
      })),
      sentiment: sentimentResult.rows.map(r => ({
        date: r.date,
        bullish: parseFloat(r.bullish || 0),
        bearish: parseFloat(r.bearish || 0),
        neutral: parseFloat(r.neutral || 0),
      })),
    });
  } catch (error) {
    logger.error('Error in /algo/markets:', { error: error.message });
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

    return sendSuccess(res, {
      items: result.rows.map(r => {
        const score = parseFloat(r.score);
        let grade = 'C';
        if (score >= 80) grade = 'A';
        else if (score >= 70) grade = 'B';
        else if (score >= 60) grade = 'C';
        else grade = 'D';

        return {
          symbol: r.symbol,
          date: r.date,
          swing_score: score,
          score: score, // alias for compatibility
          grade: grade,
          pass_gates: score >= 60,
          fail_reason: score < 60 ? 'Score below threshold' : null,
          components: r.components ? (typeof r.components === 'string' ? JSON.parse(r.components) : r.components) : {},
          company_name: r.short_name,
          sector: r.sector,
          industry: r.industry,
        };
      })
    });
  } catch (error) {
    logger.error('Error in /algo/swing-scores:', { error: error.message });
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
              ROUND(AVG(score)::numeric, 2) AS avg_score
       FROM swing_trader_scores
       WHERE date >= CURRENT_DATE - MAKE_INTERVAL(days => $1)
       GROUP BY DATE(date)
       ORDER BY eval_date ASC`,
      [days]
    );

    return sendSuccess(res, {
      items: result.rows.map(r => ({
        eval_date: r.eval_date,
        date: r.eval_date,
        total: parseInt(r.total),
        grade_aplus: parseInt(r.score_high), // scores >= 80
        grade_a: parseInt(r.score_medium), // scores 60-79
        pass_count: parseInt(r.score_high) + parseInt(r.score_medium), // A+ and A grades
        low_scores: parseInt(r.score_low),
        high_scores: parseInt(r.score_high),
        medium_scores: parseInt(r.score_medium),
        avg_score: parseFloat(r.avg_score),
      }))
    });
  } catch (error) {
    logger.error('Error in /algo/swing-scores-history:', { error: error.message });
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
        SELECT 'buy_sell_daily',       'daily',   'CRITICAL',
               MAX(date)::date,        COUNT(*),  3  FROM buy_sell_daily
        UNION ALL
        SELECT 'stock_scores',         'daily',   'CRITICAL',
               MAX(updated_at::date),  COUNT(*),  3  FROM stock_scores
        UNION ALL
        SELECT 'technical_data_daily', 'daily',   'IMPORTANT',
               MAX(date)::date,        COUNT(*),  3  FROM technical_data_daily
        UNION ALL
        SELECT 'market_health_daily',  'daily',   'IMPORTANT',
               MAX(date)::date,        COUNT(*),  7  FROM market_health_daily
        UNION ALL
        SELECT 'trend_template_data',  'daily',   'IMPORTANT',
               MAX(date)::date,        COUNT(*),  7  FROM trend_template_data
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

    const counts = { ok: 0, stale: 0, empty: 0, error: 0 };
    result.rows.forEach(r => { counts[r.status] = (counts[r.status] || 0) + 1; });

    const criticalStale = result.rows.filter(
      r => r.status !== 'ok' && (r.role || '') === 'CRITICAL'
    );

    // Only mark ready_to_trade true if we actually have data rows to check
    const ready_to_trade = result.rows.length > 0 && criticalStale.length === 0;

    return sendSuccess(res, {
      summary: counts,
      critical_stale: criticalStale.map(r => r.table_name),
      ready_to_trade,
      sources: result.rows.map(r => ({
        table: r.table_name,
        frequency: r.frequency,
        role: r.role,
        latest: r.latest_date,
        age_days: r.age_days !== null ? parseInt(r.age_days) : null,
        rows: parseInt(r.row_count),
        status: r.status,
        last_audit: null,
        error: null,
      })),
    });
  } catch (error) {
    logger.error('Error in /algo/data-status:', { error: error.message });
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
    const tiers = [
      { name: 'confirmed_uptrend', min_pct: 80, max_pct: 100,
        description: 'Healthy bull market â€” full deployment',
        risk_multiplier: 1.0, max_new_positions_today: 5,
        min_swing_score: 60, min_swing_grade: 'B',
        halt_new_entries: false, color: 'green' },
      { name: 'healthy_uptrend', min_pct: 60, max_pct: 80,
        description: 'Bull market with caution',
        risk_multiplier: 0.85, max_new_positions_today: 4,
        min_swing_score: 65, min_swing_grade: 'B',
        tighten_winners_at_r: 3.0,
        halt_new_entries: false, color: 'lightgreen' },
      { name: 'pressure', min_pct: 40, max_pct: 60,
        description: 'Uptrend under pressure',
        risk_multiplier: 0.5, max_new_positions_today: 2,
        min_swing_score: 70, min_swing_grade: 'A',
        tighten_winners_at_r: 2.0, force_partial_at_r: 3.0,
        halt_new_entries: false, color: 'yellow' },
      { name: 'caution', min_pct: 20, max_pct: 40,
        description: 'Major caution',
        risk_multiplier: 0.25, max_new_positions_today: 1,
        min_swing_score: 75, min_swing_grade: 'A',
        tighten_winners_at_r: 1.5, force_partial_at_r: 2.0,
        halt_new_entries: true, color: 'orange' },
      { name: 'correction', min_pct: 0, max_pct: 20,
        description: 'Market correction',
        risk_multiplier: 0.0, max_new_positions_today: 0,
        min_swing_score: 100, min_swing_grade: 'A+',
        tighten_winners_at_r: 1.0, force_partial_at_r: 1.5,
        halt_new_entries: true, force_exit_negative_r: true, color: 'red' },
    ];

    // Find active tier from latest exposure
    const latest = await pool.query(`SELECT exposure_pct FROM market_exposure_daily ORDER BY date DESC LIMIT 1`);
    const exp = latest.rows[0] ? parseFloat(latest.rows[0].exposure_pct) : null;
    const active = exp !== null
      ? tiers.find(t => exp >= t.min_pct && exp <= t.max_pct)
      : null;

    return sendSuccess(res, {
      current_exposure_pct: exp,
      active_tier: active,
      all_tiers: tiers,
    });
  } catch (error) {
    logger.error('Error in /algo/exposure-policy:', { error: error.message });
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
    logger.error('Error in /algo/run:', { error: error.message });
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
    logger.error('Error in /algo/patrol:', { error: error.message });
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

    return sendSuccess(res, {
      items: result.rows.map(r => ({
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
    logger.error('Error in /algo/patrol-log:', { error: error.message });
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

    return sendSuccess(res, { items: result.rows });
  } catch (error) {
    logger.error('Error fetching notifications:', { error: error.message });
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
    logger.error('Error marking notification as read:', { error: error.message });
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
    logger.error('Error deleting notification:', { error: error.message });
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
    logger.error('Error marking notifications as seen:', { error: error.message });
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

    // Parallelize initial portfolio and position count queries (independent of stock data)
    const [portfolioResult, initialPosResult] = await Promise.all([
      pool.query(`
        SELECT total_portfolio_value, total_cash, position_count
        FROM algo_portfolio_snapshots
        ORDER BY snapshot_date DESC LIMIT 1
      `),
      pool.query(`
        SELECT COUNT(*) as open_count FROM algo_positions WHERE status = 'open'
      `)
    ]);

    if (!portfolioResult.rows.length) {
      return sendError(res, 'Portfolio snapshot not available', 404);
    }

    const portfolio = portfolioResult.rows[0];
    const totalValue = parseFloat(portfolio.total_portfolio_value || 0);
    const cashAvail = parseFloat(portfolio.total_cash || 0);
    const numPos = parseInt(portfolio.position_count || 0);
    const openCount = parseInt(initialPosResult.rows[0]?.open_count || 0);

    // Calculate position size
    let posSize = position_dollars ? parseFloat(position_dollars) : (totalValue * parseFloat(position_pct || 0) / 100);
    const posPercent = (posSize / totalValue) * 100;

    // Get stock sector/industry; current price from price_daily (not company_profile,
    // which has no current_price column).
    const stockResult = await pool.query(`
      SELECT cp.ticker AS symbol, cp.sector, cp.industry,
             pd.close AS current_price
      FROM company_profile cp
      LEFT JOIN LATERAL (
        SELECT close FROM price_daily
        WHERE symbol = cp.ticker
        ORDER BY date DESC LIMIT 1
      ) pd ON true
      WHERE cp.ticker = $1
    `, [symbol.toUpperCase()]);

    const stock = stockResult.rows[0];
    if (!stock) {
      return sendError(res, `Stock ${symbol} not found`, 404);
    }

    // Get current positions in same sector â€” join company_profile since algo_positions
    // has no sector column.
    const sectorResult = await pool.query(`
      SELECT SUM(p.position_value) as sector_invested, COUNT(*) as sector_count
      FROM algo_positions p
      JOIN company_profile cp ON cp.ticker = p.symbol
      WHERE p.status = 'open' AND cp.sector = $1
    `, [stock.sector]);

    const sectorData = sectorResult.rows[0];
    const newSectorTotal = (parseFloat(sectorData.sector_invested || 0) + posSize) / totalValue * 100;

    // Worst-case drawdown impact: 15% adverse move on the full position size
    const drawdownImpact = posPercent * 0.15 / 100;

    // Check constraints
    const constraints = {
      position_limit_ok: openCount < 6, // max 6 positions
      size_limit_ok: posPercent <= 15,   // max 15% per position
      sector_limit_ok: newSectorTotal <= 30, // max 30% in one sector
      cash_ok: cashAvail >= posSize,     // have cash
      risk_ok: drawdownImpact <= 0.05    // max 5% portfolio impact
    };

    const allOk = Object.values(constraints).every(v => v);

    return sendSuccess(res, {
      symbol: symbol.toUpperCase(),
      entry_price: parseFloat(entry_price || stock.current_price || 0),
      position_size_dollars: posSize,
      position_size_percent: posPercent,
      sector: stock.sector,

      portfolio_impact: {
        new_total_positions: openCount + 1,
        position_limit: 6,
        position_limit_ok: constraints.position_limit_ok,

        new_position_percent: posPercent,
        max_position_percent: 15,
        position_size_ok: constraints.size_limit_ok,

        new_sector_percent: newSectorTotal,
        max_sector_percent: 30,
        sector_limit_ok: constraints.sector_limit_ok,

        worst_case_drawdown_impact: drawdownImpact,
        max_acceptable_impact: 0.05,
        drawdown_risk_ok: constraints.risk_ok,

        cash_required: posSize,
        cash_available: cashAvail,
        cash_ok: constraints.cash_ok
      },

      all_constraints_met: allOk,
      recommendation: allOk ? 'READY TO TRADE' : 'CONSTRAINTS VIOLATED'
    });
  } catch (error) {
    logger.error('Pre-trade simulation error:', { error: error.message });
    return sendDatabaseError(res, error, 'An error occurred while analyzing trade impact');
  }
});

// PERFORMANCE METRICS â€” Sharpe, Sortino, Calmar, max DD, profit factor
// ============================================================
router.get('/performance', authenticateToken, async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();

    // Get all closed trades for trade-based metrics
    const tradesResult = await pool.query(`
      SELECT trade_id, exit_date, profit_loss_dollars, profit_loss_pct,
             exit_r_multiple, trade_duration_days, entry_price, exit_price
      FROM algo_trades WHERE status = 'closed' AND exit_date IS NOT NULL
      ORDER BY exit_date ASC
    `);

    // Validate result structures
    validateQueryResult(tradesResult, { requireRows: false });

    // Get portfolio snapshots for return-series-based metrics
    const snapsResult = await pool.query(`
      SELECT snapshot_date, total_portfolio_value, daily_return_pct
      FROM algo_portfolio_snapshots
      ORDER BY snapshot_date ASC
    `);

    validateQueryResult(snapsResult, { requireRows: false });

    const trades = validateAndCoerceRows(tradesResult, {
      trade_id: { type: 'int', required: true },
      exit_date: { type: 'date', required: true },
      profit_loss_dollars: { type: 'float', required: false, defaultValue: 0 },
      profit_loss_pct: { type: 'float', required: false, defaultValue: 0 },
      exit_r_multiple: { type: 'float', required: false, defaultValue: 0 },
      trade_duration_days: { type: 'int', required: false, defaultValue: 0 },
      entry_price: { type: 'float', required: false },
      exit_price: { type: 'float', required: false }
    });

    const snaps = validateAndCoerceRows(snapsResult, {
      snapshot_date: { type: 'date', required: true },
      total_portfolio_value: { type: 'float', required: false, defaultValue: 0 },
      daily_return_pct: { type: 'float', required: false, defaultValue: 0 }
    });

    // ---- Trade-based metrics ----
    const wins = trades.filter(t => parseFloat(t.profit_loss_dollars) > 0);
    const losses = trades.filter(t => parseFloat(t.profit_loss_dollars) <= 0);

    const totalPnl = trades.reduce((s, t) => s + parseFloat(t.profit_loss_dollars || 0), 0);
    const grossWin = wins.reduce((s, t) => s + parseFloat(t.profit_loss_dollars || 0), 0);
    const grossLoss = Math.abs(losses.reduce((s, t) => s + parseFloat(t.profit_loss_dollars || 0), 0));

    const winRate = trades.length > 0 ? wins.length / trades.length : 0;
    const profitFactor = grossLoss > 0 ? grossWin / grossLoss : (grossWin > 0 ? Infinity : 0);

    const avgWinR = wins.length > 0
      ? wins.reduce((s, t) => s + parseFloat(t.exit_r_multiple || 0), 0) / wins.length : 0;
    const avgLossR = losses.length > 0
      ? losses.reduce((s, t) => s + parseFloat(t.exit_r_multiple || 0), 0) / losses.length : 0;
    const expectancyR = (winRate * avgWinR) + ((1 - winRate) * avgLossR);

    const avgWinPct = wins.length > 0
      ? wins.reduce((s, t) => s + parseFloat(t.profit_loss_pct || 0), 0) / wins.length : 0;
    const avgLossPct = losses.length > 0
      ? losses.reduce((s, t) => s + parseFloat(t.profit_loss_pct || 0), 0) / losses.length : 0;

    const avgHoldDays = trades.length > 0
      ? trades.reduce((s, t) => s + (parseInt(t.trade_duration_days) || 0), 0) / trades.length : 0;

    // ---- Snapshot-based metrics (annualized Sharpe/Sortino + max DD) ----
    let sharpe = 0, sortino = 0, calmar = 0, maxDD = 0, totalReturn = 0;
    if (snaps.length >= 2) {
      const dailyReturns = snaps.map(s => parseFloat(s.daily_return_pct || 0) / 100);
      const validReturns = dailyReturns.filter(r => !isNaN(r) && Number.isFinite(r));

      if (validReturns.length > 1) {
        const meanReturn = validReturns.reduce((a, b) => a + b, 0) / validReturns.length;
        const stdDev = Math.sqrt(
          validReturns.reduce((s, r) => s + Math.pow(r - meanReturn, 2), 0) / validReturns.length
        );
        // Sortino downside deviation: MAR = 0, denominator is ALL periods (not just losing days)
        const downStdDev = validReturns.length > 0
          ? Math.sqrt(validReturns.reduce((s, r) => s + Math.pow(Math.min(r, 0), 2), 0) / validReturns.length) : 0;

        // Annualize: 252 trading days
        sharpe = stdDev > 0 ? (meanReturn / stdDev) * Math.sqrt(252) : 0;
        sortino = downStdDev > 0 ? (meanReturn / downStdDev) * Math.sqrt(252) : 0;
      }

      // Max drawdown
      let peak = parseFloat(snaps[0].total_portfolio_value || 0);
      for (const s of snaps) {
        const v = parseFloat(s.total_portfolio_value || 0);
        peak = Math.max(peak, v);
        if (peak > 0) {
          const dd = (peak - v) / peak * 100;
          maxDD = Math.max(maxDD, dd);
        }
      }

      const startValue = parseFloat(snaps[0].total_portfolio_value || 0);
      const endValue = parseFloat(snaps[snaps.length - 1].total_portfolio_value || 0);
      totalReturn = startValue > 0 ? (endValue - startValue) / startValue * 100 : 0;

      // Calmar = total return / max DD
      calmar = maxDD > 0 ? totalReturn / maxDD : 0;
    }

    // ---- Streak analysis ----
    let currentStreak = 0;
    let bestWinStreak = 0;
    let worstLossStreak = 0;
    let tempWin = 0, tempLoss = 0;
    for (const t of trades) {
      if (parseFloat(t.profit_loss_dollars) > 0) {
        tempWin++; tempLoss = 0;
        bestWinStreak = Math.max(bestWinStreak, tempWin);
        currentStreak = tempWin;
      } else {
        tempLoss++; tempWin = 0;
        worstLossStreak = Math.max(worstLossStreak, tempLoss);
        currentStreak = -tempLoss;
      }
    }

    return sendSuccess(res, {
      // Trade counts
      total_trades: trades.length,
      winning_trades: wins.length,
      losing_trades: losses.length,

      // Win/loss profile
      win_rate_pct: Math.round(winRate * 1000) / 10,
      avg_win_pct: Math.round(avgWinPct * 100) / 100,
      avg_loss_pct: Math.round(avgLossPct * 100) / 100,
      avg_win_r: Math.round(avgWinR * 100) / 100,
      avg_loss_r: Math.round(avgLossR * 100) / 100,

      // Expectancy
      expectancy_r: Math.round(expectancyR * 1000) / 1000,
      profit_factor: profitFactor === Infinity ? null : Math.round(profitFactor * 100) / 100,

      // Total
      total_pnl_dollars: Math.round(totalPnl * 100) / 100,
      gross_win_dollars: Math.round(grossWin * 100) / 100,
      gross_loss_dollars: Math.round(grossLoss * 100) / 100,
      total_return_pct: Math.round(totalReturn * 100) / 100,

      // Risk-adjusted
      sharpe_annualized: Math.round(sharpe * 100) / 100,
      sortino_annualized: Math.round(sortino * 100) / 100,
      calmar_ratio: Math.round(calmar * 100) / 100,
      max_drawdown_pct: Math.round(maxDD * 100) / 100,

      // Streaks + duration
      current_streak: currentStreak,
      best_win_streak: bestWinStreak,
      worst_loss_streak: worstLossStreak,
      avg_hold_days: Math.round(avgHoldDays * 10) / 10,

      // Sample sizes
      portfolio_snapshots: snaps.length,
    });
  } catch (error) {
    logger.error('Error in /algo/performance:', { error: error.message });
    return sendDatabaseError(res, error, 'An error occurred while calculating performance metrics');
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
             unrealized_pnl_pct, position_count
      FROM algo_portfolio_snapshots
      ORDER BY snapshot_date DESC
      LIMIT $1
    `, [limit]);

    return sendSuccess(res, {
      items: result.rows.reverse().map(r => ({
        snapshot_date: r.snapshot_date,
        total_portfolio_value: parseFloat(r.total_portfolio_value || 0),
        daily_return_pct: parseFloat(r.daily_return_pct || 0),
        unrealized_pnl_pct: parseFloat(r.unrealized_pnl_pct || 0),
        position_count: parseInt(r.position_count || 0),
      }))
    });
  } catch (error) {
    logger.error('Error in /algo/equity-curve:', { error: error.message });
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

    return sendSuccess(res, {
      items: result.rows.map(r => ({
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
    logger.error('Error in /algo/audit-log:', { error: error.message });
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
    if (result.rows.length === 0) {
      return sendError(res, 'Trade not found', 404);
    }
    return sendSuccess(res, result.rows[0]);
  } catch (error) {
    logger.error('Error in /algo/trade/:id:', { error: error.message });
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

    // Latest snapshot (drawdown, daily return)
    const snapResult = await pool.query(`
      SELECT snapshot_date, total_portfolio_value, daily_return_pct, max_drawdown_pct
      FROM algo_portfolio_snapshots
      ORDER BY snapshot_date DESC LIMIT 30
    `);

    // Validate snapshot result
    validateQueryResult(snapResult, { requireRows: false });

    const snaps = validateAndCoerceRows(snapResult, {
      snapshot_date: { type: 'date', required: true },
      total_portfolio_value: { type: 'float', required: false, defaultValue: 0 },
      daily_return_pct: { type: 'float', required: false, defaultValue: 0 },
      max_drawdown_pct: { type: 'float', required: false, defaultValue: 0 }
    });
    const latest = snaps[0] || {};

    // Compute current portfolio drawdown from peak (use last 30 snapshots)
    let curDD = 0;
    if (snaps.length > 1) {
      const peak = Math.max(...snaps.map(s => parseFloat(s.total_portfolio_value || 0)));
      const cur = parseFloat(latest.total_portfolio_value || 0);
      curDD = peak > 0 ? ((peak - cur) / peak) * 100 : 0;
    }

    // Daily loss % (today)
    const dailyLossPct = -1 * Math.min(0, parseFloat(latest.daily_return_pct || 0));

    // Weekly loss = sum of daily returns over last 5 sessions, only the negative side
    let weeklyLossPct = 0;
    if (snaps.length >= 5) {
      const last5 = snaps.slice(0, 5);
      const sumDaily = last5.reduce((s, r) => s + parseFloat(r.daily_return_pct || 0), 0);
      weeklyLossPct = -1 * Math.min(0, sumDaily);
    }

    // Consecutive losses (closed trades, walking back from most recent)
    const closedTrades = await pool.query(`
      SELECT profit_loss_dollars FROM algo_trades
      WHERE status = 'closed' AND exit_date IS NOT NULL
      ORDER BY exit_date DESC LIMIT 50
    `);

    // Validate closed trades result
    validateQueryResult(closedTrades, { requireRows: false });

    const closedTradesRows = validateAndCoerceRows(closedTrades, {
      profit_loss_dollars: { type: 'float', required: false, defaultValue: 0 }
    });
    let consec = 0;
    for (const r of closedTradesRows) {
      if ((r.profit_loss_dollars || 0) < 0) consec += 1;
      else break;
    }

    // Total open risk = sum of (current - stop) * qty across open positions
    const openRiskResult = await pool.query(`
      WITH latest_trade AS (
        SELECT DISTINCT ON (symbol) symbol, stop_loss_price
        FROM algo_trades WHERE status = 'open'
        ORDER BY symbol, trade_date DESC
      )
      SELECT SUM(GREATEST(p.current_price - lt.stop_loss_price, 0) * p.quantity) AS open_risk,
             MAX(snap.total_portfolio_value) AS port_value
      FROM algo_positions p
      LEFT JOIN latest_trade lt ON lt.symbol = p.symbol
      CROSS JOIN (
        SELECT total_portfolio_value FROM algo_portfolio_snapshots
        ORDER BY snapshot_date DESC LIMIT 1
      ) snap
      WHERE p.status = 'open'
    `);

    // Validate open risk result
    validateQueryResult(openRiskResult, { minRows: 1, maxRows: 1 });

    const openRiskRow = validateAndCoerceRow(openRiskResult.rows[0], {
      open_risk: { type: 'float', required: false, defaultValue: 0 },
      port_value: { type: 'float', required: false, defaultValue: 0 }
    });
    const openRiskDollars = openRiskRow.open_risk || 0;
    const portValue = openRiskRow.port_value || 0;
    const totalRiskPct = portValue > 0 ? (openRiskDollars / portValue) * 100 : 0;

    // VIX
    const vixResult = await pool.query(`
      SELECT vix_level FROM market_health_daily ORDER BY date DESC LIMIT 1
    `);

    // Validate vix result
    validateQueryResult(vixResult, { requireRows: false });

    const vix = vixResult.rows.length > 0
      ? validateAndCoerceRow(vixResult.rows[0], {
          vix_level: { type: 'float', required: false, defaultValue: 0 }
        }).vix_level
      : 0;

    // Market stage
    const stageResult = await pool.query(`
      SELECT market_stage, market_trend FROM market_health_daily ORDER BY date DESC LIMIT 1
    `);

    // Validate stage result
    validateQueryResult(stageResult, { requireRows: false });

    const stageData = stageResult.rows.length > 0
      ? validateAndCoerceRow(stageResult.rows[0], {
          market_stage: { type: 'int', required: false, defaultValue: 1 },
          market_trend: { type: 'string', required: false, defaultValue: 'unknown' }
        })
      : { market_stage: 1, market_trend: 'unknown' };
    const stage = stageData.market_stage;
    const trend = stageData.market_trend;

    const breakers = [
      { id: 'drawdown', label: 'Portfolio Drawdown',
        current: Math.round(curDD * 100) / 100, threshold: thresh.drawdown,
        unit: '%', triggered: curDD >= thresh.drawdown,
        description: 'Halts entries when total drawdown from peak exceeds threshold' },
      { id: 'daily_loss', label: 'Daily Loss',
        current: Math.round(dailyLossPct * 100) / 100, threshold: thresh.daily_loss,
        unit: '%', triggered: dailyLossPct >= thresh.daily_loss,
        description: 'Today\'s portfolio drop below threshold halts new entries' },
      { id: 'consecutive_losses', label: 'Consecutive Losses',
        current: consec, threshold: thresh.consecutive_losses,
        unit: '', triggered: consec >= thresh.consecutive_losses,
        description: 'Cool-off after streak of losing trades' },
      { id: 'total_risk', label: 'Total Open Risk',
        current: Math.round(totalRiskPct * 100) / 100, threshold: thresh.total_risk,
        unit: '%', triggered: totalRiskPct >= thresh.total_risk,
        description: 'Sum of distance-to-stop across all open positions' },
      { id: 'vix_spike', label: 'VIX Spike',
        current: Math.round(vix * 10) / 10, threshold: thresh.vix_spike,
        unit: '', triggered: vix > thresh.vix_spike,
        description: 'Volatility expansion above threshold pauses new entries' },
      { id: 'market_stage', label: 'Market Stage',
        current: stage, threshold: 4,
        unit: '', triggered: stage === 4,
        description: `Market in stage ${stage} (${trend}) â€” stage 4 = downtrend halts entries` },
      { id: 'weekly_loss', label: 'Weekly Loss',
        current: Math.round(weeklyLossPct * 100) / 100, threshold: thresh.weekly_loss,
        unit: '%', triggered: weeklyLossPct >= thresh.weekly_loss,
        description: 'Trailing 5-session loss above threshold halts new entries' },
    ];

    return sendSuccess(res, {
      any_triggered: breakers.some(b => b.triggered),
      triggered_count: breakers.filter(b => b.triggered).length,
      breakers,
    });
  } catch (error) {
    logger.error('Error in /algo/circuit-breakers:', { error: error.message });
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
        SUM(CASE WHEN lt.price_above_sma200 THEN 1 ELSE 0 END) AS above_200d
      FROM company_profile cp
      JOIN latest_tt lt ON lt.symbol = cp.ticker
      WHERE cp.sector IS NOT NULL AND TRIM(cp.sector) <> ''
      GROUP BY cp.sector
      HAVING COUNT(*) > 5
      ORDER BY cp.sector
    `);
    return sendSuccess(res, {
      items: result.rows.map(r => ({
        sector: r.sector,
        total_stocks: parseInt(r.total_stocks),
        above_50d: parseInt(r.above_50d),
        above_200d: parseInt(r.above_200d),
        pct_above_50d: r.total_stocks > 0
          ? Math.round((r.above_50d / r.total_stocks) * 1000) / 10 : 0,
        pct_above_200d: r.total_stocks > 0
          ? Math.round((r.above_200d / r.total_stocks) * 1000) / 10 : 0,
      }))
    });
  } catch (error) {
    logger.error('Error in /algo/sector-breadth:', { error: error.message });
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
        AVG(lt.minervini_trend_score) AS avg_trend_score
      FROM company_profile cp
      JOIN latest_tt lt ON lt.symbol = cp.ticker
      WHERE cp.sector IS NOT NULL AND TRIM(cp.sector) <> ''
      GROUP BY cp.sector
      HAVING COUNT(*) > 5
      ORDER BY stage_2 DESC
    `);
    return sendSuccess(res, {
      items: result.rows.map(r => ({
        sector: r.sector,
        total: parseInt(r.total_stocks),
        stage_1: parseInt(r.stage_1 || 0),
        stage_2: parseInt(r.stage_2 || 0),
        stage_3: parseInt(r.stage_3 || 0),
        stage_4: parseInt(r.stage_4 || 0),
        pct_stage_2: r.total_stocks > 0
          ? Math.round((r.stage_2 / r.total_stocks) * 1000) / 10 : 0,
        avg_trend_score: r.avg_trend_score ? parseFloat(r.avg_trend_score) : null,
      }))
    });
  } catch (error) {
    logger.error('Error in /algo/sector-stage2:', { error: error.message });
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

    return sendSuccess(res, {
      items: result.rows.map(r => ({
        date: r.date,
        sector: r.sector,
        signal: r.signal,
        strength: parseFloat(r.strength || 0),
        rank: r.rank,
        // details JSONB may contain extended metrics from algo_sector_rotation.py
        ...(r.details || {}),
      }))
    });
  } catch (error) {
    logger.error('Error in /algo/sector-rotation:', { error: error.message });
    return sendDatabaseError(res, error, 'An error occurred while analyzing sector rotation');
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
        EXTRACT(EPOCH FROM (NOW() - TO_TIMESTAMP(latest_data_date, 'YYYY-MM-DD'))) / 3600 as age_hours,
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
      age_hours: Math.round((r.age_hours || 0) * 10) / 10,
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
    logger.error('Error in /algo/data-quality:', { error: error.message });
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
      SELECT
        COUNT(*) as total,
        SUM(CASE WHEN tier_1_pass THEN 1 ELSE 0 END) as t1_pass,
        SUM(CASE WHEN tier_2_pass THEN 1 ELSE 0 END) as t2_pass,
        SUM(CASE WHEN tier_3_pass THEN 1 ELSE 0 END) as t3_pass,
        SUM(CASE WHEN tier_4_pass THEN 1 ELSE 0 END) as t4_pass,
        SUM(CASE WHEN tier_5_pass THEN 1 ELSE 0 END) as t5_pass
      FROM filter_rejection_log
      WHERE eval_date = $1::DATE
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
          t5_pass: { type: 'int', required: false, defaultValue: 0 }
        })
      : { total: 0, t1_pass: 0, t2_pass: 0, t3_pass: 0, t4_pass: 0, t5_pass: 0 };

    const { total, t1_pass, t2_pass, t3_pass, t4_pass, t5_pass } = row;
    const t1 = t1_pass || 0;
    const t2 = t2_pass || 0;
    const t3 = t3_pass || 0;
    const t4 = t4_pass || 0;
    const t5 = t5_pass || 0;

    return sendSuccess(res, {
      date: eval_date,
      total_signals: total || 0,
      tiers: [
        { tier: 1, name: 'Data Quality', pass: t1, reject: (total - t1) },
        { tier: 2, name: 'Market Health', pass: t2, reject: (t1 - t2) },
        { tier: 3, name: 'Trend Confirmation', pass: t3, reject: (t2 - t3) },
        { tier: 4, name: 'Signal Quality', pass: t4, reject: (t3 - t4) },
        { tier: 5, name: 'Portfolio Health', pass: t5, reject: (t4 - t5) },
      ],
    });
  } catch (error) {
    logger.error('Error in /algo/rejection-funnel:', { error: error.message });
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
    const result = await pool.query(`
      SELECT
        id, trade_id, symbol, order_type, side, requested_shares, requested_price,
        order_timestamp
      FROM order_execution_log
      WHERE order_status IN ('pending', 'submitted')
      ORDER BY order_timestamp DESC
      LIMIT 20
    `);

    // Validate result structure
    validateQueryResult(result, { requireRows: false });

    const pending_orders = validateAndCoerceRows(result, {
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

    const total_pending_value = pending_orders
      .filter(o => o.side === 'BUY')
      .reduce((s, o) => s + (o.requested_shares * o.requested_price), 0);

    return sendSuccess(res, {
      pending_orders,
      total_pending_value: Math.round(total_pending_value * 100) / 100,
      approval_required: pending_orders.length > 0
    });
  } catch (error) {
    logger.error('Error in /algo/orders/pending:', { error: error.message });
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
        AVG(fill_rate_pct) as avg_fill_rate,
        AVG(ABS(slippage_bps)) as avg_slippage_bps,
        MAX(ABS(slippage_bps)) as max_slippage_bps
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
      max_slippage_bps: { type: 'float', required: false, defaultValue: 0 }
    });

    const metrics = {
      period: `last ${days} days`,
      total_orders: row.total_orders || 0,
      filled: row.filled || 0,
      rejected: row.rejected || 0,
      partial: row.partial || 0,
      fill_rate_pct: (row.avg_fill_rate || 0).toFixed(2),
      avg_slippage_bps: (row.avg_slippage_bps || 0).toFixed(2),
      max_slippage_bps: (row.max_slippage_bps || 0).toFixed(2),
      slippage_alert: (row.avg_slippage_bps || 0) > 100,
    };

    return sendSuccess(res, { metrics });
  } catch (error) {
    logger.error('Error in /algo/execution-quality:', { error: error.message });
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
    logger.error("Error in /algo/signal-performance-by-pattern:", { error: error.message });
    return sendDatabaseError(res, error, 'An error occurred while analyzing signal performance');
  }
});

module.exports = router;


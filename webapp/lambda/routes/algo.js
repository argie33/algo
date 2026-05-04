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
const { getPool } = require('../utils/database');
const { authenticateToken } = require('../middleware/auth');

const router = express.Router();

// Auth middleware: require authentication for endpoints that mutate state or
// trigger expensive operations. GET endpoints remain public for read-only data.
const requireAuth = authenticateToken;

/**
 * GET /api/algo/status
 * Current algo system status
 */
router.get('/status', async (req, res) => {
  try {
    const pool = getPool();

    // Get latest portfolio snapshot
    const snapshotResult = await pool.query(`
      SELECT
        snapshot_date,
        total_portfolio_value,
        position_count,
        unrealized_pnl_pct,
        daily_return_pct,
        market_health_status
      FROM algo_portfolio_snapshots
      ORDER BY snapshot_date DESC
      LIMIT 1
    `);

    const snapshot = snapshotResult.rows[0] || {
      position_count: 0,
      unrealized_pnl_pct: 0,
      daily_return_pct: 0
    };

    // Get active positions count
    const posResult = await pool.query(`
      SELECT COUNT(*) as open_count, SUM(position_value) as total_value
      FROM algo_positions
      WHERE status = 'open'
    `);

    const positions = posResult.rows[0] || { open_count: 0, total_value: 0 };

    // Get market health
    const healthResult = await pool.query(`
      SELECT market_trend, market_stage, distribution_days_4w, vix_level
      FROM market_health_daily
      ORDER BY date DESC
      LIMIT 1
    `);

    const health = healthResult.rows[0] || {
      market_trend: 'unknown',
      market_stage: 1,
      distribution_days_4w: 0,
      vix_level: 0
    };

    return res.json({
      success: true,
      data: {
        algo_enabled: true,
        execution_mode: 'paper',
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
        },
        timestamp: new Date()
      },
      timestamp: new Date()
    });
  } catch (error) {
    console.error('Error in /algo/status:', error);
    return res.status(500).json({
      success: false,
      error: error.message,
      timestamp: new Date()
    });
  }
});

/**
 * GET /api/algo/evaluate
 * Run signal evaluation (latest date with buy signals)
 */
router.get('/evaluate', async (req, res) => {
  try {
    const pool = getPool();

    // Get latest buy signals
    const signalResult = await pool.query(`
      SELECT symbol, date, signal, entry_price
      FROM buy_sell_daily
      WHERE signal = 'BUY'
      ORDER BY date DESC, symbol
      LIMIT 50
    `);

    const signals = signalResult.rows;

    // For each signal, get evaluation status
    const evaluated = [];
    for (const sig of signals) {
      // Check trend template
      const trendResult = await pool.query(`
        SELECT minervini_trend_score, percent_from_52w_low, percent_from_52w_high
        FROM trend_template_data
        WHERE symbol = $1 AND date = $2
        LIMIT 1
      `, [sig.symbol, sig.date]);

      // Check completeness
      const completeResult = await pool.query(`
        SELECT composite_completeness_pct
        FROM data_completeness_scores
        WHERE symbol = $1
        LIMIT 1
      `, [sig.symbol]);

      // Check SQS
      const sqsResult = await pool.query(`
        SELECT composite_sqs
        FROM signal_quality_scores
        WHERE symbol = $1 AND date = $2
        LIMIT 1
      `, [sig.symbol, sig.date]);

      const trend = trendResult.rows[0];
      const completeness = completeResult.rows[0];
      const sqs = sqsResult.rows[0];

      // Determine if passes all tiers
      const passes = {
        tier1: completeness && completeness.composite_completeness_pct >= 70,
        tier3: trend && trend.minervini_trend_score >= 8,
        tier4: sqs && sqs.composite_sqs >= 60
      };

      evaluated.push({
        symbol: sig.symbol,
        date: sig.date,
        entry_price: sig.entry_price,
        trend_score: trend ? trend.minervini_trend_score : 0,
        pct_from_52w_low: trend ? trend.percent_from_52w_low : 0,
        completeness_pct: completeness ? completeness.composite_completeness_pct : 0,
        sqs: sqs ? sqs.composite_sqs : 0,
        tier1_pass: passes.tier1,
        tier3_pass: passes.tier3,
        tier4_pass: passes.tier4,
        all_tiers_pass: passes.tier1 && passes.tier3 && passes.tier4
      });
    }

    // Sort by SQS, select top 12
    const qualified = evaluated.filter(e => e.all_tiers_pass).sort((a, b) => b.sqs - a.sqs).slice(0, 12);

    return res.json({
      success: true,
      data: {
        total_buy_signals: signals.length,
        qualified_for_trading: qualified.length,
        signals: evaluated,
        top_qualified: qualified
      },
      timestamp: new Date()
    });
  } catch (error) {
    console.error('Error in /algo/evaluate:', error);
    return res.status(500).json({
      success: false,
      error: error.message,
      timestamp: new Date()
    });
  }
});

/**
 * GET /api/algo/positions
 * Get active positions enriched with stop/target levels (from latest open trade),
 * sector (from company_profile), and Minervini stage / RS (from trend_template_data).
 */
router.get('/positions', async (req, res) => {
  try {
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

    const sf = (v) => v == null ? null : parseFloat(v);

    return res.json({
      success: true,
      items: result.rows.map(row => {
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
      },
      timestamp: new Date()
    });
  } catch (error) {
    console.error('Error in /algo/positions:', error);
    return res.status(500).json({
      success: false,
      error: error.message,
      timestamp: new Date()
    });
  }
});

/**
 * GET /api/algo/trades
 * Get trade history
 */
router.get('/trades', async (req, res) => {
  try {
    const pool = getPool();
    const limit = parseInt(req.query.limit) || 50;
    const offset = parseInt(req.query.offset) || 0;

    const result = await pool.query(`
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
        trade_duration_days
      FROM algo_trades
      ORDER BY trade_date DESC
      LIMIT $1 OFFSET $2
    `, [limit, offset]);

    const countResult = await pool.query('SELECT COUNT(*) as total FROM algo_trades');

    return res.json({
      success: true,
      items: result.rows.map(row => ({
        ...row,
        entry_price: parseFloat(row.entry_price),
        exit_price: row.exit_price ? parseFloat(row.exit_price) : null,
        profit_loss_pct: parseFloat(row.profit_loss_pct || 0)
      })),
      pagination: {
        total: parseInt(countResult.rows[0].total),
        limit,
        offset,
        page: Math.floor(offset / limit) + 1,
        totalPages: Math.ceil(parseInt(countResult.rows[0].total) / limit)
      },
      timestamp: new Date()
    });
  } catch (error) {
    console.error('Error in /algo/trades:', error);
    return res.status(500).json({
      success: false,
      error: error.message,
      timestamp: new Date()
    });
  }
});

/**
 * GET /api/algo/config
 * Get current configuration
 */
router.get('/config', async (req, res) => {
  try {
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

    return res.json({
      success: true,
      data: config,
      timestamp: new Date()
    });
  } catch (error) {
    console.error('Error in /algo/config:', error);
    return res.status(500).json({
      success: false,
      error: error.message,
      timestamp: new Date()
    });
  }
});

// ============================================================
// MARKET EXPOSURE — for the Markets page
// ============================================================
router.get('/markets', async (req, res) => {
  try {
    // Latest market exposure with full factor breakdown
    const latestQuery = `
      SELECT date, exposure_pct, raw_score, regime, distribution_days,
             factors, halt_reasons, created_at
      FROM market_exposure_daily
      ORDER BY date DESC LIMIT 1
    `;
    const pool = getPool();
    const latestResult = await pool.query(latestQuery);
    const latest = latestResult.rows[0] || null;

    // Last 90 days for chart
    const historyQuery = `
      SELECT date, exposure_pct, regime, distribution_days
      FROM market_exposure_daily
      WHERE date >= CURRENT_DATE - INTERVAL '90 days'
      ORDER BY date ASC
    `;
    const historyResult = await pool.query(historyQuery);

    // Market health current state (fallback when exposure not computed)
    const healthQuery = `
      SELECT date, market_trend, market_stage, distribution_days_4w, vix_level
      FROM market_health_daily ORDER BY date DESC LIMIT 1
    `;
    const healthResult = await pool.query(healthQuery);
    const health = healthResult.rows[0] || null;

    // Sector ranking (latest)
    const sectorsQuery = `
      SELECT sector_name, current_rank, momentum_score, rank_1w_ago, rank_4w_ago, rank_12w_ago
      FROM sector_ranking
      WHERE date_recorded = (SELECT MAX(date_recorded) FROM sector_ranking)
        AND sector_name <> '' AND sector_name IS NOT NULL AND sector_name <> 'Benchmark'
      ORDER BY current_rank ASC
    `;
    const sectorsResult = await pool.query(sectorsQuery);

    // AAII sentiment latest
    const sentimentQuery = `
      SELECT date, bullish, bearish, neutral
      FROM aaii_sentiment ORDER BY date DESC LIMIT 8
    `;
    const sentimentResult = await pool.query(sentimentQuery);

    // Determine active tier policy
    let policy = null;
    if (latest) {
      const exposurePct = parseFloat(latest.exposure_pct);
      const tiers = [
        { name: 'confirmed_uptrend', min: 80, max: 100, risk_mult: 1.0, max_new: 5,
          min_grade: 'B', halt: false, color: 'green',
          description: 'Healthy bull market — full deployment' },
        { name: 'healthy_uptrend', min: 60, max: 80, risk_mult: 0.85, max_new: 4,
          min_grade: 'B', halt: false, color: 'lightgreen',
          description: 'Bull market with caution — slightly reduced risk' },
        { name: 'pressure', min: 40, max: 60, risk_mult: 0.5, max_new: 2,
          min_grade: 'A', halt: false, color: 'yellow',
          description: 'Uptrend under pressure — defensive posture' },
        { name: 'caution', min: 20, max: 40, risk_mult: 0.25, max_new: 1,
          min_grade: 'A', halt: true, color: 'orange',
          description: 'Major caution — entries halted unless exceptional' },
        { name: 'correction', min: 0, max: 20, risk_mult: 0.0, max_new: 0,
          min_grade: 'A+', halt: true, color: 'red',
          description: 'Market correction — preserve capital' },
      ];
      policy = tiers.find(t => exposurePct >= t.min && exposurePct <= t.max) || tiers[0];
    }

    return res.json({
      success: true,
      data: {
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
          rank_1w_ago: r.rank_1w_ago,
          rank_4w_ago: r.rank_4w_ago,
        })),
        sentiment: sentimentResult.rows.map(r => ({
          date: r.date,
          bullish: parseFloat(r.bullish || 0),
          bearish: parseFloat(r.bearish || 0),
          neutral: parseFloat(r.neutral || 0),
        })),
      },
      timestamp: new Date(),
    });
  } catch (error) {
    console.error('Error in /algo/markets:', error);
    return res.status(500).json({
      success: false,
      error: error.message,
      timestamp: new Date(),
    });
  }
});

// ============================================================
// SWING TRADER SCORES — for ranking display
// ============================================================
router.get('/swing-scores', async (req, res) => {
  try {
    const pool = getPool();
    const limit = parseInt(req.query.limit) || 50;
    const minScore = parseFloat(req.query.min_score) || 0;

    const result = await pool.query(
      `SELECT s.symbol, s.eval_date, s.swing_score, s.grade,
              s.setup_pts, s.trend_pts, s.momentum_pts, s.volume_pts,
              s.fundamentals_pts, s.sector_pts, s.multi_tf_pts,
              s.pass_gates, s.fail_reason, s.components,
              cp.sector, cp.industry
       FROM swing_trader_scores s
       LEFT JOIN company_profile cp ON cp.ticker = s.symbol
       WHERE s.eval_date = (SELECT MAX(eval_date) FROM swing_trader_scores)
         AND s.swing_score >= $1
       ORDER BY s.swing_score DESC
       LIMIT $2`,
      [minScore, limit]
    );

    return res.json({
      success: true,
      items: result.rows.map(r => ({
        symbol: r.symbol,
        eval_date: r.eval_date,
        swing_score: parseFloat(r.swing_score),
        grade: r.grade,
        components: {
          setup: parseFloat(r.setup_pts || 0),
          trend: parseFloat(r.trend_pts || 0),
          momentum: parseFloat(r.momentum_pts || 0),
          volume: parseFloat(r.volume_pts || 0),
          fundamentals: parseFloat(r.fundamentals_pts || 0),
          sector: parseFloat(r.sector_pts || 0),
          multi_tf: parseFloat(r.multi_tf_pts || 0),
        },
        pass_gates: r.pass_gates,
        fail_reason: r.fail_reason,
        details: r.components,
        sector: r.sector,
        industry: r.industry,
      })),
      timestamp: new Date(),
    });
  } catch (error) {
    console.error('Error in /algo/swing-scores:', error);
    return res.status(500).json({
      success: false,
      error: error.message,
      timestamp: new Date(),
    });
  }
});

// ============================================================
// SWING SCORES HISTORY — grade counts per eval_date (for trend chart)
// ============================================================
router.get('/swing-scores-history', async (req, res) => {
  try {
    const pool = getPool();
    const days = Math.min(parseInt(req.query.days) || 30, 180);

    const result = await pool.query(
      `SELECT eval_date,
              COUNT(*) AS total,
              COUNT(*) FILTER (WHERE grade = 'A+') AS grade_aplus,
              COUNT(*) FILTER (WHERE grade = 'A')  AS grade_a,
              COUNT(*) FILTER (WHERE grade = 'B')  AS grade_b,
              COUNT(*) FILTER (WHERE grade = 'C')  AS grade_c,
              COUNT(*) FILTER (WHERE pass_gates = TRUE) AS pass_count
       FROM swing_trader_scores
       WHERE eval_date >= CURRENT_DATE - MAKE_INTERVAL(days => $1)
       GROUP BY eval_date
       ORDER BY eval_date ASC`,
      [days]
    );

    return res.json({
      success: true,
      items: result.rows.map(r => ({
        eval_date: r.eval_date,
        total: parseInt(r.total),
        grade_aplus: parseInt(r.grade_aplus),
        grade_a: parseInt(r.grade_a),
        grade_b: parseInt(r.grade_b),
        grade_c: parseInt(r.grade_c),
        pass_count: parseInt(r.pass_count),
      })),
      timestamp: new Date(),
    });
  } catch (error) {
    console.error('Error in /algo/swing-scores-history:', error);
    return res.status(500).json({ success: false, error: error.message });
  }
});

// ============================================================
// DATA FRESHNESS — for monitoring
// ============================================================
router.get('/data-status', async (req, res) => {
  try {
    const pool = getPool();
    const result = await pool.query(
      `SELECT table_name, frequency, role, latest_date, age_days, row_count,
              status, last_audit_at, error_message
       FROM data_loader_status
       ORDER BY
         CASE WHEN role LIKE 'CRITICAL%' THEN 1 WHEN role LIKE 'IMPORTANT%' THEN 2 ELSE 3 END,
         table_name`
    );

    const counts = { ok: 0, stale: 0, empty: 0, error: 0 };
    result.rows.forEach(r => { counts[r.status] = (counts[r.status] || 0) + 1; });

    const criticalStale = result.rows.filter(
      r => r.status !== 'ok' && (r.role || '').includes('CRITICAL')
    );

    return res.json({
      success: true,
      data: {
        summary: counts,
        critical_stale: criticalStale.map(r => r.table_name),
        ready_to_trade: criticalStale.length === 0,
        sources: result.rows.map(r => ({
          table: r.table_name,
          frequency: r.frequency,
          role: r.role,
          latest: r.latest_date,
          age_days: r.age_days,
          rows: r.row_count,
          status: r.status,
          last_audit: r.last_audit_at,
          error: r.error_message,
        })),
      },
      timestamp: new Date(),
    });
  } catch (error) {
    console.error('Error in /algo/data-status:', error);
    return res.status(500).json({
      success: false,
      error: error.message,
      timestamp: new Date(),
    });
  }
});

// ============================================================
// EXPOSURE POLICY — current tier rules
// ============================================================
router.get('/exposure-policy', async (req, res) => {
  try {
    const pool = getPool();
    const tiers = [
      { name: 'confirmed_uptrend', min_pct: 80, max_pct: 100,
        description: 'Healthy bull market — full deployment',
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
    const latest = await pool.query(
      `SELECT exposure_pct FROM market_exposure_daily ORDER BY date DESC LIMIT 1`
    );
    const exp = latest.rows[0] ? parseFloat(latest.rows[0].exposure_pct) : null;
    const active = exp !== null
      ? tiers.find(t => exp >= t.min_pct && exp <= t.max_pct)
      : null;

    return res.json({
      success: true,
      data: {
        current_exposure_pct: exp,
        active_tier: active,
        all_tiers: tiers,
      },
      timestamp: new Date(),
    });
  } catch (error) {
    console.error('Error in /algo/exposure-policy:', error);
    return res.status(500).json({
      success: false,
      error: error.message,
      timestamp: new Date(),
    });
  }
});

// ============================================================
// RUN ORCHESTRATOR — trigger the daily algo workflow from UI
// ============================================================
router.post('/run', requireAuth, async (req, res) => {
  const { spawn } = require('child_process');
  const path = require('path');

  try {
    const dryRun = req.body?.dry_run !== false;  // default to dry-run for safety
    const date = req.body?.date || null;

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
        try { child.kill('SIGTERM'); } catch (e) {}
        resolve({ timeout: true, exitCode: -1, output });
      }, 180000);  // 3 minute timeout

      child.on('exit', (code) => {
        clearTimeout(timeout);
        exitCode = code;
        resolve({ timeout: false, exitCode: code, output });
      });
    });

    return res.json({
      success: result.exitCode === 0,
      run_id: runId,
      dry_run: dryRun,
      date: date || 'auto',
      exit_code: result.exitCode,
      timeout: result.timeout || false,
      output: result.output.join(''),
      timestamp: new Date(),
    });
  } catch (error) {
    console.error('Error in /algo/run:', error);
    return res.status(500).json({
      success: false,
      error: error.message,
      timestamp: new Date(),
    });
  }
});

// ============================================================
// RUN DATA PATROL — trigger watchdog from UI
// ============================================================
router.post('/patrol', requireAuth, async (req, res) => {
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
        try { child.kill('SIGTERM'); } catch (e) {}
        resolve({ timeout: true, exitCode: -1, output });
      }, 60000);

      child.stdout.on('data', (c) => output.push(c.toString()));
      child.stderr.on('data', (c) => output.push(c.toString()));
      child.on('exit', (code) => {
        clearTimeout(timeout);
        resolve({ timeout: false, exitCode: code, output });
      });
    });

    return res.json({
      success: true,
      ready_to_trade: result.exitCode === 0,
      exit_code: result.exitCode,
      output: result.output.join(''),
      timestamp: new Date(),
    });
  } catch (error) {
    console.error('Error in /algo/patrol:', error);
    return res.status(500).json({
      success: false,
      error: error.message,
      timestamp: new Date(),
    });
  }
});

// ============================================================
// PATROL HISTORY — recent patrol log entries
// ============================================================
router.get('/patrol-log', async (req, res) => {
  try {
    const pool = getPool();
    const limit = parseInt(req.query.limit) || 50;
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

    return res.json({
      success: true,
      items: result.rows.map(r => ({
        id: r.id,
        run_id: r.patrol_run_id,
        check_name: r.check_name,
        severity: r.severity,
        target_table: r.target_table,
        message: r.message,
        details: r.details,
        created_at: r.created_at,
      })),
      timestamp: new Date(),
    });
  } catch (error) {
    console.error('Error in /algo/patrol-log:', error);
    return res.status(500).json({
      success: false,
      error: error.message,
      timestamp: new Date(),
    });
  }
});

// ============================================================
// NOTIFICATIONS — surface CRITICAL events to UI as toasts
// ============================================================
router.get('/notifications', async (req, res) => {
  try {
    const pool = getPool();
    const limit = parseInt(req.query.limit) || 50;
    const result = await pool.query(
      `SELECT id, kind, severity, title, message, symbol, details, seen, created_at
       FROM algo_notifications
       WHERE seen = FALSE
       ORDER BY
         CASE severity
           WHEN 'critical' THEN 1
           WHEN 'error' THEN 2
           WHEN 'warning' THEN 3
           ELSE 4 END,
         created_at DESC
       LIMIT $1`,
      [limit]
    );
    return res.json({
      success: true,
      items: result.rows,
      timestamp: new Date(),
    });
  } catch (error) {
    return res.json({ success: true, items: [], timestamp: new Date() });
  }
});

router.post('/notifications/seen', requireAuth, async (req, res) => {
  try {
    const pool = getPool();
    const ids = req.body?.ids || [];
    if (!Array.isArray(ids) || ids.length === 0) {
      return res.json({ success: true, marked: 0 });
    }
    const result = await pool.query(
      `UPDATE algo_notifications SET seen = TRUE, seen_at = CURRENT_TIMESTAMP WHERE id = ANY($1)`,
      [ids]
    );
    return res.json({ success: true, marked: result.rowCount, timestamp: new Date() });
  } catch (error) {
    return res.status(500).json({ success: false, error: error.message });
  }
});

// ============================================================
// PRE-TRADE SIMULATION — what would the algo do?
// ============================================================
router.post('/simulate', requireAuth, async (req, res) => {
  const { spawn } = require('child_process');
  const path = require('path');
  try {
    const date = req.body?.date || null;
    const args = ['algo_orchestrator.py', '--dry-run'];
    if (date) args.push('--date', date);

    const repoRoot = path.resolve(__dirname, '../../..');
    const child = spawn('python3', args, { cwd: repoRoot, env: process.env });
    const output = [];
    const result = await new Promise((resolve) => {
      const timeout = setTimeout(() => {
        try { child.kill('SIGTERM'); } catch (e) {}
        resolve({ timeout: true, exitCode: -1, output });
      }, 120000);
      child.stdout.on('data', (c) => output.push(c.toString()));
      child.stderr.on('data', (c) => output.push(c.toString()));
      child.on('exit', (code) => {
        clearTimeout(timeout);
        resolve({ timeout: false, exitCode: code, output });
      });
    });

    return res.json({
      success: result.exitCode === 0,
      exit_code: result.exitCode,
      output: result.output.join(''),
      timestamp: new Date(),
    });
  } catch (error) {
    return res.status(500).json({ success: false, error: error.message });
  }
});

// ============================================================
// PERFORMANCE METRICS — Sharpe, Sortino, Calmar, max DD, profit factor
// ============================================================
router.get('/performance', async (req, res) => {
  try {
    const pool = getPool();

    // Get all closed trades for trade-based metrics
    const tradesResult = await pool.query(`
      SELECT trade_id, exit_date, profit_loss_dollars, profit_loss_pct,
             exit_r_multiple, trade_duration_days, entry_price, exit_price
      FROM algo_trades WHERE status = 'closed' AND exit_date IS NOT NULL
      ORDER BY exit_date ASC
    `);
    const trades = tradesResult.rows;

    // Get portfolio snapshots for return-series-based metrics
    const snapsResult = await pool.query(`
      SELECT snapshot_date, total_portfolio_value, daily_return_pct
      FROM algo_portfolio_snapshots
      ORDER BY snapshot_date ASC
    `);
    const snaps = snapsResult.rows;

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
        const downside = validReturns.filter(r => r < 0);
        const downStdDev = downside.length > 0
          ? Math.sqrt(downside.reduce((s, r) => s + r * r, 0) / downside.length) : 0;

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

    return res.json({
      success: true,
      data: {
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
      },
      timestamp: new Date(),
    });
  } catch (error) {
    console.error('Error in /algo/performance:', error);
    return res.status(500).json({ success: false, error: error.message });
  }
});

/**
 * GET /api/algo/equity-curve
 * Time-series of portfolio value from algo_portfolio_snapshots
 * Used by Portfolio Dashboard equity-curve chart.
 */
router.get('/equity-curve', async (req, res) => {
  try {
    const pool = getPool();
    const limit = parseInt(req.query.limit) || 180;
    const result = await pool.query(`
      SELECT snapshot_date, total_portfolio_value, daily_return_pct,
             unrealized_pnl_pct, position_count
      FROM algo_portfolio_snapshots
      ORDER BY snapshot_date DESC
      LIMIT $1
    `, [limit]);

    return res.json({
      success: true,
      items: result.rows.reverse().map(r => ({
        snapshot_date: r.snapshot_date,
        total_portfolio_value: parseFloat(r.total_portfolio_value || 0),
        daily_return_pct: parseFloat(r.daily_return_pct || 0),
        unrealized_pnl_pct: parseFloat(r.unrealized_pnl_pct || 0),
        position_count: parseInt(r.position_count || 0),
      })),
      timestamp: new Date(),
    });
  } catch (error) {
    console.error('Error in /algo/equity-curve:', error);
    return res.status(500).json({ success: false, error: error.message });
  }
});

// ============================================================
// AUDIT LOG — every algo decision logged
// ============================================================
router.get('/audit-log', async (req, res) => {
  try {
    const pool = getPool();
    const limit = parseInt(req.query.limit) || 100;
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

    return res.json({
      success: true,
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
      })),
      timestamp: new Date(),
    });
  } catch (error) {
    console.error('Error in /algo/audit-log:', error);
    return res.status(500).json({ success: false, error: error.message });
  }
});

// ============================================================
// TRADE DETAIL — full reasoning for a single trade
// ============================================================
router.get('/trade/:tradeId', async (req, res) => {
  try {
    const pool = getPool();
    const result = await pool.query(
      `SELECT t.*, p.position_id, p.quantity AS current_qty, p.current_price,
              p.unrealized_pnl, p.unrealized_pnl_pct, p.target_levels_hit,
              p.current_stop_price
       FROM algo_trades t
       LEFT JOIN algo_positions p ON p.trade_ids LIKE '%' || t.trade_id || '%'
                                 AND p.status = 'open'
       WHERE t.trade_id = $1`,
      [req.params.tradeId]
    );
    if (result.rows.length === 0) {
      return res.status(404).json({ success: false, error: 'Trade not found' });
    }
    return res.json({
      success: true,
      data: result.rows[0],
      timestamp: new Date(),
    });
  } catch (error) {
    console.error('Error in /algo/trade/:id:', error);
    return res.status(500).json({
      success: false,
      error: error.message,
      timestamp: new Date(),
    });
  }
});

// ============================================================
// CIRCUIT BREAKERS — current state of all 7 kill-switches
// ============================================================
router.get('/circuit-breakers', async (req, res) => {
  try {
    const pool = getPool();

    // Pull config (with sensible defaults if rows missing)
    const cfgResult = await pool.query(
      `SELECT key, value FROM algo_config WHERE key = ANY($1)`,
      [[
        'halt_drawdown_pct', 'max_daily_loss_pct', 'max_consecutive_losses',
        'max_total_risk_pct', 'vix_max_threshold', 'max_weekly_loss_pct',
      ]]
    );
    const cfg = {};
    cfgResult.rows.forEach(r => { cfg[r.key] = parseFloat(r.value); });
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
    const snaps = snapResult.rows;
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
    let consec = 0;
    for (const r of closedTrades.rows) {
      if (parseFloat(r.profit_loss_dollars || 0) < 0) consec += 1;
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
    const openRiskRow = openRiskResult.rows[0] || {};
    const openRiskDollars = parseFloat(openRiskRow.open_risk || 0);
    const portValue = parseFloat(openRiskRow.port_value || 0);
    const totalRiskPct = portValue > 0 ? (openRiskDollars / portValue) * 100 : 0;

    // VIX
    const vixResult = await pool.query(`
      SELECT vix_level FROM market_health_daily ORDER BY date DESC LIMIT 1
    `);
    const vix = vixResult.rows[0] ? parseFloat(vixResult.rows[0].vix_level || 0) : 0;

    // Market stage
    const stageResult = await pool.query(`
      SELECT market_stage, market_trend FROM market_health_daily ORDER BY date DESC LIMIT 1
    `);
    const stage = stageResult.rows[0] ? parseInt(stageResult.rows[0].market_stage || 1) : 1;
    const trend = stageResult.rows[0]?.market_trend || 'unknown';

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
        description: `Market in stage ${stage} (${trend}) — stage 4 = downtrend halts entries` },
      { id: 'weekly_loss', label: 'Weekly Loss',
        current: Math.round(weeklyLossPct * 100) / 100, threshold: thresh.weekly_loss,
        unit: '%', triggered: weeklyLossPct >= thresh.weekly_loss,
        description: 'Trailing 5-session loss above threshold halts new entries' },
    ];

    return res.json({
      success: true,
      data: {
        any_triggered: breakers.some(b => b.triggered),
        triggered_count: breakers.filter(b => b.triggered).length,
        breakers,
      },
      timestamp: new Date(),
    });
  } catch (error) {
    console.error('Error in /algo/circuit-breakers:', error);
    return res.status(500).json({ success: false, error: error.message });
  }
});

// ============================================================
// SECTOR BREADTH — % of stocks above 50d / 200d MA per sector
// ============================================================
router.get('/sector-breadth', async (req, res) => {
  try {
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
    return res.json({
      success: true,
      items: result.rows.map(r => ({
        sector: r.sector,
        total_stocks: parseInt(r.total_stocks),
        above_50d: parseInt(r.above_50d),
        above_200d: parseInt(r.above_200d),
        pct_above_50d: r.total_stocks > 0
          ? Math.round((r.above_50d / r.total_stocks) * 1000) / 10 : 0,
        pct_above_200d: r.total_stocks > 0
          ? Math.round((r.above_200d / r.total_stocks) * 1000) / 10 : 0,
      })),
      timestamp: new Date(),
    });
  } catch (error) {
    console.error('Error in /algo/sector-breadth:', error);
    return res.status(500).json({ success: false, error: error.message });
  }
});

// ============================================================
// SECTOR STAGE-2 LEADERS — Stage 2 stocks per sector
// ============================================================
router.get('/sector-stage2', async (req, res) => {
  try {
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
    return res.json({
      success: true,
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
      })),
      timestamp: new Date(),
    });
  } catch (error) {
    console.error('Error in /algo/sector-stage2:', error);
    return res.status(500).json({ success: false, error: error.message });
  }
});

// ============================================================
// SECTOR ROTATION SIGNAL — defensive vs cyclical leadership timeline
// ============================================================
router.get('/sector-rotation', async (req, res) => {
  try {
    const pool = getPool();
    const limit = parseInt(req.query.limit) || 90;

    const result = await pool.query(
      `SELECT date, defensive_lead_score, cyclical_weak_score, signal,
              defensive_avg_rs, cyclical_avg_rs, spread, weeks_persistent
       FROM sector_rotation_signal
       ORDER BY date DESC LIMIT $1`,
      [limit]
    );

    return res.json({
      success: true,
      items: result.rows.reverse().map(r => ({
        date: r.date,
        defensive_lead_score: parseFloat(r.defensive_lead_score || 0),
        cyclical_weak_score: parseFloat(r.cyclical_weak_score || 0),
        signal: r.signal,
        defensive_avg_rs: parseFloat(r.defensive_avg_rs || 0),
        cyclical_avg_rs: parseFloat(r.cyclical_avg_rs || 0),
        spread: parseFloat(r.spread || 0),
        weeks_persistent: r.weeks_persistent,
      })),
      timestamp: new Date(),
    });
  } catch (error) {
    // Table may not exist yet — return empty gracefully
    return res.json({ success: true, items: [], timestamp: new Date() });
  }
});

module.exports = router;

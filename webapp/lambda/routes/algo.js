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

const router = express.Router();

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
 * Get active positions
 */
router.get('/positions', async (req, res) => {
  try {
    const pool = getPool();

    const result = await pool.query(`
      SELECT
        position_id,
        symbol,
        quantity,
        avg_entry_price,
        current_price,
        position_value,
        unrealized_pnl,
        unrealized_pnl_pct,
        status,
        stage_in_exit_plan,
        days_since_entry
      FROM algo_positions
      WHERE status = 'open'
      ORDER BY position_value DESC
    `);

    return res.json({
      success: true,
      items: result.rows.map(row => ({
        ...row,
        avg_entry_price: parseFloat(row.avg_entry_price),
        current_price: parseFloat(row.current_price),
        position_value: parseFloat(row.position_value),
        unrealized_pnl: parseFloat(row.unrealized_pnl),
        unrealized_pnl_pct: parseFloat(row.unrealized_pnl_pct)
      })),
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
router.post('/run', async (req, res) => {
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
router.post('/patrol', async (req, res) => {
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

module.exports = router;

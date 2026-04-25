const express = require("express");

const { query } = require("../utils/database");

const router = express.Router();

// Root endpoint - documentation
router.get("/", (req, res) => {
  return res.json({
    data: {
      endpoint: "strategies",
      documentation: "Options strategies and opportunity analysis",
      available_routes: [
        "GET /covered-calls - Get covered call opportunities with filters and pagination",
        "  Query params: symbol={ticker}, min_score={0-100}, min_premium_pct={num}, max_days_to_exp={num}",
        "                trend={uptrend|sideways|downtrend}, min_iv_rank={0-100}, sort_by={score|premium|max_profit|iv_rank|expiration}",
        "                limit={1-200, default 100}, page={1,2,3...}"
      ],
      examples: [
        "GET /api/strategies/covered-calls",
        "GET /api/strategies/covered-calls?symbol=AAPL&min_score=70",
        "GET /api/strategies/covered-calls?trend=uptrend&min_premium_pct=1.5&sort_by=score",
        "GET /api/strategies/covered-calls?symbol=AAPL&limit=50&page=1"
      ]
    },
    success: true
  });
});

// Get covered call opportunities with NEW METHODOLOGY filtering
router.get("/covered-calls", async (req, res) => {
  try {
    const {
      symbol,
      min_probability = 0,  // Default: show all opportunities
      min_premium_pct = 0,  // Default: show all opportunities
      trend = "all",  // Default: show all trends
      sort_by = "premium_pct",  // Sort by premium % by default
      limit = 100,
      page = 1
    } = req.query;

    // Validate pagination parameters
    const pageNum = Math.max(1, parseInt(page) || 1);
    const limitNum = Math.min(200, Math.max(1, parseInt(limit) || 100));
    const offset = (pageNum - 1) * limitNum;

    // Build WHERE clause - with flexible filtering
    let whereClause = `
      WHERE cco.data_date = (SELECT MAX(data_date) FROM covered_call_opportunities)
      AND cco.probability_of_profit >= $1
      AND cco.premium_pct >= $2
      AND (cco.expiration_date - CURRENT_DATE) BETWEEN 30 AND 60
    `;
    const params = [
      parseFloat(min_probability),
      parseFloat(min_premium_pct)
    ];
    let paramIndex = 3;

    // Optional: Filter by trend
    if (trend && trend !== 'all' && ['uptrend', 'sideways', 'downtrend'].includes(trend.toLowerCase())) {
      whereClause += ` AND cco.trend = $${paramIndex}`;
      params.push(trend.toLowerCase());
      paramIndex++;
    }

    // Optional: Filter by specific symbol
    if (symbol) {
      whereClause += ` AND cco.symbol = $${paramIndex}`;
      params.push(symbol.toUpperCase());
      paramIndex++;
    }

    // NEW: Better sort options focused on actionable metrics
    const validSortColumns = [
      'premium_pct',       // Income opportunity
      'probability_of_profit',  // Safety
      'expected_annual_return', // Annualized return
      'expiration_date',        // Time to expiration
      'max_profit_pct',    // Max profit potential
      'rsi'               // Momentum
    ];
    const sortColumn = validSortColumns.includes(sort_by) ? sort_by : 'premium_pct';
    const sortOrder = sort_by === 'expiration_date' ? 'ASC' : 'DESC';

    // Get total count for pagination
    const countSql = `
      SELECT COUNT(*) as total
      FROM covered_call_opportunities cco
      ${whereClause}
    `;

    const countResult = await query(countSql, params);
    const total = countResult.rows && countResult.rows[0] ? parseInt(countResult.rows[0].total) : 0;
    const totalPages = total > 0 ? Math.ceil(total / limitNum) : 0;

    // Get paginated results - ALL DETAILED DATA FOR COMPREHENSIVE ANALYSIS
    const sql = `
      SELECT
        cco.id,
        cco.symbol,
        cco.stock_price,
        cco.strike,
        cco.premium,
        cco.premium_pct,
        cco.breakeven_price,
        cco.expiration_date,
        (cco.expiration_date - CURRENT_DATE)::INTEGER as days_to_expiration,
        cco.probability_of_profit,
        cco.expected_annual_return,
        cco.max_profit,
        cco.max_profit_pct,
        cco.max_loss_amount,
        cco.max_loss_pct,
        cco.risk_reward_ratio,
        cco.rsi,
        cco.sma_50,
        cco.sma_200,
        cco.trend,
        cco.resistance_level,
        cco.distance_to_resistance_pct,
        cco.delta,
        cco.theta,
        cco.iv_rank,
        cco.liquidity_score,
        cco.entry_signal,
        cco.entry_confidence,
        cco.recommended_strike,
        cco.secondary_strike,
        cco.conservative_strike,
        cco.aggressive_strike,
        cco.management_strategy,
        cco.stop_loss_level,
        cco.take_profit_25_target,
        cco.take_profit_50_target,
        cco.take_profit_75_target,
        cco.days_to_earnings,
        cco.days_profit_available,
        cco.avg_daily_premium,
        cco.low_liquidity_warning,
        cco.high_beta_warning,
        cco.opportunity_score,
        cco.beta,
        cco.composite_score,
        cco.momentum_score,
        cco.analyst_count,
        cco.analyst_price_target,
        cco.analyst_bullish_ratio,
        cco.vix_level,
        cco.market_sentiment,
        cco.implied_volatility,
        cco.bid_ask_spread_pct,
        cco.open_interest_rank,
        cco.timing_score,
        cco.market_regime_score,
        cco.vol_regime_score,
        cco.earnings_risk_score,
        cco.sell_now_score,
        cco.strike_quality_score,
        cco.execution_score,
        cco.risk_adjusted_return
      FROM covered_call_opportunities cco
      ${whereClause}
      ORDER BY cco.${sortColumn} ${sortOrder}
      LIMIT $${paramIndex} OFFSET $${paramIndex + 1}
    `;

    params.push(limitNum, offset);

    const result = await query(sql, params);

    return res.json({
      items: result.rows,
      pagination: {
        page: pageNum,
        limit: limitNum,
        total,
        totalPages,
        hasNext: pageNum < totalPages,
        hasPrev: pageNum > 1
      },
      success: true
    });

  } catch (error) {
    console.error("Error fetching covered call opportunities:", error.message);
    console.error("Full error:", error);
    return res.status(500).json({
      error: "Failed to fetch covered call opportunities",
      details: error.message,
      success: false
    });
  }
});

module.exports = router;

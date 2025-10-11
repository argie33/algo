const express = require("express");

const { query } = require("../utils/database");
const { authenticateToken } = require("../middleware/auth");

const router = express.Router();

// Root endpoint - API info
router.get("/", async (req, res) => {
  res.json({
    message: "Position Tracking API - Ready",
    status: "operational",
    endpoints: [
      "GET /stocks - Get stock positioning data",
      "GET /summary - Get positioning summary",
    ],
    timestamp: new Date().toISOString(),
  });
});

// Get stock positioning data
router.get("/stocks", async (req, res) => {
  try {
    const { symbol, timeframe = "daily", limit = 50, page = 1 } = req.query;

    // Safely parse integers with validation to prevent NaN in database queries
    const limitNum = Math.max(1, Math.min(parseInt(limit, 10) || 50, 1000));
    const pageNum = Math.max(1, parseInt(page, 10) || 1);
    const offset = (pageNum - 1) * limitNum;
    console.log(
      `📊 Stock positioning data requested - symbol: ${symbol || "all"}, timeframe: ${timeframe}`
    );

    // Get positioning metrics (ownership, short interest, etc.)
    let metricsQuery = `
      SELECT
        pm.symbol,
        pm.date,
        pm.institutional_ownership,
        pm.institutional_float_held,
        pm.institution_count,
        pm.insider_ownership,
        pm.shares_short,
        pm.shares_short_prior_month,
        pm.short_ratio,
        pm.short_percent_of_float,
        pm.short_interest_change,
        pm.float_shares,
        pm.shares_outstanding
      FROM positioning_metrics pm
      WHERE pm.symbol IS NOT NULL
    `;

    let metricsParams = [];
    if (symbol) {
      metricsQuery += ` AND pm.symbol = $1`;
      metricsParams.push(symbol);
    }
    metricsQuery += ` ORDER BY pm.date DESC LIMIT 1`;

    // Get institutional positioning data from institutional_positioning table
    let institutionalQuery = `
      SELECT
        ip.symbol,
        ip.institution_type,
        ip.institution_name,
        ip.position_size,
        ip.position_change_percent,
        ip.market_share,
        ip.filing_date,
        ip.quarter
      FROM institutional_positioning ip
      WHERE ip.symbol IS NOT NULL
    `;

    let params = [];
    if (symbol) {
      institutionalQuery += ` AND ip.symbol = $1`;
      params.push(symbol);
    }

    institutionalQuery += ` ORDER BY ip.filing_date DESC, ip.position_size DESC LIMIT $${params.length + 1} OFFSET $${params.length + 2}`;
    params.push(limitNum, offset);

    // Get insider transactions (NEW!)
    let insiderTxnQuery = `
      SELECT
        symbol,
        insider_name,
        position,
        transaction_type,
        shares,
        value,
        transaction_date,
        ownership_type
      FROM insider_transactions
    `;

    let insiderParams = [];
    if (symbol) {
      insiderTxnQuery += ` WHERE symbol = $1`;
      insiderParams.push(symbol);
    }
    insiderTxnQuery += ` ORDER BY transaction_date DESC LIMIT 20`;

    // Get insider roster (NEW!)
    let insiderRosterQuery = `
      SELECT
        symbol,
        insider_name,
        position,
        most_recent_transaction,
        latest_transaction_date,
        shares_owned_directly
      FROM insider_roster
    `;

    let rosterParams = [];
    if (symbol) {
      insiderRosterQuery += ` WHERE symbol = $1`;
      rosterParams.push(symbol);
    }
    insiderRosterQuery += ` ORDER BY shares_owned_directly DESC LIMIT 20`;

    // Get retail sentiment
    let sentimentQuery = `
      SELECT
        symbol,
        bullish_percentage,
        bearish_percentage,
        neutral_percentage,
        net_sentiment,
        sentiment_change,
        source,
        date
      FROM retail_sentiment
    `;

    let sentimentParams = [];
    if (symbol) {
      sentimentQuery += ` WHERE symbol = $1`;
      sentimentParams.push(symbol);
    }
    sentimentQuery += ` ORDER BY date DESC LIMIT 10`;

    const [metricsResult, institutionalResult, insiderTxnResult, insiderRosterResult, sentimentResult] = await Promise.all([
      query(metricsQuery, metricsParams),
      query(institutionalQuery, params),
      query(insiderTxnQuery, insiderParams),
      query(insiderRosterQuery, rosterParams),
      query(sentimentQuery, sentimentParams)
    ]);

    if (!metricsResult.rows.length && !institutionalResult.rows.length && !sentimentResult.rows.length) {
      return res.status(404).json({
        success: false,
        error: "No positioning data found",
        message: "No positioning data available for this symbol",
        timestamp: new Date().toISOString()
      });
    }

    // Calculate positioning score with new data
    let positioningScore = null;
    let scoreBreakdown = {};
    const metrics = metricsResult.rows[0];

    if (metrics) {
      let score = 50; // Start neutral

      // 1. Institutional Quality Score (0-25 points)
      const instOwn = parseFloat(metrics.institutional_ownership || 0);
      const instCount = parseInt(metrics.institution_count || 0);

      // Base institutional ownership score
      let instScore = 0;
      if (instOwn > 0.7) instScore += 15;
      else if (instOwn > 0.5) instScore += 10;
      else if (instOwn > 0.3) instScore += 5;
      else if (instOwn < 0.2) instScore -= 5;

      // Institution diversity bonus (more holders = better)
      if (instCount > 500) instScore += 10;
      else if (instCount > 200) instScore += 7;
      else if (instCount > 100) instScore += 5;
      else if (instCount > 50) instScore += 3;

      score += Math.min(25, instScore);
      scoreBreakdown.institutional = Math.min(25, instScore);

      // 2. Insider Conviction Score (0-25 points)
      const insiderOwn = parseFloat(metrics.insider_ownership || 0);

      // Base insider ownership score
      let insiderScore = 0;
      if (insiderOwn > 0.15) insiderScore += 10;
      else if (insiderOwn > 0.1) insiderScore += 7;
      else if (insiderOwn > 0.05) insiderScore += 5;
      else if (insiderOwn > 0.02) insiderScore += 3;

      // Recent insider buying activity (NEW!)
      const recentTxns = insiderTxnResult.rows.filter(txn => {
        const txnDate = new Date(txn.transaction_date);
        const threeMonthsAgo = new Date();
        threeMonthsAgo.setMonth(threeMonthsAgo.getMonth() - 3);
        return txnDate >= threeMonthsAgo;
      });

      const buys = recentTxns.filter(t => t.transaction_type?.toLowerCase().includes('buy') ||
                                           t.transaction_type?.toLowerCase().includes('purchase'));
      const sells = recentTxns.filter(t => t.transaction_type?.toLowerCase().includes('sell') ||
                                            t.transaction_type?.toLowerCase().includes('sale'));

      const buyValue = buys.reduce((sum, t) => sum + (parseFloat(t.value) || 0), 0);
      const sellValue = sells.reduce((sum, t) => sum + (parseFloat(t.value) || 0), 0);

      if (buyValue > sellValue * 2) insiderScore += 15; // Heavy buying
      else if (buyValue > sellValue) insiderScore += 10; // Net buying
      else if (sellValue > buyValue * 2) insiderScore -= 10; // Heavy selling
      else if (sellValue > buyValue) insiderScore -= 5; // Net selling

      score += Math.min(25, Math.max(-10, insiderScore));
      scoreBreakdown.insider = Math.min(25, Math.max(-10, insiderScore));

      // 3. Short Interest Score (0-25 points)
      const shortPct = parseFloat(metrics.short_percent_of_float || 0);
      const shortChange = parseFloat(metrics.short_interest_change || 0);

      let shortScore = 0;
      // Short interest level
      if (shortPct > 0.3) shortScore -= 15; // Extreme short
      else if (shortPct > 0.2) shortScore -= 10; // Heavy short
      else if (shortPct > 0.1) shortScore -= 5;
      else if (shortPct < 0.02) shortScore += 10; // Very low short

      // Short interest trend
      if (shortChange < -0.15) shortScore += 15; // Major covering
      else if (shortChange < -0.1) shortScore += 10; // Shorts covering
      else if (shortChange < -0.05) shortScore += 5;
      else if (shortChange > 0.15) shortScore -= 15; // Major increase
      else if (shortChange > 0.1) shortScore -= 10; // Shorts increasing
      else if (shortChange > 0.05) shortScore -= 5;

      score += Math.min(25, Math.max(-20, shortScore));
      scoreBreakdown.short_interest = Math.min(25, Math.max(-20, shortScore));

      // 4. Smart Money Flow Score (0-25 points) (NEW!)
      let smartMoneyScore = 0;

      // Mutual fund and institutional flows
      const mutualFunds = institutionalResult.rows.filter(i => i.institution_type === 'MUTUAL_FUND');
      const hedgeFunds = institutionalResult.rows.filter(i => i.institution_type === 'HEDGE_FUND');

      const mfAccumulating = mutualFunds.filter(mf => (parseFloat(mf.position_change_percent) || 0) > 5).length;
      const mfDistributing = mutualFunds.filter(mf => (parseFloat(mf.position_change_percent) || 0) < -5).length;

      if (mfAccumulating > mfDistributing * 2) smartMoneyScore += 10; // Heavy accumulation
      else if (mfAccumulating > mfDistributing) smartMoneyScore += 5; // Net accumulation
      else if (mfDistributing > mfAccumulating * 2) smartMoneyScore -= 10; // Heavy distribution
      else if (mfDistributing > mfAccumulating) smartMoneyScore -= 5; // Net distribution

      // Hedge fund positioning
      const hfAccumulating = hedgeFunds.filter(hf => (parseFloat(hf.position_change_percent) || 0) > 5).length;
      const hfDistributing = hedgeFunds.filter(hf => (parseFloat(hf.position_change_percent) || 0) < -5).length;

      if (hfAccumulating > hfDistributing * 2) smartMoneyScore += 15;
      else if (hfAccumulating > hfDistributing) smartMoneyScore += 10;
      else if (hfDistributing > hfAccumulating * 2) smartMoneyScore -= 15;
      else if (hfDistributing > hfAccumulating) smartMoneyScore -= 10;

      score += Math.min(25, Math.max(-15, smartMoneyScore));
      scoreBreakdown.smart_money = Math.min(25, Math.max(-15, smartMoneyScore));

      positioningScore = Math.max(0, Math.min(100, score));
    }

    res.json({
      positioning_metrics: metricsResult.rows[0] || null,
      positioning_score: positioningScore,
      score_breakdown: scoreBreakdown,
      institutional_holders: institutionalResult.rows,
      insider_transactions: insiderTxnResult.rows,
      insider_roster: insiderRosterResult.rows,
      retail_sentiment: sentimentResult.rows[0] || null,
      metadata: {
        symbol: symbol || "all",
        timeframe: timeframe,
        total_records: {
          institutional: institutionalResult.rows.length,
          insider_transactions: insiderTxnResult.rows.length,
          insider_roster: insiderRosterResult.rows.length,
          sentiment: sentimentResult.rows.length,
        },
        last_updated: new Date().toISOString(),
      },
    });
  } catch (error) {
    console.error("Error fetching stock positioning data:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch stock positioning data",
    });
  }
});

// Get positioning summary
router.get("/summary", authenticateToken, async (req, res) => {
  try {
    // Get institutional positioning summary from positioning_metrics
    const institutionalSummary = await query(`
      SELECT
        AVG(COALESCE(pm.institutional_ownership, 0)) as avg_institutional_ownership,
        AVG(COALESCE(pm.insider_ownership, 0)) as avg_insider_ownership,
        AVG(COALESCE(pm.short_percent_of_float, 0)) as avg_short_interest,
        AVG(COALESCE(pm.short_interest_change, 0)) as avg_short_change,
        COUNT(CASE WHEN pm.institutional_ownership > 0.5 THEN 1 END) as high_institutional_count,
        COUNT(CASE WHEN pm.short_percent_of_float > 0.1 THEN 1 END) as high_short_count,
        COUNT(*) as total_positions
      FROM positioning_metrics pm
      WHERE pm.date >= CURRENT_DATE - INTERVAL '30 days'
    `);

    // Get retail sentiment summary
    const retailSummary = await query(`
      SELECT
        AVG(bullish_percentage) as avg_bullish,
        AVG(bearish_percentage) as avg_bearish,
        AVG(net_sentiment) as avg_net_sentiment,
        COUNT(*) as total_readings
      FROM retail_sentiment
      WHERE date >= CURRENT_DATE - INTERVAL '30 days'
    `);

    const institutional = institutionalSummary.rows[0];
    const retail = retailSummary.rows[0];

    // Calculate institutional flow (bullish if high ownership, bearish if high short interest)
    const inst_ownership_score = parseFloat(institutional.avg_institutional_ownership || 0) * 100;
    const short_interest_score = parseFloat(institutional.avg_short_interest || 0) * 100;
    const short_change_score = parseFloat(institutional.avg_short_change || 0) * 100;

    let institutional_flow = "NEUTRAL";
    if (inst_ownership_score > 60 && short_change_score < -5) {
      institutional_flow = "BULLISH";
    } else if (short_interest_score > 15 || short_change_score > 10) {
      institutional_flow = "BEARISH";
    } else if (inst_ownership_score > 50) {
      institutional_flow = "MODERATELY_BULLISH";
    } else if (short_interest_score > 10) {
      institutional_flow = "MODERATELY_BEARISH";
    }

    // Calculate overall positioning
    const retail_sentiment_value = parseFloat(retail.avg_net_sentiment || 0);
    let overall_positioning = "NEUTRAL";

    if (institutional_flow === "BULLISH" && retail_sentiment_value > 40) {
      overall_positioning = "BULLISH";
    } else if (
      (institutional_flow === "BULLISH" || institutional_flow === "MODERATELY_BULLISH") &&
      retail_sentiment_value > 20
    ) {
      overall_positioning = "MODERATELY_BULLISH";
    } else if (institutional_flow === "BEARISH" && retail_sentiment_value < -20) {
      overall_positioning = "BEARISH";
    } else if (
      (institutional_flow === "BEARISH" || institutional_flow === "MODERATELY_BEARISH") &&
      retail_sentiment_value < 0
    ) {
      overall_positioning = "MODERATELY_BEARISH";
    }

    res.json({
      market_overview: {
        institutional_flow: institutional_flow,
        retail_sentiment:
          retail_sentiment_value > 20
            ? "BULLISH"
            : retail_sentiment_value < -20
              ? "BEARISH"
              : "MIXED",
        overall_positioning: overall_positioning,
      },
      key_metrics: {
        avg_institutional_ownership: parseFloat(institutional.avg_institutional_ownership || 0),
        avg_insider_ownership: parseFloat(institutional.avg_insider_ownership || 0),
        avg_short_interest: parseFloat(institutional.avg_short_interest || 0),
        avg_short_change: parseFloat(institutional.avg_short_change || 0),
        retail_net_sentiment: retail_sentiment_value,
      },
      data_freshness: {
        institutional_positions: parseInt(institutional.total_positions || 0),
        retail_readings: parseInt(retail.total_readings || 0),
        high_institutional_count: parseInt(institutional.high_institutional_count || 0),
        high_short_count: parseInt(institutional.high_short_count || 0),
      },
      last_updated: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error fetching positioning summary:", error);
    res
      .status(500)
      .json({ success: false, error: "Failed to fetch positioning summary" });
  }
});

// Positioning data - top movers by positioning changes
router.get("/data", async (req, res) => {
  try {
    const { limit = 20 } = req.query;
    const limitNum = Math.max(1, Math.min(parseInt(limit, 10) || 20, 100));

    // Get stocks with highest institutional ownership changes
    const topInstitutionalFlows = await query(`
      WITH latest_metrics AS (
        SELECT DISTINCT ON (symbol)
          symbol,
          institutional_ownership,
          insider_ownership,
          short_percent_of_float,
          short_interest_change,
          date
        FROM positioning_metrics
        ORDER BY symbol, date DESC
      )
      SELECT
        lm.symbol,
        lm.institutional_ownership,
        lm.insider_ownership,
        lm.short_percent_of_float,
        lm.short_interest_change,
        lm.date,
        cp.company_name,
        cp.sector,
        cp.industry
      FROM latest_metrics lm
      LEFT JOIN company_profile cp ON lm.symbol = cp.symbol
      WHERE lm.institutional_ownership IS NOT NULL
      ORDER BY ABS(COALESCE(lm.short_interest_change, 0)) DESC
      LIMIT $1
    `, [limitNum]);

    // Get latest retail sentiment trends
    const retailTrends = await query(`
      SELECT DISTINCT ON (symbol)
        symbol,
        bullish_percentage,
        bearish_percentage,
        net_sentiment,
        sentiment_change,
        source,
        date
      FROM retail_sentiment
      ORDER BY symbol, date DESC
      LIMIT $1
    `, [limitNum]);

    res.json({
      success: true,
      data: {
        top_institutional_flows: topInstitutionalFlows.rows,
        retail_sentiment_trends: retailTrends.rows,
      },
      metadata: {
        limit: limitNum,
        institutional_count: topInstitutionalFlows.rows.length,
        retail_count: retailTrends.rows.length,
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error fetching positioning data:", error);
    res.status(500).json({
      success: false,
      error: "Positioning data unavailable",
      message: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

module.exports = router;

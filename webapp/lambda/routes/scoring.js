const express = require("express");

const { query } = require("../utils/database");

const router = express.Router();

// Basic ping endpoint
router.get("/ping", (req, res) => {
  res.json({
    status: "ok",
    endpoint: "scoring",
    timestamp: new Date().toISOString(),
  });
});

// Calculate comprehensive scoring for stocks
router.get("/calculate/:symbol", async (req, res) => {
  try {
    const symbol = req.params.symbol.toUpperCase();
    const forceRecalculate = req.query.recalculate === "true";

    // Check if we have recent scores unless forcing recalculation
    if (!forceRecalculate) {
      const existingScore = await query(
        `
        SELECT * FROM comprehensive_scores 
        WHERE symbol = $1 
        AND updated_at > NOW() - INTERVAL '1 hour'
        ORDER BY updated_at DESC 
        LIMIT 1
      `,
        [symbol]
      );

      if (existingScore.length > 0) {
        return res.json({
          success: true,
          scores: existingScore[0],
          cached: true,
        });
      }
    }

    // Calculate comprehensive scores
    const scores = await calculateComprehensiveScores(symbol);

    if (!scores) {
      return res.status(404).json({
        success: false,
        error: "Unable to calculate scores - insufficient data",
      });
    }

    // Store scores in database
    await storeComprehensiveScores(symbol, scores);

    res.json({
      success: true,
      scores: scores,
      cached: false,
    });
  } catch (error) {
    console.error("Scoring calculation error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to calculate comprehensive scores",
      details: error.message,
    });
  }
});

// Batch calculate scores for multiple symbols
router.post("/calculate/batch", async (req, res) => {
  try {
    const { symbols, forceRecalculate = false } = req.body;

    if (!symbols || !Array.isArray(symbols) || symbols.length === 0) {
      return res.status(400).json({
        success: false,
        error: "symbols array is required",
      });
    }

    if (symbols.length > 50) {
      return res.status(400).json({
        success: false,
        error: "Maximum 50 symbols per batch",
      });
    }

    const results = [];
    const errors = [];

    for (const symbol of symbols) {
      try {
        const symbolUpper = symbol.toUpperCase();

        // Check cache first unless forcing recalculation
        let scores = null;
        if (!forceRecalculate) {
          const existingScore = await query(
            `
            SELECT * FROM comprehensive_scores 
            WHERE symbol = $1 
            AND updated_at > NOW() - INTERVAL '1 hour'
            ORDER BY updated_at DESC 
            LIMIT 1
          `,
            [symbolUpper]
          );

          if (existingScore.length > 0) {
            scores = existingScore[0];
          }
        }

        // Calculate if not cached
        if (!scores) {
          scores = await calculateComprehensiveScores(symbolUpper);
          if (scores) {
            await storeComprehensiveScores(symbolUpper, scores);
          }
        }

        if (scores) {
          results.push({
            symbol: symbolUpper,
            scores: scores,
            success: true,
          });
        } else {
          errors.push({
            symbol: symbolUpper,
            error: "Insufficient data for scoring",
          });
        }
      } catch (error) {
        errors.push({
          symbol: symbol,
          error: error.message,
        });
      }
    }

    res.json({
      success: true,
      results: results,
      errors: errors,
      processed: results.length,
      failed: errors.length,
    });
  } catch (error) {
    console.error("Batch scoring error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to calculate batch scores",
      details: error.message,
    });
  }
});

// Get top stocks by composite score
router.get("/top", async (req, res) => {
  try {
    const limit = Math.min(parseInt(req.query.limit) || 50, 200);
    const sector = req.query.sector;
    const marketCapTier = req.query.marketCapTier;
    const minScore = parseFloat(req.query.minScore) || 0;

    let whereClause = "WHERE cs.composite_score >= $1";
    const params = [minScore];
    let paramCount = 1;

    if (sector) {
      paramCount++;
      whereClause += ` AND se.sector = $${paramCount}`;
      params.push(sector);
    }

    if (marketCapTier) {
      paramCount++;
      whereClause += ` AND se.market_cap_tier = $${paramCount}`;
      params.push(marketCapTier);
    }

    const topStocks = await query(
      `
      SELECT cs.*, se.company_name, se.sector, se.market_cap, se.market_cap_tier
      FROM comprehensive_scores cs
      JOIN stock_symbols_enhanced se ON cs.symbol = se.symbol
      ${whereClause}
      AND cs.updated_at > NOW() - INTERVAL '24 hours'
      ORDER BY cs.composite_score DESC
      LIMIT ${limit}
    `,
      params
    );

    res.json({
      success: true,
      stocks: topStocks,
      count: topStocks.length,
      filters: {
        sector: sector || "all",
        marketCapTier: marketCapTier || "all",
        minScore: minScore,
      },
    });
  } catch (error) {
    console.error("Top stocks query error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to get top stocks",
      details: error.message,
    });
  }
});

// Get scoring distribution and statistics
router.get("/stats", async (req, res) => {
  try {
    const stats = await query(`
      SELECT 
        COUNT(*) as total_stocks,
        AVG(quality_score) as avg_quality,
        AVG(growth_score) as avg_growth,
        AVG(value_score) as avg_value,
        AVG(momentum_score) as avg_momentum,
        AVG(sentiment_score) as avg_sentiment,
        AVG(positioning_score) as avg_positioning,
        AVG(composite_score) as avg_composite,
        PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY composite_score) as q1_composite,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY composite_score) as median_composite,
        PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY composite_score) as q3_composite,
        MAX(composite_score) as max_composite,
        MIN(composite_score) as min_composite
      FROM comprehensive_scores
      WHERE updated_at > NOW() - INTERVAL '24 hours'
    `);

    const sectorStats = await query(`
      SELECT 
        se.sector,
        COUNT(*) as count,
        AVG(cs.composite_score) as avg_score,
        MAX(cs.composite_score) as max_score
      FROM comprehensive_scores cs
      JOIN stock_symbols_enhanced se ON cs.symbol = se.symbol
      WHERE cs.updated_at > NOW() - INTERVAL '24 hours'
      GROUP BY se.sector
      ORDER BY avg_score DESC
    `);

    res.json({
      success: true,
      overallStats: stats[0],
      sectorStats: sectorStats,
    });
  } catch (error) {
    console.error("Scoring stats error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to get scoring statistics",
      details: error.message,
    });
  }
});

// Core scoring calculation function
async function calculateComprehensiveScores(symbol) {
  try {
    // Get all necessary data for scoring (enhanced with new data sources)
    const [
      basicInfo,
      financialData,
      technicalData,
      sentimentData,
      momentumData,
      positioningData,
      realtimeSentimentData,
    ] = await Promise.all([
      getBasicInfo(symbol),
      getFinancialMetrics(symbol),
      getTechnicalIndicators(symbol),
      getSentimentData(symbol),
      getMomentumMetrics(symbol),
      getPositioningMetrics(symbol),
      getRealtimeSentimentData(symbol),
    ]);

    if (!basicInfo) {
      console.log(`No basic info found for ${symbol}`);
      return null;
    }

    // Calculate each component score using enhanced data
    const qualityScore = calculateQualityScore(basicInfo, financialData);
    const growthScore = calculateGrowthScore(basicInfo, financialData);
    const valueScore = calculateValueScore(basicInfo, financialData);
    const momentumScore = calculateEnhancedMomentumScore(
      basicInfo,
      technicalData,
      momentumData
    );
    const sentimentScore = calculateEnhancedSentimentScore(
      sentimentData,
      realtimeSentimentData
    );
    const positioningScore = calculateEnhancedPositioningScore(
      basicInfo,
      technicalData,
      positioningData
    );

    // Calculate weighted composite score
    const compositeScore = calculateCompositeScore({
      quality: qualityScore,
      growth: growthScore,
      value: valueScore,
      momentum: momentumScore,
      sentiment: sentimentScore,
      positioning: positioningScore,
    });

    return {
      symbol: symbol,
      quality_score: qualityScore,
      growth_score: growthScore,
      value_score: valueScore,
      momentum_score: momentumScore,
      sentiment_score: sentimentScore,
      positioning_score: positioningScore,
      composite_score: compositeScore,
      calculation_date: new Date().toISOString().split("T")[0],
      data_quality: assessDataQuality(
        basicInfo,
        financialData,
        technicalData,
        sentimentData,
        momentumData,
        positioningData,
        realtimeSentimentData
      ),
    };
  } catch (error) {
    console.error(`Error calculating scores for ${symbol}:`, error);
    return null;
  }
}

// Individual scoring components
function calculateQualityScore(basicInfo, financialData) {
  let score = 0.5; // Base score
  let components = 0;

  if (financialData) {
    // ROE component (25% weight)
    if (financialData.roe !== null && financialData.roe !== undefined) {
      const roe = parseFloat(financialData.roe);
      score += (Math.min(Math.max(roe, 0), 0.5) / 0.5) * 0.25;
      components++;
    }

    // ROA component (20% weight)
    if (financialData.roa !== null && financialData.roa !== undefined) {
      const roa = parseFloat(financialData.roa);
      score += (Math.min(Math.max(roa, 0), 0.3) / 0.3) * 0.2;
      components++;
    }

    // Debt-to-Equity component (20% weight)
    if (
      financialData.debt_to_equity !== null &&
      financialData.debt_to_equity !== undefined
    ) {
      const dte = parseFloat(financialData.debt_to_equity);
      // Lower debt is better - invert and normalize
      const debtScore = Math.max(0, 1 - dte / 2); // Score decreases as D/E increases
      score += debtScore * 0.2;
      components++;
    }

    // Profit margin component (15% weight)
    if (
      financialData.net_profit_margin !== null &&
      financialData.net_profit_margin !== undefined
    ) {
      const margin = parseFloat(financialData.net_profit_margin);
      score += (Math.min(Math.max(margin, 0), 0.3) / 0.3) * 0.15;
      components++;
    }

    // Current ratio component (10% weight)
    if (
      financialData.current_ratio !== null &&
      financialData.current_ratio !== undefined
    ) {
      const cr = parseFloat(financialData.current_ratio);
      // Optimal range 1.5-3.0
      const crScore =
        cr >= 1.5 && cr <= 3.0
          ? 1.0
          : cr > 3.0
            ? Math.max(0, 1 - (cr - 3) / 3)
            : Math.max(0, cr / 1.5);
      score += crScore * 0.1;
      components++;
    }

    // Piotroski F-Score component (10% weight)
    if (
      financialData.piotroski_score !== null &&
      financialData.piotroski_score !== undefined
    ) {
      const piotroski = parseFloat(financialData.piotroski_score);
      score += (piotroski / 9) * 0.1; // Normalize to 0-1
      components++;
    }
  }

  // Normalize score if we have fewer components
  if (components > 0 && components < 6) {
    score = 0.5 + (score - 0.5) * (6 / components);
  }

  return Math.min(Math.max(score, 0), 1);
}

function calculateGrowthScore(basicInfo, financialData) {
  let score = 0.5; // Base score
  let components = 0;

  if (financialData) {
    // Revenue growth (30% weight)
    if (
      financialData.revenue_growth_1y !== null &&
      financialData.revenue_growth_1y !== undefined
    ) {
      const growth = parseFloat(financialData.revenue_growth_1y);
      // Normalize growth: 0% = 0.5, 20%+ = 1.0, negative = lower
      const growthScore = 0.5 + growth / 0.4; // 40% growth = max score
      score += Math.min(Math.max(growthScore, 0), 1) * 0.3;
      components++;
    }

    // Earnings growth (30% weight)
    if (
      financialData.earnings_growth_1y !== null &&
      financialData.earnings_growth_1y !== undefined
    ) {
      const growth = parseFloat(financialData.earnings_growth_1y);
      const growthScore = 0.5 + growth / 0.4;
      score += Math.min(Math.max(growthScore, 0), 1) * 0.3;
      components++;
    }

    // Revenue growth 3Y (20% weight)
    if (
      financialData.revenue_growth_3y !== null &&
      financialData.revenue_growth_3y !== undefined
    ) {
      const growth = parseFloat(financialData.revenue_growth_3y);
      const growthScore = 0.5 + growth / 0.3; // 30% = max for 3Y
      score += Math.min(Math.max(growthScore, 0), 1) * 0.2;
      components++;
    }

    // ROIC trend (20% weight)
    if (financialData.roic !== null && financialData.roic !== undefined) {
      const roic = parseFloat(financialData.roic);
      // ROIC > 15% is excellent
      const roicScore = Math.min(roic / 0.15, 1);
      score += Math.max(roicScore, 0) * 0.2;
      components++;
    }
  }

  // Normalize if fewer components
  if (components > 0 && components < 4) {
    score = 0.5 + (score - 0.5) * (4 / components);
  }

  return Math.min(Math.max(score, 0), 1);
}

function calculateValueScore(basicInfo, financialData) {
  let score = 0.5; // Base score
  let components = 0;

  if (basicInfo) {
    // P/E ratio (25% weight)
    if (basicInfo.trailing_pe !== null && basicInfo.trailing_pe !== undefined) {
      const pe = parseFloat(basicInfo.trailing_pe);
      if (pe > 0 && pe < 100) {
        // Reasonable P/E range
        // Lower P/E is better: P/E of 15 = score 1.0, P/E of 30+ = score 0
        const peScore = Math.max(0, 1 - (pe - 10) / 20);
        score += peScore * 0.25;
        components++;
      }
    }

    // P/B ratio (20% weight)
    if (
      basicInfo.price_to_book !== null &&
      basicInfo.price_to_book !== undefined
    ) {
      const pb = parseFloat(basicInfo.price_to_book);
      if (pb > 0 && pb < 20) {
        // P/B of 1.0 = perfect, higher is worse
        const pbScore = Math.max(0, 1 - (pb - 0.5) / 3);
        score += pbScore * 0.2;
        components++;
      }
    }
  }

  if (financialData) {
    // EV/EBITDA (20% weight)
    if (
      financialData.ev_ebitda !== null &&
      financialData.ev_ebitda !== undefined
    ) {
      const evEbitda = parseFloat(financialData.ev_ebitda);
      if (evEbitda > 0 && evEbitda < 50) {
        const evScore = Math.max(0, 1 - (evEbitda - 8) / 15);
        score += evScore * 0.2;
        components++;
      }
    }

    // Price/Sales (15% weight)
    if (
      financialData.price_to_sales !== null &&
      financialData.price_to_sales !== undefined
    ) {
      const ps = parseFloat(financialData.price_to_sales);
      if (ps > 0 && ps < 20) {
        const psScore = Math.max(0, 1 - (ps - 1) / 5);
        score += psScore * 0.15;
        components++;
      }
    }

    // Free Cash Flow Yield (10% weight)
    if (
      financialData.fcf_yield !== null &&
      financialData.fcf_yield !== undefined
    ) {
      const fcfYield = parseFloat(financialData.fcf_yield);
      // Higher FCF yield is better
      const fcfScore = Math.min(fcfYield / 0.08, 1); // 8% FCF yield = max score
      score += Math.max(fcfScore, 0) * 0.1;
      components++;
    }

    // Dividend yield (10% weight)
    if (
      basicInfo.dividend_yield !== null &&
      basicInfo.dividend_yield !== undefined
    ) {
      const divYield = parseFloat(basicInfo.dividend_yield);
      // Sweet spot 2-6%
      const divScore =
        divYield >= 0.02 && divYield <= 0.06
          ? 1.0
          : divYield > 0.06
            ? Math.max(0, 1 - (divYield - 0.06) / 0.04)
            : divYield / 0.02;
      score += divScore * 0.1;
      components++;
    }
  }

  // Normalize if fewer components
  if (components > 0 && components < 6) {
    score = 0.5 + (score - 0.5) * (6 / components);
  }

  return Math.min(Math.max(score, 0), 1);
}

function calculateEnhancedMomentumScore(
  basicInfo,
  technicalData,
  momentumData
) {
  let score = 0.5; // Base score
  let components = 0;

  // Use advanced momentum data if available
  if (momentumData) {
    // Jegadeesh-Titman 12-1 momentum (30% weight - academic standard)
    if (
      momentumData.jt_momentum_12_1 !== null &&
      momentumData.jt_momentum_12_1 !== undefined
    ) {
      const jtMomentum = parseFloat(momentumData.jt_momentum_12_1);
      // Convert to 0-1 score, with 0.2 (20%) return = max score
      const jtScore = Math.min(Math.max((jtMomentum + 0.2) / 0.4, 0), 1);
      score += jtScore * 0.3;
      components++;
    }

    // Risk-adjusted momentum (20% weight)
    if (
      momentumData.risk_adjusted_momentum !== null &&
      momentumData.risk_adjusted_momentum !== undefined
    ) {
      const riskAdjMomentum = parseFloat(momentumData.risk_adjusted_momentum);
      // Sharpe ratio style - normalize around 1.0
      const riskAdjScore = Math.min(Math.max((riskAdjMomentum + 1) / 2, 0), 1);
      score += riskAdjScore * 0.2;
      components++;
    }

    // Momentum persistence (15% weight)
    if (
      momentumData.momentum_persistence !== null &&
      momentumData.momentum_persistence !== undefined
    ) {
      const persistence = parseFloat(momentumData.momentum_persistence);
      // Higher persistence is better (already 0-1 scale)
      score += persistence * 0.15;
      components++;
    }

    // Volume-weighted momentum (15% weight)
    if (
      momentumData.volume_weighted_momentum !== null &&
      momentumData.volume_weighted_momentum !== undefined
    ) {
      const volMomentum = parseFloat(momentumData.volume_weighted_momentum);
      const volMomentumScore = Math.min(
        Math.max((volMomentum + 0.1) / 0.2, 0),
        1
      );
      score += volMomentumScore * 0.15;
      components++;
    }

    // Earnings acceleration (10% weight)
    if (
      momentumData.earnings_acceleration !== null &&
      momentumData.earnings_acceleration !== undefined
    ) {
      const earnAccel = parseFloat(momentumData.earnings_acceleration);
      const earnAccelScore = Math.min(Math.max((earnAccel + 0.1) / 0.2, 0), 1);
      score += earnAccelScore * 0.1;
      components++;
    }

    // Momentum quality (10% weight)
    if (
      momentumData.momentum_strength !== null &&
      momentumData.momentum_strength !== undefined
    ) {
      const strength = parseFloat(momentumData.momentum_strength);
      score += strength * 0.1;
      components++;
    }
  }

  // Fallback to technical indicators if no momentum data
  if (components === 0 && technicalData) {
    return calculateMomentumScore(basicInfo, technicalData);
  }

  // Normalize if fewer components
  if (components > 0 && components < 6) {
    score = 0.5 + (score - 0.5) * (6 / components);
  }

  return Math.min(Math.max(score, 0), 1);
}

// Keep original momentum function for fallback
function calculateMomentumScore(basicInfo, technicalData) {
  let score = 0.5; // Base score
  let components = 0;

  if (technicalData) {
    // RSI component (20% weight)
    if (technicalData.rsi_14 !== null && technicalData.rsi_14 !== undefined) {
      const rsi = parseFloat(technicalData.rsi_14);
      // RSI 40-60 is neutral, 60-80 is positive momentum
      const rsiScore =
        rsi >= 50 && rsi <= 70
          ? 1.0
          : rsi > 70
            ? Math.max(0, 1 - (rsi - 70) / 20)
            : Math.max(0, rsi / 50);
      score += rsiScore * 0.2;
      components++;
    }

    // MACD histogram (20% weight)
    if (
      technicalData.macd_histogram !== null &&
      technicalData.macd_histogram !== undefined
    ) {
      const macdHist = parseFloat(technicalData.macd_histogram);
      // Positive MACD histogram indicates upward momentum
      const macdScore = macdHist > 0 ? Math.min(1, macdHist * 100) : 0;
      score += macdScore * 0.2;
      components++;
    }

    // Price vs SMA 20 (15% weight)
    if (
      technicalData.price_vs_sma_20 !== null &&
      technicalData.price_vs_sma_20 !== undefined
    ) {
      const priceVsSma = parseFloat(technicalData.price_vs_sma_20);
      // Being above SMA is positive, but not too far above
      const smaScore = priceVsSma > 0 ? Math.min(1, priceVsSma * 5) : 0;
      score += smaScore * 0.15;
      components++;
    }

    // Volume ratio (15% weight)
    if (
      technicalData.volume_ratio !== null &&
      technicalData.volume_ratio !== undefined
    ) {
      const volRatio = parseFloat(technicalData.volume_ratio);
      // Higher volume supports momentum
      const volScore =
        volRatio > 1 ? Math.min(1, (volRatio - 1) * 2) : volRatio;
      score += volScore * 0.15;
      components++;
    }

    // ADX (trend strength) (15% weight)
    if (technicalData.adx_14 !== null && technicalData.adx_14 !== undefined) {
      const adx = parseFloat(technicalData.adx_14);
      // ADX > 25 indicates strong trend
      const adxScore = adx > 25 ? Math.min(1, (adx - 25) / 50) : 0;
      score += adxScore * 0.15;
      components++;
    }

    // Bollinger Band position (15% weight)
    if (
      technicalData.bb_position !== null &&
      technicalData.bb_position !== undefined
    ) {
      const bbPos = parseFloat(technicalData.bb_position);
      // Position 0.5-0.8 is ideal momentum range
      const bbScore =
        bbPos >= 0.5 && bbPos <= 0.8
          ? 1.0
          : bbPos > 0.8
            ? Math.max(0, 1 - (bbPos - 0.8) * 5)
            : bbPos * 2;
      score += bbScore * 0.15;
      components++;
    }
  }

  // Normalize if fewer components
  if (components > 0 && components < 6) {
    score = 0.5 + (score - 0.5) * (6 / components);
  }

  return Math.min(Math.max(score, 0), 1);
}

function calculateEnhancedSentimentScore(sentimentData, realtimeSentimentData) {
  let score = 0.5; // Base score
  let components = 0;

  // Use real-time sentiment data if available (higher priority)
  if (realtimeSentimentData) {
    // Composite sentiment from real-time data (35% weight)
    if (
      realtimeSentimentData.composite_sentiment !== null &&
      realtimeSentimentData.composite_sentiment !== undefined
    ) {
      const compositeSentiment = parseFloat(
        realtimeSentimentData.composite_sentiment
      );
      const compositeScore = (compositeSentiment + 1) / 2; // Convert from -1,1 to 0,1
      score += compositeScore * 0.35;
      components++;
    }

    // News sentiment with FinBERT (25% weight)
    if (
      realtimeSentimentData.news_sentiment_score !== null &&
      realtimeSentimentData.news_sentiment_score !== undefined
    ) {
      const newsSentiment = parseFloat(
        realtimeSentimentData.news_sentiment_score
      );
      const newsScore = (newsSentiment + 1) / 2;
      score += newsScore * 0.25;
      components++;
    }

    // Social media sentiment (20% weight)
    if (
      realtimeSentimentData.social_sentiment_score !== null &&
      realtimeSentimentData.social_sentiment_score !== undefined
    ) {
      const socialSentiment = parseFloat(
        realtimeSentimentData.social_sentiment_score
      );
      const socialScore = (socialSentiment + 1) / 2;
      score += socialScore * 0.2;
      components++;
    }

    // Analyst momentum (15% weight)
    if (
      realtimeSentimentData.analyst_momentum !== null &&
      realtimeSentimentData.analyst_momentum !== undefined
    ) {
      const analystMomentum = parseFloat(
        realtimeSentimentData.analyst_momentum
      );
      const analystScore = (analystMomentum + 1) / 2;
      score += analystScore * 0.15;
      components++;
    }

    // Viral score and volume (5% weight)
    if (
      realtimeSentimentData.viral_score !== null &&
      realtimeSentimentData.viral_score !== undefined
    ) {
      const viralScore = parseFloat(realtimeSentimentData.viral_score);
      const viralNormalized = Math.min(viralScore / 10, 1); // Normalize viral score
      score += viralNormalized * 0.05;
      components++;
    }
  }

  // Fallback to legacy sentiment data if real-time not available
  if (components === 0 && sentimentData) {
    return calculateSentimentScore(sentimentData);
  }

  // Normalize if fewer components
  if (components > 0 && components < 5) {
    score = 0.5 + (score - 0.5) * (5 / components);
  }

  return Math.min(Math.max(score, 0), 1);
}

// Keep original sentiment function for fallback
function calculateSentimentScore(sentimentData) {
  let score = 0.5; // Base score
  let components = 0;

  if (sentimentData) {
    // Analyst recommendations (30% weight)
    if (sentimentData.total_analysts > 0) {
      const buyRatio =
        (sentimentData.strong_buy_count + sentimentData.buy_count) /
        sentimentData.total_analysts;
      score += buyRatio * 0.3;
      components++;
    }

    // Price target vs current (25% weight)
    if (
      sentimentData.price_target_vs_current !== null &&
      sentimentData.price_target_vs_current !== undefined
    ) {
      const targetUpside = parseFloat(sentimentData.price_target_vs_current);
      // Positive upside is good, but cap at 50% upside for scoring
      const targetScore =
        Math.min(Math.max(targetUpside, -0.2), 0.5) / 0.7 + 2 / 7; // Normalize to 0-1
      score += targetScore * 0.25;
      components++;
    }

    // News sentiment (20% weight)
    if (
      sentimentData.news_sentiment_score !== null &&
      sentimentData.news_sentiment_score !== undefined
    ) {
      const newsSentiment = parseFloat(sentimentData.news_sentiment_score);
      // Convert from -1,1 to 0,1 scale
      const newsScore = (newsSentiment + 1) / 2;
      score += newsScore * 0.2;
      components++;
    }

    // Reddit/Social sentiment (15% weight)
    if (
      sentimentData.reddit_sentiment_score !== null &&
      sentimentData.reddit_sentiment_score !== undefined
    ) {
      const socialSentiment = parseFloat(sentimentData.reddit_sentiment_score);
      const socialScore = (socialSentiment + 1) / 2;
      score += socialScore * 0.15;
      components++;
    }

    // Search interest trend (10% weight)
    if (
      sentimentData.search_trend_30d !== null &&
      sentimentData.search_trend_30d !== undefined
    ) {
      const searchTrend = parseFloat(sentimentData.search_trend_30d);
      // Positive search trend indicates growing interest
      const searchScore = Math.min(Math.max(searchTrend + 0.5, 0), 1);
      score += searchScore * 0.1;
      components++;
    }
  }

  // Normalize if fewer components
  if (components > 0 && components < 5) {
    score = 0.5 + (score - 0.5) * (5 / components);
  }

  return Math.min(Math.max(score, 0), 1);
}

function calculatePositioningScore(basicInfo, technicalData) {
  let score = 0.5; // Base score
  let components = 0;

  if (basicInfo) {
    // Institutional ownership (25% weight)
    if (
      basicInfo.held_percent_institutions !== null &&
      basicInfo.held_percent_institutions !== undefined
    ) {
      const instOwnership = parseFloat(basicInfo.held_percent_institutions);
      // Sweet spot 40-80%
      const instScore =
        instOwnership >= 0.4 && instOwnership <= 0.8
          ? 1.0
          : instOwnership > 0.8
            ? Math.max(0, 1 - (instOwnership - 0.8) * 5)
            : instOwnership / 0.4;
      score += instScore * 0.25;
      components++;
    }

    // Short interest (20% weight)
    if (
      basicInfo.short_percent_outstanding !== null &&
      basicInfo.short_percent_outstanding !== undefined
    ) {
      const shortPercent = parseFloat(basicInfo.short_percent_outstanding);
      // Lower short interest is generally better
      const shortScore = Math.max(0, 1 - shortPercent / 0.2); // 20% short = score 0
      score += shortScore * 0.2;
      components++;
    }
  }

  if (technicalData) {
    // Distance from 52-week high (20% weight)
    if (technicalData.high_52w && technicalData.price) {
      const distanceFromHigh =
        (parseFloat(technicalData.price) - parseFloat(technicalData.high_52w)) /
        parseFloat(technicalData.high_52w);
      // Being near highs is positive positioning
      const highScore = Math.max(0, 1 + distanceFromHigh * 2); // Within 50% of high = good score
      score += Math.min(highScore, 1) * 0.2;
      components++;
    }

    // Price vs SMA 200 (20% weight)
    if (
      technicalData.price_vs_sma_200 !== null &&
      technicalData.price_vs_sma_200 !== undefined
    ) {
      const priceVsSma200 = parseFloat(technicalData.price_vs_sma_200);
      // Being above long-term trend is good positioning
      const sma200Score =
        priceVsSma200 > 0 ? Math.min(1, priceVsSma200 * 3) : 0;
      score += sma200Score * 0.2;
      components++;
    }

    // Volatility positioning (15% weight)
    if (
      technicalData.historical_volatility_20d !== null &&
      technicalData.historical_volatility_20d !== undefined
    ) {
      const volatility = parseFloat(technicalData.historical_volatility_20d);
      // Moderate volatility (15-25%) is ideal for positioning
      const volScore =
        volatility >= 0.15 && volatility <= 0.25
          ? 1.0
          : volatility > 0.25
            ? Math.max(0, 1 - (volatility - 0.25) * 4)
            : volatility / 0.15;
      score += volScore * 0.15;
      components++;
    }
  }

  // Normalize if fewer components
  if (components > 0 && components < 5) {
    score = 0.5 + (score - 0.5) * (5 / components);
  }

  return Math.min(Math.max(score, 0), 1);
}

function calculateEnhancedPositioningScore(
  basicInfo,
  technicalData,
  positioningData
) {
  let score = 0.5; // Base score
  let components = 0;

  // Use advanced positioning data if available
  if (positioningData) {
    // Institutional holdings analysis (25% weight)
    if (
      positioningData.institutional_ownership_change !== null &&
      positioningData.institutional_ownership_change !== undefined
    ) {
      const instChange = parseFloat(
        positioningData.institutional_ownership_change
      );
      // Positive institutional change is good, normalize around 10% change
      const instChangeScore = Math.min(
        Math.max((instChange + 0.1) / 0.2, 0),
        1
      );
      score += instChangeScore * 0.25;
      components++;
    }

    // Smart money positioning (20% weight)
    if (
      positioningData.smart_money_score !== null &&
      positioningData.smart_money_score !== undefined
    ) {
      const smartMoney = parseFloat(positioningData.smart_money_score);
      // Smart money score should already be normalized 0-1
      score += smartMoney * 0.2;
      components++;
    }

    // Insider trading sentiment (20% weight)
    if (
      positioningData.insider_sentiment_score !== null &&
      positioningData.insider_sentiment_score !== undefined
    ) {
      const insiderSentiment = parseFloat(
        positioningData.insider_sentiment_score
      );
      // Convert from -1,1 to 0,1 scale
      const insiderScore = (insiderSentiment + 1) / 2;
      score += insiderScore * 0.2;
      components++;
    }

    // Short squeeze potential (10% weight)
    if (
      positioningData.short_squeeze_potential !== null &&
      positioningData.short_squeeze_potential !== undefined
    ) {
      const squeezePotential = parseFloat(
        positioningData.short_squeeze_potential
      );
      // Already normalized 0-1 score
      score += squeezePotential * 0.1;
      components++;
    }

    // Positioning momentum (10% weight)
    if (
      positioningData.positioning_momentum !== null &&
      positioningData.positioning_momentum !== undefined
    ) {
      const posMomentum = parseFloat(positioningData.positioning_momentum);
      // Convert from -1,1 to 0,1 scale
      const posMomentumScore = (posMomentum + 1) / 2;
      score += posMomentumScore * 0.1;
      components++;
    }
  }

  // Fallback to basic positioning data if no advanced data available
  if (components === 0) {
    return calculatePositioningScore(basicInfo, technicalData);
  }

  // Normalize if fewer components
  if (components > 0 && components < 6) {
    score = 0.5 + (score - 0.5) * (6 / components);
  }

  return Math.min(Math.max(score, 0), 1);
}

function calculateCompositeScore(scores) {
  // Weighted composite score
  const weights = {
    quality: 0.25, // Fundamental strength
    growth: 0.2, // Growth potential
    value: 0.2, // Valuation attractiveness
    momentum: 0.15, // Technical momentum
    sentiment: 0.1, // Market sentiment
    positioning: 0.1, // Smart money positioning
  };

  let compositeScore = 0;
  let totalWeight = 0;

  Object.keys(weights).forEach((key) => {
    if (
      scores[key] !== null &&
      scores[key] !== undefined &&
      !isNaN(scores[key])
    ) {
      compositeScore += scores[key] * weights[key];
      totalWeight += weights[key];
    }
  });

  // Normalize if we're missing some components
  if (totalWeight > 0 && totalWeight < 1) {
    compositeScore = compositeScore / totalWeight;
  }

  return Math.min(Math.max(compositeScore, 0), 1);
}

// Data retrieval functions
async function getBasicInfo(symbol) {
  try {
    const result = await query(
      `
      SELECT * FROM stock_symbols_enhanced 
      WHERE symbol = $1
    `,
      [symbol]
    );
    return result.length > 0 ? result[0] : null;
  } catch (error) {
    console.error(`Error getting basic info for ${symbol}:`, error);
    return null;
  }
}

async function getFinancialMetrics(symbol) {
  try {
    // Get latest financial metrics from all tables
    const [profitability, balanceSheet, valuation, growth] = await Promise.all([
      query(
        `SELECT * FROM profitability_metrics WHERE symbol = $1 ORDER BY date DESC LIMIT 1`,
        [symbol]
      ),
      query(
        `SELECT * FROM balance_sheet_metrics WHERE symbol = $1 ORDER BY date DESC LIMIT 1`,
        [symbol]
      ),
      query(
        `SELECT * FROM valuation_metrics WHERE symbol = $1 ORDER BY date DESC LIMIT 1`,
        [symbol]
      ),
      query(
        `SELECT * FROM growth_metrics WHERE symbol = $1 ORDER BY date DESC LIMIT 1`,
        [symbol]
      ),
    ]);

    // Combine all financial data
    const combined = {};
    if (profitability.length > 0) Object.assign(combined, profitability[0]);
    if (balanceSheet.length > 0) Object.assign(combined, balanceSheet[0]);
    if (valuation.length > 0) Object.assign(combined, valuation[0]);
    if (growth.length > 0) Object.assign(combined, growth[0]);

    return Object.keys(combined).length > 0 ? combined : null;
  } catch (error) {
    console.error(`Error getting financial metrics for ${symbol}:`, error);
    return null;
  }
}

async function getMomentumMetrics(symbol) {
  try {
    const result = await query(
      `
      SELECT * FROM momentum_metrics 
      WHERE symbol = $1 
      ORDER BY date DESC 
      LIMIT 1
    `,
      [symbol]
    );
    return result.length > 0 ? result[0] : null;
  } catch (error) {
    console.error(`Error getting momentum metrics for ${symbol}:`, error);
    return null;
  }
}

async function getPositioningMetrics(symbol) {
  try {
    const result = await query(
      `
      SELECT * FROM positioning_metrics 
      WHERE symbol = $1 
      ORDER BY date DESC 
      LIMIT 1
    `,
      [symbol]
    );
    return result.length > 0 ? result[0] : null;
  } catch (error) {
    console.error(`Error getting positioning metrics for ${symbol}:`, error);
    return null;
  }
}

async function getRealtimeSentimentData(symbol) {
  try {
    const result = await query(
      `
      SELECT * FROM realtime_sentiment_analysis 
      WHERE symbol = $1 
      ORDER BY date DESC 
      LIMIT 1
    `,
      [symbol]
    );
    return result.length > 0 ? result[0] : null;
  } catch (error) {
    console.error(`Error getting realtime sentiment for ${symbol}:`, error);
    return null;
  }
}

async function getTechnicalIndicators(symbol) {
  try {
    const result = await query(
      `
      SELECT * FROM technical_indicators 
      WHERE symbol = $1 
      ORDER BY date DESC 
      LIMIT 1
    `,
      [symbol]
    );
    return result.length > 0 ? result[0] : null;
  } catch (error) {
    console.error(`Error getting technical indicators for ${symbol}:`, error);
    return null;
  }
}

async function getSentimentData(symbol) {
  try {
    const [analyst, social] = await Promise.all([
      query(
        `SELECT * FROM analyst_sentiment_analysis WHERE symbol = $1 ORDER BY date DESC LIMIT 1`,
        [symbol]
      ),
      query(
        `SELECT * FROM social_sentiment_analysis WHERE symbol = $1 ORDER BY date DESC LIMIT 1`,
        [symbol]
      ),
    ]);

    const combined = {};
    if (analyst.length > 0) Object.assign(combined, analyst[0]);
    if (social.length > 0) Object.assign(combined, social[0]);

    return Object.keys(combined).length > 0 ? combined : null;
  } catch (error) {
    console.error(`Error getting sentiment data for ${symbol}:`, error);
    return null;
  }
}

function assessDataQuality(
  basicInfo,
  financialData,
  technicalData,
  sentimentData,
  momentumData,
  positioningData,
  realtimeSentimentData
) {
  let qualityScore = 0;
  let maxScore = 7;

  if (basicInfo) qualityScore += 1;
  if (financialData && Object.keys(financialData).length > 5) qualityScore += 1;
  if (technicalData && Object.keys(technicalData).length > 10)
    qualityScore += 1;
  if (sentimentData && Object.keys(sentimentData).length > 3) qualityScore += 1;
  if (momentumData && Object.keys(momentumData).length > 5) qualityScore += 1;
  if (positioningData && Object.keys(positioningData).length > 5)
    qualityScore += 1;
  if (realtimeSentimentData && Object.keys(realtimeSentimentData).length > 5)
    qualityScore += 1;

  return (qualityScore / maxScore) * 100;
}

async function storeComprehensiveScores(symbol, scores) {
  try {
    await query(
      `
      INSERT INTO comprehensive_scores (
        symbol, quality_score, growth_score, value_score, momentum_score,
        sentiment_score, positioning_score, composite_score, 
        calculation_date, data_quality, created_at, updated_at
      ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW(), NOW())
      ON CONFLICT (symbol, calculation_date) DO UPDATE SET
        quality_score = EXCLUDED.quality_score,
        growth_score = EXCLUDED.growth_score,
        value_score = EXCLUDED.value_score,
        momentum_score = EXCLUDED.momentum_score,
        sentiment_score = EXCLUDED.sentiment_score,
        positioning_score = EXCLUDED.positioning_score,
        composite_score = EXCLUDED.composite_score,
        data_quality = EXCLUDED.data_quality,
        updated_at = NOW()
    `,
      [
        symbol,
        scores.quality_score,
        scores.growth_score,
        scores.value_score,
        scores.momentum_score,
        scores.sentiment_score,
        scores.positioning_score,
        scores.composite_score,
        scores.calculation_date,
        scores.data_quality,
      ]
    );
  } catch (error) {
    console.error(`Error storing scores for ${symbol}:`, error);
    throw error;
  }
}

module.exports = router;

/**
 * Scoring Helpers for Comprehensive Stock Scoring
 */

const { query } = require("./database");
const _logger = require("./logger");

/**
 * Calculate comprehensive scores for a stock
 * @param {string} symbol - Stock symbol
 * @returns {Object|null} - Comprehensive scores or null if insufficient data
 */
async function calculateComprehensiveScores(symbol) {
  try {
    // Get all necessary data for scoring
    const [basicInfo, financialData, technicalData, sentimentData, positioningData] =
      await Promise.all([
        getBasicInfo(symbol),
        getFinancialMetrics(symbol),
        getTechnicalIndicators(symbol),
        getSentimentData(symbol),
        getPositioningData(symbol),
      ]);

    if (!basicInfo) {
      console.log(`No basic info found for ${symbol}`);
      return null;
    }

    // Calculate each component score
    const qualityScore = calculateQualityScore(basicInfo, financialData);
    const growthScore = calculateGrowthScore(basicInfo, financialData);
    const valueScore = calculateValueScore(basicInfo, financialData);
    const momentumScore = calculateMomentumScore(basicInfo, technicalData);
    const sentimentScore = calculateSentimentScore(sentimentData);
    const positioningScore = calculatePositioningScore(positioningData);

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
        sentimentData
      ),
    };
  } catch (error) {
    console.error(`Error calculating scores for ${symbol}:`, error);
    return null;
  }
}

/**
 * Store comprehensive scores in the database
 * @param {string} symbol - Stock symbol
 * @param {Object} scores - Comprehensive scores object
 */
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

// Helper functions for data retrieval
async function getBasicInfo(symbol) {
  try {
    const result = await query(
      `SELECT symbol, security_name as company_name, exchange FROM stock_symbols WHERE symbol = $1`,
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
    // Try to get financial data from multiple tables
    const profitability = await query(
      `SELECT * FROM profitability_metrics WHERE symbol = $1 ORDER BY date DESC LIMIT 1`,
      [symbol]
    );

    const combined = {};
    if (profitability.length > 0) {
      Object.assign(combined, profitability[0]);
    }

    return Object.keys(combined).length > 0 ? combined : null;
  } catch (error) {
    console.error(`Error getting financial metrics for ${symbol}:`, error);
    return null;
  }
}

async function getTechnicalIndicators(symbol) {
  try {
    const result = await query(
      `SELECT * FROM technical_data_daily WHERE symbol = $1 ORDER BY date DESC LIMIT 1`,
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
    const result = await query(
      `SELECT * FROM sentiment_analysis WHERE symbol = $1 ORDER BY date DESC LIMIT 1`,
      [symbol]
    );
    return result.length > 0 ? result[0] : null;
  } catch (error) {
    console.error(`Error getting sentiment data for ${symbol}:`, error);
    return null;
  }
}

async function getPositioningData(symbol) {
  try {
    const [metrics, institutional, insiderTxns] = await Promise.all([
      query(
        `SELECT * FROM positioning_metrics WHERE symbol = $1 ORDER BY date DESC LIMIT 1`,
        [symbol]
      ),
      query(
        `SELECT institution_type, position_change_percent
         FROM institutional_positioning
         WHERE symbol = $1
         ORDER BY filing_date DESC
         LIMIT 20`,
        [symbol]
      ),
      query(
        `SELECT transaction_type, value, transaction_date
         FROM insider_transactions
         WHERE symbol = $1
         AND transaction_date >= CURRENT_DATE - INTERVAL '3 months'
         ORDER BY transaction_date DESC`,
        [symbol]
      ),
    ]);

    return {
      metrics: metrics.length > 0 ? metrics[0] : null,
      institutional: institutional || [],
      insiderTxns: insiderTxns || [],
    };
  } catch (error) {
    console.error(`Error getting positioning data for ${symbol}:`, error);
    return { metrics: null, institutional: [], insiderTxns: [] };
  }
}

// Individual scoring components
function calculateQualityScore(basicInfo, financialData) {
  let score = 0.5; // Base score
  let components = 0;

  if (financialData) {
    // ROE component
    if (financialData.roe !== null && financialData.roe !== undefined) {
      const roe = parseFloat(financialData.roe);
      score += (Math.min(Math.max(roe, 0), 0.3) / 0.3) * 0.3;
      components++;
    }

    // ROA component
    if (financialData.roa !== null && financialData.roa !== undefined) {
      const roa = parseFloat(financialData.roa);
      score += (Math.min(Math.max(roa, 0), 0.2) / 0.2) * 0.2;
      components++;
    }
  }

  // Normalize if fewer components
  if (components > 0 && components < 2) {
    score = 0.5 + (score - 0.5) * (2 / components);
  }

  return Math.min(Math.max(score, 0), 1);
}

function calculateGrowthScore(basicInfo, financialData) {
  let score = 0.5; // Base score
  let components = 0;

  if (financialData) {
    // Revenue growth
    if (
      financialData.revenue_growth_1y !== null &&
      financialData.revenue_growth_1y !== undefined
    ) {
      const growth = parseFloat(financialData.revenue_growth_1y);
      const growthScore = 0.5 + growth / 0.4; // 40% growth = max score
      score += Math.min(Math.max(growthScore, 0), 1) * 0.5;
      components++;
    }
  }

  // Normalize if fewer components
  if (components > 0 && components < 1) {
    score = 0.5 + (score - 0.5) * (1 / components);
  }

  return Math.min(Math.max(score, 0), 1);
}

function calculateValueScore(basicInfo, financialData) {
  let score = 0.5; // Base score
  let components = 0;

  if (financialData) {
    // P/E ratio
    if (
      financialData.trailing_pe !== null &&
      financialData.trailing_pe !== undefined
    ) {
      const pe = parseFloat(financialData.trailing_pe);
      if (pe > 0 && pe < 100) {
        const peScore = Math.max(0, 1 - (pe - 10) / 20);
        score += peScore * 0.4;
        components++;
      }
    }
  }

  // Normalize if fewer components
  if (components > 0 && components < 1) {
    score = 0.5 + (score - 0.5) * (1 / components);
  }

  return Math.min(Math.max(score, 0), 1);
}

function calculateMomentumScore(basicInfo, technicalData) {
  let score = 0.5; // Base score
  let components = 0;

  if (technicalData) {
    // RSI component
    if (technicalData.rsi_14 !== null && technicalData.rsi_14 !== undefined) {
      const rsi = parseFloat(technicalData.rsi_14);
      const rsiScore =
        rsi >= 50 && rsi <= 70
          ? 1.0
          : rsi > 70
            ? Math.max(0, 1 - (rsi - 70) / 20)
            : Math.max(0, rsi / 50);
      score += rsiScore * 0.3;
      components++;
    }
  }

  // Normalize if fewer components
  if (components > 0 && components < 1) {
    score = 0.5 + (score - 0.5) * (1 / components);
  }

  return Math.min(Math.max(score, 0), 1);
}

function calculateSentimentScore(sentimentData) {
  let score = 0.5; // Base score

  if (sentimentData) {
    // Simple sentiment scoring
    if (
      sentimentData.sentiment_score !== null &&
      sentimentData.sentiment_score !== undefined
    ) {
      const sentiment = parseFloat(sentimentData.sentiment_score);
      score = (sentiment + 1) / 2; // Convert from -1,1 to 0,1
    }
  }

  return Math.min(Math.max(score, 0), 1);
}

function calculatePositioningScore(positioningData) {
  let rawScore = 50; // Start neutral (0-100 scale)

  if (!positioningData || !positioningData.metrics) {
    return 0.5; // Return neutral if no data
  }

  const metrics = positioningData.metrics;
  const institutional = positioningData.institutional || [];
  const insiderTxns = positioningData.insiderTxns || [];

  // 1. Institutional Quality Score (0-25 points)
  const instOwn = parseFloat(metrics.institutional_ownership || 0);
  const instCount = parseInt(metrics.institution_count || 0);

  let instScore = 0;
  if (instOwn > 0.7) instScore += 15;
  else if (instOwn > 0.5) instScore += 10;
  else if (instOwn > 0.3) instScore += 5;
  else if (instOwn < 0.2) instScore -= 5;

  if (instCount > 500) instScore += 10;
  else if (instCount > 200) instScore += 7;
  else if (instCount > 100) instScore += 5;
  else if (instCount > 50) instScore += 3;

  rawScore += Math.min(25, instScore);

  // 2. Insider Conviction Score (0-25 points)
  const insiderOwn = parseFloat(metrics.insider_ownership || 0);

  let insiderScore = 0;
  if (insiderOwn > 0.15) insiderScore += 10;
  else if (insiderOwn > 0.1) insiderScore += 7;
  else if (insiderOwn > 0.05) insiderScore += 5;
  else if (insiderOwn > 0.02) insiderScore += 3;

  // Recent insider buying activity
  const buys = insiderTxns.filter(t =>
    t.transaction_type?.toLowerCase().includes('buy') ||
    t.transaction_type?.toLowerCase().includes('purchase')
  );
  const sells = insiderTxns.filter(t =>
    t.transaction_type?.toLowerCase().includes('sell') ||
    t.transaction_type?.toLowerCase().includes('sale')
  );

  const buyValue = buys.reduce((sum, t) => sum + (parseFloat(t.value) || 0), 0);
  const sellValue = sells.reduce((sum, t) => sum + (parseFloat(t.value) || 0), 0);

  if (buyValue > sellValue * 2) insiderScore += 15;
  else if (buyValue > sellValue) insiderScore += 10;
  else if (sellValue > buyValue * 2) insiderScore -= 10;
  else if (sellValue > buyValue) insiderScore -= 5;

  rawScore += Math.min(25, Math.max(-10, insiderScore));

  // 3. Short Interest Score (0-25 points)
  const shortPct = parseFloat(metrics.short_percent_of_float || 0);
  const shortChange = parseFloat(metrics.short_interest_change || 0);

  let shortScore = 0;
  if (shortPct > 0.3) shortScore -= 15;
  else if (shortPct > 0.2) shortScore -= 10;
  else if (shortPct > 0.1) shortScore -= 5;
  else if (shortPct < 0.02) shortScore += 10;

  if (shortChange < -0.15) shortScore += 15;
  else if (shortChange < -0.1) shortScore += 10;
  else if (shortChange < -0.05) shortScore += 5;
  else if (shortChange > 0.15) shortScore -= 15;
  else if (shortChange > 0.1) shortScore -= 10;
  else if (shortChange > 0.05) shortScore -= 5;

  rawScore += Math.min(25, Math.max(-20, shortScore));

  // 4. Smart Money Flow Score (0-25 points)
  let smartMoneyScore = 0;

  const mutualFunds = institutional.filter(i => i.institution_type === 'MUTUAL_FUND');
  const hedgeFunds = institutional.filter(i => i.institution_type === 'HEDGE_FUND');

  const mfAccumulating = mutualFunds.filter(mf => (parseFloat(mf.position_change_percent) || 0) > 5).length;
  const mfDistributing = mutualFunds.filter(mf => (parseFloat(mf.position_change_percent) || 0) < -5).length;

  if (mfAccumulating > mfDistributing * 2) smartMoneyScore += 10;
  else if (mfAccumulating > mfDistributing) smartMoneyScore += 5;
  else if (mfDistributing > mfAccumulating * 2) smartMoneyScore -= 10;
  else if (mfDistributing > mfAccumulating) smartMoneyScore -= 5;

  const hfAccumulating = hedgeFunds.filter(hf => (parseFloat(hf.position_change_percent) || 0) > 5).length;
  const hfDistributing = hedgeFunds.filter(hf => (parseFloat(hf.position_change_percent) || 0) < -5).length;

  if (hfAccumulating > hfDistributing * 2) smartMoneyScore += 15;
  else if (hfAccumulating > hfDistributing) smartMoneyScore += 10;
  else if (hfDistributing > hfAccumulating * 2) smartMoneyScore -= 15;
  else if (hfDistributing > hfAccumulating) smartMoneyScore -= 10;

  rawScore += Math.min(25, Math.max(-15, smartMoneyScore));

  // Convert from 0-100 scale to 0-1 scale
  const finalScore = Math.max(0, Math.min(100, rawScore)) / 100;
  return finalScore;
}

function calculateCompositeScore(scores) {
  const weights = {
    quality: 0.278,      // 27.8% (was 25%, gained 2.8% from sentiment)
    growth: 0.222,       // 22.2% (was 20%, gained 2.2% from sentiment)
    value: 0.222,        // 22.2% (was 20%, gained 2.2% from sentiment)
    momentum: 0.167,     // 16.7% (was 15%, gained 1.7% from sentiment)
    positioning: 0.111,  // 11.1% (was 10%, gained 1.1% from sentiment)
    // sentiment removed - was 10%
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

function assessDataQuality(
  basicInfo,
  financialData,
  technicalData,
  sentimentData
) {
  let qualityScore = 0;
  let maxScore = 4;

  if (basicInfo) qualityScore += 1;
  if (financialData && Object.keys(financialData).length > 2) qualityScore += 1;
  if (technicalData && Object.keys(technicalData).length > 5) qualityScore += 1;
  if (sentimentData && Object.keys(sentimentData).length > 2) qualityScore += 1;

  return (qualityScore / maxScore) * 100;
}

module.exports = {
  calculateComprehensiveScores,
  storeComprehensiveScores,
};

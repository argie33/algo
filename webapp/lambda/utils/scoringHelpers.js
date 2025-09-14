/**
 * Scoring Helpers for Comprehensive Stock Scoring
 */

const { query } = require('./database');
const _logger = require('./logger');

/**
 * Calculate comprehensive scores for a stock
 * @param {string} symbol - Stock symbol
 * @returns {Object|null} - Comprehensive scores or null if insufficient data
 */
async function calculateComprehensiveScores(symbol) {
  try {
    // Get all necessary data for scoring
    const [
      basicInfo,
      financialData,
      technicalData,
      sentimentData,
    ] = await Promise.all([
      getBasicInfo(symbol),
      getFinancialMetrics(symbol),
      getTechnicalIndicators(symbol),
      getSentimentData(symbol),
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
    const positioningScore = calculatePositioningScore(basicInfo, technicalData);

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
      data_quality: assessDataQuality(basicInfo, financialData, technicalData, sentimentData),
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
    if (financialData.revenue_growth_1y !== null && financialData.revenue_growth_1y !== undefined) {
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
    if (financialData.trailing_pe !== null && financialData.trailing_pe !== undefined) {
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
      const rsiScore = rsi >= 50 && rsi <= 70 ? 1.0 : rsi > 70 ? Math.max(0, 1 - (rsi - 70) / 20) : Math.max(0, rsi / 50);
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
    if (sentimentData.sentiment_score !== null && sentimentData.sentiment_score !== undefined) {
      const sentiment = parseFloat(sentimentData.sentiment_score);
      score = (sentiment + 1) / 2; // Convert from -1,1 to 0,1
    }
  }

  return Math.min(Math.max(score, 0), 1);
}

function calculatePositioningScore(basicInfo, technicalData) {
  let score = 0.5; // Base score
  
  // Simple positioning calculation
  if (technicalData) {
    if (technicalData.price_vs_sma_200 !== null && technicalData.price_vs_sma_200 !== undefined) {
      const priceVsSma200 = parseFloat(technicalData.price_vs_sma_200);
      score = priceVsSma200 > 0 ? Math.min(1, 0.5 + priceVsSma200 * 2) : 0.3;
    }
  }

  return Math.min(Math.max(score, 0), 1);
}

function calculateCompositeScore(scores) {
  const weights = {
    quality: 0.25,
    growth: 0.2,
    value: 0.2,
    momentum: 0.15,
    sentiment: 0.1,
    positioning: 0.1,
  };

  let compositeScore = 0;
  let totalWeight = 0;

  Object.keys(weights).forEach((key) => {
    if (scores[key] !== null && scores[key] !== undefined && !isNaN(scores[key])) {
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

function assessDataQuality(basicInfo, financialData, technicalData, sentimentData) {
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
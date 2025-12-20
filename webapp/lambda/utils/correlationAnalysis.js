/**
 * Correlation Analysis for Portfolio Holdings
 * Calculates correlations between stock movements
 */

const { query } = require("./database");

/**
 * Calculate simple correlation between two arrays
 */
function calculateSimpleCorrelation(returns1, returns2) {
  if (returns1.length !== returns2.length || returns1.length < 2) {
    return null;
  }

  const n = returns1.length;
  const mean1 = returns1.reduce((a, b) => a + b) / n;
  const mean2 = returns2.reduce((a, b) => a + b) / n;

  let covariance = 0;
  let variance1 = 0;
  let variance2 = 0;

  for (let i = 0; i < n; i++) {
    const diff1 = returns1[i] - mean1;
    const diff2 = returns2[i] - mean2;
    covariance += diff1 * diff2;
    variance1 += diff1 * diff1;
    variance2 += diff2 * diff2;
  }

  covariance /= n;
  variance1 /= n;
  variance2 /= n;

  if (variance1 === 0 || variance2 === 0) {
    return null;
  }

  const correlation = covariance / Math.sqrt(variance1 * variance2);
  return Math.max(-1, Math.min(1, correlation)); // Clamp to [-1, 1]
}

/**
 * Get historical returns for a stock
 */
async function getStockReturns(symbol, days = 60) {
  try {
    const result = await query(
      `SELECT date, close FROM price_daily
       WHERE symbol = $1
       ORDER BY date DESC
       LIMIT $2`,
      [symbol, days]
    );

    if (!result.rows || result.rows.length < 2) {
      return null;
    }

    const prices = result.rows.reverse();
    const returns = [];

    for (let i = 1; i < prices.length; i++) {
      const prevClose = parseFloat(prices[i - 1].close);
      const currClose = parseFloat(prices[i].close);

      if (prevClose > 0) {
        const dailyReturn = (currClose - prevClose) / prevClose;
        returns.push(dailyReturn);
      }
    }

    return returns.length > 0 ? returns : null;
  } catch (error) {
    console.error(`Error getting returns for ${symbol}:`, error.message);
    return null;
  }
}

/**
 * Calculate correlation matrix for portfolio holdings
 */
async function calculateCorrelationMatrix(symbols) {
  try {
    if (!symbols || symbols.length < 2) {
      return { success: false, error: "Need at least 2 symbols" };
    }

    console.log(`📊 Calculating correlation matrix for ${symbols.length} symbols...`);

    // Get returns for all symbols
    const returnsMap = {};
    for (const symbol of symbols) {
      const returns = await getStockReturns(symbol, 60);
      if (returns) {
        returnsMap[symbol] = returns;
      }
    }

    // Filter to only symbols with valid return data
    const validSymbols = Object.keys(returnsMap);
    if (validSymbols.length < 2) {
      return {
        success: false,
        error: "Not enough symbols with valid historical data",
      };
    }

    // Build correlation matrix
    const matrix = {};
    const correlations = [];

    for (let i = 0; i < validSymbols.length; i++) {
      for (let j = i + 1; j < validSymbols.length; j++) {
        const sym1 = validSymbols[i];
        const sym2 = validSymbols[j];

        const correlation = calculateSimpleCorrelation(
          returnsMap[sym1],
          returnsMap[sym2]
        );

        if (correlation !== null) {
          correlations.push({
            symbol1: sym1,
            symbol2: sym2,
            correlation: parseFloat(correlation.toFixed(3)),
          });

          if (!matrix[sym1]) matrix[sym1] = {};
          if (!matrix[sym2]) matrix[sym2] = {};

          matrix[sym1][sym2] = correlation;
          matrix[sym2][sym1] = correlation;
        }
      }
    }

    // Add self-correlations (always 1.0)
    for (const sym of validSymbols) {
      if (!matrix[sym]) matrix[sym] = {};
      matrix[sym][sym] = 1.0;
    }

    return {
      success: true,
      matrix,
      correlations: correlations.sort(
        (a, b) => Math.abs(b.correlation) - Math.abs(a.correlation)
      ),
      statistics: {
        symbols_analyzed: validSymbols.length,
        total_pairs: correlations.length,
        average_correlation: correlations.length
          ? (correlations.reduce((sum, c) => sum + c.correlation, 0) / correlations.length).toFixed(3)
          : null,
        highest_correlation: correlations.length ? correlations[0] : null,
        lowest_correlation: correlations.length
          ? correlations[correlations.length - 1]
          : null,
      },
    };
  } catch (error) {
    console.error("Error calculating correlation matrix:", error.message);
    return {
      success: false,
      error: error.message,
    };
  }
}

/**
 * Calculate portfolio correlation score
 * (lower correlation = better diversification)
 *
 * DATA INTEGRITY: Returns NULL when correlation data unavailable
 * (not hardcoded "neutral" 50 score)
 */
function calculateDiversificationScore(correlations) {
  if (!correlations || correlations.length === 0) {
    return null; // No correlation data available = unknown diversification
  }

  // Average absolute correlation (0 = perfect diversification, 1 = perfect correlation)
  const avgAbsCorrelation =
    correlations.reduce((sum, c) => sum + Math.abs(c.correlation), 0) /
    correlations.length;

  // Convert to score 0-100 (lower correlation = higher score)
  const diversificationScore = (1 - avgAbsCorrelation) * 100;

  return parseFloat(diversificationScore.toFixed(1));
}

/**
 * Recommend asset to reduce correlation
 * (find asset with lowest average correlation to existing holdings)
 */
function recommendLowCorrelationAsset(correlations, candidateSymbols) {
  if (!correlations || correlations.length === 0 || !candidateSymbols) {
    return null;
  }

  const correlationMap = {};
  correlations.forEach((c) => {
    if (!correlationMap[c.symbol1]) correlationMap[c.symbol1] = [];
    if (!correlationMap[c.symbol2]) correlationMap[c.symbol2] = [];
    correlationMap[c.symbol1].push(c.correlation);
    correlationMap[c.symbol2].push(c.correlation);
  });

  // Find candidate with lowest average absolute correlation
  let bestCandidate = null;
  let lowestAvgCorrelation = Infinity;

  for (const candidate of candidateSymbols) {
    if (correlationMap[candidate]) {
      const avgAbsCorr =
        correlationMap[candidate].reduce((sum, c) => sum + Math.abs(c), 0) /
        correlationMap[candidate].length;

      if (avgAbsCorr < lowestAvgCorrelation) {
        lowestAvgCorrelation = avgAbsCorr;
        bestCandidate = {
          symbol: candidate,
          average_absolute_correlation: parseFloat(
            lowestAvgCorrelation.toFixed(3)
          ),
          diversification_benefit: parseFloat(
            ((1 - lowestAvgCorrelation) * 100).toFixed(1)
          ),
        };
      }
    }
  }

  return bestCandidate;
}

module.exports = {
  calculateSimpleCorrelation,
  getStockReturns,
  calculateCorrelationMatrix,
  calculateDiversificationScore,
  recommendLowCorrelationAsset,
};

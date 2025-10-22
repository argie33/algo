/**
 * Portfolio Analytics Calculation Engine
 * All complex portfolio metrics: Sortino, Calmar, Treynor, Alpha/Beta, Factor Exposure, etc.
 */

/**
 * Calculate Sortino Ratio: Return / Downside Deviation
 * Only penalizes downside volatility, not upside
 */
function calculateSortino(returns, riskFreeRate = 0.02) {
  if (!returns || returns.length < 2) return 0;

  const annualizedReturn = (Math.pow(1 + returns.reduce((a, b) => a + b) / returns.length, 252) - 1);

  // Downside deviation: only negative returns
  const downsideReturns = returns.filter(r => r < 0);
  if (downsideReturns.length === 0) {
    return (annualizedReturn - riskFreeRate) / 0.001; // Avoid division by zero
  }

  const downwardDeviation = Math.sqrt(
    downsideReturns.reduce((sum, r) => sum + Math.pow(r, 2), 0) / downsideReturns.length
  );

  const annualizedDownsideDeviation = downwardDeviation * Math.sqrt(252);

  return (annualizedReturn - riskFreeRate) / annualizedDownsideDeviation;
}

/**
 * Calculate Calmar Ratio: Annual Return / Max Drawdown
 * Measures return relative to worst loss
 */
function calculateCalmar(returns, maxDrawdown) {
  if (!returns || returns.length === 0 || !maxDrawdown || maxDrawdown === 0) return 0;

  const totalReturn = returns.reduce((a, b) => a + b) / returns.length;
  const annualizedReturn = Math.pow(1 + totalReturn, 252) - 1;

  return annualizedReturn / Math.abs(maxDrawdown);
}

/**
 * Calculate Treynor Ratio: (Return - Risk-Free Rate) / Beta
 * Risk-adjusted return per unit of systematic risk
 */
function calculateTreynor(portfolioReturn, beta, riskFreeRate = 0.02) {
  if (!beta || beta === 0) return 0;
  return (portfolioReturn - riskFreeRate) / beta;
}

/**
 * Calculate portfolio Beta
 * Covariance of portfolio returns with market returns / Variance of market returns
 */
function calculateBeta(portfolioReturns, benchmarkReturns) {
  if (!portfolioReturns || !benchmarkReturns || portfolioReturns.length < 2) return 1.0;

  const n = portfolioReturns.length;
  const meanPortfolio = portfolioReturns.reduce((a, b) => a + b) / n;
  const meanBenchmark = benchmarkReturns.reduce((a, b) => a + b) / n;

  // Covariance
  const covariance = portfolioReturns.reduce((sum, r, i) => {
    return sum + (r - meanPortfolio) * (benchmarkReturns[i] - meanBenchmark);
  }, 0) / n;

  // Variance of benchmark
  const benchmarkVariance = benchmarkReturns.reduce((sum, r) => {
    return sum + Math.pow(r - meanBenchmark, 2);
  }, 0) / n;

  if (benchmarkVariance === 0) return 1.0;

  return covariance / benchmarkVariance;
}

/**
 * Calculate Alpha
 * Excess return compared to what CAPM would predict
 * Alpha = Portfolio Return - (Risk-Free Rate + Beta * (Benchmark Return - Risk-Free Rate))
 */
function calculateAlpha(portfolioReturn, benchmarkReturn, beta, riskFreeRate = 0.02) {
  const expectedReturn = riskFreeRate + beta * (benchmarkReturn - riskFreeRate);
  return portfolioReturn - expectedReturn;
}

/**
 * Calculate Information Ratio
 * Active return / Tracking error (std dev of active return)
 */
function calculateInformationRatio(portfolioReturns, benchmarkReturns) {
  if (!portfolioReturns || !benchmarkReturns || portfolioReturns.length < 2) return 0;

  const activeReturns = portfolioReturns.map((r, i) => r - benchmarkReturns[i]);
  const meanActiveReturn = activeReturns.reduce((a, b) => a + b) / activeReturns.length;

  const trackingError = Math.sqrt(
    activeReturns.reduce((sum, r) => sum + Math.pow(r - meanActiveReturn, 2), 0) / activeReturns.length
  );

  if (trackingError === 0) return 0;

  const annualizedMeanActiveReturn = Math.pow(1 + meanActiveReturn, 252) - 1;
  const annualizedTrackingError = trackingError * Math.sqrt(252);

  return annualizedMeanActiveReturn / annualizedTrackingError;
}

/**
 * Calculate Upside/Downside Capture Ratios
 * Measures how much of benchmark's gains/losses you capture
 */
function calculateCaptureRatios(portfolioReturns, benchmarkReturns) {
  if (!portfolioReturns || !benchmarkReturns || portfolioReturns.length < 2) {
    return { upside: 1.0, downside: 1.0 };
  }

  // Upside capture: return in positive benchmark months
  const upsideIndices = benchmarkReturns
    .map((r, i) => r > 0 ? i : null)
    .filter(i => i !== null);

  const upsideCapture = upsideIndices.length > 0
    ? (portfolioReturns.filter((_, i) => upsideIndices.includes(i)).reduce((a, b) => a + b, 0) /
       benchmarkReturns.filter((_, i) => upsideIndices.includes(i)).reduce((a, b) => a + b, 0))
    : 1.0;

  // Downside capture: return in negative benchmark months
  const downsideIndices = benchmarkReturns
    .map((r, i) => r < 0 ? i : null)
    .filter(i => i !== null);

  const downsideCapture = downsideIndices.length > 0
    ? (Math.abs(portfolioReturns.filter((_, i) => downsideIndices.includes(i)).reduce((a, b) => a + b, 0)) /
       Math.abs(benchmarkReturns.filter((_, i) => downsideIndices.includes(i)).reduce((a, b) => a + b, 0)))
    : 1.0;

  return {
    upside: isFinite(upsideCapture) ? upsideCapture : 1.0,
    downside: isFinite(downsideCapture) ? downsideCapture : 1.0
  };
}

/**
 * Calculate Skewness: Measure of distribution asymmetry
 * Negative skew = tail risk on downside
 * Positive skew = tail risk on upside
 */
function calculateSkewness(returns) {
  if (!returns || returns.length < 3) return 0;

  const n = returns.length;
  const mean = returns.reduce((a, b) => a + b) / n;
  const variance = returns.reduce((sum, r) => sum + Math.pow(r - mean, 2), 0) / n;
  const stdev = Math.sqrt(variance);

  if (stdev === 0) return 0;

  const skewness = returns.reduce((sum, r) => sum + Math.pow((r - mean) / stdev, 3), 0) / n;

  return skewness;
}

/**
 * Calculate Kurtosis: Measure of tail risk magnitude
 * Higher kurtosis = fatter tails = more extreme events
 */
function calculateKurtosis(returns) {
  if (!returns || returns.length < 4) return 0;

  const n = returns.length;
  const mean = returns.reduce((a, b) => a + b) / n;
  const variance = returns.reduce((sum, r) => sum + Math.pow(r - mean, 2), 0) / n;
  const stdev = Math.sqrt(variance);

  if (stdev === 0) return 0;

  const kurtosis = returns.reduce((sum, r) => sum + Math.pow((r - mean) / stdev, 4), 0) / n - 3; // Excess kurtosis

  return kurtosis;
}

/**
 * Calculate Conditional VaR (Expected Shortfall)
 * Average loss in worst X% of scenarios
 */
function calculateConditionalVaR(returns, confidenceLevel = 0.95) {
  if (!returns || returns.length < 2) return 0;

  const sortedReturns = [...returns].sort((a, b) => a - b);
  const cutoffIndex = Math.ceil((1 - confidenceLevel) * sortedReturns.length);

  const worstReturns = sortedReturns.slice(0, cutoffIndex);
  const averageWorstReturn = worstReturns.reduce((a, b) => a + b) / worstReturns.length;

  return averageWorstReturn;
}

/**
 * Calculate Herfindahl Index (Concentration)
 * Sum of squares of portfolio weights
 * Range: 0 (perfect diversification) to 1 (single asset)
 */
function calculateHerfindahlIndex(weights) {
  if (!weights || weights.length === 0) return 0;

  return weights.reduce((sum, w) => sum + Math.pow(w, 2), 0);
}

/**
 * Calculate Effective Number of Bets
 * How many "equal-weight" positions would equal current diversification
 */
function calculateEffectiveNumberOfBets(weights) {
  const hhi = calculateHerfindahlIndex(weights);
  if (hhi === 0) return 0;
  return 1 / hhi;
}

/**
 * Calculate Diversification Ratio
 * Average asset volatility / Portfolio volatility
 * >1 means diversification is working (portfolio vol < average asset vol)
 */
function calculateDiversificationRatio(assetVolatilities, portfolioVolatility, weights) {
  if (!assetVolatilities || assetVolatilities.length === 0 || portfolioVolatility === 0) return 1;

  const weightedVolAvg = assetVolatilities.reduce((sum, vol, i) => {
    return sum + (weights[i] || 0) * vol;
  }, 0);

  return weightedVolAvg / portfolioVolatility;
}

/**
 * Calculate rolling returns
 * Returns array of returns calculated over rolling windows
 */
function calculateRollingReturns(prices, window = 30) {
  if (!prices || prices.length <= window) return [];

  const returns = [];
  for (let i = window; i < prices.length; i++) {
    const startPrice = prices[i - window];
    const endPrice = prices[i];
    const return_ = (endPrice - startPrice) / startPrice;
    returns.push(return_);
  }

  return returns;
}

/**
 * Calculate Correlation Matrix
 * Correlation between each pair of assets
 */
function calculateCorrelationMatrix(returns) {
  if (!returns || returns.length === 0) return [];

  const n = returns.length;
  const m = returns[0].length; // number of assets

  const means = [];
  for (let j = 0; j < m; j++) {
    const mean = returns.reduce((sum, r) => sum + (r[j] || 0), 0) / n;
    means.push(mean);
  }

  const correlations = Array(m).fill(0).map(() => Array(m).fill(0));

  for (let i = 0; i < m; i++) {
    for (let j = 0; j < m; j++) {
      if (i === j) {
        correlations[i][j] = 1;
      } else {
        // Covariance
        const cov = returns.reduce((sum, r) => {
          return sum + (r[i] - means[i]) * (r[j] - means[j]);
        }, 0) / n;

        // Standard deviations
        const stdI = Math.sqrt(returns.reduce((sum, r) => sum + Math.pow(r[i] - means[i], 2), 0) / n);
        const stdJ = Math.sqrt(returns.reduce((sum, r) => sum + Math.pow(r[j] - means[j], 2), 0) / n);

        correlations[i][j] = stdI && stdJ ? cov / (stdI * stdJ) : 0;
      }
    }
  }

  return correlations;
}

/**
 * Calculate Risk Decomposition
 * How much each position contributes to total portfolio risk
 */
function calculateRiskDecomposition(weights, covariance) {
  if (!weights || !covariance || covariance.length === 0) return [];

  const n = weights.length;
  const marginalRisks = [];

  // Total portfolio variance
  let portfolioVariance = 0;
  for (let i = 0; i < n; i++) {
    for (let j = 0; j < n; j++) {
      portfolioVariance += weights[i] * weights[j] * covariance[i][j];
    }
  }

  const portfolioStdDev = Math.sqrt(portfolioVariance);

  // Marginal contribution to risk for each asset
  for (let i = 0; i < n; i++) {
    let marginalVariance = 0;
    for (let j = 0; j < n; j++) {
      marginalVariance += weights[j] * covariance[i][j];
    }

    const marginalRisk = (weights[i] * marginalVariance) / (portfolioStdDev || 1);
    marginalRisks.push(marginalRisk);
  }

  // Risk contribution as percentage
  const riskContribution = marginalRisks.map(mr =>
    portfolioStdDev ? (mr / portfolioStdDev) : 0
  );

  return {
    marginalRisks,
    riskContribution,
    percentContribution: riskContribution.map(rc => rc * 100)
  };
}

/**
 * Calculate Max Drawdown
 * Largest peak-to-trough decline
 */
function calculateMaxDrawdown(returns) {
  if (!returns || returns.length < 2) return 0;

  let cumulativeReturn = 1;
  let peak = 1;
  let maxDrawdown = 0;

  for (const ret of returns) {
    cumulativeReturn *= (1 + ret);
    if (cumulativeReturn > peak) {
      peak = cumulativeReturn;
    }
    const drawdown = (cumulativeReturn - peak) / peak;
    if (drawdown < maxDrawdown) {
      maxDrawdown = drawdown;
    }
  }

  return maxDrawdown;
}

/**
 * Calculate Win Rate
 * Percentage of periods with positive returns
 */
function calculateWinRate(returns) {
  if (!returns || returns.length === 0) return 0;

  const wins = returns.filter(r => r > 0).length;
  return (wins / returns.length) * 100;
}

/**
 * Estimate Portfolio Response to Market Scenarios
 * How portfolio would respond to various stress events
 */
function calculateStressScenarioImpact(portfolioWeights, assetBetas, scenarioMarketReturn) {
  if (!portfolioWeights || !assetBetas) return 0;

  // Weighted beta
  const portfolioBeta = portfolioWeights.reduce((sum, w, i) => {
    return sum + w * (assetBetas[i] || 1);
  }, 0);

  // Portfolio return under scenario = Beta * Market Return
  return portfolioBeta * scenarioMarketReturn;
}

/**
 * Calculate Factor Exposure
 * Estimate portfolio's exposure to common factors
 */
function calculateFactorExposure(holdings) {
  if (!holdings || holdings.length === 0) {
    return {
      growth: 0,
      value: 0,
      momentum: 0,
      quality: 0,
      dividend: 0,
      lowVolatility: 0
    };
  }

  // Simplified factor assignment based on characteristics
  // In production, this would use actual factor analysis
  let growth = 0, value = 0, momentum = 0, quality = 0, dividend = 0, lowVol = 0;
  let totalWeight = 0;

  for (const holding of holdings) {
    const weight = (holding.marketValue || holding.currentValue || 0) /
                   (holdings.reduce((sum, h) => sum + (h.marketValue || h.currentValue || 0), 0) || 1);
    totalWeight += weight;

    // Heuristic factor categorization (replace with real factor scores in production)
    if (holding.peRatio > 20) growth += weight * 0.7;
    if (holding.peRatio < 12) value += weight * 0.7;
    if (holding.momentum > 0.5) momentum += weight * 0.6;
    if (holding.grossMargin > 0.4) quality += weight * 0.5;
    if (holding.dividendYield > 0.03) dividend += weight * 0.8;
    if (holding.beta < 0.9) lowVol += weight * 0.6;
  }

  // Normalize to percentages
  return {
    growth: Math.min(growth / totalWeight, 1),
    value: Math.min(value / totalWeight, 1),
    momentum: Math.min(momentum / totalWeight, 1),
    quality: Math.min(quality / totalWeight, 1),
    dividend: Math.min(dividend / totalWeight, 1),
    lowVolatility: Math.min(lowVol / totalWeight, 1)
  };
}

module.exports = {
  calculateSortino,
  calculateCalmar,
  calculateTreynor,
  calculateBeta,
  calculateAlpha,
  calculateInformationRatio,
  calculateCaptureRatios,
  calculateSkewness,
  calculateKurtosis,
  calculateConditionalVaR,
  calculateHerfindahlIndex,
  calculateEffectiveNumberOfBets,
  calculateDiversificationRatio,
  calculateRollingReturns,
  calculateCorrelationMatrix,
  calculateRiskDecomposition,
  calculateMaxDrawdown,
  calculateWinRate,
  calculateStressScenarioImpact,
  calculateFactorExposure,
};

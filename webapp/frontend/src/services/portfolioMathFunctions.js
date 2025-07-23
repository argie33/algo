/**
 * Portfolio Math Functions - Individual Functions for Testing
 * Provides isolated math functions for unit testing
 */

/**
 * Calculate Value at Risk (VaR) for a portfolio
 */
export function calculateVaR(returns, confidenceLevel = 0.05, method = 'parametric') {
  if (!returns || returns.length === 0) {
    throw new Error('Returns array cannot be empty');
  }
  
  if (confidenceLevel <= 0 || confidenceLevel >= 1) {
    throw new Error('Confidence level must be between 0 and 1');
  }
  
  if (returns.some(r => !isFinite(r))) {
    throw new Error('Returns contain invalid values');
  }
  
  if (method === 'historical') {
    const sortedReturns = returns.slice().sort((a, b) => a - b);
    const index = Math.floor(sortedReturns.length * confidenceLevel);
    return {
      var: Math.abs(sortedReturns[index]),
      confidenceLevel,
      method: 'historical'
    };
  }
  
  // Parametric method
  const mean = returns.reduce((sum, r) => sum + r, 0) / returns.length;
  const variance = returns.reduce((sum, r) => sum + Math.pow(r - mean, 2), 0) / (returns.length - 1);
  const std = Math.sqrt(variance);
  
  const zScore = getZScore(confidenceLevel);
  const var_ = Math.abs(mean - zScore * std);
  
  return {
    var: var_,
    confidenceLevel,
    method: 'parametric'
  };
}

/**
 * Calculate Sharpe Ratio
 */
export function calculateSharpeRatio(returns, riskFreeRate = 0.02) {
  if (!returns || returns.length === 0) {
    throw new Error('Returns array cannot be empty');
  }
  
  if (returns.some(r => !isFinite(r))) {
    throw new Error('Returns contain invalid values');
  }
  
  const mean = returns.reduce((sum, r) => sum + r, 0) / returns.length;
  const variance = returns.reduce((sum, r) => sum + Math.pow(r - mean, 2), 0) / (returns.length - 1);
  const std = Math.sqrt(variance);
  
  const annualizedReturn = mean * 252;
  const annualizedVolatility = std * Math.sqrt(252);
  
  const sharpeRatio = annualizedVolatility === 0 ? Infinity : (annualizedReturn - riskFreeRate) / annualizedVolatility;
  
  return {
    sharpeRatio,
    annualizedReturn,
    annualizedVolatility
  };
}

/**
 * Calculate Beta
 */
export function calculateBeta(portfolioReturns, marketReturns) {
  if (!portfolioReturns || !marketReturns) {
    throw new Error('Both portfolio and market returns are required');
  }
  
  if (portfolioReturns.length !== marketReturns.length) {
    throw new Error('Array lengths must match');
  }
  
  const portfolioMean = portfolioReturns.reduce((sum, r) => sum + r, 0) / portfolioReturns.length;
  const marketMean = marketReturns.reduce((sum, r) => sum + r, 0) / marketReturns.length;
  
  let covariance = 0;
  let marketVariance = 0;
  
  for (let i = 0; i < portfolioReturns.length; i++) {
    const portfolioDeviation = portfolioReturns[i] - portfolioMean;
    const marketDeviation = marketReturns[i] - marketMean;
    
    covariance += portfolioDeviation * marketDeviation;
    marketVariance += marketDeviation * marketDeviation;
  }
  
  covariance /= (portfolioReturns.length - 1);
  marketVariance /= (marketReturns.length - 1);
  
  const beta = marketVariance === 0 ? 1 : covariance / marketVariance;
  
  // Calculate correlation
  const portfolioVariance = portfolioReturns.reduce((sum, r) => sum + Math.pow(r - portfolioMean, 2), 0) / (portfolioReturns.length - 1);
  const correlation = Math.sqrt(portfolioVariance * marketVariance) === 0 ? 0 : 
    covariance / Math.sqrt(portfolioVariance * marketVariance);
  
  return {
    beta,
    correlation,
    rSquared: correlation * correlation
  };
}

/**
 * Calculate Correlation Matrix
 */
export function calculateCorrelationMatrix(assetReturns) {
  const symbols = Object.keys(assetReturns);
  const numAssets = symbols.length;
  
  if (numAssets === 0) {
    return { matrix: [], symbols: [] };
  }
  
  const matrix = Array(numAssets).fill().map(() => Array(numAssets).fill(0));
  
  for (let i = 0; i < numAssets; i++) {
    for (let j = 0; j < numAssets; j++) {
      if (i === j) {
        matrix[i][j] = 1;
      } else {
        const correlation = calculateCorrelation(assetReturns[symbols[i]], assetReturns[symbols[j]]);
        matrix[i][j] = correlation;
      }
    }
  }
  
  return { matrix, symbols };
}

/**
 * Calculate Portfolio Return
 */
export function calculatePortfolioReturn(positions) {
  if (!positions || positions.length === 0) {
    throw new Error('Portfolio cannot be empty');
  }
  
  const totalWeight = positions.reduce((sum, pos) => sum + pos.weight, 0);
  if (Math.abs(totalWeight - 1) > 0.01) {
    throw new Error('Position weights must sum to 1');
  }
  
  const totalReturn = positions.reduce((sum, pos) => {
    const positionReturn = ((pos.price - (pos.costBasis || pos.price)) / (pos.costBasis || pos.price)) || 0;
    return sum + (pos.weight * positionReturn);
  }, 0);
  
  const contributions = positions.map(pos => {
    const positionReturn = ((pos.price - (pos.costBasis || pos.price)) / (pos.costBasis || pos.price)) || 0;
    return {
      symbol: pos.symbol,
      contribution: pos.weight * positionReturn
    };
  });
  
  return {
    totalReturn,
    weightedReturn: totalReturn,
    contributions
  };
}

/**
 * Calculate Volatility
 */
export function calculateVolatility(returns) {
  if (!returns || returns.length === 0) {
    return {
      dailyVolatility: 0,
      annualizedVolatility: 0,
      variance: 0
    };
  }
  
  const mean = returns.reduce((sum, r) => sum + r, 0) / returns.length;
  const variance = returns.reduce((sum, r) => sum + Math.pow(r - mean, 2), 0) / (returns.length - 1);
  const dailyVolatility = Math.sqrt(variance);
  const annualizedVolatility = dailyVolatility * Math.sqrt(252);
  
  return {
    dailyVolatility,
    annualizedVolatility,
    variance
  };
}

/**
 * Helper function to calculate correlation between two return series
 */
function calculateCorrelation(returns1, returns2) {
  if (returns1.length !== returns2.length) {
    return 0;
  }
  
  const mean1 = returns1.reduce((sum, r) => sum + r, 0) / returns1.length;
  const mean2 = returns2.reduce((sum, r) => sum + r, 0) / returns2.length;
  
  let covariance = 0;
  let variance1 = 0;
  let variance2 = 0;
  
  for (let i = 0; i < returns1.length; i++) {
    const deviation1 = returns1[i] - mean1;
    const deviation2 = returns2[i] - mean2;
    
    covariance += deviation1 * deviation2;
    variance1 += deviation1 * deviation1;
    variance2 += deviation2 * deviation2;
  }
  
  const std1 = Math.sqrt(variance1);
  const std2 = Math.sqrt(variance2);
  
  return (std1 === 0 || std2 === 0) ? 0 : covariance / (std1 * std2);
}

/**
 * Helper function to get Z-score for confidence level
 */
function getZScore(confidenceLevel) {
  const criticalValues = {
    0.01: 2.326,
    0.025: 1.96,
    0.05: 1.645,
    0.10: 1.282
  };
  
  return criticalValues[confidenceLevel] || 1.645;
}

/**
 * Basic Statistical Functions for Portfolio Math
 */

/**
 * Calculate the mean (average) of an array of numbers
 */
export function mean(data) {
  if (!Array.isArray(data) || data.length === 0) {
    throw new Error('Data must be a non-empty array');
  }
  
  const sum = data.reduce((acc, val) => acc + val, 0);
  return sum / data.length;
}

/**
 * Calculate the variance of an array of numbers
 */
export function variance(data) {
  if (!Array.isArray(data) || data.length === 0) {
    throw new Error('Data must be a non-empty array');
  }
  
  const meanValue = mean(data);
  const squaredDifferences = data.map(val => Math.pow(val - meanValue, 2));
  return mean(squaredDifferences);
}

/**
 * Calculate the standard deviation of an array of numbers
 */
export function standardDeviation(data) {
  return Math.sqrt(variance(data));
}

/**
 * Calculate the covariance between two arrays of numbers
 */
export function covariance(dataX, dataY) {
  if (!Array.isArray(dataX) || !Array.isArray(dataY)) {
    throw new Error('Both inputs must be arrays');
  }
  
  if (dataX.length !== dataY.length) {
    throw new Error('Arrays must have the same length');
  }
  
  if (dataX.length === 0) {
    throw new Error('Arrays cannot be empty');
  }
  
  const meanX = mean(dataX);
  const meanY = mean(dataY);
  
  const covariances = dataX.map((x, i) => (x - meanX) * (dataY[i] - meanY));
  return mean(covariances);
}

/**
 * Calculate the correlation coefficient between two arrays of numbers
 */
export function correlation(dataX, dataY) {
  const cov = covariance(dataX, dataY);
  const stdX = standardDeviation(dataX);
  const stdY = standardDeviation(dataY);
  
  if (stdX === 0 || stdY === 0) {
    return 0; // No correlation if either variable has no variance
  }
  
  return cov / (stdX * stdY);
}

/**
 * Calculate a percentile of an array of numbers
 */
export function percentile(data, percentile) {
  if (!Array.isArray(data) || data.length === 0) {
    throw new Error('Data must be a non-empty array');
  }
  
  if (percentile < 0 || percentile > 100) {
    throw new Error('Percentile must be between 0 and 100');
  }
  
  const sorted = [...data].sort((a, b) => a - b);
  const index = (percentile / 100) * (sorted.length - 1);
  const lower = Math.floor(index);
  const upper = Math.ceil(index);
  
  if (lower === upper) {
    return sorted[lower];
  }
  
  const weight = index - lower;
  return sorted[lower] * (1 - weight) + sorted[upper] * weight;
}

// Export all functions as default object for backward compatibility
const portfolioMathFunctions = {
  calculateVaR,
  mean,
  variance,
  standardDeviation,
  covariance,
  correlation,
  percentile
};

export default portfolioMathFunctions;
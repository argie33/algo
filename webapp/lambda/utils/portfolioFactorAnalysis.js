/**
 * Institutional-Grade Portfolio Factor Analysis
 * Provides sophisticated factor exposure analysis for institutional portfolios
 */

/**
 * Calculate factor loadings using regression analysis
 * @param {Array} returns - Portfolio returns
 * @param {Object} factorReturns - Factor returns by factor name
 * @returns {Object} Factor loadings and R-squared
 */
function calculateFactorLoadings(returns, factorReturns) {
  if (!returns || !factorReturns || returns.length === 0) {
    return {};
  }

  const factors = Object.keys(factorReturns);
  const loadings = {};
  
  factors.forEach(factor => {
    const factorData = factorReturns[factor];
    if (factorData && factorData.length === returns.length) {
      const loading = calculateBeta(returns, factorData);
      const correlation = calculateCorrelation(returns, factorData);
      const rSquared = correlation * correlation;
      
      loadings[factor] = {
        loading: loading,
        correlation: correlation,
        rSquared: rSquared,
        tStatistic: calculateTStatistic(loading, returns, factorData),
        significance: Math.abs(calculateTStatistic(loading, returns, factorData)) > 2
      };
    }
  });
  
  return loadings;
}

/**
 * Calculate beta coefficient
 * @param {Array} y - Dependent variable (portfolio returns)
 * @param {Array} x - Independent variable (factor returns)
 * @returns {number} Beta coefficient
 */
function calculateBeta(y, x) {
  if (y.length !== x.length || y.length === 0) return 0;
  
  const yMean = y.reduce((sum, val) => sum + val, 0) / y.length;
  const xMean = x.reduce((sum, val) => sum + val, 0) / x.length;
  
  let covariance = 0;
  let variance = 0;
  
  for (let i = 0; i < y.length; i++) {
    covariance += (y[i] - yMean) * (x[i] - xMean);
    variance += (x[i] - xMean) * (x[i] - xMean);
  }
  
  return variance === 0 ? 0 : covariance / variance;
}

/**
 * Calculate correlation coefficient
 * @param {Array} x - First dataset
 * @param {Array} y - Second dataset
 * @returns {number} Correlation coefficient
 */
function calculateCorrelation(x, y) {
  if (x.length !== y.length || x.length === 0) return 0;
  
  const xMean = x.reduce((sum, val) => sum + val, 0) / x.length;
  const yMean = y.reduce((sum, val) => sum + val, 0) / y.length;
  
  let numerator = 0;
  let xVariance = 0;
  let yVariance = 0;
  
  for (let i = 0; i < x.length; i++) {
    const xDiff = x[i] - xMean;
    const yDiff = y[i] - yMean;
    
    numerator += xDiff * yDiff;
    xVariance += xDiff * xDiff;
    yVariance += yDiff * yDiff;
  }
  
  const denominator = Math.sqrt(xVariance * yVariance);
  return denominator === 0 ? 0 : numerator / denominator;
}

/**
 * Calculate t-statistic for significance testing
 * @param {number} beta - Beta coefficient
 * @param {Array} y - Dependent variable
 * @param {Array} x - Independent variable
 * @returns {number} T-statistic
 */
function calculateTStatistic(beta, y, x) {
  if (y.length !== x.length || y.length < 3) return 0;
  
  const n = y.length;
  const yMean = y.reduce((sum, val) => sum + val, 0) / n;
  const xMean = x.reduce((sum, val) => sum + val, 0) / n;
  
  // Calculate residuals
  let residualSumSquares = 0;
  let xVariance = 0;
  
  for (let i = 0; i < n; i++) {
    const predicted = beta * x[i];
    const residual = y[i] - predicted;
    residualSumSquares += residual * residual;
    
    const xDiff = x[i] - xMean;
    xVariance += xDiff * xDiff;
  }
  
  const degreesOfFreedom = n - 2;
  const standardError = Math.sqrt(residualSumSquares / degreesOfFreedom / xVariance);
  
  return standardError === 0 ? 0 : beta / standardError;
}

/**
 * Perform comprehensive factor analysis on portfolio holdings
 * @param {Array} holdings - Portfolio holdings with sector and market cap data
 * @param {Array} performanceHistory - Historical performance data
 * @returns {Object} Comprehensive factor analysis
 */
function performFactorAnalysis(holdings, performanceHistory = []) {
  if (!holdings || holdings.length === 0) {
    return {
      factorExposures: {},
      styleAnalysis: {},
      riskAttribution: {},
      activeExposures: {}
    };
  }

  const totalValue = holdings.reduce((sum, h) => sum + (h.marketValue || 0), 0);
  
  // Calculate factor exposures based on holdings
  const factorExposures = calculateHoldingsFactorExposures(holdings, totalValue);
  
  // Style analysis
  const styleAnalysis = calculateStyleAnalysis(holdings, totalValue);
  
  // Risk attribution
  const riskAttribution = calculateRiskAttribution(holdings, totalValue);
  
  // Active exposures vs benchmark
  const activeExposures = calculateActiveExposures(factorExposures);
  
  return {
    factorExposures,
    styleAnalysis,
    riskAttribution,
    activeExposures,
    totalValue,
    analysisDate: new Date().toISOString()
  };
}

/**
 * Calculate factor exposures based on holdings
 * @param {Array} holdings - Portfolio holdings
 * @param {number} totalValue - Total portfolio value
 * @returns {Object} Factor exposures
 */
function calculateHoldingsFactorExposures(holdings, totalValue) {
  const exposures = {
    quality: 0,
    growth: 0,
    value: 0,
    momentum: 0,
    size: 0,
    volatility: 0,
    dividend: 0,
    profitability: 0
  };
  
  holdings.forEach(holding => {
    const weight = totalValue > 0 ? (holding.marketValue || 0) / totalValue : 0;
    const sector = holding.sector || 'Other';
    const marketCap = holding.marketCap || 'large';
    
    // Quality factor (based on sector and financial health)
    if (['Technology', 'Healthcare', 'Consumer Staples'].includes(sector)) {
      exposures.quality += weight * 0.8;
    } else if (['Utilities', 'Telecommunications'].includes(sector)) {
      exposures.quality += weight * 0.6;
    } else {
      exposures.quality += weight * 0.4;
    }
    
    // Growth factor
    if (['Technology', 'Consumer Discretionary'].includes(sector)) {
      exposures.growth += weight * 0.9;
    } else if (['Healthcare', 'Industrials'].includes(sector)) {
      exposures.growth += weight * 0.6;
    } else {
      exposures.growth += weight * 0.3;
    }
    
    // Value factor
    if (['Financials', 'Energy', 'Materials'].includes(sector)) {
      exposures.value += weight * 0.8;
    } else if (['Utilities', 'Real Estate'].includes(sector)) {
      exposures.value += weight * 0.6;
    } else {
      exposures.value += weight * 0.2;
    }
    
    // Momentum factor (based on recent performance)
    const recentReturn = holding.unrealizedPLPercent || 0;
    if (recentReturn > 10) {
      exposures.momentum += weight * 0.8;
    } else if (recentReturn > 0) {
      exposures.momentum += weight * 0.5;
    } else {
      exposures.momentum += weight * 0.2;
    }
    
    // Size factor
    if (marketCap === 'small') {
      exposures.size += weight * 0.9;
    } else if (marketCap === 'mid') {
      exposures.size += weight * 0.6;
    } else {
      exposures.size += weight * 0.3;
    }
    
    // Volatility factor (based on sector volatility)
    if (['Technology', 'Biotechnology'].includes(sector)) {
      exposures.volatility += weight * 0.9;
    } else if (['Energy', 'Materials'].includes(sector)) {
      exposures.volatility += weight * 0.7;
    } else {
      exposures.volatility += weight * 0.4;
    }
    
    // Dividend factor
    if (['Utilities', 'Real Estate', 'Consumer Staples'].includes(sector)) {
      exposures.dividend += weight * 0.8;
    } else if (['Financials', 'Telecommunications'].includes(sector)) {
      exposures.dividend += weight * 0.6;
    } else {
      exposures.dividend += weight * 0.2;
    }
    
    // Profitability factor
    if (['Technology', 'Healthcare', 'Consumer Staples'].includes(sector)) {
      exposures.profitability += weight * 0.8;
    } else if (['Financials', 'Industrials'].includes(sector)) {
      exposures.profitability += weight * 0.6;
    } else {
      exposures.profitability += weight * 0.4;
    }
  });
  
  return exposures;
}

/**
 * Calculate style analysis (Growth vs Value, Large vs Small Cap)
 * @param {Array} holdings - Portfolio holdings
 * @param {number} totalValue - Total portfolio value
 * @returns {Object} Style analysis
 */
function calculateStyleAnalysis(holdings, totalValue) {
  let growthExposure = 0;
  let valueExposure = 0;
  let largeCapExposure = 0;
  let midCapExposure = 0;
  let smallCapExposure = 0;
  
  holdings.forEach(holding => {
    const weight = totalValue > 0 ? (holding.marketValue || 0) / totalValue : 0;
    const sector = holding.sector || 'Other';
    const marketCap = holding.marketCap || 'large';
    
    // Growth vs Value
    if (['Technology', 'Consumer Discretionary', 'Communication Services'].includes(sector)) {
      growthExposure += weight;
    } else if (['Financials', 'Energy', 'Materials', 'Utilities'].includes(sector)) {
      valueExposure += weight;
    } else {
      // Neutral sectors
      growthExposure += weight * 0.5;
      valueExposure += weight * 0.5;
    }
    
    // Market Cap
    if (marketCap === 'large') {
      largeCapExposure += weight;
    } else if (marketCap === 'mid') {
      midCapExposure += weight;
    } else {
      smallCapExposure += weight;
    }
  });
  
  return {
    growthExposure,
    valueExposure,
    largeCapExposure,
    midCapExposure,
    smallCapExposure,
    styleBox: {
      growthLarge: growthExposure * largeCapExposure,
      growthMid: growthExposure * midCapExposure,
      growthSmall: growthExposure * smallCapExposure,
      valueLarge: valueExposure * largeCapExposure,
      valueMid: valueExposure * midCapExposure,
      valueSmall: valueExposure * smallCapExposure
    }
  };
}

/**
 * Calculate risk attribution by factor
 * @param {Array} holdings - Portfolio holdings
 * @param {number} totalValue - Total portfolio value
 * @returns {Object} Risk attribution
 */
function calculateRiskAttribution(holdings, totalValue) {
  const riskContribution = {};
  
  holdings.forEach(holding => {
    const weight = totalValue > 0 ? (holding.marketValue || 0) / totalValue : 0;
    const volatility = holding.volatility || 0.2; // Default 20% volatility
    const contribution = weight * weight * volatility * volatility;
    
    const sector = holding.sector || 'Other';
    riskContribution[sector] = (riskContribution[sector] || 0) + contribution;
  });
  
  const totalRisk = Object.values(riskContribution).reduce((sum, risk) => sum + risk, 0);
  
  // Normalize to percentages
  Object.keys(riskContribution).forEach(sector => {
    riskContribution[sector] = totalRisk > 0 ? (riskContribution[sector] / totalRisk) * 100 : 0;
  });
  
  return {
    sectorRiskContribution: riskContribution,
    totalPortfolioRisk: Math.sqrt(totalRisk) * 100,
    riskDiversification: calculateRiskDiversification(holdings, totalValue)
  };
}

/**
 * Calculate risk diversification benefits
 * @param {Array} holdings - Portfolio holdings
 * @param {number} totalValue - Total portfolio value
 * @returns {Object} Risk diversification metrics
 */
function calculateRiskDiversification(holdings, totalValue) {
  if (holdings.length === 0) return { diversificationRatio: 0, effectivePositions: 0 };
  
  // Calculate weighted average individual risk
  let weightedAvgRisk = 0;
  let sumSquaredWeights = 0;
  
  holdings.forEach(holding => {
    const weight = totalValue > 0 ? (holding.marketValue || 0) / totalValue : 0;
    const volatility = holding.volatility || 0.2;
    
    weightedAvgRisk += weight * volatility;
    sumSquaredWeights += weight * weight;
  });
  
  // Effective number of positions (inverse of sum of squared weights)
  const effectivePositions = sumSquaredWeights > 0 ? 1 / sumSquaredWeights : 0;
  
  // Portfolio risk (simplified - assumes average correlation of 0.3)
  const avgCorrelation = 0.3;
  const portfolioRisk = Math.sqrt(sumSquaredWeights + (1 - sumSquaredWeights) * avgCorrelation) * weightedAvgRisk;
  
  // Diversification ratio
  const diversificationRatio = portfolioRisk > 0 ? weightedAvgRisk / portfolioRisk : 0;
  
  return {
    diversificationRatio,
    effectivePositions,
    portfolioRisk: portfolioRisk * 100,
    weightedAvgRisk: weightedAvgRisk * 100
  };
}

/**
 * Calculate active exposures vs benchmark
 * @param {Object} factorExposures - Portfolio factor exposures
 * @returns {Object} Active exposures
 */
function calculateActiveExposures(factorExposures) {
  // Benchmark factor exposures (e.g., S&P 500)
  const benchmarkExposures = {
    quality: 0.6,
    growth: 0.5,
    value: 0.5,
    momentum: 0.5,
    size: 0.3,
    volatility: 0.4,
    dividend: 0.4,
    profitability: 0.6
  };
  
  const activeExposures = {};
  
  Object.keys(factorExposures).forEach(factor => {
    const portfolioExposure = factorExposures[factor] || 0;
    const benchmarkExposure = benchmarkExposures[factor] || 0;
    activeExposures[factor] = portfolioExposure - benchmarkExposure;
  });
  
  return activeExposures;
}

module.exports = {
  performFactorAnalysis,
  calculateFactorLoadings,
  calculateBeta,
  calculateCorrelation,
  calculateTStatistic,
  calculateHoldingsFactorExposures,
  calculateStyleAnalysis,
  calculateRiskAttribution,
  calculateActiveExposures
};
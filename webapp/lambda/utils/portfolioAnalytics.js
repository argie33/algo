/**
 * Advanced Portfolio Analytics Utility
 * Provides sophisticated performance metrics and risk analysis
 */

/**
 * Calculate Sharpe ratio for a portfolio
 * @param {Array} returns - Array of portfolio returns
 * @param {number} riskFreeRate - Risk-free rate (default 0.02 for 2%)
 * @returns {number} Sharpe ratio
 */
function calculateSharpeRatio(returns, riskFreeRate = 0.02) {
  if (!returns || returns.length === 0) return 0;
  
  const avgReturn = returns.reduce((sum, r) => sum + r, 0) / returns.length;
  const variance = returns.reduce((sum, r) => sum + Math.pow(r - avgReturn, 2), 0) / returns.length;
  const stdDev = Math.sqrt(variance);
  
  if (stdDev === 0) return 0;
  
  const annualizedReturn = avgReturn * 252; // 252 trading days
  const annualizedStdDev = stdDev * Math.sqrt(252);
  
  return (annualizedReturn - riskFreeRate) / annualizedStdDev;
}

/**
 * Calculate maximum drawdown
 * @param {Array} portfolioValues - Array of portfolio values over time
 * @returns {Object} Maximum drawdown info
 */
function calculateMaxDrawdown(portfolioValues) {
  if (!portfolioValues || portfolioValues.length === 0) {
    return { maxDrawdown: 0, drawdownPeriod: 0, peak: 0, trough: 0 };
  }
  
  let maxDrawdown = 0;
  let peak = portfolioValues[0];
  let trough = portfolioValues[0];
  let drawdownPeriod = 0;
  let currentDrawdownStart = 0;
  
  for (let i = 1; i < portfolioValues.length; i++) {
    if (portfolioValues[i] > peak) {
      peak = portfolioValues[i];
      currentDrawdownStart = i;
    }
    
    const drawdown = (peak - portfolioValues[i]) / peak;
    if (drawdown > maxDrawdown) {
      maxDrawdown = drawdown;
      trough = portfolioValues[i];
      drawdownPeriod = i - currentDrawdownStart;
    }
  }
  
  return {
    maxDrawdown: maxDrawdown * 100, // Convert to percentage
    drawdownPeriod,
    peak,
    trough
  };
}

/**
 * Calculate beta relative to market (S&P 500)
 * @param {Array} portfolioReturns - Portfolio returns
 * @param {Array} marketReturns - Market returns (S&P 500)
 * @returns {number} Beta coefficient
 */
function calculateBeta(portfolioReturns, marketReturns) {
  if (!portfolioReturns || !marketReturns || portfolioReturns.length !== marketReturns.length) {
    return 1.0; // Default beta of 1
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
  
  if (marketVariance === 0) return 1.0;
  
  return covariance / marketVariance;
}

/**
 * Calculate Value at Risk (VaR) at 95% confidence level
 * @param {Array} returns - Array of portfolio returns
 * @param {number} confidenceLevel - Confidence level (default 0.95)
 * @returns {number} VaR as a percentage
 */
function calculateVaR(returns, confidenceLevel = 0.95) {
  if (!returns || returns.length === 0) return 0;
  
  const sortedReturns = [...returns].sort((a, b) => a - b);
  const index = Math.floor((1 - confidenceLevel) * sortedReturns.length);
  
  return Math.abs(sortedReturns[index] || 0) * 100;
}

/**
 * Calculate portfolio volatility (annualized)
 * @param {Array} returns - Array of portfolio returns
 * @returns {number} Annualized volatility as percentage
 */
function calculateVolatility(returns) {
  if (!returns || returns.length === 0) return 0;
  
  const avgReturn = returns.reduce((sum, r) => sum + r, 0) / returns.length;
  const variance = returns.reduce((sum, r) => sum + Math.pow(r - avgReturn, 2), 0) / returns.length;
  const stdDev = Math.sqrt(variance);
  
  return stdDev * Math.sqrt(252) * 100; // Annualized volatility as percentage
}

/**
 * Calculate information ratio
 * @param {Array} portfolioReturns - Portfolio returns
 * @param {Array} benchmarkReturns - Benchmark returns
 * @returns {number} Information ratio
 */
function calculateInformationRatio(portfolioReturns, benchmarkReturns) {
  if (!portfolioReturns || !benchmarkReturns || portfolioReturns.length !== benchmarkReturns.length) {
    return 0;
  }
  
  const activeReturns = portfolioReturns.map((r, i) => r - benchmarkReturns[i]);
  const avgActiveReturn = activeReturns.reduce((sum, r) => sum + r, 0) / activeReturns.length;
  const trackingError = Math.sqrt(
    activeReturns.reduce((sum, r) => sum + Math.pow(r - avgActiveReturn, 2), 0) / activeReturns.length
  );
  
  if (trackingError === 0) return 0;
  
  return (avgActiveReturn * 252) / (trackingError * Math.sqrt(252));
}

/**
 * Calculate comprehensive portfolio analytics
 * @param {Array} portfolioData - Array of portfolio data with dates and values
 * @param {Array} benchmarkData - Optional benchmark data for comparison
 * @returns {Object} Comprehensive analytics
 */
function calculatePortfolioAnalytics(portfolioData, benchmarkData = null) {
  if (!portfolioData || portfolioData.length === 0) {
    return {
      totalReturn: 0,
      annualizedReturn: 0,
      volatility: 0,
      sharpeRatio: 0,
      maxDrawdown: 0,
      beta: 1.0,
      var95: 0,
      informationRatio: 0,
      winRate: 0,
      averageWin: 0,
      averageLoss: 0,
      profitFactor: 0
    };
  }
  
  // Calculate returns
  const returns = [];
  for (let i = 1; i < portfolioData.length; i++) {
    const currentValue = portfolioData[i].portfolioValue || portfolioData[i].value;
    const previousValue = portfolioData[i - 1].portfolioValue || portfolioData[i - 1].value;
    
    if (previousValue > 0) {
      returns.push((currentValue - previousValue) / previousValue);
    }
  }
  
  // Calculate total return
  const firstValue = portfolioData[0].portfolioValue || portfolioData[0].value;
  const lastValue = portfolioData[portfolioData.length - 1].portfolioValue || portfolioData[portfolioData.length - 1].value;
  const totalReturn = firstValue > 0 ? ((lastValue - firstValue) / firstValue) * 100 : 0;
  
  // Calculate annualized return
  const days = portfolioData.length;
  const annualizedReturn = days > 0 ? (Math.pow(lastValue / firstValue, 252 / days) - 1) * 100 : 0;
  
  // Calculate win/loss metrics
  const wins = returns.filter(r => r > 0);
  const losses = returns.filter(r => r < 0);
  const winRate = returns.length > 0 ? (wins.length / returns.length) * 100 : 0;
  const averageWin = wins.length > 0 ? wins.reduce((sum, r) => sum + r, 0) / wins.length * 100 : 0;
  const averageLoss = losses.length > 0 ? Math.abs(losses.reduce((sum, r) => sum + r, 0) / losses.length) * 100 : 0;
  const profitFactor = averageLoss > 0 ? (averageWin * wins.length) / (averageLoss * losses.length) : 0;
  
  // Calculate drawdown
  const portfolioValues = portfolioData.map(d => d.portfolioValue || d.value);
  const maxDrawdownInfo = calculateMaxDrawdown(portfolioValues);
  
  // Calculate benchmark comparison metrics
  let beta = 1.0;
  let informationRatio = 0;
  
  if (benchmarkData && benchmarkData.length === portfolioData.length) {
    const benchmarkReturns = [];
    for (let i = 1; i < benchmarkData.length; i++) {
      const currentValue = benchmarkData[i].value;
      const previousValue = benchmarkData[i - 1].value;
      
      if (previousValue > 0) {
        benchmarkReturns.push((currentValue - previousValue) / previousValue);
      }
    }
    
    beta = calculateBeta(returns, benchmarkReturns);
    informationRatio = calculateInformationRatio(returns, benchmarkReturns);
  }
  
  return {
    totalReturn,
    annualizedReturn,
    volatility: calculateVolatility(returns),
    sharpeRatio: calculateSharpeRatio(returns),
    maxDrawdown: maxDrawdownInfo.maxDrawdown,
    beta,
    var95: calculateVaR(returns),
    informationRatio,
    winRate,
    averageWin,
    averageLoss,
    profitFactor,
    drawdownInfo: maxDrawdownInfo
  };
}

/**
 * Calculate sector allocation and diversification metrics
 * @param {Array} holdings - Array of portfolio holdings
 * @returns {Object} Sector analysis
 */
function calculateSectorAnalysis(holdings) {
  if (!holdings || holdings.length === 0) {
    return {
      sectorAllocation: [],
      diversificationScore: 0,
      concentrationRisk: 0,
      herfindahlIndex: 0
    };
  }
  
  const totalValue = holdings.reduce((sum, h) => sum + (h.marketValue || 0), 0);
  
  // Calculate sector allocation
  const sectorMap = holdings.reduce((acc, holding) => {
    const sector = holding.sector || 'Other';
    acc[sector] = acc[sector] || { value: 0, count: 0 };
    acc[sector].value += holding.marketValue || 0;
    acc[sector].count += 1;
    return acc;
  }, {});
  
  const sectorAllocation = Object.entries(sectorMap).map(([sector, data]) => ({
    sector,
    value: data.value,
    allocation: totalValue > 0 ? (data.value / totalValue) * 100 : 0,
    count: data.count
  })).sort((a, b) => b.allocation - a.allocation);
  
  // Calculate Herfindahl-Hirschman Index (concentration measure)
  const herfindahlIndex = sectorAllocation.reduce((sum, sector) => {
    const weight = sector.allocation / 100;
    return sum + (weight * weight);
  }, 0);
  
  // Calculate diversification score (0-100, higher is better)
  const diversificationScore = Math.max(0, 100 - (herfindahlIndex * 100));
  
  // Calculate concentration risk (% in top 3 sectors)
  const concentrationRisk = sectorAllocation.slice(0, 3).reduce((sum, sector) => sum + sector.allocation, 0);
  
  return {
    sectorAllocation,
    diversificationScore,
    concentrationRisk,
    herfindahlIndex
  };
}

module.exports = {
  calculateSharpeRatio,
  calculateMaxDrawdown,
  calculateBeta,
  calculateVaR,
  calculateVolatility,
  calculateInformationRatio,
  calculatePortfolioAnalytics,
  calculateSectorAnalysis
};
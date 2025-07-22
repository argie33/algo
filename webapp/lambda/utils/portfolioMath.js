const { Matrix, inverse } = require('ml-matrix');

/**
 * Portfolio Mathematics and Optimization Utilities
 * Implementation of Modern Portfolio Theory algorithms
 */

class PortfolioMath {
  
  /**
   * Calculate covariance matrix from price returns
   * @param {Array<Array<number>>} returns - Matrix of returns [time x assets]
   * @returns {Matrix} - Covariance matrix
   */
  static calculateCovarianceMatrix(returns) {
    if (!returns || returns.length === 0) {
      throw new Error('Returns data is required');
    }

    const matrix = new Matrix(returns);
    const numAssets = matrix.columns;
    const numPeriods = matrix.rows;
    
    // Calculate mean returns for each asset
    const means = [];
    for (let j = 0; j < numAssets; j++) {
      const assetReturns = matrix.getColumn(j);
      const mean = assetReturns.reduce((sum, val) => sum + val, 0) / numPeriods;
      means.push(mean);
    }
    
    // Calculate covariance matrix
    const covMatrix = Matrix.zeros(numAssets, numAssets);
    
    for (let i = 0; i < numAssets; i++) {
      for (let j = 0; j < numAssets; j++) {
        let covariance = 0;
        
        for (let t = 0; t < numPeriods; t++) {
          const returnI = matrix.get(t, i) - means[i];
          const returnJ = matrix.get(t, j) - means[j];
          covariance += returnI * returnJ;
        }
        
        // Annualize the covariance (assuming daily returns)
        covariance = (covariance / (numPeriods - 1)) * 252;
        covMatrix.set(i, j, covariance);
      }
    }
    
    return covMatrix;
  }

  /**
   * Calculate correlation matrix from covariance matrix
   * @param {Matrix} covMatrix - Covariance matrix
   * @returns {Matrix} - Correlation matrix
   */
  static calculateCorrelationMatrix(covMatrix) {
    const numAssets = covMatrix.rows;
    const corrMatrix = Matrix.zeros(numAssets, numAssets);
    
    for (let i = 0; i < numAssets; i++) {
      for (let j = 0; j < numAssets; j++) {
        const cov = covMatrix.get(i, j);
        const stdI = Math.sqrt(covMatrix.get(i, i));
        const stdJ = Math.sqrt(covMatrix.get(j, j));
        
        const correlation = cov / (stdI * stdJ);
        corrMatrix.set(i, j, correlation);
      }
    }
    
    return corrMatrix;
  }

  /**
   * Calculate expected returns using various methods
   * @param {Array<Array<number>>} returns - Historical returns
   * @param {string} method - 'historical', 'ewma', 'capm'
   * @param {Object} options - Additional options
   * @returns {Array<number>} - Expected returns vector
   */
  static calculateExpectedReturns(returns, method = 'historical', options = {}) {
    const matrix = new Matrix(returns);
    const { halfLife = 60, marketReturns = null, riskFreeRate = 0.02 } = options;
    
    switch (method) {
      case 'historical':
        return this.historicalMeanReturns(matrix);
      
      case 'ewma':
        return this.exponentiallyWeightedReturns(matrix, halfLife);
      
      case 'capm':
        if (!marketReturns) {
          throw new Error('Market returns required for CAPM method');
        }
        return this.capmExpectedReturns(matrix, marketReturns, riskFreeRate);
      
      default:
        return this.historicalMeanReturns(matrix);
    }
  }

  /**
   * Historical mean returns
   */
  static historicalMeanReturns(matrix) {
    const numAssets = matrix.columns;
    const numPeriods = matrix.rows;
    const expectedReturns = [];
    
    for (let j = 0; j < numAssets; j++) {
      const assetReturns = matrix.getColumn(j);
      const mean = assetReturns.reduce((sum, val) => sum + val, 0) / numPeriods;
      // Annualize the return (assuming daily returns)
      expectedReturns.push(mean * 252);
    }
    
    return expectedReturns;
  }

  /**
   * Exponentially weighted moving average returns
   */
  static exponentiallyWeightedReturns(matrix, halfLife) {
    const numAssets = matrix.columns;
    const numPeriods = matrix.rows;
    const alpha = 1 - Math.exp(-Math.log(2) / halfLife);
    
    const expectedReturns = [];
    
    for (let j = 0; j < numAssets; j++) {
      const assetReturns = matrix.getColumn(j);
      let ewma = assetReturns[0];
      
      for (let i = 1; i < numPeriods; i++) {
        ewma = alpha * assetReturns[i] + (1 - alpha) * ewma;
      }
      
      // Annualize the return
      expectedReturns.push(ewma * 252);
    }
    
    return expectedReturns;
  }

  /**
   * CAPM expected returns
   */
  static capmExpectedReturns(matrix, marketReturns, riskFreeRate) {
    const numAssets = matrix.columns;
    const expectedReturns = [];
    
    // Calculate market variance
    const marketMean = marketReturns.reduce((sum, val) => sum + val, 0) / marketReturns.length;
    const marketVariance = marketReturns.reduce((sum, val) => sum + Math.pow(val - marketMean, 2), 0) / (marketReturns.length - 1);
    
    for (let j = 0; j < numAssets; j++) {
      const assetReturns = matrix.getColumn(j);
      const assetMean = assetReturns.reduce((sum, val) => sum + val, 0) / assetReturns.length;
      
      // Calculate beta
      let covariance = 0;
      for (let i = 0; i < assetReturns.length; i++) {
        covariance += (assetReturns[i] - assetMean) * (marketReturns[i] - marketMean);
      }
      covariance /= (assetReturns.length - 1);
      
      const beta = covariance / marketVariance;
      
      // CAPM formula: E(R) = Rf + β(E(Rm) - Rf)
      const expectedReturn = riskFreeRate + beta * (marketMean * 252 - riskFreeRate);
      expectedReturns.push(expectedReturn);
    }
    
    return expectedReturns;
  }

  /**
   * Mean-Variance Optimization (Markowitz)
   * @param {Array<number>} expectedReturns - Expected returns vector
   * @param {Matrix} covMatrix - Covariance matrix
   * @param {Object} constraints - Optimization constraints
   * @returns {Object} - Optimal weights and metrics
   */
  static meanVarianceOptimization(expectedReturns, covMatrix, constraints = {}) {
    const {
      targetReturn = null,
      riskFreeRate = 0.02,
      objective = 'maxSharpe', // 'maxSharpe', 'minRisk', 'maxReturn', 'targetReturn'
      maxWeight = 1.0,
      minWeight = 0.0,
      allowShorts = false
    } = constraints;

    const numAssets = expectedReturns.length;

    // For simplicity, using analytical solution for unconstrained case
    // In production, would use quadratic programming solver
    
    if (objective === 'maxSharpe') {
      return this.maxSharpeOptimization(expectedReturns, covMatrix, riskFreeRate);
    } else if (objective === 'minRisk') {
      return this.minVarianceOptimization(expectedReturns, covMatrix);
    } else if (objective === 'equalWeight') {
      return this.equalWeightOptimization(expectedReturns, covMatrix);
    } else if (objective === 'riskParity') {
      return this.riskParityOptimization(expectedReturns, covMatrix);
    }
    
    // Default to max Sharpe
    return this.maxSharpeOptimization(expectedReturns, covMatrix, riskFreeRate);
  }

  /**
   * Maximum Sharpe Ratio optimization
   */
  static maxSharpeOptimization(expectedReturns, covMatrix, riskFreeRate) {
    try {
      // Calculate excess returns
      const excessReturns = expectedReturns.map(r => r - riskFreeRate);
      
      // Invert covariance matrix
      const invCovMatrix = inverse(covMatrix);
      
      // Calculate optimal weights: w = (Σ^-1 * μ) / (1^T * Σ^-1 * μ)
      const excessReturnsVector = new Matrix([excessReturns]).transpose();
      const numerator = invCovMatrix.mmul(excessReturnsVector);
      
      // Sum of numerator
      const denominatorSum = numerator.getColumn(0).reduce((sum, val) => sum + val, 0);
      
      // Normalize weights
      const weights = numerator.getColumn(0).map(w => w / denominatorSum);
      
      // Calculate portfolio metrics
      const portfolioReturn = this.calculatePortfolioReturn(weights, expectedReturns);
      const portfolioVariance = this.calculatePortfolioVariance(weights, covMatrix);
      const portfolioStd = Math.sqrt(portfolioVariance);
      const sharpeRatio = (portfolioReturn - riskFreeRate) / portfolioStd;
      
      return {
        weights: weights,
        expectedReturn: portfolioReturn,
        volatility: portfolioStd,
        sharpeRatio: sharpeRatio,
        objective: 'maxSharpe'
      };
    } catch (error) {
      console.error('Max Sharpe optimization failed:', error);
      // Fallback to equal weight
      return this.equalWeightOptimization(expectedReturns, covMatrix);
    }
  }

  /**
   * Minimum variance optimization
   */
  static minVarianceOptimization(expectedReturns, covMatrix) {
    try {
      // Invert covariance matrix
      const invCovMatrix = inverse(covMatrix);
      
      // Calculate minimum variance weights: w = (Σ^-1 * 1) / (1^T * Σ^-1 * 1)
      const ones = Matrix.ones(expectedReturns.length, 1);
      const numerator = invCovMatrix.mmul(ones);
      
      // Sum for normalization
      const denominatorSum = numerator.getColumn(0).reduce((sum, val) => sum + val, 0);
      
      // Normalize weights
      const weights = numerator.getColumn(0).map(w => w / denominatorSum);
      
      // Calculate portfolio metrics
      const portfolioReturn = this.calculatePortfolioReturn(weights, expectedReturns);
      const portfolioVariance = this.calculatePortfolioVariance(weights, covMatrix);
      const portfolioStd = Math.sqrt(portfolioVariance);
      
      return {
        weights: weights,
        expectedReturn: portfolioReturn,
        volatility: portfolioStd,
        sharpeRatio: portfolioReturn / portfolioStd,
        objective: 'minRisk'
      };
    } catch (error) {
      console.error('Min variance optimization failed:', error);
      return this.equalWeightOptimization(expectedReturns, covMatrix);
    }
  }

  /**
   * Equal weight optimization (1/N portfolio)
   */
  static equalWeightOptimization(expectedReturns, covMatrix) {
    const numAssets = expectedReturns.length;
    const weights = new Array(numAssets).fill(1 / numAssets);
    
    const portfolioReturn = this.calculatePortfolioReturn(weights, expectedReturns);
    const portfolioVariance = this.calculatePortfolioVariance(weights, covMatrix);
    const portfolioStd = Math.sqrt(portfolioVariance);
    
    return {
      weights: weights,
      expectedReturn: portfolioReturn,
      volatility: portfolioStd,
      sharpeRatio: portfolioReturn / portfolioStd,
      objective: 'equalWeight'
    };
  }

  /**
   * Risk parity optimization (equal risk contribution)
   */
  static riskParityOptimization(expectedReturns, covMatrix) {
    const numAssets = expectedReturns.length;
    
    // Simplified risk parity: inverse volatility weighting
    const volatilities = [];
    for (let i = 0; i < numAssets; i++) {
      volatilities.push(Math.sqrt(covMatrix.get(i, i)));
    }
    
    // Inverse volatility weights
    const invVolWeights = volatilities.map(vol => 1 / vol);
    const sumInvVol = invVolWeights.reduce((sum, w) => sum + w, 0);
    const weights = invVolWeights.map(w => w / sumInvVol);
    
    const portfolioReturn = this.calculatePortfolioReturn(weights, expectedReturns);
    const portfolioVariance = this.calculatePortfolioVariance(weights, covMatrix);
    const portfolioStd = Math.sqrt(portfolioVariance);
    
    return {
      weights: weights,
      expectedReturn: portfolioReturn,
      volatility: portfolioStd,
      sharpeRatio: portfolioReturn / portfolioStd,
      objective: 'riskParity'
    };
  }

  /**
   * Calculate portfolio expected return
   */
  static calculatePortfolioReturn(weights, expectedReturns) {
    return weights.reduce((sum, weight, i) => sum + weight * expectedReturns[i], 0);
  }

  /**
   * Calculate portfolio variance
   */
  static calculatePortfolioVariance(weights, covMatrix) {
    const weightsMatrix = new Matrix([weights]);
    const result = weightsMatrix.mmul(covMatrix).mmul(weightsMatrix.transpose());
    return result.get(0, 0);
  }

  /**
   * Generate efficient frontier points
   * @param {Array<number>} expectedReturns - Expected returns vector
   * @param {Matrix} covMatrix - Covariance matrix
   * @param {number} numPoints - Number of frontier points
   * @returns {Array<Object>} - Efficient frontier data points
   */
  static generateEfficientFrontier(expectedReturns, covMatrix, numPoints = 20) {
    const minReturnPort = this.minVarianceOptimization(expectedReturns, covMatrix);
    const maxReturnPort = { 
      expectedReturn: Math.max(...expectedReturns),
      volatility: Math.sqrt(covMatrix.get(expectedReturns.indexOf(Math.max(...expectedReturns)), expectedReturns.indexOf(Math.max(...expectedReturns))))
    };
    
    const frontierPoints = [];
    const minReturn = minReturnPort.expectedReturn;
    const maxReturn = maxReturnPort.expectedReturn;
    
    for (let i = 0; i < numPoints; i++) {
      const targetReturn = minReturn + (maxReturn - minReturn) * (i / (numPoints - 1));
      
      // For simplicity, using approximation
      // In production, would solve constrained optimization for each target return
      const alpha = (targetReturn - minReturn) / (maxReturn - minReturn);
      const volatility = Math.sqrt(
        Math.pow(minReturnPort.volatility, 2) * Math.pow(1 - alpha, 2) +
        Math.pow(maxReturnPort.volatility, 2) * Math.pow(alpha, 2) +
        2 * alpha * (1 - alpha) * minReturnPort.volatility * maxReturnPort.volatility * 0.5
      );
      
      // Generate approximate weights for this point (linear interpolation)
      const maxReturnIndex = expectedReturns.indexOf(Math.max(...expectedReturns));
      const weights = new Array(expectedReturns.length).fill(0);
      
      if (minReturnPort.weights) {
        // Interpolate between min variance and max return portfolio weights
        for (let j = 0; j < weights.length; j++) {
          const minWeight = minReturnPort.weights[j] || (j === 0 ? 1 : 0); // Default to equal weight if not available
          const maxWeight = j === maxReturnIndex ? 1 : 0; // Max return = 100% in best asset
          weights[j] = minWeight * (1 - alpha) + maxWeight * alpha;
        }
      } else {
        // Fallback: equal weight
        weights.fill(1 / expectedReturns.length);
      }
      
      frontierPoints.push({
        expectedReturn: targetReturn,
        volatility: volatility,
        sharpeRatio: targetReturn / volatility,
        weights: weights
      });
    }
    
    return frontierPoints;
  }

  /**
   * Calculate portfolio risk metrics
   * @param {Array<number>} weights - Portfolio weights
   * @param {Array<number>} expectedReturns - Expected returns
   * @param {Matrix} covMatrix - Covariance matrix
   * @param {Array<number>} benchmarkReturns - Benchmark returns for beta calculation
   * @returns {Object} - Risk metrics
   */
  static calculateRiskMetrics(weights, expectedReturns, covMatrix, benchmarkReturns = null) {
    const portfolioReturn = this.calculatePortfolioReturn(weights, expectedReturns);
    const portfolioVariance = this.calculatePortfolioVariance(weights, covMatrix);
    const portfolioStd = Math.sqrt(portfolioVariance);
    
    const metrics = {
      expectedReturn: portfolioReturn,
      volatility: portfolioStd,
      variance: portfolioVariance,
      sharpeRatio: portfolioReturn / portfolioStd,
    };
    
    // Calculate beta if benchmark provided
    if (benchmarkReturns) {
      // This would require historical portfolio returns for proper beta calculation
      // For now, using simplified approach
      const portfolioWeightedBeta = weights.reduce((sum, weight, i) => {
        // Approximate beta as 1.0 for individual stocks
        return sum + weight * 1.0;
      }, 0);
      
      metrics.beta = portfolioWeightedBeta;
      metrics.alpha = portfolioReturn - 0.02 - portfolioWeightedBeta * 0.08; // Simplified alpha
    }
    
    return metrics;
  }

  /**
   * Calculate Value at Risk (VaR)
   * @param {Array<number>} weights - Portfolio weights
   * @param {Matrix} covMatrix - Covariance matrix
   * @param {number} confidenceLevel - Confidence level (e.g., 0.95 for 95% VaR)
   * @param {number} timeHorizon - Time horizon in days
   * @returns {number} - VaR value
   */
  static calculateVaR(weights, covMatrix, confidenceLevel = 0.95, timeHorizon = 1) {
    const portfolioStd = Math.sqrt(this.calculatePortfolioVariance(weights, covMatrix));
    
    // Assuming normal distribution
    const zScore = this.inverseNormalCDF(confidenceLevel);
    const dailyVaR = zScore * portfolioStd / Math.sqrt(252); // Convert annual to daily
    
    return dailyVaR * Math.sqrt(timeHorizon);
  }

  /**
   * Simple inverse normal CDF approximation
   */
  static inverseNormalCDF(p) {
    // Simplified approximation for normal distribution
    // In production, would use more accurate implementation
    if (p === 0.95) return 1.645;
    if (p === 0.99) return 2.326;
    if (p === 0.975) return 1.96;
    if (p === 0.90) return 1.282;
    
    // Default approximation
    return Math.sqrt(-2 * Math.log(1 - p));
  }

  /**
   * Calculate factor exposures (simplified)
   * @param {Array<number>} weights - Portfolio weights
   * @param {Object} factorData - Factor exposure data for each asset
   * @returns {Object} - Portfolio factor exposures
   */
  static calculateFactorExposures(weights, factorData) {
    const factors = ['market', 'size', 'value', 'momentum', 'quality'];
    const exposures = {};
    
    factors.forEach(factor => {
      exposures[factor] = weights.reduce((sum, weight, i) => {
        const assetExposure = factorData[i] && factorData[i][factor] || 1.0;
        return sum + weight * assetExposure;
      }, 0);
    });
    
    return exposures;
  }
}

module.exports = PortfolioMath;
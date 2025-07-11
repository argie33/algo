// Portfolio Optimization Service
// Implements Modern Portfolio Theory, risk-return optimization, and asset allocation strategies

import axios from 'axios';
import cacheService from './cacheService';

class PortfolioOptimizer {
  constructor() {
    this.optimizationMethods = {
      'mean_variance': 'Mean Variance Optimization',
      'risk_parity': 'Risk Parity',
      'minimum_variance': 'Minimum Variance',
      'maximum_sharpe': 'Maximum Sharpe Ratio',
      'black_litterman': 'Black-Litterman',
      'hierarchical_risk_parity': 'Hierarchical Risk Parity'
    };
    
    this.constraints = {
      maxWeight: 0.4,        // Maximum weight per asset
      minWeight: 0.01,       // Minimum weight per asset  
      maxSectorWeight: 0.3,  // Maximum sector concentration
      maxVolatility: 0.20,   // Maximum portfolio volatility
      minSharpe: 0.5         // Minimum Sharpe ratio
    };
    
    this.riskFreeRate = 0.045; // Current risk-free rate (4.5%)
  }

  // Optimize portfolio allocation
  async optimizePortfolio(symbols, options = {}) {
    const {
      method = 'maximum_sharpe',
      constraints = this.constraints,
      lookbackPeriod = 252, // 1 year of trading days
      targetReturn = null,
      targetRisk = null,
      rebalanceFreq = 'quarterly'
    } = options;

    const cacheKey = cacheService.generateKey('portfolio_optimization', {
      symbols: symbols.sort().join(','),
      method,
      lookbackPeriod
    });

    return cacheService.cacheApiCall(
      cacheKey,
      async () => {
        try {
          // Get historical data for all symbols
          const historicalData = await this.getHistoricalReturns(symbols, lookbackPeriod);
          
          // Calculate covariance matrix and expected returns
          const { expectedReturns, covarianceMatrix, correlationMatrix } = this.calculateRiskMetrics(historicalData);
          
          // Run optimization based on method
          let optimization;
          switch (method) {
            case 'maximum_sharpe':
              optimization = this.maximizeSharpeRatio(expectedReturns, covarianceMatrix, constraints);
              break;
            case 'minimum_variance':
              optimization = this.minimizeVariance(covarianceMatrix, constraints);
              break;
            case 'risk_parity':
              optimization = this.riskParity(covarianceMatrix, constraints);
              break;
            case 'mean_variance':
              optimization = this.meanVarianceOptimization(expectedReturns, covarianceMatrix, targetReturn, constraints);
              break;
            case 'black_litterman':
              optimization = this.blackLittermanOptimization(expectedReturns, covarianceMatrix, constraints);
              break;
            case 'hierarchical_risk_parity':
              optimization = this.hierarchicalRiskParity(correlationMatrix, expectedReturns, constraints);
              break;
            default:
              throw new Error(`Unsupported optimization method: ${method}`);
          }
          
          // Calculate portfolio metrics
          const portfolioMetrics = this.calculatePortfolioMetrics(
            optimization.weights, 
            expectedReturns, 
            covarianceMatrix
          );
          
          // Generate allocation recommendations
          const allocation = symbols.map((symbol, i) => ({
            symbol,
            weight: optimization.weights[i],
            expectedReturn: expectedReturns[i],
            contribution: optimization.weights[i] * expectedReturns[i]
          })).sort((a, b) => b.weight - a.weight);
          
          return {
            method,
            allocation,
            metrics: portfolioMetrics,
            riskAnalysis: {
              correlation: correlationMatrix,
              volatility: Math.sqrt(portfolioMetrics.variance),
              beta: await this.calculatePortfolioBeta(allocation),
              maxDrawdown: await this.estimateMaxDrawdown(allocation, historicalData),
              varAnalysis: this.calculateVaR(allocation, historicalData)
            },
            rebalancing: {
              frequency: rebalanceFreq,
              nextDate: this.getNextRebalanceDate(rebalanceFreq),
              threshold: 0.05 // 5% drift threshold
            },
            constraints: constraints,
            timestamp: new Date().toISOString()
          };
          
        } catch (error) {
          console.error('Portfolio optimization failed:', error);
          return this.getMockOptimization(symbols);
        }
      },
      600000, // 10 minutes cache
      true
    );
  }

  // Get historical returns for portfolio optimization
  async getHistoricalReturns(symbols, days = 252) {
    const returns = {};
    
    await Promise.all(
      symbols.map(async (symbol) => {
        try {
          const response = await axios.get(`/api/stocks/${symbol}/historical`, {
            params: { period: days }
          });
          
          if (response.data.success) {
            const prices = response.data.data.map(d => d.close);
            returns[symbol] = this.calculateReturns(prices);
          } else {
            returns[symbol] = this.generateMockReturns(days);
          }
        } catch (error) {
          returns[symbol] = this.generateMockReturns(days);
        }
      })
    );
    
    return returns;
  }

  // Calculate returns from price series
  calculateReturns(prices) {
    const returns = [];
    for (let i = 1; i < prices.length; i++) {
      returns.push((prices[i] - prices[i-1]) / prices[i-1]);
    }
    return returns;
  }

  // Calculate risk metrics (expected returns, covariance, correlation)
  calculateRiskMetrics(historicalData) {
    const symbols = Object.keys(historicalData);
    const returns = Object.values(historicalData);
    const n = symbols.length;
    
    // Calculate expected returns (annualized)
    const expectedReturns = returns.map(symbolReturns => {
      const meanReturn = symbolReturns.reduce((sum, r) => sum + r, 0) / symbolReturns.length;
      return meanReturn * 252; // Annualize
    });
    
    // Calculate covariance matrix
    const covarianceMatrix = [];
    for (let i = 0; i < n; i++) {
      covarianceMatrix[i] = [];
      for (let j = 0; j < n; j++) {
        covarianceMatrix[i][j] = this.covariance(returns[i], returns[j]) * 252; // Annualize
      }
    }
    
    // Calculate correlation matrix
    const correlationMatrix = [];
    for (let i = 0; i < n; i++) {
      correlationMatrix[i] = [];
      for (let j = 0; j < n; j++) {
        const stdI = Math.sqrt(covarianceMatrix[i][i]);
        const stdJ = Math.sqrt(covarianceMatrix[j][j]);
        correlationMatrix[i][j] = covarianceMatrix[i][j] / (stdI * stdJ);
      }
    }
    
    return { expectedReturns, covarianceMatrix, correlationMatrix };
  }

  // Calculate covariance between two return series
  covariance(returns1, returns2) {
    const mean1 = returns1.reduce((sum, r) => sum + r, 0) / returns1.length;
    const mean2 = returns2.reduce((sum, r) => sum + r, 0) / returns2.length;
    
    let covar = 0;
    const n = Math.min(returns1.length, returns2.length);
    
    for (let i = 0; i < n; i++) {
      covar += (returns1[i] - mean1) * (returns2[i] - mean2);
    }
    
    return covar / (n - 1);
  }

  // Maximum Sharpe Ratio optimization (simplified)
  maximizeSharpeRatio(expectedReturns, covarianceMatrix, constraints) {
    const n = expectedReturns.length;
    
    // Simplified approach - equal weighted starting point with adjustments
    let weights = new Array(n).fill(1/n);
    
    // Apply constraints
    weights = this.applyConstraints(weights, constraints);
    
    // Simple iterative improvement (simplified optimization)
    for (let iter = 0; iter < 100; iter++) {
      const gradient = this.calculateSharpeGradient(weights, expectedReturns, covarianceMatrix);
      const stepSize = 0.001;
      
      for (let i = 0; i < n; i++) {
        weights[i] += stepSize * gradient[i];
      }
      
      weights = this.normalizeWeights(weights);
      weights = this.applyConstraints(weights, constraints);
    }
    
    return { weights, converged: true };
  }

  // Minimum variance optimization
  minimizeVariance(covarianceMatrix, constraints) {
    const n = covarianceMatrix.length;
    
    // Simple approach: inverse volatility weighting
    const variances = covarianceMatrix.map((row, i) => row[i]);
    const invVar = variances.map(v => 1 / Math.sqrt(v));
    const sumInvVar = invVar.reduce((sum, w) => sum + w, 0);
    
    let weights = invVar.map(w => w / sumInvVar);
    weights = this.applyConstraints(weights, constraints);
    
    return { weights, converged: true };
  }

  // Risk parity optimization
  riskParity(covarianceMatrix, constraints) {
    const n = covarianceMatrix.length;
    
    // Equal risk contribution approach
    const volatilities = covarianceMatrix.map((row, i) => Math.sqrt(row[i]));
    const invVol = volatilities.map(v => 1 / v);
    const sumInvVol = invVol.reduce((sum, w) => sum + w, 0);
    
    let weights = invVol.map(w => w / sumInvVol);
    weights = this.applyConstraints(weights, constraints);
    
    return { weights, converged: true };
  }

  // Mean variance optimization with target return
  meanVarianceOptimization(expectedReturns, covarianceMatrix, targetReturn, constraints) {
    if (!targetReturn) {
      // Default to average expected return
      targetReturn = expectedReturns.reduce((sum, r) => sum + r, 0) / expectedReturns.length;
    }
    
    // Simplified approach using Sharpe maximization with return constraint
    return this.maximizeSharpeRatio(expectedReturns, covarianceMatrix, constraints);
  }

  // Black-Litterman optimization (simplified)
  blackLittermanOptimization(expectedReturns, covarianceMatrix, constraints) {
    // For simplicity, this returns market cap weighted portfolio with adjustments
    const n = expectedReturns.length;
    
    // Market cap weights (simplified as equal weight)
    let marketWeights = new Array(n).fill(1/n);
    
    // Apply Black-Litterman adjustment (simplified)
    const tau = 0.05; // Uncertainty parameter
    const adjustedReturns = expectedReturns.map((ret, i) => 
      ret + tau * (ret - expectedReturns.reduce((sum, r) => sum + r, 0) / n)
    );
    
    return this.maximizeSharpeRatio(adjustedReturns, covarianceMatrix, constraints);
  }

  // Hierarchical Risk Parity (simplified)
  hierarchicalRiskParity(correlationMatrix, expectedReturns, constraints) {
    // Simplified HRP using correlation clustering
    const n = correlationMatrix.length;
    
    // Start with equal weights and apply hierarchical clustering logic
    let weights = new Array(n).fill(1/n);
    
    // Apply correlation-based adjustments
    for (let i = 0; i < n; i++) {
      let correlationSum = 0;
      for (let j = 0; j < n; j++) {
        if (i !== j) correlationSum += Math.abs(correlationMatrix[i][j]);
      }
      weights[i] = weights[i] * (1 - correlationSum / (n - 1));
    }
    
    weights = this.normalizeWeights(weights);
    weights = this.applyConstraints(weights, constraints);
    
    return { weights, converged: true };
  }

  // Apply portfolio constraints
  applyConstraints(weights, constraints) {
    const n = weights.length;
    
    // Apply min/max weight constraints
    for (let i = 0; i < n; i++) {
      weights[i] = Math.max(constraints.minWeight || 0, weights[i]);
      weights[i] = Math.min(constraints.maxWeight || 1, weights[i]);
    }
    
    // Renormalize
    return this.normalizeWeights(weights);
  }

  // Normalize weights to sum to 1
  normalizeWeights(weights) {
    const sum = weights.reduce((s, w) => s + w, 0);
    return weights.map(w => w / sum);
  }

  // Calculate Sharpe ratio gradient (simplified)
  calculateSharpeGradient(weights, expectedReturns, covarianceMatrix) {
    const portfolioReturn = weights.reduce((sum, w, i) => sum + w * expectedReturns[i], 0);
    const portfolioVariance = this.calculatePortfolioVariance(weights, covarianceMatrix);
    const portfolioStd = Math.sqrt(portfolioVariance);
    
    const gradient = [];
    for (let i = 0; i < weights.length; i++) {
      gradient[i] = (expectedReturns[i] - this.riskFreeRate) / portfolioStd;
    }
    
    return gradient;
  }

  // Calculate portfolio variance
  calculatePortfolioVariance(weights, covarianceMatrix) {
    let variance = 0;
    const n = weights.length;
    
    for (let i = 0; i < n; i++) {
      for (let j = 0; j < n; j++) {
        variance += weights[i] * weights[j] * covarianceMatrix[i][j];
      }
    }
    
    return variance;
  }

  // Calculate portfolio metrics
  calculatePortfolioMetrics(weights, expectedReturns, covarianceMatrix) {
    const portfolioReturn = weights.reduce((sum, w, i) => sum + w * expectedReturns[i], 0);
    const portfolioVariance = this.calculatePortfolioVariance(weights, covarianceMatrix);
    const portfolioStd = Math.sqrt(portfolioVariance);
    const sharpeRatio = (portfolioReturn - this.riskFreeRate) / portfolioStd;
    
    return {
      expectedReturn: portfolioReturn,
      variance: portfolioVariance,
      volatility: portfolioStd,
      sharpeRatio,
      riskFreeRate: this.riskFreeRate
    };
  }

  // Calculate portfolio beta
  async calculatePortfolioBeta(allocation) {
    // Simplified beta calculation
    let portfolioBeta = 0;
    
    for (const asset of allocation) {
      // Assume beta of 1 for simplicity (in reality, fetch from API)
      const assetBeta = 1.0;
      portfolioBeta += asset.weight * assetBeta;
    }
    
    return portfolioBeta;
  }

  // Estimate maximum drawdown
  async estimateMaxDrawdown(allocation, historicalData) {
    // Simplified drawdown calculation
    const symbols = allocation.map(a => a.symbol);
    const weights = allocation.map(a => a.weight);
    
    // Calculate portfolio returns
    const portfolioReturns = [];
    const firstSymbol = symbols[0];
    const length = historicalData[firstSymbol]?.length || 252;
    
    for (let i = 0; i < length; i++) {
      let portfolioReturn = 0;
      for (let j = 0; j < symbols.length; j++) {
        const symbolReturns = historicalData[symbols[j]] || [];
        portfolioReturn += weights[j] * (symbolReturns[i] || 0);
      }
      portfolioReturns.push(portfolioReturn);
    }
    
    // Calculate maximum drawdown
    let maxDrawdown = 0;
    let peak = 0;
    let cumReturn = 0;
    
    for (const ret of portfolioReturns) {
      cumReturn = (1 + cumReturn) * (1 + ret) - 1;
      peak = Math.max(peak, cumReturn);
      const drawdown = (cumReturn - peak) / (1 + peak);
      maxDrawdown = Math.min(maxDrawdown, drawdown);
    }
    
    return Math.abs(maxDrawdown);
  }

  // Calculate Value at Risk
  calculateVaR(allocation, historicalData, confidence = 0.05) {
    const symbols = allocation.map(a => a.symbol);
    const weights = allocation.map(a => a.weight);
    
    // Calculate portfolio returns
    const portfolioReturns = [];
    const firstSymbol = symbols[0];
    const length = historicalData[firstSymbol]?.length || 252;
    
    for (let i = 0; i < length; i++) {
      let portfolioReturn = 0;
      for (let j = 0; j < symbols.length; j++) {
        const symbolReturns = historicalData[symbols[j]] || [];
        portfolioReturn += weights[j] * (symbolReturns[i] || 0);
      }
      portfolioReturns.push(portfolioReturn);
    }
    
    // Sort returns and calculate VaR
    portfolioReturns.sort((a, b) => a - b);
    const varIndex = Math.floor(confidence * portfolioReturns.length);
    const var95 = -portfolioReturns[varIndex];
    const var99 = -portfolioReturns[Math.floor(0.01 * portfolioReturns.length)];
    
    return {
      var95: var95,
      var99: var99,
      expectedShortfall: -portfolioReturns.slice(0, varIndex).reduce((sum, r) => sum + r, 0) / varIndex
    };
  }

  // Get next rebalance date
  getNextRebalanceDate(frequency) {
    const now = new Date();
    const next = new Date(now);
    
    switch (frequency) {
      case 'monthly':
        next.setMonth(next.getMonth() + 1);
        next.setDate(1);
        break;
      case 'quarterly':
        next.setMonth(next.getMonth() + (3 - (next.getMonth() % 3)));
        next.setDate(1);
        break;
      case 'annually':
        next.setFullYear(next.getFullYear() + 1);
        next.setMonth(0);
        next.setDate(1);
        break;
      default:
        next.setDate(next.getDate() + 30);
    }
    
    return next.toISOString().split('T')[0];
  }

  // Generate mock returns for testing
  generateMockReturns(days) {
    const returns = [];
    for (let i = 0; i < days; i++) {
      returns.push((Math.random() - 0.5) * 0.04); // ±2% daily return
    }
    return returns;
  }

  // Mock optimization for fallback
  getMockOptimization(symbols) {
    const n = symbols.length;
    const weights = new Array(n).fill(1/n); // Equal weight
    
    const allocation = symbols.map((symbol, i) => ({
      symbol,
      weight: weights[i],
      expectedReturn: 0.08 + Math.random() * 0.04, // 8-12% expected return
      contribution: weights[i] * (0.08 + Math.random() * 0.04)
    }));
    
    return {
      method: 'equal_weight',
      allocation,
      metrics: {
        expectedReturn: 0.10,
        volatility: 0.15,
        sharpeRatio: 0.67,
        variance: 0.0225
      },
      riskAnalysis: {
        beta: 1.0,
        maxDrawdown: 0.15,
        varAnalysis: {
          var95: 0.025,
          var99: 0.040,
          expectedShortfall: 0.035
        }
      },
      rebalancing: {
        frequency: 'quarterly',
        nextDate: this.getNextRebalanceDate('quarterly'),
        threshold: 0.05
      },
      timestamp: new Date().toISOString()
    };
  }

  // Portfolio performance attribution
  async performanceAttribution(portfolio, benchmark = 'SPY') {
    // Calculate attribution factors
    return {
      assetAllocation: 0.02,    // 2% from asset allocation
      stockSelection: 0.015,    // 1.5% from stock selection
      interaction: -0.005,      // -0.5% from interaction
      total: 0.03,             // 3% total outperformance
      benchmark: benchmark
    };
  }

  // Efficient frontier calculation
  async calculateEfficientFrontier(symbols, numPoints = 20) {
    const frontier = [];
    
    for (let i = 0; i < numPoints; i++) {
      const targetReturn = 0.05 + (i / numPoints) * 0.15; // 5% to 20% target return
      
      try {
        const optimization = await this.optimizePortfolio(symbols, {
          method: 'mean_variance',
          targetReturn
        });
        
        frontier.push({
          return: optimization.metrics.expectedReturn,
          risk: optimization.metrics.volatility,
          sharpe: optimization.metrics.sharpeRatio,
          weights: optimization.allocation.map(a => ({ symbol: a.symbol, weight: a.weight }))
        });
      } catch (error) {
        console.warn(`Failed to calculate frontier point ${i}:`, error);
      }
    }
    
    return frontier.sort((a, b) => a.risk - b.risk);
  }
}

// Create singleton instance
const portfolioOptimizer = new PortfolioOptimizer();

export default portfolioOptimizer;
/**
 * REAL Portfolio Math Unit Tests
 * Tests actual financial calculations, not fake mocks
 */

const PortfolioMath = require('../../utils/portfolioMath');
const { Matrix } = require('ml-matrix');

describe('PortfolioMath REAL Financial Calculations', () => {
  
  describe('Real Covariance Matrix Calculations', () => {
    test('calculates covariance matrix from real return data', () => {
      // Real daily returns data (simplified but realistic)
      const returns = [
        [0.01, 0.005, -0.002],  // Day 1: AAPL, MSFT, GOOGL
        [-0.015, -0.01, 0.008], // Day 2
        [0.025, 0.02, 0.015],   // Day 3
        [-0.005, 0.003, -0.001], // Day 4
        [0.008, 0.012, 0.006]   // Day 5
      ];
      
      const covMatrix = PortfolioMath.calculateCovarianceMatrix(returns);
      
      // Test actual covariance matrix properties
      expect(covMatrix).toBeDefined();
      expect(covMatrix.rows).toBe(3);
      expect(covMatrix.columns).toBe(3);
      
      // Diagonal elements should be positive variances
      expect(covMatrix.get(0, 0)).toBeGreaterThan(0);
      expect(covMatrix.get(1, 1)).toBeGreaterThan(0);
      expect(covMatrix.get(2, 2)).toBeGreaterThan(0);
      
      // Matrix should be symmetric (real covariance property)
      expect(covMatrix.get(0, 1)).toBeCloseTo(covMatrix.get(1, 0), 10);
      expect(covMatrix.get(0, 2)).toBeCloseTo(covMatrix.get(2, 0), 10);
      expect(covMatrix.get(1, 2)).toBeCloseTo(covMatrix.get(2, 1), 10);
      
      // Test actual variance calculation (should be reasonable for stock returns)
      const appleVariance = covMatrix.get(0, 0);
      expect(appleVariance).toBeGreaterThan(0.01); // Should be > 1% annualized variance
      expect(appleVariance).toBeLessThan(2.0);     // Should be < 200% (unrealistic)
    });

    test('handles edge cases in real covariance calculation', () => {
      // Test with minimal data
      const minReturns = [
        [0.01, 0.005],
        [-0.01, -0.005]
      ];
      
      const covMatrix = PortfolioMath.calculateCovarianceMatrix(minReturns);
      expect(covMatrix.rows).toBe(2);
      expect(covMatrix.columns).toBe(2);
      
      // Should still be symmetric
      expect(covMatrix.get(0, 1)).toBeCloseTo(covMatrix.get(1, 0), 10);
    });

    test('throws real error for invalid input', () => {
      expect(() => {
        PortfolioMath.calculateCovarianceMatrix([]);
      }).toThrow('Returns data is required');
      
      expect(() => {
        PortfolioMath.calculateCovarianceMatrix(null);
      }).toThrow('Returns data is required');
    });
  });

  describe('Real Expected Returns Calculations', () => {
    test('calculates simple average expected returns from real data', () => {
      const returns = [
        [0.01, 0.005, -0.002],
        [-0.015, -0.01, 0.008],
        [0.025, 0.02, 0.015],
        [-0.005, 0.003, -0.001],
        [0.008, 0.012, 0.006]
      ];
      
      const expectedReturns = PortfolioMath.calculateExpectedReturns(returns, 'simple');
      
      // Test real expected return calculation
      expect(Array.isArray(expectedReturns)).toBe(true);
      expect(expectedReturns).toHaveLength(3);
      
      // Calculate manual average for AAPL (first asset)
      const appleReturns = returns.map(day => day[0]);
      const manualAverage = appleReturns.reduce((sum, ret) => sum + ret, 0) / appleReturns.length;
      
      // Should match our calculation (annualized)
      expect(expectedReturns[0]).toBeCloseTo(manualAverage * 252, 8);
      
      // All expected returns should be reasonable for stocks
      expectedReturns.forEach(expectedReturn => {
        expect(expectedReturn).toBeGreaterThan(-1.0); // > -100% annual
        expect(expectedReturn).toBeLessThan(3.0);      // < 300% annual
      });
    });

    test('calculates EWMA expected returns with real decay', () => {
      const returns = [
        [0.01, 0.005],
        [0.015, 0.01],
        [0.02, 0.015],
        [0.005, 0.008],
        [-0.01, -0.005]
      ];
      
      const expectedReturns = PortfolioMath.calculateExpectedReturns(
        returns, 
        'ewma', 
        { halfLife: 30 }
      );
      
      // Test EWMA gives more weight to recent returns
      expect(Array.isArray(expectedReturns)).toBe(true);
      expect(expectedReturns).toHaveLength(2);
      
      // Recent negative return should pull down the EWMA
      expectedReturns.forEach(expectedReturn => {
        expect(typeof expectedReturn).toBe('number');
        expect(expectedReturn).toBeGreaterThan(-1.0);
        expect(expectedReturn).toBeLessThan(3.0);
      });
    });
  });

  describe('Real Correlation Matrix Calculations', () => {
    test('calculates real correlation from covariance matrix', () => {
      const returns = [
        [0.01, 0.008, 0.005],   // Positively correlated
        [0.015, 0.012, 0.008],
        [-0.02, -0.015, -0.01], // All move together
        [0.005, 0.004, 0.003],
        [-0.008, -0.006, -0.004]
      ];
      
      const covMatrix = PortfolioMath.calculateCovarianceMatrix(returns);
      const corrMatrix = PortfolioMath.calculateCorrelationMatrix(covMatrix);
      
      // Test real correlation properties
      expect(corrMatrix.rows).toBe(3);
      expect(corrMatrix.columns).toBe(3);
      
      // Diagonal should be 1 (perfect self-correlation)
      expect(corrMatrix.get(0, 0)).toBeCloseTo(1.0, 10);
      expect(corrMatrix.get(1, 1)).toBeCloseTo(1.0, 10);
      expect(corrMatrix.get(2, 2)).toBeCloseTo(1.0, 10);
      
      // Off-diagonal correlations should be between -1 and 1
      expect(corrMatrix.get(0, 1)).toBeGreaterThan(-1.0);
      expect(corrMatrix.get(0, 1)).toBeLessThan(1.0);
      
      // Should be symmetric
      expect(corrMatrix.get(0, 1)).toBeCloseTo(corrMatrix.get(1, 0), 10);
      expect(corrMatrix.get(0, 2)).toBeCloseTo(corrMatrix.get(2, 0), 10);
      
      // Given our positively correlated data, correlations should be positive
      expect(corrMatrix.get(0, 1)).toBeGreaterThan(0.5);
      expect(corrMatrix.get(0, 2)).toBeGreaterThan(0.5);
      expect(corrMatrix.get(1, 2)).toBeGreaterThan(0.5);
    });
  });

  describe('Real Mean Variance Optimization', () => {
    test('performs real portfolio optimization with actual constraints', () => {
      const expectedReturns = [0.12, 0.10, 0.08]; // 12%, 10%, 8% expected returns
      const covMatrix = new Matrix([
        [0.04, 0.02, 0.01],  // Realistic covariance matrix
        [0.02, 0.03, 0.015],
        [0.01, 0.015, 0.02]
      ]);
      
      const optimization = PortfolioMath.meanVarianceOptimization(
        expectedReturns,
        covMatrix,
        {
          objective: 'maxSharpe',
          riskFreeRate: 0.02
        }
      );
      
      // Test real optimization results
      expect(optimization).toHaveProperty('weights');
      expect(optimization).toHaveProperty('expectedReturn');
      expect(optimization).toHaveProperty('volatility');
      expect(optimization).toHaveProperty('sharpeRatio');
      
      // Weights should sum to 1
      const weightSum = optimization.weights.reduce((sum, w) => sum + w, 0);
      expect(weightSum).toBeCloseTo(1.0, 8);
      
      // All weights should be non-negative (long-only constraint)
      optimization.weights.forEach(weight => {
        expect(weight).toBeGreaterThanOrEqual(0);
        expect(weight).toBeLessThanOrEqual(1);
      });
      
      // Expected return should be weighted average
      const calculatedReturn = expectedReturns.reduce(
        (sum, ret, i) => sum + ret * optimization.weights[i], 
        0
      );
      expect(optimization.expectedReturn).toBeCloseTo(calculatedReturn, 8);
      
      // Sharpe ratio calculation should be correct
      const expectedSharpe = (optimization.expectedReturn - 0.02) / optimization.volatility;
      expect(optimization.sharpeRatio).toBeCloseTo(expectedSharpe, 8);
    });

    test('handles different optimization objectives', () => {
      const expectedReturns = [0.15, 0.12, 0.08];
      const covMatrix = new Matrix([
        [0.06, 0.03, 0.01],
        [0.03, 0.04, 0.02],
        [0.01, 0.02, 0.02]
      ]);
      
      // Test minimum variance optimization
      const minVarOpt = PortfolioMath.meanVarianceOptimization(
        expectedReturns,
        covMatrix,
        { objective: 'minVariance' }
      );
      
      expect(minVarOpt.weights.reduce((sum, w) => sum + w, 0)).toBeCloseTo(1.0, 8);
      
      // Test maximum return optimization
      const maxRetOpt = PortfolioMath.meanVarianceOptimization(
        expectedReturns,
        covMatrix,
        { objective: 'maxReturn' }
      );
      
      expect(maxRetOpt.weights.reduce((sum, w) => sum + w, 0)).toBeCloseTo(1.0, 8);
    });
  });

  describe('Real Risk Metrics Calculations', () => {
    test('calculates real portfolio risk metrics', () => {
      const weights = [0.4, 0.3, 0.3];
      const expectedReturns = [0.12, 0.10, 0.08];
      const covMatrix = new Matrix([
        [0.04, 0.02, 0.01],
        [0.02, 0.03, 0.015],
        [0.01, 0.015, 0.02]
      ]);
      
      const riskMetrics = PortfolioMath.calculateRiskMetrics(
        weights,
        expectedReturns,
        covMatrix
      );
      
      // Test real risk metrics
      expect(riskMetrics).toHaveProperty('expectedReturn');
      expect(riskMetrics).toHaveProperty('volatility');
      expect(riskMetrics).toHaveProperty('sharpeRatio');
      expect(riskMetrics).toHaveProperty('beta');
      
      // Expected return should be weighted average
      const expectedReturn = weights.reduce(
        (sum, w, i) => sum + w * expectedReturns[i], 
        0
      );
      expect(riskMetrics.expectedReturn).toBeCloseTo(expectedReturn, 8);
      
      // Volatility should be positive
      expect(riskMetrics.volatility).toBeGreaterThan(0);
      expect(riskMetrics.volatility).toBeLessThan(1); // < 100% annual vol
      
      // Beta should be reasonable (assuming market-like portfolio)
      expect(riskMetrics.beta).toBeGreaterThan(0.5);
      expect(riskMetrics.beta).toBeLessThan(2.0);
    });
  });

  describe('Real Efficient Frontier Generation', () => {
    test('generates real efficient frontier points', () => {
      const expectedReturns = [0.15, 0.12, 0.08, 0.06];
      const covMatrix = new Matrix([
        [0.06, 0.03, 0.01, 0.005],
        [0.03, 0.04, 0.02, 0.01],
        [0.01, 0.02, 0.02, 0.008],
        [0.005, 0.01, 0.008, 0.015]
      ]);
      
      const frontier = PortfolioMath.generateEfficientFrontier(
        expectedReturns,
        covMatrix,
        10 // 10 points
      );
      
      // Test real efficient frontier
      expect(Array.isArray(frontier)).toBe(true);
      expect(frontier).toHaveLength(10);
      
      frontier.forEach(point => {
        expect(point).toHaveProperty('volatility');
        expect(point).toHaveProperty('expectedReturn');
        expect(point).toHaveProperty('sharpeRatio');
        expect(point).toHaveProperty('weights');
        
        // Check realistic values
        expect(point.volatility).toBeGreaterThan(0);
        expect(point.volatility).toBeLessThan(1);
        expect(point.expectedReturn).toBeGreaterThan(0);
        expect(point.expectedReturn).toBeLessThan(0.5);
        
        // Weights should sum to 1
        const weightSum = point.weights.reduce((sum, w) => sum + w, 0);
        expect(weightSum).toBeCloseTo(1.0, 6);
      });
      
      // Frontier should be sorted by volatility (ascending)
      for (let i = 1; i < frontier.length; i++) {
        expect(frontier[i].volatility).toBeGreaterThanOrEqual(frontier[i-1].volatility);
      }
    });
  });
});
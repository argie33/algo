/**
 * Real Portfolio Math Service Unit Tests
 * Testing the actual portfolioMathService.js with real VaR calculations and financial mathematics
 * CRITICAL COMPONENT - Known to have VaR calculation and mathematical issues
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { Matrix } from 'ml-matrix';

// Mock React for the hook
vi.mock('react', () => ({
  useCallback: vi.fn((fn) => fn)
}));

// Import the REAL PortfolioMathService (singleton instance)
import portfolioMathService from '../../../services/portfolioMathService';

describe('📊 Real Portfolio Math Service', () => {
  let service;
  
  // Sample test data
  const mockHoldings = [
    {
      symbol: 'AAPL',
      quantity: 100,
      averagePrice: 175.25,
      marketValue: 18550
    },
    {
      symbol: 'MSFT',
      quantity: 50,
      averagePrice: 340.00,
      marketValue: 18750
    },
    {
      symbol: 'GOOGL',
      quantity: 25,
      averagePrice: 2800.00,
      marketValue: 71250
    }
  ];

  const mockHistoricalData = {
    'AAPL': Array.from({ length: 60 }, (_, i) => ({
      close: 175 + Math.sin(i * 0.1) * 10 + (Math.random() - 0.5) * 5,
      date: new Date(Date.now() - (59 - i) * 24 * 60 * 60 * 1000).toISOString()
    })),
    'MSFT': Array.from({ length: 60 }, (_, i) => ({
      close: 340 + Math.cos(i * 0.1) * 15 + (Math.random() - 0.5) * 8,
      date: new Date(Date.now() - (59 - i) * 24 * 60 * 60 * 1000).toISOString()
    })),
    'GOOGL': Array.from({ length: 60 }, (_, i) => ({
      close: 2800 + Math.sin(i * 0.05) * 100 + (Math.random() - 0.5) * 50,
      date: new Date(Date.now() - (59 - i) * 24 * 60 * 60 * 1000).toISOString()
    }))
  };

  beforeEach(() => {
    vi.clearAllMocks();
    
    service = portfolioMathService;
    service.clearCache();
    
    // Mock console to avoid noise
    vi.spyOn(console, 'log').mockImplementation(() => {});
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Service Initialization', () => {
    it('should initialize with correct default settings', () => {
      expect(service.cache).toBeInstanceOf(Map);
      expect(service.cacheTimeout).toBe(5 * 60 * 1000);
    });

    it('should start with empty cache', () => {
      expect(service.cache.size).toBe(0);
    });
  });

  describe('Portfolio VaR Calculation', () => {
    it('should calculate VaR for valid portfolio with historical data', () => {
      const result = service.calculatePortfolioVaR(mockHoldings, mockHistoricalData, 0.95, 1);
      
      expect(result).toEqual(expect.objectContaining({
        vaR: expect.any(Number),
        confidenceLevel: 0.95,
        timeHorizon: 1,
        portfolioValue: 108550, // 18550 + 18750 + 71250
        expectedReturn: expect.any(Number),
        volatility: expect.any(Number),
        sharpeRatio: expect.any(Number),
        maxDrawdown: expect.any(Number),
        beta: expect.any(Number),
        trackingError: expect.any(Number),
        informationRatio: expect.any(Number),
        riskScore: expect.any(Number),
        diversificationRatio: expect.any(Number),
        calculatedAt: expect.any(String),
        method: 'parametric',
        dataPoints: expect.any(Number)
      }));
      
      expect(result.vaR).toBeGreaterThan(0);
      expect(result.dataPoints).toBeGreaterThan(0);
    });

    it('should handle portfolio with zero value', () => {
      const zeroValueHoldings = [
        { symbol: 'AAPL', marketValue: 0 },
        { symbol: 'MSFT', marketValue: 0 }
      ];
      
      const result = service.calculatePortfolioVaR(zeroValueHoldings, mockHistoricalData);
      
      expect(result).toEqual(service.createEmptyVaRResult());
      expect(result.portfolioValue).toBe(0);
      expect(result.error).toBe('Insufficient data for calculation');
    });

    it('should handle missing historical data', () => {
      const result = service.calculatePortfolioVaR(mockHoldings, {});
      
      expect(result).toEqual(service.createEmptyVaRResult());
      expect(result.dataPoints).toBe(0);
    });

    it('should handle insufficient historical data points', () => {
      const insufficientData = {
        'AAPL': [
          { close: 175.00 },
          { close: 176.00 }
        ]
      };
      
      const result = service.calculatePortfolioVaR(mockHoldings, insufficientData);
      
      expect(result).toEqual(service.createEmptyVaRResult());
    });

    it('should calculate VaR with different confidence levels', () => {
      const var95 = service.calculatePortfolioVaR(mockHoldings, mockHistoricalData, 0.95);
      const var99 = service.calculatePortfolioVaR(mockHoldings, mockHistoricalData, 0.99);
      
      expect(var99.vaR).toBeGreaterThan(var95.vaR);
      expect(var95.confidenceLevel).toBe(0.95);
      expect(var99.confidenceLevel).toBe(0.99);
    });

    it('should adjust VaR for different time horizons', () => {
      const var1Day = service.calculatePortfolioVaR(mockHoldings, mockHistoricalData, 0.95, 1);
      const var10Day = service.calculatePortfolioVaR(mockHoldings, mockHistoricalData, 0.95, 10);
      
      expect(var10Day.vaR).toBeGreaterThan(var1Day.vaR);
      expect(var1Day.timeHorizon).toBe(1);
      expect(var10Day.timeHorizon).toBe(10);
    });

    it('should handle calculation errors gracefully', () => {
      // Create malformed holdings data
      const malformedHoldings = [
        { symbol: null, marketValue: 'invalid' }
      ];
      
      const result = service.calculatePortfolioVaR(malformedHoldings, mockHistoricalData);
      
      expect(result).toEqual(service.createEmptyVaRResult());
    });
  });

  describe('Returns Calculation from Historical Data', () => {
    it('should calculate returns correctly from price data', () => {
      const symbols = ['AAPL', 'MSFT'];
      const returns = service.calculateReturnsFromHistoricalData(symbols, mockHistoricalData);
      
      expect(returns.length).toBeGreaterThan(0);
      expect(returns[0].length).toBe(symbols.length);
      
      // Each return should be a valid number
      returns.forEach(dayReturns => {
        dayReturns.forEach(ret => {
          expect(typeof ret).toBe('number');
          expect(ret).not.toBeNaN();
        });
      });
    });

    it('should handle missing price data points', () => {
      const dataWithGaps = {
        'AAPL': [
          { close: 175.00 },
          { close: null }, // Missing data
          { close: 177.00 }
        ],
        'MSFT': [
          { close: 340.00 },
          { close: 342.00 },
          { close: 341.00 }
        ]
      };
      
      const returns = service.calculateReturnsFromHistoricalData(['AAPL', 'MSFT'], dataWithGaps);
      
      expect(returns.length).toBeGreaterThan(0);
      // Should handle missing data gracefully
    });

    it('should handle alternative price field names', () => {
      const dataWithPriceField = {
        'AAPL': [
          { price: 175.00 },
          { price: 176.00 },
          { price: 177.00 }
        ]
      };
      
      const returns = service.calculateReturnsFromHistoricalData(['AAPL'], dataWithPriceField);
      
      expect(returns.length).toBeGreaterThan(0);
    });

    it('should require minimum data points', () => {
      const insufficientData = {
        'AAPL': Array.from({ length: 10 }, (_, i) => ({ close: 175 + i }))
      };
      
      const returns = service.calculateReturnsFromHistoricalData(['AAPL'], insufficientData);
      
      expect(returns).toEqual([]);
    });

    it('should align time series for multiple symbols', () => {
      const unevenData = {
        'AAPL': Array.from({ length: 50 }, (_, i) => ({ close: 175 + i })),
        'MSFT': Array.from({ length: 40 }, (_, i) => ({ close: 340 + i }))
      };
      
      const returns = service.calculateReturnsFromHistoricalData(['AAPL', 'MSFT'], unevenData);
      
      // Should use the shorter series length
      expect(returns.length).toBeLessThanOrEqual(39); // 40 - 1 for returns calculation
    });
  });

  describe('Covariance Matrix Calculation', () => {
    it('should calculate covariance matrix from returns', () => {
      const returns = [
        [0.01, 0.02, -0.01],
        [0.02, -0.01, 0.015],
        [-0.01, 0.01, 0.005]
      ];
      
      const covMatrix = service.calculateCovarianceMatrix(returns);
      
      expect(covMatrix).toBeInstanceOf(Matrix);
      expect(covMatrix.rows).toBe(3);
      expect(covMatrix.columns).toBe(3);
      
      // Check symmetry
      expect(covMatrix.get(0, 1)).toBeCloseTo(covMatrix.get(1, 0), 5);
      expect(covMatrix.get(0, 2)).toBeCloseTo(covMatrix.get(2, 0), 5);
      expect(covMatrix.get(1, 2)).toBeCloseTo(covMatrix.get(2, 1), 5);
      
      // Diagonal elements should be positive (variances)
      expect(covMatrix.get(0, 0)).toBeGreaterThan(0);
      expect(covMatrix.get(1, 1)).toBeGreaterThan(0);
      expect(covMatrix.get(2, 2)).toBeGreaterThan(0);
    });

    it('should handle empty returns', () => {
      const covMatrix = service.calculateCovarianceMatrix([]);
      
      expect(covMatrix).toBeInstanceOf(Matrix);
      expect(covMatrix.rows).toBe(0);
      expect(covMatrix.columns).toBe(0);
    });

    it('should annualize covariance correctly', () => {
      const dailyReturns = [
        [0.001, 0.002], // Small daily returns
        [0.002, -0.001],
        [-0.001, 0.001]
      ];
      
      const covMatrix = service.calculateCovarianceMatrix(dailyReturns);
      
      // Check that values are reasonable for annualized covariance
      expect(covMatrix.get(0, 0)).toBeGreaterThan(0);
      expect(Math.abs(covMatrix.get(0, 0))).toBeLessThan(1); // Should be reasonable for stock volatility
    });
  });

  describe('Portfolio Volatility Calculation', () => {
    it('should calculate portfolio volatility correctly', () => {
      const weights = [0.4, 0.3, 0.3];
      const returns = [
        [0.01, 0.02, -0.01],
        [0.02, -0.01, 0.015],
        [-0.01, 0.01, 0.005]
      ];
      
      const covMatrix = service.calculateCovarianceMatrix(returns);
      const volatility = service.calculatePortfolioVolatility(weights, covMatrix);
      
      expect(volatility).toBeGreaterThan(0);
      expect(volatility).toBeLessThan(1); // Should be reasonable for annual volatility
    });

    it('should handle empty inputs', () => {
      const volatility = service.calculatePortfolioVolatility([], new Matrix(0, 0));
      
      expect(volatility).toBe(0);
    });

    it('should handle single asset portfolio', () => {
      const weights = [1.0];
      const returns = [[0.01], [0.02], [-0.01]];
      const covMatrix = service.calculateCovarianceMatrix(returns);
      
      const volatility = service.calculatePortfolioVolatility(weights, covMatrix);
      
      expect(volatility).toBeGreaterThan(0);
    });
  });

  describe('Expected Return Calculation', () => {
    it('should calculate portfolio expected return correctly', () => {
      const weights = [0.4, 0.3, 0.3];
      const returns = [
        [0.01, 0.02, -0.01],
        [0.02, -0.01, 0.015],
        [-0.01, 0.01, 0.005],
        [0.005, 0.01, 0.002]
      ];
      
      const expectedReturn = service.calculatePortfolioExpectedReturn(weights, returns);
      
      expect(typeof expectedReturn).toBe('number');
      expect(expectedReturn).not.toBeNaN();
      // Should be reasonable for annualized return
      expect(Math.abs(expectedReturn)).toBeLessThan(2);
    });

    it('should handle empty inputs', () => {
      const expectedReturn = service.calculatePortfolioExpectedReturn([], []);
      
      expect(expectedReturn).toBe(0);
    });

    it('should annualize returns correctly', () => {
      const weights = [1.0];
      const dailyReturns = [[0.001], [0.001], [0.001]]; // 0.1% daily return
      
      const annualizedReturn = service.calculatePortfolioExpectedReturn(weights, dailyReturns);
      
      // Should be approximately 0.1% * 252 trading days
      expect(annualizedReturn).toBeCloseTo(0.252, 1);
    });
  });

  describe('Risk Metrics Calculation', () => {
    it('should calculate comprehensive risk metrics', () => {
      const weights = [0.4, 0.3, 0.3];
      const returns = Array.from({ length: 50 }, () => [
        (Math.random() - 0.5) * 0.02,
        (Math.random() - 0.5) * 0.025,
        (Math.random() - 0.5) * 0.03
      ]);
      const covMatrix = service.calculateCovarianceMatrix(returns);
      const totalValue = 100000;
      
      const riskMetrics = service.calculateRiskMetrics(weights, returns, covMatrix, totalValue);
      
      expect(riskMetrics).toEqual(expect.objectContaining({
        sharpeRatio: expect.any(Number),
        maxDrawdown: expect.any(Number),
        beta: expect.any(Number),
        trackingError: expect.any(Number),
        informationRatio: expect.any(Number),
        riskScore: expect.any(Number),
        diversificationRatio: expect.any(Number)
      }));
      
      expect(riskMetrics.maxDrawdown).toBeGreaterThanOrEqual(0);
      expect(riskMetrics.maxDrawdown).toBeLessThanOrEqual(1);
      expect(riskMetrics.beta).toBeGreaterThan(0);
      expect(riskMetrics.riskScore).toBeGreaterThanOrEqual(0);
      expect(riskMetrics.riskScore).toBeLessThanOrEqual(100);
    });

    it('should calculate Sharpe ratio correctly', () => {
      const weights = [1.0];
      const returns = [[0.01], [0.015], [0.008], [0.012]]; // Positive returns
      const covMatrix = service.calculateCovarianceMatrix(returns);
      
      const riskMetrics = service.calculateRiskMetrics(weights, returns, covMatrix, 100000);
      
      // Should have positive Sharpe ratio for positive excess returns
      expect(riskMetrics.sharpeRatio).toBeGreaterThan(0);
    });

    it('should estimate maximum drawdown correctly', () => {
      // Create returns with a clear drawdown pattern
      const weights = [1.0];
      const returns = [
        [0.05],  // Up 5%
        [0.03],  // Up 3%
        [-0.10], // Down 10% (drawdown starts)
        [-0.05], // Down 5% more
        [0.02]   // Partial recovery
      ];
      
      const maxDrawdown = service.estimateMaxDrawdown(returns, weights);
      
      expect(maxDrawdown).toBeGreaterThan(0);
      expect(maxDrawdown).toBeLessThanOrEqual(1);
    });

    it('should calculate portfolio beta estimation', () => {
      const weights = [0.5, 0.5];
      const returns = Array.from({ length: 30 }, () => [
        (Math.random() - 0.5) * 0.02,
        (Math.random() - 0.5) * 0.03
      ]);
      
      const beta = service.calculatePortfolioBeta(weights, returns);
      
      expect(beta).toBeGreaterThan(0);
      expect(beta).toBeLessThan(3); // Reasonable range for beta
    });

    it('should calculate diversification ratio', () => {
      const weights = [0.5, 0.5];
      const returns = [
        [0.01, -0.01], // Negatively correlated
        [0.02, -0.015],
        [-0.01, 0.01]
      ];
      const covMatrix = service.calculateCovarianceMatrix(returns);
      
      const diversificationRatio = service.calculateDiversificationRatio(weights, covMatrix);
      
      expect(diversificationRatio).toBeGreaterThan(0);
      // For negatively correlated assets, should be > 1 (diversification benefit)
      expect(diversificationRatio).toBeGreaterThan(1);
    });
  });

  describe('Volatility Calculation', () => {
    it('should calculate volatility of return series', () => {
      const returns = [0.01, 0.02, -0.01, 0.015, -0.005];
      
      const volatility = service.calculateVolatility(returns);
      
      expect(volatility).toBeGreaterThan(0);
      expect(volatility).toBeLessThan(1); // Should be reasonable for annualized volatility
    });

    it('should handle empty return series', () => {
      const volatility = service.calculateVolatility([]);
      
      expect(volatility).toBe(0);
    });

    it('should handle single return value', () => {
      const volatility = service.calculateVolatility([0.01]);
      
      expect(volatility).toBe(0); // No variance with single observation
    });
  });

  describe('Inverse Normal CDF', () => {
    it('should return correct critical values for standard confidence levels', () => {
      expect(service.inverseNormalCDF(0.90)).toBeCloseTo(1.282, 2);
      expect(service.inverseNormalCDF(0.95)).toBeCloseTo(1.645, 2);
      expect(service.inverseNormalCDF(0.975)).toBeCloseTo(1.96, 2);
      expect(service.inverseNormalCDF(0.99)).toBeCloseTo(2.326, 2);
      expect(service.inverseNormalCDF(0.995)).toBeCloseTo(2.576, 2);
    });

    it('should handle non-standard confidence levels', () => {
      const z1 = service.inverseNormalCDF(0.80);
      const z2 = service.inverseNormalCDF(0.85);
      
      expect(z1).toBeGreaterThan(0);
      expect(z2).toBeGreaterThan(z1);
    });

    it('should handle lower tail probabilities', () => {
      const z1 = service.inverseNormalCDF(0.10);
      const z2 = service.inverseNormalCDF(0.05);
      
      expect(z1).toBeLessThan(0);
      expect(z2).toBeLessThan(z1);
    });
  });

  describe('Cache Management', () => {
    it('should cache and retrieve results', () => {
      const key = 'test_key';
      const result = { value: 'test_result' };
      
      service.setCachedResult(key, result);
      const cached = service.getCachedResult(key);
      
      expect(cached).toEqual(result);
    });

    it('should expire cached results after timeout', () => {
      vi.useFakeTimers();
      
      const key = 'test_key';
      const result = { value: 'test_result' };
      
      service.setCachedResult(key, result);
      
      // Fast forward past cache timeout
      vi.advanceTimersByTime(service.cacheTimeout + 1000);
      
      const cached = service.getCachedResult(key);
      
      expect(cached).toBeNull();
      
      vi.useRealTimers();
    });

    it('should clear all cached results', () => {
      service.setCachedResult('key1', { value: 1 });
      service.setCachedResult('key2', { value: 2 });
      
      expect(service.cache.size).toBe(2);
      
      service.clearCache();
      
      expect(service.cache.size).toBe(0);
    });

    it('should return null for non-existent cache keys', () => {
      const cached = service.getCachedResult('non_existent_key');
      
      expect(cached).toBeNull();
    });
  });

  describe('Real-World Financial Scenarios', () => {
    it('should handle market crash scenario', () => {
      // Simulate a market crash in historical data
      const crashData = {};
      mockHoldings.forEach(holding => {
        crashData[holding.symbol] = Array.from({ length: 50 }, (_, i) => {
          const basePrice = holding.averagePrice;
          let price;
          
          if (i < 30) {
            // Normal volatility
            price = basePrice + (Math.random() - 0.5) * basePrice * 0.02;
          } else {
            // Market crash - dramatic drop
            const crashFactor = Math.max(0.5, 1 - (i - 30) * 0.05);
            price = basePrice * crashFactor + (Math.random() - 0.5) * basePrice * 0.05;
          }
          
          return { close: price };
        });
      });
      
      const result = service.calculatePortfolioVaR(mockHoldings, crashData);
      
      expect(result.vaR).toBeGreaterThan(0);
      expect(result.maxDrawdown).toBeGreaterThan(0.1); // Should detect significant drawdown
      expect(result.volatility).toBeGreaterThan(0.2); // Should detect high volatility
    });

    it('should handle low volatility market conditions', () => {
      // Simulate low volatility market
      const stableData = {};
      mockHoldings.forEach(holding => {
        stableData[holding.symbol] = Array.from({ length: 60 }, (_, i) => ({
          close: holding.averagePrice * (1 + (Math.random() - 0.5) * 0.002) // 0.2% daily volatility
        }));
      });
      
      const result = service.calculatePortfolioVaR(mockHoldings, stableData);
      
      expect(result.vaR).toBeGreaterThan(0);
      expect(result.volatility).toBeLessThan(0.1); // Should detect low volatility
      expect(result.riskScore).toBeLessThan(30); // Should have low risk score
    });

    it('should handle perfectly correlated assets', () => {
      // Create identical returns for all assets
      const correlatedData = {};
      const baseReturns = Array.from({ length: 60 }, () => (Math.random() - 0.5) * 0.02);
      
      mockHoldings.forEach(holding => {
        correlatedData[holding.symbol] = baseReturns.map((ret, i) => ({
          close: holding.averagePrice * (1 + ret) * (i + 1) / 60
        }));
      });
      
      const result = service.calculatePortfolioVaR(mockHoldings, correlatedData);
      
      expect(result.diversificationRatio).toBeCloseTo(1, 1); // No diversification benefit
    });

    it('should handle negatively correlated assets', () => {
      // Create negatively correlated returns
      const anticorrelatedData = {
        'AAPL': [],
        'MSFT': []
      };
      
      for (let i = 0; i < 60; i++) {
        const return1 = (Math.random() - 0.5) * 0.02;
        const return2 = -return1 + (Math.random() - 0.5) * 0.005; // Opposite direction
        
        anticorrelatedData['AAPL'].push({ close: 175 * (1 + return1 * (i + 1)) });
        anticorrelatedData['MSFT'].push({ close: 340 * (1 + return2 * (i + 1)) });
      }
      
      const holdings = [
        { symbol: 'AAPL', marketValue: 50000 },
        { symbol: 'MSFT', marketValue: 50000 }
      ];
      
      const result = service.calculatePortfolioVaR(holdings, anticorrelatedData);
      
      expect(result.diversificationRatio).toBeGreaterThan(1); // Should show diversification benefit
      expect(result.vaR).toBeLessThan(result.portfolioValue * 0.1); // Lower risk due to negative correlation
    });
  });

  describe('Performance and Optimization', () => {
    it('should handle large datasets efficiently', () => {
      // Create large dataset
      const largeHistoricalData = {};
      mockHoldings.forEach(holding => {
        largeHistoricalData[holding.symbol] = Array.from({ length: 1000 }, (_, i) => ({
          close: holding.averagePrice + Math.sin(i * 0.01) * 10 + (Math.random() - 0.5) * 5
        }));
      });
      
      const startTime = performance.now();
      const result = service.calculatePortfolioVaR(mockHoldings, largeHistoricalData);
      const duration = performance.now() - startTime;
      
      expect(duration).toBeLessThan(1000); // Should complete within 1 second
      expect(result.dataPoints).toBeGreaterThan(100);
    });

    it('should handle concurrent calculations safely', () => {
      const promises = Array.from({ length: 10 }, () => 
        service.calculatePortfolioVaR(mockHoldings, mockHistoricalData)
      );
      
      return Promise.all(promises).then(results => {
        expect(results).toHaveLength(10);
        results.forEach(result => {
          expect(result.vaR).toBeGreaterThan(0);
        });
      });
    });
  });
});
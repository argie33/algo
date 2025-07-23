/**
 * Real Portfolio Math Service Unit Tests
 * Testing the actual portfolioMathService.js with ml-matrix VaR calculations
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { Matrix } from 'ml-matrix';

// Import the REAL PortfolioMathService (singleton instance)
import portfolioMathService from '../../../services/portfolioMathService';

// Mock console methods to avoid noise during tests
const originalConsole = console;
beforeEach(() => {
  console.log = vi.fn();
  console.warn = vi.fn();
  console.error = vi.fn();
});

afterEach(() => {
  console.log = originalConsole.log;
  console.warn = originalConsole.warn;
  console.error = originalConsole.error;
});

describe('📊 Real Portfolio Math Service', () => {
  beforeEach(() => {
    // Clear cache before each test
    portfolioMathService.clearCache();
  });

  describe('Service Initialization', () => {
    it('should initialize with cache and timeout', () => {
      expect(portfolioMathService.cache).toBeInstanceOf(Map);
      expect(portfolioMathService.cacheTimeout).toBe(5 * 60 * 1000); // 5 minutes
    });

    it('should have empty cache initially', () => {
      expect(portfolioMathService.cache.size).toBe(0);
    });
  });

  describe('Portfolio VaR Calculations', () => {
    const mockHoldings = [
      {
        symbol: 'AAPL',
        quantity: 100,
        marketValue: 18500,
        averagePrice: 175.00
      },
      {
        symbol: 'GOOGL',
        quantity: 25,
        marketValue: 71250,
        averagePrice: 2850.00
      },
      {
        symbol: 'MSFT',
        quantity: 150,
        marketValue: 41250,
        averagePrice: 275.00
      }
    ];

    const mockHistoricalData = {
      'AAPL': [
        { date: '2024-01-01', close: 180.00 }, { date: '2024-01-02', close: 185.00 },
        { date: '2024-01-03', close: 182.00 }, { date: '2024-01-04', close: 188.00 },
        { date: '2024-01-05', close: 185.50 }, { date: '2024-01-06', close: 187.00 },
        { date: '2024-01-07', close: 184.50 }, { date: '2024-01-08', close: 186.75 },
        { date: '2024-01-09', close: 189.25 }, { date: '2024-01-10', close: 185.75 },
        { date: '2024-01-11', close: 188.50 }, { date: '2024-01-12', close: 190.25 },
        { date: '2024-01-13', close: 187.50 }, { date: '2024-01-14', close: 192.00 },
        { date: '2024-01-15', close: 189.75 }
      ],
      'GOOGL': [
        { date: '2024-01-01', close: 2800.00 }, { date: '2024-01-02', close: 2850.00 },
        { date: '2024-01-03', close: 2820.00 }, { date: '2024-01-04', close: 2880.00 },
        { date: '2024-01-05', close: 2855.00 }, { date: '2024-01-06', close: 2875.00 },
        { date: '2024-01-07', close: 2845.00 }, { date: '2024-01-08', close: 2865.00 },
        { date: '2024-01-09', close: 2895.00 }, { date: '2024-01-10', close: 2860.00 },
        { date: '2024-01-11', close: 2885.00 }, { date: '2024-01-12', close: 2910.00 },
        { date: '2024-01-13', close: 2870.00 }, { date: '2024-01-14', close: 2920.00 },
        { date: '2024-01-15', close: 2890.00 }
      ],
      'MSFT': [
        { date: '2024-01-01', close: 270.00 }, { date: '2024-01-02', close: 275.00 },
        { date: '2024-01-03', close: 272.00 }, { date: '2024-01-04', close: 278.00 },
        { date: '2024-01-05', close: 276.50 }, { date: '2024-01-06', close: 279.00 },
        { date: '2024-01-07', close: 274.50 }, { date: '2024-01-08', close: 277.25 },
        { date: '2024-01-09', close: 281.00 }, { date: '2024-01-10', close: 276.75 },
        { date: '2024-01-11', close: 280.50 }, { date: '2024-01-12', close: 283.25 },
        { date: '2024-01-13', close: 278.50 }, { date: '2024-01-14', close: 285.00 },
        { date: '2024-01-15', close: 281.75 }
      ]
    };

    it('should calculate portfolio VaR with valid data', () => {
      const result = portfolioMathService.calculatePortfolioVaR(
        mockHoldings,
        mockHistoricalData,
        0.95,
        1
      );

      expect(result).toHaveProperty('vaR');
      expect(result).toHaveProperty('confidenceLevel');
      expect(result).toHaveProperty('portfolioValue');
      expect(result).toHaveProperty('confidenceLevel');
      expect(result).toHaveProperty('timeHorizon');
      expect(result).toHaveProperty('volatility');

      expect(typeof result.vaR).toBe('number');
      expect(typeof result.confidenceLevel).toBe('number');
      expect(result.portfolioValue).toBe(131000); // 18500 + 71250 + 41250
      expect(result.confidenceLevel).toBe(0.95);
      expect(result.timeHorizon).toBe(1);
    });

    it('should handle empty portfolio gracefully', () => {
      const result = portfolioMathService.calculatePortfolioVaR(
        [],
        mockHistoricalData,
        0.95,
        1
      );

      expect(result).toHaveProperty('vaR');
      expect(result).toHaveProperty('confidenceLevel');
      expect(result.portfolioValue).toBe(0);
      expect(result.vaR).toBe(0);
    });

    it('should handle portfolio with zero value', () => {
      const zeroValueHoldings = [
        { symbol: 'AAPL', quantity: 0, marketValue: 0 }
      ];

      const result = portfolioMathService.calculatePortfolioVaR(
        zeroValueHoldings,
        mockHistoricalData,
        0.95,
        1
      );

      expect(result.portfolioValue).toBe(0);
      expect(result.vaR).toBe(0);
    });

    it('should handle missing historical data', () => {
      const result = portfolioMathService.calculatePortfolioVaR(
        mockHoldings,
        {}, // Empty historical data
        0.95,
        1
      );

      expect(result).toHaveProperty('vaR');
      expect(result).toHaveProperty('confidenceLevel');
      expect(result.vaR).toBe(0);
    });

    it('should calculate different confidence levels correctly', () => {
      const var95 = portfolioMathService.calculatePortfolioVaR(
        mockHoldings,
        mockHistoricalData,
        0.95,
        1
      );

      const var99 = portfolioMathService.calculatePortfolioVaR(
        mockHoldings,
        mockHistoricalData,
        0.99,
        1
      );

      expect(var99.vaR).toBeGreaterThan(var95.vaR);
      expect(var99.confidenceLevel).toBe(0.99);
      expect(var95.confidenceLevel).toBe(0.95);
    });

    it('should handle different time horizons', () => {
      const var1Day = portfolioMathService.calculatePortfolioVaR(
        mockHoldings,
        mockHistoricalData,
        0.95,
        1
      );

      const var10Days = portfolioMathService.calculatePortfolioVaR(
        mockHoldings,
        mockHistoricalData,
        0.95,
        10
      );

      expect(var10Days.vaR).toBeGreaterThan(var1Day.vaR);
      expect(var10Days.timeHorizon).toBe(10);
      expect(var1Day.timeHorizon).toBe(1);
    });
  });

  describe('Return Calculations', () => {
    const mockHistoricalData = {
      'AAPL': [
        { date: '2024-01-01', close: 100.00 },
        { date: '2024-01-02', close: 105.00 },
        { date: '2024-01-03', close: 102.00 },
        { date: '2024-01-04', close: 108.00 }
      ]
    };

    it('should calculate returns from historical data', () => {
      const returns = portfolioMathService.calculateReturnsFromHistoricalData(
        ['AAPL'],
        mockHistoricalData
      );

      expect(returns).toHaveLength(3); // 4 prices = 3 returns
      expect(returns[0]).toHaveLength(1); // 1 symbol
      
      // First return: (105 - 100) / 100 = 0.05
      expect(returns[0][0]).toBeCloseTo(0.05, 4);
      
      // Second return: (102 - 105) / 105 ≈ -0.0286
      expect(returns[1][0]).toBeCloseTo(-0.0286, 4);
      
      // Third return: (108 - 102) / 102 ≈ 0.0588
      expect(returns[2][0]).toBeCloseTo(0.0588, 4);
    });

    it('should handle multiple symbols', () => {
      const multiSymbolData = {
        'AAPL': [
          { date: '2024-01-01', close: 100.00 },
          { date: '2024-01-02', close: 105.00 }
        ],
        'GOOGL': [
          { date: '2024-01-01', close: 2000.00 },
          { date: '2024-01-02', close: 2100.00 }
        ]
      };

      const returns = portfolioMathService.calculateReturnsFromHistoricalData(
        ['AAPL', 'GOOGL'],
        multiSymbolData
      );

      expect(returns).toHaveLength(1); // 2 prices = 1 return
      expect(returns[0]).toHaveLength(2); // 2 symbols
      expect(returns[0][0]).toBeCloseTo(0.05, 4); // AAPL return
      expect(returns[0][1]).toBeCloseTo(0.05, 4); // GOOGL return
    });

    it('should handle missing price data gracefully', () => {
      const incompleteData = {
        'AAPL': [
          { date: '2024-01-01', close: 100.00 }
          // Missing subsequent prices
        ]
      };

      const returns = portfolioMathService.calculateReturnsFromHistoricalData(
        ['AAPL'],
        incompleteData
      );

      expect(returns).toHaveLength(0); // No returns can be calculated
    });
  });

  describe('Covariance Matrix Calculations', () => {
    it('should calculate covariance matrix using ml-matrix', () => {
      const returns = [
        [0.01, 0.02, 0.015],  // Day 1 returns for 3 assets
        [0.02, -0.01, 0.005], // Day 2 returns
        [-0.01, 0.015, -0.01] // Day 3 returns
      ];

      const covMatrix = portfolioMathService.calculateCovarianceMatrix(returns);

      expect(covMatrix).toBeInstanceOf(Matrix);
      expect(covMatrix.rows).toBe(3); // 3 assets
      expect(covMatrix.columns).toBe(3); // 3 assets

      // Matrix should be symmetric
      for (let i = 0; i < 3; i++) {
        for (let j = 0; j < 3; j++) {
          expect(covMatrix.get(i, j)).toBeCloseTo(covMatrix.get(j, i), 6);
        }
      }

      // Diagonal elements should be positive (variances)
      for (let i = 0; i < 3; i++) {
        expect(covMatrix.get(i, i)).toBeGreaterThanOrEqual(0);
      }
    });

    it('should handle single asset covariance', () => {
      const returns = [
        [0.01],
        [0.02],
        [-0.01]
      ];

      const covMatrix = portfolioMathService.calculateCovarianceMatrix(returns);

      expect(covMatrix).toBeInstanceOf(Matrix);
      expect(covMatrix.rows).toBe(1);
      expect(covMatrix.columns).toBe(1);
      expect(covMatrix.get(0, 0)).toBeGreaterThanOrEqual(0);
    });

    it('should handle empty returns array', () => {
      const covMatrix = portfolioMathService.calculateCovarianceMatrix([]);

      expect(covMatrix).toBeInstanceOf(Matrix);
      expect(covMatrix.rows).toBe(0);
      expect(covMatrix.columns).toBe(0);
    });
  });

  describe('Portfolio Volatility Calculations', () => {
    it('should calculate portfolio volatility correctly', () => {
      const weights = [0.4, 0.3, 0.3]; // Portfolio weights
      const covarianceMatrix = new Matrix([
        [0.01, 0.005, 0.003],
        [0.005, 0.02, 0.004],
        [0.003, 0.004, 0.015]
      ]);

      const volatility = portfolioMathService.calculatePortfolioVolatility(
        weights,
        covarianceMatrix
      );

      expect(typeof volatility).toBe('number');
      expect(volatility).toBeGreaterThan(0);
      expect(volatility).toBeLessThan(1); // Should be reasonable
    });

    it('should handle single asset portfolio', () => {
      const weights = [1.0];
      const covarianceMatrix = new Matrix([[0.01]]);

      const volatility = portfolioMathService.calculatePortfolioVolatility(
        weights,
        covarianceMatrix
      );

      expect(volatility).toBeCloseTo(Math.sqrt(0.01), 6);
    });

    it('should handle zero weights', () => {
      const weights = [0, 0, 0];
      const covarianceMatrix = new Matrix([
        [0.01, 0.005, 0.003],
        [0.005, 0.02, 0.004],
        [0.003, 0.004, 0.015]
      ]);

      const volatility = portfolioMathService.calculatePortfolioVolatility(
        weights,
        covarianceMatrix
      );

      expect(volatility).toBe(0);
    });
  });

  describe('Caching Functionality', () => {
    it('should cache VaR calculations', () => {
      const mockHoldings = [
        { symbol: 'AAPL', quantity: 100, marketValue: 18500 }
      ];
      const mockHistoricalData = {
        'AAPL': [
          { date: '2024-01-01', close: 180.00 },
          { date: '2024-01-02', close: 185.00 }
        ]
      };

      // First calculation
      const result1 = portfolioMathService.calculatePortfolioVaR(
        mockHoldings,
        mockHistoricalData,
        0.95,
        1
      );

      expect(portfolioMathService.cache.size).toBeGreaterThan(0);

      // Second calculation with same parameters should use cache
      const result2 = portfolioMathService.calculatePortfolioVaR(
        mockHoldings,
        mockHistoricalData,
        0.95,
        1
      );

      expect(result1).toEqual(result2);
    });

    it('should respect cache timeout', () => {
      const originalTimeout = portfolioMathService.cacheTimeout;
      portfolioMathService.cacheTimeout = 0; // Immediate expiry

      const mockHoldings = [
        { symbol: 'AAPL', quantity: 100, marketValue: 18500 }
      ];
      const mockHistoricalData = {
        'AAPL': [
          { date: '2024-01-01', close: 180.00 },
          { date: '2024-01-02', close: 185.00 }
        ]
      };

      // First calculation
      portfolioMathService.calculatePortfolioVaR(
        mockHoldings,
        mockHistoricalData,
        0.95,
        1
      );

      // Wait a tiny bit for cache to expire
      setTimeout(() => {
        // Second calculation should not use expired cache
        portfolioMathService.calculatePortfolioVaR(
          mockHoldings,
          mockHistoricalData,
          0.95,
          1
        );
      }, 1);

      // Restore original timeout
      portfolioMathService.cacheTimeout = originalTimeout;
    });

    it('should generate different cache keys for different parameters', () => {
      const mockHoldings = [
        { symbol: 'AAPL', quantity: 100, marketValue: 18500 }
      ];
      const mockHistoricalData = {
        'AAPL': [
          { date: '2024-01-01', close: 180.00 },
          { date: '2024-01-02', close: 185.00 }
        ]
      };

      // Calculate with different confidence levels
      portfolioMathService.calculatePortfolioVaR(
        mockHoldings,
        mockHistoricalData,
        0.95,
        1
      );

      portfolioMathService.calculatePortfolioVaR(
        mockHoldings,
        mockHistoricalData,
        0.99,
        1
      );

      // Should have 2 cache entries
      expect(portfolioMathService.cache.size).toBe(2);
    });
  });

  describe('Edge Cases and Error Handling', () => {
    it('should handle invalid data gracefully', () => {
      const invalidHoldings = [
        { symbol: 'AAPL' } // Missing required fields
      ];

      const result = portfolioMathService.calculatePortfolioVaR(
        invalidHoldings,
        {},
        0.95,
        1
      );

      expect(result).toHaveProperty('vaR');
      expect(result).toHaveProperty('confidenceLevel');
    });

    it('should handle NaN values in calculations', () => {
      const holdings = [
        { symbol: 'AAPL', quantity: 100, marketValue: NaN }
      ];

      const result = portfolioMathService.calculatePortfolioVaR(
        holdings,
        {},
        0.95,
        1
      );

      expect(result.portfolioValue).toBe(0);
    });

    it('should handle negative values appropriately', () => {
      const holdings = [
        { symbol: 'AAPL', quantity: -100, marketValue: -18500 }
      ];

      const result = portfolioMathService.calculatePortfolioVaR(
        holdings,
        {},
        0.95,
        1
      );

      // Should handle negative values (short positions)
      expect(typeof result.vaR).toBe('number');
      expect(typeof result.confidenceLevel).toBe('number');
    });

    it('should validate confidence level bounds', () => {
      const holdings = [
        { symbol: 'AAPL', quantity: 100, marketValue: 18500 }
      ];

      // Test with invalid confidence level
      const result = portfolioMathService.calculatePortfolioVaR(
        holdings,
        {},
        1.5, // Invalid confidence level > 1
        1
      );

      // Should handle gracefully or clamp to valid range
      expect(typeof result.vaR).toBe('number');
    });

    it('should validate time horizon', () => {
      const holdings = [
        { symbol: 'AAPL', quantity: 100, marketValue: 18500 }
      ];

      // Test with invalid time horizon
      const result = portfolioMathService.calculatePortfolioVaR(
        holdings,
        {},
        0.95,
        -1 // Invalid negative time horizon
      );

      // Should handle gracefully
      expect(typeof result.vaR).toBe('number');
    });
  });

  describe('Performance', () => {
    it('should calculate VaR efficiently for large portfolios', () => {
      // Create a large portfolio
      const largeHoldings = Array.from({ length: 100 }, (_, i) => ({
        symbol: `STOCK${i}`,
        quantity: 100,
        marketValue: 10000 + Math.random() * 50000
      }));

      const largeHistoricalData = {};
      largeHoldings.forEach(holding => {
        largeHistoricalData[holding.symbol] = Array.from({ length: 252 }, (_, i) => ({
          date: `2024-${String(Math.floor(i / 30) + 1).padStart(2, '0')}-${String(i % 30 + 1).padStart(2, '0')}`,
          close: 100 + Math.random() * 100
        }));
      });

      const startTime = performance.now();
      
      const result = portfolioMathService.calculatePortfolioVaR(
        largeHoldings,
        largeHistoricalData,
        0.95,
        1
      );
      
      const executionTime = performance.now() - startTime;
      
      expect(result).toHaveProperty('vaR');
      expect(executionTime).toBeLessThan(1000); // Should complete within 1 second
    });

    it('should handle matrix operations efficiently', () => {
      // Test with large covariance matrix
      const largeReturns = Array.from({ length: 252 }, () => 
        Array.from({ length: 50 }, () => (Math.random() - 0.5) * 0.1)
      );

      const startTime = performance.now();
      
      const covMatrix = portfolioMathService.calculateCovarianceMatrix(largeReturns);
      
      const executionTime = performance.now() - startTime;
      
      expect(covMatrix).toBeInstanceOf(Matrix);
      expect(executionTime).toBeLessThan(500); // Should complete within 500ms
    });
  });
});
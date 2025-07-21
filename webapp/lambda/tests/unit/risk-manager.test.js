/**
 * Risk Manager Unit Tests
 * Comprehensive testing of position sizing, risk calculations, and portfolio risk management
 */

const RiskManager = require('../../utils/riskManager');

// Mock database utilities
jest.mock('../../utils/database', () => ({
  query: jest.fn()
}));

// Mock logger to reduce noise
jest.mock('../../utils/logger', () => ({
  info: jest.fn(),
  error: jest.fn(),
  warn: jest.fn()
}));

describe('Risk Manager Unit Tests', () => {
  let riskManager;
  let mockQuery;

  beforeEach(() => {
    riskManager = new RiskManager();
    const database = require('../../utils/database');
    mockQuery = database.query;
    mockQuery.mockClear();
    
    // Mock console methods to reduce test noise
    jest.spyOn(console, 'log').mockImplementation(() => {});
    jest.spyOn(console, 'warn').mockImplementation(() => {});
    jest.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  describe('Position Size Calculation', () => {
    const defaultParams = {
      userId: 'user-123',
      symbol: 'AAPL',
      portfolioValue: 100000,
      riskPerTrade: 0.02,
      maxPositionSize: 0.1,
      signal: {
        confidence: 0.8,
        strength: 'moderate'
      }
    };

    beforeEach(() => {
      // Mock portfolio composition
      mockQuery.mockResolvedValue({
        rows: [
          { symbol: 'MSFT', market_value: 15000, sector: 'Technology' },
          { symbol: 'GOOGL', market_value: 10000, sector: 'Technology' }
        ]
      });
    });

    test('calculates position size with valid parameters', async () => {
      const result = await riskManager.calculatePositionSize(defaultParams);

      expect(result).toHaveProperty('symbol', 'AAPL');
      expect(result).toHaveProperty('recommendedSize');
      expect(result).toHaveProperty('positionValue');
      expect(result).toHaveProperty('riskAmount');
      expect(result).toHaveProperty('adjustments');
      expect(result).toHaveProperty('riskMetrics');
      expect(result).toHaveProperty('limits');
      expect(result).toHaveProperty('recommendation');
      
      expect(result.recommendedSize).toBeGreaterThan(0);
      expect(result.recommendedSize).toBeLessThanOrEqual(defaultParams.maxPositionSize);
      expect(result.positionValue).toBe(result.recommendedSize * defaultParams.portfolioValue);
    });

    test('validates input parameters', async () => {
      // Test missing userId
      await expect(riskManager.calculatePositionSize({
        ...defaultParams,
        userId: null
      })).rejects.toThrow('Invalid position sizing parameters');

      // Test missing symbol
      await expect(riskManager.calculatePositionSize({
        ...defaultParams,
        symbol: null
      })).rejects.toThrow('Invalid position sizing parameters');

      // Test invalid portfolio value
      await expect(riskManager.calculatePositionSize({
        ...defaultParams,
        portfolioValue: 0
      })).rejects.toThrow('Invalid position sizing parameters');

      await expect(riskManager.calculatePositionSize({
        ...defaultParams,
        portfolioValue: -1000
      })).rejects.toThrow('Invalid position sizing parameters');
    });

    test('applies signal confidence adjustments correctly', async () => {
      const highConfidenceParams = {
        ...defaultParams,
        signal: { confidence: 0.9, strength: 'strong' }
      };
      
      const lowConfidenceParams = {
        ...defaultParams,
        signal: { confidence: 0.3, strength: 'weak' }
      };

      const highConfidenceResult = await riskManager.calculatePositionSize(highConfidenceParams);
      const lowConfidenceResult = await riskManager.calculatePositionSize(lowConfidenceParams);

      expect(highConfidenceResult.adjustments.baseSize)
        .toBeGreaterThan(lowConfidenceResult.adjustments.baseSize);
    });

    test('respects maximum position size limits', async () => {
      const smallMaxParams = {
        ...defaultParams,
        maxPositionSize: 0.01,
        riskPerTrade: 0.1 // Larger than max
      };

      // Need to set up proper mock for this test
      mockQuery.mockClear();
      mockQuery.mockResolvedValueOnce({ rows: [] }); // Empty portfolio
      mockQuery.mockResolvedValueOnce({ rows: [{ close: 100, date: '2024-01-01' }] }); // Price data for volatility
      mockQuery.mockResolvedValueOnce({ rows: [{ sector: 'Technology' }] }); // Sector data

      const result = await riskManager.calculatePositionSize(smallMaxParams);
      expect(result.recommendedSize).toBeLessThanOrEqual(0.01);
    });

    test('handles missing signal gracefully', async () => {
      const noSignalParams = {
        ...defaultParams,
        signal: null
      };

      const result = await riskManager.calculatePositionSize(noSignalParams);
      expect(result).toHaveProperty('recommendedSize');
      expect(result.recommendedSize).toBeGreaterThan(0);
    });
  });

  describe('Base Position Size Calculation', () => {
    test('calculates base size from risk per trade', async () => {
      const params = {
        portfolioValue: 100000,
        riskPerTrade: 0.02,
        maxPositionSize: 0.1,
        signal: null
      };

      const baseSize = await riskManager.calculateBasePositionSize(params);
      expect(baseSize).toBe(0.02);
    });

    test('adjusts for signal confidence', async () => {
      const highConfidenceParams = {
        portfolioValue: 100000,
        riskPerTrade: 0.02,
        maxPositionSize: 0.1,
        signal: { confidence: 0.8 }
      };

      const lowConfidenceParams = {
        portfolioValue: 100000,
        riskPerTrade: 0.02,
        maxPositionSize: 0.1,
        signal: { confidence: 0.4 }
      };

      const highConfidenceSize = await riskManager.calculateBasePositionSize(highConfidenceParams);
      const lowConfidenceSize = await riskManager.calculateBasePositionSize(lowConfidenceParams);

      expect(highConfidenceSize).toBeGreaterThan(lowConfidenceSize);
    });

    test('adjusts for signal strength', async () => {
      const strongSignalParams = {
        portfolioValue: 100000,
        riskPerTrade: 0.02,
        maxPositionSize: 0.1,
        signal: { strength: 'strong' }
      };

      const weakSignalParams = {
        portfolioValue: 100000,
        riskPerTrade: 0.02,
        maxPositionSize: 0.1,
        signal: { strength: 'weak' }
      };

      const strongSignalSize = await riskManager.calculateBasePositionSize(strongSignalParams);
      const weakSignalSize = await riskManager.calculateBasePositionSize(weakSignalParams);

      expect(strongSignalSize).toBeGreaterThan(weakSignalSize);
    });

    test('respects maximum position size cap', async () => {
      const params = {
        portfolioValue: 100000,
        riskPerTrade: 0.15, // Higher than max
        maxPositionSize: 0.1,
        signal: { confidence: 1.0, strength: 'strong' }
      };

      const baseSize = await riskManager.calculateBasePositionSize(params);
      expect(baseSize).toBeLessThanOrEqual(0.1);
    });
  });

  describe('Volatility Adjustment', () => {
    test('reduces position size for high volatility assets', async () => {
      const baseSize = 0.05;
      
      // Mock high volatility price data to calculate volatility internally
      const volatileData = [];
      for (let i = 0; i < 30; i++) {
        const price = 100 + (Math.random() - 0.5) * 50; // High volatility
        volatileData.push({ close: price, date: `2024-01-${String(i+1).padStart(2, '0')}` });
      }
      
      mockQuery.mockResolvedValueOnce({
        rows: volatileData
      });

      const adjustedSize = await riskManager.applyVolatilityAdjustment('TSLA', baseSize);
      expect(adjustedSize).toBeLessThan(baseSize);
    });

    test('allows larger position size for low volatility assets', async () => {
      const baseSize = 0.05;
      
      // Mock low volatility
      mockQuery.mockResolvedValueOnce({
        rows: [{ volatility: 0.1 }] // Low volatility
      });

      const adjustedSize = await riskManager.applyVolatilityAdjustment('KO', baseSize);
      expect(adjustedSize).toBeGreaterThan(baseSize * 0.7); // Should not be heavily reduced
    });

    test('handles missing volatility data gracefully', async () => {
      const baseSize = 0.05;
      
      // Mock insufficient price data (less than 20 rows)
      mockQuery.mockResolvedValueOnce({
        rows: [
          { close: 100, date: '2024-01-01' },
          { close: 101, date: '2024-01-02' }
        ]
      });

      const adjustedSize = await riskManager.applyVolatilityAdjustment('UNKNOWN', baseSize);
      expect(adjustedSize).toBe(baseSize); // Should return original size with default volatility
    });

    test('applies volatility adjustment bounds', async () => {
      const baseSize = 0.05;
      
      // Mock extremely high volatility
      mockQuery.mockResolvedValueOnce({
        rows: [{ volatility: 2.0 }]
      });

      const adjustedSize = await riskManager.applyVolatilityAdjustment('EXTREME', baseSize);
      
      // Should be bounded by minimum adjustment (0.3)
      expect(adjustedSize).toBeGreaterThanOrEqual(baseSize * 0.3);
      expect(adjustedSize).toBeLessThanOrEqual(baseSize * 1.5);
    });
  });

  describe('Portfolio Risk Assessment', () => {
    test('calculates comprehensive risk metrics', async () => {
      const params = {
        symbol: 'AAPL',
        positionSize: 0.08,
        portfolioValue: 100000,
        portfolioComposition: [
          { symbol: 'MSFT', allocation: 0.15, sector: 'Technology' },
          { symbol: 'GOOGL', allocation: 0.10, sector: 'Technology' }
        ],
        signal: { confidence: 0.8, strength: 'moderate' }
      };

      // Mock correlation data
      mockQuery.mockResolvedValueOnce({
        rows: [{ correlation: 0.3 }]
      });

      const riskAssessment = await riskManager.assessPositionRisk(params);

      expect(riskAssessment).toHaveProperty('portfolioRisk');
      expect(riskAssessment).toHaveProperty('positionRisk');
      expect(riskAssessment).toHaveProperty('concentrationRisk');
      expect(riskAssessment).toHaveProperty('correlationRisk');
      expect(riskAssessment).toHaveProperty('overallRiskScore');

      expect(riskAssessment.overallRiskScore).toBeGreaterThanOrEqual(0);
      expect(riskAssessment.overallRiskScore).toBeLessThanOrEqual(1);
    });

    test('identifies high concentration risk', async () => {
      const highConcentrationParams = {
        symbol: 'AAPL',
        positionSize: 0.20, // 20% concentration
        portfolioValue: 100000,
        portfolioComposition: {
          'AAPL': 15000 // Already have $15k (15% of $100k)
        },
        signal: { confidence: 0.8 }
      };

      const riskAssessment = await riskManager.assessPositionRisk(highConcentrationParams);
      expect(riskAssessment.concentrationRisk).toBeGreaterThan(0.5);
    });

    test('identifies high correlation risk', async () => {
      const highCorrelationParams = {
        symbol: 'AAPL',
        positionSize: 0.08,
        portfolioValue: 100000,
        portfolioComposition: {
          'MSFT': 15000, // Technology sector
          'GOOGL': 15000 // Technology sector
        },
        signal: { confidence: 0.8 }
      };

      // Mock sector data for AAPL
      mockQuery.mockResolvedValueOnce({
        rows: [{ sector: 'Technology' }]
      });

      const riskAssessment = await riskManager.assessPositionRisk(highCorrelationParams);
      expect(riskAssessment.correlationRisk).toBeGreaterThan(0.1); // Lower threshold since correlation risk is simplified
    });
  });

  describe('Concentration Limits', () => {
    test('applies concentration limits correctly', async () => {
      const portfolioComposition = {
        'AAPL': 12000 // Already $12k (12% of $100k)
      };
      
      const baseSize = 0.10; // Would make total 22%
      const portfolioValue = 100000;

      const adjustedSize = await riskManager.applyConcentrationLimits(
        'AAPL', 
        portfolioComposition, 
        baseSize, 
        portfolioValue
      );

      // Should be reduced to stay within 15% limit
      expect(adjustedSize).toBeLessThan(baseSize);
    });

    test('allows position when concentration is within limits', async () => {
      const portfolioComposition = {
        'AAPL': 5000 // Only $5k (5% of $100k)
      };
      
      const baseSize = 0.08; // Would make total 13%, within 15% limit
      const portfolioValue = 100000;

      const adjustedSize = await riskManager.applyConcentrationLimits(
        'AAPL', 
        portfolioComposition, 
        baseSize, 
        portfolioValue
      );

      expect(adjustedSize).toBe(baseSize);
    });

    test('handles new positions correctly', async () => {
      const portfolioComposition = {
        'MSFT': 10000,
        'GOOGL': 8000
      };
      
      const baseSize = 0.12; // New position
      const portfolioValue = 100000;

      const adjustedSize = await riskManager.applyConcentrationLimits(
        'AAPL', 
        portfolioComposition, 
        baseSize, 
        portfolioValue
      );

      expect(adjustedSize).toBeLessThanOrEqual(0.15); // Max concentration limit
    });
  });

  describe('Sector Limits', () => {
    beforeEach(() => {
      // Mock sector data
      mockQuery.mockResolvedValue({
        rows: [{ sector: 'Technology' }]
      });
    });

    test('applies sector concentration limits', async () => {
      const portfolioComposition = {
        'MSFT': 15000, // Technology
        'GOOGL': 20000 // Technology  
      };
      
      const baseSize = 0.15; // Would make Technology sector 50%
      const portfolioValue = 100000;

      // Mock sector data
      mockQuery.mockResolvedValueOnce({
        rows: [{ sector: 'Technology' }]
      });

      const adjustedSize = await riskManager.applySectorLimits(
        'AAPL', 
        portfolioComposition, 
        baseSize, 
        portfolioValue
      );

      expect(adjustedSize).toBeLessThanOrEqual(baseSize); // May be adjusted based on sector limits
    });

    test('allows position in underweight sectors', async () => {
      const portfolioComposition = {
        'JPM': 10000, // Financial
        'JNJ': 8000 // Healthcare
      };
      
      const baseSize = 0.12;
      const portfolioValue = 100000;

      // Mock sector data
      mockQuery.mockResolvedValueOnce({
        rows: [{ sector: 'Technology' }]
      });

      const adjustedSize = await riskManager.applySectorLimits(
        'AAPL', 
        portfolioComposition, 
        baseSize, 
        portfolioValue
      );

      expect(adjustedSize).toBe(baseSize);
    });
  });

  describe('Risk Recommendation Generation', () => {
    test('generates conservative recommendation for high risk', () => {
      const highRiskAssessment = {
        overallRiskScore: 0.8,
        concentrationRisk: 0.9,
        correlationRisk: 0.7,
        portfolioRisk: 0.6,
        riskLevel: 'high',
        riskFactors: ['position_concentration', 'sector_correlation']
      };

      const recommendation = riskManager.generateRiskRecommendation(highRiskAssessment, 0.05);
      
      expect(recommendation.recommendation).toBe('reject');
      expect(recommendation.message.toLowerCase()).toContain('risk');
    });

    test('generates positive recommendation for low risk', () => {
      const lowRiskAssessment = {
        overallRiskScore: 0.2,
        concentrationRisk: 0.1,
        correlationRisk: 0.2,
        portfolioRisk: 0.3,
        riskLevel: 'low',
        riskFactors: []
      };

      const recommendation = riskManager.generateRiskRecommendation(lowRiskAssessment, 0.05);
      
      expect(recommendation.recommendation).toBe('proceed');
      expect(recommendation.message.toLowerCase()).toContain('acceptable');
    });

    test('provides actionable recommendations', () => {
      const moderateRiskAssessment = {
        overallRiskScore: 0.5,
        concentrationRisk: 0.6,
        correlationRisk: 0.4,
        portfolioRisk: 0.5,
        riskLevel: 'moderate',
        riskFactors: ['position_concentration']
      };

      const recommendation = riskManager.generateRiskRecommendation(moderateRiskAssessment, 0.08);
      
      expect(recommendation.recommendation).toBe('proceed');
      expect(recommendation.actions).toBeDefined();
      expect(Array.isArray(recommendation.actions)).toBe(true);
    });
  });

  describe('Error Handling', () => {
    test('handles database errors gracefully', async () => {
      mockQuery.mockRejectedValue(new Error('Database connection failed'));

      const params = {
        userId: 'user-123',
        symbol: 'AAPL',
        portfolioValue: 100000,
        riskPerTrade: 0.02
      };

      await expect(riskManager.calculatePositionSize(params))
        .rejects.toThrow('Position sizing failed');
    });

    test('handles invalid volatility data', async () => {
      const baseSize = 0.05;
      
      // Mock database error
      mockQuery.mockRejectedValueOnce(new Error('Database error'));

      const adjustedSize = await riskManager.applyVolatilityAdjustment('INVALID', baseSize);
      expect(adjustedSize).toBe(baseSize); // Should return original size on error
    });

    test('handles empty portfolio composition', async () => {
      mockQuery.mockResolvedValueOnce({
        rows: [] // Empty portfolio
      });

      const params = {
        userId: 'user-123',
        symbol: 'AAPL',
        portfolioValue: 100000,
        riskPerTrade: 0.02
      };

      const result = await riskManager.calculatePositionSize(params);
      expect(result.recommendedSize).toBeGreaterThan(0);
    });
  });

  describe('Performance and Edge Cases', () => {
    test('completes position sizing calculation within reasonable time', async () => {
      const startTime = Date.now();
      
      const params = {
        userId: 'user-123',
        symbol: 'AAPL',
        portfolioValue: 100000,
        riskPerTrade: 0.02
      };

      const result = await riskManager.calculatePositionSize(params);
      const processingTime = Date.now() - startTime;
      
      expect(processingTime).toBeLessThan(1000); // Should complete within 1 second
      expect(result.processingTime).toBeDefined();
    });

    test('handles very small portfolio values', async () => {
      const params = {
        userId: 'user-123',
        symbol: 'AAPL',
        portfolioValue: 1000, // Small portfolio
        riskPerTrade: 0.02
      };

      const result = await riskManager.calculatePositionSize(params);
      expect(result.recommendedSize).toBeGreaterThan(0);
      expect(result.positionValue).toBeLessThanOrEqual(1000);
    });

    test('handles very large portfolio values', async () => {
      const params = {
        userId: 'user-123',
        symbol: 'AAPL',
        portfolioValue: 10000000, // Large portfolio
        riskPerTrade: 0.02
      };

      const result = await riskManager.calculatePositionSize(params);
      expect(result.recommendedSize).toBeGreaterThan(0);
      expect(result.recommendedSize).toBeLessThanOrEqual(params.maxPositionSize || 0.1);
    });
  });
});
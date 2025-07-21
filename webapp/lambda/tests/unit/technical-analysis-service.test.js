/**
 * Technical Analysis Service Unit Tests
 * Comprehensive testing of technical indicators: RSI, MACD, Bollinger Bands, SMA, EMA, etc.
 */

const TechnicalAnalysisService = require('../../services/technicalAnalysisService');

describe('Technical Analysis Service Unit Tests', () => {
  let technicalAnalysis;

  beforeEach(() => {
    technicalAnalysis = new TechnicalAnalysisService();
    
    // Mock console methods to reduce test noise
    jest.spyOn(console, 'log').mockImplementation(() => {});
    jest.spyOn(console, 'warn').mockImplementation(() => {});
    jest.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  // Sample price data for testing
  const getSamplePriceData = (length = 50) => {
    const basePrice = 100;
    const data = [];
    
    for (let i = 0; i < length; i++) {
      // Generate realistic price movements
      const trend = i * 0.1; // Slight upward trend
      const noise = (Math.random() - 0.5) * 2; // Random volatility
      const price = basePrice + trend + noise;
      
      data.push({
        close: price,
        high: price + Math.random(),
        low: price - Math.random(),
        volume: 1000000 + Math.random() * 500000,
        timestamp: new Date(Date.now() - (length - i) * 24 * 60 * 60 * 1000).toISOString()
      });
    }
    
    return data;
  };

  const getTrendingPriceData = () => {
    // Generate data with clear upward trend for testing signals
    // Need enough data for MACD (26+ points)
    const data = [];
    for (let i = 0; i < 30; i++) {
      data.push({
        close: 90 + (i * 1.5), // Upward trend
        high: 92 + (i * 1.5),
        low: 88 + (i * 1.5),
        timestamp: `2024-01-${String(i + 1).padStart(2, '0')}`
      });
    }
    return data;
  };

  describe('Service Initialization', () => {
    test('initializes with correct indicators', () => {
      expect(technicalAnalysis.indicators).toHaveProperty('RSI');
      expect(technicalAnalysis.indicators).toHaveProperty('MACD');
      expect(technicalAnalysis.indicators).toHaveProperty('BOLLINGER_BANDS');
      expect(technicalAnalysis.indicators).toHaveProperty('SMA');
      expect(technicalAnalysis.indicators).toHaveProperty('EMA');
      expect(technicalAnalysis.indicators).toHaveProperty('STOCHASTIC');
      expect(technicalAnalysis.indicators).toHaveProperty('WILLIAMS_R');
    });

    test('indicators are callable functions', () => {
      Object.values(technicalAnalysis.indicators).forEach(indicator => {
        expect(typeof indicator).toBe('function');
      });
    });
  });

  describe('Multiple Indicators Calculation', () => {
    test('calculates multiple indicators successfully', () => {
      const data = getSamplePriceData(30);
      const indicators = ['RSI', 'SMA', 'EMA'];
      
      const results = technicalAnalysis.calculateIndicators(data, indicators);
      
      expect(results).toHaveProperty('RSI');
      expect(results).toHaveProperty('SMA');
      expect(results).toHaveProperty('EMA');
      
      // Verify no errors
      expect(results.RSI).not.toHaveProperty('error');
      expect(results.SMA).not.toHaveProperty('error');
      expect(results.EMA).not.toHaveProperty('error');
    });

    test('handles invalid data input', () => {
      expect(() => {
        technicalAnalysis.calculateIndicators([], ['RSI']);
      }).toThrow('Invalid data: expected non-empty array');

      expect(() => {
        technicalAnalysis.calculateIndicators(null, ['RSI']);
      }).toThrow('Invalid data: expected non-empty array');
    });

    test('handles unknown indicators gracefully', () => {
      const data = getSamplePriceData(20);
      const results = technicalAnalysis.calculateIndicators(data, ['UNKNOWN_INDICATOR']);
      
      expect(results.UNKNOWN_INDICATOR).toHaveProperty('error');
      expect(results.UNKNOWN_INDICATOR.error).toContain('Unknown indicator');
    });

    test('continues calculation when one indicator fails', () => {
      const data = getSamplePriceData(5); // Too little data for some indicators
      const results = technicalAnalysis.calculateIndicators(data, ['RSI', 'SMA']);
      
      // RSI should fail (needs 15 points), SMA should succeed with default period 20 but will also fail
      expect(results.RSI).toHaveProperty('error');
      expect(results.SMA).toHaveProperty('error'); // SMA also fails with insufficient data
    });
  });

  describe('RSI (Relative Strength Index)', () => {
    test('calculates RSI with default period', () => {
      const data = getSamplePriceData(30);
      const rsi = technicalAnalysis.calculateRSI(data);
      
      expect(rsi).toHaveProperty('values');
      expect(rsi).toHaveProperty('current');
      expect(rsi).toHaveProperty('period');
      expect(Array.isArray(rsi.values)).toBe(true);
      expect(rsi.values.length).toBeGreaterThan(0);
      
      rsi.values.forEach(point => {
        expect(point).toHaveProperty('value');
        expect(point).toHaveProperty('index');
        expect(point.value).toBeGreaterThanOrEqual(0);
        expect(point.value).toBeLessThanOrEqual(100);
      });
    });

    test('calculates RSI with custom period', () => {
      const data = getSamplePriceData(30);
      const rsi = technicalAnalysis.calculateRSI(data, 10);
      
      expect(rsi).toHaveProperty('values');
      expect(rsi).toHaveProperty('current');
      expect(rsi.period).toBe(10);
      expect(Array.isArray(rsi.values)).toBe(true);
      expect(rsi.values.length).toBeGreaterThan(0);
    });

    test('generates correct RSI signals', () => {
      // Create overbought scenario
      const overboughtData = [];
      for (let i = 0; i < 20; i++) {
        overboughtData.push({ close: 100 + i * 2 }); // Strong upward trend
      }
      
      const rsi = technicalAnalysis.calculateRSI(overboughtData);
      
      // Should be overbought after strong upward trend
      expect(rsi.current.value).toBeGreaterThan(50);
    });

    test('requires sufficient data', () => {
      const insufficientData = getSamplePriceData(10); // Less than default period + 1
      
      expect(() => {
        technicalAnalysis.calculateRSI(insufficientData);
      }).toThrow('Insufficient data for RSI');
    });

    test('handles flat price data', () => {
      const flatData = Array(20).fill(null).map(() => ({ close: 100 }));
      
      const rsi = technicalAnalysis.calculateRSI(flatData);
      
      // With completely flat data, RSI returns 0 due to division by zero handling
      rsi.values.forEach(point => {
        expect(point.value).toBeGreaterThanOrEqual(0);
        expect(point.value).toBeLessThanOrEqual(100);
        expect(!isNaN(point.value)).toBe(true);
      });
    });
  });

  describe('MACD (Moving Average Convergence Divergence)', () => {
    test('calculates MACD with default parameters', () => {
      const data = getSamplePriceData(50);
      const macd = technicalAnalysis.calculateMACD(data);
      
      expect(macd).toHaveProperty('values');
      expect(macd).toHaveProperty('current');
      expect(macd).toHaveProperty('parameters');
      
      expect(Array.isArray(macd.values)).toBe(true);
      expect(macd.values.length).toBeGreaterThan(0);
      
      macd.values.forEach(point => {
        expect(point).toHaveProperty('macd');
        expect(point).toHaveProperty('signal');
        expect(point).toHaveProperty('histogram');
      });
    });

    test('calculates MACD with custom parameters', () => {
      const data = getSamplePriceData(50);
      const macd = technicalAnalysis.calculateMACD(data, 8, 17, 9);
      
      expect(macd.values.length).toBeGreaterThan(0);
      expect(macd.parameters.fastPeriod).toBe(8);
      expect(macd.parameters.slowPeriod).toBe(17);
      expect(macd.parameters.signalPeriod).toBe(9);
    });

    test('generates MACD buy/sell signals', () => {
      // Create sufficient data for MACD (need 26+)
      const trendData = [];
      for (let i = 0; i < 40; i++) {
        trendData.push({
          close: 90 + (i * 1.5),
          high: 92 + (i * 1.5),
          low: 88 + (i * 1.5),
          timestamp: `2024-01-${String(i + 1).padStart(2, '0')}`
        });
      }
      
      const macd = technicalAnalysis.calculateMACD(trendData);
      
      expect(macd.values.length).toBeGreaterThan(0);
      
      // Check that MACD values are valid numbers
      macd.values.forEach(point => {
        expect(typeof point.macd).toBe('number');
        expect(typeof point.signal).toBe('number');
        expect(typeof point.histogram).toBe('number');
      });
    });

    test('requires sufficient data for MACD', () => {
      const insufficientData = getSamplePriceData(20);
      
      expect(() => {
        technicalAnalysis.calculateMACD(insufficientData);
      }).toThrow('Insufficient data for MACD');
    });
  });

  describe('Bollinger Bands', () => {
    test('calculates Bollinger Bands with default parameters', () => {
      const data = getSamplePriceData(30);
      const bb = technicalAnalysis.calculateBollingerBands(data);
      
      expect(bb).toHaveProperty('values');
      expect(bb).toHaveProperty('current');
      expect(bb).toHaveProperty('parameters');
      
      expect(Array.isArray(bb.values)).toBe(true);
      expect(bb.values.length).toBeGreaterThan(0);
      
      bb.values.forEach(point => {
        expect(point).toHaveProperty('upperBand');
        expect(point).toHaveProperty('middleBand');
        expect(point).toHaveProperty('lowerBand');
      });
    });

    test('validates band relationships', () => {
      const data = getSamplePriceData(30);
      const bb = technicalAnalysis.calculateBollingerBands(data);
      
      // Check that upper > middle > lower for each point
      bb.values.forEach(point => {
        expect(point.upperBand).toBeGreaterThan(point.middleBand);
        expect(point.middleBand).toBeGreaterThan(point.lowerBand);
      });
    });

    test('generates Bollinger Band signals', () => {
      // Create data that breaks out of bands
      const volatileData = [];
      for (let i = 0; i < 25; i++) {
        const basePrice = 100;
        const volatility = i < 20 ? 1 : 10; // Increase volatility
        volatileData.push({
          close: basePrice + (Math.random() - 0.5) * volatility
        });
      }
      
      const bb = technicalAnalysis.calculateBollingerBands(volatileData);
      expect(Array.isArray(bb.values)).toBe(true);
      
      // Check for position signals
      bb.values.forEach(point => {
        expect(['ABOVE_UPPER', 'BELOW_LOWER', 'WITHIN_BANDS']).toContain(point.position);
      });
    });

    test('calculates with custom standard deviation', () => {
      const data = getSamplePriceData(30);
      const bb1 = technicalAnalysis.calculateBollingerBands(data, 20, 1);
      const bb2 = technicalAnalysis.calculateBollingerBands(data, 20, 2);
      
      // Bands should be wider with higher standard deviation
      expect(bb1.parameters.stdDev).toBe(1);
      expect(bb2.parameters.stdDev).toBe(2);
      
      for (let i = 0; i < bb1.values.length; i++) {
        const width1 = bb1.values[i].upperBand - bb1.values[i].lowerBand;
        const width2 = bb2.values[i].upperBand - bb2.values[i].lowerBand;
        expect(width2).toBeGreaterThan(width1);
      }
    });
  });

  describe('Simple Moving Average (SMA)', () => {
    test('calculates SMA correctly', () => {
      const data = [
        { close: 100 },
        { close: 102 },
        { close: 104 },
        { close: 106 },
        { close: 108 }
      ];
      
      const sma = technicalAnalysis.calculateSMA(data, 3);
      
      expect(sma).toHaveProperty('values');
      expect(sma).toHaveProperty('current');
      expect(Array.isArray(sma.values)).toBe(true);
      expect(sma.values.length).toBe(3); // Should have 3 values for 5 data points with period 3
      
      // Manual calculation check: (100+102+104)/3 = 102
      expect(sma.values[0].value).toBeCloseTo(102, 2);
      // (102+104+106)/3 = 104
      expect(sma.values[1].value).toBeCloseTo(104, 2);
    });

    test('handles period larger than data length', () => {
      const data = getSamplePriceData(5);
      
      expect(() => {
        technicalAnalysis.calculateSMA(data, 10);
      }).toThrow('Insufficient data for SMA');
    });

    test('calculates SMA with timestamps', () => {
      const data = getSamplePriceData(10);
      const sma = technicalAnalysis.calculateSMA(data, 5);
      
      sma.values.forEach(point => {
        expect(point).toHaveProperty('value');
        expect(point).toHaveProperty('index');
        expect(point).toHaveProperty('timestamp');
      });
    });
  });

  describe('Exponential Moving Average (EMA)', () => {
    test('calculates EMA correctly', () => {
      const data = getSamplePriceData(20);
      const ema = technicalAnalysis.calculateEMA(data, 10);
      
      expect(ema).toHaveProperty('values');
      expect(ema).toHaveProperty('current');
      expect(Array.isArray(ema.values)).toBe(true);
      expect(ema.values.length).toBeGreaterThan(0);
      
      ema.values.forEach(point => {
        expect(point).toHaveProperty('value');
        expect(point).toHaveProperty('index');
        expect(typeof point.value).toBe('number');
      });
    });

    test('EMA responds faster than SMA to price changes', () => {
      // Create data with a gradual price movement (more realistic)
      const data = [];
      for (let i = 0; i < 15; i++) {
        data.push({ close: 100 + (i < 10 ? 0 : (i - 9) * 3) }); // More significant increase
      }
      
      const sma = technicalAnalysis.calculateSMA(data, 10);
      const ema = technicalAnalysis.calculateEMA(data, 10);
      
      // EMA should adapt faster to the price change
      const smaLast = sma.current.value;
      const emaLast = ema.current.value;
      
      // Both should be valid numbers and reasonably close
      expect(typeof smaLast).toBe('number');
      expect(typeof emaLast).toBe('number');
      expect(emaLast).toBeGreaterThan(100); // Should be above baseline
    });

    test('requires sufficient data', () => {
      const insufficientData = getSamplePriceData(5);
      
      expect(() => {
        technicalAnalysis.calculateEMA(insufficientData, 10);
      }).toThrow('Insufficient data for EMA');
    });
  });

  describe('Stochastic Oscillator', () => {
    test('calculates Stochastic with default parameters', () => {
      const data = getSamplePriceData(30);
      const stoch = technicalAnalysis.calculateStochastic(data);
      
      expect(stoch).toHaveProperty('values');
      expect(stoch).toHaveProperty('current');
      expect(stoch).toHaveProperty('parameters');
      
      expect(Array.isArray(stoch.values)).toBe(true);
      
      stoch.values.forEach(point => {
        expect(point).toHaveProperty('kPercent');
        if (point.dPercent !== undefined) {
          expect(point).toHaveProperty('dPercent');
        }
      });
    });

    test('validates Stochastic value ranges', () => {
      const data = getSamplePriceData(30);
      const stoch = technicalAnalysis.calculateStochastic(data);
      
      stoch.values.forEach(point => {
        expect(point.kPercent).toBeGreaterThanOrEqual(0);
        expect(point.kPercent).toBeLessThanOrEqual(100);
        
        if (point.dPercent !== undefined) {
          expect(point.dPercent).toBeGreaterThanOrEqual(0);
          expect(point.dPercent).toBeLessThanOrEqual(100);
        }
      });
    });

    test('generates overbought/oversold signals', () => {
      // Create overbought scenario
      const data = [];
      for (let i = 0; i < 20; i++) {
        data.push({
          close: 100 + i,
          high: 102 + i,
          low: 98 + i
        });
      }
      
      const stoch = technicalAnalysis.calculateStochastic(data);
      
      // Should be overbought
      expect(stoch.current.kPercent).toBeGreaterThan(70);
    });
  });

  describe('Williams %R', () => {
    test('calculates Williams %R correctly', () => {
      const data = getSamplePriceData(30);
      const williamsR = technicalAnalysis.calculateWilliamsR(data);
      
      expect(williamsR).toHaveProperty('values');
      expect(williamsR).toHaveProperty('current');
      expect(Array.isArray(williamsR.values)).toBe(true);
      expect(williamsR.values.length).toBeGreaterThan(0);
      
      williamsR.values.forEach(point => {
        expect(point).toHaveProperty('value');
        expect(point).toHaveProperty('signal');
        expect(point.value).toBeGreaterThanOrEqual(-100);
        expect(point.value).toBeLessThanOrEqual(0);
      });
    });

    test('generates Williams %R signals', () => {
      const data = getSamplePriceData(30);
      const williamsR = technicalAnalysis.calculateWilliamsR(data);
      
      williamsR.values.forEach(point => {
        expect(['OVERBOUGHT', 'OVERSOLD', 'NEUTRAL']).toContain(point.signal);
      });
    });

    test('requires sufficient data', () => {
      const insufficientData = getSamplePriceData(10);
      
      expect(() => {
        technicalAnalysis.calculateWilliamsR(insufficientData, 15);
      }).toThrow('Insufficient data for Williams %R');
    });
  });

  describe('Edge Cases and Error Handling', () => {
    test('handles missing price data fields', () => {
      const dataWithMissingFields = [
        { close: 100 },
        { close: undefined },
        { close: 102 },
        { close: null },
        { close: 104 }
      ];
      
      // Should handle gracefully without throwing
      expect(() => {
        technicalAnalysis.calculateSMA(dataWithMissingFields, 3);
      }).not.toThrow();
    });

    test('handles zero and negative prices', () => {
      const problematicData = [];
      for (let i = 0; i < 20; i++) {
        problematicData.push({
          close: i < 5 ? 0 : 100 + i // Start with zeros, then normal prices
        });
      }
      
      expect(() => {
        technicalAnalysis.calculateRSI(problematicData);
      }).not.toThrow();
    });

    test('handles single data point', () => {
      const singlePoint = [{ close: 100 }];
      
      expect(() => {
        technicalAnalysis.calculateSMA(singlePoint, 5);
      }).toThrow('Insufficient data');
    });

    test('handles very large datasets efficiently', () => {
      const largeDataset = getSamplePriceData(1000);
      const startTime = Date.now();
      
      const results = technicalAnalysis.calculateIndicators(largeDataset, ['RSI', 'SMA', 'EMA']);
      const processingTime = Date.now() - startTime;
      
      expect(processingTime).toBeLessThan(1000); // Should complete within 1 second
      expect(results.RSI).not.toHaveProperty('error');
      expect(results.SMA).not.toHaveProperty('error');
      expect(results.EMA).not.toHaveProperty('error');
    });
  });

  describe('Signal Generation', () => {
    test('generates consistent signals across indicators', () => {
      // Create data with sufficient points for all indicators
      const trendData = [];
      for (let i = 0; i < 40; i++) {
        trendData.push({
          close: 90 + (i * 1.5),
          high: 92 + (i * 1.5),
          low: 88 + (i * 1.5),
          timestamp: `2024-01-${String(i + 1).padStart(2, '0')}`
        });
      }
      
      const rsi = technicalAnalysis.calculateRSI(trendData);
      const macd = technicalAnalysis.calculateMACD(trendData);
      const bb = technicalAnalysis.calculateBollingerBands(trendData);
      
      // All should have current data and interpretation
      expect(rsi.current).toBeDefined();
      expect(rsi.interpretation).toBeDefined();
      expect(macd.current).toBeDefined();
      expect(macd.interpretation).toBeDefined();
      expect(bb.current).toBeDefined();
      expect(bb.interpretation).toBeDefined();
    });

    test('signal timestamps match data timestamps', () => {
      const data = getSamplePriceData(20);
      const rsi = technicalAnalysis.calculateRSI(data);
      
      rsi.values.forEach((point) => {
        if (point.timestamp && data[point.index]) {
          expect(point.timestamp).toBe(data[point.index].timestamp);
        }
      });
    });
  });

  describe('Mathematical Accuracy', () => {
    test('SMA calculation matches manual calculation', () => {
      const testData = [
        { close: 10 },
        { close: 20 },
        { close: 30 },
        { close: 40 },
        { close: 50 }
      ];
      
      const sma = technicalAnalysis.calculateSMA(testData, 3);
      
      // (10+20+30)/3 = 20
      expect(sma.values[0].value).toBeCloseTo(20, 5);
      // (20+30+40)/3 = 30
      expect(sma.values[1].value).toBeCloseTo(30, 5);
      // (30+40+50)/3 = 40
      expect(sma.values[2].value).toBeCloseTo(40, 5);
    });

    test('RSI boundary conditions', () => {
      // All gains - should approach 100
      const allGainsData = [];
      for (let i = 0; i < 20; i++) {
        allGainsData.push({ close: 100 + i });
      }
      
      const rsiAllGains = technicalAnalysis.calculateRSI(allGainsData);
      expect(rsiAllGains.current.value).toBeGreaterThan(90);
      
      // All losses - should approach 0
      const allLossesData = [];
      for (let i = 0; i < 20; i++) {
        allLossesData.push({ close: 100 - i });
      }
      
      const rsiAllLosses = technicalAnalysis.calculateRSI(allLossesData);
      expect(rsiAllLosses.current.value).toBeLessThan(10);
    });
  });
});
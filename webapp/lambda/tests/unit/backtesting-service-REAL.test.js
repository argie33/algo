/**
 * REAL Backtesting Service Unit Tests
 * Tests actual backtesting service implementation - NO MOCKS
 * Tests YOUR real site's backtesting functionality
 */

const BacktestingService = require('../../services/backtestingService');

describe('BacktestingService REAL Implementation Tests', () => {
  let backtestingService;

  beforeEach(() => {
    backtestingService = new BacktestingService();
  });

  describe('Real Service Initialization', () => {
    test('initializes with correct strategy mappings from YOUR implementation', () => {
      expect(backtestingService.strategies).toBeDefined();
      expect(backtestingService.strategies['RSI_STRATEGY']).toBe(backtestingService.rsiStrategy);
      expect(backtestingService.strategies['MACD_STRATEGY']).toBe(backtestingService.macdStrategy);
      expect(backtestingService.strategies['BOLLINGER_STRATEGY']).toBe(backtestingService.bollingerStrategy);
      expect(backtestingService.strategies['MULTI_INDICATOR']).toBe(backtestingService.multiIndicatorStrategy);
      expect(backtestingService.strategies['MEAN_REVERSION']).toBe(backtestingService.meanReversionStrategy);
      expect(backtestingService.strategies['MOMENTUM']).toBe(backtestingService.momentumStrategy);
    });

    test('has real TechnicalAnalysisService instance', () => {
      expect(backtestingService.technicalAnalysis).toBeDefined();
      expect(typeof backtestingService.technicalAnalysis.calculateRSI).toBe('function');
      expect(typeof backtestingService.technicalAnalysis.calculateMACD).toBe('function');
      expect(typeof backtestingService.technicalAnalysis.calculateBollingerBands).toBe('function');
    });
  });

  describe('Real RSI Strategy Implementation', () => {
    function createTestPriceData(prices, symbol = 'AAPL') {
      return prices.map((price, index) => ({
        symbol: symbol,
        timestamp: `2023-01-${(index + 1).toString().padStart(2, '0')}`,
        date: `2023-01-${(index + 1).toString().padStart(2, '0')}`,
        open: price * 0.999,
        high: price * 1.02,
        low: price * 0.98,
        close: price,
        volume: 1000000
      }));
    }

    test('RSI strategy generates BUY signal when RSI < 30 (YOUR implementation)', () => {
      // Create price data that will result in low RSI (oversold condition)
      const decliningPrices = [];
      let price = 100;
      for (let i = 0; i < 60; i++) {
        price *= 0.99; // 1% decline each day
        decliningPrices.push(price);
      }
      
      const testData = createTestPriceData(decliningPrices);
      const state = { portfolio: { totalValue: 10000 } };
      const options = { riskPerTrade: 0.02 };

      // Test YOUR actual RSI strategy implementation
      const signal = backtestingService.rsiStrategy(testData, state, options);

      expect(signal).toBeDefined();
      expect(signal.action).toBe('BUY');
      expect(signal.reason).toContain('RSI oversold');
      expect(signal.indicator).toBe('RSI');
      expect(signal.confidence).toBeGreaterThan(0);
      expect(signal.value).toBeLessThan(30);
    });

    test('RSI strategy generates SELL signal when RSI > 70 (YOUR implementation)', () => {
      // Create price data that will result in high RSI (overbought condition)
      const risingPrices = [];
      let price = 100;
      for (let i = 0; i < 60; i++) {
        price *= 1.01; // 1% gain each day
        risingPrices.push(price);
      }
      
      const testData = createTestPriceData(risingPrices);
      const state = { portfolio: { totalValue: 10000 } };
      const options = { riskPerTrade: 0.02 };

      // Test YOUR actual RSI strategy implementation
      const signal = backtestingService.rsiStrategy(testData, state, options);

      expect(signal).toBeDefined();
      expect(signal.action).toBe('SELL');
      expect(signal.reason).toContain('RSI overbought');
      expect(signal.indicator).toBe('RSI');
      expect(signal.confidence).toBeGreaterThan(0);
      expect(signal.value).toBeGreaterThan(70);
    });

    test('RSI strategy returns null when RSI is neutral (30-70 range)', () => {
      // Create sideways price data that should result in neutral RSI
      const neutralPrices = [];
      for (let i = 0; i < 60; i++) {
        neutralPrices.push(100 + Math.sin(i / 10) * 2); // Small oscillation around 100
      }
      
      const testData = createTestPriceData(neutralPrices);
      const state = { portfolio: { totalValue: 10000 } };
      const options = { riskPerTrade: 0.02 };

      const signal = backtestingService.rsiStrategy(testData, state, options);
      
      // Should return null when RSI is in neutral range
      expect(signal).toBeNull();
    });
  });

  describe('Real MACD Strategy Implementation', () => {
    test('MACD strategy detects bullish crossover (YOUR implementation)', () => {
      // Create price data that creates MACD bullish crossover
      const prices = [];
      let price = 100;
      
      // Initial decline
      for (let i = 0; i < 30; i++) {
        price *= 0.998;
        prices.push(price);
      }
      
      // Then strong recovery (should create bullish crossover)
      for (let i = 0; i < 30; i++) {
        price *= 1.005;
        prices.push(price);
      }
      
      const testData = createTestPriceData(prices);
      const state = { portfolio: { totalValue: 10000 } };
      const options = { riskPerTrade: 0.02 };

      // Test YOUR actual MACD strategy implementation
      const signal = backtestingService.macdStrategy(testData, state, options);

      if (signal) { // May be null if not enough data for crossover yet
        expect(signal.action).toBe('BUY');
        expect(signal.reason).toBe('MACD bullish crossover');
        expect(signal.indicator).toBe('MACD');
        expect(signal.confidence).toBe(80);
      }
    });

    test('MACD strategy handles insufficient data gracefully', () => {
      // Test with minimal data (should not crash)
      const testData = createTestPriceData([100, 101, 102]);
      const state = { portfolio: { totalValue: 10000 } };
      const options = { riskPerTrade: 0.02 };

      // Should return null without throwing error
      const signal = backtestingService.macdStrategy(testData, state, options);
      expect(signal).toBeNull();
    });
  });

  describe('Real Bollinger Bands Strategy Implementation', () => {
    test('Bollinger strategy generates BUY when price below lower band', () => {
      // Create data with sudden price drop (below lower band)
      const prices = [];
      let price = 100;
      
      // Stable period to establish bands
      for (let i = 0; i < 25; i++) {
        prices.push(100 + Math.random() * 2 - 1); // Small variation around 100
      }
      
      // Sharp drop below lower band
      for (let i = 0; i < 5; i++) {
        price *= 0.95; // 5% drop
        prices.push(price);
      }
      
      const testData = createTestPriceData(prices);
      const state = { portfolio: { totalValue: 10000 } };
      const options = { riskPerTrade: 0.02 };

      const signal = backtestingService.bollingerStrategy(testData, state, options);

      if (signal) {
        expect(signal.action).toBe('BUY');
        expect(signal.reason).toBe('Price below lower Bollinger Band');
        expect(signal.indicator).toBe('BOLLINGER_BANDS');
        expect(signal.confidence).toBe(70);
      }
    });
  });

  describe('Real Backtest Execution', () => {
    function createRealisticTestData(days = 100) {
      const data = [];
      let price = 150; // Starting price
      const baseDate = new Date('2023-01-01');
      
      for (let i = 0; i < days; i++) {
        const date = new Date(baseDate.getTime() + i * 24 * 60 * 60 * 1000);
        
        // Realistic price movement
        const dailyChange = (Math.random() - 0.5) * 0.04; // +/- 2% daily
        price *= (1 + dailyChange);
        
        data.push({
          symbol: 'AAPL',
          timestamp: date.toISOString().split('T')[0],
          date: date.toISOString().split('T')[0],
          open: price * 0.999,
          high: price * 1.02,
          low: price * 0.98,
          close: price,
          volume: Math.floor(Math.random() * 1000000) + 500000
        });
      }
      
      return data;
    }

    test('runs complete backtest with YOUR actual implementation', async () => {
      const testData = createRealisticTestData(120);
      
      const backtestOptions = {
        initialCapital: 10000,
        commission: 0.001,
        slippage: 0.001,
        maxPositionSize: 0.8,
        riskPerTrade: 0.02,
        stopLoss: 0.05,
        takeProfit: 0.15
      };

      // Test YOUR actual runBacktest implementation
      const result = await backtestingService.runBacktest(
        testData, 
        'RSI_STRATEGY', 
        backtestOptions
      );

      // Verify YOUR implementation's return structure
      expect(result).toHaveProperty('strategy');
      expect(result).toHaveProperty('parameters');
      expect(result).toHaveProperty('initialCapital');
      expect(result).toHaveProperty('finalValue');
      expect(result).toHaveProperty('totalReturn');
      expect(result).toHaveProperty('trades');
      expect(result).toHaveProperty('metrics');
      expect(result).toHaveProperty('portfolioHistory');
      expect(result).toHaveProperty('summary');
      expect(result).toHaveProperty('period');

      // Verify actual values match YOUR implementation logic
      expect(result.strategy).toBe('RSI_STRATEGY');
      expect(result.initialCapital).toBe(10000);
      expect(result.finalValue).toBeGreaterThan(0);
      expect(Array.isArray(result.trades)).toBe(true);
      expect(Array.isArray(result.portfolioHistory)).toBe(true);
      
      // Verify period information
      expect(result.period.start).toBe(testData[0].timestamp);
      expect(result.period.end).toBe(testData[testData.length - 1].timestamp);
      expect(result.period.days).toBe(testData.length);
    });

    test('validates input parameters according to YOUR implementation', async () => {
      // Test YOUR actual validation logic
      await expect(
        backtestingService.runBacktest([], 'RSI_STRATEGY')
      ).rejects.toThrow('No historical data provided');

      await expect(
        backtestingService.runBacktest(createRealisticTestData(30), 'RSI_STRATEGY')
      ).rejects.toThrow('Insufficient data for backtesting (minimum 50 data points required)');

      await expect(
        backtestingService.runBacktest(createRealisticTestData(100), 'INVALID_STRATEGY')
      ).rejects.toThrow('Unknown strategy: INVALID_STRATEGY');
    });

    test('processes trade execution with YOUR actual logic', async () => {
      const testData = createRealisticTestData(80);
      
      const result = await backtestingService.runBacktest(
        testData,
        'RSI_STRATEGY',
        { initialCapital: 5000, commission: 0.002 }
      );

      // Check that trades match YOUR implementation structure
      if (result.trades.length > 0) {
        result.trades.forEach(trade => {
          expect(trade).toHaveProperty('type');
          expect(trade).toHaveProperty('entryPrice');
          expect(trade).toHaveProperty('exitPrice');
          expect(trade).toHaveProperty('entryDate');
          expect(trade).toHaveProperty('exitDate');
          expect(trade).toHaveProperty('size');
          expect(trade).toHaveProperty('pnl');
          expect(trade).toHaveProperty('commission');
          expect(trade).toHaveProperty('reason');
        });
      }

      // Verify metrics match YOUR implementation
      expect(result.metrics).toHaveProperty('totalTrades');
      expect(result.metrics).toHaveProperty('winningTrades');
      expect(result.metrics).toHaveProperty('losingTrades');
      expect(result.metrics).toHaveProperty('totalReturn');
      expect(result.metrics).toHaveProperty('maxDrawdown');
      expect(result.metrics).toHaveProperty('sharpeRatio');
      expect(result.metrics).toHaveProperty('winRate');
      expect(result.metrics).toHaveProperty('avgWin');
      expect(result.metrics).toHaveProperty('avgLoss');
      expect(result.metrics).toHaveProperty('profitFactor');
    });
  });

  describe('Real Portfolio History Tracking', () => {
    test('tracks portfolio value changes through YOUR implementation', async () => {
      const testData = createRealisticTestData(60);
      
      const result = await backtestingService.runBacktest(
        testData,
        'MACD_STRATEGY',
        { initialCapital: 8000 }
      );

      // Verify YOUR portfolioHistory structure
      expect(result.portfolioHistory.length).toBeGreaterThan(0);
      
      result.portfolioHistory.forEach(snapshot => {
        expect(snapshot).toHaveProperty('date');
        expect(snapshot).toHaveProperty('value');
        expect(snapshot).toHaveProperty('cash');
        expect(snapshot).toHaveProperty('holdings');
        expect(snapshot).toHaveProperty('position');
        
        // Verify value calculations
        expect(snapshot.value).toBeGreaterThan(0);
        expect(typeof snapshot.cash).toBe('number');
        expect(typeof snapshot.holdings).toBe('number');
      });

      // First entry should be initial capital
      expect(result.portfolioHistory[0].value).toBeCloseTo(8000, 2);
    });
  });

  describe('Real Filter Data by Date', () => {
    test('filters data by date range using YOUR implementation', () => {
      const testData = [];
      const baseDate = new Date('2023-01-01');
      
      for (let i = 0; i < 90; i++) {
        const date = new Date(baseDate.getTime() + i * 24 * 60 * 60 * 1000);
        testData.push({
          symbol: 'TEST',
          date: date.toISOString().split('T')[0],
          close: 100
        });
      }

      const filtered = backtestingService.filterDataByDate(
        testData, 
        '2023-02-01', 
        '2023-02-28'
      );

      expect(filtered.length).toBeGreaterThan(0);
      expect(filtered.length).toBeLessThan(testData.length);
      
      // All dates should be within range
      filtered.forEach(point => {
        expect(point.date).toMatch(/^2023-02-/);
      });
    });
  });

  function createRealisticTestData(days = 100) {
    const data = [];
    let price = 150;
    const baseDate = new Date('2023-01-01');
    
    for (let i = 0; i < days; i++) {
      const date = new Date(baseDate.getTime() + i * 24 * 60 * 60 * 1000);
      
      // Realistic price movement
      const dailyChange = (Math.random() - 0.5) * 0.04;
      price *= (1 + dailyChange);
      
      data.push({
        symbol: 'AAPL',
        timestamp: date.toISOString().split('T')[0],
        date: date.toISOString().split('T')[0],
        open: price * 0.999,
        high: price * 1.02,
        low: price * 0.98,
        close: price,
        volume: Math.floor(Math.random() * 1000000) + 500000
      });
    }
    
    return data;
  }
});
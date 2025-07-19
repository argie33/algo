/**
 * Frontend Utility Functions Unit Tests
 * Comprehensive testing for data formatting, calculations, and helper functions
 */

import { describe, test, expect, vi, beforeEach } from 'vitest';

// Mock API and external dependencies
const mockApiService = {
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  delete: vi.fn()
};

vi.mock('../services/api', () => ({
  default: mockApiService
}));

// Import utility functions to test
import {
  formatCurrency,
  formatPercent,
  formatNumber,
  calculatePercentChange,
  calculatePortfolioValue,
  validateEmail,
  validatePassword,
  debounce,
  throttle,
  generateId,
  sortByField,
  groupByField,
  filterByDateRange,
  calculateMovingAverage,
  calculateVolatility,
  formatDate,
  parseApiResponse,
  sanitizeInput,
  encryptSensitiveData,
  validateApiKey
} from '../utils/helpers';

import {
  portfolioCalculations,
  technicalIndicators,
  riskMetrics
} from '../utils/calculations';

describe('Data Formatting Utilities', () => {
  describe('formatCurrency', () => {
    test('should format positive numbers correctly', () => {
      expect(formatCurrency(1234.56)).toBe('$1,234.56');
      expect(formatCurrency(1000)).toBe('$1,000.00');
      expect(formatCurrency(0.99)).toBe('$0.99');
    });

    test('should format negative numbers correctly', () => {
      expect(formatCurrency(-1234.56)).toBe('-$1,234.56');
      expect(formatCurrency(-0.01)).toBe('-$0.01');
    });

    test('should handle zero values', () => {
      expect(formatCurrency(0)).toBe('$0.00');
      expect(formatCurrency(-0)).toBe('$0.00');
    });

    test('should handle large numbers', () => {
      expect(formatCurrency(1234567.89)).toBe('$1,234,567.89');
      expect(formatCurrency(1000000000)).toBe('$1,000,000,000.00');
    });

    test('should handle invalid inputs gracefully', () => {
      expect(formatCurrency(null)).toBe('$0.00');
      expect(formatCurrency(undefined)).toBe('$0.00');
      expect(formatCurrency(NaN)).toBe('$0.00');
      expect(formatCurrency('invalid')).toBe('$0.00');
    });

    test('should support different currencies', () => {
      expect(formatCurrency(1234.56, 'EUR')).toContain('1,234.56');
      expect(formatCurrency(1234.56, 'GBP')).toContain('1,234.56');
    });
  });

  describe('formatPercent', () => {
    test('should format percentages correctly', () => {
      expect(formatPercent(0.1234)).toBe('12.34%');
      expect(formatPercent(0.05)).toBe('5.00%');
      expect(formatPercent(-0.0567)).toBe('-5.67%');
    });

    test('should handle edge cases', () => {
      expect(formatPercent(0)).toBe('0.00%');
      expect(formatPercent(1)).toBe('100.00%');
      expect(formatPercent(-1)).toBe('-100.00%');
    });

    test('should support custom decimal places', () => {
      expect(formatPercent(0.12345, 1)).toBe('12.3%');
      expect(formatPercent(0.12345, 3)).toBe('12.345%');
    });

    test('should handle invalid inputs', () => {
      expect(formatPercent(null)).toBe('0.00%');
      expect(formatPercent(undefined)).toBe('0.00%');
      expect(formatPercent(NaN)).toBe('0.00%');
    });
  });

  describe('formatNumber', () => {
    test('should format numbers with appropriate suffixes', () => {
      expect(formatNumber(1234)).toBe('1.23K');
      expect(formatNumber(1234567)).toBe('1.23M');
      expect(formatNumber(1234567890)).toBe('1.23B');
      expect(formatNumber(1234567890123)).toBe('1.23T');
    });

    test('should handle small numbers', () => {
      expect(formatNumber(123)).toBe('123');
      expect(formatNumber(999)).toBe('999');
    });

    test('should handle negative numbers', () => {
      expect(formatNumber(-1234)).toBe('-1.23K');
      expect(formatNumber(-1234567)).toBe('-1.23M');
    });

    test('should support custom precision', () => {
      expect(formatNumber(1234567, 1)).toBe('1.2M');
      expect(formatNumber(1234567, 3)).toBe('1.235M');
    });
  });

  describe('formatDate', () => {
    test('should format dates correctly', () => {
      const date = new Date('2024-03-15T10:30:00Z');
      expect(formatDate(date)).toMatch(/Mar 15, 2024/);
    });

    test('should handle different date formats', () => {
      expect(formatDate('2024-03-15')).toBeTruthy();
      expect(formatDate(1710505800000)).toBeTruthy(); // timestamp
    });

    test('should support custom date formats', () => {
      const date = new Date('2024-03-15');
      expect(formatDate(date, 'short')).toMatch(/3\/15\/24/);
      expect(formatDate(date, 'long')).toMatch(/March 15, 2024/);
    });

    test('should handle invalid dates', () => {
      expect(formatDate(null)).toBe('Invalid Date');
      expect(formatDate('invalid')).toBe('Invalid Date');
    });
  });
});

describe('Financial Calculations', () => {
  describe('calculatePercentChange', () => {
    test('should calculate percentage change correctly', () => {
      expect(calculatePercentChange(100, 110)).toBe(0.1); // 10% increase
      expect(calculatePercentChange(100, 90)).toBe(-0.1); // 10% decrease
      expect(calculatePercentChange(50, 75)).toBe(0.5); // 50% increase
    });

    test('should handle zero values', () => {
      expect(calculatePercentChange(0, 10)).toBe(Infinity);
      expect(calculatePercentChange(10, 0)).toBe(-1);
      expect(calculatePercentChange(0, 0)).toBe(0);
    });

    test('should handle negative values', () => {
      expect(calculatePercentChange(-100, -50)).toBe(0.5);
      expect(calculatePercentChange(-50, -100)).toBe(-1);
    });
  });

  describe('calculatePortfolioValue', () => {
    test('should calculate total portfolio value', () => {
      const positions = [
        { shares: 100, currentPrice: 150 },
        { shares: 50, currentPrice: 200 },
        { shares: 200, currentPrice: 25 }
      ];

      const totalValue = calculatePortfolioValue(positions);
      expect(totalValue).toBe(30000); // 15000 + 10000 + 5000
    });

    test('should handle empty portfolio', () => {
      expect(calculatePortfolioValue([])).toBe(0);
      expect(calculatePortfolioValue(null)).toBe(0);
      expect(calculatePortfolioValue(undefined)).toBe(0);
    });

    test('should handle missing or invalid data', () => {
      const positions = [
        { shares: 100, currentPrice: 150 },
        { shares: null, currentPrice: 200 },
        { shares: 50, currentPrice: null },
        { shares: 'invalid', currentPrice: 100 }
      ];

      const totalValue = calculatePortfolioValue(positions);
      expect(totalValue).toBe(15000); // Only first position is valid
    });
  });

  describe('portfolioCalculations', () => {
    const mockPositions = [
      {
        symbol: 'AAPL',
        shares: 100,
        avgCost: 140,
        currentPrice: 150,
        marketValue: 15000
      },
      {
        symbol: 'MSFT',
        shares: 50,
        avgCost: 180,
        currentPrice: 200,
        marketValue: 10000
      }
    ];

    test('should calculate portfolio metrics correctly', () => {
      const metrics = portfolioCalculations.calculateMetrics(mockPositions);

      expect(metrics.totalValue).toBe(25000);
      expect(metrics.totalCost).toBe(23000); // (100 * 140) + (50 * 180)
      expect(metrics.totalGain).toBe(2000);
      expect(metrics.totalGainPercent).toBeCloseTo(0.087, 2);
    });

    test('should calculate position-level metrics', () => {
      const position = mockPositions[0];
      const metrics = portfolioCalculations.calculatePositionMetrics(position);

      expect(metrics.unrealizedGain).toBe(1000); // (150 - 140) * 100
      expect(metrics.unrealizedGainPercent).toBeCloseTo(0.071, 2);
      expect(metrics.weight).toBeCloseTo(0.6, 1); // 15000 / 25000
    });

    test('should calculate risk metrics', () => {
      const prices = [100, 105, 102, 108, 95, 110, 103];
      const volatility = portfolioCalculations.calculateVolatility(prices);

      expect(volatility).toBeGreaterThan(0);
      expect(volatility).toBeLessThan(1);
    });

    test('should calculate Sharpe ratio', () => {
      const returns = [0.05, -0.02, 0.08, 0.01, -0.03, 0.06];
      const riskFreeRate = 0.02;
      
      const sharpeRatio = portfolioCalculations.calculateSharpeRatio(returns, riskFreeRate);
      expect(typeof sharpeRatio).toBe('number');
      expect(sharpeRatio).not.toBeNaN();
    });
  });

  describe('technicalIndicators', () => {
    const prices = [100, 102, 104, 103, 105, 107, 106, 108, 110, 109];

    test('should calculate moving averages', () => {
      const sma5 = technicalIndicators.simpleMovingAverage(prices, 5);
      expect(sma5).toHaveLength(prices.length - 4);
      expect(sma5[0]).toBeCloseTo(102.8, 1);
    });

    test('should calculate exponential moving average', () => {
      const ema5 = technicalIndicators.exponentialMovingAverage(prices, 5);
      expect(ema5).toHaveLength(prices.length);
      expect(ema5[ema5.length - 1]).toBeGreaterThan(0);
    });

    test('should calculate RSI', () => {
      const extendedPrices = Array.from({ length: 20 }, (_, i) => 100 + Math.sin(i) * 10);
      const rsi = technicalIndicators.relativeStrengthIndex(extendedPrices, 14);
      
      expect(rsi).toHaveLength(extendedPrices.length - 13);
      rsi.forEach(value => {
        expect(value).toBeGreaterThanOrEqual(0);
        expect(value).toBeLessThanOrEqual(100);
      });
    });

    test('should calculate MACD', () => {
      const extendedPrices = Array.from({ length: 50 }, (_, i) => 100 + Math.sin(i * 0.1) * 5);
      const macd = technicalIndicators.macd(extendedPrices);
      
      expect(macd).toHaveProperty('macdLine');
      expect(macd).toHaveProperty('signalLine');
      expect(macd).toHaveProperty('histogram');
      expect(macd.macdLine.length).toBeGreaterThan(0);
    });

    test('should calculate Bollinger Bands', () => {
      const bands = technicalIndicators.bollingerBands(prices, 5, 2);
      
      expect(bands).toHaveProperty('upperBand');
      expect(bands).toHaveProperty('middleBand');
      expect(bands).toHaveProperty('lowerBand');
      
      bands.upperBand.forEach((upper, i) => {
        expect(upper).toBeGreaterThanOrEqual(bands.middleBand[i]);
        expect(bands.middleBand[i]).toBeGreaterThanOrEqual(bands.lowerBand[i]);
      });
    });
  });
});

describe('Validation Utilities', () => {
  describe('validateEmail', () => {
    test('should validate correct email formats', () => {
      expect(validateEmail('test@example.com')).toBe(true);
      expect(validateEmail('user.name+tag@domain.co.uk')).toBe(true);
      expect(validateEmail('test123@test-domain.org')).toBe(true);
    });

    test('should reject invalid email formats', () => {
      expect(validateEmail('invalid-email')).toBe(false);
      expect(validateEmail('@domain.com')).toBe(false);
      expect(validateEmail('test@')).toBe(false);
      expect(validateEmail('test.domain.com')).toBe(false);
      expect(validateEmail('')).toBe(false);
      expect(validateEmail(null)).toBe(false);
    });
  });

  describe('validatePassword', () => {
    test('should validate strong passwords', () => {
      expect(validatePassword('StrongP@ssw0rd')).toBe(true);
      expect(validatePassword('Complex123!')).toBe(true);
      expect(validatePassword('MySecure#Pass1')).toBe(true);
    });

    test('should reject weak passwords', () => {
      expect(validatePassword('weak')).toBe(false);
      expect(validatePassword('password')).toBe(false);
      expect(validatePassword('12345678')).toBe(false);
      expect(validatePassword('ALLUPPERCASE')).toBe(false);
      expect(validatePassword('alllowercase')).toBe(false);
    });

    test('should validate password requirements', () => {
      const result = validatePassword('TestP@ss123', { detailed: true });
      expect(result).toHaveProperty('valid');
      expect(result).toHaveProperty('requirements');
      expect(result.requirements).toHaveProperty('minLength');
      expect(result.requirements).toHaveProperty('hasUppercase');
      expect(result.requirements).toHaveProperty('hasLowercase');
      expect(result.requirements).toHaveProperty('hasNumbers');
      expect(result.requirements).toHaveProperty('hasSpecialChars');
    });
  });

  describe('validateApiKey', () => {
    test('should validate Alpaca API keys', () => {
      expect(validateApiKey('PKTEST123456789012345678', 'alpaca')).toBe(true);
      expect(validateApiKey('PK123456789012345678901', 'alpaca')).toBe(true);
    });

    test('should validate Polygon API keys', () => {
      expect(validateApiKey('abcdefghijklmnopqrstuvwxyz123456', 'polygon')).toBe(true);
    });

    test('should validate Finnhub API keys', () => {
      expect(validateApiKey('abcdefghijklmnopqrst', 'finnhub')).toBe(true);
    });

    test('should reject invalid API keys', () => {
      expect(validateApiKey('invalid', 'alpaca')).toBe(false);
      expect(validateApiKey('PK123', 'alpaca')).toBe(false); // Too short
      expect(validateApiKey('ABC123', 'polygon')).toBe(false); // Wrong format
      expect(validateApiKey('', 'finnhub')).toBe(false);
    });

    test('should detect placeholder values', () => {
      expect(validateApiKey('test', 'alpaca')).toBe(false);
      expect(validateApiKey('password', 'polygon')).toBe(false);
      expect(validateApiKey('your-api-key', 'finnhub')).toBe(false);
    });
  });

  describe('sanitizeInput', () => {
    test('should sanitize HTML content', () => {
      expect(sanitizeInput('<script>alert("xss")</script>')).toBe('');
      expect(sanitizeInput('<b>Bold Text</b>')).toBe('Bold Text');
      expect(sanitizeInput('Normal text')).toBe('Normal text');
    });

    test('should handle special characters', () => {
      expect(sanitizeInput('Test & Co.')).toBe('Test & Co.');
      expect(sanitizeInput('Price: $100.50')).toBe('Price: $100.50');
    });

    test('should limit input length', () => {
      const longInput = 'a'.repeat(1000);
      const sanitized = sanitizeInput(longInput, { maxLength: 100 });
      expect(sanitized.length).toBeLessThanOrEqual(100);
    });
  });
});

describe('Performance Utilities', () => {
  describe('debounce', () => {
    test('should debounce function calls', async () => {
      const mockFn = vi.fn();
      const debouncedFn = debounce(mockFn, 100);

      // Call multiple times rapidly
      debouncedFn();
      debouncedFn();
      debouncedFn();

      // Should not have been called yet
      expect(mockFn).not.toHaveBeenCalled();

      // Wait for debounce delay
      await new Promise(resolve => setTimeout(resolve, 150));

      // Should have been called only once
      expect(mockFn).toHaveBeenCalledTimes(1);
    });

    test('should pass arguments correctly', async () => {
      const mockFn = vi.fn();
      const debouncedFn = debounce(mockFn, 50);

      debouncedFn('arg1', 'arg2');

      await new Promise(resolve => setTimeout(resolve, 100));

      expect(mockFn).toHaveBeenCalledWith('arg1', 'arg2');
    });
  });

  describe('throttle', () => {
    test('should throttle function calls', async () => {
      const mockFn = vi.fn();
      const throttledFn = throttle(mockFn, 100);

      // Call multiple times rapidly
      throttledFn();
      throttledFn();
      throttledFn();

      // Should have been called immediately once
      expect(mockFn).toHaveBeenCalledTimes(1);

      // Wait for throttle delay
      await new Promise(resolve => setTimeout(resolve, 150));

      // Call again
      throttledFn();
      expect(mockFn).toHaveBeenCalledTimes(2);
    });
  });
});

describe('Data Processing Utilities', () => {
  describe('sortByField', () => {
    const testData = [
      { name: 'Apple', price: 150, volume: 1000 },
      { name: 'Microsoft', price: 200, volume: 800 },
      { name: 'Tesla', price: 120, volume: 1200 }
    ];

    test('should sort by numeric field ascending', () => {
      const sorted = sortByField(testData, 'price', 'asc');
      expect(sorted[0].price).toBe(120);
      expect(sorted[2].price).toBe(200);
    });

    test('should sort by numeric field descending', () => {
      const sorted = sortByField(testData, 'price', 'desc');
      expect(sorted[0].price).toBe(200);
      expect(sorted[2].price).toBe(120);
    });

    test('should sort by string field', () => {
      const sorted = sortByField(testData, 'name', 'asc');
      expect(sorted[0].name).toBe('Apple');
      expect(sorted[2].name).toBe('Tesla');
    });

    test('should handle missing fields', () => {
      const dataWithMissing = [
        { name: 'Apple', price: 150 },
        { name: 'Microsoft' }, // Missing price
        { name: 'Tesla', price: 120 }
      ];

      const sorted = sortByField(dataWithMissing, 'price', 'asc');
      expect(sorted).toHaveLength(3);
    });
  });

  describe('groupByField', () => {
    const testData = [
      { name: 'Apple', sector: 'Technology', price: 150 },
      { name: 'Microsoft', sector: 'Technology', price: 200 },
      { name: 'JPMorgan', sector: 'Financial', price: 140 },
      { name: 'Goldman Sachs', sector: 'Financial', price: 300 }
    ];

    test('should group by field correctly', () => {
      const grouped = groupByField(testData, 'sector');
      
      expect(grouped).toHaveProperty('Technology');
      expect(grouped).toHaveProperty('Financial');
      expect(grouped.Technology).toHaveLength(2);
      expect(grouped.Financial).toHaveLength(2);
    });

    test('should handle empty arrays', () => {
      const grouped = groupByField([], 'sector');
      expect(Object.keys(grouped)).toHaveLength(0);
    });

    test('should handle missing group field', () => {
      const dataWithMissing = [
        { name: 'Apple', sector: 'Technology' },
        { name: 'Unknown' }, // Missing sector
        { name: 'Microsoft', sector: 'Technology' }
      ];

      const grouped = groupByField(dataWithMissing, 'sector');
      expect(grouped).toHaveProperty('Technology');
      expect(grouped).toHaveProperty('undefined');
    });
  });

  describe('filterByDateRange', () => {
    const testData = [
      { date: '2024-01-15', value: 100 },
      { date: '2024-02-15', value: 110 },
      { date: '2024-03-15', value: 120 },
      { date: '2024-04-15', value: 130 }
    ];

    test('should filter by date range', () => {
      const filtered = filterByDateRange(
        testData,
        new Date('2024-02-01'),
        new Date('2024-03-31'),
        'date'
      );

      expect(filtered).toHaveLength(2);
      expect(filtered[0].date).toBe('2024-02-15');
      expect(filtered[1].date).toBe('2024-03-15');
    });

    test('should handle invalid date ranges', () => {
      const filtered = filterByDateRange(
        testData,
        new Date('2024-06-01'),
        new Date('2024-07-01'),
        'date'
      );

      expect(filtered).toHaveLength(0);
    });

    test('should handle missing date field', () => {
      const dataWithMissing = [
        { date: '2024-01-15', value: 100 },
        { value: 110 }, // Missing date
        { date: '2024-03-15', value: 120 }
      ];

      const filtered = filterByDateRange(
        dataWithMissing,
        new Date('2024-01-01'),
        new Date('2024-12-31'),
        'date'
      );

      expect(filtered).toHaveLength(2);
    });
  });
});

describe('API Response Processing', () => {
  describe('parseApiResponse', () => {
    test('should parse successful API responses', () => {
      const response = {
        success: true,
        data: { symbol: 'AAPL', price: 150 },
        message: 'Success'
      };

      const parsed = parseApiResponse(response);
      expect(parsed.success).toBe(true);
      expect(parsed.data.symbol).toBe('AAPL');
    });

    test('should handle API error responses', () => {
      const response = {
        success: false,
        error: 'Invalid symbol',
        details: { code: 'INVALID_SYMBOL' }
      };

      const parsed = parseApiResponse(response);
      expect(parsed.success).toBe(false);
      expect(parsed.error).toBe('Invalid symbol');
    });

    test('should handle malformed responses', () => {
      const response = 'invalid json response';
      const parsed = parseApiResponse(response);
      
      expect(parsed.success).toBe(false);
      expect(parsed.error).toContain('parsing');
    });

    test('should extract nested data correctly', () => {
      const response = {
        success: true,
        data: {
          quotes: [
            { symbol: 'AAPL', price: 150 },
            { symbol: 'MSFT', price: 200 }
          ],
          metadata: { timestamp: '2024-03-15' }
        }
      };

      const parsed = parseApiResponse(response);
      expect(parsed.data.quotes).toHaveLength(2);
      expect(parsed.data.metadata.timestamp).toBe('2024-03-15');
    });
  });
});

describe('Security Utilities', () => {
  describe('encryptSensitiveData', () => {
    test('should encrypt data consistently', () => {
      const data = 'sensitive-api-key';
      const encrypted1 = encryptSensitiveData(data);
      const encrypted2 = encryptSensitiveData(data);

      expect(encrypted1).toBeTruthy();
      expect(encrypted2).toBeTruthy();
      expect(encrypted1).not.toBe(data); // Should be encrypted
      expect(encrypted1).not.toBe(encrypted2); // Should use different salt/iv
    });

    test('should handle empty or null data', () => {
      expect(encryptSensitiveData('')).toBe('');
      expect(encryptSensitiveData(null)).toBe('');
      expect(encryptSensitiveData(undefined)).toBe('');
    });

    test('should encrypt different data types', () => {
      expect(encryptSensitiveData('string')).toBeTruthy();
      expect(encryptSensitiveData(12345)).toBeTruthy();
      expect(encryptSensitiveData({ key: 'value' })).toBeTruthy();
    });
  });

  describe('generateId', () => {
    test('should generate unique IDs', () => {
      const id1 = generateId();
      const id2 = generateId();

      expect(id1).toBeTruthy();
      expect(id2).toBeTruthy();
      expect(id1).not.toBe(id2);
      expect(typeof id1).toBe('string');
      expect(typeof id2).toBe('string');
    });

    test('should generate IDs of correct length', () => {
      const id = generateId();
      expect(id.length).toBeGreaterThan(8);
      expect(id.length).toBeLessThan(50);
    });

    test('should generate URL-safe IDs', () => {
      const id = generateId();
      expect(id).toMatch(/^[a-zA-Z0-9_-]+$/);
    });
  });
});
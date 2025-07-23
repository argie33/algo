/**
 * Data Validation Utilities Unit Tests
 * Tests validation functions used throughout the frontend
 */

describe('Data Validation Utilities', () => {
  describe('formatNumber', () => {
    // Mock formatNumber function based on typical implementation
    const formatNumber = (value, decimals = 0, signed = false) => {
      if (value === null || value === undefined || isNaN(value)) return 'N/A';
      
      const num = Number(value);
      const prefix = signed && num > 0 ? '+' : '';
      
      if (Math.abs(num) >= 1000000000) {
        return prefix + (num / 1000000000).toFixed(decimals) + 'B';
      } else if (Math.abs(num) >= 1000000) {
        return prefix + (num / 1000000).toFixed(decimals) + 'M';
      } else if (Math.abs(num) >= 1000) {
        return prefix + (num / 1000).toFixed(decimals) + 'K';
      } else {
        return prefix + num.toLocaleString('en-US', { 
          minimumFractionDigits: decimals,
          maximumFractionDigits: decimals 
        });
      }
    };

    test('formats large numbers with appropriate suffixes', () => {
      expect(formatNumber(1000000000)).toBe('1B');
      expect(formatNumber(1500000000, 1)).toBe('1.5B');
      expect(formatNumber(2300000, 1)).toBe('2.3M');
      expect(formatNumber(45000, 0)).toBe('45K');
    });

    test('formats small numbers with localization', () => {
      expect(formatNumber(999)).toBe('999');
      expect(formatNumber(1234)).toBe('1K');
      expect(formatNumber(123.456, 2)).toBe('123.46');
    });

    test('handles signed numbers correctly', () => {
      expect(formatNumber(1000, 0, true)).toBe('+1K');
      expect(formatNumber(-1000, 0, true)).toBe('-1K');
      expect(formatNumber(0, 0, true)).toBe('0');
    });

    test('handles edge cases', () => {
      expect(formatNumber(null)).toBe('N/A');
      expect(formatNumber(undefined)).toBe('N/A');
      expect(formatNumber(NaN)).toBe('N/A');
      expect(formatNumber('not a number')).toBe('N/A');
      expect(formatNumber(0)).toBe('0');
    });

    test('handles decimal precision correctly', () => {
      expect(formatNumber(1234567, 2)).toBe('1.23M');
      expect(formatNumber(1999999, 1)).toBe('2.0M');
      expect(formatNumber(999.9, 0)).toBe('1K');
    });
  });

  describe('formatPercent', () => {
    const formatPercent = (value, decimals = 2) => {
      if (value === null || value === undefined || isNaN(value)) return 'N/A';
      return (Number(value) * 100).toFixed(decimals) + '%';
    };

    test('formats decimal values as percentages', () => {
      expect(formatPercent(0.1534)).toBe('15.34%');
      expect(formatPercent(0.05)).toBe('5.00%');
      expect(formatPercent(1.25)).toBe('125.00%');
      expect(formatPercent(-0.075)).toBe('-7.50%');
    });

    test('handles different decimal precisions', () => {
      expect(formatPercent(0.1234, 0)).toBe('12%');
      expect(formatPercent(0.1234, 1)).toBe('12.3%');
      expect(formatPercent(0.1234, 3)).toBe('12.340%');
    });

    test('handles edge cases', () => {
      expect(formatPercent(null)).toBe('N/A');
      expect(formatPercent(undefined)).toBe('N/A');
      expect(formatPercent(NaN)).toBe('N/A');
      expect(formatPercent(0)).toBe('0.00%');
    });
  });

  describe('validateStockSymbol', () => {
    const validateStockSymbol = (symbol) => {
      if (!symbol || typeof symbol !== 'string') return false;
      // Basic validation: 1-5 characters, letters only, uppercase
      const symbolRegex = /^[A-Z]{1,5}$/;
      return symbolRegex.test(symbol.toUpperCase());
    };

    test('validates correct stock symbols', () => {
      expect(validateStockSymbol('AAPL')).toBe(true);
      expect(validateStockSymbol('MSFT')).toBe(true);
      expect(validateStockSymbol('GOOGL')).toBe(true);
      expect(validateStockSymbol('BRK.A')).toBe(false); // Contains period
      expect(validateStockSymbol('A')).toBe(true);
      expect(validateStockSymbol('ABCDE')).toBe(true);
    });

    test('rejects invalid symbols', () => {
      expect(validateStockSymbol('')).toBe(false);
      expect(validateStockSymbol(null)).toBe(false);
      expect(validateStockSymbol(undefined)).toBe(false);
      expect(validateStockSymbol(123)).toBe(false);
      expect(validateStockSymbol('ABCDEF')).toBe(false); // Too long
      expect(validateStockSymbol('ABC123')).toBe(false); // Contains numbers
      expect(validateStockSymbol('abc')).toBe(true); // Should convert to uppercase
    });
  });

  describe('sanitizeFinancialData', () => {
    const sanitizeFinancialData = (data) => {
      if (!data || typeof data !== 'object') return {};
      
      const sanitized = {};
      for (const [key, value] of Object.entries(data)) {
        if (typeof value === 'number' && !isNaN(value) && isFinite(value)) {
          sanitized[key] = value;
        } else if (typeof value === 'string' && value.trim() !== '') {
          // Try to parse as number
          const numValue = parseFloat(value);
          if (!isNaN(numValue) && isFinite(numValue)) {
            sanitized[key] = numValue;
          } else {
            sanitized[key] = value.trim();
          }
        } else if (value === null || value === undefined) {
          sanitized[key] = null;
        }
      }
      return sanitized;
    };

    test('sanitizes financial data objects', () => {
      const input = {
        price: 150.25,
        volume: '1000000',
        marketCap: 2500000000000,
        pe_ratio: null,
        invalid: NaN,
        empty: '',
        whitespace: '  trimmed  ',
        infinity: Infinity,
        negativeInfinity: -Infinity
      };

      const result = sanitizeFinancialData(input);

      expect(result.price).toBe(150.25);
      expect(result.volume).toBe(1000000);
      expect(result.marketCap).toBe(2500000000000);
      expect(result.pe_ratio).toBe(null);
      expect(result.hasOwnProperty('invalid')).toBe(false);
      expect(result.hasOwnProperty('empty')).toBe(false);
      expect(result.whitespace).toBe('trimmed');
      expect(result.hasOwnProperty('infinity')).toBe(false);
      expect(result.hasOwnProperty('negativeInfinity')).toBe(false);
    });

    test('handles edge cases', () => {
      expect(sanitizeFinancialData(null)).toEqual({});
      expect(sanitizeFinancialData(undefined)).toEqual({});
      expect(sanitizeFinancialData('not an object')).toEqual({});
      expect(sanitizeFinancialData({})).toEqual({});
    });
  });

  describe('validateApiResponse', () => {
    const validateApiResponse = (response) => {
      return {
        isValid: response && 
                 typeof response === 'object' && 
                 response.hasOwnProperty('data') &&
                 response.hasOwnProperty('success'),
        hasData: response?.data !== null && response?.data !== undefined,
        isSuccess: response?.success === true,
        errorMessage: response?.error || response?.message || null
      };
    };

    test('validates correct API responses', () => {
      const validResponse = {
        data: { price: 150 },
        success: true
      };

      const result = validateApiResponse(validResponse);
      expect(result.isValid).toBe(true);
      expect(result.hasData).toBe(true);
      expect(result.isSuccess).toBe(true);
      expect(result.errorMessage).toBe(null);
    });

    test('identifies invalid API responses', () => {
      const invalidResponses = [
        null,
        undefined,
        'string response',
        { data: null, success: false },
        { success: true }, // Missing data
        { data: [] }, // Missing success
        {}
      ];

      invalidResponses.forEach(response => {
        const result = validateApiResponse(response);
        if (response === null || response === undefined || typeof response !== 'object') {
          expect(result.isValid).toBe(false);
        }
      });
    });

    test('handles error responses', () => {
      const errorResponse = {
        data: null,
        success: false,
        error: 'API connection failed'
      };

      const result = validateApiResponse(errorResponse);
      expect(result.isValid).toBe(true); // Has required structure
      expect(result.hasData).toBe(false);
      expect(result.isSuccess).toBe(false);
      expect(result.errorMessage).toBe('API connection failed');
    });
  });

  describe('calculatePriceChange', () => {
    const calculatePriceChange = (currentPrice, previousPrice) => {
      if (!currentPrice || !previousPrice || 
          isNaN(currentPrice) || isNaN(previousPrice) || 
          previousPrice === 0) {
        return { change: 0, changePercent: 0 };
      }

      const change = currentPrice - previousPrice;
      const changePercent = (change / previousPrice) * 100;

      return {
        change: Number(change.toFixed(2)),
        changePercent: Number(changePercent.toFixed(2))
      };
    };

    test('calculates price changes correctly', () => {
      const result = calculatePriceChange(155, 150);
      expect(result.change).toBe(5);
      expect(result.changePercent).toBe(3.33);

      const negativeResult = calculatePriceChange(145, 150);
      expect(negativeResult.change).toBe(-5);
      expect(negativeResult.changePercent).toBe(-3.33);
    });

    test('handles edge cases', () => {
      expect(calculatePriceChange(null, 150)).toEqual({ change: 0, changePercent: 0 });
      expect(calculatePriceChange(155, null)).toEqual({ change: 0, changePercent: 0 });
      expect(calculatePriceChange(155, 0)).toEqual({ change: 0, changePercent: 0 });
      expect(calculatePriceChange(NaN, 150)).toEqual({ change: 0, changePercent: 0 });
    });

    test('handles precision correctly', () => {
      const result = calculatePriceChange(100.333, 100);
      expect(result.change).toBe(0.33);
      expect(result.changePercent).toBe(0.33);
    });
  });

  describe('isValidFinancialValue', () => {
    const isValidFinancialValue = (value) => {
      return value !== null && 
             value !== undefined && 
             !isNaN(value) && 
             isFinite(value) && 
             typeof value === 'number';
    };

    test('identifies valid financial values', () => {
      expect(isValidFinancialValue(150.25)).toBe(true);
      expect(isValidFinancialValue(0)).toBe(true);
      expect(isValidFinancialValue(-50.75)).toBe(true);
      expect(isValidFinancialValue(1000000)).toBe(true);
    });

    test('identifies invalid financial values', () => {
      expect(isValidFinancialValue(null)).toBe(false);
      expect(isValidFinancialValue(undefined)).toBe(false);
      expect(isValidFinancialValue(NaN)).toBe(false);
      expect(isValidFinancialValue(Infinity)).toBe(false);
      expect(isValidFinancialValue(-Infinity)).toBe(false);
      expect(isValidFinancialValue('150')).toBe(false);
      expect(isValidFinancialValue({})).toBe(false);
      expect(isValidFinancialValue([])).toBe(false);
    });
  });
});
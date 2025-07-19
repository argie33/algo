/**
 * Real API Wrapper Unit Tests
 * Testing the actual apiWrapper.js with comprehensive error handling, logging, and performance monitoring
 * CRITICAL COMPONENT - Handles all API call standardization, error management, and monitoring
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Mock ErrorManager dependency
const mockErrorManager = {
  handleError: vi.fn((config) => config),
  CATEGORIES: {
    API: 'api',
    PERFORMANCE: 'performance'
  },
  SEVERITY: {
    LOW: 'low',
    MEDIUM: 'medium',
    HIGH: 'high'
  }
};

vi.mock('../../../error/ErrorManager', () => ({
  default: mockErrorManager
}));

// Mock navigator
Object.defineProperty(global, 'navigator', {
  value: {
    userAgent: 'Test Browser',
    onLine: true
  },
  writable: true
});

// Mock performance API
Object.defineProperty(global, 'performance', {
  value: {
    now: vi.fn(() => Date.now())
  },
  writable: true
});

// Import the REAL ApiWrapper after mocks
let apiWrapper;

describe('🔧 Real API Wrapper', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    
    // Reset performance.now to return predictable values
    global.performance.now
      .mockReturnValueOnce(1000) // Start time
      .mockReturnValueOnce(1100); // End time (100ms duration)
    
    // Mock console methods
    vi.spyOn(console, 'log').mockImplementation(() => {});
    vi.spyOn(console, 'error').mockImplementation(() => {});
    
    // Dynamically import to get fresh instance
    const apiWrapperModule = await import('../../../services/apiWrapper');
    apiWrapper = apiWrapperModule.default;
    
    // Reset state
    apiWrapper.resetStats();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Service Initialization', () => {
    it('should initialize with empty state', () => {
      expect(apiWrapper.requestCount).toBe(0);
      expect(apiWrapper.performanceMetrics.size).toBe(0);
      expect(apiWrapper.errorPatterns.size).toBe(0);
    });
  });

  describe('API Function Wrapping', () => {
    it('should wrap successful API function calls', async () => {
      const mockApiFunction = vi.fn().mockResolvedValue({ data: 'success' });
      const wrappedFunction = apiWrapper.wrap(mockApiFunction, {
        operation: 'testOperation'
      });
      
      const result = await wrappedFunction('arg1', 'arg2');
      
      expect(mockApiFunction).toHaveBeenCalledWith('arg1', 'arg2');
      expect(result).toEqual({ data: 'success' });
      expect(apiWrapper.requestCount).toBe(1);
    });

    it('should handle failed API function calls', async () => {
      const mockError = new Error('API Error');
      mockError.response = { status: 500, statusText: 'Internal Server Error' };
      
      const mockApiFunction = vi.fn().mockRejectedValue(mockError);
      const wrappedFunction = apiWrapper.wrap(mockApiFunction, {
        operation: 'failingOperation'
      });
      
      await expect(wrappedFunction()).rejects.toMatchObject({
        type: 'api_request_failed',
        message: expect.stringContaining('failingOperation failed'),
        userMessage: expect.any(String),
        suggestedActions: expect.any(Array)
      });
      
      expect(mockErrorManager.handleError).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'api_request_failed',
          severity: 'high'
        })
      );
    });

    it('should apply input validation when provided', async () => {
      const mockApiFunction = vi.fn().mockResolvedValue({ data: 'success' });
      const validateInput = vi.fn().mockReturnValue({ valid: false, message: 'Invalid input' });
      
      const wrappedFunction = apiWrapper.wrap(mockApiFunction, {
        operation: 'validatedOperation',
        validateInput
      });
      
      await expect(wrappedFunction('invalid')).rejects.toThrow('Input validation failed: Invalid input');
      
      expect(validateInput).toHaveBeenCalledWith('invalid');
      expect(mockApiFunction).not.toHaveBeenCalled();
    });

    it('should apply response transformation when provided', async () => {
      const mockApiFunction = vi.fn().mockResolvedValue({ raw: 'data' });
      const transformResponse = vi.fn().mockReturnValue({ transformed: 'data' });
      
      const wrappedFunction = apiWrapper.wrap(mockApiFunction, {
        operation: 'transformedOperation',
        transformResponse
      });
      
      const result = await wrappedFunction();
      
      expect(transformResponse).toHaveBeenCalledWith({ raw: 'data' });
      expect(result).toEqual({ transformed: 'data' });
    });

    it('should generate unique request IDs', async () => {
      const mockApiFunction = vi.fn().mockResolvedValue({ data: 'success' });
      const wrappedFunction = apiWrapper.wrap(mockApiFunction);
      
      await wrappedFunction();
      await wrappedFunction();
      
      expect(apiWrapper.requestCount).toBe(2);
      expect(console.log).toHaveBeenCalledWith(
        expect.stringContaining('started'),
        expect.objectContaining({
          requestId: expect.stringMatching(/^req_1_\d+$/),
          requestCount: 1
        })
      );
      expect(console.log).toHaveBeenCalledWith(
        expect.stringContaining('started'),
        expect.objectContaining({
          requestId: expect.stringMatching(/^req_2_\d+$/),
          requestCount: 2
        })
      );
    });
  });

  describe('Request Logging', () => {
    it('should log request start with sanitized arguments', async () => {
      const mockApiFunction = vi.fn().mockResolvedValue({ data: 'success' });
      const wrappedFunction = apiWrapper.wrap(mockApiFunction, {
        operation: 'testOperation'
      });
      
      await wrappedFunction({ username: 'test', password: 'secret' });
      
      expect(console.log).toHaveBeenCalledWith(
        '🚀 [API] testOperation started',
        expect.objectContaining({
          requestId: expect.any(String),
          timestamp: expect.any(String),
          args: [{ username: 'test', password: '[REDACTED]' }],
          requestCount: 1
        })
      );
    });

    it('should log successful completion with performance metrics', async () => {
      global.performance.now
        .mockReturnValueOnce(1000) // Start
        .mockReturnValueOnce(1150); // End (150ms)
      
      const mockApiFunction = vi.fn().mockResolvedValue({ data: 'success' });
      const wrappedFunction = apiWrapper.wrap(mockApiFunction, {
        operation: 'testOperation'
      });
      
      await wrappedFunction();
      
      expect(console.log).toHaveBeenNthCalledWith(2,
        '✅ [API] testOperation completed successfully',
        expect.objectContaining({
          requestId: expect.any(String),
          duration: expect.stringMatching(/\d+\.\d+ms/),
          responseSize: expect.any(Number),
          timestamp: expect.any(String)
        })
      );
    });

    it('should track slow requests', async () => {
      global.performance.now
        .mockReturnValueOnce(1000) // Start
        .mockReturnValueOnce(7000); // End (6000ms - slow)
      
      const mockApiFunction = vi.fn().mockResolvedValue({ data: 'success' });
      const wrappedFunction = apiWrapper.wrap(mockApiFunction, {
        operation: 'slowOperation'
      });
      
      await wrappedFunction();
      
      expect(mockErrorManager.handleError).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'slow_api_request',
          category: 'performance',
          severity: 'medium',
          context: expect.objectContaining({
            operation: 'slowOperation',
            duration: 6000
          })
        })
      );
    });
  });

  describe('Error Handling', () => {
    it('should handle different HTTP status codes appropriately', async () => {
      const testCases = [
        { status: 400, expectedSeverity: 'medium', expectedMessage: 'Invalid request' },
        { status: 401, expectedSeverity: 'high', expectedMessage: 'Please sign in to continue' },
        { status: 403, expectedSeverity: 'high', expectedMessage: 'don\'t have permission' },
        { status: 404, expectedSeverity: 'low', expectedMessage: 'not found' },
        { status: 429, expectedSeverity: 'medium', expectedMessage: 'Too many requests' },
        { status: 500, expectedSeverity: 'high', expectedMessage: 'Server error' }
      ];
      
      for (const testCase of testCases) {
        const mockError = new Error('Test error');
        mockError.response = { status: testCase.status };
        
        const mockApiFunction = vi.fn().mockRejectedValue(mockError);
        const wrappedFunction = apiWrapper.wrap(mockApiFunction, {
          operation: `test_${testCase.status}`
        });
        
        try {
          await wrappedFunction();
        } catch (error) {
          expect(error.userMessage).toContain(testCase.expectedMessage);
          expect(error.severity).toBe(testCase.expectedSeverity);
        }
      }
    });

    it('should handle network offline scenarios', async () => {
      navigator.onLine = false;
      
      const mockError = new Error('Network error');
      const mockApiFunction = vi.fn().mockRejectedValue(mockError);
      const wrappedFunction = apiWrapper.wrap(mockApiFunction);
      
      try {
        await wrappedFunction();
      } catch (error) {
        expect(error.userMessage).toContain('No internet connection');
        expect(error.suggestedActions).toContain('Check your internet connection');
      }
      
      navigator.onLine = true; // Reset
    });

    it('should handle timeout errors', async () => {
      const mockError = new Error('Request timeout');
      const mockApiFunction = vi.fn().mockRejectedValue(mockError);
      const wrappedFunction = apiWrapper.wrap(mockApiFunction);
      
      try {
        await wrappedFunction();
      } catch (error) {
        expect(error.userMessage).toContain('Request timed out');
      }
    });

    it('should provide operation-specific suggestions', async () => {
      const mockError = new Error('Test error');
      mockError.response = { status: 500 };
      
      const mockApiFunction = vi.fn().mockRejectedValue(mockError);
      const wrappedFunction = apiWrapper.wrap(mockApiFunction, {
        operation: 'portfolioOperation'
      });
      
      try {
        await wrappedFunction();
      } catch (error) {
        expect(error.suggestedActions).toContain('Check your API key configuration');
        expect(error.suggestedActions).toContain('Verify your brokerage account connection');
      }
    });

    it('should provide market-specific suggestions', async () => {
      const mockError = new Error('Test error');
      mockError.response = { status: 500 };
      
      const mockApiFunction = vi.fn().mockRejectedValue(mockError);
      const wrappedFunction = apiWrapper.wrap(mockApiFunction, {
        operation: 'marketDataOperation'
      });
      
      try {
        await wrappedFunction();
      } catch (error) {
        expect(error.suggestedActions).toContain('Verify market data subscription');
        expect(error.suggestedActions).toContain('Check market hours if applicable');
      }
    });
  });

  describe('Performance Monitoring', () => {
    it('should record performance metrics for operations', async () => {
      global.performance.now
        .mockReturnValueOnce(1000).mockReturnValueOnce(1200) // 200ms
        .mockReturnValueOnce(2000).mockReturnValueOnce(2300); // 300ms
      
      const mockApiFunction = vi.fn().mockResolvedValue({ data: 'success' });
      const wrappedFunction = apiWrapper.wrap(mockApiFunction, {
        operation: 'testOperation'
      });
      
      await wrappedFunction();
      await wrappedFunction();
      
      const stats = apiWrapper.getPerformanceStats();
      
      expect(stats.testOperation).toEqual({
        count: 2,
        totalTime: 500,
        minTime: 200,
        maxTime: 300,
        avgTime: 250
      });
    });

    it('should calculate performance grades correctly', () => {
      expect(apiWrapper.getPerformanceGrade(100)).toBe('excellent');
      expect(apiWrapper.getPerformanceGrade(300)).toBe('good');
      expect(apiWrapper.getPerformanceGrade(750)).toBe('fair');
      expect(apiWrapper.getPerformanceGrade(1500)).toBe('slow');
      expect(apiWrapper.getPerformanceGrade(3000)).toBe('very_slow');
    });

    it('should calculate response size correctly', () => {
      const response = { data: 'test', numbers: [1, 2, 3] };
      const size = apiWrapper.calculateResponseSize(response);
      
      expect(size).toBe(JSON.stringify(response).length);
    });

    it('should handle response size calculation errors', () => {
      const circularObj = {};
      circularObj.self = circularObj;
      
      const size = apiWrapper.calculateResponseSize(circularObj);
      
      expect(size).toBe('unknown');
    });
  });

  describe('Error Pattern Detection', () => {
    it('should record error patterns', async () => {
      const mockError = new Error('Test error');
      mockError.response = { status: 500 };
      
      const mockApiFunction = vi.fn().mockRejectedValue(mockError);
      const wrappedFunction = apiWrapper.wrap(mockApiFunction, {
        operation: 'testOperation'
      });
      
      try {
        await wrappedFunction();
      } catch (error) {
        // Expected to throw
      }
      
      const patterns = apiWrapper.getErrorPatterns();
      expect(patterns['testOperation:500']).toBe(1);
    });

    it('should detect recurring error patterns', async () => {
      const mockError = new Error('Test error');
      mockError.response = { status: 500 };
      
      const mockApiFunction = vi.fn().mockRejectedValue(mockError);
      const wrappedFunction = apiWrapper.wrap(mockApiFunction, {
        operation: 'recurringError'
      });
      
      // Trigger the same error 4 times
      for (let i = 0; i < 4; i++) {
        try {
          await wrappedFunction();
        } catch (error) {
          // Expected to throw
        }
      }
      
      expect(mockErrorManager.handleError).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'error_pattern_detected',
          message: expect.stringContaining('Recurring error pattern detected'),
          severity: 'high',
          context: expect.objectContaining({
            operation: 'recurringError',
            errorPattern: 'recurringError:500',
            occurrences: 4
          })
        })
      );
    });

    it('should handle network errors in pattern detection', async () => {
      const mockError = new Error('Network error');
      // No response property for network errors
      
      const mockApiFunction = vi.fn().mockRejectedValue(mockError);
      const wrappedFunction = apiWrapper.wrap(mockApiFunction, {
        operation: 'networkError'
      });
      
      try {
        await wrappedFunction();
      } catch (error) {
        // Expected to throw
      }
      
      const patterns = apiWrapper.getErrorPatterns();
      expect(patterns['networkError:network']).toBe(1);
    });
  });

  describe('Argument Sanitization', () => {
    it('should sanitize sensitive fields in arguments', () => {
      const args = [
        { username: 'test', password: 'secret123' },
        { apiKey: 'key123', data: 'normal' },
        { token: 'token123', secret: 'secret456' },
        'normal string',
        123
      ];
      
      const sanitized = apiWrapper.sanitizeArgs(args);
      
      expect(sanitized).toEqual([
        { username: 'test', password: '[REDACTED]' },
        { apiKey: '[REDACTED]', data: 'normal' },
        { token: '[REDACTED]', secret: '[REDACTED]' },
        'normal string',
        123
      ]);
    });

    it('should handle null and undefined arguments', () => {
      const args = [null, undefined, { valid: 'data' }];
      const sanitized = apiWrapper.sanitizeArgs(args);
      
      expect(sanitized).toEqual([null, undefined, { valid: 'data' }]);
    });

    it('should not modify original arguments', () => {
      const originalArg = { username: 'test', password: 'secret' };
      const args = [originalArg];
      
      apiWrapper.sanitizeArgs(args);
      
      expect(originalArg.password).toBe('secret'); // Should remain unchanged
    });
  });

  describe('Statistics Management', () => {
    it('should provide comprehensive performance statistics', async () => {
      global.performance.now
        .mockReturnValueOnce(1000).mockReturnValueOnce(1150) // 150ms
        .mockReturnValueOnce(2000).mockReturnValueOnce(2250); // 250ms
      
      const mockApiFunction = vi.fn().mockResolvedValue({ data: 'success' });
      const operation1 = apiWrapper.wrap(mockApiFunction, { operation: 'op1' });
      const operation2 = apiWrapper.wrap(mockApiFunction, { operation: 'op2' });
      
      await operation1();
      await operation2();
      
      const stats = apiWrapper.getPerformanceStats();
      
      expect(stats).toEqual({
        op1: {
          count: 1,
          totalTime: 150,
          minTime: 150,
          maxTime: 150,
          avgTime: 150
        },
        op2: {
          count: 1,
          totalTime: 250,
          minTime: 250,
          maxTime: 250,
          avgTime: 250
        }
      });
    });

    it('should reset statistics correctly', async () => {
      const mockApiFunction = vi.fn().mockResolvedValue({ data: 'success' });
      const wrappedFunction = apiWrapper.wrap(mockApiFunction, {
        operation: 'testOperation'
      });
      
      await wrappedFunction();
      
      expect(apiWrapper.requestCount).toBeGreaterThan(0);
      expect(apiWrapper.performanceMetrics.size).toBeGreaterThan(0);
      
      apiWrapper.resetStats();
      
      expect(apiWrapper.requestCount).toBe(0);
      expect(apiWrapper.performanceMetrics.size).toBe(0);
      expect(apiWrapper.errorPatterns.size).toBe(0);
    });
  });

  describe('Integration with ErrorManager', () => {
    it('should track API request lifecycle in ErrorManager', async () => {
      const mockApiFunction = vi.fn().mockResolvedValue({ data: 'success' });
      const wrappedFunction = apiWrapper.wrap(mockApiFunction, {
        operation: 'trackedOperation'
      });
      
      await wrappedFunction();
      
      // Should track request start
      expect(mockErrorManager.handleError).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'api_request_started',
          category: 'api',
          severity: 'low'
        })
      );
      
      // Should track request completion
      expect(mockErrorManager.handleError).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'api_request_completed',
          category: 'api',
          severity: 'low'
        })
      );
    });

    it('should use custom category when provided', async () => {
      const mockApiFunction = vi.fn().mockResolvedValue({ data: 'success' });
      const wrappedFunction = apiWrapper.wrap(mockApiFunction, {
        operation: 'customOperation',
        category: 'custom_category'
      });
      
      await wrappedFunction();
      
      expect(mockErrorManager.handleError).toHaveBeenCalledWith(
        expect.objectContaining({
          category: 'custom_category'
        })
      );
    });
  });

  describe('Edge Cases and Error Handling', () => {
    it('should handle functions without names', async () => {
      const anonymousFunction = async () => ({ data: 'success' });
      const wrappedFunction = apiWrapper.wrap(anonymousFunction);
      
      const result = await wrappedFunction();
      
      expect(result).toEqual({ data: 'success' });
      expect(console.log).toHaveBeenCalledWith(
        expect.stringContaining('unknown_operation'),
        expect.any(Object)
      );
    });

    it('should handle validation functions that throw', async () => {
      const mockApiFunction = vi.fn();
      const throwingValidator = vi.fn().mockImplementation(() => {
        throw new Error('Validator error');
      });
      
      const wrappedFunction = apiWrapper.wrap(mockApiFunction, {
        validateInput: throwingValidator
      });
      
      await expect(wrappedFunction()).rejects.toThrow('Validator error');
      expect(mockApiFunction).not.toHaveBeenCalled();
    });

    it('should handle transform functions that throw', async () => {
      const mockApiFunction = vi.fn().mockResolvedValue({ data: 'success' });
      const throwingTransform = vi.fn().mockImplementation(() => {
        throw new Error('Transform error');
      });
      
      const wrappedFunction = apiWrapper.wrap(mockApiFunction, {
        transformResponse: throwingTransform
      });
      
      await expect(wrappedFunction()).rejects.toThrow('Transform error');
    });

    it('should handle very large response objects', async () => {
      const largeResponse = {
        data: Array.from({ length: 10000 }, (_, i) => ({ id: i, value: `item_${i}` }))
      };
      
      const mockApiFunction = vi.fn().mockResolvedValue(largeResponse);
      const wrappedFunction = apiWrapper.wrap(mockApiFunction, {
        operation: 'largeResponse'
      });
      
      const result = await wrappedFunction();
      
      expect(result).toEqual(largeResponse);
      expect(console.log).toHaveBeenCalledWith(
        expect.stringContaining('completed successfully'),
        expect.objectContaining({
          responseSize: expect.any(Number)
        })
      );
    });

    it('should handle concurrent wrapped function calls', async () => {
      global.performance.now
        .mockReturnValue(1000) // Start times
        .mockReturnValue(1100) // End times
        .mockReturnValue(2000)
        .mockReturnValue(2150);
      
      const mockApiFunction = vi.fn().mockResolvedValue({ data: 'success' });
      const wrappedFunction = apiWrapper.wrap(mockApiFunction, {
        operation: 'concurrentOperation'
      });
      
      const promises = [
        wrappedFunction('arg1'),
        wrappedFunction('arg2')
      ];
      
      const results = await Promise.all(promises);
      
      expect(results).toHaveLength(2);
      expect(apiWrapper.requestCount).toBe(2);
      expect(mockApiFunction).toHaveBeenCalledTimes(2);
    });
  });

  describe('Real-World Usage Scenarios', () => {
    it('should handle complete API workflow with retries', async () => {
      const mockApiFunction = vi.fn()
        .mockRejectedValueOnce(new Error('Temporary failure'))
        .mockResolvedValueOnce({ data: 'success' });
      
      const wrappedFunction = apiWrapper.wrap(mockApiFunction, {
        operation: 'retryableOperation',
        retryable: true
      });
      
      // First call fails
      try {
        await wrappedFunction();
      } catch (error) {
        expect(error.context.retryable).toBe(true);
      }
      
      // Second call succeeds
      const result = await wrappedFunction();
      expect(result).toEqual({ data: 'success' });
    });

    it('should track performance across multiple operations', async () => {
      const operations = ['getUserData', 'getPortfolio', 'getMarketData'];
      const durations = [100, 200, 300];
      
      for (let i = 0; i < operations.length; i++) {
        global.performance.now
          .mockReturnValueOnce(1000)
          .mockReturnValueOnce(1000 + durations[i]);
        
        const mockApiFunction = vi.fn().mockResolvedValue({ data: `${operations[i]} result` });
        const wrappedFunction = apiWrapper.wrap(mockApiFunction, {
          operation: operations[i]
        });
        
        await wrappedFunction();
      }
      
      const stats = apiWrapper.getPerformanceStats();
      
      expect(Object.keys(stats)).toHaveLength(3);
      expect(stats.getUserData.avgTime).toBe(100);
      expect(stats.getPortfolio.avgTime).toBe(200);
      expect(stats.getMarketData.avgTime).toBe(300);
    });
  });
});
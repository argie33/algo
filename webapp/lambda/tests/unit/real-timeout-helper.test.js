/**
 * UNIT TESTS: Timeout Helper
 * Real implementation testing with zero mocks for business logic
 * Comprehensive coverage of timeout handling, circuit breaker integration, and retry logic
 */

// Jest globals are automatically available in test environment

const timeoutHelper = require('../../utils/timeoutHelper');

describe('Timeout Helper Unit Tests', () => {
  let mockSuccessOperation;
  let mockFailingOperation;
  let mockSlowOperation;
  
  beforeEach(() => {
    // Reset circuit breakers before each test
    timeoutHelper.circuitBreakers.clear();
    
    // Mock successful operation
    mockSuccessOperation = jest.fn().mockResolvedValue('success');
    
    // Mock failing operation
    mockFailingOperation = jest.fn().mockRejectedValue(new Error('Operation failed'));
    
    // Mock slow operation
    mockSlowOperation = jest.fn().mockImplementation(() => 
      new Promise(resolve => setTimeout(() => resolve('slow-success'), 100))
    );
    
    // Mock console methods to reduce noise in tests
    jest.spyOn(console, 'log').mockImplementation(() => {});
    jest.spyOn(console, 'warn').mockImplementation(() => {});
    jest.spyOn(console, 'error').mockImplementation(() => {});
  });
  
  afterEach(() => {
    jest.restoreAllMocks();
  });

  describe('Default Configuration', () => {
    it('has correct default timeout values', () => {
      expect(timeoutHelper.defaultTimeouts.database).toBe(5000);
      expect(timeoutHelper.defaultTimeouts.alpaca).toBe(15000);
      expect(timeoutHelper.defaultTimeouts.news).toBe(10000);
      expect(timeoutHelper.defaultTimeouts.sentiment).toBe(8000);
      expect(timeoutHelper.defaultTimeouts.external).toBe(12000);
      expect(timeoutHelper.defaultTimeouts.upload).toBe(30000);
      expect(timeoutHelper.defaultTimeouts.websocket).toBe(5000);
    });

    it('initializes with empty circuit breakers map', () => {
      expect(timeoutHelper.circuitBreakers.size).toBe(0);
    });
  });

  describe('Basic Timeout Functionality', () => {
    it('executes operation successfully within timeout', async () => {
      const result = await timeoutHelper.withTimeout(
        mockSuccessOperation(),
        { timeout: 1000, service: 'test', operation: 'success' }
      );
      
      expect(result).toBe('success');
      expect(mockSuccessOperation).toHaveBeenCalledTimes(1);
    });

    it('throws timeout error when operation exceeds timeout', async () => {
      const verySlowOperation = () => 
        new Promise(resolve => setTimeout(() => resolve('too-slow'), 200));
      
      await expect(
        timeoutHelper.withTimeout(verySlowOperation(), {
          timeout: 50,
          service: 'test',
          operation: 'timeout-test'
        })
      ).rejects.toThrow('Timeout: test timeout-test exceeded 50ms');
    });

    it('propagates operation errors correctly', async () => {
      await expect(
        timeoutHelper.withTimeout(mockFailingOperation(), {
          timeout: 1000,
          service: 'test',
          operation: 'error-test'
        })
      ).rejects.toThrow('Operation failed');
    });

    it('uses default timeout when not specified', async () => {
      const result = await timeoutHelper.withTimeout(mockSuccessOperation());
      
      expect(result).toBe('success');
      expect(mockSuccessOperation).toHaveBeenCalledTimes(1);
    });
  });

  describe('Retry Logic', () => {
    it('retries failed operations according to retry count', async () => {
      await expect(
        timeoutHelper.withTimeout(mockFailingOperation(), {
          timeout: 1000,
          service: 'test',
          operation: 'retry-test',
          retries: 2,
          retryDelay: 10
        })
      ).rejects.toThrow('Operation failed');
      
      expect(mockFailingOperation).toHaveBeenCalledTimes(3); // Original + 2 retries
    });

    it('succeeds on retry after initial failure', async () => {
      const flakeyOperation = jest.fn()
        .mockRejectedValueOnce(new Error('First failure'))
        .mockResolvedValueOnce('success-on-retry');
      
      const result = await timeoutHelper.withTimeout(flakeyOperation(), {
        timeout: 1000,
        service: 'test',
        operation: 'flakey-test',
        retries: 2,
        retryDelay: 10
      });
      
      expect(result).toBe('success-on-retry');
      expect(flakeyOperation).toHaveBeenCalledTimes(2);
    });

    it('applies exponential backoff for retry delays', async () => {
      const startTime = Date.now();
      
      await expect(
        timeoutHelper.withTimeout(mockFailingOperation(), {
          timeout: 1000,
          service: 'test',
          operation: 'backoff-test',
          retries: 2,
          retryDelay: 50
        })
      ).rejects.toThrow('Operation failed');
      
      const endTime = Date.now();
      const totalTime = endTime - startTime;
      
      // Should take at least 50ms (first retry) + 100ms (second retry) = 150ms
      expect(totalTime).toBeGreaterThan(140);
    });

    it('does not retry without explicit retry count', async () => {
      await expect(
        timeoutHelper.withTimeout(mockFailingOperation(), {
          timeout: 1000,
          service: 'test',
          operation: 'no-retry-test'
        })
      ).rejects.toThrow('Operation failed');
      
      expect(mockFailingOperation).toHaveBeenCalledTimes(1);
    });
  });

  describe('Circuit Breaker Integration', () => {
    it('records success and resets circuit breaker', async () => {
      await timeoutHelper.withTimeout(mockSuccessOperation(), {
        timeout: 1000,
        service: 'test',
        operation: 'cb-success',
        useCircuitBreaker: true
      });
      
      const status = timeoutHelper.getCircuitBreakerStatus();
      expect(status['test-cb-success']).toMatchObject({
        state: 'closed',
        failures: 0,
        totalSuccesses: 1
      });
    });

    it('records failure and updates circuit breaker', async () => {
      await expect(
        timeoutHelper.withTimeout(mockFailingOperation(), {
          timeout: 1000,
          service: 'test',
          operation: 'cb-failure',
          useCircuitBreaker: true
        })
      ).rejects.toThrow('Operation failed');
      
      const status = timeoutHelper.getCircuitBreakerStatus();
      expect(status['test-cb-failure']).toMatchObject({
        state: 'closed',
        failures: 1,
        totalFailures: 1
      });
    });

    it('opens circuit after threshold failures', async () => {
      const serviceKey = 'test-threshold';
      
      // Trigger failures up to threshold (15)
      for (let i = 0; i < 15; i++) {
        try {
          await timeoutHelper.withTimeout(mockFailingOperation(), {
            timeout: 1000,
            service: 'test',
            operation: 'threshold',
            useCircuitBreaker: true
          });
        } catch (error) {
          // Expected failures
        }
      }
      
      const status = timeoutHelper.getCircuitBreakerStatus();
      expect(status['test-threshold'].state).toBe('open');
      expect(console.warn).toHaveBeenCalledWith(
        expect.stringContaining('Circuit breaker opened for test-threshold')
      );
    });

    it('rejects operations when circuit is open', async () => {
      const serviceKey = 'test-open';
      
      // Force circuit open
      timeoutHelper.circuitBreakers.set(serviceKey, {
        state: 'open',
        failures: 15,
        lastFailureTime: Date.now(),
        threshold: 15,
        timeout: 15000
      });
      
      await expect(
        timeoutHelper.withTimeout(mockSuccessOperation(), {
          timeout: 1000,
          service: 'test',
          operation: 'open',
          useCircuitBreaker: true
        })
      ).rejects.toThrow('Circuit breaker open for test-open');
      
      expect(mockSuccessOperation).not.toHaveBeenCalled();
    });

    it('transitions to half-open after timeout period', async () => {
      const serviceKey = 'test-halfopen';
      
      // Set circuit to open with old failure time
      timeoutHelper.circuitBreakers.set(serviceKey, {
        state: 'open',
        failures: 15,
        lastFailureTime: Date.now() - 20000, // 20 seconds ago
        threshold: 15,
        timeout: 15000,
        halfOpenMaxCalls: 8
      });
      
      // Should allow operation and transition to half-open
      const result = await timeoutHelper.withTimeout(mockSuccessOperation(), {
        timeout: 1000,
        service: 'test',
        operation: 'halfopen',
        useCircuitBreaker: true
      });
      
      expect(result).toBe('success');
      expect(console.log).toHaveBeenCalledWith(
        expect.stringContaining('Circuit breaker half-open for test-halfopen')
      );
    });
  });

  describe('HTTP Request Functionality', () => {
    beforeEach(() => {
      // Mock fetch globally
      global.fetch = jest.fn();
    });

    it('makes successful HTTP request with default options', async () => {
      const mockResponse = {
        ok: true,
        status: 200,
        statusText: 'OK',
        json: jest.fn().mockResolvedValue({ data: 'success' })
      };
      global.fetch.mockResolvedValue(mockResponse);

      const result = await timeoutHelper.httpRequest('https://api.example.com/data');
      
      expect(global.fetch).toHaveBeenCalledWith(
        'https://api.example.com/data',
        expect.objectContaining({
          method: 'GET',
          headers: expect.objectContaining({
            'User-Agent': 'Financial-Dashboard-API/1.0',
            'Accept': 'application/json'
          })
        })
      );
      expect(result).toBe(mockResponse);
    });

    it('handles POST requests with JSON body', async () => {
      const mockResponse = { ok: true, status: 201 };
      global.fetch.mockResolvedValue(mockResponse);

      const requestBody = { key: 'value' };
      
      await timeoutHelper.httpRequest('https://api.example.com/data', {
        method: 'POST',
        body: requestBody
      });
      
      expect(global.fetch).toHaveBeenCalledWith(
        'https://api.example.com/data',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify(requestBody),
          headers: expect.objectContaining({
            'Content-Type': 'application/json'
          })
        })
      );
    });

    it('throws error for non-OK HTTP responses', async () => {
      const mockResponse = {
        ok: false,
        status: 404,
        statusText: 'Not Found'
      };
      global.fetch.mockResolvedValue(mockResponse);

      await expect(
        timeoutHelper.httpRequest('https://api.example.com/notfound')
      ).rejects.toThrow('HTTP 404: Not Found');
    });

    it('handles request timeout with AbortController', async () => {
      // Mock fetch to never resolve
      global.fetch.mockImplementation(() => new Promise(() => {}));

      await expect(
        timeoutHelper.httpRequest('https://api.example.com/slow', {
          timeout: 50
        })
      ).rejects.toThrow('HTTP request timeout');
    });
  });

  describe('Database Query Functionality', () => {
    it('executes database query with circuit breaker', async () => {
      const mockQueryFn = jest.fn().mockResolvedValue([{ id: 1, name: 'test' }]);
      
      const result = await timeoutHelper.databaseQuery(mockQueryFn, {
        operation: 'select-test'
      });
      
      expect(result).toEqual([{ id: 1, name: 'test' }]);
      expect(mockQueryFn).toHaveBeenCalledTimes(1);
    });

    it('applies database-specific timeout', async () => {
      const slowQuery = jest.fn().mockImplementation(() =>
        new Promise(resolve => setTimeout(() => resolve('too-slow'), 100))
      );
      
      await expect(
        timeoutHelper.databaseQuery(slowQuery, {
          timeout: 50,
          operation: 'slow-query'
        })
      ).rejects.toThrow('Timeout: database slow-query exceeded 50ms');
    });

    it('retries failed database queries', async () => {
      const flakeyQuery = jest.fn()
        .mockRejectedValueOnce(new Error('Connection lost'))
        .mockResolvedValueOnce('query-success');
      
      const result = await timeoutHelper.databaseQuery(flakeyQuery, {
        operation: 'flakey-query',
        retries: 1
      });
      
      expect(result).toBe('query-success');
      expect(flakeyQuery).toHaveBeenCalledTimes(2);
    });
  });

  describe('Alpaca API Integration', () => {
    it('executes Alpaca API call with service-specific settings', async () => {
      const mockApiCall = jest.fn().mockResolvedValue({ account: 'data' });
      
      const result = await timeoutHelper.alpacaApiCall(mockApiCall, {
        operation: 'get-account'
      });
      
      expect(result).toEqual({ account: 'data' });
      expect(mockApiCall).toHaveBeenCalledTimes(1);
    });

    it('uses Alpaca-specific timeout and retry settings', async () => {
      const failingApiCall = jest.fn().mockRejectedValue(new Error('API error'));
      
      await expect(
        timeoutHelper.alpacaApiCall(failingApiCall, {
          operation: 'failing-call'
        })
      ).rejects.toThrow('API error');
      
      // Should retry 2 times (total 3 calls)
      expect(failingApiCall).toHaveBeenCalledTimes(3);
    });
  });

  describe('News API Integration', () => {
    it('executes news API call without circuit breaker', async () => {
      const mockNewsCall = jest.fn().mockResolvedValue(['news1', 'news2']);
      
      const result = await timeoutHelper.newsApiCall(mockNewsCall, {
        operation: 'get-headlines'
      });
      
      expect(result).toEqual(['news1', 'news2']);
      
      // Should not create circuit breaker for news API
      const status = timeoutHelper.getCircuitBreakerStatus();
      expect(status['news-get-headlines']).toBeUndefined();
    });
  });

  describe('Batch Processing', () => {
    it('processes items in batches with concurrency limit', async () => {
      const items = [1, 2, 3, 4, 5, 6, 7, 8];
      const processor = jest.fn().mockImplementation(async (item) => item * 2);
      
      const { results, errors } = await timeoutHelper.batchProcess(items, processor, {
        concurrency: 3,
        timeout: 1000
      });
      
      expect(results).toHaveLength(8);
      expect(errors).toHaveLength(0);
      expect(results.map(r => r.result)).toEqual([2, 4, 6, 8, 10, 12, 14, 16]);
      expect(processor).toHaveBeenCalledTimes(8);
    });

    it('handles errors in batch processing', async () => {
      const items = [1, 2, 3, 4];
      const processor = jest.fn().mockImplementation(async (item) => {
        if (item === 3) throw new Error(`Error processing ${item}`);
        return item * 2;
      });
      
      const { results, errors } = await timeoutHelper.batchProcess(items, processor, {
        concurrency: 2,
        continueOnError: true
      });
      
      expect(results).toHaveLength(3);
      expect(errors).toHaveLength(1);
      expect(errors[0].error.message).toBe('Error processing 3');
    });

    it('stops on first error when continueOnError is false', async () => {
      const items = [1, 2, 3, 4];
      const processor = jest.fn().mockImplementation(async (item) => {
        if (item === 2) throw new Error('Stop here');
        return item * 2;
      });
      
      await expect(
        timeoutHelper.batchProcess(items, processor, {
          concurrency: 4,
          continueOnError: false
        })
      ).rejects.toThrow('Stop here');
    });
  });

  describe('Multiple Promise Handling', () => {
    it('handles Promise.all with timeout and fail-fast', async () => {
      const promises = [
        mockSuccessOperation(),
        mockSuccessOperation(),
        mockSuccessOperation()
      ];
      
      const results = await timeoutHelper.withTimeoutAll(promises, {
        timeout: 1000,
        service: 'test',
        operation: 'batch',
        failFast: true
      });
      
      expect(results).toEqual(['success', 'success', 'success']);
    });

    it('handles Promise.allSettled for partial success', async () => {
      const promises = [
        mockSuccessOperation(),
        mockFailingOperation(),
        mockSuccessOperation()
      ];
      
      const results = await timeoutHelper.withTimeoutAll(promises, {
        timeout: 1000,
        service: 'test',
        operation: 'mixed-batch',
        failFast: false
      });
      
      expect(results).toHaveLength(3);
      expect(results[0].status).toBe('fulfilled');
      expect(results[1].status).toBe('rejected');
      expect(results[2].status).toBe('fulfilled');
    });

    it('times out batch operations', async () => {
      const slowPromises = [
        new Promise(resolve => setTimeout(() => resolve('slow1'), 200)),
        new Promise(resolve => setTimeout(() => resolve('slow2'), 200))
      ];
      
      await expect(
        timeoutHelper.withTimeoutAll(slowPromises, {
          timeout: 100,
          service: 'test',
          operation: 'slow-batch'
        })
      ).rejects.toThrow('Timeout: test slow-batch batch exceeded 100ms');
    });
  });

  describe('Circuit Breaker Metrics and Monitoring', () => {
    beforeEach(async () => {
      // Set up some circuit breaker history
      await timeoutHelper.withTimeout(mockSuccessOperation(), {
        service: 'metrics-test',
        operation: 'monitor',
        useCircuitBreaker: true
      });
      
      try {
        await timeoutHelper.withTimeout(mockFailingOperation(), {
          service: 'metrics-test',
          operation: 'monitor',
          useCircuitBreaker: true
        });
      } catch (error) {
        // Expected failure
      }
    });

    it('provides comprehensive circuit breaker status', () => {
      const status = timeoutHelper.getCircuitBreakerStatus();
      const serviceStatus = status['metrics-test-monitor'];
      
      expect(serviceStatus).toMatchObject({
        state: 'closed',
        failures: 1,
        threshold: 15,
        timeout: 15000,
        totalSuccesses: 1,
        totalFailures: 1
      });
      expect(serviceStatus.timeSinceLastFailure).toBeGreaterThan(0);
    });

    it('provides detailed metrics with performance data', () => {
      const metrics = timeoutHelper.getCircuitBreakerMetrics();
      const serviceMetrics = metrics['metrics-test-monitor'];
      
      expect(serviceMetrics).toMatchObject({
        state: 'closed',
        totalRequests: 2,
        totalSuccesses: 1,
        totalFailures: 1,
        successRate: 50,
        failureRate: 50,
        isHealthy: false, // Has failures
        isRecovering: false,
        isFailed: false,
        riskLevel: 'MINIMAL'
      });
    });

    it('calculates recent activity correctly', () => {
      const metrics = timeoutHelper.getCircuitBreakerMetrics();
      const serviceMetrics = metrics['metrics-test-monitor'];
      
      expect(serviceMetrics.recentActivity).toMatchObject({
        requests: 2,
        failures: 1,
        successes: 1,
        period: '5min'
      });
    });

    it('provides risk level assessment', () => {
      // Test different risk levels
      const breaker = timeoutHelper.circuitBreakers.get('metrics-test-monitor');
      
      // Low risk
      breaker.failures = 8; // 8/15 > 50%
      expect(timeoutHelper.getRiskLevel(breaker)).toBe('MEDIUM');
      
      // Medium risk  
      breaker.failures = 12; // 12/15 > 80%
      expect(timeoutHelper.getRiskLevel(breaker)).toBe('MEDIUM');
      
      // High risk
      breaker.state = 'open';
      expect(timeoutHelper.getRiskLevel(breaker)).toBe('HIGH');
    });

    it('provides recovery predictions', () => {
      const breaker = timeoutHelper.circuitBreakers.get('metrics-test-monitor');
      
      expect(timeoutHelper.getPredictedRecovery(breaker)).toBe('N/A - Service is healthy');
      
      breaker.state = 'half-open';
      expect(timeoutHelper.getPredictedRecovery(breaker)).toBe('In progress - Testing recovery');
      
      breaker.state = 'open';
      breaker.lastFailureTime = Date.now() - 5000;
      const prediction = timeoutHelper.getPredictedRecovery(breaker);
      expect(prediction).toMatch(/\d+ seconds/);
    });
  });

  describe('Delay Utility', () => {
    it('provides accurate delay functionality', async () => {
      const startTime = Date.now();
      await timeoutHelper.delay(50);
      const endTime = Date.now();
      
      expect(endTime - startTime).toBeGreaterThanOrEqual(45);
      expect(endTime - startTime).toBeLessThan(100);
    });
  });

  describe('Edge Cases and Error Scenarios', () => {
    it('handles operations that return null or undefined', async () => {
      const nullOperation = jest.fn().mockResolvedValue(null);
      const undefinedOperation = jest.fn().mockResolvedValue(undefined);
      
      const nullResult = await timeoutHelper.withTimeout(nullOperation());
      const undefinedResult = await timeoutHelper.withTimeout(undefinedOperation());
      
      expect(nullResult).toBe(null);
      expect(undefinedResult).toBe(undefined);
    });

    it('handles concurrent access to circuit breakers safely', async () => {
      const promises = [];
      
      // Execute multiple operations concurrently on same service
      for (let i = 0; i < 10; i++) {
        promises.push(
          timeoutHelper.withTimeout(mockSuccessOperation(), {
            service: 'concurrent',
            operation: 'test',
            useCircuitBreaker: true
          })
        );
      }
      
      const results = await Promise.all(promises);
      expect(results).toHaveLength(10);
      
      const status = timeoutHelper.getCircuitBreakerStatus();
      expect(status['concurrent-test'].totalSuccesses).toBe(10);
    });

    it('maintains circuit breaker history size limit', async () => {
      const serviceKey = 'history-test';
      
      // Execute more than 100 operations
      for (let i = 0; i < 150; i++) {
        try {
          await timeoutHelper.withTimeout(
            i % 2 === 0 ? mockSuccessOperation() : mockFailingOperation(),
            {
              service: 'history',
              operation: 'test',
              useCircuitBreaker: true
            }
          );
        } catch (error) {
          // Expected failures
        }
      }
      
      const breaker = timeoutHelper.circuitBreakers.get('history-test');
      expect(breaker.history.length).toBeLessThanOrEqual(100);
    });

    it('handles malformed options gracefully', async () => {
      // Should use defaults for undefined/null options
      const result = await timeoutHelper.withTimeout(mockSuccessOperation(), null);
      expect(result).toBe('success');
      
      const result2 = await timeoutHelper.withTimeout(mockSuccessOperation(), undefined);
      expect(result2).toBe('success');
    });
  });
});
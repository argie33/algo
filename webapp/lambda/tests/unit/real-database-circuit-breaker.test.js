/**
 * UNIT TESTS: Database Circuit Breaker
 * Real implementation testing with zero mocks for business logic
 * Comprehensive coverage of circuit breaker state management and failure recovery
 */

// Jest globals are automatically available in test environment

const DatabaseCircuitBreaker = require('../../utils/databaseCircuitBreaker');

describe('Database Circuit Breaker Unit Tests', () => {
  let circuitBreaker;
  let mockOperation;
  let mockFailingOperation;
  
  beforeEach(() => {
    circuitBreaker = new DatabaseCircuitBreaker();
    
    // Mock successful operation
    mockOperation = jest.fn().mockResolvedValue('success');
    
    // Mock failing operation
    mockFailingOperation = jest.fn().mockRejectedValue(new Error('Database connection failed'));
    
    // Mock console methods to reduce noise in tests
    jest.spyOn(console, 'log').mockImplementation(() => {});
    jest.spyOn(console, 'warn').mockImplementation(() => {});
    jest.spyOn(console, 'error').mockImplementation(() => {});
  });
  
  afterEach(() => {
    jest.restoreAllMocks();
  });

  describe('Circuit Breaker Initialization', () => {
    it('initializes with correct default state', () => {
      const status = circuitBreaker.getStatus();
      
      expect(status.state).toBe('closed');
      expect(status.failures).toBe(0);
      expect(status.totalRequests).toBe(0);
      expect(status.totalSuccesses).toBe(0);
      expect(status.totalFailures).toBe(0);
      expect(status.successRate).toBe('0%');
      expect(status.isHealthy).toBe(true);
    });

    it('sets production-ready configuration values', () => {
      expect(circuitBreaker.failureThreshold).toBe(20);
      expect(circuitBreaker.recoveryTimeout).toBe(10000);
      expect(circuitBreaker.halfOpenMaxCalls).toBe(10);
      expect(circuitBreaker.halfOpenSuccessThreshold).toBe(3);
    });
  });

  describe('Closed State Operations', () => {
    it('executes operations successfully when circuit is closed', async () => {
      const result = await circuitBreaker.execute(mockOperation, 'test-operation');
      
      expect(result).toBe('success');
      expect(mockOperation).toHaveBeenCalledTimes(1);
      
      const status = circuitBreaker.getStatus();
      expect(status.state).toBe('closed');
      expect(status.totalRequests).toBe(1);
      expect(status.totalSuccesses).toBe(1);
      expect(status.successRate).toBe('100.00%');
    });

    it('records failure but stays closed below threshold', async () => {
      await expect(
        circuitBreaker.execute(mockFailingOperation, 'failing-operation')
      ).rejects.toThrow('Database connection failed');
      
      const status = circuitBreaker.getStatus();
      expect(status.state).toBe('closed');
      expect(status.failures).toBe(1);
      expect(status.totalFailures).toBe(1);
      expect(status.isHealthy).toBe(true); // Still healthy below 50% of threshold
    });

    it('decrements failure count on successful operations', async () => {
      // Record some failures first
      for (let i = 0; i < 5; i++) {
        try {
          await circuitBreaker.execute(mockFailingOperation, 'failing-op');
        } catch (error) {
          // Expected failures
        }
      }
      
      expect(circuitBreaker.failures).toBe(5);
      
      // Execute successful operation
      await circuitBreaker.execute(mockOperation, 'success-op');
      
      expect(circuitBreaker.failures).toBe(4); // Decremented by 1
    });

    it('opens circuit when failure threshold is reached', async () => {
      // Trigger exactly failureThreshold failures
      for (let i = 0; i < circuitBreaker.failureThreshold; i++) {
        try {
          await circuitBreaker.execute(mockFailingOperation, 'threshold-test');
        } catch (error) {
          // Expected failures
        }
      }
      
      const status = circuitBreaker.getStatus();
      expect(status.state).toBe('open');
      expect(status.failures).toBe(circuitBreaker.failureThreshold);
      expect(console.error).toHaveBeenCalledWith(
        expect.stringContaining('Circuit breaker OPENED due to')
      );
    });
  });

  describe('Open State Operations', () => {
    beforeEach(async () => {
      // Force circuit to open state
      for (let i = 0; i < circuitBreaker.failureThreshold; i++) {
        try {
          await circuitBreaker.execute(mockFailingOperation, 'setup-failure');
        } catch (error) {
          // Expected failures to open circuit
        }
      }
    });

    it('rejects operations immediately when circuit is open', async () => {
      await expect(
        circuitBreaker.execute(mockOperation, 'blocked-operation')
      ).rejects.toThrow('Circuit breaker is OPEN');
      
      expect(mockOperation).not.toHaveBeenCalled();
      
      const status = circuitBreaker.getStatus();
      expect(status.state).toBe('open');
      expect(status.timeToRecovery).toBeGreaterThan(0);
    });

    it('includes remaining time in error message', async () => {
      try {
        await circuitBreaker.execute(mockOperation, 'time-check');
      } catch (error) {
        expect(error.message).toContain('unavailable for');
        expect(error.message).toContain('more seconds');
        expect(error.message).toContain('Too many connection failures');
      }
    });

    it('transitions to half-open after recovery timeout', async () => {
      // Fast-forward time using real timeout
      jest.useFakeTimers();
      
      // Advance time past recovery timeout
      jest.advanceTimersByTime(circuitBreaker.recoveryTimeout + 1000);
      
      // Restore real timers for Date.now() calls
      jest.useRealTimers();
      
      // Update lastFailureTime to simulate timeout passage
      circuitBreaker.lastFailureTime = Date.now() - circuitBreaker.recoveryTimeout - 1000;
      
      // Next operation should transition to half-open
      await circuitBreaker.execute(mockOperation, 'recovery-test');
      
      const status = circuitBreaker.getStatus();
      expect(status.state).toBe('half-open');
      expect(console.log).toHaveBeenCalledWith(
        expect.stringContaining('transitioning to HALF-OPEN')
      );
    });
  });

  describe('Half-Open State Operations', () => {
    beforeEach(async () => {
      // Set circuit to half-open state
      circuitBreaker.state = 'half-open';
      circuitBreaker.successCount = 0;
    });

    it('allows limited operations in half-open state', async () => {
      const result = await circuitBreaker.execute(mockOperation, 'half-open-test');
      
      expect(result).toBe('success');
      expect(circuitBreaker.successCount).toBe(1);
      expect(console.log).toHaveBeenCalledWith(
        expect.stringContaining('half-open success 1/3')
      );
    });

    it('closes circuit after sufficient successes', async () => {
      // Execute successful operations up to threshold
      for (let i = 0; i < circuitBreaker.halfOpenSuccessThreshold; i++) {
        await circuitBreaker.execute(mockOperation, 'closing-test');
      }
      
      const status = circuitBreaker.getStatus();
      expect(status.state).toBe('closed');
      expect(status.failures).toBe(0);
      expect(console.log).toHaveBeenCalledWith(
        expect.stringContaining('Circuit breaker CLOSED - database access restored')
      );
    });

    it('reopens circuit on failure in half-open state', async () => {
      await expect(
        circuitBreaker.execute(mockFailingOperation, 'half-open-failure')
      ).rejects.toThrow('Database connection failed');
      
      const status = circuitBreaker.getStatus();
      expect(status.state).toBe('open');
      expect(status.failures).toBeGreaterThan(0);
    });

    it('tracks success count correctly in half-open state', async () => {
      // Execute partial successes
      await circuitBreaker.execute(mockOperation, 'partial-1');
      expect(circuitBreaker.successCount).toBe(1);
      
      await circuitBreaker.execute(mockOperation, 'partial-2');
      expect(circuitBreaker.successCount).toBe(2);
      
      // Should still be half-open
      expect(circuitBreaker.state).toBe('half-open');
    });
  });

  describe('Metrics and History Tracking', () => {
    it('tracks comprehensive metrics', async () => {
      // Execute mixed operations
      await circuitBreaker.execute(mockOperation, 'success-1');
      await circuitBreaker.execute(mockOperation, 'success-2');
      
      try {
        await circuitBreaker.execute(mockFailingOperation, 'failure-1');
      } catch (error) {
        // Expected failure
      }
      
      const status = circuitBreaker.getStatus();
      expect(status.totalRequests).toBe(3);
      expect(status.totalSuccesses).toBe(2);
      expect(status.totalFailures).toBe(1);
      expect(status.successRate).toBe('66.67%');
    });

    it('maintains request history with limited size', async () => {
      // Execute more than 100 operations to test history trimming
      for (let i = 0; i < 150; i++) {
        await circuitBreaker.execute(mockOperation, `operation-${i}`);
      }
      
      const status = circuitBreaker.getStatus();
      expect(status.recentHistory).toHaveLength(10); // Last 10 in status
      expect(circuitBreaker.requestHistory).toHaveLength(100); // Max 100 total
    });

    it('records operation duration in history', async () => {
      const slowOperation = jest.fn().mockImplementation(async () => {
        await new Promise(resolve => setTimeout(resolve, 50));
        return 'slow-success';
      });
      
      await circuitBreaker.execute(slowOperation, 'duration-test');
      
      const history = circuitBreaker.requestHistory;
      const lastRecord = history[history.length - 1];
      
      expect(lastRecord.type).toBe('success');
      expect(lastRecord.operation).toBe('duration-test');
      expect(lastRecord.duration).toBeGreaterThan(0);
      expect(lastRecord.error).toBe(null);
    });

    it('records error details in failure history', async () => {
      try {
        await circuitBreaker.execute(mockFailingOperation, 'error-tracking');
      } catch (error) {
        // Expected failure
      }
      
      const history = circuitBreaker.requestHistory;
      const lastRecord = history[history.length - 1];
      
      expect(lastRecord.type).toBe('failure');
      expect(lastRecord.operation).toBe('error-tracking');
      expect(lastRecord.duration).toBe(0);
      expect(lastRecord.error).toBe('Database connection failed');
    });
  });

  describe('Health Assessment', () => {
    it('reports healthy when failures are below 50% of threshold', () => {
      // Add failures below 50% threshold
      circuitBreaker.failures = 9; // 50% of 20 threshold = 10
      
      const status = circuitBreaker.getStatus();
      expect(status.isHealthy).toBe(true);
    });

    it('reports unhealthy when failures are above 50% of threshold', () => {
      circuitBreaker.failures = 11; // Above 50% of 20 threshold
      
      const status = circuitBreaker.getStatus();
      expect(status.isHealthy).toBe(false);
    });

    it('reports unhealthy when circuit is not closed', () => {
      circuitBreaker.state = 'open';
      circuitBreaker.failures = 5; // Below threshold but circuit open
      
      const status = circuitBreaker.getStatus();
      expect(status.isHealthy).toBe(false);
    });

    it('calculates time to recovery correctly', () => {
      circuitBreaker.state = 'open';
      circuitBreaker.lastFailureTime = Date.now() - 5000; // 5 seconds ago
      
      const status = circuitBreaker.getStatus();
      expect(status.timeToRecovery).toBeCloseTo(5000, -2); // Within 100ms
    });
  });

  describe('Force Reset Functionality', () => {
    it('resets circuit breaker to clean state', async () => {
      // Force circuit to open with failures
      for (let i = 0; i < circuitBreaker.failureThreshold; i++) {
        try {
          await circuitBreaker.execute(mockFailingOperation, 'reset-test');
        } catch (error) {
          // Expected failures
        }
      }
      
      expect(circuitBreaker.state).toBe('open');
      expect(circuitBreaker.failures).toBe(circuitBreaker.failureThreshold);
      
      // Force reset
      circuitBreaker.forceReset();
      
      const status = circuitBreaker.getStatus();
      expect(status.state).toBe('closed');
      expect(status.failures).toBe(0);
      expect(status.successCount).toBe(0);
      expect(status.lastFailureTime).toBe(0);
      
      expect(console.log).toHaveBeenCalledWith(
        expect.stringContaining('EMERGENCY: Force resetting circuit breaker')
      );
    });

    it('allows operations after force reset', async () => {
      // Open circuit
      circuitBreaker.state = 'open';
      circuitBreaker.lastFailureTime = Date.now();
      
      // Force reset
      circuitBreaker.forceReset();
      
      // Should allow operations
      const result = await circuitBreaker.execute(mockOperation, 'post-reset');
      expect(result).toBe('success');
    });
  });

  describe('Concurrent Operations', () => {
    it('handles concurrent operations safely', async () => {
      const promises = [];
      
      // Execute multiple concurrent operations
      for (let i = 0; i < 10; i++) {
        promises.push(
          circuitBreaker.execute(mockOperation, `concurrent-${i}`)
        );
      }
      
      const results = await Promise.all(promises);
      
      expect(results).toHaveLength(10);
      expect(results.every(result => result === 'success')).toBe(true);
      
      const status = circuitBreaker.getStatus();
      expect(status.totalRequests).toBe(10);
      expect(status.totalSuccesses).toBe(10);
    });

    it('handles mixed concurrent success and failure operations', async () => {
      const promises = [];
      
      // Mix of successful and failing operations
      for (let i = 0; i < 5; i++) {
        promises.push(
          circuitBreaker.execute(mockOperation, `success-${i}`)
        );
        promises.push(
          circuitBreaker.execute(mockFailingOperation, `failure-${i}`)
            .catch(error => error) // Catch to prevent Promise.all rejection
        );
      }
      
      const results = await Promise.all(promises);
      
      const status = circuitBreaker.getStatus();
      expect(status.totalRequests).toBe(10);
      expect(status.totalSuccesses).toBe(5);
      expect(status.totalFailures).toBe(5);
      expect(status.successRate).toBe('50.00%');
    });
  });

  describe('Edge Cases and Error Scenarios', () => {
    it('handles operations that throw non-Error objects', async () => {
      const weirdFailingOperation = jest.fn().mockRejectedValue('string error');
      
      await expect(
        circuitBreaker.execute(weirdFailingOperation, 'weird-error')
      ).rejects.toBe('string error');
      
      const status = circuitBreaker.getStatus();
      expect(status.totalFailures).toBe(1);
    });

    it('handles operations that return undefined', async () => {
      const undefinedOperation = jest.fn().mockResolvedValue(undefined);
      
      const result = await circuitBreaker.execute(undefinedOperation, 'undefined-op');
      
      expect(result).toBeUndefined();
      
      const status = circuitBreaker.getStatus();
      expect(status.totalSuccesses).toBe(1);
    });

    it('maintains state consistency during rapid state transitions', async () => {
      // Rapidly approach failure threshold
      for (let i = 0; i < circuitBreaker.failureThreshold - 1; i++) {
        try {
          await circuitBreaker.execute(mockFailingOperation, 'rapid-fail');
        } catch (error) {
          // Expected
        }
      }
      
      expect(circuitBreaker.state).toBe('closed');
      
      // One more failure should open circuit
      try {
        await circuitBreaker.execute(mockFailingOperation, 'final-fail');
      } catch (error) {
        // Expected
      }
      
      expect(circuitBreaker.state).toBe('open');
    });

    it('handles timestamp edge cases', () => {
      // Test with very old last failure time
      circuitBreaker.lastFailureTime = 0;
      
      const status = circuitBreaker.getStatus();
      expect(status.timeSinceLastFailure).toBeGreaterThan(0);
      expect(status.timeToRecovery).toBe(0);
    });
  });
});
/**
 * Database Circuit Breaker Integration Tests
 * Tests complete database interaction with circuit breaker protection
 */

const { emergencyDatabaseRecovery, testDatabaseConnectivity, resetAllCircuitBreakers } = require('../../utils/circuitBreakerReset');
const DatabaseCircuitBreaker = require('../../utils/databaseCircuitBreaker');
const timeoutHelper = require('../../utils/timeoutHelper');

describe('Database Circuit Breaker Integration Tests', () => {
  let dbCircuitBreaker;

  beforeAll(() => {
    // Reset all circuit breakers
    resetAllCircuitBreakers();
    dbCircuitBreaker = new DatabaseCircuitBreaker();
  });

  afterAll(() => {
    // Clean up
    resetAllCircuitBreakers();
  });

  describe('Database Connection Protection', () => {
    test('should protect database operations with circuit breaker', async () => {
      console.log('🛡️ TEST: Database operation protection...');
      
      // Mock database operation that succeeds
      const successfulDbOperation = () => Promise.resolve({ 
        rows: [{ count: 1 }], 
        duration: 45 
      });
      
      const result = await dbCircuitBreaker.execute(successfulDbOperation, 'integration-test-query');
      
      expect(result).toBeDefined();
      expect(result.rows).toBeDefined();
      expect(dbCircuitBreaker.totalSuccesses).toBe(1);
      expect(dbCircuitBreaker.state).toBe('closed');
      
      console.log('✅ Database operation protection validated');
    });

    test('should handle database connection failures gracefully', async () => {
      console.log('🚨 TEST: Database connection failure handling...');
      
      // Mock database operation that fails
      const failingDbOperation = () => Promise.reject(new Error('Connection refused'));
      
      let caughtError = null;
      try {
        await dbCircuitBreaker.execute(failingDbOperation, 'integration-test-fail');
      } catch (error) {
        caughtError = error;
      }
      
      expect(caughtError).toBeDefined();
      expect(caughtError.message).toBe('Connection refused');
      expect(dbCircuitBreaker.totalFailures).toBeGreaterThan(0);
      
      console.log('✅ Database connection failure handling validated');
    });

    test('should open circuit breaker after repeated database failures', async () => {
      console.log('🔐 TEST: Circuit breaker opening after repeated failures...');
      
      const persistentFailure = () => Promise.reject(new Error('Database unavailable'));
      
      // Trigger enough failures to open circuit
      for (let i = 0; i < 25; i++) {
        try {
          await dbCircuitBreaker.execute(persistentFailure, 'repeated-failure-test');
        } catch (error) {
          // Expected failures
        }
      }
      
      expect(dbCircuitBreaker.state).toBe('open');
      
      // Next operation should fail immediately
      try {
        await dbCircuitBreaker.execute(persistentFailure, 'should-be-blocked');
        fail('Should have been blocked by circuit breaker');
      } catch (error) {
        expect(error.message).toContain('Circuit breaker is OPEN');
      }
      
      console.log('✅ Circuit breaker opening validated');
    });

    test('should recover from open state with successful operations', async () => {
      console.log('🔄 TEST: Circuit breaker recovery...');
      
      // Force circuit to open state
      const dbBreaker = new DatabaseCircuitBreaker();
      for (let i = 0; i < 25; i++) {
        dbBreaker.recordFailure('recovery-test', new Error('Test failure'));
      }
      expect(dbBreaker.state).toBe('open');
      
      // Simulate timeout passage
      dbBreaker.lastFailureTime = Date.now() - 15000; // 15 seconds ago
      
      // Successful operation should transition to half-open, then closed
      const successOperation = () => Promise.resolve('recovery success');
      
      // First success should transition to half-open
      const result1 = await dbBreaker.execute(successOperation, 'recovery-1');
      expect(result1).toBe('recovery success');
      expect(dbBreaker.state).toBe('half-open');
      
      // Additional successes should close the circuit
      await dbBreaker.execute(successOperation, 'recovery-2');
      await dbBreaker.execute(successOperation, 'recovery-3');
      
      expect(dbBreaker.state).toBe('closed');
      expect(dbBreaker.failures).toBe(0);
      
      console.log('✅ Circuit breaker recovery validated');
    });
  });

  describe('Emergency Database Recovery Integration', () => {
    test('should perform complete emergency database recovery workflow', async () => {
      console.log('🚨 TEST: Complete emergency database recovery...');
      
      // Simulate crisis state
      for (let i = 0; i < 16; i++) {
        timeoutHelper.recordFailure('database-crisis');
        timeoutHelper.recordFailure('database-query');
        timeoutHelper.recordFailure('database-connect');
      }
      
      // Verify crisis state
      expect(timeoutHelper.isCircuitOpen('database-crisis')).toBe(true);
      
      // Perform emergency recovery
      const recoveryResult = await emergencyDatabaseRecovery();
      
      expect(recoveryResult).toBeDefined();
      expect(recoveryResult.steps).toBeDefined();
      expect(recoveryResult.steps.length).toBeGreaterThan(0);
      
      // Check recovery steps
      const stepNames = recoveryResult.steps.map(step => step.step);
      expect(stepNames).toContain('reset_circuit_breakers');
      expect(stepNames).toContain('test_connectivity');
      
      // Verify circuit breakers were reset
      expect(timeoutHelper.isCircuitOpen('database-crisis')).toBe(false);
      
      console.log(`✅ Emergency recovery completed with ${recoveryResult.steps.length} steps`);
    });

    test('should test database connectivity independently', async () => {
      console.log('🧪 TEST: Independent database connectivity testing...');
      
      const connectivityResult = await testDatabaseConnectivity();
      
      expect(connectivityResult).toBeDefined();
      expect(connectivityResult).toHaveProperty('success');
      expect(connectivityResult).toHaveProperty('message');
      
      // Test accepts both success and failure (depending on environment)
      if (connectivityResult.success) {
        expect(connectivityResult.health).toBeDefined();
        console.log('✅ Database connectivity test passed');
      } else {
        expect(connectivityResult.error).toBeDefined();
        console.log('⚠️ Database connectivity test failed (expected in test environment)');
      }
    });
  });

  describe('Circuit Breaker State Management', () => {
    test('should maintain consistent state across multiple operations', async () => {
      console.log('🔄 TEST: State consistency across operations...');
      
      const stateTestBreaker = new DatabaseCircuitBreaker();
      
      // Mix of successful and failed operations
      const operations = [
        () => Promise.resolve('success-1'),
        () => Promise.reject(new Error('failure-1')),
        () => Promise.resolve('success-2'),
        () => Promise.resolve('success-3'),
        () => Promise.reject(new Error('failure-2'))
      ];
      
      let successCount = 0;
      let failureCount = 0;
      
      for (const operation of operations) {
        try {
          await stateTestBreaker.execute(operation, 'state-consistency-test');
          successCount++;
        } catch (error) {
          failureCount++;
        }
      }
      
      expect(successCount).toBe(3);
      expect(failureCount).toBe(2);
      expect(stateTestBreaker.totalSuccesses).toBe(3);
      expect(stateTestBreaker.totalFailures).toBe(2);
      expect(stateTestBreaker.totalRequests).toBe(5);
      
      console.log('✅ State consistency validated across mixed operations');
    });

    test('should handle concurrent database operations safely', async () => {
      console.log('⚡ TEST: Concurrent operation safety...');
      
      const concurrentBreaker = new DatabaseCircuitBreaker();
      
      // Create concurrent operations
      const concurrentOps = [];
      for (let i = 0; i < 10; i++) {
        const operation = () => Promise.resolve(`concurrent-result-${i}`);
        concurrentOps.push(concurrentBreaker.execute(operation, `concurrent-op-${i}`));
      }
      
      const results = await Promise.all(concurrentOps);
      
      expect(results.length).toBe(10);
      expect(concurrentBreaker.totalRequests).toBe(10);
      expect(concurrentBreaker.totalSuccesses).toBe(10);
      expect(concurrentBreaker.state).toBe('closed');
      
      console.log('✅ Concurrent operation safety validated');
    });

    test('should provide accurate metrics during mixed load', async () => {
      console.log('📊 TEST: Metrics accuracy under mixed load...');
      
      const metricsBreaker = new DatabaseCircuitBreaker();
      
      // Generate mixed load
      const operations = [];
      for (let i = 0; i < 20; i++) {
        if (i < 15) {
          operations.push(() => Promise.resolve(`success-${i}`));
        } else {
          operations.push(() => Promise.reject(new Error(`failure-${i}`)));
        }
      }
      
      // Execute all operations
      for (const operation of operations) {
        try {
          await metricsBreaker.execute(operation, 'metrics-test');
        } catch (error) {
          // Expected failures
        }
      }
      
      const status = metricsBreaker.getStatus();
      
      expect(status.totalRequests).toBe(20);
      expect(status.totalSuccesses).toBe(15);
      expect(status.totalFailures).toBe(5);
      expect(status.successRate).toBe('75.00%');
      
      console.log('✅ Metrics accuracy validated under mixed load');
    });
  });

  describe('Performance and Scalability', () => {
    test('should handle high-frequency database operations efficiently', async () => {
      console.log('⚡ TEST: High-frequency operation performance...');
      
      const performanceBreaker = new DatabaseCircuitBreaker();
      const startTime = Date.now();
      
      // High-frequency operations
      const promises = [];
      for (let i = 0; i < 100; i++) {
        const operation = () => Promise.resolve(`high-freq-${i}`);
        promises.push(performanceBreaker.execute(operation, `perf-test-${i}`));
      }
      
      await Promise.all(promises);
      
      const endTime = Date.now();
      const duration = endTime - startTime;
      
      expect(duration).toBeLessThan(5000); // Should complete in less than 5 seconds
      expect(performanceBreaker.totalRequests).toBe(100);
      expect(performanceBreaker.totalSuccesses).toBe(100);
      
      console.log(`✅ High-frequency performance validated: 100 operations in ${duration}ms`);
    });

    test('should manage memory efficiently with large operation history', async () => {
      console.log('🧠 TEST: Memory efficiency with large history...');
      
      const memoryBreaker = new DatabaseCircuitBreaker();
      
      // Generate large operation history
      for (let i = 0; i < 200; i++) {
        if (i % 2 === 0) {
          memoryBreaker.recordSuccess(`memory-test-${i}`, 50);
        } else {
          memoryBreaker.recordFailure(`memory-test-${i}`, new Error(`Test error ${i}`));
        }
      }
      
      const status = memoryBreaker.getStatus();
      
      // History should be limited to prevent memory issues
      expect(status.recentHistory.length).toBeLessThanOrEqual(10);
      expect(memoryBreaker.requestHistory.length).toBeLessThanOrEqual(100);
      
      console.log('✅ Memory efficiency validated with large operation history');
    });
  });

  describe('Error Recovery Scenarios', () => {
    test('should recover from catastrophic database failure', async () => {
      console.log('💥 TEST: Catastrophic failure recovery...');
      
      const catastropheBreaker = new DatabaseCircuitBreaker();
      
      // Simulate catastrophic failure
      for (let i = 0; i < 50; i++) {
        catastropheBreaker.recordFailure('catastrophic-test', new Error('Database down'));
      }
      
      expect(catastropheBreaker.state).toBe('open');
      expect(catastropheBreaker.failures).toBeGreaterThan(20);
      
      // Force reset and recovery
      catastropheBreaker.forceReset();
      
      expect(catastropheBreaker.state).toBe('closed');
      expect(catastropheBreaker.failures).toBe(0);
      
      // Test successful operation after reset
      const operation = () => Promise.resolve('recovery-success');
      const result = await catastropheBreaker.execute(operation, 'post-catastrophe');
      
      expect(result).toBe('recovery-success');
      expect(catastropheBreaker.state).toBe('closed');
      
      console.log('✅ Catastrophic failure recovery validated');
    });

    test('should handle partial recovery scenarios', async () => {
      console.log('🔄 TEST: Partial recovery scenario...');
      
      const partialBreaker = new DatabaseCircuitBreaker();
      
      // Create open state
      for (let i = 0; i < 25; i++) {
        partialBreaker.recordFailure('partial-recovery', new Error('Intermittent failure'));
      }
      
      expect(partialBreaker.state).toBe('open');
      
      // Simulate timeout for half-open transition
      partialBreaker.lastFailureTime = Date.now() - 15000;
      
      // Mix of successes and failures in half-open state
      const mixedOperation1 = () => Promise.resolve('partial-success-1');
      const mixedOperation2 = () => Promise.reject(new Error('partial-failure'));
      const mixedOperation3 = () => Promise.resolve('partial-success-2');
      
      await partialBreaker.execute(mixedOperation1, 'partial-1');
      expect(partialBreaker.state).toBe('half-open');
      
      try {
        await partialBreaker.execute(mixedOperation2, 'partial-2');
      } catch (error) {
        // Expected failure
      }
      
      await partialBreaker.execute(mixedOperation3, 'partial-3');
      
      // Should eventually recover with enough successes
      const finalOperation = () => Promise.resolve('final-success');
      await partialBreaker.execute(finalOperation, 'final');
      
      expect(partialBreaker.state).toBe('closed');
      
      console.log('✅ Partial recovery scenario validated');
    });
  });
});
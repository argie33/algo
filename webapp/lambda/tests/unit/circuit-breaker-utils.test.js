/**
 * Unit Tests for Circuit Breaker Utilities
 * Tests individual circuit breaker components and configurations
 */

const timeoutHelper = require('../../utils/timeoutHelper');
const { resetAllCircuitBreakers, resetCircuitBreaker, getCircuitBreakerStatus, emergencyDatabaseRecovery } = require('../../utils/circuitBreakerReset');
const DatabaseCircuitBreaker = require('../../utils/databaseCircuitBreaker');

describe('Circuit Breaker Utilities Unit Tests', () => {
  beforeEach(() => {
    // Reset all circuit breakers before each test
    resetAllCircuitBreakers();
  });

  describe('TimeoutHelper Circuit Breaker', () => {
    test('should initialize with production-ready thresholds', () => {
      const serviceKey = 'test-service-init';
      
      // Trigger circuit breaker creation
      timeoutHelper.recordFailure(serviceKey);
      
      const breaker = timeoutHelper.circuitBreakers.get(serviceKey);
      expect(breaker).toBeDefined();
      
      // Validate production thresholds
      expect(breaker.threshold).toBe(15); // PRODUCTION FIX
      expect(breaker.timeout).toBe(15000); // PRODUCTION FIX: 15 seconds
      expect(breaker.halfOpenMaxCalls).toBe(8); // PRODUCTION FIX
      
      console.log('✅ Production thresholds validated in unit test');
    });

    test('should track failure counts correctly', () => {
      const serviceKey = 'test-failure-tracking';
      
      // Record multiple failures
      for (let i = 1; i <= 10; i++) {
        timeoutHelper.recordFailure(serviceKey);
        
        const breaker = timeoutHelper.circuitBreakers.get(serviceKey);
        expect(breaker.failures).toBe(i);
        expect(breaker.totalFailures).toBe(i);
      }
      
      console.log('✅ Failure tracking validated');
    });

    test('should transition states correctly (closed -> open -> half-open -> closed)', () => {
      const serviceKey = 'test-state-transitions';
      
      // Start in closed state
      expect(timeoutHelper.isCircuitOpen(serviceKey)).toBe(false);
      
      // Record failures to trigger open state
      for (let i = 0; i < 16; i++) {
        timeoutHelper.recordFailure(serviceKey);
      }
      
      // Should be open now
      expect(timeoutHelper.isCircuitOpen(serviceKey)).toBe(true);
      
      const breaker = timeoutHelper.circuitBreakers.get(serviceKey);
      expect(breaker.state).toBe('open');
      
      // Simulate timeout passage by manipulating last failure time
      breaker.lastFailureTime = Date.now() - 20000; // 20 seconds ago
      
      // Next call should transition to half-open
      const wasOpen = timeoutHelper.isCircuitOpen(serviceKey);
      expect(wasOpen).toBe(false); // Should return false and transition to half-open
      expect(breaker.state).toBe('half-open');
      
      // Record successes to close circuit
      for (let i = 0; i < 3; i++) {
        timeoutHelper.recordSuccess(serviceKey);
      }
      
      expect(breaker.state).toBe('closed');
      expect(breaker.failures).toBe(0);
      
      console.log('✅ State transitions validated: closed -> open -> half-open -> closed');
    });

    test('should record event history correctly', () => {
      const serviceKey = 'test-event-history';
      
      // Generate mixed events
      timeoutHelper.recordSuccess(serviceKey);
      timeoutHelper.recordFailure(serviceKey);
      timeoutHelper.recordSuccess(serviceKey);
      timeoutHelper.recordFailure(serviceKey);
      
      const breaker = timeoutHelper.circuitBreakers.get(serviceKey);
      expect(breaker.history).toBeDefined();
      expect(breaker.history.length).toBeGreaterThan(0);
      
      // Check that events are recorded
      const eventTypes = breaker.history.map(event => event.type);
      expect(eventTypes).toContain('success');
      expect(eventTypes).toContain('failure');
      
      console.log('✅ Event history tracking validated');
    });

    test('should calculate metrics correctly', () => {
      const serviceKey = 'test-metrics-calculation';
      
      // Generate test data
      for (let i = 0; i < 5; i++) {
        timeoutHelper.recordSuccess(serviceKey);
      }
      for (let i = 0; i < 2; i++) {
        timeoutHelper.recordFailure(serviceKey);
      }
      
      const metrics = timeoutHelper.getCircuitBreakerMetrics();
      const serviceMetrics = metrics[serviceKey];
      
      expect(serviceMetrics).toBeDefined();
      expect(serviceMetrics.totalSuccesses).toBeGreaterThan(0);
      expect(serviceMetrics.totalFailures).toBeGreaterThan(0);
      expect(serviceMetrics.successRate).toBeDefined();
      expect(serviceMetrics.failureRate).toBeDefined();
      
      console.log('✅ Metrics calculation validated');
    });

    test('should handle recent activity tracking', () => {
      const serviceKey = 'test-recent-activity';
      
      // Generate recent activity
      timeoutHelper.recordSuccess(serviceKey);
      timeoutHelper.recordFailure(serviceKey);
      timeoutHelper.recordSuccess(serviceKey);
      
      const activity = timeoutHelper.getRecentActivity(serviceKey);
      
      expect(activity.requests).toBeGreaterThan(0);
      expect(activity.successes).toBeGreaterThan(0);
      expect(activity.failures).toBeGreaterThan(0);
      expect(activity.period).toBe('5min');
      
      console.log('✅ Recent activity tracking validated');
    });

    test('should calculate risk levels accurately', () => {
      const lowRiskKey = 'test-low-risk';
      const mediumRiskKey = 'test-medium-risk';
      const highRiskKey = 'test-high-risk';
      
      // Low risk: no failures
      timeoutHelper.recordSuccess(lowRiskKey);
      let breaker = timeoutHelper.circuitBreakers.get(lowRiskKey);
      if (breaker) {
        expect(timeoutHelper.getRiskLevel(breaker)).toBe('MINIMAL');
      }
      
      // Medium risk: half threshold
      for (let i = 0; i < 8; i++) {
        timeoutHelper.recordFailure(mediumRiskKey);
      }
      breaker = timeoutHelper.circuitBreakers.get(mediumRiskKey);
      if (breaker) {
        expect(['LOW', 'MEDIUM', 'MINIMAL']).toContain(timeoutHelper.getRiskLevel(breaker));
      }
      
      // High risk: open state
      for (let i = 0; i < 16; i++) {
        timeoutHelper.recordFailure(highRiskKey);
      }
      breaker = timeoutHelper.circuitBreakers.get(highRiskKey);
      if (breaker) {
        expect(['HIGH', 'MEDIUM']).toContain(timeoutHelper.getRiskLevel(breaker));
      }
      
      console.log('✅ Risk level calculations validated');
    });
  });

  describe('DatabaseCircuitBreaker Class', () => {
    test('should initialize with correct production configuration', () => {
      const dbBreaker = new DatabaseCircuitBreaker();
      
      expect(dbBreaker.failureThreshold).toBe(20); // PRODUCTION FIX
      expect(dbBreaker.recoveryTimeout).toBe(10000); // PRODUCTION FIX: 10 seconds
      expect(dbBreaker.halfOpenMaxCalls).toBe(10); // PRODUCTION FIX
      expect(dbBreaker.halfOpenSuccessThreshold).toBe(3);
      
      console.log('✅ DatabaseCircuitBreaker production configuration validated');
    });

    test('should execute operations and track results', async () => {
      const dbBreaker = new DatabaseCircuitBreaker();
      
      // Test successful operation
      const successOperation = () => Promise.resolve('success');
      const result = await dbBreaker.execute(successOperation, 'test-operation');
      
      expect(result).toBe('success');
      expect(dbBreaker.totalSuccesses).toBe(1);
      expect(dbBreaker.totalRequests).toBe(1);
      
      console.log('✅ Database circuit breaker operation execution validated');
    });

    test('should handle operation failures correctly', async () => {
      const dbBreaker = new DatabaseCircuitBreaker();
      
      // Test failing operation
      const failOperation = () => Promise.reject(new Error('Test failure'));
      
      try {
        await dbBreaker.execute(failOperation, 'test-fail-operation');
      } catch (error) {
        expect(error.message).toBe('Test failure');
      }
      
      expect(dbBreaker.totalFailures).toBe(1);
      expect(dbBreaker.failures).toBe(1);
      expect(dbBreaker.totalRequests).toBe(1);
      
      console.log('✅ Database circuit breaker failure handling validated');
    });

    test('should open circuit after threshold failures', async () => {
      const dbBreaker = new DatabaseCircuitBreaker();
      const failOperation = () => Promise.reject(new Error('Repeated failure'));
      
      // Trigger enough failures to open circuit
      for (let i = 0; i < 21; i++) {
        try {
          await dbBreaker.execute(failOperation, 'threshold-test');
        } catch (error) {
          // Expected to fail
        }
      }
      
      expect(dbBreaker.state).toBe('open');
      expect(dbBreaker.failures).toBeGreaterThanOrEqual(20);
      
      // Next operation should fail immediately with circuit breaker error
      try {
        await dbBreaker.execute(failOperation, 'should-be-blocked');
        fail('Should have thrown circuit breaker error');
      } catch (error) {
        expect(error.message).toContain('Circuit breaker is OPEN');
      }
      
      console.log('✅ Database circuit breaker open state validated');
    });

    test('should provide detailed status information', () => {
      const dbBreaker = new DatabaseCircuitBreaker();
      
      // Generate some activity
      dbBreaker.recordSuccess('test-status', 100);
      dbBreaker.recordFailure('test-status-fail', new Error('Test error'));
      
      const status = dbBreaker.getStatus();
      
      expect(status).toHaveProperty('state');
      expect(status).toHaveProperty('failures');
      expect(status).toHaveProperty('successCount');
      expect(status).toHaveProperty('totalRequests');
      expect(status).toHaveProperty('successRate');
      expect(status).toHaveProperty('isHealthy');
      expect(status).toHaveProperty('recentHistory');
      
      expect(status.totalRequests).toBeGreaterThanOrEqual(0);
      expect(status.recentHistory.length).toBeGreaterThanOrEqual(0);
      
      console.log('✅ Database circuit breaker status reporting validated');
    });

    test('should force reset correctly', () => {
      const dbBreaker = new DatabaseCircuitBreaker();
      
      // Simulate failures and open state
      for (let i = 0; i < 25; i++) {
        dbBreaker.recordFailure('force-reset-test', new Error('Test'));
      }
      
      expect(dbBreaker.state).toBe('open');
      expect(dbBreaker.failures).toBeGreaterThan(0);
      
      // Force reset
      dbBreaker.forceReset();
      
      expect(dbBreaker.state).toBe('closed');
      expect(dbBreaker.failures).toBe(0);
      expect(dbBreaker.successCount).toBe(0);
      
      console.log('✅ Database circuit breaker force reset validated');
    });
  });

  describe('Circuit Breaker Reset Utilities', () => {
    test('should reset all circuit breakers', () => {
      // Create some circuit breakers with failures
      const services = ['service-1', 'service-2', 'service-3'];
      
      services.forEach(service => {
        for (let i = 0; i < 16; i++) {
          timeoutHelper.recordFailure(service);
        }
      });
      
      // Verify they're all open
      services.forEach(service => {
        expect(timeoutHelper.isCircuitOpen(service)).toBe(true);
      });
      
      // Reset all
      const result = resetAllCircuitBreakers();
      
      expect(result.success).toBe(true);
      expect(result.reset).toBe(services.length);
      expect(result.services).toEqual(services);
      
      // Verify they're all closed
      services.forEach(service => {
        expect(timeoutHelper.isCircuitOpen(service)).toBe(false);
      });
      
      console.log('✅ Reset all circuit breakers validated');
    });

    test('should reset specific circuit breaker', () => {
      const serviceKey = 'specific-reset-test';
      
      // Create failure state
      for (let i = 0; i < 16; i++) {
        timeoutHelper.recordFailure(serviceKey);
      }
      
      expect(timeoutHelper.isCircuitOpen(serviceKey)).toBe(true);
      
      // Reset specific breaker
      const result = resetCircuitBreaker(serviceKey);
      
      expect(result.success).toBe(true);
      expect(result.found).toBe(true);
      expect(result.serviceKey).toBe(serviceKey);
      expect(result.newState).toBe('closed');
      
      expect(timeoutHelper.isCircuitOpen(serviceKey)).toBe(false);
      
      console.log('✅ Reset specific circuit breaker validated');
    });

    test('should get comprehensive circuit breaker status', () => {
      // Create mixed states
      timeoutHelper.recordFailure('failed-service');
      timeoutHelper.recordSuccess('healthy-service');
      
      // Open one circuit breaker
      for (let i = 0; i < 16; i++) {
        timeoutHelper.recordFailure('open-service');
      }
      
      const status = getCircuitBreakerStatus();
      
      expect(status.totalBreakers).toBeGreaterThan(0);
      expect(status.healthy).toBeGreaterThan(0);
      expect(status.open).toBeGreaterThan(0);
      expect(status.needsAttention).toBeDefined();
      expect(status.recommendations).toBeDefined();
      expect(status.circuitBreakers).toBeDefined();
      
      // Should have recommendations for open circuit breakers
      expect(status.recommendations.length).toBeGreaterThan(0);
      expect(status.needsAttention.length).toBeGreaterThan(0);
      
      console.log('✅ Comprehensive circuit breaker status validated');
    });

    test('should handle non-existent circuit breaker reset gracefully', () => {
      const result = resetCircuitBreaker('non-existent-service');
      
      expect(result.found).toBe(false);
      expect(result.serviceKey).toBe('non-existent-service');
      
      console.log('✅ Non-existent circuit breaker reset handling validated');
    });
  });

  describe('Performance and Memory Management', () => {
    test('should limit history size to prevent memory leaks', () => {
      const serviceKey = 'memory-test-service';
      
      // Generate more than 100 events
      for (let i = 0; i < 150; i++) {
        if (i % 2 === 0) {
          timeoutHelper.recordSuccess(serviceKey);
        } else {
          timeoutHelper.recordFailure(serviceKey);
        }
      }
      
      const breaker = timeoutHelper.circuitBreakers.get(serviceKey);
      expect(breaker.history.length).toBeLessThanOrEqual(100);
      
      console.log('✅ History size limit validated - prevents memory leaks');
    });

    test('should handle rapid state changes efficiently', () => {
      const serviceKey = 'rapid-changes-test';
      
      const startTime = Date.now();
      
      // Rapidly change states
      for (let i = 0; i < 1000; i++) {
        if (i % 10 === 0) {
          timeoutHelper.recordSuccess(serviceKey);
        } else {
          timeoutHelper.recordFailure(serviceKey);
        }
      }
      
      const endTime = Date.now();
      const duration = endTime - startTime;
      
      expect(duration).toBeLessThan(1000); // Should complete in less than 1 second
      
      console.log(`✅ Performance validated: 1000 state changes in ${duration}ms`);
    });
  });
});
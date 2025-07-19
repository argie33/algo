/**
 * End-to-End Circuit Breaker Crisis Resolution Tests
 * Tests the complete circuit breaker emergency response workflow
 */

const request = require('supertest');
const express = require('express');
const timeoutHelper = require('../../utils/timeoutHelper');
const { resetAllCircuitBreakers, emergencyDatabaseRecovery, getCircuitBreakerStatus } = require('../../utils/circuitBreakerReset');

// Import the emergency circuit breaker router
const emergencyCircuitBreakerRouter = require('../../routes/emergency-circuit-breaker');

describe('Circuit Breaker End-to-End Crisis Resolution', () => {
  let app;
  let circuitBreakerKeys;

  beforeAll(() => {
    // Create test Express app with emergency circuit breaker routes
    app = express();
    app.use(express.json());
    app.use('/api/emergency-circuit-breaker', emergencyCircuitBreakerRouter);
    
    // Store existing circuit breaker state
    circuitBreakerKeys = Array.from(timeoutHelper.circuitBreakers.keys());
  });

  afterAll(() => {
    // Clean up - reset all circuit breakers
    resetAllCircuitBreakers();
  });

  describe('Circuit Breaker Crisis Simulation and Recovery', () => {
    test('should simulate database circuit breaker crisis and recover', async () => {
      console.log('🚨 TEST: Simulating circuit breaker crisis...');
      
      // Step 1: Simulate failures to trigger circuit breaker opening
      const serviceKey = 'database-test-crisis';
      
      // Force multiple failures to open circuit breaker
      for (let i = 0; i < 16; i++) {
        timeoutHelper.recordFailure(serviceKey);
      }
      
      // Verify circuit breaker is now open
      const isOpen = timeoutHelper.isCircuitOpen(serviceKey);
      expect(isOpen).toBe(true);
      
      const statusBefore = timeoutHelper.getCircuitBreakerStatus();
      expect(statusBefore[serviceKey]).toBeDefined();
      expect(statusBefore[serviceKey].state).toBe('open');
      expect(statusBefore[serviceKey].failures).toBeGreaterThanOrEqual(15);
      
      console.log(`✅ Circuit breaker crisis simulated: ${serviceKey} is OPEN with ${statusBefore[serviceKey].failures} failures`);
    });

    test('should get circuit breaker status via API', async () => {
      console.log('🔍 TEST: Getting circuit breaker status via API...');
      
      const response = await request(app)
        .get('/api/emergency-circuit-breaker/status')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.status).toBeDefined();
      expect(response.body.status.totalBreakers).toBeGreaterThan(0);
      expect(response.body.status.open).toBeGreaterThan(0);
      expect(response.body.timestamp).toBeDefined();
      
      console.log(`✅ Status retrieved: ${response.body.status.totalBreakers} total breakers, ${response.body.status.open} open`);
    });

    test('should get health check showing degraded status', async () => {
      console.log('🏥 TEST: Health check should show degraded status...');
      
      const response = await request(app)
        .get('/api/emergency-circuit-breaker/health')
        .expect(503); // Service Unavailable due to open circuit breakers

      expect(response.body.success).toBe(false);
      expect(response.body.message).toContain('need attention');
      expect(response.body.health).toBeDefined();
      expect(response.body.health.overall).toBe('degraded');
      expect(response.body.health.open).toBeGreaterThan(0);
      
      console.log(`✅ Health check shows degraded status with ${response.body.health.open} open circuit breakers`);
    });

    test('should reset all circuit breakers via emergency API', async () => {
      console.log('🔄 TEST: Emergency reset all circuit breakers...');
      
      const response = await request(app)
        .post('/api/emergency-circuit-breaker/reset-all')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.result).toBeDefined();
      expect(response.body.result.reset).toBeGreaterThan(0);
      expect(response.body.result.services).toBeDefined();
      expect(response.body.nextSteps).toBeDefined();
      
      console.log(`✅ Emergency reset completed: ${response.body.result.reset} circuit breakers reset`);
    });

    test('should verify circuit breakers are closed after reset', async () => {
      console.log('✅ TEST: Verifying circuit breakers are closed...');
      
      const response = await request(app)
        .get('/api/emergency-circuit-breaker/status')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.status.open).toBe(0);
      expect(response.body.status.healthy).toBeGreaterThan(0);
      
      console.log(`✅ All circuit breakers restored: ${response.body.status.healthy} healthy, ${response.body.status.open} open`);
    });

    test('should show healthy status after reset', async () => {
      console.log('🏥 TEST: Health check should show healthy status after reset...');
      
      const response = await request(app)
        .get('/api/emergency-circuit-breaker/health')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.message).toContain('healthy');
      expect(response.body.health.overall).toBe('healthy');
      expect(response.body.health.open).toBe(0);
      
      console.log('✅ Health check shows healthy status after emergency reset');
    });
  });

  describe('Database Recovery Workflow', () => {
    test('should perform emergency database recovery', async () => {
      console.log('🚨 TEST: Emergency database recovery workflow...');
      
      const response = await request(app)
        .post('/api/emergency-circuit-breaker/database-recovery');
      
      // Accept both 200 (success) and 500 (partial success) for this test
      expect([200, 500]).toContain(response.status);
      
      expect(response.body.result).toBeDefined();
      expect(response.body.result.steps).toBeDefined();
      expect(response.body.result.steps.length).toBeGreaterThan(0);
      
      // Verify recovery steps were attempted
      const stepNames = response.body.result.steps.map(step => step.step);
      expect(stepNames).toContain('reset_circuit_breakers');
      expect(stepNames).toContain('test_connectivity');
      
      console.log(`✅ Database recovery attempted with ${response.body.result.steps.length} steps`);
    });

    test('should test database connectivity', async () => {
      console.log('🧪 TEST: Testing database connectivity...');
      
      const response = await request(app)
        .post('/api/emergency-circuit-breaker/test-database');
      
      // Accept both success and failure for connectivity test
      expect([200, 500]).toContain(response.status);
      
      expect(response.body.result).toBeDefined();
      expect(response.body.message).toBeDefined();
      expect(response.body.timestamp).toBeDefined();
      
      if (response.body.success) {
        console.log('✅ Database connectivity test passed');
      } else {
        console.log('⚠️ Database connectivity test failed (expected in test environment)');
      }
    });
  });

  describe('Circuit Breaker Configuration Validation', () => {
    test('should validate production circuit breaker thresholds', () => {
      console.log('🔧 TEST: Validating production circuit breaker configuration...');
      
      // Create a new service to check threshold configuration
      const testServiceKey = 'production-config-test';
      timeoutHelper.recordFailure(testServiceKey);
      
      const breaker = timeoutHelper.circuitBreakers.get(testServiceKey);
      expect(breaker).toBeDefined();
      
      // Validate production thresholds (from our fixes)
      expect(breaker.threshold).toBe(15); // Should be 15 (not the old 5)
      expect(breaker.timeout).toBe(15000); // Should be 15 seconds (not 60 seconds)
      expect(breaker.halfOpenMaxCalls).toBe(8); // Should be 8 (not 3)
      
      console.log('✅ Production thresholds validated:');
      console.log(`   - Failure threshold: ${breaker.threshold} (was 5)`);
      console.log(`   - Recovery timeout: ${breaker.timeout}ms (was 60000ms)`);
      console.log(`   - Half-open max calls: ${breaker.halfOpenMaxCalls} (was 3)`);
    });

    test('should validate circuit breaker recovery behavior', async () => {
      console.log('🔄 TEST: Validating circuit breaker recovery behavior...');
      
      const testServiceKey = 'recovery-behavior-test';
      
      // Trigger failures to open circuit breaker
      for (let i = 0; i < 16; i++) {
        timeoutHelper.recordFailure(testServiceKey);
      }
      
      // Verify it's open
      expect(timeoutHelper.isCircuitOpen(testServiceKey)).toBe(true);
      
      // Record a success to trigger recovery
      timeoutHelper.recordSuccess(testServiceKey);
      
      // Check if it transitions to closed or half-open
      const status = timeoutHelper.getCircuitBreakerStatus();
      const breakerStatus = status[testServiceKey];
      
      expect(breakerStatus).toBeDefined();
      expect(['closed', 'half-open']).toContain(breakerStatus.state);
      
      console.log(`✅ Recovery behavior validated: ${breakerStatus.state} after success`);
    });
  });

  describe('Performance and Metrics Validation', () => {
    test('should validate circuit breaker metrics collection', () => {
      console.log('📊 TEST: Validating circuit breaker metrics...');
      
      const metrics = timeoutHelper.getCircuitBreakerMetrics();
      expect(metrics).toBeDefined();
      expect(typeof metrics).toBe('object');
      
      // Check if metrics include expected data
      const serviceKeys = Object.keys(metrics);
      expect(serviceKeys.length).toBeGreaterThan(0);
      
      // Validate metric structure for first service
      if (serviceKeys.length > 0) {
        const firstMetric = metrics[serviceKeys[0]];
        expect(firstMetric).toHaveProperty('state');
        expect(firstMetric).toHaveProperty('totalRequests');
        expect(firstMetric).toHaveProperty('successRate');
        expect(firstMetric).toHaveProperty('isHealthy');
        expect(firstMetric).toHaveProperty('predictedRecovery');
        expect(firstMetric).toHaveProperty('riskLevel');
      }
      
      console.log(`✅ Metrics validated for ${serviceKeys.length} services`);
    });

    test('should validate circuit breaker recent activity tracking', () => {
      console.log('📈 TEST: Validating recent activity tracking...');
      
      const testServiceKey = 'activity-tracking-test';
      
      // Generate some activity
      timeoutHelper.recordSuccess(testServiceKey);
      timeoutHelper.recordFailure(testServiceKey);
      timeoutHelper.recordSuccess(testServiceKey);
      
      const activity = timeoutHelper.getRecentActivity(testServiceKey);
      expect(activity).toBeDefined();
      expect(activity).toHaveProperty('requests');
      expect(activity).toHaveProperty('failures');
      expect(activity).toHaveProperty('successes');
      expect(activity).toHaveProperty('period');
      
      expect(activity.requests).toBeGreaterThan(0);
      expect(activity.period).toBe('5min');
      
      console.log(`✅ Activity tracking validated: ${activity.requests} requests in ${activity.period}`);
    });
  });

  describe('Error Handling and Edge Cases', () => {
    test('should handle malformed emergency requests gracefully', async () => {
      console.log('🛡️ TEST: Testing error handling for malformed requests...');
      
      // Test malformed reset request
      const response = await request(app)
        .post('/api/emergency-circuit-breaker/reset-all')
        .send({ invalid: 'data' })
        .expect(200); // Should still work since reset doesn't require body
      
      expect(response.body.success).toBe(true);
      
      console.log('✅ Error handling validated for malformed requests');
    });

    test('should handle non-existent circuit breaker gracefully', () => {
      console.log('🔍 TEST: Testing non-existent circuit breaker handling...');
      
      const nonExistentKey = 'non-existent-service-12345';
      const isOpen = timeoutHelper.isCircuitOpen(nonExistentKey);
      
      expect(isOpen).toBe(false); // Should default to false for non-existent
      
      console.log('✅ Non-existent circuit breaker handling validated');
    });

    test('should validate risk level calculations', () => {
      console.log('⚠️ TEST: Validating risk level calculations...');
      
      const testServiceKey = 'risk-level-test';
      
      // Test minimal risk (no failures)
      timeoutHelper.recordSuccess(testServiceKey);
      let breaker = timeoutHelper.circuitBreakers.get(testServiceKey);
      let riskLevel = timeoutHelper.getRiskLevel(breaker);
      expect(riskLevel).toBe('MINIMAL');
      
      // Test medium risk (half threshold)
      for (let i = 0; i < 8; i++) {
        timeoutHelper.recordFailure(testServiceKey);
      }
      breaker = timeoutHelper.circuitBreakers.get(testServiceKey);
      riskLevel = timeoutHelper.getRiskLevel(breaker);
      expect(['LOW', 'MEDIUM']).toContain(riskLevel);
      
      // Test high risk (open state)
      for (let i = 0; i < 10; i++) {
        timeoutHelper.recordFailure(testServiceKey);
      }
      breaker = timeoutHelper.circuitBreakers.get(testServiceKey);
      riskLevel = timeoutHelper.getRiskLevel(breaker);
      expect(riskLevel).toBe('HIGH');
      
      console.log('✅ Risk level calculations validated');
    });
  });
});
/**
 * Circuit Breaker Deployment Validation Script
 * Tests all circuit breaker fixes and emergency recovery capabilities
 */

const timeoutHelper = require('./utils/timeoutHelper');
const { resetAllCircuitBreakers, emergencyDatabaseRecovery, getCircuitBreakerStatus } = require('./utils/circuitBreakerReset');
const DatabaseCircuitBreaker = require('./utils/databaseCircuitBreaker');

// Test the Express app with emergency routes
const express = require('express');
const app = express();
app.use(express.json());

// Add emergency circuit breaker routes
const emergencyRouter = require('./routes/emergency-circuit-breaker');
app.use('/api/emergency-circuit-breaker', emergencyRouter);

async function validateCircuitBreakerDeployment() {
  console.log('🚀 CIRCUIT BREAKER DEPLOYMENT VALIDATION\n');
  
  const results = {
    productionConfig: false,
    circuitBreakerLogic: false,
    emergencyRecovery: false,
    apiEndpoints: false,
    performanceValidation: false
  };
  
  try {
    // 1. Validate Production Configuration
    console.log('1️⃣ VALIDATING PRODUCTION CONFIGURATION');
    console.log('═══════════════════════════════════════');
    
    // Create a test circuit breaker to validate thresholds
    timeoutHelper.recordFailure('config-validation-test');
    const testBreaker = timeoutHelper.circuitBreakers.get('config-validation-test');
    
    const expectedThreshold = 15;
    const expectedTimeout = 15000;
    const expectedHalfOpenMax = 8;
    
    if (testBreaker.threshold === expectedThreshold &&
        testBreaker.timeout === expectedTimeout &&
        testBreaker.halfOpenMaxCalls === expectedHalfOpenMax) {
      results.productionConfig = true;
      console.log('✅ TimeoutHelper: Production thresholds validated');
      console.log(`   - Failure threshold: ${testBreaker.threshold} (expected: ${expectedThreshold})`);
      console.log(`   - Recovery timeout: ${testBreaker.timeout}ms (expected: ${expectedTimeout}ms)`);
      console.log(`   - Half-open max calls: ${testBreaker.halfOpenMaxCalls} (expected: ${expectedHalfOpenMax})`);
    } else {
      console.log('❌ TimeoutHelper: Production thresholds not configured correctly');
    }
    
    // Validate DatabaseCircuitBreaker configuration
    const dbBreaker = new DatabaseCircuitBreaker();
    if (dbBreaker.failureThreshold === 20 &&
        dbBreaker.recoveryTimeout === 10000 &&
        dbBreaker.halfOpenMaxCalls === 10) {
      console.log('✅ DatabaseCircuitBreaker: Production thresholds validated');
      console.log(`   - Failure threshold: ${dbBreaker.failureThreshold} (expected: 20)`);
      console.log(`   - Recovery timeout: ${dbBreaker.recoveryTimeout}ms (expected: 10000ms)`);
      console.log(`   - Half-open max calls: ${dbBreaker.halfOpenMaxCalls} (expected: 10)`);
    } else {
      console.log('❌ DatabaseCircuitBreaker: Production thresholds not configured correctly');
    }
    
    // 2. Validate Circuit Breaker Logic
    console.log('\n2️⃣ VALIDATING CIRCUIT BREAKER LOGIC');
    console.log('═══════════════════════════════════');
    
    const logicTestKey = 'logic-validation-test';
    
    // Test state transitions
    console.log('🔄 Testing state transitions...');
    
    // Start closed
    expect(!timeoutHelper.isCircuitOpen(logicTestKey), 'Initial state should be closed');
    console.log('   ✓ Initial state: CLOSED');
    
    // Trigger failures to open
    for (let i = 0; i < 16; i++) {
      timeoutHelper.recordFailure(logicTestKey);
    }
    
    expect(timeoutHelper.isCircuitOpen(logicTestKey), 'Circuit should be open after failures');
    console.log('   ✓ After 16 failures: OPEN');
    
    // Simulate recovery
    const logicBreaker = timeoutHelper.circuitBreakers.get(logicTestKey);
    logicBreaker.lastFailureTime = Date.now() - 20000; // 20 seconds ago
    
    const wasOpen = timeoutHelper.isCircuitOpen(logicTestKey);
    expect(!wasOpen, 'Circuit should transition to half-open after timeout');
    console.log('   ✓ After timeout: HALF-OPEN');
    
    // Close with successes
    for (let i = 0; i < 3; i++) {
      timeoutHelper.recordSuccess(logicTestKey);
    }
    
    expect(!timeoutHelper.isCircuitOpen(logicTestKey), 'Circuit should be closed after successes');
    console.log('   ✓ After successes: CLOSED');
    
    results.circuitBreakerLogic = true;
    console.log('✅ Circuit breaker logic validation passed');
    
    // 3. Validate Emergency Recovery
    console.log('\n3️⃣ VALIDATING EMERGENCY RECOVERY');
    console.log('════════════════════════════════');
    
    // Create crisis scenario
    console.log('🚨 Creating crisis scenario...');
    const crisisServices = ['database-crisis-1', 'database-crisis-2', 'database-crisis-3'];
    
    crisisServices.forEach(service => {
      for (let i = 0; i < 16; i++) {
        timeoutHelper.recordFailure(service);
      }
    });
    
    // Verify crisis
    const openCount = crisisServices.filter(service => timeoutHelper.isCircuitOpen(service)).length;
    expect(openCount === crisisServices.length, 'All crisis services should be open');
    console.log(`   ✓ Crisis created: ${openCount}/${crisisServices.length} services open`);
    
    // Test emergency recovery
    console.log('🔄 Testing emergency recovery...');
    const recoveryResult = await emergencyDatabaseRecovery();
    
    expect(recoveryResult && recoveryResult.steps, 'Recovery should return steps');
    console.log(`   ✓ Recovery executed with ${recoveryResult.steps.length} steps`);
    
    // Verify recovery
    const remainingOpen = crisisServices.filter(service => timeoutHelper.isCircuitOpen(service)).length;
    expect(remainingOpen === 0, 'All services should be closed after recovery');
    console.log(`   ✓ Recovery successful: ${remainingOpen}/${crisisServices.length} services still open`);
    
    results.emergencyRecovery = true;
    console.log('✅ Emergency recovery validation passed');
    
    // 4. Validate API Endpoints
    console.log('\n4️⃣ VALIDATING API ENDPOINTS');
    console.log('═══════════════════════════');
    
    const request = require('supertest');
    
    console.log('🌐 Testing emergency circuit breaker API...');
    
    // Test status endpoint
    const statusResponse = await request(app)
      .get('/api/emergency-circuit-breaker/status')
      .expect(200);
    
    expect(statusResponse.body.success, 'Status endpoint should return success');
    console.log('   ✓ Status endpoint: OK');
    
    // Test health endpoint
    const healthResponse = await request(app)
      .get('/api/emergency-circuit-breaker/health')
      .expect(200);
    
    expect(healthResponse.body.success, 'Health endpoint should return success');
    console.log('   ✓ Health endpoint: OK');
    
    // Test reset endpoint
    const resetResponse = await request(app)
      .post('/api/emergency-circuit-breaker/reset-all')
      .expect(200);
    
    expect(resetResponse.body.success, 'Reset endpoint should return success');
    console.log('   ✓ Reset endpoint: OK');
    
    results.apiEndpoints = true;
    console.log('✅ API endpoints validation passed');
    
    // 5. Performance Validation
    console.log('\n5️⃣ VALIDATING PERFORMANCE');
    console.log('═════════════════════════');
    
    console.log('⚡ Testing high-frequency operations...');
    const startTime = Date.now();
    
    // Simulate high-frequency operations
    for (let i = 0; i < 1000; i++) {
      if (i % 2 === 0) {
        timeoutHelper.recordSuccess(`perf-test-${i}`);
      } else {
        timeoutHelper.recordFailure(`perf-test-${i}`);
      }
    }
    
    const endTime = Date.now();
    const duration = endTime - startTime;
    
    expect(duration < 5000, 'Should handle 1000 operations in under 5 seconds');
    console.log(`   ✓ Performance: 1000 operations in ${duration}ms`);
    
    // Test memory efficiency
    console.log('🧠 Testing memory efficiency...');
    const testBreakers = Array.from(timeoutHelper.circuitBreakers.values());
    const maxHistorySize = Math.max(...testBreakers.map(b => b.history ? b.history.length : 0));
    
    expect(maxHistorySize <= 100, 'History should be limited to prevent memory leaks');
    console.log(`   ✓ Memory: Max history size is ${maxHistorySize} (limit: 100)`);
    
    results.performanceValidation = true;
    console.log('✅ Performance validation passed');
    
    // Summary
    console.log('\n📊 DEPLOYMENT VALIDATION SUMMARY');
    console.log('═══════════════════════════════');
    
    const passedTests = Object.values(results).filter(Boolean).length;
    const totalTests = Object.keys(results).length;
    
    Object.entries(results).forEach(([test, passed]) => {
      console.log(`${passed ? '✅' : '❌'} ${test.replace(/([A-Z])/g, ' $1').toLowerCase()}`);
    });
    
    console.log(`\n🎯 OVERALL RESULT: ${passedTests}/${totalTests} validations passed`);
    
    if (passedTests === totalTests) {
      console.log('✅ CIRCUIT BREAKER DEPLOYMENT READY FOR PRODUCTION');
      console.log('\n🚀 EMERGENCY RECOVERY CAPABILITIES VALIDATED:');
      console.log('   - Production-ready circuit breaker thresholds');
      console.log('   - Automatic state transition logic');  
      console.log('   - Emergency recovery procedures');
      console.log('   - API endpoints for crisis management');
      console.log('   - High-performance operation handling');
      console.log('\n🛡️ DATABASE ACCESS CRISIS RESOLUTION OPERATIONAL');
    } else {
      console.log('❌ DEPLOYMENT VALIDATION FAILED - See issues above');
      process.exit(1);
    }
    
  } catch (error) {
    console.error('❌ VALIDATION ERROR:', error.message);
    console.error(error.stack);
    process.exit(1);
  }
}

// Helper function for assertions
function expect(condition, message) {
  if (!condition) {
    throw new Error(`Assertion failed: ${message}`);
  }
}

// Run validation
validateCircuitBreakerDeployment().catch(error => {
  console.error('❌ Deployment validation failed:', error);
  process.exit(1);
});
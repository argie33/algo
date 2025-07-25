#!/usr/bin/env node

/**
 * Test circuit breaker integration in health endpoints
 */

// Mock environment for testing
process.env.NODE_ENV = 'test';
process.env.ALLOW_DEV_BYPASS = 'true';

console.log('🧪 Testing circuit breaker integration in health endpoints...');

async function testHealthEndpoints() {
  try {
    const express = require('express');
    const http = require('http');
    
    // Import the health router
    const healthRouter = require('./routes/health');
    
    // Create test app
    const app = express();
    app.use('/api/health', healthRouter);
    
    // Test endpoints
    const endpoints = [
      { path: '/api/health/quick', name: 'Quick Health' },
      { path: '/api/health/circuit-breakers', name: 'Circuit Breaker Status' },
      { path: '/api/health/connection', name: 'Connection Health' }
    ];
    
    const results = [];
    
    for (const endpoint of endpoints) {
      console.log(`\n📡 Testing ${endpoint.name}: ${endpoint.path}`);
      
      try {
        const server = http.createServer(app);
        const port = 3334;
        
        const response = await new Promise((resolve, reject) => {
          server.listen(port, () => {
            const options = {
              hostname: 'localhost',
              port: port,
              path: endpoint.path,
              method: 'GET'
            };
            
            const req = http.request(options, (res) => {
              let data = '';
              res.on('data', (chunk) => { data += chunk; });
              res.on('end', () => {
                server.close(() => {
                  try {
                    resolve({
                      status: res.statusCode,
                      body: JSON.parse(data)
                    });
                  } catch (parseError) {
                    reject(new Error(`JSON parse error: ${parseError.message}`));
                  }
                });
              });
            });
            
            req.on('error', (error) => {
              server.close(() => reject(error));
            });
            
            req.end();
          });
        });
        
        console.log(`   Status: ${response.status}`);
        console.log(`   Response keys: ${Object.keys(response.body).join(', ')}`);
        
        // Validate endpoint-specific requirements
        let valid = false;
        let notes = [];
        
        if (endpoint.path.includes('/quick')) {
          valid = response.status === 200 && response.body.healthy === true;
          notes.push('Quick endpoint should always return 200 OK');
        } else if (endpoint.path.includes('/circuit-breakers')) {
          valid = response.status === 200 && response.body.database && response.body.overall;
          notes.push('Should expose circuit breaker state');
        } else if (endpoint.path.includes('/connection')) {
          // Connection endpoint might return 503 due to database connection failure OR circuit breaker
          valid = (response.status === 200 && response.body.success === true) ||
                  (response.status === 503 && (
                    response.body.status === 'circuit_breaker_open' ||
                    response.body.status === 'disconnected'
                  ));
          notes.push('Should handle circuit breaker protection and database failures gracefully');
        }
        
        results.push({
          endpoint: endpoint.name,
          path: endpoint.path,
          status: response.status,
          valid,
          notes,
          hasCircuitBreakerInfo: !!response.body.circuitBreaker
        });
        
        console.log(`   Valid: ${valid ? '✅' : '❌'}`);
        if (response.body.circuitBreaker) {
          console.log(`   Circuit Breaker State: ${response.body.circuitBreaker.state}`);
        }
        
      } catch (error) {
        console.log(`   Error: ❌ ${error.message}`);
        results.push({
          endpoint: endpoint.name,
          path: endpoint.path,
          status: 'ERROR',
          valid: false,
          notes: [error.message],
          hasCircuitBreakerInfo: false
        });
      }
    }
    
    // Summary
    console.log('\n📋 Test Summary:');
    console.log('='.repeat(50));
    
    const passedTests = results.filter(r => r.valid).length;
    const totalTests = results.length;
    
    results.forEach(result => {
      console.log(`${result.valid ? '✅' : '❌'} ${result.endpoint}`);
      console.log(`   ${result.path} → ${result.status}`);
      result.notes.forEach(note => console.log(`   📝 ${note}`));
      if (result.hasCircuitBreakerInfo) {
        console.log(`   🔴 Circuit breaker info included`);
      }
    });
    
    console.log(`\nOverall: ${passedTests}/${totalTests} tests passed`);
    
    // Check for critical fixes
    const hasQuickEndpoint = results.some(r => r.path.includes('/quick') && r.valid);
    const hasCircuitBreakerEndpoint = results.some(r => r.path.includes('/circuit-breakers') && r.valid);
    const connectionHasProtection = results.some(r => r.path.includes('/connection') && (r.hasCircuitBreakerInfo || r.valid));
    
    console.log('\n🔧 Critical Fixes Status:');
    console.log(`   Quick health endpoint: ${hasQuickEndpoint ? '✅ FIXED' : '❌ MISSING'}`);
    console.log(`   Circuit breaker status: ${hasCircuitBreakerEndpoint ? '✅ FIXED' : '❌ MISSING'}`);
    console.log(`   Connection protection: ${connectionHasProtection ? '✅ FIXED' : '❌ MISSING'}`);
    
    const allCriticalFixed = hasQuickEndpoint && hasCircuitBreakerEndpoint;
    
    return {
      success: passedTests === totalTests && allCriticalFixed,
      passedTests,
      totalTests,
      criticalFixesApplied: allCriticalFixed,
      message: allCriticalFixed ? 
        'All critical circuit breaker fixes applied successfully' : 
        'Some critical fixes still needed'
    };
    
  } catch (error) {
    console.error('❌ Test failed:', error.message);
    return { success: false, message: error.message };
  }
}

// Run test
testHealthEndpoints()
  .then(result => {
    console.log('\n🎯 Final Result:');
    console.log(`Status: ${result.success ? '✅ ALL TESTS PASSED' : '❌ SOME TESTS FAILED'}`);
    console.log(`Message: ${result.message}`);
    
    if (result.criticalFixesApplied) {
      console.log('\n🚀 Ready to deploy - circuit breaker reload loop fixes applied!');
    } else {
      console.log('\n⚠️ Additional fixes needed before deployment');
    }
    
    process.exit(result.success ? 0 : 1);
  })
  .catch(error => {
    console.error('💥 Test runner failed:', error);
    process.exit(1);
  });
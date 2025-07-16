#!/usr/bin/env node

/**
 * Simple Database Connection Test
 * Tests the SSL configuration fix and circuit breaker recovery
 */

const https = require('https');

const BASE_URL = 'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev';

async function testEndpoint(path, name) {
  return new Promise((resolve, reject) => {
    const startTime = Date.now();
    const url = `${BASE_URL}${path}`;
    
    console.log(`Testing ${name}...`);
    
    const req = https.get(url, (res) => {
      let data = '';
      
      res.on('data', (chunk) => {
        data += chunk;
      });
      
      res.on('end', () => {
        const duration = Date.now() - startTime;
        
        try {
          const jsonData = JSON.parse(data);
          resolve({
            name,
            url,
            status: res.statusCode,
            duration,
            data: jsonData
          });
        } catch (parseError) {
          resolve({
            name,
            url,
            status: res.statusCode,
            duration,
            data: data,
            parseError: parseError.message
          });
        }
      });
    });
    
    req.on('error', (error) => {
      reject({
        name,
        url,
        error: error.message,
        duration: Date.now() - startTime
      });
    });
    
    req.setTimeout(15000, () => {
      req.destroy();
      reject({
        name,
        url,
        error: 'Request timeout (15s)',
        duration: Date.now() - startTime
      });
    });
  });
}

async function runTests() {
  console.log('🔧 Database Connection Test After SSL Fix');
  console.log('==========================================');
  
  const tests = [
    { path: '/api/health-full?quick=true', name: 'Quick Health Check' },
    { path: '/api/diagnostics/secrets-manager', name: 'Secrets Manager Test' },
    { path: '/api/market', name: 'Market Root' },
    { path: '/api/health-full', name: 'Full Health Check' }
  ];
  
  for (const test of tests) {
    try {
      const result = await testEndpoint(test.path, test.name);
      
      console.log(`✅ ${result.name}: ${result.status} (${result.duration}ms)`);
      
      if (result.data && typeof result.data === 'object') {
        // Check for database status
        if (result.data.database) {
          if (result.data.database.status === 'connected') {
            console.log('   🔌 Database: CONNECTED');
          } else {
            console.log('   ❌ Database: NOT CONNECTED');
          }
        }
        
        // Check for circuit breaker
        if (result.data.error && result.data.error.includes('Circuit breaker')) {
          console.log('   ⚠️ Circuit breaker: ACTIVE');
        }
        
        // Check for SSL/timeout issues
        if (result.data.error && result.data.error.includes('timeout')) {
          console.log('   ⏱️ Timeout: DETECTED');
        }
      }
      
    } catch (error) {
      console.log(`❌ ${error.name}: ${error.error} (${error.duration}ms)`);
    }
    
    console.log('');
  }
  
  console.log('Next: Wait for circuit breaker recovery and ECS tasks to complete');
}

runTests().catch(console.error);
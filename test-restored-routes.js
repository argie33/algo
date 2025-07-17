#!/usr/bin/env node

/**
 * Test Script for Restored Routes
 * Tests all restored routes (stocks, screener, websocket) for functionality
 */

const https = require('https');

const API_BASE = 'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev';

// Test endpoints to verify route restoration (using /api/ prefix)
const testEndpoints = [
  // Health checks first
  { path: '/health', method: 'GET', description: 'Main API health check' },
  { path: '/api/websocket/health', method: 'GET', description: 'WebSocket route health check' },
  
  // Public stock endpoints (no auth required)
  { path: '/api/stocks/sectors', method: 'GET', description: 'Stock sectors endpoint (public)' },
  
  // Core stock endpoints (require auth)
  { path: '/api/stocks', method: 'GET', description: 'Stock listing endpoint (requires auth)', expectAuth: true },
  { path: '/api/stocks/AAPL', method: 'GET', description: 'Individual stock data (requires auth)', expectAuth: true },
  
  // Screening endpoints (require auth)
  { path: '/api/screener', method: 'GET', description: 'Stock screening endpoint (requires auth)', expectAuth: true },
  
  // WebSocket/Live data endpoints
  { path: '/api/websocket/status', method: 'GET', description: 'Live data service status' },
];

async function makeRequest(endpoint) {
  return new Promise((resolve) => {
    const url = `${API_BASE}${endpoint.path}`;
    const startTime = Date.now();
    
    console.log(`🔍 Testing: ${endpoint.method} ${endpoint.path} - ${endpoint.description}`);
    
    const req = https.request(url, { method: endpoint.method }, (res) => {
      const duration = Date.now() - startTime;
      let data = '';
      
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          const parsed = JSON.parse(data);
          
          const isAuthError = res.statusCode === 401;
          const expectsAuth = endpoint.expectAuth === true;
          const actualSuccess = res.statusCode >= 200 && res.statusCode < 300;
          const authSuccess = expectsAuth && isAuthError; // Auth-required endpoint correctly requiring auth
          
          const result = {
            endpoint: endpoint.path,
            description: endpoint.description,
            status: res.statusCode,
            duration: duration,
            success: actualSuccess || authSuccess,
            hasData: !!parsed.data || !!parsed.response,
            responseSize: data.length,
            error: res.statusCode >= 400 ? parsed.error || parsed.message : null,
            authRequired: expectsAuth,
            authWorking: isAuthError && expectsAuth
          };
          
          if (result.success) {
            if (authSuccess) {
              console.log(`✅ ${endpoint.path}: ${res.statusCode} (${duration}ms) - Auth Required (Correct)`);
            } else {
              console.log(`✅ ${endpoint.path}: ${res.statusCode} (${duration}ms) - ${result.hasData ? 'Has Data' : 'No Data'}`);
            }
          } else {
            console.log(`❌ ${endpoint.path}: ${res.statusCode} (${duration}ms) - ${result.error || 'Error'}`);
          }
          
          resolve(result);
        } catch (parseError) {
          console.log(`⚠️  ${endpoint.path}: ${res.statusCode} (${duration}ms) - Invalid JSON response`);
          resolve({
            endpoint: endpoint.path,
            description: endpoint.description,
            status: res.statusCode,
            duration: duration,
            success: false,
            error: 'Invalid JSON response',
            rawResponse: data.slice(0, 200)
          });
        }
      });
    });
    
    req.on('error', (error) => {
      const duration = Date.now() - startTime;
      console.log(`❌ ${endpoint.path}: Network Error (${duration}ms) - ${error.message}`);
      resolve({
        endpoint: endpoint.path,
        description: endpoint.description,
        status: 0,
        duration: duration,
        success: false,
        error: error.message
      });
    });
    
    req.setTimeout(10000, () => {
      req.destroy();
      const duration = Date.now() - startTime;
      console.log(`⏰ ${endpoint.path}: Timeout (${duration}ms)`);
      resolve({
        endpoint: endpoint.path,
        description: endpoint.description,
        status: 0,
        duration: duration,
        success: false,
        error: 'Request timeout'
      });
    });
    
    req.end();
  });
}

async function runTests() {
  console.log('🚀 Starting Route Restoration Test Suite');
  console.log('==========================================');
  console.log(`Testing API: ${API_BASE}`);
  console.log(`Test Time: ${new Date().toISOString()}`);
  console.log('');
  
  const results = [];
  
  for (const endpoint of testEndpoints) {
    const result = await makeRequest(endpoint);
    results.push(result);
    
    // Wait between requests to avoid rate limiting
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  
  console.log('');
  console.log('📊 TEST RESULTS SUMMARY');
  console.log('=======================');
  
  const successful = results.filter(r => r.success);
  const failed = results.filter(r => !r.success);
  const avgDuration = results.reduce((sum, r) => sum + r.duration, 0) / results.length;
  
  console.log(`✅ Successful: ${successful.length}/${results.length} (${Math.round(successful.length/results.length*100)}%)`);
  console.log(`❌ Failed: ${failed.length}/${results.length}`);
  console.log(`⏱️  Average Response Time: ${Math.round(avgDuration)}ms`);
  console.log('');
  
  if (failed.length > 0) {
    console.log('❌ FAILED ENDPOINTS:');
    failed.forEach(result => {
      console.log(`   ${result.endpoint}: ${result.error}`);
    });
    console.log('');
  }
  
  // Categorize results by route
  const routeResults = {
    health: results.filter(r => r.endpoint.includes('health')),
    stocks: results.filter(r => r.endpoint.startsWith('/stocks') && !r.endpoint.includes('health')),
    screener: results.filter(r => r.endpoint.startsWith('/screener') && !r.endpoint.includes('health')),
    websocket: results.filter(r => r.endpoint.startsWith('/websocket') && !r.endpoint.includes('health'))
  };
  
  console.log('📋 ROUTE STATUS BREAKDOWN:');
  for (const [routeName, routeResults] of Object.entries(routeResults)) {
    const routeSuccess = routeResults.filter(r => r.success).length;
    const routeTotal = routeResults.length;
    const status = routeSuccess === routeTotal ? '✅' : routeSuccess > 0 ? '⚠️' : '❌';
    console.log(`   ${status} ${routeName.toUpperCase()}: ${routeSuccess}/${routeTotal} endpoints working`);
  }
  
  console.log('');
  
  // Overall assessment
  const healthChecksPassing = routeResults.health.filter(r => r.success).length;
  const totalHealthChecks = routeResults.health.length;
  
  if (healthChecksPassing === totalHealthChecks && successful.length >= results.length * 0.8) {
    console.log('🎉 ROUTE RESTORATION SUCCESS! All critical endpoints are working.');
  } else if (healthChecksPassing === totalHealthChecks) {
    console.log('✅ Health checks passing, but some advanced endpoints may need attention.');
  } else {
    console.log('⚠️  Route restoration may need additional troubleshooting.');
  }
  
  console.log('');
  console.log('📝 Next Steps:');
  console.log('   1. Check deployment logs if any health checks are failing');
  console.log('   2. Test authenticated endpoints with valid JWT tokens');
  console.log('   3. Verify database connectivity and API key integration');
  console.log('   4. Monitor performance and optimize slow endpoints');
  
  return {
    summary: {
      total: results.length,
      successful: successful.length,
      failed: failed.length,
      successRate: Math.round(successful.length/results.length*100),
      avgDuration: Math.round(avgDuration)
    },
    results: results,
    routeBreakdown: Object.fromEntries(
      Object.entries(routeResults).map(([route, results]) => [
        route, 
        {
          total: results.length,
          successful: results.filter(r => r.success).length
        }
      ])
    )
  };
}

// Run tests if called directly
if (require.main === module) {
  runTests().catch(console.error);
}

module.exports = { runTests, testEndpoints, API_BASE };
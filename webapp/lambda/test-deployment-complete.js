#!/usr/bin/env node
/**
 * Comprehensive Deployment Completion Test
 * Tests all aspects of the system when deployment should be complete
 */

const https = require('https');

// Import our other test modules
const { runCompleteTest } = require('./test-env-vars-working');
const { runEndpointTests } = require('./test-deployment-monitor');

const API_URL = process.env.LAMBDA_API_URL || 'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev';

// Comprehensive test suite
const COMPREHENSIVE_TESTS = [
  {
    name: 'Lambda Basic Health',
    path: '/',
    validator: (data) => data.success && data.message && !data.message.includes('EMERGENCY')
  },
  {
    name: 'Development Health',
    path: '/dev-health',
    validator: (data) => data.dev_status === 'OPERATIONAL' && data.route_loading?.all_routes_loaded
  },
  {
    name: 'API Health',
    path: '/api/health',
    validator: (data) => data.success && data.database?.status === 'connected'
  },
  {
    name: 'Full Health Check',
    path: '/api/health-full',
    validator: (data) => data.success && data.database?.status === 'connected'
  },
  {
    name: 'Stock Sectors',
    path: '/api/stocks/sectors',
    validator: (data) => data.success && Array.isArray(data.data)
  },
  {
    name: 'API Keys Management',
    path: '/api/settings/api-keys',
    validator: (data) => data.success && Array.isArray(data.data)
  },
  {
    name: 'Market Overview',
    path: '/api/market-overview',
    validator: (data) => data.success && data.data
  },
  {
    name: 'Portfolio Holdings',
    path: '/api/portfolio/holdings',
    validator: (data) => data.success
  },
  {
    name: 'Live Data Metrics',
    path: '/api/live-data/metrics',
    validator: (data) => data.success && data.data
  },
  {
    name: 'WebSocket Connection',
    path: '/api/websocket/status',
    validator: (data) => data.success
  }
];

async function makeRequest(url) {
  return new Promise((resolve) => {
    const req = https.get(url, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          resolve({
            statusCode: res.statusCode,
            data: JSON.parse(data)
          });
        } catch (e) {
          resolve({
            statusCode: res.statusCode,
            data: data,
            parseError: true
          });
        }
      });
    });
    
    req.on('error', (err) => {
      resolve({ error: err.message });
    });
    
    req.setTimeout(15000);
    req.end();
  });
}

async function runComprehensiveTests() {
  console.log('🚀 Comprehensive Deployment Completion Test');
  console.log('='.repeat(70));
  console.log(`📡 Testing API: ${API_URL}`);
  console.log(`🕐 Started: ${new Date().toISOString()}`);
  
  const results = {
    timestamp: new Date().toISOString(),
    apiUrl: API_URL,
    tests: [],
    summary: {
      total: 0,
      passed: 0,
      failed: 0,
      errors: 0
    }
  };
  
  // Run individual tests
  console.log('\n📋 Running Individual Endpoint Tests');
  console.log('-'.repeat(70));
  
  for (const test of COMPREHENSIVE_TESTS) {
    const url = `${API_URL}${test.path}`;
    console.log(`\n🧪 Testing: ${test.name}`);
    console.log(`   📡 ${test.path}`);
    
    const response = await makeRequest(url);
    
    let testResult = {
      name: test.name,
      path: test.path,
      statusCode: response.statusCode,
      success: false,
      error: null,
      details: {}
    };
    
    if (response.error) {
      testResult.error = response.error;
      console.log(`   ❌ Connection Error: ${response.error}`);
    } else if (response.parseError) {
      testResult.error = 'Invalid JSON response';
      console.log(`   ❌ Parse Error: Invalid JSON`);
    } else if (response.statusCode >= 200 && response.statusCode < 300) {
      // Test passed basic HTTP check, now validate content
      try {
        const isValid = test.validator(response.data);
        testResult.success = isValid;
        testResult.details = {
          validatorPassed: isValid,
          responseData: response.data
        };
        
        console.log(`   ${isValid ? '✅' : '❌'} Status: ${response.statusCode} - ${isValid ? 'PASS' : 'FAIL'}`);
        
        // Show key details
        if (response.data) {
          if (response.data.success !== undefined) {
            console.log(`   📊 Response Success: ${response.data.success}`);
          }
          if (response.data.message) {
            console.log(`   💬 Message: ${response.data.message.substring(0, 100)}${response.data.message.length > 100 ? '...' : ''}`);
          }
          if (response.data.database?.status) {
            console.log(`   🗄️ Database: ${response.data.database.status}`);
          }
          if (response.data.data && Array.isArray(response.data.data)) {
            console.log(`   📊 Data Count: ${response.data.data.length} items`);
          }
        }
        
      } catch (validatorError) {
        testResult.error = `Validator error: ${validatorError.message}`;
        console.log(`   ❌ Validator Error: ${validatorError.message}`);
      }
    } else {
      testResult.error = `HTTP ${response.statusCode}`;
      console.log(`   ❌ HTTP Error: ${response.statusCode}`);
    }
    
    results.tests.push(testResult);
    
    // Update summary
    results.summary.total++;
    if (testResult.success) {
      results.summary.passed++;
    } else if (testResult.error) {
      results.summary.errors++;
    } else {
      results.summary.failed++;
    }
  }
  
  // System integration assessment
  console.log('\n' + '='.repeat(70));
  console.log('🔍 System Integration Assessment');
  console.log('='.repeat(70));
  
  const criticalTests = ['Lambda Basic Health', 'Development Health', 'API Health'];
  const criticalPassed = results.tests
    .filter(t => criticalTests.includes(t.name))
    .every(t => t.success);
  
  const databaseTests = ['API Health', 'Full Health Check', 'Stock Sectors'];
  const databaseWorking = results.tests
    .filter(t => databaseTests.includes(t.name))
    .every(t => t.success);
  
  const apiTests = ['API Keys Management', 'Portfolio Holdings', 'Live Data Metrics'];
  const apisWorking = results.tests
    .filter(t => apiTests.includes(t.name))
    .some(t => t.success);
  
  console.log(`🏗️ Core Infrastructure: ${criticalPassed ? '✅ Working' : '❌ Issues'}`);
  console.log(`🗄️ Database Integration: ${databaseWorking ? '✅ Working' : '❌ Issues'}`);
  console.log(`📡 API Endpoints: ${apisWorking ? '✅ Some Working' : '❌ Not Working'}`);
  
  // Overall deployment status
  console.log('\n' + '='.repeat(70));
  console.log('📊 Final Deployment Status');
  console.log('='.repeat(70));
  
  const passRate = (results.summary.passed / results.summary.total) * 100;
  console.log(`📈 Pass Rate: ${passRate.toFixed(1)}% (${results.summary.passed}/${results.summary.total})`);
  console.log(`✅ Passed: ${results.summary.passed}`);
  console.log(`❌ Failed: ${results.summary.failed}`);
  console.log(`💥 Errors: ${results.summary.errors}`);
  
  let deploymentStatus = 'UNKNOWN';
  let deploymentMessage = '';
  
  if (passRate >= 90) {
    deploymentStatus = 'SUCCESS';
    deploymentMessage = '🎉 Deployment fully successful! System is operational.';
  } else if (passRate >= 70) {
    deploymentStatus = 'PARTIAL';
    deploymentMessage = '⚠️ Deployment partially successful. Some components working.';
  } else if (passRate >= 30) {
    deploymentStatus = 'IN_PROGRESS';
    deploymentMessage = '⏳ Deployment in progress. Core components starting to work.';
  } else {
    deploymentStatus = 'FAILED';
    deploymentMessage = '❌ Deployment appears to have issues. Most components not working.';
  }
  
  console.log(`\n🎯 Deployment Status: ${deploymentStatus}`);
  console.log(deploymentMessage);
  
  // Recommendations
  if (deploymentStatus !== 'SUCCESS') {
    console.log('\n🔧 Recommendations:');
    
    if (!criticalPassed) {
      console.log('   • Check main app stack deployment (CloudFormation)');
      console.log('   • Verify environment variables are properly set');
    }
    
    if (!databaseWorking) {
      console.log('   • Check database connectivity and secrets');
      console.log('   • Verify RDS instance is running and accessible');
    }
    
    if (!apisWorking) {
      console.log('   • Check individual API endpoint logs');
      console.log('   • Verify route loading and middleware');
    }
    
    console.log('   • Run deployment monitor to track progress');
    console.log('   • Check GitHub Actions workflow status');
  }
  
  results.deploymentStatus = deploymentStatus;
  results.passRate = passRate;
  
  return results;
}

// Run if called directly
if (require.main === module) {
  runComprehensiveTests().catch(console.error);
}

module.exports = { runComprehensiveTests };
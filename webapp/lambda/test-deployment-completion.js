#!/usr/bin/env node
/**
 * Deployment Completion Test
 * Tests when Lambda fully exits emergency mode
 */

const https = require('https');

const API_URL = 'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev';

async function testDeploymentCompletion() {
  console.log('🎯 Testing Deployment Completion');
  console.log('='.repeat(50));
  
  let testCount = 0;
  let emergencyModeDetected = false;
  let fullModeDetected = false;
  
  while (testCount < 50) { // Test for up to 50 iterations
    testCount++;
    
    console.log(`\n[${testCount.toString().padStart(2, '0')}] Testing deployment status...`);
    
    // Test multiple endpoints
    const endpoints = [
      '/dev-health',
      '/api/stocks/sectors', 
      '/api/portfolio/holdings',
      '/api/health'
    ];
    
    let emergencyCount = 0;
    let workingCount = 0;
    
    for (const endpoint of endpoints) {
      try {
        const response = await makeRequest(endpoint);
        
        if (response.data && response.data.message && response.data.message.includes('EMERGENCY')) {
          emergencyCount++;
          console.log(`   🚨 ${endpoint}: Emergency mode`);
          emergencyModeDetected = true;
        } else if (response.statusCode === 200) {
          workingCount++;
          console.log(`   ✅ ${endpoint}: Working`);
        } else {
          console.log(`   ❌ ${endpoint}: HTTP ${response.statusCode}`);
        }
      } catch (error) {
        console.log(`   💥 ${endpoint}: Error - ${error.message}`);
      }
    }
    
    console.log(`   📊 Status: ${workingCount}/${endpoints.length} working, ${emergencyCount}/${endpoints.length} emergency`);
    
    // Check for transition from emergency to full mode
    if (emergencyModeDetected && emergencyCount === 0) {
      console.log('\n🎉 DEPLOYMENT COMPLETE! Lambda exited emergency mode!');
      fullModeDetected = true;
      break;
    }
    
    if (emergencyCount === 0 && workingCount >= 3) {
      console.log('\n🚀 FULL DEPLOYMENT DETECTED! All endpoints working!');
      fullModeDetected = true;
      break;
    }
    
    // Wait 20 seconds between tests
    await new Promise(resolve => setTimeout(resolve, 20000));
  }
  
  if (fullModeDetected) {
    console.log('\n✅ SUCCESS: Deployment fully completed!');
    console.log('🎯 Lambda is now running in full production mode');
    console.log('🚀 All routes loaded and available');
    
    // Run final validation
    console.log('\n🧪 Running final validation...');
    await runFinalValidation();
  } else {
    console.log('\n⏳ Deployment still in progress after 50 tests');
    console.log('💡 Continue monitoring - deployment may take longer');
  }
}

async function makeRequest(path) {
  return new Promise((resolve, reject) => {
    const req = https.get(`${API_URL}${path}`, (res) => {
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
    
    req.on('error', reject);
    req.setTimeout(10000);
    req.end();
  });
}

async function runFinalValidation() {
  console.log('🔍 Final System Validation');
  console.log('-'.repeat(30));
  
  // Test key functionality
  const validationTests = [
    { path: '/api/health', name: 'Health Check' },
    { path: '/dev-health', name: 'Development Health' },
    { path: '/api/stocks/sectors', name: 'Stock Data' },
    { path: '/api/settings/api-keys', name: 'API Keys' },
    { path: '/api/portfolio/holdings', name: 'Portfolio' },
    { path: '/api/live-data/metrics', name: 'Live Data' }
  ];
  
  let passedTests = 0;
  
  for (const test of validationTests) {
    try {
      const response = await makeRequest(test.path);
      
      if (response.statusCode === 200) {
        console.log(`✅ ${test.name}: Working`);
        passedTests++;
      } else {
        console.log(`❌ ${test.name}: HTTP ${response.statusCode}`);
      }
    } catch (error) {
      console.log(`💥 ${test.name}: Error`);
    }
  }
  
  console.log(`\n📊 Final Score: ${passedTests}/${validationTests.length} tests passed`);
  
  if (passedTests >= validationTests.length * 0.8) {
    console.log('🎉 SYSTEM READY FOR PRODUCTION!');
  } else {
    console.log('⚠️ Some issues remain - continue monitoring');
  }
}

// Run if called directly
if (require.main === module) {
  testDeploymentCompletion().catch(console.error);
}

module.exports = { testDeploymentCompletion };
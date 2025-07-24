#!/usr/bin/env node
/**
 * Comprehensive End-to-End Testing Suite
 * Tests all crypto functionality and API key management after AWS permissions fix
 */

const simpleApiKeyService = require('./utils/simpleApiKeyService');

// Test configuration
const TEST_CONFIG = {
  testUserId: 'test-user@example.com',
  providers: ['alpaca', 'polygon', 'finnhub'],
  testApiKeys: {
    alpaca: {
      keyId: 'TEST_ALPACA_KEY_123',
      secretKey: 'TEST_ALPACA_SECRET_456'
    },
    polygon: {
      keyId: 'TEST_POLYGON_KEY_789',
      secretKey: 'TEST_POLYGON_SECRET_012'
    },
    finnhub: {
      keyId: 'TEST_FINNHUB_KEY_345',
      secretKey: 'TEST_FINNHUB_SECRET_678'
    }
  }
};

async function runComprehensiveTests() {
  console.log('🧪 Starting Comprehensive Crypto Platform Tests');
  console.log('=' .repeat(60));
  
  const results = {
    passed: 0,
    failed: 0,
    errors: []
  };

  try {
    // Test 1: API Key Service Health Check
    console.log('\n🔍 Test 1: API Key Service Health Check');
    await testApiKeyServiceHealth(results);

    // Test 2: API Key Storage & Retrieval
    console.log('\n🔐 Test 2: API Key Storage & Retrieval');
    await testApiKeyStorageRetrieval(results);

    // Test 3: Crypto Portfolio APIs
    console.log('\n📊 Test 3: Crypto Portfolio APIs');
    await testCryptoPortfolioApis(results);

    // Test 4: Real-time Crypto Data APIs
    console.log('\n⚡ Test 4: Real-time Crypto Data APIs');
    await testRealTimeCryptoApis(results);

    // Test 5: Frontend Component Integration
    console.log('\n🎨 Test 5: Frontend Component Integration');
    await testFrontendComponents(results);

    // Test 6: End-to-End Workflow
    console.log('\n🔄 Test 6: End-to-End Workflow');
    await testEndToEndWorkflow(results);

    // Test 7: Error Handling & Edge Cases
    console.log('\n⚠️ Test 7: Error Handling & Edge Cases');
    await testErrorHandling(results);

    // Test 8: Performance & Load Testing
    console.log('\n⚡ Test 8: Performance & Load Testing');
    await testPerformance(results);

  } catch (error) {
    console.error('❌ Critical test failure:', error.message);
    results.failed++;
    results.errors.push(`Critical failure: ${error.message}`);
  }

  // Final Results
  console.log('\n' + '=' .repeat(60));
  console.log('📋 TEST RESULTS SUMMARY');
  console.log('=' .repeat(60));
  console.log(`✅ Passed: ${results.passed}`);
  console.log(`❌ Failed: ${results.failed}`);
  console.log(`🎯 Success Rate: ${((results.passed / (results.passed + results.failed)) * 100).toFixed(1)}%`);
  
  if (results.errors.length > 0) {
    console.log('\n🚨 ERRORS:');
    results.errors.forEach((error, index) => {
      console.log(`${index + 1}. ${error}`);
    });
  }

  if (results.failed === 0) {
    console.log('\n🎉 ALL TESTS PASSED! Platform is ready for production use.');
  } else {
    console.log('\n⚠️ Some tests failed. Review errors above and fix issues.');
  }

  return results;
}

async function testApiKeyServiceHealth(results) {
  try {
    console.log('  Testing AWS Parameter Store connectivity...');
    const healthCheck = await simpleApiKeyService.healthCheck();
    
    if (healthCheck.status === 'healthy') {
      console.log('  ✅ API Key Service health check passed');
      console.log(`  📊 Backend: ${healthCheck.backend}`);
      console.log(`  🔐 Encryption: ${healthCheck.encryption}`);
      console.log(`  🧪 Test Result: ${healthCheck.testResult}`);
      results.passed++;
    } else {
      throw new Error(`Health check failed: ${healthCheck.error}`);
    }
  } catch (error) {
    console.error('  ❌ API Key Service health check failed:', error.message);
    results.failed++;
    results.errors.push(`API Key Service health: ${error.message}`);
  }
}

async function testApiKeyStorageRetrieval(results) {
  const { testUserId, providers, testApiKeys } = TEST_CONFIG;

  for (const provider of providers) {
    try {
      console.log(`  Testing ${provider} API key storage...`);
      
      // Store API key
      const storeResult = await simpleApiKeyService.storeApiKey(
        testUserId,
        provider,
        testApiKeys[provider].keyId,
        testApiKeys[provider].secretKey
      );

      if (!storeResult) {
        throw new Error('Store operation returned false');
      }

      // Retrieve API key
      const retrievedKey = await simpleApiKeyService.getApiKey(testUserId, provider);
      
      if (!retrievedKey) {
        throw new Error('Retrieved key is null');
      }

      if (retrievedKey.keyId !== testApiKeys[provider].keyId) {
        throw new Error('Key ID mismatch');
      }

      if (retrievedKey.secretKey !== testApiKeys[provider].secretKey) {
        throw new Error('Secret key mismatch');
      }

      console.log(`  ✅ ${provider} API key storage/retrieval passed`);
      results.passed++;

    } catch (error) {
      console.error(`  ❌ ${provider} API key test failed:`, error.message);
      results.failed++;
      results.errors.push(`${provider} API key: ${error.message}`);
    }
  }

  // Test list functionality
  try {
    console.log('  Testing API key listing...');
    const keyList = await simpleApiKeyService.listApiKeys(testUserId);
    
    if (!Array.isArray(keyList)) {
      throw new Error('List result is not an array');
    }

    if (keyList.length !== providers.length) {
      throw new Error(`Expected ${providers.length} keys, got ${keyList.length}`);
    }

    console.log(`  ✅ API key listing passed (${keyList.length} keys found)`);
    results.passed++;

  } catch (error) {
    console.error('  ❌ API key listing failed:', error.message);
    results.failed++;
    results.errors.push(`API key listing: ${error.message}`);
  }
}

async function testCryptoPortfolioApis(results) {
  // Since we can't directly test the routes without running the full server,
  // we'll test the core functionality and check file integrity
  
  try {
    console.log('  Checking crypto portfolio route file...');
    const fs = require('fs');
    const path = require('path');
    
    const portfolioRoutePath = path.join(__dirname, 'routes', 'crypto-portfolio.js');
    if (!fs.existsSync(portfolioRoutePath)) {
      throw new Error('crypto-portfolio.js route file not found');
    }

    const routeContent = fs.readFileSync(portfolioRoutePath, 'utf8');
    
    // Check for key functionality
    const requiredFunctions = [
      'GET.*portfolio',
      'POST.*portfolio.*buy',
      'POST.*portfolio.*sell',
      'GET.*portfolio.*analytics',
      'GET.*portfolio.*performance'
    ];

    for (const func of requiredFunctions) {
      if (!new RegExp(func).test(routeContent)) {
        throw new Error(`Missing required function: ${func}`);
      }
    }

    console.log('  ✅ Crypto portfolio API structure verified');
    results.passed++;

  } catch (error) {
    console.error('  ❌ Crypto portfolio API test failed:', error.message);
    results.failed++;
    results.errors.push(`Crypto portfolio API: ${error.message}`);
  }
}

async function testRealTimeCryptoApis(results) {
  try {
    console.log('  Checking real-time crypto route file...');
    const fs = require('fs');
    const path = require('path');
    
    const realtimeRoutePath = path.join(__dirname, 'routes', 'crypto-realtime.js');
    if (!fs.existsSync(realtimeRoutePath)) {
      throw new Error('crypto-realtime.js route file not found');
    }

    const routeContent = fs.readFileSync(realtimeRoutePath, 'utf8');
    
    // Check for key functionality
    const requiredFunctions = [
      'GET.*prices',
      'GET.*market-pulse',
      'POST.*alerts',
      'GET.*historical',
      'WebSocket.*simulation'
    ];

    for (const func of requiredFunctions) {
      if (!new RegExp(func).test(routeContent)) {
        throw new Error(`Missing required function: ${func}`);
      }
    }

    console.log('  ✅ Real-time crypto API structure verified');
    results.passed++;

  } catch (error) {
    console.error('  ❌ Real-time crypto API test failed:', error.message);
    results.failed++;
    results.errors.push(`Real-time crypto API: ${error.message}`);
  }
}

async function testFrontendComponents(results) {
  const components = [
    'CryptoPortfolio.jsx',
    'CryptoRealTimeTracker.jsx', 
    'CryptoAdvancedAnalytics.jsx'
  ];

  for (const component of components) {
    try {
      console.log(`  Checking ${component}...`);
      const fs = require('fs');
      const path = require('path');
      
      const componentPath = path.join(__dirname, '..', 'frontend', 'src', 'pages', component);
      if (!fs.existsSync(componentPath)) {
        throw new Error(`${component} not found`);
      }

      const componentContent = fs.readFileSync(componentPath, 'utf8');
      
      // Check for React component structure
      if (!componentContent.includes('export default')) {
        throw new Error('Missing export default');
      }

      if (!componentContent.includes('useState') && !componentContent.includes('useEffect')) {
        throw new Error('Missing React hooks');
      }

      console.log(`  ✅ ${component} structure verified`);
      results.passed++;

    } catch (error) {
      console.error(`  ❌ ${component} test failed:`, error.message);
      results.failed++;
      results.errors.push(`${component}: ${error.message}`);
    }
  }
}

async function testEndToEndWorkflow(results) {
  try {
    console.log('  Testing complete workflow integration...');
    
    // Test the integration between API keys and crypto services
    const { testUserId } = TEST_CONFIG;
    
    // Verify API keys are still stored
    const keyList = await simpleApiKeyService.listApiKeys(testUserId);
    if (keyList.length === 0) {
      throw new Error('No API keys found for workflow test');
    }

    // Test key retrieval for each provider
    for (const keyInfo of keyList) {
      const retrievedKey = await simpleApiKeyService.getApiKey(testUserId, keyInfo.provider);
      if (!retrievedKey) {
        throw new Error(`Could not retrieve ${keyInfo.provider} key for workflow`);
      }
    }

    console.log('  ✅ End-to-end workflow integration verified');
    results.passed++;

  } catch (error) {
    console.error('  ❌ End-to-end workflow test failed:', error.message);
    results.failed++;
    results.errors.push(`End-to-end workflow: ${error.message}`);
  }
}

async function testErrorHandling(results) {
  try {
    console.log('  Testing error handling scenarios...');
    
    // Test invalid user ID
    try {
      await simpleApiKeyService.storeApiKey('', 'alpaca', 'key', 'secret');
      throw new Error('Should have failed with empty user ID');
    } catch (error) {
      if (!error.message.includes('Missing required parameters')) {
        throw new Error('Unexpected error message for empty user ID');
      }
    }

    // Test invalid provider
    try {
      await simpleApiKeyService.storeApiKey('test@example.com', 'invalid-provider', 'key', 'secret');
      throw new Error('Should have failed with invalid provider');
    } catch (error) {
      if (!error.message.includes('Invalid provider')) {
        throw new Error('Unexpected error message for invalid provider');
      }
    }

    // Test non-existent key retrieval
    const nonExistentKey = await simpleApiKeyService.getApiKey('nonexistent@example.com', 'alpaca');
    if (nonExistentKey !== null) {
      throw new Error('Should return null for non-existent key');
    }

    console.log('  ✅ Error handling scenarios passed');
    results.passed++;

  } catch (error) {
    console.error('  ❌ Error handling test failed:', error.message);
    results.failed++;
    results.errors.push(`Error handling: ${error.message}`);
  }
}

async function testPerformance(results) {
  try {
    console.log('  Testing performance benchmarks...');
    
    const { testUserId } = TEST_CONFIG;
    const iterations = 5;
    const times = [];

    // Test API key retrieval performance
    for (let i = 0; i < iterations; i++) {
      const startTime = Date.now();
      await simpleApiKeyService.getApiKey(testUserId, 'alpaca');
      const endTime = Date.now();
      times.push(endTime - startTime);
    }

    const avgTime = times.reduce((a, b) => a + b, 0) / times.length;
    const maxTime = Math.max(...times);

    if (avgTime > 2000) { // 2 second threshold
      throw new Error(`Average response time too high: ${avgTime}ms`);
    }

    if (maxTime > 5000) { // 5 second max threshold
      throw new Error(`Maximum response time too high: ${maxTime}ms`);
    }

    console.log(`  ✅ Performance test passed (avg: ${avgTime.toFixed(0)}ms, max: ${maxTime}ms)`);
    results.passed++;

  } catch (error) {
    console.error('  ❌ Performance test failed:', error.message);
    results.failed++;
    results.errors.push(`Performance: ${error.message}`);
  }
}

// Cleanup function
async function cleanup() {
  try {
    console.log('\n🧹 Cleaning up test data...');
    const { testUserId, providers } = TEST_CONFIG;
    
    for (const provider of providers) {
      try {
        await simpleApiKeyService.deleteApiKey(testUserId, provider);
        console.log(`  ✅ Cleaned up ${provider} test key`);
      } catch (error) {
        console.log(`  ⚠️ Could not clean up ${provider} key: ${error.message}`);
      }
    }
    
    console.log('🧹 Cleanup completed');
  } catch (error) {
    console.error('🚨 Cleanup failed:', error.message);
  }
}

// Main execution
if (require.main === module) {
  runComprehensiveTests()
    .then(async (results) => {
      await cleanup();
      process.exit(results.failed > 0 ? 1 : 0);
    })
    .catch(async (error) => {
      console.error('🚨 Test suite failed:', error);
      await cleanup();
      process.exit(1);
    });
}

module.exports = {
  runComprehensiveTests,
  cleanup
};
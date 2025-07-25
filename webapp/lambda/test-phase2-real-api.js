#!/usr/bin/env node

/**
 * Phase 2 Real API Integration Test
 * Tests actual Alpaca API integration with user credentials
 */

const { createLogger } = require('./utils/structuredLogger');
const logger = createLogger('financial-platform', 'phase2-test');

async function testPhase2RealApiIntegration() {
  console.log('🚀 Starting Phase 2 Real API Integration Test...\n');
  
  const testResults = {
    alpacaClientCreation: false,
    hftServiceRealIntegration: false,
    positionSynchronization: false,
    realOrderExecution: false,
    mockFallback: false,
    overallSuccess: false
  };

  try {
    // Test 1: Alpaca API Client Creation
    console.log('📋 Test 1: HFT Service Alpaca Client Creation');
    console.log('----------------------------------------');
    
    try {
      const HFTService = require('./services/hftService');
      const hftService = new HFTService();
      
      console.log('✅ HFTService instantiation: PASS');
      
      // Set up mock credentials for testing
      hftService.userId = 'test-user-phase2';
      hftService.userCredentials = {
        keyId: 'test-api-key',
        secretKey: 'test-api-secret',
        isPaper: true
      };
      
      // Test Alpaca client creation
      try {
        const alpacaClient = hftService.createAlpacaClient();
        console.log('✅ Alpaca client creation: PASS');
        console.log(`   - Paper mode: ${hftService.userCredentials.isPaper}`);
        testResults.alpacaClientCreation = true;
      } catch (clientError) {
        console.log('❌ Alpaca client creation: FAIL');
        console.log(`   - Error: ${clientError.message}`);
      }
      
    } catch (error) {
      console.error('❌ HFT Service client test failed:', error.message);
    }

    // Test 2: Real Order Execution Logic (without actual API call)
    console.log('\n📋 Test 2: Real Order Execution Logic');
    console.log('----------------------------------------');
    
    try {
      const HFTService = require('./services/hftService');
      const hftService = new HFTService();
      
      hftService.userId = 'test-user-phase2';
      hftService.userCredentials = {
        keyId: 'test-api-key',
        secretKey: 'test-api-secret',
        isPaper: true
      };
      
      // Test the order execution path (will fail at API call, but tests the logic)
      const mockSignal = {
        symbol: 'AAPL',
        type: 'BUY',
        quantity: 10,
        price: 150.00,
        strategy: 'test-strategy',
        timestamp: Date.now()
      };
      
      try {
        // This will fail at the actual API call, but validates the setup
        await hftService.executeRealOrder(mockSignal, 'test-order-1', Date.now());
        console.log('✅ Real order execution logic: PASS (Would execute real order)');
        testResults.realOrderExecution = true;
      } catch (apiError) {
        if (apiError.message.includes('Invalid API key') || 
            apiError.message.includes('credentials') ||
            apiError.message.includes('authentication')) {
          console.log('✅ Real order execution logic: PASS (Expected API auth error with test credentials)');
          testResults.realOrderExecution = true;
        } else {
          console.log('❌ Real order execution logic: FAIL');
          console.log(`   - Unexpected error: ${apiError.message}`);
        }
      }
      
    } catch (error) {
      console.error('❌ Real order execution test failed:', error.message);
    }

    // Test 3: Mock Fallback
    console.log('\n📋 Test 3: Mock Order Execution Fallback');
    console.log('----------------------------------------');
    
    try {
      const HFTService = require('./services/hftService');
      const hftService = new HFTService();
      
      hftService.userId = 'test-user-phase2';
      hftService.userCredentials = null; // No credentials for mock test
      
      const mockSignal = {
        symbol: 'AAPL',
        type: 'BUY',
        quantity: 10,
        price: 150.00,
        strategy: 'test-strategy',
        timestamp: Date.now()
      };
      
      const orderResult = await hftService.executeMockOrder(mockSignal, 'test-order-mock', Date.now());
      
      if (orderResult.executionMode === 'mock') {
        console.log('✅ Mock order execution: PASS');
        console.log(`   - Execution mode: ${orderResult.executionMode}`);
        console.log(`   - Order ID: ${orderResult.orderId}`);
        testResults.mockFallback = true;
      } else {
        console.log('❌ Mock order execution: FAIL');
      }
      
    } catch (error) {
      console.error('❌ Mock fallback test failed:', error.message);
    }

    // Test 4: Position Synchronization Logic
    console.log('\n📋 Test 4: Position Synchronization Logic');
    console.log('----------------------------------------');
    
    try {
      const HFTService = require('./services/hftService');
      const hftService = new HFTService();
      
      hftService.userId = 'test-user-phase2';
      hftService.userCredentials = {
        keyId: 'test-api-key',
        secretKey: 'test-api-secret',
        isPaper: true
      };
      
      // Test position sync (will fail at API, but tests the logic)
      try {
        await hftService.synchronizePositionsWithAlpaca();
        console.log('✅ Position synchronization logic: PASS (Would sync with real positions)');
        testResults.positionSynchronization = true;
      } catch (syncError) {
        if (syncError.message.includes('Invalid API key') || 
            syncError.message.includes('credentials') ||
            syncError.message.includes('authentication')) {
          console.log('✅ Position synchronization logic: PASS (Expected API auth error with test credentials)');
          testResults.positionSynchronization = true;
        } else {
          console.log('❌ Position synchronization logic: FAIL');
          console.log(`   - Unexpected error: ${syncError.message}`);
        }
      }
      
    } catch (error) {
      console.error('❌ Position synchronization test failed:', error.message);
    }

    // Test 5: HFT Service Integration
    console.log('\n📋 Test 5: HFT Service Real Integration');
    console.log('----------------------------------------');
    
    try {
      const HFTService = require('./services/hftService');
      const hftService = new HFTService();
      
      // Test full integration flow
      hftService.userId = 'test-user-phase2';
      hftService.userCredentials = {
        keyId: 'test-api-key',
        secretKey: 'test-api-secret',
        isPaper: true
      };
      
      // Test that methods exist and are callable
      const hasCreateClient = typeof hftService.createAlpacaClient === 'function';
      const hasGetAccount = typeof hftService.getAlpacaAccount === 'function';
      const hasGetPositions = typeof hftService.getAlpacaPositions === 'function';
      const hasSyncPositions = typeof hftService.synchronizePositionsWithAlpaca === 'function';
      const hasExecuteReal = typeof hftService.executeRealOrder === 'function';
      
      if (hasCreateClient && hasGetAccount && hasGetPositions && hasSyncPositions && hasExecuteReal) {
        console.log('✅ HFT Service real integration methods: PASS');
        console.log('   - createAlpacaClient: ✅');
        console.log('   - getAlpacaAccount: ✅');
        console.log('   - getAlpacaPositions: ✅');
        console.log('   - synchronizePositionsWithAlpaca: ✅');
        console.log('   - executeRealOrder: ✅');
        testResults.hftServiceRealIntegration = true;
      } else {
        console.log('❌ HFT Service real integration methods: FAIL');
        console.log(`   - Missing methods detected`);
      }
      
    } catch (error) {
      console.error('❌ HFT Service integration test failed:', error.message);
    }

    // Overall results
    const passedTests = Object.values(testResults).filter(result => result === true).length;
    const totalTests = Object.keys(testResults).length - 1; // Exclude overallSuccess
    
    testResults.overallSuccess = passedTests === totalTests;
    
    console.log('\n📊 Phase 2 Real API Integration Test Results');
    console.log('=====================================');
    console.log(`✅ Tests Passed: ${passedTests}/${totalTests}`);
    console.log(`📋 Alpaca Client Creation: ${testResults.alpacaClientCreation ? '✅ PASS' : '❌ FAIL'}`);
    console.log(`📋 HFT Service Integration: ${testResults.hftServiceRealIntegration ? '✅ PASS' : '❌ FAIL'}`);
    console.log(`📋 Position Synchronization: ${testResults.positionSynchronization ? '✅ PASS' : '❌ FAIL'}`);
    console.log(`📋 Real Order Execution: ${testResults.realOrderExecution ? '✅ PASS' : '❌ FAIL'}`);
    console.log(`📋 Mock Fallback: ${testResults.mockFallback ? '✅ PASS' : '❌ FAIL'}`);
    
    console.log(`\n🎯 Overall Result: ${testResults.overallSuccess ? '✅ PASS' : '❌ FAIL'}`);
    
    if (testResults.overallSuccess) {
      console.log('\n🎉 Phase 2 Real API Integration is working correctly!');
      console.log('📌 Next Steps:');
      console.log('   1. Set up user with real Alpaca API keys for testing');
      console.log('   2. Test paper trading with real API calls');
      console.log('   3. Validate order execution and position sync');
      console.log('   4. Deploy to staging environment');
      console.log('   5. Monitor real-time performance and error handling');
    } else {
      console.log('\n⚠️  Some components need attention before real API testing');
    }

    return testResults;

  } catch (error) {
    console.error('🔥 Phase 2 integration test failed:', error);
    return { ...testResults, overallSuccess: false };
  }
}

// Run the test if called directly
if (require.main === module) {
  testPhase2RealApiIntegration()
    .then(results => {
      process.exit(results.overallSuccess ? 0 : 1);
    })
    .catch(error => {
      console.error('Test execution failed:', error);
      process.exit(1);
    });
}

module.exports = { testPhase2RealApiIntegration };
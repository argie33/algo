#!/usr/bin/env node

/**
 * Simple test for /api/stocks/popular endpoint
 */

// Mock environment for testing
process.env.NODE_ENV = 'test';
process.env.ALLOW_DEV_BYPASS = 'true';

console.log('🧪 Testing /api/stocks/popular endpoint...');

async function testPopular() {
  try {
    // Import and test the route directly
    const stocksRouter = require('./routes/stocks');
    
    // Create mock request and response objects
    const mockReq = {
      query: { limit: '5' },
      method: 'GET',
      path: '/popular'
    };
    
    const mockRes = {
      statusCode: 200,
      responseData: null,
      json: function(data) {
        this.responseData = data;
        console.log('📊 Response received:', JSON.stringify(data, null, 2));
      },
      status: function(code) {
        this.statusCode = code;
        return this;
      }
    };
    
    // Find the popular route handler
    const routes = stocksRouter.stack;
    const popularRoute = routes.find(layer => 
      layer.route && layer.route.path === '/popular' && layer.route.methods.get
    );
    
    if (!popularRoute) {
      throw new Error('Popular route not found');
    }
    
    console.log('📡 Executing popular route handler...');
    
    // Execute the route handler
    await popularRoute.route.stack[0].handle(mockReq, mockRes);
    
    // Validate response
    if (mockRes.statusCode === 200 && mockRes.responseData) {
      const data = mockRes.responseData;
      
      console.log('✅ Response status: 200 OK');
      console.log(`✅ Data source: ${data.source}`);
      console.log(`✅ Stock count: ${data.count}`);
      
      if (data.success && Array.isArray(data.data) && data.data.length > 0) {
        console.log('✅ Response structure is valid');
        console.log('📈 Sample stocks:');
        data.data.slice(0, 3).forEach((stock, i) => {
          console.log(`   ${i + 1}. ${stock.symbol} - ${stock.companyName} (${stock.sector})`);
        });
        return { success: true, message: 'Test passed' };
      } else {
        return { success: false, message: 'Invalid response structure' };
      }
    } else {
      return { success: false, message: `HTTP ${mockRes.statusCode} error` };
    }
    
  } catch (error) {
    console.error('❌ Test failed:', error.message);
    return { success: false, message: error.message };
  }
}

// Run test
testPopular()
  .then(result => {
    console.log('\n📋 Test Summary:');
    console.log(`Status: ${result.success ? '✅ PASSED' : '❌ FAILED'}`);
    console.log(`Message: ${result.message}`);
    process.exit(result.success ? 0 : 1);
  })
  .catch(error => {
    console.error('💥 Test runner failed:', error);
    process.exit(1);
  });
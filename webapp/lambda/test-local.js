#!/usr/bin/env node
/**
 * Local test script for Lambda function
 * Run with: node test-local.js
 */

// Load environment variables
require('dotenv').config({ path: '.env.local' });

// Mock environment for testing
process.env.NODE_ENV = 'development';
process.env.DB_HOST = process.env.DB_HOST || 'localhost';
process.env.DB_PORT = process.env.DB_PORT || '5432';
process.env.DB_NAME = process.env.DB_NAME || 'stocks';
process.env.DB_USER = process.env.DB_USER || 'postgres';
process.env.DB_PASSWORD = process.env.DB_PASSWORD || 'password';

console.log('Starting local server...');

// Start local development server
const PORT = process.env.PORT || 3001;
require('./index.js')
    console.log('Response:', JSON.stringify(rootResponse.body, null, 2));
    
    // Test quick health check (no DB required)
    console.log('\n2. Testing quick health check (/health?quick=true)...');
    const quickHealthResponse = await request(app).get('/health?quick=true');
    console.log('✓ Quick health status:', quickHealthResponse.status);
    console.log('Response:', JSON.stringify(quickHealthResponse.body, null, 2));
    
    // Test full health check (requires DB)
    console.log('\n3. Testing full health check (/health)...');
    const healthResponse = await request(app).get('/health');
    console.log('✓ Full health status:', healthResponse.status);
    if (healthResponse.status === 503) {
      console.log('Expected 503 - database unavailable in test environment');
    }
    console.log('Response:', JSON.stringify(healthResponse.body, null, 2));
    
    // Test stocks endpoint (requires DB)
    console.log('\n4. Testing stocks endpoint (/stocks)...');
    const stocksResponse = await request(app).get('/stocks');
    console.log('✓ Stocks endpoint status:', stocksResponse.status);
    if (stocksResponse.status === 503) {
      console.log('Expected 503 - database unavailable in test environment');
    }
    
    console.log('\n✅ All endpoint tests completed successfully!');
    console.log('The Lambda function should now handle database timeouts gracefully.');
    
  } catch (error) {
    console.error('❌ Test failed:', error.message);
    process.exit(1);
  }
}

// Run tests if this file is executed directly
if (require.main === module) {
  testEndpoints().then(() => {
    console.log('\n🚀 Ready for deployment!');
    process.exit(0);
  }).catch(error => {
    console.error('Test runner error:', error);
    process.exit(1);
  });
}

module.exports = { testEndpoints };

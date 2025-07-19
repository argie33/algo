/**
 * Local functionality test for financial platform
 * Tests core API routes without mocks
 */

const express = require('express');
const app = require('./index');

// Test port
const PORT = 3001;

// Start server for testing
const server = app.listen(PORT, () => {
  console.log(`🚀 Local test server running on port ${PORT}`);
  
  // Test core endpoints
  testCoreEndpoints();
});

async function testCoreEndpoints() {
  const baseUrl = `http://localhost:${PORT}`;
  
  console.log('\n📊 Testing Core API Endpoints...\n');
  
  const tests = [
    {
      name: 'Health Check',
      url: `${baseUrl}/health`,
      method: 'GET'
    },
    {
      name: 'API Configuration',
      url: `${baseUrl}/api/config`,
      method: 'GET'
    },
    {
      name: 'Market Data (without auth)',
      url: `${baseUrl}/api/market/overview`,
      method: 'GET'
    }
  ];
  
  for (const test of tests) {
    try {
      console.log(`Testing: ${test.name}`);
      
      const fetch = (await import('node-fetch')).default;
      const response = await fetch(test.url, {
        method: test.method,
        headers: {
          'Content-Type': 'application/json'
        }
      });
      
      const statusCode = response.status;
      const isSuccess = statusCode >= 200 && statusCode < 300;
      
      console.log(`  Status: ${statusCode} ${isSuccess ? '✅' : '❌'}`);
      
      if (response.headers.get('content-type')?.includes('application/json')) {
        const data = await response.json();
        console.log(`  Response: ${JSON.stringify(data, null, 2).substring(0, 200)}...`);
      }
      
    } catch (error) {
      console.log(`  Error: ${error.message} ❌`);
    }
    
    console.log('');
  }
  
  // Gracefully shutdown
  setTimeout(() => {
    console.log('🔄 Shutting down test server...');
    server.close(() => {
      console.log('✅ Test completed');
      process.exit(0);
    });
  }, 1000);
}

// Handle process termination
process.on('SIGINT', () => {
  console.log('\n🔄 Shutting down test server...');
  server.close(() => {
    process.exit(0);
  });
});
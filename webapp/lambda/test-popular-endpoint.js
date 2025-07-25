#!/usr/bin/env node

/**
 * Test script for /api/stocks/popular endpoint
 * Tests both fallback data and potential database connectivity
 */

const express = require('express');
const http = require('http');

// Mock environment for testing
process.env.NODE_ENV = 'test';
process.env.ALLOW_DEV_BYPASS = 'true';

console.log('🧪 Testing /api/stocks/popular endpoint...');

async function testPopularEndpoint() {
  try {
    // Import the stocks router
    const stocksRouter = require('./routes/stocks');
    
    // Create test app
    const app = express();
    app.use('/api/stocks', stocksRouter);
    
    console.log('📡 Testing GET /api/stocks/popular...');
    
    // Create server
    const server = http.createServer(app);
    const port = 3333;
    
    return new Promise((resolve, reject) => {
      server.listen(port, () => {
        console.log(`🚀 Test server running on port ${port}`);
        
        // Make HTTP request
        const options = {
          hostname: 'localhost',
          port: port,
          path: '/api/stocks/popular?limit=5',
          method: 'GET'
        };
        
        const req = http.request(options, (res) => {
          let data = '';
          
          res.on('data', (chunk) => {
            data += chunk;
          });
          
          res.on('end', () => {
            server.close(() => {
              try {
                const response = {
                  status: res.statusCode,
                  body: JSON.parse(data)
                };
                resolve(response);
              } catch (parseError) {
                reject(new Error(`JSON parse error: ${parseError.message}`));
              }
            });
          });
        });
        
        req.on('error', (error) => {
          server.close(() => {
            reject(error);
          });
        });
        
        req.end();
      });
    }).then(response => {
      console.log('📊 Response Status:', response.status);
      console.log('📊 Response Body:', JSON.stringify(response.body, null, 2));
      
      // Validate response structure
      if (response.status === 200) {
      const body = response.body;
      
      // Check required fields
      const requiredFields = ['success', 'data', 'count', 'source', 'timestamp'];
      const missingFields = requiredFields.filter(field => !(field in body));
      
      if (missingFields.length === 0) {
        console.log('✅ Response structure is valid');
        
        // Check data format
        if (Array.isArray(body.data) && body.data.length > 0) {
          const firstStock = body.data[0];
          const requiredStockFields = ['symbol', 'companyName', 'sector', 'exchange'];
          const missingStockFields = requiredStockFields.filter(field => !(field in firstStock));
          
          if (missingStockFields.length === 0) {
            console.log('✅ Stock data structure is valid');
            console.log(`📈 Found ${body.data.length} popular stocks`);
            console.log(`📊 Data source: ${body.source}`);
            
            // Show sample stock data
            console.log('📋 Sample stock data:');
            body.data.slice(0, 3).forEach((stock, index) => {
              console.log(`   ${index + 1}. ${stock.symbol} - ${stock.companyName} (${stock.sector})`);
            });
            
            return { success: true, message: 'Popular endpoint test passed' };
          } else {
            console.log('❌ Missing stock fields:', missingStockFields);
            return { success: false, message: 'Stock data structure invalid' };
          }
        } else {
          console.log('❌ Data array is empty or invalid');
          return { success: false, message: 'Empty or invalid data array' };
        }
      } else {
        console.log('❌ Missing response fields:', missingFields);
        return { success: false, message: 'Response structure invalid' };
      }
    } else {
      console.log('❌ HTTP Error:', response.status);
      console.log('❌ Error details:', response.body);
      return { success: false, message: `HTTP ${response.status} error` };
    }
    
  } catch (error) {
    console.error('❌ Test failed with error:', error.message);
    console.error('❌ Stack trace:', error.stack);
    return { success: false, message: error.message };
  }
}

// Run the test
testPopularEndpoint()
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
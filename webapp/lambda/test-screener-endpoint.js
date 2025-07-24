#!/usr/bin/env node

/**
 * Test Screener Endpoint
 * Directly tests the /api/stocks/screen endpoint
 */

const express = require('express');
const path = require('path');

// Set up environment
require('dotenv').config();

const app = express();
app.use(express.json());

// Import and mount the stocks route
try {
  const stocksRoute = require('./routes/stocks');
  app.use('/api/stocks', stocksRoute);
  console.log('✅ Stocks route loaded successfully');
} catch (error) {
  console.error('❌ Failed to load stocks route:', error.message);
  process.exit(1);
}

async function testScreenerEndpoint() {
  console.log('🧪 Testing screener endpoint...\n');
  
  const server = app.listen(3002, () => {
    console.log('✅ Test server running on http://localhost:3002');
  });
  
  try {
    // Test different scenarios
    const testCases = [
      {
        name: 'Basic screening (no filters)',
        url: 'http://localhost:3002/api/stocks/screen'
      },
      {
        name: 'Technology sector filter', 
        url: 'http://localhost:3002/api/stocks/screen?sector=Technology'
      },
      {
        name: 'Price range filter',
        url: 'http://localhost:3002/api/stocks/screen?priceMin=100&priceMax=1000'
      },
      {
        name: 'Market cap filter',
        url: 'http://localhost:3002/api/stocks/screen?marketCapMin=500000000000'
      },
      {
        name: 'Search filter',
        url: 'http://localhost:3002/api/stocks/screen?search=Apple'
      },
      {
        name: 'Pagination test',
        url: 'http://localhost:3002/api/stocks/screen?page=1&limit=5'
      }
    ];
    
    console.log('📡 Running test cases:\n');
    
    for (const testCase of testCases) {
      try {
        console.log(`🔍 Testing: ${testCase.name}`);
        console.log(`   URL: ${testCase.url}`);
        
        const response = await fetch(testCase.url);
        const data = await response.json();
        
        if (response.ok && data.success) {
          const itemCount = data.data ? data.data.length : 0;
          const total = data.pagination ? data.pagination.total : data.total || 0;
          const dataSource = data.metadata?.data_source || 'unknown';
          
          console.log(`   ✅ ${response.status} - ${itemCount} items (${total} total) - Source: ${dataSource}`);
          
          // Show first item structure for debugging
          if (data.data && data.data[0]) {
            const firstItem = data.data[0];
            console.log(`   📊 Sample: ${firstItem.symbol} - ${firstItem.company_name} ($${firstItem.price})`);
          }
        } else {
          console.log(`   ❌ ${response.status} - ${data.error || 'Failed'}`);
        }
        console.log('');
      } catch (error) {
        console.log(`   ❌ Request failed: ${error.message}\n`);
      }
    }
    
    console.log('🎉 Screener endpoint testing completed!');
    console.log('\n💡 If tests show "data_source: sample_data_store", the frontend will receive rich sample data');
    console.log('💡 If tests show database errors, run: ./setup-local-dev-database.sh');
    
  } finally {
    server.close();
  }
}

if (require.main === module) {
  testScreenerEndpoint().catch(console.error);
}

module.exports = { testScreenerEndpoint };
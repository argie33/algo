
/**
 * Fix Financial Schema Via API
 * This script calls the API server to run the schema fix using its existing database connection
 */

const axios = require('axios');

async function testFinancialEndpoint() {
  try {
    console.log('🧪 Testing financial endpoint before fix...');
    const response = await axios.get('http://localhost:3001/api/financials/statements?symbol=AAPL');

    if (response.data.meta && response.data.meta.source === 'mock_data') {
      console.log('❌ Financial endpoint is returning mock data - database schema issue confirmed');
      return false;
    } else {
      console.log('✅ Financial endpoint is working with real data');
      return true;
    }
  } catch (error) {
    console.log('❌ Financial endpoint failed:', error.message);
    return false;
  }
}

async function fixSchemaViaAPI() {
  try {
    console.log('🔧 Attempting to fix financial schema via API...');

    // First check if the financial endpoint is working
    const isWorking = await testFinancialEndpoint();
    if (isWorking) {
      console.log('✅ Financial endpoints already working correctly!');
      return;
    }

    // Since we can't directly modify the schema via the API,
    // let's at least trigger the database connection to see what's happening
    console.log('📊 Checking backend logs for more details...');

    // Call multiple endpoints to trigger the database errors in the logs
    const endpoints = [
      '/api/financials/statements?symbol=AAPL',
      '/api/stocks/AAPL/financials',
    ];

    for (const endpoint of endpoints) {
      try {
        const response = await axios.get(`http://localhost:3001${endpoint}`);
        console.log(`✅ ${endpoint} - Status: ${response.status}`);
        if (response.data.meta && response.data.meta.source === 'mock_data') {
          console.log(`   ⚠️  Using mock data - indicates database schema issue`);
        }
      } catch (error) {
        console.log(`❌ ${endpoint} - Error: ${error.message}`);
      }
    }

    console.log('\n📝 The financial database schema needs to be fixed manually.');
    console.log('   Check the backend logs (stderr) for database error details.');
    console.log('   The tables exist but have wrong column names:');
    console.log('   - Need: symbol, date, item_name, value');
    console.log('   - Current schema is using different column names');

  } catch (error) {
    console.error('❌ Error:', error.message);
  }
}

// Run the fix
fixSchemaViaAPI();
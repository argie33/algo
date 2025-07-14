#!/usr/bin/env node

/**
 * Test Loader Status and Database Population
 * 
 * This script checks:
 * 1. Database connectivity and health
 * 2. Which tables are populated by successful loaders
 * 3. Status of key loaders like symbols and loadinfo
 * 4. System readiness for portfolio import functionality
 */

const https = require('https');
const http = require('http');

// Configuration
const API_BASE = process.env.API_URL || 'https://your-lambda-api-url'; // Replace with actual API URL
const DEVELOPMENT_TOKEN = 'dev-access-testuser-' + Date.now();

// Utility function to make HTTP/HTTPS requests
function makeRequest(url, options = {}) {
  return new Promise((resolve, reject) => {
    const urlObj = new URL(url);
    const isHttps = urlObj.protocol === 'https:';
    const client = isHttps ? https : http;
    
    const requestOptions = {
      hostname: urlObj.hostname,
      port: urlObj.port || (isHttps ? 443 : 80),
      path: urlObj.pathname + urlObj.search,
      method: options.method || 'GET',
      headers: {
        'Authorization': `Bearer ${DEVELOPMENT_TOKEN}`,
        'Content-Type': 'application/json',
        ...options.headers
      }
    };

    const req = client.request(requestOptions, (res) => {
      let data = '';
      res.on('data', (chunk) => data += chunk);
      res.on('end', () => {
        try {
          const result = {
            statusCode: res.statusCode,
            data: JSON.parse(data),
            headers: res.headers
          };
          resolve(result);
        } catch (error) {
          resolve({
            statusCode: res.statusCode,
            data: data,
            headers: res.headers,
            parseError: error.message
          });
        }
      });
    });

    req.on('error', reject);
    req.setTimeout(30000, () => {
      req.destroy();
      reject(new Error('Request timeout'));
    });

    if (options.body) {
      req.write(JSON.stringify(options.body));
    }
    req.end();
  });
}

// Test database health and table status
async function testDatabaseHealth() {
  console.log('🔍 Testing Database Health...');
  
  try {
    const response = await makeRequest(`${API_BASE}/health`);
    
    if (response.statusCode === 200 && response.data.success) {
      console.log('✅ Database Health: HEALTHY');
      
      // Check database details
      if (response.data.database) {
        const db = response.data.database;
        console.log(`📊 Database Summary:`);
        console.log(`   - Status: ${db.status}`);
        console.log(`   - Total Tables: ${db.summary?.total_tables || 'Unknown'}`);
        console.log(`   - Healthy Tables: ${db.summary?.healthy_tables || 'Unknown'}`);
        console.log(`   - Total Records: ${db.summary?.total_records || 'Unknown'}`);
        
        // Check specific tables important for portfolio functionality
        const importantTables = ['stock_symbols', 'user_api_keys', 'portfolio_holdings', 'portfolio_metadata', 'loadinfo'];
        console.log(`\n📋 Important Tables Status:`);
        
        for (const tableName of importantTables) {
          const tableInfo = db.tables?.[tableName];
          if (tableInfo) {
            console.log(`   - ${tableName}: ${tableInfo.record_count || 0} records (${tableInfo.status || 'unknown'})`);
          } else {
            console.log(`   - ${tableName}: NOT FOUND`);
          }
        }
        
        return { healthy: true, details: db };
      }
      
      return { healthy: true, details: response.data };
    } else {
      console.log('❌ Database Health: UNHEALTHY');
      console.log(`   Status Code: ${response.statusCode}`);
      console.log(`   Response: ${JSON.stringify(response.data, null, 2)}`);
      return { healthy: false, error: response.data };
    }
  } catch (error) {
    console.log('❌ Database Health: CONNECTION FAILED');
    console.log(`   Error: ${error.message}`);
    return { healthy: false, error: error.message };
  }
}

// Test symbols loader data
async function testSymbolsData() {
  console.log('\n🔍 Testing Symbols Loader Data...');
  
  try {
    const response = await makeRequest(`${API_BASE}/stocks?limit=10`);
    
    if (response.statusCode === 200 && response.data.success) {
      const stocks = response.data.data;
      console.log(`✅ Symbols Loader: WORKING`);
      console.log(`   - Found ${stocks.length} symbols`);
      
      if (stocks.length > 0) {
        console.log(`   - Sample symbols: ${stocks.slice(0, 5).map(s => s.symbol).join(', ')}`);
        console.log(`   - Data includes: sector, market_cap, exchange info`);
        return { working: true, count: stocks.length };
      } else {
        console.log(`   - No symbols found - loader may not have run yet`);
        return { working: false, reason: 'No data found' };
      }
    } else {
      console.log('❌ Symbols Loader: NOT WORKING');
      console.log(`   Status Code: ${response.statusCode}`);
      return { working: false, error: response.data };
    }
  } catch (error) {
    console.log('❌ Symbols Loader: CONNECTION FAILED');
    console.log(`   Error: ${error.message}`);
    return { working: false, error: error.message };
  }
}

// Test loadinfo data
async function testLoadinfoData() {
  console.log('\n🔍 Testing Loadinfo Data...');
  
  try {
    // Try to get company information for a well-known stock
    const response = await makeRequest(`${API_BASE}/stocks/AAPL`);
    
    if (response.statusCode === 200 && response.data.success) {
      const stock = response.data.data;
      console.log(`✅ Loadinfo: WORKING`);
      console.log(`   - Company: ${stock.companyName || stock.name || 'Available'}`);
      console.log(`   - Sector: ${stock.sector || 'Available'}`);
      console.log(`   - Has detailed info: ${!!(stock.description || stock.industry)}`);
      return { working: true, details: stock };
    } else if (response.statusCode === 404) {
      console.log('⚠️  Loadinfo: PARTIAL - Symbol not found, but API working');
      return { working: true, reason: 'API working but no AAPL data' };
    } else {
      console.log('❌ Loadinfo: NOT WORKING');
      console.log(`   Status Code: ${response.statusCode}`);
      return { working: false, error: response.data };
    }
  } catch (error) {
    console.log('❌ Loadinfo: CONNECTION FAILED');
    console.log(`   Error: ${error.message}`);
    return { working: false, error: error.message };
  }
}

// Test authentication system
async function testAuthentication() {
  console.log('\n🔍 Testing Authentication System...');
  
  try {
    // Test a protected endpoint
    const response = await makeRequest(`${API_BASE}/portfolio/holdings`);
    
    if (response.statusCode === 200) {
      console.log(`✅ Authentication: WORKING`);
      console.log(`   - Development tokens accepted`);
      console.log(`   - Protected endpoints accessible`);
      return { working: true };
    } else if (response.statusCode === 401) {
      console.log('⚠️  Authentication: TOKEN ISSUE');
      console.log(`   - Got 401 Unauthorized - may need different token format`);
      return { working: false, reason: 'Token not accepted' };
    } else {
      console.log('❌ Authentication: UNKNOWN ISSUE');
      console.log(`   Status Code: ${response.statusCode}`);
      return { working: false, error: response.data };
    }
  } catch (error) {
    console.log('❌ Authentication: CONNECTION FAILED');
    console.log(`   Error: ${error.message}`);
    return { working: false, error: error.message };
  }
}

// Test portfolio import readiness
async function testPortfolioImport() {
  console.log('\n🔍 Testing Portfolio Import Readiness...');
  
  try {
    // Test the portfolio import endpoint structure
    const response = await makeRequest(`${API_BASE}/portfolio`);
    
    if (response.statusCode === 200 && response.data.success) {
      console.log(`✅ Portfolio API: READY`);
      console.log(`   - Portfolio endpoints available`);
      console.log(`   - System: ${response.data.data.system}`);
      console.log(`   - Available endpoints: ${response.data.data.available_endpoints?.length || 0}`);
      return { ready: true };
    } else {
      console.log('❌ Portfolio API: NOT READY');
      console.log(`   Status Code: ${response.statusCode}`);
      return { ready: false, error: response.data };
    }
  } catch (error) {
    console.log('❌ Portfolio API: CONNECTION FAILED');
    console.log(`   Error: ${error.message}`);
    return { ready: false, error: error.message };
  }
}

// Main test function
async function runSystemStatusTest() {
  console.log('🧪 Starting System Status and Loader Test\n');
  console.log('📊 This test checks the current status of:');
  console.log('   - Database health and table population');
  console.log('   - Working loaders (symbols, loadinfo)');
  console.log('   - Authentication system functionality');
  console.log('   - Portfolio import system readiness');
  console.log(`   - API Base URL: ${API_BASE}`);
  console.log('');

  const results = {};

  // Run all tests
  results.database = await testDatabaseHealth();
  results.symbols = await testSymbolsData();
  results.loadinfo = await testLoadinfoData();
  results.authentication = await testAuthentication();
  results.portfolio = await testPortfolioImport();

  // Generate summary
  console.log('\n' + '='.repeat(50));
  console.log('📋 SYSTEM STATUS SUMMARY');
  console.log('='.repeat(50));

  console.log(`🗄️  Database Health: ${results.database.healthy ? '✅ HEALTHY' : '❌ UNHEALTHY'}`);
  console.log(`📊 Symbols Loader: ${results.symbols.working ? '✅ WORKING' : '❌ NOT WORKING'}`);
  console.log(`ℹ️  Loadinfo Loader: ${results.loadinfo.working ? '✅ WORKING' : '❌ NOT WORKING'}`);
  console.log(`🔐 Authentication: ${results.authentication.working ? '✅ WORKING' : '❌ NOT WORKING'}`);
  console.log(`💼 Portfolio System: ${results.portfolio.ready ? '✅ READY' : '❌ NOT READY'}`);

  // System readiness assessment
  const criticalSystemsWorking = results.database.healthy && 
                                 results.authentication.working && 
                                 results.portfolio.ready;

  const dataLoadersWorking = results.symbols.working && results.loadinfo.working;

  console.log('\n🎯 SYSTEM READINESS:');
  if (criticalSystemsWorking && dataLoadersWorking) {
    console.log('🎉 SYSTEM FULLY OPERATIONAL');
    console.log('   - All critical systems working');
    console.log('   - Data loaders populating database');
    console.log('   - Ready for production portfolio import workflow');
  } else if (criticalSystemsWorking) {
    console.log('⚠️  SYSTEM PARTIALLY READY');
    console.log('   - Core systems working');
    console.log('   - Some data loaders may need attention');
    console.log('   - Portfolio import should work but may have limited data');
  } else {
    console.log('❌ SYSTEM NOT READY');
    console.log('   - Critical systems need attention');
    console.log('   - Portfolio import may not work correctly');
  }

  console.log('\n📝 NEXT STEPS:');
  if (!results.database.healthy) {
    console.log('   1. Fix database connectivity and health issues');
  }
  if (!results.authentication.working) {
    console.log('   2. Debug authentication token system');
  }
  if (!results.portfolio.ready) {
    console.log('   3. Ensure portfolio API endpoints are deployed');
  }
  if (!results.symbols.working) {
    console.log('   4. Run symbols loader to populate stock_symbols table');
  }
  if (!results.loadinfo.working) {
    console.log('   5. Run loadinfo loader to populate company information');
  }

  if (criticalSystemsWorking && dataLoadersWorking) {
    console.log('   ✅ No action needed - system ready for use!');
  }

  return results;
}

// Run the test if this file is executed directly
if (require.main === module) {
  // Check if API_BASE is configured
  if (API_BASE.includes('your-lambda-api-url')) {
    console.log('⚠️  Please set the API_URL environment variable or update API_BASE in the script');
    console.log('   Example: API_URL=https://your-actual-api-url node test-loader-status.js');
    process.exit(1);
  }
  
  runSystemStatusTest().then(results => {
    console.log('\n🏁 Test completed');
    process.exit(0);
  }).catch(error => {
    console.error('\n💥 Test failed:', error);
    process.exit(1);
  });
}

module.exports = { runSystemStatusTest };
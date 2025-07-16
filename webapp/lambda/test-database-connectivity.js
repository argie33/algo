#!/usr/bin/env node
/**
 * Database Connectivity Test
 * Tests database connection and data availability
 */

const https = require('https');

const API_URL = 'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev';

// Database-dependent endpoints to test
const DB_ENDPOINTS = [
  {
    path: '/api/health',
    name: 'Health Check',
    expectDatabase: true,
    critical: true
  },
  {
    path: '/api/health-full',
    name: 'Full Health Check',
    expectDatabase: true,
    critical: true
  },
  {
    path: '/api/stocks/sectors',
    name: 'Stock Sectors',
    expectData: true,
    critical: false
  },
  {
    path: '/api/settings/api-keys',
    name: 'API Keys',
    expectDatabase: true,
    critical: false
  },
  {
    path: '/api/portfolio/holdings',
    name: 'Portfolio Holdings',
    expectDatabase: true,
    critical: false
  }
];

async function makeRequest(path) {
  return new Promise((resolve) => {
    const url = `${API_URL}${path}`;
    
    const req = https.get(url, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          resolve({
            path,
            statusCode: res.statusCode,
            data: JSON.parse(data),
            timestamp: new Date().toISOString()
          });
        } catch (e) {
          resolve({
            path,
            statusCode: res.statusCode,
            data: data,
            parseError: true,
            timestamp: new Date().toISOString()
          });
        }
      });
    });
    
    req.on('error', (err) => {
      resolve({
        path,
        error: err.message,
        timestamp: new Date().toISOString()
      });
    });
    
    req.setTimeout(15000);
    req.end();
  });
}

async function testDatabaseConnectivity() {
  console.log('🗄️ Database Connectivity Test');
  console.log('='.repeat(50));
  console.log(`📡 Testing: ${API_URL}`);
  console.log(`🕐 Started: ${new Date().toISOString()}`);
  
  const results = {
    timestamp: new Date().toISOString(),
    endpoints: [],
    summary: {
      total: DB_ENDPOINTS.length,
      connected: 0,
      dataAvailable: 0,
      critical: 0,
      criticalWorking: 0
    }
  };
  
  for (const endpoint of DB_ENDPOINTS) {
    console.log(`\n🔍 Testing: ${endpoint.name} (${endpoint.path})`);
    
    const response = await makeRequest(endpoint.path);
    
    const result = {
      name: endpoint.name,
      path: endpoint.path,
      critical: endpoint.critical,
      expectDatabase: endpoint.expectDatabase,
      expectData: endpoint.expectData,
      response: response,
      databaseConnected: false,
      dataAvailable: false,
      working: false
    };
    
    if (endpoint.critical) {
      results.summary.critical++;
    }
    
    if (response.error) {
      console.log(`   ❌ Connection Error: ${response.error}`);
      result.error = response.error;
    } else if (response.parseError) {
      console.log(`   ❌ Parse Error: Invalid JSON response`);
      result.error = 'Invalid JSON';
    } else if (response.statusCode >= 400) {
      console.log(`   ❌ HTTP Error: ${response.statusCode}`);
      result.error = `HTTP ${response.statusCode}`;
    } else {
      console.log(`   ✅ HTTP Status: ${response.statusCode}`);
      
      // Check database connectivity
      if (endpoint.expectDatabase && response.data) {
        if (response.data.database) {
          const dbStatus = response.data.database.status || response.data.database.healthy;
          result.databaseConnected = dbStatus === 'connected' || dbStatus === true;
          
          console.log(`   🗄️ Database: ${result.databaseConnected ? '✅ Connected' : '❌ Not Connected'}`);
          
          if (response.data.database.error) {
            console.log(`      Error: ${response.data.database.error}`);
          }
          
          if (result.databaseConnected) {
            results.summary.connected++;
            if (endpoint.critical) {
              results.summary.criticalWorking++;
            }
          }
        }
      }
      
      // Check data availability
      if (endpoint.expectData && response.data) {
        if (response.data.success && response.data.data) {
          if (Array.isArray(response.data.data)) {
            result.dataAvailable = response.data.data.length > 0;
            console.log(`   📊 Data: ${result.dataAvailable ? `✅ ${response.data.data.length} items` : '❌ Empty'}`);
          } else {
            result.dataAvailable = true;
            console.log(`   📊 Data: ✅ Available`);
          }
          
          if (result.dataAvailable) {
            results.summary.dataAvailable++;
          }
        } else {
          console.log(`   📊 Data: ❌ Not available`);
        }
      }
      
      // Overall working status
      result.working = (!endpoint.expectDatabase || result.databaseConnected) && 
                      (!endpoint.expectData || result.dataAvailable);
      
      if (result.working) {
        console.log(`   🎯 Status: ✅ Working`);
      } else {
        console.log(`   🎯 Status: ❌ Not Working`);
      }
    }
    
    results.endpoints.push(result);
  }
  
  // Summary
  console.log('\n' + '='.repeat(50));
  console.log('📊 Database Connectivity Summary');
  console.log('='.repeat(50));
  
  const dbConnectionRate = (results.summary.connected / results.summary.total) * 100;
  const dataAvailabilityRate = (results.summary.dataAvailable / results.summary.total) * 100;
  const criticalSuccessRate = results.summary.critical > 0 ? 
    (results.summary.criticalWorking / results.summary.critical) * 100 : 100;
  
  console.log(`🗄️ Database Connections: ${results.summary.connected}/${results.summary.total} (${dbConnectionRate.toFixed(1)}%)`);
  console.log(`📊 Data Availability: ${results.summary.dataAvailable}/${results.summary.total} (${dataAvailabilityRate.toFixed(1)}%)`);
  console.log(`🚨 Critical Endpoints: ${results.summary.criticalWorking}/${results.summary.critical} (${criticalSuccessRate.toFixed(1)}%)`);
  
  // Database status assessment
  console.log('\n🔍 Database Status Assessment:');
  
  if (results.summary.connected === 0) {
    console.log('🔴 NO DATABASE CONNECTIVITY');
    console.log('   • Database connection completely failed');
    console.log('   • Check database initialization task');
    console.log('   • Verify network connectivity');
  } else if (results.summary.connected < results.summary.total) {
    console.log('🟡 PARTIAL DATABASE CONNECTIVITY');
    console.log('   • Some endpoints can connect to database');
    console.log('   • May indicate intermittent issues');
    console.log('   • Check individual endpoint errors');
  } else {
    console.log('🟢 FULL DATABASE CONNECTIVITY');
    console.log('   • All database endpoints working');
    console.log('   • Database fully operational');
  }
  
  // Data status assessment
  if (results.summary.dataAvailable === 0) {
    console.log('\n📊 Data Status: 🔴 NO DATA AVAILABLE');
    console.log('   • Database may be empty');
    console.log('   • Data loaders may not have run');
    console.log('   • Check ECS data loading tasks');
  } else if (results.summary.dataAvailable < results.summary.total) {
    console.log('\n📊 Data Status: 🟡 PARTIAL DATA AVAILABLE');
    console.log('   • Some data endpoints working');
    console.log('   • Data loading may be in progress');
  } else {
    console.log('\n📊 Data Status: 🟢 FULL DATA AVAILABLE');
    console.log('   • All data endpoints have content');
    console.log('   • Data loaders successful');
  }
  
  // Recommendations
  console.log('\n🔧 Recommendations:');
  
  if (results.summary.connected === 0) {
    console.log('   1. Check database initialization ECS task logs');
    console.log('   2. Verify database is running and accessible');
    console.log('   3. Check security group and network configuration');
    console.log('   4. Verify secrets manager configuration');
  } else if (results.summary.connected < results.summary.total) {
    console.log('   1. Review failing endpoints individually');
    console.log('   2. Check for connection pool issues');
    console.log('   3. Monitor for intermittent connectivity');
  }
  
  if (results.summary.dataAvailable === 0) {
    console.log('   1. Trigger data loading ECS tasks');
    console.log('   2. Check data loader logs for errors');
    console.log('   3. Verify database schema exists');
  }
  
  console.log(`\n✨ Test completed: ${new Date().toISOString()}`);
  
  return results;
}

// Run if called directly
if (require.main === module) {
  testDatabaseConnectivity().catch(console.error);
}

module.exports = { testDatabaseConnectivity };
#\!/usr/bin/env node

const https = require('https');

async function testDatabaseConnectivity() {
  console.log('🔍 Testing database connectivity via Lambda API...');
  
  try {
    // Test health endpoint
    const healthResponse = await fetch('https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev/api/health');
    const healthData = await healthResponse.json();
    
    console.log('📊 API Health Status:', healthData.success ? '✅ HEALTHY' : '❌ UNHEALTHY');
    console.log('🗄️  Database Status:', healthData.database?.healthy ? '✅ CONNECTED' : '❌ DISCONNECTED');
    
    if (healthData.database?.error) {
      console.log('❌ Database Error:', healthData.database.error);
    }
    
    if (healthData.database?.circuitBreakerState) {
      console.log('🔌 Circuit Breaker:', healthData.database.circuitBreakerState);
    }
    
    // Test a database-dependent endpoint
    console.log('\n🧪 Testing database-dependent endpoint...');
    
    const tableResponse = await fetch('https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev/api/admin/tables');
    const tableData = await tableResponse.json();
    
    console.log('📊 Tables endpoint status:', tableResponse.status);
    
    if (tableData.success) {
      console.log('✅ Database tables accessible:');
      if (tableData.data?.tables) {
        Object.entries(tableData.data.tables).forEach(([table, count]) => {
          console.log(`   📋 ${table}: ${count} rows`);
        });
      }
    } else {
      console.log('❌ Tables endpoint error:', tableData.message);
    }
    
    return {
      lambdaHealthy: healthData.success,
      databaseHealthy: healthData.database?.healthy || false,
      circuitBreaker: healthData.database?.circuitBreakerState,
      tablesAccessible: tableData.success
    };
    
  } catch (error) {
    console.error('❌ Test failed:', error.message);
    return {
      lambdaHealthy: false,
      databaseHealthy: false,
      error: error.message
    };
  }
}

// Use global fetch if available, otherwise use a simple HTTPS request
if (typeof fetch === 'undefined') {
  global.fetch = async function(url) {
    return new Promise((resolve, reject) => {
      const request = https.get(url, (response) => {
        let data = '';
        response.on('data', chunk => data += chunk);
        response.on('end', () => {
          resolve({
            status: response.statusCode,
            json: async () => JSON.parse(data)
          });
        });
      });
      request.on('error', reject);
    });
  };
}

testDatabaseConnectivity().then(results => {
  console.log('\n🏁 Test Results Summary:');
  console.log(JSON.stringify(results, null, 2));
  
  if (results.databaseHealthy && results.tablesAccessible) {
    console.log('\n✅ Database connectivity is WORKING\!');
    process.exit(0);
  } else {
    console.log('\n❌ Database connectivity issues detected');
    process.exit(1);
  }
});
EOF < /dev/null

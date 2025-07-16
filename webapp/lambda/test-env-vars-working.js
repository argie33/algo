#!/usr/bin/env node
/**
 * Environment Variables Working Test
 * Tests if Lambda has proper environment variables from CloudFormation
 */

const https = require('https');

// Test configuration
const API_URL = process.env.LAMBDA_API_URL || 'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev';

// Expected environment variables that should be present
const REQUIRED_ENV_VARS = [
  'DB_SECRET_ARN',
  'DB_ENDPOINT', 
  'API_KEY_ENCRYPTION_SECRET_ARN',
  'ENVIRONMENT',
  'WEBAPP_AWS_REGION',
  'COGNITO_USER_POOL_ID',
  'COGNITO_CLIENT_ID'
];

// Critical environment variables for basic functionality
const CRITICAL_ENV_VARS = [
  'DB_SECRET_ARN',
  'API_KEY_ENCRYPTION_SECRET_ARN'
];

async function makeRequest(url) {
  return new Promise((resolve, reject) => {
    console.log(`🔍 Testing: ${url}`);
    
    const req = https.get(url, (res) => {
      let data = '';
      
      res.on('data', (chunk) => {
        data += chunk;
      });
      
      res.on('end', () => {
        try {
          const parsedData = JSON.parse(data);
          resolve({
            statusCode: res.statusCode,
            headers: res.headers,
            data: parsedData
          });
        } catch (e) {
          resolve({
            statusCode: res.statusCode,
            headers: res.headers,
            data: data,
            parseError: e.message
          });
        }
      });
    });
    
    req.on('error', (err) => {
      reject(err);
    });
    
    req.setTimeout(10000, () => {
      req.destroy();
      reject(new Error('Request timeout'));
    });
  });
}

async function testEnvironmentVariables() {
  console.log('🔍 Testing Lambda Environment Variables');
  console.log('='.repeat(50));
  console.log(`📡 API URL: ${API_URL}`);
  
  try {
    // Test dev-health endpoint for environment variable status
    const devHealthUrl = `${API_URL}/dev-health`;
    const response = await makeRequest(devHealthUrl);
    
    console.log(`\n📊 Response Status: ${response.statusCode}`);
    
    if (response.statusCode !== 200) {
      console.log('❌ Dev health endpoint not responding correctly');
      console.log('Response:', response.data);
      return false;
    }
    
    const data = response.data;
    
    // Check if response has expected structure
    if (!data || typeof data !== 'object') {
      console.log('❌ Invalid response format');
      return false;
    }
    
    console.log('\n🔍 Environment Variable Analysis:');
    
    // Check missing critical variables
    if (data.missing_critical_vars) {
      const missing = data.missing_critical_vars;
      console.log(`📋 Missing Variables: ${missing.length > 0 ? missing.join(', ') : 'None'}`);
      
      if (missing.length === 0) {
        console.log('✅ All critical environment variables are present!');
      } else {
        console.log('❌ Critical environment variables missing');
        
        // Check which critical ones are missing
        const missingCritical = missing.filter(v => CRITICAL_ENV_VARS.includes(v));
        if (missingCritical.length > 0) {
          console.log(`🚫 Critical missing: ${missingCritical.join(', ')}`);
        }
      }
    }
    
    // Check route loading status
    if (data.route_loading) {
      console.log(`\n🔗 Route Loading Status:`);
      console.log(`   All Routes Loaded: ${data.route_loading.all_routes_loaded ? '✅' : '❌'}`);
      console.log(`   Middleware Fixed: ${data.route_loading.middleware_fixed ? '✅' : '❌'}`);
      console.log(`   Response Formatter: ${data.route_loading.response_formatter_active ? '✅' : '❌'}`);
    }
    
    // Check database status
    if (data.database_status) {
      console.log(`\n🗄️ Database Status:`);
      console.log(`   Config Available: ${data.database_status.config_available ? '✅' : '❌'}`);
      console.log(`   Note: ${data.database_status.note}`);
    }
    
    // Show all available environment variables (non-secret)
    if (data.all_environment_vars) {
      console.log(`\n📊 Available Environment Variables: ${Object.keys(data.all_environment_vars).length}`);
      
      // Check presence of required variables
      const presentVars = [];
      const missingVars = [];
      
      for (const varName of REQUIRED_ENV_VARS) {
        if (varName in data.all_environment_vars) {
          presentVars.push(varName);
        } else {
          missingVars.push(varName);
        }
      }
      
      console.log(`   ✅ Present (${presentVars.length}): ${presentVars.join(', ')}`);
      if (missingVars.length > 0) {
        console.log(`   ❌ Missing (${missingVars.length}): ${missingVars.join(', ')}`);
      }
    }
    
    // Overall assessment
    const isFullyReady = data.missing_critical_vars && data.missing_critical_vars.length === 0;
    const routesWorking = data.route_loading && data.route_loading.all_routes_loaded;
    const configAvailable = data.database_status && data.database_status.config_available;
    
    console.log('\n' + '='.repeat(50));
    console.log('📋 Overall Assessment');
    console.log('='.repeat(50));
    console.log(`🔗 Routes Loading: ${routesWorking ? '✅ Working' : '❌ Issues'}`);
    console.log(`🔑 Environment Variables: ${isFullyReady ? '✅ Complete' : '❌ Missing'}`);
    console.log(`🗄️ Database Config: ${configAvailable ? '✅ Available' : '❌ Missing'}`);
    
    if (isFullyReady && routesWorking && configAvailable) {
      console.log('\n🎉 Lambda is fully configured and ready!');
      console.log('✅ Main app stack deployment appears successful.');
      return true;
    } else {
      console.log('\n⏳ Lambda not yet fully ready.');
      
      if (!isFullyReady) {
        console.log('   🔧 Waiting for main app stack to provide environment variables');
      }
      if (!routesWorking) {
        console.log('   🔧 Route loading issues need resolution');
      }
      if (!configAvailable) {
        console.log('   🔧 Database configuration not available');
      }
      
      return false;
    }
    
  } catch (error) {
    console.error('❌ Error testing environment variables:', error.message);
    return false;
  }
}

// Additional test: Try to call database-dependent endpoint
async function testDatabaseConnectivity() {
  console.log('\n🗄️ Testing Database Connectivity');
  console.log('='.repeat(50));
  
  try {
    const healthUrl = `${API_URL}/api/health`;
    const response = await makeRequest(healthUrl);
    
    console.log(`📊 Health Check Status: ${response.statusCode}`);
    
    if (response.statusCode === 200 && response.data && response.data.success) {
      console.log('✅ API health check successful');
      
      if (response.data.database) {
        console.log(`🗄️ Database Status: ${response.data.database.status || 'Unknown'}`);
        
        if (response.data.database.status === 'connected') {
          console.log('✅ Database connection successful!');
          return true;
        } else {
          console.log('❌ Database connection failed');
          if (response.data.database.error) {
            console.log(`   Error: ${response.data.database.error}`);
          }
        }
      }
    } else {
      console.log('❌ API health check failed');
      if (response.data && response.data.error) {
        console.log(`   Error: ${response.data.error}`);
      }
    }
    
    return false;
    
  } catch (error) {
    console.error('❌ Error testing database connectivity:', error.message);
    return false;
  }
}

async function runCompleteTest() {
  console.log('🚀 Complete Lambda Environment Test');
  console.log('='.repeat(60));
  
  const envVarsReady = await testEnvironmentVariables();
  const dbConnected = await testDatabaseConnectivity();
  
  console.log('\n' + '='.repeat(60));
  console.log('🏁 Final Results');
  console.log('='.repeat(60));
  console.log(`🔑 Environment Variables: ${envVarsReady ? '✅ Ready' : '❌ Not Ready'}`);
  console.log(`🗄️ Database Connectivity: ${dbConnected ? '✅ Connected' : '❌ Not Connected'}`);
  
  if (envVarsReady && dbConnected) {
    console.log('\n🎉 DEPLOYMENT SUCCESSFUL!');
    console.log('✅ Lambda is fully operational with proper configuration.');
    console.log('✅ Ready for end-to-end system testing.');
  } else {
    console.log('\n⏳ Deployment still in progress...');
    if (!envVarsReady) {
      console.log('   • Waiting for main app stack deployment to complete');
    }
    if (!dbConnected) {
      console.log('   • Waiting for database connectivity to be established');
    }
  }
  
  return envVarsReady && dbConnected;
}

// Run if called directly
if (require.main === module) {
  runCompleteTest().catch(console.error);
}

module.exports = { testEnvironmentVariables, testDatabaseConnectivity, runCompleteTest };
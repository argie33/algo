#!/usr/bin/env node
/**
 * Check Deployment Status
 * Quick check to see if deployment is working and investigate 403 errors
 */

const axios = require('axios');

async function checkDeploymentStatus() {
  console.log('🔍 Checking Deployment Status');
  console.log('=============================');
  
  // Test different URLs and methods
  const baseUrls = [
    'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev',
    'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev/',
    'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com'
  ];
  
  for (const baseUrl of baseUrls) {
    console.log(`\n📡 Testing: ${baseUrl}`);
    
    try {
      const response = await axios.get(baseUrl, {
        timeout: 10000,
        validateStatus: () => true, // Don't throw on non-2xx
        headers: {
          'Accept': 'application/json',
          'User-Agent': 'Deployment-Status-Check/1.0'
        }
      });
      
      console.log(`   Status: ${response.status}`);
      console.log(`   Content-Type: ${response.headers['content-type']}`);
      console.log(`   Server: ${response.headers['server'] || 'Unknown'}`);
      
      if (response.status === 403) {
        console.log('   🚨 403 Error detected - API Gateway/Lambda integration issue');
        
        // Check if it's HTML (API Gateway error) or JSON (Lambda error)
        if (response.headers['content-type']?.includes('text/html')) {
          console.log('   📄 HTML response - likely API Gateway error');
          console.log('   🔍 Response sample:', response.data.substring(0, 200));
        } else {
          console.log('   📄 JSON response - likely Lambda error');
          console.log('   🔍 Response:', JSON.stringify(response.data));
        }
      } else if (response.status === 200) {
        console.log('   ✅ Success!');
        console.log('   🔍 Response:', JSON.stringify(response.data).substring(0, 200));
      }
      
    } catch (error) {
      console.log(`   ❌ Error: ${error.message}`);
      if (error.code === 'ENOTFOUND') {
        console.log('   🌐 DNS resolution failed - API Gateway may not exist');
      } else if (error.code === 'ECONNREFUSED') {
        console.log('   🔌 Connection refused - service may be down');
      } else if (error.code === 'ETIMEDOUT') {
        console.log('   ⏱️  Connection timeout - service may be slow');
      }
    }
  }
  
  console.log('\n🔍 Possible Issues:');
  console.log('==================');
  console.log('1. 🚀 Deployment still in progress (check GitHub Actions)');
  console.log('2. 🔧 API Gateway stage/deployment configuration issue');
  console.log('3. 📝 Lambda function integration issue');
  console.log('4. 🌐 CORS policy blocking requests');
  console.log('5. 🔐 API Gateway requires authentication');
  
  console.log('\n📋 Next Steps:');
  console.log('==============');
  console.log('1. Check GitHub Actions deployment status');
  console.log('2. Verify CloudFormation stack deployment');
  console.log('3. Check Lambda function logs in CloudWatch');
  console.log('4. Verify API Gateway stage configuration');
  console.log('5. Test with different HTTP methods (POST, OPTIONS)');
}

// Test specific endpoint patterns
async function testEndpointPatterns() {
  console.log('\n🎯 Testing Endpoint Patterns');
  console.log('============================');
  
  const baseUrl = 'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev';
  const patterns = [
    '/',
    '/health',
    '/api/health',
    '/api/diagnostics',
    '/api/stocks'
  ];
  
  for (const pattern of patterns) {
    const fullUrl = baseUrl + pattern;
    console.log(`\n🔍 Testing: ${fullUrl}`);
    
    try {
      const response = await axios({
        method: 'GET',
        url: fullUrl,
        timeout: 5000,
        validateStatus: () => true,
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        }
      });
      
      console.log(`   Status: ${response.status}`);
      
      if (response.status === 200) {
        console.log('   ✅ Working!');
      } else if (response.status === 403) {
        console.log('   🚨 403 Forbidden');
      } else if (response.status === 404) {
        console.log('   ❌ 404 Not Found');
      } else {
        console.log(`   ⚠️  Unexpected: ${response.status}`);
      }
      
    } catch (error) {
      console.log(`   ❌ Error: ${error.message}`);
    }
  }
}

async function main() {
  await checkDeploymentStatus();
  await testEndpointPatterns();
}

main().catch(console.error);
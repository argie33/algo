#!/usr/bin/env node
/**
 * Security Group Validation Tool
 * Validates ECS->RDS connectivity and security group configuration
 */

const https = require('https');
const net = require('net');
const dns = require('dns').promises;

const API_URL = 'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev';
const RDS_ENDPOINT = 'stocks.cojggi2mkthi.us-east-1.rds.amazonaws.com';
const RDS_PORT = 5432;

async function validateSecurityGroups() {
  console.log('🔒 Security Group Validation');
  console.log('='.repeat(50));
  console.log(`📡 Target: ${RDS_ENDPOINT}:${RDS_PORT}`);
  console.log(`🕐 Started: ${new Date().toISOString()}`);
  console.log();
  
  const validation = {
    timestamp: new Date().toISOString(),
    dnsResolution: null,
    networkConnectivity: null,
    tcpConnection: null,
    lambdaToRds: null,
    recommendations: []
  };
  
  try {
    // 1. DNS Resolution Test
    console.log('🔍 Step 1: DNS Resolution');
    console.log('-'.repeat(30));
    
    const addresses = await dns.lookup(RDS_ENDPOINT, { all: true });
    
    validation.dnsResolution = {
      success: true,
      addresses: addresses,
      primaryAddress: Array.isArray(addresses) ? addresses[0].address : addresses.address
    };
    
    console.log(`✅ DNS Resolution: ${RDS_ENDPOINT}`);
    if (Array.isArray(addresses)) {
      addresses.forEach((addr, index) => {
        console.log(`   ${index + 1}. ${addr.address} (${addr.family === 4 ? 'IPv4' : 'IPv6'})`);
      });
    } else {
      console.log(`   Address: ${addresses.address}`);
    }
    
    // 2. Network Connectivity Test
    console.log('\\n🔍 Step 2: Network Connectivity');
    console.log('-'.repeat(30));
    
    const targetAddress = validation.dnsResolution.primaryAddress;
    const tcpResult = await testTcpConnection(targetAddress, RDS_PORT);
    
    validation.tcpConnection = tcpResult;
    
    if (tcpResult.success) {
      console.log(`✅ TCP Connection: ${targetAddress}:${RDS_PORT} (${tcpResult.responseTime}ms)`);
      validation.networkConnectivity = { success: true, responseTime: tcpResult.responseTime };
    } else {
      console.log(`❌ TCP Connection Failed: ${tcpResult.error}`);
      validation.networkConnectivity = { success: false, error: tcpResult.error };
      
      // Analyze the error
      if (tcpResult.error.includes('ECONNREFUSED')) {
        validation.recommendations.push('Database security group may not allow inbound connections on port 5432');
        validation.recommendations.push('Check RDS security group for inbound rules from ECS subnet');
        validation.recommendations.push('Verify RDS is in the same VPC as ECS tasks');
      } else if (tcpResult.error.includes('ETIMEDOUT')) {
        validation.recommendations.push('Network timeout suggests security group or ACL blocking');
        validation.recommendations.push('Check ECS security group for outbound rules to port 5432');
        validation.recommendations.push('Verify route table configuration between subnets');
      }
    }
    
    // 3. Lambda to RDS Test
    console.log('\\n🔍 Step 3: Lambda to RDS Connectivity');
    console.log('-'.repeat(30));
    
    const lambdaResult = await testLambdaToRds();
    validation.lambdaToRds = lambdaResult;
    
    if (lambdaResult.success) {
      console.log(`✅ Lambda to RDS: Working`);
      console.log(`   Database: ${lambdaResult.databaseConnected ? 'Connected' : 'Not Connected'}`);
      console.log(`   Error: ${lambdaResult.error || 'None'}`);
    } else {
      console.log(`❌ Lambda to RDS: Failed`);
      console.log(`   Error: ${lambdaResult.error}`);
      
      if (lambdaResult.error && lambdaResult.error.includes('getSecretsValue')) {
        validation.recommendations.push('Lambda code deployment not complete - database connection bug present');
      }
    }
    
    // 4. Summary and Recommendations
    console.log('\\n🔍 Step 4: Analysis and Recommendations');
    console.log('-'.repeat(30));
    
    console.log('📊 Validation Summary:');
    console.log(`   DNS Resolution: ${validation.dnsResolution?.success ? '✅' : '❌'}`);
    console.log(`   Network Connectivity: ${validation.networkConnectivity?.success ? '✅' : '❌'}`);
    console.log(`   Lambda to RDS: ${validation.lambdaToRds?.success ? '✅' : '❌'}`);
    
    if (validation.recommendations.length > 0) {
      console.log('\\n🔧 Recommendations:');
      validation.recommendations.forEach((rec, index) => {
        console.log(`   ${index + 1}. ${rec}`);
      });
    }
    
    // 5. Next Steps
    console.log('\\n📋 Next Steps:');
    if (validation.networkConnectivity?.success && validation.lambdaToRds?.success) {
      console.log('✅ All connectivity tests passed');
      console.log('   • Security groups appear to be configured correctly');
      console.log('   • Database initialization should proceed normally');
    } else if (validation.networkConnectivity?.success && !validation.lambdaToRds?.success) {
      console.log('⚠️ Network connectivity works but Lambda connection fails');
      console.log('   • Wait for Lambda deployment to complete');
      console.log('   • Monitor database initialization progress');
    } else {
      console.log('❌ Network connectivity issues detected');
      console.log('   • Fix security group configuration');
      console.log('   • Ensure ECS subnet can reach RDS subnet');
      console.log('   • Check route table and ACL configuration');
    }
    
  } catch (error) {
    console.error('❌ Validation failed:', error.message);
    validation.error = error.message;
  }
  
  console.log(`\\n✨ Validation completed: ${new Date().toISOString()}`);
  
  return validation;
}

async function testTcpConnection(host, port, timeout = 15000) {
  return new Promise((resolve) => {
    const socket = new net.Socket();
    const startTime = Date.now();
    
    const timeoutId = setTimeout(() => {
      socket.destroy();
      resolve({
        success: false,
        error: `Connection timeout after ${timeout}ms`,
        responseTime: Date.now() - startTime
      });
    }, timeout);
    
    socket.connect(port, host, () => {
      const responseTime = Date.now() - startTime;
      clearTimeout(timeoutId);
      socket.destroy();
      resolve({
        success: true,
        responseTime
      });
    });
    
    socket.on('error', (error) => {
      clearTimeout(timeoutId);
      socket.destroy();
      resolve({
        success: false,
        error: error.message,
        responseTime: Date.now() - startTime
      });
    });
  });
}

async function testLambdaToRds() {
  return new Promise((resolve) => {
    const req = https.get(`${API_URL}/api/health`, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          const result = JSON.parse(data);
          resolve({
            success: res.statusCode === 200,
            databaseConnected: result.database?.healthy || false,
            error: result.database?.error || null,
            circuitBreakerState: result.database?.circuitBreakerState,
            fullResponse: result
          });
        } catch (e) {
          resolve({
            success: false,
            error: `Parse error: ${e.message}`,
            rawResponse: data
          });
        }
      });
    });
    
    req.on('error', (err) => {
      resolve({
        success: false,
        error: err.message
      });
    });
    
    req.setTimeout(10000);
    req.end();
  });
}

// Run if called directly
if (require.main === module) {
  validateSecurityGroups().catch(console.error);
}

module.exports = { validateSecurityGroups };
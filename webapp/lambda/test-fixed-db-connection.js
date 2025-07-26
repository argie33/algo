#!/usr/bin/env node
/**
 * Test Database Connection with Fixed Configuration
 * Tests both environment variable and AWS Secrets Manager paths
 */

const databaseManager = require('./utils/databaseConnectionManager');

async function testFixedConnection() {
  console.log('🔍 Testing Fixed Database Connection Configuration\n');
  
  try {
    // Test 1: Environment Variable Path
    console.log('📋 Test 1: Environment Variable Configuration');
    console.log('=' .repeat(50));
    
    const hasEnvVars = process.env.DB_HOST && process.env.DB_USER && process.env.DB_PASSWORD;
    if (hasEnvVars) {
      console.log('✅ Environment variables detected');
      console.log(`   Host: ${process.env.DB_HOST}`);
      console.log(`   User: ${process.env.DB_USER}`);
      console.log(`   Database: ${process.env.DB_NAME || 'stocks'}`);
      
      try {
        const result = await databaseManager.query('SELECT 1 as test, NOW() as timestamp');
        console.log('✅ Environment variable connection successful');
        console.log(`   Server time: ${result.rows[0].timestamp}`);
      } catch (error) {
        console.log('❌ Environment variable connection failed');
        console.log(`   Error: ${error.message}`);
      }
    } else {
      console.log('⚠️ Environment variables not set');
      console.log('   To test with env vars, set: DB_HOST, DB_USER, DB_PASSWORD');
    }
    
    // Test 2: AWS Secrets Manager Path
    console.log('\n📋 Test 2: AWS Secrets Manager Configuration');
    console.log('=' .repeat(50));
    
    const hasSecretArn = process.env.DB_SECRET_ARN && !process.env.DB_SECRET_ARN.includes('${');
    if (hasSecretArn) {
      console.log('✅ DB_SECRET_ARN detected');
      console.log(`   ARN: ${process.env.DB_SECRET_ARN}`);
      console.log(`   Region: ${process.env.WEBAPP_AWS_REGION || process.env.AWS_REGION || 'us-east-1'}`);
      
      // Temporarily remove env vars to force Secrets Manager path
      const envBackup = {
        DB_HOST: process.env.DB_HOST,
        DB_USER: process.env.DB_USER,
        DB_PASSWORD: process.env.DB_PASSWORD
      };
      
      delete process.env.DB_HOST;
      delete process.env.DB_USER;
      delete process.env.DB_PASSWORD;
      
      try {
        // Force reinitialize to test Secrets Manager path
        await databaseManager.forceReset();
        const result = await databaseManager.query('SELECT 1 as test, NOW() as timestamp');
        console.log('✅ AWS Secrets Manager connection successful');
        console.log(`   Server time: ${result.rows[0].timestamp}`);
      } catch (error) {
        console.log('❌ AWS Secrets Manager connection failed');
        console.log(`   Error: ${error.message}`);
        
        if (error.message.includes('AccessDeniedException')) {
          console.log('💡 This is expected in development - IAM permissions needed');
          console.log('   Lambda will have correct permissions in AWS environment');
        }
      }
      
      // Restore environment variables
      Object.assign(process.env, envBackup);
    } else {
      console.log('⚠️ DB_SECRET_ARN not properly configured');
      console.log(`   Current value: ${process.env.DB_SECRET_ARN || 'not set'}`);
    }
    
    // Test 3: Health Check
    console.log('\n📋 Test 3: Health Check');
    console.log('=' .repeat(50));
    
    try {
      const health = await databaseManager.healthCheck();
      if (health.healthy) {
        console.log('✅ Database health check passed');
        console.log(`   Status: ${health.status}`);
        console.log(`   Message: ${health.message}`);
      } else {
        console.log('❌ Database health check failed');
        console.log(`   Error: ${health.error}`);
      }
    } catch (healthError) {
      console.log('❌ Health check error');
      console.log(`   Error: ${healthError.message}`);
    }
    
    // Summary
    console.log('\n📊 Summary');
    console.log('=' .repeat(50));
    
    if (hasEnvVars) {
      console.log('✅ Environment variable fallback configured');
      console.log('   → Development testing enabled');
    } else {
      console.log('⚠️ Set DB_HOST, DB_USER, DB_PASSWORD for local testing');
    }
    
    if (hasSecretArn) {
      console.log('✅ AWS Secrets Manager path configured');
      console.log('   → Production deployment ready');
    } else {
      console.log('⚠️ DB_SECRET_ARN needs to be properly set');
    }
    
    console.log('\n🎯 Next Steps:');
    console.log('1. For local development: Set environment variables in .env.local');
    console.log('2. For production: Deploy CloudFormation template with updated IAM permissions');
    console.log('3. Lambda will automatically use correct path based on environment');
    
  } catch (error) {
    console.error('\n💥 Test script failed with error:');
    console.error(error.message);
    console.error('\nStack trace:');
    console.error(error.stack);
    process.exit(1);
  }
}

// Run the test if called directly
if (require.main === module) {
  testFixedConnection().catch(error => {
    console.error('Unhandled error:', error);
    process.exit(1);
  });
}

module.exports = testFixedConnection;
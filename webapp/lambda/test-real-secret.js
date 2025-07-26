#!/usr/bin/env node
/**
 * Test Real Secret Retrieval
 * Test accessing the actual AWS Secrets Manager secret
 */

const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');

async function testRealSecret() {
  console.log('🔐 Testing Real Secrets Manager Configuration');
  console.log('===========================================\n');
  
  // Use the real secret ARN from your AWS environment
  const realSecretArn = 'arn:aws:secretsmanager:us-east-1:626216981288:secret:stocks-db-secrets-stocks-app-stack-us-east-1-001-fl3BxQ';
  
  console.log(`📍 Testing Secret: ${realSecretArn}`);
  
  try {
    const secretsManager = new SecretsManagerClient({
      region: 'us-east-1',
      requestTimeout: 10000
    });
    
    console.log('⏳ Retrieving secret...');
    const startTime = Date.now();
    
    const command = new GetSecretValueCommand({ 
      SecretId: realSecretArn 
    });
    const response = await secretsManager.send(command);
    
    const duration = Date.now() - startTime;
    console.log(`✅ Secret retrieved successfully (${duration}ms)`);
    
    if (!response.SecretString) {
      console.log('❌ Secret value is empty');
      return;
    }
    
    let secret;
    try {
      secret = JSON.parse(response.SecretString);
      console.log('✅ Secret JSON parsed successfully');
    } catch (parseError) {
      console.log('❌ Secret contains invalid JSON:', parseError.message);
      return;
    }
    
    // Show what fields are available (without showing sensitive values)
    const fields = Object.keys(secret);
    console.log(`📋 Secret contains fields: ${fields.join(', ')}`);
    
    // Check required database fields
    const requiredFields = ['username', 'password'];
    const hostFields = ['host', 'endpoint'];
    
    const missingRequired = requiredFields.filter(field => !secret[field]);
    const hasHost = hostFields.some(field => secret[field]);
    
    if (missingRequired.length > 0) {
      console.log(`❌ Missing required fields: ${missingRequired.join(', ')}`);
    } else {
      console.log('✅ All required fields present');
    }
    
    if (!hasHost) {
      console.log('❌ Missing host/endpoint field');
    } else {
      console.log('✅ Host/endpoint field present');
    }
    
    // Show database connection details (safe values only)
    const dbHost = secret.host || secret.endpoint || 'unknown';
    const dbPort = secret.port || 5432;
    const dbName = secret.dbname || secret.database || 'unknown';
    const dbUser = secret.username;
    
    console.log('\n📊 Database Configuration:');
    console.log(`   🏗️ Host: ${dbHost}:${dbPort}`);
    console.log(`   📚 Database: ${dbName}`);
    console.log(`   👤 Username: ${dbUser}`);
    console.log(`   🔐 Password: ${secret.password ? '[SET]' : '[MISSING]'}`);
    
    // Test database connection
    console.log('\n🔌 Testing Database Connection:');
    const { Pool } = require('pg');
    
    const dbConfig = {
      host: dbHost,
      port: dbPort,
      database: dbName,
      user: dbUser,
      password: secret.password,
      ssl: { rejectUnauthorized: false },
      connectionTimeoutMillis: 8000,
      query_timeout: 12000
    };
    
    const pool = new Pool({
      ...dbConfig,
      max: 1,
      min: 0,
      acquireTimeoutMillis: 5000,
      createTimeoutMillis: 8000
    });
    
    try {
      console.log('⏳ Connecting to database...');
      const connectionStart = Date.now();
      
      const client = await pool.connect();
      const connectionDuration = Date.now() - connectionStart;
      console.log(`✅ Database connection successful (${connectionDuration}ms)`);
      
      try {
        console.log('⏳ Testing query execution...');
        const queryStart = Date.now();
        
        const result = await client.query('SELECT 1 as test, NOW() as timestamp, current_database() as db_name, current_user as db_user');
        const queryDuration = Date.now() - queryStart;
        
        console.log(`✅ Query executed successfully (${queryDuration}ms)`);
        console.log(`📍 Connected to: ${result.rows[0].db_name} as ${result.rows[0].db_user}`);
        console.log(`⏰ Server time: ${result.rows[0].timestamp}`);
        
        // Test table access
        console.log('⏳ Testing table enumeration...');
        const tableResult = await client.query(`
          SELECT COUNT(*) as table_count
          FROM information_schema.tables 
          WHERE table_schema = 'public'
        `);
        
        console.log(`✅ Found ${tableResult.rows[0].table_count} tables in public schema`);
        
        console.log('\n🎯 CONCLUSION: Database connectivity is WORKING! ✅');
        console.log('The issue must be in Lambda environment or network configuration.');
        
      } finally {
        client.release();
      }
      
    } catch (dbError) {
      console.log(`❌ Database connection failed: ${dbError.message}`);
      console.log(`Error code: ${dbError.code || 'UNKNOWN'}`);
      
      if (dbError.message.includes('timeout')) {
        console.log('\n🔧 Network/VPC Issue Detected:');
        console.log('   → Lambda may not have network access to RDS');
        console.log('   → Check VPC configuration and security groups');
        console.log('   → Verify Lambda is in correct subnets');
      }
    } finally {
      await pool.end();
    }
    
  } catch (secretError) {
    console.log(`❌ Secrets Manager failed: ${secretError.message}`);
    console.log(`Error code: ${secretError.code || 'UNKNOWN'}`);
    
    if (secretError.message.includes('AccessDenied')) {
      console.log('\n🔧 Permission Issue:');
      console.log('   → Check AWS credentials have SecretsManager permissions');
      console.log('   → Verify secret exists and is accessible');
    }
  }
}

if (require.main === module) {
  testRealSecret().catch(error => {
    console.error('\n💥 Test failed:', error.message);
    process.exit(1);
  });
}

module.exports = { testRealSecret };
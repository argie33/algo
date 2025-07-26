#!/usr/bin/env node
/**
 * Database Connectivity Debug Script
 * Comprehensive diagnosis of Lambda→RDS connectivity issues
 */

const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');

// Mock Lambda environment for testing
if (!process.env.AWS_LAMBDA_FUNCTION_NAME) {
  console.log('🔧 Running in local environment - mocking Lambda context');
  
  // Set test environment variables if not already set
  if (!process.env.DB_SECRET_ARN) {
    process.env.DB_SECRET_ARN = 'arn:aws:secretsmanager:us-east-1:123456789012:secret:test-db-secret';
  }
  if (!process.env.WEBAPP_AWS_REGION) {
    process.env.WEBAPP_AWS_REGION = 'us-east-1';
  }
}

async function debugConnectivity() {
  console.log('🔍 DATABASE CONNECTIVITY DIAGNOSTIC REPORT');
  console.log('==========================================\n');
  
  const startTime = Date.now();
  
  // 1. Environment Analysis
  console.log('📊 ENVIRONMENT ANALYSIS:');
  console.log(`   NODE_ENV: ${process.env.NODE_ENV || 'undefined'}`);
  console.log(`   AWS_LAMBDA_FUNCTION_NAME: ${process.env.AWS_LAMBDA_FUNCTION_NAME || 'undefined'}`);
  console.log(`   AWS_REGION: ${process.env.AWS_REGION || 'undefined'}`);
  console.log(`   WEBAPP_AWS_REGION: ${process.env.WEBAPP_AWS_REGION || 'undefined'}`);
  console.log(`   DB_SECRET_ARN: ${process.env.DB_SECRET_ARN ? 'SET' : 'MISSING'}`);
  console.log(`   DB_ENDPOINT: ${process.env.DB_ENDPOINT || 'undefined'}`);
  
  if (process.env.DB_SECRET_ARN) {
    console.log(`   SECRET ARN VALUE: ${process.env.DB_SECRET_ARN}`);
    
    // Check for template variable issues
    if (process.env.DB_SECRET_ARN.includes('${')) {
      console.log('   ❌ PROBLEM: Secret ARN contains unresolved CloudFormation variables');
      return;
    }
  }
  console.log('');
  
  // 2. Secrets Manager Test
  console.log('🔐 SECRETS MANAGER TEST:');
  
  if (!process.env.DB_SECRET_ARN) {
    console.log('   ❌ CRITICAL: DB_SECRET_ARN environment variable not set');
    console.log('   → Check CloudFormation stack parameters');
    console.log('   → Verify template deployment succeeded');
    return;
  }
  
  try {
    const secretsManager = new SecretsManagerClient({
      region: process.env.WEBAPP_AWS_REGION || process.env.AWS_REGION || 'us-east-1',
      requestTimeout: 10000
    });
    
    console.log('   ⏳ Attempting to retrieve database secret...');
    const secretStart = Date.now();
    
    const command = new GetSecretValueCommand({ 
      SecretId: process.env.DB_SECRET_ARN 
    });
    const response = await secretsManager.send(command);
    
    const secretDuration = Date.now() - secretStart;
    console.log(`   ✅ Secret retrieved successfully (${secretDuration}ms)`);
    
    if (!response.SecretString) {
      console.log('   ❌ PROBLEM: Secret value is empty');
      return;
    }
    
    let secret;
    try {
      secret = JSON.parse(response.SecretString);
      console.log('   ✅ Secret JSON parsed successfully');
    } catch (parseError) {
      console.log('   ❌ PROBLEM: Secret contains invalid JSON');
      console.log(`   Error: ${parseError.message}`);
      return;
    }
    
    // Check required fields
    const required = ['username', 'password', 'host'];
    const present = [];
    const missing = [];
    
    required.forEach(field => {
      const altField = field === 'host' ? 'endpoint' : field;
      if (secret[field] || secret[altField]) {
        present.push(field);
      } else {
        missing.push(field);
      }
    });
    
    console.log(`   📋 Required fields present: ${present.join(', ')}`);
    if (missing.length > 0) {
      console.log(`   ❌ Missing required fields: ${missing.join(', ')}`);
      return;
    }
    
    // Extract connection details
    const dbHost = secret.host || secret.endpoint || process.env.DB_ENDPOINT;
    const dbPort = parseInt(secret.port) || 5432;
    const dbName = secret.dbname || secret.database || 'financial_dashboard';
    
    console.log(`   🏗️ Database Host: ${dbHost}:${dbPort}`);
    console.log(`   📚 Database Name: ${dbName}`);
    console.log(`   👤 Username: ${secret.username}`);
    
    console.log('');
    
    // 3. Database Connection Test
    console.log('🔌 DATABASE CONNECTION TEST:');
    
    // Import database module
    const { Pool } = require('pg');
    
    const dbConfig = {
      host: dbHost,
      port: dbPort,
      database: dbName,
      user: secret.username,
      password: secret.password,
      ssl: { rejectUnauthorized: false },
      connectionTimeoutMillis: 8000,
      query_timeout: 12000,
      statement_timeout: 12000
    };
    
    console.log('   ⏳ Creating database connection pool...');
    const pool = new Pool({
      ...dbConfig,
      max: 1,
      min: 0,
      acquireTimeoutMillis: 5000,
      createTimeoutMillis: 8000,
      destroyTimeoutMillis: 2000,
      idleTimeoutMillis: 10000
    });
    
    try {
      console.log('   ⏳ Testing database connectivity...');
      const connectionStart = Date.now();
      
      const client = await pool.connect();
      const connectionDuration = Date.now() - connectionStart;
      console.log(`   ✅ Database connection established (${connectionDuration}ms)`);
      
      try {
        console.log('   ⏳ Testing basic query execution...');
        const queryStart = Date.now();
        
        const result = await client.query('SELECT 1 as test, NOW() as timestamp, current_database() as db_name');
        const queryDuration = Date.now() - queryStart;
        
        console.log(`   ✅ Query executed successfully (${queryDuration}ms)`);
        console.log(`   📍 Connected to database: ${result.rows[0].db_name}`);
        console.log(`   ⏰ Server time: ${result.rows[0].timestamp}`);
        
        // Test table access
        console.log('   ⏳ Testing table access...');
        try {
          const tableResult = await client.query(`
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            ORDER BY table_name 
            LIMIT 5
          `);
          
          console.log(`   ✅ Found ${tableResult.rows.length} tables:`, 
            tableResult.rows.map(r => r.table_name).join(', '));
          
        } catch (tableError) {
          console.log(`   ⚠️ Table access test failed: ${tableError.message}`);
        }
        
      } finally {
        client.release();
      }
      
    } catch (connectionError) {
      console.log(`   ❌ DATABASE CONNECTION FAILED: ${connectionError.message}`);
      console.log(`   Error Code: ${connectionError.code || 'UNKNOWN'}`);
      
      // Provide specific troubleshooting based on error
      if (connectionError.message.includes('timeout')) {
        console.log('');
        console.log('   🔧 TIMEOUT TROUBLESHOOTING:');
        console.log('   → Check Lambda VPC configuration');
        console.log('   → Verify RDS security groups allow Lambda access');
        console.log('   → Ensure RDS is in same VPC as Lambda subnets');
        console.log('   → Check if RDS instance is running');
      } else if (connectionError.message.includes('connect ECONNREFUSED')) {
        console.log('');
        console.log('   🔧 CONNECTION REFUSED TROUBLESHOOTING:');
        console.log('   → RDS instance may be stopped');
        console.log('   → Check security group rules');
        console.log('   → Verify database endpoint is correct');
      } else if (connectionError.message.includes('password')) {
        console.log('');
        console.log('   🔧 AUTHENTICATION TROUBLESHOOTING:');
        console.log('   → Check Secrets Manager contains correct password');
        console.log('   → Verify database user exists');
        console.log('   → Check password hasn\'t expired');
      }
      
    } finally {
      await pool.end();
    }
    
  } catch (secretError) {
    console.log(`   ❌ SECRETS MANAGER ERROR: ${secretError.message}`);
    console.log(`   Error Code: ${secretError.code || 'UNKNOWN'}`);
    
    if (secretError.message.includes('AccessDenied')) {
      console.log('');
      console.log('   🔧 ACCESS DENIED TROUBLESHOOTING:');
      console.log('   → Check Lambda execution role has SecretsManager permissions');
      console.log('   → Verify secret ARN is correct');
      console.log('   → Check if secret exists in correct region');
    } else if (secretError.message.includes('timeout')) {
      console.log('');
      console.log('   🔧 TIMEOUT TROUBLESHOOTING:');
      console.log('   → Check Lambda internet connectivity');
      console.log('   → Verify VPC has NAT Gateway for Secrets Manager access');
      console.log('   → Check security groups allow outbound HTTPS');
    }
  }
  
  const totalDuration = Date.now() - startTime;
  console.log(`\n⏱️ Total diagnostic time: ${totalDuration}ms`);
  
  console.log('\n🎯 NEXT STEPS:');
  console.log('1. Deploy Lambda fixes if configuration issues found');
  console.log('2. Check AWS Console for RDS instance status');
  console.log('3. Verify CloudFormation stack deployment succeeded');
  console.log('4. Test database connectivity from AWS Console');
}

// Run diagnostic
if (require.main === module) {
  debugConnectivity().catch(error => {
    console.error('\n💥 DIAGNOSTIC SCRIPT FAILED:', error.message);
    console.error(error.stack);
    process.exit(1);
  });
}

module.exports = { debugConnectivity };
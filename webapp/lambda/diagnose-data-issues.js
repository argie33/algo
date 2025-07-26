#!/usr/bin/env node

/**
 * Data Issues Diagnostic Script
 * Tests all data pipeline components to identify root causes
 */

const { query, healthCheck, initializeDatabase } = require('./utils/database');

async function diagnoseLambdaToDBConnection() {
  console.log('🔍 DIAGNOSING LAMBDA TO DATABASE CONNECTION');
  console.log('==========================================');
  
  // 1. Check environment variables
  console.log('\n1. Environment Variables:');
  console.log('- DB_SECRET_ARN:', process.env.DB_SECRET_ARN ? 'SET' : 'MISSING');
  console.log('- DB_ENDPOINT:', process.env.DB_ENDPOINT ? 'SET' : 'MISSING');
  console.log('- WEBAPP_AWS_REGION:', process.env.WEBAPP_AWS_REGION || 'MISSING');
  console.log('- AWS_REGION:', process.env.AWS_REGION || 'MISSING');
  console.log('- NODE_ENV:', process.env.NODE_ENV || 'MISSING');
  
  // 2. Test database initialization
  console.log('\n2. Database Initialization:');
  try {
    await initializeDatabase();
    console.log('✅ Database initialized successfully');
  } catch (error) {
    console.log('❌ Database initialization failed:', error.message);
    return { dbConnection: false, error: error.message };
  }
  
  // 3. Test basic query
  console.log('\n3. Basic Database Query:');
  try {
    const result = await query('SELECT 1 as test, NOW() as timestamp');
    console.log('✅ Basic query successful:', result.rows[0]);
  } catch (error) {
    console.log('❌ Basic query failed:', error.message);
    return { dbConnection: false, error: error.message };
  }
  
  // 4. Test health check
  console.log('\n4. Health Check:');
  try {
    const health = await healthCheck();
    console.log('✅ Health check successful:', health);
  } catch (error) {
    console.log('❌ Health check failed:', error.message);
    return { dbConnection: false, error: error.message };
  }
  
  // 5. Test table access
  console.log('\n5. Critical Tables Access:');
  const tables = ['stock_symbols', 'latest_prices', 'user_api_keys'];
  
  for (const table of tables) {
    try {
      const result = await query(`SELECT COUNT(*) as count FROM ${table} LIMIT 1`);
      console.log(`✅ ${table}: ${result.rows[0].count} rows`);
    } catch (error) {
      console.log(`❌ ${table}: ${error.message}`);
    }
  }
  
  return { dbConnection: true, status: 'healthy' };
}

async function diagnoseAPIEndpoints() {
  console.log('\n🔍 DIAGNOSING API ENDPOINTS');
  console.log('===========================');
  
  // Test API key service
  console.log('\n1. API Key Service:');
  try {
    const apiKeyService = require('./utils/apiKeyService');
    console.log('✅ API Key service loaded');
    console.log('- Enabled:', apiKeyService.isEnabled);
    
    const health = apiKeyService.getServiceHealth();
    console.log('- Health:', health);
  } catch (error) {
    console.log('❌ API Key service error:', error.message);
  }
  
  // Test route mounting
  console.log('\n2. Route Files:');
  const routeFiles = ['health', 'settings', 'portfolio'];
  
  for (const route of routeFiles) {
    try {
      require(`./routes/${route}`);
      console.log(`✅ routes/${route}.js loads successfully`);
    } catch (error) {
      console.log(`❌ routes/${route}.js failed:`, error.message);
    }
  }
}

async function main() {
  console.log('🚀 FINANCIAL DASHBOARD DATA ISSUES DIAGNOSTIC');
  console.log('==============================================');
  console.log('Timestamp:', new Date().toISOString());
  console.log('Lambda Function:', process.env.AWS_LAMBDA_FUNCTION_NAME || 'Local');
  
  try {
    // Diagnose database connection
    const dbResult = await diagnoseLambdaToDBConnection();
    
    // Diagnose API endpoints
    await diagnoseAPIEndpoints();
    
    console.log('\n📊 SUMMARY');
    console.log('==========');
    console.log('Database Connection:', dbResult.dbConnection ? '✅ HEALTHY' : '❌ FAILED');
    
    if (!dbResult.dbConnection) {
      console.log('\n🔧 RECOMMENDED FIXES:');
      console.log('1. Check CloudFormation deployment status');
      console.log('2. Verify RDS instance is running');
      console.log('3. Check Lambda execution role permissions');
      console.log('4. Verify Secrets Manager access');
    }
    
  } catch (error) {
    console.error('❌ DIAGNOSTIC FAILED:', error);
  }
}

// Run diagnostic if called directly
if (require.main === module) {
  main().catch(console.error);
}

module.exports = { diagnoseLambdaToDBConnection, diagnoseAPIEndpoints };
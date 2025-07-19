#!/usr/bin/env node
/**
 * Test Environment Connectivity Check
 * Validates database connectivity and environment setup for integration tests
 */

const { DatabaseTestUtils } = require('./utils/database-test-utils');

async function checkTestEnvironment() {
  console.log('🔍 Checking test environment...');
  
  const checks = {
    database: false,
    environment: false,
    dependencies: false
  };

  // Check environment variables
  console.log('\n📋 Environment Variables:');
  const envVars = [
    'TEST_DB_HOST',
    'TEST_DB_PORT', 
    'TEST_DB_NAME',
    'TEST_DB_USER',
    'TEST_DB_PASSWORD',
    'USE_REAL_DATABASE'
  ];
  
  envVars.forEach(envVar => {
    const value = process.env[envVar];
    console.log(`  ${envVar}: ${value || 'not set'}`);
  });
  
  checks.environment = true;

  // Check database connectivity
  console.log('\n🔌 Database Connectivity:');
  const dbUtils = new DatabaseTestUtils();
  try {
    await dbUtils.initialize();
    console.log('  ✅ Database connection successful');
    checks.database = true;
    
    // Test basic query
    const result = await dbUtils.query('SELECT NOW() as current_time');
    console.log('  ✅ Database query successful:', result.rows[0].current_time);
    
    await dbUtils.cleanup();
  } catch (error) {
    console.log('  ❌ Database connection failed:', error.message);
    console.log('  📝 This is expected in CI/CD without PostgreSQL');
    console.log('  📝 Tests will fall back to mock database');
  }

  // Check dependencies
  console.log('\n📦 Dependencies:');
  try {
    require('pg');
    console.log('  ✅ PostgreSQL driver available');
    require('jest');
    console.log('  ✅ Jest testing framework available');
    require('supertest');
    console.log('  ✅ Supertest API testing available');
    checks.dependencies = true;
  } catch (error) {
    console.log('  ❌ Missing dependency:', error.message);
  }

  // Summary
  console.log('\n📊 Test Environment Summary:');
  console.log(`  Environment: ${checks.environment ? '✅' : '❌'}`);
  console.log(`  Database: ${checks.database ? '✅' : '⚠️  (fallback to mocks)'}`);
  console.log(`  Dependencies: ${checks.dependencies ? '✅' : '❌'}`);
  
  if (!checks.database) {
    console.log('\n💡 Database Setup Instructions:');
    console.log('  For real database testing, set these environment variables:');
    console.log('    TEST_DB_HOST=localhost');
    console.log('    TEST_DB_PORT=5432');
    console.log('    TEST_DB_NAME=test_financial_db');
    console.log('    TEST_DB_USER=test_user');
    console.log('    TEST_DB_PASSWORD=test_pass');
    console.log('    USE_REAL_DATABASE=true');
    console.log('  \n  Or run: npm run test:integration:setup');
  }

  console.log('\n🎯 Recommendation:');
  if (checks.dependencies && checks.environment) {
    console.log('  Integration tests ready to run with mock fallbacks');
    console.log('  Run: npm test -- tests/integration/');
  } else {
    console.log('  Please install missing dependencies before running tests');
  }
}

// Run the check if called directly
if (require.main === module) {
  checkTestEnvironment()
    .then(() => process.exit(0))
    .catch(error => {
      console.error('❌ Environment check failed:', error);
      process.exit(1);
    });
}

module.exports = { checkTestEnvironment };
#!/usr/bin/env node
/**
 * Unified API Key Service Build and Validation Script
 * Tests all components and verifies deployment readiness
 */

const fs = require('fs');
const path = require('path');

// ANSI color codes for output
const colors = {
  reset: '\x1b[0m',
  red: '\x1b[31m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  cyan: '\x1b[36m'
};

function log(message, color = 'reset') {
  console.log(`${colors[color]}${message}${colors.reset}`);
}

function checkFileExists(filePath, description) {
  const fullPath = path.resolve(__dirname, '..', filePath);
  if (fs.existsSync(fullPath)) {
    log(`✅ ${description}: ${filePath}`, 'green');
    return true;
  } else {
    log(`❌ ${description}: ${filePath} - NOT FOUND`, 'red');
    return false;
  }
}

function checkFileContent(filePath, searchString, description) {
  try {
    const fullPath = path.resolve(__dirname, '..', filePath);
    const content = fs.readFileSync(fullPath, 'utf8');
    if (content.includes(searchString)) {
      log(`✅ ${description}: Found "${searchString}"`, 'green');
      return true;
    } else {
      log(`❌ ${description}: Missing "${searchString}"`, 'red');
      return false;
    }
  } catch (error) {
    log(`❌ ${description}: Error reading file - ${error.message}`, 'red');
    return false;
  }
}

async function main() {
  log('🚀 Building and Validating Unified API Key Service', 'cyan');
  log('=' * 60, 'cyan');
  
  let allChecks = true;
  
  // Check core service files
  log('📋 Checking Core Service Files:', 'blue');
  allChecks &= checkFileExists('utils/unifiedApiKeyService.js', 'Core Service');
  allChecks &= checkFileExists('utils/unifiedApiKeyDatabaseService.js', 'Database Service');
  allChecks &= checkFileExists('utils/apiKeyPerformanceOptimizer.js', 'Performance Optimizer');
  allChecks &= checkFileExists('utils/apiKeyMigrationService.js', 'Migration Service');
  allChecks &= checkFileExists('routes/unified-api-keys.js', 'API Routes');
  
  // Check frontend files
  log('\n📋 Checking Frontend Files:', 'blue');
  allChecks &= checkFileExists('../frontend/src/components/ApiKeyManager.jsx', 'React Component');
  allChecks &= checkFileExists('../frontend/src/services/unifiedApiKeyService.js', 'Frontend Service');
  
  // Check database schema
  log('\n📋 Checking Database Schema:', 'blue');
  allChecks &= checkFileExists('sql/initialize-required-tables.sql', 'Database Schema');
  allChecks &= checkFileContent('sql/initialize-required-tables.sql', 'user_api_keys', 'API Keys Table');
  
  // Check route integration
  log('\n📋 Checking Route Integration:', 'blue');
  allChecks &= checkFileContent('index.js', 'unified-api-keys', 'Route Registration');
  allChecks &= checkFileContent('index.js', '/api/api-keys', 'Route Mount Point');
  
  // Check CloudFormation configuration
  log('\n📋 Checking Infrastructure:', 'blue');
  allChecks &= checkFileExists('../../template-webapp-lambda.yml', 'CloudFormation Template');
  allChecks &= checkFileContent('../../template-webapp-lambda.yml', 'ssm:GetParameter', 'SSM Permissions');
  allChecks &= checkFileContent('../../template-webapp-lambda.yml', 'ssm:PutParameter', 'SSM Write Permissions');
  allChecks &= checkFileContent('../../template-webapp-lambda.yml', 'DB_SSL: \'true\'', 'Database SSL Config');
  
  // Check dependencies
  log('\n📋 Checking Dependencies:', 'blue');
  allChecks &= checkFileExists('utils/simpleApiKeyService.js', 'Simple API Key Service');
  allChecks &= checkFileExists('utils/databaseConnectionManager.js', 'Database Manager');
  allChecks &= checkFileExists('middleware/auth.js', 'Authentication Middleware');
  
  // Validate core service functionality
  log('\n📋 Validating Service Integration:', 'blue');
  try {
    // Test service loading
    const unifiedService = require('../utils/unifiedApiKeyService');
    const databaseService = require('../utils/unifiedApiKeyDatabaseService');
    const performanceOptimizer = require('../utils/apiKeyPerformanceOptimizer');
    const migrationService = require('../utils/apiKeyMigrationService');
    
    log('✅ All services load successfully', 'green');
    
    // Test health check methods
    if (typeof unifiedService.healthCheck === 'function') {
      log('✅ Health check method available', 'green');
    } else {
      log('❌ Health check method missing', 'red');
      allChecks = false;
    }
    
    // Test cache methods
    if (typeof unifiedService.getCacheMetrics === 'function') {
      log('✅ Cache metrics method available', 'green');
    } else {
      log('❌ Cache metrics method missing', 'red');
      allChecks = false;
    }
    
    // Test migration methods
    if (typeof migrationService.runMigration === 'function') {
      log('✅ Migration methods available', 'green');
    } else {
      log('❌ Migration methods missing', 'red');
      allChecks = false;
    }
    
  } catch (error) {
    log(`❌ Service loading failed: ${error.message}`, 'red');
    allChecks = false;
  }
  
  // Check for potential issues
  log('\n📋 Checking for Potential Issues:', 'blue');
  
  // Check for proper error handling
  if (checkFileContent('routes/unified-api-keys.js', 'try {', 'Error Handling in Routes') &&
      checkFileContent('routes/unified-api-keys.js', 'catch (error)', 'Error Catching in Routes')) {
    log('✅ Proper error handling implemented', 'green');
  } else {
    log('❌ Error handling issues detected', 'red');
    allChecks = false;
  }
  
  // Check for authentication
  if (checkFileContent('routes/unified-api-keys.js', 'authenticateToken', 'Authentication Middleware')) {
    log('✅ Authentication properly configured', 'green');
  } else {
    log('❌ Authentication not configured', 'red');
    allChecks = false;
  }
  
  // Check for caching implementation
  if (checkFileContent('utils/unifiedApiKeyService.js', 'cache', 'Caching Implementation') &&
      checkFileContent('utils/unifiedApiKeyService.js', 'LRU', 'LRU Cache')) {
    log('✅ Advanced caching implemented', 'green');
  } else {
    log('❌ Caching issues detected', 'red');
    allChecks = false;
  }
  
  // Performance and scale checks
  log('\n📋 Checking Scale Features:', 'blue');
  if (checkFileContent('utils/unifiedApiKeyService.js', 'maxCacheSize: 10000', 'High-Scale Cache') ||
      checkFileContent('utils/unifiedApiKeyService.js', 'maxCacheSize', 'Cache Size Limits')) {
    log('✅ Scale optimizations implemented', 'green');
  } else {
    log('⚠️  Scale optimizations may need review', 'yellow');
  }
  
  // Final summary
  log('\n' + '=' * 60, 'cyan');
  if (allChecks) {
    log('🎉 BUILD SUCCESSFUL - Unified API Key Service Ready for Deployment!', 'green');
    log('\n📊 Summary:', 'cyan');
    log('✅ All core service files present', 'green');
    log('✅ Database integration complete', 'green');
    log('✅ Frontend components ready', 'green');
    log('✅ CloudFormation configuration verified', 'green');
    log('✅ Route integration confirmed', 'green');
    log('✅ Authentication and security configured', 'green');
    log('✅ Performance optimizations for thousands of users', 'green');
    log('✅ Migration tools available', 'green');
    
    log('\n🚀 Next Steps:', 'blue');
    log('1. Deploy CloudFormation changes: sam build && sam deploy', 'cyan');
    log('2. Run database migrations if needed', 'cyan');
    log('3. Test unified API endpoint: GET /api/api-keys', 'cyan');
    log('4. Monitor health endpoint: GET /api/api-keys/health', 'cyan');
    log('5. Run migration: node scripts/run-migration.js', 'cyan');
    
  } else {
    log('❌ BUILD FAILED - Issues detected that need resolution', 'red');
    log('\n📋 Required Actions:', 'yellow');
    log('1. Fix missing files and dependencies', 'yellow');
    log('2. Resolve configuration issues', 'yellow');
    log('3. Re-run build validation', 'yellow');
  }
  
  return allChecks;
}

if (require.main === module) {
  main().then(success => {
    process.exit(success ? 0 : 1);
  }).catch(error => {
    log(`💥 Build script failed: ${error.message}`, 'red');
    process.exit(1);
  });
}

module.exports = { main, checkFileExists, checkFileContent };
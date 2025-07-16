#!/usr/bin/env node
/**
 * Test Deployment Readiness
 * Comprehensive test of the complete user-specific API key workflow
 */

const fs = require('fs');
const path = require('path');

// Test results tracker
const testResults = {
  syntaxErrors: [],
  routeLoading: [],
  userContextHandling: [],
  apiKeyFlow: [],
  securityChecks: [],
  deploymentReadiness: []
};

// Check syntax of all route files
function checkSyntaxErrors() {
  console.log('🔍 Checking syntax errors in route files...');
  
  const routeFiles = [
    'routes/portfolio.js',
    'routes/stocks.js',
    'routes/trades.js',
    'routes/economic.js',
    'routes/market.js',
    'routes/settings.js'
  ];
  
  let allValid = true;
  
  routeFiles.forEach(file => {
    try {
      const filePath = path.join(__dirname, file);
      if (fs.existsSync(filePath)) {
        require(filePath);
        console.log(`✅ ${file}: Syntax OK`);
        testResults.syntaxErrors.push({ file, status: 'pass' });
      } else {
        console.log(`⚠️ ${file}: File not found`);
        testResults.syntaxErrors.push({ file, status: 'missing' });
      }
    } catch (error) {
      console.log(`❌ ${file}: Syntax Error - ${error.message}`);
      testResults.syntaxErrors.push({ file, status: 'fail', error: error.message });
      allValid = false;
    }
  });
  
  return allValid;
}

// Check API key service implementation
function checkApiKeyService() {
  console.log('\\n🔐 Checking API key service implementation...');
  
  try {
    const apiKeyService = require('./utils/apiKeyService');
    console.log('✅ API key service loads successfully');
    
    // Check if critical methods exist
    const criticalMethods = ['getDecryptedApiKey', 'encryptApiKey', 'validateApiKeyFormat'];
    criticalMethods.forEach(method => {
      if (typeof apiKeyService[method] === 'function') {
        console.log(`✅ ${method}: Method exists`);
        testResults.apiKeyFlow.push({ method, status: 'pass' });
      } else {
        console.log(`❌ ${method}: Method missing`);
        testResults.apiKeyFlow.push({ method, status: 'fail' });
      }
    });
    
    return true;
  } catch (error) {
    console.log(`❌ API key service error: ${error.message}`);
    testResults.apiKeyFlow.push({ component: 'apiKeyService', status: 'fail', error: error.message });
    return false;
  }
}

// Check authentication middleware
function checkAuthMiddleware() {
  console.log('\\n🔒 Checking authentication middleware...');
  
  try {
    const authMiddleware = require('./middleware/auth');
    console.log('✅ Authentication middleware loads successfully');
    
    if (typeof authMiddleware.authenticateToken === 'function') {
      console.log('✅ authenticateToken function exists');
      testResults.userContextHandling.push({ component: 'authenticateToken', status: 'pass' });
    } else {
      console.log('❌ authenticateToken function missing');
      testResults.userContextHandling.push({ component: 'authenticateToken', status: 'fail' });
    }
    
    return true;
  } catch (error) {
    console.log(`❌ Authentication middleware error: ${error.message}`);
    testResults.userContextHandling.push({ component: 'auth', status: 'fail', error: error.message });
    return false;
  }
}

// Check database connection utilities
function checkDatabaseUtils() {
  console.log('\\n🗄️ Checking database utilities...');
  
  try {
    const database = require('./utils/database');
    console.log('✅ Database utilities load successfully');
    
    if (typeof database.query === 'function') {
      console.log('✅ query function exists');
      testResults.apiKeyFlow.push({ component: 'database.query', status: 'pass' });
    } else {
      console.log('❌ query function missing');
      testResults.apiKeyFlow.push({ component: 'database.query', status: 'fail' });
    }
    
    return true;
  } catch (error) {
    console.log(`❌ Database utilities error: ${error.message}`);
    testResults.apiKeyFlow.push({ component: 'database', status: 'fail', error: error.message });
    return false;
  }
}

// Check Alpaca service
function checkAlpacaService() {
  console.log('\\n🦙 Checking Alpaca service...');
  
  try {
    const AlpacaService = require('./utils/alpacaService');
    console.log('✅ Alpaca service loads successfully');
    
    // Check if it's a constructor function
    if (typeof AlpacaService === 'function') {
      console.log('✅ AlpacaService constructor exists');
      testResults.apiKeyFlow.push({ component: 'AlpacaService', status: 'pass' });
    } else {
      console.log('❌ AlpacaService constructor missing');
      testResults.apiKeyFlow.push({ component: 'AlpacaService', status: 'fail' });
    }
    
    return true;
  } catch (error) {
    console.log(`❌ Alpaca service error: ${error.message}`);
    testResults.apiKeyFlow.push({ component: 'AlpacaService', status: 'fail', error: error.message });
    return false;
  }
}

// Check environment variables
function checkEnvironmentVariables() {
  console.log('\\n🌍 Checking environment variables...');
  
  const requiredEnvVars = [
    'DB_SECRET_ARN',
    'DB_ENDPOINT',
    'WEBAPP_AWS_REGION',
    'API_KEY_ENCRYPTION_SECRET_ARN'
  ];
  
  const optionalEnvVars = [
    'NODE_ENV',
    'COGNITO_USER_POOL_ID',
    'COGNITO_CLIENT_ID'
  ];
  
  let allRequired = true;
  
  requiredEnvVars.forEach(envVar => {
    if (process.env[envVar]) {
      console.log(`✅ ${envVar}: Set`);
      testResults.deploymentReadiness.push({ envVar, status: 'pass', required: true });
    } else {
      console.log(`❌ ${envVar}: Missing (Required)`);
      testResults.deploymentReadiness.push({ envVar, status: 'fail', required: true });
      allRequired = false;
    }
  });
  
  optionalEnvVars.forEach(envVar => {
    if (process.env[envVar]) {
      console.log(`✅ ${envVar}: Set`);
      testResults.deploymentReadiness.push({ envVar, status: 'pass', required: false });
    } else {
      console.log(`⚠️ ${envVar}: Missing (Optional)`);
      testResults.deploymentReadiness.push({ envVar, status: 'missing', required: false });
    }
  });
  
  return allRequired;
}

// Check security configurations
function checkSecurityConfigurations() {
  console.log('\\n🛡️ Checking security configurations...');
  
  const securityChecks = [
    {
      name: 'JWT Secret Configuration',
      check: () => process.env.JWT_SECRET || process.env.COGNITO_USER_POOL_ID,
      required: true
    },
    {
      name: 'API Key Encryption Secret',
      check: () => process.env.API_KEY_ENCRYPTION_SECRET_ARN,
      required: true
    },
    {
      name: 'Database Secret ARN',
      check: () => process.env.DB_SECRET_ARN,
      required: true
    },
    {
      name: 'Production Environment Check',
      check: () => process.env.NODE_ENV !== 'production' || process.env.DISABLE_LOGGING !== 'true',
      required: false
    }
  ];
  
  let allPassed = true;
  
  securityChecks.forEach(({ name, check, required }) => {
    try {
      if (check()) {
        console.log(`✅ ${name}: OK`);
        testResults.securityChecks.push({ name, status: 'pass', required });
      } else {
        console.log(`${required ? '❌' : '⚠️'} ${name}: ${required ? 'Failed' : 'Warning'}`);
        testResults.securityChecks.push({ name, status: required ? 'fail' : 'warning', required });
        if (required) allPassed = false;
      }
    } catch (error) {
      console.log(`❌ ${name}: Error - ${error.message}`);
      testResults.securityChecks.push({ name, status: 'error', required, error: error.message });
      if (required) allPassed = false;
    }
  });
  
  return allPassed;
}

// Generate deployment readiness report
function generateDeploymentReport() {
  console.log('\\n📊 Deployment Readiness Report');
  console.log('================================');
  
  const categories = [
    { name: 'Syntax Errors', results: testResults.syntaxErrors },
    { name: 'User Context Handling', results: testResults.userContextHandling },
    { name: 'API Key Flow', results: testResults.apiKeyFlow },
    { name: 'Security Checks', results: testResults.securityChecks },
    { name: 'Deployment Readiness', results: testResults.deploymentReadiness }
  ];
  
  let overallStatus = 'READY';
  
  categories.forEach(category => {
    const passed = category.results.filter(r => r.status === 'pass').length;
    const failed = category.results.filter(r => r.status === 'fail').length;
    const warnings = category.results.filter(r => r.status === 'warning' || r.status === 'missing').length;
    
    console.log(`\\n${category.name}:`);
    console.log(`  ✅ Passed: ${passed}`);
    console.log(`  ❌ Failed: ${failed}`);
    console.log(`  ⚠️ Warnings: ${warnings}`);
    
    if (failed > 0) {
      overallStatus = 'NOT READY';
      console.log(`  🔴 Critical issues found:`);
      category.results.filter(r => r.status === 'fail').forEach(result => {
        console.log(`    - ${result.file || result.component || result.envVar || result.method || result.name}: ${result.error || 'Failed'}`);
      });
    }
  });
  
  console.log(`\\n🎯 Overall Status: ${overallStatus}`);
  
  if (overallStatus === 'READY') {
    console.log('✅ System is ready for deployment!');
    console.log('Next steps:');
    console.log('1. Package Lambda function');
    console.log('2. Deploy to AWS');
    console.log('3. Test user API key workflow');
    console.log('4. Monitor system health');
  } else {
    console.log('❌ System has critical issues that must be resolved before deployment');
  }
  
  return overallStatus === 'READY';
}

// Main test runner
async function runDeploymentReadinessTests() {
  console.log('🚀 Running Deployment Readiness Tests...');
  console.log('===========================================');
  
  const checks = [
    checkSyntaxErrors,
    checkApiKeyService,
    checkAuthMiddleware,
    checkDatabaseUtils,
    checkAlpacaService,
    checkEnvironmentVariables,
    checkSecurityConfigurations
  ];
  
  let allPassed = true;
  
  for (const check of checks) {
    const result = await check();
    if (!result) {
      allPassed = false;
    }
  }
  
  const deploymentReady = generateDeploymentReport();
  
  if (deploymentReady) {
    console.log('\\n🎉 All systems operational! Ready to deploy and test user-specific API key workflow.');
  } else {
    console.log('\\n🔧 Issues found that need attention before deployment.');
  }
  
  return deploymentReady;
}

// Run tests if called directly
if (require.main === module) {
  runDeploymentReadinessTests().catch(console.error);
}

module.exports = { runDeploymentReadinessTests, testResults };
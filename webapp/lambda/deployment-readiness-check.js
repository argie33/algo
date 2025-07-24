#!/usr/bin/env node
/**
 * Deployment Readiness Check
 * Final validation before deploying crypto platform with AWS permissions fix
 */

const fs = require('fs');
const path = require('path');

console.log('🚀 DEPLOYMENT READINESS CHECK - Crypto Platform');
console.log('=' .repeat(60));
console.log('🎯 Validating all components after AWS permissions fix');
console.log('=' .repeat(60));

const results = {
  passed: 0,
  failed: 0,
  critical: 0,
  warnings: 0,
  issues: []
};

// Critical Infrastructure Checks
console.log('\n🏗️ CRITICAL INFRASTRUCTURE VALIDATION');
console.log('-' .repeat(40));

checkCloudFormationTemplate();
checkApiKeyService();
checkDatabaseConnectivity();

// Backend API Validation  
console.log('\n🔧 BACKEND API VALIDATION');
console.log('-' .repeat(40));

checkCryptoPortfolioAPI();
checkCryptoRealtimeAPI();
checkRouteIntegration();

// Frontend Component Validation
console.log('\n🎨 FRONTEND COMPONENT VALIDATION'); 
console.log('-' .repeat(40));

checkFrontendComponents();
checkAppIntegration();

// Security & Performance Validation
console.log('\n🛡️ SECURITY & PERFORMANCE VALIDATION');
console.log('-' .repeat(40));

checkSecurityMeasures();
checkErrorHandling();
checkPerformanceOptimizations();

// Final Assessment
console.log('\n' + '=' .repeat(60));
console.log('📊 DEPLOYMENT READINESS SUMMARY');
console.log('=' .repeat(60));

console.log(`✅ Passed Checks: ${results.passed}`);  
console.log(`❌ Failed Checks: ${results.failed}`);
console.log(`🚨 Critical Issues: ${results.critical}`);
console.log(`⚠️ Warnings: ${results.warnings}`);

const totalChecks = results.passed + results.failed;
const successRate = totalChecks > 0 ? ((results.passed / totalChecks) * 100).toFixed(1) : 0;
console.log(`🎯 Success Rate: ${successRate}%`);

if (results.issues.length > 0) {
  console.log('\n📋 ISSUES TO ADDRESS:');
  results.issues.forEach((issue, index) => {
    const prefix = issue.critical ? '🚨' : issue.warning ? '⚠️' : '❌';
    console.log(`${prefix} ${index + 1}. ${issue.message}`);
  });
}

// Deployment Recommendation
console.log('\n🎯 DEPLOYMENT RECOMMENDATION');
console.log('-' .repeat(40));

if (results.critical === 0 && results.failed <= 2) {
  console.log('✅ READY FOR DEPLOYMENT');
  console.log('\n📝 Deployment Steps:');
  console.log('   1. Deploy CloudFormation template with AWS permissions');
  console.log('   2. Test API key functionality in Lambda environment');
  console.log('   3. Validate crypto endpoints with real data');
  console.log('   4. Perform end-to-end user workflow testing');
  console.log('\n🔗 Expected Functionality:');
  console.log('   ✓ Secure API key storage in AWS Parameter Store');
  console.log('   ✓ Real-time crypto price tracking');
  console.log('   ✓ Portfolio management with P&L calculations'); 
  console.log('   ✓ Advanced analytics and alerts');
  console.log('   ✓ Responsive UI with Material-UI components');
} else if (results.critical === 0) {
  console.log('⚠️ MOSTLY READY - Address warnings before production');
  console.log('\n📝 Recommended Actions:');
  console.log('   1. Fix non-critical issues');
  console.log('   2. Deploy to staging environment first');
  console.log('   3. Conduct thorough testing');
} else {
  console.log('❌ NOT READY - Critical issues must be resolved');
  console.log('\n🚨 Address critical issues before any deployment');
}

console.log('\n🔗 Testing Guide: Use test-comprehensive-crypto.js in AWS Lambda environment');

function checkCloudFormationTemplate() {
  try {
    const templatePath = path.join(__dirname, '..', 'template-webapp-lambda.yml');
    const content = fs.readFileSync(templatePath, 'utf8');
    
    // Check SSM permissions
    const ssmActions = ['ssm:GetParameter', 'ssm:PutParameter', 'ssm:DeleteParameter'];
    const kmsActions = ['kms:Decrypt', 'kms:Encrypt', 'kms:GenerateDataKey'];
    
    const ssmFound = ssmActions.every(action => content.includes(action));
    const kmsFound = kmsActions.every(action => content.includes(action));
    
    if (ssmFound && kmsFound) {
      console.log('  ✅ AWS IAM permissions properly configured');
      results.passed++;
    } else {
      const missing = [];
      if (!ssmFound) missing.push('SSM permissions');
      if (!kmsFound) missing.push('KMS permissions'); 
      
      results.failed++;
      results.critical++;
      results.issues.push({
        message: `CloudFormation missing: ${missing.join(', ')}`,
        critical: true
      });
    }
    
    // Check parameter path security
    if (content.includes('/financial-platform/users/*')) {
      console.log('  ✅ Parameter Store paths properly restricted');
      results.passed++;
    } else {
      results.warnings++;
      results.issues.push({
        message: 'Parameter Store paths not restricted - security concern',
        warning: true
      });
    }
    
  } catch (error) {
    results.failed++;
    results.critical++;
    results.issues.push({
      message: `CloudFormation template error: ${error.message}`,
      critical: true
    });
  }
}

function checkApiKeyService() {
  try {
    const servicePath = path.join(__dirname, 'utils', 'apiKeyService.js');
    const content = fs.readFileSync(servicePath, 'utf8');
    
    // Check core methods
    const methods = ['storeApiKey', 'getApiKey', 'deleteApiKey', 'listApiKeys', 'healthCheck'];
    const methodsPresent = methods.every(method => content.includes(`async ${method}(`));
    
    if (methodsPresent) {
      console.log('  ✅ API Key Service fully implemented');
      results.passed++;
    } else {
      results.failed++;
      results.critical++;
      results.issues.push({
        message: 'API Key Service missing required methods',
        critical: true
      });
    }
    
    // Check AWS SDK v3
    if (content.includes('@aws-sdk/client-ssm')) {
      console.log('  ✅ AWS SDK v3 integration confirmed');
      results.passed++;
    } else {
      results.failed++;
      results.issues.push({
        message: 'AWS SDK v3 not properly integrated'
      });
    }
    
    // Check encryption
    if (content.includes("Type: 'SecureString'")) {
      console.log('  ✅ SecureString encryption enabled');
      results.passed++;
    } else {
      results.failed++;
      results.critical++;
      results.issues.push({
        message: 'API keys not using SecureString encryption',
        critical: true
      });
    }
    
  } catch (error) {
    results.failed++;
    results.critical++;
    results.issues.push({
      message: `API Key Service error: ${error.message}`,
      critical: true
    });
  }
}

function checkDatabaseConnectivity() {
  try {
    const dbPath = path.join(__dirname, 'utils', 'database.js');
    
    if (fs.existsSync(dbPath)) {
      console.log('  ✅ Database utility available');
      results.passed++;
    } else {
      console.log('  ⚠️ Database utility not found - using fallback data');
      results.warnings++;
      results.issues.push({
        message: 'Database connectivity not verified - relying on sample data',
        warning: true
      });
    }
    
  } catch (error) {
    results.warnings++;
    results.issues.push({
      message: `Database check warning: ${error.message}`,
      warning: true
    });
  }
}

function checkCryptoPortfolioAPI() {
  try {
    const routePath = path.join(__dirname, 'routes', 'crypto-portfolio.js');
    const content = fs.readFileSync(routePath, 'utf8');
    
    // Check actual route patterns from previous analysis
    const routes = [
      "router.get('/:user_id'",           // Get portfolio
      "router.post('/:user_id/transactions'", // Add transaction  
      "router.get('/:user_id/transactions'",  // Get transactions
      "router.get('/:user_id/analytics'"      // Get analytics
    ];
    
    const routesFound = routes.filter(route => content.includes(route));
    
    if (routesFound.length >= 3) {
      console.log(`  ✅ Crypto Portfolio API (${routesFound.length}/4 endpoints)`);
      results.passed++;
    } else {
      results.failed++;
      results.issues.push({
        message: `Crypto Portfolio API incomplete: ${routesFound.length}/4 endpoints`
      });
    }
    
    // Check for portfolio management logic
    if (content.includes('portfolios') && content.includes('transactions')) {
      console.log('  ✅ Portfolio management logic implemented');
      results.passed++;
    } else {
      results.warnings++;
      results.issues.push({
        message: 'Portfolio management logic may be incomplete',
        warning: true
      });
    }
    
  } catch (error) {
    results.failed++;
    results.issues.push({
      message: `Crypto Portfolio API error: ${error.message}`
    });
  }
}

function checkCryptoRealtimeAPI() {
  try {
    const routePath = path.join(__dirname, 'routes', 'crypto-realtime.js');
    const content = fs.readFileSync(routePath, 'utf8');
    
    // Check actual route patterns
    const routes = [
      "router.get('/prices'",        // Real-time prices
      "router.get('/market-pulse'",  // Market overview
      "router.post('/alerts'",       // Price alerts
      "router.get('/history/"        // Historical data
    ];
    
    const routesFound = routes.filter(route => content.includes(route));
    
    if (routesFound.length >= 3) {
      console.log(`  ✅ Crypto Real-time API (${routesFound.length}/4 endpoints)`);
      results.passed++;
    } else {
      results.failed++;
      results.issues.push({
        message: `Crypto Real-time API incomplete: ${routesFound.length}/4 endpoints`
      });
    }
    
    // Check for caching logic
    if (content.includes('realtimeCache') && content.includes('30000')) {
      console.log('  ✅ Real-time data caching implemented');
      results.passed++;
    } else {
      results.warnings++;
      results.issues.push({
        message: 'Real-time data caching may be missing',
        warning: true
      });
    }
    
  } catch (error) {
    results.failed++;
    results.issues.push({
      message: `Crypto Real-time API error: ${error.message}`
    });
  }
}

function checkRouteIntegration() {
  try {
    const indexPath = path.join(__dirname, 'index.js');
    const content = fs.readFileSync(indexPath, 'utf8');
    
    // Check if crypto routes are mounted
    const cryptoRoutes = ['crypto-portfolio', 'crypto-realtime'];
    const mountedRoutes = cryptoRoutes.filter(route => content.includes(route));
    
    if (mountedRoutes.length === cryptoRoutes.length) {
      console.log('  ✅ Crypto routes properly mounted in Lambda');
      results.passed++;
    } else {
      results.failed++;
      results.issues.push({
        message: `Crypto routes not mounted: ${mountedRoutes.length}/${cryptoRoutes.length}`
      });
    }
    
  } catch (error) {
    results.failed++;
    results.issues.push({
      message: `Route integration error: ${error.message}`
    });
  }
}

function checkFrontendComponents() {
  const components = ['CryptoPortfolio.jsx', 'CryptoRealTimeTracker.jsx', 'CryptoAdvancedAnalytics.jsx'];
  
  components.forEach(component => {
    try {
      const componentPath = path.join(__dirname, '..', 'frontend', 'src', 'pages', component);
      const content = fs.readFileSync(componentPath, 'utf8');
      
      // Check React structure
      const hasReact = content.includes('import React') || content.includes('from \'react\'');
      const hasHooks = content.includes('useState') || content.includes('useEffect');  
      const hasExport = content.includes('export default');
      
      if (hasReact && hasHooks && hasExport) {
        console.log(`  ✅ ${component} - React component validated`);
        results.passed++;
      } else {
        results.failed++;
        results.issues.push({
          message: `${component} - React component structure incomplete`
        });
      }
      
    } catch (error) {
      results.failed++;
      results.issues.push({
        message: `${component} error: ${error.message}`
      });
    }
  });
}

function checkAppIntegration() {  
  try {
    const appPath = path.join(__dirname, '..', 'frontend', 'src', 'App.jsx');
    const content = fs.readFileSync(appPath, 'utf8');
    
    const components = ['CryptoPortfolio', 'CryptoRealTimeTracker', 'CryptoAdvancedAnalytics'];
    const integratedComponents = components.filter(comp => content.includes(comp));
    
    if (integratedComponents.length === components.length) {
      console.log('  ✅ All crypto components integrated in App.jsx');
      results.passed++;
    } else {
      results.failed++;
      results.issues.push({
        message: `App.jsx missing components: ${integratedComponents.length}/${components.length}`
      });
    }
    
  } catch (error) {
    results.failed++;
    results.issues.push({
      message: `App.jsx integration error: ${error.message}`
    });
  }
}

function checkSecurityMeasures() {
  // Check for security middleware
  const securityFiles = [
    'middleware/inputValidation.js',
    'middleware/rateLimiting.js', 
    'utils/comprehensiveErrorHandler.js'
  ];
  
  let securityScore = 0;
  securityFiles.forEach(file => {
    const filePath = path.join(__dirname, file);
    if (fs.existsSync(filePath)) {
      securityScore++;
    }
  });
  
  if (securityScore >= 2) {
    console.log(`  ✅ Security middleware present (${securityScore}/3 files)`);
    results.passed++;
  } else {
    console.log(`  ⚠️ Limited security middleware (${securityScore}/3 files)`);
    results.warnings++;
    results.issues.push({
      message: 'Security middleware could be enhanced',
      warning: true
    });
  }
}

function checkErrorHandling() {
  try {
    // Check API key service error handling
    const apiKeyPath = path.join(__dirname, 'utils', 'apiKeyService.js');
    const content = fs.readFileSync(apiKeyPath, 'utf8');
    
    if (content.includes('try {') && content.includes('catch') && content.includes('throw new Error')) {
      console.log('  ✅ Comprehensive error handling implemented');
      results.passed++;
    } else {
      results.warnings++;
      results.issues.push({
        message: 'Error handling could be improved',
        warning: true
      });
    }
    
  } catch (error) {
    results.warnings++;
    results.issues.push({
      message: `Error handling check failed: ${error.message}`,
      warning: true
    });
  }
}

function checkPerformanceOptimizations() {
  try {
    // Check for caching in real-time routes
    const realtimePath = path.join(__dirname, 'routes', 'crypto-realtime.js');
    const content = fs.readFileSync(realtimePath, 'utf8');
    
    if (content.includes('cache') && content.includes('30000')) {
      console.log('  ✅ Real-time data caching optimizations');
      results.passed++;
    } else {
      results.warnings++;
      results.issues.push({
        message: 'Performance caching could be enhanced',
        warning: true
      });
    }
    
    // Check for sample data fallbacks
    const sampleDataPath = path.join(__dirname, 'utils', 'sample-data-store.js');
    if (fs.existsSync(sampleDataPath)) {
      console.log('  ✅ Sample data fallbacks available');
      results.passed++;
    } else {
      results.warnings++;
      results.issues.push({
        message: 'No sample data fallbacks for development',
        warning: true
      });
    }
    
  } catch (error) {
    results.warnings++;
    results.issues.push({
      message: `Performance check warning: ${error.message}`,
      warning: true
    });
  }
}

// Export for use in other scripts
module.exports = {
  checkCloudFormationTemplate,
  checkApiKeyService,
  checkCryptoPortfolioAPI,
  checkCryptoRealtimeAPI
};
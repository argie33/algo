#!/usr/bin/env node
/**
 * Platform Build Validation Script
 * Validates all crypto functionality and integration points after AWS permissions fix
 */

const fs = require('fs');
const path = require('path');

console.log('🏗️ Platform Build Validation - Crypto Features & API Integration');
console.log('=' .repeat(70));

const results = {
  passed: 0,
  failed: 0,
  warnings: 0,
  errors: [],
  warnings: []
};

// Test 1: Validate CloudFormation Template Permissions
console.log('\n🔧 Test 1: CloudFormation Template - AWS Permissions');
validateCloudFormationPermissions();

// Test 2: Validate API Key Service Implementation  
console.log('\n🔐 Test 2: API Key Service Implementation');
validateApiKeyService();

// Test 3: Validate Crypto Backend Routes
console.log('\n🚀 Test 3: Crypto Backend API Routes');
validateCryptoBackendRoutes();

// Test 4: Validate Frontend Components
console.log('\n🎨 Test 4: Frontend Crypto Components');
validateFrontendComponents();

// Test 5: Validate Route Integration
console.log('\n🔗 Test 5: Route Integration & App Configuration');
validateRouteIntegration();

// Test 6: Validate Sample Data & Fallbacks
console.log('\n📊 Test 6: Sample Data & Development Fallbacks');
validateSampleDataIntegration();

// Test 7: Validate Error Handling & Security
console.log('\n🛡️ Test 7: Error Handling & Security Patterns');
validateSecurityAndErrorHandling();

// Final Results
console.log('\n' + '=' .repeat(70));
console.log('📋 VALIDATION RESULTS SUMMARY');
console.log('=' .repeat(70));
console.log(`✅ Passed: ${results.passed}`);
console.log(`❌ Failed: ${results.failed}`);
console.log(`⚠️ Warnings: ${results.warnings}`);
console.log(`🎯 Success Rate: ${((results.passed / (results.passed + results.failed)) * 100).toFixed(1)}%`);

if (results.errors.length > 0) {
  console.log('\n🚨 CRITICAL ISSUES:');
  results.errors.forEach((error, index) => {
    console.log(`${index + 1}. ${error}`);
  });
}

if (results.warnings.length > 0) {
  console.log('\n⚠️ WARNINGS:');
  results.warnings.forEach((warning, index) => {
    console.log(`${index + 1}. ${warning}`);
  });
}

if (results.failed === 0) {
  console.log('\n🎉 PLATFORM BUILD VALIDATED! Ready for deployment and testing.');
  console.log('\n📝 Next Steps:');
  console.log('   1. Deploy CloudFormation template with updated IAM permissions');
  console.log('   2. Test API key storage/retrieval in AWS Lambda environment');
  console.log('   3. Validate crypto features with real API keys');
  console.log('   4. Perform end-to-end user workflow testing');
} else {
  console.log('\n⚠️ Some validation checks failed. Address critical issues before deployment.');
}

function validateCloudFormationPermissions() {
  try {
    const templatePath = path.join(__dirname, '..', 'template-webapp-lambda.yml');
    
    if (!fs.existsSync(templatePath)) {
      throw new Error('CloudFormation template not found');
    }
    
    const templateContent = fs.readFileSync(templatePath, 'utf8');
    
    // Check for SSM permissions
    const requiredSSMActions = [
      'ssm:GetParameter',
      'ssm:PutParameter', 
      'ssm:DeleteParameter',
      'ssm:GetParameters',
      'ssm:GetParametersByPath'
    ];
    
    const requiredKMSActions = [
      'kms:Decrypt',
      'kms:Encrypt',
      'kms:GenerateDataKey'
    ];
    
    let ssmPermissionsFound = 0;
    let kmsPermissionsFound = 0;
    
    for (const action of requiredSSMActions) {
      if (templateContent.includes(action)) {
        ssmPermissionsFound++;
      }
    }
    
    for (const action of requiredKMSActions) {
      if (templateContent.includes(action)) {
        kmsPermissionsFound++;
      }
    }
    
    if (ssmPermissionsFound === requiredSSMActions.length) {
      console.log('  ✅ SSM Parameter Store permissions configured');
      results.passed++;
    } else {
      throw new Error(`Missing SSM permissions: ${ssmPermissionsFound}/${requiredSSMActions.length} found`);
    }
    
    if (kmsPermissionsFound === requiredKMSActions.length) {
      console.log('  ✅ KMS encryption permissions configured');
      results.passed++;
    } else {
      throw new Error(`Missing KMS permissions: ${kmsPermissionsFound}/${requiredKMSActions.length} found`);
    }
    
    // Check for parameter path restriction
    if (templateContent.includes('/financial-platform/users/*')) {
      console.log('  ✅ Parameter path restrictions properly configured');
      results.passed++;
    } else {
      results.warnings.push('Parameter path restrictions not found - consider adding for security');
      results.warnings++;
    }
    
  } catch (error) {
    console.error('  ❌ CloudFormation validation failed:', error.message);
    results.failed++;
    results.errors.push(`CloudFormation: ${error.message}`);
  }
}

function validateApiKeyService() {
  try {
    const servicePath = path.join(__dirname, 'utils', 'simpleApiKeyService.js');
    
    if (!fs.existsSync(servicePath)) {
      throw new Error('simpleApiKeyService.js not found');
    }
    
    const serviceContent = fs.readFileSync(servicePath, 'utf8');
    
    // Check for required methods
    const requiredMethods = [
      'storeApiKey',
      'getApiKey', 
      'deleteApiKey',
      'listApiKeys',
      'healthCheck'
    ];
    
    let methodsFound = 0;
    for (const method of requiredMethods) {
      if (serviceContent.includes(`async ${method}(`) || serviceContent.includes(`${method}(`)) {
        methodsFound++;
      }
    }
    
    if (methodsFound === requiredMethods.length) {
      console.log('  ✅ All required API key service methods implemented');
      results.passed++;
    } else {
      throw new Error(`Missing methods: ${methodsFound}/${requiredMethods.length} found`);
    }
    
    // Check for AWS SDK v3 usage
    if (serviceContent.includes('@aws-sdk/client-ssm')) {
      console.log('  ✅ AWS SDK v3 properly imported');
      results.passed++;
    } else {
      throw new Error('AWS SDK v3 not properly imported');
    }
    
    // Check for encryption type
    if (serviceContent.includes("Type: 'SecureString'")) {
      console.log('  ✅ SecureString encryption configured');
      results.passed++;
    } else {
      throw new Error('SecureString encryption not configured');
    }
    
    // Check for parameter path encoding
    if (serviceContent.includes('encodeUserId') && serviceContent.includes('decodeUserId')) {
      console.log('  ✅ User ID encoding/decoding implemented');
      results.passed++;
    } else {
      results.warnings.push('User ID encoding not found - may cause issues with email addresses');
      results.warnings++;
    }
    
  } catch (error) {
    console.error('  ❌ API Key Service validation failed:', error.message);
    results.failed++;
    results.errors.push(`API Key Service: ${error.message}`);
  }
}

function validateCryptoBackendRoutes() {
  const routes = [
    {
      name: 'crypto-portfolio.js',
      requiredEndpoints: [
        'router.get.*/:user_id',
        'router.post.*/:user_id/buy',
        'router.post.*/:user_id/sell', 
        'router.get.*/:user_id/analytics',
        'router.get.*/:user_id/performance'
      ]
    },
    {
      name: 'crypto-realtime.js', 
      requiredEndpoints: [
        'router.get.*/prices',
        'router.get.*/market-pulse',
        'router.post.*/alerts',
        'router.get.*/historical'
      ]
    }
  ];
  
  for (const route of routes) {
    try {
      const routePath = path.join(__dirname, 'routes', route.name);
      
      if (!fs.existsSync(routePath)) {
        throw new Error(`${route.name} not found`);
      }
      
      const routeContent = fs.readFileSync(routePath, 'utf8');
      
      let endpointsFound = 0;
      for (const endpoint of route.requiredEndpoints) {
        if (new RegExp(endpoint).test(routeContent)) {
          endpointsFound++;
        }
      }
      
      if (endpointsFound === route.requiredEndpoints.length) {
        console.log(`  ✅ ${route.name} - All endpoints implemented (${endpointsFound}/${route.requiredEndpoints.length})`);
        results.passed++;
      } else {
        throw new Error(`${route.name} missing endpoints: ${endpointsFound}/${route.requiredEndpoints.length} found`);
      }
      
      // Check for error handling
      if (routeContent.includes('try {') && routeContent.includes('catch')) {
        console.log(`  ✅ ${route.name} - Error handling implemented`);
        results.passed++;
      } else {
        results.warnings.push(`${route.name} - Limited error handling found`);
        results.warnings++;
      }
      
    } catch (error) {
      console.error(`  ❌ ${route.name} validation failed:`, error.message);
      results.failed++;
      results.errors.push(`${route.name}: ${error.message}`);
    }
  }
}

function validateFrontendComponents() {
  const components = [
    {
      name: 'CryptoPortfolio.jsx',
      requiredFeatures: [
        'import.*React',
        'useState',
        'useEffect',
        'export default'
      ]
    },
    {
      name: 'CryptoRealTimeTracker.jsx',
      requiredFeatures: [
        'import.*React',
        'useState', 
        'useEffect',
        'export default'
      ]
    },
    {
      name: 'CryptoAdvancedAnalytics.jsx',
      requiredFeatures: [
        'import.*React',
        'useState',
        'useEffect', 
        'export default'
      ]
    }
  ];
  
  for (const component of components) {
    try {
      const componentPath = path.join(__dirname, '..', 'frontend', 'src', 'pages', component.name);
      
      if (!fs.existsSync(componentPath)) {
        throw new Error(`${component.name} not found`);
      }
      
      const componentContent = fs.readFileSync(componentPath, 'utf8');
      
      let featuresFound = 0;
      for (const feature of component.requiredFeatures) {
        if (new RegExp(feature).test(componentContent)) {
          featuresFound++;
        }
      }
      
      if (featuresFound === component.requiredFeatures.length) {
        console.log(`  ✅ ${component.name} - React component structure validated`);
        results.passed++;
      } else {
        throw new Error(`${component.name} missing features: ${featuresFound}/${component.requiredFeatures.length} found`);
      }
      
      // Check for Material-UI integration
      if (componentContent.includes('@mui/material') || componentContent.includes('Material-UI')) {
        console.log(`  ✅ ${component.name} - Material-UI integration found`);
        results.passed++;
      } else {
        results.warnings.push(`${component.name} - No Material-UI imports found`);
        results.warnings++;
      }
      
    } catch (error) {
      console.error(`  ❌ ${component.name} validation failed:`, error.message);
      results.failed++;
      results.errors.push(`${component.name}: ${error.message}`);
    }
  }
}

function validateRouteIntegration() {
  try {
    // Check Lambda index.js for route mounting
    const indexPath = path.join(__dirname, 'index.js');
    
    if (!fs.existsSync(indexPath)) {
      throw new Error('Lambda index.js not found');
    }
    
    const indexContent = fs.readFileSync(indexPath, 'utf8');
    
    // Check for crypto route mounting
    const cryptoRoutes = ['crypto-portfolio', 'crypto-realtime'];
    let routesMounted = 0;
    
    for (const route of cryptoRoutes) {
      if (indexContent.includes(route)) {
        routesMounted++;
      }
    }
    
    if (routesMounted === cryptoRoutes.length) {
      console.log('  ✅ Crypto routes properly mounted in Lambda');
      results.passed++;
    } else {
      throw new Error(`Crypto routes not mounted: ${routesMounted}/${cryptoRoutes.length} found`);
    }
    
    // Check frontend App.jsx for routing
    const appPath = path.join(__dirname, '..', 'frontend', 'src', 'App.jsx');
    
    if (!fs.existsSync(appPath)) {
      throw new Error('Frontend App.jsx not found');
    }
    
    const appContent = fs.readFileSync(appPath, 'utf8');
    
    const cryptoComponents = ['CryptoPortfolio', 'CryptoRealTimeTracker', 'CryptoAdvancedAnalytics'];
    let componentsImported = 0;
    
    for (const component of cryptoComponents) {
      if (appContent.includes(component)) {
        componentsImported++;
      }
    }
    
    if (componentsImported === cryptoComponents.length) {
      console.log('  ✅ Crypto components properly integrated in App.jsx');
      results.passed++;
    } else {
      throw new Error(`Crypto components not integrated: ${componentsImported}/${cryptoComponents.length} found`);
    }
    
  } catch (error) {
    console.error('  ❌ Route integration validation failed:', error.message);
    results.failed++;
    results.errors.push(`Route integration: ${error.message}`);
  }
}

function validateSampleDataIntegration() {
  try {
    const sampleDataPath = path.join(__dirname, 'utils', 'sample-data-store.js');
    
    if (!fs.existsSync(sampleDataPath)) {
      throw new Error('sample-data-store.js not found');
    }
    
    const sampleContent = fs.readFileSync(sampleDataPath, 'utf8');
    
    // Check for comprehensive sample data
    if (sampleContent.includes('SAMPLE_STOCKS') && sampleContent.includes('SAMPLE_PORTFOLIO')) {
      console.log('  ✅ Sample data structures found');
      results.passed++;
    } else {
      throw new Error('Sample data structures missing');
    }
    
    // Check for screening function
    if (sampleContent.includes('getScreenerResults')) {
      console.log('  ✅ Stock screening function implemented');
      results.passed++;
    } else {
      throw new Error('Stock screening function missing');
    }
    
    // Count sample stocks
    const stockMatches = sampleContent.match(/symbol: ['"`][\w.]+['"`]/g);
    if (stockMatches && stockMatches.length >= 10) {
      console.log(`  ✅ Comprehensive sample data (${stockMatches.length} stocks)`);
      results.passed++;
    } else {
      results.warnings.push('Limited sample data - consider adding more stocks for testing');
      results.warnings++;
    }
    
  } catch (error) {
    console.error('  ❌ Sample data validation failed:', error.message);
    results.failed++;
    results.errors.push(`Sample data: ${error.message}`);
  }
}

function validateSecurityAndErrorHandling() {
  try {
    // Check for input validation
    const validationPath = path.join(__dirname, 'middleware', 'inputValidation.js');
    
    if (fs.existsSync(validationPath)) {
      console.log('  ✅ Input validation middleware found');
      results.passed++;
    } else {
      results.warnings.push('Input validation middleware not found');
      results.warnings++;
    }
    
    // Check for rate limiting
    const rateLimitPath = path.join(__dirname, 'middleware', 'rateLimiting.js');
    
    if (fs.existsSync(rateLimitPath)) {
      console.log('  ✅ Rate limiting middleware found');
      results.passed++;
    } else {
      results.warnings.push('Rate limiting middleware not found');
      results.warnings++;
    }
    
    // Check for comprehensive error handling
    const errorHandlerPath = path.join(__dirname, 'utils', 'comprehensiveErrorHandler.js');
    
    if (fs.existsSync(errorHandlerPath)) {
      console.log('  ✅ Comprehensive error handler found');
      results.passed++;
    } else {
      results.warnings.push('Comprehensive error handler not found');
      results.warnings++;
    }
    
    // Check API key service for proper error handling
    const apiKeyPath = path.join(__dirname, 'utils', 'simpleApiKeyService.js');
    const apiKeyContent = fs.readFileSync(apiKeyPath, 'utf8');
    
    if (apiKeyContent.includes('try {') && apiKeyContent.includes('catch') && apiKeyContent.includes('throw new Error')) {
      console.log('  ✅ API key service error handling validated');
      results.passed++;
    } else {
      results.warnings.push('API key service error handling could be improved');
      results.warnings++;
    }
    
  } catch (error) {
    console.error('  ❌ Security validation failed:', error.message);
    results.failed++;
    results.errors.push(`Security: ${error.message}`);
  }
}

// Run if called directly
if (require.main === module) {
  process.exit(results.failed > 0 ? 1 : 0);
}

module.exports = { validateCloudFormationPermissions, validateApiKeyService };
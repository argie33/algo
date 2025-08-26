#!/usr/bin/env node

/**
 * DEPLOYMENT-READY VALIDATION SUITE
 * 
 * Comprehensive pre-deployment validation to prevent React Context errors
 * and other runtime issues from reaching production.
 * 
 * This suite validates all the fixes implemented to catch the error:
 * "Cannot set properties of undefined (setting 'ContextConsumer')"
 */

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

console.log('🚀 DEPLOYMENT-READY VALIDATION SUITE');
console.log('=====================================');
console.log('Comprehensive validation to prevent React Context errors in production');
console.log('');

let allTestsPassed = true;
const results = [];

function runTest(name, command, description) {
  console.log(`📋 ${name}: ${description}`);
  console.log(`   Command: ${command}`);
  
  try {
    const startTime = Date.now();
    const output = execSync(command, { 
      stdio: 'pipe', 
      encoding: 'utf8',
      timeout: 180000 // 3 minutes timeout
    });
    const duration = Date.now() - startTime;
    
    console.log(`   ✅ PASSED (${duration}ms)`);
    results.push({
      name,
      status: 'PASSED',
      duration,
      output: output.substring(0, 200) + (output.length > 200 ? '...' : '')
    });
    return true;
  } catch (error) {
    console.log(`   ❌ FAILED (exit code: ${error.status})`);
    console.log(`   Error: ${error.message.substring(0, 300)}...`);
    results.push({
      name,
      status: 'FAILED',
      error: error.message.substring(0, 300),
      exitCode: error.status
    });
    allTestsPassed = false;
    return false;
  }
}

// VALIDATION LAYER 1: Dependency Validation
console.log('\n🔍 LAYER 1: DEPENDENCY VALIDATION');
console.log('----------------------------------');

runTest(
  'Dependency Conflict Detection',
  'npm run test:dep',
  'Validates react-is@^18.3.1 override and hoist-non-react-statics compatibility'
);

runTest(
  'Package JSON Override Verification',
  'node -e "const pkg = require(\'./package.json\'); if (pkg.overrides[\'react-is\'] !== \'^18.3.1\') throw new Error(\'react-is override missing\'); console.log(\'✅ react-is override confirmed:\', pkg.overrides[\'react-is\']);"',
  'Confirms package.json overrides are properly configured'
);

// VALIDATION LAYER 2: Build Process Validation
console.log('\n🏗️ LAYER 2: BUILD PROCESS VALIDATION');
console.log('------------------------------------');

runTest(
  'Enhanced Build Process',
  'npm run build',
  'Runs enhanced build with dependency validation (test:dep + vite build)'
);

runTest(
  'Linting with Context Validation',
  'npm run lint',
  'ESLint validation with proper React Context usage patterns'
);

// VALIDATION LAYER 3: Integration Testing
console.log('\n🧪 LAYER 3: INTEGRATION TESTING');
console.log('--------------------------------');

runTest(
  'React Context Dependency Integration Test',
  'npx vitest run src/tests/integration/react-context-dependency.test.jsx --reporter=basic',
  'Comprehensive React Context compatibility testing with real AuthContext'
);

runTest(
  'Unit Test Suite',
  'npm run test:unit',
  'Complete unit test suite with Context provider testing'
);

runTest(
  'Component Integration Tests',
  'npm run test:component',
  'Component-level integration testing with Context consumers'
);

// VALIDATION LAYER 4: End-to-End Runtime Validation
console.log('\n🌐 LAYER 4: END-TO-END RUNTIME VALIDATION');
console.log('------------------------------------------');

runTest(
  'Critical Flows E2E (Runtime Error Detection)',
  'VITE_API_URL=http://localhost:3001 PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS=1 timeout 60s npx playwright test critical-flows.spec.js --project=desktop-chrome --reporter=line --timeout=15000 --max-failures=1',
  'E2E tests with console error monitoring (catches React Context errors)'
);

runTest(
  'API Error Handling (Malformed Data)',
  'VITE_API_URL=http://localhost:3001 PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS=1 timeout 30s npx playwright test api-error-handling.spec.js --project=desktop-chrome --reporter=line --timeout=10000 -g "malformed JSON" --max-failures=1',
  'API error handling with malformed JSON response validation'
);

// VALIDATION LAYER 5: Production Simulation
console.log('\n🚀 LAYER 5: PRODUCTION SIMULATION');
console.log('----------------------------------');

runTest(
  'Production Build Validation',
  'NODE_ENV=production npm run build',
  'Production build with all optimizations and dependency checks'
);

runTest(
  'Bundle Analysis',
  'node -e "const fs = require(\'fs\'); const stats = fs.statSync(\'dist/assets/index*.js\'); console.log(\'Bundle size:\', (stats.size / 1024).toFixed(2), \'KB\'); if (stats.size > 2000000) throw new Error(\'Bundle too large\');"',
  'Bundle size validation and dependency analysis'
);

// RESULTS SUMMARY
console.log('\n📊 VALIDATION RESULTS SUMMARY');
console.log('==============================');

const passedTests = results.filter(r => r.status === 'PASSED').length;
const failedTests = results.filter(r => r.status === 'FAILED').length;

console.log(`Total Tests: ${results.length}`);
console.log(`✅ Passed: ${passedTests}`);
console.log(`❌ Failed: ${failedTests}`);
console.log('');

if (allTestsPassed) {
  console.log('🎉 ALL VALIDATIONS PASSED!');
  console.log('');
  console.log('✅ DEPLOYMENT READY - React Context Error Prevention Confirmed');
  console.log('');
  console.log('Multi-layered protection verified:');
  console.log('  🔍 Dependency validation catches react-is conflicts');
  console.log('  🏗️ Build process includes dependency checks');
  console.log('  🧪 Integration tests validate Context compatibility');
  console.log('  🌐 E2E tests monitor runtime errors');
  console.log('  🚀 Production builds include all validations');
  console.log('');
  console.log('The error "Cannot set properties of undefined (setting \'ContextConsumer\')"');
  console.log('will be caught by MULTIPLE validation layers before reaching production.');
  
  process.exit(0);
} else {
  console.log('🚨 DEPLOYMENT BLOCKED - Validation Failures Detected');
  console.log('');
  console.log('Failed validations:');
  results
    .filter(r => r.status === 'FAILED')
    .forEach(r => {
      console.log(`  ❌ ${r.name}: Exit code ${r.exitCode}`);
      if (r.error) {
        console.log(`     ${r.error}`);
      }
    });
  console.log('');
  console.log('🛠️ Fix the failing validations before deploying to production.');
  
  process.exit(1);
}
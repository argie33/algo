#!/usr/bin/env node

/**
 * Playwright Setup Verification Script
 * Verifies that the comprehensive test suite is properly configured
 */

import fs from 'fs';
import { execSync } from 'child_process';

const testFiles = [
  'src/tests/e2e/critical-flows.spec.js',
  'src/tests/e2e/visual-regression.visual.spec.js', 
  'src/tests/e2e/accessibility.accessibility.spec.js',
  'src/tests/e2e/performance.perf.spec.js',
  'src/tests/e2e/dev-server-validation.test.js',
  'src/tests/e2e/auth.setup.js',
  'src/tests/e2e/global-setup.js',
  'src/tests/e2e/global-teardown.js'
];

const configFiles = [
  'playwright.config.js',
  'playwright.config.ci.js'
];

const requiredDependencies = [
  '@playwright/test',
  '@axe-core/playwright'
];

console.log('🧪 Verifying Playwright Test Suite Setup...\n');

// Check test files
console.log('📁 Checking test files...');
let missingFiles = [];
for (const file of testFiles) {
  if (fs.existsSync(file)) {
    console.log(`  ✅ ${file}`);
  } else {
    console.log(`  ❌ ${file}`);
    missingFiles.push(file);
  }
}

// Check configuration files
console.log('\n⚙️ Checking configuration files...');
let missingConfigs = [];
for (const config of configFiles) {
  if (fs.existsSync(config)) {
    console.log(`  ✅ ${config}`);
  } else {
    console.log(`  ❌ ${config}`);
    missingConfigs.push(config);
  }
}

// Check dependencies
console.log('\n📦 Checking dependencies...');
const packageJson = JSON.parse(fs.readFileSync('package.json', 'utf8'));
const allDeps = { ...packageJson.dependencies, ...packageJson.devDependencies };
let missingDeps = [];
for (const dep of requiredDependencies) {
  if (allDeps[dep]) {
    console.log(`  ✅ ${dep} (${allDeps[dep]})`);
  } else {
    console.log(`  ❌ ${dep}`);
    missingDeps.push(dep);
  }
}

// Check test scripts
console.log('\n🚀 Checking npm test scripts...');
const expectedScripts = [
  'test:validation',
  'test:e2e', 
  'test:e2e:critical',
  'test:e2e:visual',
  'test:e2e:a11y',
  'test:e2e:perf',
  'test:e2e:mobile',
  'test:e2e:report'
];

let missingScripts = [];
for (const script of expectedScripts) {
  if (packageJson.scripts[script]) {
    console.log(`  ✅ npm run ${script}`);
  } else {
    console.log(`  ❌ npm run ${script}`);
    missingScripts.push(script);
  }
}

// Test discovery
console.log('\n🔍 Testing Playwright test discovery...');
try {
  const listOutput = execSync('PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS=1 npx playwright test --list', { encoding: 'utf8' });
  const testCount = (listOutput.match(/Total: (\d+) tests/)?.[1]) || '0';
  console.log(`  ✅ Discovered ${testCount} tests`);
  
  if (parseInt(testCount) < 200) {
    console.log(`  ⚠️ Expected ~245 tests, found ${testCount}. Some test projects may not be configured correctly.`);
  }
} catch (error) {
  console.log(`  ❌ Test discovery failed: ${error.message}`);
}

// Test validation script
console.log('\n🧹 Testing validation script...');
try {
  execSync('npm run test:validation', { encoding: 'utf8', stdio: 'pipe' });
  console.log('  ✅ Validation tests pass');
} catch (error) {
  console.log('  ❌ Validation tests failed');
  console.log(`     Error: ${error.message}`);
}

// Summary
console.log('\n📊 Setup Verification Summary:');
const issues = missingFiles.length + missingConfigs.length + missingDeps.length + missingScripts.length;

if (issues === 0) {
  console.log('✅ Perfect! Comprehensive Playwright test suite is fully configured.');
  console.log('\n🚀 Ready to run:');
  console.log('   npm run test:validation  # Basic validation (works without browser deps)');
  console.log('   npm run test:e2e         # Full test suite (requires: sudo npx playwright install-deps)');
} else {
  console.log(`❌ Found ${issues} issues that need to be fixed:`);
  if (missingFiles.length > 0) console.log(`   Missing test files: ${missingFiles.join(', ')}`);
  if (missingConfigs.length > 0) console.log(`   Missing config files: ${missingConfigs.join(', ')}`);
  if (missingDeps.length > 0) console.log(`   Missing dependencies: ${missingDeps.join(', ')}`);
  if (missingScripts.length > 0) console.log(`   Missing npm scripts: ${missingScripts.join(', ')}`);
}

console.log('\n📚 For detailed instructions, see: TESTING.md');
console.log('💡 To run full test suite: sudo npx playwright install-deps && npm run test:e2e');
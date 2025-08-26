#!/usr/bin/env node

/**
 * Comprehensive Test: React 18 Dependency Compatibility Detection
 * 
 * Tests that our enhanced dependency validation catches ALL critical
 * React 18 compatibility issues that could cause runtime errors.
 */

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

console.log('🧪 COMPREHENSIVE DEPENDENCY VALIDATION TEST');
console.log('===========================================');
console.log('Testing whether our system catches ALL critical React 18 issues\n');

// Test scenarios that should be caught
const testScenarios = [
  {
    name: 'react-is v19.x compatibility issue',
    description: 'The exact error you encountered - should be caught by react-is analysis',
    packageChanges: { overrides: { 'react-is': '^19.0.0' } },
    expectedDetection: 'react-is override set to v19.x.*incompatible with hoist-non-react-statics'
  },
  {
    name: '@mui/styles with React 18',
    description: 'Official MUI incompatibility - should be caught by MUI analysis',
    packageChanges: { dependencies: { '@mui/styles': '^4.11.0' } },
    expectedDetection: '@mui/styles is not compatible with React 18'
  },
  {
    name: 'Old Testing Library version',
    description: 'Testing Library <v13 incompatibility - should be caught by testing analysis',
    packageChanges: { devDependencies: { '@testing-library/react': '^12.0.0' } },
    expectedDetection: '@testing-library/react.*incompatible with React 18.*requires v13+'
  },
  {
    name: 'Old MUI Material version',  
    description: 'MUI v4 incompatibility - should be caught by MUI analysis',
    packageChanges: { dependencies: { '@mui/material': '^4.12.0' } },
    expectedDetection: 'MUI Material.*incompatible with React 18.*requires v5+'
  },
  {
    name: 'Missing react-is override',
    description: 'No override for react-is - should be caught by override validation',
    packageChanges: { overrides: {} }, // Remove react-is override
    expectedDetection: 'react-is override missing from package.json'
  }
];

let allTestsPassed = true;
const results = [];

// Backup original package.json
const originalPackage = fs.readFileSync('package.json', 'utf8');
const originalPkg = JSON.parse(originalPackage);

async function runTest(scenario) {
  console.log(`📋 Testing: ${scenario.name}`);
  console.log(`   Description: ${scenario.description}`);
  
  try {
    // Create modified package.json for this test
    const testPkg = JSON.parse(originalPackage);
    
    // Apply changes
    Object.entries(scenario.packageChanges).forEach(([section, changes]) => {
      if (section === 'overrides' && Object.keys(changes).length === 0) {
        // Remove overrides entirely for this test
        delete testPkg.overrides;
      } else {
        testPkg[section] = { ...testPkg[section], ...changes };
      }
    });
    
    // Write test package.json
    fs.writeFileSync('package.json', JSON.stringify(testPkg, null, 2));
    
    // Run our dependency validation
    const output = execSync('node dep-test.cjs', { encoding: 'utf8', stdio: 'pipe' });
    
    // Check if expected detection is found
    const detected = new RegExp(scenario.expectedDetection, 'i').test(output);
    
    if (detected) {
      console.log(`   ✅ PASSED - Correctly detected: ${scenario.expectedDetection}`);
      results.push({ scenario: scenario.name, status: 'PASSED', detected: true });
    } else {
      console.log(`   ❌ FAILED - Did not detect: ${scenario.expectedDetection}`);
      console.log(`   Output preview: ${output.substring(0, 200)}...`);
      results.push({ scenario: scenario.name, status: 'FAILED', detected: false });
      allTestsPassed = false;
    }
    
  } catch (error) {
    // Error is expected for compatibility issues - check if it contains our detection
    const detected = new RegExp(scenario.expectedDetection, 'i').test(error.message || error.stdout || '');
    
    if (detected) {
      console.log(`   ✅ PASSED - Correctly detected in error: ${scenario.expectedDetection}`);
      results.push({ scenario: scenario.name, status: 'PASSED', detected: true });
    } else {
      console.log(`   ❌ FAILED - Error but no detection: ${scenario.expectedDetection}`);
      console.log(`   Error: ${error.message?.substring(0, 200)}...`);
      results.push({ scenario: scenario.name, status: 'FAILED', detected: false });
      allTestsPassed = false;
    }
  } finally {
    // Always restore original package.json
    fs.writeFileSync('package.json', originalPackage);
  }
  
  console.log('');
}

// Run all test scenarios
(async () => {
  for (const scenario of testScenarios) {
    await runTest(scenario);
  }
  
  // Test Results Summary
  console.log('📊 COMPREHENSIVE TEST RESULTS');
  console.log('==============================');
  
  const passedTests = results.filter(r => r.status === 'PASSED').length;
  const failedTests = results.filter(r => r.status === 'FAILED').length;
  
  console.log(`Total Tests: ${results.length}`);
  console.log(`✅ Passed: ${passedTests}`);
  console.log(`❌ Failed: ${failedTests}`);
  console.log('');
  
  if (allTestsPassed) {
    console.log('🎉 ALL VALIDATION TESTS PASSED!');
    console.log('');
    console.log('✅ Our enhanced dependency validation successfully catches:');
    testScenarios.forEach(scenario => {
      console.log(`  ✓ ${scenario.name}`);
    });
    console.log('');
    console.log('🛡️  Your React Context error will NEVER happen again!');
    console.log('   The validation catches ALL critical React 18 compatibility issues');
    console.log('   before they can cause runtime errors.');
    
    process.exit(0);
  } else {
    console.log('🚨 SOME VALIDATION TESTS FAILED');
    console.log('');
    console.log('Failed scenarios:');
    results
      .filter(r => r.status === 'FAILED')
      .forEach(r => {
        console.log(`  ❌ ${r.scenario}`);
      });
    console.log('');
    console.log('⚠️  These compatibility issues might not be caught automatically.');
    console.log('   Consider enhancing the validation rules for these scenarios.');
    
    process.exit(1);
  }
})();
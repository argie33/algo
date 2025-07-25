#!/usr/bin/env node

/**
 * Auth Middleware Fix Verification Test
 * Validates that all route files use proper auth middleware imports
 */

const fs = require('fs');
const path = require('path');

async function testAuthMiddlewareFixes() {
  console.log('🔐 Testing Auth Middleware Import Fixes...\n');
  
  const testResults = {
    filesChecked: 0,
    correctImports: 0,
    incorrectImports: 0,
    authUsageCorrect: 0,
    authUsageIncorrect: 0,
    issues: [],
    overallSuccess: false
  };

  try {
    const routesDir = path.join(__dirname, 'routes');
    const routeFiles = fs.readdirSync(routesDir).filter(file => file.endsWith('.js'));
    
    console.log(`📁 Found ${routeFiles.length} route files to check`);
    console.log('=' .repeat(60));

    for (const file of routeFiles) {
      const filePath = path.join(routesDir, file);
      const content = fs.readFileSync(filePath, 'utf8');
      testResults.filesChecked++;
      
      // Test 1: Check for correct import pattern
      const hasCorrectImport = content.includes("const { authenticateToken") || 
                              content.includes("const { authenticateUser, authenticateToken") ||
                              content.includes("const { authenticateToken, authenticateUser");
      
      const hasIncorrectImport = content.includes("const auth = require('../middleware/auth')") && 
                                !hasCorrectImport;
      
      // Test 2: Check for proper auth usage in routes
      const authUsagePatterns = [
        /router\.\w+\([^,]+,\s*authenticateToken/g,
        /router\.\w+\([^,]+,\s*authenticateUser/g
      ];
      
      const incorrectAuthUsage = /router\.\w+\([^,]+,\s*auth,/g;
      
      let hasCorrectAuthUsage = false;
      let hasIncorrectAuthUsage = false;
      
      for (const pattern of authUsagePatterns) {
        if (pattern.test(content)) {
          hasCorrectAuthUsage = true;
          break;
        }
      }
      
      if (incorrectAuthUsage.test(content)) {
        hasIncorrectAuthUsage = true;
      }
      
      // Record results
      if (hasCorrectImport) {
        testResults.correctImports++;
      } else if (hasIncorrectImport) {
        testResults.incorrectImports++;
        testResults.issues.push(`${file}: Uses old auth import pattern`);
      }
      
      if (hasCorrectAuthUsage) {
        testResults.authUsageCorrect++;
      }
      
      if (hasIncorrectAuthUsage) {
        testResults.authUsageIncorrect++;
        testResults.issues.push(`${file}: Uses incorrect auth middleware in routes`);
      }
      
      // Report per file
      let status = '✅';
      if (hasIncorrectImport || hasIncorrectAuthUsage) {
        status = '❌';
      } else if (!hasCorrectImport && !hasCorrectAuthUsage) {
        status = '⚠️';  // No auth middleware used
      }
      
      console.log(`${status} ${file.padEnd(35)} | Import: ${hasCorrectImport ? '✅' : hasIncorrectImport ? '❌' : '⚠️'} | Usage: ${hasCorrectAuthUsage ? '✅' : hasIncorrectAuthUsage ? '❌' : '⚠️'}`);
    }

    // Test specific critical files
    console.log('\n🎯 Critical File Validation:');
    console.log('=' .repeat(60));
    
    const criticalFiles = ['hftTrading.js', 'portfolio.js', 'liveData.js', 'unified-api-keys.js'];
    
    for (const criticalFile of criticalFiles) {
      const filePath = path.join(routesDir, criticalFile);
      if (fs.existsSync(filePath)) {
        const content = fs.readFileSync(filePath, 'utf8');
        
        const hasDestructuredImport = content.includes('const { authenticateToken }');
        const usesAuthenticateToken = content.includes('authenticateToken,');
        const noOldAuthUsage = !content.includes(', auth,');
        
        const isValid = hasDestructuredImport && usesAuthenticateToken && noOldAuthUsage;
        
        console.log(`${isValid ? '✅' : '❌'} ${criticalFile.padEnd(25)} | Valid: ${isValid}`);
        
        if (!isValid) {
          testResults.issues.push(`CRITICAL: ${criticalFile} has auth middleware issues`);
        }
      } else {
        console.log(`⚠️  ${criticalFile.padEnd(25)} | File not found`);
      }
    }

    // Summary
    console.log('\n📊 Auth Middleware Fix Test Results');
    console.log('=' .repeat(60));
    console.log(`📁 Files Checked: ${testResults.filesChecked}`);
    console.log(`✅ Correct Imports: ${testResults.correctImports}`);
    console.log(`❌ Incorrect Imports: ${testResults.incorrectImports}`);
    console.log(`✅ Correct Auth Usage: ${testResults.authUsageCorrect}`);
    console.log(`❌ Incorrect Auth Usage: ${testResults.authUsageIncorrect}`);
    
    if (testResults.issues.length > 0) {
      console.log('\n⚠️  Issues Found:');
      testResults.issues.forEach(issue => console.log(`   - ${issue}`));
    }
    
    testResults.overallSuccess = testResults.incorrectImports === 0 && testResults.authUsageIncorrect === 0;
    
    console.log(`\n🎯 Overall Result: ${testResults.overallSuccess ? '✅ PASS' : '❌ FAIL'}`);
    
    if (testResults.overallSuccess) {
      console.log('\n🎉 All auth middleware imports and usage are correct!');
      console.log('✅ Ready to proceed with Phase 2 real API integration');
    } else {
      console.log('\n⚠️  Some auth middleware issues need to be fixed before proceeding');
    }

    return testResults;

  } catch (error) {
    console.error('🔥 Auth middleware test failed:', error);
    return { ...testResults, overallSuccess: false };
  }
}

// Run the test if called directly
if (require.main === module) {
  testAuthMiddlewareFixes()
    .then(results => {
      process.exit(results.overallSuccess ? 0 : 1);
    })
    .catch(error => {
      console.error('Test execution failed:', error);
      process.exit(1);
    });
}

module.exports = { testAuthMiddlewareFixes };
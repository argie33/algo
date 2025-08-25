#!/usr/bin/env node

/**
 * Test Infrastructure Validation Script
 * Validates that all test systems are working correctly
 */

const { execSync, spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

console.log('🧪 Financial Platform Test Infrastructure Validation\n');

const results = {
  backend: { passing: 0, failing: 0, total: 0 },
  frontend: { passing: 0, failing: 0, total: 0 },
  e2e: { passing: 0, failing: 0, total: 0 },
  integration: { passing: 0, failing: 0, total: 0 }
};

async function runCommand(command, cwd, description) {
  console.log(`\n📋 ${description}...`);
  console.log(`💻 Running: ${command}`);
  
  return new Promise((resolve) => {
    const [cmd, ...args] = command.split(' ');
    const child = spawn(cmd, args, { 
      cwd,
      stdio: ['pipe', 'pipe', 'pipe'],
      env: { ...process.env, NODE_ENV: 'test' }
    });

    let stdout = '';
    let stderr = '';
    
    child.stdout.on('data', (data) => {
      stdout += data.toString();
    });
    
    child.stderr.on('data', (data) => {
      stderr += data.toString();
    });
    
    child.on('close', (code) => {
      const success = code === 0;
      console.log(success ? '✅ PASSED' : '❌ FAILED');
      
      if (success) {
        // Extract test counts from output
        const testCounts = extractTestCounts(stdout + stderr);
        console.log(`📊 Tests: ${testCounts.passing} passed, ${testCounts.failing} failed, ${testCounts.total} total`);
        resolve({ success: true, ...testCounts, output: stdout });
      } else {
        console.log(`❌ Exit code: ${code}`);
        if (stderr) {
          console.log('Error output:', stderr.substring(0, 500));
        }
        resolve({ success: false, passing: 0, failing: 1, total: 1, output: stdout + stderr });
      }
    });
    
    // Timeout after 60 seconds
    setTimeout(() => {
      child.kill();
      console.log('⏰ Command timed out');
      resolve({ success: false, passing: 0, failing: 1, total: 1, output: 'Timeout' });
    }, 60000);
  });
}

function extractTestCounts(output) {
  // Extract test counts from various test runner outputs
  let passing = 0, failing = 0, total = 0;
  
  // Jest/Vitest patterns
  const jestMatch = output.match(/(\d+)\s+passed.*?(\d+)\s+failed.*?(\d+)\s+total/i);
  if (jestMatch) {
    passing = parseInt(jestMatch[1]);
    failing = parseInt(jestMatch[2]); 
    total = parseInt(jestMatch[3]);
    return { passing, failing, total };
  }
  
  // Playwright patterns
  const playwrightMatch = output.match(/(\d+)\s+passed.*?(\d+)\s+failed/i);
  if (playwrightMatch) {
    passing = parseInt(playwrightMatch[1]);
    failing = parseInt(playwrightMatch[2]);
    total = passing + failing;
    return { passing, failing, total };
  }
  
  // Simple patterns
  const simplePass = output.match(/(\d+)\s+passed/i);
  const simpleFail = output.match(/(\d+)\s+failed/i);
  
  if (simplePass) passing = parseInt(simplePass[1]);
  if (simpleFail) failing = parseInt(simpleFail[1]);
  total = passing + failing;
  
  return { passing, failing, total };
}

async function validateTestInfrastructure() {
  const backendPath = path.join(__dirname, 'webapp/lambda');
  const frontendPath = path.join(__dirname, 'webapp/frontend');
  
  console.log('🔧 Validating test infrastructure setup...\n');
  
  // 1. Backend Unit Tests
  console.log('='.repeat(60));
  console.log('🚀 BACKEND UNIT TESTS');
  console.log('='.repeat(60));
  
  const backendResult = await runCommand(
    'npm test -- tests/unit/simple.test.js --verbose --no-coverage',
    backendPath,
    'Backend Unit Tests (Simple)'
  );
  
  results.backend.passing += backendResult.passing;
  results.backend.failing += backendResult.failing;
  results.backend.total += backendResult.total;
  
  // 2. Frontend Unit Tests
  console.log('\n' + '='.repeat(60));
  console.log('⚛️  FRONTEND UNIT TESTS');
  console.log('='.repeat(60));
  
  const frontendResult = await runCommand(
    'npx vitest run src/tests/simple.test.jsx',
    frontendPath,
    'Frontend Unit Tests (Simple)'
  );
  
  results.frontend.passing += frontendResult.passing;
  results.frontend.failing += frontendResult.failing;
  results.frontend.total += frontendResult.total;
  
  // 3. Integration Tests (Backend)
  console.log('\n' + '='.repeat(60));
  console.log('🔗 INTEGRATION TESTS');
  console.log('='.repeat(60));
  
  const integrationResult = await runCommand(
    'npm test -- tests/integration/security/api-key-encryption.integration.test.js --verbose --no-coverage',
    backendPath,
    'API Key Encryption Integration'
  );
  
  results.integration.passing += integrationResult.passing;
  results.integration.failing += integrationResult.failing;
  results.integration.total += integrationResult.total;
  
  // 4. Generate Summary Report
  console.log('\n' + '='.repeat(80));
  console.log('📊 TEST INFRASTRUCTURE VALIDATION SUMMARY');
  console.log('='.repeat(80));
  
  const totalPassing = results.backend.passing + results.frontend.passing + results.integration.passing;
  const totalFailing = results.backend.failing + results.frontend.failing + results.integration.failing;
  const totalTests = results.backend.total + results.frontend.total + results.integration.total;
  
  console.log(`\n🚀 Backend Tests:     ${results.backend.passing}/${results.backend.total} passing`);
  console.log(`⚛️  Frontend Tests:    ${results.frontend.passing}/${results.frontend.total} passing`);
  console.log(`🔗 Integration Tests: ${results.integration.passing}/${results.integration.total} passing`);
  console.log(`\n📈 Overall Results:   ${totalPassing}/${totalTests} tests passing (${((totalPassing/totalTests)*100).toFixed(1)}%)`);
  
  // 5. Assessment
  const healthScore = (totalPassing / totalTests) * 100;
  let status = 'UNKNOWN';
  let recommendation = '';
  
  if (healthScore >= 90) {
    status = '🟢 EXCELLENT';
    recommendation = 'Test infrastructure is working well. Ready for development.';
  } else if (healthScore >= 70) {
    status = '🟡 GOOD';
    recommendation = 'Test infrastructure is mostly working. Minor issues to address.';
  } else if (healthScore >= 50) {
    status = '🟠 NEEDS WORK';
    recommendation = 'Test infrastructure has issues that should be fixed before major development.';
  } else {
    status = '🔴 CRITICAL';
    recommendation = 'Test infrastructure needs immediate attention before continuing development.';
  }
  
  console.log(`\n📋 Infrastructure Status: ${status}`);
  console.log(`💡 Recommendation: ${recommendation}`);
  
  // 6. Next Steps
  console.log('\n📝 NEXT STEPS:');
  
  if (results.backend.failing > 0) {
    console.log('• Fix failing backend tests');
  }
  if (results.frontend.failing > 0) {
    console.log('• Fix failing frontend tests');  
  }
  if (results.integration.failing > 0) {
    console.log('• Fix failing integration tests');
  }
  
  if (totalFailing === 0) {
    console.log('• ✅ All basic tests passing - test infrastructure ready!');
    console.log('• Run full test suites: npm run test:comprehensive (backend), npm run test:ci (frontend)');
    console.log('• Set up E2E tests with proper development server');
  }
  
  console.log('\n' + '='.repeat(80));
  
  return healthScore >= 70;
}

// Run validation
validateTestInfrastructure()
  .then(success => {
    process.exit(success ? 0 : 1);
  })
  .catch(error => {
    console.error('❌ Validation failed:', error);
    process.exit(1);
  });
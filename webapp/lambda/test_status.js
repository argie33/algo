const { exec } = require('child_process');

const testTargets = [
  'tests/integration/routes/insider.integration.test.js',
  'tests/integration/routes/economic.integration.test.js',
  'tests/unit/routes/trades.test.js'
];

async function runTest(testPath) {
  return new Promise((resolve) => {
    exec(`timeout 30 npm test -- "${testPath}" 2>&1`, (error, stdout, stderr) => {
      const output = stdout + stderr;
      const passMatch = output.match(/Tests:\s+(\d+)\s+passed/);
      const failMatch = output.match(/(\d+)\s+failed/);
      const totalMatch = output.match(/(\d+)\s+total/);

      const passed = passMatch ? parseInt(passMatch[1]) : 0;
      const failed = failMatch ? parseInt(failMatch[1]) : 0;
      const total = totalMatch ? parseInt(totalMatch[1]) : 0;

      resolve({
        testPath: testPath.split('/').pop(),
        passed,
        failed,
        total,
        status: failed === 0 ? 'PASS' : 'FAIL'
      });
    });
  });
}

async function checkAllTests() {
  console.log('📊 Checking test status...\n');

  for (const testPath of testTargets) {
    const result = await runTest(testPath);
    const emoji = result.status === 'PASS' ? '✅' : '❌';
    console.log(`${emoji} ${result.testPath}: ${result.passed}/${result.total} passed, ${result.failed} failed (${result.status})`);
  }

  console.log('\n🎯 Test Summary Complete');
}

checkAllTests().catch(console.error);
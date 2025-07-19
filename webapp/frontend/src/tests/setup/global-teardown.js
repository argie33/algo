/**
 * Global Teardown for Integration Tests
 * Runs after all tests to clean up the testing environment
 */

export default async function globalTeardown() {
  console.log('🧹 Starting global teardown for integration tests...');
  
  const fs = await import('fs');
  const path = await import('path');
  
  // Cleanup temporary files
  const tempDir = '/tmp';
  try {
    const tempFiles = fs.readdirSync(tempDir).filter(file => 
      file.startsWith('test-') || file.includes('playwright')
    );
    
    tempFiles.forEach(file => {
      try {
        fs.unlinkSync(path.join(tempDir, file));
      } catch (error) {
        // Ignore cleanup errors
      }
    });
    
    if (tempFiles.length > 0) {
      console.log(`🗑️ Cleaned up ${tempFiles.length} temporary files`);
    }
  } catch (error) {
    // Ignore cleanup errors
  }
  
  // Generate test summary
  const testResultsDir = path.join(process.cwd(), 'test-results');
  if (fs.existsSync(testResultsDir)) {
    try {
      const resultsFile = path.join(testResultsDir, 'test-results.json');
      if (fs.existsSync(resultsFile)) {
        const results = JSON.parse(fs.readFileSync(resultsFile, 'utf8'));
        
        console.log('\n📊 Integration Test Summary:');
        console.log(`✅ Passed: ${results.stats?.passed || 0}`);
        console.log(`❌ Failed: ${results.stats?.failed || 0}`);
        console.log(`⏭️ Skipped: ${results.stats?.skipped || 0}`);
        console.log(`⏱️ Duration: ${(results.stats?.duration || 0) / 1000}s`);
      }
    } catch (error) {
      console.log('⚠️ Could not read test results');
    }
  }
  
  console.log('✅ Global teardown completed');
}
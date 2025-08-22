/**
 * Global Teardown for E2E Tests
 * Cleans up test environment after running Playwright tests
 */

async function globalTeardown() {
  console.log('🧹 Starting E2E test environment cleanup...');

  try {
    // Cleanup test data if needed
    console.log('📋 Cleaning up test artifacts...');

    // Log test summary information
    const fs = await import('fs');
    const path = await import('path');
    
    const resultsDir = path.join(process.cwd(), 'test-results');
    
    if (fs.existsSync(resultsDir)) {
      // Count test artifacts
      const files = fs.readdirSync(resultsDir);
      const jsonResults = files.filter(f => f.endsWith('.json'));
      const xmlResults = files.filter(f => f.endsWith('.xml'));
      const artifacts = files.filter(f => f.includes('trace') || f.includes('video') || f.includes('screenshot'));
      
      console.log('📊 Test execution summary:');
      console.log(`   JSON reports: ${jsonResults.length}`);
      console.log(`   XML reports: ${xmlResults.length}`);
      console.log(`   Artifacts (traces/videos/screenshots): ${artifacts.length}`);
      
      // Read and log basic test results if available
      const jsonResultFile = path.join(resultsDir, 'e2e-results.json');
      if (fs.existsSync(jsonResultFile)) {
        try {
          const resultsData = JSON.parse(fs.readFileSync(jsonResultFile, 'utf8'));
          const stats = resultsData.stats || {};
          
          console.log('🎯 Test execution statistics:');
          console.log(`   Total tests: ${stats.tests || 'N/A'}`);
          console.log(`   Passed: ${stats.expected || 'N/A'}`);
          console.log(`   Failed: ${stats.unexpected || 'N/A'}`);
          console.log(`   Skipped: ${stats.skipped || 'N/A'}`);
          
          if (stats.unexpected > 0) {
            console.log('❌ Some tests failed - check reports for details');
          } else {
            console.log('✅ All tests completed successfully');
          }
        } catch (error) {
          console.log('⚠️ Could not parse test results JSON');
        }
      }
    }

    // Environment cleanup
    console.log('🔧 Performing environment cleanup...');
    
    // Clear any test-specific environment variables
    delete process.env.TEST_USER_EMAIL;
    delete process.env.TEST_USER_PASSWORD;
    
    // Log completion time
    const endTime = new Date().toISOString();
    console.log(`🏁 E2E test environment cleanup completed at ${endTime}`);

    // Final status
    console.log('✨ E2E test suite execution completed');

  } catch (error) {
    console.error('❌ Global teardown encountered an error:', error.message);
    console.log('🔍 Teardown error details:', error.stack);
    
    // Don't fail on teardown errors
    console.log('⚠️ Teardown completed with warnings');
  }
}

export default globalTeardown;
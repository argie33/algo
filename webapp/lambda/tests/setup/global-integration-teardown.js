/**
 * Global Integration Test Teardown
 * Runs once after all integration tests complete
 */

module.exports = async () => {
  console.log('🧹 Starting global integration test teardown...');
  
  try {
    // Clean up any global resources if needed
    // Note: Infrastructure cleanup is handled by CI/CD pipeline
    
    // Force close any remaining connections
    if (global.integrationTestDbPool) {
      await global.integrationTestDbPool.end();
      console.log('✅ Database connection pool closed');
    }
    
    // Clear global test variables
    delete global.integrationTestDbPool;
    delete global.integrationTestConfig;
    
    console.log('✅ Global integration test teardown completed');
    
  } catch (error) {
    console.error('❌ Global integration test teardown failed:', error.message);
    // Don't fail - this is cleanup
  }
};
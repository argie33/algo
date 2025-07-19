/**
 * Global Test Teardown
 * Ensures all test resources are properly cleaned up
 */

const { dbTestUtils } = require('../utils/database-test-utils');

module.exports = async () => {
  console.log('🧹 Starting global test teardown...');
  
  try {
    // Cleanup database test utilities
    await dbTestUtils.cleanup();
    
    // Wait for all database operations to complete
    await dbTestUtils.waitForDatabase(10000);
    
    // Give time for any remaining async operations
    await new Promise(resolve => setTimeout(resolve, 1000));
    
    console.log('✅ Global test teardown completed successfully');
  } catch (error) {
    console.error('❌ Error during global test teardown:', error);
    process.exit(1);
  }
};
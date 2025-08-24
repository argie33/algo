/**
 * Global Playwright Teardown
 * Runs once after all tests - cleanup resources
 */

async function globalTeardown() {
  console.log('🧹 Running global E2E test cleanup...');
  
  // Clean up any test data or resources
  // For now, just log completion
  console.log('✅ Global teardown completed');
}

export default globalTeardown;
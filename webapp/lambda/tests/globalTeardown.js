// Global teardown - runs once after all tests

module.exports = async () => {
  // Clean up any global resources
  
  // Force garbage collection if available
  if (global.gc) {
    global.gc();
  }
  
  console.log('🧹 Global test teardown completed');
};
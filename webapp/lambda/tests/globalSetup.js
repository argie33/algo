// Global setup - runs once before all tests

module.exports = async () => {
  // Set test environment variables
  process.env.NODE_ENV = 'test';
  process.env.LOG_LEVEL = 'error'; // Reduce logging noise
  
  // Disable background services during tests
  process.env.DISABLE_LIVE_DATA_MANAGER = 'true';
  process.env.DISABLE_ALERT_SYSTEM = 'true';
  process.env.DISABLE_REAL_TIME_SERVICE = 'true';
  
  console.log('🧪 Global test setup completed');
};
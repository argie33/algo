// Global teardown for tests - cleanup database connections and processes
module.exports = async () => {
  try {
    console.log('🧹 Global test teardown starting...');

    // Close database pool connections
    const { pool } = require('../../utils/database');
    if (pool) {
      await pool.end();
      console.log('✅ Database connection pool closed');
    }

    // Additional cleanup for any other resources
    // Force cleanup any hanging timers or intervals
    if (global.gc) {
      global.gc();
    }

    console.log('🧹 Global test teardown complete');
  } catch (error) {
    console.error('❌ Error during global teardown:', error);
  }
};
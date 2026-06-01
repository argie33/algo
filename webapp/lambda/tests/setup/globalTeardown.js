// Global teardown for tests - cleanup database connections and processes
module.exports = async () => {
  try {

    // Close database pool connections
    const { pool } = require('../../utils/database');
    if (pool) {
      await pool.end();
    }

    // Additional cleanup for any other resources
    // Force cleanup any hanging timers or intervals
    if (global.gc) {
      global.gc();
    }

  } catch (error) {
    console.error(' Error during global teardown:', error);
  }
};
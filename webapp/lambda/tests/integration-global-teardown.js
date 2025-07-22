/**
 * Global Teardown for Real Integration Tests
 * Cleans up real database and services after all tests
 */

const { Pool } = require('pg');

module.exports = async () => {
  console.log('🧹 Starting real integration test cleanup...');
  
  try {
    if (global.__DB_CONFIG__) {
      const pool = new Pool(global.__DB_CONFIG__);
      
      // Clean up test data (optional - keep for debugging)
      // await pool.query('TRUNCATE TABLE users, portfolio, trades CASCADE');
      
      await pool.end();
      console.log('✅ Database connections closed');
    }
    
    console.log('🎯 Real integration test cleanup completed');
    
  } catch (error) {
    console.error('⚠️ Cleanup warning:', error.message);
    // Don't fail the process for cleanup errors
  }
};
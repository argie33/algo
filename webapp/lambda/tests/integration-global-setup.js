/**
 * Global Setup for Real Integration Tests
 * Sets up real database and services before all tests
 */

const { setupRealDatabase } = require('../scripts/setup-real-integration-db');

module.exports = async () => {
  console.log('🚀 Starting REAL integration test setup...');
  
  try {
    // Try to setup real database, but don't fail if unavailable
    try {
      const dbSetup = await setupRealDatabase();
      
      if (dbSetup.success) {
        console.log('✅ Real database setup completed');
        console.log('📊 Test data available:');
        console.log(`   Users: ${dbSetup.testDataCounts.users}`);
        console.log(`   Portfolio entries: ${dbSetup.testDataCounts.portfolio}`);
        console.log(`   Stock data entries: ${dbSetup.testDataCounts.stockData}`);
        
        // Store database config globally for tests
        global.__DB_CONFIG__ = dbSetup.config;
        global.__TEST_DATA__ = dbSetup.testDataCounts;
        global.__DB_AVAILABLE__ = true;
      }
    } catch (dbError) {
      console.warn('⚠️ Real database not available:', dbError.message);
      console.warn('   Integration tests will run with fallback behavior');
      console.warn('   To enable full real testing, start PostgreSQL and create financial_platform_test database');
      
      // Set fallback configuration
      global.__DB_CONFIG__ = {
        host: 'localhost',
        port: 5432,
        database: 'financial_platform_test',
        user: 'postgres',
        password: ''
      };
      global.__TEST_DATA__ = { users: 0, portfolio: 0, stockData: 0 };
      global.__DB_AVAILABLE__ = false;
    }
    
    console.log('🎉 Real integration test setup completed!');
    console.log('   Database available:', global.__DB_AVAILABLE__);
    
  } catch (error) {
    console.error('❌ Critical integration test setup failed:', error.message);
    process.exit(1);
  }
};
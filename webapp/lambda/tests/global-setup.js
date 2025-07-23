/**
 * Global Jest Setup for Database Mocking
 * Mocks database connections to avoid requiring real PostgreSQL
 */

module.exports = async () => {
  // Set environment variables to avoid database connections
  process.env.NODE_ENV = 'test';
  process.env.USE_MOCK_DATABASE = 'true';
  process.env.DB_HOST = 'mock-db-host';
  process.env.DB_PORT = '5432';
  process.env.DB_NAME = 'mock_test_db';
  process.env.DB_USER = 'mock_user';
  process.env.DB_PASSWORD = 'mock_password';
  process.env.DB_SSL = 'false';
  
  // Mock AWS secrets
  process.env.JWT_SECRET = 'test-jwt-secret-key-for-unit-tests';
  process.env.API_KEY_ENCRYPTION_SECRET = 'test-encryption-secret-key-32-bytes!!';
  
  console.log('🧪 Global Jest setup complete - database mocked for unit tests');
};
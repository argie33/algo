/**
 * Jest setup file to mock database connection for tests
 * This ensures tests use mock data instead of trying to connect to real database
 */

const { mockDatabaseModule } = require('./database');

// Mock the database module globally for all tests
jest.mock('../../utils/database', () => mockDatabaseModule);

// Ensure NODE_ENV is set to test
process.env.NODE_ENV = 'test';

// Mock other AWS services that might be used
jest.mock('@aws-sdk/client-secrets-manager', () => ({
  SecretsManagerClient: jest.fn().mockImplementation(() => ({
    send: jest.fn().mockResolvedValue({
      SecretString: JSON.stringify({
        host: 'localhost',
        port: 5432,
        username: 'test',
        password: 'test',
        dbname: 'test'
      })
    })
  })),
  GetSecretValueCommand: jest.fn()
}));

// Suppress console logs during tests unless there's an error
const originalConsoleLog = console.log;
const originalConsoleWarn = console.warn;

console.log = (...args) => {
  if (process.env.JEST_VERBOSE === 'true') {
    originalConsoleLog(...args);
  }
};

console.warn = (...args) => {
  if (process.env.JEST_VERBOSE === 'true') {
    originalConsoleWarn(...args);
  }
};

// Keep error logging active
console.error = console.error;
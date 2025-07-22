/**
 * PROPER UNIT TESTS: Database Utilities
 * Real tests of actual business logic without external dependencies
 */

const database = require('../../utils/database');

describe('Database Utilities Unit Tests (Industry Standard)', () => {
  beforeEach(() => {
    // Restore original environment for clean testing
    delete process.env.AWS_LAMBDA_FUNCTION_NAME;
    delete process.env.LAMBDA_CONCURRENT_EXECUTIONS;
    delete process.env.NODE_ENV;
    delete process.env.EXPECTED_CONCURRENT_USERS;
  });

  describe('Table Name Extraction', () => {
    it('extracts table names from simple SELECT queries', () => {
      const sql = 'SELECT * FROM users WHERE id = $1';
      const result = database.extractTableName(sql);
      expect(result).toBe('users');
    });

    it('extracts table names from INSERT queries', () => {
      const sql = 'INSERT INTO portfolio_holdings (symbol, quantity) VALUES ($1, $2)';
      const result = database.extractTableName(sql);
      expect(result).toBe('portfolio_holdings');
    });

    it('extracts table names from CTE queries', () => {
      const sql = 'WITH cte AS (SELECT * FROM scores) SELECT * FROM cte';
      const result = database.extractTableName(sql);
      expect(result).toBe('scores');
    });

    it('returns "unknown" for malformed queries', () => {
      const testCases = ['', '   ', 'INVALID SQL', null, undefined];
      
      testCases.forEach(sql => {
        const result = database.extractTableName(sql || '');
        expect(result).toBe('unknown');
      });
    });
  });

  describe('Connection Pool Configuration', () => {
    it('calculates optimal pool size for Lambda environment', () => {
      process.env.AWS_LAMBDA_FUNCTION_NAME = 'test-function';
      process.env.LAMBDA_CONCURRENT_EXECUTIONS = '20';

      const config = database.calculateOptimalPoolConfig();
      
      expect(config.max).toBeGreaterThan(0);
      expect(config.max).toBeLessThanOrEqual(20); // Lambda max is min(concurrency * 2, 20)
      expect(config.min).toBeGreaterThanOrEqual(1);
      expect(config.min).toBeLessThanOrEqual(5); // Lambda min is max(1, floor(baseConnections/2))
    });

    it('uses production configuration for non-Lambda environment', () => {
      delete process.env.AWS_LAMBDA_FUNCTION_NAME;
      process.env.NODE_ENV = 'production';
      process.env.EXPECTED_CONCURRENT_USERS = '25';
      
      const config = database.calculateOptimalPoolConfig();
      
      // Based on the actual implementation: expectedUsers as max for production
      expect(config.max).toBe(25);
      expect(config.min).toBeGreaterThanOrEqual(1);
      expect(config.acquireTimeoutMillis).toBeDefined();
      expect(config.createTimeoutMillis).toBeDefined();
    });

    it('uses development configuration by default', () => {
      delete process.env.AWS_LAMBDA_FUNCTION_NAME;
      delete process.env.NODE_ENV; // defaults to development
      
      const config = database.calculateOptimalPoolConfig();
      
      // Development uses small pool: max=5
      expect(config.max).toBe(5);
      expect(config.min).toBe(1);
    });
  });

  describe('Function Exports', () => {
    it('exports all required database functions', () => {
      expect(typeof database.query).toBe('function');
      expect(typeof database.safeQuery).toBe('function');
      expect(typeof database.transaction).toBe('function');
      expect(typeof database.extractTableName).toBe('function');
      expect(typeof database.calculateOptimalPoolConfig).toBe('function');
      expect(typeof database.initializeDatabase).toBe('function');
      expect(typeof database.closeDatabase).toBe('function');
      expect(typeof database.healthCheck).toBe('function');
      expect(typeof database.getPoolStatus).toBe('function');
    });
  });

  describe('Database Exports', () => {
    it('exports core database functions', () => {
      expect(typeof database.query).toBe('function');
      expect(typeof database.extractTableName).toBe('function');
      expect(typeof database.calculateOptimalPoolConfig).toBe('function');
    });
  });
});
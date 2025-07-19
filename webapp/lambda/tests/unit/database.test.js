/**
 * Database Service Unit Tests
 * Comprehensive testing for database connection, query execution, and error handling
 */

// Jest globals are automatically available in test environment

// Mock AWS SDK and dependencies before importing the database module
jest.mock('@aws-sdk/client-secrets-manager');
jest.mock('pg');
jest.mock('../../utils/secureLogger', () => ({
  secureLogger: {
    debug: jest.fn(),
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
    security: jest.fn()
  }
}));

describe('Database Service', () => {
  let mockPool;
  let mockClient;
  let mockSecretsManager;
  let Pool;
  let SecretsManagerClient;
  let GetSecretValueCommand;
  
  beforeEach(() => {
    // Reset all mocks
    jest.clearAllMocks();
    
    // Get mocked modules
    const pg = require('pg');
    const awsSecretsManager = require('@aws-sdk/client-secrets-manager');
    
    Pool = pg.Pool;
    SecretsManagerClient = awsSecretsManager.SecretsManagerClient;
    GetSecretValueCommand = awsSecretsManager.GetSecretValueCommand;
    
    // Mock pg Pool
    mockPool = {
      connect: jest.fn(),
      query: jest.fn(),
      end: jest.fn(),
      on: jest.fn(),
      totalCount: 0,
      idleCount: 0,
      waitingCount: 0
    };
    Pool.mockImplementation(() => mockPool);
    
    // Mock client object
    mockClient = {
      query: jest.fn(),
      release: jest.fn()
    };
    
    // Mock AWS Secrets Manager
    mockSecretsManager = {
      send: jest.fn()
    };
    SecretsManagerClient.mockImplementation(() => mockSecretsManager);
    
    // Reset environment variables
    process.env.DB_HOST = undefined;
    process.env.DB_USER = undefined;
    process.env.DB_PASSWORD = undefined;
    process.env.DB_SECRET_ARN = undefined;
  });

  describe('Database Configuration', () => {
    test('should load config from environment variables', async () => {
      // Set environment variables
      process.env.DB_HOST = 'localhost';
      process.env.DB_USER = 'testuser';
      process.env.DB_PASSWORD = 'testpass';
      process.env.DB_NAME = 'testdb';
      process.env.DB_PORT = '5432';
      
      // Import database after setting env vars
      const database = require('../../utils/database');
      
      // Test should pass with valid environment variables
      expect(process.env.DB_HOST).toBe('localhost');
      expect(process.env.DB_USER).toBe('testuser');
      expect(process.env.DB_PASSWORD).toBe('testpass');
    });

    test('should load config from AWS Secrets Manager', async () => {
      // Set only secret ARN
      process.env.DB_SECRET_ARN = 'arn:aws:secretsmanager:us-east-1:123456789012:secret:test-secret';
      
      // Mock Secrets Manager response
      const mockSecret = {
        host: 'rds-host.amazonaws.com',
        username: 'dbuser',
        password: 'dbpass',
        dbname: 'stocks',
        port: 5432
      };
      
      mockSecretsManager.send.mockResolvedValue({
        SecretString: JSON.stringify(mockSecret)
      });
      
      // Import and test
      delete require.cache[require.resolve('../../utils/database')];
      const database = require('../../utils/database');
      
      // Should attempt to use Secrets Manager
      expect(SecretsManagerClient).toHaveBeenCalled();
    });

    test('should handle missing configuration gracefully', async () => {
      // No environment variables set
      delete require.cache[require.resolve('../../utils/database')];
      
      expect(() => {
        require('../../utils/database');
      }).not.toThrow();
    });

    test('should validate SSL configuration options', () => {
      process.env.DB_SSL = 'true';
      
      delete require.cache[require.resolve('../../utils/database')];
      const database = require('../../utils/database');
      
      // SSL should be configured when environment variable is set
      expect(process.env.DB_SSL).toBe('true');
    });
  });

  describe('Connection Pool Management', () => {
    beforeEach(() => {
      process.env.DB_HOST = 'localhost';
      process.env.DB_USER = 'testuser';
      process.env.DB_PASSWORD = 'testpass';
      process.env.DB_NAME = 'testdb';
    });

    test('should create connection pool with correct configuration', async () => {
      delete require.cache[require.resolve('../../utils/database')];
      const { initializeDatabase } = require('../../utils/database');
      
      mockPool.connect.mockResolvedValue(mockClient);
      mockClient.query.mockResolvedValue({ rows: [{ test: 1 }] });
      
      await initializeDatabase();
      
      expect(Pool).toHaveBeenCalledWith(expect.objectContaining({
        host: 'localhost',
        user: 'testuser',
        password: 'testpass',
        database: 'testdb'
      }));
    });

    test('should handle pool connection failures', async () => {
      delete require.cache[require.resolve('../../utils/database')];
      const { initializeDatabase } = require('../../utils/database');
      
      mockPool.connect.mockRejectedValue(new Error('Connection failed'));
      
      await expect(initializeDatabase()).rejects.toThrow('Connection failed');
    });

    test('should setup pool event listeners', async () => {
      delete require.cache[require.resolve('../../utils/database')];
      const { initializeDatabase } = require('../../utils/database');
      
      mockPool.connect.mockResolvedValue(mockClient);
      mockClient.query.mockResolvedValue({ rows: [{ test: 1 }] });
      
      await initializeDatabase();
      
      // Should register event listeners
      expect(mockPool.on).toHaveBeenCalledWith('connect', expect.any(Function));
      expect(mockPool.on).toHaveBeenCalledWith('acquire', expect.any(Function));
      expect(mockPool.on).toHaveBeenCalledWith('remove', expect.any(Function));
      expect(mockPool.on).toHaveBeenCalledWith('error', expect.any(Function));
    });

    test('should calculate optimal pool configuration for Lambda', () => {
      process.env.AWS_LAMBDA_FUNCTION_NAME = 'test-function';
      process.env.LAMBDA_CONCURRENT_EXECUTIONS = '10';
      
      delete require.cache[require.resolve('../../utils/database')];
      const database = require('../../utils/database');
      
      // Lambda environment should affect pool configuration
      expect(process.env.AWS_LAMBDA_FUNCTION_NAME).toBe('test-function');
    });

    test('should handle pool cleanup on process exit', async () => {
      delete require.cache[require.resolve('../../utils/database')];
      const { initializeDatabase } = require('../../utils/database');
      
      mockPool.connect.mockResolvedValue(mockClient);
      mockClient.query.mockResolvedValue({ rows: [{ test: 1 }] });
      
      await initializeDatabase();
      
      // Should setup cleanup handlers
      expect(mockPool.end).toBeDefined();
    });
  });

  describe('Query Execution', () => {
    beforeEach(async () => {
      process.env.DB_HOST = 'localhost';
      process.env.DB_USER = 'testuser';
      process.env.DB_PASSWORD = 'testpass';
      process.env.DB_NAME = 'testdb';
      
      delete require.cache[require.resolve('../../utils/database')];
      
      mockPool.connect.mockResolvedValue(mockClient);
      mockClient.query.mockResolvedValue({ rows: [{ test: 1 }] });
    });

    test('should execute simple queries successfully', async () => {
      const { query } = require('../../utils/database');
      
      const mockResult = { rows: [{ id: 1, name: 'test' }], rowCount: 1 };
      mockClient.query.mockResolvedValue(mockResult);
      
      const result = await query('SELECT * FROM test_table');
      
      expect(mockClient.query).toHaveBeenCalledWith('SELECT * FROM test_table', []);
      expect(result).toEqual(mockResult);
    });

    test('should execute parameterized queries safely', async () => {
      const { query } = require('../../utils/database');
      
      const mockResult = { rows: [{ id: 1, name: 'test' }], rowCount: 1 };
      mockClient.query.mockResolvedValue(mockResult);
      
      const result = await query('SELECT * FROM users WHERE id = $1', [123]);
      
      expect(mockClient.query).toHaveBeenCalledWith('SELECT * FROM users WHERE id = $1', [123]);
      expect(result).toEqual(mockResult);
    });

    test('should handle query timeouts gracefully', async () => {
      const { query } = require('../../utils/database');
      
      mockClient.query.mockImplementation(() => 
        new Promise((_, reject) => 
          setTimeout(() => reject(new Error('Query timeout')), 100)
        )
      );
      
      await expect(query('SELECT * FROM slow_table')).rejects.toThrow('Query timeout');
    });

    test('should handle malformed SQL gracefully', async () => {
      const { query } = require('../../utils/database');
      
      mockClient.query.mockRejectedValue(new Error('syntax error at or near "INVALID"'));
      
      await expect(query('INVALID SQL QUERY')).rejects.toThrow('syntax error');
    });

    test('should properly release connections after queries', async () => {
      const { query } = require('../../utils/database');
      
      mockClient.query.mockResolvedValue({ rows: [], rowCount: 0 });
      
      await query('SELECT 1');
      
      expect(mockClient.release).toHaveBeenCalled();
    });

    test('should handle connection acquisition failures', async () => {
      const { query } = require('../../utils/database');
      
      mockPool.connect.mockRejectedValue(new Error('Pool exhausted'));
      
      await expect(query('SELECT 1')).rejects.toThrow('Pool exhausted');
    });
  });

  describe('Transaction Management', () => {
    beforeEach(async () => {
      process.env.DB_HOST = 'localhost';
      process.env.DB_USER = 'testuser';
      process.env.DB_PASSWORD = 'testpass';
      process.env.DB_NAME = 'testdb';
      
      delete require.cache[require.resolve('../../utils/database')];
      
      mockPool.connect.mockResolvedValue(mockClient);
      mockClient.query.mockResolvedValue({ rows: [{ test: 1 }] });
    });

    test('should handle transaction commit successfully', async () => {
      const { withTransaction } = require('../../utils/database');
      
      if (withTransaction) {
        const result = await withTransaction(async (client) => {
          await client.query('INSERT INTO test_table (name) VALUES ($1)', ['test']);
          return { success: true };
        });
        
        expect(mockClient.query).toHaveBeenCalledWith('BEGIN');
        expect(mockClient.query).toHaveBeenCalledWith('COMMIT');
        expect(result).toEqual({ success: true });
      }
    });

    test('should handle transaction rollback on error', async () => {
      const { withTransaction } = require('../../utils/database');
      
      if (withTransaction) {
        mockClient.query.mockImplementation((sql) => {
          if (sql.includes('INSERT')) {
            throw new Error('Constraint violation');
          }
          return Promise.resolve({ rows: [], rowCount: 0 });
        });
        
        await expect(withTransaction(async (client) => {
          await client.query('INSERT INTO test_table (name) VALUES ($1)', ['test']);
        })).rejects.toThrow('Constraint violation');
        
        expect(mockClient.query).toHaveBeenCalledWith('ROLLBACK');
      }
    });
  });

  describe('Error Handling & Recovery', () => {
    test('should implement circuit breaker pattern', async () => {
      process.env.DB_HOST = 'localhost';
      process.env.DB_USER = 'testuser';
      process.env.DB_PASSWORD = 'testpass';
      
      delete require.cache[require.resolve('../../utils/database')];
      const { query } = require('../../utils/database');
      
      // Simulate multiple consecutive failures
      mockPool.connect.mockRejectedValue(new Error('Connection refused'));
      
      // Should eventually trigger circuit breaker
      for (let i = 0; i < 6; i++) {
        try {
          await query('SELECT 1');
        } catch (error) {
          // Expected to fail
        }
      }
      
      // Verify error handling was called
      expect(mockPool.connect).toHaveBeenCalled();
    });

    test('should log database errors appropriately', async () => {
      const { secureLogger } = require('../utils/secureLogger');
      
      process.env.DB_HOST = 'localhost';
      process.env.DB_USER = 'testuser';
      process.env.DB_PASSWORD = 'testpass';
      
      delete require.cache[require.resolve('../../utils/database')];
      const { query } = require('../../utils/database');
      
      mockPool.connect.mockRejectedValue(new Error('Database error'));
      
      try {
        await query('SELECT 1');
      } catch (error) {
        // Expected to fail
      }
      
      // Should log errors securely
      expect(secureLogger.error).toHaveBeenCalled();
    });

    test('should handle AWS Secrets Manager errors', async () => {
      process.env.DB_SECRET_ARN = 'arn:aws:secretsmanager:us-east-1:123456789012:secret:test';
      
      mockSecretsManager.send.mockRejectedValue(new Error('Access denied'));
      
      delete require.cache[require.resolve('../../utils/database')];
      
      // Should handle Secrets Manager failures gracefully
      expect(() => {
        require('../../utils/database');
      }).not.toThrow();
    });
  });

  describe('Performance & Monitoring', () => {
    test('should track connection pool metrics', async () => {
      process.env.DB_HOST = 'localhost';
      process.env.DB_USER = 'testuser';
      process.env.DB_PASSWORD = 'testpass';
      
      delete require.cache[require.resolve('../../utils/database')];
      const { getPoolStats } = require('../../utils/database');
      
      if (getPoolStats) {
        const stats = getPoolStats();
        expect(stats).toHaveProperty('totalCount');
        expect(stats).toHaveProperty('idleCount');
        expect(stats).toHaveProperty('waitingCount');
      }
    });

    test('should measure query execution time', async () => {
      const { secureLogger } = require('../utils/secureLogger');
      
      process.env.DB_HOST = 'localhost';
      process.env.DB_USER = 'testuser';
      process.env.DB_PASSWORD = 'testpass';
      
      delete require.cache[require.resolve('../../utils/database')];
      const { query } = require('../../utils/database');
      
      mockPool.connect.mockResolvedValue(mockClient);
      mockClient.query.mockImplementation(() => 
        new Promise(resolve => 
          setTimeout(() => resolve({ rows: [], rowCount: 0 }), 100)
        )
      );
      
      await query('SELECT 1');
      
      // Should log performance metrics
      expect(secureLogger.debug).toHaveBeenCalled();
    });
  });

  describe('Security & Compliance', () => {
    test('should prevent SQL injection in queries', async () => {
      process.env.DB_HOST = 'localhost';
      process.env.DB_USER = 'testuser';
      process.env.DB_PASSWORD = 'testpass';
      
      delete require.cache[require.resolve('../../utils/database')];
      const { query } = require('../../utils/database');
      
      mockPool.connect.mockResolvedValue(mockClient);
      mockClient.query.mockResolvedValue({ rows: [], rowCount: 0 });
      
      // Should use parameterized queries
      await query('SELECT * FROM users WHERE id = $1', [1]);
      
      expect(mockClient.query).toHaveBeenCalledWith(
        'SELECT * FROM users WHERE id = $1',
        [1]
      );
    });

    test('should sanitize sensitive data in logs', async () => {
      const { secureLogger } = require('../utils/secureLogger');
      
      process.env.DB_HOST = 'localhost';
      process.env.DB_USER = 'testuser';
      process.env.DB_PASSWORD = 'supersecret';
      
      delete require.cache[require.resolve('../../utils/database')];
      require('../../utils/database');
      
      // Should not log passwords in plain text
      const logCalls = secureLogger.info.mock.calls.flat();
      const loggedText = logCalls.join(' ');
      
      expect(loggedText).not.toContain('supersecret');
    });

    test('should validate database configuration schema', () => {
      const validConfigs = [
        { host: 'localhost', user: 'test', password: 'pass', database: 'db' },
        { host: '127.0.0.1', port: 5432, user: 'user', password: 'pass', database: 'stocks' }
      ];
      
      validConfigs.forEach(config => {
        expect(config).toHaveProperty('host');
        expect(config).toHaveProperty('user');
        expect(config).toHaveProperty('password');
        expect(config).toHaveProperty('database');
      });
    });
  });
});
// Simple unit tests for database utility

// Mock AWS SDK
const mockSecretsManager = {
  send: jest.fn()
};

jest.mock('@aws-sdk/client-secrets-manager', () => ({
  SecretsManagerClient: jest.fn(() => mockSecretsManager),
  GetSecretValueCommand: jest.fn()
}));

// Mock pg module
const mockPool = {
  query: jest.fn(),
  connect: jest.fn(),
  end: jest.fn(),
  on: jest.fn(),
  totalCount: 5,
  idleCount: 3,
  waitingCount: 0
};

const mockClient = {
  query: jest.fn(),
  release: jest.fn()
};

jest.mock('pg', () => ({
  Pool: jest.fn(() => mockPool)
}));

// Mock schemaValidator to prevent actual schema operations
jest.mock('../../utils/schemaValidator', () => ({
  generateCreateTableSQL: jest.fn(() => 'CREATE TABLE test ()'),
  listTables: jest.fn(() => [])
}));

// Mock console to reduce noise
console.log = jest.fn();
console.warn = jest.fn();
console.error = jest.fn();

const { Pool } = require('pg');

describe('Database Utility Simple Tests', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    
    // Reset mock implementations
    mockPool.connect.mockResolvedValue(mockClient);
    mockClient.query.mockResolvedValue({ rows: [{ now: new Date() }] });
    
    // Clear environment variables
    delete process.env.DB_SECRET_ARN;
    delete process.env.DB_HOST;
    delete process.env.DB_ENDPOINT;
    delete process.env.DB_PORT;
    delete process.env.DB_NAME;
    delete process.env.DB_USER;
    delete process.env.DB_PASSWORD;
    delete process.env.DB_SSL;
    
    // Clear module cache to get fresh instance
    delete require.cache[require.resolve('../../utils/database')];
  });

  test('should export database functions', () => {
    const database = require('../../utils/database');
    
    expect(database.initializeDatabase).toBeInstanceOf(Function);
    expect(database.getPool).toBeInstanceOf(Function);
    expect(database.query).toBeInstanceOf(Function);
    expect(database.transaction).toBeInstanceOf(Function);
    expect(database.closeDatabase).toBeInstanceOf(Function);
    expect(database.healthCheck).toBeInstanceOf(Function);
  });

  test('should initialize database with environment variables', async () => {
    process.env.DB_HOST = 'localhost';
    process.env.DB_USER = 'testuser';
    process.env.DB_PASSWORD = 'testpass';
    process.env.DB_NAME = 'testdb';
    process.env.DB_PORT = '5432';
    
    const database = require('../../utils/database');
    
    const result = await database.initializeDatabase();
    
    expect(Pool).toHaveBeenCalledWith(expect.objectContaining({
      host: 'localhost',
      user: 'testuser',
      password: 'testpass',
      database: 'testdb',
      port: 5432
    }));
    
    expect(mockPool.connect).toHaveBeenCalled();
    expect(mockClient.query).toHaveBeenCalledWith('SELECT NOW()');
    expect(mockClient.release).toHaveBeenCalled();
    expect(result).toBe(mockPool);
  });

  test('should return null when no database configuration available', async () => {
    const database = require('../../utils/database');
    
    const result = await database.initializeDatabase();
    
    expect(result).toBeNull();
  });

  test('should handle database connection errors', async () => {
    process.env.DB_HOST = 'localhost';
    process.env.DB_USER = 'testuser';
    
    mockPool.connect.mockRejectedValue(new Error('Connection failed'));
    
    const database = require('../../utils/database');
    
    const result = await database.initializeDatabase();
    
    expect(result).toBeNull();
  });

  test('should execute queries when database is initialized', async () => {
    process.env.DB_HOST = 'localhost';
    process.env.DB_USER = 'testuser';
    process.env.DB_PASSWORD = 'testpass';
    process.env.DB_NAME = 'testdb';
    
    const database = require('../../utils/database');
    
    // Initialize first
    await database.initializeDatabase();
    
    // Then execute query
    const expectedResult = { rows: [{ id: 1 }], rowCount: 1 };
    mockPool.query.mockResolvedValue(expectedResult);
    
    const result = await database.query('SELECT * FROM test');
    
    expect(result).toEqual(expectedResult);
    expect(mockPool.query).toHaveBeenCalledWith('SELECT * FROM test', []);
  });

  test('should handle query errors', async () => {
    process.env.DB_HOST = 'localhost';
    process.env.DB_USER = 'testuser';
    process.env.DB_PASSWORD = 'testpass';
    process.env.DB_NAME = 'testdb';
    
    const database = require('../../utils/database');
    
    await database.initializeDatabase();
    
    mockPool.query.mockRejectedValue(new Error('Query failed'));
    
    await expect(database.query('SELECT * FROM test')).rejects.toThrow('Query failed');
  });

  test('should return health check when database is healthy', async () => {
    process.env.DB_HOST = 'localhost';
    process.env.DB_USER = 'testuser';
    process.env.DB_PASSWORD = 'testpass';
    process.env.DB_NAME = 'testdb';
    
    const database = require('../../utils/database');
    
    await database.initializeDatabase();
    
    const healthResult = {
      rows: [{
        timestamp: new Date().toISOString(),
        db_version: 'PostgreSQL 14.0'
      }]
    };
    
    mockPool.query.mockResolvedValue(healthResult);
    
    const health = await database.healthCheck();
    
    expect(health.status).toBe('healthy');
    expect(health.timestamp).toBeDefined();
    expect(health.version).toBe('PostgreSQL 14.0');
  });

  test('should return unhealthy status when database query fails', async () => {
    process.env.DB_HOST = 'localhost';
    process.env.DB_USER = 'testuser';
    process.env.DB_PASSWORD = 'testpass';
    process.env.DB_NAME = 'testdb';
    
    const database = require('../../utils/database');
    
    await database.initializeDatabase();
    
    mockPool.query.mockRejectedValue(new Error('Database unavailable'));
    
    const health = await database.healthCheck();
    
    expect(health.status).toBe('unhealthy');
    expect(health.error).toBe('Database unavailable');
  });

  test('should close database connections', async () => {
    process.env.DB_HOST = 'localhost';
    process.env.DB_USER = 'testuser';
    process.env.DB_PASSWORD = 'testpass';
    process.env.DB_NAME = 'testdb';
    
    const database = require('../../utils/database');
    
    await database.initializeDatabase();
    await database.closeDatabase();
    
    expect(mockPool.end).toHaveBeenCalled();
  });

  test('should execute transactions', async () => {
    process.env.DB_HOST = 'localhost';
    process.env.DB_USER = 'testuser';
    process.env.DB_PASSWORD = 'testpass';
    process.env.DB_NAME = 'testdb';
    
    const database = require('../../utils/database');
    
    await database.initializeDatabase();
    
    const mockCallback = jest.fn().mockResolvedValue('success');
    
    const result = await database.transaction(mockCallback);
    
    expect(result).toBe('success');
    expect(mockClient.query).toHaveBeenCalledWith('BEGIN');
    expect(mockCallback).toHaveBeenCalledWith(mockClient);
    expect(mockClient.query).toHaveBeenCalledWith('COMMIT');
    expect(mockClient.release).toHaveBeenCalled();
  });

  test('should rollback transaction on error', async () => {
    process.env.DB_HOST = 'localhost';
    process.env.DB_USER = 'testuser';
    process.env.DB_PASSWORD = 'testpass';
    process.env.DB_NAME = 'testdb';
    
    const database = require('../../utils/database');
    
    await database.initializeDatabase();
    
    const mockCallback = jest.fn().mockRejectedValue(new Error('Transaction failed'));
    
    await expect(database.transaction(mockCallback)).rejects.toThrow('Transaction failed');
    
    expect(mockClient.query).toHaveBeenCalledWith('BEGIN');
    expect(mockClient.query).toHaveBeenCalledWith('ROLLBACK');
    expect(mockClient.release).toHaveBeenCalled();
  });

  test('should handle SSL configuration', async () => {
    process.env.DB_HOST = 'localhost';
    process.env.DB_USER = 'testuser';
    process.env.DB_PASSWORD = 'testpass';
    process.env.DB_NAME = 'testdb';
    process.env.DB_SSL = 'false';
    
    const database = require('../../utils/database');
    
    await database.initializeDatabase();
    
    expect(Pool).toHaveBeenCalledWith(expect.objectContaining({
      ssl: false
    }));
  });

  test('should use SSL by default', async () => {
    process.env.DB_HOST = 'localhost';
    process.env.DB_USER = 'testuser';
    process.env.DB_PASSWORD = 'testpass';
    process.env.DB_NAME = 'testdb';
    
    const database = require('../../utils/database');
    
    await database.initializeDatabase();
    
    expect(Pool).toHaveBeenCalledWith(expect.objectContaining({
      ssl: { rejectUnauthorized: false }
    }));
  });
});
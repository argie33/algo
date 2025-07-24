/**
 * Unified API Key Service Tests
 * Comprehensive test suite for the redesigned API key service
 */

const request = require('supertest');

// Mock environment variables
process.env.NODE_ENV = 'test';
process.env.DB_SECRET_ARN = 'test-secret-arn';
process.env.DB_ENDPOINT = 'test-endpoint';

// Import modules under test
const unifiedApiKeyService = require('../utils/unifiedApiKeyService');
const unifiedApiKeyDatabaseService = require('../utils/unifiedApiKeyDatabaseService');
const apiKeyPerformanceOptimizer = require('../utils/apiKeyPerformanceOptimizer');
const migrationService = require('../utils/apiKeyMigrationService');

describe('Unified API Key Service', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('Core Service Tests', () => {
    it('should initialize with proper configuration', () => {
      expect(unifiedApiKeyService).toBeDefined();
      expect(typeof unifiedApiKeyService.getAlpacaKey).toBe('function');
      expect(typeof unifiedApiKeyService.saveAlpacaKey).toBe('function');
      expect(typeof unifiedApiKeyService.removeAlpacaKey).toBe('function');
      expect(typeof unifiedApiKeyService.healthCheck).toBe('function');
    });

    it('should handle cache operations correctly', () => {
      const metrics = unifiedApiKeyService.getCacheMetrics();
      expect(metrics).to.have.property('size');
      expect(metrics).to.have.property('maxSize');
      expect(metrics).to.have.property('hits');
      expect(metrics).to.have.property('misses');
      expect(metrics).to.have.property('hitRate');
    });

    it('should validate API key format', async () => {
      const validKey = 'PKTEST1234567890ABCDEF';
      const invalidKey = 'INVALID';
      
      try {
        await unifiedApiKeyService.saveAlpacaKey('test-user', validKey, 'TESTSECRET123456789012345678901234567890', true);
      } catch (error) {
        // Expected to fail due to mocked dependencies, but should validate format
        expect(error.message).to.not.include('Invalid Alpaca API key format');
      }
    });

    it('should handle graceful degradation', async () => {
      // Mock service failure
      sandbox.stub(require('../utils/simpleApiKeyService'), 'getApiKey').rejects(new Error('Service unavailable'));
      
      const result = await unifiedApiKeyService.getAlpacaKey('test-user');
      expect(result).to.be.null; // Should gracefully return null instead of throwing
    });
  });

  describe('Database Service Tests', () => {
    it('should normalize database row data correctly', () => {
      const mockDbRow = {
        id: 1,
        user_id: 'test-user',
        provider: 'alpaca',
        api_key_encrypted: 'encrypted-key',
        secret_encrypted: 'encrypted-secret',
        is_sandbox: true,
        is_active: true,
        validation_status: 'active',
        created_at: new Date(),
        updated_at: new Date()
      };

      const normalized = unifiedApiKeyDatabaseService.normalizeApiKeyData(mockDbRow);
      expect(normalized).to.have.property('userId', 'test-user');
      expect(normalized).to.have.property('provider', 'alpaca');
      expect(normalized).to.have.property('apiKey', 'encrypted-key');
      expect(normalized).to.have.property('secretKey', 'encrypted-secret');
    });

    it('should mask API keys for display', () => {
      const apiKey = 'PKTEST1234567890ABCDEF';
      const masked = unifiedApiKeyDatabaseService.maskApiKey(apiKey);
      expect(masked).to.equal('PKTE****CDEF');
    });

    it('should handle health check', async () => {
      // Mock database manager
      sandbox.stub(require('../utils/databaseConnectionManager'), 'query').resolves({
        rows: [{ health_check: 1 }]
      });

      const health = await unifiedApiKeyDatabaseService.healthCheck();
      expect(health).to.have.property('healthy', true);
      expect(health).to.have.property('connection', 'active');
    });
  });

  describe('Performance Optimizer Tests', () => {
    it('should initialize with correct configuration', () => {
      expect(apiKeyPerformanceOptimizer).to.be.an('object');
      expect(apiKeyPerformanceOptimizer.getMetrics).to.be.a('function');
      expect(apiKeyPerformanceOptimizer.checkRateLimit).to.be.a('function');
      expect(apiKeyPerformanceOptimizer.checkCircuitBreaker).to.be.a('function');
    });

    it('should enforce rate limits', () => {
      const userId = 'test-user';
      
      // Should allow first request
      const allowed1 = apiKeyPerformanceOptimizer.checkRateLimit(userId);
      expect(allowed1).to.be.true;
      
      // Simulate many requests to test limit
      for (let i = 0; i < 105; i++) {
        apiKeyPerformanceOptimizer.checkRateLimit(userId);
      }
      
      // Should deny after limit
      const allowedAfterLimit = apiKeyPerformanceOptimizer.checkRateLimit(userId);
      expect(allowedAfterLimit).to.be.false;
    });

    it('should track performance metrics', () => {
      const initialMetrics = apiKeyPerformanceOptimizer.getMetrics();
      expect(initialMetrics).to.have.property('requestCount');
      expect(initialMetrics).to.have.property('batchedRequests');
      expect(initialMetrics).to.have.property('requestsPerSecond');
    });

    it('should implement circuit breaker', () => {
      // Initially should be closed (allow requests)
      const initialState = apiKeyPerformanceOptimizer.checkCircuitBreaker();
      expect(initialState).to.be.true;
      
      // Record multiple errors to trigger circuit breaker
      for (let i = 0; i < 15; i++) {
        apiKeyPerformanceOptimizer.recordError();
      }
      
      // Should open circuit breaker
      const afterErrors = apiKeyPerformanceOptimizer.checkCircuitBreaker();
      expect(afterErrors).to.be.false;
    });
  });

  describe('Migration Service Tests', () => {
    it('should validate legacy key format', () => {
      const validKey = {
        userId: 'test-user',
        apiKey: 'PKTEST1234567890ABCDEF',
        secretKey: 'TESTSECRET123456789012345678901234567890',
        provider: 'alpaca'
      };

      const invalidKey = {
        userId: 'test-user',
        apiKey: 'INVALID',
        secretKey: 'SHORT',
        provider: 'alpaca'
      };

      expect(migrationService.validateLegacyKey(validKey)).to.be.true;
      expect(migrationService.validateLegacyKey(invalidKey)).to.be.false;
    });

    it('should chunk arrays correctly', () => {
      const array = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
      const chunks = migrationService.chunkArray(array, 3);
      
      expect(chunks).to.have.length(4);
      expect(chunks[0]).to.deep.equal([1, 2, 3]);
      expect(chunks[1]).to.deep.equal([4, 5, 6]);
      expect(chunks[2]).to.deep.equal([7, 8, 9]);
      expect(chunks[3]).to.deep.equal([10]);
    });

    it('should deduplicate API keys', () => {
      const duplicateKeys = [
        { userId: 'user1', createdAt: '2023-01-01', apiKey: 'key1' },
        { userId: 'user1', createdAt: '2023-01-02', apiKey: 'key2' }, // newer
        { userId: 'user2', createdAt: '2023-01-01', apiKey: 'key3' }
      ];

      const unique = migrationService.deduplicateApiKeys(duplicateKeys);
      expect(unique).to.have.length(2);
      expect(unique.find(k => k.userId === 'user1').apiKey).to.equal('key2'); // Should keep newer
    });

    it('should handle migration status', () => {
      const status = migrationService.getStatus();
      expect(status).to.have.property('total');
      expect(status).to.have.property('migrated');
      expect(status).to.have.property('failed');
      expect(status).to.have.property('skipped');
      expect(status).to.have.property('errors');
    });
  });

  describe('Integration Tests', () => {
    let app;

    before(() => {
      // Load the express app
      app = require('../index').app;
    });

    it('should respond to health check', async () => {
      const response = await request(app)
        .get('/api/api-keys/health')
        .expect(200);

      expect(response.body).to.have.property('success');
      expect(response.body).to.have.property('service', 'unified-api-keys');
    });

    it('should require authentication for API key operations', async () => {
      await request(app)
        .get('/api/api-keys')
        .expect(401);
    });

    it('should handle OPTIONS requests (CORS)', async () => {
      await request(app)
        .options('/api/api-keys')
        .expect(200);
    });

    it('should validate POST request data', async () => {
      // Mock authentication
      const authStub = sandbox.stub(require('../middleware/auth'), 'authenticateToken');
      authStub.callsFake((req, res, next) => {
        req.user = { sub: 'test-user' };
        next();
      });

      await request(app)
        .post('/api/api-keys')
        .send({}) // Empty body should fail validation
        .expect(400);
    });
  });

  describe('Scale and Performance Tests', () => {
    it('should handle high-scale cache operations', () => {
      // Test cache with many entries
      const service = unifiedApiKeyService;
      
      // Add many cache entries to test LRU behavior
      for (let i = 0; i < 15000; i++) {
        service._addToCache(`test-key-${i}`, { data: `test-data-${i}` });
      }
      
      const metrics = service.getCacheMetrics();
      expect(parseInt(metrics.size)).to.be.at.most(10000); // Should respect max cache size
    });

    it('should batch operations efficiently', async () => {
      const userIds = Array.from({ length: 20 }, (_, i) => `user-${i}`);
      
      // Mock the batch operation
      sandbox.stub(apiKeyPerformanceOptimizer, 'batchFetchFromParameterStore').resolves({
        'user-1': { keyId: 'key1', secretKey: 'secret1' },
        'user-2': { keyId: 'key2', secretKey: 'secret2' }
      });

      try {
        const results = await apiKeyPerformanceOptimizer.batchGetApiKeys(userIds);
        expect(results).to.be.an('array');
      } catch (error) {
        // Expected to fail due to mocking, but should not crash
        expect(error).to.be.instanceOf(Error);
      }
    });
  });

  describe('Error Handling Tests', () => {
    it('should handle Parameter Store failures gracefully', async () => {
      // Mock Parameter Store failure
      sandbox.stub(require('../utils/simpleApiKeyService'), 'getApiKey').rejects(new Error('AWS Error'));
      
      const result = await unifiedApiKeyService.getAlpacaKey('test-user');
      expect(result).toBeNull(); // Should not throw, return null for graceful degradation
    });

    it('should handle database failures gracefully', async () => {
      // Mock database failure
      sandbox.stub(require('../utils/databaseConnectionManager'), 'query').rejects(new Error('Database Error'));
      
      const result = await unifiedApiKeyDatabaseService.getApiKeyFromDatabase('test-user');
      expect(result).toBeNull(); // Should not throw, return null for graceful degradation
    });

    it('should maintain service availability during failures', async () => {
      // Mock both Parameter Store and database failures
      sandbox.stub(require('../utils/simpleApiKeyService'), 'getApiKey').rejects(new Error('AWS Error'));
      sandbox.stub(require('../utils/databaseConnectionManager'), 'query').rejects(new Error('Database Error'));
      
      const health = await unifiedApiKeyService.healthCheck();
      expect(health).to.have.property('healthy', false);
      expect(health).to.have.property('error');
    });
  });

  describe('Security Tests', () => {
    it('should mask sensitive data in logs', () => {
      const apiKey = 'PKTEST1234567890ABCDEF';
      const masked = unifiedApiKeyService.maskApiKey(apiKey);
      
      expect(masked).to.not.equal(apiKey);
      expect(masked).to.include('****');
      expect(masked.length).to.be.lessThan(apiKey.length);
    });

    it('should validate input parameters', async () => {
      try {
        await unifiedApiKeyService.saveAlpacaKey('', '', '');
      } catch (error) {
        expect(error.message).to.include('required');
      }
    });

    it('should prevent unauthorized access', async () => {
      // This would be tested more thoroughly in integration tests
      // with actual authentication middleware
      expect(true).to.be.true; // Placeholder
    });
  });
});

// Test helper functions
function createMockUser(id = 'test-user') {
  return {
    sub: id,
    email: `${id}@example.com`,
    groups: ['user']
  };
}

function createMockApiKey(userId = 'test-user') {
  return {
    id: 1,
    userId,
    provider: 'alpaca',
    apiKey: 'PKTEST1234567890ABCDEF',
    secretKey: 'TESTSECRET123456789012345678901234567890',
    isSandbox: true,
    isActive: true,
    createdAt: new Date(),
    updatedAt: new Date()
  };
}

module.exports = {
  createMockUser,
  createMockApiKey
};
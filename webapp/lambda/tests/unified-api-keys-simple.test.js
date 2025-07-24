/**
 * Unified API Key Service - Simple Tests
 * Core functionality tests for the redesigned API key service
 */

// Mock environment variables
process.env.NODE_ENV = 'test';
process.env.DB_SECRET_ARN = 'test-secret-arn';
process.env.DB_ENDPOINT = 'test-endpoint';

describe('Unified API Key Service - Core Tests', () => {
  
  describe('Service Loading and Initialization', () => {
    test('should load all core services without errors', () => {
      expect(() => {
        const unifiedApiKeyService = require('../utils/unifiedApiKeyService');
        const unifiedApiKeyDatabaseService = require('../utils/unifiedApiKeyDatabaseService');
        const apiKeyPerformanceOptimizer = require('../utils/apiKeyPerformanceOptimizer');
        const migrationService = require('../utils/apiKeyMigrationService');
        
        expect(unifiedApiKeyService).toBeDefined();
        expect(unifiedApiKeyDatabaseService).toBeDefined();
        expect(apiKeyPerformanceOptimizer).toBeDefined();
        expect(migrationService).toBeDefined();
      }).not.toThrow();
    });

    test('unified service should have all required methods', () => {
      const unifiedApiKeyService = require('../utils/unifiedApiKeyService');
      
      expect(typeof unifiedApiKeyService.getAlpacaKey).toBe('function');
      expect(typeof unifiedApiKeyService.saveAlpacaKey).toBe('function');
      expect(typeof unifiedApiKeyService.removeAlpacaKey).toBe('function');
      expect(typeof unifiedApiKeyService.hasAlpacaKey).toBe('function');
      expect(typeof unifiedApiKeyService.getApiKeySummary).toBe('function');
      expect(typeof unifiedApiKeyService.healthCheck).toBe('function');
      expect(typeof unifiedApiKeyService.getCacheMetrics).toBe('function');
      expect(typeof unifiedApiKeyService.clearCache).toBe('function');
    });

    test('database service should have all required methods', () => {
      const databaseService = require('../utils/unifiedApiKeyDatabaseService');
      
      expect(typeof databaseService.getApiKeyFromDatabase).toBe('function');
      expect(typeof databaseService.saveApiKeyToDatabase).toBe('function');
      expect(typeof databaseService.removeApiKeyFromDatabase).toBe('function');
      expect(typeof databaseService.markApiKeyAsMigrated).toBe('function');
      expect(typeof databaseService.getAllApiKeysForMigration).toBe('function');
      expect(typeof databaseService.getMigrationStats).toBe('function');
      expect(typeof databaseService.healthCheck).toBe('function');
    });

    test('performance optimizer should have all required methods', () => {
      const optimizer = require('../utils/apiKeyPerformanceOptimizer');
      
      expect(typeof optimizer.checkRateLimit).toBe('function');
      expect(typeof optimizer.checkCircuitBreaker).toBe('function');
      expect(typeof optimizer.recordError).toBe('function');
      expect(typeof optimizer.getMetrics).toBe('function');
      expect(typeof optimizer.resetMetrics).toBe('function');
    });

    test('migration service should have all required methods', () => {
      const migration = require('../utils/apiKeyMigrationService');
      
      expect(typeof migration.discoverLegacyApiKeys).toBe('function');
      expect(typeof migration.runMigration).toBe('function');
      expect(typeof migration.rollbackMigration).toBe('function');
      expect(typeof migration.validateLegacyKey).toBe('function');
      expect(typeof migration.getStatus).toBe('function');
    });
  });

  describe('Route Handler Loading', () => {
    test('should load unified API keys route handler', () => {
      expect(() => {
        const unifiedRoutes = require('../routes/unified-api-keys');
        expect(unifiedRoutes).toBeDefined();
      }).not.toThrow();
    });
  });

  describe('Cache Operations', () => {
    test('should provide cache metrics', () => {
      const unifiedApiKeyService = require('../utils/unifiedApiKeyService');
      const metrics = unifiedApiKeyService.getCacheMetrics();
      
      expect(metrics).toHaveProperty('size');
      expect(metrics).toHaveProperty('maxSize');
      expect(metrics).toHaveProperty('hits');
      expect(metrics).toHaveProperty('misses');
      expect(metrics).toHaveProperty('hitRate');
      expect(metrics).toHaveProperty('utilizationPercent');
      expect(metrics).toHaveProperty('memoryEfficient');
      
      expect(typeof metrics.size).toBe('number');
      expect(typeof metrics.maxSize).toBe('number');
      expect(typeof metrics.hits).toBe('number');
      expect(typeof metrics.misses).toBe('number');
    });

    test('should clear cache without errors', () => {
      const unifiedApiKeyService = require('../utils/unifiedApiKeyService');
      
      expect(() => {
        unifiedApiKeyService.clearCache();
      }).not.toThrow();
      
      expect(() => {
        unifiedApiKeyService.clearCache('test-user');
      }).not.toThrow();
    });
  });

  describe('Data Validation', () => {
    test('should validate API key format correctly', () => {
      const databaseService = require('../utils/unifiedApiKeyDatabaseService');
      
      // Valid API key
      const validKey = 'PKTEST1234567890ABCDEF1234567890';
      const masked = databaseService.maskApiKey(validKey);
      expect(masked).toContain('****');
      expect(masked.length).toBeLessThan(validKey.length);
      
      // Invalid/short API key
      const shortKey = 'PK123';
      const maskedShort = databaseService.maskApiKey(shortKey);
      expect(maskedShort).toBe('****');
    });

    test('should validate legacy key format', () => {
      const migration = require('../utils/apiKeyMigrationService');
      
      const validKey = {
        userId: 'test-user',
        apiKey: 'PKTEST1234567890ABCDEF1234567890',
        secretKey: 'TESTSECRET123456789012345678901234567890123456789012345678901234567890',
        provider: 'alpaca'
      };
      
      const invalidKey = {
        userId: 'test-user',
        apiKey: 'INVALID',
        secretKey: 'SHORT',
        provider: 'alpaca'
      };
      
      expect(migration.validateLegacyKey(validKey)).toBe(true);
      expect(migration.validateLegacyKey(invalidKey)).toBe(false);
      expect(migration.validateLegacyKey({})).toBe(false);
      expect(migration.validateLegacyKey(null)).toBe(false);
    });
  });

  describe('Performance Features', () => {
    test('should track performance metrics', () => {
      const optimizer = require('../utils/apiKeyPerformanceOptimizer');
      const metrics = optimizer.getMetrics();
      
      expect(metrics).toHaveProperty('requestCount');
      expect(metrics).toHaveProperty('batchedRequests');
      expect(metrics).toHaveProperty('cacheHits');
      expect(metrics).toHaveProperty('cacheMisses');
      expect(metrics).toHaveProperty('avgResponseTime');
      expect(metrics).toHaveProperty('errors');
      expect(metrics).toHaveProperty('uptime');
      expect(metrics).toHaveProperty('requestsPerSecond');
      expect(metrics).toHaveProperty('cacheHitRate');
      expect(metrics).toHaveProperty('errorRate');
    });

    test('should enforce rate limits', () => {
      const optimizer = require('../utils/apiKeyPerformanceOptimizer');
      const userId = 'test-user-rate-limit';
      
      // Should allow initial requests
      expect(optimizer.checkRateLimit(userId)).toBe(true);
      expect(optimizer.checkRateLimit(userId)).toBe(true);
      
      // Simulate hitting rate limit
      for (let i = 0; i < 105; i++) {
        optimizer.checkRateLimit(userId);
      }
      
      // Should block after rate limit
      expect(optimizer.checkRateLimit(userId)).toBe(false);
    });

    test('should implement circuit breaker', () => {
      const optimizer = require('../utils/apiKeyPerformanceOptimizer');
      
      // Initially should allow requests
      expect(optimizer.checkCircuitBreaker()).toBe(true);
      
      // Record many errors to trip circuit breaker
      for (let i = 0; i < 15; i++) {
        optimizer.recordError();
      }
      
      // Should open circuit breaker
      expect(optimizer.checkCircuitBreaker()).toBe(false);
    });

    test('should reset metrics', () => {
      const optimizer = require('../utils/apiKeyPerformanceOptimizer');
      
      // Record some activity
      optimizer.recordError();
      optimizer.checkRateLimit('test-user');
      
      // Reset metrics
      expect(() => {
        optimizer.resetMetrics();
      }).not.toThrow();
      
      const metrics = optimizer.getMetrics();
      expect(metrics.requestCount).toBe(0);
      expect(metrics.errors).toBe(0);
    });
  });

  describe('Migration Features', () => {
    test('should chunk arrays correctly', () => {
      const migration = require('../utils/apiKeyMigrationService');
      
      const array = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
      const chunks = migration.chunkArray(array, 3);
      
      expect(chunks).toHaveLength(4);
      expect(chunks[0]).toEqual([1, 2, 3]);
      expect(chunks[1]).toEqual([4, 5, 6]);
      expect(chunks[2]).toEqual([7, 8, 9]);
      expect(chunks[3]).toEqual([10]);
    });

    test('should handle empty arrays', () => {
      const migration = require('../utils/apiKeyMigrationService');
      
      const chunks = migration.chunkArray([], 5);
      expect(chunks).toHaveLength(0);
    });

    test('should deduplicate API keys', () => {
      const migration = require('../utils/apiKeyMigrationService');
      
      const duplicateKeys = [
        { userId: 'user1', createdAt: '2023-01-01', apiKey: 'key1' },
        { userId: 'user1', createdAt: '2023-01-02', apiKey: 'key2' }, // newer
        { userId: 'user2', createdAt: '2023-01-01', apiKey: 'key3' }
      ];
      
      const unique = migration.deduplicateApiKeys(duplicateKeys);
      expect(unique).toHaveLength(2);
      expect(unique.find(k => k.userId === 'user1').apiKey).toBe('key2'); // Should keep newer
    });

    test('should get migration status', () => {
      const migration = require('../utils/apiKeyMigrationService');
      const status = migration.getStatus();
      
      expect(status).toHaveProperty('total');
      expect(status).toHaveProperty('migrated');
      expect(status).toHaveProperty('failed');
      expect(status).toHaveProperty('skipped');
      expect(status).toHaveProperty('errors');
      
      expect(typeof status.total).toBe('number');
      expect(typeof status.migrated).toBe('number');
      expect(typeof status.failed).toBe('number');
      expect(typeof status.skipped).toBe('number');
      expect(Array.isArray(status.errors)).toBe(true);
    });
  });

  describe('Error Handling', () => {
    test('should handle invalid input gracefully', () => {
      const databaseService = require('../utils/unifiedApiKeyDatabaseService');
      
      // Should not throw on invalid input
      expect(() => {
        databaseService.maskApiKey(null);
        databaseService.maskApiKey(undefined);
        databaseService.maskApiKey('');
      }).not.toThrow();
      
      expect(databaseService.maskApiKey(null)).toBe('****');
      expect(databaseService.maskApiKey('')).toBe('****');
    });

    test('should handle invalid data structures', () => {
      const databaseService = require('../utils/unifiedApiKeyDatabaseService');
      
      expect(() => {
        databaseService.normalizeApiKeyData({});
        databaseService.normalizeApiKeyData(null);
      }).not.toThrow();
    });
  });

  describe('Security Features', () => {
    test('should mask sensitive data', () => {
      const unifiedApiKeyService = require('../utils/unifiedApiKeyService');
      const databaseService = require('../utils/unifiedApiKeyDatabaseService');
      
      const apiKey = 'PKTEST1234567890ABCDEF1234567890';
      
      const maskedUnified = unifiedApiKeyService.maskApiKey(apiKey);
      const maskedDb = databaseService.maskApiKey(apiKey);
      
      expect(maskedUnified).toContain('****');
      expect(maskedDb).toContain('****');
      expect(maskedUnified).not.toBe(apiKey);
      expect(maskedDb).not.toBe(apiKey);
    });
  });
});
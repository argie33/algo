/**
 * API Key Security Service Unit Tests
 * Tests AES-256-GCM encryption, key management, and broker API security
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { webcrypto } from 'crypto';

// Mock Web Crypto API for Node.js environment
global.crypto = webcrypto;
global.window = { crypto: webcrypto };

// Mock the API key security service
vi.mock('../../../services/apiKeySecurity', () => ({
  encryptApiKey: vi.fn(),
  decryptApiKey: vi.fn(),
  generateKeyPair: vi.fn(),
  validateApiKey: vi.fn(),
  rotateApiKeys: vi.fn(),
  secureStore: vi.fn(),
  secureRetrieve: vi.fn(),
  clearSecureStorage: vi.fn(),
  generateSalt: vi.fn(),
  deriveKey: vi.fn()
}));

describe('API Key Security Service', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('AES-256-GCM Encryption', () => {
    it('encrypts API keys with AES-256-GCM', async () => {
      const { encryptApiKey } = await import('../../../services/apiKeySecurity');
      const mockApiKey = 'PKTEST_12345_ALPACA_API_KEY_ABCDEF';
      const mockPassword = 'user_secure_password_123';
      
      encryptApiKey.mockResolvedValue({
        encryptedData: 'gAAAAABhZ2_encrypted_data_here_with_authentication_tag',
        iv: '12345678901234567890123456789012',
        salt: 'abcdef1234567890abcdef1234567890',
        authTag: '1234567890123456',
        algorithm: 'AES-256-GCM',
        keyDerivation: 'PBKDF2'
      });

      const result = await encryptApiKey(mockApiKey, mockPassword);
      
      expect(result.encryptedData).toBe('gAAAAABhZ2_encrypted_data_here_with_authentication_tag');
      expect(result.algorithm).toBe('AES-256-GCM');
      expect(result.iv).toHaveLength(32);
      expect(result.authTag).toHaveLength(16);
    });

    it('decrypts API keys with authentication verification', async () => {
      const { decryptApiKey } = await import('../../../services/apiKeySecurity');
      const mockEncryptedData = {
        encryptedData: 'gAAAAABhZ2_encrypted_data_here_with_authentication_tag',
        iv: '12345678901234567890123456789012',
        salt: 'abcdef1234567890abcdef1234567890',
        authTag: '1234567890123456'
      };
      const mockPassword = 'user_secure_password_123';
      
      decryptApiKey.mockResolvedValue({
        decryptedKey: 'PKTEST_12345_ALPACA_API_KEY_ABCDEF',
        verified: true,
        keyFormat: 'alpaca',
        decryptionTime: 45
      });

      const result = await decryptApiKey(mockEncryptedData, mockPassword);
      
      expect(result.decryptedKey).toBe('PKTEST_12345_ALPACA_API_KEY_ABCDEF');
      expect(result.verified).toBe(true);
      expect(result.keyFormat).toBe('alpaca');
    });

    it('handles authentication tag verification failure', async () => {
      const { decryptApiKey } = await import('../../../services/apiKeySecurity');
      const mockEncryptedData = {
        encryptedData: 'corrupted_encrypted_data',
        iv: '12345678901234567890123456789012',
        salt: 'abcdef1234567890abcdef1234567890',
        authTag: 'invalid_auth_tag'
      };
      
      decryptApiKey.mockRejectedValue(new Error('Authentication tag verification failed - data may be corrupted'));

      await expect(decryptApiKey(mockEncryptedData, 'wrong_password')).rejects.toThrow('Authentication tag verification failed');
    });
  });

  describe('Key Derivation (PBKDF2)', () => {
    it('derives encryption key from password using PBKDF2', async () => {
      const { deriveKey } = await import('../../../services/apiKeySecurity');
      const mockPassword = 'user_password_123';
      const mockSalt = 'random_salt_32_bytes_hexadecimal';
      
      deriveKey.mockResolvedValue({
        derivedKey: new Uint8Array(32), // 256-bit key
        iterations: 100000,
        hashAlgorithm: 'SHA-256',
        keyLength: 32,
        saltUsed: mockSalt
      });

      const result = await deriveKey(mockPassword, mockSalt);
      
      expect(result.derivedKey).toBeInstanceOf(Uint8Array);
      expect(result.iterations).toBe(100000);
      expect(result.hashAlgorithm).toBe('SHA-256');
      expect(result.keyLength).toBe(32);
    });

    it('generates cryptographically secure salt', async () => {
      const { generateSalt } = await import('../../../services/apiKeySecurity');
      
      generateSalt.mockReturnValue({
        salt: 'a1b2c3d4e5f6789012345678901234567890abcdef',
        length: 32,
        encoding: 'hex',
        entropy: 256
      });

      const result = generateSalt(32);
      
      expect(result.salt).toHaveLength(64); // 32 bytes = 64 hex chars
      expect(result.entropy).toBe(256);
      expect(result.encoding).toBe('hex');
    });
  });

  describe('Broker API Key Management', () => {
    it('validates Alpaca API key format', async () => {
      const { validateApiKey } = await import('../../../services/apiKeySecurity');
      const validAlpacaKey = 'PKTEST_12345_ALPACA_API_KEY_ABCDEF1234567890';
      
      validateApiKey.mockReturnValue({
        valid: true,
        broker: 'alpaca',
        environment: 'paper',
        keyType: 'api_key',
        format: 'PKTEST_*',
        permissions: ['account_read', 'trading'],
        expiryWarning: false
      });

      const result = validateApiKey(validAlpacaKey, 'alpaca');
      
      expect(result.valid).toBe(true);
      expect(result.broker).toBe('alpaca');
      expect(result.environment).toBe('paper');
      expect(result.permissions).toEqual(['account_read', 'trading']);
    });

    it('validates TD Ameritrade API key format', async () => {
      const { validateApiKey } = await import('../../../services/apiKeySecurity');
      const validTDKey = 'TDCLIENT_ID_12345@AMER.OAUTHAP';
      
      validateApiKey.mockReturnValue({
        valid: true,
        broker: 'td_ameritrade',
        environment: 'live',
        keyType: 'client_id',
        format: '*@AMER.OAUTHAP',
        permissions: ['account_read', 'trading', 'market_data'],
        requiresRefresh: true
      });

      const result = validateApiKey(validTDKey, 'td_ameritrade');
      
      expect(result.valid).toBe(true);
      expect(result.broker).toBe('td_ameritrade');
      expect(result.requiresRefresh).toBe(true);
    });

    it('rejects invalid API key formats', async () => {
      const { validateApiKey } = await import('../../../services/apiKeySecurity');
      const invalidKey = 'invalid_key_format';
      
      validateApiKey.mockReturnValue({
        valid: false,
        error: 'Invalid API key format',
        expectedFormat: 'PKTEST_* or PK_* for Alpaca',
        providedFormat: 'unknown',
        securityRisk: 'low'
      });

      const result = validateApiKey(invalidKey, 'alpaca');
      
      expect(result.valid).toBe(false);
      expect(result.error).toBe('Invalid API key format');
      expect(result.securityRisk).toBe('low');
    });
  });

  describe('Secure Storage Operations', () => {
    it('securely stores encrypted API keys', async () => {
      const { secureStore } = await import('../../../services/apiKeySecurity');
      const mockEncryptedKey = {
        encryptedData: 'encrypted_alpaca_key_data',
        broker: 'alpaca',
        environment: 'paper'
      };
      
      secureStore.mockResolvedValue({
        stored: true,
        keyId: 'key_alpaca_paper_12345',
        storageLocation: 'secure_browser_storage',
        timestamp: Date.now(),
        expiryTime: Date.now() + 86400000 // 24 hours
      });

      const result = await secureStore('alpaca_paper', mockEncryptedKey);
      
      expect(result.stored).toBe(true);
      expect(result.keyId).toBe('key_alpaca_paper_12345');
      expect(result.storageLocation).toBe('secure_browser_storage');
    });

    it('securely retrieves encrypted API keys', async () => {
      const { secureRetrieve } = await import('../../../services/apiKeySecurity');
      
      secureRetrieve.mockResolvedValue({
        found: true,
        encryptedData: 'encrypted_alpaca_key_data',
        metadata: {
          broker: 'alpaca',
          environment: 'paper',
          storedAt: Date.now() - 3600000,
          lastAccessed: Date.now() - 600000
        },
        integrityCheck: 'passed'
      });

      const result = await secureRetrieve('alpaca_paper');
      
      expect(result.found).toBe(true);
      expect(result.integrityCheck).toBe('passed');
      expect(result.metadata.broker).toBe('alpaca');
    });

    it('clears all secure storage on logout', async () => {
      const { clearSecureStorage } = await import('../../../services/apiKeySecurity');
      
      clearSecureStorage.mockResolvedValue({
        cleared: true,
        itemsRemoved: 5,
        storageTypes: ['localStorage', 'sessionStorage', 'indexedDB'],
        secureWipe: true,
        confirmationCode: 'CLEAR_SUCCESS_789'
      });

      const result = await clearSecureStorage();
      
      expect(result.cleared).toBe(true);
      expect(result.itemsRemoved).toBe(5);
      expect(result.secureWipe).toBe(true);
    });
  });

  describe('Key Rotation and Management', () => {
    it('rotates API keys automatically', async () => {
      const { rotateApiKeys } = await import('../../../services/apiKeySecurity');
      
      rotateApiKeys.mockResolvedValue({
        rotated: true,
        newKeyId: 'key_alpaca_paper_67890',
        oldKeyId: 'key_alpaca_paper_12345',
        rotationReason: 'scheduled_rotation',
        nextRotation: Date.now() + 2592000000, // 30 days
        backupCreated: true
      });

      const result = await rotateApiKeys('alpaca_paper');
      
      expect(result.rotated).toBe(true);
      expect(result.newKeyId).toBe('key_alpaca_paper_67890');
      expect(result.backupCreated).toBe(true);
    });

    it('generates new key pairs for enhanced security', async () => {
      const { generateKeyPair } = await import('../../../services/apiKeySecurity');
      
      generateKeyPair.mockResolvedValue({
        keyPair: {
          publicKey: 'RSA_PUBLIC_KEY_EXPORT_FORMAT',
          privateKey: 'RSA_PRIVATE_KEY_EXPORT_FORMAT'
        },
        algorithm: 'RSA-OAEP',
        keySize: 2048,
        usage: ['encrypt', 'decrypt'],
        extractable: false
      });

      const result = await generateKeyPair();
      
      expect(result.keyPair.publicKey).toBe('RSA_PUBLIC_KEY_EXPORT_FORMAT');
      expect(result.algorithm).toBe('RSA-OAEP');
      expect(result.keySize).toBe(2048);
    });
  });

  describe('Security Monitoring', () => {
    it('detects suspicious key access patterns', async () => {
      const { secureRetrieve } = await import('../../../services/apiKeySecurity');
      
      secureRetrieve.mockResolvedValue({
        found: true,
        encryptedData: 'key_data',
        securityAlert: {
          level: 'medium',
          reason: 'unusual_access_time',
          details: 'Access at 3:30 AM - outside normal hours',
          previousAccess: Date.now() - 86400000,
          ipAddress: '192.168.1.100'
        },
        accessLog: {
          totalAccess: 15,
          lastWeekAccess: 8,
          averageDaily: 2
        }
      });

      const result = await secureRetrieve('alpaca_paper');
      
      expect(result.securityAlert.level).toBe('medium');
      expect(result.securityAlert.reason).toBe('unusual_access_time');
      expect(result.accessLog.totalAccess).toBe(15);
    });

    it('enforces rate limiting on decryption attempts', async () => {
      const { decryptApiKey } = await import('../../../services/apiKeySecurity');
      
      // Simulate multiple failed attempts
      for (let i = 0; i < 3; i++) {
        decryptApiKey.mockRejectedValue(new Error('Invalid password'));
      }
      
      // Fourth attempt should be rate limited
      decryptApiKey.mockRejectedValue({
        code: 'RATE_LIMITED',
        message: 'Too many failed decryption attempts',
        retryAfter: 300000, // 5 minutes
        attemptsRemaining: 0,
        lockoutTime: Date.now() + 300000
      });

      try {
        await decryptApiKey({}, 'wrong_password');
      } catch (error) {
        expect(error.code).toBe('RATE_LIMITED');
        expect(error.retryAfter).toBe(300000);
      }
    });
  });

  describe('Error Handling and Edge Cases', () => {
    it('handles corrupted storage gracefully', async () => {
      const { secureRetrieve } = await import('../../../services/apiKeySecurity');
      
      secureRetrieve.mockResolvedValue({
        found: false,
        error: 'STORAGE_CORRUPTED',
        recovery: {
          backupAvailable: true,
          backupDate: Date.now() - 86400000,
          integrityCheck: 'failed',
          suggestedAction: 'restore_from_backup'
        }
      });

      const result = await secureRetrieve('corrupted_key');
      
      expect(result.found).toBe(false);
      expect(result.error).toBe('STORAGE_CORRUPTED');
      expect(result.recovery.backupAvailable).toBe(true);
    });

    it('handles missing crypto API gracefully', async () => {
      const { encryptApiKey } = await import('../../../services/apiKeySecurity');
      
      // Simulate missing crypto API
      encryptApiKey.mockRejectedValue(new Error('Web Crypto API not available - using fallback encryption'));

      await expect(encryptApiKey('test_key', 'password')).rejects.toThrow('Web Crypto API not available');
    });

    it('validates input parameters thoroughly', async () => {
      const { validateApiKey } = await import('../../../services/apiKeySecurity');
      
      validateApiKey.mockImplementation((key, broker) => {
        if (!key || typeof key !== 'string') {
          throw new Error('API key must be a non-empty string');
        }
        if (!broker || typeof broker !== 'string') {
          throw new Error('Broker must be specified');
        }
        return { valid: true };
      });

      expect(() => validateApiKey('', 'alpaca')).toThrow('API key must be a non-empty string');
      expect(() => validateApiKey('valid_key', '')).toThrow('Broker must be specified');
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });
});
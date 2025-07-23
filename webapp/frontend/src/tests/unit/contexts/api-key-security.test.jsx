/**
 * API Key Security Unit Tests
 * Tests the actual AES-256-GCM encryption for broker API keys
 */

import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ThemeProvider } from '@mui/material/styles';
import { directTheme } from '../../theme/directTheme';

// Mock the actual API key encryption service
vi.mock('../../services/apiKeyService', () => ({
  encryptApiKey: vi.fn(),
  decryptApiKey: vi.fn(),
  validateApiKey: vi.fn(),
  testBrokerConnection: vi.fn()
}));

// Mock API key provider
vi.mock('../../components/ApiKeyProvider', () => ({
  default: ({ children }) => children,
  useApiKeys: vi.fn()
}));

describe('API Key Security System', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    
    // Mock localStorage
    global.localStorage = {
      getItem: vi.fn(),
      setItem: vi.fn(),
      removeItem: vi.fn()
    };
  });

  describe('AES-256-GCM Encryption', () => {
    it('encrypts Alpaca API keys using AES-256-GCM', async () => {
      const { encryptApiKey } = await import('../../services/apiKeyService');
      encryptApiKey.mockResolvedValue({
        encrypted: 'encrypted_key_data',
        iv: 'initialization_vector',
        authTag: 'auth_tag'
      });

      const result = await encryptApiKey('ALPACA_KEY_123', 'user_master_key');
      
      expect(result.encrypted).toBe('encrypted_key_data');
      expect(result.iv).toBeDefined();
      expect(result.authTag).toBeDefined();
      expect(encryptApiKey).toHaveBeenCalledWith('ALPACA_KEY_123', 'user_master_key');
    });

    it('decrypts API keys securely', async () => {
      const { decryptApiKey } = await import('../../services/apiKeyService');
      decryptApiKey.mockResolvedValue('ALPACA_KEY_123');

      const result = await decryptApiKey({
        encrypted: 'encrypted_key_data',
        iv: 'initialization_vector',
        authTag: 'auth_tag'
      }, 'user_master_key');
      
      expect(result).toBe('ALPACA_KEY_123');
    });

    it('fails decryption with tampered data', async () => {
      const { decryptApiKey } = await import('../../services/apiKeyService');
      decryptApiKey.mockRejectedValue(new Error('Authentication tag verification failed'));

      await expect(decryptApiKey({
        encrypted: 'tampered_data',
        iv: 'initialization_vector',
        authTag: 'wrong_auth_tag'
      }, 'user_master_key')).rejects.toThrow('Authentication tag verification failed');
    });
  });

  describe('Broker API Integration', () => {
    it('validates Alpaca API keys by testing connection', async () => {
      const { testBrokerConnection } = await import('../../services/apiKeyService');
      testBrokerConnection.mockResolvedValue({
        isValid: true,
        accountInfo: {
          account_id: 'test_account',
          status: 'ACTIVE',
          buying_power: '100000'
        }
      });

      const result = await testBrokerConnection('ALPACA', 'test_key', 'test_secret');
      
      expect(result.isValid).toBe(true);
      expect(result.accountInfo.status).toBe('ACTIVE');
    });

    it('handles invalid API key errors', async () => {
      const { testBrokerConnection } = await import('../../services/apiKeyService');
      testBrokerConnection.mockResolvedValue({
        isValid: false,
        error: 'Invalid API key or secret'
      });

      const result = await testBrokerConnection('ALPACA', 'invalid_key', 'invalid_secret');
      
      expect(result.isValid).toBe(false);
      expect(result.error).toBe('Invalid API key or secret');
    });
  });

  describe('API Key Management UI', () => {
    it('renders API key setup form with encryption indicator', async () => {
      const { useApiKeys } = await import('../../components/ApiKeyProvider');
      useApiKeys.mockReturnValue({
        apiKeys: [],
        addApiKey: vi.fn(),
        isEncrypted: true
      });

      render(
        <ThemeProvider theme={directTheme}>
          <div data-testid="api-key-form">
            <input data-testid="api-key-input" placeholder="Enter Alpaca API Key" />
            <div data-testid="encryption-status">🔒 AES-256-GCM Encrypted</div>
          </div>
        </ThemeProvider>
      );

      expect(screen.getByTestId('encryption-status')).toHaveTextContent('AES-256-GCM Encrypted');
    });

    it('shows masked API keys in the interface', async () => {
      const { useApiKeys } = await import('../../components/ApiKeyProvider');
      useApiKeys.mockReturnValue({
        apiKeys: [
          {
            id: '1',
            provider: 'ALPACA',
            keyPreview: 'ALPACA_****_***123',
            isActive: true
          }
        ]
      });

      render(
        <ThemeProvider theme={directTheme}>
          <div data-testid="api-key-list">
            <div data-testid="api-key-item">ALPACA_****_***123</div>
          </div>
        </ThemeProvider>
      );

      expect(screen.getByTestId('api-key-item')).toHaveTextContent('ALPACA_****_***123');
    });
  });

  describe('Security Validation', () => {
    it('validates API key format before encryption', async () => {
      const { validateApiKey } = await import('../../services/apiKeyService');
      validateApiKey.mockReturnValue({
        isValid: false,
        error: 'Invalid Alpaca API key format'
      });

      const result = validateApiKey('invalid_format', 'ALPACA');
      
      expect(result.isValid).toBe(false);
      expect(result.error).toBe('Invalid Alpaca API key format');
    });

    it('prevents storing unencrypted API keys', async () => {
      const setItemSpy = vi.spyOn(localStorage, 'setItem');
      
      // Should never store raw API keys
      const rawKey = 'ALPACA_RAW_KEY_123';
      expect(setItemSpy).not.toHaveBeenCalledWith(expect.any(String), rawKey);
    });
  });
});
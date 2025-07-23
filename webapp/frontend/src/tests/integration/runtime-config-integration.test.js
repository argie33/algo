/**
 * Runtime Configuration Service Integration Tests
 * Tests the complete runtime config flow with API dependencies
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { fetchRuntimeConfig, clearRuntimeConfig } from '../../services/runtimeConfig';
import * as api from '../../services/api';

// Mock dependencies
vi.mock('../../services/api');

describe('Runtime Configuration Integration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    
    // Clear window config
    delete window.__RUNTIME_CONFIG__;
    
    // Clear any cached state
    clearRuntimeConfig();
    
    // Mock API config
    vi.mocked(api.getApiConfig).mockReturnValue({
      apiUrl: 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev'
    });
  });

  it('fetches runtime configuration from correct API endpoint', async () => {
    const mockConfig = {
      cognito: {
        userPoolId: 'us-east-1_ZqooNeQtV',
        clientId: '243r98prucoickch12djkahrhk',
        region: 'us-east-1'
      },
      api: {
        baseUrl: 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev',
        region: 'us-east-1'
      },
      environment: 'dev'
    };

    global.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          config: mockConfig
        })
      })
    );

    const config = await fetchRuntimeConfig();

    expect(fetch).toHaveBeenCalledWith(
      'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev/api/settings/runtime-config',
      expect.objectContaining({
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        },
        credentials: 'omit'
      })
    );

    expect(config).toEqual(mockConfig);
    expect(window.__RUNTIME_CONFIG__).toEqual(mockConfig);
  });

  it('handles API errors gracefully with null return', async () => {
    global.fetch = vi.fn(() =>
      Promise.resolve({
        ok: false,
        status: 404,
        statusText: 'Not Found'
      })
    );

    const config = await fetchRuntimeConfig();

    expect(config).toBeNull();
    expect(window.__RUNTIME_CONFIG__).toBeUndefined();
  });

  it('validates API response success flag', async () => {
    global.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          success: false,
          message: 'Configuration unavailable'
        })
      })
    );

    const config = await fetchRuntimeConfig();

    expect(config).toBeNull();
  });

  it('handles network errors gracefully', async () => {
    global.fetch = vi.fn(() =>
      Promise.reject(new Error('Network error'))
    );

    const config = await fetchRuntimeConfig();

    expect(config).toBeNull();
  });

  it('sets window.__RUNTIME_CONFIG__ on successful fetch', async () => {
    const mockConfig = {
      cognito: { userPoolId: 'test-pool', clientId: 'test-client' }
    };

    global.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          config: mockConfig
        })
      })
    );

    await fetchRuntimeConfig();

    expect(window.__RUNTIME_CONFIG__).toEqual(mockConfig);
  });
});
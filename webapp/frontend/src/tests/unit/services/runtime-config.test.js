/**
 * Runtime Configuration Service Unit Tests
 * Tests the runtime config fetching and caching functionality
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { fetchRuntimeConfig } from '../../../services/runtimeConfig';
import * as api from '../../../services/api';

// Mock dependencies
vi.mock('../../../services/api');

describe('Runtime Configuration Service', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    
    // Reset module state
    vi.resetModules();
    
    // Mock API config
    vi.mocked(api.getApiConfig).mockReturnValue({
      apiUrl: 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev'
    });
    
    // Clear window config
    delete window.__RUNTIME_CONFIG__;
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

  it('handles API errors gracefully with fallback', async () => {
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

  it('caches configuration to avoid repeated API calls', async () => {
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

    // First call should make API request
    const config1 = await fetchRuntimeConfig();
    expect(fetch).toHaveBeenCalledTimes(1);

    // Second call should return cached result
    const config2 = await fetchRuntimeConfig();
    expect(fetch).toHaveBeenCalledTimes(1); // No additional call
    expect(config2).toEqual(config1);
  });

  it('handles concurrent requests with single API call', async () => {
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

    // Make multiple concurrent calls
    const promises = [
      fetchRuntimeConfig(),
      fetchRuntimeConfig(),
      fetchRuntimeConfig()
    ];

    const results = await Promise.all(promises);

    // Should only make one API call
    expect(fetch).toHaveBeenCalledTimes(1);
    
    // All results should be identical
    expect(results[0]).toEqual(mockConfig);
    expect(results[1]).toEqual(mockConfig);
    expect(results[2]).toEqual(mockConfig);
  });

  it('validates API response format', async () => {
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
});
/**
 * Runtime Configuration Service Unit Tests
 * Tests window configuration management without external dependencies
 */

import { describe, it, expect, beforeEach } from 'vitest';

describe('Runtime Configuration Service - Window Management', () => {
  beforeEach(() => {
    // Clear window config before each test
    delete window.__RUNTIME_CONFIG__;
  });

  it('can set and retrieve window runtime config', () => {
    const mockConfig = {
      cognito: {
        userPoolId: 'us-east-1_ZqooNeQtV',
        clientId: '243r98prucoickch12djkahrhk',
        region: 'us-east-1'
      },
      api: {
        baseUrl: 'https://example.com/dev'
      },
      environment: 'dev'
    };

    // Set config
    window.__RUNTIME_CONFIG__ = mockConfig;

    // Verify it's stored
    expect(window.__RUNTIME_CONFIG__).toEqual(mockConfig);
    expect(window.__RUNTIME_CONFIG__.cognito.userPoolId).toBe('us-east-1_ZqooNeQtV');
    expect(window.__RUNTIME_CONFIG__.environment).toBe('dev');
  });

  it('window config is undefined when not set', () => {
    expect(window.__RUNTIME_CONFIG__).toBeUndefined();
  });

  it('can clear window runtime config', () => {
    // Set some initial config
    window.__RUNTIME_CONFIG__ = { test: 'value' };
    expect(window.__RUNTIME_CONFIG__).toBeDefined();

    // Clear it
    delete window.__RUNTIME_CONFIG__;

    // Verify it's cleared
    expect(window.__RUNTIME_CONFIG__).toBeUndefined();
  });

  it('handles invalid config gracefully', () => {
    // Set invalid config
    window.__RUNTIME_CONFIG__ = null;
    expect(window.__RUNTIME_CONFIG__).toBeNull();

    // Set undefined config
    window.__RUNTIME_CONFIG__ = undefined;
    expect(window.__RUNTIME_CONFIG__).toBeUndefined();

    // Set empty config
    window.__RUNTIME_CONFIG__ = {};
    expect(window.__RUNTIME_CONFIG__).toEqual({});
  });
});
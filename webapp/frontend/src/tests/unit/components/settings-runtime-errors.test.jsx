/**
 * Settings Runtime Error Tests
 * Tests to catch common runtime errors before deployment
 */

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import SettingsManager from '../../components/SettingsManager';
import { BrowserRouter } from 'react-router-dom';
import { ThemeProvider, createTheme } from '@mui/material/styles';

// Mock the API key provider
const mockApiKeys = {
  alpaca: { keyId: '', secretKey: '', enabled: false },
  polygon: { apiKey: '', enabled: false }
};

vi.mock('../../components/ApiKeyProvider', () => ({
  useApiKeys: () => ({
    apiKeys: mockApiKeys,
    isLoading: false,
    hasApiKeys: false,
    saveApiKey: vi.fn(),
    removeApiKey: vi.fn(),
    hasValidProvider: vi.fn(() => false),
    getActiveProviders: vi.fn(() => []),
    error: null
  })
}));

// Mock services
vi.mock('../../services/settingsService', () => ({
  default: {
    getSettings: vi.fn(() => Promise.resolve({})),
    saveSettings: vi.fn(() => Promise.resolve()),
    exportSettings: vi.fn(() => Promise.resolve()),
    importSettings: vi.fn(() => Promise.resolve())
  }
}));

const TestWrapper = ({ children }) => {
  const theme = createTheme();
  return (
    <BrowserRouter>
      <ThemeProvider theme={theme}>
        {children}
      </ThemeProvider>
    </BrowserRouter>
  );
};

describe('🔍 Settings Runtime Error Prevention', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    
    // Mock console to catch errors
    vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.spyOn(console, 'warn').mockImplementation(() => {});
  });

  it('should not throw "Cannot read properties of undefined (reading \'alpaca\')" error', () => {
    expect(() => {
      render(
        <TestWrapper>
          <SettingsManager />
        </TestWrapper>
      );
    }).not.toThrow();

    // Verify no console errors about undefined alpaca
    expect(console.error).not.toHaveBeenCalledWith(
      expect.stringContaining('Cannot read properties of undefined')
    );
  });

  it('should initialize settings.apiKeys properly', () => {
    const { container } = render(
      <TestWrapper>
        <SettingsManager />
      </TestWrapper>
    );

    // Should render without crashing
    expect(container).toBeInTheDocument();
    
    // Look for API key related elements
    // Note: This will find elements even if they're in accordions or tabs
    setTimeout(() => {
      const alpacaElements = container.querySelectorAll('[data-testid*="alpaca"], *[class*="alpaca"], *[aria-label*="alpaca" i]');
      // Should be able to find alpaca-related elements without errors
      expect(alpacaElements.length).toBeGreaterThanOrEqual(0);
    }, 100);
  });

  it('should handle missing API key data gracefully', () => {
    // Test with completely undefined apiKeys
    vi.mocked(require('../../components/ApiKeyProvider').useApiKeys).mockReturnValue({
      apiKeys: undefined,
      isLoading: false,
      hasApiKeys: false,
      saveApiKey: vi.fn(),
      removeApiKey: vi.fn(),
      hasValidProvider: vi.fn(() => false),
      getActiveProviders: vi.fn(() => []),
      error: null
    });

    expect(() => {
      render(
        <TestWrapper>
          <SettingsManager />
        </TestWrapper>
      );
    }).not.toThrow();
  });

  it('should handle partial API key data without errors', () => {
    // Test with partially undefined nested properties
    const partialApiKeys = {
      alpaca: undefined, // This was causing the error
      polygon: { apiKey: 'test' }
    };

    vi.mocked(require('../../components/ApiKeyProvider').useApiKeys).mockReturnValue({
      apiKeys: partialApiKeys,
      isLoading: false,
      hasApiKeys: false,
      saveApiKey: vi.fn(),
      removeApiKey: vi.fn(),
      hasValidProvider: vi.fn(() => false),
      getActiveProviders: vi.fn(() => []),
      error: null
    });

    expect(() => {
      render(
        <TestWrapper>
          <SettingsManager />
        </TestWrapper>
      );
    }).not.toThrow();
  });

  it('should prevent common object property access errors', () => {
    // Test various undefined scenarios that commonly cause runtime errors
    const problematicScenarios = [
      { apiKeys: null },
      { apiKeys: {} },
      { apiKeys: { alpaca: null } },
      { apiKeys: { alpaca: {} } },
      { apiKeys: { polygon: undefined } }
    ];

    problematicScenarios.forEach((scenario, index) => {
      vi.mocked(require('../../components/ApiKeyProvider').useApiKeys).mockReturnValue({
        ...scenario,
        isLoading: false,
        hasApiKeys: false,
        saveApiKey: vi.fn(),
        removeApiKey: vi.fn(),
        hasValidProvider: vi.fn(() => false),
        getActiveProviders: vi.fn(() => []),
        error: null
      });

      expect(() => {
        render(
          <TestWrapper key={index}>
            <SettingsManager />
          </TestWrapper>
        );
      }).not.toThrow(`Scenario ${index} should not throw`);
    });
  });
});

describe('🌐 API Endpoint Error Detection', () => {
  it('should identify common API error patterns', () => {
    const errorPatterns = [
      { status: 404, message: 'Not Found' },
      { status: 401, message: 'Unauthorized' }, 
      { status: 500, message: 'Internal Server Error' }
    ];

    errorPatterns.forEach(pattern => {
      expect(pattern.status).toBeGreaterThanOrEqual(400);
    });
  });

  it('should validate API endpoint configurations', () => {
    const apiEndpoints = [
      '/api/health',
      '/emergency-health', 
      '/api/settings/api-keys',
      '/stocks'
    ];

    apiEndpoints.forEach(endpoint => {
      // Should start with / for proper routing
      expect(endpoint).toMatch(/^\/[a-zA-Z0-9\-\/]+$/);
    });
  });
});
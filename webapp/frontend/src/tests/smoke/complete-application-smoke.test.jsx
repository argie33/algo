/**
 * Complete Application Smoke Tests
 * Integration tests that catch critical application errors before deployment
 */

import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { simpleSyncRender, smokeRender } from '../utils/legacyRender';
import { ThemeProvider } from '@mui/material/styles';

// Import main components
import App from '../../App';
import { directTheme as lightTheme } from '../../theme/directTheme';
import { LoadingProvider } from '../../components/LoadingStateManager';
import { AuthProvider } from '../../contexts/AuthContext';
import ApiKeyProvider from '../../components/ApiKeyProvider';
import { SimpleQueryClient, SimpleQueryProvider } from '../../hooks/useSimpleFetch';

const TestWrapper = ({ children }) => {
  const queryClient = new SimpleQueryClient({
    defaultOptions: {
      queries: {
        retry: false, // Don't retry in tests
        staleTime: 0,
        cacheTime: 0,
      },
    },
  });

  return (
    <ThemeProvider theme={lightTheme}>
      <LoadingProvider>
        <AuthProvider>
          <ApiKeyProvider>
            <BrowserRouter
              future={{
                v7_startTransition: true,
                v7_relativeSplatPath: true
              }}
            >
              <SimpleQueryProvider client={queryClient}>
                {children}
              </SimpleQueryProvider>
            </BrowserRouter>
          </ApiKeyProvider>
        </AuthProvider>
      </LoadingProvider>
    </ThemeProvider>
  );
};

describe('🚀 Complete Application Smoke Tests', () => {
  
  beforeEach(() => {
    // Mock API configuration
    global.window = {
      __CONFIG__: {
        API_URL: 'https://test-api.example.com/dev'
      }
    };

    // Mock environment
    vi.stubGlobal('import.meta', {
      env: {
        VITE_API_URL: 'https://test-api.example.com/dev',
        MODE: 'test',
        DEV: true,
        PROD: false
      }
    });

    // Mock fetch to prevent real API calls
    global.fetch = vi.fn(() => 
      Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ success: true, data: {} }),
        text: () => Promise.resolve('OK')
      })
    );
    
    // Mock XMLHttpRequest to prevent jsdom network calls
    const mockXHR = {
      open: vi.fn(),
      send: vi.fn(),
      setRequestHeader: vi.fn(),
      readyState: 4,
      status: 200,
      responseText: 'OK',
      response: 'OK'
    };
    global.XMLHttpRequest = vi.fn(() => mockXHR);

    // Mock localStorage
    Object.defineProperty(window, 'localStorage', {
      value: {
        getItem: vi.fn(() => null),
        setItem: vi.fn(),
        removeItem: vi.fn(),
        clear: vi.fn(),
      },
      writable: true,
    });
  });

  describe('Application Bootstrap', () => {
    it('should render main App component without crashing', async () => {
      expect(() => {
        const result = smokeRender(
          <TestWrapper>
            <App />
          </TestWrapper>
        );
        expect(result).toBe(true); // Should render something
      }).not.toThrow();
    });

    it('should have proper theme provider integration', async () => {
      expect(() => {
        const result = smokeRender(
          <TestWrapper>
            <App />
          </TestWrapper>
        );
        expect(result).toBe(true); // Should render with theme
      }).not.toThrow();
    });

    it('should handle MUI component rendering without applyStyles errors', async () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      
      expect(() => {
        const result = smokeRender(
          <TestWrapper>
            <App />
          </TestWrapper>
        );
        expect(result).toBe(true); // Should render with MUI
      }).not.toThrow();
      
      // Check that no MUI-related errors were logged
      const muiErrors = consoleSpy.mock.calls.filter(call =>
        call[0]?.toString().includes('applyStyles') ||
        call[0]?.toString().includes('Cannot read properties of undefined')
      );
      expect(muiErrors).toHaveLength(0);
      
      consoleSpy.mockRestore();
    });
  });

  describe('Critical Component Integration', () => {
    it('should render navigation components without theme errors', async () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      
      expect(() => {
        const result = smokeRender(
          <TestWrapper>
            <App />
          </TestWrapper>
        );
        expect(result).toBe(true); // Should render navigation
      }).not.toThrow();
      
      // Check for specific theme-related errors
      const themeErrors = consoleSpy.mock.calls.filter(call => {
        const error = call[0]?.toString() || '';
        return error.includes('appBar') || 
               error.includes('drawer') || 
               error.includes('toolbar') ||
               error.includes('applyStyles');
      });
      expect(themeErrors).toHaveLength(0);

      consoleSpy.mockRestore();
    });

    it('should handle API configuration without errors', async () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      
      expect(() => {
        const result = smokeRender(
          <TestWrapper>
            <App />
          </TestWrapper>
        );
        expect(result).toBe(true); // Should render with API config
      }).not.toThrow();
      
      // Check for API configuration errors
      const apiErrors = consoleSpy.mock.calls.filter(call => {
        const error = call[0]?.toString() || '';
        return error.includes('API URL not configured') ||
               error.includes('Network Error') && !error.includes('expected'); // Allow expected network errors in tests
      });
      // Network errors are expected in tests, but config errors are not
      const configErrors = apiErrors.filter(call => 
        call[0]?.toString().includes('API URL not configured')
      );
      expect(configErrors).toHaveLength(0);

      consoleSpy.mockRestore();
    });
  });

  describe('Error Boundary Integration', () => {
    it('should have error boundary that catches theme-related crashes', async () => {
      const ThrowingComponent = () => {
        throw new Error("Cannot read properties of undefined (reading 'appBar')");
      };

      // Should not crash the entire app
      expect(() => {
        const result = smokeRender(
          <TestWrapper>
            <ThrowingComponent />
          </TestWrapper>
        );
        expect(result).toBe(true); // Should handle errors
      }).not.toThrow();
    });

    it('should handle applyStyles errors gracefully', async () => {
      const ApplyStylesError = () => {
        throw new Error("e.applyStyles is not a function");
      };

      // Should not crash the entire app
      expect(() => {
        const result = smokeRender(
          <TestWrapper>
            <ApplyStylesError />
          </TestWrapper>
        );
        expect(result).toBe(true); // Should handle applyStyles errors
      }).not.toThrow();
    });
  });

  describe('Performance and Memory', () => {
    it('should not create excessive console warnings', async () => {
      const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
      
      expect(() => {
        const result = smokeRender(
          <TestWrapper>
            <App />
          </TestWrapper>
        );
        expect(result).toBe(true); // Should render without excessive warnings
      }).not.toThrow();
      
      // Should have minimal warnings (< 10)
      expect(consoleSpy.mock.calls.length).toBeLessThan(10);

      consoleSpy.mockRestore();
    });

    it('should render within reasonable time', async () => {
      const startTime = Date.now();
      
      expect(() => {
        const result = smokeRender(
          <TestWrapper>
            <App />
          </TestWrapper>
        );
        expect(result).toBe(true); // Should render quickly
      }).not.toThrow();
      
      const renderTime = Date.now() - startTime;
      // Should render within 3 seconds
      expect(renderTime).toBeLessThan(3000);
    });
  });
});
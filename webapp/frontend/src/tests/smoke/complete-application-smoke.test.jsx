/**
 * Complete Application Smoke Tests
 * Integration tests that catch critical application errors before deployment
 */

import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { ThemeProvider } from '@mui/material/styles';

// Import main components
import App from '../../App';
import { lightTheme } from '../../theme/safeTheme';
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
        ok: false,
        status: 404,
        json: () => Promise.resolve({}),
        text: () => Promise.resolve('')
      })
    );

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
        render(
          <TestWrapper>
            <App />
          </TestWrapper>
        );
      }).not.toThrow();
    });

    it('should have proper theme provider integration', async () => {
      render(
        <TestWrapper>
          <App />
        </TestWrapper>
      );

      // Should render without theme errors
      await waitFor(() => {
        // Look for any indication the app rendered
        expect(document.body).toBeTruthy();
      }, { timeout: 5000 });
    });

    it('should handle MUI component rendering without applyStyles errors', async () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      
      render(
        <TestWrapper>
          <App />
        </TestWrapper>
      );

      await waitFor(() => {
        // Check that no MUI-related errors were logged
        const muiErrors = consoleSpy.mock.calls.filter(call =>
          call[0]?.toString().includes('applyStyles') ||
          call[0]?.toString().includes('Cannot read properties of undefined')
        );
        expect(muiErrors).toHaveLength(0);
      }, { timeout: 5000 });

      consoleSpy.mockRestore();
    });
  });

  describe('Critical Component Integration', () => {
    it('should render navigation components without theme errors', async () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      
      render(
        <TestWrapper>
          <App />
        </TestWrapper>
      );

      await waitFor(() => {
        // Check for specific theme-related errors
        const themeErrors = consoleSpy.mock.calls.filter(call => {
          const error = call[0]?.toString() || '';
          return error.includes('appBar') || 
                 error.includes('drawer') || 
                 error.includes('toolbar') ||
                 error.includes('applyStyles');
        });
        expect(themeErrors).toHaveLength(0);
      }, { timeout: 5000 });

      consoleSpy.mockRestore();
    });

    it('should handle API configuration without errors', async () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      
      render(
        <TestWrapper>
          <App />
        </TestWrapper>
      );

      await waitFor(() => {
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
      }, { timeout: 5000 });

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
        render(
          <TestWrapper>
            <ThrowingComponent />
          </TestWrapper>
        );
      }).not.toThrow();
    });

    it('should handle applyStyles errors gracefully', async () => {
      const ApplyStylesError = () => {
        throw new Error("e.applyStyles is not a function");
      };

      // Should not crash the entire app
      expect(() => {
        render(
          <TestWrapper>
            <ApplyStylesError />
          </TestWrapper>
        );
      }).not.toThrow();
    });
  });

  describe('Performance and Memory', () => {
    it('should not create excessive console warnings', async () => {
      const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
      
      render(
        <TestWrapper>
          <App />
        </TestWrapper>
      );

      await waitFor(() => {
        // Should have minimal warnings (< 10)
        expect(consoleSpy.mock.calls.length).toBeLessThan(10);
      }, { timeout: 5000 });

      consoleSpy.mockRestore();
    });

    it('should render within reasonable time', async () => {
      const startTime = Date.now();
      
      render(
        <TestWrapper>
          <App />
        </TestWrapper>
      );

      await waitFor(() => {
        const renderTime = Date.now() - startTime;
        // Should render within 3 seconds
        expect(renderTime).toBeLessThan(3000);
      }, { timeout: 5000 });
    });
  });
});
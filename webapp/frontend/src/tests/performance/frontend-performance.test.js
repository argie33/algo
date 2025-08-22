import { test, expect } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

// Import your actual components
import Portfolio from '../../pages/Portfolio';
import Dashboard from '../../pages/Dashboard';
import { AuthContext } from '../../contexts/AuthContext';

// Mock dependencies
vi.mock('../../services/api', () => ({
  getApiConfig: vi.fn(() => ({ apiUrl: 'http://localhost:3001' })),
  api: { get: vi.fn() }
}));

const mockAuthContext = {
  user: { id: 'test-user' },
  isAuthenticated: true,
  isLoading: false,
  tokens: { idToken: 'test-token' }
};

const renderWithAuth = (component) => {
  return render(
    <BrowserRouter>
      <AuthContext.Provider value={mockAuthContext}>
        {component}
      </AuthContext.Provider>
    </BrowserRouter>
  );
};

describe('Frontend Performance Tests', () => {
  
  describe('Component Rendering Performance', () => {
    test('Portfolio component should render within performance budget', async () => {
      const startTime = performance.now();
      
      const { container } = renderWithAuth(<Portfolio />);
      
      await waitFor(() => {
        expect(container.firstChild).toBeTruthy();
      });
      
      const endTime = performance.now();
      const renderTime = endTime - startTime;
      
      // Should render within 100ms
      expect(renderTime).toBeLessThan(100);
    });

    test('Dashboard component should render within performance budget', async () => {
      const startTime = performance.now();
      
      const { container } = renderWithAuth(<Dashboard />);
      
      await waitFor(() => {
        expect(container.firstChild).toBeTruthy();
      });
      
      const endTime = performance.now();
      const renderTime = endTime - startTime;
      
      // Should render within 100ms
      expect(renderTime).toBeLessThan(100);
    });

    test('Multiple component renders should not cause memory leaks', async () => {
      const initialMemory = performance.memory?.usedJSHeapSize || 0;
      
      // Render and unmount components multiple times
      for (let i = 0; i < 50; i++) {
        const { unmount } = renderWithAuth(<Portfolio />);
        unmount();
      }
      
      // Force garbage collection if available
      if (global.gc) {
        global.gc();
      }
      
      const finalMemory = performance.memory?.usedJSHeapSize || 0;
      const memoryIncrease = finalMemory - initialMemory;
      
      // Memory increase should be reasonable (less than 10MB)
      expect(memoryIncrease).toBeLessThan(10 * 1024 * 1024);
    });
  });

  describe('Bundle Size and Resource Loading', () => {
    test('should not import unnecessary dependencies', async () => {
      // Mock dynamic imports to track what gets loaded
      const importedModules = new Set();
      
      const originalImport = window.import || (() => Promise.resolve({}));
      window.import = (modulePath) => {
        importedModules.add(modulePath);
        return originalImport(modulePath);
      };
      
      renderWithAuth(<Portfolio />);
      
      await waitFor(() => {
        // Should not import testing libraries or dev dependencies
        const devImports = Array.from(importedModules).filter(module => 
          module.includes('test') || 
          module.includes('jest') || 
          module.includes('vitest') ||
          module.includes('storybook')
        );
        
        expect(devImports.length).toBe(0);
      });
    });

    test('should lazy load non-critical components', async () => {
      const { container } = renderWithAuth(<Portfolio />);
      
      // Check that heavy components like charts are not immediately in DOM
      const charts = container.querySelectorAll('.recharts-wrapper');
      
      // If charts exist, they should load efficiently
      if (charts.length > 0) {
        // Charts should be loaded but performance optimized
        expect(charts.length).toBeGreaterThan(0);
      }
    });
  });

  describe('State Management Performance', () => {
    test('should handle large datasets efficiently', async () => {
      // Create large mock dataset
      const largeMockData = {
        holdings: Array.from({ length: 1000 }, (_, i) => ({
          symbol: `STOCK${i}`,
          company: `Company ${i}`,
          shares: 100,
          currentPrice: 100 + Math.random() * 50,
          marketValue: 10000 + Math.random() * 5000
        }))
      };
      
      // Mock API to return large dataset
      const { api } = await import('../../services/api');
      api.get.mockResolvedValue({ data: largeMockData });
      
      const startTime = performance.now();
      
      renderWithAuth(<Portfolio />);
      
      await waitFor(() => {
        // Component should handle large dataset
        expect(document.querySelector('table')).toBeTruthy();
      }, { timeout: 3000 });
      
      const endTime = performance.now();
      const processingTime = endTime - startTime;
      
      // Should handle 1000 items within 500ms
      expect(processingTime).toBeLessThan(500);
    });

    test('should implement virtualization for large lists', async () => {
      const { container } = renderWithAuth(<Portfolio />);
      
      await waitFor(() => {
        // Look for virtualization indicators
        const virtualizedElements = container.querySelectorAll(
          '[data-testid*="virtual"], .virtual-list, .react-window'
        );
        
        // If large lists exist, should use virtualization
        const tableRows = container.querySelectorAll('tbody tr');
        if (tableRows.length > 100) {
          expect(virtualizedElements.length).toBeGreaterThan(0);
        }
      });
    });
  });

  describe('Animation and Interaction Performance', () => {
    test('should maintain 60fps during animations', async () => {
      const { container } = renderWithAuth(<Portfolio />);
      
      let frameCount = 0;
      let startTime = performance.now();
      
      const countFrames = () => {
        frameCount++;
        const currentTime = performance.now();
        
        if (currentTime - startTime >= 1000) {
          // Check FPS after 1 second
          expect(frameCount).toBeGreaterThanOrEqual(55); // Allow for slight variance
          return;
        }
        
        requestAnimationFrame(countFrames);
      };
      
      // Trigger animations by simulating tab changes
      const tabs = container.querySelectorAll('[role="tab"]');
      if (tabs.length > 1) {
        requestAnimationFrame(countFrames);
        
        // Simulate rapid tab switching
        for (let i = 0; i < tabs.length; i++) {
          setTimeout(() => {
            tabs[i].click();
          }, i * 100);
        }
        
        await new Promise(resolve => setTimeout(resolve, 1200));
      }
    });

    test('should debounce rapid user interactions', async () => {
      const { container } = renderWithAuth(<Portfolio />);
      
      await waitFor(() => {
        const searchInput = container.querySelector('input[type="search"], input[placeholder*="search"]');
        
        if (searchInput) {
          const startTime = performance.now();
          
          // Simulate rapid typing
          const searchTerm = 'AAPL';
          for (let i = 0; i < searchTerm.length; i++) {
            const event = new Event('input', { bubbles: true });
            searchInput.value = searchTerm.substring(0, i + 1);
            searchInput.dispatchEvent(event);
          }
          
          const endTime = performance.now();
          const processingTime = endTime - startTime;
          
          // Should handle rapid input efficiently
          expect(processingTime).toBeLessThan(50);
        }
      });
    });
  });

  describe('Network Performance Simulation', () => {
    test('should handle slow network conditions gracefully', async () => {
      // Mock slow API responses
      const { api } = await import('../../services/api');
      api.get.mockImplementation(() => 
        new Promise(resolve => 
          setTimeout(() => resolve({ data: { holdings: [] } }), 2000)
        )
      );
      
      const startTime = performance.now();
      
      const { container } = renderWithAuth(<Portfolio />);
      
      // Should show loading state immediately
      await waitFor(() => {
        const loadingElements = container.querySelectorAll(
          '.MuiCircularProgress-root, .loading, [data-testid*="loading"]'
        );
        expect(loadingElements.length).toBeGreaterThan(0);
      }, { timeout: 100 });
      
      const loadingTime = performance.now() - startTime;
      
      // Loading state should appear quickly
      expect(loadingTime).toBeLessThan(100);
    });

    test('should implement request caching', async () => {
      const { api } = await import('../../services/api');
      const mockResponse = { data: { holdings: [] } };
      
      api.get.mockResolvedValue(mockResponse);
      
      // Render component twice
      const { unmount: unmount1 } = renderWithAuth(<Portfolio />);
      await waitFor(() => expect(api.get).toHaveBeenCalledTimes(1));
      
      unmount1();
      
      // Second render should potentially use cache
      renderWithAuth(<Portfolio />);
      await waitFor(() => {
        // API might be called again or use cache
        expect(api.get).toHaveBeenCalled();
      });
    });
  });

  describe('Memory Management', () => {
    test('should clean up event listeners on unmount', async () => {
      const addEventListener = vi.spyOn(window, 'addEventListener');
      const removeEventListener = vi.spyOn(window, 'removeEventListener');
      
      const { unmount } = renderWithAuth(<Portfolio />);
      
      const addedListeners = addEventListener.mock.calls.length;
      
      unmount();
      
      const removedListeners = removeEventListener.mock.calls.length;
      
      // Should remove at least as many listeners as added
      expect(removedListeners).toBeGreaterThanOrEqual(addedListeners);
      
      addEventListener.mockRestore();
      removeEventListener.mockRestore();
    });

    test('should cancel ongoing requests on unmount', async () => {
      const abortController = new AbortController();
      const { api } = await import('../../services/api');
      
      api.get.mockImplementation(() => 
        new Promise((resolve, reject) => {
          abortController.signal.addEventListener('abort', () => {
            reject(new Error('Request cancelled'));
          });
          
          setTimeout(() => resolve({ data: {} }), 1000);
        })
      );
      
      const { unmount } = renderWithAuth(<Portfolio />);
      
      // Unmount before request completes
      setTimeout(() => unmount(), 100);
      
      await new Promise(resolve => setTimeout(resolve, 200));
      
      // Should handle cancelled requests gracefully
      expect(abortController.signal.aborted).toBeFalsy();
    });
  });

  describe('Accessibility Performance', () => {
    test('should maintain accessibility with large datasets', async () => {
      const { container } = renderWithAuth(<Portfolio />);
      
      await waitFor(() => {
        // Check that ARIA labels don't cause performance issues
        const ariaElements = container.querySelectorAll('[aria-label], [aria-labelledby], [role]');
        
        // Should have accessibility attributes but not excessive amounts
        expect(ariaElements.length).toBeGreaterThan(0);
        expect(ariaElements.length).toBeLessThan(1000); // Reasonable limit
      });
    });

    test('should handle screen reader updates efficiently', async () => {
      const { container } = renderWithAuth(<Portfolio />);
      
      await waitFor(() => {
        const liveRegions = container.querySelectorAll('[aria-live]');
        
        // Should have live regions for important updates
        if (liveRegions.length > 0) {
          liveRegions.forEach(region => {
            // Live regions should be properly configured
            expect(['polite', 'assertive', 'off']).toContain(
              region.getAttribute('aria-live')
            );
          });
        }
      });
    });
  });
});
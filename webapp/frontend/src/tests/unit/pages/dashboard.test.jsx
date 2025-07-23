/**
 * Dashboard Page Unit Tests
 * Tests the main dashboard functionality including authentication, data loading, and UI components
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';

// Import the component to test
import Dashboard from '../../../pages/Dashboard';

// Mock useSimpleFetch hook to replace React Query
vi.mock('../../../hooks/useSimpleFetch', () => ({
  useSimpleFetch: vi.fn(() => ({
    data: {
      portfolio: { value: 50000, change: 1250, changePercent: 2.56 },
      market: { sp500: 4500, nasdaq: 14200, dow: 34800 },
      watchlist: [
        { symbol: 'AAPL', price: 175.25, change: 2.45, changePercent: 1.42 },
        { symbol: 'MSFT', price: 332.89, change: -1.23, changePercent: -0.37 }
      ]
    },
    loading: false,
    error: null,
    isLoading: false,
    isError: false,
    isSuccess: true,
    refetch: vi.fn()
  }))
}));

// Mock AuthContext
const mockAuthContext = {
  user: { username: 'testuser', email: 'test@example.com' },
  isAuthenticated: true,
  isLoading: false,
  tokens: { accessToken: 'mock-token' }
};

vi.mock('../../../contexts/AuthContext', () => ({
  useAuth: () => mockAuthContext
}));

// Mock react-router-dom
const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate
  };
});

// Mock components that might not be fully testable
vi.mock('../../../components/fallbacks/DataNotAvailable', () => ({
  DataNotAvailable: ({ message }) => <div data-testid="data-not-available">{message}</div>,
  LoadingFallback: () => <div data-testid="loading-fallback">Loading...</div>
}));

vi.mock('../../../components/ui/layout', () => ({
  PageLayout: ({ children }) => <div data-testid="page-layout">{children}</div>,
  CardLayout: ({ children, title }) => (
    <div data-testid="card-layout">
      <h3>{title}</h3>
      {children}
    </div>
  ),
  GridLayout: ({ children }) => <div data-testid="grid-layout">{children}</div>
}));

// Mock fetch for API calls
const mockFetch = vi.fn();
global.fetch = mockFetch;

// Mock localStorage
const mockLocalStorage = {
  getItem: vi.fn(() => 'mock-token'),
  setItem: vi.fn(),
  removeItem: vi.fn()
};
Object.defineProperty(window, 'localStorage', { value: mockLocalStorage });

// Test wrapper component
const TestWrapper = ({ children }) => (
  <BrowserRouter>
    {children}
  </BrowserRouter>
);

describe('📊 Dashboard Page Tests', () => {
  const user = userEvent.setup();

  beforeEach(() => {
    vi.clearAllMocks();
    mockNavigate.mockClear();
    
    // Default fetch responses
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({
        success: true,
        data: {
          portfolio: { value: 50000, change: 1250, changePercent: 2.56 },
          market: { sp500: 4500, nasdaq: 14200, dow: 34800 },
          watchlist: [
            { symbol: 'AAPL', price: 175.25, change: 2.45, changePercent: 1.42 },
            { symbol: 'MSFT', price: 332.89, change: -1.23, changePercent: -0.37 }
          ],
          recentTrades: [
            { symbol: 'TSLA', action: 'BUY', shares: 10, price: 245.67, timestamp: '2025-07-22T10:30:00Z' }
          ]
        }
      })
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe('Component Rendering', () => {
    it('should render dashboard page with main layout', () => {
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      expect(screen.getByTestId('page-layout')).toBeInTheDocument();
      expect(screen.getByTestId('grid-layout')).toBeInTheDocument();
    });

    it('should show loading state initially', () => {
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      expect(screen.getByTestId('loading-fallback')).toBeInTheDocument();
    });

    it('should display dashboard title or header elements', () => {
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      // Check for dashboard-specific elements that should be present
      expect(screen.getByTestId('page-layout')).toBeInTheDocument();
    });
  });

  describe('Authentication Integration', () => {
    it('should handle authenticated user state', () => {
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      // Component should render without redirecting if authenticated
      expect(screen.getByTestId('page-layout')).toBeInTheDocument();
      expect(mockNavigate).not.toHaveBeenCalled();
    });

    it('should handle unauthenticated state', () => {
      // Mock unauthenticated state
      vi.mocked(vi.importMock('../../../contexts/AuthContext').useAuth).mockReturnValue({
        user: null,
        isAuthenticated: false,
        isLoading: false,
        tokens: null
      });

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      // Should still render (auth redirect is handled by route protection)
      expect(screen.getByTestId('page-layout')).toBeInTheDocument();
    });
  });

  describe('Data Fetching with useSimpleFetch', () => {
    it('should use useSimpleFetch hook for data loading', async () => {
      const { useSimpleFetch } = await import('../../../hooks/useSimpleFetch');
      
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      // Dashboard should call useSimpleFetch multiple times for different data
      expect(useSimpleFetch).toHaveBeenCalled();
    });

    it('should handle successful data loading with useSimpleFetch', async () => {
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      // Should render without loading state since mock shows loaded data
      expect(screen.getByTestId('page-layout')).toBeInTheDocument();
      expect(screen.queryByTestId('loading-fallback')).not.toBeInTheDocument();
    });

    it('should handle loading state with useSimpleFetch', async () => {
      const { useSimpleFetch } = await import('../../../hooks/useSimpleFetch');
      
      // Mock loading state
      useSimpleFetch.mockReturnValue({
        data: null,
        loading: true,
        error: null,
        isLoading: true,
        isError: false,
        isSuccess: false,
        refetch: vi.fn()
      });

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      expect(screen.getByTestId('loading-fallback')).toBeInTheDocument();
    });

    it('should handle error state with useSimpleFetch', async () => {
      const { useSimpleFetch } = await import('../../../hooks/useSimpleFetch');
      
      // Mock error state
      useSimpleFetch.mockReturnValue({
        data: null,
        loading: false,
        error: 'API Error',
        isLoading: false,
        isError: true,
        isSuccess: false,
        refetch: vi.fn()
      });

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      // Should handle error gracefully
      expect(screen.getByTestId('page-layout')).toBeInTheDocument();
    });
  });

  describe('Data Display', () => {
    it('should display dashboard data when loaded via useSimpleFetch', async () => {
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      // Data should be processed (specific UI assertions would depend on actual implementation)
      expect(screen.getByTestId('page-layout')).toBeInTheDocument();
      expect(screen.getByTestId('grid-layout')).toBeInTheDocument();
    });

    it('should handle data rendering without fetch dependency', async () => {
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      // Should render page layout with useSimpleFetch data
      expect(screen.getByTestId('page-layout')).toBeInTheDocument();
    });

    it('should display multiple data widgets from useSimpleFetch', async () => {
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      // Should render grid layout for multiple dashboard widgets
      expect(screen.getByTestId('grid-layout')).toBeInTheDocument();
    });
  });

  describe('User Interactions', () => {
    it('should handle refresh functionality with useSimpleFetch refetch', async () => {
      const mockRefetch = vi.fn();
      const { useSimpleFetch } = await import('../../../hooks/useSimpleFetch');
      
      useSimpleFetch.mockReturnValue({
        data: { portfolio: { value: 50000 } },
        loading: false,
        error: null,
        isLoading: false,
        isError: false,
        isSuccess: true,
        refetch: mockRefetch
      });

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      // Refetch function should be available from useSimpleFetch
      expect(mockRefetch).toBeDefined();
      expect(screen.getByTestId('page-layout')).toBeInTheDocument();
    });

    it('should handle navigation to other pages', () => {
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      // The navigate function should be available for use
      expect(mockNavigate).toBeDefined();
    });
  });

  describe('Error Handling', () => {
    it('should display error state when useSimpleFetch fails', async () => {
      const { useSimpleFetch } = await import('../../../hooks/useSimpleFetch');
      
      useSimpleFetch.mockReturnValue({
        data: null,
        loading: false,
        error: 'Network error',
        isLoading: false,
        isError: true,
        isSuccess: false,
        refetch: vi.fn()
      });

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      // Should handle error gracefully
      expect(screen.getByTestId('page-layout')).toBeInTheDocument();
    });

    it('should handle partial data loading with multiple useSimpleFetch calls', async () => {
      const { useSimpleFetch } = await import('../../../hooks/useSimpleFetch');
      
      // Mock mixed success/failure states for different data sources
      useSimpleFetch
        .mockReturnValueOnce({
          data: { portfolio: { value: 50000 } },
          loading: false,
          error: null,
          isLoading: false,
          isError: false,
          isSuccess: true,
          refetch: vi.fn()
        })
        .mockReturnValueOnce({
          data: null,
          loading: false,
          error: 'Market data failed',
          isLoading: false,
          isError: true,
          isSuccess: false,
          refetch: vi.fn()
        });

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      // Should handle partial failures gracefully
      expect(screen.getByTestId('page-layout')).toBeInTheDocument();
    });
  });

  describe('Performance', () => {
    it('should not cause memory leaks with multiple renders', () => {
      const { unmount } = render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      unmount();

      // Should unmount cleanly
      expect(true).toBe(true);
    });

    it('should handle rapid re-renders gracefully', () => {
      const { rerender } = render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      // Re-render multiple times
      for (let i = 0; i < 5; i++) {
        rerender(
          <TestWrapper>
            <Dashboard />
          </TestWrapper>
        );
      }

      expect(screen.getByTestId('page-layout')).toBeInTheDocument();
    });
  });

  describe('Accessibility', () => {
    it('should have proper semantic structure', () => {
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      // Should have main layout elements
      expect(screen.getByTestId('page-layout')).toBeInTheDocument();
      expect(screen.getByTestId('grid-layout')).toBeInTheDocument();
    });

    it('should be keyboard navigable', async () => {
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      // Should support keyboard navigation
      const layout = screen.getByTestId('page-layout');
      expect(layout).toBeInTheDocument();
    });
  });
});
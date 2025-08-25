/**
 * Comprehensive Dashboard Component Tests
 * Tests all key Dashboard functionality, data loading, and user interactions
 */

import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import Dashboard from '../../../pages/Dashboard';
import { TestWrapper } from '../../test-utils';

// Mock all external dependencies
vi.mock('../../../services/api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn()
  }
}));

vi.mock('../../../hooks/useAuth', () => ({
  useAuth: () => ({
    user: { id: 'test-user', username: 'testuser' },
    isAuthenticated: true,
    token: 'test-token'
  })
}));

vi.mock('../../../components/MarketStatusBar', () => ({
  default: () => <div data-testid="market-status-bar">Market Status Bar</div>
}));

vi.mock('../../../components/RealTimePriceWidget', () => ({
  default: () => <div data-testid="realtime-price-widget">Real Time Price Widget</div>
}));

describe('Dashboard Component - Comprehensive Testing', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Page Loading and Structure', () => {
    it('should render Dashboard with proper structure', async () => {
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      expect(screen.getByText('Financial Dashboard')).toBeInTheDocument();
      expect(screen.getByText(/Welcome to your institutional-grade/)).toBeInTheDocument();
    });

    it('should display market status bar component', async () => {
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByTestId('market-status-bar')).toBeInTheDocument();
      });
    });

    it('should display real-time price widgets', async () => {
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByTestId('realtime-price-widget')).toBeInTheDocument();
      });
    });
  });

  describe('Navigation and Quick Actions', () => {
    it('should render navigation cards for major sections', async () => {
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      // Check for key navigation sections
      expect(screen.getByText('Markets')).toBeInTheDocument();
      expect(screen.getByText('Portfolio')).toBeInTheDocument();
      expect(screen.getByText('Research & Education')).toBeInTheDocument();
    });

    it('should handle navigation card clicks', async () => {
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      const marketsCard = screen.getByText('Markets').closest('[role="button"]');
      if (marketsCard) {
        fireEvent.click(marketsCard);
        // Navigation is handled by React Router, so we just verify no errors
        expect(marketsCard).toBeInTheDocument();
      }
    });

    it('should display quick action buttons', async () => {
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      // Look for common action buttons
      const buttons = screen.getAllByRole('button');
      expect(buttons.length).toBeGreaterThan(0);
    });
  });

  describe('Data Integration and API Calls', () => {
    it('should handle dashboard data loading gracefully', async () => {
      const { api } = await import('../../../services/api');
      api.get.mockResolvedValue({
        data: {
          marketStatus: { isOpen: true },
          indices: { SPY: 445.32, QQQ: 375.68 },
          portfolio: { totalValue: 125750.50 }
        }
      });

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText('Financial Dashboard')).toBeInTheDocument();
      });
    });

    it('should handle API errors gracefully', async () => {
      const { api } = await import('../../../services/api');
      api.get.mockRejectedValue(new Error('API Error'));

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText('Financial Dashboard')).toBeInTheDocument();
      });

      // Should still render basic structure even with API errors
      expect(screen.getByText('Markets')).toBeInTheDocument();
    });
  });

  describe('Responsive Design and Layout', () => {
    it('should render properly on mobile viewports', async () => {
      // Mock mobile viewport
      Object.defineProperty(window, 'innerWidth', {
        writable: true,
        configurable: true,
        value: 375,
      });

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      expect(screen.getByText('Financial Dashboard')).toBeInTheDocument();
      expect(screen.getByText('Markets')).toBeInTheDocument();
    });

    it('should handle different screen sizes appropriately', async () => {
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      // Test that grid layouts are present
      const container = screen.getByText('Financial Dashboard').closest('div');
      expect(container).toBeInTheDocument();
    });
  });

  describe('User Interaction and Accessibility', () => {
    it('should support keyboard navigation', async () => {
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      // Find focusable elements
      const buttons = screen.getAllByRole('button');
      if (buttons.length > 0) {
        buttons[0].focus();
        expect(document.activeElement).toBe(buttons[0]);
      }
    });

    it('should have proper ARIA labels and roles', async () => {
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      const buttons = screen.getAllByRole('button');
      expect(buttons.length).toBeGreaterThan(0);

      // Check for proper heading structure
      const mainHeading = screen.getByRole('heading', { level: 1 });
      expect(mainHeading).toBeInTheDocument();
    });

    it('should handle user interactions without errors', async () => {
      const consoleSpy = vi.spyOn(console, 'error');
      
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      // Interact with various elements
      const buttons = screen.getAllByRole('button');
      if (buttons.length > 0) {
        fireEvent.click(buttons[0]);
      }

      expect(consoleSpy).not.toHaveBeenCalled();
      consoleSpy.mockRestore();
    });
  });

  describe('Performance and Loading States', () => {
    it('should render without performance issues', async () => {
      const startTime = performance.now();
      
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      const endTime = performance.now();
      const renderTime = endTime - startTime;

      // Should render within reasonable time (500ms)
      expect(renderTime).toBeLessThan(500);
    });

    it('should handle concurrent data updates', async () => {
      const { api } = await import('../../../services/api');
      api.get.mockResolvedValue({ data: { test: 'data' } });

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      // Simulate multiple rapid updates
      for (let i = 0; i < 5; i++) {
        fireEvent(window, new Event('focus'));
      }

      await waitFor(() => {
        expect(screen.getByText('Financial Dashboard')).toBeInTheDocument();
      });
    });
  });

  describe('Error Boundaries and Edge Cases', () => {
    it('should handle component errors gracefully', async () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      // Component should render even if there are minor errors
      expect(screen.getByText('Financial Dashboard')).toBeInTheDocument();
      
      consoleSpy.mockRestore();
    });

    it('should handle missing data gracefully', async () => {
      const { api } = await import('../../../services/api');
      api.get.mockResolvedValue({ data: null });

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText('Financial Dashboard')).toBeInTheDocument();
      });
    });
  });
});
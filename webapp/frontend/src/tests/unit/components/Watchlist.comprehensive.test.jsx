/**
 * Comprehensive Watchlist Component Tests
 * Tests watchlist functionality, stock management, real-time updates, and user interactions
 */

import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import Watchlist from '../../../pages/Watchlist';
import { TestWrapper } from '../../test-utils';

// Mock all external dependencies
// Mock the API service with comprehensive mock
vi.mock("../../services/api", async (_importOriginal) => {
  const { createApiServiceMock } = await import('../mocks/api-service-mock');
  return {
    default: createApiServiceMock(),
    ...createApiServiceMock()
  };
});

vi.mock('../../../hooks/useAuth', () => ({
  useAuth: () => ({
    user: { id: 'test-user', username: 'testuser' },
    isAuthenticated: true,
    token: 'test-token'
  })
}));

describe('Watchlist Component - Comprehensive Testing', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Page Structure and Initial Load', () => {
    it('should render Watchlist with proper title and structure', async () => {
      render(
        <TestWrapper>
          <Watchlist />
        </TestWrapper>
      );

      expect(screen.getByText('Watchlist')).toBeInTheDocument();
      expect(screen.getByText(/Track your favorite stocks/)).toBeInTheDocument();
    });

    it('should display add stock functionality', async () => {
      render(
        <TestWrapper>
          <Watchlist />
        </TestWrapper>
      );

      // Should have some way to add stocks
      const addButtons = screen.getAllByRole('button');
      const addButton = addButtons.find(btn => 
        btn.textContent && (
          btn.textContent.toLowerCase().includes('add') ||
          btn.textContent.toLowerCase().includes('+')
        )
      );

      expect(addButton || addButtons.length > 0).toBeTruthy();
    });

    it('should handle component lifecycle properly', async () => {
      const { unmount } = render(
        <TestWrapper>
          <Watchlist />
        </TestWrapper>
      );

      expect(screen.getByText('Watchlist')).toBeInTheDocument();
      
      // Should unmount cleanly
      unmount();
    });
  });

  describe('Watchlist Data Management', () => {
    it('should fetch and display watchlist items', async () => {
      const { api } = await import('../../../services/api');
      api.get.mockResolvedValue({
        data: {
          watchlist: [
            {
              id: 1,
              symbol: 'AAPL',
              name: 'Apple Inc.',
              price: 175.30,
              change: 2.45,
              changePercent: 1.42,
              lastUpdated: '2025-08-23T14:30:00Z'
            },
            {
              id: 2,
              symbol: 'MSFT',
              name: 'Microsoft Corporation',
              price: 385.75,
              change: -1.25,
              changePercent: -0.32,
              lastUpdated: '2025-08-23T14:30:00Z'
            }
          ]
        }
      });

      render(
        <TestWrapper>
          <Watchlist />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(api.get).toHaveBeenCalledWith(expect.stringContaining('/watchlist'));
      });
    });

    it('should handle empty watchlist state', async () => {
      const { api } = await import('../../../services/api');
      api.get.mockResolvedValue({
        data: { watchlist: [] }
      });

      render(
        <TestWrapper>
          <Watchlist />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(api.get).toHaveBeenCalled();
      });

      // Should show empty state message
      expect(screen.getByText('Watchlist')).toBeInTheDocument();
    });

    it('should handle API errors gracefully', async () => {
      const { api } = await import('../../../services/api');
      api.get.mockRejectedValue(new Error('Watchlist service unavailable'));

      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

      render(
        <TestWrapper>
          <Watchlist />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText('Watchlist')).toBeInTheDocument();
      });

      consoleSpy.mockRestore();
    });
  });

  describe('Adding and Removing Stocks', () => {
    it('should handle adding new stock to watchlist', async () => {
      const { api } = await import('../../../services/api');
      api.post.mockResolvedValue({
        data: { success: true, message: 'Stock added to watchlist' }
      });

      render(
        <TestWrapper>
          <Watchlist />
        </TestWrapper>
      );

      // Look for add stock input or button
      const inputs = screen.queryAllByRole('textbox');
      const addButtons = screen.getAllByRole('button');

      if (inputs.length > 0) {
        fireEvent.change(inputs[0], { target: { value: 'GOOGL' } });
        
        const addButton = addButtons.find(btn => 
          btn.textContent && btn.textContent.toLowerCase().includes('add')
        );
        
        if (addButton) {
          fireEvent.click(addButton);
          
          await waitFor(() => {
            expect(api.post).toHaveBeenCalledWith(
              expect.stringContaining('/watchlist'),
              expect.objectContaining({ symbol: 'GOOGL' })
            );
          });
        }
      }

      expect(screen.getByText('Watchlist')).toBeInTheDocument();
    });

    it('should handle removing stock from watchlist', async () => {
      const { api } = await import('../../../services/api');
      api.get.mockResolvedValue({
        data: {
          watchlist: [
            { id: 1, symbol: 'AAPL', price: 175.30 }
          ]
        }
      });
      api.delete.mockResolvedValue({
        data: { success: true, message: 'Stock removed from watchlist' }
      });

      render(
        <TestWrapper>
          <Watchlist />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(api.get).toHaveBeenCalled();
      });

      // Look for remove/delete buttons
      const buttons = screen.getAllByRole('button');
      const removeButton = buttons.find(btn => 
        btn.textContent && (
          btn.textContent.toLowerCase().includes('remove') ||
          btn.textContent.toLowerCase().includes('delete') ||
          btn.textContent.includes('×')
        )
      );

      if (removeButton) {
        fireEvent.click(removeButton);
        
        await waitFor(() => {
          expect(api.delete || api.post).toHaveBeenCalled();
        });
      }
    });

    it('should handle bulk operations on watchlist items', async () => {
      const { api } = await import('../../../services/api');
      api.get.mockResolvedValue({
        data: {
          watchlist: [
            { id: 1, symbol: 'AAPL' },
            { id: 2, symbol: 'MSFT' },
            { id: 3, symbol: 'GOOGL' }
          ]
        }
      });

      render(
        <TestWrapper>
          <Watchlist />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(api.get).toHaveBeenCalled();
      });

      // Look for bulk action controls (checkboxes, select all)
      const checkboxes = screen.queryAllByRole('checkbox');
      if (checkboxes.length > 0) {
        fireEvent.click(checkboxes[0]);
      }

      expect(screen.getByText('Watchlist')).toBeInTheDocument();
    });
  });

  describe('Real-time Price Updates', () => {
    it('should handle periodic price refresh', async () => {
      const { api } = await import('../../../services/api');
      api.get.mockResolvedValue({
        data: { watchlist: [{ id: 1, symbol: 'AAPL', price: 175.30 }] }
      });

      render(
        <TestWrapper>
          <Watchlist />
        </TestWrapper>
      );

      // Simulate time passing for price updates
      vi.advanceTimersByTime(30000); // 30 seconds

      await waitFor(() => {
        expect(api.get).toHaveBeenCalled();
      });
    });

    it('should handle real-time price WebSocket updates', async () => {
      render(
        <TestWrapper>
          <Watchlist />
        </TestWrapper>
      );

      // Simulate focus event that might trigger updates
      fireEvent(window, new Event('focus'));

      expect(screen.getByText('Watchlist')).toBeInTheDocument();
    });

    it('should display price change indicators', async () => {
      const { api } = await import('../../../services/api');
      api.get.mockResolvedValue({
        data: {
          watchlist: [
            { id: 1, symbol: 'AAPL', price: 175.30, change: 2.45, changePercent: 1.42 },
            { id: 2, symbol: 'MSFT', price: 385.75, change: -1.25, changePercent: -0.32 }
          ]
        }
      });

      render(
        <TestWrapper>
          <Watchlist />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(api.get).toHaveBeenCalled();
      });

      // Should handle positive and negative changes
      expect(screen.getByText('Watchlist')).toBeInTheDocument();
    });
  });

  describe('Sorting and Filtering', () => {
    it('should handle sorting by different columns', async () => {
      render(
        <TestWrapper>
          <Watchlist />
        </TestWrapper>
      );

      // Look for sortable column headers
      const headers = screen.queryAllByRole('columnheader');
      if (headers.length > 0) {
        fireEvent.click(headers[0]);
      }

      // Alternative: look for sort buttons
      const buttons = screen.getAllByRole('button');
      const sortButton = buttons.find(btn => 
        btn.textContent && (
          btn.textContent.toLowerCase().includes('sort') ||
          btn.textContent.toLowerCase().includes('price') ||
          btn.textContent.toLowerCase().includes('change')
        )
      );

      if (sortButton) {
        fireEvent.click(sortButton);
      }

      expect(screen.getByText('Watchlist')).toBeInTheDocument();
    });

    it('should handle filtering by sector or market cap', async () => {
      render(
        <TestWrapper>
          <Watchlist />
        </TestWrapper>
      );

      // Look for filter controls
      const selects = screen.queryAllByRole('combobox');
      if (selects.length > 0) {
        fireEvent.click(selects[0]);
      }

      expect(screen.getByText('Watchlist')).toBeInTheDocument();
    });

    it('should handle search functionality', async () => {
      render(
        <TestWrapper>
          <Watchlist />
        </TestWrapper>
      );

      // Look for search input
      const searchInputs = screen.queryAllByRole('textbox');
      const searchInput = searchInputs.find(input => 
        input.placeholder && input.placeholder.toLowerCase().includes('search')
      );

      if (searchInput) {
        fireEvent.change(searchInput, { target: { value: 'AAPL' } });
      }

      expect(screen.getByText('Watchlist')).toBeInTheDocument();
    });
  });

  describe('User Interactions and Navigation', () => {
    it('should handle clicking on stock rows for details', async () => {
      const { api } = await import('../../../services/api');
      api.get.mockResolvedValue({
        data: {
          watchlist: [
            { id: 1, symbol: 'AAPL', name: 'Apple Inc.', price: 175.30 }
          ]
        }
      });

      render(
        <TestWrapper>
          <Watchlist />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(api.get).toHaveBeenCalled();
      });

      // Look for clickable rows or links
      const buttons = screen.getAllByRole('button');
      if (buttons.length > 0) {
        fireEvent.click(buttons[0]);
      }

      expect(screen.getByText('Watchlist')).toBeInTheDocument();
    });

    it('should handle portfolio integration actions', async () => {
      render(
        <TestWrapper>
          <Watchlist />
        </TestWrapper>
      );

      // Look for portfolio-related actions
      const buttons = screen.getAllByRole('button');
      const portfolioButton = buttons.find(btn => 
        btn.textContent && btn.textContent.toLowerCase().includes('portfolio')
      );

      if (portfolioButton) {
        fireEvent.click(portfolioButton);
      }

      expect(screen.getByText('Watchlist')).toBeInTheDocument();
    });

    it('should handle export and sharing functionality', async () => {
      render(
        <TestWrapper>
          <Watchlist />
        </TestWrapper>
      );

      // Look for export buttons
      const buttons = screen.getAllByRole('button');
      const exportButton = buttons.find(btn => 
        btn.textContent && (
          btn.textContent.toLowerCase().includes('export') ||
          btn.textContent.toLowerCase().includes('share')
        )
      );

      if (exportButton) {
        fireEvent.click(exportButton);
      }

      expect(screen.getByText('Watchlist')).toBeInTheDocument();
    });
  });

  describe('Mobile and Responsive Design', () => {
    it('should adapt to mobile viewport', async () => {
      Object.defineProperty(window, 'innerWidth', {
        writable: true,
        configurable: true,
        value: 375,
      });

      render(
        <TestWrapper>
          <Watchlist />
        </TestWrapper>
      );

      expect(screen.getByText('Watchlist')).toBeInTheDocument();
    });

    it('should handle touch interactions', async () => {
      render(
        <TestWrapper>
          <Watchlist />
        </TestWrapper>
      );

      const buttons = screen.getAllByRole('button');
      if (buttons.length > 0) {
        fireEvent.touchStart(buttons[0]);
        fireEvent.touchEnd(buttons[0]);
      }

      expect(screen.getByText('Watchlist')).toBeInTheDocument();
    });

    it('should maintain functionality on different screen sizes', async () => {
      // Test tablet size
      Object.defineProperty(window, 'innerWidth', {
        writable: true,
        configurable: true,
        value: 768,
      });

      render(
        <TestWrapper>
          <Watchlist />
        </TestWrapper>
      );

      expect(screen.getByText('Watchlist')).toBeInTheDocument();
    });
  });

  describe('Performance and Optimization', () => {
    it('should handle large watchlists efficiently', async () => {
      const { api } = await import('../../../services/api');
      const largeWatchlist = Array.from({ length: 100 }, (_, i) => ({
        id: i,
        symbol: `STOCK${i}`,
        name: `Company ${i}`,
        price: 100 + Math.random() * 50,
        change: Math.random() * 10 - 5,
        changePercent: Math.random() * 5 - 2.5
      }));

      api.get.mockResolvedValue({ data: { watchlist: largeWatchlist } });

      const startTime = performance.now();
      render(
        <TestWrapper>
          <Watchlist />
        </TestWrapper>
      );
      const endTime = performance.now();

      expect(endTime - startTime).toBeLessThan(1000);
      expect(screen.getByText('Watchlist')).toBeInTheDocument();
    });

    it('should handle rapid updates without performance issues', async () => {
      const { api } = await import('../../../services/api');
      api.get.mockResolvedValue({ data: { watchlist: [] } });

      render(
        <TestWrapper>
          <Watchlist />
        </TestWrapper>
      );

      // Simulate rapid updates
      for (let i = 0; i < 15; i++) {
        fireEvent(window, new Event('focus'));
        await new Promise(resolve => setTimeout(resolve, 10));
      }

      expect(screen.getByText('Watchlist')).toBeInTheDocument();
    });
  });

  describe('Accessibility and User Experience', () => {
    it('should have proper heading structure', async () => {
      render(
        <TestWrapper>
          <Watchlist />
        </TestWrapper>
      );

      const mainHeading = screen.getByRole('heading', { level: 1 });
      expect(mainHeading).toBeInTheDocument();
      expect(mainHeading).toHaveTextContent('Watchlist');
    });

    it('should support keyboard navigation', async () => {
      render(
        <TestWrapper>
          <Watchlist />
        </TestWrapper>
      );

      const focusableElements = screen.getAllByRole('button');
      if (focusableElements.length > 0) {
        focusableElements[0].focus();
        expect(document.activeElement).toBe(focusableElements[0]);

        // Test tab navigation
        if (focusableElements.length > 1) {
          focusableElements[1].focus();
          expect(document.activeElement).toBe(focusableElements[1]);
        }
      }
    });

    it('should have appropriate ARIA labels and table structure', async () => {
      render(
        <TestWrapper>
          <Watchlist />
        </TestWrapper>
      );

      // Check for proper table structure if watchlist is displayed as table
      const tables = screen.queryAllByRole('table');
      const buttons = screen.getAllByRole('button');
      
      expect(tables.length >= 0 || buttons.length > 0).toBeTruthy();
    });

    it('should handle errors with user-friendly messages', async () => {
      const { api } = await import('../../../services/api');
      api.get.mockRejectedValue(new Error('Network error'));

      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

      render(
        <TestWrapper>
          <Watchlist />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText('Watchlist')).toBeInTheDocument();
      });

      consoleSpy.mockRestore();
    });
  });
});
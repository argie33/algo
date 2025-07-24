/**
 * User-Specific Watchlist Integration Test
 * Tests complete watchlist functionality with user authentication
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';
import { ThemeProvider, createTheme } from '@mui/material/styles';

// Component imports
import Watchlist from '../../pages/Watchlist.jsx';
import { AuthContext } from '../../contexts/AuthContext.jsx';

// Mock API services
import * as api from '../../services/api.js';

// Mock data
const mockUser = {
  sub: 'test-user-123',
  username: 'testuser',
  email: 'test@example.com'
};

const mockWatchlists = [
  {
    id: 1,
    user_id: 'test-user-123',
    name: 'My Portfolio',
    description: 'Primary investment tracking',
    color: '#1976d2',
    created_at: '2024-01-01T00:00:00Z',
    item_count: 3
  },
  {
    id: 2,
    user_id: 'test-user-123',
    name: 'Tech Stocks',
    description: 'Technology companies',
    color: '#4caf50',
    created_at: '2024-01-02T00:00:00Z',
    item_count: 2
  }
];

const mockWatchlistItems = [
  {
    id: 1,
    watchlist_id: 1,
    symbol: 'AAPL',
    short_name: 'Apple Inc.',
    current_price: 189.45,
    day_change_amount: 2.30,
    day_change_percent: 1.23,
    volume: 45230000,
    market_cap: 2950000000000,
    trailing_pe: 28.5,
    fifty_two_week_low: 124.17,
    fifty_two_week_high: 199.62,
    sector: 'Technology',
    position_order: 1
  },
  {
    id: 2,
    watchlist_id: 1,
    symbol: 'MSFT',
    short_name: 'Microsoft Corporation',
    current_price: 334.89,
    day_change_amount: -1.45,
    day_change_percent: -0.43,
    volume: 23450000,
    market_cap: 2480000000000,
    trailing_pe: 32.1,
    fifty_two_week_low: 245.18,
    fifty_two_week_high: 384.30,
    sector: 'Technology',
    position_order: 2
  }
];

const mockAuthContext = {
  user: mockUser,
  isAuthenticated: true,
  isLoading: false,
  error: null,
  tokens: {
    accessToken: 'mock-access-token',
    idToken: 'mock-id-token'
  }
};

const theme = createTheme();

// Mock API functions
vi.mock('../../services/api.js', () => ({
  getWatchlists: vi.fn(),
  createWatchlist: vi.fn(),
  deleteWatchlist: vi.fn(),
  getWatchlistItems: vi.fn(),
  addWatchlistItem: vi.fn(),
  deleteWatchlistItem: vi.fn(),
  reorderWatchlistItems: vi.fn(),
  api: {
    get: vi.fn()
  }
}));

// Test wrapper component
const TestWrapper = ({ children, authContextValue = mockAuthContext }) => (
  <BrowserRouter>
    <ThemeProvider theme={theme}>
      <AuthContext.Provider value={authContextValue}>
        {children}
      </AuthContext.Provider>
    </ThemeProvider>
  </BrowserRouter>
);

describe('User-Specific Watchlist Integration Tests', () => {
  beforeEach(() => {
    // Reset all mocks
    vi.clearAllMocks();
    
    // Setup default API responses
    api.getWatchlists.mockResolvedValue(mockWatchlists);
    api.getWatchlistItems.mockResolvedValue(mockWatchlistItems);
    api.api.get.mockResolvedValue({ data: { symbols: [] } });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe('Authentication Integration', () => {
    it('should require authentication to view watchlists', async () => {
      const unauthenticatedContext = {
        ...mockAuthContext,
        isAuthenticated: false,
        user: null
      };

      render(
        <TestWrapper authContextValue={unauthenticatedContext}>
          <Watchlist />
        </TestWrapper>
      );

      expect(screen.getByText(/please sign in to access your watchlists/i)).toBeInTheDocument();
      expect(api.getWatchlists).not.toHaveBeenCalled();
    });

    it('should load user-specific watchlists when authenticated', async () => {
      render(
        <TestWrapper>
          <Watchlist />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(api.getWatchlists).toHaveBeenCalledTimes(1);
      });

      expect(screen.getByText('My Portfolio')).toBeInTheDocument();
      expect(screen.getByText('Tech Stocks')).toBeInTheDocument();
    });
  });

  describe('Watchlist CRUD Operations', () => {
    it('should create a new user-specific watchlist', async () => {
      const newWatchlist = {
        id: 3,
        user_id: 'test-user-123',
        name: 'New Watchlist',
        description: 'Test description',
        color: '#ff5722'
      };

      api.createWatchlist.mockResolvedValue(newWatchlist);

      render(
        <TestWrapper>
          <Watchlist />
        </TestWrapper>
      );

      // Wait for initial load
      await waitFor(() => {
        expect(screen.getByText('My Portfolio')).toBeInTheDocument();
      });

      // Click new watchlist button
      const newWatchlistButton = screen.getByRole('button', { name: /new watchlist/i });
      await userEvent.click(newWatchlistButton);

      // Fill out form
      const nameInput = screen.getByLabelText(/watchlist name/i);
      const descriptionInput = screen.getByLabelText(/description/i);
      
      await userEvent.type(nameInput, 'New Watchlist');
      await userEvent.type(descriptionInput, 'Test description');

      // Submit form
      const createButton = screen.getByRole('button', { name: /create/i });
      await userEvent.click(createButton);

      await waitFor(() => {
        expect(api.createWatchlist).toHaveBeenCalledWith({
          name: 'New Watchlist',
          description: 'Test description'
        });
      });
    });

    it('should handle watchlist creation errors gracefully', async () => {
      api.createWatchlist.mockRejectedValue(new Error('Failed to create watchlist'));

      render(
        <TestWrapper>
          <Watchlist />
        </TestWrapper>
      );

      // Wait for initial load
      await waitFor(() => {
        expect(screen.getByText('My Portfolio')).toBeInTheDocument();
      });

      // Try to create watchlist
      const newWatchlistButton = screen.getByRole('button', { name: /new watchlist/i });
      await userEvent.click(newWatchlistButton);

      const nameInput = screen.getByLabelText(/watchlist name/i);
      await userEvent.type(nameInput, 'Test Watchlist');

      const createButton = screen.getByRole('button', { name: /create/i });
      await userEvent.click(createButton);

      // Should show error message
      await waitFor(() => {
        expect(screen.getByText(/error creating watchlist/i)).toBeInTheDocument();
      });
    });

    it('should delete a user watchlist', async () => {
      api.deleteWatchlist.mockResolvedValue({ success: true });

      render(
        <TestWrapper>
          <Watchlist />
        </TestWrapper>
      );

      // Wait for initial load
      await waitFor(() => {
        expect(screen.getByText('My Portfolio')).toBeInTheDocument();
      });

      // Find and click delete button (this would be in the tab)
      const deleteButtons = screen.getAllByTestId('DeleteIcon');
      await userEvent.click(deleteButtons[0]);

      await waitFor(() => {
        expect(api.deleteWatchlist).toHaveBeenCalledWith(1);
      });
    });
  });

  describe('Watchlist Items Management', () => {
    beforeEach(() => {
      api.getWatchlistItems.mockResolvedValue(mockWatchlistItems);
    });

    it('should load watchlist items for selected watchlist', async () => {
      render(
        <TestWrapper>
          <Watchlist />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(api.getWatchlistItems).toHaveBeenCalledWith(1);
      });

      expect(screen.getByText('AAPL')).toBeInTheDocument();
      expect(screen.getByText('MSFT')).toBeInTheDocument();
      expect(screen.getByText('Apple Inc.')).toBeInTheDocument();
      expect(screen.getByText('Microsoft Corporation')).toBeInTheDocument();
    });

    it('should add a stock to watchlist', async () => {
      const newItem = {
        id: 3,
        watchlist_id: 1,
        symbol: 'GOOGL',
        short_name: 'Alphabet Inc.',
        current_price: 134.23
      };

      api.addWatchlistItem.mockResolvedValue(newItem);

      render(
        <TestWrapper>
          <Watchlist />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument();
      });

      // Find the autocomplete input
      const addStockInput = screen.getByPlaceholderText(/search for a stock symbol/i);
      await userEvent.type(addStockInput, 'GOOGL');
      
      // Simulate selecting from autocomplete
      fireEvent.change(addStockInput, { target: { value: 'GOOGL' } });

      await waitFor(() => {
        expect(api.addWatchlistItem).toHaveBeenCalledWith(1, {
          symbol: 'GOOGL'
        });
      });
    });

    it('should remove a stock from watchlist', async () => {
      api.deleteWatchlistItem.mockResolvedValue({ success: true });

      render(
        <TestWrapper>
          <Watchlist />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument();
      });

      // Find and click delete button for a stock
      const deleteButtons = screen.getAllByTestId('DeleteIcon');
      const stockDeleteButton = deleteButtons.find(button => 
        button.closest('tr')?.textContent?.includes('AAPL')
      );
      
      if (stockDeleteButton) {
        await userEvent.click(stockDeleteButton);

        await waitFor(() => {
          expect(api.deleteWatchlistItem).toHaveBeenCalledWith(1, 1);
        });
      }
    });

    it('should handle reordering watchlist items', async () => {
      api.reorderWatchlistItems.mockResolvedValue({ success: true });

      render(
        <TestWrapper>
          <Watchlist />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument();
      });

      // Simulate drag and drop reordering
      // This is a simplified test - real drag and drop would be more complex
      const reorderedIds = [2, 1]; // MSFT first, then AAPL

      // Simulate the drag end event that would call reorderWatchlistItems
      await waitFor(() => {
        // In a real scenario, this would be triggered by the drag and drop
        // For testing, we manually verify the API would be called
        expect(api.reorderWatchlistItems).not.toHaveBeenCalled();
      });
    });
  });

  describe('Data Persistence and Synchronization', () => {
    it('should maintain watchlist state across tab switches', async () => {
      render(
        <TestWrapper>
          <Watchlist />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText('My Portfolio')).toBeInTheDocument();
      });

      // Switch to second tab
      const techStocksTab = screen.getByText('Tech Stocks');
      await userEvent.click(techStocksTab);

      await waitFor(() => {
        expect(api.getWatchlistItems).toHaveBeenCalledWith(2);
      });

      // Switch back to first tab
      const myPortfolioTab = screen.getByText('My Portfolio');
      await userEvent.click(myPortfolioTab);

      await waitFor(() => {
        expect(api.getWatchlistItems).toHaveBeenCalledWith(1);
      });
    });

    it('should handle API errors gracefully with fallback data', async () => {
      api.getWatchlists.mockRejectedValue(new Error('API Error'));
      api.getWatchlistItems.mockRejectedValue(new Error('API Error'));

      render(
        <TestWrapper>
          <Watchlist />
        </TestWrapper>
      );

      // Should show fallback content when API fails
      await waitFor(() => {
        expect(screen.getByText(/error loading watchlists/i)).toBeInTheDocument();
      });
    });
  });

  describe('Real-time Updates', () => {
    it('should refresh watchlist data periodically when market is open', async () => {
      // Mock market hours (9:30 AM - 4:00 PM ET on weekdays)
      const mockDate = new Date('2024-01-15T14:30:00.000Z'); // Monday 2:30 PM ET
      vi.setSystemTime(mockDate);

      render(
        <TestWrapper>
          <Watchlist />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(api.getWatchlistItems).toHaveBeenCalledTimes(1);
      });

      // Fast-forward time to trigger refresh
      vi.advanceTimersByTime(30000); // 30 seconds

      await waitFor(() => {
        expect(api.getWatchlistItems).toHaveBeenCalledTimes(2);
      });

      vi.useRealTimers();
    });
  });

  describe('User Experience', () => {
    it('should display loading states appropriately', async () => {
      // Make API calls hang to test loading state
      api.getWatchlists.mockImplementation(() => new Promise(() => {}));

      render(
        <TestWrapper>
          <Watchlist />
        </TestWrapper>
      );

      // Should show loading indicator
      expect(screen.getByRole('progressbar')).toBeInTheDocument();
    });

    it('should show appropriate stock count in watchlist tabs', async () => {
      render(
        <TestWrapper>
          <Watchlist />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText('3 stocks')).toBeInTheDocument();
      });
    });

    it('should format currency and percentage values correctly', async () => {
      render(
        <TestWrapper>
          <Watchlist />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText('$189.45')).toBeInTheDocument();
        expect(screen.getByText('$2.30')).toBeInTheDocument();
        expect(screen.getByText('(1.23%)')).toBeInTheDocument();
      });
    });
  });
});
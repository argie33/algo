/**
 * Simple Watchlist API Integration Test
 * Tests the watchlist API functionality without complex component rendering
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

// Import API functions to test
import {
  getWatchlists,
  createWatchlist,
  deleteWatchlist,
  getWatchlistItems,
  addWatchlistItem,
  deleteWatchlistItem,
  reorderWatchlistItems
} from '../../services/api.js';

// Mock fetch globally
global.fetch = vi.fn();

describe('Watchlist API Integration Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Set up default mock response
    global.fetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ success: true, data: [] })
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('User-Specific Watchlist Operations', () => {
    it('should call getWatchlists API endpoint', async () => {
      const mockWatchlists = [
        { id: 1, name: 'My Watchlist', user_id: 'test-user-123' },
        { id: 2, name: 'Tech Stocks', user_id: 'test-user-123' }
      ];

      global.fetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ success: true, data: mockWatchlists })
      });

      const result = await getWatchlists();
      
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/watchlist'),
        expect.objectContaining({
          method: 'GET',
          headers: expect.objectContaining({
            'Content-Type': 'application/json'
          })
        })
      );
      
      expect(result.data).toEqual(mockWatchlists);
    });

    it('should call createWatchlist API endpoint with user data', async () => {
      const newWatchlist = {
        name: 'New Watchlist',
        description: 'Test description'
      };

      const mockResponse = {
        id: 3,
        user_id: 'test-user-123',
        ...newWatchlist
      };

      global.fetch.mockResolvedValueOnce({
        ok: true,
        status: 201,
        json: () => Promise.resolve({ success: true, data: mockResponse })
      });

      const result = await createWatchlist(newWatchlist);
      
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/watchlist'),
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'Content-Type': 'application/json'
          }),
          body: JSON.stringify(newWatchlist)
        })
      );
    });

    it('should call getWatchlistItems with specific watchlist ID', async () => {
      const mockItems = [
        {
          id: 1,
          watchlist_id: 1,
          symbol: 'AAPL',
          current_price: 189.45,
          day_change_percent: 1.23
        }
      ];

      global.fetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ success: true, data: mockItems })
      });

      const result = await getWatchlistItems(1);
      
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/watchlist/1/items'),
        expect.objectContaining({
          method: 'GET'
        })
      );
    });

    it('should call addWatchlistItem with symbol data', async () => {
      const itemData = { symbol: 'MSFT' };
      const mockResponse = {
        id: 2,
        watchlist_id: 1,
        symbol: 'MSFT'
      };

      global.fetch.mockResolvedValueOnce({
        ok: true,
        status: 201,
        json: () => Promise.resolve({ success: true, data: mockResponse })
      });

      const result = await addWatchlistItem(1, itemData);
      
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/watchlist/1/items'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify(itemData)
        })
      );
    });

    it('should call deleteWatchlistItem with correct IDs', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ success: true, message: 'Item deleted' })
      });

      await deleteWatchlistItem(1, 2);
      
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/watchlist/1/items/2'),
        expect.objectContaining({
          method: 'DELETE'
        })
      );
    });

    it('should call reorderWatchlistItems with item array', async () => {
      const itemIds = [3, 1, 2];

      global.fetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ success: true, message: 'Items reordered' })
      });

      await reorderWatchlistItems(1, itemIds);
      
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/watchlist/1/items/reorder'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ itemIds })
        })
      );
    });
  });

  describe('Error Handling', () => {
    it('should handle API errors gracefully', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: () => Promise.resolve({ 
          success: false, 
          error: 'Internal server error' 
        })
      });

      try {
        await getWatchlists();
        expect.fail('Should have thrown an error');
      } catch (error) {
        expect(error).toBeDefined();
      }
    });

    it('should handle network errors', async () => {
      global.fetch.mockRejectedValueOnce(new Error('Network error'));

      try {
        await getWatchlists();
        expect.fail('Should have thrown an error');
      } catch (error) {
        expect(error.message).toBe('Network error');
      }
    });
  });

  describe('Authentication Integration', () => {
    it('should include authorization headers when available', async () => {
      // Mock localStorage to simulate authentication
      const mockToken = 'mock-jwt-token';
      Object.defineProperty(window, 'localStorage', {
        value: {
          getItem: vi.fn(() => mockToken),
          setItem: vi.fn(),
          removeItem: vi.fn()
        },
        writable: true
      });

      global.fetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ success: true, data: [] })
      });

      await getWatchlists();
      
      expect(global.fetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.objectContaining({
            'Authorization': expect.stringContaining('Bearer')
          })
        })
      );
    });
  });

  describe('Data Validation', () => {
    it('should validate required fields for createWatchlist', async () => {
      try {
        await createWatchlist({}); // Missing name
        expect.fail('Should have thrown validation error');
      } catch (error) {
        expect(error.message).toContain('name');
      }
    });

    it('should validate required fields for addWatchlistItem', async () => {
      try {
        await addWatchlistItem(1, {}); // Missing symbol
        expect.fail('Should have thrown validation error');
      } catch (error) {
        expect(error.message).toContain('symbol');
      }
    });

    it('should validate watchlist ID parameters', async () => {
      try {
        await getWatchlistItems(); // Missing watchlist ID
        expect.fail('Should have thrown validation error');
      } catch (error) {
        expect(error.message).toContain('ID');
      }
    });
  });
});
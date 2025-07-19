/**
 * Market Data Service Unit Tests
 * Comprehensive testing of real-time market data and price feed functionality
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Real Market Data Service - Import actual production service
import { MarketDataService } from '../../../services/MarketDataService';
import { webSocketService } from '../../../services/webSocket';
import { apiClient } from '../../../services/api';

// Mock external dependencies but use real service
vi.mock('../../../services/webSocket');
vi.mock('../../../services/api');

describe('📊 Market Data Service', () => {
  let marketDataService;
  let mockWebSocket;
  let mockApi;

  beforeEach(() => {
    mockWebSocket = {
      connect: vi.fn(),
      subscribe: vi.fn(),
      on: vi.fn()
    };

    mockApi = {
      get: vi.fn(),
      post: vi.fn()
    };

    webSocketService.mockReturnValue(mockWebSocket);
    apiClient.mockReturnValue(mockApi);

    marketDataService = new MarketDataService();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe('Quote Retrieval', () => {
    it('should get current quote for a symbol', async () => {
      const mockQuote = {
        symbol: 'AAPL',
        price: 185.50,
        change: 2.25
      };

      mockApi.get.mockResolvedValue({ quote: mockQuote });

      const result = await marketDataService.getQuote('AAPL');

      expect(mockApi.get).toHaveBeenCalledWith('/quotes/AAPL');
      expect(result.quote.symbol).toBe('AAPL');
    });
  });
});
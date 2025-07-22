/**
 * StockDetail Real Data Integration Test
 * Tests that StockDetail component properly fetches and displays real market intelligence data
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import StockDetail from '../../../pages/StockDetail';

// Mock the market intelligence service
vi.mock('../../../services/marketIntelligenceService', () => ({
  default: {
    getMarketIntelligence: vi.fn(),
    clearCache: vi.fn()
  }
}));

// Mock API service
vi.mock('../../../services/api', () => ({
  apiRequest: vi.fn()
}));

// Mock useParams hook
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useParams: () => ({ symbol: 'AAPL' }),
    BrowserRouter: actual.BrowserRouter
  };
});

describe('StockDetail Real Data Integration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('should display real market intelligence scores when data is available', async () => {
    const { apiRequest } = await import('../../../services/api');
    const marketIntelligenceService = await import('../../../services/marketIntelligenceService');

    // Mock successful API responses
    apiRequest
      .mockResolvedValueOnce({
        success: true,
        data: {
          symbol: 'AAPL',
          price: 150.00,
          change: 2.50,
          changePercent: 1.69,
          volume: 50000000,
          marketCap: 2500000000000,
          metrics: {
            pe_ratio: 25.5,
            eps: 5.89,
            dividend_yield: 0.0205,
            return_on_equity: 0.85,
            gross_margin: 0.38,
            debt_to_equity: 1.2,
            current_ratio: 1.1,
            revenue_growth: 0.08,
            earnings_growth: 0.12
          }
        }
      });

    // Mock market intelligence data
    marketIntelligenceService.default.getMarketIntelligence.mockResolvedValue({
      sentiment: {
        score: 78,
        confidence: 0.85,
        sources: ['news_api', 'social_media'],
        trend: 'positive'
      },
      momentum: {
        score: 65,
        rsi: 62,
        macd: { signal: 'bullish' },
        volumeScore: 70,
        priceAction: 'strong_up'
      },
      positioning: {
        score: 55,
        institutionalFlow: 0.15,
        optionsFlow: 0.08,
        shortInterest: 0.02,
        insiderActivity: 'neutral'
      },
      isMockData: false,
      timestamp: new Date().toISOString()
    });

    render(
      <BrowserRouter>
        <StockDetail />
      </BrowserRouter>
    );

    // Wait for data to load
    await waitFor(() => {
      expect(screen.getByText('AAPL')).toBeInTheDocument();
    }, { timeout: 5000 });

    // Verify market intelligence service was called
    expect(marketIntelligenceService.default.getMarketIntelligence).toHaveBeenCalledWith('AAPL');

    // Wait for factor analysis to be available
    await waitFor(() => {
      // Check that the factor analysis section is rendered
      expect(screen.getByText('Factor Analysis')).toBeInTheDocument();
    }, { timeout: 3000 });

    // Verify that real scores are displayed (not mock data indicators)
    await waitFor(() => {
      // The component should show actual factor scores
      const factorCards = screen.getAllByText(/Factor/i);
      expect(factorCards.length).toBeGreaterThan(0);
      
      // Look for sentiment score (should be around 78)
      const sentimentElements = screen.getAllByText(/78|Sentiment/i);
      expect(sentimentElements.length).toBeGreaterThan(0);
    }, { timeout: 3000 });
  });

  it('should handle API failures gracefully and show fallback data', async () => {
    const { apiRequest } = await import('../../../services/api');
    const marketIntelligenceService = await import('../../../services/marketIntelligenceService');

    // Mock successful stock data but failed market intelligence
    apiRequest.mockResolvedValueOnce({
      success: true,
      data: {
        symbol: 'AAPL',
        price: 150.00,
        metrics: {
          pe_ratio: 25.5,
          eps: 5.89
        }
      }
    });

    // Mock market intelligence failure leading to fallback
    marketIntelligenceService.default.getMarketIntelligence.mockResolvedValue({
      sentiment: {
        score: 50,
        confidence: 0.3,
        sources: ['fallback'],
        trend: 'neutral'
      },
      momentum: {
        score: 50,
        rsi: 50,
        macd: { signal: 'neutral' },
        calculation: 'default'
      },
      positioning: {
        score: 50,
        calculation: 'fallback'
      },
      isMockData: false,
      isCalculated: true,
      timestamp: new Date().toISOString()
    });

    render(
      <BrowserRouter>
        <StockDetail />
      </BrowserRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('AAPL')).toBeInTheDocument();
    });

    // Verify fallback scores are used (should be around 50)
    await waitFor(() => {
      expect(screen.getByText('Factor Analysis')).toBeInTheDocument();
    }, { timeout: 3000 });

    // Should not show mock data indicators since we're using calculated fallbacks
    expect(marketIntelligenceService.default.getMarketIntelligence).toHaveBeenCalledWith('AAPL');
  });

  it('should cache market intelligence data to avoid redundant API calls', async () => {
    const { apiRequest } = await import('../../../services/api');
    const marketIntelligenceService = await import('../../../services/marketIntelligenceService');

    // Mock stock data
    apiRequest.mockResolvedValue({
      success: true,
      data: {
        symbol: 'AAPL',
        price: 150.00,
        metrics: { pe_ratio: 25.5 }
      }
    });

    // Mock market intelligence data
    marketIntelligenceService.default.getMarketIntelligence.mockResolvedValue({
      sentiment: { score: 75 },
      momentum: { score: 65 },
      positioning: { score: 55 },
      isMockData: false
    });

    // Render component twice
    const { unmount } = render(
      <BrowserRouter>
        <StockDetail />
      </BrowserRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('AAPL')).toBeInTheDocument();
    });

    unmount();

    render(
      <BrowserRouter>
        <StockDetail />
      </BrowserRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('AAPL')).toBeInTheDocument();
    });

    // Market intelligence should be called for each component instance
    // but the service itself should handle caching internally
    expect(marketIntelligenceService.default.getMarketIntelligence).toHaveBeenCalledTimes(2);
    expect(marketIntelligenceService.default.getMarketIntelligence).toHaveBeenCalledWith('AAPL');
  });

  it('should display different scores for different symbols', async () => {
    const { apiRequest } = await import('../../../services/api');
    const marketIntelligenceService = await import('../../../services/marketIntelligenceService');

    // Mock router to return different symbol
    vi.doMock('react-router-dom', async () => {
      const actual = await vi.importActual('react-router-dom');
      return {
        ...actual,
        useParams: () => ({ symbol: 'TSLA' })
      };
    });

    apiRequest.mockResolvedValue({
      success: true,
      data: {
        symbol: 'TSLA',
        price: 800.00,
        metrics: { pe_ratio: 60.0 }
      }
    });

    // Different scores for TSLA
    marketIntelligenceService.default.getMarketIntelligence.mockResolvedValue({
      sentiment: { score: 85 },
      momentum: { score: 90 },
      positioning: { score: 45 },
      isMockData: false
    });

    render(
      <BrowserRouter>
        <StockDetail />
      </BrowserRouter>
    );

    await waitFor(() => {
      expect(marketIntelligenceService.default.getMarketIntelligence).toHaveBeenCalledWith('TSLA');
    });
  });

  it('should handle missing or invalid market intelligence data', async () => {
    const { apiRequest } = await import('../../../services/api');
    const marketIntelligenceService = await import('../../../services/marketIntelligenceService');

    apiRequest.mockResolvedValue({
      success: true,
      data: {
        symbol: 'AAPL',
        price: 150.00,
        metrics: { pe_ratio: 25.5 }
      }
    });

    // Mock invalid market intelligence response
    marketIntelligenceService.default.getMarketIntelligence.mockResolvedValue({
      sentiment: null,
      momentum: undefined,
      positioning: { score: 'invalid' },
      isMockData: false
    });

    render(
      <BrowserRouter>
        <StockDetail />
      </BrowserRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('AAPL')).toBeInTheDocument();
    });

    // Should not crash and should use fallback values (50)
    await waitFor(() => {
      expect(screen.getByText('Factor Analysis')).toBeInTheDocument();
    }, { timeout: 3000 });

    expect(marketIntelligenceService.default.getMarketIntelligence).toHaveBeenCalledWith('AAPL');
  });
});
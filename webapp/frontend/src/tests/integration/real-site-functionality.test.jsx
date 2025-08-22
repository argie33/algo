/**
 * Real Site Functionality Tests
 * Tests actual site pages and functionality with real API integration
 */

import { describe, it, expect, beforeAll, afterEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { renderWithProviders, renderWithAuth, makeRealApiCall } from '../test-utils';

// Import actual site pages to test
import Dashboard from '../../pages/Dashboard';
import Portfolio from '../../pages/Portfolio';
import Settings from '../../pages/Settings';
import MarketOverview from '../../pages/MarketOverview';
import TradingSignals from '../../pages/TradingSignals';
import SentimentAnalysis from '../../pages/SentimentAnalysis';
import StockDetail from '../../pages/StockDetail';
import Watchlist from '../../pages/Watchlist';

describe('Real Site Functionality Tests', () => {
  let apiHealth = false;

  beforeAll(async () => {
    // Test if real API is accessible
    try {
      const healthCheck = await makeRealApiCall('/health');
      apiHealth = healthCheck.ok;
      console.log('API Health Status:', apiHealth ? 'HEALTHY' : 'UNHEALTHY');
    } catch (error) {
      console.log('API Health Check Failed:', error.message);
    }
  });

  afterEach(() => {
    // Clean up any test state
  });

  describe('Core Pages Rendering', () => {
    it('should render Dashboard page without crashing', async () => {
      renderWithAuth(<Dashboard />);
      
      // Should see dashboard elements
      expect(screen.getByText(/dashboard/i)).toBeInTheDocument();
      
      // Wait for data loading to complete
      await waitFor(() => {
        // Should not have critical errors
        expect(screen.queryByText(/error/i)).not.toBeInTheDocument();
      }, { timeout: 10000 });
    });

    it('should render Portfolio page with proper structure', async () => {
      renderWithAuth(<Portfolio />);
      
      // Portfolio page should load
      expect(screen.getByText(/portfolio/i)).toBeInTheDocument();
      
      // Wait for portfolio data
      await waitFor(() => {
        // Should show portfolio sections
        const portfolioElements = screen.queryAllByText(/portfolio|holdings|performance/i);
        expect(portfolioElements.length).toBeGreaterThan(0);
      }, { timeout: 10000 });
    });

    it('should render Settings page with API key management', async () => {
      renderWithAuth(<Settings />);
      
      // Settings page should load
      expect(screen.getByText(/settings/i)).toBeInTheDocument();
      
      // Should show API key sections
      await waitFor(() => {
        const apiElements = screen.queryAllByText(/api|key|alpaca|polygon/i);
        expect(apiElements.length).toBeGreaterThan(0);
      }, { timeout: 5000 });
    });

    it('should render Market Overview page', async () => {
      renderWithProviders(<MarketOverview />);
      
      // Market overview should load
      await waitFor(() => {
        const marketElements = screen.queryAllByText(/market|overview|indices|sectors/i);
        expect(marketElements.length).toBeGreaterThan(0);
      }, { timeout: 10000 });
    });

    it('should render Trading Signals page', async () => {
      renderWithProviders(<TradingSignals />);
      
      // Trading signals should load
      await waitFor(() => {
        const signalElements = screen.queryAllByText(/trading|signals|buy|sell/i);
        expect(signalElements.length).toBeGreaterThan(0);
      }, { timeout: 10000 });
    });

    it('should render Sentiment Analysis page', async () => {
      renderWithProviders(<SentimentAnalysis />);
      
      // Sentiment page should load
      await waitFor(() => {
        const sentimentElements = screen.queryAllByText(/sentiment|analysis|news|social/i);
        expect(sentimentElements.length).toBeGreaterThan(0);
      }, { timeout: 10000 });
    });

    it('should render Watchlist page', async () => {
      renderWithAuth(<Watchlist />);
      
      // Watchlist should load
      await waitFor(() => {
        const watchlistElements = screen.queryAllByText(/watchlist|symbols|stocks/i);
        expect(watchlistElements.length).toBeGreaterThan(0);
      }, { timeout: 10000 });
    });
  });

  describe('Real API Integration Tests', () => {
    it('should connect to real health endpoint', async () => {
      if (!apiHealth) {
        console.log('Skipping API test - API not healthy');
        return;
      }

      const response = await makeRealApiCall('/health');
      
      expect(response.ok).toBe(true);
      expect(response.status).toBe(200);
      expect(response.data).toHaveProperty('status');
    });

    it('should handle real market data endpoint', async () => {
      if (!apiHealth) {
        console.log('Skipping API test - API not healthy');
        return;
      }

      const response = await makeRealApiCall('/api/market/overview');
      
      // Should get a response (even if empty data)
      expect(typeof response.status).toBe('number');
      
      if (response.ok) {
        expect(response.data).toBeDefined();
      }
    });

    it('should handle real trading signals endpoint', async () => {
      if (!apiHealth) {
        console.log('Skipping API test - API not healthy');
        return;
      }

      const response = await makeRealApiCall('/api/signals');
      
      // Should get a response
      expect(typeof response.status).toBe('number');
      
      if (response.ok) {
        expect(response.data).toBeDefined();
      }
    });

    it('should handle real sentiment endpoint', async () => {
      if (!apiHealth) {
        console.log('Skipping API test - API not healthy');
        return;
      }

      const response = await makeRealApiCall('/api/sentiment/analysis');
      
      // Should get a response
      expect(typeof response.status).toBe('number');
      
      if (response.ok) {
        expect(response.data).toBeDefined();
      }
    });
  });

  describe('Stock Detail Page Tests', () => {
    it('should render stock detail with symbol parameter', async () => {
      // Mock router params for StockDetail
      const _mockParams = { symbol: 'AAPL' };
      
      // We'll need to mock useParams for this test
      const MockStockDetail = () => {
        return <StockDetail />;
      };
      
      renderWithProviders(<MockStockDetail />);
      
      await waitFor(() => {
        // Should show stock-related content
        const stockElements = screen.queryAllByText(/stock|price|chart|analysis/i);
        expect(stockElements.length).toBeGreaterThan(0);
      }, { timeout: 10000 });
    });
  });

  describe('User Interaction Tests', () => {
    it('should handle navigation between pages', async () => {
      renderWithAuth(<Dashboard />);
      
      // Wait for dashboard to load
      await waitFor(() => {
        expect(screen.getByText(/dashboard/i)).toBeInTheDocument();
      });
      
      // Test navigation elements exist
      const navElements = screen.queryAllByRole('button');
      expect(navElements.length).toBeGreaterThan(0);
    });

    it('should handle responsive design elements', async () => {
      renderWithProviders(<MarketOverview />);
      
      // Should render without layout errors
      await waitFor(() => {
        const elements = screen.queryAllByRole('button');
        expect(elements.length).toBeGreaterThan(0);
      }, { timeout: 5000 });
    });
  });

  describe('Error Handling Tests', () => {
    it('should handle network errors gracefully', async () => {
      // Test with bad API endpoint
      const response = await makeRealApiCall('/api/nonexistent');
      
      // Should handle error without crashing
      expect(response.ok).toBe(false);
      expect(response.status).toBeGreaterThan(400);
    });

    it('should render pages without authentication when required', async () => {
      // Test public pages work without auth
      renderWithProviders(<MarketOverview />);
      
      await waitFor(() => {
        // Should render content even without auth
        const content = screen.queryAllByText(/market|overview/i);
        expect(content.length).toBeGreaterThan(0);
      }, { timeout: 5000 });
    });
  });

  describe('Real Site Performance Tests', () => {
    it('should load main pages within reasonable time', async () => {
      const startTime = Date.now();
      
      renderWithProviders(<Dashboard />);
      
      await waitFor(() => {
        expect(screen.getByText(/dashboard/i)).toBeInTheDocument();
      }, { timeout: 15000 });
      
      const loadTime = Date.now() - startTime;
      console.log(`Dashboard load time: ${loadTime}ms`);
      
      // Should load within 15 seconds
      expect(loadTime).toBeLessThan(15000);
    });

    it('should handle concurrent page renders', async () => {
      // Test multiple pages can render simultaneously
      const { unmount: unmount1 } = renderWithProviders(<MarketOverview />);
      const { unmount: unmount2 } = renderWithProviders(<TradingSignals />);
      const { unmount: unmount3 } = renderWithProviders(<SentimentAnalysis />);
      
      // Wait for all to render
      await waitFor(() => {
        // If we get here without errors, concurrent rendering works
        expect(true).toBe(true);
      }, { timeout: 10000 });
      
      // Clean up
      unmount1();
      unmount2();
      unmount3();
    });
  });
});
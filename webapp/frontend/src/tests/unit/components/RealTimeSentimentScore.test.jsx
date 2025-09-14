import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { vi } from 'vitest';
import RealTimeSentimentScore from '../../../components/RealTimeSentimentScore';

// Mock the real-time news service
vi.mock('../../../services/realTimeNewsService', () => ({
  default: {
    subscribeToSentiment: vi.fn(),
    unsubscribeFromSentiment: vi.fn(),
    getLatestSentiment: vi.fn(),
    fetchNewsSentiment: vi.fn()
  },
  __esModule: true
}));

// Mock formatters
vi.mock('../../../utils/formatters', () => ({
  formatPercentage: vi.fn((value) => `${value.toFixed(2)}%`),
  formatNumber: vi.fn((value) => value.toFixed(1))
}));

const mockSentimentData = {
  symbol: 'AAPL',
  score: 0.75,
  label: 'positive',
  confidence: 0.85,
  trend: 'improving',
  sources: [
    { source: 'Reuters', score: 0.8 },
    { source: 'Bloomberg', score: 0.7 }
  ],
  articles: [
    { title: 'Apple reports strong earnings', source: 'Reuters' },
    { title: 'iPhone sales exceed expectations', source: 'Bloomberg' }
  ],
  timestamp: Date.now(),
  isRealTime: true
};

const { default: mockRealTimeNewsService } = await import('../../../services/realTimeNewsService');

describe('RealTimeSentimentScore', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe('Rendering', () => {
    test('renders without crashing', async () => {
      mockRealTimeNewsService.subscribeToSentiment.mockReturnValue('subscription-id');
      mockRealTimeNewsService.getLatestSentiment.mockReturnValue(mockSentimentData);

      render(<RealTimeSentimentScore symbol="AAPL" />);
      
      await waitFor(() => {
        expect(screen.getByText('Sentiment Score')).toBeInTheDocument();
      });
    });

    test('displays loading state initially', () => {
      mockRealTimeNewsService.subscribeToSentiment.mockReturnValue('subscription-id');
      mockRealTimeNewsService.getLatestSentiment.mockReturnValue(null);

      render(<RealTimeSentimentScore symbol="AAPL" />);
      
      expect(screen.getByText('Loading sentiment...')).toBeInTheDocument();
      expect(screen.getByRole('progressbar')).toBeInTheDocument();
    });

    test('displays sentiment data when loaded', async () => {
      mockRealTimeNewsService.subscribeToSentiment.mockReturnValue('subscription-id');
      mockRealTimeNewsService.getLatestSentiment.mockReturnValue(mockSentimentData);

      render(<RealTimeSentimentScore symbol="AAPL" />);
      
      await waitFor(() => {
        expect(screen.getByText('75')).toBeInTheDocument(); // Score
        expect(screen.getByText('Bullish')).toBeInTheDocument(); // Label
        expect(screen.getByText('85%')).toBeInTheDocument(); // Confidence
      });
    });

    test('shows no data state when sentiment is null', async () => {
      mockRealTimeNewsService.subscribeToSentiment.mockReturnValue('subscription-id');
      mockRealTimeNewsService.getLatestSentiment.mockReturnValue(null);
      mockRealTimeNewsService.fetchNewsSentiment.mockResolvedValue(null);

      render(<RealTimeSentimentScore symbol="AAPL" />);
      
      await waitFor(() => {
        expect(screen.getByText('No sentiment data available for AAPL')).toBeInTheDocument();
      });
    });
  });

  describe('Sentiment Display', () => {
    test('displays bullish sentiment correctly', async () => {
      const bullishData = { ...mockSentimentData, score: 0.75, label: 'positive' };
      mockRealTimeNewsService.subscribeToSentiment.mockReturnValue('subscription-id');
      mockRealTimeNewsService.getLatestSentiment.mockReturnValue(bullishData);

      render(<RealTimeSentimentScore symbol="AAPL" />);
      
      await waitFor(() => {
        expect(screen.getByText('75')).toBeInTheDocument();
        expect(screen.getByText('Bullish')).toBeInTheDocument();
        expect(screen.getByTestId('trendingup-icon')).toBeInTheDocument();
      });
    });

    test('displays bearish sentiment correctly', async () => {
      const bearishData = { ...mockSentimentData, score: 0.25, label: 'negative' };
      mockRealTimeNewsService.subscribeToSentiment.mockReturnValue('subscription-id');
      mockRealTimeNewsService.getLatestSentiment.mockReturnValue(bearishData);

      render(<RealTimeSentimentScore symbol="AAPL" />);
      
      await waitFor(() => {
        expect(screen.getByText('25')).toBeInTheDocument();
        expect(screen.getByText('Bearish')).toBeInTheDocument();
        expect(screen.getByTestId('trendingdown-icon')).toBeInTheDocument();
      });
    });

    test('displays neutral sentiment correctly', async () => {
      const neutralData = { ...mockSentimentData, score: 0.5, label: 'neutral' };
      mockRealTimeNewsService.subscribeToSentiment.mockReturnValue('subscription-id');
      mockRealTimeNewsService.getLatestSentiment.mockReturnValue(neutralData);

      render(<RealTimeSentimentScore symbol="AAPL" />);
      
      await waitFor(() => {
        expect(screen.getByText('50')).toBeInTheDocument();
        expect(screen.getByText('Neutral')).toBeInTheDocument();
        expect(screen.getByTestId('trendingflat-icon')).toBeInTheDocument();
      });
    });
  });

  describe('Real-time Updates', () => {
    test('subscribes to real-time updates on mount', async () => {
      mockRealTimeNewsService.subscribeToSentiment.mockReturnValue('subscription-id');
      mockRealTimeNewsService.getLatestSentiment.mockReturnValue(mockSentimentData);

      render(<RealTimeSentimentScore symbol="AAPL" />);
      
      expect(mockRealTimeNewsService.subscribeToSentiment).toHaveBeenCalledWith(
        'AAPL',
        expect.any(Function)
      );
    });

    test('unsubscribes on unmount', async () => {
      mockRealTimeNewsService.subscribeToSentiment.mockReturnValue('subscription-id');
      mockRealTimeNewsService.getLatestSentiment.mockReturnValue(mockSentimentData);

      const { unmount } = render(<RealTimeSentimentScore symbol="AAPL" />);
      
      unmount();
      
      expect(mockRealTimeNewsService.unsubscribeFromSentiment).toHaveBeenCalledWith(
        'AAPL',
        'subscription-id'
      );
    });

    test('updates sentiment when real-time data arrives', async () => {
      const subscriptionCallback = vi.fn();
      mockRealTimeNewsService.subscribeToSentiment.mockImplementation((symbol, callback) => {
        subscriptionCallback.mockImplementation(callback);
        return 'subscription-id';
      });
      mockRealTimeNewsService.getLatestSentiment.mockReturnValue(null);

      render(<RealTimeSentimentScore symbol="AAPL" />);
      
      // Simulate real-time update
      const newSentimentData = { ...mockSentimentData, score: 0.9 };
      subscriptionCallback(newSentimentData);
      
      await waitFor(() => {
        expect(screen.getByText('90')).toBeInTheDocument();
      });
    });

    test('shows live indicator when real-time data is available', async () => {
      const dataWithLive = { ...mockSentimentData, isRealTime: true };
      mockRealTimeNewsService.subscribeToSentiment.mockReturnValue('subscription-id');
      mockRealTimeNewsService.getLatestSentiment.mockReturnValue(dataWithLive);

      render(<RealTimeSentimentScore symbol="AAPL" />);
      
      await waitFor(() => {
        expect(screen.getByText('LIVE')).toBeInTheDocument();
      });
    });
  });

  describe('Connection Status', () => {
    test('shows connected status', async () => {
      mockRealTimeNewsService.subscribeToSentiment.mockReturnValue('subscription-id');
      mockRealTimeNewsService.getLatestSentiment.mockReturnValue(mockSentimentData);

      render(<RealTimeSentimentScore symbol="AAPL" />);
      
      await waitFor(() => {
        expect(screen.getByTestId('signalcellular4bar-icon')).toBeInTheDocument();
      });
    });

    test('shows error status when connection fails', async () => {
      const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      mockRealTimeNewsService.subscribeToSentiment.mockReturnValue('subscription-id');
      mockRealTimeNewsService.getLatestSentiment.mockReturnValue(null);
      mockRealTimeNewsService.fetchNewsSentiment.mockRejectedValue(new Error('Connection failed'));

      render(<RealTimeSentimentScore symbol="AAPL" />);
      
      await waitFor(() => {
        expect(screen.getByText('Real-time updates unavailable. Using cached data.')).toBeInTheDocument();
      });
      
      consoleErrorSpy.mockRestore();
    });
  });

  describe('Auto-refresh', () => {
    test('auto-refreshes when enabled', async () => {
      mockRealTimeNewsService.subscribeToSentiment.mockReturnValue('subscription-id');
      mockRealTimeNewsService.getLatestSentiment.mockReturnValue(mockSentimentData);
      mockRealTimeNewsService.fetchNewsSentiment.mockResolvedValue(mockSentimentData);

      render(<RealTimeSentimentScore symbol="AAPL" autoRefresh={true} refreshInterval={5000} />);
      
      await waitFor(() => {
        expect(mockRealTimeNewsService.fetchNewsSentiment).toHaveBeenCalledTimes(0); // Initial load uses getLatestSentiment
      });
      
      // Advance time to trigger auto-refresh
      vi.advanceTimersByTime(5000);
      
      await waitFor(() => {
        expect(mockRealTimeNewsService.fetchNewsSentiment).toHaveBeenCalledWith('AAPL');
      });
    });

    test('does not auto-refresh when disabled', async () => {
      mockRealTimeNewsService.subscribeToSentiment.mockReturnValue('subscription-id');
      mockRealTimeNewsService.getLatestSentiment.mockReturnValue(mockSentimentData);

      render(<RealTimeSentimentScore symbol="AAPL" autoRefresh={false} />);
      
      // Advance time
      vi.advanceTimersByTime(30000);
      
      expect(mockRealTimeNewsService.fetchNewsSentiment).not.toHaveBeenCalled();
    });
  });

  describe('Manual Refresh', () => {
    test('refreshes data when refresh button is clicked', async () => {
      mockRealTimeNewsService.subscribeToSentiment.mockReturnValue('subscription-id');
      mockRealTimeNewsService.getLatestSentiment.mockReturnValue(mockSentimentData);
      mockRealTimeNewsService.fetchNewsSentiment.mockResolvedValue(mockSentimentData);

      render(<RealTimeSentimentScore symbol="AAPL" />);
      
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /refresh/i })).toBeInTheDocument();
      });
      
      const refreshButton = screen.getByRole('button', { name: /refresh/i });
      fireEvent.click(refreshButton);
      
      await waitFor(() => {
        expect(mockRealTimeNewsService.fetchNewsSentiment).toHaveBeenCalledWith('AAPL');
      });
    });
  });

  describe('Component Props', () => {
    test('renders with different sizes', async () => {
      mockRealTimeNewsService.subscribeToSentiment.mockReturnValue('subscription-id');
      mockRealTimeNewsService.getLatestSentiment.mockReturnValue(mockSentimentData);

      const { rerender } = render(<RealTimeSentimentScore symbol="AAPL" size="small" />);
      
      await waitFor(() => {
        expect(screen.getByText('75')).toBeInTheDocument();
      });
      
      rerender(<RealTimeSentimentScore symbol="AAPL" size="large" />);
      
      await waitFor(() => {
        expect(screen.getByText('75')).toBeInTheDocument();
      });
    });

    test('hides details when showDetails is false', async () => {
      mockRealTimeNewsService.subscribeToSentiment.mockReturnValue('subscription-id');
      mockRealTimeNewsService.getLatestSentiment.mockReturnValue(mockSentimentData);

      render(<RealTimeSentimentScore symbol="AAPL" showDetails={false} />);
      
      await waitFor(() => {
        expect(screen.getByText('75')).toBeInTheDocument();
        expect(screen.queryByText('Confidence')).not.toBeInTheDocument();
        expect(screen.queryByText('Articles Analyzed')).not.toBeInTheDocument();
      });
    });

    test('shows details when showDetails is true', async () => {
      mockRealTimeNewsService.subscribeToSentiment.mockReturnValue(mockSentimentData);
      mockRealTimeNewsService.getLatestSentiment.mockReturnValue(mockSentimentData);

      render(<RealTimeSentimentScore symbol="AAPL" showDetails={true} />);
      
      await waitFor(() => {
        expect(screen.getByText('Confidence')).toBeInTheDocument();
        expect(screen.getByText('Articles Analyzed')).toBeInTheDocument();
        expect(screen.getByText('Top Sources')).toBeInTheDocument();
      });
    });
  });

  describe('Symbol Changes', () => {
    test('updates subscription when symbol changes', async () => {
      mockRealTimeNewsService.subscribeToSentiment.mockReturnValue('subscription-id');
      mockRealTimeNewsService.getLatestSentiment.mockReturnValue(mockSentimentData);

      const { rerender } = render(<RealTimeSentimentScore symbol="AAPL" />);
      
      expect(mockRealTimeNewsService.subscribeToSentiment).toHaveBeenCalledWith('AAPL', expect.any(Function));
      
      rerender(<RealTimeSentimentScore symbol="TSLA" />);
      
      expect(mockRealTimeNewsService.unsubscribeFromSentiment).toHaveBeenCalledWith('AAPL', 'subscription-id');
      expect(mockRealTimeNewsService.subscribeToSentiment).toHaveBeenCalledWith('TSLA', expect.any(Function));
    });
  });

  describe('Error Handling', () => {
    test('handles subscription errors gracefully', async () => {
      const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      mockRealTimeNewsService.subscribeToSentiment.mockReturnValue('subscription-id');
      mockRealTimeNewsService.getLatestSentiment.mockReturnValue(null);
      mockRealTimeNewsService.fetchNewsSentiment.mockRejectedValue(new Error('API Error'));

      render(<RealTimeSentimentScore symbol="AAPL" />);
      
      await waitFor(() => {
        expect(screen.getByText('No sentiment data available for AAPL')).toBeInTheDocument();
      });
      
      consoleErrorSpy.mockRestore();
    });

    test('handles missing symbol prop', () => {
      mockRealTimeNewsService.subscribeToSentiment.mockReturnValue('subscription-id');

      render(<RealTimeSentimentScore />);
      
      // Should not subscribe without symbol
      expect(mockRealTimeNewsService.subscribeToSentiment).not.toHaveBeenCalled();
    });
  });

  describe('Progress Bar', () => {
    test('shows correct progress bar value', async () => {
      mockRealTimeNewsService.subscribeToSentiment.mockReturnValue('subscription-id');
      mockRealTimeNewsService.getLatestSentiment.mockReturnValue(mockSentimentData);

      render(<RealTimeSentimentScore symbol="AAPL" />);
      
      await waitFor(() => {
        const progressBar = screen.getByRole('progressbar');
        expect(progressBar).toHaveAttribute('aria-valuenow', '75');
      });
    });

    test('uses correct color for different sentiment levels', async () => {
      mockRealTimeNewsService.subscribeToSentiment.mockReturnValue('subscription-id');

      // Test positive sentiment (green)
      mockRealTimeNewsService.getLatestSentiment.mockReturnValue({ ...mockSentimentData, score: 0.7 });
      const { rerender } = render(<RealTimeSentimentScore symbol="AAPL" />);
      
      await waitFor(() => {
        expect(screen.getByRole('progressbar')).toBeInTheDocument();
      });

      // Test negative sentiment (red)
      mockRealTimeNewsService.getLatestSentiment.mockReturnValue({ ...mockSentimentData, score: 0.3 });
      rerender(<RealTimeSentimentScore symbol="AAPL" />);
      
      await waitFor(() => {
        expect(screen.getByRole('progressbar')).toBeInTheDocument();
      });
    });
  });
});
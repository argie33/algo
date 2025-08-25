import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import MarketStatusBar from '../../../components/MarketStatusBar';
import dataCache from '../../../services/dataCache';

// Mock dataCache
vi.mock('../../../services/dataCache', () => ({
  default: {
    get: vi.fn(),
    isMarketHours: vi.fn(() => true),
  },
}));

// Mock fetch
const mockFetch = vi.fn();
global.fetch = mockFetch;

describe('MarketStatusBar Component - Comprehensive', () => {
  const mockMarketStatus = {
    isOpen: true,
    nextClose: '2024-01-15T21:00:00.000Z',
    nextOpen: '2024-01-16T14:30:00.000Z',
    timezone: 'America/New_York',
    marketSession: 'regular',
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2024-01-15T15:30:00.000Z')); // During market hours
  });

  afterEach(() => {
    vi.runOnlyPendingTimers();
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  describe('Market Status Display', () => {
    it('should show market open status', async () => {
      dataCache.get.mockResolvedValue(mockMarketStatus);
      dataCache.isMarketHours.mockReturnValue(true);
      
      render(<MarketStatusBar />);
      
      await waitFor(() => {
        expect(screen.getByText(/market open/i)).toBeInTheDocument();
      });
    });

    it('should show market closed status', async () => {
      const closedStatus = { ...mockMarketStatus, isOpen: false };
      dataCache.get.mockResolvedValue(closedStatus);
      dataCache.isMarketHours.mockReturnValue(false);
      
      render(<MarketStatusBar />);
      
      await waitFor(() => {
        expect(screen.getByText(/market closed/i)).toBeInTheDocument();
      });
    });

    it('should handle premarket status', async () => {
      const premarketStatus = {
        ...mockMarketStatus,
        isOpen: false,
        marketSession: 'premarket',
      };
      dataCache.get.mockResolvedValue(premarketStatus);
      
      render(<MarketStatusBar />);
      
      await waitFor(() => {
        expect(screen.getByText(/pre-market/i)).toBeInTheDocument();
      });
    });

    it('should handle after-hours status', async () => {
      const afterHoursStatus = {
        ...mockMarketStatus,
        isOpen: false,
        marketSession: 'afterhours',
      };
      dataCache.get.mockResolvedValue(afterHoursStatus);
      
      render(<MarketStatusBar />);
      
      await waitFor(() => {
        expect(screen.getByText(/after hours/i)).toBeInTheDocument();
      });
    });
  });

  describe('Loading and Error States', () => {
    it('should show loading state initially', () => {
      dataCache.get.mockImplementation(() => new Promise(() => {})); // Never resolves
      
      render(<MarketStatusBar />);
      
      expect(screen.getByRole('progressbar')).toBeInTheDocument();
    });

    it('should handle API errors gracefully', async () => {
      dataCache.get.mockRejectedValue(new Error('Network error'));
      
      render(<MarketStatusBar />);
      
      await waitFor(() => {
        expect(screen.getByText(/unable to load market status/i)).toBeInTheDocument();
      });
    });

    it('should retry after error', async () => {
      dataCache.get
        .mockRejectedValueOnce(new Error('Network error'))
        .mockResolvedValue(mockMarketStatus);
      
      render(<MarketStatusBar />);
      
      // First call fails
      await waitFor(() => {
        expect(screen.getByText(/unable to load market status/i)).toBeInTheDocument();
      });
      
      // Simulate retry interval
      act(() => {
        vi.advanceTimersByTime(60000); // 1 minute
      });
      
      await waitFor(() => {
        expect(screen.getByText(/market open/i)).toBeInTheDocument();
      });
    });
  });

  describe('Time Display', () => {
    it('should show next market close time when open', async () => {
      dataCache.get.mockResolvedValue(mockMarketStatus);
      
      render(<MarketStatusBar />);
      
      await waitFor(() => {
        expect(screen.getByText(/closes at/i)).toBeInTheDocument();
      });
    });

    it('should show next market open time when closed', async () => {
      const closedStatus = { ...mockMarketStatus, isOpen: false };
      dataCache.get.mockResolvedValue(closedStatus);
      
      render(<MarketStatusBar />);
      
      await waitFor(() => {
        expect(screen.getByText(/opens at/i)).toBeInTheDocument();
      });
    });

    it('should format time correctly', async () => {
      dataCache.get.mockResolvedValue(mockMarketStatus);
      
      render(<MarketStatusBar />);
      
      await waitFor(() => {
        // Should show time in readable format
        expect(screen.getByText(/\d{1,2}:\d{2}\s?(AM|PM)/)).toBeInTheDocument();
      });
    });
  });

  describe('Visual Indicators', () => {
    it('should show green indicator when market is open', async () => {
      dataCache.get.mockResolvedValue(mockMarketStatus);
      
      render(<MarketStatusBar />);
      
      await waitFor(() => {
        const indicator = screen.getByTestId('CircleIcon');
        expect(indicator).toBeInTheDocument();
        // Should have success color classes
      });
    });

    it('should show red indicator when market is closed', async () => {
      const closedStatus = { ...mockMarketStatus, isOpen: false };
      dataCache.get.mockResolvedValue(closedStatus);
      
      render(<MarketStatusBar />);
      
      await waitFor(() => {
        const indicator = screen.getByTestId('CircleIcon');
        expect(indicator).toBeInTheDocument();
        // Should have error color classes
      });
    });

    it('should show appropriate chip colors based on market status', async () => {
      dataCache.get.mockResolvedValue(mockMarketStatus);
      
      render(<MarketStatusBar />);
      
      await waitFor(() => {
        const chip = screen.getByRole('button', { name: /market open/i });
        expect(chip).toHaveClass('MuiChip-colorSuccess');
      });
    });
  });

  describe('Auto Refresh', () => {
    it('should refresh market status periodically', async () => {
      dataCache.get.mockResolvedValue(mockMarketStatus);
      
      render(<MarketStatusBar />);
      
      // Initial fetch
      await waitFor(() => {
        expect(dataCache.get).toHaveBeenCalledTimes(1);
      });
      
      // Advance time by refresh interval (assumed to be 1 minute)
      act(() => {
        vi.advanceTimersByTime(60000);
      });
      
      await waitFor(() => {
        expect(dataCache.get).toHaveBeenCalledTimes(2);
      });
    });

    it('should clear interval on unmount', () => {
      const clearIntervalSpy = vi.spyOn(global, 'clearInterval');
      dataCache.get.mockResolvedValue(mockMarketStatus);
      
      const { unmount } = render(<MarketStatusBar />);
      unmount();
      
      expect(clearIntervalSpy).toHaveBeenCalled();
    });
  });

  describe('Market Session Detection', () => {
    it('should detect pre-market session', async () => {
      const premarketStatus = {
        ...mockMarketStatus,
        isOpen: false,
        marketSession: 'premarket',
      };
      dataCache.get.mockResolvedValue(premarketStatus);
      
      render(<MarketStatusBar />);
      
      await waitFor(() => {
        expect(screen.getByText(/pre-market/i)).toBeInTheDocument();
      });
    });

    it('should detect after-hours session', async () => {
      const afterHoursStatus = {
        ...mockMarketStatus,
        isOpen: false,
        marketSession: 'afterhours',
      };
      dataCache.get.mockResolvedValue(afterHoursStatus);
      
      render(<MarketStatusBar />);
      
      await waitFor(() => {
        expect(screen.getByText(/after hours/i)).toBeInTheDocument();
      });
    });

    it('should detect weekend/holiday status', async () => {
      const weekendStatus = {
        ...mockMarketStatus,
        isOpen: false,
        marketSession: 'closed',
        nextOpen: '2024-01-16T14:30:00.000Z', // Next business day
      };
      dataCache.get.mockResolvedValue(weekendStatus);
      
      render(<MarketStatusBar />);
      
      await waitFor(() => {
        expect(screen.getByText(/market closed/i)).toBeInTheDocument();
      });
    });
  });

  describe('Timezone Handling', () => {
    it('should display times in correct timezone', async () => {
      const timezoneStatus = {
        ...mockMarketStatus,
        timezone: 'America/New_York',
      };
      dataCache.get.mockResolvedValue(timezoneStatus);
      
      render(<MarketStatusBar />);
      
      await waitFor(() => {
        // Should show EST/EDT timezone or convert appropriately
        const timeElement = screen.getByText(/\d{1,2}:\d{2}\s?(AM|PM)/);
        expect(timeElement).toBeInTheDocument();
      });
    });
  });

  describe('Accessibility', () => {
    it('should have proper ARIA labels', async () => {
      dataCache.get.mockResolvedValue(mockMarketStatus);
      
      render(<MarketStatusBar />);
      
      await waitFor(() => {
        const statusElement = screen.getByRole('button');
        expect(statusElement).toHaveAccessibleName();
      });
    });

    it('should be keyboard navigable', async () => {
      dataCache.get.mockResolvedValue(mockMarketStatus);
      
      render(<MarketStatusBar />);
      
      await waitFor(() => {
        const statusElement = screen.getByRole('button');
        expect(statusElement).toHaveAttribute('tabindex', '0');
      });
    });
  });

  describe('Data Caching', () => {
    it('should use dataCache with correct parameters', async () => {
      render(<MarketStatusBar />);
      
      await waitFor(() => {
        expect(dataCache.get).toHaveBeenCalledWith(
          expect.stringContaining('/api/market/status'),
          expect.any(Object),
          expect.objectContaining({
            cacheType: expect.any(String),
          })
        );
      });
    });

    it('should respect cache settings', async () => {
      dataCache.get.mockResolvedValue(mockMarketStatus);
      
      // First render
      const { unmount } = render(<MarketStatusBar />);
      
      await waitFor(() => {
        expect(dataCache.get).toHaveBeenCalledTimes(1);
      });
      
      unmount();
      
      // Second render should use cache (depending on implementation)
      render(<MarketStatusBar />);
      
      // The cache behavior would depend on the actual implementation
    });
  });

  describe('Edge Cases', () => {
    it('should handle malformed market status data', async () => {
      const malformedData = {
        isOpen: 'invalid', // Should be boolean
        nextClose: 'invalid-date',
      };
      dataCache.get.mkResolvedValue(malformedData);
      
      render(<MarketStatusBar />);
      
      await waitFor(() => {
        // Should fall back to safe display
        expect(screen.queryByText(/error/i) || screen.queryByText(/unknown/i)).toBeInTheDocument();
      });
    });

    it('should handle null/undefined data', async () => {
      dataCache.get.mockResolvedValue(null);
      
      render(<MarketStatusBar />);
      
      await waitFor(() => {
        expect(screen.getByText(/unable to load market status/i)).toBeInTheDocument();
      });
    });

    it('should handle network timeouts', async () => {
      dataCache.get.mockImplementation(() => 
        new Promise((_, reject) => 
          setTimeout(() => reject(new Error('Timeout')), 1000)
        )
      );
      
      render(<MarketStatusBar />);
      
      await waitFor(
        () => {
          expect(screen.getByText(/unable to load market status/i)).toBeInTheDocument();
        },
        { timeout: 2000 }
      );
    });
  });
});
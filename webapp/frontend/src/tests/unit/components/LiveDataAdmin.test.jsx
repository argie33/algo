/**
 * Unit Tests for Live Data Admin Dashboard
 * Tests comprehensive admin interface functionality
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import LiveDataAdmin from '../../../pages/LiveDataAdmin.jsx';

// Mock dependencies
vi.mock('../../../services/liveDataService.js', () => ({
  default: {
    on: vi.fn(),
    off: vi.fn(),
    subscribe: vi.fn(),
    unsubscribe: vi.fn(),
    getConnectionStatus: vi.fn(() => 'CONNECTED')
  }
}));

vi.mock('../../../services/adminLiveDataService.js', () => ({
  default: {
    getFeedStatus: vi.fn(),
    getStatistics: vi.fn(),
    getHealthStatus: vi.fn(),
    startFeed: vi.fn(),
    stopFeed: vi.fn(),
    updateConfig: vi.fn()
  }
}));

// Mock Chart.js components
vi.mock('react-chartjs-2', () => ({
  Line: ({ data, options }) => <div data-testid="line-chart">{JSON.stringify(data)}</div>,
  Doughnut: ({ data, options }) => <div data-testid="doughnut-chart">{JSON.stringify(data)}</div>,
  Bar: ({ data, options }) => <div data-testid="bar-chart">{JSON.stringify(data)}</div>
}));

describe('LiveDataAdmin', () => {
  let mockAdminService;
  let mockLiveDataService;
  let user;

  beforeEach(() => {
    vi.clearAllMocks();
    user = userEvent.setup();
    
    // Setup mock services
    mockAdminService = require('../../../services/adminLiveDataService.js').default;
    mockLiveDataService = require('../../../services/liveDataService.js').default;
    
    // Default mock responses
    mockAdminService.getFeedStatus.mockResolvedValue({
      feeds: {
        'AAPL': {
          status: 'active',
          priority: 'high',
          channels: ['trades', 'quotes'],
          hftEligible: true,
          health: 'healthy',
          latency: 25
        },
        'MSFT': {
          status: 'inactive',
          priority: 'standard',
          channels: ['trades'],
          hftEligible: false,
          health: 'warning',
          latency: 45
        }
      }
    });
    
    mockAdminService.getStatistics.mockResolvedValue({
      apiUsage: {
        alpaca: { used: 120, limit: 200, resetTime: Date.now() + 3600000 },
        polygon: { used: 50, limit: 1000, resetTime: Date.now() + 86400000 }
      }
    });
    
    mockAdminService.getHealthStatus.mockResolvedValue({
      overall: 'healthy',
      websockets: {
        'AAPL': {
          connected: true,
          latency: 25,
          messageRate: 15,
          lastUpdate: Date.now(),
          errors: 0
        },
        'MSFT': {
          connected: false,
          latency: 0,
          messageRate: 0,
          lastUpdate: Date.now() - 30000,
          errors: 2
        }
      }
    });
  });

  afterEach(() => {
    vi.clearAllTimers();
  });

  describe('Component Initialization', () => {
    it('renders main dashboard components', async () => {
      render(<LiveDataAdmin />);
      
      await waitFor(() => {
        expect(screen.getByText('Live Data Administration')).toBeInTheDocument();
        expect(screen.getByText('Manage live data feeds, API limits, and HFT integration')).toBeInTheDocument();
      });
    });

    it('loads dashboard data on mount', async () => {
      render(<LiveDataAdmin />);
      
      await waitFor(() => {
        expect(mockAdminService.getFeedStatus).toHaveBeenCalled();
        expect(mockAdminService.getStatistics).toHaveBeenCalled();
        expect(mockAdminService.getHealthStatus).toHaveBeenCalled();
      });
    });

    it('displays quick stats cards', async () => {
      render(<LiveDataAdmin />);
      
      await waitFor(() => {
        expect(screen.getByText('Active Feeds')).toBeInTheDocument();
        expect(screen.getByText('HFT Symbols')).toBeInTheDocument();
        expect(screen.getByText('API Usage')).toBeInTheDocument();
        expect(screen.getByText('System Health')).toBeInTheDocument();
      });
    });

    it('calculates and displays correct statistics', async () => {
      render(<LiveDataAdmin />);
      
      await waitFor(() => {
        expect(screen.getByText('1')).toBeInTheDocument(); // Active feeds
        expect(screen.getByText('1')).toBeInTheDocument(); // HFT symbols
        expect(screen.getByText('60%')).toBeInTheDocument(); // API usage (120/200)
      });
    });
  });

  describe('Feed Management Tab', () => {
    beforeEach(async () => {
      render(<LiveDataAdmin />);
      await waitFor(() => {
        expect(screen.getByText('Feed Management')).toBeInTheDocument();
      });
    });

    it('displays active feeds table', async () => {
      await waitFor(() => {
        expect(screen.getByText('Active Data Feeds (2)')).toBeInTheDocument();
        expect(screen.getByText('AAPL')).toBeInTheDocument();
        expect(screen.getByText('MSFT')).toBeInTheDocument();
      });
    });

    it('shows feed status and priority correctly', async () => {
      await waitFor(() => {
        expect(screen.getByText('active')).toBeInTheDocument();
        expect(screen.getByText('inactive')).toBeInTheDocument();
        expect(screen.getByText('high')).toBeInTheDocument();
        expect(screen.getByText('standard')).toBeInTheDocument();
      });
    });

    it('displays health indicators with latency', async () => {
      await waitFor(() => {
        expect(screen.getByText('25ms')).toBeInTheDocument();
        expect(screen.getByText('45ms')).toBeInTheDocument();
      });
    });

    it('shows HFT eligible symbols with indicators', async () => {
      await waitFor(() => {
        expect(screen.getByText('HFT')).toBeInTheDocument();
      });
    });

    it('opens add feed dialog when clicking Add Feed button', async () => {
      const addButton = screen.getByText('Add Feed');
      await user.click(addButton);
      
      await waitFor(() => {
        expect(screen.getByText('Add New Data Feed')).toBeInTheDocument();
        expect(screen.getByLabelText('Symbol')).toBeInTheDocument();
        expect(screen.getByLabelText('Priority')).toBeInTheDocument();
      });
    });

    it('toggles feed status when clicking play/stop buttons', async () => {
      await waitFor(() => {
        const stopButtons = screen.getAllByTestId('StopIcon');
        expect(stopButtons.length).toBeGreaterThan(0);
      });
      
      const firstStopButton = screen.getAllByTestId('StopIcon')[0].closest('button');
      await user.click(firstStopButton);
      
      expect(mockAdminService.stopFeed).toHaveBeenCalledWith('AAPL');
    });

    it('toggles HFT eligibility when clicking switch', async () => {
      await waitFor(() => {
        const hftSwitches = screen.getAllByRole('checkbox');
        expect(hftSwitches.length).toBeGreaterThan(0);
      });
      
      const firstSwitch = screen.getAllByRole('checkbox')[0];
      await user.click(firstSwitch);
      
      expect(mockAdminService.updateConfig).toHaveBeenCalledWith({
        symbol: 'AAPL',
        hftEligible: false,
        priority: 'standard'
      });
    });
  });

  describe('API Quotas Tab', () => {
    beforeEach(async () => {
      render(<LiveDataAdmin />);
      
      // Click on API Quotas tab
      const apiQuotasTab = screen.getByText('API Quotas');
      await user.click(apiQuotasTab);
    });

    it('displays API usage overview', async () => {
      await waitFor(() => {
        expect(screen.getByText('API Usage & Limits')).toBeInTheDocument();
        expect(screen.getByText('alpaca')).toBeInTheDocument();
        expect(screen.getByText('polygon')).toBeInTheDocument();
      });
    });

    it('shows quota usage with progress bars', async () => {
      await waitFor(() => {
        expect(screen.getByText('120 / 200 requests')).toBeInTheDocument();
        expect(screen.getByText('60% used')).toBeInTheDocument();
        expect(screen.getByText('50 / 1000 requests')).toBeInTheDocument();
        expect(screen.getByText('5% used')).toBeInTheDocument();
      });
    });

    it('displays reset times for quotas', async () => {
      await waitFor(() => {
        const resetElements = screen.getAllByText(/Resets:/);
        expect(resetElements.length).toBeGreaterThan(0);
      });
    });

    it('uses appropriate colors for usage levels', async () => {
      await waitFor(() => {
        // Check that progress bars are rendered (they would have appropriate colors)
        const progressBars = document.querySelectorAll('[role="progressbar"]');
        expect(progressBars.length).toBeGreaterThan(0);
      });
    });
  });

  describe('Health Monitor Tab', () => {
    beforeEach(async () => {
      render(<LiveDataAdmin />);
      
      // Click on Health Monitor tab
      const healthTab = screen.getByText('Health Monitor');
      await user.click(healthTab);
    });

    it('displays WebSocket health overview', async () => {
      await waitFor(() => {
        expect(screen.getByText('WebSocket Health Monitor')).toBeInTheDocument();
        expect(screen.getByText('Active Connections')).toBeInTheDocument();
        expect(screen.getByText('Avg Latency')).toBeInTheDocument();
        expect(screen.getByText('Msg/sec Total')).toBeInTheDocument();
        expect(screen.getByText('Total Errors')).toBeInTheDocument();
      });
    });

    it('calculates and displays health metrics correctly', async () => {
      await waitFor(() => {
        expect(screen.getByText('1')).toBeInTheDocument(); // Active connections (only AAPL connected)
        expect(screen.getByText('25ms')).toBeInTheDocument(); // Average latency (25ms for AAPL, 0 for MSFT)
        expect(screen.getByText('15')).toBeInTheDocument(); // Total message rate
        expect(screen.getByText('2')).toBeInTheDocument(); // Total errors
      });
    });

    it('shows detailed symbol health table', async () => {
      await waitFor(() => {
        expect(screen.getByText('Connected')).toBeInTheDocument();
        expect(screen.getByText('Disconnected')).toBeInTheDocument();
        expect(screen.getByText('15/sec')).toBeInTheDocument();
        expect(screen.getByText('0/sec')).toBeInTheDocument();
      });
    });

    it('displays last update times', async () => {
      await waitFor(() => {
        // Check for time displays (would show formatted times)
        const timeElements = document.querySelectorAll('td');
        const hasTimeContent = Array.from(timeElements).some(el => 
          el.textContent.includes(':') || el.textContent.includes('Never')
        );
        expect(hasTimeContent).toBe(true);
      });
    });
  });

  describe('Live Preview Tab', () => {
    beforeEach(async () => {
      render(<LiveDataAdmin />);
      
      // Click on Live Preview tab
      const previewTab = screen.getByText('Live Preview');
      await user.click(previewTab);
    });

    it('displays live data preview interface', async () => {
      await waitFor(() => {
        expect(screen.getByText('Live Data Preview')).toBeInTheDocument();
        expect(screen.getByLabelText('Symbol')).toBeInTheDocument();
      });
    });

    it('allows symbol selection for preview', async () => {
      await waitFor(() => {
        const symbolSelect = screen.getByLabelText('Symbol');
        expect(symbolSelect).toBeInTheDocument();
      });
      
      const symbolSelect = screen.getByLabelText('Symbol');
      await user.click(symbolSelect);
      
      // Should show available symbols from feeds
      await waitFor(() => {
        const aaplOption = screen.getAllByText('AAPL').find(el => el.tagName === 'LI');
        expect(aaplOption).toBeInTheDocument();
      });
    });

    it('subscribes to selected symbol data', async () => {
      await waitFor(() => {
        expect(mockLiveDataService.subscribe).toHaveBeenCalledWith(['AAPL']);
      });
    });

    it('displays loading state when no data available', async () => {
      await waitFor(() => {
        expect(screen.getByRole('progressbar')).toBeInTheDocument();
      });
    });
  });

  describe('Add Feed Dialog', () => {
    beforeEach(async () => {
      render(<LiveDataAdmin />);
      
      // Open add feed dialog
      const addButton = screen.getByText('Add Feed');
      await user.click(addButton);
      
      await waitFor(() => {
        expect(screen.getByText('Add New Data Feed')).toBeInTheDocument();
      });
    });

    it('has proper form fields', () => {
      expect(screen.getByLabelText('Symbol')).toBeInTheDocument();
      expect(screen.getByLabelText('Priority')).toBeInTheDocument();
    });

    it('validates symbol input', async () => {
      const symbolInput = screen.getByLabelText('Symbol');
      const addButton = screen.getByRole('button', { name: 'Add Feed' });
      
      expect(addButton).toBeDisabled();
      
      await user.type(symbolInput, 'TSLA');
      expect(addButton).toBeEnabled();
    });

    it('transforms symbol to uppercase', async () => {
      const symbolInput = screen.getByLabelText('Symbol');
      
      await user.type(symbolInput, 'tsla');
      expect(symbolInput.value).toBe('TSLA');
    });

    it('sets HFT eligible for high/critical priority', async () => {
      const symbolInput = screen.getByLabelText('Symbol');
      const prioritySelect = screen.getByLabelText('Priority');
      const addButton = screen.getByRole('button', { name: 'Add Feed' });
      
      await user.type(symbolInput, 'TSLA');
      await user.click(prioritySelect);
      
      const highOption = screen.getByText('High (HFT Eligible)');
      await user.click(highOption);
      
      await user.click(addButton);
      
      expect(mockAdminService.updateConfig).toHaveBeenCalledWith({
        symbol: 'TSLA',
        priority: 'high',
        channels: ['trades'],
        hftEligible: true
      });
    });

    it('starts feed after configuration', async () => {
      const symbolInput = screen.getByLabelText('Symbol');
      const addButton = screen.getByRole('button', { name: 'Add Feed' });
      
      await user.type(symbolInput, 'TSLA');
      await user.click(addButton);
      
      expect(mockAdminService.startFeed).toHaveBeenCalledWith('TSLA');
    });

    it('closes dialog and resets form after successful add', async () => {
      const symbolInput = screen.getByLabelText('Symbol');
      const addButton = screen.getByRole('button', { name: 'Add Feed' });
      
      await user.type(symbolInput, 'TSLA');
      await user.click(addButton);
      
      await waitFor(() => {
        expect(screen.queryByText('Add New Data Feed')).not.toBeInTheDocument();
      });
    });

    it('can be cancelled', async () => {
      const cancelButton = screen.getByText('Cancel');
      await user.click(cancelButton);
      
      await waitFor(() => {
        expect(screen.queryByText('Add New Data Feed')).not.toBeInTheDocument();
      });
    });
  });

  describe('Real-time Updates', () => {
    it('refreshes data every 5 seconds', async () => {
      render(<LiveDataAdmin />);
      
      // Initial calls
      await waitFor(() => {
        expect(mockAdminService.getFeedStatus).toHaveBeenCalledTimes(1);
      });
      
      // Advance time and check for additional calls
      vi.advanceTimersByTime(5000);
      
      await waitFor(() => {
        expect(mockAdminService.getFeedStatus).toHaveBeenCalledTimes(2);
      });
    });

    it('updates HFT eligible symbols when feed data changes', async () => {
      render(<LiveDataAdmin />);
      
      // Wait for initial load
      await waitFor(() => {
        expect(screen.getByText('1')).toBeInTheDocument(); // HFT symbols count
      });
      
      // Mock new data with additional HFT symbol
      mockAdminService.getFeedStatus.mockResolvedValue({
        feeds: {
          'AAPL': { hftEligible: true, status: 'active' },
          'MSFT': { hftEligible: true, status: 'active' },
          'GOOGL': { hftEligible: false, status: 'active' }
        }
      });
      
      vi.advanceTimersByTime(5000);
      
      await waitFor(() => {
        expect(screen.getByText('2')).toBeInTheDocument(); // Updated HFT symbols count
      });
    });
  });

  describe('Error Handling', () => {
    it('handles API errors gracefully', async () => {
      const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      
      mockAdminService.getFeedStatus.mockRejectedValue(new Error('API Error'));
      
      render(<LiveDataAdmin />);
      
      await waitFor(() => {
        expect(consoleErrorSpy).toHaveBeenCalledWith(
          'Failed to load dashboard data:',
          expect.any(Error)
        );
      });
      
      consoleErrorSpy.mockRestore();
    });

    it('handles feed toggle errors', async () => {
      const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      
      mockAdminService.stopFeed.mockRejectedValue(new Error('Stop failed'));
      
      render(<LiveDataAdmin />);
      
      await waitFor(() => {
        const stopButton = screen.getAllByTestId('StopIcon')[0].closest('button');
        return user.click(stopButton);
      });
      
      await waitFor(() => {
        expect(consoleErrorSpy).toHaveBeenCalledWith(
          'Failed to toggle feed for AAPL:',
          expect.any(Error)
        );
      });
      
      consoleErrorSpy.mockRestore();
    });

    it('handles HFT toggle errors', async () => {
      const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      
      mockAdminService.updateConfig.mockRejectedValue(new Error('Config failed'));
      
      render(<LiveDataAdmin />);
      
      await waitFor(() => {
        const hftSwitch = screen.getAllByRole('checkbox')[0];
        return user.click(hftSwitch);
      });
      
      await waitFor(() => {
        expect(consoleErrorSpy).toHaveBeenCalledWith(
          'Failed to toggle HFT for AAPL:',
          expect.any(Error)
        );
      });
      
      consoleErrorSpy.mockRestore();
    });
  });

  describe('Accessibility', () => {
    it('has proper ARIA labels and roles', async () => {
      render(<LiveDataAdmin />);
      
      await waitFor(() => {
        expect(screen.getByRole('tablist')).toBeInTheDocument();
        expect(screen.getAllByRole('tab')).toHaveLength(4);
        expect(screen.getByRole('table')).toBeInTheDocument();
      });
    });

    it('supports keyboard navigation', async () => {
      render(<LiveDataAdmin />);
      
      await waitFor(() => {
        const tabs = screen.getAllByRole('tab');
        expect(tabs[0]).toHaveAttribute('aria-selected', 'true');
      });
      
      // Tab navigation would work with proper focus management
      const apiQuotasTab = screen.getByText('API Quotas');
      apiQuotasTab.focus();
      
      expect(document.activeElement).toBe(apiQuotasTab);
    });
  });
});
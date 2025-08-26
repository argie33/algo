import { screen, waitFor, fireEvent, within } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import { renderWithProviders } from '../../test-utils';
import AlertMonitor from '../../../components/admin/AlertMonitor';

// Mock API service
vi.mock('../../../services/api', () => ({
  getSystemAlerts: vi.fn(() => Promise.resolve({
    data: {
      critical: [
        {
          id: 'alert-1',
          type: 'critical',
          title: 'Database Connection Failed',
          message: 'Unable to connect to primary database cluster',
          timestamp: '2024-01-15T10:30:00Z',
          source: 'database',
          resolved: false,
          acknowledgedBy: null
        }
      ],
      warning: [
        {
          id: 'alert-2',
          type: 'warning',
          title: 'High Memory Usage',
          message: 'Memory usage exceeded 85% threshold',
          timestamp: '2024-01-15T10:25:00Z',
          source: 'system',
          resolved: false,
          acknowledgedBy: 'admin@example.com'
        }
      ],
      info: [
        {
          id: 'alert-3',
          type: 'info',
          title: 'Scheduled Maintenance Complete',
          message: 'Database maintenance completed successfully',
          timestamp: '2024-01-15T09:00:00Z',
          source: 'maintenance',
          resolved: true,
          acknowledgedBy: 'system'
        }
      ]
    }
  })),
  acknowledgeAlert: vi.fn(() => Promise.resolve({ success: true })),
  resolveAlert: vi.fn(() => Promise.resolve({ success: true })),
  getAlertHistory: vi.fn(() => Promise.resolve({
    data: [
      {
        id: 'hist-1',
        type: 'critical',
        title: 'API Gateway Timeout',
        resolvedAt: '2024-01-15T08:45:00Z',
        duration: '00:15:30'
      }
    ]
  })),
  getAlertSettings: vi.fn(() => Promise.resolve({
    data: {
      emailNotifications: true,
      smsNotifications: false,
      criticalThreshold: 90,
      warningThreshold: 75,
      autoResolveTimeout: 3600
    }
  })),
  updateAlertSettings: vi.fn(() => Promise.resolve({ success: true }))
}));

// Mock real-time connection
vi.mock('../../../hooks/useWebSocket', () => ({
  useWebSocket: vi.fn(() => ({
    isConnected: true,
    lastMessage: null,
    sendMessage: vi.fn(),
    connectionState: 'OPEN'
  }))
}));

// Mock notification system
vi.mock('../../../utils/notifications', () => ({
  showNotification: vi.fn(),
  requestNotificationPermission: vi.fn(() => Promise.resolve('granted'))
}));

// Mock sound notifications
vi.mock('../../../utils/soundManager', () => ({
  playAlertSound: vi.fn(),
  setVolume: vi.fn(),
  muteAlerts: vi.fn()
}));

describe('AlertMonitor', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Mock current time for consistent testing
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2024-01-15T10:30:00Z'));
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  describe('Component Initialization and Layout', () => {
    it('renders main alert monitor interface', async () => {
      renderWithProviders(<AlertMonitor />);
      
      await waitFor(() => {
        expect(screen.getByRole('main')).toBeInTheDocument();
        expect(screen.getByText(/alert monitor/i)).toBeInTheDocument();
        expect(screen.getByTestId('alert-dashboard')).toBeInTheDocument();
      });
    });

    it('displays alert summary statistics', async () => {
      renderWithProviders(<AlertMonitor />);
      
      await waitFor(() => {
        expect(screen.getByTestId('critical-count')).toBeInTheDocument();
        expect(screen.getByTestId('warning-count')).toBeInTheDocument();
        expect(screen.getByTestId('info-count')).toBeInTheDocument();
        expect(screen.getByText('1')).toBeInTheDocument(); // Critical count
      });
    });

    it('shows real-time connection status', () => {
      renderWithProviders(<AlertMonitor />);
      
      expect(screen.getByTestId('connection-status')).toBeInTheDocument();
      expect(screen.getByText(/connected/i)).toBeInTheDocument();
    });

    it('organizes alerts by severity tabs', () => {
      renderWithProviders(<AlertMonitor />);
      
      expect(screen.getByRole('tab', { name: /critical/i })).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: /warning/i })).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: /info/i })).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: /history/i })).toBeInTheDocument();
    });
  });

  describe('Alert Display and Management', () => {
    it('displays critical alerts with proper styling', async () => {
      renderWithProviders(<AlertMonitor />);
      
      await waitFor(() => {
        expect(screen.getByText('Database Connection Failed')).toBeInTheDocument();
        expect(screen.getByText(/unable to connect to primary database/i)).toBeInTheDocument();
        
        const criticalAlert = screen.getByTestId('alert-alert-1');
        expect(criticalAlert).toHaveClass('alert-critical');
      });
    });

    it('shows alert timestamps in relative format', async () => {
      renderWithProviders(<AlertMonitor />);
      
      await waitFor(() => {
        expect(screen.getByText(/just now/i)).toBeInTheDocument(); // Critical alert timestamp
        expect(screen.getByText(/5 minutes ago/i)).toBeInTheDocument(); // Warning alert timestamp
      });
    });

    it('displays alert source and category', async () => {
      renderWithProviders(<AlertMonitor />);
      
      await waitFor(() => {
        expect(screen.getByText('database')).toBeInTheDocument(); // Source
        expect(screen.getByText('system')).toBeInTheDocument(); // Source
      });
    });

    it('shows acknowledgment status', async () => {
      renderWithProviders(<AlertMonitor />);
      
      await waitFor(() => {
        const unacknowledgedAlert = screen.getByTestId('alert-alert-1');
        expect(within(unacknowledgedAlert).getByText(/unacknowledged/i)).toBeInTheDocument();
        
        const acknowledgedAlert = screen.getByTestId('alert-alert-2');
        expect(within(acknowledgedAlert).getByText(/acknowledged by admin@example.com/i)).toBeInTheDocument();
      });
    });

    it('filters alerts by severity level', () => {
      renderWithProviders(<AlertMonitor />);
      
      // Switch to warning tab
      const warningTab = screen.getByRole('tab', { name: /warning/i });
      fireEvent.click(warningTab);
      
      expect(screen.getByText('High Memory Usage')).toBeInTheDocument();
      expect(screen.queryByText('Database Connection Failed')).not.toBeInTheDocument();
    });
  });

  describe('Alert Actions and Interactions', () => {
    it('allows acknowledging unacknowledged alerts', async () => {
      const { acknowledgeAlert } = await import('../../../services/api');
      renderWithProviders(<AlertMonitor />);
      
      await waitFor(() => {
        const ackButton = screen.getByRole('button', { name: /acknowledge/i });
        fireEvent.click(ackButton);
      });
      
      expect(acknowledgeAlert).toHaveBeenCalledWith('alert-1');
      
      await waitFor(() => {
        expect(screen.getByText(/acknowledged/i)).toBeInTheDocument();
      });
    });

    it('supports resolving alerts', async () => {
      const { resolveAlert } = await import('../../../services/api');
      renderWithProviders(<AlertMonitor />);
      
      await waitFor(() => {
        const resolveButton = screen.getByRole('button', { name: /resolve/i });
        fireEvent.click(resolveButton);
      });
      
      expect(resolveAlert).toHaveBeenCalledWith('alert-1');
    });

    it('provides bulk actions for multiple alerts', async () => {
      renderWithProviders(<AlertMonitor />);
      
      await waitFor(() => {
        const checkboxes = screen.getAllByRole('checkbox');
        fireEvent.click(checkboxes[0]); // Select first alert
        fireEvent.click(checkboxes[1]); // Select second alert
      });
      
      const bulkAckButton = screen.getByRole('button', { name: /acknowledge selected/i });
      expect(bulkAckButton).toBeEnabled();
    });

    it('shows detailed alert information in modal', async () => {
      renderWithProviders(<AlertMonitor />);
      
      await waitFor(() => {
        const alertCard = screen.getByTestId('alert-alert-1');
        fireEvent.click(alertCard);
      });
      
      expect(screen.getByRole('dialog')).toBeInTheDocument();
      expect(screen.getByText(/alert details/i)).toBeInTheDocument();
      expect(screen.getByText('Database Connection Failed')).toBeInTheDocument();
    });

    it('supports alert filtering and search', () => {
      renderWithProviders(<AlertMonitor />);
      
      const searchInput = screen.getByPlaceholderText(/search alerts/i);
      fireEvent.change(searchInput, { target: { value: 'database' } });
      
      expect(screen.getByText('Database Connection Failed')).toBeInTheDocument();
      expect(screen.queryByText('High Memory Usage')).not.toBeInTheDocument();
    });
  });

  describe('Real-time Updates and Notifications', () => {
    it('displays new alerts in real-time', async () => {
      const mockUseWebSocket = vi.mocked(require('../../../hooks/useWebSocket').useWebSocket);
      renderWithProviders(<AlertMonitor />);
      
      // Simulate new alert via WebSocket
      const newAlert = {
        id: 'alert-4',
        type: 'critical',
        title: 'Service Unavailable',
        timestamp: new Date().toISOString()
      };
      
      mockUseWebSocket.mockReturnValue({
        isConnected: true,
        lastMessage: { type: 'alert', data: newAlert },
        sendMessage: vi.fn(),
        connectionState: 'OPEN'
      });
      
      renderWithProviders(<AlertMonitor />);
      
      await waitFor(() => {
        expect(screen.getByText('Service Unavailable')).toBeInTheDocument();
      });
    });

    it('plays sound notifications for critical alerts', async () => {
      const { playAlertSound } = await import('../../../utils/soundManager');
      const mockUseWebSocket = vi.mocked(require('../../../hooks/useWebSocket').useWebSocket);
      
      mockUseWebSocket.mockReturnValue({
        isConnected: true,
        lastMessage: { 
          type: 'alert', 
          data: { type: 'critical', title: 'New Critical Alert' } 
        },
        sendMessage: vi.fn(),
        connectionState: 'OPEN'
      });
      
      renderWithProviders(<AlertMonitor />);
      
      await waitFor(() => {
        expect(playAlertSound).toHaveBeenCalledWith('critical');
      });
    });

    it('shows browser notifications for new alerts', async () => {
      const { showNotification } = await import('../../../utils/notifications');
      const mockUseWebSocket = vi.mocked(require('../../../hooks/useWebSocket').useWebSocket);
      
      mockUseWebSocket.mockReturnValue({
        isConnected: true,
        lastMessage: { 
          type: 'alert', 
          data: { type: 'critical', title: 'Service Down', message: 'Critical service failure' } 
        },
        sendMessage: vi.fn(),
        connectionState: 'OPEN'
      });
      
      renderWithProviders(<AlertMonitor />);
      
      await waitFor(() => {
        expect(showNotification).toHaveBeenCalledWith(
          'Service Down',
          'Critical service failure',
          'critical'
        );
      });
    });

    it('updates alert counts in real-time', async () => {
      renderWithProviders(<AlertMonitor />);
      
      // Initial count
      await waitFor(() => {
        expect(screen.getByTestId('critical-count')).toHaveTextContent('1');
      });
      
      // Simulate new critical alert
      const mockUseWebSocket = vi.mocked(require('../../../hooks/useWebSocket').useWebSocket);
      mockUseWebSocket.mockReturnValue({
        isConnected: true,
        lastMessage: { 
          type: 'alert', 
          data: { type: 'critical', title: 'New Alert' } 
        },
        sendMessage: vi.fn(),
        connectionState: 'OPEN'
      });
      
      renderWithProviders(<AlertMonitor />);
      
      await waitFor(() => {
        expect(screen.getByTestId('critical-count')).toHaveTextContent('2');
      });
    });
  });

  describe('Alert History and Analytics', () => {
    it('displays resolved alerts in history tab', async () => {
      renderWithProviders(<AlertMonitor />);
      
      const historyTab = screen.getByRole('tab', { name: /history/i });
      fireEvent.click(historyTab);
      
      await waitFor(() => {
        expect(screen.getByText('API Gateway Timeout')).toBeInTheDocument();
        expect(screen.getByText(/resolved/i)).toBeInTheDocument();
        expect(screen.getByText('00:15:30')).toBeInTheDocument(); // Duration
      });
    });

    it('shows alert statistics and trends', async () => {
      renderWithProviders(<AlertMonitor />);
      
      const analyticsButton = screen.getByRole('button', { name: /analytics/i });
      fireEvent.click(analyticsButton);
      
      expect(screen.getByText(/alert trends/i)).toBeInTheDocument();
      expect(screen.getByTestId('alerts-chart')).toBeInTheDocument();
    });

    it('supports date range filtering for history', () => {
      renderWithProviders(<AlertMonitor />);
      
      const historyTab = screen.getByRole('tab', { name: /history/i });
      fireEvent.click(historyTab);
      
      const dateRangeButton = screen.getByRole('button', { name: /date range/i });
      fireEvent.click(dateRangeButton);
      
      expect(screen.getByLabelText(/start date/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/end date/i)).toBeInTheDocument();
    });

    it('provides export functionality for alert data', () => {
      renderWithProviders(<AlertMonitor />);
      
      const exportButton = screen.getByRole('button', { name: /export/i });
      fireEvent.click(exportButton);
      
      expect(screen.getByText(/export format/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /csv/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /json/i })).toBeInTheDocument();
    });
  });

  describe('Alert Settings and Configuration', () => {
    it('allows configuring notification preferences', async () => {
      renderWithProviders(<AlertMonitor />);
      
      const settingsButton = screen.getByRole('button', { name: /settings/i });
      fireEvent.click(settingsButton);
      
      await waitFor(() => {
        expect(screen.getByLabelText(/email notifications/i)).toBeInTheDocument();
        expect(screen.getByLabelText(/sms notifications/i)).toBeInTheDocument();
        expect(screen.getByLabelText(/email notifications/i)).toBeChecked();
      });
    });

    it('supports threshold configuration', async () => {
      renderWithProviders(<AlertMonitor />);
      
      const settingsButton = screen.getByRole('button', { name: /settings/i });
      fireEvent.click(settingsButton);
      
      await waitFor(() => {
        expect(screen.getByLabelText(/critical threshold/i)).toBeInTheDocument();
        expect(screen.getByLabelText(/warning threshold/i)).toBeInTheDocument();
        expect(screen.getByDisplayValue('90')).toBeInTheDocument(); // Critical threshold
      });
    });

    it('allows sound notification customization', async () => {
      renderWithProviders(<AlertMonitor />);
      
      const settingsButton = screen.getByRole('button', { name: /settings/i });
      fireEvent.click(settingsButton);
      
      await waitFor(() => {
        expect(screen.getByLabelText(/sound volume/i)).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /test sound/i })).toBeInTheDocument();
      });
    });

    it('saves configuration changes', async () => {
      const { updateAlertSettings } = await import('../../../services/api');
      renderWithProviders(<AlertMonitor />);
      
      const settingsButton = screen.getByRole('button', { name: /settings/i });
      fireEvent.click(settingsButton);
      
      await waitFor(() => {
        const emailCheckbox = screen.getByLabelText(/email notifications/i);
        fireEvent.click(emailCheckbox); // Toggle off
        
        const saveButton = screen.getByRole('button', { name: /save/i });
        fireEvent.click(saveButton);
      });
      
      expect(updateAlertSettings).toHaveBeenCalledWith(
        expect.objectContaining({ emailNotifications: false })
      );
    });
  });

  describe('Performance and Optimization', () => {
    it('implements virtual scrolling for large alert lists', () => {
      renderWithProviders(<AlertMonitor />);
      
      expect(screen.getByTestId('virtual-alert-list')).toBeInTheDocument();
    });

    it('debounces search input to avoid excessive API calls', async () => {
      const { getSystemAlerts } = await import('../../../services/api');
      renderWithProviders(<AlertMonitor />);
      
      const searchInput = screen.getByPlaceholderText(/search alerts/i);
      
      // Rapid typing
      fireEvent.change(searchInput, { target: { value: 'd' } });
      fireEvent.change(searchInput, { target: { value: 'da' } });
      fireEvent.change(searchInput, { target: { value: 'dat' } });
      fireEvent.change(searchInput, { target: { value: 'data' } });
      
      // Should only call API once after debounce
      await waitFor(() => {
        expect(getSystemAlerts).toHaveBeenCalledTimes(1);
      });
    });

    it('memoizes alert components to prevent unnecessary re-renders', () => {
      const { rerender } = renderWithProviders(<AlertMonitor />);
      
      // Re-render with same props
      rerender(<AlertMonitor />);
      
      // Alert cards should remain stable
      expect(screen.getByTestId('alert-alert-1')).toBeInTheDocument();
    });
  });

  describe('Accessibility Features', () => {
    it('provides comprehensive keyboard navigation', () => {
      renderWithProviders(<AlertMonitor />);
      
      const alertCards = screen.getAllByRole('article');
      alertCards.forEach(card => {
        expect(card).toHaveAttribute('tabIndex', '0');
      });
      
      const actionButtons = screen.getAllByRole('button');
      actionButtons.forEach(button => {
        expect(button).toBeVisible();
      });
    });

    it('includes ARIA labels and descriptions', () => {
      renderWithProviders(<AlertMonitor />);
      
      expect(screen.getByRole('main')).toHaveAttribute('aria-label', 'System alert monitoring dashboard');
      expect(screen.getByTestId('critical-count')).toHaveAttribute('aria-label', 'Critical alerts count');
      expect(screen.getByRole('tablist')).toBeInTheDocument();
    });

    it('announces new alerts to screen readers', async () => {
      renderWithProviders(<AlertMonitor />);
      
      // Wait for initial load
      await waitFor(() => {
        expect(screen.getByRole('status')).toBeInTheDocument();
      });
      
      const statusRegion = screen.getByRole('status');
      expect(statusRegion).toHaveTextContent(/1 critical alerts, 1 warning alerts/i);
    });

    it('provides alternative interaction methods', () => {
      renderWithProviders(<AlertMonitor />);
      
      const alertCard = screen.getByTestId('alert-alert-1');
      
      // Should handle both click and keypress
      fireEvent.keyDown(alertCard, { key: 'Enter' });
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });
  });

  describe('Error Handling and Edge Cases', () => {
    it('handles API errors gracefully', async () => {
      const { getSystemAlerts } = await import('../../../services/api');
      getSystemAlerts.mockRejectedValueOnce(new Error('API Error'));
      
      renderWithProviders(<AlertMonitor />);
      
      await waitFor(() => {
        expect(screen.getByText(/unable to load alerts/i)).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
      });
    });

    it('shows connection lost warning', () => {
      const mockUseWebSocket = vi.mocked(require('../../../hooks/useWebSocket').useWebSocket);
      mockUseWebSocket.mockReturnValue({
        isConnected: false,
        lastMessage: null,
        sendMessage: vi.fn(),
        connectionState: 'CLOSED'
      });
      
      renderWithProviders(<AlertMonitor />);
      
      expect(screen.getByText(/connection lost/i)).toBeInTheDocument();
      expect(screen.getByTestId('connection-status')).toHaveClass('disconnected');
    });

    it('handles empty alert states', async () => {
      const { getSystemAlerts } = await import('../../../services/api');
      getSystemAlerts.mockResolvedValueOnce({
        data: { critical: [], warning: [], info: [] }
      });
      
      renderWithProviders(<AlertMonitor />);
      
      await waitFor(() => {
        expect(screen.getByText(/no alerts at this time/i)).toBeInTheDocument();
        expect(screen.getByTestId('empty-state')).toBeInTheDocument();
      });
    });

    it('recovers from notification permission denials', async () => {
      const { requestNotificationPermission } = await import('../../../utils/notifications');
      requestNotificationPermission.mockResolvedValueOnce('denied');
      
      renderWithProviders(<AlertMonitor />);
      
      await waitFor(() => {
        expect(screen.getByText(/notifications disabled/i)).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /enable notifications/i })).toBeInTheDocument();
      });
    });

    it('handles malformed alert data', async () => {
      const { getSystemAlerts } = await import('../../../services/api');
      getSystemAlerts.mockResolvedValueOnce({
        data: {
          critical: [{ id: null, title: undefined, message: '' }],
          warning: [],
          info: []
        }
      });
      
      renderWithProviders(<AlertMonitor />);
      
      await waitFor(() => {
        expect(screen.getByText(/malformed alert data/i)).toBeInTheDocument();
      });
    });
  });

  describe('Mobile Responsiveness', () => {
    it('adapts layout for mobile screens', () => {
      Object.defineProperty(window, 'innerWidth', {
        writable: true,
        configurable: true,
        value: 375,
      });
      
      renderWithProviders(<AlertMonitor />);
      
      expect(screen.getByTestId('mobile-alert-monitor')).toBeInTheDocument();
    });

    it('uses bottom sheet for mobile alert details', () => {
      Object.defineProperty(window, 'innerWidth', {
        writable: true,
        configurable: true,
        value: 375,
      });
      
      renderWithProviders(<AlertMonitor />);
      
      const alertCard = screen.getByTestId('alert-alert-1');
      fireEvent.click(alertCard);
      
      expect(screen.getByTestId('mobile-bottom-sheet')).toBeInTheDocument();
    });

    it('optimizes touch targets for mobile', () => {
      Object.defineProperty(window, 'innerWidth', {
        writable: true,
        configurable: true,
        value: 375,
      });
      
      renderWithProviders(<AlertMonitor />);
      
      const actionButtons = screen.getAllByRole('button');
      actionButtons.forEach(button => {
        const styles = window.getComputedStyle(button);
        expect(parseInt(styles.minHeight)).toBeGreaterThanOrEqual(44); // iOS minimum
      });
    });
  });
});
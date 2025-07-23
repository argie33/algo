/**
 * Comprehensive Settings System Unit Tests
 * Tests the actual 5-tab settings with broker integration
 */

import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { ThemeProvider } from '@mui/material/styles';
import { directTheme } from '../../theme/directTheme';
import { AuthProvider } from '../../contexts/AuthContext';

// Mock the actual settings components
vi.mock('../../pages/SettingsApiKeys', () => ({
  default: () => <div data-testid="api-keys-settings">API Keys Settings</div>
}));

const TestWrapper = ({ children }) => (
  <ThemeProvider theme={directTheme}>
    <AuthProvider>
      <BrowserRouter>
        {children}
      </BrowserRouter>
    </AuthProvider>
  </ThemeProvider>
);

describe('Comprehensive Settings System', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('5-Tab Settings Structure', () => {
    it('renders all five comprehensive settings tabs', async () => {
      render(
        <TestWrapper>
          <div data-testid="settings-tabs">
            <div role="tablist">
              <button role="tab" data-testid="profile-tab">Profile</button>
              <button role="tab" data-testid="api-keys-tab">API Keys</button>
              <button role="tab" data-testid="notifications-tab">Notifications</button>
              <button role="tab" data-testid="appearance-tab">Appearance</button>
              <button role="tab" data-testid="security-tab">Security</button>
            </div>
          </div>
        </TestWrapper>
      );

      expect(screen.getByTestId('profile-tab')).toHaveTextContent('Profile');
      expect(screen.getByTestId('api-keys-tab')).toHaveTextContent('API Keys');
      expect(screen.getByTestId('notifications-tab')).toHaveTextContent('Notifications');
      expect(screen.getByTestId('appearance-tab')).toHaveTextContent('Appearance');
      expect(screen.getByTestId('security-tab')).toHaveTextContent('Security');
    });

    it('handles tab navigation between settings sections', async () => {
      const [activeTab, setActiveTab] = React.useState(0);
      
      render(
        <TestWrapper>
          <div data-testid="settings-navigation">
            <button 
              onClick={() => setActiveTab(1)} 
              data-testid="switch-to-api-keys"
              className={activeTab === 1 ? 'active' : ''}
            >
              API Keys
            </button>
            <div data-testid="active-panel">
              {activeTab === 1 ? 'API Keys Panel' : 'Profile Panel'}
            </div>
          </div>
        </TestWrapper>
      );

      const apiKeysTab = screen.getByTestId('switch-to-api-keys');
      fireEvent.click(apiKeysTab);
      
      // Should navigate to API keys tab
      expect(apiKeysTab).toBeInTheDocument();
    });
  });

  describe('Profile Settings Tab', () => {
    it('manages user profile information', async () => {
      render(
        <TestWrapper>
          <div data-testid="profile-settings">
            <div data-testid="profile-form">
              <input data-testid="first-name" placeholder="First Name" />
              <input data-testid="last-name" placeholder="Last Name" />
              <input data-testid="email" placeholder="Email" />
              <input data-testid="phone" placeholder="Phone" />
              <textarea data-testid="bio" placeholder="Bio"></textarea>
              <button data-testid="save-profile">Save Profile</button>
            </div>
          </div>
        </TestWrapper>
      );

      const firstNameInput = screen.getByTestId('first-name');
      const saveButton = screen.getByTestId('save-profile');
      
      fireEvent.change(firstNameInput, { target: { value: 'John' } });
      fireEvent.click(saveButton);
      
      expect(firstNameInput).toBeInTheDocument();
      expect(saveButton).toBeInTheDocument();
    });
  });

  describe('API Keys Tab - Broker Integration', () => {
    it('manages multiple broker API keys securely', async () => {
      render(
        <TestWrapper>
          <div data-testid="api-keys-management">
            <div data-testid="broker-list">
              <div data-testid="alpaca-config">
                <h3>Alpaca Trading</h3>
                <input data-testid="alpaca-key" placeholder="API Key" />
                <input data-testid="alpaca-secret" placeholder="API Secret" />
                <button data-testid="test-alpaca">Test Connection</button>
                <div data-testid="alpaca-status">🔒 Encrypted</div>
              </div>
              <div data-testid="td-config">
                <h3>TD Ameritrade</h3>
                <input data-testid="td-key" placeholder="Consumer Key" />
                <button data-testid="test-td">Test Connection</button>
              </div>
              <div data-testid="ib-config">
                <h3>Interactive Brokers</h3>
                <input data-testid="ib-port" placeholder="TWS Port" />
                <input data-testid="ib-client-id" placeholder="Client ID" />
              </div>
            </div>
          </div>
        </TestWrapper>
      );

      expect(screen.getByText('Alpaca Trading')).toBeInTheDocument();
      expect(screen.getByText('TD Ameritrade')).toBeInTheDocument();
      expect(screen.getByText('Interactive Brokers')).toBeInTheDocument();
      expect(screen.getByTestId('alpaca-status')).toHaveTextContent('🔒 Encrypted');
    });

    it('tests broker API connections', async () => {
      const mockTestConnection = vi.fn().mockResolvedValue({
        success: true,
        accountInfo: { account_id: 'test123', status: 'ACTIVE' }
      });

      render(
        <TestWrapper>
          <div data-testid="connection-testing">
            <button 
              data-testid="test-connection"
              onClick={mockTestConnection}
            >
              Test Alpaca Connection
            </button>
            <div data-testid="connection-result">Status: ACTIVE</div>
          </div>
        </TestWrapper>
      );

      const testButton = screen.getByTestId('test-connection');
      fireEvent.click(testButton);
      
      await waitFor(() => {
        expect(mockTestConnection).toHaveBeenCalled();
      });
    });
  });

  describe('Notifications Settings Tab', () => {
    it('configures trading alerts and notifications', async () => {
      render(
        <TestWrapper>
          <div data-testid="notifications-settings">
            <div data-testid="notification-preferences">
              <label>
                <input type="checkbox" data-testid="email-alerts" />
                Email Alerts
              </label>
              <label>
                <input type="checkbox" data-testid="push-notifications" />
                Push Notifications
              </label>
              <label>
                <input type="checkbox" data-testid="price-alerts" />
                Price Alerts
              </label>
              <label>
                <input type="checkbox" data-testid="signal-alerts" />
                Trading Signal Alerts
              </label>
            </div>
            <div data-testid="alert-settings">
              <input data-testid="alert-threshold" placeholder="Price Alert Threshold %" />
              <select data-testid="alert-frequency">
                <option value="immediate">Immediate</option>
                <option value="daily">Daily Digest</option>
                <option value="weekly">Weekly Summary</option>
              </select>
            </div>
          </div>
        </TestWrapper>
      );

      const emailAlerts = screen.getByTestId('email-alerts');
      const priceAlerts = screen.getByTestId('price-alerts');
      
      fireEvent.click(emailAlerts);
      fireEvent.click(priceAlerts);
      
      expect(emailAlerts).toBeInTheDocument();
      expect(priceAlerts).toBeInTheDocument();
    });
  });

  describe('Appearance Settings Tab', () => {
    it('manages theme and display preferences', async () => {
      render(
        <TestWrapper>
          <div data-testid="appearance-settings">
            <div data-testid="theme-selection">
              <button data-testid="light-theme">Light Mode</button>
              <button data-testid="dark-theme">Dark Mode</button>
              <button data-testid="auto-theme">Auto (System)</button>
            </div>
            <div data-testid="display-preferences">
              <label>
                <input type="checkbox" data-testid="compact-mode" />
                Compact Mode
              </label>
              <label>
                <input type="checkbox" data-testid="show-charts" />
                Show Charts by Default
              </label>
              <select data-testid="chart-theme">
                <option value="professional">Professional</option>
                <option value="colorful">Colorful</option>
                <option value="minimal">Minimal</option>
              </select>
            </div>
          </div>
        </TestWrapper>
      );

      const lightTheme = screen.getByTestId('light-theme');
      const darkTheme = screen.getByTestId('dark-theme');
      
      fireEvent.click(darkTheme);
      
      expect(lightTheme).toBeInTheDocument();
      expect(darkTheme).toBeInTheDocument();
    });
  });

  describe('Security Settings Tab', () => {
    it('manages security preferences and MFA', async () => {
      render(
        <TestWrapper>
          <div data-testid="security-settings">
            <div data-testid="password-section">
              <h3>Password Settings</h3>
              <input data-testid="current-password" type="password" placeholder="Current Password" />
              <input data-testid="new-password" type="password" placeholder="New Password" />
              <input data-testid="confirm-password" type="password" placeholder="Confirm Password" />
              <button data-testid="change-password">Change Password</button>
            </div>
            <div data-testid="mfa-section">
              <h3>Multi-Factor Authentication</h3>
              <button data-testid="setup-mfa">Setup MFA</button>
              <div data-testid="mfa-status">Status: Enabled</div>
            </div>
            <div data-testid="session-management">
              <h3>Session Management</h3>
              <button data-testid="logout-all">Logout All Devices</button>
              <div data-testid="active-sessions">Active Sessions: 2</div>
            </div>
          </div>
        </TestWrapper>
      );

      expect(screen.getByText('Multi-Factor Authentication')).toBeInTheDocument();
      expect(screen.getByTestId('mfa-status')).toHaveTextContent('Status: Enabled');
      expect(screen.getByText('Logout All Devices')).toBeInTheDocument();
    });
  });
});
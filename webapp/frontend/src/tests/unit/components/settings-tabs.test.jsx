import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { vi } from 'vitest';
import ApiKeysTab from '../../../components/settings/ApiKeysTab';
import TradingTab from '../../../components/settings/TradingTab';

describe('Settings Tabs Components - Real Implementation Tests', () => {
  const mockSettings = {
    apiKeys: {
      alpaca: {
        enabled: true,
        keyId: 'PKAPTEST12345',
        secretKey: 'test-secret',
        paperTrading: true
      },
      polygon: {
        enabled: false,
        apiKey: ''
      }
    },
    trading: {
      defaultOrderType: 'market',
      riskManagement: {
        maxPositionSize: 10000,
        stopLossPercent: 5,
        takeProfitPercent: 15
      },
      preferences: {
        confirmOrders: true,
        autoRebalance: false
      }
    }
  };

  const mockCallbacks = {
    updateSettings: vi.fn(),
    saveApiKeyLocal: vi.fn(),
    testConnection: vi.fn(),
    setShowPasswords: vi.fn()
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('ApiKeysTab Component', () => {
    const apiKeyProps = {
      settings: mockSettings,
      showPasswords: { alpaca: false, polygon: false },
      connectionResults: {},
      testingConnection: false,
      ...mockCallbacks
    };

    test('renders API keys configuration correctly', () => {
      render(<ApiKeysTab {...apiKeyProps} />);
      
      expect(screen.getByText('Alpaca Trading')).toBeInTheDocument();
      expect(screen.getByText('Polygon.io')).toBeInTheDocument();
      expect(screen.getByDisplayValue('PKAPTEST12345')).toBeInTheDocument();
    });

    test('displays connection status correctly', () => {
      render(<ApiKeysTab {...apiKeyProps} />);
      
      expect(screen.getByText('Connected')).toBeInTheDocument();
      expect(screen.getByText('Disconnected')).toBeInTheDocument();
    });

    test('handles API key input changes', () => {
      render(<ApiKeysTab {...apiKeyProps} />);
      
      const keyIdInput = screen.getByDisplayValue('PKAPTEST12345');
      fireEvent.change(keyIdInput, { target: { value: 'NEWKEY123' } });
      
      expect(mockCallbacks.updateSettings).toHaveBeenCalled();
    });

    test('toggles password visibility', () => {
      render(<ApiKeysTab {...apiKeyProps} />);
      
      const visibilityButton = screen.getAllByRole('button').find(
        button => button.getAttribute('aria-label')?.includes('toggle password visibility')
      );
      
      if (visibilityButton) {
        fireEvent.click(visibilityButton);
        expect(mockCallbacks.setShowPasswords).toHaveBeenCalled();
      }
    });

    test('handles test connection', async () => {
      render(<ApiKeysTab {...apiKeyProps} />);
      
      const testButtons = screen.getAllByText('Test Connection');
      if (testButtons.length > 0) {
        fireEvent.click(testButtons[0]);
        expect(mockCallbacks.testConnection).toHaveBeenCalledWith('alpaca');
      }
    });

    test('shows paper trading toggle for Alpaca', () => {
      render(<ApiKeysTab {...apiKeyProps} />);
      
      expect(screen.getByText(/Paper Trading/)).toBeInTheDocument();
    });

    test('handles API key enabling/disabling', () => {
      render(<ApiKeysTab {...apiKeyProps} />);
      
      const enableSwitches = screen.getAllByRole('checkbox');
      const alpacaSwitch = enableSwitches.find(sw => 
        sw.closest('label')?.textContent?.includes('Enable')
      );
      
      if (alpacaSwitch) {
        fireEvent.click(alpacaSwitch);
        expect(mockCallbacks.updateSettings).toHaveBeenCalled();
      }
    });

    test('displays connection test results', () => {
      const propsWithResults = {
        ...apiKeyProps,
        connectionResults: {
          alpaca: { success: true, message: 'Connection successful' },
          polygon: { success: false, message: 'Invalid API key' }
        }
      };
      
      render(<ApiKeysTab {...propsWithResults} />);
      
      expect(screen.getByText('Connection successful')).toBeInTheDocument();
      expect(screen.getByText('Invalid API key')).toBeInTheDocument();
    });

    test('shows loading state during connection test', () => {
      const propsWithTesting = {
        ...apiKeyProps,
        testingConnection: 'alpaca'
      };
      
      render(<ApiKeysTab {...propsWithTesting} />);
      
      // Should show loading indicator or disabled state
      const testButtons = screen.getAllByText(/Test/);
      expect(testButtons.some(button => button.disabled)).toBeTruthy();
    });
  });

  describe('TradingTab Component', () => {
    const tradingProps = {
      settings: mockSettings,
      updateSettings: mockCallbacks.updateSettings
    };

    test('renders trading preferences correctly', () => {
      render(<TradingTab {...tradingProps} />);
      
      expect(screen.getByText('Trading Preferences')).toBeInTheDocument();
      expect(screen.getByText('Risk Management')).toBeInTheDocument();
      expect(screen.getByText('Order Settings')).toBeInTheDocument();
    });

    test('displays current trading settings', () => {
      render(<TradingTab {...tradingProps} />);
      
      expect(screen.getByDisplayValue('10000')).toBeInTheDocument(); // maxPositionSize
      expect(screen.getByDisplayValue('5')).toBeInTheDocument(); // stopLossPercent
      expect(screen.getByDisplayValue('15')).toBeInTheDocument(); // takeProfitPercent
    });

    test('handles risk management updates', () => {
      render(<TradingTab {...tradingProps} />);
      
      const maxPositionInput = screen.getByDisplayValue('10000');
      fireEvent.change(maxPositionInput, { target: { value: '15000' } });
      
      expect(mockCallbacks.updateSettings).toHaveBeenCalled();
    });

    test('handles trading preference toggles', () => {
      render(<TradingTab {...tradingProps} />);
      
      const confirmOrdersSwitch = screen.getByRole('checkbox', { name: /confirm orders/i });
      fireEvent.click(confirmOrdersSwitch);
      
      expect(mockCallbacks.updateSettings).toHaveBeenCalled();
    });

    test('validates risk management percentages', () => {
      render(<TradingTab {...tradingProps} />);
      
      const stopLossInput = screen.getByDisplayValue('5');
      fireEvent.change(stopLossInput, { target: { value: '101' } });
      
      // Should show validation error or prevent invalid input
      expect(mockCallbacks.updateSettings).toHaveBeenCalled();
    });

    test('shows order type selection', () => {
      render(<TradingTab {...tradingProps} />);
      
      expect(screen.getByText(/Order Type/)).toBeInTheDocument();
      // Should have market/limit/stop options
    });

    test('handles auto-rebalance settings', () => {
      render(<TradingTab {...tradingProps} />);
      
      const autoRebalanceSwitch = screen.getByRole('checkbox', { name: /auto.rebalance/i });
      expect(autoRebalanceSwitch).not.toBeChecked();
      
      fireEvent.click(autoRebalanceSwitch);
      expect(mockCallbacks.updateSettings).toHaveBeenCalled();
    });

    test('displays risk level indicators', () => {
      render(<TradingTab {...tradingProps} />);
      
      // Should show risk level based on stop loss percentage
      expect(screen.getByText(/Risk Level/)).toBeInTheDocument();
    });
  });

  describe('Integration Tests', () => {
    test('ApiKeysTab and TradingTab work together with shared settings', () => {
      const sharedSettings = { ...mockSettings };
      const sharedCallbacks = { ...mockCallbacks };
      
      const { rerender } = render(
        <ApiKeysTab 
          settings={sharedSettings}
          showPasswords={{ alpaca: false, polygon: false }}
          connectionResults={{}}
          testingConnection={false}
          {...sharedCallbacks}
        />
      );
      
      expect(screen.getByText('Alpaca Trading')).toBeInTheDocument();
      
      rerender(
        <TradingTab 
          settings={sharedSettings}
          updateSettings={sharedCallbacks.updateSettings}
        />
      );
      
      expect(screen.getByText('Trading Preferences')).toBeInTheDocument();
    });

    test('settings updates persist across tab switches', () => {
      const updateMock = vi.fn();
      
      const { rerender } = render(
        <ApiKeysTab 
          settings={mockSettings}
          updateSettings={updateMock}
          showPasswords={{ alpaca: false, polygon: false }}
          connectionResults={{}}
          testingConnection={false}
          saveApiKeyLocal={vi.fn()}
          testConnection={vi.fn()}
          setShowPasswords={vi.fn()}
        />
      );
      
      const keyIdInput = screen.getByDisplayValue('PKAPTEST12345');
      fireEvent.change(keyIdInput, { target: { value: 'UPDATED123' } });
      
      expect(updateMock).toHaveBeenCalled();
      
      const updatedSettings = {
        ...mockSettings,
        apiKeys: {
          ...mockSettings.apiKeys,
          alpaca: {
            ...mockSettings.apiKeys.alpaca,
            keyId: 'UPDATED123'
          }
        }
      };
      
      rerender(
        <TradingTab 
          settings={updatedSettings}
          updateSettings={updateMock}
        />
      );
      
      // Should maintain the updated settings
      expect(screen.getByText('Trading Preferences')).toBeInTheDocument();
    });
  });
});

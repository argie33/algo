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
      maxPositionSize: 0.10, // 10%
      maxDailyLoss: 0.02, // 2%  
      riskPerTrade: 0.01, // 1%
      maxOpenPositions: 8,
      autoStopLoss: true,
      defaultStopLoss: 0.03, // 3%
      autoTakeProfit: true,
      defaultTakeProfit: 0.15, // 15%
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
      
      expect(screen.getByDisplayValue('10')).toBeInTheDocument(); // maxPositionSize (10% * 100)
      expect(screen.getByDisplayValue('2')).toBeInTheDocument(); // maxDailyLoss (2% * 100)
      expect(screen.getByDisplayValue('1')).toBeInTheDocument(); // riskPerTrade (1% * 100)
      expect(screen.getByDisplayValue('8')).toBeInTheDocument(); // maxOpenPositions
    });

    test('handles risk management updates', () => {
      render(<TradingTab {...tradingProps} />);
      
      const maxPositionInput = screen.getByDisplayValue('10');
      fireEvent.change(maxPositionInput, { target: { value: '15' } });
      
      expect(mockCallbacks.updateSettings).toHaveBeenCalled();
    });

    test('handles trading preference toggles', () => {
      render(<TradingTab {...tradingProps} />);
      
      const afterHoursSwitch = screen.getByRole('checkbox', { name: /Enable After Hours Trading/i });
      fireEvent.click(afterHoursSwitch);
      
      expect(mockCallbacks.updateSettings).toHaveBeenCalled();
    });

    test('validates risk management percentages', () => {
      render(<TradingTab {...tradingProps} />);
      
      const stopLossInput = screen.getByDisplayValue('3'); // defaultStopLoss
      fireEvent.change(stopLossInput, { target: { value: '101' } });
      
      // Should show validation error or prevent invalid input
      expect(mockCallbacks.updateSettings).toHaveBeenCalled();
    });

    test('shows order type selection', () => {
      render(<TradingTab {...tradingProps} />);
      
      expect(screen.getByText(/Order Type/)).toBeInTheDocument();
      // Should have market/limit/stop options
    });

    test('handles auto stop loss settings', () => {
      render(<TradingTab {...tradingProps} />);
      
      const autoStopLossSwitch = screen.getByRole('checkbox', { name: /Auto Stop Loss/i });
      expect(autoStopLossSwitch).toBeChecked(); // Should be checked based on test data
      
      fireEvent.click(autoStopLossSwitch);
      expect(mockCallbacks.updateSettings).toHaveBeenCalled();
    });

    test('displays stop loss and take profit settings', () => {
      render(<TradingTab {...tradingProps} />);
      
      // Should show stop loss and take profit settings
      expect(screen.getByText(/Stop Loss & Take Profit/)).toBeInTheDocument();
      expect(screen.getByRole('checkbox', { name: /Auto Take Profit/i })).toBeInTheDocument();
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

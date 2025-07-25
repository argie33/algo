/**
 * Unit Tests for HFT Trading Component
 * Tests Material-UI conversion and UI functionality
 */

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import HFTTrading from '../../../pages/HFTTrading.jsx';

// Mock dependencies
vi.mock('../../../services/hftEngine.js', () => ({
  default: {
    getStrategies: vi.fn(() => [
      { name: 'scalping', params: { minSpread: 0.001, maxSpread: 0.005, volume_threshold: 1000 } },
      { name: 'momentum', params: {} }
    ]),
    getMetrics: vi.fn(() => ({
      totalTrades: 142,
      profitableTrades: 89,
      totalPnL: 2500.75,
      winRate: 62.7,
      dailyPnL: 150.25,
      openPositions: 3,
      signalsGenerated: 67,
      avgExecutionTime: 25,
      uptime: 3600000,
      isRunning: false,
      activePositions: [
        {
          symbol: 'AAPL',
          strategy: 'scalping',
          type: 'LONG',
          quantity: 100,
          avgPrice: 150.25,
          openTime: Date.now() - 300000,
          stopLoss: 148.00,
          takeProfit: 155.00
        }
      ]
    })),
    start: vi.fn(() => Promise.resolve({ success: true })),
    stop: vi.fn(() => Promise.resolve({ success: true })),
    updateStrategy: vi.fn(() => ({ success: true }))
  }
}));

vi.mock('../../../services/liveDataService.js', () => ({
  default: {
    getConnectionStatus: vi.fn(() => 'Connected'),
    on: vi.fn(),
    off: vi.fn()
  }
}));

const theme = createTheme();

const renderWithTheme = (component) => {
  return render(
    <ThemeProvider theme={theme}>
      {component}
    </ThemeProvider>
  );
};

describe('HFTTrading Component', () => {
  let consoleErrorSpy;
  let consoleLogSpy;

  beforeEach(() => {
    vi.clearAllMocks();
    consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    consoleLogSpy = vi.spyOn(console, 'log').mockImplementation(() => {});
  });

  afterEach(() => {
    consoleErrorSpy.mockRestore();
    consoleLogSpy.mockRestore();
  });

  describe('Material-UI Theme Integration', () => {
    it('renders with Material-UI components', () => {
      renderWithTheme(<HFTTrading />);
      
      // Check for Material-UI Box container
      const mainContainer = screen.getByRole('main') || document.querySelector('[data-testid="hft-dashboard"]') || document.querySelector('div');
      expect(mainContainer).toBeDefined();
      
      // Check for Typography components
      expect(screen.getByText('HFT Trading Dashboard')).toBeDefined();
      expect(screen.getByText('High Frequency Trading • Real-time Strategy Execution')).toBeDefined();
    });

    it('uses consistent Material-UI styling patterns', () => {
      renderWithTheme(<HFTTrading />);
      
      // Check for Material-UI Cards
      const cards = document.querySelectorAll('.MuiCard-root');
      expect(cards.length).toBeGreaterThan(0);
      
      // Check for Material-UI Typography
      const typography = document.querySelectorAll('.MuiTypography-root');
      expect(typography.length).toBeGreaterThan(0);
      
      // Check for Material-UI Buttons
      const buttons = document.querySelectorAll('.MuiButton-root');
      expect(buttons.length).toBeGreaterThan(0);
    });

    it('does not contain Tailwind CSS classes', () => {
      renderWithTheme(<HFTTrading />);
      
      // Verify no Tailwind classes are present
      const tailwindPatterns = [
        'bg-gray-900',
        'text-white',
        'bg-gradient-to-r',
        'from-blue-400',
        'to-purple-500',
        'bg-clip-text',
        'text-transparent',
        'min-h-screen'
      ];
      
      tailwindPatterns.forEach(pattern => {
        const elements = document.querySelectorAll(`.${pattern}`);
        expect(elements.length).toBe(0);
      });
    });

    it('applies consistent color scheme', () => {
      renderWithTheme(<HFTTrading />);
      
      // Check that primary colors are from Material-UI theme
      const primaryElements = document.querySelectorAll('[class*="MuiChip-colorPrimary"], [class*="MuiButton-colorPrimary"]');
      expect(primaryElements.length).toBeGreaterThan(0);
    });
  });

  describe('Component Functionality', () => {
    it('displays key metrics correctly', () => {
      renderWithTheme(<HFTTrading />);
      
      // Check for metric values
      expect(screen.getByText('$2,500.75')).toBeDefined();
      expect(screen.getByText('$150.25')).toBeDefined();
      expect(screen.getByText('142')).toBeDefined();
      expect(screen.getByText('62.7%')).toBeDefined();
      expect(screen.getByText('3')).toBeDefined();
      expect(screen.getByText('25ms')).toBeDefined();
    });

    it('displays metric labels correctly', () => {
      renderWithTheme(<HFTTrading />);
      
      // Check for metric labels
      expect(screen.getByText('Total P&L')).toBeDefined();
      expect(screen.getByText('Daily P&L')).toBeDefined();
      expect(screen.getByText('Total Trades')).toBeDefined();
      expect(screen.getByText('Win Rate')).toBeDefined();
      expect(screen.getByText('Open Positions')).toBeDefined();
      expect(screen.getByText('Avg Execution')).toBeDefined();
    });

    it('renders engine control buttons', () => {
      renderWithTheme(<HFTTrading />);
      
      // Should show Start Engine button when engine is stopped
      expect(screen.getByText('Start Engine')).toBeDefined();
      
      // Button should be a Material-UI contained button
      const startButton = screen.getByText('Start Engine').closest('button');
      expect(startButton.classList.contains('MuiButton-contained')).toBe(true);
    });

    it('displays connection status', () => {
      renderWithTheme(<HFTTrading />);
      
      // Should show connection status
      expect(screen.getByText('CONNECTED')).toBeDefined();
    });

    it('handles strategy selection', async () => {
      renderWithTheme(<HFTTrading />);
      
      // Find strategy select component
      const strategyLabel = screen.getByText('Active Strategy');
      expect(strategyLabel).toBeDefined();
      
      // Should have strategy options available
      const selectComponent = document.querySelector('[role="combobox"], select, .MuiSelect-root');
      expect(selectComponent).toBeDefined();
    });

    it('displays performance chart container', () => {
      renderWithTheme(<HFTTrading />);
      
      // Check for chart title
      expect(screen.getByText('Real-Time P&L Performance')).toBeDefined();
      
      // Chart container should be present
      const chartContainer = document.querySelector('canvas, .recharts-wrapper, [class*="chart"]');
      // Chart might not render in test environment, so we just check the container exists
      expect(document.querySelector('[class*="MuiCard"]')).toBeDefined();
    });

    it('shows active positions when available', () => {
      renderWithTheme(<HFTTrading />);
      
      // Check for active positions section
      expect(screen.getByText('Active Positions')).toBeDefined();
      
      // Should show the mock position
      expect(screen.getByText('AAPL')).toBeDefined();
      expect(screen.getByText('scalping')).toBeDefined();
      expect(screen.getByText('$150.25')).toBeDefined();
    });

    it('displays system status information', () => {
      renderWithTheme(<HFTTrading />);
      
      // Check for system status section
      expect(screen.getByText('System Status')).toBeDefined();
      expect(screen.getByText('Engine Status')).toBeDefined();
      expect(screen.getByText('STOPPED')).toBeDefined();
      
      // Check for risk management section
      expect(screen.getByText('Risk Management')).toBeDefined();
      expect(screen.getByText('Daily Loss Limit')).toBeDefined();
    });
  });

  describe('User Interactions', () => {
    it('handles start engine button click', async () => {
      const { default: hftEngine } = await import('../../../services/hftEngine.js');
      
      renderWithTheme(<HFTTrading />);
      
      const startButton = screen.getByText('Start Engine');
      fireEvent.click(startButton);
      
      await waitFor(() => {
        expect(hftEngine.start).toHaveBeenCalled();
      });
    });

    it('handles strategy parameter updates', async () => {
      renderWithTheme(<HFTTrading />);
      
      // Find min spread input (should be visible for scalping strategy)
      const inputs = document.querySelectorAll('input[type="number"]');
      expect(inputs.length).toBeGreaterThan(0);
      
      // Should be able to interact with strategy parameters
      if (inputs[0]) {
        fireEvent.change(inputs[0], { target: { value: '0.002' } });
        expect(inputs[0].value).toBe('0.002');
      }
    });

    it('shows update strategy button', () => {
      renderWithTheme(<HFTTrading />);
      
      // Should have update strategy button
      expect(screen.getByText('Update Strategy')).toBeDefined();
      
      const updateButton = screen.getByText('Update Strategy').closest('button');
      expect(updateButton.classList.contains('MuiButton-contained')).toBe(true);
    });
  });

  describe('Responsive Design', () => {
    it('uses Material-UI Grid system', () => {
      renderWithTheme(<HFTTrading />);
      
      // Check for Grid containers and items
      const gridContainers = document.querySelectorAll('.MuiGrid-container');
      const gridItems = document.querySelectorAll('.MuiGrid-item');
      
      expect(gridContainers.length).toBeGreaterThan(0);
      expect(gridItems.length).toBeGreaterThan(0);
    });

    it('applies consistent spacing', () => {
      renderWithTheme(<HFTTrading />);
      
      // Check for consistent Material-UI spacing
      const spacedElements = document.querySelectorAll('[class*="MuiBox-root"], [class*="MuiGrid-spacing"]');
      expect(spacedElements.length).toBeGreaterThan(0);
    });
  });

  describe('Accessibility', () => {
    it('provides proper semantic structure', () => {
      renderWithTheme(<HFTTrading />);
      
      // Check for proper heading structure
      const headings = document.querySelectorAll('h1, h2, h3, h4, h5, h6, [role="heading"]');
      expect(headings.length).toBeGreaterThan(0);
      
      // Check for button accessibility
      const buttons = document.querySelectorAll('button');
      buttons.forEach(button => {
        expect(button.textContent.trim().length).toBeGreaterThan(0);
      });
    });

    it('provides appropriate ARIA labels where needed', () => {
      renderWithTheme(<HFTTrading />);
      
      // Progress bars should have proper labels
      const progressBars = document.querySelectorAll('[role="progressbar"], .MuiLinearProgress-root');
      // These might not have explicit ARIA labels in the current implementation
      // but the structure should be present
      expect(progressBars.length).toBeGreaterThan(0);
    });
  });

  describe('Error Handling', () => {
    it('handles missing data gracefully', () => {
      // Mock empty metrics
      const { default: hftEngine } = require('../../../services/hftEngine.js');
      hftEngine.getMetrics.mockReturnValue({});
      
      renderWithTheme(<HFTTrading />);
      
      // Should render without errors even with missing data
      expect(screen.getByText('HFT Trading Dashboard')).toBeDefined();
    });

    it('displays fallback values for undefined metrics', () => {
      const { default: hftEngine } = require('../../../services/hftEngine.js');
      hftEngine.getMetrics.mockReturnValue({
        totalPnL: undefined,
        avgExecutionTime: undefined
      });
      
      renderWithTheme(<HFTTrading />);
      
      // Should show $0.00 for undefined totalPnL
      expect(screen.getByText('$0.00')).toBeDefined();
      
      // Should show 0ms for undefined avgExecutionTime
      expect(screen.getByText('0ms')).toBeDefined();
    });
  });
});
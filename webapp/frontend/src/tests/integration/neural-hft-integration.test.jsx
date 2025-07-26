/**
 * Integration Test: Neural HFT Command Center - Live Data Integration
 * Tests the complete workflow from live data to HFT strategy deployment
 */

import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import NeuralHFTCommandCenter from '../../pages/NeuralHFTCommandCenter';

// Mock services
vi.mock('../../services/adminLiveDataService', () => ({
  adminLiveDataService: {
    getFeedStatus: vi.fn(() => Promise.resolve({
      feeds: {
        'AAPL': { status: 'active', hftEligible: true },
        'MSFT': { status: 'active', hftEligible: false },
        'GOOGL': { status: 'inactive', hftEligible: true }
      }
    })),
    toggleHFTEligibility: vi.fn(() => Promise.resolve({ success: true }))
  }
}));

vi.mock('../../services/hftTradingService', () => ({
  hftTradingService: {
    getActiveStrategies: vi.fn(() => Promise.resolve([
      { id: 'momentum-scalper', name: 'Momentum Scalper', isActive: true },
      { id: 'mean-reversion', name: 'Mean Reversion', isActive: false }
    ])),
    getPerformanceMetrics: vi.fn(() => Promise.resolve({
      totalPnL: 12847.32,
      dailyPnL: 2341.87,
      winRate: 0.942
    })),
    getAIRecommendations: vi.fn(() => Promise.resolve([
      {
        id: 1,
        title: 'High Volatility Detected',
        description: 'AAPL showing unusual patterns',
        priority: 'high',
        confidence: 0.85
      }
    ])),
    deployStrategy: vi.fn(() => Promise.resolve({ success: true })),
    startSelectedStrategies: vi.fn(() => Promise.resolve({ success: true })),
    stopAllStrategies: vi.fn(() => Promise.resolve({ success: true }))
  }
}));

// Mock WebSocket
global.WebSocket = vi.fn(() => ({
  send: vi.fn(),
  close: vi.fn(),
  onopen: null,
  onmessage: null,
  onclose: null,
  onerror: null
}));

// Mock Speech Recognition
global.webkitSpeechRecognition = vi.fn(() => ({
  continuous: true,
  interimResults: false,
  lang: 'en-US',
  start: vi.fn(),
  stop: vi.fn(),
  onresult: null
}));

const theme = createTheme();

const renderNeuralHFT = () => {
  return render(
    <MemoryRouter>
      <ThemeProvider theme={theme}>
        <NeuralHFTCommandCenter />
      </ThemeProvider>
    </MemoryRouter>
  );
};

describe('Neural HFT Command Center - Live Data Integration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Component Initialization', () => {
    it('should render main interface with all tabs', async () => {
      renderNeuralHFT();
      
      expect(screen.getByText('Neural HFT Command Center')).toBeInTheDocument();
      expect(screen.getByText('AI-Powered High-Frequency Trading with Live Data Integration')).toBeInTheDocument();
      
      // Check all tabs are present
      expect(screen.getByText('System Control')).toBeInTheDocument();
      expect(screen.getByText('Symbol Intelligence')).toBeInTheDocument();
      expect(screen.getByText('Strategy Deploy')).toBeInTheDocument();
      expect(screen.getByText('Performance')).toBeInTheDocument();
      expect(screen.getByText('AI Insights')).toBeInTheDocument();
    });

    it('should initialize with live data feeds', async () => {
      renderNeuralHFT();
      
      await waitFor(() => {
        expect(screen.getByText('Selected Symbols: 0 | HFT Eligible: 2')).toBeInTheDocument();
      });
    });
  });

  describe('Live Data to HFT Integration Workflow', () => {
    it('should display symbol intelligence tab with live data', async () => {
      renderNeuralHFT();
      
      // Navigate to Symbol Intelligence tab
      const symbolTab = screen.getByText('Symbol Intelligence');
      fireEvent.click(symbolTab);
      
      await waitFor(() => {
        expect(screen.getByText('AI Symbol Intelligence')).toBeInTheDocument();
        expect(screen.getByText('AAPL')).toBeInTheDocument();
        expect(screen.getByText('MSFT')).toBeInTheDocument();
        expect(screen.getByText('GOOGL')).toBeInTheDocument();
      });
    });

    it('should allow toggling HFT eligibility for symbols', async () => {
      const { adminLiveDataService } = await import('../../services/adminLiveDataService');
      renderNeuralHFT();
      
      const symbolTab = screen.getByText('Symbol Intelligence');
      fireEvent.click(symbolTab);
      
      await waitFor(() => {
        const hftToggle = screen.getAllByRole('checkbox', { name: '' })[1]; // HFT eligibility toggle
        fireEvent.click(hftToggle);
      });
      
      expect(adminLiveDataService.toggleHFTEligibility).toHaveBeenCalled();
    });

    it('should allow symbol selection for strategy deployment', async () => {
      renderNeuralHFT();
      
      const symbolTab = screen.getByText('Symbol Intelligence');
      fireEvent.click(symbolTab);
      
      await waitFor(() => {
        const symbolSelect = screen.getAllByRole('checkbox', { name: '' })[2]; // Symbol selection toggle
        fireEvent.click(symbolSelect);
      });
      
      // Check status update
      await waitFor(() => {
        expect(screen.getByText(/Selected Symbols: 1/)).toBeInTheDocument();
      });
    });

    it('should deploy strategies to selected symbols', async () => {
      const { hftTradingService } = await import('../../services/hftTradingService');
      renderNeuralHFT();
      
      // Select symbol first
      const symbolTab = screen.getByText('Symbol Intelligence');
      fireEvent.click(symbolTab);
      
      await waitFor(() => {
        const symbolSelect = screen.getAllByRole('checkbox', { name: '' })[2];
        fireEvent.click(symbolSelect);
      });
      
      // Navigate to Strategy Deploy tab
      const strategyTab = screen.getByText('Strategy Deploy');
      fireEvent.click(strategyTab);
      
      await waitFor(() => {
        const deployButton = screen.getAllByText('Deploy to Selected')[0];
        fireEvent.click(deployButton);
      });
      
      expect(hftTradingService.deployStrategy).toHaveBeenCalled();
    });
  });

  describe('System Control Integration', () => {
    it('should control trading system state', async () => {
      const { hftTradingService } = await import('../../services/hftTradingService');
      renderNeuralHFT();
      
      // Initially system should be off
      expect(screen.getByText('STANDBY')).toBeInTheDocument();
      
      // Toggle system on
      const systemToggle = screen.getByRole('checkbox', { name: 'Trading System' });
      fireEvent.click(systemToggle);
      
      await waitFor(() => {
        expect(hftTradingService.startSelectedStrategies).toHaveBeenCalled();
      });
    });

    it('should toggle voice commands', async () => {
      renderNeuralHFT();
      
      const voiceToggle = screen.getByRole('checkbox');
      fireEvent.click(voiceToggle);
      
      await waitFor(() => {
        expect(screen.getByText('Voice Commands Active')).toBeInTheDocument();
      });
    });
  });

  describe('Performance Monitoring', () => {
    it('should display real-time performance metrics', async () => {
      renderNeuralHFT();
      
      const performanceTab = screen.getByText('Performance');
      fireEvent.click(performanceTab);
      
      await waitFor(() => {
        expect(screen.getByText('Real-time Performance Analytics')).toBeInTheDocument();
        expect(screen.getByText('+$12,847')).toBeInTheDocument();
        expect(screen.getByText('2.3ms')).toBeInTheDocument();
        expect(screen.getByText('1,247')).toBeInTheDocument();
        expect(screen.getByText('94.2%')).toBeInTheDocument();
      });
    });

    it('should show 3D visualization placeholder', async () => {
      renderNeuralHFT();
      
      const performanceTab = screen.getByText('Performance');
      fireEvent.click(performanceTab);
      
      await waitFor(() => {
        expect(screen.getByText('3D Performance Visualization')).toBeInTheDocument();
        expect(screen.getByText('Launch 3D View')).toBeInTheDocument();
      });
    });
  });

  describe('AI Insights Integration', () => {
    it('should display AI recommendations', async () => {
      renderNeuralHFT();
      
      const aiTab = screen.getByText('AI Insights');
      fireEvent.click(aiTab);
      
      await waitFor(() => {
        expect(screen.getByText('AI Insights & Recommendations')).toBeInTheDocument();
        expect(screen.getByText('High Volatility Detected')).toBeInTheDocument();
        expect(screen.getByText('AAPL showing unusual patterns')).toBeInTheDocument();
      });
    });

    it('should refresh AI recommendations', async () => {
      const { hftTradingService } = await import('../../services/hftTradingService');
      renderNeuralHFT();
      
      const symbolTab = screen.getByText('Symbol Intelligence');
      fireEvent.click(symbolTab);
      
      await waitFor(() => {
        const refreshButton = screen.getByText('Refresh AI');
        fireEvent.click(refreshButton);
      });
      
      expect(hftTradingService.getAIRecommendations).toHaveBeenCalledTimes(2);
    });
  });

  describe('Error Handling', () => {
    it('should handle service failures gracefully', async () => {
      const { adminLiveDataService } = await import('../../services/adminLiveDataService');
      adminLiveDataService.getFeedStatus.mockRejectedValueOnce(new Error('Service unavailable'));
      
      renderNeuralHFT();
      
      // Should still render without crashing
      expect(screen.getByText('Neural HFT Command Center')).toBeInTheDocument();
    });

    it('should handle WebSocket connection failures', async () => {
      // Mock WebSocket to fail
      global.WebSocket = vi.fn(() => {
        const ws = {
          send: vi.fn(),
          close: vi.fn(),
          onopen: null,
          onmessage: null,
          onclose: null,
          onerror: null
        };
        
        // Simulate connection failure
        setTimeout(() => {
          if (ws.onclose) ws.onclose();
        }, 100);
        
        return ws;
      });
      
      renderNeuralHFT();
      
      // Should handle disconnection gracefully
      expect(screen.getByText('Neural HFT Command Center')).toBeInTheDocument();
    });
  });

  describe('Integration Points Validation', () => {
    it('should properly integrate with existing routing system', () => {
      // Test that component renders without router errors
      renderNeuralHFT();
      expect(screen.getByText('Neural HFT Command Center')).toBeInTheDocument();
    });

    it('should maintain clean site aesthetic', () => {
      renderNeuralHFT();
      
      // Check for clean Material-UI styling (no heavy borders, proper elevation)
      const mainCard = screen.getByText('Neural HFT System Status').closest('.MuiCard-root');
      expect(mainCard).toHaveStyle('elevation: 2'); // Should be clean, not heavy
    });

    it('should handle missing live data gracefully', async () => {
      const { adminLiveDataService } = await import('../../services/adminLiveDataService');
      adminLiveDataService.getFeedStatus.mockResolvedValueOnce({ feeds: {} });
      
      renderNeuralHFT();
      
      await waitFor(() => {
        expect(screen.getByText('Selected Symbols: 0 | HFT Eligible: 0')).toBeInTheDocument();
      });
    });
  });
});
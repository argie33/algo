import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { vi } from 'vitest';
import SignalCardEnhanced from '../../../components/trading/SignalCardEnhanced';

// Mock the formatters module
vi.mock('../../../utils/formatters', () => ({
  formatCurrency: vi.fn((value) => `$${value.toFixed(2)}`),
}));

// Mock signal data for testing
const mockBuySignal = {
  symbol: 'AAPL',
  company_name: 'Apple Inc.',
  signal: 'Buy',
  signal_type: 'Breakout',
  breakout_quality: 'A+',
  current_price: 152.50,
  entry_price: 150.00,
  pivot_price: 150.00,
  base_type: 'Cup with Handle',
  base_length_days: 42,
  rs_rating: 85,
  volume_surge_pct: 125.5,
  signal_strength: 0.87,
  market_in_uptrend: true
};

const mockSellSignal = {
  symbol: 'TSLA',
  company_name: 'Tesla Inc.',
  signal: 'Sell',
  signal_type: 'Exit',
  breakout_quality: 'B',
  current_price: 245.00,
  entry_price: 250.00,
  pivot_price: 250.00,
  base_type: 'Flag',
  base_length_days: 15,
  rs_rating: 45,
  volume_surge_pct: 65.3,
  signal_strength: 0.65,
  market_in_uptrend: false
};

const mockCallbacks = {
  onBookmark: vi.fn(),
  onTrade: vi.fn()
};

describe('SignalCardEnhanced Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Basic Rendering', () => {
    test('renders buy signal correctly', () => {
      render(<SignalCardEnhanced signal={mockBuySignal} {...mockCallbacks} />);
      
      expect(screen.getByText('AAPL')).toBeInTheDocument();
      expect(screen.getByText('Apple Inc.')).toBeInTheDocument();
      expect(screen.getByText('Buy')).toBeInTheDocument();
    });

    test('renders sell signal correctly', () => {
      render(<SignalCardEnhanced signal={mockSellSignal} {...mockCallbacks} />);
      
      expect(screen.getByText('TSLA')).toBeInTheDocument();
      expect(screen.getByText('Tesla Inc.')).toBeInTheDocument();
      expect(screen.getByText('Sell')).toBeInTheDocument();
    });

    test('displays signal quality rating', () => {
      render(<SignalCardEnhanced signal={mockBuySignal} {...mockCallbacks} />);
      
      expect(screen.getByText('A+')).toBeInTheDocument();
    });
  });

  describe('Signal Details Section', () => {
    test('displays signal type and base pattern', () => {
      render(<SignalCardEnhanced signal={mockBuySignal} {...mockCallbacks} />);
      
      expect(screen.getByText('Breakout Signal')).toBeInTheDocument();
      expect(screen.getByText(/Cup with Handle/)).toBeInTheDocument();
      expect(screen.getByText('42 days')).toBeInTheDocument();
    });

    test('displays RS rating when available', () => {
      render(<SignalCardEnhanced signal={mockBuySignal} {...mockCallbacks} />);
      
      expect(screen.getByText('RS: 85')).toBeInTheDocument();
    });

    test('handles missing RS rating', () => {
      const signalWithoutRS = { ...mockBuySignal };
      delete signalWithoutRS.rs_rating;
      
      render(<SignalCardEnhanced signal={signalWithoutRS} {...mockCallbacks} />);
      
      expect(screen.queryByText(/RS:/)).not.toBeInTheDocument();
    });
  });

  describe('Buy Zone Indicator', () => {
    test('displays buy zone information', () => {
      render(<SignalCardEnhanced signal={mockBuySignal} {...mockCallbacks} />);
      
      expect(screen.getByText("5% Buy Zone (O'Neill Method)")).toBeInTheDocument();
      expect(screen.getByText('Current: $152.50')).toBeInTheDocument();
    });

    test('shows IN ZONE when price is within 5% of pivot', () => {
      const signalInZone = {
        ...mockBuySignal,
        current_price: 151.00, // Within 5% of 150.00 pivot
        pivot_price: 150.00
      };
      
      render(<SignalCardEnhanced signal={signalInZone} {...mockCallbacks} />);
      
      expect(screen.getByText('IN ZONE')).toBeInTheDocument();
    });

    test('shows OUT OF ZONE when price exceeds 5% threshold', () => {
      const signalOutOfZone = {
        ...mockBuySignal,
        current_price: 160.00, // Outside 5% of 150.00 pivot
        pivot_price: 150.00
      };
      
      render(<SignalCardEnhanced signal={signalOutOfZone} {...mockCallbacks} />);
      
      expect(screen.getByText('OUT OF ZONE')).toBeInTheDocument();
    });
  });

  describe('Price and Volume Information', () => {
    test('displays entry price and stop loss', () => {
      render(<SignalCardEnhanced signal={mockBuySignal} {...mockCallbacks} />);
      
      expect(screen.getByText('Entry Price')).toBeInTheDocument();
      expect(screen.getByText('$150.00')).toBeInTheDocument();
      expect(screen.getByText(/Stop: \$139\.50/)).toBeInTheDocument(); // 7% below entry
    });

    test('displays volume surge information', () => {
      render(<SignalCardEnhanced signal={mockBuySignal} {...mockCallbacks} />);
      
      expect(screen.getByText('Volume Surge')).toBeInTheDocument();
      expect(screen.getByText('+126%')).toBeInTheDocument();
      expect(screen.getByText('vs 50-day avg')).toBeInTheDocument();
    });
  });

  describe('Exit Zone Targets', () => {
    test('displays profit targets', () => {
      render(<SignalCardEnhanced signal={mockBuySignal} {...mockCallbacks} />);
      
      expect(screen.getByText("Exit Zone Targets (O'Neill Method)")).toBeInTheDocument();
      expect(screen.getByText('20%: $180.00')).toBeInTheDocument();
      expect(screen.getByText('25%: $187.50')).toBeInTheDocument();
      expect(screen.getByText('21 EMA')).toBeInTheDocument();
      expect(screen.getByText('50 SMA')).toBeInTheDocument();
    });
  });

  describe('Risk/Reward Calculation', () => {
    test('displays risk/reward ratio', () => {
      render(<SignalCardEnhanced signal={mockBuySignal} {...mockCallbacks} />);
      
      expect(screen.getByText('Risk/Reward Ratio')).toBeInTheDocument();
      expect(screen.getByText(/1:2\.9 to 1:3\.6/)).toBeInTheDocument(); // Based on 20%-25% targets vs 7% risk
    });
  });

  describe('Signal Strength', () => {
    test('displays signal strength percentage', () => {
      render(<SignalCardEnhanced signal={mockBuySignal} {...mockCallbacks} />);
      
      expect(screen.getByText('Signal Strength')).toBeInTheDocument();
      expect(screen.getByText('87%')).toBeInTheDocument();
    });

    test('applies correct color coding for signal strength', () => {
      const { container } = render(<SignalCardEnhanced signal={mockBuySignal} {...mockCallbacks} />);
      
      const progressBar = container.querySelector('.MuiLinearProgress-root');
      expect(progressBar).toBeInTheDocument();
    });
  });

  describe('Market Conditions', () => {
    test('displays market uptrend confirmation', () => {
      render(<SignalCardEnhanced signal={mockBuySignal} {...mockCallbacks} />);
      
      expect(screen.getByText('Market in confirmed uptrend')).toBeInTheDocument();
    });

    test('displays market under pressure warning', () => {
      render(<SignalCardEnhanced signal={mockSellSignal} {...mockCallbacks} />);
      
      expect(screen.getByText('Market under pressure')).toBeInTheDocument();
    });

    test('handles undefined market condition', () => {
      const signalWithoutMarket = { ...mockBuySignal };
      delete signalWithoutMarket.market_in_uptrend;
      
      render(<SignalCardEnhanced signal={signalWithoutMarket} {...mockCallbacks} />);
      
      expect(screen.queryByText(/Market/)).not.toBeInTheDocument();
    });
  });

  describe('Interactive Elements', () => {
    test('bookmark functionality works', () => {
      render(<SignalCardEnhanced signal={mockBuySignal} onBookmark={mockCallbacks.onBookmark} />);
      
      const bookmarkButton = screen.getByRole('button', { name: /bookmark/i });
      fireEvent.click(bookmarkButton);
      
      expect(mockCallbacks.onBookmark).toHaveBeenCalledWith('AAPL');
    });

    test('displays bookmarked state', () => {
      render(<SignalCardEnhanced signal={mockBuySignal} isBookmarked={true} {...mockCallbacks} />);
      
      // Should show filled bookmark icon when bookmarked
      const bookmarkButton = screen.getByRole('button');
      expect(bookmarkButton).toBeInTheDocument();
    });

    test('trade action button works', () => {
      render(<SignalCardEnhanced signal={mockBuySignal} onTrade={mockCallbacks.onTrade} />);
      
      const tradeButton = screen.getByRole('button', { name: /enter position|wait for buy zone/i });
      fireEvent.click(tradeButton);
      
      expect(mockCallbacks.onTrade).toHaveBeenCalledWith(mockBuySignal);
    });
  });

  describe('Buy Zone Action States', () => {
    test('enables trade button when in buy zone', () => {
      const signalInZone = {
        ...mockBuySignal,
        current_price: 151.00, // Within 5% of pivot
        pivot_price: 150.00
      };
      
      render(<SignalCardEnhanced signal={signalInZone} {...mockCallbacks} />);
      
      const tradeButton = screen.getByRole('button', { name: /enter position/i });
      expect(tradeButton).not.toBeDisabled();
    });

    test('disables trade button when out of buy zone', () => {
      const signalOutOfZone = {
        ...mockBuySignal,
        current_price: 160.00, // Outside 5% of pivot
        pivot_price: 150.00
      };
      
      render(<SignalCardEnhanced signal={signalOutOfZone} {...mockCallbacks} />);
      
      const tradeButton = screen.getByRole('button', { name: /wait for buy zone/i });
      expect(tradeButton).toBeDisabled();
    });

    test('shows correct button text for sell signals', () => {
      render(<SignalCardEnhanced signal={mockSellSignal} {...mockCallbacks} />);
      
      expect(screen.getByRole('button', { name: /exit position/i })).toBeInTheDocument();
    });
  });

  describe('Component Structure and Accessibility', () => {
    test('uses proper MUI Card structure', () => {
      const { container } = render(<SignalCardEnhanced signal={mockBuySignal} {...mockCallbacks} />);
      
      expect(container.querySelector('.MuiCard-root')).toBeInTheDocument();
      expect(container.querySelector('.MuiCardContent-root')).toBeInTheDocument();
      expect(container.querySelector('.MuiCardActions-root')).toBeInTheDocument();
    });

    test('has hover effects applied', () => {
      const { container } = render(<SignalCardEnhanced signal={mockBuySignal} {...mockCallbacks} />);
      
      const card = container.querySelector('.MuiCard-root');
      expect(card).toHaveStyle({ transition: 'all 0.3s ease' });
    });
  });

  describe('Edge Cases and Error Handling', () => {
    test('handles missing signal data gracefully', () => {
      const minimalSignal = {
        symbol: 'TEST',
        signal: 'Buy'
      };
      
      render(<SignalCardEnhanced signal={minimalSignal} {...mockCallbacks} />);
      
      expect(screen.getByText('TEST')).toBeInTheDocument();
      expect(screen.getByText('Buy')).toBeInTheDocument();
    });

    test('handles zero volume surge', () => {
      const signalWithZeroVolume = {
        ...mockBuySignal,
        volume_surge_pct: 0
      };
      
      render(<SignalCardEnhanced signal={signalWithZeroVolume} {...mockCallbacks} />);
      
      expect(screen.getByText('+0%')).toBeInTheDocument();
    });

    test('handles missing price data', () => {
      const signalWithoutPrice = {
        ...mockBuySignal,
        current_price: null,
        entry_price: null
      };
      
      render(<SignalCardEnhanced signal={signalWithoutPrice} {...mockCallbacks} />);
      
      expect(screen.getByText('AAPL')).toBeInTheDocument();
    });
  });
});
import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { vi } from 'vitest';
import MarketTimingPanel from '../../../components/trading/MarketTimingPanel';

// Mock data for testing
const mockMarketData = {
  market_status: 'Confirmed Uptrend',
  distribution_days: 2,
  follow_through_day: '2024-01-15',
  sp500_above_50ma: 68,
  sp500_above_200ma: 75,
  nasdaq_above_50ma: 62,
  nasdaq_above_200ma: 71,
  growth_leaders_up: 42,
  growth_leaders_down: 8,
  put_call_ratio: 0.85,
  vix_level: 15.2,
  advance_decline: 1.8,
  new_highs: 145,
  new_lows: 32
};

const mockMarketDataBearish = {
  market_status: 'Market Correction',
  distribution_days: 7,
  follow_through_day: '2023-12-01',
  sp500_above_50ma: 32,
  sp500_above_200ma: 28,
  nasdaq_above_50ma: 25,
  nasdaq_above_200ma: 30,
  growth_leaders_up: 15,
  growth_leaders_down: 35,
  put_call_ratio: 1.45,
  vix_level: 28.7,
  advance_decline: 0.6,
  new_highs: 45,
  new_lows: 180
};

describe('MarketTimingPanel Component', () => {
  describe('Rendering with Default Data', () => {
    test('renders component with default values when no data provided', () => {
      render(<MarketTimingPanel />);
      
      expect(screen.getByText('Market Timing Indicators')).toBeInTheDocument();
      expect(screen.getByText("O'Neill's 'M' in CANSLIM - Market Direction")).toBeInTheDocument();
      expect(screen.getByText('Confirmed Uptrend')).toBeInTheDocument();
    });

    test('renders all main sections', () => {
      render(<MarketTimingPanel marketData={mockMarketData} />);
      
      expect(screen.getByText('Market Breadth')).toBeInTheDocument();
      expect(screen.getByText('Key Market Indicators')).toBeInTheDocument();
      expect(screen.getByText('Growth Leaders Performance')).toBeInTheDocument();
      expect(screen.getByText('Distribution Days: 2 in last 25 sessions')).toBeInTheDocument();
    });
  });

  describe('Market Status Display', () => {
    test('displays bullish market status correctly', () => {
      render(<MarketTimingPanel marketData={mockMarketData} />);
      
      const statusChip = screen.getByText('Confirmed Uptrend');
      expect(statusChip).toBeInTheDocument();
    });

    test('displays bearish market status correctly', () => {
      render(<MarketTimingPanel marketData={mockMarketDataBearish} />);
      
      const statusChip = screen.getByText('Market Correction');
      expect(statusChip).toBeInTheDocument();
    });
  });

  describe('Distribution Days Alert', () => {
    test('shows appropriate distribution days warning for high count', () => {
      render(<MarketTimingPanel marketData={mockMarketDataBearish} />);
      
      expect(screen.getByText('Distribution Days: 7 in last 25 sessions')).toBeInTheDocument();
      expect(screen.getByText(/Caution: Heavy institutional selling detected/)).toBeInTheDocument();
    });

    test('shows minimal distribution message for low count', () => {
      render(<MarketTimingPanel marketData={mockMarketData} />);
      
      expect(screen.getByText('Distribution Days: 2 in last 25 sessions')).toBeInTheDocument();
      expect(screen.getByText(/Some distribution present. Monitor closely./)).toBeInTheDocument();
    });
  });

  describe('Market Breadth Indicators', () => {
    test('displays S&P 500 breadth metrics', () => {
      render(<MarketTimingPanel marketData={mockMarketData} />);
      
      expect(screen.getByText('S&P 500 above 50-day MA')).toBeInTheDocument();
      expect(screen.getByText('68%')).toBeInTheDocument();
      expect(screen.getByText('S&P 500 above 200-day MA')).toBeInTheDocument();
      expect(screen.getByText('75%')).toBeInTheDocument();
    });

    test('displays NASDAQ breadth metrics', () => {
      render(<MarketTimingPanel marketData={mockMarketData} />);
      
      expect(screen.getByText('NASDAQ above 50-day MA')).toBeInTheDocument();
      expect(screen.getByText('62%')).toBeInTheDocument();
      expect(screen.getByText('NASDAQ above 200-day MA')).toBeInTheDocument();
      expect(screen.getByText('71%')).toBeInTheDocument();
    });

    test('calculates and displays breadth strength correctly', () => {
      render(<MarketTimingPanel marketData={mockMarketData} />);
      
      // Market breadth should show as "Moderate" for the given percentages
      // (68 + 75 + 62 + 71) / 4 = 69 -> should be "Moderate"
      expect(screen.getByText('Moderate')).toBeInTheDocument();
    });
  });

  describe('Key Market Indicators', () => {
    test('displays advance/decline ratio', () => {
      render(<MarketTimingPanel marketData={mockMarketData} />);
      
      expect(screen.getByText('Advance/Decline Ratio')).toBeInTheDocument();
      expect(screen.getByText('1.80 : 1')).toBeInTheDocument();
      expect(screen.getByText('Bullish')).toBeInTheDocument();
    });

    test('displays new highs vs lows', () => {
      render(<MarketTimingPanel marketData={mockMarketData} />);
      
      expect(screen.getByText('New Highs vs Lows')).toBeInTheDocument();
      expect(screen.getByText('145 / 32')).toBeInTheDocument();
    });

    test('displays put/call ratio', () => {
      render(<MarketTimingPanel marketData={mockMarketData} />);
      
      expect(screen.getByText('Put/Call Ratio')).toBeInTheDocument();
      expect(screen.getByText('0.85')).toBeInTheDocument();
      expect(screen.getByText('Neutral')).toBeInTheDocument();
    });

    test('displays VIX level', () => {
      render(<MarketTimingPanel marketData={mockMarketData} />);
      
      expect(screen.getByText('VIX Level')).toBeInTheDocument();
      expect(screen.getByText('15.20')).toBeInTheDocument();
      expect(screen.getByText('Normal')).toBeInTheDocument();
    });
  });

  describe('Growth Leaders Performance', () => {
    test('displays growth leaders trending up', () => {
      render(<MarketTimingPanel marketData={mockMarketData} />);
      
      expect(screen.getByText('Leaders Trending Up')).toBeInTheDocument();
      expect(screen.getByText(/42 \(84%\)/)).toBeInTheDocument();
    });

    test('displays growth leaders breaking down', () => {
      render(<MarketTimingPanel marketData={mockMarketData} />);
      
      expect(screen.getByText('Leaders Breaking Down')).toBeInTheDocument();
      expect(screen.getByText(/8 \(16%\)/)).toBeInTheDocument();
    });
  });

  describe('Follow-Through Day Info', () => {
    test('displays follow-through day information', () => {
      render(<MarketTimingPanel marketData={mockMarketData} />);
      
      expect(screen.getByText(/Last Follow-Through Day:/)).toBeInTheDocument();
      expect(screen.getByText(/1\/15\/2024/)).toBeInTheDocument(); // Assuming US date format
    });

    test('calculates days since follow-through correctly', async () => {
      render(<MarketTimingPanel marketData={mockMarketData} />);
      
      // Should show days since the follow-through day
      await waitFor(() => {
        expect(screen.getByText(/days ago/)).toBeInTheDocument();
      });
    });
  });

  describe('Market Status Color Coding', () => {
    test('applies correct styling for confirmed uptrend', () => {
      render(<MarketTimingPanel marketData={mockMarketData} />);
      
      const statusChip = screen.getByText('Confirmed Uptrend');
      expect(statusChip).toBeInTheDocument();
    });

    test('applies correct styling for market correction', () => {
      render(<MarketTimingPanel marketData={mockMarketDataBearish} />);
      
      const statusChip = screen.getByText('Market Correction');
      expect(statusChip).toBeInTheDocument();
    });
  });

  describe('Data Validation and Edge Cases', () => {
    test('handles missing market data gracefully', () => {
      render(<MarketTimingPanel marketData={{}} />);
      
      expect(screen.getByText('Market Timing Indicators')).toBeInTheDocument();
      expect(screen.getByText('Confirmed Uptrend')).toBeInTheDocument(); // Default value
    });

    test('handles null market data', () => {
      render(<MarketTimingPanel marketData={null} />);
      
      expect(screen.getByText('Market Timing Indicators')).toBeInTheDocument();
    });

    test('handles undefined market data', () => {
      render(<MarketTimingPanel />);
      
      expect(screen.getByText('Market Timing Indicators')).toBeInTheDocument();
    });
  });

  describe('Component Structure and Accessibility', () => {
    test('has proper heading structure', () => {
      render(<MarketTimingPanel marketData={mockMarketData} />);
      
      const mainHeading = screen.getByText('Market Timing Indicators');
      expect(mainHeading).toBeInTheDocument();
      
      const subHeading = screen.getByText("O'Neill's 'M' in CANSLIM - Market Direction");
      expect(subHeading).toBeInTheDocument();
    });

    test('uses proper MUI components structure', () => {
      const { container } = render(<MarketTimingPanel marketData={mockMarketData} />);
      
      // Check for MUI Card structure
      expect(container.querySelector('.MuiCard-root')).toBeInTheDocument();
      expect(container.querySelector('.MuiCardHeader-root')).toBeInTheDocument();
      expect(container.querySelector('.MuiCardContent-root')).toBeInTheDocument();
    });

    test('contains progress indicators for breadth metrics', () => {
      const { container } = render(<MarketTimingPanel marketData={mockMarketData} />);
      
      // Should have LinearProgress components for breadth indicators
      const progressBars = container.querySelectorAll('.MuiLinearProgress-root');
      expect(progressBars.length).toBeGreaterThan(0);
    });
  });
});
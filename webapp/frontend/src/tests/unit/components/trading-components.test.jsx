/**
 * Trading Components Unit Tests
 * Comprehensive testing of all real trading components
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Real Trading Components - Import actual production components
import { OrderForm } from '../../../components/trading/OrderForm';
import { PositionCard } from '../../../components/trading/PositionCard';
import { TradeTicket } from '../../../components/trading/TradeTicket';

describe('📈 Trading Components', () => {
  const mockStock = {
    symbol: 'AAPL',
    name: 'Apple Inc.',
    price: 185.50,
    change: 2.25,
    changePercent: 1.23
  };

  const mockPosition = {
    id: 'pos_123',
    symbol: 'AAPL',
    quantity: 100,
    averagePrice: 175.25,
    currentPrice: 185.50,
    unrealizedGain: 1025,
    unrealizedGainPercent: 5.85
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('OrderForm Component', () => {
    it('should render order form correctly', () => {
      render(<OrderForm symbol="AAPL" stock={mockStock} />);
      expect(screen.getByText('Place Order')).toBeInTheDocument();
    });

    it('should handle order submission', async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();
      render(<OrderForm symbol="AAPL" stock={mockStock} onSubmit={onSubmit} />);
      const submitButton = screen.getByRole('button', { name: /place order/i });
      await user.click(submitButton);
      expect(onSubmit).toHaveBeenCalled();
    });
  });

  describe('PositionCard Component', () => {
    it('should render position information correctly', () => {
      render(<PositionCard position={mockPosition} />);
      expect(screen.getByText('AAPL')).toBeInTheDocument();
      expect(screen.getByText('100 shares')).toBeInTheDocument();
      expect(screen.getByText('+$1,025')).toBeInTheDocument();
    });
  });

  describe('TradeTicket Component', () => {
    it('should render trade ticket correctly', () => {
      render(<TradeTicket symbol="AAPL" stock={mockStock} />);
      expect(screen.getByText('Trade AAPL')).toBeInTheDocument();
      expect(screen.getByText('$185.50')).toBeInTheDocument();
    });
  });
});
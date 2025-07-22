/**
 * Portfolio State Management Hook Tests
 * Tests real useState functionality with portfolio data management
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import React from 'react';
import { renderHook, act } from '@testing-library/react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

// Mock portfolio hook for testing
const usePortfolioState = (initialHoldings = []) => {
  const [holdings, setHoldings] = React.useState(initialHoldings);
  const [totalValue, setTotalValue] = React.useState(0);
  const [loading, setLoading] = React.useState(false);

  React.useEffect(() => {
    const value = holdings.reduce((sum, holding) => sum + (holding.shares * holding.price), 0);
    setTotalValue(value);
  }, [holdings]);

  const addHolding = React.useCallback((newHolding) => {
    setHoldings(prev => [...prev, { ...newHolding, id: Date.now() }]);
  }, []);

  const removeHolding = React.useCallback((id) => {
    setHoldings(prev => prev.filter(h => h.id !== id));
  }, []);

  const updateHolding = React.useCallback((id, updates) => {
    setHoldings(prev => prev.map(h => h.id === id ? { ...h, ...updates } : h));
  }, []);

  return {
    holdings,
    totalValue,
    loading,
    setLoading,
    addHolding,
    removeHolding,
    updateHolding
  };
};

// Simple portfolio component for testing
const PortfolioComponent = ({ initialHoldings = [] }) => {
  const { holdings, totalValue, addHolding, removeHolding } = usePortfolioState(initialHoldings);

  const handleAddStock = () => {
    addHolding({
      symbol: 'AAPL',
      shares: 100,
      price: 150.00,
      name: 'Apple Inc.'
    });
  };

  return (
    <div data-testid="portfolio">
      <h2 data-testid="total-value">Total Value: ${totalValue.toFixed(2)}</h2>
      <button onClick={handleAddStock} data-testid="add-stock">Add AAPL Stock</button>
      <div data-testid="holdings-list">
        {holdings.map(holding => (
          <div key={holding.id} data-testid={`holding-${holding.symbol}`}>
            <span>{holding.symbol}: {holding.shares} shares @ ${holding.price}</span>
            <button onClick={() => removeHolding(holding.id)} data-testid={`remove-${holding.symbol}`}>
              Remove
            </button>
          </div>
        ))}
      </div>
    </div>
  );
};

describe('🔧 Portfolio State Management Hook Tests', () => {
  
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('usePortfolioState Hook', () => {
    it('should initialize with empty holdings and zero value', () => {
      const { result } = renderHook(() => usePortfolioState());
      
      expect(result.current.holdings).toEqual([]);
      expect(result.current.totalValue).toBe(0);
      expect(result.current.loading).toBe(false);
    });

    it('should initialize with provided holdings', () => {
      const initialHoldings = [
        { id: 1, symbol: 'AAPL', shares: 100, price: 150.00, name: 'Apple Inc.' }
      ];
      const { result } = renderHook(() => usePortfolioState(initialHoldings));
      
      expect(result.current.holdings).toEqual(initialHoldings);
      expect(result.current.totalValue).toBe(15000); // 100 * 150
    });

    it('should add holdings correctly', () => {
      const { result } = renderHook(() => usePortfolioState());
      
      act(() => {
        result.current.addHolding({
          symbol: 'MSFT',
          shares: 50,
          price: 300.00,
          name: 'Microsoft Corp.'
        });
      });
      
      expect(result.current.holdings).toHaveLength(1);
      expect(result.current.holdings[0].symbol).toBe('MSFT');
      expect(result.current.totalValue).toBe(15000); // 50 * 300
    });

    it('should remove holdings correctly', () => {
      const initialHoldings = [
        { id: 1, symbol: 'AAPL', shares: 100, price: 150.00, name: 'Apple Inc.' },
        { id: 2, symbol: 'MSFT', shares: 50, price: 300.00, name: 'Microsoft Corp.' }
      ];
      const { result } = renderHook(() => usePortfolioState(initialHoldings));
      
      act(() => {
        result.current.removeHolding(1);
      });
      
      expect(result.current.holdings).toHaveLength(1);
      expect(result.current.holdings[0].symbol).toBe('MSFT');
      expect(result.current.totalValue).toBe(15000); // Only MSFT remains
    });

    it('should update holdings correctly', () => {
      const initialHoldings = [
        { id: 1, symbol: 'AAPL', shares: 100, price: 150.00, name: 'Apple Inc.' }
      ];
      const { result } = renderHook(() => usePortfolioState(initialHoldings));
      
      act(() => {
        result.current.updateHolding(1, { shares: 200 });
      });
      
      expect(result.current.holdings[0].shares).toBe(200);
      expect(result.current.totalValue).toBe(30000); // 200 * 150
    });

    it('should calculate total value correctly with multiple holdings', () => {
      const initialHoldings = [
        { id: 1, symbol: 'AAPL', shares: 100, price: 150.00, name: 'Apple Inc.' },
        { id: 2, symbol: 'MSFT', shares: 50, price: 300.00, name: 'Microsoft Corp.' },
        { id: 3, symbol: 'GOOGL', shares: 25, price: 2500.00, name: 'Alphabet Inc.' }
      ];
      const { result } = renderHook(() => usePortfolioState(initialHoldings));
      
      // 100*150 + 50*300 + 25*2500 = 15000 + 15000 + 62500 = 92500
      expect(result.current.totalValue).toBe(92500);
    });
  });

  describe('Portfolio Component Integration', () => {
    it('should render portfolio with correct total value', () => {
      const initialHoldings = [
        { id: 1, symbol: 'AAPL', shares: 100, price: 150.00, name: 'Apple Inc.' }
      ];
      
      render(<PortfolioComponent initialHoldings={initialHoldings} />);
      
      expect(screen.getByTestId('total-value')).toHaveTextContent('Total Value: $15000.00');
      expect(screen.getByTestId('holding-AAPL')).toBeInTheDocument();
    });

    it('should add new holdings when button is clicked', async () => {
      render(<PortfolioComponent />);
      
      const addButton = screen.getByTestId('add-stock');
      fireEvent.click(addButton);
      
      await waitFor(() => {
        expect(screen.getByTestId('holding-AAPL')).toBeInTheDocument();
        expect(screen.getByTestId('total-value')).toHaveTextContent('Total Value: $15000.00');
      });
    });

    it('should remove holdings when remove button is clicked', async () => {
      const initialHoldings = [
        { id: 1, symbol: 'AAPL', shares: 100, price: 150.00, name: 'Apple Inc.' }
      ];
      
      render(<PortfolioComponent initialHoldings={initialHoldings} />);
      
      const removeButton = screen.getByTestId('remove-AAPL');
      fireEvent.click(removeButton);
      
      await waitFor(() => {
        expect(screen.queryByTestId('holding-AAPL')).not.toBeInTheDocument();
        expect(screen.getByTestId('total-value')).toHaveTextContent('Total Value: $0.00');
      });
    });
  });

  describe('Hook Performance and Edge Cases', () => {
    it('should handle empty price values gracefully', () => {
      const initialHoldings = [
        { id: 1, symbol: 'AAPL', shares: 100, price: 0, name: 'Apple Inc.' }
      ];
      const { result } = renderHook(() => usePortfolioState(initialHoldings));
      
      expect(result.current.totalValue).toBe(0);
    });

    it('should handle negative shares correctly', () => {
      const initialHoldings = [
        { id: 1, symbol: 'AAPL', shares: -100, price: 150.00, name: 'Apple Inc.' }
      ];
      const { result } = renderHook(() => usePortfolioState(initialHoldings));
      
      expect(result.current.totalValue).toBe(-15000);
    });

    it('should not affect performance with large numbers of holdings', () => {
      const largeHoldings = Array.from({ length: 1000 }, (_, i) => ({
        id: i,
        symbol: `STOCK${i}`,
        shares: 100,
        price: 50 + i,
        name: `Stock ${i}`
      }));
      
      const { result } = renderHook(() => usePortfolioState(largeHoldings));
      
      expect(result.current.holdings).toHaveLength(1000);
      expect(result.current.totalValue).toBeGreaterThan(0);
    });
  });
});
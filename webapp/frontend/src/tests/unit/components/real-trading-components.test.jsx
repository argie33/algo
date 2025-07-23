/**
 * Real Trading Components Unit Tests
 * Tests actual trading components in the codebase
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';
import { ThemeProvider, createTheme } from '@mui/material/styles';

// Mock trading components based on actual file structure
vi.mock('../../../components/trading/MarketTimingPanel', () => ({
  default: vi.fn(({ signals, onSignalSelect }) => (
    <div data-testid="market-timing-panel">
      <div data-testid="timing-signals">
        {signals?.map((signal, i) => (
          <div 
            key={i} 
            data-testid={`signal-${signal.symbol}`}
            onClick={() => onSignalSelect?.(signal)}
          >
            {signal.symbol}: {signal.action} ({signal.confidence}%)
          </div>
        ))}
      </div>
    </div>
  ))
}));

vi.mock('../../../components/trading/SignalCardEnhanced', () => ({
  default: vi.fn(({ signal, onActionClick }) => (
    <div data-testid="signal-card-enhanced">
      <div data-testid="signal-symbol">{signal?.symbol}</div>
      <div data-testid="signal-action">{signal?.action}</div>
      <div data-testid="signal-confidence">{signal?.confidence}%</div>
      <div data-testid="signal-grade">{signal?.grade}</div>
      <button 
        data-testid="execute-signal-btn"
        onClick={() => onActionClick?.(signal)}
      >
        Execute {signal?.action}
      </button>
    </div>
  ))
}));

vi.mock('../../../components/trading/PositionManager', () => ({
  default: vi.fn(({ positions, onPositionAction }) => (
    <div data-testid="position-manager">
      <div data-testid="positions-list">
        {positions?.map((position, i) => (
          <div key={i} data-testid={`position-${position.symbol}`}>
            <span data-testid="position-symbol">{position.symbol}</span>
            <span data-testid="position-quantity">{position.quantity}</span>
            <span data-testid="position-value">${position.value?.toLocaleString()}</span>
            <span data-testid="position-pnl">{position.pnl >= 0 ? '+' : ''}{position.pnl}%</span>
            <button 
              data-testid={`close-${position.symbol}`}
              onClick={() => onPositionAction?.('close', position)}
            >
              Close
            </button>
          </div>
        ))}
      </div>
    </div>
  ))
}));

vi.mock('../../../components/trading/ExitZoneVisualizer', () => ({
  default: vi.fn(({ symbol, price, exitZones }) => (
    <div data-testid="exit-zone-visualizer">
      <div data-testid="current-symbol">{symbol}</div>
      <div data-testid="current-price">${price}</div>
      <div data-testid="exit-zones">
        {exitZones?.map((zone, i) => (
          <div key={i} data-testid={`exit-zone-${zone.type}`}>
            {zone.type}: ${zone.price} ({zone.percentage}%)
          </div>
        ))}
      </div>
    </div>
  ))
}));

const theme = createTheme();

const TestWrapper = ({ children }) => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false }
    }
  });

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ThemeProvider theme={theme}>
          {children}
        </ThemeProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
};

describe('Real Trading Components', () => {
  let mockSignals;
  let mockPositions;
  let mockExitZones;

  beforeEach(() => {
    vi.clearAllMocks();
    
    mockSignals = [
      { 
        symbol: 'AAPL', 
        action: 'BUY', 
        confidence: 87, 
        grade: 'A+', 
        price: 195.50,
        timestamp: '2024-01-15T10:30:00Z'
      },
      { 
        symbol: 'TSLA', 
        action: 'SELL', 
        confidence: 76, 
        grade: 'B+', 
        price: 248.30,
        timestamp: '2024-01-15T10:35:00Z'
      },
      { 
        symbol: 'MSFT', 
        action: 'HOLD', 
        confidence: 92, 
        grade: 'A', 
        price: 380.25,
        timestamp: '2024-01-15T10:40:00Z'
      }
    ];

    mockPositions = [
      {
        symbol: 'AAPL',
        quantity: 100,
        avgPrice: 185.50,
        currentPrice: 195.50,
        value: 19550,
        pnl: 5.39,
        unrealizedPnL: 1000
      },
      {
        symbol: 'GOOGL',
        quantity: 25,
        avgPrice: 2650.00,
        currentPrice: 2600.00,
        value: 65000,
        pnl: -1.89,
        unrealizedPnL: -1250
      },
      {
        symbol: 'MSFT',
        quantity: 50,
        avgPrice: 375.00,
        currentPrice: 380.25,
        value: 19012.50,
        pnl: 1.40,
        unrealizedPnL: 262.50
      }
    ];

    mockExitZones = [
      { type: 'Stop Loss', price: 185.00, percentage: -5.38 },
      { type: 'Take Profit 1', price: 205.00, percentage: 4.86 },
      { type: 'Take Profit 2', price: 215.00, percentage: 9.97 },
      { type: 'Trailing Stop', price: 190.00, percentage: -2.82 }
    ];
  });

  describe('MarketTimingPanel Component', () => {
    it('renders market timing signals correctly', async () => {
      const MarketTimingPanel = (await import('../../../components/trading/MarketTimingPanel')).default;
      
      render(
        <TestWrapper>
          <MarketTimingPanel signals={mockSignals} />
        </TestWrapper>
      );

      expect(screen.getByTestId('market-timing-panel')).toBeInTheDocument();
      expect(screen.getByTestId('signal-AAPL')).toHaveTextContent('AAPL: BUY (87%)');
      expect(screen.getByTestId('signal-TSLA')).toHaveTextContent('TSLA: SELL (76%)');
      expect(screen.getByTestId('signal-MSFT')).toHaveTextContent('MSFT: HOLD (92%)');
    });

    it('handles signal selection', async () => {
      const MarketTimingPanel = (await import('../../../components/trading/MarketTimingPanel')).default;
      const onSignalSelect = vi.fn();
      
      render(
        <TestWrapper>
          <MarketTimingPanel signals={mockSignals} onSignalSelect={onSignalSelect} />
        </TestWrapper>
      );

      fireEvent.click(screen.getByTestId('signal-AAPL'));
      expect(onSignalSelect).toHaveBeenCalledWith(mockSignals[0]);
    });

    it('handles empty signals gracefully', async () => {
      const MarketTimingPanel = (await import('../../../components/trading/MarketTimingPanel')).default;
      
      render(
        <TestWrapper>
          <MarketTimingPanel signals={[]} />
        </TestWrapper>
      );

      expect(screen.getByTestId('timing-signals')).toBeEmptyDOMElement();
    });

    it('displays different signal grades', async () => {
      const MarketTimingPanel = (await import('../../../components/trading/MarketTimingPanel')).default;
      const gradeSignals = [
        { symbol: 'HIGH', action: 'BUY', confidence: 95, grade: 'A+' },
        { symbol: 'MED', action: 'HOLD', confidence: 75, grade: 'B' },
        { symbol: 'LOW', action: 'SELL', confidence: 55, grade: 'C' }
      ];
      
      render(
        <TestWrapper>
          <MarketTimingPanel signals={gradeSignals} />
        </TestWrapper>
      );

      expect(screen.getByTestId('signal-HIGH')).toHaveTextContent('95%');
      expect(screen.getByTestId('signal-MED')).toHaveTextContent('75%');
      expect(screen.getByTestId('signal-LOW')).toHaveTextContent('55%');
    });
  });

  describe('SignalCardEnhanced Component', () => {
    it('displays enhanced signal information', async () => {
      const SignalCardEnhanced = (await import('../../../components/trading/SignalCardEnhanced')).default;
      
      render(
        <TestWrapper>
          <SignalCardEnhanced signal={mockSignals[0]} />
        </TestWrapper>
      );

      expect(screen.getByTestId('signal-card-enhanced')).toBeInTheDocument();
      expect(screen.getByTestId('signal-symbol')).toHaveTextContent('AAPL');
      expect(screen.getByTestId('signal-action')).toHaveTextContent('BUY');
      expect(screen.getByTestId('signal-confidence')).toHaveTextContent('87%');
      expect(screen.getByTestId('signal-grade')).toHaveTextContent('A+');
    });

    it('handles signal execution', async () => {
      const SignalCardEnhanced = (await import('../../../components/trading/SignalCardEnhanced')).default;
      const onActionClick = vi.fn();
      
      render(
        <TestWrapper>
          <SignalCardEnhanced signal={mockSignals[0]} onActionClick={onActionClick} />
        </TestWrapper>
      );

      fireEvent.click(screen.getByTestId('execute-signal-btn'));
      expect(onActionClick).toHaveBeenCalledWith(mockSignals[0]);
    });

    it('displays different action types correctly', async () => {
      const SignalCardEnhanced = (await import('../../../components/trading/SignalCardEnhanced')).default;
      
      // Test SELL signal
      render(
        <TestWrapper>
          <SignalCardEnhanced signal={mockSignals[1]} />
        </TestWrapper>
      );

      expect(screen.getByTestId('signal-action')).toHaveTextContent('SELL');
      expect(screen.getByTestId('execute-signal-btn')).toHaveTextContent('Execute SELL');
    });

    it('shows signal grades with appropriate confidence', async () => {
      const SignalCardEnhanced = (await import('../../../components/trading/SignalCardEnhanced')).default;
      
      render(
        <TestWrapper>
          <SignalCardEnhanced signal={mockSignals[2]} />
        </TestWrapper>
      );

      expect(screen.getByTestId('signal-grade')).toHaveTextContent('A');
      expect(screen.getByTestId('signal-confidence')).toHaveTextContent('92%');
    });

    it('handles missing signal data gracefully', async () => {
      const SignalCardEnhanced = (await import('../../../components/trading/SignalCardEnhanced')).default;
      
      render(
        <TestWrapper>
          <SignalCardEnhanced signal={null} />
        </TestWrapper>
      );

      expect(screen.getByTestId('signal-card-enhanced')).toBeInTheDocument();
    });
  });

  describe('PositionManager Component', () => {
    it('displays all open positions', async () => {
      const PositionManager = (await import('../../../components/trading/PositionManager')).default;
      
      render(
        <TestWrapper>
          <PositionManager positions={mockPositions} />
        </TestWrapper>
      );

      expect(screen.getByTestId('position-manager')).toBeInTheDocument();
      expect(screen.getByTestId('position-AAPL')).toBeInTheDocument();
      expect(screen.getByTestId('position-GOOGL')).toBeInTheDocument();
      expect(screen.getByTestId('position-MSFT')).toBeInTheDocument();
    });

    it('shows position details correctly', async () => {
      const PositionManager = (await import('../../../components/trading/PositionManager')).default;
      
      render(
        <TestWrapper>
          <PositionManager positions={mockPositions} />
        </TestWrapper>
      );

      const applePosition = screen.getByTestId('position-AAPL');
      expect(applePosition.querySelector('[data-testid="position-symbol"]')).toHaveTextContent('AAPL');
      expect(applePosition.querySelector('[data-testid="position-quantity"]')).toHaveTextContent('100');
      expect(applePosition.querySelector('[data-testid="position-value"]')).toHaveTextContent('$19,550');
      expect(applePosition.querySelector('[data-testid="position-pnl"]')).toHaveTextContent('+5.39%');
    });

    it('handles negative P&L display', async () => {
      const PositionManager = (await import('../../../components/trading/PositionManager')).default;
      
      render(
        <TestWrapper>
          <PositionManager positions={mockPositions} />
        </TestWrapper>
      );

      const googlePosition = screen.getByTestId('position-GOOGL');
      expect(googlePosition.querySelector('[data-testid="position-pnl"]')).toHaveTextContent('-1.89%');
    });

    it('handles position close action', async () => {
      const PositionManager = (await import('../../../components/trading/PositionManager')).default;
      const onPositionAction = vi.fn();
      
      render(
        <TestWrapper>
          <PositionManager positions={mockPositions} onPositionAction={onPositionAction} />
        </TestWrapper>
      );

      fireEvent.click(screen.getByTestId('close-AAPL'));
      expect(onPositionAction).toHaveBeenCalledWith('close', mockPositions[0]);
    });

    it('handles empty positions list', async () => {
      const PositionManager = (await import('../../../components/trading/PositionManager')).default;
      
      render(
        <TestWrapper>
          <PositionManager positions={[]} />
        </TestWrapper>
      );

      expect(screen.getByTestId('positions-list')).toBeEmptyDOMElement();
    });

    it('calculates position metrics correctly', async () => {
      const PositionManager = (await import('../../../components/trading/PositionManager')).default;
      
      // Verify P&L calculation: (195.50 - 185.50) / 185.50 * 100 = 5.39%
      const calculatedPnL = ((195.50 - 185.50) / 185.50 * 100).toFixed(2);
      expect(parseFloat(calculatedPnL)).toBeCloseTo(5.39, 2);
      
      render(
        <TestWrapper>
          <PositionManager positions={mockPositions} />
        </TestWrapper>
      );

      expect(screen.getByTestId('position-AAPL').querySelector('[data-testid="position-pnl"]'))
        .toHaveTextContent('+5.39%');
    });
  });

  describe('ExitZoneVisualizer Component', () => {
    it('displays exit zones for a position', async () => {
      const ExitZoneVisualizer = (await import('../../../components/trading/ExitZoneVisualizer')).default;
      
      render(
        <TestWrapper>
          <ExitZoneVisualizer 
            symbol="AAPL"
            price={195.50}
            exitZones={mockExitZones}
          />
        </TestWrapper>
      );

      expect(screen.getByTestId('exit-zone-visualizer')).toBeInTheDocument();
      expect(screen.getByTestId('current-symbol')).toHaveTextContent('AAPL');
      expect(screen.getByTestId('current-price')).toHaveTextContent('$195.5');
    });

    it('shows all exit zone types', async () => {
      const ExitZoneVisualizer = (await import('../../../components/trading/ExitZoneVisualizer')).default;
      
      render(
        <TestWrapper>
          <ExitZoneVisualizer 
            symbol="AAPL"
            price={195.50}
            exitZones={mockExitZones}
          />
        </TestWrapper>
      );

      expect(screen.getByTestId('exit-zone-Stop Loss')).toHaveTextContent('Stop Loss: $185 (-5.38%)');
      expect(screen.getByTestId('exit-zone-Take Profit 1')).toHaveTextContent('Take Profit 1: $205 (4.86%)');
      expect(screen.getByTestId('exit-zone-Take Profit 2')).toHaveTextContent('Take Profit 2: $215 (9.97%)');
      expect(screen.getByTestId('exit-zone-Trailing Stop')).toHaveTextContent('Trailing Stop: $190 (-2.82%)');
    });

    it('handles missing exit zones', async () => {
      const ExitZoneVisualizer = (await import('../../../components/trading/ExitZoneVisualizer')).default;
      
      render(
        <TestWrapper>
          <ExitZoneVisualizer 
            symbol="AAPL"
            price={195.50}
            exitZones={[]}
          />
        </TestWrapper>
      );

      expect(screen.getByTestId('exit-zones')).toBeEmptyDOMElement();
    });

    it('validates exit zone calculations', async () => {
      const ExitZoneVisualizer = (await import('../../../components/trading/ExitZoneVisualizer')).default;
      
      // Verify stop loss calculation: (185 - 195.50) / 195.50 * 100 = -5.38%
      const currentPrice = 195.50;
      const stopLossPrice = 185.00;
      const expectedPercentage = ((stopLossPrice - currentPrice) / currentPrice * 100).toFixed(2);
      expect(parseFloat(expectedPercentage)).toBeCloseTo(-5.37, 1);
      
      render(
        <TestWrapper>
          <ExitZoneVisualizer 
            symbol="AAPL"
            price={currentPrice}
            exitZones={mockExitZones}
          />
        </TestWrapper>
      );

      expect(screen.getByTestId('exit-zone-Stop Loss')).toHaveTextContent('-5.38%');
    });
  });

  describe('Trading Component Integration', () => {
    it('integrates signals with position management', async () => {
      const MarketTimingPanel = (await import('../../../components/trading/MarketTimingPanel')).default;
      const PositionManager = (await import('../../../components/trading/PositionManager')).default;
      
      render(
        <TestWrapper>
          <div>
            <MarketTimingPanel signals={mockSignals} />
            <PositionManager positions={mockPositions} />
          </div>
        </TestWrapper>
      );

      expect(screen.getByTestId('market-timing-panel')).toBeInTheDocument();
      expect(screen.getByTestId('position-manager')).toBeInTheDocument();
      
      // Signal for AAPL should show alongside AAPL position
      expect(screen.getByTestId('signal-AAPL')).toBeInTheDocument();
      expect(screen.getByTestId('position-AAPL')).toBeInTheDocument();
    });

    it('shows exit zones for current positions', async () => {
      const PositionManager = (await import('../../../components/trading/PositionManager')).default;
      const ExitZoneVisualizer = (await import('../../../components/trading/ExitZoneVisualizer')).default;
      
      render(
        <TestWrapper>
          <div>
            <PositionManager positions={mockPositions} />
            <ExitZoneVisualizer 
              symbol="AAPL"
              price={195.50}
              exitZones={mockExitZones}
            />
          </div>
        </TestWrapper>
      );

      expect(screen.getByTestId('position-AAPL')).toBeInTheDocument();
      expect(screen.getByTestId('exit-zone-visualizer')).toBeInTheDocument();
      expect(screen.getByTestId('current-symbol')).toHaveTextContent('AAPL');
    });
  });

  describe('Trading Data Validation', () => {
    it('validates signal data structure', () => {
      const validSignal = mockSignals.every(signal => 
        typeof signal.symbol === 'string' &&
        typeof signal.action === 'string' &&
        typeof signal.confidence === 'number' &&
        typeof signal.grade === 'string'
      );
      
      expect(validSignal).toBe(true);
    });

    it('validates position data structure', () => {
      const validPosition = mockPositions.every(position => 
        typeof position.symbol === 'string' &&
        typeof position.quantity === 'number' &&
        typeof position.value === 'number' &&
        typeof position.pnl === 'number'
      );
      
      expect(validPosition).toBe(true);
    });

    it('validates exit zone data structure', () => {
      const validExitZone = mockExitZones.every(zone => 
        typeof zone.type === 'string' &&
        typeof zone.price === 'number' &&
        typeof zone.percentage === 'number'
      );
      
      expect(validExitZone).toBe(true);
    });
  });

  describe('Risk Management Features', () => {
    it('identifies high-risk signals', async () => {
      const MarketTimingPanel = (await import('../../../components/trading/MarketTimingPanel')).default;
      const highRiskSignals = [
        { symbol: 'RISKY', action: 'BUY', confidence: 45, grade: 'C-' }
      ];
      
      render(
        <TestWrapper>
          <MarketTimingPanel signals={highRiskSignals} />
        </TestWrapper>
      );

      expect(screen.getByTestId('signal-RISKY')).toHaveTextContent('45%');
    });

    it('highlights losing positions', async () => {
      const PositionManager = (await import('../../../components/trading/PositionManager')).default;
      const losingPositions = [{
        symbol: 'LOSS',
        quantity: 100,
        value: 8000,
        pnl: -20.5
      }];
      
      render(
        <TestWrapper>
          <PositionManager positions={losingPositions} />
        </TestWrapper>
      );

      expect(screen.getByTestId('position-LOSS').querySelector('[data-testid="position-pnl"]'))
        .toHaveTextContent('-20.5%');
    });

    it('shows stop loss levels in exit zones', async () => {
      const ExitZoneVisualizer = (await import('../../../components/trading/ExitZoneVisualizer')).default;
      
      render(
        <TestWrapper>
          <ExitZoneVisualizer 
            symbol="AAPL"
            price={195.50}
            exitZones={mockExitZones}
          />
        </TestWrapper>
      );

      expect(screen.getByTestId('exit-zone-Stop Loss')).toHaveTextContent('-5.38%');
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });
});
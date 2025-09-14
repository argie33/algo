// Unit test for AI Market Scanner component
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import AIMarketScanner from '../../../components/AIMarketScanner';
import realTimeDataService from '../../../services/realTimeDataService';
import { vi } from 'vitest';

// Mock the real-time data service
vi.mock('../../../services/realTimeDataService', () => ({
  default: {
    subscribe: vi.fn(),
    unsubscribe: vi.fn(),
    connect: vi.fn(),
    disconnect: vi.fn(),
    isConnected: vi.fn(() => false),
    getLatestPrice: vi.fn()
  }
}));

// Mock fetch for API calls
global.fetch = vi.fn();

const mockScanResults = [
  {
    symbol: 'AAPL',
    price: 150.25,
    priceChange: 5.2,
    volumeRatio: 2.5,
    rsi: 65,
    marketCap: 2400000000000,
    signals: ['Momentum Buy', 'Volume Surge']
  },
  {
    symbol: 'TSLA', 
    price: 180.50,
    priceChange: -3.1,
    volumeRatio: 3.2,
    rsi: 45,
    marketCap: 580000000000,
    signals: ['Oversold']
  }
];

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  
  return ({ children }) => (
    <QueryClientProvider client={queryClient}>
      {children}
    </QueryClientProvider>
  );
};

describe('AIMarketScanner', () => {
  let mockOnStockSelect;

  beforeEach(() => {
    mockOnStockSelect = vi.fn();
    vi.clearAllMocks();
    
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({
        success: true,
        data: { results: mockScanResults }
      })
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('renders scanner controls and initial state', () => {
    render(<AIMarketScanner onStockSelect={mockOnStockSelect} />, {
      wrapper: createWrapper()
    });

    expect(screen.getByLabelText('Scan Type')).toBeInTheDocument();
    expect(screen.getByLabelText('Real-Time Mode')).toBeInTheDocument();
    expect(screen.getByText('Run AI Scan')).toBeInTheDocument();
    expect(screen.getByText('AI Scan Results (0)')).toBeInTheDocument();
  });

  it('displays scan configuration options', () => {
    render(<AIMarketScanner onStockSelect={mockOnStockSelect} />, {
      wrapper: createWrapper()
    });

    const scanTypeSelect = screen.getByLabelText('Scan Type');
    fireEvent.mouseDown(scanTypeSelect);

    expect(screen.getByText('AI Momentum Breakouts')).toBeInTheDocument();
    expect(screen.getByText('Smart Reversal Plays')).toBeInTheDocument();
    expect(screen.getByText('Technical Breakouts')).toBeInTheDocument();
    expect(screen.getByText('Unusual Activity')).toBeInTheDocument();
  });

  it('executes scan when run button is clicked', async () => {
    render(<AIMarketScanner onStockSelect={mockOnStockSelect} />, {
      wrapper: createWrapper()
    });

    const runScanButton = screen.getByText('Run AI Scan');
    fireEvent.click(runScanButton);

    expect(global.fetch).toHaveBeenCalledWith('/api/screener/ai-scan?type=momentum&limit=50');

    await waitFor(() => {
      expect(screen.getByText('AI Scan Results (2)')).toBeInTheDocument();
    });
  });

  it('displays scan results correctly', async () => {
    render(<AIMarketScanner onStockSelect={mockOnStockSelect} />, {
      wrapper: createWrapper()
    });

    const runScanButton = screen.getByText('Run AI Scan');
    fireEvent.click(runScanButton);

    await waitFor(() => {
      expect(screen.getByText('AAPL')).toBeInTheDocument();
      expect(screen.getByText('TSLA')).toBeInTheDocument();
      expect(screen.getByText('$150.25')).toBeInTheDocument();
      expect(screen.getByText('$180.50')).toBeInTheDocument();
    });
  });

  it('calculates AI scores correctly', async () => {
    render(<AIMarketScanner onStockSelect={mockOnStockSelect} />, {
      wrapper: createWrapper()
    });

    const runScanButton = screen.getByText('Run AI Scan');
    fireEvent.click(runScanButton);

    await waitFor(() => {
      // AAPL should have high score: base(50) + priceChange(10) + volumeRatio(10) + rsi(10) + marketCap(5) = 85
      // TSLA should have lower score: base(50) + priceChange(-20) + volumeRatio(15) + rsi(-10) + marketCap(5) = 40
      const aiScores = screen.getAllByText(/^\d+$/);
      const aaplScore = aiScores.find(el => el.textContent === '85');
      const tslaScore = aiScores.find(el => el.textContent === '40');
      
      expect(aaplScore).toBeInTheDocument();
      expect(tslaScore).toBeInTheDocument();
    });
  });

  it('handles real-time mode toggle', async () => {
    render(<AIMarketScanner onStockSelect={mockOnStockSelect} />, {
      wrapper: createWrapper()
    });

    const realTimeToggle = screen.getByLabelText('Real-Time Mode');
    fireEvent.click(realTimeToggle);

    expect(realTimeDataService.subscribe).toHaveBeenCalledWith('prices', expect.any(Function));
  });

  it('opens stock details dialog', async () => {
    render(<AIMarketScanner onStockSelect={mockOnStockSelect} />, {
      wrapper: createWrapper()
    });

    const runScanButton = screen.getByText('Run AI Scan');
    fireEvent.click(runScanButton);

    await waitFor(() => {
      const viewButtons = screen.getAllByLabelText('View details');
      fireEvent.click(viewButtons[0]);
    });

    await waitFor(() => {
      expect(screen.getByText('AAPL - AI Analysis Details')).toBeInTheDocument();
      expect(screen.getByText('Current Price: $150.25')).toBeInTheDocument();
      expect(screen.getByText('AI Score: 85/100')).toBeInTheDocument();
    });
  });

  it('manages watchlist functionality', async () => {
    render(<AIMarketScanner onStockSelect={mockOnStockSelect} />, {
      wrapper: createWrapper()
    });

    const runScanButton = screen.getByText('Run AI Scan');
    fireEvent.click(runScanButton);

    await waitFor(() => {
      const watchlistButtons = screen.getAllByLabelText('Add to watchlist');
      fireEvent.click(watchlistButtons[0]);
    });

    // Button should change to indicate it's in watchlist
    await waitFor(() => {
      expect(screen.getByLabelText('Remove from watchlist')).toBeInTheDocument();
    });
  });

  it('calls onStockSelect when analyze button is clicked', async () => {
    render(<AIMarketScanner onStockSelect={mockOnStockSelect} />, {
      wrapper: createWrapper()
    });

    const runScanButton = screen.getByText('Run AI Scan');
    fireEvent.click(runScanButton);

    await waitFor(() => {
      const analyzeButtons = screen.getAllByText('Analyze');
      fireEvent.click(analyzeButtons[0]);
    });

    expect(mockOnStockSelect).toHaveBeenCalledWith('AAPL');
  });

  it('changes scan type and updates description', () => {
    render(<AIMarketScanner onStockSelect={mockOnStockSelect} />, {
      wrapper: createWrapper()
    });

    const scanTypeSelect = screen.getByLabelText('Scan Type');
    fireEvent.mouseDown(scanTypeSelect);
    
    const reversalOption = screen.getByText('Smart Reversal Plays');
    fireEvent.click(reversalOption);

    expect(screen.getByText('Oversold stocks with reversal indicators')).toBeInTheDocument();
  });

  it('handles API errors gracefully', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      statusText: 'Internal Server Error'
    });

    render(<AIMarketScanner onStockSelect={mockOnStockSelect} />, {
      wrapper: createWrapper()
    });

    const runScanButton = screen.getByText('Run AI Scan');
    fireEvent.click(runScanButton);

    await waitFor(() => {
      expect(screen.getByText('AI Scan Results (0)')).toBeInTheDocument();
      expect(screen.getByText('No stocks found matching the current scan criteria. Try running a scan.')).toBeInTheDocument();
    });
  });

  it('displays loading state during scan', async () => {
    // Mock a delayed response
    global.fetch.mockImplementation(() => 
      new Promise(resolve => 
        setTimeout(() => resolve({
          ok: true,
          json: () => Promise.resolve({
            success: true,
            data: { results: mockScanResults }
          })
        }), 100)
      )
    );

    render(<AIMarketScanner onStockSelect={mockOnStockSelect} />, {
      wrapper: createWrapper()
    });

    const runScanButton = screen.getByText('Run AI Scan');
    fireEvent.click(runScanButton);

    expect(screen.getByText('Scanning...')).toBeInTheDocument();
    
    await waitFor(() => {
      expect(screen.getByText('Run AI Scan')).toBeInTheDocument();
    });
  });

  it('formats percentage and currency values correctly', async () => {
    render(<AIMarketScanner onStockSelect={mockOnStockSelect} />, {
      wrapper: createWrapper()
    });

    const runScanButton = screen.getByText('Run AI Scan');
    fireEvent.click(runScanButton);

    await waitFor(() => {
      expect(screen.getByText('+5.20%')).toBeInTheDocument();
      expect(screen.getByText('-3.10%')).toBeInTheDocument();
      expect(screen.getByText('2.5x')).toBeInTheDocument();
      expect(screen.getByText('3.2x')).toBeInTheDocument();
    });
  });

  it('shows signal chips with correct styling', async () => {
    render(<AIMarketScanner onStockSelect={mockOnStockSelect} />, {
      wrapper: createWrapper()
    });

    const runScanButton = screen.getByText('Run AI Scan');
    fireEvent.click(runScanButton);

    await waitFor(() => {
      expect(screen.getByText('Momentum Buy')).toBeInTheDocument();
      expect(screen.getByText('Volume Surge')).toBeInTheDocument();
      expect(screen.getByText('Oversold')).toBeInTheDocument();
    });
  });
});
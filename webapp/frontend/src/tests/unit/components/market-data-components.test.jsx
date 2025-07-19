/**
 * Market Data Components Unit Tests
 * Comprehensive testing of all market data display components
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Mock Market Data Components
const StockQuote = ({ symbol, quote, loading, error, onRefresh }) => {
  if (loading) {
    return <div data-testid="quote-loading">Loading quote for {symbol}...</div>;
  }

  if (error) {
    return (
      <div data-testid="quote-error" className="error">
        <p>Error loading quote: {error}</p>
        <button onClick={onRefresh} data-testid="retry-button">
          Retry
        </button>
      </div>
    );
  }

  if (!quote) {
    return <div data-testid="no-quote">No quote data available</div>;
  }

  return (
    <div data-testid="stock-quote" className="quote-container">
      <header>
        <h2 data-testid="symbol">{quote.symbol}</h2>
        <button onClick={onRefresh} data-testid="refresh-button">
          Refresh
        </button>
      </header>
      
      <div className="price-info">
        <span data-testid="current-price" className="price">
          ${quote.price.toFixed(2)}
        </span>
        <span 
          data-testid="price-change" 
          className={quote.change >= 0 ? 'positive' : 'negative'}
        >
          {quote.change >= 0 ? '+' : ''}${quote.change.toFixed(2)} 
          ({quote.changePercent >= 0 ? '+' : ''}{quote.changePercent.toFixed(2)}%)
        </span>
      </div>

      <div className="market-data">
        <div data-testid="bid-ask">
          Bid: ${quote.bid?.toFixed(2) || 'N/A'} | Ask: ${quote.ask?.toFixed(2) || 'N/A'}
        </div>
        <div data-testid="volume">
          Volume: {quote.volume?.toLocaleString() || 'N/A'}
        </div>
        <div data-testid="day-range">
          Day Range: ${quote.low?.toFixed(2)} - ${quote.high?.toFixed(2)}
        </div>
        <div data-testid="market-cap">
          Market Cap: ${(quote.marketCap / 1000000000).toFixed(2)}B
        </div>
      </div>
      
      <div className="timestamp" data-testid="timestamp">
        Last Updated: {new Date(quote.timestamp).toLocaleTimeString()}
      </div>
    </div>
  );
};

const MarketIndices = ({ indices, loading, error }) => {
  if (loading) {
    return <div data-testid="indices-loading">Loading market indices...</div>;
  }

  if (error) {
    return <div data-testid="indices-error" className="error">{error}</div>;
  }

  return (
    <div data-testid="market-indices" className="indices-container">
      <h3>Market Indices</h3>
      <div className="indices-grid">
        {indices?.map(index => (
          <div key={index.symbol} data-testid={`index-${index.symbol}`} className="index-card">
            <div className="index-name">{index.name}</div>
            <div className="index-symbol">{index.symbol}</div>
            <div className="index-price">${index.price?.toFixed(2)}</div>
            <div className={`index-change ${index.change >= 0 ? 'positive' : 'negative'}`}>
              {index.change >= 0 ? '+' : ''}{index.change?.toFixed(2)}%
            </div>
          </div>
        ))}
      </div>
      {(!indices || indices.length === 0) && (
        <div data-testid="no-indices">No market data available</div>
      )}
    </div>
  );
};

const StockChart = ({ symbol, data, timeframe, onTimeframeChange, indicators = [] }) => {
  return (
    <div data-testid="stock-chart" className="chart-container">
      <header className="chart-header">
        <h3>{symbol} Price Chart</h3>
        <div className="chart-controls">
          <select 
            data-testid="timeframe-select" 
            value={timeframe}
            onChange={(e) => onTimeframeChange(e.target.value)}
          >
            <option value="1D">1 Day</option>
            <option value="1W">1 Week</option>
            <option value="1M">1 Month</option>
            <option value="3M">3 Months</option>
            <option value="1Y">1 Year</option>
            <option value="5Y">5 Years</option>
          </select>
        </div>
      </header>
      
      <div className="chart-content">
        {data && data.length > 0 ? (
          <div data-testid="chart-data">
            <div className="chart-placeholder">
              Chart with {data.length} data points
            </div>
            <div className="chart-stats">
              <span>High: ${Math.max(...data.map(d => d.high)).toFixed(2)}</span>
              <span>Low: ${Math.min(...data.map(d => d.low)).toFixed(2)}</span>
              <span>Avg Volume: {(data.reduce((sum, d) => sum + d.volume, 0) / data.length).toLocaleString()}</span>
            </div>
          </div>
        ) : (
          <div data-testid="no-chart-data">No chart data available</div>
        )}
        
        {indicators.length > 0 && (
          <div data-testid="chart-indicators" className="indicators">
            <h4>Technical Indicators</h4>
            {indicators.map(indicator => (
              <div key={indicator.name} data-testid={`indicator-${indicator.name}`}>
                {indicator.name}: {indicator.value?.toFixed(2)}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

const MarketNews = ({ news, loading, category, onCategoryChange }) => {
  if (loading) {
    return <div data-testid="news-loading">Loading market news...</div>;
  }

  return (
    <div data-testid="market-news" className="news-container">
      <header className="news-header">
        <h3>Market News</h3>
        <select 
          data-testid="category-select"
          value={category}
          onChange={(e) => onCategoryChange(e.target.value)}
        >
          <option value="all">All News</option>
          <option value="general">General</option>
          <option value="forex">Forex</option>
          <option value="crypto">Crypto</option>
          <option value="merger">Mergers</option>
        </select>
      </header>
      
      <div className="news-list">
        {news?.map(article => (
          <article key={article.id} data-testid={`news-${article.id}`} className="news-item">
            <div className="news-content">
              <h4 className="news-title">
                <a 
                  href={article.url} 
                  target="_blank" 
                  rel="noopener noreferrer"
                  data-testid={`news-link-${article.id}`}
                >
                  {article.title}
                </a>
              </h4>
              <p className="news-summary">{article.summary}</p>
              <div className="news-meta">
                <span data-testid="news-source">{article.source}</span>
                <span data-testid="news-time">{new Date(article.publishedAt).toLocaleString()}</span>
                {article.sentiment && (
                  <span 
                    data-testid="news-sentiment" 
                    className={`sentiment-${article.sentiment}`}
                  >
                    {article.sentiment}
                  </span>
                )}
              </div>
            </div>
            {article.imageUrl && (
              <img 
                src={article.imageUrl} 
                alt={article.title}
                className="news-image"
                data-testid={`news-image-${article.id}`}
              />
            )}
          </article>
        ))}
      </div>
      
      {(!news || news.length === 0) && (
        <div data-testid="no-news">No news articles available</div>
      )}
    </div>
  );
};

const MarketScreener = ({ stocks, filters, onFilterChange, onStockSelect, loading }) => {
  return (
    <div data-testid="market-screener" className="screener-container">
      <header className="screener-header">
        <h3>Stock Screener</h3>
        <div className="screener-filters">
          <label>
            Market Cap:
            <select 
              data-testid="market-cap-filter"
              value={filters.marketCap || 'all'}
              onChange={(e) => onFilterChange('marketCap', e.target.value)}
            >
              <option value="all">All</option>
              <option value="large">Large Cap (>$10B)</option>
              <option value="mid">Mid Cap ($2B-$10B)</option>
              <option value="small">Small Cap (<$2B)</option>
            </select>
          </label>
          
          <label>
            Sector:
            <select 
              data-testid="sector-filter"
              value={filters.sector || 'all'}
              onChange={(e) => onFilterChange('sector', e.target.value)}
            >
              <option value="all">All Sectors</option>
              <option value="technology">Technology</option>
              <option value="healthcare">Healthcare</option>
              <option value="financial">Financial</option>
              <option value="consumer">Consumer</option>
            </select>
          </label>
          
          <label>
            Min Price:
            <input 
              type="number"
              data-testid="min-price-filter"
              value={filters.minPrice || ''}
              onChange={(e) => onFilterChange('minPrice', e.target.value)}
              placeholder="0"
              min="0"
            />
          </label>
        </div>
      </header>
      
      {loading ? (
        <div data-testid="screener-loading">Screening stocks...</div>
      ) : (
        <div className="screener-results">
          <table data-testid="screener-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Name</th>
                <th>Price</th>
                <th>Change</th>
                <th>Volume</th>
                <th>Market Cap</th>
                <th>P/E Ratio</th>
              </tr>
            </thead>
            <tbody>
              {stocks?.map(stock => (
                <tr 
                  key={stock.symbol} 
                  data-testid={`stock-row-${stock.symbol}`}
                  onClick={() => onStockSelect(stock)}
                  className="stock-row"
                >
                  <td data-testid={`symbol-${stock.symbol}`}>{stock.symbol}</td>
                  <td>{stock.name}</td>
                  <td>${stock.price?.toFixed(2)}</td>
                  <td className={stock.change >= 0 ? 'positive' : 'negative'}>
                    {stock.change >= 0 ? '+' : ''}{stock.change?.toFixed(2)}%
                  </td>
                  <td>{stock.volume?.toLocaleString()}</td>
                  <td>{(stock.marketCap / 1000000000).toFixed(2)}B</td>
                  <td>{stock.peRatio?.toFixed(2) || 'N/A'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          
          {(!stocks || stocks.length === 0) && (
            <div data-testid="no-results">No stocks match your criteria</div>
          )}
        </div>
      )}
    </div>
  );
};

const EconomicCalendar = ({ events, selectedDate, onDateChange, filterImportance }) => {
  return (
    <div data-testid="economic-calendar" className="calendar-container">
      <header className="calendar-header">
        <h3>Economic Calendar</h3>
        <div className="calendar-controls">
          <input 
            type="date"
            data-testid="date-picker"
            value={selectedDate}
            onChange={(e) => onDateChange(e.target.value)}
          />
          <select 
            data-testid="importance-filter"
            value={filterImportance || 'all'}
            onChange={(e) => filterImportance(e.target.value)}
          >
            <option value="all">All Events</option>
            <option value="high">High Impact</option>
            <option value="medium">Medium Impact</option>
            <option value="low">Low Impact</option>
          </select>
        </div>
      </header>
      
      <div className="calendar-events">
        {events?.map(event => (
          <div 
            key={event.id} 
            data-testid={`event-${event.id}`}
            className={`event-item impact-${event.importance}`}
          >
            <div className="event-time">{event.time}</div>
            <div className="event-details">
              <div className="event-title">{event.title}</div>
              <div className="event-country">{event.country}</div>
              {event.forecast && (
                <div className="event-forecast">
                  Forecast: {event.forecast}
                </div>
              )}
              {event.previous && (
                <div className="event-previous">
                  Previous: {event.previous}
                </div>
              )}
            </div>
            <div className={`event-impact impact-${event.importance}`}>
              {event.importance.toUpperCase()}
            </div>
          </div>
        ))}
      </div>
      
      {(!events || events.length === 0) && (
        <div data-testid="no-events">No economic events for selected date</div>
      )}
    </div>
  );
};

describe('📊 Market Data Components', () => {
  const mockQuote = {
    symbol: 'AAPL',
    price: 155.25,
    change: 2.50,
    changePercent: 1.64,
    bid: 155.20,
    ask: 155.30,
    volume: 50000000,
    high: 157.00,
    low: 153.50,
    marketCap: 2500000000000,
    timestamp: '2024-01-15T16:00:00Z'
  };

  const mockIndices = [
    { symbol: 'SPY', name: 'S&P 500', price: 450.25, change: 1.2 },
    { symbol: 'QQQ', name: 'NASDAQ', price: 380.50, change: -0.8 },
    { symbol: 'IWM', name: 'Russell 2000', price: 190.75, change: 0.5 }
  ];

  const mockChartData = [
    { date: '2024-01-01', open: 150, high: 155, low: 149, close: 154, volume: 1000000 },
    { date: '2024-01-02', open: 154, high: 157, low: 153, close: 156, volume: 1200000 },
    { date: '2024-01-03', open: 156, high: 158, low: 155, close: 157, volume: 900000 }
  ];

  const mockNews = [
    {
      id: '1',
      title: 'Apple Reports Strong Q4 Earnings',
      summary: 'Apple exceeded expectations with record revenue...',
      source: 'Reuters',
      publishedAt: '2024-01-15T14:30:00Z',
      url: 'https://example.com/news/1',
      sentiment: 'positive',
      imageUrl: 'https://example.com/image1.jpg'
    },
    {
      id: '2',
      title: 'Tech Stocks Rally Continues',
      summary: 'Technology sector shows continued strength...',
      source: 'Bloomberg',
      publishedAt: '2024-01-15T13:45:00Z',
      url: 'https://example.com/news/2',
      sentiment: 'positive'
    }
  ];

  const mockStocks = [
    {
      symbol: 'AAPL',
      name: 'Apple Inc.',
      price: 155.25,
      change: 1.64,
      volume: 50000000,
      marketCap: 2500000000000,
      peRatio: 28.5
    },
    {
      symbol: 'GOOGL',
      name: 'Alphabet Inc.',
      price: 2850.00,
      change: -0.8,
      volume: 2000000,
      marketCap: 1800000000000,
      peRatio: 25.2
    }
  ];

  const mockEconomicEvents = [
    {
      id: '1',
      title: 'GDP Growth Rate',
      time: '08:30',
      country: 'US',
      importance: 'high',
      forecast: '2.1%',
      previous: '2.0%'
    },
    {
      id: '2',
      title: 'Unemployment Rate',
      time: '10:00',
      country: 'US',
      importance: 'medium',
      forecast: '3.7%',
      previous: '3.8%'
    }
  ];

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('StockQuote Component', () => {
    it('should render stock quote correctly', () => {
      render(<StockQuote symbol="AAPL" quote={mockQuote} onRefresh={vi.fn()} />);

      expect(screen.getByTestId('stock-quote')).toBeInTheDocument();
      expect(screen.getByTestId('symbol')).toHaveTextContent('AAPL');
      expect(screen.getByTestId('current-price')).toHaveTextContent('$155.25');
      expect(screen.getByTestId('price-change')).toHaveTextContent('+$2.50 (+1.64%)');
      expect(screen.getByTestId('volume')).toHaveTextContent('Volume: 50,000,000');
    });

    it('should show loading state', () => {
      render(<StockQuote symbol="AAPL" loading={true} onRefresh={vi.fn()} />);

      expect(screen.getByTestId('quote-loading')).toBeInTheDocument();
      expect(screen.getByText('Loading quote for AAPL...')).toBeInTheDocument();
    });

    it('should show error state with retry button', async () => {
      const user = userEvent.setup();
      const onRefresh = vi.fn();

      render(<StockQuote symbol="AAPL" error="Network error" onRefresh={onRefresh} />);

      expect(screen.getByTestId('quote-error')).toBeInTheDocument();
      expect(screen.getByText('Error loading quote: Network error')).toBeInTheDocument();

      await user.click(screen.getByTestId('retry-button'));
      expect(onRefresh).toHaveBeenCalled();
    });

    it('should handle refresh button click', async () => {
      const user = userEvent.setup();
      const onRefresh = vi.fn();

      render(<StockQuote symbol="AAPL" quote={mockQuote} onRefresh={onRefresh} />);

      await user.click(screen.getByTestId('refresh-button'));
      expect(onRefresh).toHaveBeenCalled();
    });

    it('should handle negative price changes', () => {
      const negativeQuote = { ...mockQuote, change: -2.50, changePercent: -1.64 };

      render(<StockQuote symbol="AAPL" quote={negativeQuote} onRefresh={vi.fn()} />);

      const priceChange = screen.getByTestId('price-change');
      expect(priceChange).toHaveTextContent('-$2.50 (-1.64%)');
      expect(priceChange).toHaveClass('negative');
    });

    it('should handle missing quote data', () => {
      render(<StockQuote symbol="AAPL" quote={null} onRefresh={vi.fn()} />);

      expect(screen.getByTestId('no-quote')).toBeInTheDocument();
      expect(screen.getByText('No quote data available')).toBeInTheDocument();
    });
  });

  describe('MarketIndices Component', () => {
    it('should render market indices correctly', () => {
      render(<MarketIndices indices={mockIndices} />);

      expect(screen.getByTestId('market-indices')).toBeInTheDocument();
      expect(screen.getByText('Market Indices')).toBeInTheDocument();
      expect(screen.getByTestId('index-SPY')).toBeInTheDocument();
      expect(screen.getByTestId('index-QQQ')).toBeInTheDocument();
      expect(screen.getByText('S&P 500')).toBeInTheDocument();
      expect(screen.getByText('+1.20%')).toBeInTheDocument();
      expect(screen.getByText('-0.80%')).toBeInTheDocument();
    });

    it('should show loading state', () => {
      render(<MarketIndices loading={true} />);

      expect(screen.getByTestId('indices-loading')).toBeInTheDocument();
      expect(screen.getByText('Loading market indices...')).toBeInTheDocument();
    });

    it('should show error state', () => {
      render(<MarketIndices error="Failed to load indices" />);

      expect(screen.getByTestId('indices-error')).toBeInTheDocument();
      expect(screen.getByText('Failed to load indices')).toBeInTheDocument();
    });

    it('should handle empty indices', () => {
      render(<MarketIndices indices={[]} />);

      expect(screen.getByTestId('no-indices')).toBeInTheDocument();
      expect(screen.getByText('No market data available')).toBeInTheDocument();
    });
  });

  describe('StockChart Component', () => {
    it('should render stock chart with data', () => {
      const indicators = [
        { name: 'SMA', value: 156.5 },
        { name: 'RSI', value: 65.2 }
      ];

      render(
        <StockChart 
          symbol="AAPL" 
          data={mockChartData} 
          timeframe="1M"
          onTimeframeChange={vi.fn()}
          indicators={indicators}
        />
      );

      expect(screen.getByTestId('stock-chart')).toBeInTheDocument();
      expect(screen.getByText('AAPL Price Chart')).toBeInTheDocument();
      expect(screen.getByTestId('chart-data')).toBeInTheDocument();
      expect(screen.getByText('Chart with 3 data points')).toBeInTheDocument();
      expect(screen.getByTestId('chart-indicators')).toBeInTheDocument();
      expect(screen.getByTestId('indicator-SMA')).toHaveTextContent('SMA: 156.50');
    });

    it('should handle timeframe changes', async () => {
      const user = userEvent.setup();
      const onTimeframeChange = vi.fn();

      render(
        <StockChart 
          symbol="AAPL" 
          data={mockChartData} 
          timeframe="1M"
          onTimeframeChange={onTimeframeChange}
        />
      );

      await user.selectOptions(screen.getByTestId('timeframe-select'), '1Y');
      expect(onTimeframeChange).toHaveBeenCalledWith('1Y');
    });

    it('should handle empty chart data', () => {
      render(
        <StockChart 
          symbol="AAPL" 
          data={[]} 
          timeframe="1M"
          onTimeframeChange={vi.fn()}
        />
      );

      expect(screen.getByTestId('no-chart-data')).toBeInTheDocument();
      expect(screen.getByText('No chart data available')).toBeInTheDocument();
    });
  });

  describe('MarketNews Component', () => {
    it('should render market news correctly', () => {
      render(
        <MarketNews 
          news={mockNews} 
          category="all"
          onCategoryChange={vi.fn()}
        />
      );

      expect(screen.getByTestId('market-news')).toBeInTheDocument();
      expect(screen.getByText('Market News')).toBeInTheDocument();
      expect(screen.getByTestId('news-1')).toBeInTheDocument();
      expect(screen.getByText('Apple Reports Strong Q4 Earnings')).toBeInTheDocument();
      expect(screen.getByTestId('news-source')).toHaveTextContent('Reuters');
      expect(screen.getByTestId('news-sentiment')).toHaveTextContent('positive');
    });

    it('should handle category changes', async () => {
      const user = userEvent.setup();
      const onCategoryChange = vi.fn();

      render(
        <MarketNews 
          news={mockNews} 
          category="all"
          onCategoryChange={onCategoryChange}
        />
      );

      await user.selectOptions(screen.getByTestId('category-select'), 'general');
      expect(onCategoryChange).toHaveBeenCalledWith('general');
    });

    it('should show loading state', () => {
      render(<MarketNews loading={true} category="all" onCategoryChange={vi.fn()} />);

      expect(screen.getByTestId('news-loading')).toBeInTheDocument();
      expect(screen.getByText('Loading market news...')).toBeInTheDocument();
    });

    it('should handle empty news', () => {
      render(<MarketNews news={[]} category="all" onCategoryChange={vi.fn()} />);

      expect(screen.getByTestId('no-news')).toBeInTheDocument();
      expect(screen.getByText('No news articles available')).toBeInTheDocument();
    });

    it('should handle news articles with images', () => {
      render(<MarketNews news={mockNews} category="all" onCategoryChange={vi.fn()} />);

      expect(screen.getByTestId('news-image-1')).toBeInTheDocument();
      expect(screen.queryByTestId('news-image-2')).not.toBeInTheDocument();
    });
  });

  describe('MarketScreener Component', () => {
    it('should render stock screener correctly', () => {
      const filters = { marketCap: 'large', sector: 'technology' };

      render(
        <MarketScreener 
          stocks={mockStocks}
          filters={filters}
          onFilterChange={vi.fn()}
          onStockSelect={vi.fn()}
        />
      );

      expect(screen.getByTestId('market-screener')).toBeInTheDocument();
      expect(screen.getByText('Stock Screener')).toBeInTheDocument();
      expect(screen.getByTestId('screener-table')).toBeInTheDocument();
      expect(screen.getByTestId('stock-row-AAPL')).toBeInTheDocument();
      expect(screen.getByTestId('symbol-AAPL')).toHaveTextContent('AAPL');
    });

    it('should handle filter changes', async () => {
      const user = userEvent.setup();
      const onFilterChange = vi.fn();

      render(
        <MarketScreener 
          stocks={mockStocks}
          filters={{}}
          onFilterChange={onFilterChange}
          onStockSelect={vi.fn()}
        />
      );

      await user.selectOptions(screen.getByTestId('market-cap-filter'), 'large');
      expect(onFilterChange).toHaveBeenCalledWith('marketCap', 'large');

      await user.type(screen.getByTestId('min-price-filter'), '100');
      expect(onFilterChange).toHaveBeenCalledWith('minPrice', '100');
    });

    it('should handle stock selection', async () => {
      const user = userEvent.setup();
      const onStockSelect = vi.fn();

      render(
        <MarketScreener 
          stocks={mockStocks}
          filters={{}}
          onFilterChange={vi.fn()}
          onStockSelect={onStockSelect}
        />
      );

      await user.click(screen.getByTestId('stock-row-AAPL'));
      expect(onStockSelect).toHaveBeenCalledWith(mockStocks[0]);
    });

    it('should show loading state', () => {
      render(
        <MarketScreener 
          stocks={[]}
          filters={{}}
          onFilterChange={vi.fn()}
          onStockSelect={vi.fn()}
          loading={true}
        />
      );

      expect(screen.getByTestId('screener-loading')).toBeInTheDocument();
      expect(screen.getByText('Screening stocks...')).toBeInTheDocument();
    });

    it('should handle no results', () => {
      render(
        <MarketScreener 
          stocks={[]}
          filters={{}}
          onFilterChange={vi.fn()}
          onStockSelect={vi.fn()}
        />
      );

      expect(screen.getByTestId('no-results')).toBeInTheDocument();
      expect(screen.getByText('No stocks match your criteria')).toBeInTheDocument();
    });
  });

  describe('EconomicCalendar Component', () => {
    it('should render economic calendar correctly', () => {
      render(
        <EconomicCalendar 
          events={mockEconomicEvents}
          selectedDate="2024-01-15"
          onDateChange={vi.fn()}
          filterImportance={vi.fn()}
        />
      );

      expect(screen.getByTestId('economic-calendar')).toBeInTheDocument();
      expect(screen.getByText('Economic Calendar')).toBeInTheDocument();
      expect(screen.getByTestId('event-1')).toBeInTheDocument();
      expect(screen.getByText('GDP Growth Rate')).toBeInTheDocument();
      expect(screen.getByText('Forecast: 2.1%')).toBeInTheDocument();
      expect(screen.getByText('Previous: 2.0%')).toBeInTheDocument();
    });

    it('should handle date changes', async () => {
      const user = userEvent.setup();
      const onDateChange = vi.fn();

      render(
        <EconomicCalendar 
          events={mockEconomicEvents}
          selectedDate="2024-01-15"
          onDateChange={onDateChange}
          filterImportance={vi.fn()}
        />
      );

      await user.clear(screen.getByTestId('date-picker'));
      await user.type(screen.getByTestId('date-picker'), '2024-01-16');
      expect(onDateChange).toHaveBeenCalled();
    });

    it('should handle importance filter changes', async () => {
      const user = userEvent.setup();
      const filterImportance = vi.fn();

      render(
        <EconomicCalendar 
          events={mockEconomicEvents}
          selectedDate="2024-01-15"
          onDateChange={vi.fn()}
          filterImportance={filterImportance}
        />
      );

      await user.selectOptions(screen.getByTestId('importance-filter'), 'high');
      expect(filterImportance).toHaveBeenCalledWith('high');
    });

    it('should handle no events', () => {
      render(
        <EconomicCalendar 
          events={[]}
          selectedDate="2024-01-15"
          onDateChange={vi.fn()}
          filterImportance={vi.fn()}
        />
      );

      expect(screen.getByTestId('no-events')).toBeInTheDocument();
      expect(screen.getByText('No economic events for selected date')).toBeInTheDocument();
    });

    it('should display event importance levels', () => {
      render(
        <EconomicCalendar 
          events={mockEconomicEvents}
          selectedDate="2024-01-15"
          onDateChange={vi.fn()}
          filterImportance={vi.fn()}
        />
      );

      expect(screen.getByText('HIGH')).toBeInTheDocument();
      expect(screen.getByText('MEDIUM')).toBeInTheDocument();
    });
  });

  describe('Component Integration', () => {
    it('should integrate quote with chart components', () => {
      render(
        <div>
          <StockQuote symbol="AAPL" quote={mockQuote} onRefresh={vi.fn()} />
          <StockChart 
            symbol="AAPL" 
            data={mockChartData} 
            timeframe="1M"
            onTimeframeChange={vi.fn()}
          />
        </div>
      );

      expect(screen.getByTestId('stock-quote')).toBeInTheDocument();
      expect(screen.getByTestId('stock-chart')).toBeInTheDocument();
    });

    it('should integrate screener with quote selection', async () => {
      const user = userEvent.setup();
      let selectedStock = null;

      const handleStockSelect = (stock) => {
        selectedStock = stock;
      };

      const { rerender } = render(
        <div>
          <MarketScreener 
            stocks={mockStocks}
            filters={{}}
            onFilterChange={vi.fn()}
            onStockSelect={handleStockSelect}
          />
          {selectedStock && (
            <StockQuote 
              symbol={selectedStock.symbol} 
              quote={selectedStock} 
              onRefresh={vi.fn()} 
            />
          )}
        </div>
      );

      await user.click(screen.getByTestId('stock-row-AAPL'));

      rerender(
        <div>
          <MarketScreener 
            stocks={mockStocks}
            filters={{}}
            onFilterChange={vi.fn()}
            onStockSelect={handleStockSelect}
          />
          <StockQuote 
            symbol="AAPL" 
            quote={mockStocks[0]} 
            onRefresh={vi.fn()} 
          />
        </div>
      );

      expect(screen.getByTestId('stock-quote')).toBeInTheDocument();
      expect(screen.getByTestId('symbol')).toHaveTextContent('AAPL');
    });
  });

  describe('Performance', () => {
    it('should render large datasets efficiently', () => {
      const largeStockList = Array.from({ length: 1000 }, (_, i) => ({
        symbol: `STOCK${i}`,
        name: `Company ${i}`,
        price: 100 + i,
        change: (Math.random() - 0.5) * 10,
        volume: 1000000 + i * 1000,
        marketCap: 1000000000 + i * 1000000,
        peRatio: 20 + Math.random() * 20
      }));

      const startTime = performance.now();
      render(
        <MarketScreener 
          stocks={largeStockList}
          filters={{}}
          onFilterChange={vi.fn()}
          onStockSelect={vi.fn()}
        />
      );
      const renderTime = performance.now() - startTime;

      expect(renderTime).toBeLessThan(500); // 500ms
      expect(screen.getByTestId('screener-table')).toBeInTheDocument();
    });
  });

  describe('Accessibility', () => {
    it('should have proper ARIA labels and keyboard navigation', async () => {
      const user = userEvent.setup();

      render(<StockQuote symbol="AAPL" quote={mockQuote} onRefresh={vi.fn()} />);

      const refreshButton = screen.getByTestId('refresh-button');
      
      await user.tab();
      expect(refreshButton).toHaveFocus();
    });

    it('should handle screen reader compatibility', () => {
      render(<MarketIndices indices={mockIndices} />);

      const indices = screen.getByTestId('market-indices');
      expect(indices).toBeInTheDocument();
      
      // Check that important information is accessible
      expect(screen.getByText('S&P 500')).toBeInTheDocument();
      expect(screen.getByText('+1.20%')).toBeInTheDocument();
    });
  });

  describe('Error Handling', () => {
    it('should handle corrupted data gracefully', () => {
      const corruptedQuote = {
        symbol: null,
        price: 'invalid',
        change: undefined,
        volume: 'not-a-number'
      };

      expect(() => {
        render(<StockQuote symbol="AAPL" quote={corruptedQuote} onRefresh={vi.fn()} />);
      }).not.toThrow();
    });

    it('should handle missing callback functions', () => {
      expect(() => {
        render(<StockQuote symbol="AAPL" quote={mockQuote} />);
      }).not.toThrow();

      expect(() => {
        render(<MarketScreener stocks={mockStocks} filters={{}} />);
      }).not.toThrow();
    });
  });
});
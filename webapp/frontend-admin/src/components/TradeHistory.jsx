import React, { useState, useEffect } from 'react';
import './TradeHistory.css';

const TradeHistory = ({ _userId }) => {
  const [trades, setTrades] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [filters, setFilters] = useState({
    symbol: '',
    timeframe: '3m',
  });

  useEffect(() => {
    fetchTradeHistory();
    fetchTradeSummary();
  }, [filters]);

  const fetchTradeHistory = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        timeframe: filters.timeframe,
        ...(filters.symbol && { symbol: filters.symbol })
      });

      const response = await fetch(`/api/trades/history?${params}`, {
        headers: {
          'X-Dev-Bypass-Token': 'dev-bypass-token',
        }
      });

      if (!response.ok) throw new Error('Failed to fetch trades');

      const data = await response.json();
      if (data.success) {
        // Extract trades array from nested structure
        const tradesData = data.data?.trades?.trades_data || data.data?.trades;
        setTrades(Array.isArray(tradesData) ? tradesData : []);
      }
      setError(null);
    } catch (err) {
      setError(err.message);
      console.error('Error fetching trades:', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchTradeSummary = async () => {
    try {
      const response = await fetch('/api/trades/summary', {
        headers: {
          'X-Dev-Bypass-Token': 'dev-bypass-token',
        }
      });

      if (!response.ok) throw new Error('Failed to fetch summary');

      const data = await response.json();
      if (data.success) {
        // Extract summary object from response
        const summaryData = data.data?.summary || null;
        if (summaryData && typeof summaryData === 'object' && !Array.isArray(summaryData)) {
          setSummary(summaryData);
        } else {
          setSummary(null);
        }
      }
    } catch (err) {
      console.error('Error fetching summary:', err);
    }
  };

  const formatCurrency = (value) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
    }).format(value);
  };

  const formatPercent = (value) => {
    // If value is already > 1, it's likely already percentage-scaled (e.g., 61.31 for 61.31%)
    // If value is < 1, it's a decimal (e.g., 0.6131 for 61.31%)
    if (value === null || value === undefined) return 'N/A';
    const numValue = parseFloat(value);
    if (numValue > 1) {
      // Already percentage-scaled, just format as-is
      return `${numValue.toFixed(2)}%`;
    } else {
      // Decimal format, multiply by 100
      return `${(numValue * 100).toFixed(2)}%`;
    }
  };

  return (
    <div className="trade-history">
      <h2>Trade History</h2>

      {summary && (
        <div className="trade-summary">
          <div className="summary-card">
            <div className="summary-label">Total Trades</div>
            <div className="summary-value">{summary.total_trades}</div>
          </div>

          <div className="summary-card">
            <div className="summary-label">Win Rate</div>
            <div className="summary-value">{formatPercent(summary.win_rate)}</div>
          </div>

          <div className="summary-card">
            <div className="summary-label">Realized P&L</div>
            <div className={`summary-value ${summary.total_realized_pnl >= 0 ? 'positive' : 'negative'}`}>
              {formatCurrency(summary.total_realized_pnl)}
            </div>
          </div>

          <div className="summary-card">
            <div className="summary-label">Largest Win</div>
            <div className="summary-value positive">
              {summary.largest_win ? formatCurrency(summary.largest_win) : 'N/A'}
            </div>
          </div>

          <div className="summary-card">
            <div className="summary-label">Largest Loss</div>
            <div className="summary-value negative">
              {summary.largest_loss ? formatCurrency(summary.largest_loss) : 'N/A'}
            </div>
          </div>
        </div>
      )}

      <div className="trade-filters">
        <input
          type="text"
          placeholder="Filter by symbol..."
          value={filters.symbol}
          onChange={(e) => setFilters({ ...filters, symbol: e.target.value.toUpperCase() })}
          className="filter-input"
        />

        <select
          value={filters.timeframe}
          onChange={(e) => setFilters({ ...filters, timeframe: e.target.value })}
          className="filter-select"
        >
          <option value="1w">1 Week</option>
          <option value="1m">1 Month</option>
          <option value="3m">3 Months</option>
          <option value="6m">6 Months</option>
          <option value="1y">1 Year</option>
          <option value="all">All Time</option>
        </select>
      </div>

      {loading ? (
        <div className="loading">Loading trades...</div>
      ) : error ? (
        <div className="error">{error}</div>
      ) : trades.length === 0 ? (
        <div className="empty-state">
          <p>No trades found for the selected period</p>
          <p className="empty-subtext">Trade history endpoint is ready for Alpaca account integration</p>
        </div>
      ) : (
        <div className="trade-table-container">
          <table className="trade-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Symbol</th>
                <th>Type</th>
                <th>Qty</th>
                <th>Execution Price</th>
                <th>Order Value</th>
                <th>Commission</th>
                <th>Realized P&L</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((trade, index) => (
                <tr key={index} className={`trade-row ${trade.realized_pnl >= 0 ? 'win' : 'loss'}`}>
                  <td>{new Date(trade.execution_date).toLocaleDateString()}</td>
                  <td className="symbol">{trade.symbol}</td>
                  <td className={`type ${trade.type.toLowerCase()}`}>{trade.type.toUpperCase()}</td>
                  <td>{trade.quantity}</td>
                  <td>${trade.execution_price.toFixed(2)}</td>
                  <td>{formatCurrency(trade.order_value)}</td>
                  <td>{formatCurrency(trade.commission || 0)}</td>
                  <td className={`pnl ${trade.realized_pnl >= 0 ? 'positive' : 'negative'}`}>
                    {formatCurrency(trade.realized_pnl || 0)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default TradeHistory;

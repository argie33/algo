import React from 'react';

export const PortfolioSummaryWidget = ({ 
  data, 
  loading, 
  onNavigate, 
  onRefresh, 
  showUnrealizedGains,
  ...props 
}) => {
  if (loading) {
    return (
      <div className="portfoliosummarywidget" style={{ padding: '1rem', border: '1px solid #e0e0e0', borderRadius: '8px' }} {...props}>
        <h3 style={{ margin: '0 0 1rem 0' }}>Portfolio Summary</h3>
        <div role="progressbar">Loading...</div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="portfoliosummarywidget" style={{ padding: '1rem', border: '1px solid #e0e0e0', borderRadius: '8px' }} {...props}>
        <h3 style={{ margin: '0 0 1rem 0' }}>Portfolio Summary</h3>
        <div>No data available</div>
      </div>
    );
  }

  // Handle malformed data
  if (typeof data.totalValue !== 'number' || data.dayChange === null || data.dayChangePercent === undefined) {
    return (
      <div className="portfoliosummarywidget" style={{ padding: '1rem', border: '1px solid #e0e0e0', borderRadius: '8px' }} {...props}>
        <h3 style={{ margin: '0 0 1rem 0' }}>Portfolio Summary</h3>
        <div>Data error</div>
      </div>
    );
  }

  const formatCurrency = (value) => {
    if (typeof value !== 'number') return '$0';
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0
    }).format(value);
  };

  const formatChange = (value) => {
    if (typeof value !== 'number') return '$0';
    const formatted = formatCurrency(Math.abs(value));
    return value >= 0 ? `+${formatted}` : `-${formatted}`;
  };

  const formatPercent = (value) => {
    if (typeof value !== 'number') return '0%';
    return value >= 0 ? `+${value.toFixed(2)}%` : `${value.toFixed(2)}%`;
  };

  return (
    <div 
      className="portfoliosummarywidget" 
      style={{ padding: '1rem', border: '1px solid #e0e0e0', borderRadius: '8px' }} 
      {...props}
      role="region"
      aria-label="Portfolio Summary"
    >
      <h3 style={{ margin: '0 0 1rem 0' }}>Portfolio Summary</h3>
      
      <div style={{ display: 'grid', gap: '0.5rem' }}>
        <div>
          <strong>Total Value:</strong> {formatCurrency(data.totalValue)}
        </div>
        
        <div>
          <strong>Day Change:</strong> {formatChange(data.dayChange)} ({formatPercent(data.dayChangePercent)})
        </div>
        
        {data.positions && (
          <div>
            <strong>Positions:</strong> {data.positions} positions
          </div>
        )}
        
        {showUnrealizedGains && data.unrealizedGainLoss && (
          <div>
            <strong>Unrealized P&L:</strong> {formatChange(data.unrealizedGainLoss)} ({formatPercent(data.unrealizedGainLossPercent)})
          </div>
        )}
        
        {data.cash && (
          <div>
            <strong>Cash:</strong> {formatCurrency(data.cash)}
          </div>
        )}
      </div>

      <div style={{ marginTop: '1rem', display: 'flex', gap: '0.5rem' }}>
        {onNavigate && (
          <button 
            onClick={() => onNavigate('/portfolio')}
            style={{ padding: '0.5rem 1rem', border: '1px solid #ccc', borderRadius: '4px', cursor: 'pointer' }}
          >
            View Portfolio
          </button>
        )}
        
        {onRefresh && (
          <button 
            onClick={onRefresh}
            style={{ padding: '0.5rem 1rem', border: '1px solid #ccc', borderRadius: '4px', cursor: 'pointer' }}
          >
            Refresh
          </button>
        )}
      </div>

      <div role="status" aria-live="polite" style={{ position: 'absolute', left: '-9999px' }}>
        Portfolio updated
      </div>
    </div>
  );
};

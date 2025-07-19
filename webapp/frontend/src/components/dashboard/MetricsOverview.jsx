import React from 'react';

export const MetricsOverview = ({ metrics = {}, ...props }) => {
  const {
    portfolioValue = 0,
    dayChange = 0,
    dayChangePercent = 0,
    marketStatus = 'closed',
    alertCount = 0
  } = metrics;

  const isPositive = dayChange >= 0;

  return (
    <div className="metrics-overview" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem' }} {...props}>
      <div className="metric-card" style={{ padding: '1rem', border: '1px solid #e0e0e0', borderRadius: '8px', backgroundColor: '#fff' }}>
        <h4 style={{ margin: '0 0 0.5rem 0', color: '#666', fontSize: '0.9rem' }}>Portfolio Value</h4>
        <div style={{ fontSize: '1.5rem', fontWeight: 'bold' }}>${portfolioValue.toLocaleString()}</div>
      </div>
      
      <div className="metric-card" style={{ padding: '1rem', border: '1px solid #e0e0e0', borderRadius: '8px', backgroundColor: '#fff' }}>
        <h4 style={{ margin: '0 0 0.5rem 0', color: '#666', fontSize: '0.9rem' }}>Day Change</h4>
        <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: isPositive ? '#4caf50' : '#f44336' }}>
          {isPositive ? '+' : ''}${dayChange.toLocaleString()} ({isPositive ? '+' : ''}{dayChangePercent.toFixed(2)}%)
        </div>
      </div>
      
      <div className="metric-card" style={{ padding: '1rem', border: '1px solid #e0e0e0', borderRadius: '8px', backgroundColor: '#fff' }}>
        <h4 style={{ margin: '0 0 0.5rem 0', color: '#666', fontSize: '0.9rem' }}>Market Status</h4>
        <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: marketStatus === 'open' ? '#4caf50' : '#f44336' }}>
          {marketStatus.charAt(0).toUpperCase() + marketStatus.slice(1)}
        </div>
      </div>
      
      <div className="metric-card" style={{ padding: '1rem', border: '1px solid #e0e0e0', borderRadius: '8px', backgroundColor: '#fff' }}>
        <h4 style={{ margin: '0 0 0.5rem 0', color: '#666', fontSize: '0.9rem' }}>Alerts</h4>
        <div style={{ fontSize: '1.5rem', fontWeight: 'bold' }}>{alertCount}</div>
      </div>
    </div>
  );
};
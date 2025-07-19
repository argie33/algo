import React from 'react';

export const RiskMetricsWidget = ({ data, ...props }) => {
  return (
    <div className="riskmetricswidget" style={{ padding: '1rem', border: '1px solid #e0e0e0', borderRadius: '8px' }} {...props}>
      <h3 style={{ margin: '0 0 1rem 0' }}>RiskMetricsWidget</h3>
      <div>Widget content for {JSON.stringify(data)}</div>
    </div>
  );
};

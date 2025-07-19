import React from 'react';

export const PerformanceWidget = ({ data, ...props }) => {
  return (
    <div className="performancewidget" style={{ padding: '1rem', border: '1px solid #e0e0e0', borderRadius: '8px' }} {...props}>
      <h3 style={{ margin: '0 0 1rem 0' }}>PerformanceWidget</h3>
      <div>Widget content for {JSON.stringify(data)}</div>
    </div>
  );
};

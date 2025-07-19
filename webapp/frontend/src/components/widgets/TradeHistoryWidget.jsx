import React from 'react';

export const TradeHistoryWidget = ({ data, ...props }) => {
  return (
    <div className="tradehistorywidget" style={{ padding: '1rem', border: '1px solid #e0e0e0', borderRadius: '8px' }} {...props}>
      <h3 style={{ margin: '0 0 1rem 0' }}>TradeHistoryWidget</h3>
      <div>Widget content for {JSON.stringify(data)}</div>
    </div>
  );
};

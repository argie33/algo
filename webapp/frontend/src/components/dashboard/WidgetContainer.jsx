import React from 'react';

export const WidgetContainer = ({ title, children, actions, loading = false, error = null, ...props }) => {
  if (loading) {
    return (
      <div className="widget-container loading" style={{ padding: '1rem', border: '1px solid #e0e0e0', borderRadius: '8px', backgroundColor: '#fff' }}>
        <div>Loading...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="widget-container error" style={{ padding: '1rem', border: '1px solid #ff6b6b', borderRadius: '8px', backgroundColor: '#fff' }}>
        <div style={{ color: '#ff6b6b' }}>Error: {error}</div>
      </div>
    );
  }

  return (
    <div className="widget-container" style={{ padding: '1rem', border: '1px solid #e0e0e0', borderRadius: '8px', backgroundColor: '#fff' }} {...props}>
      {title && (
        <div className="widget-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <h3 style={{ margin: 0 }}>{title}</h3>
          {actions && <div className="widget-actions">{actions}</div>}
        </div>
      )}
      <div className="widget-content">{children}</div>
    </div>
  );
};
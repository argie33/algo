/**
 * DataStateManager — reusable wrapper for loading/error/empty states
 *
 * Usage:
 *   <DataStateManager loading={isLoading} error={error} data={data}>
 *     <YourContent data={data} />
 *   </DataStateManager>
 */

import React from 'react';
import { AlertTriangle, Inbox, Loader } from 'lucide-react';

export function DataStateManager({ loading, error, data, children, emptyMessage = 'No data available' }) {
  // Show loading state
  if (loading) {
    return (
      <div style={{ padding: 'var(--space-4)', textAlign: 'center' }}>
        <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 'var(--space-2)' }}>
          <Loader size={24} className="spin" />
        </div>
        <div className="t-sm muted">Loading data...</div>
      </div>
    );
  }

  // Show error state
  if (error) {
    return (
      <div style={{ padding: 'var(--space-4)' }}>
        <div className="alert alert-danger">
          <div className="flex gap-3 items-start">
            <AlertTriangle size={20} style={{ flexShrink: 0, marginTop: 2 }} />
            <div>
              <div className="strong">Failed to load data</div>
              <div className="t-xs muted" style={{ marginTop: 4 }}>
                {typeof error === 'string' ? error : error?.message || 'Unknown error'}
              </div>
              <div className="t-2xs muted" style={{ marginTop: 8 }}>
                Please try refreshing the page or contact support if the issue persists.
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Show empty state
  if (!data || (Array.isArray(data) && data.length === 0)) {
    return (
      <div style={{ padding: 'var(--space-4)', textAlign: 'center', color: 'var(--text-muted)' }}>
        <Inbox size={40} style={{ margin: '0 auto var(--space-2)', opacity: 0.5 }} />
        <div className="t-sm">{emptyMessage}</div>
      </div>
    );
  }

  // Data exists - render children
  return children;
}

/**
 * Quick error alert for inline errors
 */
export function ErrorAlert({ error, onDismiss }) {
  if (!error) return null;
  return (
    <div className="alert alert-danger" style={{ marginBottom: 'var(--space-3)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
      <span className="t-xs">{typeof error === 'string' ? error : error?.message || 'An error occurred'}</span>
      {onDismiss && <button onClick={onDismiss} className="btn btn-outline btn-xs">Dismiss</button>}
    </div>
  );
}

export default DataStateManager;

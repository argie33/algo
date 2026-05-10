/**
 * DataSection — Reusable data display wrapper with error handling
 *
 * Provides consistent handling of:
 * - Loading states
 * - Error states (with error message)
 * - Empty states
 * - Data freshness indicators
 */

import React from 'react';
import { Inbox, AlertCircle } from 'lucide-react';

export function DataSection({
  title,
  subtitle,
  isLoading,
  error,
  isEmpty,
  emptyMessage = 'No data available',
  errorMessage,
  freshness, // { lastUpdated: Date, expectedRefresh: number (ms) }
  children,
  className = 'card'
}) {
  const isFresh = !freshness || (Date.now() - freshness.lastUpdated.getTime()) <= freshness.expectedRefresh;
  const ageMinutes = freshness ? Math.floor((Date.now() - freshness.lastUpdated.getTime()) / 60000) : null;

  return (
    <div className={className}>
      {(title || subtitle) && (
        <div className="card-head">
          <div>
            {title && <div className="card-title">{title}</div>}
            {subtitle && <div className="card-sub">{subtitle}</div>}
          </div>
          {freshness && !isFresh && (
            <div className="badge badge-amber" style={{ fontSize: 'var(--t-2xs)' }}>
              Stale ({ageMinutes}m old)
            </div>
          )}
          {freshness && isFresh && ageMinutes !== null && (
            <div className="t-2xs muted" style={{ fontSize: 'var(--t-2xs)' }}>
              Updated {ageMinutes}m ago
            </div>
          )}
        </div>
      )}
      <div className="card-body">
        {isLoading && !error ? (
          <div className="empty">
            <Inbox size={32} className="muted" />
            <div className="empty-title">Loading…</div>
          </div>
        ) : error ? (
          <div className="empty">
            <AlertCircle size={32} style={{ color: 'var(--danger)' }} />
            <div className="empty-title">Failed to load data</div>
            <div className="empty-desc">{errorMessage || error.message || 'Unknown error'}</div>
          </div>
        ) : isEmpty ? (
          <div className="empty">
            <Inbox size={32} className="muted" />
            <div className="empty-title">{emptyMessage}</div>
          </div>
        ) : (
          children
        )}
      </div>
    </div>
  );
}

/**
 * TruncatedList — Display a list with "X of Y" indicator and expand option
 */
export function TruncatedList({
  items,
  limit,
  renderItem,
  emptyMessage = 'No items',
  header,
}) {
  const displayed = items.slice(0, limit);
  const total = items.length;
  const hasMore = total > limit;

  return (
    <>
      {header && <div style={{ marginBottom: 'var(--space-3)', fontWeight: 'var(--w-semibold)' }}>{header}</div>}
      {total === 0 ? (
        <div className="muted t-sm">{emptyMessage}</div>
      ) : (
        <>
          {displayed.map((item, i) => renderItem(item, i))}
          <div className="flex justify-between items-center" style={{ marginTop: 'var(--space-2)', fontSize: 'var(--t-2xs)' }}>
            <span className="muted">
              Showing {displayed.length} of {total} items
              {hasMore && ` (${total - limit} more hidden)`}
            </span>
            {hasMore && (
              <button className="btn btn-text btn-xs" style={{ cursor: 'pointer' }}>
                View all {total} →
              </button>
            )}
          </div>
        </>
      )}
    </>
  );
}

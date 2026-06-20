import React from 'react';
import { AlertTriangle, Clock, AlertCircle } from 'lucide-react';

/**
 * Component to display data age and staleness warnings
 * Shows when data is from cache and how old it is
 * Warns if data is phantom (>2 hours old)
 */
export const DataAgeIndicator = ({
  fetchedAt,
  isFromCache = false,
  isStale = false,
  label = 'Data',
}) => {
  if (!fetchedAt) return null;

  const now = Date.now();
  const ageMs = now - fetchedAt;
  const ageMinutes = Math.floor(ageMs / 60000);
  const ageHours = Math.floor(ageMs / 3600000);
  const ageDays = Math.floor(ageMs / 86400000);

  let ageText = '';
  if (ageMinutes < 1) {
    ageText = 'just now';
  } else if (ageMinutes < 60) {
    ageText = `${ageMinutes}m ago`;
  } else if (ageHours < 24) {
    ageText = `${ageHours}h ago`;
  } else {
    ageText = `${ageDays}d ago`;
  }

  if (isStale) {
    return (
      <div style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 'var(--space-1)',
        padding: 'var(--space-1) var(--space-2)',
        borderRadius: 'var(--r-sm)',
        background: 'rgba(239, 68, 68, 0.1)',
        border: '1px solid var(--danger-soft)',
        fontSize: 'var(--t-xs)',
        color: 'var(--danger)',
        fontWeight: 'var(--w-semibold)',
      }}>
        <AlertTriangle size={14} />
        <span>⚠️ {label} is stale ({ageText})</span>
      </div>
    );
  }

  if (isFromCache) {
    return (
      <div style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 'var(--space-1)',
        padding: 'var(--space-1) var(--space-2)',
        borderRadius: 'var(--r-sm)',
        background: 'rgba(251, 191, 36, 0.1)',
        border: '1px solid var(--amber-soft)',
        fontSize: 'var(--t-xs)',
        color: 'var(--amber)',
        fontWeight: 'var(--w-semibold)',
      }}>
        <Clock size={14} />
        <span>🔄 {label} from cache ({ageText})</span>
      </div>
    );
  }

  return null;
};

/**
 * Banner to show when critical data is phantom (>2 hours old)
 * Blocks rendering of critical sections until fresh data arrives
 */
export const StaleDataWarning = ({
  sections = [],
  age = 0,
  onRetry = null,
}) => {
  if (!sections.length) return null;

  const ageMinutes = Math.floor(age / 60000);
  const ageHours = Math.floor(age / 3600000);

  let ageText = '';
  if (ageMinutes < 60) {
    ageText = `${ageMinutes} minute${ageMinutes !== 1 ? 's' : ''}`;
  } else {
    ageText = `${ageHours} hour${ageHours !== 1 ? 's' : ''}`;
  }

  return (
    <div style={{
      padding: 'var(--space-3)',
      borderRadius: 'var(--r-md)',
      background: 'var(--danger-light)',
      border: '2px solid var(--danger)',
      marginBottom: 'var(--space-4)',
    }}>
      <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'flex-start' }}>
        <AlertCircle size={20} style={{ color: 'var(--danger)', flexShrink: 0, marginTop: '2px' }} />
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 'var(--w-semibold)', color: 'var(--danger)', marginBottom: 'var(--space-1)' }}>
            ⚠️ Stale Data Warning
          </div>
          <div className="muted t-sm" style={{ marginBottom: 'var(--space-2)' }}>
            The following data is {ageText} old and may not reflect current market conditions:
          </div>
          <ul style={{ marginBottom: 'var(--space-3)', paddingLeft: '1.5em' }}>
            {sections.map((section, idx) => (
              <li key={idx} className="muted t-sm" style={{ marginBottom: 'var(--space-1)' }}>
                {section}
              </li>
            ))}
          </ul>
          <div className="muted t-xs" style={{ fontStyle: 'italic' }}>
            ℹ️ For accurate positions and risk data, please refresh. Do not make trading decisions based on stale data.
          </div>
          {onRetry && (
            <button
              className="btn btn-sm"
              style={{ marginTop: 'var(--space-2)' }}
              onClick={onRetry}
            >
              🔄 Refresh Now
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export default { DataAgeIndicator, StaleDataWarning };

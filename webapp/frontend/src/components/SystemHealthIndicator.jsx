import React, { useEffect, useState } from 'react';
import { AlertCircle } from 'lucide-react';
import { api } from '../services/api';

/**
 * SystemHealthIndicator - Shows system degradation status and signal freshness in header
 * ISSUE #13 FIX: Propagate signal freshness to frontend for user visibility
 * Fetches /api/health (public endpoint) every 30s and alerts if degraded or signals stale
 */
export function SystemHealthIndicator() {
  const [isDegraded, setIsDegraded] = useState(false);
  const [signalFreshness, setSignalFreshness] = useState(null);
  const [statusMessage, setStatusMessage] = useState('');

  useEffect(() => {
    let cancelled = false;

    const fetchHealth = async () => {
      try {
        const response = await api.get('/api/health', { timeout: 10000 });
        if (cancelled) return;

        const data = response.data?.data || response.data;
        setIsDegraded(data?.degraded_mode_active === true);
        setSignalFreshness(data?.freshness);

        // Build status message for user
        if (data?.degraded_mode_active) {
          setStatusMessage('System in degraded mode: Position sizes reduced to 50%');
        } else if (data?.freshness?.status === 'STALE') {
          setStatusMessage(`Signals are stale (${data.freshness.signal_age_hours} hours old). Use with caution.`);
        } else if (data?.freshness?.status === 'OK' && data.freshness.signal_age_hours > 12) {
          setStatusMessage(`Signals waiting for fresh data (${data.freshness.signal_age_hours} hours old).`);
        }
      } catch (error) {
        // Silent fail - health check is non-critical
        console.debug('[SystemHealthIndicator] Health check error:', error?.message);
      }
    };

    fetchHealth();
    const id = setInterval(fetchHealth, 30000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  // Show badge if degraded or signals are stale
  const showBadge = isDegraded || signalFreshness?.status === 'STALE' || (signalFreshness?.status === 'OK' && signalFreshness?.signal_age_hours > 12);

  if (!showBadge) return null;

  const badgeColor = isDegraded ? 'badge-danger' : (signalFreshness?.status === 'STALE' ? 'badge-danger' : 'badge-warning');
  const badgeLabel = isDegraded ? 'DEGRADED' : (signalFreshness?.status === 'STALE' ? 'SIGNALS STALE' : 'SIGNALS AGING');

  return (
    <div
      className={`badge ${badgeColor}`}
      style={{ display: 'flex', alignItems: 'center', gap: '6px', cursor: 'help' }}
      title={statusMessage || `Signal freshness: ${signalFreshness?.signal_age_hours || '?'} hours old`}
    >
      <AlertCircle size={14} />
      <span>{badgeLabel}</span>
    </div>
  );
}

export default SystemHealthIndicator;

import React, { useEffect, useState } from 'react';
import { AlertCircle } from 'lucide-react';
import { api } from '../services/api';

/**
 * SystemHealthIndicator - Shows system degradation status in header
 * Fetches /api/health (public endpoint) every 30s and alerts if degraded
 */
export function SystemHealthIndicator() {
  const [isDegraded, setIsDegraded] = useState(false);
  const [freshness, setFreshness] = useState(null);

  useEffect(() => {
    let cancelled = false;

    const fetchHealth = async () => {
      try {
        const response = await api.get('/api/health', { timeout: 3000 });
        if (cancelled) return;

        const data = response.data?.data || response.data;
        setIsDegraded(data?.degraded_mode_active === true);
        setFreshness(data?.freshness);
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

  if (!isDegraded) return null;

  const freshnessDays = freshness?.oldest_data_age_days?.toFixed(1) || '?';
  return (
    <div
      className="badge badge-danger"
      style={{ display: 'flex', alignItems: 'center', gap: '6px', cursor: 'help' }}
      title={`System degraded: data is ${freshnessDays} days old. Position sizes reduced to 50%.`}
    >
      <AlertCircle size={14} />
      <span>DEGRADED</span>
    </div>
  );
}

export default SystemHealthIndicator;

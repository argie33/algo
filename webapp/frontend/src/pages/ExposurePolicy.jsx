/**
 * Exposure Policy — Market exposure limits by market regime
 *
 * Displays:
 * - Current exposure percentage
 * - Active tier (entry/pyramid restrictions)
 * - Market factors driving the tier
 * - Halt reasons if applicable
 */

import React from 'react';
import { Shield, AlertTriangle } from 'lucide-react';
import { useApiQuery } from '../hooks/useApiQuery';
import { SkeletonKpi } from '../components/Skeleton';
import { api } from '../services/api';

const getTierColor = (tier) => {
  const tierLower = (tier || '').toLowerCase();
  if (tierLower === 'tier1' || tierLower === 'tier 1') return 'var(--success)';
  if (tierLower === 'tier2' || tierLower === 'tier 2') return 'var(--amber)';
  if (tierLower === 'tier3' || tierLower === 'tier 3') return 'var(--danger)';
  if (tierLower === 'tier4' || tierLower === 'tier 4') return '#7f1d1d';
  return 'var(--text-secondary)';
};

const getTierLabel = (tier) => {
  const tierLower = (tier || '').toLowerCase();
  const labels = {
    'tier1': { label: 'Tier 1 — Aggressive', desc: 'Strong uptrend, entry allowed' },
    'tier 1': { label: 'Tier 1 — Aggressive', desc: 'Strong uptrend, entry allowed' },
    'tier2': { label: 'Tier 2 — Moderate', desc: 'Uptrend, entry allowed (limited)' },
    'tier 2': { label: 'Tier 2 — Moderate', desc: 'Uptrend, entry allowed (limited)' },
    'tier3': { label: 'Tier 3 — Cautious', desc: 'Transition, pyramiding only' },
    'tier 3': { label: 'Tier 3 — Cautious', desc: 'Transition, pyramiding only' },
    'tier4': { label: 'Tier 4 — Defensive', desc: 'Downtrend, entry halted' },
    'tier 4': { label: 'Tier 4 — Defensive', desc: 'Downtrend, entry halted' },
  };
  return labels[tierLower] || { label: 'Unknown', desc: 'Market regime unclear' };
};

const ExposurePolicy = () => {
  const { data: policyData, loading: isLoading, error } = useApiQuery(
    ['exposure-policy'],
    () => api.get('/api/algo/exposure-policy')
  );

  if (isLoading) {
    return (
      <div className="main-content">
        <div className="page-head">
          <div>
            <div className="page-head-title">Exposure Policy</div>
            <div className="page-head-sub">Market exposure limits and entry restrictions</div>
          </div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-6)' }}>
          <SkeletonKpi />
          <SkeletonKpi />
        </div>
      </div>
    );
  }

  const policy = policyData?.data || policyData || {};
  const hasData = policy.current_exposure_pct !== null && policy.current_exposure_pct !== undefined;
  const activeTier = policy.active_tier || {};
  const tierInfo = getTierLabel(policy.exposure_tier);
  const isHalted = policy.halt_reasons && Array.isArray(policy.halt_reasons) && policy.halt_reasons.length > 0;

  return (
    <div className="main-content">
      <div className="page-head">
        <div>
          <div className="page-head-title">Exposure Policy</div>
          <div className="page-head-sub">Market exposure limits and entry restrictions</div>
        </div>
      </div>

      {error && (
        <div className="alert alert-warning" style={{ marginBottom: 'var(--space-6)' }}>
          <AlertTriangle size={20} style={{ marginRight: 'var(--space-2)' }} />
          {error.message || 'Failed to load exposure policy'}
        </div>
      )}

      {!hasData && !error && (
        <div className="alert alert-info" style={{ marginBottom: 'var(--space-6)' }}>
          <Shield size={20} style={{ marginRight: 'var(--space-2)' }} />
          Exposure policy is not yet available. Data will appear after market data loads.
        </div>
      )}

      {/* Current Status */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-6)', marginBottom: 'var(--space-6)' }}>
        {/* Exposure Percentage */}
        <div className="card">
          <div className="card-head">
            <div className="card-title">Current Exposure</div>
            <div className="card-sub">Percentage of portfolio in positions</div>
          </div>
          <div className="card-body">
            <div style={{ fontSize: 'var(--t-3xl)', fontWeight: 'var(--w-bold)', color: 'var(--brand)', marginBottom: 'var(--space-3)' }}>
              {policy.current_exposure_pct !== null && policy.current_exposure_pct !== undefined
                ? `${policy.current_exposure_pct.toFixed(1)}%`
                : '—'}
            </div>
            <div style={{ fontSize: 'var(--t-sm)', color: 'var(--text-secondary)' }}>
              Amount of capital deployed
            </div>
          </div>
        </div>

        {/* Market Tier */}
        <div className="card" style={{ borderLeft: `4px solid ${getTierColor(policy.exposure_tier)}` }}>
          <div className="card-head">
            <div className="card-title" style={{ color: getTierColor(policy.exposure_tier) }}>
              {tierInfo.label}
            </div>
            <div className="card-sub">{tierInfo.desc}</div>
          </div>
          <div className="card-body">
            <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', marginBottom: 'var(--space-3)' }}>
              <Shield size={24} color={getTierColor(policy.exposure_tier)} />
              <div>
                <div style={{ fontWeight: 'var(--w-bold)', fontSize: 'var(--t-sm)' }}>
                  Entry Status: {policy.is_entry_allowed ? '✓ Allowed' : '✗ Halted'}
                </div>
                <div style={{ fontSize: 'var(--t-xs)', color: 'var(--text-secondary)' }}>
                  {policy.is_entry_allowed ? 'New positions can be opened' : 'Entry is restricted in this regime'}
                </div>
              </div>
            </div>
            {activeTier.min_positions && activeTier.max_positions && (
              <div style={{ fontSize: 'var(--t-sm)', color: 'var(--text-secondary)' }}>
                Position limit: {activeTier.min_positions}–{activeTier.max_positions}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Market Factors */}
      {policy.regime_factors && (
        <div className="card" style={{ marginBottom: 'var(--space-6)' }}>
          <div className="card-head">
            <div className="card-title">Market Factors</div>
            <div className="card-sub">Metrics driving the exposure tier</div>
          </div>
          <div className="card-body">
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-4)' }}>
              {policy.regime_factors.sp500_stage !== null && policy.regime_factors.sp500_stage !== undefined && (
                <div style={{ paddingBottom: 'var(--space-3)', borderBottom: '1px solid var(--border)' }}>
                  <div style={{ fontSize: 'var(--t-xs)', color: 'var(--text-secondary)', textTransform: 'uppercase', fontWeight: 'var(--w-bold)', marginBottom: 'var(--space-1)' }}>
                    S&P 500 Stage
                  </div>
                  <div style={{ fontSize: 'var(--t-lg)', fontWeight: 'var(--w-bold)' }}>
                    Stage {policy.regime_factors.sp500_stage}
                  </div>
                </div>
              )}

              {policy.regime_factors.vix_level !== null && policy.regime_factors.vix_level !== undefined && (
                <div style={{ paddingBottom: 'var(--space-3)', borderBottom: '1px solid var(--border)' }}>
                  <div style={{ fontSize: 'var(--t-xs)', color: 'var(--text-secondary)', textTransform: 'uppercase', fontWeight: 'var(--w-bold)', marginBottom: 'var(--space-1)' }}>
                    VIX Level
                  </div>
                  <div style={{ fontSize: 'var(--t-lg)', fontWeight: 'var(--w-bold)', color: policy.regime_factors.vix_level > 30 ? 'var(--danger)' : 'var(--text)' }}>
                    {policy.regime_factors.vix_level.toFixed(1)}
                  </div>
                </div>
              )}

              {policy.regime_factors.advance_decline_ratio !== null && policy.regime_factors.advance_decline_ratio !== undefined && (
                <div style={{ paddingBottom: 'var(--space-3)', borderBottom: '1px solid var(--border)' }}>
                  <div style={{ fontSize: 'var(--t-xs)', color: 'var(--text-secondary)', textTransform: 'uppercase', fontWeight: 'var(--w-bold)', marginBottom: 'var(--space-1)' }}>
                    Advance/Decline
                  </div>
                  <div style={{ fontSize: 'var(--t-lg)', fontWeight: 'var(--w-bold)' }}>
                    {policy.regime_factors.advance_decline_ratio.toFixed(2)}
                  </div>
                </div>
              )}

              {policy.regime_factors.breadth_momentum !== null && policy.regime_factors.breadth_momentum !== undefined && (
                <div style={{ paddingBottom: 'var(--space-3)', borderBottom: '1px solid var(--border)' }}>
                  <div style={{ fontSize: 'var(--t-xs)', color: 'var(--text-secondary)', textTransform: 'uppercase', fontWeight: 'var(--w-bold)', marginBottom: 'var(--space-1)' }}>
                    Breadth Momentum
                  </div>
                  <div style={{ fontSize: 'var(--t-lg)', fontWeight: 'var(--w-bold)', color: policy.regime_factors.breadth_momentum > 0 ? 'var(--success)' : 'var(--danger)' }}>
                    {policy.regime_factors.breadth_momentum.toFixed(1)}
                  </div>
                </div>
              )}

              {policy.regime_factors.distribution_days !== null && policy.regime_factors.distribution_days !== undefined && (
                <div style={{ paddingBottom: 'var(--space-3)', borderBottom: '1px solid var(--border)' }}>
                  <div style={{ fontSize: 'var(--t-xs)', color: 'var(--text-secondary)', textTransform: 'uppercase', fontWeight: 'var(--w-bold)', marginBottom: 'var(--space-1)' }}>
                    Distribution Days
                  </div>
                  <div style={{ fontSize: 'var(--t-lg)', fontWeight: 'var(--w-bold)', color: policy.regime_factors.distribution_days > 3 ? 'var(--danger)' : 'var(--text)' }}>
                    {policy.regime_factors.distribution_days}
                  </div>
                </div>
              )}

              {policy.regime_factors.market_stage !== null && policy.regime_factors.market_stage !== undefined && (
                <div style={{ paddingBottom: 'var(--space-3)', borderBottom: '1px solid var(--border)' }}>
                  <div style={{ fontSize: 'var(--t-xs)', color: 'var(--text-secondary)', textTransform: 'uppercase', fontWeight: 'var(--w-bold)', marginBottom: 'var(--space-1)' }}>
                    Market Stage
                  </div>
                  <div style={{ fontSize: 'var(--t-lg)', fontWeight: 'var(--w-bold)' }}>
                    {policy.regime_factors.market_stage}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Halt Reasons */}
      {isHalted && (
        <div className="card" style={{ backgroundColor: 'rgba(127, 29, 29, 0.2)', borderLeft: '4px solid var(--danger)', marginBottom: 'var(--space-6)' }}>
          <div className="card-head">
            <div className="card-title" style={{ color: 'var(--danger)' }}>
              <AlertTriangle size={20} style={{ display: 'inline', marginRight: 'var(--space-2)' }} />
              Entry Halted
            </div>
            <div className="card-sub">Reasons for trading halt</div>
          </div>
          <div className="card-body">
            {policy.halt_reasons.map((reason, idx) => (
              <div key={idx} style={{ marginBottom: idx < policy.halt_reasons.length - 1 ? 'var(--space-2)' : 0 }}>
                <div style={{ fontSize: 'var(--t-sm)', color: 'var(--text-secondary)' }}>
                  • {reason}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* All Tiers Reference */}
      {policy.all_tiers && Array.isArray(policy.all_tiers) && (
        <div className="card">
          <div className="card-head">
            <div className="card-title">Exposure Tiers</div>
            <div className="card-sub">Entry rules by market regime</div>
          </div>
          <div className="card-body">
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-4)' }}>
              {policy.all_tiers.map((tier, idx) => (
                <div
                  key={idx}
                  style={{
                    padding: 'var(--space-3)',
                    borderRadius: 'var(--r-sm)',
                    backgroundColor: 'var(--surface-2)',
                    borderLeft: `3px solid ${getTierColor(tier.name)}`,
                  }}
                >
                  <div style={{ fontSize: 'var(--t-sm)', fontWeight: 'var(--w-bold)', color: getTierColor(tier.name), marginBottom: 'var(--space-2)' }}>
                    {getTierLabel(tier.name).label}
                  </div>
                  {tier.description && (
                    <div style={{ fontSize: 'var(--t-xs)', color: 'var(--text-secondary)', marginBottom: 'var(--space-2)', lineHeight: 1.5 }}>
                      {tier.description}
                    </div>
                  )}
                  {tier.threshold !== undefined && (
                    <div style={{ fontSize: 'var(--t-xs)', color: 'var(--text-secondary)' }}>
                      <strong>Condition:</strong> {typeof tier.threshold === 'number' ? tier.threshold.toFixed(2) : tier.threshold}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Last Update */}
      {policy.as_of && (
        <div style={{ marginTop: 'var(--space-6)', textAlign: 'center', color: 'var(--text-secondary)', fontSize: 'var(--t-xs)' }}>
          Last updated: {new Date(policy.as_of).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' })}
        </div>
      )}
    </div>
  );
};

export default ExposurePolicy;

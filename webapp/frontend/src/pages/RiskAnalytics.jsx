/**
 * Risk Analytics — Portfolio risk metrics and analysis
 *
 * Displays:
 * - Value at Risk (VaR) metrics at 95% confidence
 * - Portfolio beta and concentration risk
 * - Stressed scenarios
 */

import React from 'react';
import { Shield, AlertTriangle } from 'lucide-react';
import { useApiQuery } from '../hooks/useApiQuery';
import { SkeletonKpi } from '../components/Skeleton';
import { api } from '../services/api';

const RiskAnalytics = () => {
  const { data: riskMetrics, loading: isLoading, error } = useApiQuery(
    ['risk-metrics'],
    () => api.get('/api/algo/risk-metrics')
  );

  if (isLoading) {
    return (
      <div className="main-content">
        <div className="page-head">
          <div>
            <div className="page-head-title">Risk Analytics</div>
            <div className="page-head-sub">Portfolio risk metrics and stress scenarios</div>
          </div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-6)' }}>
          <SkeletonKpi />
          <SkeletonKpi />
          <SkeletonKpi />
          <SkeletonKpi />
        </div>
      </div>
    );
  }

  const metrics = riskMetrics?.data || riskMetrics || {};
  const hasData = metrics.var_pct_95 !== null && metrics.var_pct_95 !== undefined;

  return (
    <div className="main-content">
      <div className="page-head">
        <div>
          <div className="page-head-title">Risk Analytics</div>
          <div className="page-head-sub">Portfolio risk metrics and stress scenarios</div>
        </div>
      </div>

      {error && (
        <div className="alert alert-warning" style={{ marginBottom: 'var(--space-6)' }}>
          <AlertTriangle size={20} style={{ marginRight: 'var(--space-2)' }} />
          {error.message || 'Failed to load risk metrics'}
        </div>
      )}

      {!hasData && !error && (
        <div className="alert alert-info" style={{ marginBottom: 'var(--space-6)' }}>
          <Shield size={20} style={{ marginRight: 'var(--space-2)' }} />
          Risk metrics are not yet available. Data will appear after sufficient trading history.
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-6)' }}>
        {/* Value at Risk (95%) */}
        <div className="card">
          <div className="card-head">
            <div className="card-title">Value at Risk (95%)</div>
            <div className="card-sub">Maximum expected loss at 95% confidence</div>
          </div>
          <div className="card-body">
            <div style={{ fontSize: 'var(--t-2xl)', fontWeight: 'var(--w-bold)', color: 'var(--danger)', marginBottom: 'var(--space-3)' }}>
              {metrics.var_pct_95 !== null && metrics.var_pct_95 !== undefined
                ? `${Math.abs(metrics.var_pct_95).toFixed(2)}%`
                : '—'}
            </div>
            <div style={{ fontSize: 'var(--t-sm)', color: 'var(--text-secondary)' }}>
              The portfolio could lose this much in the worst 5% of scenarios
            </div>
          </div>
        </div>

        {/* Conditional Value at Risk (95%) */}
        <div className="card">
          <div className="card-head">
            <div className="card-title">Conditional VaR (95%)</div>
            <div className="card-sub">Expected loss beyond VaR threshold</div>
          </div>
          <div className="card-body">
            <div style={{ fontSize: 'var(--t-2xl)', fontWeight: 'var(--w-bold)', color: 'var(--danger)', marginBottom: 'var(--space-3)' }}>
              {metrics.cvar_pct_95 !== null && metrics.cvar_pct_95 !== undefined
                ? `${Math.abs(metrics.cvar_pct_95).toFixed(2)}%`
                : '—'}
            </div>
            <div style={{ fontSize: 'var(--t-sm)', color: 'var(--text-secondary)' }}>
              Average loss when VaR threshold is breached (tail risk)
            </div>
          </div>
        </div>

        {/* Stressed VaR */}
        <div className="card">
          <div className="card-head">
            <div className="card-title">Stressed VaR</div>
            <div className="card-sub">Risk under adverse market conditions</div>
          </div>
          <div className="card-body">
            <div style={{ fontSize: 'var(--t-2xl)', fontWeight: 'var(--w-bold)', color: 'var(--danger)', marginBottom: 'var(--space-3)' }}>
              {metrics.stressed_var_pct !== null && metrics.stressed_var_pct !== undefined
                ? `${Math.abs(metrics.stressed_var_pct).toFixed(2)}%`
                : '—'}
            </div>
            <div style={{ fontSize: 'var(--t-sm)', color: 'var(--text-secondary)' }}>
              Potential loss under stress scenarios (market crash, liquidity crisis)
            </div>
          </div>
        </div>

        {/* Portfolio Beta */}
        <div className="card">
          <div className="card-head">
            <div className="card-title">Portfolio Beta</div>
            <div className="card-sub">Systematic risk relative to S&P 500</div>
          </div>
          <div className="card-body">
            <div style={{ fontSize: 'var(--t-2xl)', fontWeight: 'var(--w-bold)', color: metrics.portfolio_beta > 1 ? 'var(--danger)' : 'var(--success)', marginBottom: 'var(--space-3)' }}>
              {metrics.portfolio_beta !== null && metrics.portfolio_beta !== undefined
                ? metrics.portfolio_beta.toFixed(2)
                : '—'}
            </div>
            <div style={{ fontSize: 'var(--t-sm)', color: 'var(--text-secondary)' }}>
              {metrics.portfolio_beta > 1 ? 'More volatile than market' : metrics.portfolio_beta < 1 ? 'Less volatile than market' : 'Matches market volatility'}
            </div>
          </div>
        </div>

        {/* Top 5 Concentration Risk */}
        <div className="card">
          <div className="card-head">
            <div className="card-title">Top 5 Concentration</div>
            <div className="card-sub">Percentage in top 5 holdings</div>
          </div>
          <div className="card-body">
            <div style={{ fontSize: 'var(--t-2xl)', fontWeight: 'var(--w-bold)', color: metrics.top_5_concentration > 50 ? 'var(--danger)' : 'var(--success)', marginBottom: 'var(--space-3)' }}>
              {metrics.top_5_concentration !== null && metrics.top_5_concentration !== undefined
                ? `${metrics.top_5_concentration.toFixed(1)}%`
                : '—'}
            </div>
            <div style={{ fontSize: 'var(--t-sm)', color: 'var(--text-secondary)' }}>
              {metrics.top_5_concentration > 50 ? 'High concentration risk' : 'Healthy diversification'}
            </div>
          </div>
        </div>

        {/* Report Date */}
        <div className="card">
          <div className="card-head">
            <div className="card-title">Report Date</div>
            <div className="card-sub">Last update</div>
          </div>
          <div className="card-body">
            <div style={{ fontSize: 'var(--t-xl)', fontWeight: 'var(--w-semibold)', marginBottom: 'var(--space-3)' }}>
              {metrics.report_date
                ? new Date(metrics.report_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
                : '—'}
            </div>
            <div style={{ fontSize: 'var(--t-sm)', color: 'var(--text-secondary)' }}>
              Metrics computed at end of trading day
            </div>
          </div>
        </div>
      </div>

      {/* Guidance Section */}
      <div className="card" style={{ marginTop: 'var(--space-6)' }}>
        <div className="card-head">
          <div className="card-title">What These Metrics Mean</div>
        </div>
        <div className="card-body">
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-4)' }}>
            <div>
              <div style={{ fontWeight: 'var(--w-bold)', marginBottom: 'var(--space-2)' }}>Value at Risk (VaR)</div>
              <div style={{ fontSize: 'var(--t-sm)', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                The maximum loss expected 95% of the time. If VaR is 5%, there's a 5% chance of losing more than that in a given period.
              </div>
            </div>
            <div>
              <div style={{ fontWeight: 'var(--w-bold)', marginBottom: 'var(--space-2)' }}>Conditional VaR</div>
              <div style={{ fontSize: 'var(--t-sm)', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                When VaR is exceeded, how much worse could it get? Measures tail risk — the severity of worst-case scenarios.
              </div>
            </div>
            <div>
              <div style={{ fontWeight: 'var(--w-bold)', marginBottom: 'var(--space-2)' }}>Stressed VaR</div>
              <div style={{ fontSize: 'var(--t-sm)', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                Estimated loss during a crisis using historical stress scenarios. Shows how your portfolio performs when the market breaks.
              </div>
            </div>
            <div>
              <div style={{ fontWeight: 'var(--w-bold)', marginBottom: 'var(--space-2)' }}>Portfolio Beta</div>
              <div style={{ fontSize: 'var(--t-sm)', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                Beta &gt; 1 = more volatile than the market. Beta &lt; 1 = less volatile. Higher beta = higher risk but higher return potential.
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default RiskAnalytics;

/**
 * Swing Trading Algo Dashboard
 *
 * Focus: orchestrator run status, open positions (stops/targets/R), signal pipeline,
 * exposure, circuit breakers, config, compact performance snapshot.
 *
 * Portfolio deep analytics → /app/portfolio  |  Market internals → /app/markets
 * Trade history → /app/trades                |  Audit trail → /app/audit
 */

import React, { useState, useCallback, useMemo } from 'react';
import {
  Shield, RefreshCw, CheckCircle, XCircle, AlertTriangle,
} from 'lucide-react';
import { api } from '../services/api';
import { useApiQuery, useApiPaginatedQuery } from '../hooks/useApiQuery';
import { QuerySection } from '../components/QueryErrorBoundary';
import ErrorBoundary from '../components/ErrorBoundary';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip as RechartTooltip, ResponsiveContainer,
} from 'recharts';
import RiskTab from './components/RiskTab';
import PerformanceTab from './components/PerformanceTab';

// ============================================================================
// THEME / COLOR UTILITIES
// ============================================================================
const TOOLTIP_STYLE = {
  background: 'var(--surface)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--r-sm)',
  fontSize: 'var(--t-xs)',
  padding: 'var(--space-2) var(--space-3)',
};

const tierColor = (n) => ({
  confirmed_uptrend: 'var(--success)',
  healthy_uptrend: '#56b97a',
  pressure: 'var(--amber)',
  caution: 'var(--amber)',
  correction: 'var(--danger)',
}[n] || 'var(--text-muted)');

const SectionCard = ({ title, action, children, sx = {} }) => (
  <div className="card" style={{ marginBottom: 'var(--space-4)', ...sx }}>
    {title && (
      <div className="card-head">
        <div><div className="card-title">{title}</div></div>
        {action && <div className="card-actions">{action}</div>}
      </div>
    )}
    <div className="card-body">{children}</div>
  </div>
);

const Stat = ({ label, value, sub, color }) => (
  <div>
    <div className="t-2xs muted strong">{label}</div>
    <div className="mono tnum" style={{ color: color || 'var(--text-2)', fontSize: 'var(--t-lg)', fontWeight: 'var(--w-bold)', marginTop: 4 }}>{value}</div>
    {sub && <div className="t-2xs muted" style={{ marginTop: 4 }}>{sub}</div>}
  </div>
);

// ============================================================================
// LAST RUN SUMMARY
// ============================================================================
function LastRunSummary({ lastRun }) {
  if (!lastRun?.run_id) {
    return <div className="t-xs muted" style={{ marginTop: 'var(--space-3)' }}>No run data yet</div>;
  }

  const runAt = lastRun.run_at ? new Date(lastRun.run_at) : null;
  const ageMinutes = runAt ? Math.round((Date.now() - runAt.getTime()) / 60000) : null;
  const ageLabel = ageMinutes == null ? '—'
    : ageMinutes < 60 ? `${ageMinutes}m ago`
    : ageMinutes < 1440 ? `${Math.round(ageMinutes / 60)}h ago`
    : `${Math.round(ageMinutes / 1440)}d ago`;

  const Icon = lastRun.success && !lastRun.halted ? CheckCircle
    : lastRun.halted ? AlertTriangle
    : XCircle;
  const iconColor = lastRun.success && !lastRun.halted ? 'var(--success)'
    : lastRun.halted ? 'var(--amber)'
    : 'var(--danger)';
  const label = lastRun.success && !lastRun.halted ? 'COMPLETED'
    : lastRun.halted ? 'HALTED'
    : 'ERROR';

  const phases = (lastRun.phases || []).filter(p =>
    p.action_type?.startsWith('phase_') && !p.action_type.includes('pipeline_health')
  );
  const lastPhase = phases[phases.length - 1];

  return (
    <div style={{ marginTop: 'var(--space-3)' }}>
      <div className="flex items-center gap-2" style={{ marginBottom: 'var(--space-2)' }}>
        <Icon size={16} style={{ color: iconColor, flexShrink: 0 }} />
        <span className="mono t-xs strong" style={{ color: iconColor }}>{label}</span>
        <span className="t-2xs muted">{ageLabel}</span>
      </div>
      {lastPhase && (
        <div className="t-2xs muted" style={{ marginBottom: 'var(--space-1)' }}>
          Last: {lastPhase.action_type?.replace('phase_', 'P').replace(/_/g, ' ')}
        </div>
      )}
      <div className="t-2xs muted mono" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {lastRun.run_id}
      </div>
    </div>
  );
}

// ============================================================================
// MAIN COMPONENT
// ============================================================================
function AlgoTradingDashboardPage() {
  const [tab, setTab] = useState(0);
  const [autoRefresh, setAutoRefresh] = useState(true);

  const qOpts = { refetchInterval: autoRefresh ? 30000 : false };
  const adminOpts = { ...qOpts, retry: false };

  const { data: markets,         isLoading: mLoading,   error: err1,  refetch: r1  } = useApiQuery(['algo','markets'],        () => api.get('/api/algo/markets'), qOpts);
  const { items: scores,         isLoading: sLoading,   error: err2,  refetch: r2  } = useApiPaginatedQuery(['algo','scores'], () => api.get('/api/algo/swing-scores?limit=100'), qOpts);
  const { data: config,          isLoading: cLoading,   error: err5,  refetch: r5  } = useApiQuery(['algo','config'],          () => api.get('/api/algo/config'), adminOpts);
  const { data: dataStatus,      isLoading: dLoading,   error: err6,  refetch: r6  } = useApiQuery(['algo','data-status'],     () => api.get('/api/algo/data-status'), adminOpts);
  const { data: policy,          isLoading: poLoading,  error: err7,  refetch: r7  } = useApiQuery(['algo','policy'],          () => api.get('/api/algo/exposure-policy'), adminOpts);
  const { data: evaluated,       isLoading: evLoading,  error: err8,  refetch: r8  } = useApiQuery(['algo','evaluate'],        () => api.get('/api/algo/evaluate'), adminOpts);
  const { data: circuitBreakers, isLoading: cbLoading,  error: err11, refetch: r11 } = useApiQuery(['algo','circuit'],         () => api.get('/api/algo/circuit-breakers'), adminOpts);
  const { data: dataQuality,     isLoading: dqLoading,  error: err12, refetch: r12 } = useApiQuery(['algo','dq'],              () => api.get('/api/algo/data-quality'), adminOpts);
  const { data: rejectionFunnel, isLoading: rfLoading,  error: err13, refetch: r13 } = useApiQuery(['algo','funnel'],          () => api.get('/api/algo/rejection-funnel'), adminOpts);
  const { data: lastRun,                                error: err14, refetch: r14 } = useApiQuery(['algo','last-run'],        () => api.get('/api/algo/last-run'), adminOpts);
  const { data: positionsResp,   isLoading: posLoading, error: err15, refetch: r15 } = useApiQuery(['algo','positions'],       () => api.get('/api/algo/positions'), adminOpts);
  const { data: performance,                            error: err16, refetch: r16 } = useApiQuery(['algo','performance'],     () => api.get('/api/algo/performance'), adminOpts);
  const { data: algoStatus,                             error: err17, refetch: r17 } = useApiQuery(['algo','status'],          () => api.get('/api/algo/status'), adminOpts);
  const { items: equityCurve,                           error: err18, refetch: r18 } = useApiPaginatedQuery(['algo','equity'], () => api.get('/api/algo/equity-curve?limit=180'), adminOpts);

  const refetchAll = useCallback(() => {
    [r1,r2,r5,r6,r7,r8,r11,r12,r13,r14,r15,r16,r17,r18].forEach(fn => fn?.());
  }, [r1,r2,r5,r6,r7,r8,r11,r12,r13,r14,r15,r16,r17,r18]);

  const configMap = useMemo(() => {
    const items = config?.items || (Array.isArray(config) ? config : []);
    return items.reduce((acc, row) => { acc[row.key] = row; return acc; }, {});
  }, [config]);

  const positions = useMemo(() => {
    const raw = positionsResp?.items || (Array.isArray(positionsResp) ? positionsResp : []);
    return raw;
  }, [positionsResp]);

  const posFreshness = positionsResp?.data_freshness;

  const data = {
    scores:           scores || [],
    config:           configMap,
    dataStatus,
    policy,
    evaluated,
    circuitBreakers,
    dataQuality,
    rejectionFunnel,
    lastRun,
    positions,
    performance,
    algoStatus,
    equityCurve:      equityCurve || [],
  };

  const market = markets;

  // Aggregate position stats for KPI card
  const posStats = useMemo(() => {
    if (!positions.length) return { count: 0, totalValue: 0, unrealizedPnl: 0 };
    return {
      count: positions.length,
      totalValue: positions.reduce((s, p) => s + (Number(p.position_value) || 0), 0),
      unrealizedPnl: positions.reduce((s, p) => s + (Number(p.unrealized_pnl) || 0), 0),
    };
  }, [positions]);

  if (mLoading && !markets) {
    return (
      <div className="main-content">
        <div className="empty"><div className="empty-title">Loading…</div></div>
      </div>
    );
  }

  const allErrors = [err1,err2,err5,err6,err7,err8,err11,err12,err13,err14,err15,err16,err17,err18];
  const allErrorNames = ['markets','scores','config','data-status','policy','evaluate','circuit-breakers','data-quality','rejection-funnel','last-run','positions','performance','status','equity-curve'];
  const failedQueries = allErrorNames.filter((_, i) => allErrors[i]);

  return (
    <div className="main-content">
      {/* HEADER */}
      <div className="page-head">
        <div>
          <div className="page-head-title">Swing Trading Algo</div>
          <div className="page-head-sub">Pine signals · multi-factor scoring · composite exposure · hedge-fund discipline</div>
        </div>
        <div className="page-head-actions">
          {allErrors.some(Boolean) && (
            <span className="badge badge-danger" title={`Failed: ${failedQueries.join(', ')}`}>
              ⚠ {allErrors.filter(Boolean).length} source(s) failed
            </span>
          )}
          <span className={`badge ${data.dataStatus?.ready_to_trade ? 'badge-success' : 'badge-danger'}`}>
            {data.dataStatus?.ready_to_trade ? 'DATA READY' : 'DATA STALE'}
          </span>
          <button className="btn btn-outline btn-sm" onClick={refetchAll} disabled={mLoading} title="Refresh all data">
            <RefreshCw size={14} /> Refresh
          </button>
          <button className={`btn ${autoRefresh ? 'btn-primary' : 'btn-outline'} btn-sm`}
            onClick={() => setAutoRefresh(!autoRefresh)}>
            {autoRefresh ? 'AUTO 30s' : 'MANUAL'}
          </button>
        </div>
      </div>

      {/* ERROR ALERTS FOR FAILED QUERIES */}
      {failedQueries.length > 0 && (
        <div style={{ marginBottom: 'var(--space-4)', padding: 'var(--space-3)', background: 'rgba(239, 68, 68, 0.1)', border: '1px solid var(--danger)', borderRadius: 'var(--r-sm)' }}>
          <div className="flex gap-3 items-start">
            <AlertTriangle size={18} style={{ color: 'var(--danger)', flexShrink: 0, marginTop: 2 }} />
            <div>
              <div className="t-sm strong" style={{ color: 'var(--danger)', marginBottom: 4 }}>
                {failedQueries.length} data source{failedQueries.length === 1 ? '' : 's'} failed to load
              </div>
              <div className="t-xs muted">
                {failedQueries.join(', ')}. Some sections may be incomplete. Click "Refresh" to retry.
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TOP STRIP — 4 ALGO-SPECIFIC KPI CARDS */}
      <div className="grid grid-4" style={{ marginBottom: 'var(--space-4)' }}>

        {/* Card 1: Market Exposure + Tier */}
        <div className="card" style={{ background: tierColor(market?.active_tier?.name), color: 'white', border: 'none' }}>
          <div style={{ padding: 'var(--space-4)' }}>
            <div className="flex justify-between items-start">
              <div>
                <div className="eyebrow" style={{ color: 'rgba(255,255,255,0.85)' }}>Market Exposure</div>
                <div className="mono tnum" style={{ fontSize: 'var(--t-3xl)', fontWeight: 'var(--w-bold)', lineHeight: 1, marginTop: 8 }}>
                  {market?.current?.exposure_pct ?? '--'}<span style={{ fontSize: 'var(--t-lg)', marginLeft: 4 }}>%</span>
                </div>
                <div style={{ fontWeight: 'var(--w-semibold)', marginTop: 8, opacity: 0.95 }}>
                  {market?.active_tier?.name?.replace(/_/g, ' ').toUpperCase() || 'UNKNOWN'}
                </div>
                <div className="t-xs" style={{ opacity: 0.85, marginTop: 4 }}>
                  {market?.active_tier?.description}
                </div>
              </div>
              <Shield size={28} style={{ opacity: 0.7 }} />
            </div>
          </div>
        </div>

        {/* Card 2: Open Positions */}
        <div className="card">
          <div className="card-body">
            <div className="eyebrow">Open Positions</div>
            {posLoading && !posStats.count ? (
              <div className="t-xs muted" style={{ marginTop: 'var(--space-3)' }}>Loading…</div>
            ) : (
              <div style={{ marginTop: 'var(--space-3)' }}>
                <div className="mono tnum" style={{ fontSize: 'var(--t-3xl)', fontWeight: 'var(--w-bold)', lineHeight: 1, color: 'var(--text-2)' }}>
                  {posStats.count}
                </div>
                <div style={{ marginTop: 'var(--space-3)' }}>
                  <div className="flex justify-between" style={{ marginBottom: 'var(--space-2)' }}>
                    <span className="t-xs muted">Total value</span>
                    <span className="mono tnum t-xs">${posStats.totalValue.toLocaleString('en-US', { maximumFractionDigits: 0 })}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="t-xs muted">Unrealized P&L</span>
                    <span className={`mono tnum t-xs ${posStats.unrealizedPnl >= 0 ? 'up' : 'down'}`}>
                      {posStats.unrealizedPnl >= 0 ? '+' : ''}${posStats.unrealizedPnl.toLocaleString('en-US', { maximumFractionDigits: 0 })}
                    </span>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Card 3: Signal Pipeline Today */}
        <div className="card">
          <div className="card-body">
            <div className="eyebrow">Signal Pipeline</div>
            <div style={{ marginTop: 'var(--space-3)' }}>
              <div className="flex justify-between" style={{ marginBottom: 'var(--space-2)' }}>
                <span className="t-xs muted">Raw BUY signals</span>
                <span className="mono tnum t-xs">{data.evaluated?.candidates?.screened ?? '--'}</span>
              </div>
              <div className="flex justify-between" style={{ marginBottom: 'var(--space-2)' }}>
                <span className="t-xs muted">Passed all gates</span>
                <span className="mono tnum t-xs up">{(data.scores || []).filter(s => s.pass_gates).length}</span>
              </div>
              <div className="flex justify-between" style={{ marginBottom: 'var(--space-2)' }}>
                <span className="t-xs muted">Blocked / filtered</span>
                <span className="mono tnum t-xs muted">{(data.scores || []).filter(s => !s.pass_gates).length}</span>
              </div>
              <div className="flex justify-between">
                <span className="t-xs muted">Data ready</span>
                <span className={`mono tnum t-xs ${data.dataStatus?.ready_to_trade ? 'up' : 'down'}`}>
                  {data.dataStatus?.ready_to_trade ? 'YES' : 'NO'}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Card 4: Last Orchestrator Run */}
        <div className="card">
          <div className="card-body">
            <div className="eyebrow">Last Orchestrator Run</div>
            <LastRunSummary lastRun={data.lastRun} />
          </div>
        </div>
      </div>

      {/* ACCOUNT + PERFORMANCE STRIP */}
      {(data.algoStatus?.portfolio?.total_value > 0 || data.performance?.total_trades > 0) && (
        <div className="card" style={{ marginBottom: 'var(--space-4)' }}>
          <div className="card-body">
            <div className="flex gap-6 flex-wrap items-center">
              {/* Alpaca-sourced portfolio snapshot */}
              {data.algoStatus?.portfolio?.total_value > 0 && <>
                <div>
                  <div className="t-2xs muted strong">PORTFOLIO VALUE</div>
                  <div className="mono tnum" style={{ fontSize: 'var(--t-base)', fontWeight: 'var(--w-bold)', color: 'var(--text-2)' }}>
                    ${data.algoStatus.portfolio.total_value.toLocaleString('en-US', { maximumFractionDigits: 0 })}
                  </div>
                </div>
                <div style={{ width: 1, height: 28, background: 'var(--border)' }} />
                <div>
                  <div className="t-2xs muted strong">TODAY</div>
                  <div className={`mono tnum ${(data.algoStatus.portfolio.daily_return_pct || 0) >= 0 ? 'up' : 'down'}`} style={{ fontSize: 'var(--t-base)', fontWeight: 'var(--w-bold)' }}>
                    {(data.algoStatus.portfolio.daily_return_pct || 0) >= 0 ? '+' : ''}{(data.algoStatus.portfolio.daily_return_pct || 0).toFixed(2)}%
                  </div>
                </div>
                <div style={{ width: 1, height: 28, background: 'var(--border)' }} />
                <div>
                  <div className="t-2xs muted strong">UNREALIZED</div>
                  <div className={`mono tnum ${(data.algoStatus.portfolio.unrealized_pnl_pct || 0) >= 0 ? 'up' : 'down'}`} style={{ fontSize: 'var(--t-base)', fontWeight: 'var(--w-bold)' }}>
                    {(data.algoStatus.portfolio.unrealized_pnl_pct || 0) >= 0 ? '+' : ''}{(data.algoStatus.portfolio.unrealized_pnl_pct || 0).toFixed(2)}%
                  </div>
                </div>
                <div style={{ width: 1, height: 28, background: 'var(--border)' }} />
              </>}
              {/* Closed-trade stats */}
              {data.performance?.total_trades > 0 && <>
                <div>
                  <div className="t-2xs muted strong">WIN RATE</div>
                  <div className="mono tnum" style={{ fontSize: 'var(--t-base)', fontWeight: 'var(--w-bold)', color: data.performance.win_rate_pct >= 50 ? 'var(--success)' : 'var(--danger)' }}>
                    {data.performance.win_rate_pct}%
                  </div>
                </div>
                <div style={{ width: 1, height: 28, background: 'var(--border)' }} />
                <div>
                  <div className="t-2xs muted strong">TOTAL P&L</div>
                  <div className={`mono tnum ${data.performance.total_pnl_dollars >= 0 ? 'up' : 'down'}`} style={{ fontSize: 'var(--t-base)', fontWeight: 'var(--w-bold)' }}>
                    {data.performance.total_pnl_dollars >= 0 ? '+' : ''}${(data.performance.total_pnl_dollars || 0).toLocaleString('en-US', { maximumFractionDigits: 0 })}
                  </div>
                </div>
                <div style={{ width: 1, height: 28, background: 'var(--border)' }} />
                <div>
                  <div className="t-2xs muted strong">TRADES</div>
                  <div className="mono tnum" style={{ fontSize: 'var(--t-base)', fontWeight: 'var(--w-bold)' }}>
                    {data.performance.total_trades} <span className="t-2xs muted">({data.performance.winning_trades}W / {data.performance.losing_trades}L)</span>
                  </div>
                </div>
                <div style={{ width: 1, height: 28, background: 'var(--border)' }} />
                <div>
                  <div className="t-2xs muted strong">SHARPE</div>
                  <div className="mono tnum" style={{ fontSize: 'var(--t-base)', fontWeight: 'var(--w-bold)', color: data.performance.sharpe_annualized >= 1 ? 'var(--success)' : 'var(--amber)' }}>
                    {data.performance.sharpe_annualized ?? '—'}
                  </div>
                </div>
                <div style={{ width: 1, height: 28, background: 'var(--border)' }} />
                <div>
                  <div className="t-2xs muted strong">MAX DD</div>
                  <div className="mono tnum" style={{ fontSize: 'var(--t-base)', fontWeight: 'var(--w-bold)', color: data.performance.max_drawdown_pct > 20 ? 'var(--danger)' : data.performance.max_drawdown_pct > 10 ? 'var(--amber)' : 'var(--text-2)' }}>
                    {data.performance.max_drawdown_pct ?? '—'}%
                  </div>
                </div>
                <div style={{ width: 1, height: 28, background: 'var(--border)' }} />
                <div>
                  <div className="t-2xs muted strong">STREAK</div>
                  <div className={`mono tnum ${data.performance.current_streak >= 0 ? 'up' : 'down'}`} style={{ fontSize: 'var(--t-base)', fontWeight: 'var(--w-bold)' }}>
                    {data.performance.current_streak >= 0 ? `+${data.performance.current_streak} W` : `${Math.abs(data.performance.current_streak)} L`}
                  </div>
                </div>
                <div style={{ width: 1, height: 28, background: 'var(--border)' }} />
                <div>
                  <div className="t-2xs muted strong">EXPECTANCY</div>
                  <div className={`mono tnum ${data.performance.expectancy_r >= 0 ? 'up' : 'down'}`} style={{ fontSize: 'var(--t-base)', fontWeight: 'var(--w-bold)' }}>
                    {data.performance.expectancy_r >= 0 ? '+' : ''}{data.performance.expectancy_r ?? '—'}R
                  </div>
                </div>
              </>}
            </div>
          </div>
        </div>
      )}

      {/* HALT REASONS BANNER */}
      {market?.current?.halt_reasons?.length > 0 && (
        <div className="alert alert-warn" style={{ marginBottom: 'var(--space-4)' }}>
          <span className="mono tnum strong">ACTIVE EXPOSURE VETOES: {Array.isArray(market.current.halt_reasons) ? market.current.halt_reasons.join(' · ') : market.current.halt_reasons}</span>
        </div>
      )}

      {/* TABS */}
      <div className="card" style={{ overflow: 'hidden' }}>
        <div style={{ display: 'flex', borderBottom: '1px solid var(--border)', flexWrap: 'wrap' }}>
          {[
            { label: `SETUPS (${(data.scores || []).filter(s => s.pass_gates).length})`, errors: [err2, err8] },
            { label: `POSITIONS (${posStats.count})`, errors: [err15] },
            { label: 'PERFORMANCE', errors: [err16, err18] },
            { label: `RISK${data.circuitBreakers?.system_halted ? ' ⚠' : ''}`, errors: [err11] },
            { label: 'PIPELINE', errors: [err7, err12, err13] },
            { label: 'CONFIG', errors: [err5] },
          ].map((tab_cfg, i) => (
            <button key={i} type="button" onClick={() => setTab(i)} title={tab_cfg.errors.some(Boolean) ? 'Some data failed to load' : ''} style={{
              background: 'transparent',
              border: 'none',
              borderBottom: `2px solid ${tab === i ? 'var(--brand)' : 'transparent'}`,
              color: tab_cfg.errors.some(Boolean) ? 'var(--danger)' : (tab === i ? 'var(--brand)' : 'var(--text-muted)'),
              fontWeight: tab === i ? 'var(--w-semibold)' : 'var(--w-medium)',
              fontSize: 'var(--t-sm)',
              padding: 'var(--space-3) var(--space-4)',
              cursor: 'pointer',
              marginBottom: -1,
              opacity: tab_cfg.errors.some(Boolean) ? 0.8 : 1,
            }}>
              {tab_cfg.label}{tab_cfg.errors.some(Boolean) ? ' ⚠' : ''}
            </button>
          ))}
        </div>

        {tab === 0 && <SetupsTab scores={data.scores} evaluated={data.evaluated} error={err2 || err8} />}
        {tab === 1 && <PositionsTab positions={data.positions} priceFreshness={posFreshness} error={err15} loading={posLoading} />}
        {tab === 2 && <PerformanceTab performance={data.performance} equityCurve={data.equityCurve} />}
        {tab === 3 && (err11 ?
          <div style={{padding: 'var(--space-4)'}}><div className="alert alert-danger"><strong>Failed to load risk data:</strong> {err11?.message || 'Unknown error'}</div></div>
          : data.circuitBreakers ? <RiskTab circuitBreakers={data.circuitBreakers} markets={market} positions={data.positions} /> : <div style={{padding: 'var(--space-4)'}}><div className="alert alert-info">No circuit breaker data</div></div>
        )}
        {tab === 4 && <PipelineTab policy={data.policy} markets={market} dataQuality={data.dataQuality} dataStatus={data.dataStatus} rejectionFunnel={data.rejectionFunnel} circuitBreakers={data.circuitBreakers} lastRun={data.lastRun} error={err7 || err12 || err13 || err14} />}
        {tab === 5 && (err5 ?
          <div style={{padding: 'var(--space-4)'}}><div className="alert alert-danger"><strong>Failed to load config:</strong> {err5?.message || 'Unknown error'}</div></div>
          : data.config ? <ConfigTab config={data.config} /> : <div style={{padding: 'var(--space-4)'}}><div className="alert alert-info">No config data</div></div>
        )}
      </div>
    </div>
  );
}

// ============================================================================
// SETUPS TAB
// ============================================================================
function SetupsTab({ scores, evaluated, error }) {
  const [expandedRow, setExpandedRow] = useState(null);
  const passing = (scores || []).filter(s => s.pass_gates);
  const blocked = (scores || []).filter(s => !s.pass_gates);

  if (error) {
    return (
      <div style={{ padding: 'var(--space-4)' }}>
        <div className="alert alert-danger">
          <strong>Failed to load setup data:</strong> {error?.message || 'Unknown error'}
        </div>
      </div>
    );
  }

  return (
    <div style={{ padding: 'var(--space-4)' }}>
      <div className="flex gap-4 flex-wrap" style={{ marginBottom: 'var(--space-4)' }}>
        <Stat label="Raw Buy Signals" value={evaluated?.candidates?.screened || 0} />
        <Stat label="Passing Score" value={passing.length} color="var(--success)" />
        <Stat label="Blocked" value={blocked.length} color="var(--amber)" />
        <Stat label="Latest Date" value={scores?.[0]?.date || '—'} />
      </div>

      <div className="t-xs mono muted" style={{ marginBottom: 'var(--space-4)', display: 'block' }}>
        Weights: 25% setup · 20% trend · 20% momentum · 12% volume · 10% fundamentals · 8% sector · 5% multi-tf
      </div>

      <SectionCard title={`Top Setups (${passing.length})`}>
        <div style={{ overflowX: 'auto' }}>
          <table className="data-table">
            <thead>
              <tr>
                {['Sym', 'Grade', 'Score', 'Setup', 'Trend', 'Mom', 'Vol', 'Fund', 'Sec', 'MTF', 'Sector', 'Industry'].map(h => (
                  <th key={h} style={{ fontSize: 'var(--t-2xs)', letterSpacing: 0.8 }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {passing.map(s => (
                <React.Fragment key={s.symbol}>
                  <tr onClick={() => setExpandedRow(expandedRow === s.symbol ? null : s.symbol)} style={{ cursor: 'pointer' }}>
                    <td className="strong mono">{s.symbol}</td>
                    <td>
                      <span className={`badge ${s.grade?.startsWith('A') ? 'badge-success' : s.grade === 'B' ? 'badge-cyan' : s.grade === 'C' ? 'badge-amber' : 'badge'}`}
                        style={{ fontSize: 'var(--t-2xs)' }}>
                        {s.grade}
                      </span>
                    </td>
                    <td className="num strong mono">{(Number(s.swing_score) || 0).toFixed(1)}</td>
                    <ScoreCell value={(s.components || {}).setup} max={25} />
                    <ScoreCell value={(s.components || {}).trend} max={20} />
                    <ScoreCell value={(s.components || {}).momentum} max={20} />
                    <ScoreCell value={(s.components || {}).volume} max={12} />
                    <ScoreCell value={(s.components || {}).fundamentals} max={10} />
                    <ScoreCell value={(s.components || {}).sector} max={8} />
                    <ScoreCell value={(s.components || {}).multi_tf} max={5} />
                    <td className="t-xs">{s.sector || '—'}</td>
                    <td className="t-2xs muted">{s.industry || '—'}</td>
                  </tr>
                  {expandedRow === s.symbol && (
                    <tr style={{ background: 'var(--bg)' }}>
                      <td colSpan={12} style={{ padding: 'var(--space-4)', borderColor: 'var(--border)' }}>
                        <ScoreDetailExpanded details={s.details} symbol={s.symbol} />
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </div>
      </SectionCard>

      {blocked.length > 0 && (
        <SectionCard title={`Blocked Candidates (${blocked.length}) — Failed Hard Gates`}>
          <div style={{ overflowX: 'auto', maxHeight: 400, overflowY: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Fail Reason</th>
                  <th>Sector</th>
                </tr>
              </thead>
              <tbody>
                {blocked.map(s => (
                  <tr key={s.symbol}>
                    <td className="strong mono">{s.symbol}</td>
                    <td className="t-xs" style={{ color: 'var(--amber)' }}>{s.fail_reason}</td>
                    <td className="t-xs muted">{s.sector || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SectionCard>
      )}
    </div>
  );
}

const ScoreCell = ({ value, max }) => {
  const numValue = Number(value) || 0;
  const pct = max > 0 ? (numValue / max) : 0;
  const color = pct >= 0.7 ? 'var(--success)' : pct >= 0.4 ? 'var(--amber)' : 'var(--danger)';
  return (
    <td className="num mono tnum" style={{ color, fontSize: 'var(--t-xs)' }}>
      {numValue.toFixed(1)}
    </td>
  );
};

const ScoreDetailExpanded = ({ details, _symbol }) => {
  if (!details || typeof details !== 'object') return null;
  const ent = Object.entries(details).filter(([_, v]) => v != null);
  return (
    <div className="grid grid-2" style={{ gap: 'var(--space-4)' }}>
      {ent.map(([key, info]) => (
        <div key={key}>
          <div className="t-xs mono strong" style={{ color: 'var(--brand)' }}>
            {key.toUpperCase()}: {typeof info?.pts === 'number' ? info.pts.toFixed(1) : info?.pts ?? '—'} / {info?.max ?? '—'}
          </div>
          {info?.detail && (
            <div className="t-2xs muted mono" style={{ marginTop: 4 }}>
              {Object.entries(info.detail).filter(([k]) => !['pts', 'max'].includes(k))
                .map(([k, v]) => (
                  <div key={k}>{k}: {typeof v === 'object' ? JSON.stringify(v) : String(v)}</div>
                ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
};

// ============================================================================
// POSITIONS TAB — algo's live open book with risk management fields
// ============================================================================
function PositionsTab({ positions, priceFreshness, error, loading }) {
  const [expanded, setExpanded] = useState(null);

  if (error) {
    return (
      <div style={{ padding: 'var(--space-4)' }}>
        <div className="alert alert-danger">
          <strong>Failed to load positions:</strong> {error?.message || 'Unknown error'}
        </div>
      </div>
    );
  }

  if (loading && !positions?.length) {
    return <div style={{ padding: 'var(--space-4)' }}><div className="t-xs muted">Loading positions…</div></div>;
  }

  if (!positions?.length) {
    return (
      <div style={{ padding: 'var(--space-4)' }}>
        <div className="empty">
          <div className="empty-title">No open positions</div>
          <div className="empty-sub">The algo is flat — no active holdings</div>
        </div>
      </div>
    );
  }

  const totalValue = positions.reduce((s, p) => s + (Number(p.position_value) || 0), 0);
  const totalUnrealized = positions.reduce((s, p) => s + (Number(p.unrealized_pnl) || 0), 0);
  const totalRisk = positions.reduce((s, p) => s + (Number(p.open_risk_dollars) || 0), 0);

  const syncAge = priceFreshness?.last_updated
    ? (() => {
        const m = Math.round((Date.now() - new Date(priceFreshness.last_updated).getTime()) / 60000);
        return m < 60 ? `${m}m ago` : m < 1440 ? `${Math.round(m / 60)}h ago` : `${Math.round(m / 1440)}d ago`;
      })()
    : null;

  return (
    <div style={{ padding: 'var(--space-4)' }}>
      {/* Summary strip */}
      <div className="flex gap-6 flex-wrap items-end" style={{ marginBottom: 'var(--space-4)' }}>
        <Stat label="Positions" value={positions.length} />
        <Stat
          label="Total Value"
          value={`$${totalValue.toLocaleString('en-US', { maximumFractionDigits: 0 })}`}
        />
        <Stat
          label="Unrealized P&L"
          value={`${totalUnrealized >= 0 ? '+' : ''}$${totalUnrealized.toLocaleString('en-US', { maximumFractionDigits: 0 })}`}
          color={totalUnrealized >= 0 ? 'var(--success)' : 'var(--danger)'}
        />
        <Stat
          label="Open Risk $"
          value={`$${totalRisk.toLocaleString('en-US', { maximumFractionDigits: 0 })}`}
          color="var(--amber)"
          sub="to stop loss"
        />
        {syncAge && (
          <div className="t-2xs muted" style={{ marginLeft: 'auto' }}>
            Prices synced from Alpaca: <strong>{syncAge}</strong>
            {priceFreshness?.status === 'stale' && <span className="down" style={{ marginLeft: 4 }}>· STALE</span>}
          </div>
        )}
      </div>

      <div style={{ overflowX: 'auto' }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>Symbol</th>
              <th className="num">Entry</th>
              <th className="num">Current</th>
              <th className="num">P&L %</th>
              <th className="num">R-Mult</th>
              <th className="num">Stop</th>
              <th className="num">Dist%</th>
              <th className="num">T1→</th>
              <th className="num">T2→</th>
              <th className="num">Days</th>
              <th>Stage</th>
              <th>Sector</th>
            </tr>
          </thead>
          <tbody>
            {positions.map(p => {
              const pnlPct = Number(p.unrealized_pnl_pct) || 0;
              const rMult = Number(p.r_multiple);
              const distToStop = Number(p.distance_to_stop_pct);
              const stopWarning = !isNaN(distToStop) && distToStop < 3;
              const isExpanded = expanded === p.symbol;
              return (
                <React.Fragment key={p.symbol}>
                  <tr
                    onClick={() => setExpanded(isExpanded ? null : p.symbol)}
                    style={{ cursor: 'pointer' }}
                  >
                    <td className="strong mono">{p.symbol}</td>
                    <td className="num mono tnum t-xs">${Number(p.avg_entry_price || 0).toFixed(2)}</td>
                    <td className="num mono tnum t-xs">${Number(p.current_price || 0).toFixed(2)}</td>
                    <td className={`num mono tnum t-xs ${pnlPct >= 0 ? 'up' : 'down'}`}>
                      {pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%
                    </td>
                    <td className={`num mono tnum t-xs ${isNaN(rMult) ? '' : rMult >= 1 ? 'up' : rMult >= 0 ? '' : 'down'}`}>
                      {isNaN(rMult) ? '—' : `${rMult >= 0 ? '+' : ''}${rMult.toFixed(2)}R`}
                    </td>
                    <td className="num mono tnum t-xs">
                      {p.current_stop_price ? `$${Number(p.current_stop_price).toFixed(2)}` : '—'}
                    </td>
                    <td className={`num mono tnum t-xs ${stopWarning ? 'down' : ''}`} title={stopWarning ? 'Near stop!' : ''}>
                      {isNaN(distToStop) ? '—' : `${distToStop.toFixed(1)}%`}
                    </td>
                    <td className="num mono tnum t-xs muted">
                      {p.distance_to_t1_pct != null ? `+${Number(p.distance_to_t1_pct).toFixed(1)}%` : '—'}
                    </td>
                    <td className="num mono tnum t-xs muted">
                      {p.distance_to_t2_pct != null ? `+${Number(p.distance_to_t2_pct).toFixed(1)}%` : '—'}
                    </td>
                    <td className="num mono tnum t-xs">{p.days_since_entry ?? '—'}</td>
                    <td className="t-xs">
                      {p.weinstein_stage ? (
                        <span className={`badge ${p.weinstein_stage === 2 ? 'badge-success' : p.weinstein_stage === 1 ? 'badge-cyan' : p.weinstein_stage === 3 ? 'badge-amber' : 'badge-danger'}`}
                          style={{ fontSize: 'var(--t-2xs)' }}>
                          S{p.weinstein_stage}
                        </span>
                      ) : '—'}
                    </td>
                    <td className="t-xs muted">{p.sector || '—'}</td>
                  </tr>
                  {isExpanded && (
                    <tr style={{ background: 'var(--bg)' }}>
                      <td colSpan={12} style={{ padding: 'var(--space-4)', borderColor: 'var(--border)' }}>
                        <PositionDetail p={p} />
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function PositionDetail({ p }) {
  const fields = [
    ['Position Value', p.position_value != null ? `$${Number(p.position_value).toLocaleString('en-US', { maximumFractionDigits: 0 })}` : '—'],
    ['Shares / Qty', p.quantity ?? '—'],
    ['Unrealized P&L', p.unrealized_pnl != null ? `$${Number(p.unrealized_pnl).toFixed(2)}` : '—'],
    ['Open Risk $', p.open_risk_dollars != null ? `$${Number(p.open_risk_dollars).toFixed(2)}` : '—'],
    ['Original Stop', p.trade_stop_price != null ? `$${Number(p.trade_stop_price).toFixed(2)}` : '—'],
    ['Current Stop', p.current_stop_price != null ? `$${Number(p.current_stop_price).toFixed(2)}` : '—'],
    ['Target 1', p.target_1_price != null ? `$${Number(p.target_1_price).toFixed(2)}` : '—'],
    ['Target 2', p.target_2_price != null ? `$${Number(p.target_2_price).toFixed(2)}` : '—'],
    ['Target 3', p.target_3_price != null ? `$${Number(p.target_3_price).toFixed(2)}` : '—'],
    ['Levels Hit', p.target_levels_hit ?? 0],
    ['Exit Stage', p.stage_in_exit_plan ?? '—'],
    ['Dist-to-Stop', p.distance_to_stop_pct != null ? `${Number(p.distance_to_stop_pct).toFixed(2)}%` : '—'],
    ['52w Low', p.pct_from_52w_low != null ? `+${Number(p.pct_from_52w_low).toFixed(1)}%` : '—'],
    ['Trend Score', p.minervini_trend_score != null ? Number(p.minervini_trend_score).toFixed(1) : '—'],
    ['Distrib. Days', p.distribution_day_count ?? 0],
  ];
  return (
    <div className="grid grid-4" style={{ gap: 'var(--space-3)' }}>
      {fields.map(([label, val]) => (
        <div key={label}>
          <div className="t-2xs muted strong">{label.toUpperCase()}</div>
          <div className="mono t-xs" style={{ marginTop: 2, color: 'var(--text-2)' }}>{val}</div>
        </div>
      ))}
    </div>
  );
}

// ============================================================================
// PIPELINE TAB — live 7-phase orchestrator status + data loader health
// ============================================================================
function PipelineTab({ policy, _markets, dataQuality, dataStatus, rejectionFunnel, circuitBreakers, lastRun }) {
  const loaders = dataStatus?.sources || [];
  const funnelTiers = (rejectionFunnel && Array.isArray(rejectionFunnel.funnel) ? rejectionFunnel.funnel : [])
    .filter(f => f != null)
    .map(f => ({
      name: typeof f.stage === 'string' ? f.stage.replace('All Signals Generated', 'All Signals').replace('Passed Quality Filters', 'Quality OK').replace(/High-Quality.*/, 'SQS ≥ 60') : 'Unknown',
      pass: Number(f.count) || 0,
      reject: Number(f.rejection_count) || 0,
    }));
  const overallStatus = dataStatus?.ready_to_trade ? 'ok' : dataQuality?.accuracy_check === 'warning' ? 'warning' : 'error';
  const statusColor2 = overallStatus === 'ok' ? 'var(--success)' : overallStatus === 'warning' ? 'var(--amber)' : 'var(--danger)';

  const phaseStatusMap = {};
  if (lastRun?.phases) {
    for (const p of lastRun.phases) {
      const m = p.action_type?.match(/^phase_(\w+)_/);
      if (m) phaseStatusMap[m[1]] = p.status;
    }
  }
  const hasLastRun = !!lastRun?.run_id;
  const runAge = lastRun?.run_at
    ? Math.round((Date.now() - new Date(lastRun.run_at).getTime()) / 60000)
    : null;

  const phaseColor = (n) => {
    if (!hasLastRun) return overallStatus === 'ok' ? 'ok' : 'unknown';
    const s = phaseStatusMap[n];
    if (!s) return 'unknown';
    if (s === 'success') return 'ok';
    if (s === 'halt') return 'warn';
    if (s === 'warn' || s === 'skip' || s === 'error') return s === 'error' ? 'fail' : 'warn';
    return 'ok';
  };
  const phaseBadge = (n) => {
    if (!hasLastRun) return '—';
    const s = phaseStatusMap[n];
    if (!s) return '—';
    if (s === 'success') return '✓ OK';
    if (s === 'halt') return '⊘ HALT';
    if (s === 'warn' || s === 'skip') return '⚠ WARN';
    if (s === 'error') return '✗ ERR';
    return s;
  };
  const phaseBarColor = (n) => {
    const c = phaseColor(n);
    return c === 'ok' ? 'var(--success)' : c === 'warn' ? 'var(--amber)' : c === 'fail' ? 'var(--danger)' : 'var(--border)';
  };

  const PHASES = [
    { n: '1', name: 'Data Freshness', desc: 'Halt if SPY price / market health / trend template stale', mode: 'fail-closed' },
    { n: '2', name: 'Circuit Breakers', desc: 'Drawdown / daily loss / VIX / market stage / consec losses', mode: 'fail-closed' },
    { n: '3', name: 'Position Monitor', desc: 'Review open positions: hold / raise stop / early exit', mode: 'fail-open' },
    { n: '3b', name: 'Exposure Policy', desc: 'Tier-based stops, partial exits, force-exit losers', mode: 'fail-open' },
    { n: '4', name: 'Exit Execution', desc: 'Execute stops, T1/T2/T3 targets, time decay, RS-break', mode: 'fail-open' },
    { n: '4b', name: 'Pyramid Adds', desc: 'Add to winners at defined extension points', mode: 'fail-open' },
    { n: '5', name: 'Signal Generation', desc: `Pine BUYs → 6-tier filter → swing_score rank${rejectionFunnel?.summary?.total_initial ? ` · ${rejectionFunnel?.summary?.total_initial} signals` : ''}`, mode: 'fail-open' },
    { n: '6', name: 'Entry Execution', desc: 'Idempotent fills, tier caps, grade filter, sector limit', mode: 'fail-open' },
    { n: '7', name: 'Reconciliation', desc: 'Alpaca sync, P&L snapshot, attribution, weight tuning', mode: 'fail-open' },
  ];

  return (
    <div style={{ padding: 'var(--space-4)' }}>
      <div className="grid grid-2" style={{ gap: 'var(--space-4)' }}>
        {/* Phase status */}
        <SectionCard title={`Orchestrator Phases${hasLastRun && runAge != null ? ` — last run ${runAge < 60 ? `${runAge}m ago` : `${Math.round(runAge/60)}h ago`}` : ''}`}>
          {!hasLastRun && (
            <div className="t-xs muted" style={{ marginBottom: 'var(--space-3)' }}>
              No run history yet — statuses shown below are design-time defaults.
            </div>
          )}
          {PHASES.map(ph => {
            const color = phaseBarColor(ph.n);
            const badge = phaseBadge(ph.n);
            const badgeClass = phaseColor(ph.n) === 'ok' ? 'badge-success' : phaseColor(ph.n) === 'warn' ? 'badge-amber' : phaseColor(ph.n) === 'fail' ? 'badge-danger' : '';
            return (
              <div key={ph.n} style={{
                padding: 'var(--space-3)',
                marginBottom: 'var(--space-2)',
                background: 'var(--surface-2)',
                border: '1px solid var(--border)',
                borderLeft: `4px solid ${color}`,
                borderRadius: 'var(--r-md)',
              }}>
                <div className="flex justify-between items-center">
                  <div style={{ flex: 1 }}>
                    <div className="t-2xs strong mono" style={{ color: 'var(--brand)' }}>PHASE {ph.n}</div>
                    <div className="strong">{ph.name}</div>
                    <div className="t-2xs muted">{ph.desc}</div>
                  </div>
                  <div className="flex gap-2 items-center">
                    {hasLastRun && (
                      <span className={`badge ${badgeClass}`} style={{ fontSize: 'var(--t-2xs)', fontWeight: 'var(--w-bold)' }}>
                        {badge}
                      </span>
                    )}
                    <span className={`badge ${ph.mode === 'fail-closed' ? 'badge-danger' : ''}`}
                      style={{ fontSize: 'var(--t-2xs)' }}>
                      {ph.mode}
                    </span>
                  </div>
                </div>
              </div>
            );
          })}
        </SectionCard>

        <div>
          {/* Signal Rejection Funnel */}
          {funnelTiers.length > 0 && (
            <SectionCard title={`Signal Filter Funnel (${rejectionFunnel?.summary?.total_initial || 0} total)`} sx={{ marginBottom: 'var(--space-4)' }}>
              <div style={{ height: 160 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={funnelTiers} margin={{ top: 4, right: 12, bottom: 0, left: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border-soft)" />
                    <XAxis dataKey="name" tick={{ fill: 'var(--text-muted)', fontSize: 9 }} />
                    <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 10 }} />
                    <RechartTooltip
                      contentStyle={TOOLTIP_STYLE}
                      formatter={(v, n) => [v, n === 'pass' ? 'Pass' : 'Reject']}
                    />
                    <Bar dataKey="pass" fill="var(--success)" stackId="a" name="pass" />
                    <Bar dataKey="reject" fill="var(--danger)" stackId="a" name="reject" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </SectionCard>
          )}

          {/* Data Loader Status */}
          <SectionCard title="Data Loaders" action={
            <span className={`badge ${statusColor2 === 'var(--success)' ? 'badge-success' : statusColor2 === 'var(--amber)' ? 'badge-amber' : 'badge-danger'}`}
              style={{ fontSize: 'var(--t-2xs)' }}>
              {overallStatus.toUpperCase()}
            </span>
          }>
            {loaders.length === 0 ? (
              <div className="t-xs muted">No loader data available</div>
            ) : (
              <div style={{ overflowX: 'auto', maxHeight: 280 }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Table</th>
                      <th className="num">Rows</th>
                      <th>Last Updated</th>
                      <th className="num">Age (h)</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {loaders.map((l, i) => {
                      const s = (l.status || 'unknown').toUpperCase();
                      const sc = s === 'OK' ? 'badge-success' : s === 'STALE' ? 'badge-amber' : 'badge-danger';
                      return (
                        <tr key={i}>
                          <td className="mono t-xs">{l.name}</td>
                          <td className="muted t-xs">{l.row_count?.toLocaleString() ?? '—'}</td>
                          <td className="mono t-xs">{l.last_updated ? new Date(l.last_updated).toLocaleDateString() : '—'}</td>
                          <td className={`num mono tnum t-xs ${l.age_hours > 72 ? 'down' : ''}`}>
                            {l.age_hours != null ? l.age_hours.toFixed(1) : '—'}
                          </td>
                          <td><span className={`badge ${sc}`} style={{ fontSize: 'var(--t-2xs)' }}>{s}</span></td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </SectionCard>

          {/* Exposure Policy Matrix */}
          <SectionCard title="Exposure Tier Policy Matrix" sx={{ marginTop: 'var(--space-4)' }}>
            <div className="t-xs muted" style={{ marginBottom: 'var(--space-3)' }}>
              Current exposure: {policy?.current_exposure_pct ?? '—'}% → tier <span style={{ color: 'var(--text-2)', fontWeight: 'var(--w-bold)' }}>{policy?.active_tier?.name?.toUpperCase()}</span>
            </div>
            <div style={{ overflowX: 'auto' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Tier</th>
                    <th>Range</th>
                    <th>Risk</th>
                    <th>New/Day</th>
                    <th>Grade</th>
                    <th>Halt</th>
                  </tr>
                </thead>
                <tbody>
                  {(policy?.all_tiers || []).map(t => {
                    const isActive = t.name === policy?.active_tier?.name;
                    return (
                      <tr key={t.name} style={{ background: isActive ? 'var(--surface-2)' : '' }}>
                        <td className="strong mono t-xs" style={{ color: tierColor(t.name) }}>
                          {isActive && '▶ '}{t.name}
                        </td>
                        <td className="mono t-xs">{t.min_pct}-{t.max_pct}%</td>
                        <td className="mono t-xs">{t.risk_multiplier}x</td>
                        <td className="mono t-xs">{t.max_new_positions_today}</td>
                        <td>
                          <span className={`badge ${t.min_swing_grade?.startsWith('A') ? 'badge-success' : t.min_swing_grade === 'B' ? 'badge-cyan' : t.min_swing_grade === 'C' ? 'badge-amber' : 'badge'}`}
                            style={{ fontSize: 'var(--t-2xs)' }}>
                            {t.min_swing_grade}
                          </span>
                        </td>
                        <td className={`strong mono t-xs ${t.halt_new_entries ? 'down' : 'up'}`}>
                          {t.halt_new_entries ? 'HALT' : 'allow'}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </SectionCard>
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// CONFIG TAB
// ============================================================================
function ConfigTab({ config }) {
  if (!config) return <div style={{ padding: 'var(--space-3)' }}><div className="alert alert-info">Config not loaded</div></div>;
  const entries = Object.entries(config).sort((a, b) => a[0].localeCompare(b[0]));
  return (
    <div style={{ padding: 'var(--space-3)' }}>
      <div className="t-xs muted" style={{ marginBottom: 'var(--space-3)', display: 'block' }}>
        {entries.length} configuration parameters · all hot-reload via /api/algo/config/:key
      </div>
      <div className="grid grid-4" style={{ gap: 'var(--space-2)' }}>
        {entries.map(([key, val]) => (
          <div key={key} className="card" style={{ padding: 'var(--space-3)' }}>
            <div className="t-2xs muted strong" style={{ letterSpacing: '1px', marginBottom: 8 }}>
              {key.toUpperCase()}
            </div>
            <div className="mono strong" style={{
              color: 'var(--text-2)', fontWeight: 'var(--w-bold)', fontSize: 'var(--t-base)',
              marginBottom: 8
            }}>
              {String(val.value)}
            </div>
            <div className="t-2xs muted">{val.description}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function AlgoTradingDashboard() {
  return (
    <ErrorBoundary>
      <AlgoTradingDashboardPage />
    </ErrorBoundary>
  );
}

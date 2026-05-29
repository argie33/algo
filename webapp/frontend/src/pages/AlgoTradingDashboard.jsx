/**
 * Swing Trading Algo Dashboard — Institutional Grade
 *
 * Tabs: Setups / Risk / Pipeline / Config
 * Markets → /app/markets  |  Positions → /app/portfolio
 * Trades → /app/trades    |  Audit → /app/audit
 */

import React, { useState, useCallback, useMemo } from 'react';
import {
  Shield, RefreshCw,
} from 'lucide-react';
import { api } from '../services/api';
import { useApiQuery, useApiPaginatedQuery } from '../hooks/useApiQuery';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip as RechartTooltip, ResponsiveContainer,
} from 'recharts';
import RiskTab from './components/RiskTab';
import { formatPercentageChange, formatNumber } from '../utils/formatters';

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


// Reusable styled card
const SectionCard = ({ title, action, children, sx = {} }) => (
  <div className="card" style={{ marginBottom: 'var(--space-4)', ...sx }}>
    {title && (
      <div className="card-head">
        <div>
          <div className="card-title">{title}</div>
        </div>
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
function AlgoTradingDashboard() {
  const [tab, setTab] = useState(0);
  const [autoRefresh, setAutoRefresh] = useState(true);

  const qOpts = { refetchInterval: autoRefresh ? 30000 : false };
  const adminOpts = { ...qOpts, retry: false }; // don't retry on 401/403

  // One hook per endpoint — React Query deduplicates and caches
  const { data: status,         isLoading: loading,   error: err0,  refetch: r0  } = useApiQuery(['algo','status'],        () => api.get('/api/algo/status'), qOpts);
  const { data: markets,        isLoading: mLoading,  error: err1,  refetch: r1  } = useApiQuery(['algo','markets'],        () => api.get('/api/algo/markets'), qOpts);
  const { items: scores,        isLoading: _sLoading, error: err2,  refetch: r2  } = useApiPaginatedQuery(['algo','scores'], () => api.get('/api/algo/swing-scores?limit=100'), qOpts);
  const { data: config,         isLoading: _cLoading, error: err5,  refetch: r5  } = useApiQuery(['algo','config'],         () => api.get('/api/algo/config'), qOpts);
  const { data: dataStatus,     isLoading: _dLoading, error: err6,  refetch: r6  } = useApiQuery(['algo','data-status'],    () => api.get('/api/algo/data-status'), qOpts);
  const { data: policy,         isLoading: _poLoading,error: err7,  refetch: r7  } = useApiQuery(['algo','policy'],         () => api.get('/api/algo/exposure-policy'), qOpts);
  const { data: evaluated,      isLoading: _evLoading,error: err8,  refetch: r8  } = useApiQuery(['algo','evaluate'],       () => api.get('/api/algo/evaluate'), qOpts);
  const { data: circuitBreakers,isLoading: _cbLoading,error: err11, refetch: r11 } = useApiQuery(['algo','circuit'],        () => api.get('/api/algo/circuit-breakers'), adminOpts);
  const { data: dataQuality,    isLoading: _dqLoading,error: err12, refetch: r12 } = useApiQuery(['algo','dq'],             () => api.get('/api/algo/data-quality'), qOpts);
  const { data: rejectionFunnel,isLoading: _rfLoading,error: err13, refetch: r13 } = useApiQuery(['algo','funnel'],         () => api.get('/api/algo/rejection-funnel'), qOpts);

  const refetchAll = useCallback(() => {
    [r0,r1,r2,r5,r6,r7,r8,r11,r12,r13].forEach(fn => fn?.());
  }, [r0,r1,r2,r5,r6,r7,r8,r11,r12,r13]);

  // Transform config from array [{key, value, ...}] to dict {key: {value, ...}}
  const configMap = useMemo(() => {
    const items = config?.items || (Array.isArray(config) ? config : []);
    return items.reduce((acc, row) => { acc[row.key] = row; return acc; }, {});
  }, [config]);

  // Stable data shape consumed by sub-components
  const data = {
    status,
    scores:           scores || [],
    config:           configMap,
    dataStatus,
    policy,
    evaluated,
    circuitBreakers,
    dataQuality,
    rejectionFunnel,
  };

  const portfolio = status?.portfolio || {};
  const market = markets;
  const openPositions = status?.portfolio?.open_positions ?? 0;

  if (loading && !status) {
    return (
      <div className="main-content">
        <div className="empty"><div className="empty-title">Loading…</div></div>
      </div>
    );
  }

  return (
    <div className="main-content">
      {/* HEADER */}
      <div className="page-head">
        <div>
          <div className="page-head-title">Swing Trading Algo</div>
          <div className="page-head-sub">Pine signals · multi-factor scoring · composite exposure · hedge-fund discipline</div>
        </div>
        <div className="page-head-actions">
          {[err0,err1,err2,err5,err6,err7,err8,err11,err12,err13].some(Boolean) && (
            <span className="badge badge-danger" title={`Failed: ${['status','markets','scores','config','data-status','policy','evaluate','circuit-breakers','data-quality','rejection-funnel']
              .filter((_, i) => [err0,err1,err2,err5,err6,err7,err8,err11,err12,err13][i])
              .join(', ')}`}>
              ⚠ {[err0,err1,err2,err5,err6,err7,err8,err11,err12,err13].filter(Boolean).length} data source(s) failed
            </span>
          )}
          <span className={`badge ${data.dataStatus?.ready_to_trade ? 'badge-success' : 'badge-danger'}`}>
            {data.dataStatus?.ready_to_trade ? 'DATA READY' : 'DATA STALE'}
          </span>
          <button className="btn btn-outline btn-sm" onClick={refetchAll} disabled={loading || mLoading} title="Refresh all data">
            <RefreshCw size={14} /> Refresh
          </button>
          <button className={`btn ${autoRefresh ? 'btn-primary' : 'btn-outline'} btn-sm`}
            onClick={() => setAutoRefresh(!autoRefresh)}>
            {autoRefresh ? 'AUTO 30s' : 'MANUAL'}
          </button>
        </div>
      </div>

      {/* TOP STRIP — 4 KPI CARDS */}
      <div className="grid grid-4" style={{ marginBottom: 'var(--space-4)' }}>
        <div className="card" style={{ background: tierColor(market?.active_tier?.name), color: 'white', border: 'none' }}>
          <div style={{ padding: 'var(--space-4)' }}>
            <div className="flex justify-between items-start">
              <div>
                <div className="eyebrow" style={{ color: 'rgba(255,255,255,0.85)', opacity: 0.85 }}>Market Exposure</div>
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

        <div className="card">
          <div className="card-body">
            <Stat label="Portfolio Value"
              value={`$${(portfolio.total_value || 0).toLocaleString()}`}
              sub={
                <span style={{
                  color: (Number(portfolio.unrealized_pnl_pct) || 0) >= 0 ? 'var(--success)' : 'var(--danger)',
                  fontWeight: 'var(--w-semibold)',
                }}>
                  {formatPercentageChange(portfolio.unrealized_pnl_pct)} unrealized
                </span>
              }
            />
            <div style={{ height: 1, background: 'var(--border)', margin: 'var(--space-3) 0' }} />
            <div className="flex gap-4">
              <Stat label="Daily" value={
                <span style={{ color: (Number(portfolio.daily_return_pct) || 0) >= 0 ? 'var(--success)' : 'var(--danger)' }}>
                  {formatPercentageChange(portfolio.daily_return_pct)}
                </span>
              } />
              <Stat label="Positions" value={`${openPositions}/${data.config?.max_positions?.value || 6}`} />
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-body">
            <div className="eyebrow">Active Tier Policy</div>
            <div style={{ marginTop: 'var(--space-3)' }}>
              <div className="flex justify-between" style={{ marginBottom: 'var(--space-2)' }}>
                <span className="t-xs muted">Risk multiplier</span>
                <span className="mono tnum t-xs">{market?.active_tier?.risk_mult ?? '--'}x</span>
              </div>
              <div className="flex justify-between" style={{ marginBottom: 'var(--space-2)' }}>
                <span className="t-xs muted">Max new / day</span>
                <span className="mono tnum t-xs">{market?.active_tier?.max_new ?? '--'}</span>
              </div>
              <div className="flex justify-between" style={{ marginBottom: 'var(--space-2)' }}>
                <span className="t-xs muted">Min grade</span>
                <span className={`badge ${market?.active_tier?.min_grade?.startsWith('A') ? 'badge-success' : market?.active_tier?.min_grade === 'B' ? 'badge-cyan' : market?.active_tier?.min_grade === 'C' ? 'badge-amber' : 'badge'}`}
                  style={{ fontSize: 'var(--t-2xs)' }}>
                  {market?.active_tier?.min_grade || '--'}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="t-xs muted">Entries</span>
                <span className={`mono tnum t-xs ${market?.active_tier?.halt ? 'down' : 'up'}`}>
                  {market?.active_tier?.halt ? 'HALTED' : 'ALLOWED'}
                </span>
              </div>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-body">
            <div className="eyebrow">Market Internals</div>
            <div style={{ marginTop: 'var(--space-3)' }}>
              <div className="flex justify-between" style={{ marginBottom: 'var(--space-2)' }}>
                <span className="t-xs muted">Distribution days (4w)</span>
                <span className={`mono tnum t-xs ${
                  market?.current?.distribution_days >= 5 ? 'down' :
                  market?.current?.distribution_days >= 4 ? '' : 'up'
                }`}>
                  {market?.current?.distribution_days ?? '--'}
                </span>
              </div>
              <div className="flex justify-between" style={{ marginBottom: 'var(--space-2)' }}>
                <span className="t-xs muted">Trend</span>
                <span className="mono tnum t-xs">{market?.market_health?.market_trend || '--'}</span>
              </div>
              <div className="flex justify-between" style={{ marginBottom: 'var(--space-2)' }}>
                <span className="t-xs muted">Stage</span>
                <span className="mono tnum t-xs">{market?.market_health?.market_stage || '--'}</span>
              </div>
              <div className="flex justify-between">
                <span className="t-xs muted">VIX</span>
                <span className="mono tnum t-xs">{market?.market_health?.vix_level ?? '--'}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* HALT REASONS BANNER */}
      {market?.current?.halt_reasons && (
        <div className="alert alert-warn" style={{ marginBottom: 'var(--space-4)' }}>
          <span className="mono tnum strong">ACTIVE EXPOSURE VETOES: {market.current.halt_reasons}</span>
        </div>
      )}

      {/* TABS */}
      <div className="card" style={{ overflow: 'hidden' }}>
        <div style={{ display: 'flex', borderBottom: '1px solid var(--border)', flexWrap: 'wrap' }}>
          {[
            { label: `SETUPS (${(data.scores || []).filter(s => s.pass_gates).length})`, errors: [err2, err8] },
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
        {tab === 1 && (err11 ?
          <div style={{padding: 'var(--space-4)'}}><div className="alert alert-danger"><strong>Failed to load risk data:</strong> {err11?.message || 'Unknown error'}</div></div>
          : data.circuitBreakers ? <RiskTab circuitBreakers={data.circuitBreakers} markets={market} positions={[]} /> : <div style={{padding: 'var(--space-4)'}}><div className="alert alert-info">No circuit breaker data</div></div>
        )}
        {tab === 2 && <PipelineTab policy={data.policy} markets={market} dataQuality={data.dataQuality} dataStatus={data.dataStatus} rejectionFunnel={data.rejectionFunnel} circuitBreakers={data.circuitBreakers} error={err7 || err12 || err13} />}
        {tab === 3 && (err5 ?
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
        <Stat label="Raw Buy Signals" value={evaluated?.total_buy_signals || 0} />
        <Stat label="Passing Score" value={passing.length} color="var(--success)" />
        <Stat label="Blocked" value={blocked.length} color="var(--amber)" />
        <Stat label="Latest Date" value={scores?.[0]?.eval_date || '—'} />
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
                    <ScoreCell value={s.components.setup} max={25} />
                    <ScoreCell value={s.components.trend} max={20} />
                    <ScoreCell value={s.components.momentum} max={20} />
                    <ScoreCell value={s.components.volume} max={12} />
                    <ScoreCell value={s.components.fundamentals} max={10} />
                    <ScoreCell value={s.components.sector} max={8} />
                    <ScoreCell value={s.components.multi_tf} max={5} />
                    <td className="t-xs">{s.sector}</td>
                    <td className="t-2xs muted">{s.industry}</td>
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
        <SectionCard title={`Blocked Candidates (${blocked.length}) — Failed Hard Gates`} style={{ marginTop: 'var(--space-4)' }}>
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
                    <td className="t-xs muted">{s.sector}</td>
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
  if (!details) return null;
  const ent = Object.entries(details);
  return (
    <div className="grid grid-2" style={{ gap: 'var(--space-4)' }}>
      {ent.map(([key, info]) => (
        <div key={key}>
          <div className="t-xs mono strong" style={{ color: 'var(--brand)' }}>
            {key.toUpperCase()}: {info?.pts?.toFixed?.(1) ?? '—'} / {info?.max ?? '—'}
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
// PIPELINE TAB — live 7-phase orchestrator status + data loader health
// ============================================================================
function PipelineTab({ policy, _markets, dataQuality, dataStatus, rejectionFunnel, circuitBreakers }) {
  const loaders = dataStatus?.sources || [];
  const funnelTiers = rejectionFunnel?.tiers || [];
  const overallStatus = dataStatus?.ready_to_trade ? 'ok' : dataQuality?.accuracy_check === 'warning' ? 'warning' : 'error';
  const statusColor2 = overallStatus === 'ok' ? 'var(--success)' : overallStatus === 'warning' ? 'var(--amber)' : 'var(--danger)';

  const PHASES = [
    { n: '1', name: 'Data Freshness', desc: 'Halt if any CRITICAL data > 7d stale', mode: 'fail-closed',
      live: overallStatus === 'ok' ? 'ok' : overallStatus === 'warning' ? 'warn' : 'fail' },
    { n: '2', name: 'Circuit Breakers', desc: 'Drawdown / consec losses / VIX / breadth / data', mode: 'fail-closed',
      live: circuitBreakers?.system_halted ? 'fail' : 'ok' },
    { n: '3', name: 'Position Monitor', desc: 'RS, sector, time decay, earnings — flag for action', mode: 'fail-open', live: 'ok' },
    { n: '3b', name: 'Exposure Policy', desc: 'Tier-based stops, partials, force-exit losers', mode: 'fail-open', live: 'ok' },
    { n: '4', name: 'Exit Execution', desc: 'Stops, T1/T2/T3, time, TD, RS-break, distribution', mode: 'fail-open', live: 'ok' },
    { n: '5', name: 'Signal Generation', desc: `Pine BUYs â†’ 6 tiers â†’ swing_score ranking${rejectionFunnel?.total_signals ? ` · ${rejectionFunnel.total_signals} signals` : ''}`, mode: 'fail-open', live: 'ok' },
    { n: '6', name: 'Entry Execution', desc: 'Idempotent fills, tier caps, grade filter', mode: 'fail-open', live: 'ok' },
    { n: '7', name: 'Reconciliation', desc: 'Alpaca sync, P&L, snapshot, audit trail', mode: 'fail-open', live: 'ok' },
  ];

  const liveColor = (s) => s === 'ok' ? 'var(--success)' : s === 'warn' ? 'var(--amber)' : 'var(--danger)';

  return (
    <div style={{ padding: 'var(--space-4)' }}>
      <div className="grid grid-2" style={{ gap: 'var(--space-4)' }}>
        {/* Phase status */}
        <SectionCard title="7-Phase Daily Workflow — Live Status">
          {PHASES.map(ph => (
            <div key={ph.n} style={{
              padding: 'var(--space-3)',
              marginBottom: 'var(--space-2)',
              background: 'var(--surface-2)',
              border: `1px solid var(--border)`,
              borderLeft: `4px solid ${liveColor(ph.live)}`,
              borderRadius: 'var(--r-md)',
            }}>
              <div className="flex justify-between items-center">
                <div style={{ flex: 1 }}>
                  <div className="t-2xs strong mono" style={{ color: 'var(--brand)' }}>PHASE {ph.n}</div>
                  <div className="strong">{ph.name}</div>
                  <div className="t-2xs muted">{ph.desc}</div>
                </div>
                <div className="flex gap-2 items-center">
                  <span className={`badge ${ph.live === 'ok' ? 'badge-success' : ph.live === 'warn' ? 'badge-amber' : 'badge-danger'}`}
                    style={{ fontSize: 'var(--t-2xs)', fontWeight: 'var(--w-bold)' }}>
                    {ph.live === 'ok' ? 'âœ“ OK' : ph.live === 'warn' ? '⚠ WARN' : 'âœ— FAIL'}
                  </span>
                  <span className={`badge ${ph.mode === 'fail-closed' ? 'badge-danger' : ''}`}
                    style={{ fontSize: 'var(--t-2xs)' }}>
                    {ph.mode}
                  </span>
                </div>
              </div>
            </div>
          ))}
        </SectionCard>

        <div>
          {/* Signal Rejection Funnel */}
          {funnelTiers.length > 0 && (
            <SectionCard title={`Signal Filter Funnel (${rejectionFunnel?.total_signals || 0} total)`} style={{ marginBottom: 'var(--space-4)' }}>
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
          <SectionCard title={`Data Loaders`} action={
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
          <SectionCard title="Exposure Tier Policy Matrix" style={{ marginTop: 'var(--space-4)' }}>
            <div className="t-xs muted" style={{ marginBottom: 'var(--space-3)' }}>
              Current exposure: {policy?.current_exposure_pct ?? '—'}% â†’ tier <span style={{ color: 'var(--text-2)', fontWeight: 'var(--w-bold)' }}>{policy?.active_tier?.name?.toUpperCase()}</span>
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
                          {isActive && 'â–¶ '}{t.name}
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

export default AlgoTradingDashboard;


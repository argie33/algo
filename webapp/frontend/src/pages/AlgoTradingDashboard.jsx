/**
 * Swing Trading Algo Dashboard — Institutional Grade
 *
 * Full data density, dark professional palette, every detail visible.
 * Tabs: Markets / Setups / Positions / Trades / Workflow / Data / Config
 */

import React, { useState, useCallback } from 'react';
import {
  TrendingUp, TrendingDown, CheckCircle, AlertTriangle, Shield,
  ChevronDown, ChevronUp, RefreshCw,
} from 'lucide-react';
import { api } from '../services/api';
import { useApiQuery, useApiPaginatedQuery } from '../hooks/useApiQuery';
import { DataStateManager, ErrorAlert } from '../components/DataStateManager';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip as RechartTooltip, ResponsiveContainer,
} from 'recharts';
import PerformanceTab from './components/PerformanceTab';
import RiskTab from './components/RiskTab';

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

const statusBg = (s) => ({
  ok: 'var(--success)',
  stale: 'var(--amber)',
  empty: 'var(--danger)',
  error: 'var(--danger)',
}[s] || 'var(--text-muted)');

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

const FactorBar = ({ label, pts, max, detail, expanded, onToggle }) => {
  const numPts = Number(pts) || 0;
  const pct = max > 0 ? (numPts / max * 100) : 0;
  const barColor = pct >= 70 ? 'var(--success)' : pct >= 40 ? 'var(--amber)' : 'var(--danger)';
  return (
    <div style={{ marginBottom: 12, cursor: 'pointer' }} onClick={onToggle}>
      <div className="flex justify-between items-center" style={{ marginBottom: 4 }}>
        <div className="flex items-center gap-2">
          {onToggle && (expanded ? <ChevronUp size={14} className="muted" /> : <ChevronDown size={14} className="muted" />)}
          <span className="t-xs strong">{label}</span>
        </div>
        <span className="mono tnum t-xs" style={{ color: barColor }}>{numPts.toFixed(1)} / {max}</span>
      </div>
      <div className="bar">
        <div className="bar-fill" style={{ width: `${pct}%`, background: barColor }} />
      </div>
      {expanded && (
        <div className="t-2xs muted mono" style={{ marginTop: 8, paddingLeft: 16 }}>
          {detail && Object.entries(detail).filter(([k]) => !['pts', 'max', 'score_factor'].includes(k))
            .map(([k, v]) => (
              <div key={k}>{k}: {typeof v === 'object' ? JSON.stringify(v) : String(v)}</div>
            ))}
        </div>
      )}
    </div>
  );
};

// ============================================================================
function AlgoTradingDashboard() {
  const [tab, setTab] = useState(0);
  const [autoRefresh, setAutoRefresh] = useState(true);

  const qOpts = { refetchInterval: autoRefresh ? 30000 : false };
  const adminOpts = { ...qOpts, retry: false }; // don't retry on 401/403

  // One hook per endpoint — React Query deduplicates and caches
  const { data: status,      isLoading: loading, error: err0,  refetch: r0  } = useApiQuery(['algo','status'],        () => api.get('/api/algo/status'), qOpts);
  const { data: markets,     isLoading: mLoading, error: err1, refetch: r1  } = useApiQuery(['algo','markets'],       () => api.get('/api/algo/markets'), qOpts);
  const { items: scores,     isLoading: sLoading, error: err2, refetch: r2  } = useApiPaginatedQuery(['algo','scores'],    () => api.get('/api/algo/swing-scores?limit=100'), qOpts);
  const { items: positions,  isLoading: pLoading, error: err3, refetch: r3  } = useApiPaginatedQuery(['algo','positions'], () => api.get('/api/algo/positions'), qOpts);
  const { items: trades,     isLoading: tLoading, error: err4, refetch: r4  } = useApiPaginatedQuery(['algo','trades'],    () => api.get('/api/algo/trades?limit=200'), qOpts);
  const { data: config,      isLoading: cLoading, error: err5, refetch: r5  } = useApiQuery(['algo','config'],        () => api.get('/api/algo/config'), qOpts);
  const { data: dataStatus,  isLoading: dLoading, error: err6, refetch: r6  } = useApiQuery(['algo','data-status'],   () => api.get('/api/algo/data-status'), qOpts);
  const { data: policy,      isLoading: poLoading,error: err7, refetch: r7  } = useApiQuery(['algo','policy'],        () => api.get('/api/algo/exposure-policy'), qOpts);
  const { data: evaluated,   isLoading: evLoading,error: err8, refetch: r8  } = useApiQuery(['algo','evaluate'],      () => api.get('/api/algo/evaluate'), qOpts);
  const { items: patrolLog,  isLoading: paLoading,error: err9, refetch: r9  } = useApiPaginatedQuery(['algo','patrol'],    () => api.get('/api/algo/patrol-log?limit=30&min_severity=info'), adminOpts);
  const { items: notifications,isLoading: nLoading,error: err10,refetch: r10 } = useApiPaginatedQuery(['algo','notifs'],    () => api.get('/api/algo/notifications'), qOpts);
  const { data: circuitBreakers,isLoading: cbLoading,error: err11,refetch: r11 } = useApiQuery(['algo','circuit'],       () => api.get('/api/algo/circuit-breakers'), adminOpts);
  const { data: dataQuality,  isLoading: dqLoading,error: err12,refetch: r12 } = useApiQuery(['algo','dq'],            () => api.get('/api/algo/data-quality'), qOpts);
  const { data: rejectionFunnel,isLoading: rfLoading,error: err13,refetch: r13 } = useApiQuery(['algo','funnel'],        () => api.get('/api/algo/rejection-funnel'), qOpts);

  const refetchAll = useCallback(() => {
    [r0,r1,r2,r3,r4,r5,r6,r7,r8,r9,r10,r11,r12,r13].forEach(fn => fn?.());
  }, [r0,r1,r2,r3,r4,r5,r6,r7,r8,r9,r10,r11,r12,r13]);

  // Stable data shape consumed by sub-components
  const data = {
    status,
    scores:        scores        || [],
    positions:     positions     || [],
    trades:        trades        || [],
    config,
    dataStatus,
    policy,
    evaluated,
    patrolLog:     patrolLog     || [],
    notifications: notifications || [],
    circuitBreakers,
    dataQuality,
    rejectionFunnel,
  };

  const portfolio = status?.portfolio || {};
  const market = markets;

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
          {[err0,err1,err2,err3,err4,err5,err6,err7,err8,err9,err10,err11,err12,err13].some(Boolean) && (
            <span className="badge badge-danger" title={`Failed: ${['status','markets','scores','positions','trades','config','data-status','policy','evaluate','patrol','notifications','circuit-breakers','data-quality','rejection-funnel']
              .filter((_, i) => [err0,err1,err2,err3,err4,err5,err6,err7,err8,err9,err10,err11,err12,err13][i])
              .join(', ')}`}>
              ⚠ {[err0,err1,err2,err3,err4,err5,err6,err7,err8,err9,err10,err11,err12,err13].filter(Boolean).length} data source(s) failed
            </span>
          )}
          <span className={`badge ${data.dataStatus?.ready_to_trade ? 'badge-success' : 'badge-danger'}`}>
            {data.dataStatus?.ready_to_trade ? 'DATA READY' : 'DATA STALE'}
          </span>
          <button className="btn btn-outline btn-sm" onClick={refetchAll} disabled={loading || mLoading}>
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
                  {(Number(portfolio.unrealized_pnl_pct) || 0) >= 0 ? '+' : ''}
                  {(Number(portfolio.unrealized_pnl_pct) || 0).toFixed(2)}% unrealized
                </span>
              }
            />
            <div style={{ height: 1, background: 'var(--border)', margin: 'var(--space-3) 0' }} />
            <div className="flex gap-4">
              <Stat label="Daily" value={
                <span style={{ color: (Number(portfolio.daily_return_pct) || 0) >= 0 ? 'var(--success)' : 'var(--danger)' }}>
                  {(Number(portfolio.daily_return_pct) || 0) >= 0 ? '+' : ''}{(Number(portfolio.daily_return_pct) || 0).toFixed(2)}%
                </span>
              } />
              <Stat label="Positions" value={`${data.positions?.length || 0}/${data.config?.max_positions?.value || 6}`} />
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
            { label: 'MARKETS', errors: [err1] },
            { label: `SETUPS (${(data.scores || []).filter(s => s.pass_gates).length})`, errors: [err2, err8] },
            { label: `POSITIONS (${data.positions?.length || 0})`, errors: [err3] },
            { label: `TRADES (${data.trades?.length || 0})`, errors: [err4] },
            { label: 'PERFORMANCE', errors: [] },
            { label: `RISK${data.circuitBreakers?.any_triggered ? ' ⚠' : ''}`, errors: [err11] },
            { label: 'AUDIT', errors: [] },
            { label: 'PIPELINE', errors: [err7, err12, err13] },
            { label: 'DATA HEALTH', errors: [err6, err9] },
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

        {tab === 0 && (err1 ?
          <div style={{padding: 'var(--space-4)'}}><div className="alert alert-danger"><strong>Failed to load markets data:</strong> {err1?.message || 'Unknown error'}</div></div>
          : market ? <MarketsTab markets={market} /> : <div style={{padding: 'var(--space-4)'}}><div className="alert alert-danger">No markets data available</div></div>
        )}
        {tab === 1 && <SetupsTab scores={data.scores} evaluated={data.evaluated} error={err2 || err8} />}
        {tab === 2 && (err3 ?
          <div style={{padding: 'var(--space-4)'}}><div className="alert alert-danger"><strong>Failed to load positions:</strong> {err3?.message || 'Unknown error'}</div></div>
          : data.positions ? <PositionsTab positions={data.positions} /> : <div style={{padding: 'var(--space-4)'}}><div className="alert alert-info">No active positions</div></div>
        )}
        {tab === 3 && (err4 ?
          <div style={{padding: 'var(--space-4)'}}><div className="alert alert-danger"><strong>Failed to load trades:</strong> {err4?.message || 'Unknown error'}</div></div>
          : data.trades ? <TradesTab trades={data.trades} /> : <div style={{padding: 'var(--space-4)'}}><div className="alert alert-info">No trades</div></div>
        )}
        {tab === 4 && <PerformanceTab performance={data.performance} equityCurve={data.equityCurve} />}
        {tab === 5 && (err11 ?
          <div style={{padding: 'var(--space-4)'}}><div className="alert alert-danger"><strong>Failed to load risk data:</strong> {err11?.message || 'Unknown error'}</div></div>
          : data.circuitBreakers ? <RiskTab circuitBreakers={data.circuitBreakers} markets={market} positions={data.positions} /> : <div style={{padding: 'var(--space-4)'}}><div className="alert alert-info">No circuit breaker data</div></div>
        )}
        {tab === 6 && <AuditTab auditLog={data.auditLog} />}
        {tab === 7 && <PipelineTab policy={data.policy} markets={market} dataQuality={data.dataQuality} rejectionFunnel={data.rejectionFunnel} circuitBreakers={data.circuitBreakers} error={err7 || err12 || err13} />}
        {tab === 8 && <DataStatusTab dataStatus={data.dataStatus} patrolLog={data.patrolLog} error={err6 || err9} />}
        {tab === 9 && (err5 ?
          <div style={{padding: 'var(--space-4)'}}><div className="alert alert-danger"><strong>Failed to load config:</strong> {err5?.message || 'Unknown error'}</div></div>
          : data.config ? <ConfigTab config={data.config} /> : <div style={{padding: 'var(--space-4)'}}><div className="alert alert-info">No config data</div></div>
        )}
      </div>
    </div>
  );
}

// ============================================================================
// MARKETS TAB
// ============================================================================
function MarketsTab({ markets }) {
  const [expanded, setExpanded] = useState({});
  const toggle = (k) => setExpanded(e => ({ ...e, [k]: !e[k] }));

  if (!markets) {
    return (
      <div style={{ padding: 'var(--space-4)' }}>
        <div className="alert alert-info">No markets data — run algo_market_exposure.py</div>
      </div>
    );
  }

  const factors = markets.current?.factors || {};
  const factorList = [
    ['ibd_state', 'MARKET STATE', 20],
    ['trend_30wk', 'TREND 30-WK MA', 15],
    ['breadth_50dma', 'BREADTH > 50-DMA', 15],
    ['breadth_200dma', 'BREADTH > 200-DMA', 10],
    ['vix_regime', 'VIX REGIME', 10],
    ['mcclellan', 'MCCLELLAN OSC', 10],
    ['new_highs_lows', 'NEW HIGHS / LOWS', 8],
    ['ad_line', 'A/D LINE', 7],
    ['aaii_sentiment', 'AAII SENTIMENT', 5],
  ];

  return (
    <div style={{ padding: 'var(--space-4)' }}>
      <div className="grid grid-2" style={{ gap: 'var(--space-4)', marginBottom: 'var(--space-4)' }}>
        {/* 9-FACTOR EXPOSURE BREAKDOWN */}
        <SectionCard title="9-Factor Exposure Composite" action={
          <div className="flex gap-2">
            <span className="badge mono tnum">{markets.current?.raw_score}</span>
            <span className="badge mono tnum" style={{ background: tierColor(markets.active_tier?.name), color: 'white' }}>
              {markets.current?.exposure_pct}%
            </span>
          </div>
        }>
          {factorList.map(([key, label, max]) => (
            <FactorBar
              key={key}
              label={label}
              pts={parseFloat(factors[key]?.pts || 0)}
              max={max}
              detail={factors[key]}
              expanded={expanded[key]}
              onToggle={() => toggle(key)}
            />
          ))}
        </SectionCard>

        {/* SECTOR RANKING */}
        <SectionCard title="Sector Strength (Today)">
          <div style={{ overflowX: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Sector</th>
                  <th className="num">Momentum</th>
                  <th className="num">1W Ago</th>
                  <th className="num">4W Ago</th>
                  <th className="num">12W</th>
                  <th className="num">Trend</th>
                </tr>
              </thead>
              <tbody>
                {(markets.sectors || []).map(s => {
                  const w1Delta = s.rank_1w_ago ? s.rank_1w_ago - s.rank : 0;
                  const w4Delta = s.rank_4w_ago ? s.rank_4w_ago - s.rank : 0;
                  return (
                    <tr key={s.name}>
                      <td className="mono tnum strong">#{s.rank}</td>
                      <td className="strong">{s.name}</td>
                      <td className={`num mono tnum ${s.momentum >= 0 ? 'up' : 'down'}`}>
                        {(Number(s.momentum) || 0) >= 0 ? '+' : ''}{(Number(s.momentum) || 0).toFixed(2)}
                      </td>
                      <td className="num mono tnum muted">{s.rank_1w_ago || '—'}</td>
                      <td className="num mono tnum muted">{s.rank_4w_ago || '—'}</td>
                      <td className="num mono tnum muted">{s.rank_12w_ago || '—'}</td>
                      <td className="num">
                        {w4Delta > 1 ? <TrendingUp size={16} className="up" style={{ display: 'inline' }} /> :
                          w4Delta < -1 ? <TrendingDown size={16} className="down" style={{ display: 'inline' }} /> :
                          <span className="muted">•</span>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </SectionCard>
      </div>

      <div className="grid grid-2" style={{ gap: 'var(--space-4)', marginBottom: 'var(--space-4)' }}>
        {/* AAII SENTIMENT */}
        <SectionCard title={`AAII Investor Sentiment (${(markets.sentiment || []).length} weeks)`}>
          <div style={{ overflowX: 'auto', maxHeight: 280, overflowY: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Week</th>
                  <th className="num">Bull %</th>
                  <th className="num">Bear %</th>
                  <th className="num">Neut %</th>
                  <th className="num">Spread</th>
                </tr>
              </thead>
              <tbody>
                {(markets.sentiment || []).map(s => {
                  const sp = (s.bullish || 0) - (s.bearish || 0);
                  return (
                    <tr key={s.date}>
                      <td className="mono tnum">{s.date}</td>
                      <td className="num mono tnum up">{(Number(s.bullish) || 0).toFixed(1)}</td>
                      <td className="num mono tnum down">{(Number(s.bearish) || 0).toFixed(1)}</td>
                      <td className="num mono tnum muted">{(Number(s.neutral) || 0).toFixed(1)}</td>
                      <td className={`num mono tnum ${(Number(sp) || 0) >= 0 ? 'up' : 'down'}`}>
                        {(Number(sp) || 0) >= 0 ? '+' : ''}{(Number(sp) || 0).toFixed(1)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </SectionCard>

        {/* HISTORY */}
        <SectionCard title={`Exposure History (${(markets.history || []).length} days)`}>
          <div style={{ maxHeight: 400, overflowY: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th className="num">Exposure</th>
                  <th className="num">DD</th>
                  <th>Regime</th>
                </tr>
              </thead>
              <tbody>
                {[...(markets.history || [])].reverse().map(h => (
                  <tr key={h.date}>
                    <td className="mono tnum">{h.date}</td>
                    <td className="num mono tnum strong" style={{ color: tierColor(h.regime) }}>
                      {h.exposure_pct?.toFixed(0)}%
                    </td>
                    <td className="num mono tnum">{h.distribution_days || 0}</td>
                    <td className="mono tnum" style={{ color: tierColor(h.regime), fontSize: 'var(--t-xs)' }}>
                      {h.regime}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SectionCard>
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

const ScoreDetailExpanded = ({ details, symbol }) => {
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
// POSITIONS TAB
// ============================================================================
function PositionsTab({ positions }) {
  if (!positions || positions.length === 0)
    return (
      <div style={{ padding: 'var(--space-4)' }}>
        <div className="alert alert-info">No active positions</div>
      </div>
    );
  return (
    <div style={{ padding: 'var(--space-4)' }}>
      <SectionCard title="Active Positions">
        <div style={{ overflowX: 'auto' }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th className="num">Qty</th>
                <th className="num">Entry</th>
                <th className="num">Current</th>
                <th className="num">Stop</th>
                <th className="num">Value</th>
                <th className="num">P&L $</th>
                <th className="num">P&L %</th>
                <th className="num">Days</th>
                <th className="num">Targets</th>
                <th>Stage</th>
              </tr>
            </thead>
            <tbody>
              {positions.map(p => {
                const pnlClass = p.unrealized_pnl >= 0 ? 'up' : 'down';
                return (
                  <tr key={p.position_id}>
                    <td className="strong mono">{p.symbol}</td>
                    <td className="num mono tnum">{p.quantity}</td>
                    <td className="num mono tnum">${(Number(p.avg_entry_price) || 0).toFixed(2)}</td>
                    <td className={`num strong mono tnum ${pnlClass}`}>${(Number(p.current_price) || 0).toFixed(2)}</td>
                    <td className="num mono tnum" style={{ color: 'var(--amber)' }}>
                      ${(Number(p.current_stop_price || p.stop_loss_price) || 0).toFixed(2)}
                    </td>
                    <td className="num mono tnum">${p.position_value?.toLocaleString()}</td>
                    <td className={`num strong mono tnum ${pnlClass}`}>
                      ${(Number(p.unrealized_pnl) || 0).toFixed(2)}
                    </td>
                    <td className={`num strong mono tnum ${pnlClass}`}>
                      {(Number(p.unrealized_pnl_pct) || 0).toFixed(2)}%
                    </td>
                    <td className="num mono tnum">{p.days_since_entry || 0}</td>
                    <td className="num mono tnum" style={{ color: 'var(--brand)' }}>
                      {p.target_levels_hit || 0}/3
                    </td>
                    <td className="t-xs muted">{p.stage_in_exit_plan || '—'}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </SectionCard>
    </div>
  );
}

// ============================================================================
// TRADES TAB
// ============================================================================
function TradesTab({ trades }) {
  if (!trades || trades.length === 0)
    return (
      <div style={{ padding: 'var(--space-4)' }}>
        <div className="alert alert-info">No trade history</div>
      </div>
    );

  const closed = trades.filter(t => t.status === 'closed');
  const wins = closed.filter(t => t.profit_loss_dollars > 0);
  const winRate = closed.length > 0 ? (wins.length / closed.length * 100).toFixed(1) : '0';
  const totalPnl = closed.reduce((s, t) => s + (parseFloat(t.profit_loss_dollars) || 0), 0);
  const avgR = closed.reduce((s, t) => s + (parseFloat(t.exit_r_multiple) || 0), 0) / Math.max(1, closed.length);

  return (
    <div style={{ padding: 'var(--space-4)' }}>
      <div className="flex gap-6 flex-wrap" style={{ marginBottom: 'var(--space-4)' }}>
        <Stat label="Closed Trades" value={closed.length} />
        <Stat label="Win Rate" value={`${winRate}%`} color={parseFloat(winRate) >= 50 ? 'var(--success)' : 'var(--danger)'} />
        <Stat label="Avg R" value={avgR.toFixed(2)} color={avgR > 0 ? 'var(--success)' : 'var(--danger)'} />
        <Stat label="Total P&L" value={`$${totalPnl.toFixed(2)}`}
          color={totalPnl >= 0 ? 'var(--success)' : 'var(--danger)'} />
      </div>

      <SectionCard title="Trade History">
        <div style={{ overflowX: 'auto', maxHeight: 600 }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th className="num">Date</th>
                <th className="num">Entry</th>
                <th className="num">Exit</th>
                <th className="num">P&L $</th>
                <th className="num">P&L %</th>
                <th className="num">R-Mult</th>
                <th className="num">Days</th>
                <th>Exit Reason</th>
                <th>Partial Chain</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {trades.map(t => {
                const pnlClass = t.profit_loss_dollars >= 0 ? 'up' : 'down';
                return (
                  <tr key={t.trade_id}>
                    <td className="strong mono">{t.symbol}</td>
                    <td className="num mono tnum muted t-xs">{t.trade_date}</td>
                    <td className="num mono tnum">${t.entry_price?.toFixed(2)}</td>
                    <td className={`num mono tnum ${t.exit_price ? '' : 'muted'}`}>
                      {t.exit_price ? `$${t.exit_price.toFixed(2)}` : '—'}
                    </td>
                    <td className={`num strong mono tnum ${pnlClass}`}>
                      ${t.profit_loss_dollars?.toFixed(2) || '—'}
                    </td>
                    <td className={`num mono tnum ${pnlClass}`}>
                      {t.profit_loss_pct?.toFixed(2)}%
                    </td>
                    <td className={`num strong mono tnum ${t.exit_r_multiple > 0 ? 'up' : t.exit_r_multiple < 0 ? 'down' : ''}`}>
                      {t.exit_r_multiple ? `${t.exit_r_multiple > 0 ? '+' : ''}${t.exit_r_multiple.toFixed(2)}R` : '—'}
                    </td>
                    <td className="num mono tnum">{t.trade_duration_days || 0}</td>
                    <td className="t-xs" style={{ maxWidth: 200 }}>{t.exit_reason || '—'}</td>
                    <td className="t-2xs mono" style={{ maxWidth: 280, whiteSpace: 'pre-wrap', color: 'var(--purple)' }}>
                      {t.partial_exits_log || '—'}
                    </td>
                    <td>
                      <span className={`badge ${t.status === 'closed' ? '' : 'badge-brand'}`} style={{ fontSize: 'var(--t-2xs)' }}>
                        {t.status}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </SectionCard>
    </div>
  );
}

// ============================================================================
// PIPELINE TAB — live 7-phase orchestrator status + data loader health
// ============================================================================
function PipelineTab({ policy, markets, dataQuality, rejectionFunnel, circuitBreakers }) {
  const loaders = dataQuality?.checks || [];
  const funnelTiers = rejectionFunnel?.tiers || [];
  const overallStatus = dataQuality?.status || 'unknown';
  const statusColor2 = overallStatus === 'ok' ? 'var(--success)' : overallStatus === 'warning' ? 'var(--amber)' : 'var(--danger)';

  const PHASES = [
    { n: '1', name: 'Data Freshness', desc: 'Halt if any CRITICAL data > 7d stale', mode: 'fail-closed',
      live: overallStatus === 'ok' ? 'ok' : overallStatus === 'warning' ? 'warn' : 'fail' },
    { n: '2', name: 'Circuit Breakers', desc: 'Drawdown / consec losses / VIX / breadth / data', mode: 'fail-closed',
      live: circuitBreakers?.any_triggered ? 'fail' : 'ok' },
    { n: '3', name: 'Position Monitor', desc: 'RS, sector, time decay, earnings — flag for action', mode: 'fail-open', live: 'ok' },
    { n: '3b', name: 'Exposure Policy', desc: 'Tier-based stops, partials, force-exit losers', mode: 'fail-open', live: 'ok' },
    { n: '4', name: 'Exit Execution', desc: 'Stops, T1/T2/T3, time, TD, RS-break, distribution', mode: 'fail-open', live: 'ok' },
    { n: '5', name: 'Signal Generation', desc: `Pine BUYs → 6 tiers → swing_score ranking${rejectionFunnel?.total_signals ? ` · ${rejectionFunnel.total_signals} signals` : ''}`, mode: 'fail-open', live: 'ok' },
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
                    {ph.live === 'ok' ? '✓ OK' : ph.live === 'warn' ? '⚠ WARN' : '✗ FAIL'}
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
                      <th>Loader</th>
                      <th>Table</th>
                      <th>Latest Date</th>
                      <th className="num">Age (h)</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {loaders.map((l, i) => {
                      const s = l.status || 'unknown';
                      const sc = s === 'OK' ? 'badge-success' : s === 'WARNING' ? 'badge-amber' : 'badge-danger';
                      return (
                        <tr key={i}>
                          <td className="mono t-xs">{l.loader}</td>
                          <td className="muted t-xs">{l.table}</td>
                          <td className="mono t-xs">{l.latest_date || '—'}</td>
                          <td className={`num mono tnum t-xs ${l.age_hours > (l.max_age_hours || 24) ? 'down' : ''}`}>
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
// DATA STATUS TAB
// ============================================================================
function DataStatusTab({ dataStatus, patrolLog }) {
  const [running, setRunning] = useState(false);
  const runPatrol = async () => {
    setRunning(true);
    try {
      await api.post('/api/algo/patrol', { quick: false });
      window.location.reload();
    } catch (e) {
      console.error(e);
    }
    setRunning(false);
  };
  if (!dataStatus) return <div style={{ padding: 'var(--space-3)' }}><div className="alert alert-info">Data status not loaded</div></div>;
  return (
    <div style={{ padding: 'var(--space-3)' }}>
      <div style={{
        padding: 'var(--space-3)', marginBottom: 'var(--space-3)', borderRadius: 'var(--r-md)',
        background: dataStatus.ready_to_trade ? '#0e2a18' : '#3a1414',
        border: `1px solid ${dataStatus.ready_to_trade ? 'var(--success)' : 'var(--danger)'}`,
      }}>
        <div className="flex items-center gap-3">
          {dataStatus.ready_to_trade ?
            <CheckCircle size={28} style={{ color: 'var(--success)' }} /> :
            <AlertTriangle size={28} style={{ color: 'var(--danger)' }} />}
          <div>
            <div style={{ color: 'var(--text-2)', fontWeight: 'var(--w-bold)', fontSize: 'var(--t-lg)' }}>
              {dataStatus.ready_to_trade ? 'READY TO TRADE' : 'DATA STALE — ALGO WILL FAIL-CLOSE'}
            </div>
            <div className="mono t-xs muted" style={{ marginTop: 4 }}>
              {dataStatus.summary.ok} ok · {dataStatus.summary.stale} stale · {dataStatus.summary.empty} empty · {dataStatus.summary.error} error
            </div>
            {!dataStatus.ready_to_trade && (
              <div className="mono t-xs" style={{ color: 'var(--danger)', marginTop: 4 }}>
                Critical stale: {dataStatus.critical_stale.join(', ')}
              </div>
            )}
          </div>
        </div>
      </div>

      <div style={{ marginBottom: 'var(--space-3)', display: 'flex', justifyContent: 'flex-end' }}>
        <button className="btn btn-primary btn-sm" onClick={runPatrol} disabled={running}>
          {running ? 'RUNNING...' : 'RUN DATA PATROL NOW'}
        </button>
      </div>

      {patrolLog && patrolLog.length > 0 && (
        <SectionCard title={`Recent Patrol Findings (${patrolLog.length})`}>
          <div style={{ overflowX: 'auto', maxHeight: 400 }}>
            <table className="data-table">
              <thead>
                <tr>
                  {['SEVERITY', 'CHECK', 'TARGET', 'MESSAGE', 'WHEN'].map(h => (
                    <th key={h} style={{ fontSize: 'var(--t-2xs)', fontWeight: 'var(--w-bold)', letterSpacing: '1px' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {patrolLog.map(log => (
                  <tr key={log.id}>
                    <td>
                      <span className={`badge ${log.severity === 'critical' || log.severity === 'error' ? 'badge-danger' : log.severity === 'warn' ? 'badge-warn' : 'badge-success'}`}>
                        {log.severity.toUpperCase()}
                      </span>
                    </td>
                    <td className="mono t-xs">{log.check_name}</td>
                    <td className="strong mono">{log.target_table}</td>
                    <td className="t-xs">{log.message}</td>
                    <td className="mono t-xs muted">{new Date(log.created_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SectionCard>
      )}

      <SectionCard title={`Data Sources (${(dataStatus.sources || []).length})`}>
        <div style={{ overflowX: 'auto' }}>
          <table className="data-table">
            <thead>
              <tr>
                {['STATUS', 'TABLE', 'FREQUENCY', 'ROLE', 'LATEST', 'AGE', 'ROWS'].map(h => (
                  <th key={h} style={{ fontSize: 'var(--t-2xs)', fontWeight: 'var(--w-bold)', letterSpacing: '1px' }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(dataStatus.sources || []).map(s => (
                <tr key={s.table}>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <div style={{
                        display: 'inline-block', width: 6, height: 6, borderRadius: '50%',
                        background: statusBg(s.status),
                      }} />
                      <span className="mono t-xs strong" style={{ textTransform: 'uppercase', color: statusBg(s.status) }}>
                        {s.status}
                      </span>
                    </div>
                  </td>
                  <td className="strong mono">{s.table}</td>
                  <td className="mono t-xs">{s.frequency}</td>
                  <td className="t-xs muted">{s.role}</td>
                  <td className="mono t-xs">{s.latest || '-'}</td>
                  <td className="mono" style={{ color: s.age_days > 7 ? 'var(--amber)' : 'var(--text)' }}>
                    {s.age_days !== null ? `${s.age_days}d` : '-'}
                  </td>
                  <td className="mono">{s.rows?.toLocaleString() || '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SectionCard>
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

// ============================================================================
// AUDIT TAB
// ============================================================================
function AuditTab({ auditLog }) {
  if (!auditLog || auditLog.length === 0) {
    return <div style={{ padding: 'var(--space-3)' }}><div className="alert alert-info">
      No audit entries yet
    </div></div>;
  }
  return (
    <div style={{ padding: 'var(--space-3)' }}>
      <div className="t-xs muted" style={{ marginBottom: 'var(--space-3)', display: 'block' }}>
        Every algo decision logged with timestamp, actor, status, and full details JSON.
      </div>
      <SectionCard title={`Audit Trail (${auditLog.length} most recent)`}>
        <div style={{ overflowX: 'auto', maxHeight: 600 }}>
          <table className="data-table">
            <thead>
              <tr>
                {['WHEN', 'ACTION', 'SYMBOL', 'ACTOR', 'STATUS', 'DETAILS'].map(h => (
                  <th key={h} style={{ fontSize: 'var(--t-2xs)', fontWeight: 'var(--w-bold)', letterSpacing: '1px' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {auditLog.map(a => (
                <tr key={a.id}>
                  <td className="mono t-2xs muted">{new Date(a.created_at).toLocaleString()}</td>
                  <td className="mono t-xs">{a.action_type}</td>
                  <td className="strong mono">{a.symbol || '-'}</td>
                  <td className="t-xs muted">{a.actor || '-'}</td>
                  <td>
                    <span className={`badge ${a.status === 'success' ? 'badge-success' : a.status === 'halt' ? 'badge-warn' : a.status === 'error' ? 'badge-danger' : 'badge-secondary'}`}>
                      {a.status || '-'}
                    </span>
                  </td>
                  <td className="mono t-2xs muted" style={{
                    maxWidth: 500, overflow: 'hidden', textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}>
                    {a.details ? JSON.stringify(a.details).substring(0, 200) : '-'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SectionCard>
    </div>
  );
}

export default AlgoTradingDashboard;

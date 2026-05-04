/**
 * Market Health — flagship dashboard.
 *
 * Pure JSX + theme.css classes. No MUI. No Tailwind. Dark theme.
 * All tokens from src/styles/tokens.css.
 *
 * Sections:
 *   1. Regime banner (exposure, tier, halt status)
 *   2. Major indices grid w/ 30d sparklines
 *   3. 9-factor exposure composite
 *   4. Market pulse (DD circle + FTD)
 *   5. 90d exposure history area chart
 *   6. Breadth bar chart (% > 50/200 DMA)
 *   7. New highs vs lows
 *   8. AAII sentiment chart
 *   9. VIX regime
 *  10. Market internals (advancers/decliners + 30d A/D line)
 *  11. Top movers
 *  12. Seasonality context
 */

import React, { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  ResponsiveContainer, AreaChart, Area, LineChart, Line, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip as RTooltip, ReferenceLine, Cell, Legend,
  ComposedChart,
} from 'recharts';
import {
  RefreshCw, ShieldCheck, TrendingUp, TrendingDown, Activity, AlertTriangle, Inbox,
} from 'lucide-react';
import { api } from '../services/api';

// ═══════════════════════════════════════════════════════════════════════════
// TOKENS (mirror tokens.css for chart colors)
// ═══════════════════════════════════════════════════════════════════════════
const C = {
  bg: '#0a0c12',
  bg2: '#0f1219',
  surface: '#141720',
  surface2: '#1a1e2d',
  border: '#232838',
  border2: '#2a2f42',
  text: '#e8eaf4',
  textMuted: '#8891b0',
  textFaint: '#6b7a99',
  brand: '#6366f1',
  brand2: '#818cf8',
  cyan: '#22d3ee',
  success: '#22c55e',
  danger: '#ef4444',
  amber: '#f59e0b',
  purple: '#a78bfa',
};

const REGIME_COLOR = {
  confirmed_uptrend: C.success,
  healthy_uptrend: C.brand2,
  pressure: C.amber,
  uptrend_under_pressure: C.amber,
  caution: C.amber,
  correction: C.danger,
};

// ═══════════════════════════════════════════════════════════════════════════
// HELPERS
// ═══════════════════════════════════════════════════════════════════════════
const num = (v, dp = 2) => v == null || isNaN(Number(v)) ? '—' : Number(v).toFixed(dp);
const fmtMoney = (v) => v == null ? '—' : `$${Number(v).toFixed(2)}`;
const fmtAgo = (ts) => {
  if (!ts) return '—';
  const s = (Date.now() - new Date(ts).getTime()) / 1000;
  if (s < 60) return `${Math.floor(s)}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
};

// ═══════════════════════════════════════════════════════════════════════════
// MAIN
// ═══════════════════════════════════════════════════════════════════════════

export default function MarketsHealth() {
  const [ts, setTs] = useState(new Date());

  const { data: marketsData, isLoading: marketsLoading, refetch: refetchMarkets } = useQuery({
    queryKey: ['algo-markets'],
    queryFn: () => api.get('/api/algo/markets').then(r => r.data?.data),
    refetchInterval: 30000,
  });
  const { data: sentimentData } = useQuery({
    queryKey: ['market-sentiment-30d'],
    queryFn: () => api.get('/api/market/sentiment?range=30d').then(r => r.data?.data),
    refetchInterval: 60000,
  });
  const { data: moversData } = useQuery({
    queryKey: ['market-top-movers'],
    queryFn: () => api.get('/api/market/top-movers').then(r => r.data?.data),
    refetchInterval: 60000,
  });
  const { data: technicalsData } = useQuery({
    queryKey: ['market-technicals'],
    queryFn: () => api.get('/api/market/technicals').then(r => r.data?.data),
    refetchInterval: 60000,
  });
  const { data: seasonalityData } = useQuery({
    queryKey: ['market-seasonality'],
    queryFn: () => api.get('/api/market/seasonality').then(r => r.data?.data),
    refetchInterval: 1000 * 60 * 60,
  });

  useEffect(() => {
    const id = setInterval(() => setTs(new Date()), 30000);
    return () => clearInterval(id);
  }, []);

  const refetchAll = () => { refetchMarkets(); setTs(new Date()); };
  const m = marketsData;

  if (marketsLoading && !m) {
    return (
      <div className="main-content">
        <div className="empty"><Inbox /><div className="empty-title">Loading market data…</div></div>
      </div>
    );
  }

  return (
    <div className="main-content">
      {/* Page header */}
      <div className="page-head">
        <div>
          <div className="page-head-title">Market Health</div>
          <div className="page-head-sub">Updated {fmtAgo(ts)} · Auto-refresh 30s</div>
        </div>
        <div className="page-head-actions">
          <button className="btn btn-outline btn-sm" onClick={refetchAll}>
            <RefreshCw size={14} /> Refresh
          </button>
        </div>
      </div>

      <RegimeBanner markets={m} />
      <IndicesStrip />

      <div className="grid grid-2" style={{ marginTop: 'var(--space-4)' }}>
        <ExposureFactors markets={m} />
        <MarketPulse markets={m} />
      </div>

      <div style={{ marginTop: 'var(--space-4)' }}>
        <ExposureHistory markets={m} />
      </div>

      <div className="grid grid-2" style={{ marginTop: 'var(--space-4)' }}>
        <BreadthCard markets={m} />
        <NewHighsLowsCard markets={m} />
      </div>

      <div className="grid grid-2" style={{ marginTop: 'var(--space-4)' }}>
        <SentimentCard markets={m} sentiment={sentimentData} />
        <VixCard markets={m} />
      </div>

      <div className="grid grid-2" style={{ marginTop: 'var(--space-4)' }}>
        <InternalsCard data={technicalsData} />
        <TopMoversCard data={moversData} />
      </div>

      <div style={{ marginTop: 'var(--space-4)' }}>
        <SeasonalityCard data={seasonalityData} />
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// 1. REGIME BANNER
// ═══════════════════════════════════════════════════════════════════════════

function RegimeBanner({ markets }) {
  if (!markets?.current) {
    return (
      <div className="alert alert-warn">
        <AlertTriangle size={18} />
        <div>
          <div style={{ fontWeight: 'var(--w-semibold)' }}>Exposure not yet computed</div>
          <div className="muted t-sm">Run algo_market_exposure.py to populate the 9-factor regime.</div>
        </div>
      </div>
    );
  }
  const cur = markets.current;
  const tier = markets.active_tier || {};
  const exposure = cur.exposure_pct;
  const regime = tier.name || cur.regime || 'unknown';
  const color = REGIME_COLOR[regime] || C.textMuted;

  return (
    <div className="card" style={{ borderLeft: `3px solid ${color}`, padding: 'var(--space-6) var(--space-7)' }}>
      <div className="grid" style={{ gridTemplateColumns: '1.4fr 1.2fr 0.8fr 0.8fr 1fr', gap: 'var(--space-5)', alignItems: 'center' }}>
        <div className="flex items-center gap-3">
          <div style={{
            width: 56, height: 56, borderRadius: 'var(--r-md)',
            background: `linear-gradient(135deg, ${color}30 0%, ${color}10 100%)`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            border: `1px solid ${color}50`,
          }}>
            <ShieldCheck size={28} color={color} />
          </div>
          <div>
            <div className="eyebrow">Market Exposure</div>
            <div className="mono tnum" style={{ fontSize: 'var(--t-3xl)', fontWeight: 'var(--w-extra)', color, lineHeight: 1 }}>
              {exposure}<span style={{ fontSize: 'var(--t-lg)', fontWeight: 'var(--w-semibold)' }}>%</span>
            </div>
          </div>
        </div>

        <div>
          <div className="eyebrow">Regime Tier</div>
          <div style={{ fontSize: 'var(--t-lg)', fontWeight: 'var(--w-semibold)', color, marginTop: 4 }}>
            {String(regime).replace(/_/g, ' ').toUpperCase()}
          </div>
          {tier.description && <div className="muted t-xs" style={{ marginTop: 4 }}>{tier.description}</div>}
        </div>

        <div>
          <div className="eyebrow">Risk ×</div>
          <div className="mono tnum" style={{ fontSize: 'var(--t-xl)', fontWeight: 'var(--w-bold)', marginTop: 4 }}>
            {tier.risk_mult ?? '—'}
          </div>
        </div>

        <div>
          <div className="eyebrow">Max New</div>
          <div className="mono tnum" style={{ fontSize: 'var(--t-xl)', fontWeight: 'var(--w-bold)', marginTop: 4 }}>
            {tier.max_new ?? '—'}
          </div>
        </div>

        <div>
          <div className="eyebrow">Entry</div>
          <div style={{ marginTop: 4 }}>
            <span className={`badge badge-lg ${tier.halt ? 'badge-danger' : 'badge-success'}`}>
              {tier.halt ? 'HALTED' : 'ALLOWED'}
            </span>
          </div>
        </div>
      </div>

      {cur.halt_reasons && (
        <div className="alert alert-warn" style={{ marginTop: 'var(--space-4)' }}>
          <AlertTriangle size={16} />
          <div><strong>Active vetoes:</strong> {cur.halt_reasons}</div>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// 2. INDICES STRIP
// ═══════════════════════════════════════════════════════════════════════════

function IndicesStrip() {
  const seeds = [
    { symbol: 'SPY', name: 'S&P 500' },
    { symbol: 'QQQ', name: 'Nasdaq 100' },
    { symbol: 'IWM', name: 'Russell 2000' },
    { symbol: 'DIA', name: 'Dow Jones' },
  ];
  return (
    <div className="card card-pad" style={{ marginTop: 'var(--space-4)' }}>
      <div className="sect-head">
        <div className="sect-title">Major Indices</div>
        <div className="sect-sub">Last close · Daily change · 30-day trend</div>
      </div>
      <div className="grid grid-4">
        {seeds.map(idx => <IndexCell key={idx.symbol} idx={idx} />)}
      </div>
    </div>
  );
}

function IndexCell({ idx }) {
  const { data } = useQuery({
    queryKey: ['index-history', idx.symbol],
    queryFn: () => api.get(`/api/prices/history/${idx.symbol}?timeframe=daily&limit=30`)
      .then(r => r.data?.data?.items || r.data?.items || []),
    staleTime: 60000,
  });
  const series = (data || []).slice(-30).map(p => ({
    date: p.date, close: parseFloat(p.close || p.adj_close),
  }));
  const last = series[series.length - 1]?.close;
  const prev = series[series.length - 2]?.close;
  const chg = last && prev ? last - prev : null;
  const chgPct = chg && prev ? (chg / prev) * 100 : null;
  const positive = chgPct != null && chgPct >= 0;
  const sparkColor = positive ? C.success : C.danger;

  return (
    <div className="panel" style={{ padding: 'var(--space-3) var(--space-4)' }}>
      <div className="flex items-start justify-between" style={{ marginBottom: 4 }}>
        <div>
          <div style={{ fontSize: 'var(--t-md)', fontWeight: 'var(--w-bold)', color: 'var(--text)' }}>{idx.symbol}</div>
          <div className="muted" style={{ fontSize: 'var(--t-2xs)' }}>{idx.name}</div>
        </div>
        {chgPct != null && (positive
          ? <TrendingUp size={16} color={C.success} />
          : <TrendingDown size={16} color={C.danger} />)}
      </div>
      <div className="mono tnum" style={{ fontSize: 'var(--t-xl)', fontWeight: 'var(--w-semibold)', color: 'var(--text)' }}>
        {last != null ? fmtMoney(last) : '—'}
      </div>
      {chgPct != null && (
        <div className={`mono tnum ${positive ? 'up' : 'down'}`} style={{ fontSize: 'var(--t-sm)', fontWeight: 'var(--w-semibold)' }}>
          {chg >= 0 ? '+' : ''}{num(chg)} ({chg >= 0 ? '+' : ''}{num(chgPct)}%)
        </div>
      )}
      {series.length >= 2 && (
        <div style={{ marginTop: 8, height: 30 }}>
          <ResponsiveContainer>
            <AreaChart data={series}>
              <defs>
                <linearGradient id={`ig-${idx.symbol}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={sparkColor} stopOpacity={0.4} />
                  <stop offset="100%" stopColor={sparkColor} stopOpacity={0} />
                </linearGradient>
              </defs>
              <Area type="monotone" dataKey="close" stroke={sparkColor} strokeWidth={1.5} fill={`url(#ig-${idx.symbol})`} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// 3. EXPOSURE FACTORS
// ═══════════════════════════════════════════════════════════════════════════

function ExposureFactors({ markets }) {
  const factors = markets?.current?.factors || {};
  const list = [
    ['ibd_state',       'MARKET STATE',           20],
    ['trend_30wk',      '30-WEEK MA TREND',       15],
    ['breadth_50dma',   'BREADTH (% > 50-DMA)',   15],
    ['breadth_200dma',  'HEALTH (% > 200-DMA)',   10],
    ['vix_regime',      'VIX REGIME',             10],
    ['mcclellan',       'MCCLELLAN OSCILLATOR',   10],
    ['new_highs_lows',  'NEW HIGHS - LOWS',       8],
    ['ad_line',         'A/D LINE CONFIRMATION',  7],
    ['aaii_sentiment',  'SENTIMENT (CONTRARIAN)', 5],
  ];
  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">9-Factor Exposure Composite</div>
          <div className="card-sub">
            {markets?.current ? `Raw ${num(markets.current.raw_score, 1)} → capped ${markets.current.exposure_pct}%`
              : 'Each factor independently scored, summed for total exposure'}
          </div>
        </div>
      </div>
      <div className="card-body">
        {list.map(([key, label, max]) => {
          const f = factors[key] || {};
          const pct = f.max ? Math.max(0, Math.min(100, (f.pts / f.max) * 100)) : 0;
          const fillClass = pct >= 70 ? 'success' : pct >= 40 ? '' : pct >= 20 ? 'warn' : 'danger';
          const sub = [];
          if (f.value != null) sub.push(`val ${num(f.value, 2)}`);
          if (f.state) sub.push(f.state);
          if (f.relation) sub.push(f.relation);
          if (f.bull_bear_spread != null) sub.push(`spread ${num(f.bull_bear_spread, 1)}`);
          if (f.new_highs != null) sub.push(`${f.new_highs} highs / ${f.new_lows} lows`);
          if (f.distribution_days_25d != null) sub.push(`${f.distribution_days_25d} dist days`);
          return (
            <div key={key} style={{ marginBottom: 'var(--space-3)' }}>
              <div className="flex items-center justify-between" style={{ marginBottom: 4 }}>
                <span className="eyebrow">{label}</span>
                <span className="mono tnum t-xs strong">{num(f.pts || 0, 1)} / {f.max || max}</span>
              </div>
              <div className="bar">
                <div className={`bar-fill ${fillClass}`} style={{ width: `${pct}%` }} />
              </div>
              {sub.length > 0 && (
                <div className="t-2xs muted" style={{ marginTop: 4 }}>{sub.join(' · ')}</div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// 4. MARKET PULSE
// ═══════════════════════════════════════════════════════════════════════════

function MarketPulse({ markets }) {
  const cur = markets?.current;
  if (!cur) return <Empty title="No data" desc="Pulse loads when exposure is computed" />;
  const dd = cur.distribution_days || 0;
  const ftd = cur.factors?.ibd_state?.follow_through_day;
  const state = cur.factors?.ibd_state?.state || '—';
  const ddColor = dd >= 5 ? C.danger : dd >= 4 ? C.amber : C.success;

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">Market Pulse</div>
          <div className="card-sub">Institutional selling pressure</div>
        </div>
      </div>
      <div className="card-body">
        <div className="flex items-center justify-center" style={{ padding: 'var(--space-5) 0' }}>
          <div style={{
            width: 120, height: 120, borderRadius: '50%',
            background: `radial-gradient(circle, ${ddColor}20 0%, transparent 70%)`,
            border: `4px solid ${ddColor}`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            boxShadow: `0 0 32px ${ddColor}40`,
          }}>
            <span className="mono tnum" style={{ fontSize: 'var(--t-3xl)', fontWeight: 'var(--w-extra)', color: ddColor }}>{dd}</span>
          </div>
        </div>
        <div className="eyebrow center" style={{ marginBottom: 'var(--space-4)' }}>Distribution Days (25 sessions)</div>
        <div className="panel" style={{ background: 'var(--bg-2)' }}>
          <div className="flex items-center justify-between t-sm mono" style={{ padding: '6px 0' }}>
            <span className="muted">Follow-Through Day</span>
            <span className={ftd ? 'up' : 'down'} style={{ fontWeight: 'var(--w-bold)' }}>{ftd ? 'YES' : 'NO'}</span>
          </div>
          <div className="flex items-center justify-between t-sm mono" style={{ padding: '6px 0', borderTop: '1px solid var(--border-soft)' }}>
            <span className="muted">State</span>
            <span className={state.includes('uptrend') ? 'up' : 'down'} style={{ fontWeight: 'var(--w-bold)' }}>
              {state.replace(/_/g, ' ').toUpperCase()}
            </span>
          </div>
        </div>
        <div className="t-xs muted" style={{ marginTop: 'var(--space-3)' }}>
          5+ distribution days in 4 weeks signals correction. Confirmed uptrend requires
          &lt; 4 dist days plus a follow-through day after a rally attempt.
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// 5. EXPOSURE HISTORY
// ═══════════════════════════════════════════════════════════════════════════

function ExposureHistory({ markets }) {
  const history = (markets?.history || []).slice().reverse();
  if (!history.length) return <Empty title="Exposure history" desc="Builds over time as exposure runs daily" wrap />;
  const data = history.map(h => ({
    date: h.date, exposure: parseFloat(h.exposure_pct),
    regime: h.regime, dd: h.distribution_days,
  }));
  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">Exposure History — last {data.length} sessions</div>
          <div className="card-sub">How the algo's risk allocation moved with the market regime</div>
        </div>
      </div>
      <div className="card-body" style={{ padding: 'var(--space-4)' }}>
        <div style={{ height: 320 }}>
          <ResponsiveContainer>
            <AreaChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id="expGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={C.brand} stopOpacity={0.4} />
                  <stop offset="100%" stopColor={C.brand} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke={C.border} strokeDasharray="2 4" />
              <XAxis dataKey="date" tick={{ fill: C.textFaint, fontSize: 11 }} tickFormatter={d => String(d).slice(5)} />
              <YAxis domain={[0, 100]} tick={{ fill: C.textFaint, fontSize: 11 }} tickFormatter={v => `${v}%`} width={42} />
              <RTooltip contentStyle={{ background: C.surface, border: `1px solid ${C.border2}`, borderRadius: 8, fontSize: 12, color: C.text }} />
              <ReferenceLine y={80} stroke={C.success} strokeDasharray="3 3" label={{ value: 'Confirmed', fill: C.success, fontSize: 10, position: 'right' }} />
              <ReferenceLine y={60} stroke={C.brand2}  strokeDasharray="3 3" label={{ value: 'Healthy',   fill: C.brand2,  fontSize: 10, position: 'right' }} />
              <ReferenceLine y={40} stroke={C.amber}   strokeDasharray="3 3" label={{ value: 'Pressure',  fill: C.amber,   fontSize: 10, position: 'right' }} />
              <ReferenceLine y={20} stroke={C.danger}  strokeDasharray="3 3" label={{ value: 'Caution',   fill: C.danger,  fontSize: 10, position: 'right' }} />
              <Area type="monotone" dataKey="exposure" stroke={C.brand2} strokeWidth={2} fill="url(#expGrad)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// 6. BREADTH
// ═══════════════════════════════════════════════════════════════════════════

function BreadthCard({ markets }) {
  const cur = markets?.current?.factors || {};
  const b50 = cur.breadth_50dma || {};
  const b200 = cur.breadth_200dma || {};
  const data = [
    { name: '> 50-DMA',  value: b50.value || 0,  count: `${b50.above || 0}/${b50.total || 0}` },
    { name: '> 200-DMA', value: b200.value || 0, count: `${b200.above || 0}/${b200.total || 0}` },
  ];
  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">Market Breadth</div>
          <div className="card-sub">% of stocks above key moving averages</div>
        </div>
      </div>
      <div className="card-body">
        <div style={{ height: 200 }}>
          <ResponsiveContainer>
            <BarChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }} barSize={56}>
              <CartesianGrid stroke={C.border} strokeDasharray="2 4" />
              <XAxis dataKey="name" tick={{ fill: C.textFaint, fontSize: 11 }} />
              <YAxis domain={[0, 100]} tick={{ fill: C.textFaint, fontSize: 11 }} tickFormatter={v => `${v}%`} />
              <RTooltip contentStyle={{ background: C.surface, border: `1px solid ${C.border2}`, borderRadius: 8, fontSize: 12, color: C.text }}
                formatter={(v, _, p) => [`${v}% (${p.payload.count})`, p.payload.name]} />
              <ReferenceLine y={50} stroke={C.textMuted} strokeDasharray="3 3" />
              <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                {data.map((d, i) => (
                  <Cell key={i} fill={d.value >= 60 ? C.success : d.value >= 40 ? C.brand2 : C.danger} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="grid grid-3" style={{ marginTop: 'var(--space-3)' }}>
          <div className="stile">
            <div className="stile-label">&gt; 50-DMA</div>
            <div className="stile-value">{num(b50.value, 1)}%</div>
            <div className="stile-sub">{b50.above || 0} of {b50.total || 0}</div>
          </div>
          <div className="stile">
            <div className="stile-label">&gt; 200-DMA</div>
            <div className="stile-value">{num(b200.value, 1)}%</div>
            <div className="stile-sub">{b200.above || 0} of {b200.total || 0}</div>
          </div>
          <div className="stile">
            <div className="stile-label">McClellan</div>
            <div className="stile-value">{num(cur.mcclellan?.value, 1)}</div>
            <div className="stile-sub">{cur.mcclellan?.value > 0 ? 'positive' : 'negative'}</div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// 7. NEW HIGHS / LOWS
// ═══════════════════════════════════════════════════════════════════════════

function NewHighsLowsCard({ markets }) {
  const nhnl = markets?.current?.factors?.new_highs_lows || {};
  const data = [
    { name: 'New Highs', value: nhnl.new_highs || 0, fill: C.success },
    { name: 'New Lows',  value: -(nhnl.new_lows || 0), fill: C.danger },
  ];
  const net = nhnl.net || 0;
  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">New Highs vs Lows</div>
          <div className="card-sub">Net market leadership signal</div>
        </div>
      </div>
      <div className="card-body">
        <div style={{ height: 200 }}>
          <ResponsiveContainer>
            <BarChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }} barSize={64}>
              <CartesianGrid stroke={C.border} strokeDasharray="2 4" />
              <XAxis dataKey="name" tick={{ fill: C.textFaint, fontSize: 11 }} />
              <YAxis tick={{ fill: C.textFaint, fontSize: 11 }} />
              <ReferenceLine y={0} stroke={C.border2} />
              <RTooltip contentStyle={{ background: C.surface, border: `1px solid ${C.border2}`, borderRadius: 8, fontSize: 12, color: C.text }}
                formatter={(v, _, p) => [Math.abs(v), p.payload.name]} />
              <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                {data.map((d, i) => <Cell key={i} fill={d.fill} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="grid grid-3" style={{ marginTop: 'var(--space-3)' }}>
          <div className="stile"><div className="stile-label">Highs</div><div className="stile-value up">{nhnl.new_highs || 0}</div></div>
          <div className="stile"><div className="stile-label">Lows</div><div className="stile-value down">{nhnl.new_lows || 0}</div></div>
          <div className="stile"><div className="stile-label">Net</div><div className={`stile-value ${net >= 0 ? 'up' : 'down'}`}>{net}</div></div>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// 8. SENTIMENT
// ═══════════════════════════════════════════════════════════════════════════

function SentimentCard({ markets, sentiment }) {
  const aaiiHistory = sentiment?.aaii || markets?.sentiment || [];
  const naaim = sentiment?.naaim?.exposure ?? sentiment?.naaim;
  const fearGreed = sentiment?.fearGreed?.value ?? sentiment?.fearGreed;
  if (!aaiiHistory.length) return <Empty title="Investor Sentiment" desc="AAII data not yet loaded" wrap />;
  const data = aaiiHistory.slice().reverse().map(s => ({
    date: s.date,
    bull: parseFloat(s.bullish || 0),
    bear: parseFloat(s.bearish || 0),
    neutral: parseFloat(s.neutral || 0),
  }));
  const latest = data[data.length - 1] || {};
  const spread = (latest.bull || 0) - (latest.bear || 0);
  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">Investor Sentiment</div>
          <div className="card-sub">AAII bull/bear · contrarian signal at extremes</div>
        </div>
      </div>
      <div className="card-body">
        <div style={{ height: 200 }}>
          <ResponsiveContainer>
            <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
              <CartesianGrid stroke={C.border} strokeDasharray="2 4" />
              <XAxis dataKey="date" tick={{ fill: C.textFaint, fontSize: 11 }} tickFormatter={d => String(d).slice(5)} />
              <YAxis tick={{ fill: C.textFaint, fontSize: 11 }} tickFormatter={v => `${v}%`} />
              <RTooltip contentStyle={{ background: C.surface, border: `1px solid ${C.border2}`, borderRadius: 8, fontSize: 12, color: C.text }} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Line type="monotone" dataKey="bull" stroke={C.success} strokeWidth={2} dot={false} name="Bullish" />
              <Line type="monotone" dataKey="bear" stroke={C.danger}  strokeWidth={2} dot={false} name="Bearish" />
              <Line type="monotone" dataKey="neutral" stroke={C.textMuted} strokeWidth={1.5} strokeDasharray="3 3" dot={false} name="Neutral" />
            </LineChart>
          </ResponsiveContainer>
        </div>
        <div className="grid grid-4" style={{ marginTop: 'var(--space-3)' }}>
          <div className="stile"><div className="stile-label">Bullish</div><div className="stile-value up">{num(latest.bull, 1)}%</div></div>
          <div className="stile"><div className="stile-label">Bearish</div><div className="stile-value down">{num(latest.bear, 1)}%</div></div>
          <div className="stile">
            <div className="stile-label">Spread</div>
            <div className={`stile-value ${spread >= 0 ? 'up' : 'down'}`}>{spread >= 0 ? '+' : ''}{num(spread, 1)}</div>
            <div className="stile-sub">{Math.abs(spread) > 20 ? 'contrarian alert' : 'normal'}</div>
          </div>
          <div className="stile">
            <div className="stile-label">{naaim != null ? 'NAAIM' : 'Fear/Greed'}</div>
            <div className="stile-value">{naaim != null ? `${num(naaim, 0)}%` : (fearGreed != null ? num(fearGreed, 0) : '—')}</div>
            <div className="stile-sub">{naaim != null ? 'manager exposure' : (fearGreed > 50 ? 'greed' : 'fear')}</div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// 9. VIX
// ═══════════════════════════════════════════════════════════════════════════

function VixCard({ markets }) {
  const vix = markets?.current?.factors?.vix_regime || {};
  const level = vix.value || 0;
  const regime =
    level < 15 ? 'Calm' :
    level < 20 ? 'Normal' :
    level < 28 ? 'Elevated' :
    level < 36 ? 'High' : 'Extreme';
  const variant =
    level < 15 ? 'badge-success' :
    level < 20 ? 'badge-brand' :
    level < 28 ? 'badge-amber' : 'badge-danger';
  const color =
    level < 15 ? C.success :
    level < 20 ? C.brand2 :
    level < 28 ? C.amber : C.danger;

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">Volatility Regime (VIX)</div>
          <div className="card-sub">Implied volatility — proxy for market fear</div>
        </div>
      </div>
      <div className="card-body" style={{ textAlign: 'center', padding: 'var(--space-7)' }}>
        <div className="mono tnum" style={{ fontSize: 56, fontWeight: 'var(--w-extra)', color, lineHeight: 1, textShadow: `0 0 32px ${color}40` }}>
          {num(level, 2)}
        </div>
        <div style={{ marginTop: 12 }}>
          <span className={`badge badge-lg ${variant}`}>{regime.toUpperCase()}</span>
        </div>
        <div className="t-2xs faint mono" style={{ marginTop: 8 }}>{vix.rising ? 'RISING' : 'STABLE/FALLING'}</div>
        <div className="grid grid-4" style={{ marginTop: 'var(--space-5)', fontFamily: 'var(--font-mono)', fontSize: 'var(--t-2xs)' }}>
          <div className="stile" style={{ alignItems: 'center', textAlign: 'center' }}>
            <div className="stile-label">&lt; 15</div><div className="stile-sub up">Calm</div>
          </div>
          <div className="stile" style={{ alignItems: 'center', textAlign: 'center' }}>
            <div className="stile-label">15–20</div><div className="stile-sub" style={{ color: C.brand2 }}>Normal</div>
          </div>
          <div className="stile" style={{ alignItems: 'center', textAlign: 'center' }}>
            <div className="stile-label">20–28</div><div className="stile-sub" style={{ color: C.amber }}>Elevated</div>
          </div>
          <div className="stile" style={{ alignItems: 'center', textAlign: 'center' }}>
            <div className="stile-label">28+</div><div className="stile-sub down">High</div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// 10. INTERNALS
// ═══════════════════════════════════════════════════════════════════════════

function InternalsCard({ data }) {
  if (!data) return <Empty title="Market Internals" desc="Loading" wrap />;
  const breadth = data.breadth || {};
  const advancing = parseInt(breadth.advancing) || 0;
  const declining = parseInt(breadth.declining) || 0;
  const unchanged = parseInt(breadth.unchanged) || 0;
  const total = parseInt(breadth.total_stocks) || (advancing + declining + unchanged);
  const advPct = total ? (advancing / total) * 100 : 0;
  const decPct = total ? (declining / total) * 100 : 0;
  const adRatio = declining > 0 ? (advancing / declining) : 0;
  const mcclellan = (data.mcclellan_oscillator || []).slice(0, 30).reverse().map(d => ({
    date: d.date, value: parseFloat(d.advance_decline_line || 0),
  }));
  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">Market Internals</div>
          <div className="card-sub">Today's breadth · 30-day A/D line</div>
        </div>
      </div>
      <div className="card-body">
        <div className="grid grid-3" style={{ marginBottom: 'var(--space-4)' }}>
          <div className="stile"><div className="stile-label">Advancing</div><div className="stile-value up">{advancing.toLocaleString('en-US')}</div><div className="stile-sub">{num(advPct, 1)}%</div></div>
          <div className="stile"><div className="stile-label">Declining</div><div className="stile-value down">{declining.toLocaleString('en-US')}</div><div className="stile-sub">{num(decPct, 1)}%</div></div>
          <div className="stile"><div className="stile-label">A/D Ratio</div><div className={`stile-value ${adRatio > 1 ? 'up' : 'down'}`}>{num(adRatio, 2)}</div><div className="stile-sub">{unchanged} unch.</div></div>
        </div>
        {mcclellan.length > 1 && (
          <div style={{ height: 140 }}>
            <ResponsiveContainer>
              <AreaChart data={mcclellan} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                <defs>
                  <linearGradient id="mcGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={C.brand2} stopOpacity={0.4} />
                    <stop offset="100%" stopColor={C.brand2} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke={C.border} strokeDasharray="2 4" />
                <XAxis dataKey="date" tick={{ fill: C.textFaint, fontSize: 10 }} tickFormatter={d => String(d).slice(5, 10)} />
                <YAxis tick={{ fill: C.textFaint, fontSize: 10 }} width={60} tickFormatter={v => v.toLocaleString('en-US')} />
                <ReferenceLine y={0} stroke={C.border2} />
                <RTooltip contentStyle={{ background: C.surface, border: `1px solid ${C.border2}`, borderRadius: 8, fontSize: 11, color: C.text }} />
                <Area type="monotone" dataKey="value" stroke={C.brand2} strokeWidth={1.5} fill="url(#mcGrad)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// 11. TOP MOVERS
// ═══════════════════════════════════════════════════════════════════════════

function TopMoversCard({ data }) {
  if (!data) return <Empty title="Top Movers" desc="Loading" wrap />;
  const gainers = (data.gainers || []).slice(0, 6);
  const losers = (data.losers || []).slice(0, 6);
  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">Top Movers</div>
          <div className="card-sub">Day's biggest moves</div>
        </div>
      </div>
      <div className="card-body">
        <div className="eyebrow up" style={{ marginBottom: 6 }}>Gainers</div>
        {gainers.length === 0 ? <div className="muted t-xs">—</div> : gainers.map((g, i) => (
          <Mover key={i} symbol={g.symbol} chg={g.change_pct || g.changePercent} dir="up" />
        ))}
        <div className="eyebrow down" style={{ marginTop: 'var(--space-3)', marginBottom: 6, borderTop: '1px solid var(--border-soft)', paddingTop: 'var(--space-3)' }}>Losers</div>
        {losers.length === 0 ? <div className="muted t-xs">—</div> : losers.map((l, i) => (
          <Mover key={i} symbol={l.symbol} chg={l.change_pct || l.changePercent} dir="down" />
        ))}
      </div>
    </div>
  );
}
function Mover({ symbol, chg, dir }) {
  return (
    <div className="flex items-center justify-between" style={{ padding: '4px 0', fontSize: 'var(--t-sm)' }}>
      <span className="mono" style={{ fontWeight: 'var(--w-bold)' }}>{symbol}</span>
      <span className={`mono tnum ${dir}`} style={{ fontWeight: 'var(--w-semibold)' }}>
        {chg >= 0 ? '+' : ''}{num(chg, 2)}%
      </span>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// 12. SEASONALITY
// ═══════════════════════════════════════════════════════════════════════════

function SeasonalityCard({ data }) {
  if (!data) return null;
  const ytd = parseFloat(data.currentYearReturn || 0);
  const cur = data.currentPosition || {};
  const periods = cur.activePeriods || [];
  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">Seasonality &amp; Cycle Context</div>
          <div className="card-sub">Where we are in the calendar / political cycle</div>
        </div>
      </div>
      <div className="card-body">
        <div className="grid grid-4">
          <div className="stile">
            <div className="stile-label">{data.currentYear || '—'} YTD</div>
            <div className={`stile-value ${ytd >= 0 ? 'up' : 'down'}`}>{ytd >= 0 ? '+' : ''}{num(ytd, 2)}%</div>
          </div>
          <div className="stile"><div className="stile-label">Cycle</div><div className="stile-value" style={{ fontSize: 'var(--t-sm)' }}>{cur.presidentialCycle || '—'}</div></div>
          <div className="stile"><div className="stile-label">Monthly Avg</div><div className="stile-value" style={{ fontSize: 'var(--t-sm)' }}>{cur.monthlyTrend || '—'}</div></div>
          <div className="stile"><div className="stile-label">Quarterly</div><div className="stile-value" style={{ fontSize: 'var(--t-sm)' }}>{cur.quarterlyTrend || '—'}</div></div>
        </div>
        {periods.length > 0 && (
          <div className="flex gap-2" style={{ marginTop: 'var(--space-4)', flexWrap: 'wrap' }}>
            {periods.map((p, i) => <span key={i} className="badge badge-amber">{p}</span>)}
          </div>
        )}
        {cur.nextMajorEvent?.month && (
          <div className="t-xs muted" style={{ marginTop: 'var(--space-3)' }}>
            <span className="strong">Next major event:</span>{' '}
            {cur.nextMajorEvent.month} — {cur.nextMajorEvent.description || cur.nextMajorEvent.name || ''}
          </div>
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// EMPTY HELPER
// ═══════════════════════════════════════════════════════════════════════════
function Empty({ title, desc, wrap }) {
  const inner = (
    <div className="empty">
      <Inbox />
      <div className="empty-title">{title}</div>
      {desc && <div className="empty-desc">{desc}</div>}
    </div>
  );
  if (!wrap) return <div className="card">{inner}</div>;
  return <div className="card card-pad">{inner}</div>;
}

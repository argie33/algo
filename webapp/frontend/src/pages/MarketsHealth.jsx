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
 *  13. Sector Heat Map (11 sector ETFs, day % change tile grid)
 *  14. Sector Rotation Map (Mansfield 4-quadrant: leading/improving/weakening/lagging)
 *  15. Yield Curve (3M-30Y line + inversion warning)
 *  16. Volatility Term Structure (VIX9D / VIX / VIX3M / VIX6M)
 *  17. Distribution Days Timeline (last 25 sessions, colored bars)
 *  18. Sentiment Composite (Fear & Greed gauge + AAII spread)
 *  19. Economic Calendar (next 7 days)
 *  20. Earnings Calendar (this week)
 */

import React, { useEffect, useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  ResponsiveContainer, AreaChart, Area, LineChart, Line, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip as RTooltip, ReferenceLine, Cell, Legend,
  ComposedChart, ScatterChart, Scatter, ZAxis,
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
const fmtPct = (v, dp = 2) => v == null || isNaN(Number(v)) ? '—'
  : `${Number(v) >= 0 ? '+' : ''}${Number(v).toFixed(dp)}%`;
const fmtDate = (d) => {
  if (!d) return '—';
  const dt = new Date(d);
  if (isNaN(dt.getTime())) return String(d).slice(0, 10);
  return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
};
const TOOLTIP_STYLE = {
  background: 'var(--surface)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--r-sm)',
  fontSize: 'var(--t-xs)',
  padding: 'var(--space-2) var(--space-3)',
  color: 'var(--text)',
  boxShadow: 'var(--shadow-md)',
};
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
  const navigate = useNavigate();
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

      {/* ──────────── 13. Sector Heat Map ──────────── */}
      <div style={{ marginTop: 'var(--space-4)' }}>
        <SectorHeatMap onSelect={(sec) => navigate(`/app/sectors?focus=${encodeURIComponent(sec)}`)} />
      </div>

      {/* ──────────── 14. Sector Rotation Map ──────────── */}
      <div style={{ marginTop: 'var(--space-4)' }}>
        <SectorRotationMap markets={m} onSelect={(sec) => navigate(`/app/sectors?focus=${encodeURIComponent(sec)}`)} />
      </div>

      {/* ──────────── 15-16. Yield Curve + VIX Term Structure ──────────── */}
      <div className="grid grid-2" style={{ marginTop: 'var(--space-4)' }}>
        <YieldCurveCard />
        <VolTermStructureCard />
      </div>

      {/* ──────────── 17. Distribution Days Timeline ──────────── */}
      <div style={{ marginTop: 'var(--space-4)' }}>
        <DistributionDaysTimeline />
      </div>

      {/* ──────────── 18. Sentiment Composite (Fear & Greed + AAII spread) ──────────── */}
      <div style={{ marginTop: 'var(--space-4)' }}>
        <SentimentCompositeCard markets={m} sentiment={sentimentData} />
      </div>

      {/* ──────────── 19-20. Economic + Earnings Calendars ──────────── */}
      <div className="grid grid-2" style={{ marginTop: 'var(--space-4)' }}>
        <EconomicCalendarCard />
        <EarningsCalendarCard onSelect={(sym) => navigate(`/app/stock/${sym}`)} />
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
// 13. SECTOR HEAT MAP
// ═══════════════════════════════════════════════════════════════════════════

const SECTOR_ETFS = [
  { etf: 'XLK', name: 'Technology',           weight: 30 },
  { etf: 'XLF', name: 'Financials',           weight: 14 },
  { etf: 'XLV', name: 'Health Care',          weight: 12 },
  { etf: 'XLY', name: 'Consumer Discretionary',weight: 11 },
  { etf: 'XLC', name: 'Communication Services',weight: 9  },
  { etf: 'XLI', name: 'Industrials',          weight: 8  },
  { etf: 'XLP', name: 'Consumer Staples',     weight: 6  },
  { etf: 'XLE', name: 'Energy',               weight: 4  },
  { etf: 'XLU', name: 'Utilities',            weight: 3  },
  { etf: 'XLRE',name: 'Real Estate',          weight: 2  },
  { etf: 'XLB', name: 'Materials',            weight: 2  },
];

function SectorTile({ etf, name, weight, onSelect }) {
  const { data } = useQuery({
    queryKey: ['sector-tile', etf],
    queryFn: () => api.get(`/api/prices/history/${etf}?timeframe=daily&limit=2`)
      .then(r => r.data?.data?.items || r.data?.items || []),
    staleTime: 30000,
    refetchInterval: 60000,
  });
  const series = data || [];
  const last = series[0]?.close ?? series[series.length - 1]?.close;
  const prev = series[1]?.close ?? series[series.length - 2]?.close;
  const lastN = last != null ? parseFloat(last) : null;
  const prevN = prev != null ? parseFloat(prev) : null;
  const chgPct = lastN && prevN ? ((lastN - prevN) / prevN) * 100 : null;

  // Color by intensity: green up, red down
  const intensity = chgPct == null ? 0 : Math.min(Math.abs(chgPct) / 3, 1);
  const baseColor = chgPct == null ? 'var(--surface-2)'
    : chgPct >= 0
    ? `rgba(34, 197, 94, ${0.15 + intensity * 0.55})`
    : `rgba(239, 68, 68, ${0.15 + intensity * 0.55})`;
  const borderC = chgPct == null ? 'var(--border)'
    : chgPct >= 0 ? 'var(--success)' : 'var(--danger)';

  // Size proportional to weight (rough mcap proxy)
  const fontSize = 11 + weight * 0.25; // 11.5 to 18.5px
  return (
    <button
      onClick={() => onSelect && onSelect(name)}
      className="mono"
      style={{
        background: baseColor,
        border: `1px solid ${borderC}`,
        borderRadius: 'var(--r-sm)',
        padding: 'var(--space-3)',
        color: 'var(--text)',
        cursor: 'pointer',
        textAlign: 'left',
        gridColumn: `span ${Math.max(1, Math.round(weight / 3))}`,
        gridRow:    `span ${Math.max(1, Math.round(weight / 6))}`,
        minHeight: 70,
        display: 'flex', flexDirection: 'column', justifyContent: 'space-between',
        transition: 'transform 100ms',
      }}
      onMouseEnter={(e) => e.currentTarget.style.transform = 'scale(1.02)'}
      onMouseLeave={(e) => e.currentTarget.style.transform = 'scale(1)'}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <span style={{ fontWeight: 'var(--w-bold)', fontSize: `${fontSize}px` }}>{etf}</span>
        <span className="t-2xs" style={{ color: 'var(--text-faint)' }}>{weight}%</span>
      </div>
      <div className="t-2xs" style={{ color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {name}
      </div>
      <div className="tnum" style={{
        fontSize: `${fontSize + 2}px`,
        fontWeight: 'var(--w-bold)',
        color: chgPct == null ? 'var(--text-faint)' : (chgPct >= 0 ? 'var(--success)' : 'var(--danger)'),
      }}>
        {chgPct == null ? '—' : fmtPct(chgPct)}
      </div>
    </button>
  );
}

function SectorHeatMap({ onSelect }) {
  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">Sector Heat Map</div>
          <div className="card-sub">11 SPDR sector ETFs · tile size = approx S&P weight · color = today's % change · click to drill</div>
        </div>
      </div>
      <div className="card-body">
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(20, 1fr)',
          gridAutoRows: '40px',
          gap: 'var(--space-2)',
        }}>
          {SECTOR_ETFS.map(s => (
            <SectorTile key={s.etf} etf={s.etf} name={s.name} weight={s.weight} onSelect={onSelect} />
          ))}
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// 14. SECTOR ROTATION MAP (Mansfield 4-quadrant)
// ═══════════════════════════════════════════════════════════════════════════

function SectorRotationMap({ markets, onSelect }) {
  const sectors = markets?.sectors || [];
  // RS-Rank: lower current_rank = stronger (invert to score 0-100, higher = better)
  // RS-Momentum: positive if rank improved (rank_4w_ago > current_rank)
  const data = useMemo(() => {
    if (!sectors.length) return [];
    const maxRank = Math.max(...sectors.map(s => s.rank || 0)) || sectors.length;
    return sectors.map(s => {
      const rsRank = maxRank ? ((maxRank - (s.rank || maxRank)) / maxRank) * 100 : 50;
      const rsMomentum = s.rank_4w_ago != null && s.rank != null
        ? (s.rank_4w_ago - s.rank) // positive = improving
        : 0;
      return {
        name: s.name,
        rsRank: Number(rsRank.toFixed(1)),
        rsMomentum: Number(rsMomentum),
        rank: s.rank,
        momentum: s.momentum,
      };
    });
  }, [sectors]);

  if (!data.length) return <Empty title="Sector Rotation" desc="Sector ranking data not available" />;

  // Compute axis ranges
  const momRange = Math.max(2, Math.max(...data.map(d => Math.abs(d.rsMomentum))));

  // Quadrant: leading (high RS, +mom), improving (low RS, +mom), weakening (high RS, -mom), lagging (low RS, -mom)
  const quadrant = (d) => {
    if (d.rsRank >= 50 && d.rsMomentum >= 0) return 'leading';
    if (d.rsRank < 50  && d.rsMomentum >= 0) return 'improving';
    if (d.rsRank >= 50 && d.rsMomentum < 0)  return 'weakening';
    return 'lagging';
  };
  const QUAD_COLOR = {
    leading:   C.success,
    improving: C.cyan,
    weakening: C.amber,
    lagging:   C.danger,
  };

  const RotTooltip = ({ active, payload }) => {
    if (!active || !payload?.[0]) return null;
    const p = payload[0].payload;
    return (
      <div style={TOOLTIP_STYLE}>
        <div style={{ fontWeight: 'var(--w-bold)', marginBottom: 4 }}>{p.name}</div>
        <div className="mono tnum">RS-Rank: {p.rsRank.toFixed(1)}</div>
        <div className="mono tnum">4w Δrank: {p.rsMomentum >= 0 ? '+' : ''}{p.rsMomentum}</div>
        <div className="mono tnum">Quadrant: {quadrant(p)}</div>
      </div>
    );
  };

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">Sector Rotation Map</div>
          <div className="card-sub">RS-Rank vs 4-week momentum · leading / improving / weakening / lagging</div>
        </div>
      </div>
      <div className="card-body">
        <div style={{ height: 360, position: 'relative' }}>
          <ResponsiveContainer>
            <ScatterChart margin={{ top: 16, right: 24, bottom: 24, left: 24 }}>
              <CartesianGrid stroke={C.border} strokeDasharray="2 4" />
              <XAxis type="number" dataKey="rsRank" domain={[0, 100]}
                tick={{ fill: C.textFaint, fontSize: 11 }}
                label={{ value: 'RS-Rank →', position: 'insideBottom', offset: -8, fill: C.textFaint, fontSize: 11 }} />
              <YAxis type="number" dataKey="rsMomentum" domain={[-momRange, momRange]}
                tick={{ fill: C.textFaint, fontSize: 11 }}
                label={{ value: '4-week Δ rank', angle: -90, position: 'insideLeft', fill: C.textFaint, fontSize: 11 }} />
              <ZAxis range={[80, 80]} />
              <ReferenceLine x={50} stroke={C.border2} strokeDasharray="3 3" />
              <ReferenceLine y={0}  stroke={C.border2} strokeDasharray="3 3" />
              <RTooltip content={<RotTooltip />} cursor={{ strokeDasharray: '3 3' }} />
              <Scatter
                data={data}
                shape={(props) => {
                  const { cx, cy, payload } = props;
                  return (
                    <g style={{ cursor: 'pointer' }} onClick={() => onSelect && onSelect(payload.name)}>
                      <circle cx={cx} cy={cy} r={8} fill={QUAD_COLOR[quadrant(payload)]} fillOpacity={0.7}
                              stroke={QUAD_COLOR[quadrant(payload)]} strokeWidth={1.5} />
                      <text x={cx} y={cy - 12} fill={C.text} fontSize={10} textAnchor="middle"
                            style={{ fontFamily: 'var(--font-mono)', fontWeight: 'var(--w-semibold)' }}>
                        {payload.name.slice(0, 8)}
                      </text>
                    </g>
                  );
                }}
              />
            </ScatterChart>
          </ResponsiveContainer>
        </div>
        <div className="grid grid-4" style={{ marginTop: 'var(--space-3)' }}>
          {[
            ['Leading',   'leading',   'High RS · + mom'],
            ['Improving', 'improving', 'Low RS · + mom'],
            ['Weakening', 'weakening', 'High RS · - mom'],
            ['Lagging',   'lagging',   'Low RS · - mom'],
          ].map(([label, key, sub]) => (
            <div key={key} className="stile" style={{ borderLeft: `3px solid ${QUAD_COLOR[key]}` }}>
              <div className="stile-label" style={{ color: QUAD_COLOR[key] }}>{label}</div>
              <div className="stile-value" style={{ fontSize: 'var(--t-lg)' }}>
                {data.filter(d => quadrant(d) === key).length}
              </div>
              <div className="stile-sub">{sub}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// 15. YIELD CURVE
// ═══════════════════════════════════════════════════════════════════════════

function YieldCurveCard() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['yield-curve-full'],
    queryFn: () => api.get('/api/economic/yield-curve-full').then(r => r.data?.data),
    refetchInterval: 1000 * 60 * 30,
  });

  if (isLoading && !data) return <Empty title="Yield Curve" desc="Loading…" wrap />;
  if (isError || !data?.currentCurve) return <Empty title="Yield Curve" desc="Treasury data not available" wrap />;

  const order = ['3M', '6M', '1Y', '2Y', '3Y', '5Y', '7Y', '10Y', '20Y', '30Y'];
  const curve = order
    .filter(k => data.currentCurve[k] != null)
    .map(k => ({ maturity: k, yield: parseFloat(data.currentCurve[k]) }));

  if (!curve.length) return <Empty title="Yield Curve" desc="No maturities available" wrap />;

  const spread2y10y = data.spreads?.T10Y2Y;
  const spread3m10y = data.spreads?.T10Y3M;
  const isInverted = data.isInverted;

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">Treasury Yield Curve</div>
          <div className="card-sub">
            Current curve · 2s10s {spread2y10y != null ? `${num(spread2y10y, 2)}%` : '—'}
            {' · '}3m10y {spread3m10y != null ? `${num(spread3m10y, 2)}%` : '—'}
          </div>
        </div>
        {isInverted && (
          <span className="badge badge-danger" style={{ fontSize: 'var(--t-2xs)' }}>
            <AlertTriangle size={11} style={{ marginRight: 4 }} />INVERTED
          </span>
        )}
      </div>
      <div className="card-body">
        <div style={{
          background: isInverted ? 'var(--danger-soft)' : 'transparent',
          borderRadius: 'var(--r-sm)',
          padding: isInverted ? 'var(--space-2)' : 0,
        }}>
          <div style={{ height: 220 }}>
            <ResponsiveContainer>
              <LineChart data={curve} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
                <CartesianGrid stroke={C.border} strokeDasharray="2 4" />
                <XAxis dataKey="maturity" tick={{ fill: C.textFaint, fontSize: 11 }} />
                <YAxis tick={{ fill: C.textFaint, fontSize: 11 }} tickFormatter={v => `${v}%`}
                       domain={['dataMin - 0.2', 'dataMax + 0.2']} />
                <RTooltip contentStyle={TOOLTIP_STYLE}
                  formatter={(v) => [`${num(v, 3)}%`, 'Yield']} />
                <Line type="monotone" dataKey="yield"
                      stroke={isInverted ? C.danger : C.brand}
                      strokeWidth={2.5}
                      dot={{ fill: isInverted ? C.danger : C.brand, r: 4 }}
                      activeDot={{ r: 6 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
        {isInverted && (
          <div className="t-xs muted" style={{ marginTop: 'var(--space-3)' }}>
            <strong style={{ color: 'var(--danger)' }}>Recession warning:</strong>{' '}
            10Y &lt; 2Y spread historically precedes recessions by 6-24 months.
          </div>
        )}
        <div className="grid grid-3" style={{ marginTop: 'var(--space-3)' }}>
          <div className="stile">
            <div className="stile-label">3M</div>
            <div className="stile-value mono tnum">{curve.find(c => c.maturity === '3M')?.yield.toFixed(2) || '—'}%</div>
          </div>
          <div className="stile">
            <div className="stile-label">10Y</div>
            <div className="stile-value mono tnum">{curve.find(c => c.maturity === '10Y')?.yield.toFixed(2) || '—'}%</div>
          </div>
          <div className="stile">
            <div className="stile-label">30Y</div>
            <div className="stile-value mono tnum">{curve.find(c => c.maturity === '30Y')?.yield.toFixed(2) || '—'}%</div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// 16. VOLATILITY TERM STRUCTURE
// ═══════════════════════════════════════════════════════════════════════════

function useTermPoint(sym) {
  const { data } = useQuery({
    queryKey: ['vix-term', sym],
    queryFn: () => api.get(`/api/prices/history/${encodeURIComponent(sym)}?timeframe=daily&limit=2`)
      .then(r => r.data?.data?.items || r.data?.items || [])
      .catch(() => []),
    staleTime: 60000,
    refetchInterval: 60000,
  });
  const series = data || [];
  const last = series[0]?.close ?? series[series.length - 1]?.close;
  return last != null ? parseFloat(last) : null;
}

function VolTermStructureCard() {
  const v9d = useTermPoint('^VIX9D');
  const vix = useTermPoint('^VIX');
  const v3m = useTermPoint('^VIX3M');
  const v6m = useTermPoint('^VIX6M');

  const points = [
    { label: 'VIX9D', days: 9,   value: v9d },
    { label: 'VIX',   days: 30,  value: vix },
    { label: 'VIX3M', days: 90,  value: v3m },
    { label: 'VIX6M', days: 180, value: v6m },
  ].filter(p => p.value != null);

  if (points.length < 2) return <Empty title="Vol Term Structure" desc="VIX term structure data not loaded (^VIX9D / ^VIX3M / ^VIX6M)" wrap />;

  // Contango if value increases with time, backwardation if decreases
  const isBackwardation = points.length >= 2 &&
    points[0].value > points[points.length - 1].value;
  const ratio = points.length >= 2 ? (points[points.length - 1].value / points[0].value) : 1;

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">Volatility Term Structure</div>
          <div className="card-sub">
            {isBackwardation
              ? 'BACKWARDATION — short-term stress, near-term IV elevated'
              : 'CONTANGO — normal regime, vol curve upward-sloping'}
          </div>
        </div>
        <span className={`badge ${isBackwardation ? 'badge-danger' : 'badge-success'}`}>
          {isBackwardation ? 'STRESS' : 'NORMAL'}
        </span>
      </div>
      <div className="card-body">
        <div style={{ height: 200 }}>
          <ResponsiveContainer>
            <LineChart data={points} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
              <CartesianGrid stroke={C.border} strokeDasharray="2 4" />
              <XAxis dataKey="label" tick={{ fill: C.textFaint, fontSize: 11 }} />
              <YAxis tick={{ fill: C.textFaint, fontSize: 11 }} domain={['dataMin - 1', 'dataMax + 1']} />
              <RTooltip contentStyle={TOOLTIP_STYLE} formatter={(v) => [num(v, 2), 'IV']} />
              <Line type="monotone" dataKey="value"
                stroke={isBackwardation ? C.danger : C.brand}
                strokeWidth={2.5}
                dot={{ fill: isBackwardation ? C.danger : C.brand, r: 5 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
        <div className="grid" style={{ gridTemplateColumns: `repeat(${points.length}, 1fr)`, marginTop: 'var(--space-3)' }}>
          {points.map(p => (
            <div key={p.label} className="stile">
              <div className="stile-label">{p.label}</div>
              <div className="stile-value mono tnum">{num(p.value, 2)}</div>
              <div className="stile-sub">{p.days}d</div>
            </div>
          ))}
        </div>
        <div className="t-xs muted" style={{ marginTop: 'var(--space-3)' }}>
          Front/back ratio {num(ratio, 2)} · {ratio < 1 ? 'inverted' : 'upward'}.
          Backwardation often coincides with market stress and short-term tops in vol.
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// 17. DISTRIBUTION DAYS TIMELINE
// ═══════════════════════════════════════════════════════════════════════════

function DistributionDaysTimeline() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['distribution-days'],
    queryFn: () => api.get('/api/market/distribution-days').then(r => r.data?.data),
    refetchInterval: 1000 * 60 * 5,
  });

  if (isLoading && !data) return <Empty title="Distribution Days" desc="Loading…" wrap />;
  if (isError || !data) return <Empty title="Distribution Days" desc="Distribution days data not loaded" wrap />;

  const indices = ['^GSPC', '^IXIC', '^DJI'].filter(k => data[k]);
  if (!indices.length) return <Empty title="Distribution Days" desc="No index data available" wrap />;

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">Distribution Days · last 25 sessions</div>
          <div className="card-sub">
            Red = institutional selling (down day on heavier volume) · Gray = normal
          </div>
        </div>
      </div>
      <div className="card-body">
        {indices.map(sym => {
          const idx = data[sym];
          const days = (idx.days || []).slice().sort((a, b) => (a.days_ago ?? 0) - (b.days_ago ?? 0));
          // Build last 25-day timeline; oldest left → newest right
          const timeline = days.slice(0, 25).reverse();
          const sigColor = idx.signal === 'NORMAL' ? C.success
            : idx.signal === 'WATCH' ? C.brand2
            : idx.signal === 'CAUTION' ? C.amber
            : C.danger;
          return (
            <div key={sym} style={{ marginBottom: 'var(--space-4)' }}>
              <div className="flex items-center justify-between" style={{ marginBottom: 6 }}>
                <div>
                  <span className="mono" style={{ fontWeight: 'var(--w-bold)' }}>{idx.name}</span>
                  <span className="muted t-xs" style={{ marginLeft: 8 }}>({sym})</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="mono tnum t-sm" style={{ color: sigColor, fontWeight: 'var(--w-bold)' }}>
                    {idx.count} dist days
                  </span>
                  <span className={`badge ${
                    idx.signal === 'NORMAL' ? 'badge-success' :
                    idx.signal === 'WATCH' ? 'badge-brand' :
                    idx.signal === 'CAUTION' ? 'badge-amber' : 'badge-danger'
                  }`}>{idx.signal}</span>
                </div>
              </div>
              <div style={{ display: 'flex', gap: 2, height: 32 }}>
                {Array.from({ length: 25 }).map((_, i) => {
                  const d = timeline[i];
                  const isDist = !!d;
                  const chg = d?.change_pct;
                  const volRatio = d?.volume_ratio;
                  return (
                    <div
                      key={i}
                      title={d
                        ? `${d.date} · ${num(chg, 2)}% · vol ${num(volRatio, 2)}×`
                        : 'normal session'}
                      style={{
                        flex: 1,
                        minWidth: 12,
                        background: isDist ? C.danger : 'var(--surface-2)',
                        border: isDist ? `1px solid ${C.danger}` : '1px solid var(--border-soft)',
                        borderRadius: 2,
                        opacity: isDist ? Math.min(1, 0.55 + (volRatio || 1) * 0.15) : 0.5,
                      }}
                    />
                  );
                })}
              </div>
              <div className="t-2xs faint" style={{ marginTop: 4, display: 'flex', justifyContent: 'space-between' }}>
                <span>← 25 sessions ago</span>
                <span>today →</span>
              </div>
            </div>
          );
        })}
        <div className="t-xs muted" style={{ marginTop: 'var(--space-3)' }}>
          5+ distribution days in 25 sessions historically signals correction. Color intensity reflects volume ratio above average.
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// 18. SENTIMENT COMPOSITE (Fear & Greed gauge + AAII spread mini-chart)
// ═══════════════════════════════════════════════════════════════════════════

function SentimentCompositeCard({ markets, sentiment }) {
  const { data: fgData } = useQuery({
    queryKey: ['fear-greed-30d'],
    queryFn: () => api.get('/api/market/fear-greed?range=30d')
      .then(r => r.data?.data?.items || []),
    refetchInterval: 1000 * 60 * 60,
  });

  const fg = (fgData || []).slice();
  const fgLatest = fg.length ? fg[fg.length - 1] : null;
  const fgValue = fgLatest?.value ?? fgLatest?.fear_greed_value ?? null;

  // AAII bull-bear spread last 30 sessions for mini chart
  const aaii = sentiment?.aaii || markets?.sentiment || [];
  const aaiiSeries = aaii.slice().reverse().map(s => ({
    date: s.date,
    spread: parseFloat(s.bullish || 0) - parseFloat(s.bearish || 0),
  }));
  const aaiiLatest = aaiiSeries[aaiiSeries.length - 1];

  // Gauge segments for Fear & Greed
  const fgRegime = fgValue == null ? null
    : fgValue < 25 ? { label: 'Extreme Fear',   color: C.danger }
    : fgValue < 45 ? { label: 'Fear',           color: C.amber  }
    : fgValue < 55 ? { label: 'Neutral',        color: C.textMuted }
    : fgValue < 75 ? { label: 'Greed',          color: C.cyan   }
    :                { label: 'Extreme Greed',  color: C.success };

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">Sentiment Composite</div>
          <div className="card-sub">CNN Fear &amp; Greed · AAII bull-bear spread · contrarian indicators</div>
        </div>
      </div>
      <div className="card-body">
        <div className="grid grid-2" style={{ gap: 'var(--space-5)' }}>
          {/* Fear & Greed gauge */}
          <div>
            <div className="eyebrow" style={{ marginBottom: 8 }}>CNN Fear &amp; Greed Index</div>
            {fgValue == null ? (
              <Empty title="Fear &amp; Greed" desc="Data not loaded" />
            ) : (
              <>
                <div style={{ position: 'relative', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                  <FGGauge value={fgValue} regime={fgRegime} />
                  <div style={{ marginTop: 'var(--space-3)', textAlign: 'center' }}>
                    <div className="mono tnum" style={{ fontSize: 'var(--t-3xl)', fontWeight: 'var(--w-extra)', color: fgRegime.color, lineHeight: 1 }}>
                      {fgValue}
                    </div>
                    <div className="t-sm" style={{ color: fgRegime.color, fontWeight: 'var(--w-bold)', textTransform: 'uppercase', marginTop: 4 }}>
                      {fgRegime.label}
                    </div>
                  </div>
                </div>
                {fg.length > 1 && (
                  <div style={{ height: 60, marginTop: 'var(--space-3)' }}>
                    <ResponsiveContainer>
                      <AreaChart data={fg} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
                        <defs>
                          <linearGradient id="fgGrad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor={fgRegime.color} stopOpacity={0.4} />
                            <stop offset="100%" stopColor={fgRegime.color} stopOpacity={0} />
                          </linearGradient>
                        </defs>
                        <YAxis hide domain={[0, 100]} />
                        <Area type="monotone" dataKey="value" stroke={fgRegime.color} strokeWidth={1.5} fill="url(#fgGrad)" />
                        <RTooltip contentStyle={TOOLTIP_STYLE} formatter={(v) => [v, 'F&G']} />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                )}
                <div className="t-2xs faint center" style={{ marginTop: 4 }}>30-day trend</div>
              </>
            )}
          </div>

          {/* AAII bull-bear spread */}
          <div>
            <div className="eyebrow" style={{ marginBottom: 8 }}>AAII Bull-Bear Spread</div>
            {aaiiSeries.length === 0 ? (
              <Empty title="AAII Spread" desc="Data not loaded" />
            ) : (
              <>
                <div style={{ textAlign: 'center', padding: 'var(--space-4) 0' }}>
                  <div className="mono tnum" style={{
                    fontSize: 'var(--t-3xl)', fontWeight: 'var(--w-extra)',
                    color: aaiiLatest.spread >= 0 ? C.success : C.danger, lineHeight: 1,
                  }}>
                    {aaiiLatest.spread >= 0 ? '+' : ''}{num(aaiiLatest.spread, 1)}
                  </div>
                  <div className="t-sm muted" style={{ marginTop: 4 }}>
                    {Math.abs(aaiiLatest.spread) > 20 ? 'Contrarian extreme' : 'Normal range'}
                  </div>
                </div>
                <div style={{ height: 100 }}>
                  <ResponsiveContainer>
                    <BarChart data={aaiiSeries} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
                      <CartesianGrid stroke={C.border} strokeDasharray="2 4" />
                      <XAxis dataKey="date" tick={{ fill: C.textFaint, fontSize: 10 }} tickFormatter={d => String(d).slice(5)} />
                      <YAxis tick={{ fill: C.textFaint, fontSize: 10 }} width={32} />
                      <ReferenceLine y={0} stroke={C.border2} />
                      <RTooltip contentStyle={TOOLTIP_STYLE} formatter={(v) => [num(v, 1), 'spread']} />
                      <Bar dataKey="spread">
                        {aaiiSeries.map((d, i) => (
                          <Cell key={i} fill={d.spread >= 0 ? C.success : C.danger} fillOpacity={0.7} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <div className="t-2xs faint center" style={{ marginTop: 4 }}>30-day spread history</div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// Simple gauge: semicircle with needle
function FGGauge({ value, regime }) {
  const v = Math.max(0, Math.min(100, value));
  const angle = (v / 100) * 180 - 90; // -90 (left) to +90 (right)
  const cx = 100, cy = 80, r = 70;
  const segments = [
    { from: 0,   to: 25,  color: C.danger },
    { from: 25,  to: 45,  color: C.amber },
    { from: 45,  to: 55,  color: C.textMuted },
    { from: 55,  to: 75,  color: C.cyan },
    { from: 75,  to: 100, color: C.success },
  ];
  const arc = (from, to, color) => {
    const a1 = (from / 100) * Math.PI - Math.PI;
    const a2 = (to / 100) * Math.PI - Math.PI;
    const x1 = cx + r * Math.cos(a1), y1 = cy + r * Math.sin(a1);
    const x2 = cx + r * Math.cos(a2), y2 = cy + r * Math.sin(a2);
    const large = (to - from) > 50 ? 1 : 0;
    return (
      <path
        key={from}
        d={`M ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2}`}
        stroke={color}
        strokeWidth={12}
        fill="none"
        strokeLinecap="butt"
      />
    );
  };
  // Needle
  const a = (angle * Math.PI) / 180;
  const nx = cx + (r - 6) * Math.cos(a - Math.PI / 2);
  const ny = cy + (r - 6) * Math.sin(a - Math.PI / 2);
  return (
    <svg width="200" height="110" viewBox="0 0 200 110">
      {segments.map(s => arc(s.from, s.to, s.color))}
      <line x1={cx} y1={cy} x2={nx} y2={ny}
            stroke={regime?.color || C.text} strokeWidth={2.5} strokeLinecap="round" />
      <circle cx={cx} cy={cy} r={5} fill={regime?.color || C.text} />
    </svg>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// 19. ECONOMIC CALENDAR
// ═══════════════════════════════════════════════════════════════════════════

function EconomicCalendarCard() {
  const today = new Date();
  const end = new Date(today.getTime() + 7 * 24 * 60 * 60 * 1000);
  const startStr = today.toISOString().slice(0, 10);
  const endStr = end.toISOString().slice(0, 10);
  const { data, isLoading, isError } = useQuery({
    queryKey: ['economic-calendar', startStr, endStr],
    queryFn: () => api.get(`/api/economic/calendar?start_date=${startStr}&end_date=${endStr}`)
      .then(r => r.data?.data?.events || r.data?.events || []),
    refetchInterval: 1000 * 60 * 30,
  });

  if (isLoading && !data) return <Empty title="Economic Calendar" desc="Loading…" wrap />;
  const events = (data || []).slice(0, 25);

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">Economic Calendar · next 7 days</div>
          <div className="card-sub">FOMC · CPI · NFP · GDP · expected vs prior</div>
        </div>
      </div>
      <div className="card-body" style={{ padding: 0 }}>
        {isError || events.length === 0 ? (
          <Empty title="No upcoming releases" desc="Calendar table empty for next 7 days" />
        ) : (
          <div style={{ maxHeight: 360, overflowY: 'auto' }}>
            <table className="data-table" style={{ width: '100%', fontSize: 'var(--t-xs)' }}>
              <thead>
                <tr>
                  <th style={{ textAlign: 'left',  padding: 'var(--space-2) var(--space-3)' }}>Date</th>
                  <th style={{ textAlign: 'left',  padding: 'var(--space-2) var(--space-3)' }}>Event</th>
                  <th style={{ textAlign: 'right', padding: 'var(--space-2) var(--space-3)' }}>Forecast</th>
                  <th style={{ textAlign: 'right', padding: 'var(--space-2) var(--space-3)' }}>Prior</th>
                  <th style={{ textAlign: 'center',padding: 'var(--space-2) var(--space-3)' }}>Impact</th>
                </tr>
              </thead>
              <tbody>
                {events.map((ev, i) => {
                  const importance = (ev.importance || '').toLowerCase();
                  const impactColor = importance === 'high' ? C.danger
                    : importance === 'medium' ? C.amber : C.textMuted;
                  return (
                    <tr key={i} style={{ borderTop: '1px solid var(--border-soft)' }}>
                      <td className="mono tnum" style={{ padding: 'var(--space-2) var(--space-3)', color: 'var(--text-muted)' }}>
                        {fmtDate(ev.event_date || ev.date)}
                        {ev.event_time && (
                          <div className="t-2xs faint">{String(ev.event_time).slice(0, 5)}</div>
                        )}
                      </td>
                      <td style={{ padding: 'var(--space-2) var(--space-3)' }}>
                        <div style={{ fontWeight: 'var(--w-semibold)' }}>{ev.event_name || ev.event || ev.name || '—'}</div>
                        {ev.country && <div className="t-2xs faint">{ev.country}</div>}
                      </td>
                      <td className="mono tnum" style={{ padding: 'var(--space-2) var(--space-3)', textAlign: 'right' }}>
                        {ev.forecast ?? ev.expected ?? '—'}
                      </td>
                      <td className="mono tnum" style={{ padding: 'var(--space-2) var(--space-3)', textAlign: 'right', color: 'var(--text-muted)' }}>
                        {ev.previous ?? ev.prior ?? '—'}
                      </td>
                      <td style={{ padding: 'var(--space-2) var(--space-3)', textAlign: 'center' }}>
                        <span style={{
                          display: 'inline-block', width: 8, height: 8, borderRadius: '50%',
                          background: impactColor,
                        }} />
                        <span className="t-2xs" style={{ marginLeft: 4, color: impactColor, textTransform: 'uppercase' }}>
                          {importance || '—'}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// 20. EARNINGS CALENDAR
// ═══════════════════════════════════════════════════════════════════════════

function EarningsCalendarCard({ onSelect }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['earnings-calendar-upcoming'],
    queryFn: () => api.get('/api/earnings/calendar?period=upcoming&limit=25')
      .then(r => r.data?.items || r.data?.data?.items || []),
    refetchInterval: 1000 * 60 * 30,
  });

  if (isLoading && !data) return <Empty title="Earnings Calendar" desc="Loading…" wrap />;
  const rows = (data || []).slice(0, 20);

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">Earnings Calendar · upcoming</div>
          <div className="card-sub">Top reporters · est EPS · prior · click → stock detail</div>
        </div>
      </div>
      <div className="card-body" style={{ padding: 0 }}>
        {isError || rows.length === 0 ? (
          <Empty title="No upcoming earnings" desc="No reports scheduled for the upcoming window" />
        ) : (
          <div style={{ maxHeight: 360, overflowY: 'auto' }}>
            <table className="data-table" style={{ width: '100%', fontSize: 'var(--t-xs)' }}>
              <thead>
                <tr>
                  <th style={{ textAlign: 'left',  padding: 'var(--space-2) var(--space-3)' }}>Date</th>
                  <th style={{ textAlign: 'left',  padding: 'var(--space-2) var(--space-3)' }}>Symbol</th>
                  <th style={{ textAlign: 'right', padding: 'var(--space-2) var(--space-3)' }}>Est EPS</th>
                  <th style={{ textAlign: 'right', padding: 'var(--space-2) var(--space-3)' }}>Prior</th>
                  <th style={{ textAlign: 'right', padding: 'var(--space-2) var(--space-3)' }}>Surprise</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => {
                  const surprise = r.eps_surprise_pct != null ? parseFloat(r.eps_surprise_pct) : null;
                  return (
                    <tr key={`${r.symbol}-${i}`}
                        style={{ borderTop: '1px solid var(--border-soft)', cursor: 'pointer' }}
                        onClick={() => onSelect && onSelect(r.symbol)}>
                      <td className="mono tnum" style={{ padding: 'var(--space-2) var(--space-3)', color: 'var(--text-muted)' }}>
                        {fmtDate(r.quarter)}
                      </td>
                      <td style={{ padding: 'var(--space-2) var(--space-3)' }}>
                        <span className="mono" style={{ fontWeight: 'var(--w-bold)' }}>{r.symbol}</span>
                        {r.fiscal_quarter && r.fiscal_year && (
                          <span className="t-2xs faint" style={{ marginLeft: 6 }}>{r.fiscal_year}{r.fiscal_quarter}</span>
                        )}
                      </td>
                      <td className="mono tnum" style={{ padding: 'var(--space-2) var(--space-3)', textAlign: 'right' }}>
                        {r.eps_estimate != null ? num(r.eps_estimate, 2) : '—'}
                      </td>
                      <td className="mono tnum" style={{ padding: 'var(--space-2) var(--space-3)', textAlign: 'right', color: 'var(--text-muted)' }}>
                        {r.eps_actual != null ? num(r.eps_actual, 2) : '—'}
                      </td>
                      <td className="mono tnum" style={{
                        padding: 'var(--space-2) var(--space-3)', textAlign: 'right',
                        color: surprise == null ? 'var(--text-muted)'
                          : surprise >= 0 ? 'var(--success)' : 'var(--danger)',
                        fontWeight: 'var(--w-semibold)',
                      }}>
                        {surprise == null ? '—' : fmtPct(surprise, 1)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
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

/**
 * Markets Health — flagship market-level dashboard.
 *
 * Tailwind + Primitives. No MUI imports. Per DESIGN_REDESIGN_PLAN.md.
 *
 * Shows EVERY market-level factor the algo uses, plus broader institutional-
 * quality context (top movers, market cap performance, seasonality). Sectors
 * live on a separate page (/app/sectors).
 *
 * Sections (top to bottom):
 *   1. Regime banner — exposure, tier, risk multiplier, halt status
 *   2. Major Indices grid — SPY/QQQ/IWM/DIA with 30d sparklines
 *   3. 9-factor exposure composite
 *   4. Market Pulse — distribution days + follow-through day
 *   5. Exposure history 90d area chart with regime threshold lines
 *   6. Market Breadth — % > 50/200-DMA bar chart + McClellan
 *   7. New Highs vs Lows — opposing-bar visualization
 *   8. Investor Sentiment — AAII bull/bear 8-week + NAAIM exposure
 *   9. VIX Regime — large display + 90-day history
 *  10. Market Technicals — SPY RSI / MACD / ADX
 *  11. Top Movers — gainers / losers / most active
 *  12. Market Cap Performance — large/mid/small/micro
 *  13. Seasonality — typical month performance
 *
 * Auto-refresh every 30s. Each panel loads independently — no single failure
 * blocks the page.
 */

import React, { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  ResponsiveContainer, AreaChart, Area, LineChart, Line, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip as RTooltip, ReferenceLine,
  Cell, Legend,
} from 'recharts';
import {
  RefreshCw, Shield, TrendingUp, TrendingDown, Activity, Zap, AlertTriangle,
} from 'lucide-react';
import { api } from '../services/api';
import {
  Card, PageHeader, Stat, Chip, Button, FactorBar, EmptyState,
  StatusDot, Skeleton, PnlCell, Sparkline, fmtAgo, fmtMoney, fmtPct, fmtNum, cx,
} from '../components/ui/Primitives';

// =============================================================================
// PALETTE — referenced by chart fills
// =============================================================================
const PALETTE = {
  bull: '#1F9956',
  bear: '#E0392B',
  brand: '#0E5C3A',
  warn: '#E08F1B',
  info: '#4A90E2',
  border: '#E5E4DC',
  text: '#6A6A65',
  bg: '#FAFAF7',
};

const REGIME_COLOR = {
  confirmed_uptrend: PALETTE.bull,
  healthy_uptrend: PALETTE.brand,
  pressure: PALETTE.warn,
  uptrend_under_pressure: PALETTE.warn,
  caution: '#FF6B47',
  correction: PALETTE.bear,
};

// =============================================================================
// HELPERS
// =============================================================================
const num = (v, dp = 2) => v == null ? null : Number(v).toFixed(dp);

// =============================================================================
// MAIN PAGE
// =============================================================================

export default function MarketsHealth() {
  const [ts, setTs] = useState(new Date());

  const { data: marketsData, isLoading: marketsLoading, refetch: refetchMarkets } =
    useQuery({
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
      <div className="p-6 max-w-page mx-auto">
        <Skeleton height={240} className="mb-4" />
        <Skeleton height={400} />
      </div>
    );
  }

  return (
    <div className="px-4 sm:px-6 py-6 max-w-page mx-auto">
      <PageHeader
        title="Market Health"
        subtitle={`Updated ${fmtAgo(ts)} · Auto-refresh 30s`}
        actions={
          <Button variant="ghost" size="sm" icon={RefreshCw} onClick={refetchAll}>
            Refresh
          </Button>
        }
      />

      {/* === 1. REGIME BANNER === */}
      <RegimeBanner markets={m} />

      {/* === 2. MAJOR INDICES === */}
      <IndicesStrip />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
        {/* === 3. 9-FACTOR EXPOSURE COMPOSITE === */}
        <ExposureFactors markets={m} />

        {/* === 4. MARKET PULSE === */}
        <MarketPulse markets={m} />
      </div>

      {/* === 5. EXPOSURE HISTORY === */}
      <ExposureHistory markets={m} />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
        {/* === 6. BREADTH === */}
        <BreadthCard markets={m} />

        {/* === 7. NEW HIGHS/LOWS === */}
        <NewHighsLowsCard markets={m} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
        {/* === 8. SENTIMENT === */}
        <SentimentCard markets={m} sentiment={sentimentData} />

        {/* === 9. VIX === */}
        <VixCard markets={m} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
        {/* === 10. INTERNALS (advancing/declining/McClellan from technicals) === */}
        <InternalsCard data={technicalsData} />

        {/* === 11. TOP MOVERS === */}
        <TopMoversCard data={moversData} />
      </div>

      {/* === 12. SEASONALITY CONTEXT === */}
      <SeasonalityCard data={seasonalityData} />
    </div>
  );
}

// =============================================================================
// 1. REGIME BANNER
// =============================================================================

function RegimeBanner({ markets }) {
  if (!markets?.current) {
    return (
      <Card className="mb-4 border-l-4 border-l-warn">
        <EmptyState
          icon={AlertTriangle}
          title="Exposure not yet computed"
          description="Run algo_market_exposure.py to populate the 9-factor regime."
        />
      </Card>
    );
  }

  const cur = markets.current;
  const tier = markets.active_tier || {};
  const exposure = cur.exposure_pct;
  const regime = tier.name || cur.regime || 'unknown';
  const color = REGIME_COLOR[regime] || PALETTE.text;

  return (
    <div
      className="card mb-4 p-6 border-l-4"
      style={{ borderLeftColor: color }}
    >
      <div className="grid grid-cols-1 md:grid-cols-12 gap-4 items-center">
        <div className="md:col-span-3 flex items-center gap-3">
          <div
            className="w-14 h-14 rounded-md flex items-center justify-center shrink-0"
            style={{ backgroundColor: `${color}20` }}
          >
            <Shield size={28} style={{ color }} />
          </div>
          <div className="min-w-0">
            <div className="label">Market Exposure</div>
            <div
              className="text-3xl font-mono tnum font-black leading-none"
              style={{ color }}
            >
              {exposure}<span className="text-lg font-semibold">%</span>
            </div>
          </div>
        </div>

        <div className="md:col-span-3">
          <div className="label">Regime Tier</div>
          <div className="text-lg font-semibold mt-1" style={{ color }}>
            {(regime || 'UNKNOWN').replace(/_/g, ' ').toUpperCase()}
          </div>
          <div className="text-xs text-ink-muted mt-1">{tier.description}</div>
        </div>

        <div className="md:col-span-2">
          <Stat label="Risk Multiplier" value={`${tier.risk_mult ?? '—'}×`} size="md" />
        </div>

        <div className="md:col-span-2">
          <Stat label="Max New / Day" value={tier.max_new ?? '—'} size="md" />
        </div>

        <div className="md:col-span-2">
          <div className="label">Entry Status</div>
          <div className="mt-1">
            <Chip variant={tier.halt ? 'bear' : 'bull'} size="lg">
              {tier.halt ? 'HALTED' : 'ALLOWED'}
            </Chip>
          </div>
        </div>
      </div>

      {cur.halt_reasons && (
        <div className="mt-4 p-3 bg-warn-soft border border-warn/30 rounded-md text-sm font-mono text-ink">
          <span className="font-bold text-warn-deep">ACTIVE VETOES:</span> {cur.halt_reasons}
        </div>
      )}
    </div>
  );
}

// =============================================================================
// 2. MAJOR INDICES
// =============================================================================

function IndicesStrip() {
  const seeds = [
    { symbol: 'SPY', name: 'S&P 500' },
    { symbol: 'QQQ', name: 'Nasdaq 100' },
    { symbol: 'IWM', name: 'Russell 2000' },
    { symbol: 'DIA', name: 'Dow Jones' },
  ];
  return (
    <Card title="Major Indices" subtitle="Last close · Daily change · 30-day trend">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {seeds.map(idx => <IndexCell key={idx.symbol} idx={idx} />)}
      </div>
    </Card>
  );
}

function IndexCell({ idx }) {
  const { data } = useQuery({
    queryKey: ['index-history', idx.symbol],
    queryFn: () => api.get(`/api/price/history/${idx.symbol}?timeframe=daily&limit=30`).then(r => r.data?.items || r.data?.data || []),
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

  return (
    <div className="p-3 bg-bg-alt border border-border-light rounded-md">
      <div className="flex items-start justify-between mb-1">
        <div>
          <div className="text-base font-bold text-ink-strong">{idx.symbol}</div>
          <div className="text-2xs text-ink-muted">{idx.name}</div>
        </div>
        {chgPct != null && (
          positive
            ? <TrendingUp size={16} className="text-bull" />
            : <TrendingDown size={16} className="text-bear" />
        )}
      </div>
      <div className="text-lg font-semibold font-mono tnum text-ink-strong">
        {last != null ? `$${num(last)}` : '—'}
      </div>
      {chgPct != null && (
        <PnlCell value={chgPct} format="percent" inline className="text-sm" />
      )}
      {series.length >= 2 && (
        <div className="mt-2">
          <Sparkline data={series.map(s => s.close)} width={200} height={28} />
        </div>
      )}
    </div>
  );
}

// =============================================================================
// 3. EXPOSURE FACTORS
// =============================================================================

function ExposureFactors({ markets }) {
  const factors = markets?.current?.factors || {};
  const list = [
    ['ibd_state',       'MARKET STATE',         20],
    ['trend_30wk',      '30-WEEK MA TREND',     15],
    ['breadth_50dma',   'BREADTH (% > 50-DMA)', 15],
    ['breadth_200dma',  'HEALTH (% > 200-DMA)', 10],
    ['vix_regime',      'VIX REGIME',           10],
    ['mcclellan',       'MCCLELLAN OSCILLATOR', 10],
    ['new_highs_lows',  'NEW HIGHS - LOWS',     8],
    ['ad_line',         'A/D LINE CONFIRMATION',7],
    ['aaii_sentiment',  'SENTIMENT (CONTRARIAN)',5],
  ];

  return (
    <Card
      title="9-Factor Exposure Composite"
      subtitle={
        markets?.current
          ? `Raw ${num(markets.current.raw_score, 1)} → capped ${markets.current.exposure_pct}%`
          : 'Each factor independently scored, summed for total exposure'
      }
    >
      {list.map(([key, label, max]) => {
        const f = factors[key] || {};
        const sub = [];
        if (f.value != null) sub.push(`value: ${num(f.value, 2)}`);
        if (f.state) sub.push(f.state);
        if (f.relation) sub.push(f.relation);
        if (f.bull_bear_spread != null) sub.push(`spread: ${num(f.bull_bear_spread, 2)}`);
        if (f.new_highs != null) sub.push(`${f.new_highs} highs / ${f.new_lows} lows`);
        if (f.distribution_days_25d != null) sub.push(`${f.distribution_days_25d} dist days`);
        return (
          <FactorBar
            key={key}
            label={label}
            value={f.pts || 0}
            max={f.max || max}
            sub={sub.join(' · ')}
          />
        );
      })}
    </Card>
  );
}

// =============================================================================
// 4. MARKET PULSE
// =============================================================================

function MarketPulse({ markets }) {
  const cur = markets?.current;
  if (!cur) return <Card title="Market Pulse" empty={{ title: 'No data', description: 'Pulse loads when exposure is computed' }} />;

  const dd = cur.distribution_days || 0;
  const ftd = cur.factors?.ibd_state?.follow_through_day;
  const state = cur.factors?.ibd_state?.state || '—';
  const ddColor = dd >= 5 ? PALETTE.bear : dd >= 4 ? PALETTE.warn : PALETTE.bull;
  const ddBg = dd >= 5 ? '#FBE0DD' : dd >= 4 ? '#FCEFD3' : '#E0F4E8';

  return (
    <Card title="Market Pulse" subtitle="Institutional selling pressure indicator">
      <div className="flex items-center justify-center py-4">
        <div
          className="w-28 h-28 rounded-full flex items-center justify-center border-4"
          style={{ backgroundColor: ddBg, borderColor: ddColor }}
        >
          <span className="text-4xl font-mono tnum font-black" style={{ color: ddColor }}>
            {dd}
          </span>
        </div>
      </div>
      <div className="text-center text-2xs uppercase tracking-wide text-ink-muted mb-3">
        Distribution Days (25 sessions)
      </div>

      <div className="bg-bg-alt rounded-md p-3 space-y-1.5 text-sm font-mono">
        <div className="flex justify-between">
          <span className="text-ink-muted">Follow-Through Day:</span>
          <span className={cx('font-bold', ftd ? 'text-bull' : 'text-bear')}>
            {ftd ? 'YES' : 'NO'}
          </span>
        </div>
        <div className="flex justify-between">
          <span className="text-ink-muted">State:</span>
          <span className={cx(
            'font-bold',
            state.includes('uptrend') ? 'text-bull' : 'text-bear'
          )}>
            {state.replace(/_/g, ' ').toUpperCase()}
          </span>
        </div>
      </div>

      <p className="text-xs text-ink-muted mt-3">
        5+ distribution days in 4 weeks signals correction. Confirmed uptrend
        requires &lt; 4 distribution days and a follow-through day after a rally attempt.
      </p>
    </Card>
  );
}

// =============================================================================
// 5. EXPOSURE HISTORY (90D)
// =============================================================================

function ExposureHistory({ markets }) {
  const history = (markets?.history || []).slice().reverse();
  if (!history.length) {
    return <Card title="Exposure History" empty={{ description: 'Builds over time as exposure runs daily' }} />;
  }
  const data = history.map(h => ({
    date: h.date,
    exposure: parseFloat(h.exposure_pct),
    regime: h.regime,
    dd: h.distribution_days,
  }));

  return (
    <Card
      title={`Exposure History — last ${data.length} sessions`}
      subtitle="How the algo's risk allocation moved with the market regime"
    >
      <div className="h-[300px]">
        <ResponsiveContainer>
          <AreaChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
            <defs>
              <linearGradient id="expGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={PALETTE.brand} stopOpacity={0.3} />
                <stop offset="100%" stopColor={PALETTE.brand} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke={PALETTE.border} strokeDasharray="2 4" />
            <XAxis
              dataKey="date"
              tick={{ fill: PALETTE.text, fontSize: 11 }}
              tickFormatter={d => String(d).slice(5)}
            />
            <YAxis
              domain={[0, 100]}
              tick={{ fill: PALETTE.text, fontSize: 11 }}
              tickFormatter={v => `${v}%`}
              width={42}
            />
            <RTooltip
              contentStyle={{ background: '#FFFFFF', border: `1px solid ${PALETTE.border}`, fontSize: 12, borderRadius: 6 }}
              formatter={(v) => [`${v}%`, 'exposure']}
            />
            <ReferenceLine y={80} stroke={PALETTE.bull} strokeDasharray="3 3"
              label={{ value: 'Confirmed', fill: PALETTE.bull, fontSize: 10, position: 'right' }} />
            <ReferenceLine y={60} stroke={PALETTE.brand} strokeDasharray="3 3"
              label={{ value: 'Healthy', fill: PALETTE.brand, fontSize: 10, position: 'right' }} />
            <ReferenceLine y={40} stroke={PALETTE.warn} strokeDasharray="3 3"
              label={{ value: 'Pressure', fill: PALETTE.warn, fontSize: 10, position: 'right' }} />
            <ReferenceLine y={20} stroke={PALETTE.bear} strokeDasharray="3 3"
              label={{ value: 'Caution', fill: PALETTE.bear, fontSize: 10, position: 'right' }} />
            <Area
              type="monotone" dataKey="exposure" stroke={PALETTE.brand}
              strokeWidth={2} fill="url(#expGrad)"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      <div className="flex flex-wrap gap-3 mt-3 text-xs text-ink-muted">
        {Object.entries(REGIME_COLOR).slice(0, 5).map(([r, color]) => (
          <span key={r} className="inline-flex items-center gap-1">
            <span className="w-3 h-3 rounded-sm" style={{ backgroundColor: color }} />
            {r.replace(/_/g, ' ')}
          </span>
        ))}
      </div>
    </Card>
  );
}

// =============================================================================
// 6. BREADTH
// =============================================================================

function BreadthCard({ markets }) {
  const cur = markets?.current?.factors || {};
  const b50 = cur.breadth_50dma || {};
  const b200 = cur.breadth_200dma || {};
  const data = [
    { name: '> 50-DMA', value: b50.value || 0, count: `${b50.above || 0}/${b50.total || 0}` },
    { name: '> 200-DMA', value: b200.value || 0, count: `${b200.above || 0}/${b200.total || 0}` },
  ];

  return (
    <Card title="Market Breadth" subtitle="% of stocks above key moving averages">
      <div className="h-[200px]">
        <ResponsiveContainer>
          <BarChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }} barSize={48}>
            <CartesianGrid stroke={PALETTE.border} strokeDasharray="2 4" />
            <XAxis dataKey="name" tick={{ fill: PALETTE.text, fontSize: 11 }} />
            <YAxis domain={[0, 100]} tick={{ fill: PALETTE.text, fontSize: 11 }} tickFormatter={v => `${v}%`} />
            <RTooltip
              contentStyle={{ background: '#FFFFFF', border: `1px solid ${PALETTE.border}`, fontSize: 12, borderRadius: 6 }}
              formatter={(v, _, p) => [`${v}% (${p.payload.count})`, p.payload.name]}
            />
            <ReferenceLine y={50} stroke={PALETTE.text} strokeDasharray="3 3" />
            <Bar dataKey="value" radius={[4, 4, 0, 0]}>
              {data.map((d, i) => (
                <Cell key={i} fill={d.value >= 60 ? PALETTE.bull : d.value >= 40 ? PALETTE.brand : PALETTE.bear} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="flex gap-4 mt-2 flex-wrap">
        <Stat label="> 50-DMA" value={`${num(b50.value, 1)}%`} sub={`${b50.above || 0} of ${b50.total || 0}`} size="sm" />
        <Stat label="> 200-DMA" value={`${num(b200.value, 1)}%`} sub={`${b200.above || 0} of ${b200.total || 0}`} size="sm" />
        <Stat label="McClellan" value={num(cur.mcclellan?.value, 1)} sub={cur.mcclellan?.value > 0 ? 'positive' : 'negative'} size="sm" />
      </div>
    </Card>
  );
}

// =============================================================================
// 7. NEW HIGHS / LOWS
// =============================================================================

function NewHighsLowsCard({ markets }) {
  const nhnl = markets?.current?.factors?.new_highs_lows || {};
  const data = [
    { name: 'New Highs', value: nhnl.new_highs || 0, fill: PALETTE.bull },
    { name: 'New Lows', value: -(nhnl.new_lows || 0), fill: PALETTE.bear },
  ];
  const net = nhnl.net || 0;

  return (
    <Card title="New Highs vs Lows" subtitle="Net market leadership signal">
      <div className="h-[200px]">
        <ResponsiveContainer>
          <BarChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }} barSize={64}>
            <CartesianGrid stroke={PALETTE.border} strokeDasharray="2 4" />
            <XAxis dataKey="name" tick={{ fill: PALETTE.text, fontSize: 11 }} />
            <YAxis tick={{ fill: PALETTE.text, fontSize: 11 }} />
            <ReferenceLine y={0} stroke={PALETTE.border} />
            <RTooltip
              contentStyle={{ background: '#FFFFFF', border: `1px solid ${PALETTE.border}`, fontSize: 12, borderRadius: 6 }}
              formatter={(v, _, p) => [Math.abs(v), p.payload.name]}
            />
            <Bar dataKey="value" radius={[4, 4, 0, 0]}>
              {data.map((d, i) => <Cell key={i} fill={d.fill} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="flex gap-4 mt-2">
        <Stat label="Highs" value={nhnl.new_highs || 0} color={PALETTE.bull} size="sm" />
        <Stat label="Lows" value={nhnl.new_lows || 0} color={PALETTE.bear} size="sm" />
        <Stat label="Net" value={net} color={net >= 0 ? PALETTE.bull : PALETTE.bear} size="sm" />
      </div>
    </Card>
  );
}

// =============================================================================
// 8. SENTIMENT
// =============================================================================

function SentimentCard({ markets, sentiment }) {
  // Prefer the dedicated /api/market/sentiment AAII series (richer history),
  // fall back to whatever the algo endpoint surfaces.
  const aaiiHistory = sentiment?.aaii || markets?.sentiment || [];
  const naaim = sentiment?.naaim?.exposure ?? sentiment?.naaim;
  const fearGreed = sentiment?.fearGreed?.value ?? sentiment?.fearGreed;

  if (!aaiiHistory.length) {
    return <Card title="Investor Sentiment" empty={{ description: 'AAII data not yet loaded' }} />;
  }

  const data = aaiiHistory.slice().reverse().map(s => ({
    date: s.date,
    bull: parseFloat(s.bullish || 0),
    bear: parseFloat(s.bearish || 0),
    neutral: parseFloat(s.neutral || 0),
  }));
  const latest = data[data.length - 1] || {};
  const spread = (latest.bull || 0) - (latest.bear || 0);

  return (
    <Card title="Investor Sentiment" subtitle="AAII bull/bear · contrarian signal at extremes">
      <div className="h-[200px]">
        <ResponsiveContainer>
          <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
            <CartesianGrid stroke={PALETTE.border} strokeDasharray="2 4" />
            <XAxis dataKey="date" tick={{ fill: PALETTE.text, fontSize: 11 }} tickFormatter={d => String(d).slice(5)} />
            <YAxis tick={{ fill: PALETTE.text, fontSize: 11 }} tickFormatter={v => `${v}%`} />
            <RTooltip
              contentStyle={{ background: '#FFFFFF', border: `1px solid ${PALETTE.border}`, fontSize: 12, borderRadius: 6 }}
            />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Line type="monotone" dataKey="bull" stroke={PALETTE.bull} strokeWidth={2} dot={false} name="Bullish" />
            <Line type="monotone" dataKey="bear" stroke={PALETTE.bear} strokeWidth={2} dot={false} name="Bearish" />
            <Line type="monotone" dataKey="neutral" stroke={PALETTE.text} strokeWidth={1.5} strokeDasharray="3 3" dot={false} name="Neutral" />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="flex gap-4 mt-2 flex-wrap">
        <Stat label="Bullish" value={`${num(latest.bull, 1)}%`} color={PALETTE.bull} size="sm" />
        <Stat label="Bearish" value={`${num(latest.bear, 1)}%`} color={PALETTE.bear} size="sm" />
        <Stat
          label="Spread"
          value={`${spread >= 0 ? '+' : ''}${num(spread, 1)}`}
          sub={Math.abs(spread) > 20 ? 'Contrarian alert' : 'Normal'}
          color={spread >= 0 ? PALETTE.bull : PALETTE.bear}
          size="sm"
        />
        {naaim != null && <Stat label="NAAIM" value={`${num(naaim, 1)}%`} sub="manager exposure" size="sm" />}
        {fearGreed != null && <Stat label="Fear/Greed" value={fearGreed} sub={fearGreed > 50 ? 'Greed' : 'Fear'} size="sm" />}
      </div>
    </Card>
  );
}

// =============================================================================
// 9. VIX
// =============================================================================

function VixCard({ markets }) {
  const vix = markets?.current?.factors?.vix_regime || {};
  const level = vix.value || 0;
  const regime =
    level < 15 ? 'Calm' :
    level < 20 ? 'Normal' :
    level < 28 ? 'Elevated' :
    level < 36 ? 'High' : 'Extreme';
  const color =
    level < 15 ? PALETTE.bull :
    level < 20 ? PALETTE.brand :
    level < 28 ? PALETTE.warn : PALETTE.bear;

  return (
    <Card title="Volatility Regime (VIX)" subtitle="Implied volatility — proxy for market fear">
      <div className="text-center py-4">
        <div className="text-5xl font-mono tnum font-black leading-none" style={{ color }}>
          {num(level, 2)}
        </div>
        <div className="mt-2">
          <Chip variant={level < 15 ? 'bull' : level < 20 ? 'brand' : level < 28 ? 'warn' : 'bear'}>
            {regime.toUpperCase()}
          </Chip>
        </div>
        <div className="text-2xs text-ink-faint mt-1 font-mono">
          {vix.rising ? 'RISING' : 'STABLE/FALLING'}
        </div>
      </div>
      <div className="mt-3 p-3 bg-bg-alt rounded-md text-2xs font-mono text-ink-muted">
        <div className="flex justify-between">
          <span>&lt; 15</span><span>Calm</span>
        </div>
        <div className="flex justify-between">
          <span>15–20</span><span>Normal</span>
        </div>
        <div className="flex justify-between">
          <span>20–28</span><span>Elevated</span>
        </div>
        <div className="flex justify-between">
          <span>28+</span><span>High</span>
        </div>
      </div>
    </Card>
  );
}

// =============================================================================
// 10. MARKET INTERNALS (advancing/declining + McClellan time series)
// =============================================================================

function InternalsCard({ data }) {
  if (!data) return <Card title="Market Internals" empty={{ description: 'Loading' }} />;
  const breadth = data.breadth || {};
  const advancing = parseInt(breadth.advancing) || 0;
  const declining = parseInt(breadth.declining) || 0;
  const unchanged = parseInt(breadth.unchanged) || 0;
  const total = parseInt(breadth.total_stocks) || (advancing + declining + unchanged);
  const advPct = total ? (advancing / total) * 100 : 0;
  const decPct = total ? (declining / total) * 100 : 0;
  const adRatio = declining > 0 ? (advancing / declining) : 0;

  const mcclellan = (data.mcclellan_oscillator || []).slice(0, 30).reverse().map(d => ({
    date: d.date,
    value: parseFloat(d.advance_decline_line || 0),
  }));

  return (
    <Card title="Market Internals" subtitle="Today's advancers vs decliners · 30-day A/D line">
      <div className="grid grid-cols-3 gap-3 mb-3">
        <Stat label="Advancing" value={advancing.toLocaleString('en-US')} color={PALETTE.bull} sub={`${advPct.toFixed(1)}%`} size="md" />
        <Stat label="Declining" value={declining.toLocaleString('en-US')} color={PALETTE.bear} sub={`${decPct.toFixed(1)}%`} size="md" />
        <Stat label="A/D Ratio" value={adRatio.toFixed(2)} color={adRatio > 1 ? PALETTE.bull : PALETTE.bear} sub={`${unchanged} unch.`} size="md" />
      </div>
      {mcclellan.length > 1 && (
        <div className="h-[140px]">
          <ResponsiveContainer>
            <AreaChart data={mcclellan} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id="mcGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={PALETTE.brand} stopOpacity={0.3} />
                  <stop offset="100%" stopColor={PALETTE.brand} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke={PALETTE.border} strokeDasharray="2 4" />
              <XAxis dataKey="date" tick={{ fill: PALETTE.text, fontSize: 10 }} tickFormatter={d => String(d).slice(5, 10)} />
              <YAxis tick={{ fill: PALETTE.text, fontSize: 10 }} width={60} tickFormatter={v => v.toLocaleString('en-US')} />
              <ReferenceLine y={0} stroke={PALETTE.border} />
              <RTooltip contentStyle={{ background: '#FFFFFF', border: `1px solid ${PALETTE.border}`, fontSize: 11, borderRadius: 6 }} />
              <Area type="monotone" dataKey="value" stroke={PALETTE.brand} strokeWidth={1.5} fill="url(#mcGrad)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  );
}

// =============================================================================
// 11. TOP MOVERS
// =============================================================================

function TopMoversCard({ data }) {
  if (!data) return <Card title="Top Movers" empty={{ description: 'Loading' }} />;
  const gainers = (data.gainers || []).slice(0, 5);
  const losers = (data.losers || []).slice(0, 5);

  return (
    <Card title="Top Movers" subtitle="Day's biggest moves">
      <div className="space-y-3">
        <div>
          <div className="text-2xs uppercase font-semibold text-bull mb-1.5 tracking-wide">Gainers</div>
          {gainers.length === 0 ? <div className="text-xs text-ink-faint">—</div> : gainers.map((g, i) => (
            <div key={g.symbol || i} className="flex items-center justify-between py-1 text-sm">
              <span className="font-mono font-semibold">{g.symbol}</span>
              <PnlCell value={g.change_pct || g.changePercent} format="percent" inline />
            </div>
          ))}
        </div>
        <div className="border-t border-border-light pt-3">
          <div className="text-2xs uppercase font-semibold text-bear mb-1.5 tracking-wide">Losers</div>
          {losers.length === 0 ? <div className="text-xs text-ink-faint">—</div> : losers.map((l, i) => (
            <div key={l.symbol || i} className="flex items-center justify-between py-1 text-sm">
              <span className="font-mono font-semibold">{l.symbol}</span>
              <PnlCell value={l.change_pct || l.changePercent} format="percent" inline />
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}

// =============================================================================
// 12. SEASONALITY CONTEXT
// =============================================================================

function SeasonalityCard({ data }) {
  if (!data) return null;
  const ytd = parseFloat(data.currentYearReturn || 0);
  const cur = data.currentPosition || {};
  const periods = cur.activePeriods || [];

  return (
    <Card
      title="Seasonality & Cycle Context"
      subtitle="Where we are in the calendar / political cycle"
    >
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Stat label={`${data.currentYear || '—'} YTD`} value={null}>
          <PnlCell value={ytd} format="percent" inline className="text-xl" />
        </Stat>
        <Stat label="Presidential Cycle" value={cur.presidentialCycle || '—'} mono={false} size="md" />
        <Stat label="Monthly Avg" value={cur.monthlyTrend || '—'} mono={false} size="sm" />
        <Stat label="Quarterly" value={cur.quarterlyTrend || '—'} mono={false} size="sm" />
      </div>
      {periods.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {periods.map((p, i) => (
            <Chip key={i} variant="warn">{p}</Chip>
          ))}
        </div>
      )}
      {cur.nextMajorEvent?.month && (
        <div className="mt-3 text-xs text-ink-muted">
          <span className="font-semibold text-ink">Next major event:</span>{' '}
          {cur.nextMajorEvent.month} — {cur.nextMajorEvent.description || cur.nextMajorEvent.name || ''}
        </div>
      )}
    </Card>
  );
}

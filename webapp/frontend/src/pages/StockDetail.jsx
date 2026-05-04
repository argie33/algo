/**
 * Stock Detail — drilldown for /app/stock/:symbol.
 *
 * Tabs: Overview | Signals | Scores | Financials | Earnings.
 * Pulls data from existing endpoints + composes them into a single view.
 *
 * Tailwind + Primitives. No MUI imports. Per DESIGN_REDESIGN_PLAN.md §4 Page P.
 */

import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip as RTooltip, Bar, ComposedChart,
} from 'recharts';
import { ArrowLeft, RefreshCw, ExternalLink, TrendingUp, TrendingDown } from 'lucide-react';
import { api } from '../services/api';
import {
  Card, PageHeader, Stat, Chip, GradeChip, Button, Tabs, PnlCell,
  Skeleton, EmptyState, fmtAgo, cx,
} from '../components/ui/Primitives';

const PALETTE = {
  brand: '#0E5C3A', bull: '#1F9956', bear: '#E0392B',
  border: '#E5E4DC', text: '#6A6A65',
};

const num = (v, dp = 2) => v == null ? '—' : Number(v).toFixed(dp);
const fmtMoney = (v) => v == null ? '—' : `$${Number(v).toFixed(2)}`;
const fmtBig = (v) => {
  if (v == null) return '—';
  const n = Number(v);
  if (Math.abs(n) >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
  if (Math.abs(n) >= 1e6) return `$${(n / 1e6).toFixed(1)}M`;
  if (Math.abs(n) >= 1e3) return `$${(n / 1e3).toFixed(1)}K`;
  return `$${n.toFixed(2)}`;
};

// =============================================================================
// MAIN
// =============================================================================

export default function StockDetail() {
  const { symbol } = useParams();
  const navigate = useNavigate();
  const [tab, setTab] = useState('overview');

  const { data: priceData, isLoading: priceLoading } = useQuery({
    queryKey: ['stock-price', symbol],
    queryFn: () => api.get(`/api/price/history/${symbol}?timeframe=daily&limit=180`).then(r => r.data?.items || r.data?.data || []),
    enabled: !!symbol,
  });

  const { data: profileData } = useQuery({
    queryKey: ['stock-profile', symbol],
    queryFn: () => api.get(`/api/stocks/${symbol}`).then(r => r.data?.data || r.data).catch(() => null),
    enabled: !!symbol,
  });

  const { data: scoresData } = useQuery({
    queryKey: ['stock-scores', symbol],
    queryFn: () => api.get(`/api/scores/${symbol}`).then(r => r.data?.data || r.data).catch(() => null),
    enabled: !!symbol,
  });

  const { data: signalsData } = useQuery({
    queryKey: ['stock-signals', symbol],
    queryFn: () => api.get(`/api/signals/stocks?symbol=${symbol}&timeframe=daily&limit=20`)
      .then(r => r.data?.items || []).catch(() => []),
    enabled: !!symbol,
  });

  const series = (priceData || []).slice(-180).map(p => ({
    date: p.date,
    close: parseFloat(p.close || p.adj_close),
    volume: parseFloat(p.volume || 0),
  }));
  const last = series[series.length - 1]?.close;
  const prev = series[series.length - 2]?.close;
  const yearAgo = series[Math.max(0, series.length - 252)]?.close;
  const dayChg = last && prev ? ((last - prev) / prev) * 100 : null;
  const yearChg = last && yearAgo ? ((last - yearAgo) / yearAgo) * 100 : null;

  return (
    <div className="px-4 sm:px-6 py-6 max-w-page mx-auto">
      <button
        onClick={() => navigate(-1)}
        className="text-xs text-ink-muted hover:text-ink mb-2 inline-flex items-center gap-1"
      >
        <ArrowLeft size={12} /> Back
      </button>

      {/* HERO */}
      <Card className="mb-4 border-l-4 border-l-brand" padded>
        <div className="grid grid-cols-1 md:grid-cols-12 gap-4 items-center">
          <div className="md:col-span-4">
            <div className="text-3xl font-black text-ink-strong">{symbol}</div>
            <div className="text-sm text-ink-muted">
              {profileData?.long_name || profileData?.name || 'Stock'}
            </div>
            <div className="flex items-center gap-2 mt-1 flex-wrap">
              {profileData?.sector && <Chip variant="brand">{profileData.sector}</Chip>}
              {profileData?.industry && <Chip variant="muted">{profileData.industry}</Chip>}
            </div>
          </div>

          <div className="md:col-span-2">
            <Stat
              label="Last Close"
              value={fmtMoney(last)}
              size="xl"
            />
            {dayChg != null && <PnlCell value={dayChg} format="percent" inline className="text-sm mt-1" />}
          </div>

          <div className="md:col-span-2">
            <Stat label="1-Year Return" value={null} size="md" />
            {yearChg != null && <PnlCell value={yearChg} format="percent" inline className="text-base font-semibold" />}
          </div>

          <div className="md:col-span-2">
            <Stat
              label="Market Cap"
              value={fmtBig(profileData?.market_cap)}
              size="md"
            />
          </div>

          <div className="md:col-span-2">
            <Stat
              label="Avg Vol"
              value={profileData?.average_volume ? Number(profileData.average_volume).toLocaleString('en-US') : '—'}
              size="sm"
            />
          </div>
        </div>
      </Card>

      {/* CHART */}
      <Card title="Price · 6 months" subtitle="Daily close + volume" padded>
        {priceLoading ? <Skeleton height={300} /> : !series.length ? (
          <EmptyState title="No price data" description="No history available for this symbol" />
        ) : (
          <div className="h-[320px]">
            <ResponsiveContainer>
              <ComposedChart data={series} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
                <defs>
                  <linearGradient id="closeGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={PALETTE.brand} stopOpacity={0.3} />
                    <stop offset="100%" stopColor={PALETTE.brand} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke={PALETTE.border} strokeDasharray="2 4" />
                <XAxis
                  dataKey="date" tick={{ fill: PALETTE.text, fontSize: 11 }}
                  tickFormatter={d => String(d).slice(5)}
                />
                <YAxis
                  yAxisId="left" tick={{ fill: PALETTE.text, fontSize: 11 }}
                  tickFormatter={v => `$${v}`} domain={['auto', 'auto']}
                />
                <YAxis
                  yAxisId="right" orientation="right" tick={{ fill: PALETTE.text, fontSize: 11 }}
                  tickFormatter={v => v >= 1e6 ? `${(v/1e6).toFixed(0)}M` : `${(v/1e3).toFixed(0)}K`}
                />
                <RTooltip
                  contentStyle={{ background: '#FFFFFF', border: `1px solid ${PALETTE.border}`, fontSize: 12, borderRadius: 6 }}
                />
                <Bar yAxisId="right" dataKey="volume" fill={PALETTE.border} opacity={0.6} />
                <Area
                  yAxisId="left" type="monotone" dataKey="close"
                  stroke={PALETTE.brand} strokeWidth={2} fill="url(#closeGrad)"
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        )}
      </Card>

      {/* TABS */}
      <Tabs
        tabs={[
          { value: 'overview', label: 'Overview' },
          { value: 'signals',  label: 'Signals',  count: signalsData?.length },
          { value: 'scores',   label: 'Scores' },
        ]}
        value={tab} onChange={setTab}
        className="mb-4"
      />

      {tab === 'overview' && <OverviewTab profile={profileData} scores={scoresData} />}
      {tab === 'signals'  && <SignalsTab signals={signalsData} />}
      {tab === 'scores'   && <ScoresTab scores={scoresData} />}
    </div>
  );
}

// =============================================================================
// TABS
// =============================================================================

function OverviewTab({ profile, scores }) {
  if (!profile && !scores) {
    return <Card empty={{ title: 'No data', description: 'Profile not yet loaded for this symbol' }} />;
  }
  const stats = [
    ['Composite score', scores?.composite_score, '/100'],
    ['Quality',         scores?.quality_score,    '/100'],
    ['Momentum',        scores?.momentum_score,   '/100'],
    ['Value',           scores?.value_score,      '/100'],
    ['Growth',          scores?.growth_score,     '/100'],
    ['Stability',       scores?.stability_score,  '/100'],
    ['52w high',        profile?.fifty_two_week_high, '$'],
    ['52w low',         profile?.fifty_two_week_low,  '$'],
    ['Beta',            profile?.beta, ''],
    ['P/E',             profile?.trailing_pe, ''],
    ['Forward P/E',     profile?.forward_pe, ''],
    ['EPS (TTM)',       profile?.trailing_eps, '$'],
    ['Dividend yield',  profile?.dividend_yield, '%'],
    ['Shares out',      profile?.shares_outstanding, ''],
    ['Float',           profile?.float_shares, ''],
  ];
  return (
    <Card padded>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {stats.map(([label, value, suffix]) => (
          <Stat
            key={label}
            label={label}
            value={value == null ? '—' :
              suffix === '$' ? fmtMoney(value) :
              suffix === '%' ? `${(Number(value) * 100).toFixed(2)}%` :
              suffix === '/100' ? num(value, 1) :
              suffix === '' && Number(value) > 1e6 ? Number(value).toLocaleString('en-US') :
              num(value, 2)
            }
            size="sm"
          />
        ))}
      </div>
    </Card>
  );
}

function SignalsTab({ signals }) {
  if (!signals?.length) {
    return <Card empty={{ title: 'No signals', description: 'No buy/sell signals in the last 20 sessions' }} />;
  }
  return (
    <Card padded>
      <div className="space-y-1">
        {signals.map((s, i) => (
          <div
            key={i}
            className="flex items-center gap-3 p-2 rounded hover:bg-bg-alt text-sm"
          >
            <Chip variant={s.signal === 'BUY' ? 'bull' : 'bear'} className="w-12 justify-center">
              {s.signal}
            </Chip>
            <span className="font-mono tnum text-ink-muted">{String(s.signal_triggered_date || s.date).slice(0, 10)}</span>
            <span className="font-mono tnum">{fmtMoney(s.close)}</span>
            {s.buylevel && <span className="text-ink-muted text-xs">buy {fmtMoney(s.buylevel)}</span>}
            {s.stoplevel && <span className="text-ink-muted text-xs">stop {fmtMoney(s.stoplevel)}</span>}
            {s.market_stage && <Chip variant="muted">{s.market_stage}</Chip>}
            <div className="flex-1" />
            {s.risk_reward_ratio && (
              <span className="font-mono tnum text-xs text-ink-muted">
                R/R {Number(s.risk_reward_ratio).toFixed(2)}
              </span>
            )}
          </div>
        ))}
      </div>
    </Card>
  );
}

function ScoresTab({ scores }) {
  if (!scores) {
    return <Card empty={{ title: 'No scores' }} />;
  }
  const items = [
    ['Composite',    scores.composite_score],
    ['Quality',      scores.quality_score],
    ['Momentum',     scores.momentum_score],
    ['Value',        scores.value_score],
    ['Growth',       scores.growth_score],
    ['Stability',    scores.stability_score],
    ['Positioning',  scores.positioning_score],
  ];
  return (
    <Card padded>
      <div className="space-y-3">
        {items.map(([label, value]) => {
          const v = value == null ? null : Number(value);
          const pct = v == null ? 0 : Math.max(0, Math.min(100, v));
          const color = v == null ? '#9A9A95' :
            v >= 80 ? '#1F9956' :
            v >= 60 ? '#0E5C3A' :
            v >= 40 ? '#E08F1B' : '#E0392B';
          return (
            <div key={label}>
              <div className="flex justify-between mb-1">
                <span className="label">{label}</span>
                <span className="font-mono tnum text-sm font-semibold">
                  {v == null ? '—' : v.toFixed(1)}
                </span>
              </div>
              <div className="h-2 bg-bg-alt rounded-sm overflow-hidden">
                <div
                  className="h-full transition-all"
                  style={{ width: `${pct}%`, backgroundColor: color }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

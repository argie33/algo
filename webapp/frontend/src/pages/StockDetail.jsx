/**
 * Stock Detail — drilldown for /app/stock/:symbol.
 * Pure JSX + theme.css classes.
 */

import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  ResponsiveContainer, ComposedChart, Area, Bar, XAxis, YAxis,
  CartesianGrid, Tooltip as RTooltip,
} from 'recharts';
import { ArrowLeft, RefreshCw, Inbox } from 'lucide-react';
import { api } from '../services/api';

const C_brand = '#6366f1';
const C_brand2 = '#818cf8';
const C_border = '#232838';
const C_text = '#e8eaf4';
const C_text_faint = '#6b7a99';

const num = (v, dp = 2) => v == null || isNaN(Number(v)) ? '—' : Number(v).toFixed(dp);
const fmtMoney = (v) => v == null ? '—' : `$${Number(v).toFixed(2)}`;
const fmtBig = (v) => {
  if (v == null) return '—';
  const n = Number(v);
  if (Math.abs(n) >= 1e12) return `$${(n / 1e12).toFixed(2)}T`;
  if (Math.abs(n) >= 1e9)  return `$${(n / 1e9).toFixed(2)}B`;
  if (Math.abs(n) >= 1e6)  return `$${(n / 1e6).toFixed(1)}M`;
  if (Math.abs(n) >= 1e3)  return `$${(n / 1e3).toFixed(1)}K`;
  return `$${n.toFixed(2)}`;
};

export default function StockDetail() {
  const { symbol } = useParams();
  const navigate = useNavigate();
  const [tab, setTab] = useState('overview');

  const { data: priceData, isLoading: priceLoading, refetch: refetchPrice } = useQuery({
    queryKey: ['stock-price', symbol],
    queryFn: () => api.get(`/api/prices/history/${symbol}?timeframe=daily&limit=180`)
      .then(r => r.data?.data?.items || r.data?.items || []),
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
    date: p.date, close: parseFloat(p.close || p.adj_close), volume: parseFloat(p.volume || 0),
  }));
  const last = series[series.length - 1]?.close;
  const prev = series[series.length - 2]?.close;
  const yearAgo = series[Math.max(0, series.length - 252)]?.close;
  const dayChg = last && prev ? ((last - prev) / prev) * 100 : null;
  const yearChg = last && yearAgo ? ((last - yearAgo) / yearAgo) * 100 : null;

  const profile = profileData?.profile || profileData?.stock || profileData || {};

  return (
    <div className="main-content">
      <button className="btn btn-ghost btn-sm" onClick={() => navigate(-1)} style={{ marginBottom: 8 }}>
        <ArrowLeft size={14} /> Back
      </button>

      <div className="card" style={{ borderLeft: '3px solid var(--brand)', padding: 'var(--space-6)' }}>
        <div className="grid" style={{ gridTemplateColumns: '2fr 1fr 1fr 1fr 1fr', gap: 'var(--space-4)', alignItems: 'center' }}>
          <div>
            <div style={{ fontSize: 'var(--t-3xl)', fontWeight: 'var(--w-extra)', letterSpacing: '-0.025em', color: 'var(--text)', lineHeight: 1 }}>
              {symbol}
            </div>
            <div className="muted t-sm" style={{ marginTop: 4 }}>{profile.long_name || profile.name || profile.short_name || 'Stock'}</div>
            <div className="flex gap-2" style={{ marginTop: 8, flexWrap: 'wrap' }}>
              {profile.sector && <span className="badge badge-brand">{profile.sector}</span>}
              {profile.industry && <span className="badge">{profile.industry}</span>}
            </div>
          </div>
          <div>
            <div className="eyebrow">Last Close</div>
            <div className="mono tnum" style={{ fontSize: 'var(--t-2xl)', fontWeight: 'var(--w-bold)', marginTop: 4 }}>{fmtMoney(last)}</div>
            {dayChg != null && (
              <div className={`mono tnum ${dayChg >= 0 ? 'up' : 'down'} t-sm`} style={{ fontWeight: 'var(--w-semibold)' }}>
                {dayChg >= 0 ? '+' : ''}{num(dayChg, 2)}%
              </div>
            )}
          </div>
          <div>
            <div className="eyebrow">1y Return</div>
            <div className={`mono tnum ${yearChg >= 0 ? 'up' : 'down'}`} style={{ fontSize: 'var(--t-xl)', fontWeight: 'var(--w-bold)', marginTop: 4 }}>
              {yearChg != null ? (yearChg >= 0 ? '+' : '') + num(yearChg, 1) + '%' : '—'}
            </div>
          </div>
          <div>
            <div className="eyebrow">Market Cap</div>
            <div className="mono tnum" style={{ fontSize: 'var(--t-xl)', fontWeight: 'var(--w-bold)', marginTop: 4 }}>{fmtBig(profile.market_cap)}</div>
          </div>
          <div>
            <div className="eyebrow">Avg Vol</div>
            <div className="mono tnum" style={{ fontSize: 'var(--t-md)', marginTop: 4 }}>
              {profile.average_volume ? Number(profile.average_volume).toLocaleString('en-US') : '—'}
            </div>
          </div>
        </div>
      </div>

      <div className="card" style={{ marginTop: 'var(--space-4)' }}>
        <div className="card-head">
          <div>
            <div className="card-title">Price · 6 months</div>
            <div className="card-sub">Daily close + volume</div>
          </div>
          <div className="card-actions">
            <button className="btn btn-icon btn-ghost" onClick={() => refetchPrice()}><RefreshCw size={14} /></button>
          </div>
        </div>
        <div className="card-body" style={{ padding: 'var(--space-4)' }}>
          {priceLoading ? <Empty title="Loading…" /> : !series.length ? (
            <Empty title="No price data" desc="No history available for this symbol." />
          ) : (
            <div style={{ height: 360 }}>
              <ResponsiveContainer>
                <ComposedChart data={series} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
                  <defs>
                    <linearGradient id="closeGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={C_brand2} stopOpacity={0.4} />
                      <stop offset="100%" stopColor={C_brand2} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke={C_border} strokeDasharray="2 4" />
                  <XAxis dataKey="date" tick={{ fill: C_text_faint, fontSize: 11 }} tickFormatter={d => String(d).slice(5)} />
                  <YAxis yAxisId="left" tick={{ fill: C_text_faint, fontSize: 11 }} tickFormatter={v => `$${v}`} domain={['auto', 'auto']} />
                  <YAxis yAxisId="right" orientation="right" tick={{ fill: C_text_faint, fontSize: 11 }}
                    tickFormatter={v => v >= 1e6 ? `${(v / 1e6).toFixed(0)}M` : `${(v / 1e3).toFixed(0)}K`} />
                  <RTooltip contentStyle={{ background: '#141720', border: `1px solid ${C_border}`, borderRadius: 8, fontSize: 12, color: C_text }} />
                  <Bar yAxisId="right" dataKey="volume" fill={C_border} opacity={0.6} />
                  <Area yAxisId="left" type="monotone" dataKey="close" stroke={C_brand2} strokeWidth={2} fill="url(#closeGrad)" />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      </div>

      <div style={{ display: 'flex', borderBottom: '1px solid var(--border)', marginTop: 'var(--space-4)' }}>
        {[['overview','Overview'],['signals','Signals'],['scores','Scores']].map(([v, l]) => (
          <button key={v} type="button" onClick={() => setTab(v)} style={{
            background: 'transparent', border: 'none',
            borderBottom: `2px solid ${tab === v ? 'var(--brand)' : 'transparent'}`,
            color: tab === v ? 'var(--brand-2)' : 'var(--text-muted)',
            fontWeight: tab === v ? 'var(--w-semibold)' : 'var(--w-medium)',
            fontSize: 'var(--t-sm)', padding: '12px 16px', cursor: 'pointer', marginBottom: -1,
          }}>{l} {v === 'signals' && signalsData?.length > 0 && (
            <span className="badge mono tnum" style={{ marginLeft: 6 }}>{signalsData.length}</span>
          )}</button>
        ))}
      </div>

      <div style={{ marginTop: 'var(--space-4)' }}>
        {tab === 'overview' && <OverviewTab profile={profile} scores={scoresData} />}
        {tab === 'signals'  && <SignalsTab signals={signalsData} />}
        {tab === 'scores'   && <ScoresTab scores={scoresData} />}
      </div>
    </div>
  );
}

function OverviewTab({ profile, scores }) {
  const stats = [
    ['Composite score', scores?.composite_score, '/100'],
    ['Quality', scores?.quality_score, '/100'],
    ['Momentum', scores?.momentum_score, '/100'],
    ['Value', scores?.value_score, '/100'],
    ['Growth', scores?.growth_score, '/100'],
    ['Stability', scores?.stability_score, '/100'],
    ['52w high', profile?.fifty_two_week_high, '$'],
    ['52w low', profile?.fifty_two_week_low, '$'],
    ['Beta', profile?.beta, ''],
    ['P/E (TTM)', profile?.trailing_pe, ''],
    ['Forward P/E', profile?.forward_pe, ''],
    ['EPS (TTM)', profile?.trailing_eps, '$'],
    ['Dividend yield', profile?.dividend_yield, '%'],
    ['Shares out', profile?.shares_outstanding, 'big'],
    ['Float', profile?.float_shares, 'big'],
  ];
  const fmt = (val, suf) => {
    if (val == null) return '—';
    if (suf === '$') return fmtMoney(val);
    if (suf === '%') return `${(Number(val) * 100).toFixed(2)}%`;
    if (suf === '/100') return num(val, 1);
    if (suf === 'big') return Number(val).toLocaleString('en-US');
    return num(val);
  };
  return (
    <div className="card card-pad">
      <div className="grid grid-4">
        {stats.map(([label, val, suf]) => (
          <div className="stile" key={label}>
            <div className="stile-label">{label}</div>
            <div className="stile-value">{fmt(val, suf)}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function SignalsTab({ signals }) {
  if (!signals?.length) return <Empty title="No signals" desc="No buy/sell signals in the last 20 sessions" wrap />;
  return (
    <div className="card card-pad">
      <div className="flex flex-col gap-2">
        {signals.map((s, i) => (
          <div key={i} className="panel flex items-center gap-3" style={{ padding: 'var(--space-3) var(--space-4)' }}>
            <span className={`badge ${s.signal === 'BUY' ? 'badge-success' : 'badge-danger'}`} style={{ minWidth: 48, justifyContent: 'center' }}>{s.signal}</span>
            <span className="mono muted t-xs">{String(s.signal_triggered_date || s.date).slice(0, 10)}</span>
            <span className="mono tnum">{fmtMoney(s.close)}</span>
            {s.buylevel && <span className="muted t-xs">buy {fmtMoney(s.buylevel)}</span>}
            {s.stoplevel && <span className="muted t-xs">stop {fmtMoney(s.stoplevel)}</span>}
            {s.market_stage && <span className="badge">{s.market_stage}</span>}
            <div className="flex-1" />
            {s.risk_reward_ratio && <span className="mono tnum t-xs muted">R/R {Number(s.risk_reward_ratio).toFixed(2)}</span>}
          </div>
        ))}
      </div>
    </div>
  );
}

function ScoresTab({ scores }) {
  if (!scores) return <Empty title="No scores" wrap />;
  const items = [
    ['Composite', scores.composite_score],
    ['Quality', scores.quality_score],
    ['Momentum', scores.momentum_score],
    ['Value', scores.value_score],
    ['Growth', scores.growth_score],
    ['Stability', scores.stability_score],
    ['Positioning', scores.positioning_score],
  ];
  return (
    <div className="card card-pad">
      <div className="flex flex-col" style={{ gap: 'var(--space-3)' }}>
        {items.map(([label, value]) => {
          const v = value == null ? null : Number(value);
          const pct = v == null ? 0 : Math.max(0, Math.min(100, v));
          const fillClass = v == null ? '' : v >= 80 ? 'success' : v >= 60 ? '' : v >= 40 ? 'warn' : 'danger';
          return (
            <div key={label}>
              <div className="flex items-center justify-between" style={{ marginBottom: 4 }}>
                <span className="eyebrow">{label}</span>
                <span className="mono tnum t-sm strong">{v == null ? '—' : v.toFixed(1)}</span>
              </div>
              <div className="bar"><div className={`bar-fill ${fillClass}`} style={{ width: `${pct}%` }} /></div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Empty({ title, desc, wrap }) {
  const inner = (
    <div className="empty">
      <Inbox />
      <div className="empty-title">{title}</div>
      {desc && <div className="empty-desc">{desc}</div>}
    </div>
  );
  return wrap ? <div className="card card-pad">{inner}</div> : inner;
}

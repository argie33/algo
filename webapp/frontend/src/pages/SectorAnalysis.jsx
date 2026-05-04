/**
 * Sector Analysis — sector + industry rankings, daily strength, ranking trend.
 * Plus deeper analytics: Mansfield RS rotation, momentum spider, sector breadth,
 * stage-2 leaders, sector-vs-SPY relative line, defensive/cyclical signal.
 *
 * Pure JSX + theme.css classes. Recharts only.
 */

import React, { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  RefreshCw, Inbox, AlertCircle, ChevronDown, ChevronRight,
  TrendingUp, TrendingDown, Minus,
} from 'lucide-react';
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid,
  ResponsiveContainer, Tooltip, Cell, Legend,
  ScatterChart, Scatter, ZAxis, ReferenceLine,
  RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar,
  AreaChart, Area,
} from 'recharts';
import { api } from '../services/api';
import { formatPercentageChange } from '../utils/formatters';
import { formatXAxisDate } from '../utils/dateFormatters';

const TT_STYLE = {
  background: 'var(--surface)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--r-sm)',
  fontSize: 'var(--t-xs)',
  padding: 'var(--space-2) var(--space-3)',
};

const SECTOR_COLORS = {
  Technology: 'var(--brand)',
  Healthcare: 'var(--success)',
  Financials: 'var(--amber)',
  'Consumer Discretionary': 'var(--purple)',
  'Consumer Staples': '#795548',
  Energy: 'var(--danger)',
  Industrials: '#607D8B',
  Materials: '#8BC34A',
  Utilities: '#FFC107',
  'Real Estate': '#E91E63',
  'Communication Services': 'var(--cyan)',
};
const FALLBACK_PALETTE = [
  'var(--brand)', 'var(--cyan)', 'var(--purple)', 'var(--success)',
  'var(--amber)', 'var(--danger)', '#8BC34A', '#E91E63',
  '#FFC107', '#795548', '#607D8B', '#FF6B6B',
];
const colorFor = (name, idx) =>
  SECTOR_COLORS[name] || FALLBACK_PALETTE[idx % FALLBACK_PALETTE.length];

const num = (v, dp = 2) => v == null || isNaN(Number(v)) ? '—' : Number(v).toFixed(dp);
const fmtPct = (v) => formatPercentageChange(v);
const pctClass = (v) => {
  const n = Number(v);
  if (!isFinite(n)) return 'flat';
  if (n > 0) return 'up';
  if (n < 0) return 'down';
  return 'flat';
};

const computeMA = (values, period) =>
  values.map((_, i) => {
    if (i < period - 1) return null;
    const slice = values.slice(i - period + 1, i + 1).filter(v => v != null);
    if (slice.length < Math.ceil(period * 0.7)) return null;
    return slice.reduce((a, b) => a + b, 0) / slice.length;
  });

const enrichWithMAs = (rows) => {
  if (!rows?.length) return rows || [];
  const series = rows.map(r => r.dailyStrengthScore);
  const ma10 = computeMA(series, 10);
  const ma20 = computeMA(series, 20);
  return rows.map((r, i) => ({
    ...r,
    ma_10: r.ma_10 ?? ma10[i],
    ma_20: r.ma_20 ?? ma20[i],
  }));
};

const TimeRangeChips = ({ value, onChange }) => {
  const opts = [
    { v: '3m', label: '3M' },
    { v: '6m', label: '6M' },
    { v: '1y', label: '1Y' },
  ];
  return (
    <div className="flex gap-2">
      {opts.map(o => (
        <button
          key={o.v}
          type="button"
          className={`btn btn-sm ${value === o.v ? 'btn-primary' : 'btn-outline'}`}
          onClick={() => onChange(o.v)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
};

const filterByRange = (rows, range) => {
  if (!rows?.length || !rows[0]?.date) return rows || [];
  const cutoff = new Date();
  if (range === '3m') cutoff.setMonth(cutoff.getMonth() - 3);
  else if (range === '6m') cutoff.setMonth(cutoff.getMonth() - 6);
  else cutoff.setFullYear(cutoff.getFullYear() - 1);
  const out = rows.filter(r => {
    try { return new Date(r.date) >= cutoff; } catch { return true; }
  });
  return out.length > 0 ? out : rows;
};

const TrendIcon = ({ trend, size = 16 }) => {
  const t = (trend || '').toLowerCase();
  if (t.includes('up')) return <TrendingUp size={size} style={{ color: 'var(--success)' }} />;
  if (t.includes('down')) return <TrendingDown size={size} style={{ color: 'var(--danger)' }} />;
  return <Minus size={size} style={{ color: 'var(--text-faint)' }} />;
};

const momentumBadge = (m) => {
  if (m === 'Strong') return 'badge-success';
  if (m === 'Moderate') return 'badge-cyan';
  if (m === 'Weak') return 'badge-amber';
  return '';
};

// ─── Mansfield RS rotation chart (4-quadrant scatter) ──────────────────────
function MansfieldRotation({ sectors }) {
  const data = useMemo(() => {
    if (!sectors || sectors.length === 0) return [];
    // RS-rank percentile = 100 * (N - rank + 1) / N (higher = stronger)
    // RS-momentum = change in rank over 1 week (rank_1w_ago - current_rank);
    //               positive value = rank improved (got stronger)
    const N = sectors.filter(s => s.current_rank != null).length || sectors.length;
    return sectors
      .filter(s => s.current_rank != null && (s.sector_name || s.sector))
      .map((s, i) => {
        const name = s.sector_name || s.sector;
        const rank = Number(s.current_rank);
        const rsPct = ((N - rank + 1) / N) * 100;
        const w1 = s.rank_1w_ago != null ? (Number(s.rank_1w_ago) - rank) : 0;
        const stockCount = Number(s.stock_count || 1);
        return {
          name,
          rs: Math.round(rsPct * 10) / 10,
          momentum: w1,
          size: stockCount,
          color: colorFor(name, i),
        };
      });
  }, [sectors]);

  if (data.length === 0) return <Empty title="No sector RS data" />;

  return (
    <div style={{ width: '100%', height: 380, position: 'relative' }}>
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart margin={{ top: 16, right: 24, bottom: 32, left: 0 }}>
          <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" />
          <XAxis type="number" dataKey="rs" name="RS Rank %ile" domain={[0, 100]}
                 stroke="var(--text-3)" fontSize={11}
                 label={{ value: 'RS Rank Percentile (higher = stronger)',
                          position: 'insideBottom', offset: -16,
                          fill: 'var(--text-3)', fontSize: 11 }} />
          <YAxis type="number" dataKey="momentum" name="1W Rank Δ"
                 stroke="var(--text-3)" fontSize={11} width={48}
                 label={{ value: '1W rank change (+ = improving)',
                          angle: -90, position: 'insideLeft',
                          fill: 'var(--text-3)', fontSize: 11 }} />
          <ZAxis type="number" dataKey="size" range={[60, 360]} name="Stocks" />
          <ReferenceLine x={50} stroke="var(--border)" strokeDasharray="3 3" />
          <ReferenceLine y={0} stroke="var(--border)" strokeDasharray="3 3" />
          <Tooltip contentStyle={TT_STYLE}
            formatter={(v, n) => {
              if (n === 'RS Rank %ile') return [`${v}%`, n];
              if (n === '1W Rank Δ') return [v > 0 ? `+${v}` : v, n];
              return [v, n];
            }}
            labelFormatter={() => ''}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const p = payload[0].payload;
              return (
                <div style={TT_STYLE}>
                  <div className="strong">{p.name}</div>
                  <div className="t-xs muted mono tnum">RS: {p.rs}%</div>
                  <div className="t-xs muted mono tnum">
                    Momentum: {p.momentum > 0 ? `+${p.momentum}` : p.momentum}
                  </div>
                  <div className="t-xs muted mono tnum">Stocks: {p.size}</div>
                </div>
              );
            }} />
          <Scatter data={data}>
            {data.map((d, i) => (
              <Cell key={i} fill={d.color} />
            ))}
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
      {/* Quadrant labels */}
      <QuadrantLabel pos={{ top: 8, right: 24 }} color="var(--success)" label="Leading" />
      <QuadrantLabel pos={{ top: 8, left: 24 }} color="var(--cyan)" label="Improving" />
      <QuadrantLabel pos={{ bottom: 56, right: 24 }} color="var(--amber)" label="Weakening" />
      <QuadrantLabel pos={{ bottom: 56, left: 24 }} color="var(--danger)" label="Lagging" />
    </div>
  );
}

function QuadrantLabel({ pos, color, label }) {
  return (
    <div style={{
      position: 'absolute', ...pos,
      fontSize: 'var(--t-2xs)', fontWeight: 'var(--w-bold)',
      color, letterSpacing: '0.08em', textTransform: 'uppercase',
      pointerEvents: 'none',
    }}>{label}</div>
  );
}

// ─── Sector momentum spider chart ──────────────────────────────────────────
function MomentumSpider({ sectors }) {
  // Pick top-6 by current rank for legibility
  const data = useMemo(() => {
    if (!sectors || sectors.length === 0) return [];
    const top = sectors.slice()
      .filter(s => s.current_rank != null)
      .sort((a, b) => (a.current_rank ?? 999) - (b.current_rank ?? 999))
      .slice(0, 6);
    if (top.length === 0) return [];
    const axes = [
      { key: 'performance_1d', label: '1D' },
      { key: 'performance_5d', label: '5D' },
      { key: 'performance_20d', label: '20D' },
    ];
    // For each axis, build one row with all sectors as series
    return axes.map(a => {
      const row = { axis: a.label };
      for (const s of top) {
        const name = s.sector_name || s.sector;
        const v = s[a.key];
        row[name] = v == null ? 0 : Number(v);
      }
      return row;
    });
  }, [sectors]);

  const sectorNames = useMemo(() => {
    if (data.length === 0) return [];
    return Object.keys(data[0]).filter(k => k !== 'axis');
  }, [data]);

  if (data.length === 0 || sectorNames.length === 0) {
    return <Empty title="No sector momentum data" />;
  }

  return (
    <div style={{ width: '100%', height: 320 }}>
      <ResponsiveContainer width="100%" height="100%">
        <RadarChart data={data}>
          <PolarGrid stroke="var(--border-soft)" />
          <PolarAngleAxis dataKey="axis" stroke="var(--text-3)" fontSize={11} />
          <PolarRadiusAxis stroke="var(--text-3)" fontSize={10}
                           tickFormatter={(v) => `${v}%`} />
          <Tooltip contentStyle={TT_STYLE}
            formatter={(v) => [`${Number(v).toFixed(2)}%`, '']} />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          {sectorNames.map((name, i) => (
            <Radar key={name} dataKey={name} stroke={colorFor(name, i)}
                   fill={colorFor(name, i)} fillOpacity={0.15} strokeWidth={2}
                   isAnimationActive={false} />
          ))}
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}

// ─── Sector vs SPY relative line chart ─────────────────────────────────────
// Single batched fetch — fixed slot count so we never violate rules-of-hooks.
function SectorRelativeChart({ sectors }) {
  const top = useMemo(() => {
    if (!sectors) return [];
    return sectors
      .filter(s => s.sector_name || s.sector)
      .slice(0, 8)
      .map(s => s.sector_name || s.sector);
  }, [sectors]);

  // One query that fans out internally — keeps hook count constant
  const { data: merged, isLoading } = useQuery({
    queryKey: ['sector-relative-90', top.join('|')],
    queryFn: async () => {
      if (top.length === 0) return [];
      const results = await Promise.all(top.map(name =>
        api.get(`/api/sectors/${encodeURIComponent(name)}/trend?days=90`)
           .then(r => ({ name, trendData: (r.data?.data || r.data)?.trendData || [] }))
           .catch(() => ({ name, trendData: [] }))
      ));
      const all = {};
      for (const { name, trendData } of results) {
        if (!trendData || trendData.length === 0) continue;
        const first = Number(trendData[0].avgPrice) || 1;
        for (const r of trendData) {
          const dateKey = String(r.date).slice(0, 10);
          if (!all[dateKey]) all[dateKey] = { date: dateKey };
          const indexed = first > 0 ? (Number(r.avgPrice) / first) * 100 : 100;
          all[dateKey][name] = Number(indexed.toFixed(2));
        }
      }
      return Object.values(all).sort((a, b) => a.date.localeCompare(b.date));
    },
    enabled: top.length > 0,
    staleTime: 1000 * 60 * 10,
    refetchInterval: 60000,
    retry: false,
  });

  if (isLoading) return <Empty title="Loading…" />;
  if (!merged || merged.length < 2) {
    return <Empty title="No relative-performance data" />;
  }

  return (
    <div style={{ width: '100%', height: 320 }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={merged} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" />
          <XAxis dataKey="date" stroke="var(--text-3)" fontSize={11}
                 interval={Math.max(1, Math.floor(merged.length / 8))}
                 tickFormatter={formatXAxisDate} />
          <YAxis stroke="var(--text-3)" fontSize={11} width={48}
                 tickFormatter={(v) => v.toFixed(0)} />
          <Tooltip contentStyle={TT_STYLE}
            labelFormatter={(l) => formatXAxisDate(l)}
            formatter={(v) => [v, '']} />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          <ReferenceLine y={100} stroke="var(--border)" strokeDasharray="3 3" />
          {top.map((name, i) => (
            <Line key={name} type="monotone" dataKey={name}
                  stroke={colorFor(name, i)} strokeWidth={1.75}
                  dot={false} connectNulls isAnimationActive={false} />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

// ─── Sector breadth (% above 50d / 200d MA) ────────────────────────────────
function SectorBreadthChart() {
  const { data, isLoading } = useQuery({
    queryKey: ['sector-breadth'],
    queryFn: () => api.get('/api/algo/sector-breadth')
                      .then(r => r.data?.items || []).catch(() => []),
    refetchInterval: 60000,
    retry: false,
  });

  if (isLoading) return <Empty title="Loading breadth…" />;
  if (!data || data.length === 0) return <Empty title="No breadth data" />;

  const sorted = [...data].sort((a, b) => b.pct_above_200d - a.pct_above_200d);

  return (
    <div style={{ width: '100%', height: Math.max(300, sorted.length * 28 + 40) }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={sorted} layout="vertical"
                  margin={{ top: 4, right: 16, left: 4, bottom: 0 }}>
          <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" />
          <XAxis type="number" stroke="var(--text-3)" fontSize={11}
                 domain={[0, 100]} tickFormatter={(v) => `${v}%`} />
          <YAxis type="category" dataKey="sector" stroke="var(--text-3)"
                 fontSize={11} width={130} />
          <Tooltip contentStyle={TT_STYLE}
            formatter={(v, n) => [`${v}%`, n === 'pct_above_50d' ? '> 50D MA' : '> 200D MA']} />
          <Legend wrapperStyle={{ fontSize: 11 }}
                  formatter={(v) => v === 'pct_above_50d' ? '% > 50D MA' : '% > 200D MA'} />
          <Bar dataKey="pct_above_50d" fill="var(--cyan)" radius={[0, 2, 2, 0]} />
          <Bar dataKey="pct_above_200d" fill="var(--brand)" radius={[0, 2, 2, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

// ─── Stage-2 leaders per sector ────────────────────────────────────────────
function Stage2LeadersChart() {
  const { data, isLoading } = useQuery({
    queryKey: ['sector-stage2'],
    queryFn: () => api.get('/api/algo/sector-stage2')
                      .then(r => r.data?.items || []).catch(() => []),
    refetchInterval: 60000,
    retry: false,
  });

  if (isLoading) return <Empty title="Loading…" />;
  if (!data || data.length === 0) {
    return <Empty title="No stage data" desc="Requires trend_template_data coverage." />;
  }
  const sorted = [...data].sort((a, b) => b.pct_stage_2 - a.pct_stage_2);

  return (
    <div style={{ width: '100%', height: Math.max(300, sorted.length * 28 + 40) }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={sorted} layout="vertical"
                  margin={{ top: 4, right: 16, left: 4, bottom: 0 }}>
          <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" />
          <XAxis type="number" stroke="var(--text-3)" fontSize={11}
                 domain={[0, 100]} tickFormatter={(v) => `${v}%`} />
          <YAxis type="category" dataKey="sector" stroke="var(--text-3)"
                 fontSize={11} width={130} />
          <Tooltip contentStyle={TT_STYLE}
            formatter={(v, n, p) => {
              if (n === 'pct_stage_2') {
                return [`${v}% (${p.payload.stage_2}/${p.payload.total} stocks)`, 'Stage-2'];
              }
              return [v, n];
            }} />
          <Bar dataKey="pct_stage_2" fill="var(--success)" radius={[0, 2, 2, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

// ─── Defensive vs Cyclical signal timeline ─────────────────────────────────
function DefensiveCyclicalChart() {
  const { data, isLoading } = useQuery({
    queryKey: ['sector-rotation'],
    queryFn: () => api.get('/api/algo/sector-rotation?limit=180')
                      .then(r => r.data?.items || []).catch(() => []),
    refetchInterval: 60000,
    retry: false,
  });

  if (isLoading) return <Empty title="Loading…" />;
  if (!data || data.length === 0) {
    return <Empty title="Sector rotation signal not yet computed"
                  desc="Run algo_sector_rotation.py to populate." />;
  }

  const series = data.map(d => ({
    date: String(d.date).slice(5, 10),
    defensive: d.defensive_lead_score,
    cyclical: d.cyclical_weak_score,
    spread: d.spread,
  }));

  const last = data[data.length - 1] || {};

  return (
    <div>
      <div className="grid grid-3" style={{ marginBottom: 'var(--space-3)' }}>
        <div className="stile">
          <div className="stile-label">Current Signal</div>
          <div className="stile-value">{last.signal || '—'}</div>
        </div>
        <div className="stile">
          <div className="stile-label">Defensive Lead</div>
          <div className="stile-value">{num(last.defensive_lead_score)}</div>
        </div>
        <div className="stile">
          <div className="stile-label">Persistent</div>
          <div className="stile-value">
            {last.weeks_persistent != null ? `${last.weeks_persistent}w` : '—'}
          </div>
        </div>
      </div>
      <div style={{ width: '100%', height: 260 }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={series} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" />
            <XAxis dataKey="date" stroke="var(--text-3)" fontSize={11}
                   interval={Math.max(1, Math.floor(series.length / 8))} />
            <YAxis stroke="var(--text-3)" fontSize={11} width={36} />
            <Tooltip contentStyle={TT_STYLE} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <ReferenceLine y={0} stroke="var(--border)" />
            <Area type="monotone" dataKey="defensive" stroke="var(--purple)"
                  fill="var(--purple)" fillOpacity={0.2} name="Defensive lead" />
            <Area type="monotone" dataKey="cyclical" stroke="var(--amber)"
                  fill="var(--amber)" fillOpacity={0.15} name="Cyclical weak" />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

// ─── Daily Strength Chart with MA10 + MA20 ─────────────────────────────────
function DailyStrengthChart({ name, type, range }) {
  const endpoint = type === 'sector'
    ? `/api/sectors/${encodeURIComponent(name)}/trend?days=365`
    : `/api/industries/${encodeURIComponent(name)}/trend?days=365`;

  const { data: resp, isLoading } = useQuery({
    queryKey: [`${type}-strength`, name],
    queryFn: () => api.get(endpoint).then(r => r.data?.data || r.data).catch(() => null),
    enabled: !!name,
    staleTime: 1000 * 60 * 10,
    retry: false,
  });

  if (isLoading) return <Empty title="Loading…" />;

  const trendArr = resp?.trendData || [];
  const firstAvgPrice = trendArr[0]?.avgPrice || null;
  const raw = trendArr.map(d => ({
    ...d,
    dailyStrengthScore: d.dailyStrengthScore != null
      ? Number(d.dailyStrengthScore)
      : (firstAvgPrice ? ((Number(d.avgPrice) / firstAvgPrice) - 1) * 100 : null),
  }));
  const enriched = enrichWithMAs(raw);
  const filtered = filterByRange(enriched, range);

  const data = filtered.map(r => ({
    date: r.date,
    price: r.dailyStrengthScore != null ? Number(r.dailyStrengthScore) : null,
    ma_10: r.ma_10 != null ? Number(r.ma_10) : null,
    ma_20: r.ma_20 != null ? Number(r.ma_20) : null,
  })).filter(r => r.price !== null);

  if (data.length === 0) {
    return <Empty title="No daily strength data available" />;
  }

  const xInterval = Math.max(1, Math.floor(data.length / 8));
  const last = data[data.length - 1] || {};
  const aboveMA20 = last.price != null && last.ma_20 != null && last.price > last.ma_20;
  const aboveMA10 = last.price != null && last.ma_10 != null && last.price > last.ma_10;
  const priceColor = aboveMA20 ? 'var(--success)' : aboveMA10 ? 'var(--amber)' : 'var(--danger)';

  return (
    <div style={{ width: '100%', height: 300 }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" />
          <XAxis
            dataKey="date" stroke="var(--text-3)" fontSize={11}
            interval={xInterval} tickFormatter={formatXAxisDate}
          />
          <YAxis stroke="var(--text-3)" fontSize={11} width={50} />
          <Tooltip
            contentStyle={TT_STYLE}
            formatter={(v) => typeof v === 'number' ? v.toFixed(2) : v}
            labelFormatter={(l) => formatXAxisDate(l)}
          />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          <Line type="monotone" dataKey="price" stroke={priceColor} strokeWidth={2.5}
                dot={false} connectNulls name="Daily Strength" isAnimationActive={false} />
          <Line type="monotone" dataKey="ma_10" stroke="var(--cyan)" strokeWidth={1.5}
                strokeDasharray="4 3" dot={false} connectNulls name="MA 10" isAnimationActive={false} />
          <Line type="monotone" dataKey="ma_20" stroke="var(--purple)" strokeWidth={1.5}
                strokeDasharray="4 3" dot={false} connectNulls name="MA 20" isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

// ─── Ranking Trend Chart ───────────────────────────────────────────────────
function RankingTrendChart({ name, type, range }) {
  const endpoint = type === 'sector'
    ? `/api/sectors/${encodeURIComponent(name)}/trend?days=365`
    : `/api/industries/${encodeURIComponent(name)}/trend?days=365`;

  const { data: resp, isLoading } = useQuery({
    queryKey: [`${type}-rank-trend`, name],
    queryFn: () => api.get(endpoint).then(r => r.data?.data || r.data).catch(() => null),
    enabled: !!name,
    staleTime: 1000 * 60 * 10,
    retry: false,
  });

  if (isLoading) return <Empty title="Loading…" />;

  let history = (resp?.trendData || []).map(r => ({
    date: r.date,
    rank: r.rank ?? null,
    momentum: r.dailyStrengthScore != null ? Number(r.dailyStrengthScore)
            : r.momentumScore != null ? Number(r.momentumScore)
            : r.momentum != null ? Number(r.momentum)
            : r.avgPrice != null ? Number(r.avgPrice)
            : null,
  }));
  history = filterByRange(history, range);

  const ranks = history.map(h => h.rank).filter(r => r != null);
  const minR = ranks.length ? Math.min(...ranks) : null;
  const maxR = ranks.length ? Math.max(...ranks) : null;
  const cur = ranks.length ? history[history.length - 1].rank : null;
  const hasMomentum = history.some(h => h.momentum != null);

  if (!ranks.length && !hasMomentum) {
    return <Empty title="No historical trend data available" />;
  }

  return (
    <div className="flex" style={{ flexDirection: 'column', gap: 'var(--space-3)' }}>
      <div className="grid grid-3">
        <div className="stile">
          <div className="stile-label">Current</div>
          <div className="stile-value">#{cur ?? '—'}</div>
        </div>
        <div className="stile">
          <div className="stile-label">Best</div>
          <div className="stile-value up">#{minR ?? '—'}</div>
        </div>
        <div className="stile">
          <div className="stile-label">Worst</div>
          <div className="stile-value down">#{maxR ?? '—'}</div>
        </div>
      </div>

      <div style={{ width: '100%', height: 280 }}>
        {ranks.length > 0 ? (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={history} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
              <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" />
              <XAxis
                dataKey="date" stroke="var(--text-3)" fontSize={11}
                interval={Math.max(1, Math.floor(history.length / 8))}
                tickFormatter={formatXAxisDate}
              />
              <YAxis
                stroke="var(--text-3)" fontSize={11} reversed width={48}
                label={{ value: 'Rank', angle: -90, position: 'insideLeft',
                         fill: 'var(--text-3)', fontSize: 11 }}
              />
              <Tooltip
                contentStyle={TT_STYLE}
                formatter={(v) => `#${v}`}
                labelFormatter={(l) => formatXAxisDate(l)}
              />
              <Line type="monotone" dataKey="rank" stroke="var(--brand)" strokeWidth={2}
                    dot={false} name="Rank" isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={history} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
              <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" />
              <XAxis
                dataKey="date" stroke="var(--text-3)" fontSize={11}
                interval={Math.max(1, Math.floor(history.length / 8))}
                tickFormatter={formatXAxisDate}
              />
              <YAxis stroke="var(--text-3)" fontSize={11} width={48} />
              <Tooltip contentStyle={TT_STYLE} labelFormatter={(l) => formatXAxisDate(l)} />
              <Line type="monotone" dataKey="momentum" stroke="var(--cyan)" strokeWidth={2}
                    dot={false} name="Momentum" connectNulls isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}

// ─── Mini sparkline for table row ──────────────────────────────────────────
function SparklineTrend({ name, type }) {
  const endpoint = type === 'sector'
    ? `/api/sectors/${encodeURIComponent(name)}/trend?days=90`
    : `/api/industries/${encodeURIComponent(name)}/trend?days=90`;

  const { data: resp } = useQuery({
    queryKey: [`${type}-sparkline`, name],
    queryFn: () => api.get(endpoint).then(r => r.data?.data || r.data).catch(() => null),
    enabled: !!name,
    staleTime: 1000 * 60 * 10,
    retry: false,
  });

  const rows = (resp?.trendData || []).filter(r => r.rank != null);
  if (rows.length < 2) return <span className="t-xs muted">—</span>;

  const data = rows.map(r => ({ date: r.date, rank: r.rank }));
  return (
    <div style={{ width: 90, height: 30 }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 2, right: 2, bottom: 2, left: 2 }}>
          <YAxis hide reversed domain={['dataMin', 'dataMax']} />
          <Line type="monotone" dataKey="rank" stroke="var(--brand)"
                strokeWidth={1.5} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

// ─── Top Companies for an industry ─────────────────────────────────────────
function TopCompanies({ industry }) {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const { data, isLoading } = useQuery({
    queryKey: ['industry-top-companies', industry],
    queryFn: () =>
      api.get('/api/scores/stockscores?limit=200&sortBy=composite_score&sortOrder=desc')
        .then(r => r.data?.items || []).catch(() => []),
    enabled: open,
    staleTime: 1000 * 60 * 10,
    retry: false,
  });

  // Filter to industry-matched names if metadata available, else show top
  const filtered = useMemo(() => {
    if (!data) return [];
    const matched = data.filter(d =>
      (d.industry || '').toLowerCase() === (industry || '').toLowerCase()
    );
    return (matched.length ? matched : data).slice(0, 20);
  }, [data, industry]);

  return (
    <div>
      <button
        type="button"
        className="btn btn-outline btn-sm"
        onClick={() => setOpen(!open)}
        style={{ width: '100%', justifyContent: 'space-between' }}
      >
        <span>{open ? 'Hide' : 'Show'} top performing companies</span>
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
      </button>

      {open && (
        <div style={{ marginTop: 'var(--space-3)' }}>
          {isLoading ? (
            <Empty title="Loading companies…" />
          ) : filtered.length === 0 ? (
            <Empty title="No companies found" />
          ) : (
            <div className="grid grid-4">
              {filtered.map(c => (
                <div
                  className="card card-hover"
                  key={c.symbol}
                  onClick={() => navigate(`/app/stock/${c.symbol}`)}
                  style={{ padding: 'var(--space-3)', cursor: 'pointer' }}
                >
                  <div className="flex items-center justify-between">
                    <span className="strong" style={{ fontWeight: 'var(--w-bold)' }}>{c.symbol}</span>
                    {c.composite_score != null && (
                      <span className="badge badge-brand mono tnum t-2xs">
                        {Number(c.composite_score).toFixed(0)}
                      </span>
                    )}
                  </div>
                  <div className="t-xs muted" style={{
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  }}>
                    {(c.company_name || c.fullName || '').substring(0, 40)}
                  </div>
                  {c.price != null && (
                    <div className="t-xs mono tnum" style={{ marginTop: 'var(--space-1)' }}>
                      ${num(c.price)}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Sector drill-down detail panel ────────────────────────────────────────
function SectorDetail({ sector, industries }) {
  const [range, setRange] = useState('3m');
  const name = sector.sector_name || sector.sector;
  const matched = (industries || []).filter(ind => {
    const indSector = (ind.sector || ind.sector_name || '').trim();
    return indSector === name.trim();
  });
  // Top-10 industries within sector (sorted by rank)
  const top10 = matched.slice()
    .sort((a, b) => (a.current_rank ?? 9999) - (b.current_rank ?? 9999))
    .slice(0, 10);

  return (
    <div className="card-body" style={{
      background: 'var(--surface)',
      borderTop: '1px solid var(--border)',
    }}>
      <div className="grid grid-4">
        <Stile label="Rank" value={`#${sector.current_rank || sector.overall_rank || '—'}`} />
        <Stile label="Momentum" value={sector.current_momentum || sector.momentum || '—'} />
        <Stile label="Trend" value={sector.current_trend || sector.trend || '—'} />
        <Stile
          label="Trailing P/E"
          value={sector.pe?.trailing != null ? sector.pe.trailing.toFixed(2) : '—'}
        />
      </div>

      <div className="grid grid-3" style={{ marginTop: 'var(--space-4)' }}>
        <Stile label="1W Ago" value={sector.rank_1w_ago != null ? `#${sector.rank_1w_ago}` : '—'} />
        <Stile label="4W Ago" value={sector.rank_4w_ago != null ? `#${sector.rank_4w_ago}` : '—'} />
        <Stile label="12W Ago" value={sector.rank_12w_ago != null ? `#${sector.rank_12w_ago}` : '—'} />
      </div>

      <div className="card" style={{ marginTop: 'var(--space-4)' }}>
        <div className="card-head">
          <div>
            <div className="card-title">Ranking Trend</div>
            <div className="card-sub">Historical rank position</div>
          </div>
          <TimeRangeChips value={range} onChange={setRange} />
        </div>
        <div className="card-body">
          <RankingTrendChart name={name} type="sector" range={range} />
        </div>
      </div>

      <div className="card" style={{ marginTop: 'var(--space-4)' }}>
        <div className="card-head">
          <div>
            <div className="card-title">Daily Strength</div>
            <div className="card-sub">Price proxy with MA10 / MA20 (color: above MA20 = green)</div>
          </div>
        </div>
        <div className="card-body">
          <DailyStrengthChart name={name} type="sector" range={range} />
        </div>
      </div>

      <div className="card" style={{ marginTop: 'var(--space-4)' }}>
        <div className="card-head">
          <div>
            <div className="card-title">Top 10 Industries within {name}</div>
            <div className="card-sub">Sorted by RS rank · {matched.length} total</div>
          </div>
        </div>
        <div className="card-body">
          {top10.length === 0 ? (
            <div className="t-sm muted">No industries available</div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th className="num">Rank</th>
                  <th>Industry</th>
                  <th className="num">1D %</th>
                  <th className="num">5D %</th>
                  <th className="num">20D %</th>
                  <th className="num">Stocks</th>
                </tr>
              </thead>
              <tbody>
                {top10.map(ind => (
                  <tr key={ind.industry}>
                    <td className="num">
                      <span className="badge badge-brand mono tnum">
                        #{ind.current_rank ?? '—'}
                      </span>
                    </td>
                    <td>
                      <span className="strong" style={{ fontWeight: 'var(--w-semibold)' }}>
                        {ind.industry}
                      </span>
                    </td>
                    <td className="num">
                      <span className={`mono tnum ${pctClass(ind.performance_1d)}`}>
                        {fmtPct(ind.performance_1d)}
                      </span>
                    </td>
                    <td className="num">
                      <span className={`mono tnum ${pctClass(ind.performance_5d)}`}>
                        {fmtPct(ind.performance_5d)}
                      </span>
                    </td>
                    <td className="num">
                      <span className={`mono tnum ${pctClass(ind.performance_20d)}`}>
                        {fmtPct(ind.performance_20d)}
                      </span>
                    </td>
                    <td className="num mono tnum muted">{ind.stock_count || 0}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Industry drill-down detail panel ──────────────────────────────────────
function IndustryDetail({ industry }) {
  const [range, setRange] = useState('3m');
  return (
    <div className="card-body" style={{
      background: 'var(--surface)',
      borderTop: '1px solid var(--border)',
    }}>
      <div className="grid grid-4">
        <Stile label="Sector" value={industry.sector || '—'} />
        <Stile label="Stocks" value={industry.stock_count || 0} />
        <Stile label="Momentum" value={industry.current_momentum || '—'} />
        <Stile label="Trend" value={industry.current_trend || '—'} />
      </div>

      <div className="grid grid-3" style={{ marginTop: 'var(--space-4)' }}>
        <Stile label="1W Ago" value={industry.rank_1w_ago != null ? `#${industry.rank_1w_ago}` : '—'} />
        <Stile label="4W Ago" value={industry.rank_4w_ago != null ? `#${industry.rank_4w_ago}` : '—'} />
        <Stile label="12W Ago" value={industry.rank_12w_ago != null ? `#${industry.rank_12w_ago}` : '—'} />
      </div>

      <div className="card" style={{ marginTop: 'var(--space-4)' }}>
        <div className="card-head">
          <div>
            <div className="card-title">Ranking Trend</div>
            <div className="card-sub">Historical rank position</div>
          </div>
          <TimeRangeChips value={range} onChange={setRange} />
        </div>
        <div className="card-body">
          <RankingTrendChart name={industry.industry} type="industry" range={range} />
        </div>
      </div>

      <div className="card" style={{ marginTop: 'var(--space-4)' }}>
        <div className="card-head">
          <div>
            <div className="card-title">Daily Strength</div>
            <div className="card-sub">Price proxy with MA10 / MA20</div>
          </div>
        </div>
        <div className="card-body">
          <DailyStrengthChart name={industry.industry} type="industry" range={range} />
        </div>
      </div>

      <div className="card" style={{ marginTop: 'var(--space-4)' }}>
        <div className="card-head">
          <div>
            <div className="card-title">Top Performing Companies</div>
            <div className="card-sub">{industry.industry}</div>
          </div>
        </div>
        <div className="card-body">
          <TopCompanies industry={industry.industry} />
        </div>
      </div>
    </div>
  );
}

// ─── Sectors view ──────────────────────────────────────────────────────────
function SectorsView({ sectors, industries, isLoading, error }) {
  const [perfRange, setPerfRange] = useState('1d');
  const [expanded, setExpanded] = useState(null);

  const performanceVal = (s, range) => {
    switch (range) {
      case '5d': return s.current_perf_5d ?? s.performance_5d;
      case '20d': return s.current_perf_20d ?? s.performance_20d;
      case 'ytd': return s.current_perf_ytd ?? s.performance_ytd ?? s.current_perf_1d ?? s.performance_1d;
      default: return s.current_perf_1d ?? s.performance_1d;
    }
  };

  const chartData = useMemo(() => {
    return (sectors || [])
      .filter(s => {
        const name = s.sector_name || s.sector;
        const v = performanceVal(s, perfRange);
        return name && v != null && !isNaN(Number(v));
      })
      .map((s, i) => {
        const name = s.sector_name || s.sector;
        return {
          name: name.length > 16 ? `${name.slice(0, 16)}…` : name,
          fullName: name,
          performance: Number(Number(performanceVal(s, perfRange)).toFixed(2)),
          color: colorFor(name, i),
        };
      })
      .sort((a, b) => b.performance - a.performance);
  }, [sectors, perfRange]);

  const sortedSectors = useMemo(() => {
    return (sectors || [])
      .filter(s => s.sector_name || s.sector)
      .slice()
      .sort((a, b) =>
        (a.current_rank ?? a.overall_rank ?? 999) -
        (b.current_rank ?? b.overall_rank ?? 999)
      );
  }, [sectors]);

  return (
    <>
      {/* Mansfield rotation + Momentum spider */}
      <div className="grid grid-2" style={{ marginBottom: 'var(--space-4)' }}>
        <div className="card">
          <div className="card-head">
            <div>
              <div className="card-title">Relative Strength Rotation</div>
              <div className="card-sub">Quadrant scatter · x: RS-rank %ile · y: 1-week rank Δ · size: stocks</div>
            </div>
          </div>
          <div className="card-body">
            <MansfieldRotation sectors={sortedSectors} />
          </div>
        </div>
        <div className="card">
          <div className="card-head">
            <div>
              <div className="card-title">Top-6 Sector Momentum</div>
              <div className="card-sub">Spider radar · 1D / 5D / 20D returns per top-ranked sector</div>
            </div>
          </div>
          <div className="card-body">
            <MomentumSpider sectors={sortedSectors} />
          </div>
        </div>
      </div>

      {/* Sector vs SPY-style relative line */}
      <div className="card" style={{ marginBottom: 'var(--space-4)' }}>
        <div className="card-head">
          <div>
            <div className="card-title">Sector Relative Performance (90D)</div>
            <div className="card-sub">All series indexed to 100 at start · top-8 ranked sectors</div>
          </div>
        </div>
        <div className="card-body">
          <SectorRelativeChart sectors={sortedSectors} />
        </div>
      </div>

      {/* Breadth + Stage-2 */}
      <div className="grid grid-2" style={{ marginBottom: 'var(--space-4)' }}>
        <div className="card">
          <div className="card-head">
            <div>
              <div className="card-title">Sector Breadth</div>
              <div className="card-sub">% of constituent stocks above 50D / 200D MA</div>
            </div>
          </div>
          <div className="card-body">
            <SectorBreadthChart />
          </div>
        </div>
        <div className="card">
          <div className="card-head">
            <div>
              <div className="card-title">Stage-2 Leaders by Sector</div>
              <div className="card-sub">% of stocks in Stage-2 (markup) phase</div>
            </div>
          </div>
          <div className="card-body">
            <Stage2LeadersChart />
          </div>
        </div>
      </div>

      {/* Defensive vs cyclical */}
      <div className="card" style={{ marginBottom: 'var(--space-4)' }}>
        <div className="card-head">
          <div>
            <div className="card-title">Defensive vs Cyclical Leadership</div>
            <div className="card-sub">Sector rotation signal · risk-off when defensive lead persists</div>
          </div>
        </div>
        <div className="card-body">
          <DefensiveCyclicalChart />
        </div>
      </div>

      {/* Performance bars */}
      <div className="card">
        <div className="card-head">
          <div>
            <div className="card-title">Sector Performance</div>
            <div className="card-sub">Ranked by selected timeframe return</div>
          </div>
          <div className="flex gap-2">
            {[
              { v: '1d', label: 'Daily' },
              { v: '5d', label: '5D' },
              { v: '20d', label: '20D' },
              { v: 'ytd', label: 'YTD' },
            ].map(o => (
              <button
                key={o.v}
                type="button"
                className={`btn btn-sm ${perfRange === o.v ? 'btn-primary' : 'btn-outline'}`}
                onClick={() => setPerfRange(o.v)}
              >
                {o.label}
              </button>
            ))}
          </div>
        </div>
        <div className="card-body" style={{ height: 380 }}>
          {chartData.length === 0 ? (
            <Empty title="No sector performance data" />
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 80 }}>
                <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" />
                <XAxis
                  dataKey="name" stroke="var(--text-3)" fontSize={11}
                  angle={-45} textAnchor="end" height={70} interval={0}
                />
                <YAxis stroke="var(--text-3)" fontSize={11}
                       tickFormatter={(v) => `${v}%`} />
                <Tooltip
                  contentStyle={TT_STYLE}
                  formatter={(v) => [`${v}%`, 'Performance']}
                  labelFormatter={(l, p) => p?.[0]?.payload?.fullName || l}
                />
                <Bar dataKey="performance" radius={[4, 4, 0, 0]}>
                  {chartData.map((d, i) => (
                    <Cell key={i} fill={d.performance >= 0 ? 'var(--success)' : 'var(--danger)'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      <div className="card" style={{ marginTop: 'var(--space-4)' }}>
        <div className="card-head">
          <div>
            <div className="card-title">Sector Rankings</div>
            <div className="card-sub">Click a row to drill into trends, daily strength, top industries</div>
          </div>
        </div>
        <div className="card-body" style={{ padding: 0 }}>
          {error ? (
            <div className="alert alert-warn" style={{ margin: 'var(--space-4)' }}>
              <AlertCircle size={16} /><div>Sector data not available.</div>
            </div>
          ) : isLoading ? (
            <Empty title="Loading sectors…" />
          ) : sortedSectors.length === 0 ? (
            <Empty title="No sector data available" />
          ) : (
            <div style={{ overflow: 'auto' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th></th>
                    <th>Sector</th>
                    <th className="num">Rank</th>
                    <th className="num">1W Ago</th>
                    <th className="num">4W Ago</th>
                    <th className="num">12W Ago</th>
                    <th>Momentum</th>
                    <th>Trend</th>
                    <th className="num">1D %</th>
                    <th className="num">5D %</th>
                    <th className="num">20D %</th>
                    <th>Trend (90d)</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedSectors.map((s, i) => {
                    const name = s.sector_name || s.sector;
                    const key = `${name}-${i}`;
                    const isOpen = expanded === key;
                    const p1 = s.current_perf_1d ?? s.performance_1d;
                    const p5 = s.current_perf_5d ?? s.performance_5d;
                    const p20 = s.current_perf_20d ?? s.performance_20d;
                    return (
                      <React.Fragment key={key}>
                        <tr onClick={() => setExpanded(isOpen ? null : key)}>
                          <td style={{ width: 24 }}>
                            {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                          </td>
                          <td><span className="strong" style={{ fontWeight: 'var(--w-bold)' }}>{name}</span></td>
                          <td className="num">
                            <span className="badge badge-brand mono tnum">
                              #{s.current_rank ?? s.overall_rank ?? '—'}
                            </span>
                          </td>
                          <td className="num mono tnum muted">
                            {s.rank_1w_ago != null ? s.rank_1w_ago : '—'}
                          </td>
                          <td className="num mono tnum muted">
                            {s.rank_4w_ago != null ? s.rank_4w_ago : '—'}
                          </td>
                          <td className="num mono tnum muted">
                            {s.rank_12w_ago != null ? s.rank_12w_ago : '—'}
                          </td>
                          <td>
                            <span className={`badge ${momentumBadge(s.current_momentum || s.momentum)}`}>
                              {s.current_momentum || s.momentum || '—'}
                            </span>
                          </td>
                          <td><TrendIcon trend={s.current_trend || s.trend} /></td>
                          <td className="num">
                            <span className={`mono tnum ${pctClass(p1)}`}>{fmtPct(p1)}</span>
                          </td>
                          <td className="num">
                            <span className={`mono tnum ${pctClass(p5)}`}>{fmtPct(p5)}</span>
                          </td>
                          <td className="num">
                            <span className={`mono tnum ${pctClass(p20)}`}>{fmtPct(p20)}</span>
                          </td>
                          <td><SparklineTrend name={name} type="sector" /></td>
                        </tr>
                        {isOpen && (
                          <tr>
                            <td colSpan={12} style={{ padding: 0 }}>
                              <SectorDetail sector={s} industries={industries} />
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </>
  );
}

// ─── Industries view ───────────────────────────────────────────────────────
function IndustriesView({ industries, isLoading, error }) {
  const [expanded, setExpanded] = useState(null);
  const [search, setSearch] = useState('');

  const sorted = useMemo(() => {
    const q = search.trim().toLowerCase();
    return (industries || [])
      .filter(i => i.industry)
      .filter(i => !q || i.industry.toLowerCase().includes(q) || (i.sector || '').toLowerCase().includes(q))
      .slice()
      .sort((a, b) => (a.current_rank ?? 999) - (b.current_rank ?? 999));
  }, [industries, search]);

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">Industry Rankings</div>
          <div className="card-sub">Click a row to drill into trends and top companies</div>
        </div>
        <input
          className="input"
          placeholder="Search industry or sector"
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{ width: 260 }}
        />
      </div>
      <div className="card-body" style={{ padding: 0 }}>
        {error ? (
          <div className="alert alert-info" style={{ margin: 'var(--space-4)' }}>
            <AlertCircle size={16} />
            <div>Industry performance data is currently loading or unavailable.</div>
          </div>
        ) : isLoading ? (
          <Empty title="Loading industries…" />
        ) : sorted.length === 0 ? (
          <Empty title="No industry data available" />
        ) : (
          <div style={{ overflow: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th></th>
                  <th className="num">Rank</th>
                  <th>Industry</th>
                  <th>Sector</th>
                  <th className="num">1W</th>
                  <th className="num">4W</th>
                  <th className="num">12W</th>
                  <th>Momentum</th>
                  <th>Trend</th>
                  <th className="num">1D %</th>
                  <th className="num">5D %</th>
                  <th className="num">20D %</th>
                  <th className="num">Stocks</th>
                  <th>Trend (90d)</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((ind, i) => {
                  const key = `${ind.industry}-${i}`;
                  const isOpen = expanded === key;
                  return (
                    <React.Fragment key={key}>
                      <tr onClick={() => setExpanded(isOpen ? null : key)}>
                        <td style={{ width: 24 }}>
                          {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                        </td>
                        <td className="num">
                          <span className="badge badge-brand mono tnum">
                            #{ind.current_rank ?? '—'}
                          </span>
                        </td>
                        <td><span className="strong" style={{ fontWeight: 'var(--w-semibold)' }}>{ind.industry}</span></td>
                        <td className="t-xs muted">{ind.sector || '—'}</td>
                        <td className="num mono tnum muted">
                          {ind.rank_1w_ago != null ? ind.rank_1w_ago : '—'}
                        </td>
                        <td className="num mono tnum muted">
                          {ind.rank_4w_ago != null ? ind.rank_4w_ago : '—'}
                        </td>
                        <td className="num mono tnum muted">
                          {ind.rank_12w_ago != null ? ind.rank_12w_ago : '—'}
                        </td>
                        <td>
                          <span className={`badge ${momentumBadge(ind.current_momentum)}`}>
                            {ind.current_momentum || '—'}
                          </span>
                        </td>
                        <td><TrendIcon trend={ind.current_trend} /></td>
                        <td className="num">
                          <span className={`mono tnum ${pctClass(ind.performance_1d)}`}>
                            {fmtPct(ind.performance_1d)}
                          </span>
                        </td>
                        <td className="num">
                          <span className={`mono tnum ${pctClass(ind.performance_5d)}`}>
                            {fmtPct(ind.performance_5d)}
                          </span>
                        </td>
                        <td className="num">
                          <span className={`mono tnum ${pctClass(ind.performance_20d)}`}>
                            {fmtPct(ind.performance_20d)}
                          </span>
                        </td>
                        <td className="num mono tnum muted">{ind.stock_count || 0}</td>
                        <td><SparklineTrend name={ind.industry} type="industry" /></td>
                      </tr>
                      {isOpen && (
                        <tr>
                          <td colSpan={14} style={{ padding: 0 }}>
                            <IndustryDetail industry={ind} />
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
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

// ─── Page root ─────────────────────────────────────────────────────────────
export default function SectorAnalysis() {
  const [tab, setTab] = useState('sectors');

  const sectorsQ = useQuery({
    queryKey: ['sectors-list'],
    queryFn: () => api.get('/api/sectors?limit=500').then(r => r.data?.items || []),
    staleTime: 1000 * 60 * 5,
    refetchInterval: 60000,
    retry: false,
  });
  const industriesQ = useQuery({
    queryKey: ['industries-list'],
    queryFn: () => api.get('/api/industries').then(r => r.data?.items || []),
    staleTime: 1000 * 60 * 5,
    refetchInterval: 60000,
    retry: false,
  });

  const sectors = sectorsQ.data || [];
  const industries = industriesQ.data || [];

  const refresh = () => {
    sectorsQ.refetch();
    industriesQ.refetch();
  };

  return (
    <div className="main-content">
      <div className="page-head">
        <div>
          <div className="page-head-title">Sector Analysis</div>
          <div className="page-head-sub">
            Sector + industry rankings · RS rotation · breadth · stage-2 leaders
          </div>
        </div>
        <div className="page-head-actions">
          <span className="badge badge-brand">{sectors.length} sectors</span>
          <span className="badge">{industries.length} industries</span>
          <button className="btn btn-outline btn-sm" onClick={refresh}>
            <RefreshCw size={14} /> Refresh
          </button>
        </div>
      </div>

      <Tabs
        tabs={[
          { value: 'sectors', label: 'Sectors', count: sectors.length || null },
          { value: 'industries', label: 'Industries', count: industries.length || null },
        ]}
        value={tab}
        onChange={setTab}
      />

      <div style={{ marginTop: 'var(--space-4)' }}>
        {tab === 'sectors' && (
          <SectorsView
            sectors={sectors}
            industries={industries}
            isLoading={sectorsQ.isLoading}
            error={sectorsQ.error}
          />
        )}
        {tab === 'industries' && (
          <IndustriesView
            industries={industries}
            isLoading={industriesQ.isLoading}
            error={industriesQ.error}
          />
        )}
      </div>
    </div>
  );
}

// ─── Tabs / Stile / Empty primitives ───────────────────────────────────────
function Tabs({ tabs, value, onChange }) {
  return (
    <div style={{ display: 'flex', borderBottom: '1px solid var(--border)' }}>
      {tabs.map(t => (
        <button
          key={t.value}
          type="button"
          onClick={() => onChange(t.value)}
          style={{
            background: 'transparent',
            border: 'none',
            borderBottom: `2px solid ${value === t.value ? 'var(--brand)' : 'transparent'}`,
            color: value === t.value ? 'var(--brand-2)' : 'var(--text-muted)',
            fontWeight: value === t.value ? 'var(--w-semibold)' : 'var(--w-medium)',
            fontSize: 'var(--t-sm)',
            padding: '12px 16px',
            cursor: 'pointer',
            marginBottom: -1,
            transition: 'all var(--t-fast)',
          }}
        >
          {t.label}
          {t.count != null && (
            <span className="badge mono tnum" style={{ marginLeft: 8 }}>{t.count}</span>
          )}
        </button>
      ))}
    </div>
  );
}

function Stile({ label, value }) {
  return (
    <div className="stile">
      <div className="stile-label">{label}</div>
      <div className="stile-value">{value}</div>
    </div>
  );
}

function Empty({ title, desc }) {
  return (
    <div className="empty">
      <Inbox size={36} />
      <div className="empty-title">{title}</div>
      {desc && <div className="empty-desc">{desc}</div>}
    </div>
  );
}

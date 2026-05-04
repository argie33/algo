/**
 * Sector Analysis — sector + industry rankings, daily strength, ranking trend.
 * Pure JSX + theme.css classes.
 */

import React, { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  RefreshCw, Inbox, AlertCircle, ChevronDown, ChevronRight,
  TrendingUp, TrendingDown, Minus,
} from 'lucide-react';
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid,
  ResponsiveContainer, Tooltip, Cell, Legend,
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
  const [open, setOpen] = useState(false);
  const { data, isLoading } = useQuery({
    queryKey: ['industry-top-companies', industry],
    queryFn: () =>
      api.get('/api/scores/stockscores?limit=20&sortBy=composite_score&sortOrder=desc')
        .then(r => r.data?.items || []).catch(() => []),
    enabled: open,
    staleTime: 1000 * 60 * 10,
    retry: false,
  });

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
          ) : !data || data.length === 0 ? (
            <Empty title="No companies found" />
          ) : (
            <div className="grid grid-4">
              {data.map(c => (
                <div className="card" key={c.symbol} style={{ padding: 'var(--space-3)' }}>
                  <div className="strong" style={{ fontWeight: 'var(--w-bold)' }}>{c.symbol}</div>
                  <div className="t-xs muted" style={{
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  }}>
                    {(c.company_name || c.fullName || '').substring(0, 40)}
                  </div>
                  {c.price?.current && (
                    <div className="t-xs mono tnum" style={{ marginTop: 'var(--space-1)' }}>
                      ${num(c.price.current)}
                    </div>
                  )}
                  {c.marketCap && (
                    <div className="t-2xs muted mono">
                      ${(c.marketCap / 1e9).toFixed(1)}B
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
            <div className="card-title">Industries ({matched.length})</div>
            <div className="card-sub">Members of {name}</div>
          </div>
        </div>
        <div className="card-body">
          {matched.length === 0 ? (
            <div className="t-sm muted">No industries available</div>
          ) : (
            <div className="grid grid-3">
              {matched
                .slice()
                .sort((a, b) => (a.current_rank ?? 9999) - (b.current_rank ?? 9999))
                .map(ind => (
                  <div key={ind.industry} className="card" style={{ padding: 'var(--space-3)' }}>
                    <div className="t-xs muted">#{ind.current_rank ?? '—'}</div>
                    <div className="strong t-sm" style={{ fontWeight: 'var(--w-semibold)' }}>
                      {ind.industry}
                    </div>
                    <div className="t-xs muted" style={{ marginTop: 'var(--space-1)' }}>
                      <span className={`mono tnum ${pctClass(ind.performance_1d)}`}>
                        {fmtPct(ind.performance_1d)}
                      </span>
                      <span className="muted"> · {ind.stock_count || 0} stocks</span>
                    </div>
                  </div>
                ))}
            </div>
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
            <div className="card-sub">Click a row to drill into trends, daily strength, industries</div>
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
    retry: false,
  });
  const industriesQ = useQuery({
    queryKey: ['industries-list'],
    queryFn: () => api.get('/api/industries').then(r => r.data?.items || []),
    staleTime: 1000 * 60 * 5,
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
            Sector + industry rankings · Mansfield RS · daily strength · ranking trend
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
